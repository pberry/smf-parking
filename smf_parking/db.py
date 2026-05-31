from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .scraper import LotReading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts          TEXT NOT NULL,
    lot_id      TEXT NOT NULL,
    lot_name    TEXT NOT NULL,
    open_spaces INTEGER,
    status      TEXT NOT NULL,
    raw         TEXT,
    PRIMARY KEY (ts, lot_id)
);
CREATE INDEX IF NOT EXISTS idx_readings_lot_ts ON readings (lot_id, ts);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_readings(
    conn: sqlite3.Connection, ts: str, readings: Iterable[LotReading]
) -> int:
    rows = [
        (ts, r.lot_id, r.lot_name, r.open_spaces, r.status, r.raw) for r in readings
    ]
    cur = conn.executemany(
        "INSERT OR IGNORE INTO readings "
        "(ts, lot_id, lot_name, open_spaces, status, raw) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return cur.rowcount
