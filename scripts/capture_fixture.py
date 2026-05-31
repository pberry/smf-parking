"""Render the SMF parking page once and dump useful artifacts for development.

Outputs:
  - tests/fixtures/rendered_sample.html  (full hydrated DOM)
  - /tmp/smf_lots_text.txt               (visible text near each lot anchor)
  - /tmp/smf_lots_dump.json              (per-lot innerHTML and aria/text snippets)
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://flysmf.gov/to-and-from/parking"
LOT_IDS = [
    "parking-garage",
    "garage-2",
    "daily-lot",
    "east-economy",
    "south-economy",
    "west-economy",
]

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "rendered_sample.html"
TEXT_DUMP = Path("/tmp/smf_lots_text.txt")
JSON_DUMP = Path("/tmp/smf_lots_dump.json")


def main() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        # Give the Livewire lazy-load a moment after networkidle.
        page.wait_for_timeout(3_000)

        FIXTURE.write_text(page.content(), encoding="utf-8")

        text_lines: list[str] = []
        dump: dict[str, dict] = {}
        for lot_id in LOT_IDS:
            sel = f'[data-anchor-id="{lot_id}"]'
            try:
                handle = page.locator(sel).first
                inner_text = handle.inner_text(timeout=5_000)
                inner_html = handle.inner_html(timeout=5_000)
            except Exception as exc:  # noqa: BLE001
                inner_text = f"<error: {exc!r}>"
                inner_html = ""
            text_lines.append(f"=== {lot_id} ===")
            text_lines.append(inner_text)
            text_lines.append("")
            dump[lot_id] = {
                "text": inner_text,
                "html_first_2000": inner_html[:2000],
            }

        TEXT_DUMP.write_text("\n".join(text_lines), encoding="utf-8")
        JSON_DUMP.write_text(json.dumps(dump, indent=2), encoding="utf-8")
        browser.close()

    print(f"wrote: {FIXTURE}")
    print(f"wrote: {TEXT_DUMP}")
    print(f"wrote: {JSON_DUMP}")


if __name__ == "__main__":
    main()
