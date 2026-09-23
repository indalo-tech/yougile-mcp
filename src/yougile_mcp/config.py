"""Settings from the environment and workspace config from ``.yougile.json`` files.

The API key is read only from the environment and is never accepted from config files.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .client import DEFAULT_BASE_URL, normalize_base_url
from .ratelimit import DEFAULT_LIMIT

Role = Literal["reader", "member", "admin"]
ROLES: tuple[Role, ...] = ("reader", "member", "admin")

REPO_FILE = ".yougile.json"
GLOBAL_FILE = ".yougile-mcp.json"
KNOWN_KEYS = {
    "project",
    "board",
    "role",
    "projects",
    "confirm_projects",
    "deny",
    "workflows",
    "done_columns",
    "instructions",
    "timezone",
}
DEFAULT_TIMEZONE = "Europe/Moscow"


class ConfigError(ValueError):
    pass


def _zone(name: str, source: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"{source}: unknown time zone {name!r} (use e.g. Europe/Moscow)") from exc


def default_state_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "yougile-mcp"


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str = DEFAULT_BASE_URL
    rate_limit: int = DEFAULT_LIMIT
    state_dir: Path = field(default_factory=default_state_dir)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        try:
            rate = int(env.get("YOUGILE_RATE_LIMIT", DEFAULT_LIMIT))
        except ValueError as exc:
            raise ConfigError("YOUGILE_RATE_LIMIT must be an integer") from exc
        state = env.get("YOUGILE_MCP_STATE_DIR")
        return cls(
            api_key=(env.get("YOUGILE_API_KEY") or "").strip() or None,
            base_url=normalize_base_url(env.get("YOUGILE_BASE_URL") or DEFAULT_BASE_URL),
            rate_limit=rate,
            state_dir=Path(state).expanduser() if state else default_state_dir(),
        )


@dataclass
class WorkspaceConfig:
    """Defaults and restrictions for one workspace (a repository or a user)."""

    project: str | None = None
    board: str | None = None
    role: Role = "admin"
    projects: list[str] | None = None  # allowlist of project names or ids; None = all
    confirm_projects: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    workflows: dict[str, list[str]] = field(default_factory=dict)
    # Columns that mean "done" even without the completed flag: a title for every board
    # ("Готово") or one column as "Project / Board / Column".
    done_columns: list[str] = field(default_factory=list)
    instructions: str = ""
    timezone: str = DEFAULT_TIMEZONE
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], source: str = "<dict>") -> WorkspaceConfig:
        cfg = cls()
        cfg.merge(data, source)
        return cfg

    def merge(self, data: Mapping[str, Any], source: str) -> None:
        if not isinstance(data, Mapping):
            raise ConfigError(f"{source}: top level must be a JSON object")
        if any(k.lower() in ("api_key", "apikey", "key", "token") for k in data):
            raise ConfigError(f"{source}: API keys belong in YOUGILE_API_KEY, not in config files")
        for key in data:
            if key not in KNOWN_KEYS and not key.startswith("$"):
                self.warnings.append(f"{source}: unknown key {key!r} ignored")
        if "project" in data:
            self.project = _opt_str(data["project"], "project", source)
        if "board" in data:
            self.board = _opt_str(data["board"], "board", source)
        if "role" in data:
            if data["role"] not in ROLES:
                raise ConfigError(f"{source}: role must be one of {', '.join(ROLES)}")
            self.role = data["role"]
        if "projects" in data:
            self.projects = (
                None
                if data["projects"] is None
                else _str_list(data["projects"], "projects", source)
            )
        if "confirm_projects" in data:
            self.confirm_projects = _str_list(data["confirm_projects"], "confirm_projects", source)
        if "deny" in data:
            self.deny = _str_list(data["deny"], "deny", source)
        if "workflows" in data:
            wf = data["workflows"]
            if not isinstance(wf, Mapping):
                raise ConfigError(f"{source}: workflows must map 'Project / Board' to column lists")
            for board, chain in wf.items():
                self.workflows[str(board)] = _str_list(chain, f"workflows[{board!r}]", source)
        if "done_columns" in data:
            self.done_columns = _str_list(data["done_columns"], "done_columns", source)
        if "instructions" in data:
            text = data["instructions"]
            if isinstance(text, list):
                text = "\n".join(str(t) for t in text)
            self.instructions = str(text or "")
        if "timezone" in data:
            name = _opt_str(data["timezone"], "timezone", source) or DEFAULT_TIMEZONE
            _zone(name, source)
            self.timezone = name
        self.sources.append(source)


def _opt_str(value: Any, name: str, source: str) -> str | None:
    if value is None or isinstance(value, str):
        return value or None
    raise ConfigError(f"{source}: {name} must be a string")


def _str_list(value: Any, name: str, source: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ConfigError(f"{source}: {name} must be a list of strings")


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        return json.loads(path.read_text("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON ({exc})") from exc


def find_repo_config(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / REPO_FILE
        if candidate.is_file():
            return candidate
    return None


def load_workspace_config(
    cwd: Path | None = None, env: Mapping[str, str] | None = None, home: Path | None = None
) -> WorkspaceConfig:
    """Global ``~/.yougile-mcp.json`` first, then the repo ``.yougile.json`` (or YOUGILE_CONFIG)."""
    env = os.environ if env is None else env
    cfg = WorkspaceConfig()
    global_file = (home or Path.home()) / GLOBAL_FILE
    if global_file.is_file():
        cfg.merge(_read_json(global_file), str(global_file))
    explicit = env.get("YOUGILE_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"YOUGILE_CONFIG points to a missing file: {path}")
    else:
        path = find_repo_config((cwd or Path.cwd()).resolve())
    if path is not None and path != global_file:
        cfg.merge(_read_json(path), str(path))
    if tz_name := env.get("YOUGILE_TIMEZONE"):
        _zone(tz_name, "YOUGILE_TIMEZONE")
        cfg.timezone = tz_name
    return cfg
