from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from yougile_mcp.client import YouGileClient
from yougile_mcp.config import WorkspaceConfig
from yougile_mcp.directory import Directory
from yougile_mcp.policy import Policy
from yougile_mcp.runtime import Runtime

MSK_2026_09_30 = 1790715600000  # 2026-09-30 00:00 Europe/Moscow

PROJECTS = [
    {"id": "p-int", "title": "Разработка"},
    {"id": "p-cli", "title": "Клиенты"},
]
BOARDS = [
    {"id": "b-hub-int", "title": "Сайт", "projectId": "p-int"},
    {"id": "b-hub-cli", "title": "Сайт", "projectId": "p-cli"},
]
COLUMNS = [
    {"id": "c-int-queue", "title": "Очередь", "boardId": "b-hub-int"},
    {"id": "c-int-work", "title": "В работе", "boardId": "b-hub-int"},
    {"id": "c-int-review", "title": "На проверке", "boardId": "b-hub-int"},
    {"id": "c-int-done", "title": "Готово", "boardId": "b-hub-int"},
    {"id": "c-cli-queue", "title": "Очередь", "boardId": "b-hub-cli"},
    {"id": "c-cli-work", "title": "В работе", "boardId": "b-hub-cli"},
]
# The fake enforces a Workflow chain on the internal board: only neighbouring moves pass.
WORKFLOW = {"b-hub-int": ["c-int-queue", "c-int-work", "c-int-review", "c-int-done"]}
USERS = [
    {"id": "u-me", "realName": "Анна Смирнова", "email": "anna@example.com", "isAdmin": True},
    {"id": "u-ivan", "realName": "Иван Петров", "email": "ivan@example.com"},
]
STRING_STICKERS = [
    {"id": "st-prio", "name": "Приоритет", "states": [{"id": "s-high", "name": "Высокий"}]}
]
TASKS = {
    "t-int": {
        "id": "t-int",
        "title": "Internal",
        "columnId": "c-int-queue",
        "idTaskCommon": "ID-1",
        "idTaskProject": "DEV-1",
        "timestamp": MSK_2026_09_30 - 86_400_000,
        "createdBy": "u-me",
        "assigned": ["u-ivan"],
        "deadline": {"deadline": MSK_2026_09_30, "startDate": MSK_2026_09_30},
        "timeTracking": {"plan": 5, "work": 3},
        "checklists": [
            {
                "title": "Шаги",
                "items": [
                    {"title": "Написать код", "isCompleted": False},
                    {"title": "Проверить", "isCompleted": False},
                ],
            }
        ],
        # st-num: a sticker type the API does not list (a number), so it has no name for us
        "stickers": {"st-prio": "s-high", "st-num": "0"},
        "description": "<p>Первая строка</p><p>Вторая &amp; последняя</p>",
    },
    "t-done": {
        "id": "t-done",
        "title": "Finished work",
        "columnId": "c-int-done",
        "idTaskCommon": "ID-3",
        "completed": True,
        "completedTimestamp": MSK_2026_09_30 - 2 * 86_400_000 + 15 * 3_600_000,  # 28.09 15:00
    },
    "t-cli": {"id": "t-cli", "title": "Client", "columnId": "c-cli-queue", "idTaskCommon": "ID-2"},
}
MESSAGES = {
    "t-int": [
        {"id": 1000, "fromUserId": "u-ivan", "text": "Начал"},
        {"id": 2000, "fromUserId": "u-me", "text": "Ок"},
        {"id": 3000, "fromUserId": "u-ivan", "text": "Готово к проверке"},
    ]
}


def page(items: list[dict]) -> dict:
    return {
        "paging": {"count": len(items), "limit": 1000, "offset": 0, "next": False},
        "content": items,
    }


def ok(data: Any, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, json=data)


class FakeYouGile:
    """Small in-memory YouGile API with mutable tasks and chats; records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.overrides: dict[tuple[str, str], Callable[[httpx2.Request], httpx2.Response]] = {}
        self.tasks = copy.deepcopy(TASKS)
        self.messages = copy.deepcopy(MESSAGES)
        self.uploads: list[str] = []

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content or b"null")

    def bodies(self, method: str, path: str) -> list[Any]:
        return [
            json.loads(r.content or b"null")
            for r in self.requests
            if r.method == method and r.url.path == path
        ]

    def calls(self, method: str, path: str) -> int:
        return sum(1 for r in self.requests if r.method == method and r.url.path == path)

    def find_task(self, ref: str) -> dict | None:
        for task in self.tasks.values():
            if ref in (task["id"], task.get("idTaskCommon"), task.get("idTaskProject")):
                return task
        return None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api-v2")
        method = request.method
        if (method, path) in self.overrides:
            return self.overrides[(method, path)](request)
        parts = path.strip("/").split("/")
        multipart = request.headers.get("content-type", "").startswith("multipart/")
        body = json.loads(request.content) if request.content and not multipart else None

        if method == "GET":
            static = {
                "/projects": PROJECTS,
                "/boards": BOARDS,
                "/columns": COLUMNS,
                "/users": USERS,
                "/string-stickers": STRING_STICKERS,
                "/sprint-stickers": [],
            }
            if path in static:
                return ok(page(static[path]))
            if path == "/users/me":
                return ok(USERS[0])
            if path in ("/task-list", "/tasks"):
                column = request.url.params.get("columnId")
                assignee = request.url.params.get("assignedTo")
                items = [
                    t
                    for t in self.tasks.values()
                    if (not column or t.get("columnId") == column)
                    and (not assignee or assignee in (t.get("assigned") or []))
                ]
                return ok(page(items))
            if parts[0] == "tasks" and len(parts) == 2:
                task = self.find_task(parts[1])
                return ok(task) if task else ok({"error": "Not found"}, 404)
            if parts[0] == "chats":
                if self.find_task(parts[1]) is None:
                    return ok({"error": "Not found"}, 404)
                return ok(page(self.messages.get(parts[1], [])))

        if method == "PUT" and parts[0] == "tasks" and len(parts) == 2:
            task = self.find_task(parts[1])
            if task is None:
                return ok({"error": "Not found"}, 404)
            new_column = (body or {}).get("columnId")
            if new_column and new_column != task.get("columnId"):
                board = next(c["boardId"] for c in COLUMNS if c["id"] == task["columnId"])
                chain = WORKFLOW.get(board) or []
                jump = new_column in chain and (
                    abs(chain.index(new_column) - chain.index(task["columnId"])) != 1
                )
                if jump:
                    return ok({"error": "Переход запрещён настройками Workflow"}, 400)
            task.update(body or {})
            return ok({"id": task["id"]})

        if method == "POST" and path == "/upload-file":
            # multipart: the file name is in the part's Content-Disposition header
            name = request.content.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
            self.uploads.append(name)
            url = f"/user-data/company/{name}"
            return ok({"result": "ok", "url": url, "fullUrl": "https://yougile.test" + url})
        if method == "POST" and path == "/tasks":
            new = {"id": "t-new", "idTaskCommon": "ID-99", **(body or {})}
            new.pop("idempotencyKey", None)
            self.tasks["t-new"] = new
            return ok({"id": "t-new"}, 201)
        if method == "POST" and parts[0] == "chats" and parts[-1] == "messages":
            chat = self.messages.setdefault(parts[1], [])
            # A message id is its creation time in ms, so a new one is always the largest.
            new_id = max((m["id"] for m in chat), default=0) + 1000
            message = {"id": new_id, "fromUserId": "u-me", **(body or {})}
            chat.append(message)
            return ok({"id": message["id"]}, 201)
        return ok({"error": f"no fake route for {method} {path}"}, 404)


@pytest.fixture
def fake() -> FakeYouGile:
    return FakeYouGile()


@pytest.fixture
def make_runtime(fake: FakeYouGile) -> Callable[..., Runtime]:
    def build(**config: Any) -> Runtime:
        client = YouGileClient("test-key", transport=httpx2.MockTransport(fake))
        cfg = WorkspaceConfig.from_dict(config)
        return Runtime(client, cfg, Policy.from_config(cfg), Directory(client))

    return build
