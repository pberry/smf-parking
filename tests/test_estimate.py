from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from smf_parking.db import connect, init_schema, insert_readings
from smf_parking.estimate import _load_lot, estimate_at, format_estimate
from smf_parking.scraper import LotReading

PACIFIC = ZoneInfo("America/Los_Angeles")


def _df(rows: list[tuple[str, float | None, str]]) -> pd.DataFrame:
    """rows: (ts_iso_utc, open_spaces, status) -> _load_lot-shaped DataFrame."""
    df = pd.DataFrame(rows, columns=["ts", "open_spaces", "status"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(PACIFIC)
    df["open_spaces"] = df["open_spaces"].astype("Float64")
    return df


def test_estimate_matches_same_weekday_and_time_of_day() -> None:
    # Three Thursdays at 16:00 PDT (23:00Z), one Friday at 16:00 PDT excluded.
    df = _df(
        [
            ("2026-06-04T23:00:00Z", 170, "open"),
            ("2026-06-11T23:00:00Z", 190, "open"),
            ("2026-06-18T23:00:00Z", 210, "open"),
            ("2026-06-12T23:00:00Z", 999, "open"),  # Friday, must be excluded
        ]
    )
    target = datetime(2026, 6, 25, 16, 0, tzinfo=PACIFIC)  # a Thursday

    est = estimate_at(df, target, window_minutes=30)

    assert est.weekday == "Thursday"
    assert est.n == 3
    assert est.median == 190
    assert est.min == 170
    assert est.max == 210


def test_estimate_respects_window_minutes() -> None:
    df = _df(
        [
            ("2026-06-04T23:00:00Z", 170, "open"),  # 16:00 PDT, exact match
            ("2026-06-04T23:45:00Z", 500, "open"),  # 16:45 PDT, 45 min away
        ]
    )
    target = datetime(2026, 6, 4, 16, 0, tzinfo=PACIFIC)

    tight = estimate_at(df, target, window_minutes=30)
    wide = estimate_at(df, target, window_minutes=45)

    assert tight.n == 1
    assert tight.mean == 170
    assert wide.n == 2


def test_estimate_reports_closed_fraction() -> None:
    df = _df(
        [
            ("2026-06-04T23:00:00Z", 170, "open"),
            ("2026-06-11T23:00:00Z", 0, "closed"),
        ]
    )
    target = datetime(2026, 6, 18, 16, 0, tzinfo=PACIFIC)

    est = estimate_at(df, target, window_minutes=30)

    assert est.n == 2
    assert est.closed_fraction == 0.5


def test_estimate_empty_history_returns_zero_samples() -> None:
    est = estimate_at(pd.DataFrame(), datetime(2026, 7, 30, 16, 0, tzinfo=PACIFIC))
    assert est.n == 0
    assert est.mean is None


def test_format_estimate_handles_no_matches() -> None:
    est = estimate_at(pd.DataFrame(), datetime(2026, 7, 30, 16, 0, tzinfo=PACIFIC))
    text = format_estimate(est, "Garage")
    assert "No historical" in text


def test_load_lot_returns_pacific_timestamps(tmp_path: Path) -> None:
    db_path = tmp_path / "parking.db"
    conn = connect(db_path)
    init_schema(conn)
    insert_readings(
        conn,
        "2026-05-30T23:00:00Z",  # 16:00 PDT
        [
            LotReading("garage", "Garage", 400, "open", "400"),
            LotReading("daily-a", "Daily A", 12, "open", "12"),
        ],
    )
    conn.close()

    df = _load_lot(db_path, "garage")

    assert len(df) == 1
    assert df["ts"].iloc[0].hour == 16
    assert df["ts"].iloc[0].tzinfo is not None
    assert df["lot_name"].iloc[0] == "Garage"


def test_load_lot_missing_lot_returns_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "parking.db"
    conn = connect(db_path)
    init_schema(conn)
    conn.close()

    df = _load_lot(db_path, "garage")

    assert df.empty
