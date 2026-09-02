# llm-sse-gateway

[![CI](https://github.com/egoring/llm-sse-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/egoring/llm-sse-gateway/actions/workflows/ci.yml)

> English: [README.en.md](README.en.md)

**LLM 응답을 SSE로 스트리밍하는 FastAPI 게이트웨이 — 백엔드가 죽어도 채팅은 살아야 한다.**

로컬 vLLM 같은 primary 백엔드가 다운되면 첫 토큰이 나가기 전에 fallback 백엔드로 투명하게 전환합니다. 실서비스 LLM 챗봇 백엔드를 운영하며 겪은 "모델 서버는 언젠가 죽는다"를 코드로 옮긴 것입니다.

## 이런 상황에서 씁니다

**상황** — 사내 GPU 서버의 vLLM으로 챗봇을 운영한다. GPU 재시작·OOM·모델 교체 때마다 챗봇이 통째로 죽는다. 그렇다고 전부 외부 API로 돌리면 비용이 상시 발생한다.

**도입 후** — 게이트웨이를 앞에 세우면 평소엔 로컬 vLLM(추가 비용 0), 장애 순간에만 외부 API로 자동 전환된다. 프론트엔드는 게이트웨이 하나만 바라보므로 백엔드 교체·장애가 사용자에게 드러나지 않는다 — 실서비스 LLM 챗봇 백엔드를 운영하며 겪은 문제를 그대로 옮긴 구성이다.

## 폴백 규칙 — 이 저장소의 핵심 설계

| 실패 시점 | 동작 | 이유 |
|---|---|---|
| **첫 토큰 전** | 다음 백엔드로 투명 폴백 | 사용자는 아무것도 못 봤으므로 어떤 백엔드가 답해도 무방 |
| **스트리밍 중** | 폴백하지 않고 `error` 이벤트(부분 응답 표시)로 종료 | 다른 모델이 이어 쓰면 앞뒤가 안 맞는 응답이 된다 — 어중간한 이어붙이기보다 정직한 실패 |

클라이언트는 `backend` 이벤트로 어느 백엔드가 응답 중인지 항상 알 수 있습니다.

## SSE 이벤트 프로토콜

```
event: backend   data: {"name": "primary"}          ← 사용 백엔드 확정
event: token     data: {"text": "안"}                ← 토큰 델타 (반복)
event: done      data: {"backend": "primary", "tokens": 42}
event: error     data: {"message": "...", "partial": true|false}
```

## 설치·실행

```bash
pip install -e .

export GW_PRIMARY_BASE="http://localhost:8000/v1"    # vLLM
export GW_PRIMARY_MODEL="Qwen/Qwen2.5-7B-Instruct-AWQ"
export GW_FALLBACK_BASE="https://api.openai.com/v1"  # 선택 — 없으면 폴백 없음
export GW_FALLBACK_KEY="sk-..."
export GW_FALLBACK_MODEL="gpt-4o-mini"

llm-sse-gateway   # 127.0.0.1:8080
```

```bash
curl -N localhost:8080/v1/chat -H 'Content-Type: application/json' -d '{"prompt": "안녕이라고 해줘"}'
curl localhost:8080/healthz    # {"ok": true, "backends": ["primary", "fallback"]}
```

파이썬 클라이언트 예시는 [examples/client.py](examples/client.py)에 있습니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest   # 9건, 네트워크 불필요 — 정상 스트리밍, 사망 폴백, 전멸 에러, 중간 실패 비폴백, SSE 포맷
```

모의 백엔드를 주입해 폴백 체인의 네 시나리오(정상 / primary 사망 / 전원 사망 / 스트리밍 중 끊김)를 전부 검증합니다.

## 함께 보기

- [log-triage-agent](https://github.com/egoring/log-triage-agent) — LangGraph 로그 트리아지 에이전트
- [judge-mcp](https://github.com/egoring/judge-mcp) — LLM-as-Judge 평가 MCP 서버
- [sql-guard-mcp](https://github.com/egoring/sql-guard-mcp) — AI 에이전트용 읽기 전용 SQL 가드

## 라이선스

MIT
