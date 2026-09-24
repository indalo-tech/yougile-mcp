"""The hours screen: planned vs worked hours of the tasks completed in a period.

YouGile keeps only a task's total hours, not when they were logged, so "for a period" means
the tasks completed in it; open tasks with logged hours are shown apart. A task with several
assignees splits its hours evenly between them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.actions import CallTool, SetState
from prefab_ui.components import (
    Button,
    Card,
    CardContent,
    Column,
    DataTable,
    DataTableColumn,
    Grid,
    Heading,
    Input,
    Metric,
    Muted,
    Row,
    Tab,
    Tabs,
    Text,
)
from prefab_ui.components.charts import BarChart, ChartSeries
from prefab_ui.components.control_flow import Else, If
from prefab_ui.rx import RESULT
from pydantic import Field

from ..caller import tool_errors
from ..present import format_ms, parse_when, today, user_label
from ..smart import Found, Work, search_tasks
from .screens import add_screens, display_toggle, on_error, screen

NOBODY = "Без исполнителя"


def _h(value: float) -> float:
    return round(value, 1)


def _hours(task: dict) -> tuple[float, float]:
    tracking = task.get("timeTracking") or {}
    return float(tracking.get("plan") or 0), float(tracking.get("work") or 0)


def _project(found: Found, task: dict) -> str:
    s = found.structure
    project_id = s.project_of_column(task.get("columnId"))
    return (s.projects.get(project_id or "") or {}).get("title") or "Без проекта"


def _bars(totals: dict[str, list[float]]) -> list[dict[str, Any]]:
    rows = [{"name": k, "plan": _h(v[0]), "work": _h(v[1])} for k, v in totals.items()]
    return sorted(rows, key=lambda r: r["work"], reverse=True)


def _row(task: dict, plan: float, work: float, **extra: Any) -> dict[str, Any]:
    return {
        "code": task.get("idTaskCommon") or "",
        "title": task.get("title") or "",
        "plan": _h(plan),
        "work": _h(work),
        **extra,
    }


async def state(
    work: Work,
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
    person: str | None = None,
) -> dict[str, Any]:
    day = today(work.tz)
    start = format_ms(parse_when(since, work.tz)[0], work.tz, False) if since else None
    end = format_ms(parse_when(until, work.tz)[0], work.tz, False) if until else None
    start = start or (day - timedelta(days=day.weekday())).isoformat()
    end = end or day.isoformat()
    user = await work.directory.find_user(person) if person else None
    assignee = user["id"] if user else None
    done = await search_tasks(
        work, project=project, assignee=assignee, completed_since=start, completed_until=end
    )
    by_person: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    by_project: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    over, no_plan = [], []
    total_plan = total_work = 0.0
    for t in done.tasks:
        plan, spent = _hours(t)
        total_plan += plan
        total_work += spent
        by_project[_project(done, t)][0] += plan
        by_project[_project(done, t)][1] += spent
        people = t.get("assigned") or []
        names = [user_label(done.users.get(u), u) for u in people] or [NOBODY]
        for name in names:
            by_person[name][0] += plan / len(names)
            by_person[name][1] += spent / len(names)
        if plan and spent > plan:
            over.append(
                _row(t, plan, spent, over=_h(spent - plan), percent=round((spent / plan - 1) * 100))
            )
        elif not plan:
            no_plan.append(_row(t, plan, spent))
    over.sort(key=lambda r: r["over"], reverse=True)

    opened = await search_tasks(work, project=project, assignee=assignee)
    logged = []
    for t in opened.tasks:
        plan, spent = _hours(t)
        if spent:
            logged.append(_row(t, plan, spent, left=_h(max(plan - spent, 0))))
    logged.sort(key=lambda r: r["work"], reverse=True)
    return {
        "since": start,
        "until": end,
        "project": project or "",
        "person": assignee or "",
        "scope": ", ".join(x for x in (project, user_label(user, "") if user else None) if x),
        "totals": {
            "tasks": len(done.tasks),
            "plan": _h(total_plan),
            "work": _h(total_work),
            "delta": f"{total_work - total_plan:+.1f}",
        },
        "by_person": _bars(by_person),
        "by_project": _bars(by_project),
        "over": over,
        "no_plan": no_plan,
        "logged": logged,
        "counts": {"over": len(over), "no_plan": len(no_plan), "logged": len(logged)},
        "truncated": done.truncated or opened.truncated,
    }


def for_model(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": f"{s['since']} — {s['until']}",
        **({"scope": s["scope"]} if s["scope"] else {}),
        "totals": s["totals"],
        "by_person": s["by_person"],
        "by_project": s["by_project"],
        "overruns": s["over"],
        "completed_without_plan": s["no_plan"],
        "open_with_logged_hours": s["logged"],
        **({"truncated": True} if s["truncated"] else {}),
    }


def table(key: str, columns: list[tuple[str, str]], empty: str) -> None:
    with If(f"report.counts.{key}"):
        DataTable(
            columns=[
                DataTableColumn(
                    key=k, header=h, sortable=True, width=None if k == "title" else "90px"
                )
                for k, h in columns
            ],
            rows=f"{{{{ report.{key} }}}}",
            paginated=True,
            page_size=10,
        )
    with Else():
        Muted(empty)


def chart(key: str) -> None:
    BarChart(
        data=f"{{{{ report.{key} }}}}",
        series=[
            ChartSeries(data_key="plan", label="План"),
            ChartSeries(data_key="work", label="Факт"),
        ],
        x_axis="name",
        height=260,
        show_legend=True,
    )


def view() -> Column:
    show = CallTool(
        "yougile_app_hours",
        arguments={
            "since": "{{ since_input }}",
            "until": "{{ until_input }}",
            "project": "{{ report.project }}",
            "person": "{{ report.person }}",
        },
        on_success=SetState("report", RESULT),
        on_error=on_error(),
    )
    task = [("code", "Номер"), ("title", "Задача"), ("plan", "План"), ("work", "Факт")]
    with Column(gap=4) as root:
        with Row(align="center", justify="between", css_class="flex-wrap gap-2"):
            with Column(gap=0):
                Heading("Часы: {{ report.since }} — {{ report.until }}", level=3)
                with If("report.scope"):
                    Muted("{{ report.scope }}")
            with Row(gap=2, align="center", css_class="flex-wrap"):
                Input(name="since_input", input_type="date", css_class="w-40")
                Input(name="until_input", input_type="date", css_class="w-40")
                Button("Показать", size="sm", on_click=show)
                display_toggle()
        with Grid(min_column_width="9rem", gap=3):
            Metric(label="Задач выполнено", value="{{ report.totals.tasks }}")
            Metric(label="План, ч", value="{{ report.totals.plan }}")
            Metric(label="Факт, ч", value="{{ report.totals.work }}")
            Metric(label="Отклонение, ч", value="{{ report.totals.delta }}")
        with Card(css_class="py-0 gap-0"), CardContent(css_class="p-4"), Tabs(value="people"):
            with Tab(title="По людям", value="people"):
                chart("by_person")
            with Tab(title="По проектам", value="projects"):
                chart("by_project")
        for title, key, cols, empty in (
            (
                "Перерасход",
                "over",
                [*task, ("over", "Сверх, ч"), ("percent", "Сверх, %")],
                "Перерасхода нет",
            ),
            ("Выполнены без плана", "no_plan", task, "Таких нет"),
            (
                "Открытые со списанными часами (могли списать и до периода)",
                "logged",
                [*task, ("left", "Осталось")],
                "Таких нет",
            ),
        ):
            with Card(css_class="py-0 gap-0"), CardContent(css_class="p-4"), Column(gap=2):
                Text(title, bold=True)
                table(key, cols, empty)
        Muted(
            "YouGile хранит только сумму часов по задаче, без дат списания, поэтому период — это "
            "задачи, выполненные в нём. Часы задачи с несколькими исполнителями делятся поровну."
        )
    return root


@tool_errors
async def yougile_show_hours(
    since: Annotated[
        str | None, Field(description="Period start, YYYY-MM-DD (default: Monday)")
    ] = None,
    until: Annotated[
        str | None, Field(description="Period end, YYYY-MM-DD (default: today)")
    ] = None,
    project: Annotated[str | None, Field(description="Only this project")] = None,
    person: Annotated[
        str | None, Field(description='Only this assignee: name, email or "me"')
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user an hours report for a period: planned vs worked hours of the tasks
    completed in it, as charts by person and by project, with tables of overruns, completed
    tasks without a plan and open tasks with logged hours; the user can change the period.
    You also get it as text. Changes nothing in YouGile."""
    work = Work(ctx)
    s = await state(work, since, until, project, person)
    return screen(
        f"Часы {s['since']} — {s['until']}",
        view(),
        {"report": s, "since_input": s["since"], "until_input": s["until"]},
        {"shown_to_user": "hours report", **for_model(s)},
    )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_show_hours)
