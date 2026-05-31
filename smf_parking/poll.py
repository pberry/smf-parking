from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import db, scraper

DEFAULT_DB = Path("data/parking.db")
DEFAULT_LOG = Path("data/poll.log")


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _hourly_ts() -> str:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Poll the SMF parking page once and record readings to SQLite."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)

    _setup_logging(args.log)
    log = logging.getLogger("smf_parking.poll")

    ts = _hourly_ts()
    try:
        readings = scraper.scrape()
    except Exception:
        log.exception("scrape failed; aborting without writing")
        return 1

    conn = db.connect(args.db)
    db.init_schema(conn)
    inserted = db.insert_readings(conn, ts, readings)
    conn.close()

    summary = ", ".join(
        f"{r.lot_name}={r.raw}" for r in sorted(readings, key=lambda r: r.lot_id)
    )
    log.info("ts=%s inserted=%d/%d lots: %s", ts, inserted, len(readings), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
