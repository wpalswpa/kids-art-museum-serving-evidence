"""큐에서 작품을 하나씩 가져와 모델을 부르고 규칙(fallback.apply)으로 상태를 바꾼다.

모델 응답을 규칙의 분류로 바꾸는 곳은 classify() 한 곳이다(platform.md 3절).
"""
import json
import os
import time
from pathlib import Path

import jsonschema
import pymysql
import requests
from prometheus_client import start_http_server

import db
import fallback as f
from obs import ATTEMPTS, DURATION, JOBS, RETRIES, event, logger

log = logger("worker")
MODEL_URL = os.environ.get("MODEL_URL", "http://model:8001")
MODEL_TIMEOUT = float(os.environ.get("MODEL_TIMEOUT", "1.0"))
LEASE_SECONDS = 30
SCHEMA = json.loads((Path(__file__).resolve().parent / "contracts" / "model_response.schema.json").read_text(encoding="utf-8"))


def classify(art_id, title, stage):
    """모델을 한 번 부르고 (분류, 지연 ms)를 돌려준다."""
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{MODEL_URL}/render", json={"artwork_id": art_id, "title": title, "stage": stage}, timeout=MODEL_TIMEOUT)
        if r.status_code != 200:  # 503 포함: 모델 서버가 결과를 못 냄
            kind = "engine_down"
        else:
            try:
                body = r.json()
                jsonschema.validate(body, SCHEMA)
                kind = body["status"]
            # 깨진 JSON·스키마 불일치는 모델 품질 부족과 구분한다.
            # fallback.apply는 이를 같은 단계 재시도로 처리한다(결정 004).
            except (ValueError, jsonschema.ValidationError):
                kind = "invalid_response"
    except requests.Timeout:
        kind = "timeout"
    except requests.ConnectionError:
        kind = "engine_down"
    return kind, round((time.perf_counter() - t0) * 1000)


def claim(conn):
    # 잠긴 행은 건너뛰고 임대 시간을 기록해 중단된 작업을 다시 가져올 수 있게 한다.
    # 임대 갱신·중복 모델 호출 방지까지 보장하지 않는다. 공개 재현은 워커 1개다.
    with conn.cursor() as cur:
        cur.execute("""SELECT * FROM artworks WHERE status='queued' OR (status='running' AND lease_until < NOW(3))
                       ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED""")
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE artworks SET status='running', lease_until=NOW(3) + INTERVAL %s SECOND WHERE id=%s",
                        (LEASE_SECONDS, row["id"]))
    conn.commit()
    return row


def process(conn, row):
    art = f.Artwork(wanted=row["wanted"])
    art.target, art.attempts, art.result = row["target"], row["stage_attempts"], row["result"]
    art.causes = json.loads(row["causes"])
    stage = art.target
    kind, latency = classify(row["id"], row["title"], stage)
    f.apply(art, kind)
    attempt = art.log[-1][2]
    ATTEMPTS.labels(stage, kind).inc()
    if kind in f.INFRA_ERRORS and not art.closed:
        RETRIES.inc()
    status = "done" if art.result else ("not_delivered" if f.NOT_DELIVERED in art.causes else "queued")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO attempts (artwork_id, stage, classification, attempt, latency_ms) VALUES (%s,%s,%s,%s,%s)",
                    (row["id"], stage, kind, attempt, latency))
        cur.execute("UPDATE artworks SET target=%s, stage_attempts=%s, result=%s, causes=%s, status=%s, lease_until=NULL WHERE id=%s",
                    (art.target, art.attempts, art.result, json.dumps(art.causes), status, row["id"]))
        if status in ("done", "not_delivered"):
            cur.execute("SELECT TIMESTAMPDIFF(MICROSECOND, created_at, NOW(3)) AS us FROM artworks WHERE id=%s", (row["id"],))
            DURATION.observe(cur.fetchone()["us"] / 1e6)
    # 시도 기록과 상태를 한 트랜잭션으로 저장한 뒤 완료 지표를 올린다.
    # 메모리 지표는 재시작·DB 장애 때 DB와 영구히 일치하는 원장이 아니다.
    conn.commit()
    if status in ("done", "not_delivered"):
        JOBS.labels(status if status == "not_delivered" else f"done_{art.result}").inc()
    event(log, "attempt", job_id=row["id"], stage=stage, attempt=attempt, classification=kind, latency_ms=latency,
          status=status, causes=art.causes)


def main():
    start_http_server(9101)
    db.init()
    event(log, "worker started", model_url=MODEL_URL, model_timeout_s=MODEL_TIMEOUT)
    conn = None
    while True:
        try:
            conn = conn or db.connect()
            row = claim(conn)
            if row:
                process(conn, row)
            else:
                time.sleep(0.2)
        except pymysql.MySQLError as exc:
            event(log, "db unavailable", error=type(exc).__name__)
            if conn:
                try:
                    conn.close()
                except pymysql.MySQLError as close_exc:
                    event(log, "close failed", error=type(close_exc).__name__)
            conn = None
            time.sleep(1)


if __name__ == "__main__":
    main()
