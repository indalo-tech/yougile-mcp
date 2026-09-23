"""Thin async HTTP client for YouGile REST API v2 with rate limiting and safe retries."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx2

from . import __version__
from .ratelimit import NoopRateLimiter, RateLimiter

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ru.yougile.com"
DEFAULT_429_PAUSE = 10.0
BACKOFF = (1.0, 3.0, 6.0)


class YouGileError(Exception):
    def __init__(self, status: int, message: str, payload: Any = None) -> None:
        super().__init__(f"YouGile API {status}: {message}" if status else message)
        self.status = status
        self.message = message
        self.payload = payload


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url.removesuffix("/api-v2")


def _query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return value


def _error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message"):
            msg = payload.get(key)
            if isinstance(msg, list):
                return "; ".join(str(m) for m in msg)
            if msg:
                return str(msg)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:500]
    return fallback


def _retry_after(resp: httpx2.Response) -> float:
    try:
        return max(1.0, float(resp.headers.get("Retry-After", "")))
    except ValueError:
        return DEFAULT_429_PAUSE


class YouGileClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        *,
        limiter: RateLimiter | None = None,
        timeout: float = 30.0,
        max_attempts: int = 3,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.limiter: RateLimiter = limiter or NoopRateLimiter()
        self.max_attempts = max(1, max_attempts)
        self._api_key = api_key
        self._http = httpx2.AsyncClient(
            base_url=self.base_url + "/api-v2",
            headers={"Accept": "application/json", "User-Agent": f"yougile-mcp/{__version__}"},
            timeout=timeout,
            transport=transport,
        )
        self.requests_made = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> YouGileClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json: Any = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        auth: bool = True,
    ) -> Any:
        method = method.upper()
        headers: dict[str, str] = {}
        if auth:
            if not self._api_key:
                raise YouGileError(0, "YOUGILE_API_KEY is not set")
            headers["Authorization"] = f"Bearer {self._api_key}"
        params = {k: _query_value(v) for k, v in (query or {}).items() if v is not None}
        idempotent = method in ("GET", "PUT", "DELETE") or (
            isinstance(json, dict) and bool(json.get("idempotencyKey"))
        )

        for attempt in range(1, self.max_attempts + 1):
            last = attempt == self.max_attempts
            await self.limiter.acquire()
            started = time.monotonic()
            try:
                resp = await self._http.request(
                    method, path, params=params or None, json=json, files=files, headers=headers
                )
            except httpx2.TransportError as exc:
                # A connect error means nothing reached the server, so any method may retry.
                retryable = idempotent or isinstance(exc, httpx2.ConnectError)
                log.warning("%s %s failed: %s (attempt %d)", method, path, exc, attempt)
                if retryable and not last:
                    await asyncio.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
                    continue
                raise YouGileError(0, f"network error: {exc}") from exc
            finally:
                self.requests_made += 1

            log.info(
                "%s %s -> %d (%.0f ms)",
                method,
                path,
                resp.status_code,
                (time.monotonic() - started) * 1000,
            )
            if resp.status_code == 429:
                # The request was rejected, not executed: safe to repeat for any method.
                await self.limiter.penalize(_retry_after(resp))
                if not last:
                    continue
            elif resp.status_code >= 500 and idempotent and not last:
                await asyncio.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
                continue
            return self._parse(resp)
        raise AssertionError("unreachable")

    @staticmethod
    def _parse(resp: httpx2.Response) -> Any:
        payload: Any
        try:
            payload = resp.json() if resp.content else None
        except ValueError:
            payload = resp.text
        if resp.is_success:
            return payload
        raise YouGileError(
            resp.status_code, _error_message(payload, resp.reason_phrase or "error"), payload
        )
