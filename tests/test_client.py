import httpx2
import pytest

from yougile_mcp import client as client_mod
from yougile_mcp.client import YouGileClient, YouGileError, normalize_base_url


class RecordingLimiter:
    def __init__(self):
        self.acquired = 0
        self.penalties: list[float] = []

    async def acquire(self):
        self.acquired += 1

    async def penalize(self, seconds):
        self.penalties.append(seconds)


def make(handler, **kw):
    return YouGileClient("secret", transport=httpx2.MockTransport(handler), **kw)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", instant)


async def test_auth_header_and_query_serialization():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx2.Response(200, json={"ok": 1})

    async with make(handler) as c:
        assert await c.request("GET", "/tasks", query={"includeDeleted": True, "skip": None}) == {
            "ok": 1
        }
    assert seen["auth"] == "Bearer secret"
    assert seen["url"] == "https://ru.yougile.com/api-v2/tasks?includeDeleted=true"


async def test_429_penalizes_and_retries():
    responses = iter(
        [httpx2.Response(429, headers={"Retry-After": "7"}), httpx2.Response(200, json=[])]
    )
    limiter = RecordingLimiter()
    async with make(lambda r: next(responses), limiter=limiter) as c:
        assert await c.request("POST", "/chats/x/messages", json={"text": "a"}) == []
    assert limiter.penalties == [7.0]
    assert limiter.acquired == 2


async def test_post_without_idempotency_key_is_not_retried_on_5xx():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx2.Response(502, json={"error": "bad gateway"})

    async with make(handler) as c:
        with pytest.raises(YouGileError) as err:
            await c.request("POST", "/chats/x/messages", json={"text": "a"})
    assert len(calls) == 1
    assert err.value.status == 502 and err.value.message == "bad gateway"


async def test_get_and_idempotent_post_are_retried_on_5xx():
    for method, body in (("GET", None), ("POST", {"title": "t", "idempotencyKey": "k"})):
        responses = iter([httpx2.Response(503), httpx2.Response(200, json={"id": 1})])
        async with make(lambda r, it=responses: next(it)) as c:
            assert await c.request(method, "/tasks", json=body) == {"id": 1}


async def test_error_message_list_is_joined():
    async with make(
        lambda r: httpx2.Response(400, json={"message": ["a is bad", "b is bad"]})
    ) as c:
        with pytest.raises(YouGileError, match="a is bad; b is bad"):
            await c.request("PUT", "/tasks/x", json={})


async def test_missing_key():
    async with YouGileClient(
        None, transport=httpx2.MockTransport(lambda r: httpx2.Response(200))
    ) as c:
        with pytest.raises(YouGileError, match="YOUGILE_API_KEY"):
            await c.request("GET", "/tasks")


def test_normalize_base_url():
    assert normalize_base_url("https://ru.yougile.com/api-v2/") == "https://ru.yougile.com"
    assert normalize_base_url("https://yougile.example.com") == "https://yougile.example.com"
