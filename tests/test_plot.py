from __future__ import annotations

from pathlib import Path

import pandas as pd

from smf_parking.db import connect, init_schema, insert_readings
from smf_parking.plot import _load
from smf_parking.scraper import LotReading


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
