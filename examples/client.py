# SSE 클라이언트 예시 — 게이트웨이 응답을 이벤트 단위로 읽는다
import httpx

with httpx.stream("POST", "http://127.0.0.1:8080/v1/chat", json={"prompt": "안녕이라고 해줘"}, timeout=120) as r:
    for line in r.iter_lines():
        if line:
            print(line)
