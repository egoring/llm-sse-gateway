# FastAPI 앱 — POST /v1/chat 을 SSE 스트림으로 응답한다
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .backends import backends_from_env
from .gateway import stream_chat, to_sse


class ChatRequest(BaseModel):
    """채팅 요청 본문."""

    prompt: str = Field(min_length=1, description="사용자 프롬프트")


def create_app(backends: list | None = None) -> FastAPI:
    """앱을 만든다. backends 주입 시 그대로 사용 (테스트용), 없으면 환경 변수에서 구성."""
    app = FastAPI(title="llm-sse-gateway", version="0.1.0")
    app.state.backends = backends

    def _chain() -> list:
        """요청 시점에 백엔드 체인을 확정한다 — 환경 변수 변경 즉시 반영."""
        return app.state.backends if app.state.backends is not None else backends_from_env()

    @app.post("/v1/chat")
    async def chat(req: ChatRequest) -> StreamingResponse:
        """프롬프트 하나를 받아 토큰을 SSE로 흘려보낸다."""

        async def event_source():
            """게이트웨이 이벤트를 SSE 와이어 포맷으로 변환해 흘린다."""
            async for event in stream_chat(_chain(), req.prompt):
                yield to_sse(event)

        return StreamingResponse(event_source(), media_type="text/event-stream")

    @app.get("/healthz")
    async def healthz() -> dict:
        """게이트웨이 상태와 구성된 백엔드 체인을 돌려준다."""
        try:
            names = [b.name for b in _chain()]
        except Exception as e:  # 설정 오류도 상태로 보여준다
            return {"ok": False, "error": str(e)}
        return {"ok": True, "backends": names}

    return app


app = create_app()


def main() -> None:
    """uvicorn으로 서버를 띄운다 (개발용 진입점)."""
    import uvicorn

    uvicorn.run("llm_sse_gateway.app:app", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
