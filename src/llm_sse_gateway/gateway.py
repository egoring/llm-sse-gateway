# 폴백 체인 핵심 로직 — 첫 토큰 전 실패는 다음 백엔드로, 중간 실패는 정직하게 에러로
from __future__ import annotations

from collections.abc import AsyncIterator

from .backends import BackendError


async def stream_chat(backends: list, prompt: str) -> AsyncIterator[dict]:
    """백엔드 체인을 순서대로 시도하며 SSE용 이벤트 dict를 낸다.

    이벤트: backend(사용 백엔드 확정) → token(델타)* → done / error

    폴백 규칙: 아직 토큰을 하나도 내보내지 않았을 때의 실패만 다음 백엔드로 넘어간다.
    토큰을 이미 내보낸 뒤의 실패는 폴백하지 않는다 — 다른 모델로 이어 쓰면 앞뒤가
    안 맞는 응답이 되므로, 부분 응답임을 알리는 error 이벤트로 정직하게 끝낸다.
    """
    last_error: BackendError | None = None
    for backend in backends:
        sent = 0
        try:
            async for token in backend.stream(prompt):
                if sent == 0:
                    yield {"event": "backend", "data": {"name": backend.name}}
                sent += 1
                yield {"event": "token", "data": {"text": token}}
            if sent == 0:
                yield {"event": "backend", "data": {"name": backend.name}}
            yield {"event": "done", "data": {"backend": backend.name, "tokens": sent}}
            return
        except BackendError as e:
            last_error = e
            if sent > 0:
                yield {"event": "error", "data": {"message": f"스트리밍 중단 (부분 응답 {sent}토큰): {e}", "partial": True}}
                return
            # 첫 토큰 전 실패 -> 다음 백엔드로 폴백
    yield {"event": "error", "data": {"message": f"모든 백엔드가 실패했습니다: {last_error}", "partial": False}}


def to_sse(event: dict) -> str:
    """이벤트 dict 하나를 SSE 와이어 포맷 문자열로 바꾼다."""
    import json

    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
