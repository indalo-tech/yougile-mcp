from datetime import UTC, datetime

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


async def test_confirmation_is_asked_before_the_internal_task_is_made(client_for, fake):
    # Asking after the internal task would make it again on the repeat with confirm=true.
    before = set(fake.tasks)
    args = {
        "title": "TD-91 доработка",
        "board": "Разработка / Сайт",
        "column": "Очередь",
        "client_title": "Новая возможность",
        "client_description": "Для клиента",
    }
    async with client_for(**COPIES, confirm_projects=["Клиенты"]) as c:
        with pytest.raises(ToolError, match="confirmation_required"):
            await c.call_tool("yougile_create_task", args)
        assert set(fake.tasks) == before, "nothing written before the answer"
        result = await call(c, "yougile_create_task", **args, confirm=True)
    made = set(fake.tasks) - before
    assert len(made) == 2, "one internal task and its client copy, once"
    assert result["client_copy"]["created"] is True


async def test_a_link_line_to_an_internal_task_is_not_followed(client_for, fake):
    # The link line is text anyone can edit: ID-3 is another internal task, not a client one.
    fake.tasks["t-int"]["description"] = "План.\n\nКарточка для клиента: ID-3"
    untouched = dict(fake.tasks["t-done"])
    async with client_for(**COPIES) as c:
        logged = await call(c, "yougile_log_time", task="ID-1", hours=2)
    assert "is not in «Клиенты»" in logged["client_copy"]["error"]
    assert fake.tasks["t-done"] == untouched, "the other internal task is left alone"


def test_the_last_link_line_counts():
    task = {"description": "<p>Карточка для клиента: ID-7</p><p>Карточка для клиента: ID-9</p>"}
    assert linked(task) == "ID-9"


async def test_only_tasks_of_the_source_project(client_for):
    async with client_for(**COPIES) as c:
        with pytest.raises(ToolError, match="is not in «Разработка»"):
            await call(c, "yougile_client_copy", task="ID-2", **CLIENT_TEXT)


async def test_copies_overview_lists_linked_and_unlinked(client_for):
    # The fake's cards were done on 28.09: «lately» must reach back that far, whatever today is.
    lately = (datetime.now(UTC) - datetime(2026, 9, 28, tzinfo=UTC)).days + 7
    async with client_for(**COPIES) as c:
        board = {"board": "Разработка / Сайт", "recent_days": lately}
        before = await call(c, "yougile_client_copies", **board)
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        after = await call(c, "yougile_client_copies", **board)
    # ID-3 is done, but lately: a daily record like it still waits to be tied to a result
    assert [t["number"] for t in before["unlinked"]] == ["ID-1", "ID-3"]
    assert before["unlinked"][1]["done"] is True and before["linked"] == []
    assert before["client_board"] == "Клиенты / Сайт"
    assert [t["number"] for t in before["client_board_tasks"]] == ["ID-2"]
    assert after["linked"] == [
        {
            "number": "ID-1",
            "title": "Internal",
            "column": "Очередь",
            "plan_hours": 5,
            "work_hours": 3,
            "client_task": "ID-99",
        }
    ]


async def test_append_to_the_description(client_for, fake):
    async with client_for() as c:
        await call(c, "yougile_update_task", task="ID-1", append_description="Итог: готово")
        html = fake.tasks["t-int"]["description"]
        fake.tasks["t-int"]["description"] = "**Разбор**\n\n- шаг"
        await call(c, "yougile_update_task", task="ID-1", append_description="Итог")
        await call(c, "yougile_update_task", task="ID-2", append_description="Первый текст")
        with pytest.raises(ToolError, match="either description or append_description"):
            await call(
                c, "yougile_update_task", task="ID-1", description="a", append_description="b"
            )
    assert html == "<p>Первая строка</p><p>Вторая &amp; последняя</p><p>Итог: готово</p>"
    assert fake.tasks["t-int"]["description"] == "**Разбор**\n\n- шаг\n\nИтог"
    assert fake.tasks["t-cli"]["description"] == "Первый текст"


async def test_appended_text_goes_before_the_client_link(client_for, fake):
    async with client_for(**COPIES) as c:
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        await call(c, "yougile_update_task", task="ID-1", append_description="Итог")
    assert fake.tasks["t-int"]["description"].endswith(
        "<p>Итог</p><p>Карточка для клиента: ID-99</p>"
    )


CHAIN = {"workflows": {"Разработка / Сайт": ["Очередь", "В работе", "На проверке", "Готово"]}}


async def test_several_cards_make_one_client_task(client_for, fake):
    async with client_for(**COPIES, **CHAIN) as c:
        await call(c, "yougile_client_copy", task="ID-1", **CLIENT_TEXT)
        linked_too = await call(c, "yougile_client_copy", task="ID-3", client_task="ID-99")
        logged = await call(c, "yougile_log_time", task="ID-3", hours=2)
        moved = await call(c, "yougile_move_task", task="ID-1", column="В работе")
    assert linked_too["client_task"] == "ID-99" and linked_too["linked"] is True
    assert linked(fake.tasks["t-done"]) == "ID-99"
    # hours are the sum of the cards: ID-1 has 5 planned / 3 worked, ID-3 got 2 worked
    assert logged["client_copy"]["synced"] == ["timeTracking"]
    assert fake.tasks["t-new"]["timeTracking"] == {"plan": 5.0, "work": 5.0}
    # the done ID-3 does not pull the result forward: it goes where the open ID-1 is
    assert moved["client_copy"]["synced"] == ["column"]
    assert fake.tasks["t-new"]["columnId"] == "c-cli-work"
    assert fake.calls("POST", "/api-v2/tasks") == 1


async def test_linking_to_a_client_task_with_its_own_hours_asks_first(client_for, fake):
    fake.tasks["t-cli"]["timeTracking"] = {"plan": 8, "work": 8}
    async with client_for(**COPIES) as c:
        with pytest.raises(ToolError, match="recount_hours"):
            await call(c, "yougile_client_copy", task="ID-1", client_task="ID-2")
        assert linked(fake.tasks["t-int"]) is None
        result = await call(
            c, "yougile_client_copy", task="ID-1", client_task="ID-2", recount_hours=True
        )
        with pytest.raises(ToolError, match="already linked to ID-2"):
            await call(c, "yougile_client_copy", task="ID-1", client_task="ID-99")
    assert result["synced"] == ["deadline", "timeTracking"]
    assert fake.tasks["t-cli"]["timeTracking"] == {"plan": 5.0, "work": 3.0}


async def test_a_new_client_task_needs_its_text(client_for):
    async with client_for(**COPIES) as c:
        with pytest.raises(ToolError, match="needs title and description"):
            await call(c, "yougile_client_copy", task="ID-1")


# ---------------- review: archived cards, completion, one board ----------------


async def test_archived_cards_do_not_hold_the_client_task(make_runtime, fake):
    from yougile_mcp import copies, smart

    runtime.set_default(make_runtime(**COPIES))
    try:
        fake.tasks["t-int"]["description"] = "Карточка для клиента: ID-2"
        fake.tasks["t-arch"] = {
            "id": "t-arch",
            "title": "Брошенная",
            "columnId": "c-int-work",
            "idTaskCommon": "ID-8",
            "archived": True,
            "description": "Карточка для клиента: ID-2",
        }
        work = smart.Work(None)
        group = await copies.linked_cards(work, await work.structure(), fake.tasks["t-int"], "ID-2")
    finally:
        runtime.set_default(None)
    assert [t["id"] for t in group] == ["t-int"]


async def test_archiving_the_lagging_card_lets_the_client_task_move_on(client_for, fake):
    fake.tasks["t-int"].update(columnId="c-int-work", description="Карточка для клиента: ID-2")
    fake.tasks["t-int"]["timeTracking"] = {"plan": 0, "work": 1}
    fake.tasks["t-lag"] = {
        "id": "t-lag",
        "title": "Отстающая",
        "columnId": "c-int-queue",
        "idTaskCommon": "ID-8",
        "timeTracking": {"plan": 0, "work": 0.5},
        "description": "Карточка для клиента: ID-2",
    }
    fake.tasks["t-cli"]["timeTracking"] = {"plan": 0, "work": 1.5}
    async with client_for(**COPIES) as c:
        result = await call(c, "yougile_update_task", task="ID-8", archived=True)
    assert {"column", "timeTracking"} <= set(result["client_copy"]["synced"])
    assert fake.tasks["t-cli"]["columnId"] == "c-cli-work"
    assert fake.tasks["t-cli"]["timeTracking"] == {"plan": 0, "work": 1.0}


async def test_completing_a_linked_card_syncs_its_client_task(client_for, fake, monkeypatch):
    from yougile_mcp import copies

    seen = []

    async def follow(_work, task, what):
        seen.append((task["id"], what))
        return {}

    monkeypatch.setattr(copies, "follow", follow)
    fake.tasks["t-int"]["description"] = "Карточка для клиента: ID-2"
    async with client_for(**COPIES) as c:
        await call(c, "yougile_update_task", task="ID-1", completed=True)
    assert seen == [("t-int", ("column",))]  # completing keeps the card in the group


async def test_a_client_task_follows_cards_of_one_board(client_for, fake, monkeypatch):
    import conftest

    monkeypatch.setattr(
        conftest,
        "BOARDS",
        [*conftest.BOARDS, {"id": "b-bot", "title": "Бот", "projectId": "p-int"}],
    )
    monkeypatch.setattr(
        conftest,
        "COLUMNS",
        [*conftest.COLUMNS, {"id": "c-bot-work", "title": "В работе", "boardId": "b-bot"}],
    )
    fake.tasks["t-int"]["description"] = "Карточка для клиента: ID-2"
    fake.tasks["t-bot"] = {
        "id": "t-bot",
        "title": "Бот",
        "columnId": "c-bot-work",
        "idTaskCommon": "ID-9",
    }
    async with client_for(**COPIES) as c:
        with pytest.raises(ToolError, match="follows the cards of one internal board"):
            await call(c, "yougile_client_copy", task="ID-9", client_task="ID-2")
    assert "Карточка для клиента" not in (fake.tasks["t-bot"].get("description") or "")
