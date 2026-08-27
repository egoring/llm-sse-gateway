# llm-sse-gateway

[![CI](https://github.com/egoring/llm-sse-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/egoring/llm-sse-gateway/actions/workflows/ci.yml)

> 한국어: [README.md](README.md)

**A FastAPI gateway that streams LLM responses over SSE — chat must survive a dead backend.**

When the primary backend (e.g., local vLLM) is down, the gateway transparently falls back to the next backend — but only before the first token. Born from operating a production LLM chatbot backend: model servers die eventually.

## The fallback rule — the core design

| Failure point | Behavior | Why |
|---|---|---|
| **Before first token** | Transparent fallback to next backend | The user saw nothing yet; any backend may answer |
| **Mid-stream** | No fallback; emit `error` with `partial: true` | Another model continuing the text produces incoherent output — honest failure beats a stitched answer |

Clients always know which backend is answering via the `backend` event.

## SSE protocol

```
event: backend   data: {"name": "primary"}
event: token     data: {"text": "..."}      (repeated)
event: done      data: {"backend": "primary", "tokens": 42}
event: error     data: {"message": "...", "partial": true|false}
```

## Install & run

```bash
pip install -e .

export GW_PRIMARY_BASE="http://localhost:8000/v1"    # vLLM
export GW_PRIMARY_MODEL="Qwen/Qwen2.5-7B-Instruct-AWQ"
export GW_FALLBACK_BASE="https://api.openai.com/v1"  # optional
export GW_FALLBACK_KEY="sk-..."
export GW_FALLBACK_MODEL="gpt-4o-mini"

llm-sse-gateway   # 127.0.0.1:8080
curl -N localhost:8080/v1/chat -H 'Content-Type: application/json' -d '{"prompt": "say hi"}'
```

## Tests

```bash
pip install -e ".[dev]"
pytest   # 9 tests, no network — happy path, dead-primary fallback, all-dead error, mid-stream no-fallback, wire format
```

## See also

- [log-triage-agent](https://github.com/egoring/log-triage-agent) — LangGraph log triage agent
- [judge-mcp](https://github.com/egoring/judge-mcp) — LLM-as-Judge evaluation MCP server
- [sql-guard-mcp](https://github.com/egoring/sql-guard-mcp) — read-only SQL guard for AI agents

## License

MIT
