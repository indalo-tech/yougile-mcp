"""A task's history (YouGile's task log, ``tasks.get_log``): when a card reached a column.

YouGile keeps no date for a card put into a done column without being marked completed, and
the task API says nothing about when a card moved. The log does: ``move`` events carry the
columns (``from``, ``to``) and the time; ``add`` is the creation (in the column the card was
created in). The log keeps a year of events.

Every lookup is one request against the company's shared limit, so a call looks up at most
MAX_LOOKUPS tasks — the most recently created first — and says how many it left unchecked.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import progress
from .client import YouGileError

if TYPE_CHECKING:
    from .smart import Work

MAX_LOOKUPS = 20  # task logs one call may read
LOG_LIMIT = 100  # events per log read: enough for a card's recent moves
DONE_AT = "historyDoneAt"  # the date found in the log, kept on the task dict


@dataclass
class Lookups:
    """Logs read in one call, so a task is read once, and what was left unread."""

    budget: int = field(default_factory=lambda: MAX_LOOKUPS)  # read when made, not imported
    logs: dict[str, list[dict]] = field(default_factory=dict)
    unchecked: int = 0

    async def log(self, work: Work, task_id: str) -> list[dict] | None:
        if task_id in self.logs:
            return self.logs[task_id]
        if self.budget <= 0:
            self.unchecked += 1
            return None
        self.budget -= 1
        try:
            page = await work.caller.call("tasks.get_log", {"id": task_id, "limit": LOG_LIMIT})
        except YouGileError:
            self.logs[task_id] = []  # no log (an old API, no rights): as if nothing is known
            return []
        content = page.get("content", []) if isinstance(page, dict) else []
        self.logs[task_id] = [e for e in content if isinstance(e, dict)]
        return self.logs[task_id]


def arrived(events: Iterable[dict], columns: Collection[str], current: str | None) -> int | None:
    """When the card last came into one of ``columns``: its latest move there, or — never
    moved and still there — its creation. None when the log does not tell (older than a
    year, say)."""
    events = list(events)
    moves = sorted(
        (e for e in events if e.get("type") == "move"),
        key=lambda e: e.get("timestamp") or 0,
        reverse=True,
    )
    for e in moves:
        if e.get("to") in columns:
            return int(e["timestamp"])
    if not moves and current in columns:
        created = next((e for e in events if e.get("type") == "add"), None)
        if created and created.get("timestamp"):
            return int(created["timestamp"])
    return None


async def date_done_cards(
    work: Work,
    tasks: list[dict],
    done_columns: Collection[str],
    lookups: Lookups,
    before: int | None = None,
) -> list[dict]:
    """The tasks, those in a done column without a completion date given the date they came
    there (DONE_AT) from their log. The newest cards are looked up first; cards created at or
    after ``before`` (the period's end) cannot have been done in it and are not looked up."""
    undated = [
        t
        for t in tasks
        if t.get("columnId") in done_columns
        and not (t.get("completed") and t.get("completedTimestamp"))
        and (before is None or (t.get("timestamp") or 0) < before)
    ]
    if not undated:
        return tasks
    undated.sort(key=lambda t: t.get("timestamp") or 0, reverse=True)
    await progress.report(f"Смотрю историю задач в колонках «готово»: {len(undated)}")
    found: dict[str, int] = {}
    for t in undated:
        events = await lookups.log(work, t["id"])
        if events and (when := arrived(events, done_columns, t.get("columnId"))):
            found[t["id"]] = when
    return [{**t, DONE_AT: found[t["id"]]} if t["id"] in found else t for t in tasks]


def done_at(task: dict) -> int | None:
    """When the task was done: its completion date, or the one its log gave."""
    if task.get("completed") and task.get("completedTimestamp"):
        return int(task["completedTimestamp"])
    return task.get(DONE_AT)


async def moves_since(
    work: Work, tasks: list[dict], since: int, lookups: Lookups
) -> list[tuple[dict, dict]]:
    """(task, move) for every move of these tasks at or after ``since``, newest first."""
    moved: list[tuple[dict, dict]] = []
    for t in tasks:
        events = await lookups.log(work, t["id"])
        for e in events or []:
            if e.get("type") == "move" and (e.get("timestamp") or 0) >= since:
                moved.append((t, e))
    moved.sort(key=lambda m: m[1].get("timestamp") or 0, reverse=True)
    return moved


def note(lookups: Lookups) -> dict[str, Any]:
    """What to tell when the budget ran out."""
    if not lookups.unchecked:
        return {}
    return {
        "history_unchecked": lookups.unchecked,
        "history_hint": f"the history of {lookups.unchecked} more card(s) was not read (each is "
        "a request against the company's limit): narrow the search (a board, a person) to "
        "date them",
    }
