"""Run catalog operations for one tool call: policy checks, human confirmation, error mapping.

Both the domain tools and the task-level tools go through ``Caller``, so permissions apply
identically everywhere. A confirmation is asked at most once per tool call, even when the
tool performs several writes (e.g. moving a card step by step along a Workflow chain).
"""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec

from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult

from . import runtime
from .catalog import find
from .client import YouGileError
from .directory import Ambiguous, NotFound
from .dispatch import ParamError, Prepared, error_hint, prepare
from .policy import PolicyError

MODERN_PROTOCOL = "2026-07-28"
STRUCTURE_TOOLS = {"projects", "boards", "columns"}


class InputRequired(Exception):  # noqa: N818 - control flow, not an error
    """Ask the client for input (2026-07-28 protocol); the tool is re-run with the answer."""

    def __init__(self, result: InputRequiredResult) -> None:
        super().__init__("input required")
        self.result = result


class Cancelled(Exception):  # noqa: N818 - control flow, not an error
    """The user declined a confirmation."""


def _client_can_elicit(ctx: Context) -> bool:
    try:
        caps = ctx.session.client_capabilities
    except Exception:  # noqa: BLE001 - no session: no elicitation
        return False
    return bool(caps and caps.elicitation is not None)


def _is_modern(ctx: Context) -> bool:
    rc = ctx.request_context
    return bool(rc is not None and str(getattr(rc, "protocol_version", "")) >= MODERN_PROTOCOL)


def preview(prep: Prepared) -> str:
    target = ", ".join(f"{k}={v}" for k, v in prep.path_values.items())
    body = json.dumps(prep.body or {}, ensure_ascii=False)
    if len(body) > 600:
        body = body[:600] + "…"
    return f"{prep.op.full_name}({target}) {body}"


async def ask_confirmation(
    ctx: Context | None, what: str, titles: list[str], confirm_flag: bool
) -> bool:
    """True if confirmed. Raises InputRequired (modern clients) or ToolError (no elicitation)."""
    message = (
        f"Запись в проект «{', '.join(titles)}», который видят внешние участники. "
        f"Подтвердить?\n{what}"
    )
    if ctx is not None and _client_can_elicit(ctx):
        if _is_modern(ctx):
            responses = ctx.input_responses
            if responses is None:
                params = ElicitRequestFormParams(
                    message=message,
                    requested_schema={
                        "type": "object",
                        "properties": {"value": {"type": "boolean", "title": "Подтверждаю запись"}},
                        "required": ["value"],
                    },
                )
                raise InputRequired(
                    InputRequiredResult(
                        result_type="input_required",
                        input_requests={
                            "confirm": ElicitRequest(method="elicitation/create", params=params)
                        },
                    )
                )
            answer = responses.get("confirm")
            content = getattr(answer, "content", None) or {}
            return getattr(answer, "action", None) == "accept" and bool(content.get("value"))
        result = await ctx.elicit(message, response_type=bool)
        return result.action == "accept" and bool(getattr(result, "data", False))
    if confirm_flag:
        return True
    raise ToolError(
        "confirmation_required: this writes into a project visible to external people "
        f"({', '.join(titles)}). Show the user exactly what will be written:\n{what}\n"
        "Repeat the call with confirm=true only after the user explicitly agrees."
    )


class Caller:
    def __init__(self, ctx: Context | None = None, confirm: bool = False) -> None:
        self.rt = runtime.current()
        self.ctx = ctx
        self.confirm_flag = confirm
        self.confirmed: set[str] = set()

    @property
    def config(self):  # noqa: ANN201 - convenience
        return self.rt.config

    async def call(self, operation: str, params: dict[str, Any] | None = None) -> Any:
        op = find(operation)
        if op is None:
            raise ValueError(f"unknown catalog operation {operation}")
        rt = self.rt
        prep = prepare(op, params, allow_local_files=rt.allow_local_files)
        rt.policy.check_static(op, prep.body)
        guard = await rt.policy.guard(op, prep, rt.client, rt.directory)
        pending = [t for t in guard.confirm_titles if t not in self.confirmed]
        if pending:
            if not await ask_confirmation(self.ctx, preview(prep), pending, self.confirm_flag):
                raise Cancelled()
            self.confirmed.update(pending)
        try:
            result = await prep.send(rt.client)
        except YouGileError as exc:
            exc.hint = error_hint(op)  # type: ignore[attr-defined]
            raise
        result = await guard.apply(result, rt.directory)
        if op.access != "read" and op.tool in STRUCTURE_TOOLS:
            rt.directory.invalidate()
        return result


def describe_api_error(exc: YouGileError) -> str:
    detail = f"YouGile API error {exc.status}: {exc.message}" if exc.status else exc.message
    if exc.status in (400, 422) and getattr(exc, "hint", None):
        detail += f" (hint: {exc.hint})"  # type: ignore[attr-defined]
    elif exc.status == 403:
        detail += " (the API key's owner lacks rights for this in YouGile)"
    elif exc.status == 404:
        detail += " (not found, or not visible to the API key's owner)"
    return detail


def describe_policy_error(exc: PolicyError) -> str:
    """The refusal plus where this session's permissions can be changed."""
    try:
        hint = runtime.current().settings_hint
    except RuntimeError:
        return str(exc)
    return f"{exc}. Permissions are set in {hint}"


P = ParamSpec("P")


def tool_errors(fn: Callable[P, Awaitable[Any]]) -> Callable[P, Awaitable[Any]]:
    """Map domain errors to ToolError and control-flow exceptions to results."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        try:
            return await fn(*args, **kwargs)
        except InputRequired as req:
            return req.result
        except Cancelled:
            return {"cancelled": True, "reason": "the user did not confirm the write"}
        except PolicyError as exc:
            raise ToolError(describe_policy_error(exc)) from exc
        except (ParamError, NotFound, Ambiguous, ValueError) as exc:
            raise ToolError(str(exc)) from exc
        except YouGileError as exc:
            raise ToolError(describe_api_error(exc)) from exc

    return wrapper
