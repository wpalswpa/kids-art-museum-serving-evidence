"""계약 검사와 장애 주입 시험(docs/platform.md 5절). docker compose로 띄운 서비스를 상대로 돈다.

    docker compose up -d --build && API_URL=http://localhost:8000 python -m pytest tests/integration -v

API_URL이 없으면 건너뛴다. DB 중지 시나리오는 COMPOSE=1일 때만 돈다(docker compose 명령이 필요).
"""
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import requests
import yaml

API = os.environ.get("API_URL")
WORKER_METRICS = os.environ.get("WORKER_METRICS_URL", "http://localhost:9101/metrics")
MODEL = os.environ.get("MODEL_URL", "http://localhost:8001")
pytestmark = pytest.mark.skipif(not API, reason="API_URL이 없으면 통합 시험을 건너뛴다")
SPEC = yaml.safe_load((Path(__file__).resolve().parents[2] / "contracts/openapi.yaml").read_text(encoding="utf-8"))
CHECKED = []  # 계약으로 검증한 (메서드, 경로, 상태) 기록


def contract(resp, method, path):
    """실제 응답 본문을 OpenAPI에 적힌 그 경로·메서드·상태의 스키마로 검증한다."""
    op = SPEC["paths"][path][method]
    spec = op["responses"].get(str(resp.status_code))
    assert spec is not None, f"{method.upper()} {path}가 계약에 없는 상태 {resp.status_code}를 돌려줌: {resp.text[:200]}"
    if "$ref" in spec:
        spec = SPEC["components"]["responses"][spec["$ref"].split("/")[-1]]
    schema = dict(spec["content"]["application/json"]["schema"], components=SPEC["components"])
    jsonschema.Draft202012Validator(schema).validate(resp.json())
    assert resp.headers.get("X-Request-ID"), "모든 응답에 X-Request-ID가 있어야 한다"
    CHECKED.append((method, path, resp.status_code))
    return resp.json()


def upload(wanted, title):
    r = requests.post(f"{API}/artworks", json={"wanted": wanted, "title": title}, timeout=10)
    art = contract(r, "post", "/artworks")
    assert r.status_code == 201
    assert art["on_wall"] == "frame", "올리는 즉시 원본 액자로 걸려야 한다(결정 001)"
    return art


def wait_closed(art_id, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        r = requests.get(f"{API}/artworks/{art_id}", timeout=10)
        art = contract(r, "get", "/artworks/{id}")
        assert art["on_wall"] == "frame", "결과 확인 전에는 원본 액자만 걸린다"
        if art["status"] in ("done", "not_delivered"):
            return art
        time.sleep(0.3)
    raise AssertionError(f"작품 {art_id}가 {seconds}초 안에 끝나지 않음")


def invariants(art):
    per_stage = {}
    for a in art["attempts"]:
        per_stage[a["stage"]] = max(per_stage.get(a["stage"], 0), a["attempt"])
    assert all(n <= 3 for n in per_stage.values()), "단계별 시도는 3회를 넘지 않는다"
    if "not_delivered" in art["causes"]:
        assert "guardian_switch" not in art["causes"]
        assert art["result"] is None


def metric(url, name, labels=""):
    text = requests.get(url, timeout=10).text
    total = 0.0
    for line in text.splitlines():
        if labels in line and re.match(rf"{name}(\{{|\s)", line):
            total += float(line.rsplit(" ", 1)[1])
    return total


@pytest.fixture(scope="module")
def before():
    return {"jobs": metric(WORKER_METRICS, "jobs_total"), "retries": metric(WORKER_METRICS, "job_retries_total")}


def tag():
    return uuid.uuid4().hex[:6]


def test_1_ok(before):
    art = wait_closed(upload("animated", f"t{tag()}")["id"])
    assert (art["status"], art["result"], art["causes"]) == ("done", "animated", [])
    assert [a["classification"] for a in art["attempts"]] == ["ok"]
    invariants(art)


def test_2_quality_below_downgrades(before):
    art = wait_closed(upload("animated", f"t{tag()} plan:quality_below")["id"])
    assert art["result"] == "relief" and art["causes"] == ["model_downgrade"]
    assert [(a["stage"], a["classification"]) for a in art["attempts"]] == [("animated", "quality_below"), ("relief", "ok")]
    invariants(art)


def test_3_timeout_then_ok_retries_same_stage(before):
    art = wait_closed(upload("animated", f"t{tag()} plan:timeout,ok")["id"])
    assert art["result"] == "animated" and art["causes"] == ["infra_failure"]
    assert [(a["classification"], a["attempt"]) for a in art["attempts"]] == [("timeout", 1), ("ok", 2)]
    assert art["attempts"][0]["latency_ms"] >= 900, "시간 초과는 실제로 모델 시간 제한(1초)을 기다린 뒤 분류된다"
    invariants(art)


def test_4_three_timeouts_not_delivered_and_only_frame_confirm(before):
    art = wait_closed(upload("animated", f"t{tag()} plan:timeout,timeout,timeout")["id"])
    assert art["status"] == "not_delivered" and art["causes"] == ["infra_failure", "not_delivered"]
    r = requests.post(f"{API}/artworks/{art['id']}/confirm", json={"choice": "animated"}, timeout=10)
    assert contract(r, "post", "/artworks/{id}/confirm")["error"] == "invalid_request"
    r = requests.post(f"{API}/artworks/{art['id']}/confirm", json={"choice": "frame"}, timeout=10)
    after = contract(r, "post", "/artworks/{id}/confirm")
    assert after["on_wall"] == "frame" and "guardian_switch" not in after["causes"]
    invariants(after)


def test_5_contract_violation_is_retried(before):
    art = wait_closed(upload("animated", f"t{tag()} plan:invalid,badfield,ok")["id"])
    assert [a["classification"] for a in art["attempts"]] == ["invalid_response", "invalid_response", "ok"]
    assert art["result"] == "animated" and "model_downgrade" not in art["causes"]
    invariants(art)


def test_6_engine_down_three_times(before):
    art = wait_closed(upload("sculpture", f"t{tag()} plan:down,down,down")["id"])
    assert art["status"] == "not_delivered"
    assert [a["classification"] for a in art["attempts"]] == ["engine_down"] * 3
    invariants(art)


def test_7_frame_never_calls_model(before):
    art = upload("frame", f"t{tag()} plan:down")
    assert art["status"] == "done" and art["causes"] == ["guardian_choice"] and art["attempts"] == []
    time.sleep(1)
    assert requests.get(f"{MODEL}/calls/{art['id']}", timeout=10).json()["calls"] == 0


def test_8_errors_follow_contract(before):
    contract(requests.get(f"{API}/artworks/999999", timeout=10), "get", "/artworks/{id}")
    r = requests.post(f"{API}/artworks", json={"wanted": "hologram", "title": "x"}, timeout=10)
    assert contract(r, "post", "/artworks")["error"] == "invalid_request"
    art = upload("animated", f"t{tag()} plan:timeout,timeout,ok")
    r = requests.post(f"{API}/artworks/{art['id']}/confirm", json={"choice": "animated"}, timeout=10)
    assert contract(r, "post", "/artworks/{id}/confirm")["error"] == "not_ready"
    rid = "trace-" + tag()
    r = requests.get(f"{API}/healthz", headers={"X-Request-ID": rid}, timeout=10)
    contract(r, "get", "/healthz")
    assert r.headers["X-Request-ID"] == rid, "요청한 X-Request-ID를 그대로 돌려준다"
    wait_closed(art["id"])


def test_9_confirm_switch_is_recorded(before):
    art = wait_closed(upload("animated", f"t{tag()}")["id"])
    r = requests.post(f"{API}/artworks/{art['id']}/confirm", json={"choice": "relief"}, timeout=10)
    after = contract(r, "post", "/artworks/{id}/confirm")
    assert after["on_wall"] == "relief" and after["causes"] == ["guardian_switch"]


def test_10_metrics_match_outcomes(before):
    """앞 시나리오에서 모델을 거쳐 끝난 작품 8개와 재시도 수가 워커 지표와 같아야 한다."""
    jobs = metric(WORKER_METRICS, "jobs_total") - before["jobs"]
    retries = metric(WORKER_METRICS, "job_retries_total") - before["retries"]
    assert jobs == 8, f"끝난 작업 지표 {jobs}"
    # 재시도: 3번 1 · 4번 2 · 5번 2 · 6번 2 · 8번 2
    assert retries == 9, f"재시도 지표 {retries}"
    assert metric(f"{API}/metrics", "http_requests_total", 'route="/artworks"') > 0


@pytest.mark.skipif(os.environ.get("COMPOSE") != "1", reason="DB 중지 시나리오는 COMPOSE=1에서만")
def test_11_db_outage_and_recovery():
    art = upload("animated", f"t{tag()} plan:timeout,timeout,ok")
    subprocess.run(["docker", "compose", "stop", "db"], check=True)
    try:
        r = requests.post(f"{API}/artworks", json={"wanted": "animated", "title": "while-down"}, timeout=15)
        body = contract(r, "post", "/artworks")
        assert r.status_code == 503 and body["error"] == "db_unavailable" and body["request_id"]
        r = requests.get(f"{API}/readyz", timeout=15)
        assert r.status_code == 503 and contract(r, "get", "/readyz")["error"] == "db_unavailable"
    finally:
        subprocess.run(["docker", "compose", "start", "db"], check=True)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if requests.get(f"{API}/readyz", timeout=5).status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    contract(requests.get(f"{API}/readyz", timeout=10), "get", "/readyz")
    done = wait_closed(art["id"], seconds=90)
    assert done["result"] == "animated", "DB가 멈추기 전에 올린 작품이 재시작 뒤 끝까지 처리된다"
    invariants(done)
