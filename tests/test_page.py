import json
import re
from pathlib import Path

from autopost.page import PAGE

FIX = Path(__file__).parent / "fixtures" / "dashboard_sample.json"


def test_page_is_string_with_key_elements():
    assert isinstance(PAGE, str)
    for ident in ("kpis", "chart", "pp", "aud", "tc", "bt", "tabs", "tbody", "syncBtn", "exportBtn", "q", "banner"):
        assert 'id="%s"' % ident in PAGE
    assert "/api/dashboard?range=" in PAGE and "/api/analytics/sync" in PAGE
    assert "Performance Overview" in PAGE and "Best Posting Times" in PAGE


def test_page_has_no_unsafe_html_sinks():
    assert "innerHTML" not in PAGE and "outerHTML" not in PAGE and "insertAdjacentHTML" not in PAGE
    assert "document.write" not in PAGE and "eval(" not in PAGE
    assert not re.search(r"(src|href)=\"https?://", PAGE)  # no external assets
    assert "@import" not in PAGE and "<link" not in PAGE


def test_fixture_is_consistent():
    d = json.loads(FIX.read_text())
    assert d["kpis"]["total_posts"]["value"] == len(d["rows"]) == d["tab_counts"]["all"]
    assert sum(p["posts"] for p in d["platforms"]) == len(d["rows"])
    for p in d["platforms"]:
        assert p["posts"] == sum(1 for r in d["rows"] if r["platform"] == p["platform"])
