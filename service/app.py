"""작품 올리기·조회·결과 확인 API. 계약은 contracts/openapi.yaml."""
import json
import time
import uuid

import pymysql
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

import db
import fallback as f
from obs import HTTP_REQUESTS, event, logger

log = logger("api")
app = FastAPI(title="kids-art-museum job API")
KINDS = {"animated", "sculpture", "relief", "frame"}


def error(status, code, request, detail=None):
    body = {"error": code, "request_id": request.state.request_id}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status)


@app.on_event("startup")
def startup():
    db.init()


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except pymysql.MySQLError as exc:
        response = error(503, "db_unavailable", request, type(exc).__name__)
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    response.headers["X-Request-ID"] = request.state.request_id
    if path != "/metrics":
        HTTP_REQUESTS.labels(path, str(response.status_code)).inc()
        event(log, "request", request_id=request.state.request_id, method=request.method, route=path,
              status=response.status_code, latency_ms=round((time.perf_counter() - t0) * 1000))
    return response


@app.exception_handler(pymysql.MySQLError)
async def db_down(request, exc):
    return error(503, "db_unavailable", request, type(exc).__name__)


@app.exception_handler(RequestValidationError)
async def invalid(request, exc):
    return error(422, "invalid_request", request, "; ".join(e["msg"] for e in exc.errors())[:200])


def load(cur, art_id):
    cur.execute("SELECT * FROM artworks WHERE id=%s", (art_id,))
    row = cur.fetchone()
    if not row:
        return None
    cur.execute("SELECT * FROM attempts WHERE artwork_id=%s ORDER BY id", (art_id,))
    return db.row_to_artwork(row, cur.fetchall())


@app.post("/artworks", status_code=201)
def upload(body: dict, request: Request):
    wanted, title = body.get("wanted"), body.get("title")
    if set(body) - {"wanted", "title"} or wanted not in KINDS or not isinstance(title, str) or not 1 <= len(title) <= 120:
        return error(422, "invalid_request", request, "wanted는 animated|sculpture|relief|frame, title은 1~120자")
    art = f.upload(wanted)  # 원본 액자로 먼저 건다(결정 001)
    status = "done" if art.result else "queued"
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO artworks (title, wanted, on_wall, target, result, causes, status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (title, wanted, art.on_wall, art.target, art.result, json.dumps(art.causes), status))
            art_id = cur.lastrowid
            conn.commit()
            out = load(cur, art_id)
    finally:
        conn.close()
    event(log, "uploaded", request_id=request.state.request_id, job_id=art_id, wanted=wanted, status=status)
    return JSONResponse(out, status_code=201)


@app.get("/artworks/{art_id}")
def get(art_id: int, request: Request):
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            out = load(cur, art_id)
    finally:
        conn.close()
    return out if out else error(404, "not_found", request)


@app.post("/artworks/{art_id}/confirm")
def confirm(art_id: int, body: dict, request: Request):
    choice = body.get("choice")
    if set(body) != {"choice"} or choice not in KINDS:
        return error(422, "invalid_request", request, "choice는 animated|sculpture|relief|frame")
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM artworks WHERE id=%s FOR UPDATE", (art_id,))
            row = cur.fetchone()
            if not row:
                return error(404, "not_found", request)
            if row["status"] in ("queued", "running"):
                return error(409, "not_ready", request, "결과를 아직 만드는 중")
            art = f.Artwork(wanted=row["wanted"])
            art.on_wall, art.target, art.result = row["on_wall"], row["target"], row["result"]
            art.causes = json.loads(row["causes"])
            try:
                f.confirm(art, choice)
            except ValueError as exc:
                return error(422, "invalid_request", request, str(exc))
            cur.execute("UPDATE artworks SET on_wall=%s, causes=%s WHERE id=%s", (art.on_wall, json.dumps(art.causes), art_id))
            conn.commit()
            out = load(cur, art_id)
    finally:
        conn.close()
    event(log, "confirmed", request_id=request.state.request_id, job_id=art_id, choice=choice)
    return out


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def ready(request: Request):
    try:
        conn = db.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
    except pymysql.MySQLError as exc:
        return error(503, "db_unavailable", request, type(exc).__name__)
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
