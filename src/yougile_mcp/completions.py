"""Argument completion for the ready-made scenarios: people, projects, boards, columns, dates.

MCP completes prompt arguments only (tools have no completion), so these are the fields a
person fills in by hand in the client. Names come from the cached company structure; projects
outside the session's allowlist are not offered.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any

from mcp.types import Completion, PromptReference

from . import runtime
from .directory import NotFound, Structure, _norm

log = logging.getLogger(__name__)

MAX_VALUES = 100  # the protocol's cap per answer
ResolveRuntime = Callable[[], Awaitable[runtime.Runtime]]


def _matching(candidates: Iterable[str], typed: str) -> Completion:
    """Prefix matches first, then the rest that contain the typed text; no duplicates."""
    wanted = _norm(typed)
    unique = list(dict.fromkeys(c for c in candidates if c))
    starts = [c for c in unique if _norm(c).startswith(wanted)]
    contains = [c for c in unique if wanted and wanted in _norm(c) and c not in starts]
    found = starts + contains
    return Completion(values=found[:MAX_VALUES], total=len(found), has_more=len(found) > MAX_VALUES)


def _allowed_projects(rt: runtime.Runtime, s: Structure) -> list[dict]:
    policy = rt.policy
    allowed = (
        None if policy.project_refs is None else policy.resolve_projects(policy.project_refs, s)
    )
    return [p for p in s.projects.values() if allowed is None or p["id"] in allowed]


def _boards(rt: runtime.Runtime, s: Structure, project: str | None) -> list[str]:
    projects = _allowed_projects(rt, s)
    if project:
        projects = [p for p in projects if _norm(p.get("title")) == _norm(project)] or projects
    return [s.board_label(b) for p in projects for b in s.boards_of_project(p["id"])]


def _columns(rt: runtime.Runtime, s: Structure, board: str | None) -> list[str]:
    if board:
        try:
            found = s.find_board(board)
        except (NotFound, LookupError):
            found = None
        if found is not None:
            return [c.get("title") for c in s.columns_of_board(found["id"])]
    ids = {p["id"] for p in _allowed_projects(rt, s)}
    return sorted(
        {c.get("title") for c in s.columns.values() if s.project_of_column(c["id"]) in ids}
    )


def _dates(argument: str, today: date) -> list[str]:
    monday = today - timedelta(days=today.weekday())
    first = today.replace(day=1)
    last_month_end = first - timedelta(days=1)
    if argument == "since":
        days = [monday, monday - timedelta(days=7), first, last_month_end.replace(day=1)]
    else:
        days = [today, today - timedelta(days=1), monday - timedelta(days=1), last_month_end]
    return [d.isoformat() for d in days]


async def _values(rt: runtime.Runtime, prompt: str, argument: str, given: dict[str, str]):
    if argument == "person":
        users = await rt.directory.users()
        return ["me", *(u.get("realName") or u.get("email") for u in users)]
    if argument in ("since", "until") and prompt == "hours_report":
        return _dates(argument, datetime.now(rt.config.tz).date())
    s = await rt.directory.structure()
    if argument == "project":
        return [p.get("title") for p in _allowed_projects(rt, s)]
    if argument == "board":
        return _boards(rt, s, given.get("project"))
    if argument == "column":
        return _columns(rt, s, given.get("board"))
    return []


def completion_handler(resolve: ResolveRuntime | None) -> Callable[..., Awaitable[Any]]:
    """The server's completion handler; ``resolve`` finds the caller's runtime when nothing
    is bound (a hosted server: completion requests skip the middleware)."""

    async def complete(ref: Any, argument: Any, context: Any) -> Completion | None:
        if not isinstance(ref, PromptReference):
            return None
        try:
            rt = runtime.current()
        except RuntimeError:
            if resolve is None:
                return None
            try:
                rt = await resolve()
            except Exception as exc:  # noqa: BLE001 - no suggestions beat a failed request
                log.debug("completion without a runtime: %s", exc)
                return None
        given = dict(getattr(context, "arguments", None) or {})
        try:
            values = await _values(rt, ref.name, argument.name, given)
        except Exception as exc:  # noqa: BLE001 - e.g. YouGile unreachable or rate limited
            log.debug("completion failed: %s", exc)
            return None
        return _matching(values, argument.value or "")

    return complete
