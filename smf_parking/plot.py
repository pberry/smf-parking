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
DAILY_AVERAGE_WEEKS = 4
_DAY_TYPE_COLORS = {"Weekday": "tab:blue", "Weekend": "tab:orange"}


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
    # Closed lots store as 0 (a real dip); unknown rows have NULL open_spaces
    # already, so they surface as NA and matplotlib draws them as gaps.
    df["open_spaces"] = df["open_spaces"].astype("Float64")
    return df


def _hourly_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Bucket readings by lot, weekday/weekend, and hour-of-day, averaging
    across whatever trailing window the caller loaded. Feeds the rolling
    daily-average plots (a "typical day" curve per lot).

    Buckets with no valid reading (every row NA, e.g. a lot with no history
    yet) are dropped rather than kept as NaN so they don't render as broken
    points.
    """
    columns = ["lot_id", "day_type", "hour", "mean", "std", "lot_name"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    work = df.copy()
    work["hour"] = work["ts"].dt.hour
    work["day_type"] = work["ts"].dt.dayofweek.map(
        lambda d: "Weekend" if d >= 5 else "Weekday"
    )
    stats = (
        work.groupby(["lot_id", "day_type", "hour"])["open_spaces"]
        .agg(mean="mean", std="std")
        .reset_index()
        .dropna(subset=["mean"])
    )
    names = work.groupby("lot_id")["lot_name"].last()
    stats["lot_name"] = stats["lot_id"].map(names)
    return stats


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


def _plot_daily_one(stats: pd.DataFrame, lot_id: str, out_path: Path, weeks: int) -> None:
    sub = stats[stats["lot_id"] == lot_id]
    if sub.empty:
        return
    name = sub["lot_name"].iloc[0]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for day_type, color in _DAY_TYPE_COLORS.items():
        day_sub = sub[sub["day_type"] == day_type].sort_values("hour")
        if day_sub.empty:
            continue
        ax.plot(
            day_sub["hour"], day_sub["mean"], marker=".", label=day_type, color=color
        )
        std = day_sub["std"].fillna(0)
        lower = (day_sub["mean"] - std).clip(lower=0)
        upper = day_sub["mean"] + std
        ax.fill_between(day_sub["hour"], lower, upper, alpha=0.2, color=color)
    ax.set_title(f"{name} — average open spaces by hour ({weeks}-week rolling avg)")
    ax.set_ylabel("Open spaces")
    ax.set_xlabel("Hour of day (Pacific)")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.5, 23.5)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize="small")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _plot_daily_all(stats: pd.DataFrame, out_path: Path, weeks: int) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    for ax, day_type in zip(axes, ("Weekday", "Weekend")):
        day_df = stats[stats["day_type"] == day_type]
        for lot_id, sub in day_df.sort_values("hour").groupby("lot_id"):
            ax.plot(
                sub["hour"],
                sub["mean"],
                marker=".",
                linewidth=1,
                label=sub["lot_name"].iloc[0],
            )
        ax.set_title(day_type)
        ax.set_xlabel("Hour of day (Pacific)")
        ax.set_xticks(range(0, 24, 4))
        ax.set_xlim(-0.5, 23.5)
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Open spaces")
    axes[-1].legend(loc="best", fontsize="small")
    fig.suptitle(f"SMF parking — average open spaces by hour ({weeks}-week rolling avg)")
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

    daily_df = _load(args.db, DAILY_AVERAGE_WEEKS * 7)
    stats = _hourly_stats(daily_df)
    for lot_id in sorted(stats["lot_id"].unique()):
        _plot_daily_one(
            stats, lot_id, args.out / f"daily-{lot_id}.png", DAILY_AVERAGE_WEEKS
        )
    if not stats.empty:
        _plot_daily_all(stats, args.out / "daily-all-lots.png", DAILY_AVERAGE_WEEKS)

    print(f"wrote plots to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
