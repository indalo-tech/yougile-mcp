"""A task's history (its log) dates cards put into a done column unmarked, and shows moves."""

from __future__ import annotations

import json
import time

import pytest
from conftest import MSK_2026_09_30
from fastmcp import Client
from mcp.client import advertise

from yougile_mcp import apps, history, runtime
from yougile_mcp.server import build_server

DAY = 86_400_000
DONE = {"done_columns": ["Готово"]}


@pytest.fixture
def client_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return Client(build_server(rt))

    yield build
    runtime.set_default(None)


def card(fake, tid: str, number: str, created: int, column: str = "c-int-done", **extra):
    fake.tasks[tid] = {
        "id": tid,
        "title": f"Card {number}",
        "columnId": column,
        "idTaskCommon": number,
        "timestamp": created,
        "assigned": ["u-ivan"],
        **extra,
    }


def move(when: int, src: str, dst: str) -> dict:
    return {"timestamp": when, "type": "move", "userId": "u-me", "from": src, "to": dst}


def add(when: int) -> dict:
    return {"timestamp": when, "type": "add", "userId": "u-me"}


async def find(c, **args):
    return (await c.call_tool("yougile_find_tasks", args)).data


async def test_cards_moved_into_done_are_dated_by_their_log(client_for, fake):
    # moved into «Готово» on 29.09: in the period
    card(fake, "t-moved", "ID-10", MSK_2026_09_30 - 5 * DAY)
    fake.logs["t-moved"] = [
        move(MSK_2026_09_30 - DAY + 10 * 3_600_000, "c-int-review", "c-int-done"),
        move(MSK_2026_09_30 - 3 * DAY, "c-int-queue", "c-int-review"),
        add(MSK_2026_09_30 - 5 * DAY),
    ]
    # created right in «Готово» on 29.09, never moved: its creation is the date
    card(fake, "t-born", "ID-11", MSK_2026_09_30 - DAY)
    fake.logs["t-born"] = [add(MSK_2026_09_30 - DAY)]
    # moved into «Готово» on 01.09: before the period
    card(fake, "t-old", "ID-12", MSK_2026_09_30 - 40 * DAY)
    fake.logs["t-old"] = [move(MSK_2026_09_30 - 29 * DAY, "c-int-review", "c-int-done")]
    # created after the period: not looked up at all
    card(fake, "t-later", "ID-13", MSK_2026_09_30 + 5 * DAY)

    async with client_for(**DONE) as c:
        found = await find(c, completed_since="2026-09-28", completed_until="2026-09-29")
    numbers = [t["number"] for t in found["tasks"]]
    assert numbers == ["ID-10", "ID-11", "ID-3"], "newest first, the marked ID-3 too"
    dated = {t["number"]: t for t in found["tasks"]}
    assert dated["ID-10"]["completed_at"] == "2026-09-29 10:00"
    assert dated["ID-10"]["date_from_history"] is True and dated["ID-10"]["done_by_column"]
    assert "date_from_history" not in dated["ID-3"]
    assert "history_unchecked" not in found
    assert fake.calls("GET", "/api-v2/tasks/t-later/log") == 0


async def test_a_limited_number_of_logs_is_read(client_for, fake, monkeypatch):
    monkeypatch.setattr(history, "MAX_LOOKUPS", 1)
    for n in range(3):
        card(fake, f"t-{n}", f"ID-2{n}", MSK_2026_09_30 - (5 + n) * DAY)
        fake.logs[f"t-{n}"] = [move(MSK_2026_09_30 - DAY, "c-int-review", "c-int-done")]
    async with client_for(**DONE) as c:
        found = await find(c, completed_since="2026-09-28", completed_until="2026-09-29")
    assert [t["number"] for t in found["tasks"] if t.get("date_from_history")] == ["ID-20"]
    assert found["history_unchecked"] == 2 and "narrow the search" in found["history_hint"]
    assert sum(fake.calls("GET", f"/api-v2/tasks/t-{n}/log") for n in range(3)) == 1


def test_arrived_reads_the_latest_move_into_the_columns():
    events = [move(300, "a", "done"), move(200, "done", "a"), move(100, "q", "done"), add(50)]
    assert history.arrived(events, {"done"}, "done") == 300
    assert history.arrived([add(50)], {"done"}, "done") == 50
    assert history.arrived([add(50)], {"done"}, "q") is None
    assert history.arrived([move(100, "q", "a")], {"done"}, "done") is None


@pytest.mark.skipif(not apps.available(), reason="needs the apps extra")
async def test_the_standup_shows_what_moved(make_runtime, fake):
    now = int(time.time() * 1000)
    fake.tasks["t-int"]["columnId"] = "c-int-work"
    fake.logs["t-int"] = [move(now - 3_600_000, "c-int-queue", "c-int-work")]
    rt = make_runtime()
    runtime.set_default(rt)
    try:
        draws = advertise(apps.UI_EXTENSION_ID, {"mimeTypes": ["text/html;profile=mcp-app"]})
        async with Client(build_server(rt), extensions=[draws]) as client:
            result = await client.call_tool("yougile_show_standup", {"person": "Иван"})
    finally:
        runtime.set_default(None)
    standup = result.structured_content["state"]["standup"]
    assert [i["code"] for i in standup["moved"]] == ["ID-1"]
    assert standup["moved"][0]["extra"].startswith("Очередь → В работе")
    assert "**Сдвинулось:**" in standup["text"]
    assert json.loads(result.content[0].text)["moved"][0].startswith("ID-1 Internal (Очередь")
