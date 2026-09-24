"""The triage screen: the queue's open tasks with their problems, fixed right in the row.

Problems: no assignee, no deadline, overdue, no planned hours. The person's load is counted
on the same board (open tasks and planned hours), which costs one request per column.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any

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
    Grid,
    Heading,
    Input,
    Metric,
    Muted,
    Row,
    Small,
    Text,
)
from prefab_ui.components.charts import BarChart, ChartSeries
from prefab_ui.components.control_flow import Else, ForEach, If
from prefab_ui.rx import RESULT, Rx
from pydantic import Field

from ..caller import tool_errors
from ..directory import Structure, _norm
from ..present import format_ms, is_done, is_overdue, user_label
from ..smart import Work
from . import data
from .screens import TITLE_LINK, add_screens, card_view, display_toggle, on_error, screen

QUEUE_WORDS = ("очеред", "бэклог", "backlog", "входящ", "inbox", "todo", "to do", "новые")
PROBLEMS = {
    "assignee": "нет исполнителя",
    "deadline": "нет срока",
    "overdue": "просрочена",
    "plan": "нет плана",
}


def queue_column(work: Work, s: Structure, board_id: str, column: str | None) -> dict:
    if column:
        return s.find_column(column, board_id)
    chain = work.workflow(s, board_id)
    if chain:
        return s.columns[chain[0]]
    columns = s.columns_of_board(board_id)
    named = [c for c in columns if any(w in _norm(c.get("title")) for w in QUEUE_WORDS)]
    if not named and not columns:
        raise ValueError(f"{s.board_label(s.boards[board_id])} has no columns")
    return (named or columns)[0]


def _row(t: dict, work: Work, users: dict[str, dict], now: datetime, done_ids) -> dict[str, Any]:
    deadline = (t.get("deadline") or {}).get("deadline")
    has_deadline = bool(deadline) and not (t.get("deadline") or {}).get("deleted")
    plan = float((t.get("timeTracking") or {}).get("plan") or 0)
    assigned = t.get("assigned") or []
    problems = [
        PROBLEMS[key]
        for key, bad in (
            ("assignee", not assigned),
            ("deadline", not has_deadline),
            ("overdue", is_overdue(t, work.tz, now, done_ids)),
            ("plan", not plan),
        )
        if bad
    ]
    names = ", ".join(user_label(users.get(u), u) for u in assigned) or "—"
    shown_deadline = format_ms(deadline, work.tz, False) if has_deadline else ""
    shown_plan = f"{plan:g} ч" if plan else "—"
    return {
        "id": t["id"],
        "code": t.get("idTaskCommon") or "",
        "title": t.get("title") or "",
        "assignees": names,
        "info": f"Исполнители: {names} · Срок: {shown_deadline or '—'} · План: {shown_plan}",
        "assignee_id": assigned[0] if assigned else "",
        "deadline": shown_deadline,
        "plan": f"{plan:g}" if plan else "",
        "problems": problems,
        "problem_count": len(problems),
    }


async def state(work: Work, board_id: str, column: str | None = None) -> dict[str, Any]:
    s = await work.structure()
    col = queue_column(work, s, board_id, column)
    users = await work.directory.users_by_id()
    done_ids = work.done_columns(s)
    now = datetime.now(work.tz)
    rows: list[dict[str, Any]] = []
    load: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for c in s.columns_of_board(board_id):
        tasks, _ = await work.list_tasks({"columnId": c["id"]})
        for t in tasks:
            if t.get("archived") or t.get("deleted") or is_done(t, done_ids):
                continue
            plan = float((t.get("timeTracking") or {}).get("plan") or 0)
            for u in t.get("assigned") or []:
                load[user_label(users.get(u), u)][0] += 1
                load[user_label(users.get(u), u)][1] += plan
            if c["id"] == col["id"]:
                rows.append(_row(t, work, users, now, done_ids))
    rows.sort(key=lambda r: r["problem_count"], reverse=True)
    counts = {key: sum(1 for r in rows if word in r["problems"]) for key, word in PROBLEMS.items()}
    return {
        "board": board_id,
        "column": col["id"],
        "label": s.column_label(col["id"]),
        "rows": rows,
        "counts": {"tasks": len(rows), **counts, "problems": sum(1 for r in rows if r["problems"])},
        "has_load": bool(load),
        "load": sorted(
            ({"name": k, "tasks": v[0], "plan": round(v[1], 1)} for k, v in load.items()),
            key=lambda r: r["tasks"],
            reverse=True,
        ),
    }


def for_model(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue": s["label"],
        "counts": s["counts"],
        "tasks": [
            {
                "number": r["code"],
                "title": r["title"],
                "assignees": r["assignees"],
                **({"deadline": r["deadline"]} if r["deadline"] else {}),
                **({"plan_hours": r["plan"]} if r["plan"] else {}),
                **({"problems": r["problems"]} if r["problems"] else {}),
            }
            for r in s["rows"]
        ],
        "board_load": s["load"],
    }


def refresh() -> CallTool:
    return CallTool(
        "yougile_app_triage",
        arguments={"board": "{{ triage.board }}", "column": "{{ triage.column }}"},
        on_success=SetState("triage", RESULT),
        on_error=on_error(),
    )


def editor(row: Any, people: list[dict[str, str]]) -> None:
    """The row's editors: assignee, deadline, planned hours; saving returns the fresh queue."""
    with Combobox(
        name="edit_assignee",
        placeholder="Исполнитель",
        search_placeholder="Найти человека",
        css_class="w-56",
    ):
        for person in people:
            ComboboxOption(value=person["id"], label=person["label"])
    Input(name="edit_deadline", input_type="date", css_class="w-40")
    Input(name="edit_plan", input_type="number", placeholder="План, ч", step=0.5, css_class="w-28")
    Button(
        "Сохранить",
        size="sm",
        on_click=CallTool(
            "yougile_app_triage_save",
            arguments={
                "task": f"{row.id}",
                "board": "{{ triage.board }}",
                "column": "{{ triage.column }}",
                "assignee": "{{ edit_assignee }}",
                "deadline": "{{ edit_deadline }}",
                "plan_hours": "{{ edit_plan }}",
            },
            on_success=[
                SetState("triage", RESULT),
                SetState("edit", ""),
                ShowToast("Сохранено", variant="success"),
            ],
            on_error=on_error(),
        ),
    )
    Button("Отмена", variant="outline", size="sm", on_click=SetState("edit", ""))


def view(people: list[dict[str, str]]) -> Column:
    with Column(gap=4) as root:
        with Row(align="center", justify="between", css_class="flex-wrap gap-2"):
            with Column(gap=0):
                Heading("Разбор очереди", level=3)
                Muted("{{ triage.label }}")
            with Row(gap=2):
                Button("Обновить", variant="outline", size="sm", on_click=refresh())
                display_toggle()
        with Grid(min_column_width="8rem", gap=3):
            Metric(label="В очереди", value="{{ triage.counts.tasks }}")
            Metric(label="Без исполнителя", value="{{ triage.counts.assignee }}")
            Metric(label="Без срока", value="{{ triage.counts.deadline }}")
            Metric(label="Без плана", value="{{ triage.counts.plan }}")
            Metric(label="Просрочено", value="{{ triage.counts.overdue }}")

        with (
            If("triage.counts.tasks"),
            ForEach("triage.rows") as (ri, row),
            Card(css_class="py-0 gap-0"),
            CardContent(css_class="p-3"),
            Column(gap=2),
        ):
            with Row(gap=2, align="center", justify="between", css_class="flex-wrap"):
                Button(
                    f"{row.code} {row.title}",
                    variant="ghost",
                    size="sm",
                    css_class=TITLE_LINK,
                    on_click=CallTool(
                        "yougile_app_task",
                        arguments={"task": f"{row.id}"},
                        on_success=SetState("task", RESULT),
                        on_error=on_error(),
                    ),
                )
                with (
                    Row(gap=1, css_class="flex-wrap"),
                    ForEach(f"triage.rows.{ri}.problems") as (_, problem),
                ):
                    Badge(f"{problem}", variant="destructive")
            Small(f"{row.info}")
            # One row is edited at a time, so the editors' state keys never clash.
            with If(row.id == Rx("edit")), Row(gap=2, align="end", css_class="flex-wrap"):
                editor(row, people)
            with Else(), If("can.update"):
                Button(
                    "Исправить",
                    variant="outline",
                    size="xs",
                    css_class="self-start",
                    on_click=[
                        SetState("edit_assignee", f"{row.assignee_id}"),
                        SetState("edit_deadline", f"{row.deadline}"),
                        SetState("edit_plan", f"{row.plan}"),
                        SetState("edit", f"{row.id}"),
                    ],
                )
        with Else():
            Muted("Очередь пуста")

        with If("task"), Column(gap=2):
            with Row(justify="end"):
                Button(
                    "Закрыть карточку",
                    variant="outline",
                    size="sm",
                    on_click=SetState("task", None),
                )
            card_view(refresh())

        with Card(css_class="py-0 gap-0"), CardContent(css_class="p-4"), Column(gap=2):
            Text("Загрузка на доске: открытые задачи и план часов", bold=True)
            with If("triage.has_load"):
                BarChart(
                    data="{{ triage.load }}",
                    series=[
                        ChartSeries(data_key="tasks", label="Задач"),
                        ChartSeries(data_key="plan", label="План, ч"),
                    ],
                    x_axis="name",
                    height=240,
                    show_legend=True,
                )
            with Else():
                Muted("На доске нет задач с исполнителями")
    return root


@tool_errors
async def yougile_show_triage(
    board: Annotated[
        str | None,
        Field(description='Board name or "Project / Board"; default: the user\'s board'),
    ] = None,
    column: Annotated[
        str | None,
        Field(description="Queue column; default: the first Workflow column or one like «Очередь»"),
    ] = None,
    project: Annotated[str | None, Field(description="Project, if boards repeat")] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user a queue triage: the open tasks of a board's queue column with their
    problems (no assignee, no deadline, overdue, no planned hours), the people's load on the
    board, and editors to set the assignee, deadline and planned hours right in the row. You
    also get it as text; suggest fixes, but the user applies them on the screen."""
    work = Work(ctx)
    b = await work.board(board, project)
    s = await state(work, b["id"], column)
    return screen(
        f"Разбор очереди — {s['label']}",
        view(await data.people(work)),
        {
            "triage": s,
            "edit": "",
            "edit_assignee": "",
            "edit_deadline": "",
            "edit_plan": "",
            "task": None,
            "can": data.rights(work),
            "hours_input": "",
            "message_input": "",
        },
        {"shown_to_user": "queue triage", **for_model(s)},
    )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_show_triage)
