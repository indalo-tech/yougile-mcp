from __future__ import annotations

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
    {"id": "c-cli-queue", "title": "Очередь", "boardId": "b-hub-cli"},
    {"id": "c-cli-work", "title": "В работе", "boardId": "b-hub-cli"},
]
TASKS = {
    "t-int": {
        "id": "t-int",
        "title": "Internal",
        "columnId": "c-int-queue",
        "idTaskCommon": "ID-1",
    },
    "t-cli": {"id": "t-cli", "title": "Client", "columnId": "c-cli-queue", "idTaskCommon": "ID-2"},
}


def page(items: list[dict]) -> dict:
    return {
        "paging": {"count": len(items), "limit": 1000, "offset": 0, "next": False},
        "content": items,
    }


class FakeYouGile:
    """Minimal in-memory YouGile API; records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.overrides: dict[tuple[str, str], Callable[[httpx2.Request], httpx2.Response]] = {}

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content or b"null")

    def calls(self, method: str, path: str) -> int:
        return sum(1 for r in self.requests if r.method == method and r.url.path == path)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api-v2")
        key = (request.method, path)
        if key in self.overrides:
            return self.overrides[key](request)
        if request.method == "GET":
            if path == "/projects":
                return httpx2.Response(200, json=page(PROJECTS))
            if path == "/boards":
                return httpx2.Response(200, json=page(BOARDS))
            if path == "/columns":
                return httpx2.Response(200, json=page(COLUMNS))
            if path in ("/task-list", "/tasks"):
                return httpx2.Response(200, json=page(list(TASKS.values())))
            if path.startswith("/tasks/"):
                task_id = path.split("/")[2]
                for task in TASKS.values():
                    if task_id in (task["id"], task["idTaskCommon"]):
                        return httpx2.Response(200, json=task)
                return httpx2.Response(404, json={"error": "Not found"})
            if path.startswith("/chats/"):
                return httpx2.Response(200, json=page([{"id": 1, "text": "hi"}]))
        if request.method == "PUT" and path.startswith("/tasks/"):
            return httpx2.Response(200, json={"id": path.split("/")[2]})
        if request.method == "POST" and path.startswith("/chats/"):
            return httpx2.Response(201, json={"id": 123})
        if request.method == "POST" and path == "/tasks":
            return httpx2.Response(201, json={"id": "t-new"})
        return httpx2.Response(404, json={"error": f"no fake route for {request.method} {path}"})


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
