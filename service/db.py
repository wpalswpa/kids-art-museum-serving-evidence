"""MariaDB 연결과 표. 작품 표 하나가 상태이자 큐다(FOR UPDATE SKIP LOCKED)."""
import json
import os
import time

import pymysql

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS artworks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(120) NOT NULL,
        wanted VARCHAR(16) NOT NULL,
        on_wall VARCHAR(16) NOT NULL,
        target VARCHAR(16) NOT NULL,
        stage_attempts INT NOT NULL DEFAULT 0,
        result VARCHAR(16) NULL,
        causes TEXT NOT NULL,
        status VARCHAR(16) NOT NULL,
        lease_until DATETIME(3) NULL,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
        KEY status_idx (status, lease_until)
    )""",
    """CREATE TABLE IF NOT EXISTS attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        artwork_id INT NOT NULL,
        stage VARCHAR(16) NOT NULL,
        classification VARCHAR(24) NOT NULL,
        attempt INT NOT NULL,
        latency_ms INT NOT NULL,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        KEY artwork_idx (artwork_id)
    )""",
]


def connect():
    return pymysql.connect(host=os.environ.get("DB_HOST", "db"), port=int(os.environ.get("DB_PORT", "3306")),
                           user=os.environ.get("DB_USER", "museum"), password=os.environ.get("DB_PASSWORD", "museum"),
                           database=os.environ.get("DB_NAME", "museum"), autocommit=False, connect_timeout=2,
                           read_timeout=5, write_timeout=5, cursorclass=pymysql.cursors.DictCursor)


def init(wait_seconds=60):
    """DB가 뜰 때까지 기다렸다가 표를 만든다."""
    deadline = time.time() + wait_seconds
    while True:
        try:
            conn = connect()
            with conn.cursor() as cur:
                for stmt in SCHEMA:
                    cur.execute(stmt)
            conn.commit()
            conn.close()
            return
        except pymysql.MySQLError:
            if time.time() > deadline:
                raise
            time.sleep(1)


def row_to_artwork(row, attempts):
    return {"id": row["id"], "title": row["title"], "wanted": row["wanted"], "on_wall": row["on_wall"],
            "target": row["target"], "status": row["status"], "result": row["result"],
            "causes": json.loads(row["causes"]),
            "attempts": [{"stage": a["stage"], "classification": a["classification"], "attempt": a["attempt"],
                          "latency_ms": a["latency_ms"]} for a in attempts]}
