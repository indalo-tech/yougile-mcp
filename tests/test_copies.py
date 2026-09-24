import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from yougile_mcp import runtime
from yougile_mcp.config import ClientCopy, ConfigError, WorkspaceConfig
from yougile_mcp.copies import linked, with_link
from yougile_mcp.server import build_server

COPIES = {"client_copy": {"from": "Разработка", "to": "Клиенты"}}
CLIENT_TEXT = {"title": "Проверка номера", "description": "Номер будет подтверждаться."}


@pytest.fixture
def client_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return Client(build_server(rt))

    yield build
    runtime.set_default(None)


async def call(client, tool, **args):
    return (await client.call_tool(tool, args)).data


def test_config_reads_client_copy():
    cfg = WorkspaceConfig.from_dict({"client_copy": {**COPIES["client_copy"], "rules": ["a", "b"]}})
    assert cfg.client_copy == ClientCopy("Разработка", "Клиенты", "a\nb")
    assert WorkspaceConfig.from_dict({"client_copy": None}).client_copy is None
    with pytest.raises(ConfigError, match="both from and to"):
        WorkspaceConfig.from_dict({"client_copy": {"from": "Разработка"}})


def test_link_line_keeps_the_description_format():
    html = with_link("<p>Разбор</p><p>Карточка для клиента: ID-5</p>", "ID-9")
    assert html == "<p>Разбор</p><p>Карточка для клиента: ID-9</p>"
    text = with_link("**Разбор**\n\n## Шаги\n\nКарточка для клиента: ID-5", "ID-9")
    assert text == "**Разбор**\n\n## Шаги\n\nКарточка для клиента: ID-9"
    assert linked({"description": text}) == "ID-9" and linked({"description": "нет"}) is None


async def test_copy_tools_only_where_the_setting_is_on(client_for):
    async with client_for() as c:
        tools = {t.name: t for t in await c.list_tools()}
    assert "yougile_client_copy" not in tools and "yougile_client_copies" not in tools
    assert "client_title" not in tools["yougile_create_task"].input_schema["properties"]
    async with client_for(**COPIES) as c:
        tools = {t.name: t for t in await c.list_tools()}
        overview = await call(c, "yougile_overview")
    assert {"yougile_client_copy", "yougile_client_copies"} <= set(tools)
    assert "client_title" in tools["yougile_create_task"].input_schema["properties"]
    assert (
        overview["client_copy"]["to"] == "Клиенты"
        and "личных данных" in (overview["client_copy"]["rules"])
    )


async def test_copy_creates_the_twin_and_links_it(client_for, fake):
    async with client_for(**COPIES) as c:
        result = await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
    assert result == {
        "task": "ID-1",
        "client_task": "ID-99",
        "created": True,
        "where": "Клиенты / Сайт / Очередь",
    }
    twin = fake.tasks["t-new"]
    assert twin["columnId"] == "c-cli-queue" and twin["title"] == "Проверка номера"
    assert twin["timeTracking"] == {"plan": 5, "work": 3}
    assert twin["deadline"]["deadline"] == fake.tasks["t-int"]["deadline"]["deadline"]
    assert fake.tasks["t-int"]["description"].endswith("<p>Карточка для клиента: ID-99</p>")


async def test_twin_follows_moves_hours_and_deadline(client_for, fake):
    async with client_for(**COPIES) as c:
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        moved = await call(c, "yougile_move_task", task="ID-1", column="В работе")
        logged = await call(c, "yougile_log_time", task="ID-1", hours=2)
        updated = await call(c, "yougile_update_task", task="ID-1", deadline="2026-10-15")
        # the client board has no «На проверке»: the twin stays, nothing breaks
        review = await call(c, "yougile_move_task", task="ID-1", column="На проверке")
    twin = fake.tasks["t-new"]
    assert moved["client_copy"] == {"client_task": "ID-99", "synced": ["column"]}
    assert logged["client_copy"]["synced"] == ["timeTracking"]
    assert updated["client_copy"]["synced"] == ["deadline"]
    assert "client_copy" not in review
    assert twin["columnId"] == "c-cli-work" and twin["timeTracking"] == {"plan": 5, "work": 5}
    assert twin["deadline"]["deadline"] == fake.tasks["t-int"]["deadline"]["deadline"]


async def test_new_description_keeps_the_link(client_for, fake):
    async with client_for(**COPIES) as c:
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        await call(c, "yougile_update_task", task="ID-1", description="Новый разбор")
    assert linked(fake.tasks["t-int"]) == "ID-99"


async def test_second_copy_updates_the_same_twin(client_for, fake):
    async with client_for(**COPIES) as c:
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        again = await call(
            c, "yougile_client_copy", task="ID-1", title="Новый заголовок", description="Текст"
        )
    assert again["updated"] is True and fake.tasks["t-new"]["title"] == "Новый заголовок"
    assert fake.calls("POST", "/api-v2/tasks") == 1


async def test_create_task_with_its_client_copy(client_for, fake):
    async with client_for(**COPIES) as c:
        result = await call(
            c,
            "yougile_create_task",
            title="TD-90 рефакторинг",
            board="Разработка / Сайт",
            column="Очередь",
            client_title="Новая возможность",
            client_description="Для клиента",
        )
    assert result["created"]["number"] == "ID-99"
    assert result["client_copy"] == {
        "task": "ID-99",
        "client_task": "ID-100",
        "created": True,
        "where": "Клиенты / Сайт / Очередь",
    }
    assert fake.tasks["t-new2"]["title"] == "Новая возможность"
    assert linked(fake.tasks["t-new"]) == "ID-100"


async def test_only_tasks_of_the_source_project(client_for):
    async with client_for(**COPIES) as c:
        with pytest.raises(ToolError, match="is not in «Разработка»"):
            await call(c, "yougile_client_copy", task="ID-2", **CLIENT_TEXT)


async def test_copies_overview_lists_linked_and_unlinked(client_for):
    async with client_for(**COPIES) as c:
        before = await call(c, "yougile_client_copies", board="Разработка / Сайт")
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        after = await call(c, "yougile_client_copies", board="Разработка / Сайт")
    assert [t["number"] for t in before["unlinked"]] == ["ID-1"] and before["linked"] == []
    assert before["client_board"] == "Клиенты / Сайт"
    assert [t["number"] for t in before["client_board_tasks"]] == ["ID-2"]
    assert after["linked"] == [
        {
            "number": "ID-1",
            "title": "Internal",
            "column": "Очередь",
            "plan_hours": 5,
            "client_task": "ID-99",
        }
    ]
