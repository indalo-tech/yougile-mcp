"""The attach-files screen: drop files onto a task; they go to YouGile and into its chat.

Files travel from the browser to this server inside a tool call (base64), so their size is
capped: the screen refuses bigger ones before sending, the server checks again.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.actions import CallTool, SetState, ShowToast
from prefab_ui.components import (
    Badge,
    Button,
    Column,
    DropZone,
    Heading,
    Link,
    Muted,
    Row,
    Small,
    Textarea,
)
from prefab_ui.components.control_flow import ForEach, If
from prefab_ui.rx import RESULT, Rx
from pydantic import BaseModel, Field

from ..caller import tool_errors
from ..smart import TaskRef, Work, attach_files
from .screens import add_screens, display_toggle, on_error, screen

MAX_FILE_MB = 10
MAX_FILES = 10


class DroppedFile(BaseModel):
    """A file as the screen's drop zone hands it over."""

    name: str
    size: int = 0
    type: str = ""
    data: str = Field(description="Base64 content")


def view() -> Column:
    chosen = Rx("files").length() > 0
    with Column(gap=3) as root:
        with Row(align="center", justify="between"):
            with Column(gap=0):
                Heading("Файлы в задачу", level=3)
                Muted("{{ task.number }} {{ task.title }}")
            display_toggle()
        DropZone(
            name="files",
            label="Перетащите файлы сюда или нажмите, чтобы выбрать",
            description=f"До {MAX_FILES} файлов, каждый до {MAX_FILE_MB} МБ",
            multiple=True,
            max_size=MAX_FILE_MB * 1024 * 1024,
        )
        with If(chosen), Column(gap=1):
            Small("Выбрано:")
            with ForEach("files") as (_, file):
                Muted(f"{file.name}")
        Textarea(name="comment", placeholder="Комментарий к файлам (необязательно)", rows=2)
        with Row(gap=2):
            Button(
                "Прикрепить",
                disabled=~chosen,
                on_click=CallTool(
                    "yougile_app_attach",
                    arguments={
                        "task": "{{ task.id }}",
                        "files": "{{ files }}",
                        "comment": "{{ comment }}",
                    },
                    on_success=[
                        SetState("attached", RESULT.attached),
                        SetState("files", []),
                        SetState("comment", ""),
                        ShowToast("Файлы прикреплены", variant="success"),
                    ],
                    on_error=on_error(),
                ),
            )
            with If(chosen):
                Button("Очистить", variant="outline", on_click=SetState("files", []))
        with If(Rx("attached").length() > 0), Column(gap=1):
            Small("Прикреплено к задаче:")
            with ForEach("attached") as (_, file), Row(gap=2, align="center"):
                Badge("файл", variant="secondary")
                Link(f"{file.name}", href=f"{file.url}", target="_blank")
    return root


@tool_errors
async def yougile_attach_files(task: TaskRef, ctx: Context | None = None) -> ToolResult:
    """Show the user a place to drop files for a task: they go to YouGile and appear in the
    task's chat as attachments, with an optional comment. Use it when the user wants to attach
    files from their computer to a task."""
    work = Work(ctx)
    t = await work.task(task)
    number = t.get("idTaskCommon") or work.number(t)
    return screen(
        f"Файлы в задачу {number}",
        view(),
        {
            "task": {"id": t["id"], "number": number, "title": t.get("title") or ""},
            "files": [],
            "comment": "",
            "attached": [],
        },
        {
            "shown_to_user": "a drop zone for files; the user attaches them with its button",
            "task": number,
            "title": t.get("title"),
        },
    )


def decoded_size(file: DroppedFile) -> int:
    try:
        return len(base64.b64decode(file.data, validate=True))
    except (binascii.Error, ValueError):
        raise ValueError(f"{file.name}: the file content is damaged, drop it again") from None


@tool_errors
async def yougile_app_attach(
    task: TaskRef,
    files: Annotated[list[DroppedFile], Field(max_length=MAX_FILES)],
    comment: str | None = None,
) -> dict[str, Any]:
    """Upload the dropped files and post them into the task's chat."""
    if not files:
        raise ValueError("choose files first")
    for file in files:
        if decoded_size(file) > MAX_FILE_MB * 1024 * 1024:
            raise ValueError(f"{file.name} is larger than {MAX_FILE_MB} MB")
    work = Work(None, confirm=True)  # the click is the confirmation
    t = await work.task(task)
    uploads = [{"content_base64": f.data, "filename": f.name} for f in files]
    attached = await attach_files(work, t, uploads, comment)
    return {"attached": [{"name": a["name"], "url": a["link"]} for a in attached]}


def register(mcp: FastMCP) -> None:
    add_screens(mcp, yougile_attach_files)
