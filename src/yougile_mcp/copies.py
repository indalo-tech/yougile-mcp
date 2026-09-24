"""Client-facing copies of tasks (the ``client_copy`` setting).

An internal task about client work gets a twin in the client project, with a title and a
description written for the client, on the board and in the column of the same name. The
internal card keeps the link as a line "Карточка для клиента: ID-123"; the client card says
nothing about the internal one. Once linked, moves, hours and the deadline of the internal
task follow to the twin whenever they change through this server.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations
from pydantic import Field

from . import smart
from .caller import tool_errors
from .config import ClientCopy
from .directory import Structure, _norm
from .present import html_to_text, is_done, is_html, text_to_html
from .smart import Confirm, TaskRef, Work

LINK_LABEL = "Карточка для клиента"
LINK = re.compile(LINK_LABEL + r":\s*([A-Za-zА-Яа-яЁё]+-\d+)")
LINK_HTML = re.compile(r"<p>\s*" + LINK_LABEL + r":[^<]*</p>", re.I)
LINK_TEXT = re.compile(r"\n*" + LINK_LABEL + r":[^\n]*")

DEFAULT_RULES = """\
Клиентская карточка — для заказчика, не для команды:
- заголовок человеческим языком, о пользе или проблеме; без внутренних кодов (TD-82), эмодзи, \
имён функций, коммитов, таблиц и серверов;
- описание в один-три коротких абзаца: что было не так или что нужно, что сделаем или сделали;
- никаких личных данных: телефонов, имён клиентов, адресов, почты, номеров записей;
- без внутренних оценок, догадок и спорных деталей; числа — только понятные заказчику;
- в клиентский проект идут только задачи по заказу клиента; внутренние работы (рефакторинг, \
CI, инфраструктура, уборка, эксперименты) — не идут."""

# What follows the internal task to its twin; each name is one kind of change.
SYNCED = ("column", "hours", "deadline")


def settings(work: Work) -> ClientCopy:
    cfg = work.cfg.client_copy
    if cfg is None:
        raise ValueError(
            "client copies are not configured: set client_copy (from and to projects) in "
            f"{work.rt.settings_hint}"
        )
    return cfg


def rules(cfg: ClientCopy) -> str:
    return cfg.rules.strip() or DEFAULT_RULES


def linked(task: dict) -> str | None:
    """The client twin's number written in an internal task, if any."""
    match = LINK.search(html_to_text(task.get("description")))
    return match.group(1) if match else None


def with_link(description: str | None, number: str) -> str:
    """The internal description with the link line (replacing an older one) at the end, in
    the description's own format: HTML, or plain text as tasks written through the API often
    have."""
    text = description or ""
    line = f"{LINK_LABEL}: {number}"
    if is_html(text):
        return LINK_HTML.sub("", text).rstrip() + f"<p>{line}</p>"
    body = LINK_TEXT.sub("", text).rstrip()
    return f"{body}\n\n{line}" if body else line


def _project(s: Structure, ref: str) -> dict:
    return s.find_project(ref)


def _board_of(s: Structure, task: dict) -> dict:
    board_id = s.board_of_column(task.get("columnId"))
    if not board_id:
        raise ValueError("the task is not on a board")
    return s.boards[board_id]


def _same_title(items: list[dict], title: str | None) -> dict | None:
    wanted = _norm(title)
    return next((i for i in items if _norm(i.get("title")) == wanted), None)


async def _target_board(
    work: Work,
    s: Structure,
    cfg: ClientCopy,
    internal_board: dict,
    board: str | None,
    create_board: bool,
) -> tuple[dict, bool]:
    target = _project(s, cfg.target)
    boards = s.boards_of_project(target["id"])
    if board:
        return s.find_board(board, target["id"]), False
    found = _same_title(boards, internal_board.get("title"))
    if found is not None:
        return found, False
    if not create_board:
        names = ", ".join(b.get("title", "?") for b in boards)
        raise ValueError(
            f"«{target.get('title')}» has no board «{internal_board.get('title')}». Ask the user "
            f"whether to create it (create_board=true) or which board to use (board). Boards: "
            f"{names}"
        )
    created = await work.caller.call(
        "boards.create", {"title": internal_board.get("title"), "projectId": target["id"]}
    )
    for column in s.columns_of_board(internal_board["id"]):
        await work.caller.call(
            "columns.create", {"title": column.get("title"), "boardId": created["id"]}
        )
    s = await work.directory.structure(refresh=True)
    return s.boards[created["id"]], True


def _hours(task: dict) -> dict[str, Any]:
    tracking = task.get("timeTracking") or {}
    return {"plan": tracking.get("plan") or 0, "work": tracking.get("work") or 0}


def _deadline(task: dict) -> dict[str, Any]:
    deadline = task.get("deadline") or {}
    if deadline.get("deleted") or not deadline.get("deadline"):
        return {"deleted": True}
    return {
        k: deadline[k] for k in ("deadline", "startDate", "withTime") if deadline.get(k) is not None
    }


async def copy(
    work: Work,
    ref: str,
    title: str,
    description: str,
    board: str | None = None,
    create_board: bool = False,
) -> dict[str, Any]:
    """Create or update the client twin of an internal task."""
    cfg = settings(work)
    s = await work.structure()
    t = await work.task(ref)
    source = _project(s, cfg.source)
    if s.project_of_column(t.get("columnId")) != source["id"]:
        raise ValueError(f"{work.number(t)} is not in «{source.get('title')}»")
    number = linked(t)
    if number:
        twin = await work.task(number)
        await work.caller.call(
            "tasks.update",
            {"id": twin["id"], "title": title, "description": text_to_html(description)},
        )
        synced = await sync(work, t, SYNCED, twin=twin)
        return {"task": work.number(t), "client_task": number, "updated": True, **synced}

    internal_board = _board_of(s, t)
    target_board, board_created = await _target_board(
        work, s, cfg, internal_board, board, create_board
    )
    s = await work.structure()
    columns = s.columns_of_board(target_board["id"])
    internal_column = s.columns.get(t.get("columnId") or "", {})
    column = _same_title(columns, internal_column.get("title")) or (columns[0] if columns else None)
    if column is None:
        raise ValueError(f"{s.board_label(target_board)} has no columns")
    body: dict[str, Any] = {
        "title": title,
        "columnId": column["id"],
        "description": text_to_html(description),
        "timeTracking": _hours(t),
    }
    deadline = _deadline(t)
    if not deadline.get("deleted"):
        body["deadline"] = deadline
    if t.get("completed"):
        body["completed"] = True
    created = await work.caller.call("tasks.create", body)
    twin = await work.task(created["id"])
    twin_number = work.number(twin)
    await work.caller.call(
        "tasks.update", {"id": t["id"], "description": with_link(t.get("description"), twin_number)}
    )
    return {
        "task": work.number(t),
        "client_task": twin_number,
        "created": True,
        "where": s.column_label(column["id"]),
        **({"board_created": s.board_label(target_board)} if board_created else {}),
    }


async def sync(
    work: Work, task: dict, what: tuple[str, ...] | set[str], twin: dict | None = None
) -> dict[str, Any]:
    """Carry the internal task's column, hours and deadline over to its twin.

    ``task`` may be the internal task as it was before the change: only its link is read
    here, the current state is fetched. Returns what changed, for the tool's result."""
    number = linked(task)
    if not number or work.cfg.client_copy is None:
        return {}
    current = await work.task(task["id"])
    twin = twin or await work.task(number)
    body: dict[str, Any] = {}
    if "hours" in what and _hours(current) != _hours(twin):
        body["timeTracking"] = _hours(current)
    if "deadline" in what and _deadline(current) != _deadline(twin):
        body["deadline"] = _deadline(current)
    changed = sorted(body)
    if body:
        await work.caller.call("tasks.update", {"id": twin["id"], **body})
    if "column" in what:
        s = await work.structure()
        title = s.columns.get(current.get("columnId") or "", {}).get("title")
        twin_board = s.board_of_column(twin.get("columnId"))
        target = _same_title(s.columns_of_board(twin_board), title) if twin_board else None
        if target is not None and target["id"] != twin.get("columnId"):
            moved = await smart.yougile_move_task(twin["id"], target["id"], confirm=True)
            if isinstance(moved, dict) and moved.get("to"):
                changed.append("column")
    return {"client_task": number, "synced": changed} if changed else {}


async def follow(work: Work, task: dict, what: tuple[str, ...]) -> dict[str, Any]:
    """Sync after a change made by a tool; a failure is reported, never raised: the change
    to the internal task itself has already been made."""
    if work.cfg.client_copy is None or not linked(task):
        return {}
    try:
        # The setting is the company's consent to keep the twin in step: no second question.
        synced = await sync(Work(None, confirm=True), task, what)
    except Exception as exc:  # noqa: BLE001 - reported to the model instead
        return {"client_copy": {"client_task": linked(task), "error": str(exc)}}
    return {"client_copy": synced} if synced else {}


async def overview(work: Work, board: str | None, project: str | None) -> dict[str, Any]:
    """Open internal tasks of a board, linked or not, beside the client board's tasks."""
    cfg = settings(work)
    s = await work.structure()
    source = _project(s, cfg.source)
    target = _project(s, cfg.target)
    internal = await work.board(board, project or source.get("title"))
    if internal.get("projectId") != source["id"]:
        raise ValueError(f"{s.board_label(internal)} is not in «{source.get('title')}»")
    client = _same_title(s.boards_of_project(target["id"]), internal.get("title"))
    done_ids = work.done_columns(s)

    def line(t: dict) -> dict[str, Any]:
        tracking = t.get("timeTracking") or {}
        return {
            "number": work.number(t),
            "title": t.get("title"),
            "column": s.columns.get(t.get("columnId") or "", {}).get("title"),
            **({"plan_hours": tracking["plan"]} if tracking.get("plan") else {}),
        }

    linked_tasks, unlinked = [], []
    for column in s.columns_of_board(internal["id"]):
        tasks, _ = await work.list_tasks({"columnId": column["id"]})
        for t in tasks:
            if t.get("archived") or t.get("deleted") or is_done(t, done_ids):
                continue
            number = linked(t)
            if number:
                linked_tasks.append({**line(t), "client_task": number})
            else:
                text = html_to_text(t.get("description"))
                unlinked.append(
                    {**line(t), "description": text[:300] + ("…" if len(text) > 300 else "")}
                )
    client_tasks: list[dict] = []
    if client is not None:
        for column in s.columns_of_board(client["id"]):
            tasks, _ = await work.list_tasks({"columnId": column["id"]})
            client_tasks += [line(t) for t in tasks if not t.get("archived")]
    return {
        "internal_board": s.board_label(internal),
        "client_board": s.board_label(client) if client else None,
        "rules": rules(cfg),
        "linked": linked_tasks,
        "unlinked": unlinked,
        "client_board_tasks": client_tasks,
    }


def describe(cfg: ClientCopy | None) -> dict[str, Any] | None:
    if cfg is None:
        return None
    return {"from": cfg.source, "to": cfg.target, "rules": rules(cfg)}


# ---------- tools ----------


@tool_errors
async def yougile_client_copy(
    task: TaskRef,
    title: Annotated[str, Field(description="Title for the client")],
    description: Annotated[str, Field(description="Description for the client (plain text)")],
    board: Annotated[
        str | None,
        Field(description="Client board, when it differs from the internal board's name"),
    ] = None,
    create_board: Annotated[
        bool,
        Field(description="Create the client board with the same columns if it is missing"),
    ] = False,
    confirm: Confirm = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create or update the client copy of an internal task (the client_copy setting): a
    twin in the client project on the board and in the column of the same name, with the
    internal task's hours and deadline, and a title and description you write for the client
    by the company's rules (yougile_overview → client_copy.rules): no internal codes,
    technical details or personal data. Only for tasks about client work. The internal card
    gets the line «Карточка для клиента: ID-…»; afterwards moves, hours and the deadline
    follow to the twin by themselves."""
    return await copy(Work(ctx, confirm), task, title, description, board, create_board)


@tool_errors
async def yougile_client_copies(
    board: Annotated[
        str | None, Field(description="Internal board; default: the user's board")
    ] = None,
    project: Annotated[str | None, Field(description="Internal project, if boards repeat")] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Client copies of an internal board: its open tasks with a client twin (linked) and
    without one (unlinked, with the start of the description), the tasks already on the
    client board of the same name, and the rules for client texts. Before copying, compare
    unlinked tasks with the client board's tasks: a similar one there is an older pair made
    by hand — leave it alone and do not copy that task again."""
    return await overview(Work(ctx), board, project)


def register(mcp: FastMCP) -> None:
    mcp.add_tool(
        Tool.from_function(
            yougile_client_copy,
            output_schema=None,
            annotations=ToolAnnotations(destructive_hint=False),
        )
    )
    mcp.add_tool(
        Tool.from_function(
            yougile_client_copies,
            output_schema=None,
            annotations=ToolAnnotations(read_only_hint=True),
        )
    )
