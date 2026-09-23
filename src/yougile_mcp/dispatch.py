"""Turn a tool call ``(operation, params)`` into an HTTP request; describe operations for help."""

from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .catalog import Operation, Param
from .client import YouGileClient


class ParamError(ValueError):
    """Invalid parameters for an operation; the message is meant for the model."""


@dataclass
class Prepared:
    op: Operation
    path: str
    path_values: dict[str, str]
    query: dict[str, Any]
    body: dict[str, Any] | None
    files: dict[str, tuple[str, bytes, str]] | None = None

    async def send(self, client: YouGileClient) -> Any:
        return await client.request(
            self.op.method,
            self.path,
            query=self.query or None,
            json=None if self.files else self.body,
            files=self.files,
        )


def prepare(op: Operation, params: dict[str, Any] | None) -> Prepared:
    params = dict(params or {})
    explicit_query = params.pop("query", None) or {}
    explicit_body = params.pop("body", None) or {}
    if not isinstance(explicit_query, dict) or not isinstance(explicit_body, dict):
        raise ParamError('"query" and "body" must be objects')

    path_values: dict[str, str] = {}
    path_params = op.path_params
    for p in path_params:
        value = params.pop(p.name, None)
        if value is None and len(path_params) == 1 and p.name != "id":
            value = params.pop("id", None)  # tolerate {"id": ...} for chatId / projectId
        if value is None or value == "":
            raise ParamError(f"{op.full_name}: missing required path parameter {p.name!r}")
        path_values[p.name] = str(value)

    if op.is_multipart:
        return _prepare_upload(op, params, path_values)

    query_names = {p.name for p in op.query_params}
    body_fields = op.body_fields
    query: dict[str, Any] = {}
    body: dict[str, Any] = {}
    unknown: list[str] = []
    for key, value in {**explicit_query, **params}.items():
        if key in query_names:
            query[key] = value
        elif op.body_schema is not None and (key in body_fields or not body_fields):
            body[key] = value
        else:
            unknown.append(key)
    for key, value in explicit_body.items():
        if op.body_schema is None or (body_fields and key not in body_fields):
            unknown.append(key)
        else:
            body[key] = value
    if unknown:
        allowed = sorted(query_names | set(body_fields) | {p.name for p in path_params})
        raise ParamError(
            f"{op.full_name}: unknown parameter(s) {', '.join(sorted(set(unknown)))}. "
            f"Allowed: {', '.join(allowed) or 'none'}. See yougile_help('{op.full_name}')."
        )
    if op.method == "POST" and "idempotencyKey" in body_fields and "idempotencyKey" not in body:
        body["idempotencyKey"] = str(uuid.uuid4())  # makes create retries safe

    path = op.path
    for name, value in path_values.items():
        path = path.replace("{" + name + "}", quote(value, safe=""))
    has_body = op.body_schema is not None
    return Prepared(op, path, path_values, query, body if has_body else None)


def _prepare_upload(op: Operation, params: dict[str, Any], path_values: dict[str, str]) -> Prepared:
    file_path = params.pop("file_path", None)
    content_b64 = params.pop("content_base64", None)
    filename = params.pop("filename", None)
    if params:
        raise ParamError(
            f"{op.full_name}: unknown parameter(s) {', '.join(sorted(params))}. "
            "Allowed: file_path, or content_base64 + filename."
        )
    if file_path:
        src = Path(str(file_path)).expanduser()
        if not src.is_file():
            raise ParamError(f"file not found: {src}")
        data, filename = src.read_bytes(), filename or src.name
    elif content_b64 and filename:
        try:
            data = base64.b64decode(str(content_b64), validate=True)
        except ValueError as exc:
            raise ParamError(f"content_base64 is not valid base64: {exc}") from exc
    else:
        raise ParamError(
            f"{op.full_name}: pass file_path, or content_base64 together with filename"
        )
    ctype = mimetypes.guess_type(str(filename))[0] or "application/octet-stream"
    return Prepared(
        op, op.path, path_values, {}, None, files={"file": (str(filename), data, ctype)}
    )


# ---------- help rendering ----------


def type_of(schema: dict[str, Any], depth: int = 0) -> str:
    if "enum" in schema:
        return "enum(" + "|".join(str(v) for v in schema["enum"][:15]) + ")"
    kind = schema.get("type")
    if kind == "array":
        return f"array<{type_of(schema.get('items', {}), depth + 1)}>"
    props = schema.get("properties")
    if (kind == "object" or props) and props and depth < 2:
        req = set(schema.get("required", []))
        inner = ", ".join(
            f"{k}{'*' if k in req else ''}: {type_of(v, depth + 1)}"
            for k, v in list(props.items())[:15]
        )
        return "object{" + inner + "}"
    return str(kind or "any")


def _field(name: str, schema: dict[str, Any], required: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "type": type_of(schema)}
    if required:
        out["required"] = True
    if desc := (schema.get("description") or "").strip():
        out["description"] = desc if len(desc) <= 400 else desc[:400] + "…"
    if "example" in schema:
        example = json.dumps(schema["example"], ensure_ascii=False)
        if len(example) <= 300:
            out["example"] = schema["example"]
    if "default" in schema:
        out["default"] = schema["default"]
    return out


def _param(p: Param) -> dict[str, Any]:
    return _field(
        p.name,
        {**p.schema, "description": p.description or p.schema.get("description")},
        p.required,
    )


def describe(op: Operation) -> dict[str, Any]:
    info: dict[str, Any] = {
        "operation": op.full_name,
        "summary": op.summary,
        "http": f"{op.method} /api-v2{op.path}",
        "access": op.access,
    }
    if op.description:
        info["description"] = op.description[:1500]
    if op.path_params:
        info["path_params"] = [_param(p) for p in op.path_params]
    if op.query_params:
        info["query_params"] = [_param(p) for p in op.query_params]
    if op.is_multipart:
        info["body"] = [
            {
                "name": "file_path",
                "type": "string",
                "description": "Local path of the file to upload",
            },
            {
                "name": "content_base64",
                "type": "string",
                "description": "Or: file content in base64",
            },
            {
                "name": "filename",
                "type": "string",
                "description": "File name (with content_base64)",
            },
        ]
    elif op.body_schema is not None:
        req = set(op.body_required)
        info["body"] = [
            _field(k, v, k in req) for k, v in op.body_fields.items() if k != "idempotencyKey"
        ]
    info["usage"] = (
        "Pass path params, query params and body fields together in one flat params object."
    )
    return info


def error_hint(op: Operation) -> str:
    parts = []
    if op.body_required:
        parts.append("required body fields: " + ", ".join(op.body_required))
    required_query = [p.name for p in op.query_params if p.required]
    if required_query:
        parts.append("required query params: " + ", ".join(required_query))
    parts.append(f"see yougile_help('{op.full_name}')")
    return "; ".join(parts)
