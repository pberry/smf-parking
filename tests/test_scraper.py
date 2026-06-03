from __future__ import annotations

from pathlib import Path

import pytest

from smf_parking.scraper import LotReading, ScrapeError, parse

FIXTURE = Path(__file__).parent / "fixtures" / "rendered_sample.html"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_expected_lots(fixture_html: str) -> None:
    readings = parse(fixture_html)
    names = {r.lot_name for r in readings}
    # Captured fixture contains these five rows. New lots (e.g. Garage 2 when
    # it opens) will appear automatically; we don't pin the exact set, only
    # that the known ones are present.
    expected = {"Garage", "Daily A", "South Economy Lot", "East Economy Lot",
                "West Economy Lot"}
    assert expected.issubset(names), names


def test_open_readings_have_integer_spaces(fixture_html: str) -> None:
    readings = parse(fixture_html)
    for r in readings:
        if r.status == "open":
            assert isinstance(r.open_spaces, int)
            assert r.open_spaces >= 0
        elif r.status == "closed":
            assert r.open_spaces == 0
        else:
            assert r.open_spaces is None


def test_closed_lot_is_marked_closed(fixture_html: str) -> None:
    readings = {r.lot_name: r for r in parse(fixture_html)}
    west = readings["West Economy Lot"]
    assert west.status == "closed"
    assert west.open_spaces == 0
    assert west.raw.lower() == "closed"


def test_lot_ids_are_stable_slugs(fixture_html: str) -> None:
    readings = parse(fixture_html)
    assert {r.lot_id for r in readings} >= {
        "garage", "daily-a", "south-economy-lot",
        "east-economy-lot", "west-economy-lot",
    }


def test_parse_raises_when_widget_missing() -> None:
    with pytest.raises(ScrapeError):
        parse("<html><body>nothing here</body></html>")


def test_lot_reading_dataclass_is_frozen() -> None:
    r = LotReading(lot_id="x", lot_name="X", open_spaces=1, status="open", raw="1")
    with pytest.raises(Exception):
        r.open_spaces = 2  # type: ignore[misc]
