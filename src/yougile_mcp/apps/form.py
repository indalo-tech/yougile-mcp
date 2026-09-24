"""The new-task form: the person fills it in and creates the task with a click."""

from __future__ import annotations

from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.actions import CallTool, SetState, ShowToast
from prefab_ui.components import (
    Button,
    Column,
    Combobox,
    ComboboxOption,
    Heading,
    Input,
    Muted,
    Row,
    Small,
    Textarea,
)
from prefab_ui.components.control_flow import Else, ForEach, If
from prefab_ui.rx import RESULT, Rx
from pydantic import Field

from ..caller import tool_errors
from ..present import format_ms, parse_when
from ..smart import Work
from . import data
from .screens import add_screens, card_view, display_toggle, on_error, screen

FIELDS = ("title", "description", "assignee", "deadline", "plan_hours", "checklist")


def form_view(boards: list[dict[str, str]], people: list[dict[str, str]]) -> Column:
    with Column(gap=3) as view:
        with Row(align="center", justify="between"):
            Heading("Новая задача", level=3)
            display_toggle()
        with If("!task"), Column(gap=3):
            Small("Доска")
            with Combobox(
                name="board_id",
                placeholder="Выберите доску",
                search_placeholder="Найти доску",
                on_change=CallTool(
                    "yougile_app_columns",
                    arguments={"board": "{{ $event }}"},
                    on_success=[
                        SetState("columns", RESULT.columns),
                        SetState("column_id", RESULT.column_id),
                    ],
                    on_error=on_error(),
                ),
            ):
                for b in boards:
                    ComboboxOption(value=b["id"], label=b["label"])
            with If("board_id"), Column(gap=1):
                Small("Колонка")
                with (
                    Row(gap=2, css_class="flex-wrap"),
                    ForEach("columns") as (_, col),
                ):
                    with If(col.id == Rx("column_id")):
                        Button(f"{col.title}", size="sm")
                    with Else():
                        Button(
                            f"{col.title}",
                            variant="outline",
                            size="sm",
                            on_click=SetState("column_id", f"{col.id}"),
                        )
            Input(name="title", placeholder="Название задачи")
            Textarea(name="description", placeholder="Описание", rows=3)
            with Row(gap=2, css_class="flex-wrap"):
                with Combobox(
                    name="assignee",
                    placeholder="Исполнитель",
                    search_placeholder="Найти человека",
                    css_class="w-56",
                ):
                    for person in people:
                        ComboboxOption(value=person["id"], label=person["label"])
                Input(name="deadline", input_type="date", css_class="w-44")
                Input(
                    name="plan_hours",
                    input_type="number",
                    placeholder="План, ч",
                    step=0.5,
                    css_class="w-28",
                )
            Textarea(name="checklist", placeholder="Чек-лист: по пункту на строку", rows=3)
            Button(
                "Создать задачу",
                disabled="{{ !title || !column_id }}",
                on_click=CallTool(
                    "yougile_app_create",
                    arguments={
                        "board": "{{ board_id }}",
                        "column": "{{ column_id }}",
                        **{name: "{{ " + name + " }}" for name in FIELDS},
                    },
                    on_success=[
                        SetState("task", RESULT),
                        ShowToast("Задача создана", variant="success"),
                    ],
                    on_error=on_error(),
                ),
            )
        with Else(), Column(gap=2):
            with Row(align="center", justify="between"):
                Muted("Задача создана")
                Button(
                    "Создать ещё",
                    variant="outline",
                    size="sm",
                    on_click=[
                        SetState("task", None),
                        *(
                            SetState(name, "")
                            for name in ("title", "description", "plan_hours", "checklist")
                        ),
                    ],
                )
            card_view()
    return view


@tool_errors
async def yougile_new_task_form(
    title: str | None = None,
    board: Annotated[
        str | None,
        Field(description='Board name or "Project / Board"; default: the user\'s board'),
    ] = None,
    project: Annotated[str | None, Field(description="Project, if boards repeat")] = None,
    column: Annotated[str | None, Field(description="Column name")] = None,
    description: str | None = None,
    assignee: Annotated[str | None, Field(description='Name, email or "me"')] = None,
    deadline: Annotated[str | None, Field(description='Date "YYYY-MM-DD" or "DD.MM.YYYY"')] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user a form for a new task, filled in with whatever you already know; the
    user checks it, completes it and creates the task with a button. Do not create the task
    yourself after showing the form. Use it when the user wants to create a task and would
    rather fill in the details themselves."""
    work = Work(ctx)
    s = await work.structure()
    board_id = ""
    if board or project or work.rt.board or work.cfg.board:
        board_id = (await work.board(board, project))["id"]
    columns = data.columns_of(work, s, board_id) if board_id else {"columns": [], "column_id": ""}
    if column and board_id:
        columns["column_id"] = s.find_column(column, board_id)["id"]
    state = {
        "board_id": board_id,
        **columns,
        "title": title or "",
        "description": description or "",
        "assignee": (await work.directory.find_user(assignee))["id"] if assignee else "",
        "deadline": format_ms(parse_when(deadline, work.tz)[0], work.tz, False) if deadline else "",
        "plan_hours": "",
        "checklist": "",
        "task": None,
        "can": data.rights(work),
        "hours_input": "",
        "message_input": "",
    }
    board_label = s.board_label(s.boards[board_id]) if board_id else None
    column_title = next(
        (c["title"] for c in columns["columns"] if c["id"] == columns["column_id"]), None
    )
    prefilled = {
        "board": board_label,
        "column": column_title,
        "title": title,
        "description": description,
        "assignee": assignee,
        "deadline": state["deadline"] or None,
    }
    return screen(
        "Новая задача",
        form_view(data.boards(work, s), await data.people(work)),
        state,
        {
            "shown_to_user": "new task form; the user creates the task with its button",
            **{k: v for k, v in prefilled.items() if v},
        },
    )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_new_task_form)
