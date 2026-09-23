"""Task-level tools: names and task numbers instead of UUIDs, calendar dates instead of timestamps.

Every API call goes through ``Caller``, so the session's permissions and confirmations apply
exactly as for the domain tools.
"""

import copy
import re
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations
from pydantic import Field

from .caller import Caller, tool_errors
from .client import YouGileError
from .directory import Ambiguous, NotFound, Structure, _norm
from .present import (
    format_ms,
    html_to_text,
    parse_when,
    status_of,
    task_card,
    task_summary,
    text_to_html,
    user_label,
)

MAX_PAGES = 10  # 10 000 tasks per search is plenty and protects the shared rate limit
PER_COLUMN_THRESHOLD = 4  # up to this many columns: one filtered request per column
COLORS = ("primary", "gray", "red", "pink", "yellow", "green", "turquoise", "blue", "violet")
CLEAR_WORDS = {"", "none", "null", "-", "нет", "clear", "убрать"}
TASK_NUMBER = re.compile(r"^[A-Za-zА-Яа-яЁё]+-\d+$")

TaskRef = Annotated[str, Field(description="Task number like ID-123 or DEV-12, or its id")]
Confirm = Annotated[
    bool,
    Field(
        description="Set true only after the user explicitly approved a write into a "
        "client-facing project (needed only when the tool answered confirmation_required)."
    ),
]
When = Annotated[
    str | None,
    Field(description='Date "YYYY-MM-DD" or "DD.MM.YYYY", optionally with " HH:MM" '),
]


class Work:
    """Shared helpers for one tool call."""

    def __init__(self, ctx: Context | None, confirm: bool = False) -> None:
        self.caller = Caller(ctx, confirm)
        self.rt = self.caller.rt
        self.cfg = self.rt.config
        self.tz = self.cfg.tz
        self.directory = self.rt.directory

    async def structure(self) -> Structure:
        return await self.directory.structure()

    async def task(self, ref: str) -> dict:
        return await self.caller.call("tasks.get", {"id": ref.strip()})

    def number(self, task: dict) -> str:
        return task.get("idTaskCommon") or task.get("id", "?")

    async def board(self, board: str | None, project: str | None) -> dict:
        structure = await self.structure()
        ref = board or self.cfg.board
        if not ref:
            raise ValueError("board is required (no default board in .yougile.json)")
        explicit_project = project is not None or "/" in ref
        scope = project if explicit_project else self.cfg.project
        try:
            return structure.find_board(ref, None if "/" in ref else scope)
        except NotFound:
            if explicit_project or scope is None:
                raise
            return structure.find_board(ref)  # the default project was only a hint

    def workflow(self, structure: Structure, board_id: str) -> list[str] | None:
        """Column ids of the configured Workflow chain for a board, if any."""
        for key, chain in self.cfg.workflows.items():
            try:
                board = structure.find_board(key)
            except (NotFound, Ambiguous):
                continue
            if board["id"] == board_id:
                return [structure.find_column(title, board_id)["id"] for title in chain]
        return None

    async def user_ids(self, refs: list[str]) -> list[str]:
        return [(await self.directory.find_user(ref))["id"] for ref in refs]

    def deadline(self, end: str, start: str | None) -> dict[str, Any]:
        end_ms, with_time = parse_when(end, self.tz)
        body: dict[str, Any] = {"deadline": end_ms, "withTime": with_time}
        if start:
            body["startDate"] = parse_when(start, self.tz)[0]
        return body

    async def list_tasks(self, query: dict[str, Any]) -> tuple[list[dict], bool]:
        tasks: list[dict] = []
        for page_no in range(MAX_PAGES):
            page = await self.caller.call(
                "tasks.list", {**query, "limit": 1000, "offset": page_no * 1000}
            )
            content = (page or {}).get("content", [])
            tasks.extend(content)
            if not (page or {}).get("paging", {}).get("next") or not content:
                return tasks, False
        return tasks, True

    async def messages(self, chat_id: str, limit: int) -> list[dict]:
        page = await self.caller.call("chats.list_messages", {"chatId": chat_id, "limit": 1000})
        items = sorted(
            (m for m in (page or {}).get("content", []) if not m.get("deleted")),
            key=lambda m: m.get("id", 0),
        )[-limit:]
        users = await self.directory.users_by_id()
        return [
            {
                "at": format_ms(m.get("id"), self.tz),
                "from": user_label(users.get(m.get("fromUserId", "")), "system"),
                "text": m.get("text") or html_to_text(m.get("textHtml")),
            }
            for m in items
        ]


def _color(value: str) -> str:
    name = value.strip().lower().removeprefix("task-")
    if name not in COLORS:
        raise ValueError(f"unknown color {value!r}; use one of: {', '.join(COLORS)}")
    return f"task-{name}"


def _find_item(checklists: list[dict], text: str) -> dict:
    items = [item for cl in checklists for item in cl.get("items", [])]
    wanted = _norm(text)
    exact = [i for i in items if _norm(i.get("title")) == wanted]
    found = exact or [i for i in items if wanted in _norm(i.get("title"))]
    if len(found) == 1:
        return found[0]
    names = ", ".join(repr(i.get("title")) for i in (found or items))
    kind = "ambiguous" if found else "not found"
    raise ValueError(f"checklist item {text!r} is {kind}. Items: {names or 'none'}")


# ---------- tools ----------


@tool_errors
async def yougile_overview(
    project: Annotated[str | None, Field(description="Only this project (name or id)")] = None,
    include_ids: Annotated[bool, Field(description="Add board and column ids")] = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Company structure: projects -> boards -> columns in screen order, Workflow chains,
    workspace defaults and this session's permissions. Start here to learn the names."""
    work = Work(ctx)
    s = await work.structure()
    policy = work.rt.policy
    allowed = (
        None if policy.project_refs is None else policy.resolve_projects(policy.project_refs, s)
    )
    projects = [s.find_project(project)] if project else list(s.projects.values())
    projects = [p for p in projects if allowed is None or p["id"] in allowed]
    result = []
    for p in projects:
        boards = []
        for b in s.boards_of_project(p["id"]):
            columns = s.columns_of_board(b["id"])
            entry: dict[str, Any] = {
                "board": b.get("title"),
                "columns": [c.get("title") for c in columns],
            }
            chain = work.workflow(s, b["id"])
            if chain:
                entry["workflow"] = [s.columns[c].get("title") for c in chain]
            if include_ids:
                entry["id"] = b["id"]
                entry["column_ids"] = {c.get("title"): c["id"] for c in columns}
            boards.append(entry)
        item: dict[str, Any] = {"project": p.get("title"), "boards": boards}
        if include_ids:
            item["id"] = p["id"]
        result.append(item)
    return {
        "projects": result,
        "defaults": {"project": work.cfg.project, "board": work.cfg.board},
        "permissions": policy.summary(),
        "timezone": work.cfg.timezone,
        **({"company_rules": work.cfg.instructions.strip()} if work.cfg.instructions else {}),
    }


@tool_errors
async def yougile_find_tasks(
    text: Annotated[str | None, Field(description="Words from the title, or a task number")] = None,
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
    include_archived: bool = False,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Find tasks by project/board/column names, assignee and title words.
    Without a place, searches the default project from .yougile.json, else the whole company."""
    work = Work(ctx)
    if text and TASK_NUMBER.match(text.strip()):
        task = await work.task(text)
        s = await work.structure()
        users = await work.directory.users_by_id()
        return {"count": 1, "tasks": [task_summary(task, s, users, work.tz)]}

    s = await work.structure()
    columns: list[str] | None
    if column or board:
        b = await work.board(board, project)
        columns = (
            [s.find_column(column, b["id"])["id"]]
            if column
            else [c["id"] for c in s.columns_of_board(b["id"])]
        )
        scope = s.board_label(b) + (f" / {s.columns[columns[0]].get('title')}" if column else "")
    elif project or work.cfg.project:
        p = s.find_project(project or work.cfg.project)
        columns = [
            c["id"] for b in s.boards_of_project(p["id"]) for c in s.columns_of_board(b["id"])
        ]
        scope = p.get("title", "")
    else:
        columns, scope = None, "whole company"

    query: dict[str, Any] = {}
    if assignee:
        query["assignedTo"] = (await work.directory.find_user(assignee))["id"]
    truncated = False
    if columns is not None and len(columns) <= PER_COLUMN_THRESHOLD:
        tasks: list[dict] = []
        for cid in columns:
            found, cut = await work.list_tasks({**query, "columnId": cid})
            tasks.extend(found)
            truncated |= cut
    else:
        tasks, truncated = await work.list_tasks(query)
        if columns is not None:
            wanted = set(columns)
            tasks = [t for t in tasks if t.get("columnId") in wanted]

    status = status or ("any" if column else "open")
    words = _norm(text).split() if text else []
    selected = [
        t
        for t in tasks
        if (include_archived or not t.get("archived"))
        and (status == "any" or (status == "completed") == bool(t.get("completed")))
        and all(w in _norm(t.get("title")) for w in words)
    ]
    users = await work.directory.users_by_id() if any(t.get("assigned") for t in selected) else {}
    return {
        "scope": scope,
        "count": len(selected),
        "tasks": [task_summary(t, s, users, work.tz) for t in selected[:limit]],
        **({"shown": limit} if len(selected) > limit else {}),
        **({"truncated": True} if truncated else {}),
    }


@tool_errors
async def yougile_task(
    task: TaskRef,
    messages: Annotated[
        int, Field(ge=0, le=100, description="Also show the last N chat messages")
    ] = 0,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Open a task card: where it is, status, assignees, deadline, hours, checklists,
    stickers by name, description, and optionally the latest chat messages."""
    work = Work(ctx)
    t = await work.task(task)
    s = await work.structure()
    users = await work.directory.users_by_id()
    stickers = await work.directory.stickers() if t.get("stickers") else {}
    card = task_card(t, s, users, stickers, work.tz)
    if messages:
        card["messages"] = await work.messages(t["id"], messages)
    return card


@tool_errors
async def yougile_create_task(
    title: str,
    column: Annotated[
        str | None,
        Field(description="Column name; default: the first column of the board's Workflow chain"),
    ] = None,
    board: Annotated[
        str | None, Field(description='Board name or "Project / Board"; default from config')
    ] = None,
    project: Annotated[str | None, Field(description="Project, to disambiguate the board")] = None,
    description: Annotated[
        str | None, Field(description="Plain text (newlines kept) or HTML")
    ] = None,
    assignees: Annotated[list[str] | None, Field(description='Names, emails or "me"')] = None,
    deadline: When = None,
    start: When = None,
    plan_hours: Annotated[float | None, Field(ge=0)] = None,
    checklist: Annotated[list[str] | None, Field(description="Checklist items")] = None,
    checklist_title: str = "Чек-лист",
    color: Annotated[str | None, Field(description=f"One of: {', '.join(COLORS)}")] = None,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a task using names: board and column, assignees by name or email,
    deadline as a date, planned hours and a checklist."""
    work = Work(ctx, confirm)
    s = await work.structure()
    b = await work.board(board, project)
    if column:
        column_id = s.find_column(column, b["id"])["id"]
    elif chain := work.workflow(s, b["id"]):
        column_id = chain[0]
    else:
        names = ", ".join(c.get("title", "?") for c in s.columns_of_board(b["id"]))
        raise ValueError(f"column is required for {s.board_label(b)}; columns: {names}")
    body: dict[str, Any] = {"title": title, "columnId": column_id}
    if description:
        body["description"] = text_to_html(description)
    if assignees:
        body["assigned"] = await work.user_ids(assignees)
    if start and not deadline:
        raise ValueError("start needs a deadline too")
    if deadline:
        body["deadline"] = work.deadline(deadline, start)
    if plan_hours is not None:
        body["timeTracking"] = {"plan": plan_hours, "work": 0}
    if checklist:
        body["checklists"] = [
            {
                "title": checklist_title,
                "items": [{"title": i, "isCompleted": False} for i in checklist],
            }
        ]
    if color:
        body["color"] = _color(color)
    created = await work.caller.call("tasks.create", body)
    t = await work.task(created["id"])
    users = await work.directory.users_by_id() if t.get("assigned") else {}
    return {"created": task_summary(t, s, users, work.tz)}


@tool_errors
async def yougile_update_task(
    task: TaskRef,
    title: str | None = None,
    description: Annotated[str | None, Field(description="Replaces the description")] = None,
    assignees: Annotated[list[str] | None, Field(description="Replace assignees")] = None,
    add_assignees: list[str] | None = None,
    remove_assignees: list[str] | None = None,
    deadline: Annotated[
        str | None, Field(description='Date, or "none" to remove the deadline')
    ] = None,
    start: When = None,
    plan_hours: Annotated[float | None, Field(ge=0)] = None,
    completed: bool | None = None,
    archived: bool | None = None,
    color: str | None = None,
    check: Annotated[list[str] | None, Field(description="Checklist items to mark done")] = None,
    uncheck: list[str] | None = None,
    add_items: Annotated[list[str] | None, Field(description="New checklist items")] = None,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Edit a task: title, description, assignees (by name), deadline, planned hours,
    completion, archive, color, checklist items. Only the given fields change."""
    work = Work(ctx, confirm)
    t = await work.task(task)
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = text_to_html(description)
    if assignees is not None or add_assignees or remove_assignees:
        current = (
            list(t.get("assigned") or []) if assignees is None else await work.user_ids(assignees)
        )
        for uid in await work.user_ids(add_assignees or []):
            if uid not in current:
                current.append(uid)
        removed = set(await work.user_ids(remove_assignees or []))
        body["assigned"] = [u for u in current if u not in removed]
    if deadline is not None:
        if _norm(deadline) in CLEAR_WORDS:
            body["deadline"] = {"deleted": True}
        else:
            body["deadline"] = work.deadline(deadline, start)
    elif start is not None:
        raise ValueError("start needs a deadline too")
    if plan_hours is not None:
        tracking = t.get("timeTracking") or {}
        body["timeTracking"] = {"plan": plan_hours, "work": tracking.get("work", 0)}
    if completed is not None:
        body["completed"] = completed
    if archived is not None:
        body["archived"] = archived
    if color is not None:
        body["color"] = _color(color)
    if check or uncheck or add_items:
        checklists = copy.deepcopy(t.get("checklists") or [])
        for text in check or []:
            _find_item(checklists, text)["isCompleted"] = True
        for text in uncheck or []:
            _find_item(checklists, text)["isCompleted"] = False
        if add_items:
            if not checklists:
                checklists.append({"title": "Чек-лист", "items": []})
            checklists[0].setdefault("items", []).extend(
                {"title": i, "isCompleted": False} for i in add_items
            )
        body["checklists"] = checklists
    if not body:
        raise ValueError("nothing to change: pass at least one field")
    await work.caller.call("tasks.update", {"id": t["id"], **body})
    return {"task": work.number(t), "changed": sorted(body)}


@tool_errors
async def yougile_move_task(
    task: TaskRef,
    column: Annotated[str, Field(description="Target column name")],
    board: Annotated[
        str | None, Field(description="Target board, when moving to another board")
    ] = None,
    project: str | None = None,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Move a task to another column. On boards with a Workflow chain configured in
    .yougile.json the card is walked through every intermediate column, since YouGile
    rejects jumps over the chain."""
    work = Work(ctx, confirm)
    t = await work.task(task)
    s = await work.structure()
    current = t.get("columnId")
    current_board = s.board_of_column(current)
    target_board = await work.board(board, project) if board else s.boards.get(current_board or "")
    if target_board is None:
        raise ValueError("the task has no column; pass board and column")
    target = s.find_column(column, target_board["id"])["id"]
    if target == current:
        return {"task": work.number(t), "moved": False, "where": s.column_label(current)}

    path = [target]
    chain = work.workflow(s, target_board["id"]) if target_board["id"] == current_board else None
    if chain and current in chain and target in chain:
        i, j = chain.index(current), chain.index(target)
        path = chain[i + 1 : j + 1] if j > i else list(reversed(chain[j:i]))
    done: list[str] = []
    for step in path:
        try:
            await work.caller.call("tasks.update", {"id": t["id"], "columnId": step})
        except YouGileError as exc:
            if exc.status != 400:
                raise
            now_at = s.column_label(done[-1] if done else current)
            hint = (
                "YouGile rejected this transition; the board's Workflow may need other steps."
                if chain
                else "YouGile rejected the direct move, most likely because of the Workflow "
                "extension. Add the column chain for this board to .yougile.json, e.g. "
                f'"workflows": {{"{s.board_label(target_board)}": '
                f"{[c.get('title') for c in s.columns_of_board(target_board['id'])]}}}."
            )
            raise ValueError(
                f"{work.number(t)}: move to {s.column_label(step)} failed ({exc.message}). "
                f"The task is now in {now_at}. {hint}"
            ) from exc
        done.append(step)
    return {
        "task": work.number(t),
        "from": s.column_label(current),
        "to": s.column_label(target),
        "path": [s.columns[c].get("title") for c in done],
    }


@tool_errors
async def yougile_log_time(
    task: TaskRef,
    hours: Annotated[float, Field(description="Hours to add to the worked time (negative to fix)")],
    plan_hours: Annotated[
        float | None, Field(ge=0, description="Also set the planned hours")
    ] = None,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Add worked hours to a task's time tracking (plan/work), keeping the plan."""
    work = Work(ctx, confirm)
    t = await work.task(task)
    tracking = t.get("timeTracking") or {}
    was = {"plan": tracking.get("plan", 0), "work": tracking.get("work", 0)}
    new_work = round(float(was["work"] or 0) + hours, 2)
    if new_work < 0:
        raise ValueError(f"worked time would become negative ({new_work} h)")
    now = {"plan": was["plan"] if plan_hours is None else plan_hours, "work": new_work}
    await work.caller.call("tasks.update", {"id": t["id"], "timeTracking": now})
    return {"task": work.number(t), "hours": now, "was": was}


@tool_errors
async def yougile_task_chat(
    task: TaskRef,
    send: Annotated[str | None, Field(description="Message to post (plain text)")] = None,
    limit: Annotated[int, Field(ge=1, le=200, description="How many latest messages")] = 20,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Read the latest messages of a task's chat, optionally posting a message first."""
    work = Work(ctx, confirm)
    t = await work.task(task)
    if send:
        await work.caller.call(
            "chats.send_message",
            {"chatId": t["id"], "text": send, "textHtml": text_to_html(send), "label": ""},
        )
    return {
        "task": work.number(t),
        "title": t.get("title"),
        "status": status_of(t),
        **({"sent": True} if send else {}),
        "messages": await work.messages(t["id"], limit),
    }


READ_ONLY = (yougile_overview, yougile_find_tasks, yougile_task)
WRITES = (
    yougile_create_task,
    yougile_update_task,
    yougile_move_task,
    yougile_log_time,
    yougile_task_chat,
)


def register(mcp: FastMCP) -> None:
    for fn in READ_ONLY:
        mcp.add_tool(
            Tool.from_function(
                fn, output_schema=None, annotations=ToolAnnotations(read_only_hint=True)
            )
        )
    for fn in WRITES:
        mcp.add_tool(
            Tool.from_function(
                fn, output_schema=None, annotations=ToolAnnotations(destructive_hint=False)
            )
        )
