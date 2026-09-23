"""FastMCP server: one tool per API domain plus yougile_help."""

import contextlib
import difflib
import json
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from mcp.types import (
    ElicitRequest,
    ElicitRequestFormParams,
    InputRequiredResult,
    ToolAnnotations,
)
from pydantic import Field

from . import __version__, runtime
from .catalog import TOOLS, Operation, by_tool, find
from .client import YouGileError
from .directory import Ambiguous, NotFound
from .dispatch import ParamError, Prepared, describe, error_hint, prepare
from .policy import PolicyError

MODERN_PROTOCOL = "2026-07-28"
STRUCTURE_TOOLS = {"projects", "boards", "columns"}

BASE_INSTRUCTIONS = """\
YouGile (task tracker) REST API v2. Tools are grouped by domain (yougile_tasks, yougile_chats, \
yougile_boards, yougile_columns, yougile_projects, yougile_users, yougile_stickers, \
yougile_company, yougile_files, yougile_crm). Each takes `operation` and one flat `params` \
object holding path params, query params and body fields together. Before a write you have \
not done yet in this session, call yougile_help("tool.operation") for the exact fields.

Facts:
- A task can be addressed by its number wherever a task id is expected: the company-wide \
ID-123 or the project one like DEV-12.
- A task's chat id equals the task id (yougile_chats with chatId = task id).
- Deleting is soft: update with deleted=true; lists hide deleted objects unless includeDeleted=true.
- Lists return {paging, content}; default limit 50, max 1000; paging.next means more pages.
- Dates (deadline, sprint dates) are Unix timestamps in milliseconds; \
timeTracking plan/work are hours.
- Checklists and stickers are replaced as a whole on update: read, modify, write back.
- The API allows 50 requests per minute per company, shared with all colleagues: prefer \
filters and larger limits over many small calls.
"""


def instructions(rt: runtime.Runtime | None) -> str:
    text = BASE_INSTRUCTIONS
    if rt is None:
        return text
    text += f"\nSession permissions: {rt.policy.summary()}."
    if rt.config.project or rt.config.board:
        text += (
            f"\nWorkspace defaults: project={rt.config.project or '-'}, "
            f"board={rt.config.board or '-'}."
        )
    if rt.config.instructions:
        text += "\n\nCompany rules:\n" + rt.config.instructions.strip()
    return text


# ---------- confirmation ----------


def _client_can_elicit(ctx: Context) -> bool:
    try:
        caps = ctx.session.client_capabilities
    except Exception:  # noqa: BLE001 - no session: no elicitation
        return False
    return bool(caps and caps.elicitation is not None)


def _is_modern(ctx: Context) -> bool:
    rc = ctx.request_context
    return bool(rc is not None and str(getattr(rc, "protocol_version", "")) >= MODERN_PROTOCOL)


def _preview(prep: Prepared) -> str:
    target = ", ".join(f"{k}={v}" for k, v in prep.path_values.items())
    body = json.dumps(prep.body or {}, ensure_ascii=False)
    if len(body) > 600:
        body = body[:600] + "…"
    return f"{prep.op.full_name}({target}) {body}"


async def _confirm(
    ctx: Context | None, prep: Prepared, titles: list[str], confirm_flag: bool
) -> bool | InputRequiredResult:
    message = (
        f"Запись в проект «{', '.join(titles)}», который видят внешние участники. "
        f"Подтвердить?\n{_preview(prep)}"
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
                return InputRequiredResult(
                    result_type="input_required",
                    input_requests={
                        "confirm": ElicitRequest(method="elicitation/create", params=params)
                    },
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
        f"({', '.join(titles)}). Show the user exactly what will be written:\n{_preview(prep)}\n"
        "Repeat the call with confirm=true only after the user explicitly agrees."
    )


# ---------- execution ----------


def _operation(tool: str, operation: str) -> Operation:
    ops = by_tool()[tool]
    if operation in ops:
        return ops[operation]
    close = difflib.get_close_matches(operation, list(ops), n=3)
    raise ToolError(
        f"unknown operation {operation!r} for yougile_{tool}. "
        + (f"Did you mean: {', '.join(close)}? " if close else "")
        + f"Available: {', '.join(ops)}"
    )


async def execute(
    tool: str, operation: str, params: dict[str, Any] | None, confirm: bool, ctx: Context | None
) -> Any:
    rt = runtime.current()
    op = _operation(tool, operation)
    try:
        prep = prepare(op, params)
        rt.policy.check_static(op, prep.body)
        guard = await rt.policy.guard(op, prep, rt.client, rt.directory)
        if guard.confirm_titles:
            decision = await _confirm(ctx, prep, guard.confirm_titles, confirm)
            if isinstance(decision, InputRequiredResult):
                return decision
            if not decision:
                return {"cancelled": True, "reason": "the user did not confirm the write"}
        result = await prep.send(rt.client)
        result = await guard.apply(result, rt.directory)
    except (ParamError, PolicyError, NotFound, Ambiguous) as exc:
        raise ToolError(str(exc)) from exc
    except YouGileError as exc:
        detail = f"YouGile API error {exc.status}: {exc.message}" if exc.status else exc.message
        if exc.status in (400, 422):
            detail += f" (hint: {error_hint(op)})"
        elif exc.status == 403:
            detail += " (the API key's owner lacks rights for this in YouGile)"
        elif exc.status == 404:
            detail += " (not found, or not visible to the API key's owner)"
        raise ToolError(detail) from exc
    if op.access != "read" and op.tool in STRUCTURE_TOOLS:
        rt.directory.invalidate()
    return {"ok": True} if result in (None, "", {}) else result


# ---------- tool construction ----------

PARAMS_DOC = (
    "Flat object with path params, query params and body fields, "
    'e.g. {"id": "ID-123", "title": "New title"}. See yougile_help("tool.operation").'
)
CONFIRM_DOC = (
    "Set true only after the user explicitly approved a write into a client-facing project "
    "(needed only when the tool answered confirmation_required)."
)


def _tool_description(tool: str) -> str:
    lines = [TOOLS[tool], "", "Operations ([access]):"]
    for name, op in by_tool()[tool].items():
        lines.append(f"- {name} [{op.access}]: {op.summary}")
    lines.append("")
    lines.append(f"Call yougile_help('{tool}.<operation>') for parameters.")
    return "\n".join(lines)


def _domain_tool(tool: str) -> Tool:
    async def handler(operation, params=None, confirm=False, ctx=None):  # type: ignore[no-untyped-def]
        return await execute(tool, operation, params, confirm, ctx)

    handler.__annotations__ = {
        "operation": Literal[tuple(by_tool()[tool])],  # type: ignore[misc]
        "params": Annotated[dict[str, Any] | None, Field(description=PARAMS_DOC)],
        "confirm": Annotated[bool, Field(description=CONFIRM_DOC)],
        "ctx": Context | None,
        "return": Any,
    }
    handler.__name__ = f"yougile_{tool}"
    return Tool.from_function(
        handler,
        name=f"yougile_{tool}",
        description=_tool_description(tool),
        output_schema=None,
        annotations=ToolAnnotations(open_world_hint=True),
    )


async def yougile_help(
    operation: Annotated[
        str,
        Field(description='"list" for everything, a tool name like "tasks", or "tasks.create"'),
    ] = "list",
) -> dict[str, Any]:
    """Describe YouGile tools and operations: parameters, types, required fields, access level."""
    query = (operation or "list").strip().removeprefix("yougile_")
    tools = by_tool()
    if query in ("", "list", "all"):
        result: dict[str, Any] = {
            tool: {name: f"[{op.access}] {op.summary}" for name, op in ops.items()}
            for tool, ops in tools.items()
        }
        with contextlib.suppress(RuntimeError):
            result["_session"] = runtime.current().policy.summary()
        return result
    if query in tools:
        return {
            "tool": f"yougile_{query}",
            "description": TOOLS[query],
            "operations": {n: describe(op) for n, op in tools[query].items()},
        }
    op = find(query)
    if op is not None:
        return describe(op)
    names = [f"{t}.{n}" for t, ops in tools.items() for n in ops]
    close = difflib.get_close_matches(query, names, n=5, cutoff=0.4)
    raise ToolError(
        f"unknown operation {operation!r}. "
        + (f"Did you mean: {', '.join(close)}?" if close else "")
    )


def build_server(rt: runtime.Runtime | None = None) -> FastMCP:
    mcp = FastMCP(name="yougile", instructions=instructions(rt), version=__version__)
    for tool in TOOLS:
        mcp.add_tool(_domain_tool(tool))
    mcp.add_tool(
        Tool.from_function(
            yougile_help,
            name="yougile_help",
            annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        )
    )
    return mcp
