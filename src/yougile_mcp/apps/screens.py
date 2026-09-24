"""The screens the model opens: the task table and the task card."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.apps.config import AppConfig, app_config_to_meta_dict
from fastmcp.server.providers.prefab_synthesis import PREFAB_PLACEHOLDER_URI
from fastmcp.tools import Tool, ToolResult
from mcp.types import TextContent, ToolAnnotations
from prefab_ui.actions import Action, CallTool, RequestDisplayMode, SetState, ShowToast
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Button,
    Card,
    CardContent,
    Column,
    DataTable,
    DataTableColumn,
    Heading,
    Input,
    Muted,
    Progress,
    Row,
    Separator,
    Small,
    Text,
    Textarea,
)
from prefab_ui.components.control_flow import Else, ForEach, If
from prefab_ui.rx import RESULT, Rx
from pydantic import Field

from .. import runtime
from ..budget import DEFAULT_MAX_CHARS, fit
from ..caller import tool_errors
from ..smart import TaskRef, Work, search_tasks
from . import data

TABLE_PAGE = 20  # rows per page in the task table


def on_error() -> ShowToast:
    return ShowToast("Не получилось", description="{{ $error }}", variant="error")


def act(tool: str, arguments: dict[str, Any], *then: Action, done: str = "Готово") -> CallTool:
    """A button's call: the tool returns the fresh card, which replaces the one shown."""
    return CallTool(
        tool,
        arguments={"task": "{{ task.id }}", **arguments},
        on_success=[SetState("task", RESULT), *then, ShowToast(done, variant="success")],
        on_error=on_error(),
    )


def display_toggle() -> None:
    """A button that asks the host for the whole window and back; the host may refuse."""
    with If(Rx("$host.displayMode") == "fullscreen"):
        Button("Свернуть", variant="outline", size="sm", on_click=RequestDisplayMode("inline"))
    with Else():
        Button(
            "Развернуть", variant="outline", size="sm", on_click=RequestDisplayMode("fullscreen")
        )


def card_view(*then: Action) -> Card:
    """The card of the task in state ``task``; ``then`` runs after each button's call."""
    with Card() as view, CardContent(css_class="pt-6"), Column(gap=4):
        with Row(gap=2, align="center"):
            Badge("{{ task.number }}", variant="outline")
            Heading("{{ task.title }}", level=3)
        with Row(gap=2, align="center"):
            with If("task.overdue"):
                Badge("{{ task.status }}", variant="destructive")
            with Else():
                Badge("{{ task.status }}", variant="secondary")
            Muted("{{ task.where }}")
        with If("task.client_facing && can.update"):
            Small("Проект видят клиенты: нажатие кнопки — это подтверждение записи.")
        Text("Исполнители: {{ task.assignees }}")
        Text("Срок: {{ task.deadline }}")
        with If("task.hours.text"), Column(gap=1):
            Text("Часы: {{ task.hours.text }}")
            with If("task.hours.plan"):
                Progress(value="{{ task.hours.percent }}", max=100, size="sm")

        with If("can.update"):
            with Row(gap=2):
                with If("task.done"):
                    Button(
                        "Вернуть в работу",
                        variant="outline",
                        on_click=act("yougile_app_complete", {"completed": False}, *then),
                    )
                with Else():
                    Button(
                        "Выполнено",
                        on_click=act("yougile_app_complete", {"completed": True}, *then),
                    )
                with If(~Rx("task.mine")):
                    Button(
                        "Взять себе",
                        variant="outline",
                        on_click=act("yougile_app_take", {}, *then),
                    )
            with Column(gap=1):
                Small("Перенести в колонку:")
                with (
                    Row(gap=2, css_class="flex-wrap"),
                    ForEach("task.columns") as (_, col),
                    If(col.id != Rx("task.column_id")),
                ):
                    Button(
                        f"{col.title}",
                        variant="outline",
                        size="sm",
                        on_click=act(
                            "yougile_app_move", {"column": f"{col.id}"}, *then, done="Перенесено"
                        ),
                    )
            with Row(gap=2, align="end"):
                Input(
                    name="hours_input",
                    input_type="number",
                    placeholder="Часы",
                    step=0.25,
                    css_class="w-28",
                )
                Button(
                    "Списать часы",
                    variant="outline",
                    disabled="{{ !hours_input }}",
                    on_click=act(
                        "yougile_app_log_time",
                        {"hours": "{{ hours_input }}"},
                        SetState("hours_input", ""),
                        *then,
                        done="Часы списаны",
                    ),
                )

        with ForEach("task.checklists") as (ci, checklist), Column(gap=1):
            Separator()
            Text(f"{checklist.title}", bold=True)
            # A Checkbox cannot take its value from a loop item, so an item is a toggle button.
            with ForEach(f"task.checklists.{ci}.items") as (ii, item):
                with If("can.update"):
                    Button(
                        f"{item.mark} {item.title}",
                        variant="ghost",
                        size="sm",
                        css_class="justify-start h-auto whitespace-normal text-left",
                        on_click=act(
                            "yougile_app_check",
                            {"checklist": f"{ci}", "item": f"{ii}", "done": f"{~item.done}"},
                            *then,
                            done="Сохранено",
                        ),
                    )
                with Else():
                    Text(f"{item.mark} {item.title}")

        with If("task.description"):
            Separator()
            Text("{{ task.description }}", css_class="whitespace-pre-wrap")

        Separator()
        Text("Чат задачи", bold=True)
        with If("task.messages_count"), ForEach("task.messages") as (_, message), Column(gap=0):
            Small(f"{message.author} · {message.at}")
            Text(f"{message.text}", css_class="whitespace-pre-wrap")
        with Else():
            Muted("Сообщений нет")
        with If("can.chat"), Column(gap=2):
            Textarea(name="message_input", placeholder="Сообщение в чат задачи", rows=2)
            Button(
                "Отправить",
                disabled="{{ !message_input }}",
                on_click=act(
                    "yougile_app_send",
                    {"text": "{{ message_input }}"},
                    SetState("message_input", ""),
                    *then,
                    done="Отправлено",
                ),
            )
    return view


def screen(title: str, view: Any, state: dict[str, Any], for_model: dict[str, Any]) -> ToolResult:
    """The screen for the person and the same data as text for the model."""
    try:
        limit = runtime.current().max_response_chars
    except RuntimeError:
        limit = DEFAULT_MAX_CHARS
    text = json.dumps(fit(for_model, limit), ensure_ascii=False)
    app = PrefabApp(title=title, view=view, state=state)
    return ToolResult(content=[TextContent(type="text", text=text)], structured_content=app)


# ---------- screens ----------


@tool_errors
async def yougile_show_task(task: TaskRef, ctx: Context | None = None) -> ToolResult:
    """Show the user a task card they can work with: status, assignees, deadline, hours,
    checklist, description and chat, with buttons to complete it, take it, move it, tick
    checklist items, log hours and post to the chat. You also get the card as text.
    Use it when the user wants to see or work on one task."""
    work = Work(ctx)
    state = await data.card(work, task)
    shown = {"shown_to_user": "task card", **data.card_for_model(state)}
    with Column(gap=2) as view:
        with Row(justify="end"):
            display_toggle()
        card_view()
    return screen(
        f"{state['number']} {state['title']}",
        view,
        {"task": state, "can": data.rights(work), "hours_input": "", "message_input": ""},
        shown,
    )


@tool_errors
async def yougile_show_tasks(
    text: Annotated[str | None, Field(description="Words from the title")] = None,
    project: Annotated[str | None, Field(description="Project name")] = None,
    board: Annotated[str | None, Field(description='Board name or "Project / Board"')] = None,
    column: Annotated[
        str | None, Field(description="Column name (needs a board or default)")
    ] = None,
    assignee: Annotated[str | None, Field(description='Name, email or "me"')] = None,
    status: Annotated[
        Literal["open", "completed", "any"] | None,
        Field(description='Default "open", or "any" when a column is given'),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 200,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user a table of tasks (same filters as yougile_find_tasks) with search and
    sorting; clicking a row opens the task card with its buttons. You also get the tasks as
    text. Use it when the user wants to look through a list of tasks."""
    work = Work(ctx)
    query = {
        "text": text,
        "project": project,
        "board": board,
        "column": column,
        "assignee": assignee,
        "status": status,
    }
    found = await search_tasks(work, **query)
    refresh = CallTool(
        "yougile_app_tasks",
        arguments={**{k: v for k, v in query.items() if v is not None}, "limit": limit},
        on_success=[SetState("tasks", RESULT.tasks), SetState("count", RESULT.count)],
        on_error=on_error(),
    )
    table_rows = data.rows(found, limit)
    with Column(gap=4) as view:
        with Row(gap=2, align="center", justify="between"):
            Muted("{{ scope }}: {{ count }}")
            with Row(gap=2):
                Button("Обновить", variant="outline", size="sm", on_click=refresh)
                display_toggle()
        DataTable(
            columns=[
                DataTableColumn(key="number", header="Номер", sortable=True, width="90px"),
                DataTableColumn(key="title", header="Задача", sortable=True),
                DataTableColumn(key="where", header="Колонка", sortable=True),
                DataTableColumn(key="assignees", header="Исполнители", sortable=True),
                DataTableColumn(key="deadline", header="Срок", sortable=True, width="110px"),
                DataTableColumn(key="status", header="Статус", sortable=True, width="110px"),
            ],
            rows="{{ tasks }}",
            search=True,
            paginated=len(table_rows) > TABLE_PAGE,
            page_size=TABLE_PAGE,
            on_row_click=CallTool(
                "yougile_app_task",
                arguments={"task": "{{ $event.id }}"},
                on_success=SetState("task", RESULT),
                on_error=on_error(),
            ),
        )
        with If("task"), Column(gap=2):
            with Row(justify="end"):
                Button(
                    "Закрыть карточку",
                    variant="outline",
                    size="sm",
                    on_click=SetState("task", None),
                )
            card_view(refresh)
    state = {
        "scope": found.scope,
        "count": data.count_text(found, limit),
        "tasks": table_rows,
        "task": None,
        "can": data.rights(work),
        "hours_input": "",
        "message_input": "",
    }
    return screen(
        f"Задачи — {found.scope}",
        view,
        state,
        {"shown_to_user": "task table", **found.result(min(limit, 50))},
    )


SCREEN_TOOLS = (yougile_show_task, yougile_show_tasks)


def add_screens(mcp: FastMCP, *fns: Any) -> None:
    """Register screen tools: the model calls them, the client draws their result."""
    ui = app_config_to_meta_dict(
        AppConfig(resource_uri=PREFAB_PLACEHOLDER_URI, visibility=["model"])
    )
    for fn in fns:
        mcp.add_tool(
            Tool.from_function(
                fn,
                output_schema=None,
                meta={"ui": ui},
                annotations=ToolAnnotations(read_only_hint=True),
            )
        )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, *SCREEN_TOOLS)
