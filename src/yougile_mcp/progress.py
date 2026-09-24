"""Progress notes for long tool calls: waiting for YouGile's rate limit, many pages of tasks,
a card walking a Workflow chain.

Any layer can call ``report`` without knowing about MCP; the tool wrapper binds the call's
context. It is best effort: a client that did not ask for progress gets nothing, and a failed
notification never breaks the call.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any

log = logging.getLogger(__name__)


class Reporter:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.step = 0  # MCP wants progress to grow with every notification

    async def report(self, message: str) -> None:
        self.step += 1
        try:
            await self.ctx.report_progress(self.step, None, message)
        except Exception as exc:  # noqa: BLE001 - progress must never break the call
            log.debug("progress notification failed: %s", exc)


_reporter: ContextVar[Reporter | None] = ContextVar("yougile_progress", default=None)


def bind(ctx: Any) -> Token[Reporter | None]:
    return _reporter.set(Reporter(ctx) if ctx is not None else None)


def reset(token: Token[Reporter | None]) -> None:
    _reporter.reset(token)


async def report(message: str) -> None:
    reporter = _reporter.get()
    if reporter is not None:
        await reporter.report(message)


def rate_limit_note(wait: float) -> str:
    return (
        f"Жду лимит YouGile (50 запросов в минуту на компанию): ещё около {max(1, round(wait))} с"
    )
