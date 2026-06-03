# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- License is now 0BSD (was unstated/MIT-in-metadata-only); added `LICENSE` file.
- Plots now render timestamps in Pacific (`America/Los_Angeles`) instead of UTC.
  Storage stays in UTC; only display changed. Handles PST/PDT automatically.
- README launchd instructions now use `<your-username>` as a placeholder
  instead of hardcoding the author's username.
- Closed lots are now stored as `open_spaces = 0` instead of `NULL`. Status
  column still distinguishes `closed` from `open`, so the two cases remain
  separable; only the numeric column changed.
- `smf-plot` now draws closed periods as a dip to 0 instead of a gap, matching
  the new storage contract. Unknown-status rows (NULL `open_spaces`) still
  render as gaps.

## [1.0.0] - 2026-05-30

### Added
- Hourly Playwright scraper for the SMF parking page.
- SQLite append-only `readings` table keyed by `(ts, lot_id)`.
- `smf-poll` CLI for one-shot polling (idempotent within the hour).
- `smf-plot` CLI for per-lot and combined PNG trend plots.
- `launchd` plist for hourly scheduling on macOS.
- pytest coverage for parser (against a captured HTML fixture) and DB helpers.
