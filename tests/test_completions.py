import pytest
from fastmcp import Client
from mcp.types import PromptReference

from yougile_mcp import runtime
from yougile_mcp.completions import _matching
from yougile_mcp.server import build_server


@pytest.fixture
def client_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return Client(build_server(rt))

    yield build
    runtime.set_default(None)


async def values(client, prompt, name, typed="", **given):
    ref = PromptReference(type="ref/prompt", name=prompt)
    result = await client.complete(ref, {"name": name, "value": typed}, given or None)
    return result.values


async def test_people_projects_boards_columns(client_for):
    async with client_for() as c:
        assert await values(c, "standup", "person", "ив") == ["Иван Петров"]
        assert (await values(c, "standup", "person"))[0] == "me"
        assert await values(c, "hours_report", "project", "раз") == ["Разработка"]
        assert await values(c, "triage", "board", "сайт") == ["Разработка / Сайт", "Клиенты / Сайт"]
        assert await values(c, "triage", "board", project="Клиенты") == ["Клиенты / Сайт"]
        columns = await values(c, "triage", "column", board="Разработка / Сайт")
        assert columns == ["Очередь", "В работе", "На проверке", "Готово"]
        assert await values(c, "triage", "column", "раб", board="Разработка / Сайт") == ["В работе"]


def test_prefix_matches_come_first():
    found = _matching(["Сайт и Работы", "Работы", "Прочее", "Работы"], "раб")
    assert found.values == ["Работы", "Сайт и Работы"] and found.total == 2


async def test_period_dates_are_offered(client_for):
    async with client_for() as c:
        since = await values(c, "hours_report", "since")
        until = await values(c, "hours_report", "until")
    assert len(since) == 4 and all(len(d) == 10 for d in since) and until


async def test_projects_outside_the_allowlist_are_not_offered(client_for):
    async with client_for(projects=["Разработка"]) as c:
        assert await values(c, "triage", "project") == ["Разработка"]
        assert await values(c, "triage", "board") == ["Разработка / Сайт"]


async def test_hosted_servers_resolve_the_runtime(make_runtime):
    rt = make_runtime()

    async def resolve():
        return rt

    async with Client(build_server(resolve_runtime=resolve)) as c:
        assert await values(c, "standup", "person", "анна") == ["Анна Смирнова"]
    async with Client(build_server()) as c:
        assert await values(c, "standup", "person") == [], "no runtime: no suggestions"
