"""The board screen: columns side by side with their cards, a filter by assignee, moves."""

from __future__ import annotations

from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.actions import CallTool, SetState, ShowToast
from prefab_ui.components import (
    Badge,
    Button,
    Card,
    CardContent,
    Column,
    Combobox,
    ComboboxOption,
    Heading,
    Row,
    Small,
    Text,
)
from prefab_ui.components.control_flow import Else, ForEach, If
from prefab_ui.rx import RESULT
from pydantic import Field

from ..caller import tool_errors
from ..smart import Work
from . import data
from .screens import add_screens, card_view, display_toggle, on_error, screen


def refresh(assignee: str = "{{ who }}") -> CallTool:
    return CallTool(
        "yougile_app_board",
        arguments={"board": "{{ board.id }}", "assignee": assignee},
        on_success=SetState("board", RESULT),
        on_error=on_error(),
    )


def board_view(people: list[dict[str, str]]) -> Column:
    with Column(gap=4) as view:
        with Row(gap=2, align="center", justify="between", css_class="flex-wrap"):
            Heading("{{ board.label }}", level=3)
            with Row(gap=2, align="center"):
                with Combobox(
                    name="who",
                    placeholder="Исполнитель",
                    search_placeholder="Найти человека",
                    on_change=[SetState("who", "{{ $event }}"), refresh("{{ $event }}")],
                    css_class="w-56",
                ):
                    ComboboxOption(value=data.EVERYONE, label="Все исполнители")
                    for person in people:
                        ComboboxOption(value=person["id"], label=person["label"])
                Button("Обновить", variant="outline", size="sm", on_click=refresh())
                display_toggle()

        with (
            Row(gap=3, align="start", css_class="overflow-x-auto pb-2"),
            ForEach("board.columns") as (ci, col),
            Card(css_class="w-72 shrink-0 py-0 gap-0"),
            CardContent(css_class="p-3"),
            Column(gap=2),
        ):
            with Row(align="center", justify="between"):
                Text(f"{col.title}", bold=True)
                Badge(f"{col.count}", variant="secondary")
            with (
                ForEach(f"board.columns.{ci}.tasks") as (_, task),
                Card(css_class="py-0 gap-0"),
                Column(gap=1, css_class="p-3"),
            ):
                Button(
                    f"{task.code} {task.title}",
                    variant="ghost",
                    size="sm",
                    css_class="h-auto p-0 justify-start text-left whitespace-normal font-medium",
                    on_click=CallTool(
                        "yougile_app_task",
                        arguments={"task": f"{task.id}"},
                        on_success=SetState("task", RESULT),
                        on_error=on_error(),
                    ),
                )
                with If(task.assignees):
                    Small(f"{task.assignees}")
                with If(task.deadline):
                    with If(task.overdue):
                        Small(f"Срок: {task.deadline}", css_class="text-destructive")
                    with Else():
                        Small(f"Срок: {task.deadline}")
                with If("can.update"), Row(gap=1, justify="end"):
                    for side, label in (("prev", "←"), ("next", "→")):
                        with If(getattr(task, side)):
                            Button(
                                label,
                                variant="outline",
                                size="xs",
                                on_click=CallTool(
                                    "yougile_app_move",
                                    arguments={
                                        "task": f"{task.id}",
                                        "column": f"{getattr(task, side)}",
                                    },
                                    on_success=[
                                        refresh(),
                                        ShowToast("Перенесено", variant="success"),
                                    ],
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
            card_view(refresh())
    return view


@tool_errors
async def yougile_show_board(
    board: Annotated[
        str | None,
        Field(description='Board name or "Project / Board"; default: the user\'s board'),
    ] = None,
    project: Annotated[str | None, Field(description="Project, if boards repeat")] = None,
    assignee: Annotated[
        str | None, Field(description='Show only this person\'s cards: name, email or "me"')
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user a board: its columns side by side with the task cards, a filter by
    assignee, arrows to move a card to the next or previous column, and the full task card on
    click. You also get the board as text. Use it when the user wants to see a board."""
    work = Work(ctx)
    b = await work.board(board, project)
    who = (await work.directory.find_user(assignee))["id"] if assignee else data.EVERYONE
    state = await data.board(work, b["id"], who)
    people = await data.people(work)
    return screen(
        state["label"],
        board_view(people),
        {
            "board": state,
            "who": who,
            "task": None,
            "can": data.rights(work),
            "hours_input": "",
            "message_input": "",
        },
        {"shown_to_user": "board", **data.board_for_model(state)},
    )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_show_board)
