# OpenAI 호환 스트리밍 백엔드 — vLLM·Ollama·OpenAI 모두 같은 인터페이스로 다룬다
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

CONNECT_TIMEOUT = 5.0    # 연결은 짧게 — 죽은 백엔드는 빨리 포기하고 폴백으로
READ_TIMEOUT = 120.0     # 토큰 생성은 길게


class BackendError(RuntimeError):
    """백엔드 호출 실패 — 게이트웨이가 폴백 판단에 쓰는 예외."""


class OpenAIStreamBackend:
    """OpenAI 호환 /chat/completions 스트리밍 백엔드 하나를 감싼다."""

    def __init__(self, name: str, api_base: str, api_key: str = "", model: str = "") -> None:
        """이름(로그·이벤트 표시용)과 접속 정보를 받는다."""
        self.name = name
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """토큰 델타를 순서대로 낸다. 연결·상태 오류는 BackendError로 바꿔 던진다."""
        timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key or 'local'}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread())[:200]
                        raise BackendError(f"{self.name}: HTTP {resp.status_code} — {body!r}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        delta = json.loads(payload)["choices"][0].get("delta", {}).get("content")
                        if delta:
                            yield delta
        except httpx.HTTPError as e:
            raise BackendError(f"{self.name}: 연결 실패 — {e}") from e


def backends_from_env() -> list[OpenAIStreamBackend]:
    """환경 변수에서 primary·fallback 백엔드 체인을 만든다.

    GW_PRIMARY_BASE / GW_PRIMARY_KEY / GW_PRIMARY_MODEL   (필수)
    GW_FALLBACK_BASE / GW_FALLBACK_KEY / GW_FALLBACK_MODEL (선택 — 없으면 폴백 없음)
    """
    primary_base = os.environ.get("GW_PRIMARY_BASE", "")
    if not primary_base:
        raise BackendError("GW_PRIMARY_BASE가 설정되지 않았습니다. 예: http://localhost:8000/v1 (vLLM)")
    chain = [OpenAIStreamBackend(
        "primary", primary_base,
        os.environ.get("GW_PRIMARY_KEY", ""), os.environ.get("GW_PRIMARY_MODEL", ""),
    )]
    if os.environ.get("GW_FALLBACK_BASE"):
        chain.append(OpenAIStreamBackend(
            "fallback", os.environ["GW_FALLBACK_BASE"],
            os.environ.get("GW_FALLBACK_KEY", ""), os.environ.get("GW_FALLBACK_MODEL", ""),
        ))
    return chain
