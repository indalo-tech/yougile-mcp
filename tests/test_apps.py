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
    assert result.structured_content["state"]["can"] == {"update": False, "chat": False}


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
