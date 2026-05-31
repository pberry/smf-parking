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

## Scheduling (macOS, launchd)

Edit `launchd/com.pberry.smf-parking.plist` to point at the absolute paths of
your venv's `python` and this project, then:

```sh
launchctl bootstrap gui/$UID launchd/com.pberry.smf-parking.plist
launchctl print gui/$UID/com.pberry.smf-parking   # verify
```

To remove:

```sh
launchctl bootout gui/$UID/com.pberry.smf-parking
```

Logs land in `data/launchd.log`.

## Tests

```sh
pytest
```

Tests run offline against a captured HTML fixture in `tests/fixtures/`.

## If it stops working

**Check first:** `launchctl print gui/$UID/com.pberry.smf-parking | grep -E 'last exit code|runs ='`
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
