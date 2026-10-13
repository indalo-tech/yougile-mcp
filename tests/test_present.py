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


def test_text_to_html_keeps_formatting_and_escapes_the_rest():
    from yougile_mcp.copies import linked, with_link
    from yougile_mcp.present import text_to_html

    mixed = "Шаги:\n1. поправить <code>save()</code>\n2. <script>alert(1)</script> & готово"
    out = text_to_html(mixed)
    assert "<br>" in out and "<code>save()</code>" in out, "newlines and formatting kept"
    assert "<script>" not in out and "&lt;script&gt;" in out and "&amp; готово" in out
    risky = '<p onclick="x()">a</p><a href="javascript:alert(1)">b</a><a href="https://y.ru">c</a>'
    out = text_to_html(risky)
    assert "onclick" not in out and "javascript" not in out
    assert '<a href="https://y.ru">c</a>' in out and "<p>a</p>" in out
    styled = '<p><span style="color: red" class="mention" data-id="u1">@Ann</span></p>'
    assert text_to_html(styled) == styled, "YouGile's own markup survives"
    assert text_to_html("a < b, <сегодня>") == "a &lt; b, &lt;сегодня&gt;"
    # The client-copy link line survives a round trip, once
    desc = with_link(text_to_html("<p>План</p>"), "ID-7")
    again = with_link(text_to_html(desc), "ID-7")
    assert again.count("Карточка для клиента") == 1 and linked({"description": again}) == "ID-7"
