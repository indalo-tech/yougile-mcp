"""The stand-up screen: done since the previous working day, in progress, next, blockers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.actions import CallTool, SendMessage, SetState, ShowToast
from prefab_ui.components import (
    Button,
    Card,
    CardContent,
    Column,
    Grid,
    Heading,
    Markdown,
    Metric,
    Muted,
    Row,
    Small,
    Text,
)
from prefab_ui.components.control_flow import Else, ForEach, If
from prefab_ui.rx import RESULT
from pydantic import Field

from ..caller import tool_errors
from ..directory import _norm
from ..present import format_ms, is_overdue, today, user_label
from ..prompts import previous_workday
from ..smart import Found, Work, search_tasks
from .screens import add_screens, display_toggle, on_error, screen

# Columns whose tasks count as "in progress" rather than waiting in the queue.
IN_PROGRESS_WORDS = ("работ", "провер", "progress", "review", "тест", "test", "doing")


def _in_progress(found: Found, task: dict) -> bool:
    column = _norm(found.structure.columns.get(task.get("columnId") or "", {}).get("title"))
    return any(word in column for word in IN_PROGRESS_WORDS)


def _line(found: Found, task: dict, extra: str = "") -> dict[str, str]:
    column = found.structure.columns.get(task.get("columnId") or "", {}).get("title") or ""
    return {
        "code": task.get("idTaskCommon") or "",
        "title": task.get("title") or "",
        "where": column,
        "extra": extra,
        "note": " · ".join(x for x in (column, extra) if x),
    }


def _md(items: list[dict[str, str]]) -> str:
    if not items:
        return "—"
    return "\n".join(
        f"- {i['code']} {i['title']}" + (f" ({i['extra']})" if i["extra"] else "") for i in items
    )


async def state(work: Work, person: str = "me", project: str | None = None) -> dict[str, Any]:
    user = await work.directory.find_user(person or "me")
    since = previous_workday(today(work.tz))
    done = await search_tasks(
        work, assignee=user["id"], project=project, completed_since=since.isoformat()
    )
    opened = await search_tasks(work, assignee=user["id"], project=project)
    now = datetime.now(work.tz)
    doing, queue, overdue, no_deadline = [], [], [], []
    for t in opened.tasks:
        late = is_overdue(t, work.tz, now, opened.done_ids)
        deadline = (t.get("deadline") or {}).get("deadline")
        extra = f"срок {format_ms(deadline, work.tz, False)}" if deadline else ""
        line = _line(opened, t, ("просрочена, " + extra) if late else extra)
        (doing if _in_progress(opened, t) else queue).append(line)
        if late:
            overdue.append(line)
        elif _in_progress(opened, t) and not deadline:
            no_deadline.append(_line(opened, t, "в работе без срока"))
    finished = [
        _line(done, t, f"выполнена {format_ms(t.get('completedTimestamp'), work.tz)}")
        for t in done.tasks
    ]
    blockers = overdue + no_deadline
    name = user_label(user, "?")
    text = (
        f"**Стендап — {name}, {today(work.tz):%d.%m.%Y}**\n\n"
        f"**Вчера:**\n{_md(finished)}\n\n"
        f"**Сегодня:**\n{_md(doing)}\n\n"
        f"**Блокеры и риски:**\n{_md(blockers)}"
    )
    return {
        "person": user["id"],
        "project": project or "",
        "name": name,
        "since": f"{since:%d.%m.%Y}",
        "counts": {
            "done": len(finished),
            "doing": len(doing),
            "queue": len(queue),
            "overdue": len(overdue),
            "blockers": len(blockers),
        },
        "done": finished,
        "doing": doing,
        "queue": queue,
        "blockers": blockers,
        "text": text,
    }


def for_model(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "person": s["name"],
        "done_since": s["since"],
        **{k: [f"{i['code']} {i['title']}" for i in s[k]] for k in ("done", "doing", "queue")},
        "blockers": [f"{i['code']} {i['title']} ({i['extra']})" for i in s["blockers"]],
    }


def section(title: str, key: str) -> None:
    with Card(css_class="py-0 gap-0"), CardContent(css_class="p-4"), Column(gap=2):
        Text(title, bold=True)
        with If(f"standup.counts.{key}"), ForEach(f"standup.{key}") as (_, item), Column(gap=0):
            Text(f"{item.code} {item.title}")
            Small(f"{item.note}")
        with Else():
            Muted("—")


def view() -> Column:
    refresh = CallTool(
        "yougile_app_standup",
        arguments={"person": "{{ standup.person }}", "project": "{{ standup.project }}"},
        on_success=SetState("standup", RESULT),
        on_error=on_error(),
    )
    with Column(gap=4) as root:
        with Row(align="center", justify="between", css_class="flex-wrap gap-2"):
            with Column(gap=0):
                Heading("Стендап — {{ standup.name }}", level=3)
                Muted("Сделано с {{ standup.since }}")
            with Row(gap=2):
                Button("Обновить", variant="outline", size="sm", on_click=refresh)
                display_toggle()
        with Grid(min_column_width="9rem", gap=3):
            Metric(label="Сделано", value="{{ standup.counts.done }}")
            Metric(label="В работе", value="{{ standup.counts.doing }}")
            Metric(label="В очереди", value="{{ standup.counts.queue }}")
            Metric(label="Просрочено", value="{{ standup.counts.overdue }}")
        with Grid(min_column_width="18rem", gap=3):
            section("Вчера", "done")
            section("Сегодня — в работе", "doing")
            section("Блокеры и риски", "blockers")
            section("Дальше по очереди", "queue")
        with Card(css_class="py-0 gap-0"), CardContent(css_class="p-4"), Column(gap=2):
            Text("Текст для команды", bold=True)
            Markdown("{{ standup.text }}")
            with Row(gap=2):
                Button(
                    "Отправить в чат",
                    on_click=[
                        SendMessage(
                            "Вот мой стендап. Проверь его и помоги отправить команде:\n\n"
                            "{{ standup.text }}"
                        ),
                        ShowToast("Отправлено в чат", variant="success"),
                    ],
                )
    return root


@tool_errors
async def yougile_show_standup(
    person: Annotated[
        str, Field(description='Whose stand-up: name, email or "me" (default)')
    ] = "me",
    project: Annotated[str | None, Field(description="Only this project")] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Show the user a stand-up: what was done since the previous working day, what is in
    progress, what is next in the queue, and blockers (overdue tasks, work without a deadline),
    with counts and a ready text they can send to this chat. You also get it as text. Use it
    when the user asks for their (or someone's) stand-up. Changes nothing in YouGile."""
    work = Work(ctx)
    s = await state(work, person, project)
    return screen(
        f"Стендап — {s['name']}",
        view(),
        {"standup": s},
        {"shown_to_user": "stand-up", **for_model(s)},
    )


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_show_standup)
