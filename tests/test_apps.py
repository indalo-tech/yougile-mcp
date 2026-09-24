import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.client import advertise

from yougile_mcp import apps, runtime
from yougile_mcp.server import build_server

pytestmark = pytest.mark.skipif(not apps.available(), reason="needs the apps extra")

CHAIN = {"Разработка / Сайт": ["Очередь", "В работе", "На проверке", "Готово"]}
DRAWS = advertise(apps.UI_EXTENSION_ID, {"mimeTypes": ["text/html;profile=mcp-app"]})


@pytest.fixture
def server_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return build_server(rt)

    yield build
    runtime.set_default(None)


def drawing(server):
    return Client(server, extensions=[DRAWS])


async def test_screens_only_for_clients_that_draw_them(server_for):
    server = server_for()
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert not names & {*apps.SCREENS, *apps.ACTIONS}
    async with drawing(server) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert {*apps.SCREENS, *apps.ACTIONS} <= set(tools)
    assert tools["yougile_show_task"].meta["ui"]["visibility"] == ["model"]
    assert tools["yougile_show_task"].meta["ui"]["resourceUri"].startswith("ui://prefab/")
    assert tools["yougile_app_move"].meta["ui"]["visibility"] == ["app"]


async def test_buttons_follow_permissions(server_for):
    async with drawing(server_for(role="reader")) as client:
        names = {t.name for t in await client.list_tools()}
        result = await client.call_tool("yougile_show_task", {"task": "ID-1"})
    assert {"yougile_show_task", "yougile_show_tasks", "yougile_app_task"} <= names
    assert not {"yougile_app_move", "yougile_app_complete", "yougile_app_send"} & names
    can = result.structured_content["state"]["can"]
    assert can == {"update": False, "chat": False, "create": False}


async def test_task_card_screen(server_for):
    async with drawing(server_for()) as client:
        result = await client.call_tool("yougile_show_task", {"task": "ID-1"})
    for_model = json.loads(result.content[0].text)
    assert for_model["shown_to_user"] == "task card" and for_model["title"] == "Internal"
    assert for_model["checklists"][0]["items"] == ["[ ] Написать код", "[ ] Проверить"]
    assert "id" not in for_model and "columns" not in for_model
    screen = result.structured_content
    assert "$prefab" in screen and screen["view"]
    card = screen["state"]["task"]
    assert card["id"] == "t-int" and card["hours"]["percent"] == 60
    assert [c["title"] for c in card["columns"]] == ["Очередь", "В работе", "На проверке", "Готово"]
    assert card["messages"][-1]["author"] == "Иван Петров"
    assert card["mine"] is False and card["client_facing"] is False


async def test_task_table_screen_and_refresh(server_for):
    async with drawing(server_for()) as client:
        result = await client.call_tool("yougile_show_tasks", {"board": "Разработка / Сайт"})
        again = await client.call_tool("yougile_app_tasks", {"board": "Разработка / Сайт"})
    state = result.structured_content["state"]
    assert [row["number"] for row in state["tasks"]] == ["ID-1"]
    assert state["tasks"][0]["id"] == "t-int" and state["tasks"][0]["status"] == "Открыта"
    assert state["tasks"][0]["where"] == "Очередь"  # the scope is in the title already
    assert json.loads(result.content[0].text)["tasks"][0]["number"] == "ID-1"
    assert again.structured_content == {"tasks": state["tasks"], "count": "1"}


async def test_buttons_write_and_return_the_fresh_card(server_for, fake):
    async with drawing(server_for(workflows=CHAIN)) as client:
        checked = await client.call_tool(
            "yougile_app_check", {"task": "t-int", "checklist": 0, "item": 1, "done": True}
        )
        taken = await client.call_tool("yougile_app_take", {"task": "t-int"})
        logged = await client.call_tool("yougile_app_log_time", {"task": "t-int", "hours": 1.5})
        sent = await client.call_tool("yougile_app_send", {"task": "t-int", "text": "Смотрю"})
        moved = await client.call_tool(
            "yougile_app_move", {"task": "t-int", "column": "c-int-review"}
        )
        done = await client.call_tool("yougile_app_complete", {"task": "t-int", "completed": True})
    assert checked.structured_content["checklists"][0]["items"][1]["done"] is True
    assert taken.structured_content["mine"] is True
    assert fake.tasks["t-int"]["assigned"] == ["u-ivan", "u-me"]
    assert logged.structured_content["hours"]["work"] == 4.5
    assert sent.structured_content["messages"][-1]["text"] == "Смотрю"
    # the fake refuses jumps over the Workflow chain: the move went step by step
    assert moved.structured_content["where"] == "Разработка / Сайт / На проверке"
    assert done.structured_content["done"] is True and fake.tasks["t-int"]["completed"] is True


async def test_click_confirms_writes_into_client_projects(server_for, fake):
    async with drawing(server_for(confirm_projects=["Клиенты"])) as client:
        card = await client.call_tool("yougile_show_task", {"task": "ID-2"})
        done = await client.call_tool("yougile_app_complete", {"task": "t-cli", "completed": True})
    assert card.structured_content["state"]["task"]["client_facing"] is True
    assert done.structured_content["done"] is True and fake.tasks["t-cli"]["completed"] is True


async def test_buttons_still_obey_the_policy(server_for, fake):
    async with drawing(server_for(projects=["Разработка"])) as client:
        with pytest.raises(ToolError, match="outside the projects"):
            await client.call_tool("yougile_app_complete", {"task": "t-cli", "completed": True})
    assert "completed" not in fake.tasks["t-cli"]


async def test_screens_can_ask_for_the_whole_window(server_for):
    async with drawing(server_for()) as client:
        card = await client.call_tool("yougile_show_task", {"task": "ID-1"})
        table = await client.call_tool("yougile_show_tasks", {"board": "Разработка / Сайт"})
    for result in (card, table):
        view = json.dumps(result.structured_content["view"])
        assert '"mode": "fullscreen"' in view and '"mode": "inline"' in view


async def test_board_screen_columns_cards_and_filter(server_for):
    async with drawing(server_for()) as client:
        result = await client.call_tool("yougile_show_board", {"board": "Разработка / Сайт"})
        annas = await client.call_tool(
            "yougile_app_board", {"board": "b-hub-int", "assignee": "u-me"}
        )
    board = result.structured_content["state"]["board"]
    assert board["label"] == "Разработка / Сайт"
    columns = {c["title"]: c for c in board["columns"]}
    assert list(columns) == ["Очередь", "В работе", "На проверке", "Готово"]
    card = columns["Очередь"]["tasks"][0]
    assert card["code"] == "ID-1" and card["prev"] == "" and card["next"] == "c-int-work"
    assert columns["Готово"]["tasks"][0]["done"] is True and columns["Готово"]["count"] == "1"
    for_model = json.loads(result.content[0].text)
    assert for_model["columns"][0]["tasks"][0]["number"] == "ID-1"
    # nobody assigned Anna: the filtered board has no cards
    assert all(not c["tasks"] for c in annas.structured_content["columns"])


async def test_form_needs_the_right_to_create(server_for):
    async with drawing(server_for(role="member", deny=["tasks.create"])) as client:
        names = {t.name for t in await client.list_tools()}
    assert "yougile_new_task_form" not in names and "yougile_app_create" not in names
    assert "yougile_show_board" in names


async def test_form_prefills_and_creates_the_task(server_for, fake):
    async with drawing(server_for(workflows=CHAIN)) as client:
        form = await client.call_tool(
            "yougile_new_task_form",
            {"title": "Сделать отчёт", "board": "Разработка / Сайт", "deadline": "30.09.2026"},
        )
        columns = await client.call_tool("yougile_app_columns", {"board": "b-hub-cli"})
        created = await client.call_tool(
            "yougile_app_create",
            {
                "board": "b-hub-int",
                "column": "c-int-work",
                "title": "Сделать отчёт",
                "description": "",
                "assignee": "u-ivan",
                "deadline": "2026-09-30",
                "plan_hours": "2,5",
                "checklist": "Собрать данные\n\nНаписать",
            },
        )
    state = form.structured_content["state"]
    assert state["board_id"] == "b-hub-int" and state["column_id"] == "c-int-queue"
    assert state["title"] == "Сделать отчёт" and state["deadline"] == "2026-09-30"
    assert json.loads(form.content[0].text)["board"] == "Разработка / Сайт"
    assert columns.structured_content["column_id"] == "c-cli-queue"
    task = fake.tasks["t-new"]
    assert task["columnId"] == "c-int-work" and task["assigned"] == ["u-ivan"]
    assert task["timeTracking"] == {"plan": 2.5, "work": 0} and "description" not in task
    assert [i["title"] for i in task["checklists"][0]["items"]] == ["Собрать данные", "Написать"]
    assert created.structured_content["number"] == "ID-99"


async def test_standup_screen_sorts_the_open_work(server_for):
    async with drawing(server_for()) as client:
        result = await client.call_tool("yougile_show_standup", {"person": "Иван"})
        again = await client.call_tool("yougile_app_standup", {"person": "u-ivan"})
    standup = result.structured_content["state"]["standup"]
    assert standup["name"] == "Иван Петров" and standup["person"] == "u-ivan"
    assert [i["code"] for i in standup["queue"]] == ["ID-1"] and standup["doing"] == []
    assert "**Вчера:**" in standup["text"] and "**Блокеры и риски:**" in standup["text"]
    assert json.loads(result.content[0].text)["queue"] == ["ID-1 Internal"]
    assert again.structured_content["counts"] == standup["counts"]


async def test_hours_screen_counts_the_period_and_open_work(server_for):
    async with drawing(server_for()) as client:
        result = await client.call_tool(
            "yougile_show_hours", {"since": "2026-09-01", "until": "30.09.2026"}
        )
        other = await client.call_tool(
            "yougile_app_hours", {"since": "2026-10-01", "until": "2026-10-31"}
        )
    report = result.structured_content["state"]["report"]
    assert (report["since"], report["until"]) == ("2026-09-01", "2026-09-30")
    assert report["totals"]["tasks"] == 1  # ID-3, completed on 28.09
    assert report["by_person"] == [{"name": "Без исполнителя", "plan": 0.0, "work": 0.0}]
    assert [r["code"] for r in report["no_plan"]] == ["ID-3"]
    assert report["logged"] == [
        {"code": "ID-1", "title": "Internal", "plan": 5.0, "work": 3.0, "left": 2.0}
    ]
    assert other.structured_content["totals"]["tasks"] == 0


async def test_triage_screen_and_row_edit(server_for, fake):
    async with drawing(server_for(workflows=CHAIN)) as client:
        result = await client.call_tool("yougile_show_triage", {"board": "Разработка / Сайт"})
        saved = await client.call_tool(
            "yougile_app_triage_save",
            {
                "task": "t-int",
                "board": "b-hub-int",
                "column": "c-int-queue",
                "assignee": "u-me",
                "deadline": "2026-10-15",
                "plan_hours": "8",
            },
        )
    triage = result.structured_content["state"]["triage"]
    assert triage["label"] == "Разработка / Сайт / Очередь"
    row = triage["rows"][0]
    assert row["code"] == "ID-1" and row["assignee_id"] == "u-ivan" and row["plan"] == "5"
    assert not {"нет исполнителя", "нет срока", "нет плана"} & set(row["problems"])
    assert {"name": "Иван Петров", "tasks": 1, "plan": 5.0} in triage["load"]
    task = fake.tasks["t-int"]
    assert task["assigned"] == ["u-ivan", "u-me"] and task["timeTracking"]["plan"] == 8
    assert saved.structured_content["rows"][0]["deadline"] == "2026-10-15"


async def test_triage_save_changes_nothing_when_nothing_changed(server_for, fake):
    async with drawing(server_for(workflows=CHAIN)) as client:
        await client.call_tool(
            "yougile_app_triage_save",
            {
                "task": "t-int",
                "board": "b-hub-int",
                "column": "c-int-queue",
                "assignee": "u-ivan",
                "deadline": "2026-09-30",
                "plan_hours": "5",
            },
        )
    assert fake.calls("PUT", "/api-v2/tasks/t-int") == 0


async def test_attach_file_tool_posts_the_file_into_the_chat(server_for, fake):
    async with Client(server_for()) as client:
        result = await client.call_tool(
            "yougile_attach_file",
            {
                "task": "ID-1",
                "content_base64": "aGVsbG8=",
                "filename": "отчёт.txt",
                "comment": "См.",
            },
        )
    assert fake.uploads == ["отчёт.txt"]
    texts = [m["text"] for m in fake.messages["t-int"][-2:]]
    assert texts == ["См.", "/root/#file:/user-data/company/отчёт.txt"]
    assert result.data["attached"] == [
        {"name": "отчёт.txt", "url": "https://yougile.test/user-data/company/отчёт.txt"}
    ]


async def test_attach_needs_upload_and_chat_rights(server_for):
    async with drawing(server_for(role="member", deny=["files.upload"])) as client:
        names = {t.name for t in await client.list_tools()}
    assert not {"yougile_attach_file", "yougile_attach_files", "yougile_app_attach"} & names


async def test_attach_screen_uploads_dropped_files(server_for, fake):
    dropped = [
        {"name": "a.png", "size": 5, "type": "image/png", "data": "aGVsbG8="},
        {"name": "b.pdf", "size": 5, "type": "application/pdf", "data": "aGVsbG8="},
    ]
    async with drawing(server_for(confirm_projects=["Клиенты"])) as client:
        screen = await client.call_tool("yougile_attach_files", {"task": "ID-2"})
        result = await client.call_tool(
            "yougile_app_attach", {"task": "t-cli", "files": dropped, "comment": ""}
        )
    assert screen.structured_content["state"]["task"]["number"] == "ID-2"
    assert fake.uploads == ["a.png", "b.pdf"]  # a click needs no further confirmation
    assert [m["text"] for m in fake.messages["t-cli"]] == [
        "/root/#file:/user-data/company/a.png",
        "/root/#file:/user-data/company/b.pdf",
    ]
    assert [a["name"] for a in result.structured_content["attached"]] == ["a.png", "b.pdf"]
    assert all(m["textHtml"] == "" for m in fake.messages["t-cli"])  # as YouGile stores files


async def test_attach_screen_refuses_big_and_broken_files(server_for, fake, monkeypatch):
    from yougile_mcp.apps import files

    monkeypatch.setattr(files, "MAX_FILE_MB", 0)
    async with drawing(server_for()) as client:
        with pytest.raises(ToolError, match="larger than 0 MB"):
            await client.call_tool(
                "yougile_app_attach",
                {"task": "t-int", "files": [{"name": "big.bin", "data": "aGVsbG8="}]},
            )
        monkeypatch.setattr(files, "MAX_FILE_MB", 10)
        with pytest.raises(ToolError, match="damaged"):
            await client.call_tool(
                "yougile_app_attach",
                {"task": "t-int", "files": [{"name": "bad.bin", "data": "не base64"}]},
            )
    assert fake.uploads == []
