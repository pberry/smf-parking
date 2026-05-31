from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

DEFAULT_DB = Path("data/parking.db")
DEFAULT_OUT = Path("plots")
# Data is stored in UTC; plots render in Pacific (handles PST/PDT automatically).
DISPLAY_TZ = ZoneInfo("America/Los_Angeles")


def _load(db_path: Path, days: int) -> pd.DataFrame:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat().replace(
        "+00:00", "Z"
    )
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT ts, lot_id, lot_name, open_spaces, status
            FROM readings
            WHERE ts >= ?
            ORDER BY ts
            """,
            conn,
            params=(cutoff,),
        )
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(DISPLAY_TZ)
    # NaN-out closed/unknown rows so matplotlib draws gaps automatically.
    df.loc[df["status"] != "open", "open_spaces"] = pd.NA
    df["open_spaces"] = df["open_spaces"].astype("Float64")
    return df


def _format_time_axis(ax: plt.Axes, days: int) -> None:
    if days <= 2:
        loc = mdates.HourLocator(interval=3)
        fmt = mdates.DateFormatter("%m-%d %H:%M", tz=DISPLAY_TZ)
    elif days <= 14:
        loc = mdates.DayLocator()
        fmt = mdates.DateFormatter("%m-%d", tz=DISPLAY_TZ)
    else:
        loc = mdates.AutoDateLocator()
        fmt = mdates.ConciseDateFormatter(loc, tz=DISPLAY_TZ)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(fmt)
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_horizontalalignment("right")


def _plot_one(df: pd.DataFrame, lot_id: str, out_path: Path, days: int) -> None:
    sub = df[df["lot_id"] == lot_id].sort_values("ts")
    if sub.empty:
        return
    name = sub["lot_name"].iloc[-1]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(sub["ts"], sub["open_spaces"], marker=".", linewidth=1)
    ax.set_title(f"{name} — open spaces (last {days} days)")
    ax.set_ylabel("Open spaces")
    ax.set_xlabel("Time (Pacific)")
    ax.grid(True, alpha=0.3)
    _format_time_axis(ax, days)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _plot_all(df: pd.DataFrame, out_path: Path, days: int) -> None:
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lot_id, sub in df.sort_values("ts").groupby("lot_id"):
        name = sub["lot_name"].iloc[-1]
        ax.plot(sub["ts"], sub["open_spaces"], marker=".", linewidth=1, label=name)
    ax.set_title(f"SMF parking — open spaces by lot (last {days} days)")
    ax.set_ylabel("Open spaces")
    ax.set_xlabel("Time (Pacific)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize="small")
    _format_time_axis(ax, days)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render trend PNGs from the SMF parking SQLite database."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    df = _load(args.db, args.days)
    if df.empty:
        print(f"no readings in last {args.days} days", file=sys.stderr)
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for lot_id in sorted(df["lot_id"].unique()):
        _plot_one(df, lot_id, args.out / f"{lot_id}.png", args.days)
    _plot_all(df, args.out / "all-lots.png", args.days)
    print(f"wrote plots to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
