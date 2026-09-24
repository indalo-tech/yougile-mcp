from fastmcp import Client

from yougile_mcp import runtime
from yougile_mcp.budget import fit, size
from yougile_mcp.server import build_server


def test_small_results_pass_untouched():
    result = {"tasks": [{"title": "a"}]}
    assert fit(result, 1000) is result


def test_long_lists_lose_their_tail_and_say_so():
    result = {
        "paging": {"next": True},
        "content": [{"title": f"задача {i}" * 5} for i in range(500)],
    }
    trimmed = fit(result, 5000)
    assert size(trimmed) <= 5000
    shown = len(trimmed["content"])
    assert 1 <= shown < 500 and trimmed["content"][0] == result["content"][0]
    assert trimmed["truncated"]["lists"]["content"] == {"shown": shown, "total": 500}
    assert "offset" in trimmed["truncated"]["hint"]
    assert len(result["content"]) == 500, "the original is not changed"


def test_long_texts_are_shortened_when_lists_are_not_enough():
    result = {"title": "Карточка", "description": "текст " * 5000, "messages": []}
    trimmed = fit(result, 4000)
    assert size(trimmed) <= 4000 and trimmed["title"] == "Карточка"
    assert trimmed["description"].endswith("…[cut]")
    assert trimmed["truncated"]["texts_cut"] == 1


def test_top_level_lists_are_wrapped():
    trimmed = fit([{"id": i, "title": "x" * 50} for i in range(300)], 3000)
    assert trimmed["truncated"]["lists"]["items"]["total"] == 300 and size(trimmed) <= 3000


async def test_tools_apply_the_runtime_limit(make_runtime, fake):
    rt = make_runtime()
    rt.max_response_chars = 700
    runtime.set_default(rt)
    try:
        async with Client(build_server(rt)) as c:
            data = (await c.call_tool("yougile_tasks", {"operation": "list"})).data
    finally:
        runtime.set_default(None)
    assert data["truncated"]["hint"] and size(data) <= 700
