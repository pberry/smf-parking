# smf-parking

Hourly poller and plotter for parking availability at Sacramento International
Airport (SMF). Renders the [SMF parking
page](https://flysmf.gov/to-and-from/parking) with a headless browser, records
open-space counts per lot to SQLite, and plots trends.

## Tracked lots

Lots are discovered from the live widget, so new ones (e.g. Garage 2 when it
opens in Fall 2026) start being recorded automatically. As of the first poll,
the page exposes:

| `lot_id`            | Display name (from the widget) |
| ------------------- | ------------------------------ |
| `garage`            | Garage                         |
| `daily-a`           | Daily A                        |
| `east-economy-lot`  | East Economy Lot               |
| `south-economy-lot` | South Economy Lot              |
| `west-economy-lot`  | West Economy Lot               |

Closed lots are recorded with `status='closed'` and `open_spaces=NULL`; they
are automatically excluded from plots (gap in the line) and resume tracking
the next hour their value flips back to a number.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
```

## Use

```sh
# Poll once (writes to data/parking.db).
smf-poll

# Render trend PNGs for the last 30 days into plots/.
smf-plot
```

Both commands accept `--db PATH`; `smf-plot` also accepts `--out DIR` and
`--days N`.

`smf-plot` writes two kinds of PNGs per lot (plus a combined view):

- `<lot_id>.png` / `all-lots.png` — every hourly reading over the last
  `--days` days, for spotting trends and outages.
- `daily-<lot_id>.png` / `daily-all-lots.png` — a rolling 4-week average for
  each hour of day, split into weekday/weekend lines, for spotting the
  "typical day" shape. Always uses a trailing 4-week window, independent of
  `--days`.

## Estimating future availability

`smf-estimate` gives a probabilistic read on a lot's availability at a future
date/time, e.g. planning a trip:

```sh
smf-estimate --lot garage --at "2026-07-30 16:00"
```

It finds every historical reading that shares the target's weekday name
(e.g. "Thursday") and falls within `--window-minutes` (default 30) of its
time-of-day, then reports the empirical distribution (median, observed
range, 10th-90th percentile band) of that lot's `open_spaces` across those
matches. Pass `--at` multiple times to see a trend across a visit window
(e.g. arrival through departure). It's a historical analog, not a forecast —
accuracy depends entirely on how much matching history exists (`n` in the
output), which is small until the database has accumulated many weeks.

## Scheduling (macOS, launchd)

The repo ships with `launchd/com.pberry.smf-parking.plist` (`pberry` is my
username — replace `pberry` with `<your-username>` everywhere below, and
both rename the file and edit the `<key>Label</key>` value inside it to
match). Also update the absolute paths inside the plist to point at your
venv's `python` and project directory.

```sh
launchctl bootstrap gui/$UID launchd/com.<your-username>.smf-parking.plist
launchctl print gui/$UID/com.<your-username>.smf-parking   # verify
```

To remove:

```sh
launchctl bootout gui/$UID/com.<your-username>.smf-parking
```

Logs land in `data/launchd.log`.

## Tests

```sh
pytest
```

Tests run offline against a captured HTML fixture in `tests/fixtures/`.

## If it stops working

**Check first:** `launchctl print gui/$UID/com.<your-username>.smf-parking | grep -E 'last exit code|runs ='`
and tail `data/launchd.log` — the failure mode is almost always one of these:

- **Venv interpreter is gone** (e.g. you ran `brew uninstall python@3.14`, or
  Homebrew dropped a formula). Symptom: `posix_spawn` error in the log, or
  `bad interpreter: No such file or directory`. Fix by rebuilding the venv:

  ```sh
  rm -rf .venv
  python3 -m venv .venv
  .venv/bin/pip install -e '.[dev]'
  .venv/bin/playwright install chromium
  ```

  No code changes needed — `pyproject.toml` accepts any Python `>=3.12`.

- **SMF page changed structure** (e.g. lots widget renamed, new framework).
  Symptom: `ScrapeError: lots widget not found` in the log. Refresh the test
  fixture and the parser will tell you what broke:

  ```sh
  .venv/bin/python scripts/capture_fixture.py
  pytest
  ```

- **Playwright Chromium upgraded out from under us.** Symptom: browser-launch
  error. Re-run `.venv/bin/playwright install chromium`.

- **Network blip / SMF site down.** Symptom: timeout in the log. Single
  failures are harmless — the next hourly run picks up where it left off.
  Persistent failures mean the URL or the site is genuinely broken.
