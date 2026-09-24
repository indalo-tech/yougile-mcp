"""Interactive screens (MCP Apps) drawn with Prefab UI, for clients that can show them.

A screen is a tool the model calls (``yougile_show_*``): the person gets the screen, the model
gets a short text version of the same data. Buttons on a screen call ``yougile_app_*`` tools,
which only the screen may call; they go through ``Caller`` like every other tool, so the
session's permissions apply. A click is the person's confirmation of that write, including
writes into projects that need one.

Everything here needs the optional ``apps`` extra (Prefab UI); without it, or for clients that
do not announce MCP Apps support (Claude Code, for one), these tools are not shown at all.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

UI_EXTENSION_ID = "io.modelcontextprotocol/ui"  # = fastmcp.apps.config.UI_EXTENSION_ID

# Screens, with the operations a screen needs to be of any use.
SCREENS = {
    "yougile_show_tasks": ("tasks.list",),
    "yougile_show_task": ("tasks.get",),
    "yougile_show_board": ("tasks.list",),
    "yougile_new_task_form": ("tasks.create",),
}
# Tools behind the screens' buttons, with the operations they go through.
ACTIONS = {
    "yougile_app_tasks": ("tasks.list",),
    "yougile_app_task": ("tasks.get",),
    "yougile_app_board": ("tasks.list",),
    "yougile_app_columns": ("tasks.create",),
    "yougile_app_create": ("tasks.create",),
    "yougile_app_complete": ("tasks.update",),
    "yougile_app_take": ("tasks.update",),
    "yougile_app_move": ("tasks.update",),
    "yougile_app_check": ("tasks.update",),
    "yougile_app_log_time": ("tasks.update",),
    "yougile_app_send": ("chats.send_message",),
}


def available() -> bool:
    """Whether Prefab UI is installed (the ``apps`` extra)."""
    return importlib.util.find_spec("prefab_ui") is not None


def client_draws(ctx: Any) -> bool:
    """Whether the client of this request announced MCP Apps support."""
    if ctx is None:
        return False
    try:
        session = ctx.session
    except RuntimeError:
        return False
    # 2026-07-28 requests carry capabilities without the rest of the initialize params.
    caps = getattr(session, "client_capabilities", None)
    if caps is None:
        params = getattr(session, "client_params", None)
        caps = getattr(params, "capabilities", None)
    if caps is None:
        return False
    extensions = getattr(caps, "extensions", None) or (caps.model_extra or {}).get("extensions")
    return bool(extensions) and UI_EXTENSION_ID in extensions


def register(mcp: FastMCP) -> None:
    if not available():
        return
    from . import actions, board, form, screens

    screens.register(mcp)
    board.register(mcp)
    form.register(mcp)
    actions.register(mcp)
