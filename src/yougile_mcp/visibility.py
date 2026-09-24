"""Show each session only the tools and operations its permissions allow.

The policy still checks every call; this only keeps the model from reaching for what would be
refused: a read-only session does not see the task-writing tools, and a domain tool lists only
the operations the role and the denied operations leave. Screens (MCP Apps) and the tools behind
their buttons are shown only to clients that draw screens.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool

from . import apps, runtime
from .catalog import TOOLS, by_tool, find
from .policy import Policy, PolicyError

# Task-level tools that exist only to write, with the operations they write through.
WRITING_TOOLS = {
    "yougile_create_task": ("tasks.create",),
    "yougile_update_task": ("tasks.update",),
    "yougile_move_task": ("tasks.update",),
    "yougile_log_time": ("tasks.update",),
}
# Tools that also write: without the operation, these parameters go away.
WRITING_PARAMS = {
    "yougile_task_chat": (
        "chats.send_message",
        ("send", "confirm"),
        "Read the latest messages of a task's chat.",
    )
}


def tool_description(tool: str, operations: Sequence[str] | None = None) -> str:
    ops = by_tool()[tool]
    lines = [TOOLS[tool], "", "Operations ([access]):"]
    for name in operations or ops:
        lines.append(f"- {name} [{ops[name].access}]: {ops[name].summary}")
    lines.append("")
    lines.append(f"Call yougile_help('{tool}.<operation>') for parameters.")
    return "\n".join(lines)


def allowed(policy: Policy, operation: str) -> bool:
    op = find(operation)
    if op is None:
        return True
    try:
        policy.check_static(op, None)
    except PolicyError:
        return False
    return True


def _without_params(tool: Tool, names: Sequence[str], description: str) -> Tool:
    params = copy.deepcopy(tool.parameters)
    for name in names:
        params.get("properties", {}).pop(name, None)
        if name in params.get("required", []):
            params["required"].remove(name)
    return tool.model_copy(update={"parameters": params, "description": description})


def _domain_tool(tool: Tool, domain: str, policy: Policy) -> Tool | None:
    ops = [name for name, op in by_tool()[domain].items() if allowed(policy, op.full_name)]
    if not ops:
        return None
    if len(ops) == len(by_tool()[domain]):
        return tool
    params = copy.deepcopy(tool.parameters)
    params["properties"]["operation"]["enum"] = ops
    return tool.model_copy(
        update={"parameters": params, "description": tool_description(domain, ops)}
    )


def without_screens(tools: Sequence[Tool]) -> list[Tool]:
    return [t for t in tools if t.name not in apps.SCREENS and t.name not in apps.ACTIONS]


def visible_tools(tools: Sequence[Tool], policy: Policy) -> list[Tool]:
    shown: list[Tool] = []
    for tool in tools:
        name = tool.name
        if name in apps.ACTIONS:
            if all(allowed(policy, op) for op in apps.ACTIONS[name]):
                shown.append(tool)
        elif name in WRITING_TOOLS:
            if all(allowed(policy, op) for op in WRITING_TOOLS[name]):
                shown.append(tool)
        elif name in WRITING_PARAMS:
            op, params, description = WRITING_PARAMS[name]
            shown.append(
                tool if allowed(policy, op) else _without_params(tool, params, description)
            )
        elif name.startswith("yougile_") and name.removeprefix("yougile_") in TOOLS:
            narrowed = _domain_tool(tool, name.removeprefix("yougile_"), policy)
            if narrowed is not None:
                shown.append(narrowed)
        else:
            shown.append(tool)
    return shown


class ToolVisibility(Middleware):
    """Filters tool listings by the permissions of the runtime bound for the request, and by
    whether the client draws screens."""

    async def on_list_tools(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Sequence[Tool]]
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        if not apps.client_draws(context.fastmcp_context):
            tools = without_screens(tools)
        try:
            rt = runtime.current()
        except RuntimeError:
            return tools  # no runtime bound (e.g. the hosted server could not resolve the user)
        return visible_tools(tools, rt.policy)
