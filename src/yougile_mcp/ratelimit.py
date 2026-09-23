"""Rate limiting for the YouGile API: 50 requests per minute per company, shared by everyone.

``SqliteRateLimiter`` coordinates all local processes (every Claude session spawns its own
stdio server) through one SQLite file; ``MemoryRateLimiter`` is the in-process fallback.
A hosted deployment can plug in its own limiter (e.g. Redis keyed by company id).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 45  # headroom below YouGile's 50/min for people using the web UI meanwhile
WINDOW = 60.0
MAX_SLEEP = 5.0


class RateLimiter(Protocol):
    async def acquire(self) -> None:
        """Wait until one more request fits into the window, then account for it."""

    async def penalize(self, seconds: float) -> None:
        """Block every caller for ``seconds`` (after the API answered 429)."""


class NoopRateLimiter:
    async def acquire(self) -> None:
        return None

    async def penalize(self, seconds: float) -> None:
        return None


class MemoryRateLimiter:
    """Sliding window within one process."""

    def __init__(self, limit: int = DEFAULT_LIMIT, window: float = WINDOW) -> None:
        self.limit, self.window = limit, window
        self._hits: deque[float] = deque()
        self._blocked_until = 0.0
        self._lock = asyncio.Lock()

    def _wait_time(self, now: float) -> float:
        while self._hits and self._hits[0] <= now - self.window:
            self._hits.popleft()
        if self._blocked_until > now:
            return self._blocked_until - now
        if len(self._hits) < self.limit:
            self._hits.append(now)
            return 0.0
        return self._hits[0] + self.window - now + 0.05

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                wait = self._wait_time(time.time())
            if wait <= 0:
                return
            await asyncio.sleep(min(wait, MAX_SLEEP))

    async def penalize(self, seconds: float) -> None:
        async with self._lock:
            self._blocked_until = max(self._blocked_until, time.time() + seconds)


class SqliteRateLimiter:
    """Sliding window shared across processes via a SQLite file; ``bucket`` separates companies."""

    def __init__(
        self, path: Path, bucket: str, limit: int = DEFAULT_LIMIT, window: float = WINDOW
    ) -> None:
        self.path, self.bucket, self.limit, self.window = path, bucket, limit, window
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS hits (bucket TEXT NOT NULL, ts REAL NOT NULL)")
            con.execute("CREATE INDEX IF NOT EXISTS hits_bucket_ts ON hits (bucket, ts)")
            con.execute(
                "CREATE TABLE IF NOT EXISTS blocks (bucket TEXT PRIMARY KEY, until REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def _try_acquire(self) -> float:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            now = time.time()
            con.execute(
                "DELETE FROM hits WHERE bucket = ? AND ts <= ?", (self.bucket, now - self.window)
            )
            row = con.execute(
                "SELECT until FROM blocks WHERE bucket = ?", (self.bucket,)
            ).fetchone()
            if row and row[0] > now:
                con.execute("COMMIT")
                return row[0] - now
            count, oldest = con.execute(
                "SELECT COUNT(*), MIN(ts) FROM hits WHERE bucket = ?", (self.bucket,)
            ).fetchone()
            if count < self.limit:
                con.execute("INSERT INTO hits (bucket, ts) VALUES (?, ?)", (self.bucket, now))
                con.execute("COMMIT")
                return 0.0
            con.execute("COMMIT")
            return oldest + self.window - now + 0.05
        finally:
            con.close()

    def _penalize(self, seconds: float) -> None:
        con = self._connect()
        try:
            until = time.time() + seconds
            con.execute(
                "INSERT INTO blocks (bucket, until) VALUES (?, ?) "
                "ON CONFLICT(bucket) DO UPDATE SET until = MAX(until, excluded.until)",
                (self.bucket, until),
            )
        finally:
            con.close()

    async def acquire(self) -> None:
        while True:
            wait = await asyncio.to_thread(self._try_acquire)
            if wait <= 0:
                return
            await asyncio.sleep(min(wait, MAX_SLEEP))

    async def penalize(self, seconds: float) -> None:
        await asyncio.to_thread(self._penalize, seconds)


def local_rate_limiter(state_dir: Path, bucket: str, limit: int = DEFAULT_LIMIT) -> RateLimiter:
    """Cross-process limiter for local use; falls back to in-process if SQLite is unusable."""
    if limit <= 0:
        return NoopRateLimiter()
    try:
        return SqliteRateLimiter(state_dir / "ratelimit.sqlite3", bucket, limit)
    except (OSError, sqlite3.Error) as exc:
        log.warning("shared rate limiter unavailable (%s); limiting this process only", exc)
        return MemoryRateLimiter(limit)
