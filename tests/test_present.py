from zoneinfo import ZoneInfo

import pytest

from yougile_mcp.present import (
    format_deadline,
    html_to_text,
    parse_when,
    text_to_html,
)

MSK = ZoneInfo("Europe/Moscow")
MIDNIGHT = 1790715600000  # 2026-09-30 00:00 MSK, what the YouGile UI stores for a date


def test_dates_become_company_midnight():
    assert parse_when("2026-09-30", MSK) == (MIDNIGHT, False)
    assert parse_when("30.09.2026", MSK) == (MIDNIGHT, False)
    assert parse_when("2026-09-30 18:30", MSK) == (MIDNIGHT + (18 * 60 + 30) * 60_000, True)
    assert parse_when("30.09.2026 18:30", MSK)[1] is True
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_when("next friday", MSK)


def test_deadline_rendering():
    assert format_deadline({"deadline": MIDNIGHT + 12}, MSK) == "2026-09-30"
    assert format_deadline({"deadline": MIDNIGHT, "withTime": True}, MSK) == "2026-09-30 00:00"
    assert format_deadline({"deadline": MIDNIGHT, "startDate": MIDNIGHT - 2 * 86_400_000}, MSK) == {
        "start": "2026-09-28",
        "end": "2026-09-30",
    }
    assert format_deadline({"deadline": MIDNIGHT, "deleted": True}, MSK) is None
    assert format_deadline(None, MSK) is None


def test_html_conversions():
    assert text_to_html("a < b\nnext") == "a &lt; b<br>next"
    assert text_to_html("<p>already html</p>") == "<p>already html</p>"
    assert html_to_text("<p>one</p><p>two &amp; three</p>") == "one\ntwo & three"
    assert html_to_text("a<br>b<ul><li>x</li></ul>") == "a\nb- x"
    assert html_to_text(None) == ""
