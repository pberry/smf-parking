from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import Literal

from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

URL = "https://flysmf.gov/to-and-from/parking"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

Status = Literal["open", "closed", "unknown"]


@dataclass(frozen=True)
class LotReading:
    lot_id: str
    lot_name: str
    open_spaces: int | None
    status: Status
    raw: str


class ScrapeError(RuntimeError):
    """Raised when the page can't be scraped or the lots widget is missing."""


# Locate the Livewire "lots" component's tbody. The wire:id is randomized per
# request, so we anchor on the snapshot containing "name":"lots" (HTML-encoded
# in the page source as &quot;name&quot;:&quot;lots&quot;).
_WIDGET_RE = re.compile(
    r'wire:snapshot="[^"]*&quot;name&quot;:&quot;lots&quot;[^"]*"'
    r"[\s\S]*?<tbody[^>]*>([\s\S]*?)</tbody>",
)

# Each row has two relevant cells: the lot name and the availability value.
# The "<!--[if BLOCK]><![endif]-->" comments Laravel emits are skipped by [\s\S]*?.
_ROW_RE = re.compile(
    r'<tr[^>]*>\s*'
    r'<td[^>]*>([^<]+)</td>\s*'
    r'<td[^>]*>\s*([^<]+?)\s*</td>',
)


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _normalize(raw: str) -> tuple[Status, int | None]:
    raw = raw.strip()
    if raw.isdigit():
        return "open", int(raw)
    if raw.lower() == "closed":
        return "closed", None
    return "unknown", None


def parse(page_html: str) -> list[LotReading]:
    """Parse the lots widget out of a rendered parking-page HTML document."""
    m = _WIDGET_RE.search(page_html)
    if not m:
        raise ScrapeError("lots widget not found in rendered HTML")

    readings: list[LotReading] = []
    for name_raw, value_raw in _ROW_RE.findall(m.group(1)):
        name = html.unescape(name_raw).strip()
        value = html.unescape(value_raw).strip()
        status, open_spaces = _normalize(value)
        if status == "unknown":
            log.warning("unrecognized availability value for %r: %r", name, value)
        readings.append(
            LotReading(
                lot_id=_slugify(name),
                lot_name=name,
                open_spaces=open_spaces,
                status=status,
                raw=value,
            )
        )

    if not readings:
        raise ScrapeError("lots widget contained no rows")
    return readings


def scrape(timeout_ms: int = 60_000, settle_ms: int = 3_000) -> list[LotReading]:
    """Render the SMF parking page and parse the live lots widget."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.goto(URL, wait_until="networkidle", timeout=timeout_ms)
            # Livewire lazy-loads the lots component after networkidle fires.
            page.wait_for_timeout(settle_ms)
            page_html = page.content()
        finally:
            browser.close()
    return parse(page_html)
