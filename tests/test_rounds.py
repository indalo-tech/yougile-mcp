"""The 2026-07-28 protocol's rounds: a confirmation per project, kept across the reruns."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from yougile_mcp import runtime, smart

ACCEPT = SimpleNamespace(action="accept", content={"value": True})
DECLINE = SimpleNamespace(action="decline", content={})


def modern(responses=None, state=None):
    """Enough of a Context for a client that elicits on the 2026-07-28 protocol."""
    return SimpleNamespace(
        session=SimpleNamespace(client_capabilities=SimpleNamespace(elicitation=object())),
        request_context=SimpleNamespace(protocol_version="2026-07-28"),
        input_responses=responses,
        request_state=state,
    )


@pytest.fixture
def rt_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return rt

    yield build
    runtime.set_default(None)


ARGS = {
    "title": "TD-92 доработка",
    "board": "Разработка / Сайт",
    "column": "Очередь",
    "client_title": "Новая возможность",
    "client_description": "Для клиента",
}


async def test_two_projects_two_confirmations_one_write_each(rt_for, fake):
    rt_for(
        client_copy={"from": "Разработка", "to": "Клиенты"},
        confirm_projects=["Клиенты", "Разработка"],
    )
    before = set(fake.tasks)
    first = await smart.yougile_create_task(**ARGS, ctx=modern())
    assert list(first.input_requests) == ["confirm:Клиенты"]
    second = await smart.yougile_create_task(
        **ARGS, ctx=modern({"confirm:Клиенты": ACCEPT}, first.request_state)
    )
    assert list(second.input_requests) == ["confirm:Разработка"], "a yes for one is not for all"
    assert json.loads(second.request_state)["confirmed"] == ["Клиенты"]
    assert set(fake.tasks) == before, "nothing written while anything is unconfirmed"
    done = await smart.yougile_create_task(
        **ARGS, ctx=modern({"confirm:Разработка": ACCEPT}, second.request_state)
    )
    assert done["client_copy"]["created"] is True
    assert len(set(fake.tasks) - before) == 2, "one internal task and its copy, once"


async def test_a_declined_project_stops_the_call(rt_for, fake):
    rt_for(confirm_projects=["Клиенты"])
    args = {"title": "x", "board": "Клиенты / Сайт", "column": "Очередь"}
    first = await smart.yougile_create_task(**args, ctx=modern())
    result = await smart.yougile_create_task(
        **args, ctx=modern({"confirm:Клиенты": DECLINE}, first.request_state)
    )
    assert result == {"cancelled": True, "reason": "the user did not confirm the write"}
