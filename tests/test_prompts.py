from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastmcp import Client

from yougile_mcp import runtime
from yougile_mcp.prompts import previous_workday
from yougile_mcp.server import build_server


@pytest.fixture
def client_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return Client(build_server(rt))

    yield build
    runtime.set_default(None)


async def text(client, name, **args):
    result = await client.get_prompt(name, args)
    return result.messages[0].content.text


def test_previous_workday_skips_the_weekend():
    assert previous_workday(date(2026, 9, 28)) == date(2026, 9, 25), "Monday -> Friday"
    assert previous_workday(date(2026, 9, 27)) == date(2026, 9, 25), "Sunday -> Friday"
    assert previous_workday(date(2026, 9, 26)) == date(2026, 9, 25), "Saturday -> Friday"
    assert previous_workday(date(2026, 9, 23)) == date(2026, 9, 22)


async def test_prompts_are_listed_with_titles(client_for):
    async with client_for() as c:
        prompts = {p.name: p for p in await c.list_prompts()}
    assert set(prompts) == {"standup", "hours_report", "triage", "client_sync"}
    assert prompts["standup"].title == "Стендап"
    args = {a.name: a.required for a in prompts["hours_report"].arguments}
    assert args == {"since": False, "until": False, "project": False, "person": False}


async def test_standup_uses_the_company_day(client_for):
    zone = ZoneInfo("Asia/Yerevan")
    today = datetime.now(zone).date()
    async with client_for(timezone="Asia/Yerevan") as c:
        mine = await text(c, "standup")
        theirs = await text(c, "standup", person="Иван", project="Разработка")
    assert "Asia/Yerevan" in mine and f"{today:%d.%m.%Y}" in mine
    since = previous_workday(today).isoformat()
    assert f'yougile_find_tasks(assignee="me", completed_since="{since}")' in mine
    assert "стендап для Иван" in theirs
    assert 'assignee="Иван", project="Разработка"' in theirs


async def test_hours_report_defaults_to_this_week(client_for):
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    monday = today - timedelta(days=today.weekday())
    async with client_for() as c:
        week = await text(c, "hours_report")
        custom = await text(c, "hours_report", since="2026-09-01", until="2026-09-30", person="me")
    assert f'completed_since="{monday.isoformat()}", completed_until="{today.isoformat()}"' in week
    assert "без дат списания" in week, "the report says what YouGile cannot tell"
    assert 'assignee="me", completed_since="2026-09-01", completed_until="2026-09-30"' in custom


async def test_triage_changes_nothing_without_consent(client_for):
    async with client_for() as c:
        board = await text(c, "triage", board="Разработка / Сайт", column="Очередь")
        company = await text(c, "triage")
    assert 'board="Разработка / Сайт", column="Очередь", status="open"' in board
    assert "во всей компании" in company
    assert "только после явного согласия" in board and "yougile_update_task" in board
