"""Probabilistic availability estimate for a lot at a future date/time.

Method: pull every historical reading that shares the target's weekday name
and falls within a tolerance window of its time-of-day (an "analog" sample),
then report the empirical distribution of open_spaces for that sample. This
makes no assumption about trend or seasonality beyond "same weekday, same
time of day behaves similarly" -- with only a couple of months of history,
fitting anything fancier would overfit noise.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

DEFAULT_DB = Path("data/parking.db")
DISPLAY_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_WINDOW_MINUTES = 30


@dataclass
class Estimate:
    weekday: str
    target_time: str
    window_minutes: int
    n: int
    first_date: date | None
    last_date: date | None
    mean: float | None
    median: float | None
    std: float | None
    min: float | None
    max: float | None
    p10: float | None
    p90: float | None
    closed_fraction: float | None


def _load_lot(db_path: str | Path, lot_id: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT ts, lot_name, open_spaces, status FROM readings "
            "WHERE lot_id = ? ORDER BY ts",
            conn,
            params=(lot_id,),
        )
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(DISPLAY_TZ)
    df["open_spaces"] = df["open_spaces"].astype("Float64")
    return df


def _minute_distance(a: pd.Series, b: int) -> pd.Series:
    """Circular distance in minutes between times-of-day, so 23:50 is
    close to 00:10 rather than ~1420 minutes away."""
    raw = (a - b).abs()
    return pd.concat([raw, 1440 - raw], axis=1).min(axis=1)


def estimate_at(
    df: pd.DataFrame, target: datetime, window_minutes: int = DEFAULT_WINDOW_MINUTES
) -> Estimate:
    """`target` must be a tz-aware datetime in DISPLAY_TZ (or convertible)."""
    weekday = target.strftime("%A")
    target_minutes = target.hour * 60 + target.minute
    target_label = target.strftime("%H:%M")

    if df.empty:
        return Estimate(
            weekday, target_label, window_minutes, 0, None, None, None, None,
            None, None, None, None, None, None,
        )

    work = df.copy()
    work["minute_of_day"] = work["ts"].dt.hour * 60 + work["ts"].dt.minute
    work["weekday"] = work["ts"].dt.day_name()
    dist = _minute_distance(work["minute_of_day"], target_minutes)
    matched = work[(work["weekday"] == weekday) & (dist <= window_minutes)]

    valid = matched["open_spaces"].dropna()
    dates = matched["ts"].dt.date
    closed_fraction = float((matched["status"] == "closed").mean()) if len(matched) else None

    return Estimate(
        weekday=weekday,
        target_time=target_label,
        window_minutes=window_minutes,
        n=len(matched),
        first_date=dates.min() if not dates.empty else None,
        last_date=dates.max() if not dates.empty else None,
        mean=float(valid.mean()) if not valid.empty else None,
        median=float(valid.median()) if not valid.empty else None,
        std=float(valid.std()) if len(valid) > 1 else None,
        min=float(valid.min()) if not valid.empty else None,
        max=float(valid.max()) if not valid.empty else None,
        p10=float(valid.quantile(0.10)) if not valid.empty else None,
        p90=float(valid.quantile(0.90)) if not valid.empty else None,
        closed_fraction=closed_fraction,
    )


def format_estimate(est: Estimate, lot_name: str) -> str:
    if est.n == 0:
        return (
            f"No historical {est.weekday} readings within "
            f"{est.window_minutes} min of {est.target_time} for {lot_name}."
        )
    lines = [
        f"{lot_name} — {est.weekday}s around {est.target_time} "
        f"(±{est.window_minutes} min, n={est.n}, {est.first_date} to {est.last_date})",
    ]
    if est.mean is None:
        lines.append("  All matching readings were closed/unknown; no open_spaces data.")
        return "\n".join(lines)
    lines.append(
        f"  median {est.median:.0f} open spaces  "
        f"(mean {est.mean:.0f}, std {est.std:.0f})" if est.std is not None
        else f"  median {est.median:.0f} open spaces (mean {est.mean:.0f})"
    )
    lines.append(f"  observed range: {est.min:.0f}-{est.max:.0f}")
    lines.append(
        f"  80% of the time historically: {est.p10:.0f}-{est.p90:.0f} open spaces"
    )
    if est.closed_fraction:
        lines.append(f"  lot was recorded closed {est.closed_fraction:.0%} of matching samples")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate parking availability for a future date/time from "
            "historical same-weekday, same-time-of-day readings."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lot", default="garage-1", help="lot_id (default: garage-1)")
    parser.add_argument(
        "--at",
        required=True,
        action="append",
        metavar="YYYY-MM-DD HH:MM",
        help="target local (Pacific) date/time; repeat --at for multiple times",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=DEFAULT_WINDOW_MINUTES,
        help="tolerance window around each --at time-of-day (default: 30)",
    )
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    df = _load_lot(args.db, args.lot)
    if df.empty:
        print(f"no readings found for lot {args.lot!r}", file=sys.stderr)
        return 1
    lot_name = str(df["lot_name"].iloc[-1]) if "lot_name" in df.columns else args.lot

    for at in args.at:
        target = datetime.fromisoformat(at).replace(tzinfo=DISPLAY_TZ)
        est = estimate_at(df, target, args.window_minutes)
        print(format_estimate(est, lot_name))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
