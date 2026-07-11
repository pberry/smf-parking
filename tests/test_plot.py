from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from smf_parking.db import connect, init_schema, insert_readings
from smf_parking.plot import _hourly_stats, _load
from smf_parking.scraper import LotReading

PACIFIC = ZoneInfo("America/Los_Angeles")


def _reading_df(rows: list[tuple[str, str, str, float | None]]) -> pd.DataFrame:
    """Build a post-_load-shaped DataFrame directly: (ts_iso, lot_id, lot_name,
    open_spaces) rows, skipping the DB round trip."""
    df = pd.DataFrame(rows, columns=["ts", "lot_id", "lot_name", "open_spaces"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(PACIFIC)
    df["open_spaces"] = df["open_spaces"].astype("Float64")
    return df


def test_load_returns_pacific_timestamps(tmp_path: Path) -> None:
    """DB stores UTC; the plotter must hand back Pacific-zone timestamps so
    matplotlib's axis renders local wall-clock time."""
    db_path = tmp_path / "parking.db"
    conn = connect(db_path)
    init_schema(conn)
    insert_readings(
        conn,
        "2026-05-30T23:00:00Z",  # 16:00 PDT (UTC-7) on this date
        [LotReading("garage", "Garage", 400, "open", "400")],
    )
    conn.close()

    df = _load(db_path, days=365)

    assert len(df) == 1
    ts = df["ts"].iloc[0]
    assert ts.tzinfo is not None
    assert str(ts.tzinfo) == "America/Los_Angeles"
    assert ts.hour == 16
    assert ts.minute == 0


def test_load_renders_closed_as_zero_not_gap(tmp_path: Path) -> None:
    """Closed lots are stored as 0; the plotter must surface that as 0 so the
    line dips instead of breaking. Unknown rows (open_spaces=None) still
    surface as NA so they remain gaps."""
    db_path = tmp_path / "parking.db"
    conn = connect(db_path)
    init_schema(conn)
    insert_readings(
        conn,
        "2026-05-30T23:00:00Z",
        [
            LotReading("garage", "Garage", 400, "open", "400"),
            LotReading("daily-a", "Daily A", 0, "closed", "Closed"),
            LotReading("mystery", "Mystery", None, "unknown", "???"),
        ],
    )
    conn.close()

    df = _load(db_path, days=365).set_index("lot_id")["open_spaces"]

    assert df["garage"] == 400
    assert df["daily-a"] == 0
    assert pd.isna(df["mystery"])


def test_hourly_stats_splits_weekday_and_weekend() -> None:
    """The rolling daily-average plots need one bucket per (lot, day-type,
    hour-of-day), collapsing across the trailing weeks."""
    df = _reading_df(
        [
            ("2026-06-01T23:00:00Z", "garage", "Garage", 100),  # Mon 16:00 PDT
            ("2026-06-08T23:00:00Z", "garage", "Garage", 200),  # Mon 16:00 PDT
            ("2026-06-06T23:00:00Z", "garage", "Garage", 50),  # Sat 16:00 PDT
        ]
    )

    stats = _hourly_stats(df).set_index(["lot_id", "day_type", "hour"])

    weekday = stats.loc[("garage", "Weekday", 16)]
    assert weekday["mean"] == 150
    assert weekday["std"] == pytest.approx(70.71067811865476)
    assert weekday["lot_name"] == "Garage"

    weekend = stats.loc[("garage", "Weekend", 16)]
    assert weekend["mean"] == 50
    assert pd.isna(weekend["std"])  # single sample: no spread to report


def test_hourly_stats_closed_zero_counted_unknown_excluded() -> None:
    """Matches _load's contract: closed (0) is a real reading and pulls the
    average down; unknown (NA) is excluded rather than treated as 0."""
    df = _reading_df(
        [
            ("2026-06-01T23:00:00Z", "garage", "Garage", 100),
            ("2026-06-01T23:00:00Z", "daily-a", "Daily A", 0),
            ("2026-06-01T23:00:00Z", "mystery", "Mystery", None),
            ("2026-06-08T23:00:00Z", "daily-a", "Daily A", 100),
        ]
    )

    stats = _hourly_stats(df).set_index(["lot_id", "day_type", "hour"])

    assert stats.loc[("daily-a", "Weekday", 16), "mean"] == 50
    assert ("mystery", "Weekday", 16) not in stats.index


def test_hourly_stats_empty_df() -> None:
    df = _reading_df([])

    stats = _hourly_stats(df)

    assert stats.empty
    assert list(stats.columns) == ["lot_id", "day_type", "hour", "mean", "std", "lot_name"]
