"""Tools behind the screens' buttons (visible to the screen, not to the model).

Each one does what its button says through the task-level tools and returns fresh data for
the screen. A click is the person's own decision, so a write into a project that needs a
confirmation goes ahead without asking again (``confirm=True``, no elicitation).
"""

from __future__ import annotations

import copy
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.apps.config import AppConfig, app_config_to_meta_dict
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import smart
from ..caller import tool_errors
from ..present import format_ms
from ..smart import TaskRef, Work, search_tasks
from . import data, hours, standup, triage


def _clicked() -> Work:
    """A tool call for a click: no ctx, so nothing is asked; the click is the confirmation."""
    return Work(None, confirm=True)


@tool_errors
async def yougile_app_task(task: TaskRef) -> dict[str, Any]:
    """The task card's data."""
    return await data.card(Work(None), task)


@tool_errors
async def yougile_app_tasks(
    text: str | None = None,
    project: str | None = None,
    board: str | None = None,
    column: str | None = None,
    assignee: str | None = None,
    status: Literal["open", "completed", "any"] | None = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 200,
) -> dict[str, Any]:
    """The task table's rows, searched again."""
    found = await search_tasks(
        Work(None),
        text=text,
        project=project,
        board=board,
        column=column,
        assignee=assignee,
        status=status,
    )
    return {"tasks": data.rows(found, limit), "count": data.count_text(found, limit)}


@tool_errors
async def yougile_app_complete(task: TaskRef, completed: bool) -> dict[str, Any]:
    """Mark the task completed, or reopen it."""
    work = _clicked()
    t = await work.task(task)
    await work.caller.call("tasks.update", {"id": t["id"], "completed": completed})
    return await data.card(work, t["id"])


@tool_errors
async def yougile_app_take(task: TaskRef) -> dict[str, Any]:
    """Add the person to the task's assignees."""
    work = _clicked()
    t = await work.task(task)
    me = (await work.directory.me())["id"]
    assigned = list(t.get("assigned") or [])
    if me not in assigned:
        await work.caller.call("tasks.update", {"id": t["id"], "assigned": [*assigned, me]})
    return await data.card(work, t["id"])


@tool_errors
async def yougile_app_move(
    task: TaskRef, column: Annotated[str, Field(description="Column id")]
) -> dict[str, Any]:
    """Move the task to a column of its board, along the Workflow chain if there is one."""
    await smart.yougile_move_task(task, column, confirm=True)
    return await data.card(Work(None), task)


@tool_errors
async def yougile_app_check(
    task: TaskRef,
    checklist: Annotated[int, Field(ge=0, description="Checklist position")],
    item: Annotated[int, Field(ge=0, description="Item position in the checklist")],
    done: bool,
) -> dict[str, Any]:
    """Tick or untick a checklist item."""
    work = _clicked()
    t = await work.task(task)
    checklists = copy.deepcopy(t.get("checklists") or [])
    try:
        entry = checklists[checklist]["items"][item]
    except (IndexError, KeyError):
        raise ValueError("the checklist has changed; refresh the card") from None
    entry["isCompleted"] = done
    await work.caller.call("tasks.update", {"id": t["id"], "checklists": checklists})
    return await data.card(work, t["id"])


@tool_errors
async def yougile_app_log_time(
    task: TaskRef, hours: Annotated[float, Field(description="Hours to add")]
) -> dict[str, Any]:
    """Add worked hours to the task."""
    await smart.yougile_log_time(task, hours, confirm=True)
    return await data.card(Work(None), task)


@tool_errors
async def yougile_app_send(
    task: TaskRef, text: Annotated[str, Field(min_length=1)]
) -> dict[str, Any]:
    """Post a message to the task's chat."""
    await smart.yougile_task_chat(task, send=text, limit=1, confirm=True)
    return await data.card(Work(None), task)


@tool_errors
async def yougile_app_board(
    board: Annotated[str, Field(description="Board id")],
    assignee: Annotated[str | None, Field(description='User id, or "all"')] = None,
) -> dict[str, Any]:
    """The board's columns and cards, optionally for one assignee."""
    return await data.board(Work(None), board, assignee)


@tool_errors
async def yougile_app_columns(
    board: Annotated[str, Field(description="Board id")],
) -> dict[str, Any]:
    """A board's columns for the new-task form."""
    work = Work(None)
    return data.columns_of(work, await work.structure(), board)


def _blank(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _hours(value: str | None) -> float | None:
    text = _blank(value)
    try:
        return float(text.replace(",", ".")) if text else None
    except ValueError:
        raise ValueError(f"hours {text!r} are not a number") from None


@tool_errors
async def yougile_app_create(
    board: Annotated[str, Field(description="Board id")],
    column: Annotated[str, Field(description="Column id")],
    title: Annotated[str, Field(min_length=1)],
    description: str | None = None,
    assignee: Annotated[str | None, Field(description="User id")] = None,
    deadline: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    plan_hours: Annotated[str | None, Field(description="Planned hours")] = None,
    checklist: Annotated[str | None, Field(description="Checklist items, one per line")] = None,
) -> dict[str, Any]:
    """Create the task from the form; returns its card."""
    plan = _hours(plan_hours)
    items = [line.strip() for line in (checklist or "").splitlines() if line.strip()]
    created = await smart.yougile_create_task(
        title.strip(),
        column=column,
        board=board,
        description=_blank(description),
        assignees=[assignee] if _blank(assignee) else None,
        deadline=_blank(deadline),
        plan_hours=plan,
        checklist=items or None,
        confirm=True,
    )
    return await data.card(Work(None), created["created"]["number"])


@tool_errors
async def yougile_app_standup(
    person: Annotated[str, Field(description="User id")], project: str | None = None
) -> dict[str, Any]:
    """The stand-up, gathered again."""
    return await standup.state(Work(None), person, _blank(project))


@tool_errors
async def yougile_app_hours(
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
    person: Annotated[str | None, Field(description="User id")] = None,
) -> dict[str, Any]:
    """The hours report for another period."""
    return await hours.state(
        Work(None), _blank(since), _blank(until), _blank(project), _blank(person)
    )


@tool_errors
async def yougile_app_triage(
    board: Annotated[str, Field(description="Board id")],
    column: Annotated[str | None, Field(description="Column id")] = None,
) -> dict[str, Any]:
    """The queue triage, gathered again."""
    return await triage.state(Work(None), board, _blank(column))


@tool_errors
async def yougile_app_triage_save(
    task: TaskRef,
    board: Annotated[str, Field(description="Board id")],
    column: Annotated[str, Field(description="Column id")],
    assignee: Annotated[str | None, Field(description="User id to add")] = None,
    deadline: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    plan_hours: Annotated[str | None, Field(description="Planned hours")] = None,
) -> dict[str, Any]:
    """Apply a triage row's edits (only what changed) and return the fresh triage."""
    work = _clicked()
    t = await work.task(task)
    changes: dict[str, Any] = {}
    who = _blank(assignee)
    if who and who not in (t.get("assigned") or []):
        changes["add_assignees"] = [who]
    day = _blank(deadline)
    current = (t.get("deadline") or {}).get("deadline")
    if day and day != (format_ms(current, work.tz, False) if current else None):
        changes["deadline"] = day
    plan = _hours(plan_hours)
    if plan is not None and plan != float((t.get("timeTracking") or {}).get("plan") or 0):
        changes["plan_hours"] = plan
    if changes:
        await smart.yougile_update_task(t["id"], confirm=True, **changes)
    return await triage.state(Work(None), board, column)


READS = (
    yougile_app_task,
    yougile_app_tasks,
    yougile_app_board,
    yougile_app_columns,
    yougile_app_standup,
    yougile_app_hours,
    yougile_app_triage,
)
WRITES = (
    yougile_app_complete,
    yougile_app_take,
    yougile_app_move,
    yougile_app_check,
    yougile_app_log_time,
    yougile_app_send,
    yougile_app_create,
    yougile_app_triage_save,
)


def register(mcp: FastMCP) -> None:
    ui = app_config_to_meta_dict(AppConfig(visibility=["app"]))
    for fns, hints in (
        (READS, ToolAnnotations(read_only_hint=True)),
        (WRITES, ToolAnnotations(destructive_hint=False)),
    ):
        for fn in fns:
            mcp.add_tool(Tool.from_function(fn, meta={"ui": ui}, annotations=hints))
