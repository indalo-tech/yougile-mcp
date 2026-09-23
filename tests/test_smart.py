import pytest
from conftest import MSK_2026_09_30
from fastmcp import Client
from fastmcp.exceptions import ToolError

from yougile_mcp import runtime
from yougile_mcp.server import build_server

CHAIN = {"Разработка / Сайт": ["Очередь", "В работе", "На проверке", "Готово"]}


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


async def test_overview_lists_structure_in_order(client_for):
    async with client_for(workflows=CHAIN, projects=["Разработка"]) as c:
        data = await call(c, "yougile_overview")
    assert [p["project"] for p in data["projects"]] == ["Разработка"], "allowlist hides others"
    board = data["projects"][0]["boards"][0]
    assert board["columns"] == ["Очередь", "В работе", "На проверке", "Готово"]
    assert board["workflow"] == CHAIN["Разработка / Сайт"]
    assert "role=admin" in data["permissions"] and data["timezone"] == "Europe/Moscow"


async def test_find_tasks_by_place_assignee_and_number(client_for, fake):
    async with client_for(project="Разработка") as c:
        default_scope = await call(c, "yougile_find_tasks")
        assert default_scope["scope"] == "Разработка"
        assert [t["number"] for t in default_scope["tasks"]] == ["ID-1"], "open only by default"

        in_column = await call(c, "yougile_find_tasks", board="Разработка / Сайт", column="Готово")
        assert [t["number"] for t in in_column["tasks"]] == ["ID-3"], "any status in a column"

        mine = await call(c, "yougile_find_tasks", assignee="Иван", status="any")
        assert [t["number"] for t in mine["tasks"]] == ["ID-1"]
        assert mine["tasks"][0]["assignees"] == ["Иван Петров"]

        by_number = await call(c, "yougile_find_tasks", text="DEV-1")
        assert by_number["tasks"][0]["where"] == "Разработка / Сайт / Очередь"
        assert by_number["scope"] == "task number", "same shape as any other search"

        by_words = await call(c, "yougile_find_tasks", text="finished WORK", status="any")
        assert [t["number"] for t in by_words["tasks"]] == ["ID-3"]


async def test_find_completed_in_a_period_and_overdue(client_for, fake):
    fake.tasks["t-int"]["deadline"] = {"deadline": 1577836800000}  # 2020-01-01, long past
    fake.tasks["t-done"]["deadline"] = {"deadline": 1577836800000}
    async with client_for() as c:
        done = await call(c, "yougile_find_tasks", completed_since="2026-09-28")
        assert [t["number"] for t in done["tasks"]] == ["ID-3"], "a period implies completed"
        assert done["tasks"][0]["completed_at"] == "2026-09-28 15:00"
        assert "overdue" not in done["tasks"][0], "a completed task is never overdue"
        until = await call(c, "yougile_find_tasks", completed_until="28.09.2026")
        assert [t["number"] for t in until["tasks"]] == ["ID-3"], "until covers the whole day"
        assert (await call(c, "yougile_find_tasks", completed_since="2026-09-29"))["count"] == 0
        assert (await call(c, "yougile_find_tasks", completed_until="2026-09-27"))["count"] == 0
        open_tasks = await call(c, "yougile_find_tasks", board="Разработка / Сайт")
        assert open_tasks["tasks"][0]["overdue"] is True


async def test_done_columns_count_as_done(client_for, fake):
    fake.tasks["t-done"].update(completed=False, completedTimestamp=None)  # moved, not marked
    fake.tasks["t-done"]["deadline"] = {"deadline": 1577836800000}  # long past: yet not overdue
    async with client_for(done_columns=["готово"]) as c:
        overview = await call(c, "yougile_overview")
        assert overview["done_columns"] == ["готово"]
        open_now = await call(c, "yougile_find_tasks", board="Разработка / Сайт")
        assert [t["number"] for t in open_now["tasks"]] == ["ID-1"], "done column is not open"
        done = await call(c, "yougile_find_tasks", board="Разработка / Сайт", status="completed")
        task = done["tasks"][0]
        assert (task["number"], task["status"], task["done_by_column"]) == (
            "ID-3",
            "completed",
            True,
        )
        assert "overdue" not in task and "completed_at" not in task
        card = await call(c, "yougile_task", task="ID-3")
        assert card["status"] == "completed" and card["done_by_column"] is True


async def test_move_into_a_done_column_marks_completed(client_for, fake):
    async with client_for(workflows=CHAIN, done_columns=["Разработка / Сайт / Готово"]) as c:
        data = await call(c, "yougile_move_task", task="ID-1", column="Готово")
        assert data["completed"] is True
        bodies = fake.bodies("PUT", "/api-v2/tasks/t-int")
        assert [b.get("completed") for b in bodies] == [None, None, True], "only on the last step"
        back = await call(c, "yougile_move_task", task="ID-1", column="На проверке")
        assert back["completed"] is False, "moving out of a done column reopens the task"
        assert fake.tasks["t-int"]["completed"] is False
        stay = await call(c, "yougile_move_task", task="ID-1", column="В работе")
        assert "completed" not in stay, "between ordinary columns nothing changes"


async def test_task_card_has_names_dates_and_messages(client_for):
    async with client_for() as c:
        card = await call(c, "yougile_task", task="ID-1", messages=2)
    assert card["where"] == "Разработка / Сайт / Очередь"
    assert card["assignees"] == ["Иван Петров"]
    assert card["deadline"] == "2026-09-30"
    assert card["hours"] == {"plan": 5, "work": 3}
    assert card["checklists"][0]["items"] == ["[ ] Написать код", "[ ] Проверить"]
    assert card["stickers"] == {"Приоритет": "Высокий"}
    assert card["other_stickers"] == {"st-num": "0"}, "unnamed stickers never pose as names"
    assert card["description"] == "Первая строка\nВторая & последняя"
    assert card["created"]["by"] == "Анна Смирнова"
    assert [m["text"] for m in card["messages"]] == ["Ок", "Готово к проверке"]


async def test_create_task_with_names(client_for, fake):
    async with client_for(workflows=CHAIN, board="Сайт", project="Разработка") as c:
        data = await call(
            c,
            "yougile_create_task",
            title="Новая",
            description="строка 1\nстрока 2",
            assignees=["me", "ivan@example.com"],
            deadline="30.09.2026",
            plan_hours=4,
            checklist=["a", "b"],
            color="red",
        )
    body = fake.bodies("POST", "/api-v2/tasks")[0]
    assert body["columnId"] == "c-int-queue", "first column of the Workflow chain"
    assert body["assigned"] == ["u-me", "u-ivan"]
    assert body["deadline"] == {"deadline": MSK_2026_09_30, "withTime": False}
    assert body["timeTracking"] == {"plan": 4, "work": 0}
    assert body["checklists"][0]["items"][1] == {"title": "b", "isCompleted": False}
    assert body["description"] == "строка 1<br>строка 2"
    assert body["color"] == "task-red"
    assert data["created"]["number"] == "ID-99"


async def test_create_task_needs_a_column_without_workflow(client_for):
    async with client_for() as c:
        with pytest.raises(ToolError, match="column is required.*Очередь, В работе"):
            await call(c, "yougile_create_task", title="x", board="Клиенты / Сайт")


async def test_update_task_checklist_assignees_deadline(client_for, fake):
    async with client_for() as c:
        data = await call(
            c,
            "yougile_update_task",
            task="ID-1",
            check=["написать"],
            add_items=["Выкатить"],
            add_assignees=["Анна"],
            deadline="none",
            completed=True,
        )
        assert data["changed"] == ["assigned", "checklists", "completed", "deadline"]
        body = fake.bodies("PUT", "/api-v2/tasks/t-int")[-1]
        items = body["checklists"][0]["items"]
        assert items[0] == {"title": "Написать код", "isCompleted": True}
        assert items[-1] == {"title": "Выкатить", "isCompleted": False}
        assert body["assigned"] == ["u-ivan", "u-me"]
        assert body["deadline"] == {"deleted": True}
        with pytest.raises(ToolError, match="nothing to change"):
            await call(c, "yougile_update_task", task="ID-1")
        with pytest.raises(ToolError, match="not found"):
            await call(c, "yougile_update_task", task="ID-1", check=["нет такого"])


async def test_move_follows_workflow_chain(client_for, fake):
    async with client_for(workflows=CHAIN) as c:
        data = await call(c, "yougile_move_task", task="ID-1", column="Готово")
    assert data["path"] == ["В работе", "На проверке", "Готово"]
    assert fake.tasks["t-int"]["columnId"] == "c-int-done"


async def test_move_backwards_and_noop(client_for, fake):
    fake.tasks["t-int"]["columnId"] = "c-int-done"
    async with client_for(workflows=CHAIN) as c:
        back = await call(c, "yougile_move_task", task="ID-1", column="В работе")
        assert back["path"] == ["На проверке", "В работе"]
        same = await call(c, "yougile_move_task", task="ID-1", column="в работе")
        assert same["moved"] is False


async def test_move_without_chain_explains_workflow(client_for, fake):
    async with client_for() as c:
        with pytest.raises(ToolError, match="Workflow extension.*workflows.*Разработка / Сайт"):
            await call(c, "yougile_move_task", task="ID-1", column="Готово")
    assert fake.tasks["t-int"]["columnId"] == "c-int-queue"


async def test_hints_point_where_settings_live(make_runtime):
    rt = make_runtime()
    rt.settings_hint = "the admin page https://yougile.example/admin"
    runtime.set_default(rt)
    try:
        async with Client(build_server(rt)) as c:
            with pytest.raises(ToolError, match="no default board is set in the admin page"):
                await call(c, "yougile_create_task", title="x")
            with pytest.raises(ToolError, match=r"workflows setting \(the admin page"):
                await call(c, "yougile_move_task", task="ID-1", column="Готово")
    finally:
        runtime.set_default(None)


async def test_log_time_adds_to_worked_hours(client_for, fake):
    async with client_for() as c:
        data = await call(c, "yougile_log_time", task="DEV-1", hours=1.5)
        assert data == {
            "task": "ID-1",
            "hours": {"plan": 5, "work": 4.5},
            "was": {"plan": 5, "work": 3},
        }
        with pytest.raises(ToolError, match="negative"):
            await call(c, "yougile_log_time", task="ID-1", hours=-10)


async def test_task_chat_sends_and_reads(client_for, fake):
    async with client_for() as c:
        data = await call(c, "yougile_task_chat", task="ID-1", send="Привет\nмир", limit=2)
    sent = fake.bodies("POST", "/api-v2/chats/t-int/messages")[0]
    assert sent == {"text": "Привет\nмир", "textHtml": "Привет<br>мир", "label": ""}
    assert [m["text"] for m in data["messages"]] == ["Готово к проверке", "Привет\nмир"]


async def test_client_project_write_needs_confirmation_once(client_for, fake):
    prompts = []

    async def approve(message, response_type, params, context):
        prompts.append(message)
        return response_type(value=True)

    rt_client = client_for(confirm_projects=["Клиенты"])
    async with Client(rt_client.transport, elicitation_handler=approve) as c:
        await call(c, "yougile_update_task", task="ID-2", title="x")
        await call(c, "yougile_log_time", task="ID-1", hours=1)  # internal: no prompt
    assert len(prompts) == 1 and "Клиенты" in prompts[0]


async def test_multi_step_move_asks_once(client_for, fake):
    prompts = []

    async def approve(message, response_type, params, context):
        prompts.append(message)
        return response_type(value=True)

    rt_client = client_for(confirm_projects=["Разработка"], workflows=CHAIN)
    async with Client(rt_client.transport, elicitation_handler=approve) as c:
        data = await call(c, "yougile_move_task", task="ID-1", column="Готово")
    assert len(data["path"]) == 3 and len(prompts) == 1


async def test_reader_role_cannot_write_via_task_tools(client_for, fake):
    async with client_for(role="reader") as c:
        with pytest.raises(ToolError, match="needs role"):
            await call(c, "yougile_log_time", task="ID-1", hours=1)
    assert fake.calls("PUT", "/api-v2/tasks/t-int") == 0


async def test_overview_carries_company_rules(client_for):
    async with client_for(instructions=["Пишите кратко."]) as c:
        data = await call(c, "yougile_overview")
    assert data["company_rules"] == "Пишите кратко."
