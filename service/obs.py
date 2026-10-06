"""한 줄 JSON 로그와 Prometheus 지표."""
import json
import logging
import sys
import time

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter("http_requests_total", "API 요청 수", ["route", "status"])
JOBS = Counter("jobs_total", "끝난 작업 수", ["outcome"])
ATTEMPTS = Counter("job_attempts_total", "모델 호출 시도 수", ["stage", "classification"])
RETRIES = Counter("job_retries_total", "같은 단계를 다시 시도한 수")
DURATION = Histogram("job_duration_seconds", "작품 하나가 올린 뒤 끝날 때까지 걸린 시간",
                     buckets=(0.5, 1, 2, 5, 10, 30, 60, 120))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {"ts": round(time.time(), 3), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        out.update(getattr(record, "fields", {}))
        return json.dumps(out, ensure_ascii=False)


def logger(name):
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def event(log, msg, **fields):
    log.info(msg, extra={"fields": fields})
