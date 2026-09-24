from fastmcp import Client

from yougile_mcp import progress, runtime
from yougile_mcp.ratelimit import MemoryRateLimiter
from yougile_mcp.server import build_server

CHAIN = {"Разработка / Сайт": ["Очередь", "В работе", "На проверке", "Готово"]}


class FakeCtx:
    def __init__(self) -> None:
        self.notes: list[tuple[float, str]] = []

    async def report_progress(self, value, total=None, message=None):  # noqa: ANN001
        self.notes.append((value, message))


class BrokenCtx:
    async def report_progress(self, value, total=None, message=None):  # noqa: ANN001
        raise RuntimeError("client went away")


async def test_rate_limit_waits_are_reported():
    ctx = FakeCtx()
    limiter = MemoryRateLimiter(limit=1, window=0.3)
    token = progress.bind(ctx)
    try:
        await limiter.acquire()
        await limiter.acquire()  # waits for the window
    finally:
        progress.reset(token)
    assert ctx.notes and "Жду лимит YouGile" in ctx.notes[0][1]
    assert [v for v, _ in ctx.notes] == sorted({v for v, _ in ctx.notes}), "values only grow"


async def test_progress_never_breaks_the_call():
    token = progress.bind(BrokenCtx())
    try:
        await progress.report("что-то")
    finally:
        progress.reset(token)
    await progress.report("без контекста ничего не происходит")


async def test_workflow_steps_are_reported(make_runtime):
    notes = []

    async def on_progress(value, total, message):  # noqa: ANN001
        notes.append(message)

    rt = make_runtime(workflows=CHAIN)
    runtime.set_default(rt)
    try:
        async with Client(build_server(rt), progress_handler=on_progress) as c:
            await c.call_tool("yougile_move_task", {"task": "ID-1", "column": "Готово"})
    finally:
        runtime.set_default(None)
    steps = [n for n in notes if "шаг" in n]
    assert steps == [
        "ID-1: шаг 1 из 3 — «В работе»",
        "ID-1: шаг 2 из 3 — «На проверке»",
        "ID-1: шаг 3 из 3 — «Готово»",
    ]
