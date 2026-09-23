"""Permissions on top of YouGile's own: role, project allowlist, confirmations, denied operations.

YouGile already applies the rights of the key's owner. This layer narrows them further for
an MCP session: e.g. a read-only agent, one allowed project, or "ask before writing into the
client-facing project".
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .catalog import Operation
from .client import YouGileClient, YouGileError
from .config import Role, WorkspaceConfig
from .directory import Directory, Structure, _norm
from .dispatch import Prepared

ROLE_LEVEL = {"reader": 0, "member": 1, "admin": 2}
ACCESS_LEVEL = {"read": 0, "write": 1, "admin": 2}
ROLE_FOR_ACCESS = {"read": "reader", "write": "member", "admin": "admin"}

# Company-level writes that remain allowed under a project allowlist.
COMPANY_WRITES_ALLOWED = {"files.upload"}

ProjectOf = Callable[[Structure, Any], "str | None"]


class PolicyError(PermissionError):
    """The operation is not allowed; the message is meant for the model and the user."""


def action_names(op: Operation, body: dict[str, Any] | None) -> list[str]:
    """``tasks.update`` with ``deleted: true`` is also the action ``tasks.delete``."""
    names = [op.full_name]
    if op.name.startswith("update") and isinstance(body, dict) and body.get("deleted") is True:
        names.append(f"{op.tool}.{op.name.replace('update', 'delete', 1)}")
    return names


@dataclass
class Guard:
    """What the policy decided for one call; ``apply`` enforces it on the API result."""

    op: Operation | None = None
    allowed: set[str] | None = None
    confirm_titles: list[str] = field(default_factory=list)
    result_project: ProjectOf | None = None  # single object must belong to an allowed project
    item_project: ProjectOf | None = None  # list items outside allowed projects are hidden

    async def apply(self, result: Any, directory: Directory) -> Any:
        if self.allowed is None:
            return result
        structure = await directory.structure()
        if self.result_project is not None and isinstance(result, dict):
            project = self.result_project(structure, result)
            if project is None:  # maybe created after the cache was loaded
                project = self.result_project(await directory.structure(refresh=True), result)
            if project not in self.allowed:
                raise PolicyError(
                    f"{self.op.full_name if self.op else 'operation'}: "
                    "the object is outside the projects allowed for this session"
                )
        if self.item_project is not None and isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                if any(self.item_project(structure, i) is None for i in content):
                    structure = await directory.structure(refresh=True)
                kept = [i for i in content if self.item_project(structure, i) in self.allowed]
                if len(kept) != len(content):
                    result = {
                        **result,
                        "content": kept,
                        "hidden_by_policy": len(content) - len(kept),
                    }
        return result


@dataclass
class Policy:
    role: Role = "admin"
    project_refs: list[str] | None = None
    confirm_refs: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: WorkspaceConfig) -> Policy:
        return cls(cfg.role, cfg.projects, list(cfg.confirm_projects), list(cfg.deny))

    def summary(self) -> str:
        parts = [f"role={self.role}"]
        if self.project_refs is not None:
            parts.append("projects=" + (", ".join(self.project_refs) or "none"))
        if self.confirm_refs:
            parts.append("confirm writes in: " + ", ".join(self.confirm_refs))
        if self.deny:
            parts.append("denied: " + ", ".join(self.deny))
        return "; ".join(parts)

    # ---- static checks (no API calls) ----

    def check_static(self, op: Operation, body: dict[str, Any] | None) -> None:
        if ROLE_LEVEL[self.role] < ACCESS_LEVEL[op.access]:
            raise PolicyError(
                f"{op.full_name} needs role {ROLE_FOR_ACCESS[op.access]!r}; "
                f"this session is {self.role!r}"
            )
        for name in action_names(op, body):
            for pattern in self.deny:
                if fnmatch.fnmatchcase(name, pattern.removeprefix("yougile_")):
                    raise PolicyError(f"{name} is denied for this session (rule {pattern!r})")

    # ---- project scoping (may need the structure cache and a prefetch) ----

    @staticmethod
    def resolve_projects(refs: list[str], structure: Structure) -> set[str]:
        ids = set()
        for ref in refs:
            if ref in structure.projects:
                ids.add(ref)
            else:
                ids.update(
                    pid
                    for pid, p in structure.projects.items()
                    if _norm(p.get("title")) == _norm(ref)
                )
        return ids

    async def guard(
        self, op: Operation, prep: Prepared, client: YouGileClient, directory: Directory
    ) -> Guard:
        writes = op.access != "read"
        if self.project_refs is None and not (self.confirm_refs and writes):
            return Guard(op=op)
        structure = await directory.structure()
        allowed = (
            None
            if self.project_refs is None
            else self.resolve_projects(self.project_refs, structure)
        )
        confirm = self.resolve_projects(self.confirm_refs, structure) if writes else set()

        scope = await _scope(op, prep, client, directory, structure)
        guard = Guard(op=op, allowed=allowed)
        if allowed is not None:
            if scope.projects is None:
                if writes and op.full_name not in COMPANY_WRITES_ALLOWED:
                    raise PolicyError(
                        f"{op.full_name} is company-wide and this session is limited to projects: "
                        + ", ".join(self.project_refs or [])
                    )
            elif not scope.projects or not scope.projects <= allowed:
                raise PolicyError(
                    f"{op.full_name}: the target is outside the projects allowed for this session"
                )
            guard.result_project = scope.result_project
            guard.item_project = scope.item_project
        if confirm and scope.projects and scope.projects & confirm:
            guard.confirm_titles = sorted(
                structure.projects[p].get("title", p) for p in scope.projects & confirm
            )
        return guard


@dataclass
class _Scope:
    projects: set[str] | None = None  # None = company-level (or checked on the result)
    result_project: ProjectOf | None = None
    item_project: ProjectOf | None = None


def _known(*ids: str | None) -> set[str]:
    """Target set, or an empty set (= deny) when any target cannot be determined."""
    return {i for i in ids if i} if all(ids) else set()


def _task_project(s: Structure, task: Any) -> str | None:
    return s.project_of_column((task or {}).get("columnId"))


async def _fetch_task_project(
    task_id: str, client: YouGileClient, directory: Directory
) -> str | None:
    task = await client.request("GET", f"/tasks/{task_id}")
    return await directory.project_of_column((task or {}).get("columnId"))


async def _scope(
    op: Operation, prep: Prepared, client: YouGileClient, directory: Directory, s: Structure
) -> _Scope:
    tool, name = op.tool, op.name
    pv, body, query = prep.path_values, prep.body or {}, prep.query

    if tool == "projects":
        if name == "list":
            return _Scope(item_project=lambda _s, p: p.get("id"))
        if name == "create":
            return _Scope()
        return _Scope(projects={pv.get("id") or pv.get("projectId")})
    if tool == "boards":
        if name == "list":
            pid = query.get("projectId")
            return _Scope(
                projects={pid} if pid else None, item_project=lambda _s, b: b.get("projectId")
            )
        if name == "create":
            return _Scope(projects=_known(body.get("projectId")))
        ids = [s.project_of_board(pv["id"])]
        if body.get("projectId"):
            ids.append(body["projectId"])
        return _Scope(projects=_known(*ids))
    if tool == "columns":
        if name == "list":
            bid = query.get("boardId")
            return _Scope(
                projects=_known(s.project_of_board(bid)) if bid else None,
                item_project=lambda st, c: st.project_of_board(c.get("boardId")),
            )
        if name == "create":
            return _Scope(projects=_known(s.project_of_board(body.get("boardId"))))
        ids = [await directory.project_of_column(pv["id"])]
        if body.get("boardId"):
            ids.append(s.project_of_board(body["boardId"]))
        return _Scope(projects=_known(*ids))
    if tool == "tasks":
        if name in ("list", "list_newest"):
            cid = query.get("columnId")
            return _Scope(
                projects=_known(await directory.project_of_column(cid)) if cid else None,
                item_project=_task_project,
            )
        if name == "create":
            return _Scope(projects=_known(await directory.project_of_column(body.get("columnId"))))
        if name == "get":
            return _Scope(result_project=_task_project)  # checked on the fetched task, no prefetch
        ids = [await _fetch_task_project(pv["id"], client, directory)]
        if body.get("columnId"):
            ids.append(await directory.project_of_column(body["columnId"]))
        return _Scope(projects=_known(*ids))
    if tool == "chats" and "chatId" in pv:
        try:
            return _Scope(
                projects=_known(await _fetch_task_project(pv["chatId"], client, directory))
            )
        except YouGileError as exc:
            if exc.status in (400, 404):
                return _Scope()  # not a task: a group chat, which is company-level
            raise
    if tool == "crm" and name == "create_contact_person":
        return _Scope(projects=_known(body.get("projectId")))
    return _Scope()
