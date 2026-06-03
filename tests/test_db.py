from __future__ import annotations

import sqlite3

import pytest

from smf_parking import db
from smf_parking.scraper import LotReading


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    db.init_schema(c)
    return c


def _sample() -> list[LotReading]:
    return [
        LotReading("garage", "Garage", 382, "open", "382"),
        LotReading("daily-a", "Daily A", 144, "open", "144"),
        LotReading("west-economy-lot", "West Economy Lot", 0, "closed", "Closed"),
    ]


def test_insert_round_trip(conn: sqlite3.Connection) -> None:
    inserted = db.insert_readings(conn, "2026-05-30T17:00:00Z", _sample())
    assert inserted == 3
    rows = conn.execute(
        "SELECT lot_id, lot_name, open_spaces, status, raw FROM readings ORDER BY lot_id"
    ).fetchall()
    assert rows == [
        ("daily-a", "Daily A", 144, "open", "144"),
        ("garage", "Garage", 382, "open", "382"),
        ("west-economy-lot", "West Economy Lot", 0, "closed", "Closed"),
    ]


def test_reinsert_same_hour_is_idempotent(conn: sqlite3.Connection) -> None:
    ts = "2026-05-30T17:00:00Z"
    db.insert_readings(conn, ts, _sample())
    db.insert_readings(conn, ts, _sample())
    count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    assert count == 3


def test_reopening_lot_records_new_status(conn: sqlite3.Connection) -> None:
    # Hour 1: West Economy is Closed.
    db.insert_readings(conn, "2026-05-30T17:00:00Z", _sample())
    # Hour 2: West Economy reopens with a number — no special handling needed,
    # it's just another row.
    reopened = [
        LotReading("west-economy-lot", "West Economy Lot", 2100, "open", "2100"),
    ]
    db.insert_readings(conn, "2026-05-30T18:00:00Z", reopened)

    history = conn.execute(
        "SELECT ts, status, open_spaces FROM readings "
        "WHERE lot_id = 'west-economy-lot' ORDER BY ts"
    ).fetchall()
    assert history == [
        ("2026-05-30T17:00:00Z", "closed", 0),
        ("2026-05-30T18:00:00Z", "open", 2100),
    ]
