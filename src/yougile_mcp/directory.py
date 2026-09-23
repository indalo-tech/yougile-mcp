"""Cached company structure (projects, boards, columns, users) and name resolution.

Loading everything takes a handful of requests (lists accept limit=1000), so the cache
saves the shared 50 requests/minute budget for real work.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from .client import YouGileClient

DEFAULT_TTL = 300.0
PAGE = 1000


class NotFound(LookupError):
    pass


class Ambiguous(LookupError):
    pass


async def fetch_all(
    client: YouGileClient, path: str, query: dict[str, Any] | None = None
) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        page = await client.request(
            "GET", path, query={**(query or {}), "limit": PAGE, "offset": offset}
        )
        content = (page or {}).get("content", []) if isinstance(page, dict) else []
        items.extend(content)
        paging = (page or {}).get("paging", {}) if isinstance(page, dict) else {}
        if not paging.get("next") or not content:
            return items
        offset += len(content)


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


@dataclass
class Structure:
    projects: dict[str, dict] = field(default_factory=dict)
    boards: dict[str, dict] = field(default_factory=dict)
    columns: dict[str, dict] = field(default_factory=dict)
    loaded_at: float = 0.0

    def project_of_board(self, board_id: str | None) -> str | None:
        board = self.boards.get(board_id or "")
        return board.get("projectId") if board else None

    def project_of_column(self, column_id: str | None) -> str | None:
        column = self.columns.get(column_id or "")
        return self.project_of_board(column.get("boardId")) if column else None

    def board_of_column(self, column_id: str | None) -> str | None:
        column = self.columns.get(column_id or "")
        return column.get("boardId") if column else None

    def columns_of_board(self, board_id: str) -> list[dict]:
        """Columns in the order the API returns them (which matches the screen order)."""
        return [c for c in self.columns.values() if c.get("boardId") == board_id]

    def boards_of_project(self, project_id: str) -> list[dict]:
        return [b for b in self.boards.values() if b.get("projectId") == project_id]

    # ---- name resolution: every lookup accepts an id or a (case-insensitive) title ----

    def find_project(self, ref: str) -> dict:
        return _pick(self.projects.values(), ref, "project")

    def find_board(self, ref: str, project: str | None = None) -> dict:
        """``ref`` may be "Project / Board", a board title, or an id."""
        if ref in self.boards:
            return self.boards[ref]
        if "/" in ref and project is None:
            proj_ref, _, board_ref = ref.rpartition("/")
            project = self.find_project(proj_ref.strip())["id"]
            ref = board_ref.strip()
        elif project is not None and project not in self.projects:
            project = self.find_project(project)["id"]
        pool = [b for b in self.boards.values() if project is None or b.get("projectId") == project]
        return _pick(pool, ref, "board", label=self.board_label)

    def find_column(self, ref: str, board_id: str) -> dict:
        if ref in self.columns and self.columns[ref].get("boardId") == board_id:
            return self.columns[ref]
        return _pick(self.columns_of_board(board_id), ref, "column")

    def board_label(self, board: dict) -> str:
        project = self.projects.get(board.get("projectId", ""), {})
        return f"{project.get('title', '?')} / {board.get('title', '?')}"

    def column_label(self, column_id: str | None) -> str | None:
        column = self.columns.get(column_id or "")
        if not column:
            return None
        board = self.boards.get(column.get("boardId", ""), {})
        return f"{self.board_label(board)} / {column.get('title', '?')}"


def _pick(items: Any, ref: str, kind: str, label: Any = None) -> dict:
    items = list(items)
    for item in items:
        if item.get("id") == ref:
            return item
    wanted = _norm(ref)
    exact = [i for i in items if _norm(i.get("title")) == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        names = ", ".join((label or (lambda i: i.get("title")))(i) for i in exact)
        raise Ambiguous(f"{kind} {ref!r} is ambiguous: {names}")
    partial = [i for i in items if wanted and wanted in _norm(i.get("title"))]
    if len(partial) == 1:
        return partial[0]
    hint = ", ".join(
        sorted(str((label or (lambda i: i.get("title")))(i)) for i in (partial or items))[:20]
    )
    raise NotFound(f"{kind} {ref!r} not found" + (f". Candidates: {hint}" if hint else ""))


class Directory:
    def __init__(self, client: YouGileClient, ttl: float = DEFAULT_TTL) -> None:
        self.client = client
        self.ttl = ttl
        self._structure: Structure | None = None
        self._users: tuple[float, list[dict]] | None = None
        self._stickers: tuple[float, dict[str, dict]] | None = None
        self._me: dict | None = None
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._structure = None

    async def structure(self, *, refresh: bool = False) -> Structure:
        async with self._lock:
            now = time.monotonic()
            if refresh or self._structure is None or now - self._structure.loaded_at > self.ttl:
                projects = await fetch_all(self.client, "/projects")
                boards = await fetch_all(self.client, "/boards")
                columns = await fetch_all(self.client, "/columns")
                self._structure = Structure(
                    projects={p["id"]: p for p in projects},
                    boards={b["id"]: b for b in boards},
                    columns={c["id"]: c for c in columns},
                    loaded_at=now,
                )
            return self._structure

    async def project_of_column(self, column_id: str | None) -> str | None:
        """Project of a column, refreshing the cache once if the column is new."""
        if not column_id:
            return None
        structure = await self.structure()
        project = structure.project_of_column(column_id)
        if project is None:
            project = (await self.structure(refresh=True)).project_of_column(column_id)
        return project

    async def users(self) -> list[dict]:
        now = time.monotonic()
        if self._users is None or now - self._users[0] > self.ttl:
            self._users = (now, await fetch_all(self.client, "/users"))
        return self._users[1]

    async def users_by_id(self) -> dict[str, dict]:
        return {u["id"]: u for u in await self.users()}

    async def me(self) -> dict:
        if self._me is None:
            self._me = await self.client.request("GET", "/users/me")
        return self._me

    async def stickers(self) -> dict[str, dict]:
        """``{sticker_id: {"name": ..., "states": {state_id: name}}}`` for all custom stickers."""
        now = time.monotonic()
        if self._stickers is None or now - self._stickers[0] > self.ttl:
            table: dict[str, dict] = {}
            for path in ("/string-stickers", "/sprint-stickers"):
                for sticker in await fetch_all(self.client, path):
                    states = {s["id"]: s.get("name", s["id"]) for s in sticker.get("states") or []}
                    table[sticker["id"]] = {
                        "name": sticker.get("name", sticker["id"]),
                        "states": states,
                    }
            self._stickers = (now, table)
        return self._stickers[1]

    async def find_user(self, ref: str) -> dict:
        """By id, email, "me", or (partial, case-insensitive) real name."""
        if _norm(ref) in ("me", "я"):
            return await self.me()
        users = await self.users()
        wanted = _norm(ref)
        for user in users:
            if user.get("id") == ref or _norm(user.get("email")) == wanted:
                return user
        named = [dict(u, title=u.get("realName") or u.get("email")) for u in users]
        found = _pick(named, ref, "user")
        return next(u for u in users if u.get("id") == found.get("id"))
