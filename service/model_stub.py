"""가짜 모델 서버(시험 전용). 작품 제목의 계획(plan:timeout,ok)대로 호출 순서마다 응답한다."""
import asyncio
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(title="model stub")
calls = defaultdict(int)


@app.post("/render")
async def render(request: Request):
    body = await request.json()
    title, n = body["title"], calls[body["artwork_id"]]
    calls[body["artwork_id"]] += 1
    plan = title.split("plan:", 1)[1].split(",") if "plan:" in title else []
    step = plan[n] if n < len(plan) else "ok"
    if step == "timeout":
        await asyncio.sleep(3)
        return {"status": "ok"}
    if step == "down":
        return JSONResponse({"detail": "engine down"}, status_code=503)
    if step == "invalid":
        return PlainTextResponse("{not json", status_code=200)
    if step == "badfield":
        return {"state": "ok"}
    return {"status": step}


@app.get("/calls/{artwork_id}")
def count(artwork_id: int):
    return {"calls": calls[artwork_id]}
