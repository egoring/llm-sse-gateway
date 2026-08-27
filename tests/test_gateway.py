# 게이트웨이 폴백·SSE 스트리밍 테스트 — 모의 백엔드로 네트워크 없이 검증한다
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llm_sse_gateway.app import create_app
from llm_sse_gateway.backends import BackendError
from llm_sse_gateway.gateway import stream_chat, to_sse


class FakeBackend:
    """정해진 토큰을 흘리거나, 지정 지점에서 실패하는 모의 백엔드."""

    def __init__(self, name: str, tokens: list[str] | None = None, fail_after: int | None = None) -> None:
        """tokens=None이면 즉시 실패, fail_after=n이면 n개 토큰 후 실패한다."""
        self.name = name
        self.tokens = tokens
        self.fail_after = fail_after

    async def stream(self, prompt: str):
        """모의 토큰 스트림 — 실패 시나리오를 재현한다."""
        if self.tokens is None:
            raise BackendError(f"{self.name}: 연결 실패")
        for i, tok in enumerate(self.tokens):
            if self.fail_after is not None and i >= self.fail_after:
                raise BackendError(f"{self.name}: 스트리밍 중 끊김")
            yield tok


async def collect(gen) -> list[dict]:
    """비동기 이벤트 제너레이터를 리스트로 수집한다."""
    return [e async for e in gen]


@pytest.mark.anyio
async def test_primary_streams_tokens():
    """정상 경로 — backend·token·done 순서로 이벤트가 나간다."""
    events = await collect(stream_chat([FakeBackend("primary", ["안", "녕"])], "hi"))
    kinds = [e["event"] for e in events]
    assert kinds == ["backend", "token", "token", "done"]
    assert events[0]["data"]["name"] == "primary"
    assert events[-1]["data"]["tokens"] == 2


@pytest.mark.anyio
async def test_dead_primary_falls_back():
    """primary 즉사 시 fallback 백엔드로 투명 전환된다."""
    chain = [FakeBackend("primary", None), FakeBackend("fallback", ["폴", "백"])]
    events = await collect(stream_chat(chain, "hi"))
    assert events[0] == {"event": "backend", "data": {"name": "fallback"}}
    assert [e["event"] for e in events] == ["backend", "token", "token", "done"]


@pytest.mark.anyio
async def test_all_backends_dead_yields_error():
    """전 백엔드 실패 시 partial=false인 error 하나로 끝난다."""
    chain = [FakeBackend("primary", None), FakeBackend("fallback", None)]
    events = await collect(stream_chat(chain, "hi"))
    assert [e["event"] for e in events] == ["error"]
    assert events[0]["data"]["partial"] is False


@pytest.mark.anyio
async def test_midstream_failure_does_not_fall_back():
    """토큰 송출 후 실패는 폴백 없이 부분 응답 error로 끝난다."""
    # 토큰을 이미 내보낸 뒤의 실패는 폴백하면 안 된다 — 부분 응답 error로 끝나야 한다
    chain = [FakeBackend("primary", ["일", "부", "응답"], fail_after=2), FakeBackend("fallback", ["새", "응", "답"])]
    events = await collect(stream_chat(chain, "hi"))
    kinds = [e["event"] for e in events]
    assert kinds == ["backend", "token", "token", "error"]
    assert events[-1]["data"]["partial"] is True
    assert "fallback" not in str(events)  # 폴백 백엔드는 호출조차 되지 않는다


def test_to_sse_wire_format():
    """이벤트 dict가 SSE 와이어 포맷 문자열로 정확히 변환된다."""
    line = to_sse({"event": "token", "data": {"text": "안녕"}})
    assert line == 'event: token\ndata: {"text": "안녕"}\n\n'


def _client(chain) -> TestClient:
    """모의 백엔드 체인을 물린 TestClient를 만든다."""
    return TestClient(create_app(backends=chain))


def test_http_endpoint_streams_sse():
    """HTTP 엔드포인트가 text/event-stream으로 SSE를 흘린다."""
    client = _client([FakeBackend("primary", ["하", "이"])])
    with client.stream("POST", "/v1/chat", json={"prompt": "인사해줘"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "event: backend" in body and "event: done" in body
    assert body.count("event: token") == 2


def test_http_endpoint_fallback_visible_to_client():
    """클라이언트가 backend 이벤트로 폴백 사실을 알 수 있다."""
    client = _client([FakeBackend("primary", None), FakeBackend("fallback", ["ok"])])
    with client.stream("POST", "/v1/chat", json={"prompt": "x"}) as resp:
        body = "".join(resp.iter_text())
    assert '"name": "fallback"' in body


def test_empty_prompt_rejected():
    """빈 프롬프트는 422로 거절된다."""
    client = _client([FakeBackend("primary", ["x"])])
    assert client.post("/v1/chat", json={"prompt": ""}).status_code == 422


def test_healthz_lists_chain():
    """healthz가 구성된 백엔드 체인을 나열한다."""
    client = _client([FakeBackend("primary", ["x"]), FakeBackend("fallback", ["y"])])
    data = client.get("/healthz").json()
    assert data == {"ok": True, "backends": ["primary", "fallback"]}
