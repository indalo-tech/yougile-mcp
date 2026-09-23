"""Human-friendly conversions: dates in the company time zone, HTML <-> text, compact task views."""

from __future__ import annotations

import html
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .directory import Structure

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S")


def parse_when(text: str, tz: ZoneInfo) -> tuple[int, bool]:
    """``"2026-09-30"`` or ``"30.09.2026 18:00"`` -> (Unix ms, with_time).

    A date without time becomes local midnight, which is what the YouGile UI stores.
    """
    value = text.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            moment = datetime.strptime(value, fmt).replace(tzinfo=tz)
            return int(moment.timestamp() * 1000), True
        except ValueError:
            pass
    for fmt in _DATE_FORMATS:
        try:
            day = datetime.strptime(value, fmt).date()
            return int(datetime.combine(day, time(), tz).timestamp() * 1000), False
        except ValueError:
            pass
    raise ValueError(
        f"cannot read the date {text!r}: use YYYY-MM-DD or DD.MM.YYYY, optionally with HH:MM"
    )


def format_ms(ms: int | float | None, tz: ZoneInfo, with_time: bool = True) -> str | None:
    if not ms:
        return None
    moment = datetime.fromtimestamp(ms / 1000, tz)
    return moment.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def format_deadline(deadline: dict | None, tz: ZoneInfo) -> Any:
    if not deadline or deadline.get("deleted") or not deadline.get("deadline"):
        return None
    with_time = bool(deadline.get("withTime"))
    end = format_ms(deadline["deadline"], tz, with_time)
    start_ms = deadline.get("startDate")
    if start_ms and abs(start_ms - deadline["deadline"]) >= 60_000:
        return {"start": format_ms(start_ms, tz, with_time), "end": end}
    return end


def today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def is_overdue(task: dict, tz: ZoneInfo, now: datetime | None = None) -> bool:
    """An open task past its deadline; a deadline without time lasts until the end of that day."""
    deadline = task.get("deadline") or {}
    if task.get("completed") or task.get("archived"):
        return False
    if deadline.get("deleted") or not deadline.get("deadline"):
        return False
    now = now or datetime.now(tz)
    due = datetime.fromtimestamp(deadline["deadline"] / 1000, tz)
    return due < now if deadline.get("withTime") else due.date() < now.date()


_HTML_TAG = re.compile(r"</?(p|br|b|i|u|s|ul|ol|li|a|strong|em|div|span|h\d|pre|code)\b", re.I)


def text_to_html(text: str) -> str:
    """Plain text (with newlines) -> YouGile HTML; text that already is HTML passes as is."""
    if _HTML_TAG.search(text):
        return text
    return html.escape(text, quote=False).replace("\n", "<br>")


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</(p|div|li|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def status_of(task: dict) -> str:
    if task.get("deleted"):
        return "deleted"
    if task.get("archived"):
        return "archived"
    return "completed" if task.get("completed") else "open"


def user_label(user: dict | None, fallback: str = "?") -> str:
    if not user:
        return fallback
    return user.get("realName") or user.get("email") or fallback


def task_summary(
    task: dict,
    structure: Structure,
    users: dict[str, dict],
    tz: ZoneInfo,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One line per task for lists."""
    out: dict[str, Any] = {
        "number": task.get("idTaskCommon"),
        "title": task.get("title"),
        "where": structure.column_label(task.get("columnId")) or "(no column)",
        "status": status_of(task),
    }
    if task.get("completed") and task.get("completedTimestamp"):
        out["completed_at"] = format_ms(task["completedTimestamp"], tz)
    if task.get("idTaskProject"):
        out["project_number"] = task["idTaskProject"]
    if task.get("assigned"):
        out["assignees"] = [user_label(users.get(u), u) for u in task["assigned"]]
    if deadline := format_deadline(task.get("deadline"), tz):
        out["deadline"] = deadline
        if is_overdue(task, tz, now):
            out["overdue"] = True
    tracking = task.get("timeTracking") or {}
    if tracking.get("plan") or tracking.get("work"):
        out["hours"] = {"plan": tracking.get("plan", 0), "work": tracking.get("work", 0)}
    return out


def task_card(
    task: dict,
    structure: Structure,
    users: dict[str, dict],
    stickers: dict[str, dict],
    tz: ZoneInfo,
) -> dict[str, Any]:
    """Everything a person would read on the card, with names instead of ids."""
    card = task_summary(task, structure, users, tz)
    card["id"] = task.get("id")
    if task.get("createdBy") or task.get("timestamp"):
        card["created"] = {
            "at": format_ms(task.get("timestamp"), tz),
            "by": user_label(users.get(task.get("createdBy", "")), task.get("createdBy") or "?"),
        }
    if task.get("color"):
        card["color"] = task["color"]
    if task.get("checklists"):
        card["checklists"] = [
            {
                "title": cl.get("title", ""),
                "items": [
                    f"[{'x' if item.get('isCompleted') else ' '}] {item.get('title', '')}"
                    for item in cl.get("items", [])
                ],
            }
            for cl in task["checklists"]
        ]
    if task.get("stickers"):
        named: dict[str, Any] = {}
        unnamed: dict[str, Any] = {}  # types the API does not list (numbers, free text)
        for sticker_id, value in task["stickers"].items():
            sticker = stickers.get(sticker_id)
            if sticker is None:
                unnamed[sticker_id] = value
            else:
                named[sticker["name"]] = sticker["states"].get(value, value)
        if named:
            card["stickers"] = named
        if unnamed:
            card["other_stickers"] = unnamed
    if task.get("subtasks"):
        card["subtasks"] = len(task["subtasks"])
    if description := html_to_text(task.get("description")):
        card["description"] = description
    return card
