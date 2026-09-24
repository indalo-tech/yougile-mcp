"""What the screens show, as plain data: table rows, a task card, a board, the new-task form.

Display strings are made here, on the server, so the screens need no formatting logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..directory import Structure
from ..present import (
    format_deadline,
    html_to_text,
    is_done,
    is_overdue,
    status_of,
    user_label,
)
from ..smart import Found, Work
from ..visibility import allowed

STATUS_WORDS = {
    "open": "Открыта",
    "completed": "Выполнена",
    "archived": "В архиве",
    "deleted": "Удалена",
}
CARD_MESSAGES = 10  # latest chat messages on a card
BOARD_COLUMN_LIMIT = 30  # cards per board column; the column shows how many there are in all
EVERYONE = "all"  # the board filter's value for "every assignee"


def rights(work: Work) -> dict[str, bool]:
    """Which buttons the session may use; the policy still checks every call."""
    policy = work.rt.policy
    return {
        "update": allowed(policy, "tasks.update"),
        "chat": allowed(policy, "chats.send_message"),
        "create": allowed(policy, "tasks.create"),
    }


def _deadline_text(task: dict, work: Work) -> str:
    deadline = format_deadline(task.get("deadline"), work.tz)
    if isinstance(deadline, dict):
        return f"{deadline['start']} — {deadline['end']}"
    return deadline or ""


def _status_label(task: dict, done_ids: frozenset[str], overdue: bool) -> str:
    status = status_of(task, done_ids)
    return "Просрочена" if overdue and status == "open" else STATUS_WORDS.get(status, status)


def _hours(task: dict) -> dict[str, Any]:
    tracking = task.get("timeTracking") or {}
    plan = float(tracking.get("plan") or 0)
    work = float(tracking.get("work") or 0)
    text = f"{work:g} ч из {plan:g} ч" if plan else (f"{work:g} ч" if work else "")
    percent = min(100, round(work / plan * 100)) if plan else 0
    return {"plan": plan, "work": work, "text": text, "percent": percent}


def rows(found: Found, limit: int) -> list[dict[str, Any]]:
    """One row per task for the table."""
    now = datetime.now(found.tz)
    prefix = found.scope + " / "  # the title names the project or board already
    out = []
    for t in found.tasks[:limit]:
        overdue = is_overdue(t, found.tz, now, found.done_ids)
        deadline = format_deadline(t.get("deadline"), found.tz)
        out.append(
            {
                "id": t.get("id"),
                "number": t.get("idTaskCommon") or "",
                "title": t.get("title") or "",
                "where": (found.structure.column_label(t.get("columnId")) or "").removeprefix(
                    prefix
                ),
                "assignees": ", ".join(
                    user_label(found.users.get(u), u) for u in t.get("assigned") or []
                ),
                "deadline": deadline["end"] if isinstance(deadline, dict) else deadline or "",
                "status": _status_label(t, found.done_ids, overdue),
            }
        )
    return out


def count_text(found: Found, limit: int) -> str:
    total = len(found.tasks)
    text = f"{min(total, limit)} из {total}" if total > limit else str(total)
    return text + (" (поиск остановлен на 10 000 задач)" if found.truncated else "")


async def card(work: Work, ref: str) -> dict[str, Any]:
    """Everything the task card shows, with ids for its buttons."""
    t = await work.task(ref)
    s = await work.structure()
    users = await work.directory.users_by_id()
    me = await work.directory.me()
    done_ids = work.done_columns(s)
    overdue = is_overdue(t, work.tz, done_columns=done_ids)
    column_id = t.get("columnId")
    board_id = s.board_of_column(column_id)
    project_id = s.project_of_column(column_id)
    policy = work.rt.policy
    client_facing = bool(
        project_id and project_id in policy.resolve_projects(policy.confirm_refs, s)
    )
    assigned = list(t.get("assigned") or [])
    messages = [
        {"at": m["at"], "author": m["from"], "text": m["text"]}
        for m in await work.messages(t["id"], CARD_MESSAGES)
    ]
    return {
        "id": t["id"],
        "number": t.get("idTaskCommon") or work.number(t),
        "title": t.get("title") or "",
        "where": s.column_label(column_id) or "",
        "column_id": column_id,
        "columns": [
            {"id": c["id"], "title": c.get("title") or ""}
            for c in (s.columns_of_board(board_id) if board_id else [])
        ],
        "status": _status_label(t, done_ids, overdue),
        "done": is_done(t, done_ids),
        "overdue": overdue,
        "assignees": ", ".join(user_label(users.get(u), u) for u in assigned) or "—",
        "mine": me.get("id") in assigned,
        "deadline": _deadline_text(t, work) or "—",
        "hours": _hours(t),
        "checklists": [
            {
                "title": cl.get("title") or "Чек-лист",
                "items": [
                    {
                        "title": item.get("title") or "",
                        "done": bool(item.get("isCompleted")),
                        "mark": "☑" if item.get("isCompleted") else "☐",
                    }
                    for item in cl.get("items") or []
                ],
            }
            for cl in t.get("checklists") or []
        ],
        "description": html_to_text(t.get("description")),
        "messages": messages,
        "messages_count": len(messages),
        "client_facing": client_facing,
    }


def card_for_model(state: dict[str, Any]) -> dict[str, Any]:
    """The card as the model reads it: no ids or screen-only fields."""
    hidden = {"id", "column_id", "columns", "mine", "client_facing", "messages_count"}
    out = {k: v for k, v in state.items() if k not in hidden and v not in ("", [], "—")}
    out["hours"] = state["hours"]["text"] or None
    out["checklists"] = [
        {
            "title": cl["title"],
            "items": [f"[{'x' if i['done'] else ' '}] {i['title']}" for i in cl["items"]],
        }
        for cl in state["checklists"]
    ] or None
    return {k: v for k, v in out.items() if v is not None}


# ---------- board and form ----------


def _allowed_projects(work: Work, s: Structure) -> set[str] | None:
    policy = work.rt.policy
    if policy.project_refs is None:
        return None
    return policy.resolve_projects(policy.project_refs, s)


def boards(work: Work, s: Structure) -> list[dict[str, str]]:
    """Boards the session may work in, as "Project / Board", in screen order."""
    allowed_ids = _allowed_projects(work, s)
    return [
        {"id": b["id"], "label": s.board_label(b)}
        for p in s.projects.values()
        if allowed_ids is None or p["id"] in allowed_ids
        for b in s.boards_of_project(p["id"])
        if s.columns_of_board(b["id"])
    ]


async def people(work: Work) -> list[dict[str, str]]:
    users = await work.directory.users()
    listed = sorted(
        ({"id": u["id"], "label": user_label(u, u["id"])} for u in users if u.get("id")),
        key=lambda u: u["label"].lower(),
    )
    return listed


def columns_of(work: Work, s: Structure, board_id: str) -> dict[str, Any]:
    """A board's columns for the form, and the one a new task goes to by default."""
    columns = [{"id": c["id"], "title": c.get("title") or ""} for c in s.columns_of_board(board_id)]
    chain = work.workflow(s, board_id)
    first = chain[0] if chain else (columns[0]["id"] if columns else "")
    return {"columns": columns, "column_id": first}


def _board_task(
    t: dict, work: Work, users: dict[str, dict], done_ids: frozenset[str], near: dict[str, str]
) -> dict[str, Any]:
    overdue = is_overdue(t, work.tz, done_columns=done_ids)
    deadline = format_deadline(t.get("deadline"), work.tz)
    return {
        "id": t["id"],
        "code": t.get("idTaskCommon") or "",  # not "number": that is an Rx pipe in loops
        "title": t.get("title") or "",
        "assignees": ", ".join(user_label(users.get(u), u) for u in t.get("assigned") or []),
        "deadline": deadline["end"] if isinstance(deadline, dict) else deadline or "",
        "overdue": overdue,
        "done": is_done(t, done_ids),
        "prev": near.get("prev", ""),
        "next": near.get("next", ""),
    }


async def board(work: Work, board_id: str, assignee: str | None = None) -> dict[str, Any]:
    """The board's columns with their cards; ``assignee`` (an id) narrows the cards."""
    s = await work.structure()
    b = s.boards[board_id]
    columns = s.columns_of_board(board_id)
    done_ids = work.done_columns(s)
    users = await work.directory.users_by_id()
    query = {"assignedTo": assignee} if assignee and assignee != EVERYONE else {}
    out = []
    for i, col in enumerate(columns):
        tasks, _ = await work.list_tasks({**query, "columnId": col["id"]})
        tasks = [t for t in tasks if not t.get("archived") and not t.get("deleted")]
        if col["id"] in done_ids or all(t.get("completed") for t in tasks):
            tasks.sort(key=lambda t: t.get("completedTimestamp") or 0, reverse=True)
        near = {
            "prev": columns[i - 1]["id"] if i > 0 else "",
            "next": columns[i + 1]["id"] if i + 1 < len(columns) else "",
        }
        shown = tasks[:BOARD_COLUMN_LIMIT]
        out.append(
            {
                "id": col["id"],
                "title": col.get("title") or "",
                "count": f"{len(shown)} из {len(tasks)}"
                if len(tasks) > len(shown)
                else str(len(tasks)),
                "tasks": [_board_task(t, work, users, done_ids, near) for t in shown],
            }
        )
    return {"id": board_id, "label": s.board_label(b), "columns": out}


def board_for_model(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "board": state["label"],
        "columns": [
            {
                "column": col["title"],
                "count": col["count"],
                "tasks": [
                    {
                        k: v
                        for k, v in (
                            ("number", t["code"]),
                            ("title", t["title"]),
                            ("assignees", t["assignees"]),
                            ("deadline", t["deadline"]),
                            ("overdue", t["overdue"] or None),
                        )
                        if v
                    }
                    for t in col["tasks"]
                ],
            }
            for col in state["columns"]
        ],
    }
