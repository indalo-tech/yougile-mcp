"""Operation catalog: the bundled YouGile OpenAPI spec plus a curated mapping onto MCP tools.

Every operation in the spec must be listed in ``MAPPING`` (tests enforce it), so a spec
update that adds endpoints fails loudly instead of silently dropping them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Literal

Access = Literal["read", "write", "admin"]

API_PREFIX = "/api-v2"

# operationId -> (tool, operation, access). tool=None: not exposed as an MCP tool
# (auth endpoints take a login and password, which must never pass through a model).
MAPPING: dict[str, tuple[str | None, str, Access]] = {
    # tasks
    "TaskController_search": ("tasks", "list", "read"),
    "TaskController_searchReversed": ("tasks", "list_newest", "read"),
    "TaskController_get": ("tasks", "get", "read"),
    "TaskController_create": ("tasks", "create", "write"),
    "TaskController_update": ("tasks", "update", "write"),
    "TaskController_getChatSubscribers": ("tasks", "get_chat_subscribers", "read"),
    "TaskController_updateChatSubscribers": ("tasks", "set_chat_subscribers", "write"),
    # chats
    "ChatMessageController_search": ("chats", "list_messages", "read"),
    "ChatMessageController_get": ("chats", "get_message", "read"),
    "ChatMessageController_sendMessage": ("chats", "send_message", "write"),
    "ChatMessageController_update": ("chats", "update_message", "write"),
    "ChatMessageController_typing": ("chats", "typing", "write"),
    "GroupChatController_search": ("chats", "list_group_chats", "read"),
    "GroupChatController_get": ("chats", "get_group_chat", "read"),
    "GroupChatController_create": ("chats", "create_group_chat", "write"),
    "GroupChatController_update": ("chats", "update_group_chat", "write"),
    # boards
    "BoardController_search": ("boards", "list", "read"),
    "BoardController_get": ("boards", "get", "read"),
    "BoardController_create": ("boards", "create", "admin"),
    "BoardController_update": ("boards", "update", "admin"),
    # columns
    "ColumnController_search": ("columns", "list", "read"),
    "ColumnController_get": ("columns", "get", "read"),
    "ColumnController_create": ("columns", "create", "admin"),
    "ColumnController_update": ("columns", "update", "admin"),
    # projects and project roles
    "ProjectController_search": ("projects", "list", "read"),
    "ProjectController_get": ("projects", "get", "read"),
    "ProjectController_create": ("projects", "create", "admin"),
    "ProjectController_update": ("projects", "update", "admin"),
    "ProjectRolesController_search": ("projects", "list_roles", "read"),
    "ProjectRolesController_get": ("projects", "get_role", "read"),
    "ProjectRolesController_create": ("projects", "create_role", "admin"),
    "ProjectRolesController_update": ("projects", "update_role", "admin"),
    "ProjectRolesController_delete": ("projects", "delete_role", "admin"),
    # users and departments
    "UserController_search": ("users", "list", "read"),
    "UserController_get": ("users", "get", "read"),
    "UserController_getMe": ("users", "me", "read"),
    "UserController_create": ("users", "invite", "admin"),
    "UserController_update": ("users", "update", "admin"),
    "UserController_delete": ("users", "remove", "admin"),
    "DepartmentController_search": ("users", "list_departments", "read"),
    "DepartmentController_get": ("users", "get_department", "read"),
    "DepartmentController_create": ("users", "create_department", "admin"),
    "DepartmentController_update": ("users", "update_department", "admin"),
    # stickers
    "StringStickerController_search": ("stickers", "list_string", "read"),
    "StringStickerController_get": ("stickers", "get_string", "read"),
    "StringStickerController_create": ("stickers", "create_string", "admin"),
    "StringStickerController_update": ("stickers", "update_string", "admin"),
    "StringStickerStateController_get": ("stickers", "get_string_state", "read"),
    "StringStickerStateController_create": ("stickers", "create_string_state", "admin"),
    "StringStickerStateController_update": ("stickers", "update_string_state", "admin"),
    "SprintStickerController_search": ("stickers", "list_sprint", "read"),
    "SprintStickerController_getSticker": ("stickers", "get_sprint", "read"),
    "SprintStickerController_create": ("stickers", "create_sprint", "admin"),
    "SprintStickerController_update": ("stickers", "update_sprint", "admin"),
    "SprintStickerStateController_get": ("stickers", "get_sprint_state", "read"),
    "SprintStickerStateController_create": ("stickers", "create_sprint_state", "admin"),
    "SprintStickerStateController_update": ("stickers", "update_sprint_state", "admin"),
    # company and webhooks
    "CompanyController_get": ("company", "get", "read"),
    "CompanyController_update": ("company", "update", "admin"),
    "WebhookController_search": ("company", "list_webhooks", "admin"),
    "WebhookController_create": ("company", "create_webhook", "admin"),
    "WebhookController_put": ("company", "update_webhook", "admin"),
    # files
    "FileController_uploadFile": ("files", "upload", "write"),
    # crm
    "CrmContactPersonsController_create": ("crm", "create_contact_person", "write"),
    "CrmExternalIdController_findContactByExternalId": (
        "crm",
        "find_contact_by_external_id",
        "read",
    ),
    # auth: CLI only
    "getCompanies": (None, "list_companies", "read"),
    "AuthKeyController_search": (None, "list_keys", "read"),
    "AuthKeyController_create": (None, "create_key", "write"),
    "AuthKeyController_delete": (None, "delete_key", "write"),
}

TOOLS: dict[str, str] = {
    "tasks": (
        "YouGile tasks: list/search (filters: columnId, assignedTo, stickerId, title), get by UUID "
        "or by number like ID-123, create, update (move via columnId, complete, archive, deadline, "
        "timeTracking plan/work hours, checklists, stickers, soft-delete via deleted=true), "
        "task chat subscribers. A task's chat id equals the task id (see yougile_chats)."
    ),
    "chats": (
        "Chat messages of tasks (chatId = task id) and group chats: history, send, edit/delete, "
        "reactions; group chat management."
    ),
    "boards": "Boards: list (by projectId), get, create, update/rename/move/soft-delete.",
    "columns": "Board columns: list (by boardId), get, create, update/rename/soft-delete.",
    "projects": "Projects and project roles: list, get, create, update members, roles CRUD.",
    "users": "Company employees and departments: list, get, me, invite, update, remove.",
    "stickers": "Custom stickers (string/state and sprint) and their states.",
    "company": "Company details and webhooks (event subscriptions).",
    "files": "Upload a file to YouGile; returns a URL to use in chat messages or descriptions.",
    "crm": "CRM: contact persons and lookup of contacts by external messenger id.",
}


@dataclass(frozen=True)
class Param:
    name: str
    location: Literal["path", "query"]
    required: bool
    schema: dict[str, Any]
    description: str = ""


@dataclass(frozen=True)
class Operation:
    operation_id: str
    tool: str | None
    name: str
    access: Access
    method: str
    path: str
    summary: str
    description: str
    params: tuple[Param, ...] = ()
    body_schema: dict[str, Any] | None = None
    body_content_type: str | None = None
    body_required: tuple[str, ...] = field(default=())

    @property
    def full_name(self) -> str:
        return f"{self.tool}.{self.name}"

    @property
    def path_params(self) -> list[Param]:
        return [p for p in self.params if p.location == "path"]

    @property
    def query_params(self) -> list[Param]:
        return [p for p in self.params if p.location == "query"]

    @property
    def body_fields(self) -> dict[str, Any]:
        return (self.body_schema or {}).get("properties", {})

    @property
    def is_multipart(self) -> bool:
        return self.body_content_type == "multipart/form-data"


def load_spec() -> dict[str, Any]:
    text = resources.files("yougile_mcp").joinpath("data/openapi.json").read_text("utf-8")
    return json.loads(text)


def _ref_name(schema: dict[str, Any]) -> str:
    # The spec has at least one broken "$ref": "#/components/schemas/" next to an inline schema.
    return str(schema.get("$ref", "")).rsplit("/", 1)[-1]


def deref(schema: dict[str, Any], schemas: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Resolve $ref and single-item allOf wrappers recursively (bounded depth)."""
    if depth > 8:
        return schema
    name = _ref_name(schema)
    if name:
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        return deref({**schemas[name], **merged}, schemas, depth + 1)
    schema = {k: v for k, v in schema.items() if k != "$ref"}
    if "allOf" in schema and len(schema["allOf"]) == 1:
        inner = deref(schema["allOf"][0], schemas, depth + 1)
        rest = {k: v for k, v in schema.items() if k != "allOf"}
        return {**inner, **rest}
    out = dict(schema)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {k: deref(v, schemas, depth + 1) for k, v in out["properties"].items()}
    if isinstance(out.get("items"), dict):
        out["items"] = deref(out["items"], schemas, depth + 1)
    return out


def _normalize_path(path: str) -> str:
    path = path.removeprefix(API_PREFIX)
    # "/companies{*companyId}" is an optional wildcard suffix; the bare path means "my company".
    return path.replace("{*companyId}", "")


@cache
def operations() -> dict[str, Operation]:
    """All spec operations keyed by operationId."""
    spec = load_spec()
    schemas = spec.get("components", {}).get("schemas", {})
    result: dict[str, Operation] = {}
    for raw_path, item in spec["paths"].items():
        for method, op in item.items():
            op_id = op["operationId"]
            if op_id not in MAPPING:
                raise KeyError(f"operation {op_id} is not mapped in catalog.MAPPING")
            tool, name, access = MAPPING[op_id]
            params = tuple(
                Param(
                    name=p["name"],
                    location=p["in"],
                    required=bool(p.get("required")),
                    schema=deref(p.get("schema", {}), schemas),
                    description=(p.get("description") or "").strip(),
                )
                for p in op.get("parameters", [])
                if p["in"] in ("path", "query")
            )
            body_schema = content_type = None
            body_required: tuple[str, ...] = ()
            if rb := op.get("requestBody"):
                content_type, media = next(iter(rb["content"].items()))
                body_schema = deref(media.get("schema", {}), schemas)
                body_required = tuple(body_schema.get("required", []))
            result[op_id] = Operation(
                operation_id=op_id,
                tool=tool,
                name=name,
                access=access,
                method=method.upper(),
                path=_normalize_path(raw_path),
                summary=(op.get("summary") or "").strip(),
                description=(op.get("description") or "").strip(),
                params=params,
                body_schema=body_schema,
                body_content_type=content_type,
                body_required=body_required,
            )
    return result


@cache
def by_tool() -> dict[str, dict[str, Operation]]:
    """Exposed operations grouped by tool: {"tasks": {"create": Operation, ...}, ...}."""
    grouped: dict[str, dict[str, Operation]] = {t: {} for t in TOOLS}
    for op in operations().values():
        if op.tool is not None:
            grouped[op.tool][op.name] = op
    return grouped


def find(name: str) -> Operation | None:
    """Look up an exposed operation by "tool.op", "yougile_tool.op" or a unique bare op name."""
    name = name.strip().removeprefix("yougile_")
    tools = by_tool()
    if "." in name:
        tool, _, op = name.partition(".")
        return tools.get(tool, {}).get(op)
    matches = [ops[name] for ops in tools.values() if name in ops]
    return matches[0] if len(matches) == 1 else None


def auth_operation(name: str) -> Operation:
    """Auth endpoints (not exposed as tools) by their catalog name, e.g. "create_key"."""
    for op in operations().values():
        if op.tool is None and op.name == name:
            return op
    raise KeyError(name)
