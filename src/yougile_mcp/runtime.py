"""Per-request runtime: API client, config, policy and structure cache.

Tools read the runtime from a ContextVar, never from shared server state, so a hosted
deployment can bind a different tenant per request without cross-talk. The local stdio
server simply installs one default runtime.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass

from .client import YouGileClient
from .config import Settings, WorkspaceConfig
from .directory import Directory
from .policy import Policy
from .ratelimit import local_rate_limiter


@dataclass
class Runtime:
    client: YouGileClient
    config: WorkspaceConfig
    policy: Policy
    directory: Directory
    allow_local_files: bool = True  # hosted servers set False: no reading of the server's disk
    # Where people change this session's workspace settings (default board, Workflow chains);
    # error messages send them there. A hosted server names its admin page instead.
    settings_hint: str = ".yougile.json"


_current: ContextVar[Runtime | None] = ContextVar("yougile_runtime", default=None)
_default: Runtime | None = None


def set_default(runtime: Runtime | None) -> None:
    global _default
    _default = runtime


def bind(runtime: Runtime) -> Token[Runtime | None]:
    return _current.set(runtime)


def reset(token: Token[Runtime | None]) -> None:
    _current.reset(token)


def current() -> Runtime:
    runtime = _current.get() or _default
    if runtime is None:
        raise RuntimeError("YouGile runtime is not configured")
    return runtime


def key_bucket(api_key: str | None) -> str:
    """Rate-limit bucket for a key without storing the key itself."""
    return hashlib.sha256((api_key or "").encode()).hexdigest()[:16]


def build_local_runtime(settings: Settings, config: WorkspaceConfig) -> Runtime:
    limiter = local_rate_limiter(
        settings.state_dir, key_bucket(settings.api_key), settings.rate_limit
    )
    client = YouGileClient(settings.api_key, settings.base_url, limiter=limiter)
    return Runtime(client, config, Policy.from_config(config), Directory(client))
