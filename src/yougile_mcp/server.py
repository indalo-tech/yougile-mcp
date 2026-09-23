"""FastMCP server: task-level tools, one tool per API domain, and yougile_help."""

import contextlib
import difflib
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, runtime, smart
from .caller import Caller, tool_errors
from .catalog import TOOLS, Operation, by_tool, find
from .dispatch import describe

BASE_INSTRUCTIONS = """\
YouGile (task tracker). Two kinds of tools:
- Task-level tools take names and numbers instead of UUIDs: yougile_overview (projects, \
boards, columns), yougile_find_tasks, yougile_task (open a card), yougile_create_task, \
yougile_update_task, yougile_move_task (follows Workflow chains), yougile_log_time, \
yougile_task_chat. Prefer them for everyday work.
- Domain tools cover the whole REST API v2 (yougile_tasks, yougile_chats, yougile_boards, \
yougile_columns, yougile_projects, yougile_users, yougile_stickers, yougile_company, \
yougile_files, yougile_crm). Each takes `operation` and one flat `params` object holding path \
params, query params and body fields together. Before a write you have not done yet in this \
session, call yougile_help("tool.operation") for the exact fields.

Facts:
- A task can be addressed by its number wherever a task is expected: the company-wide \
ID-123 or the project one like DEV-12.
- A task's chat id equals the task id.
- Deleting is soft: update with deleted=true; lists hide deleted objects unless includeDeleted=true.
- Raw API dates are Unix timestamps in milliseconds; task-level tools take and show dates \
as YYYY-MM-DD [HH:MM] in the company time zone. Hours are hours.
- Checklists and stickers are replaced as a whole on raw updates: read, modify, write back.
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
    text += f"\nCompany time zone: {rt.config.timezone}."
    if rt.config.instructions:
        text += "\n\nCompany rules:\n" + rt.config.instructions.strip()
    return text


# ---------- domain tools ----------


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


@tool_errors
async def execute(
    tool: str, operation: str, params: dict[str, Any] | None, confirm: bool, ctx: Context | None
) -> Any:
    op = _operation(tool, operation)
    result = await Caller(ctx, confirm).call(op.full_name, params)
    return {"ok": True} if result in (None, "", {}) else result


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
    """Describe YouGile domain tools and operations: parameters, types, required fields, access."""
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
    smart.register(mcp)
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
