"""What the screens show, as plain data: rows for the task table and the state of a task card.

Display strings are made here, on the server, so the screens need no formatting logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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


def rights(work: Work) -> dict[str, bool]:
    """Which buttons the session may use; the policy still checks every call."""
    policy = work.rt.policy
    return {
        "update": allowed(policy, "tasks.update"),
        "chat": allowed(policy, "chats.send_message"),
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
