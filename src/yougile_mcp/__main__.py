"""Command line: run the MCP server, issue an API key, or check the setup."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from typing import Any

from . import __version__, runtime
from .client import YouGileClient, YouGileError
from .config import ConfigError, Settings, load_workspace_config

log = logging.getLogger("yougile_mcp")


def _setup_logging() -> None:
    # stdout carries the MCP protocol over stdio, so logs must go to stderr.
    level = os.environ.get("YOUGILE_MCP_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        stream=sys.stderr, level=level, format="%(levelname)s %(name)s: %(message)s"
    )


def _load() -> tuple[Settings, Any]:
    try:
        settings = Settings.from_env()
        config = load_workspace_config()
    except ConfigError as exc:
        sys.exit(f"yougile-mcp: {exc}")
    for warning in config.warnings:
        log.warning(warning)
    return settings, config


def cmd_serve(args: argparse.Namespace) -> None:
    from .server import build_server

    settings, config = _load()
    if not settings.api_key:
        sys.exit("yougile-mcp: set YOUGILE_API_KEY (run `yougile-mcp setup` to issue a key)")
    rt = runtime.build_local_runtime(settings, config)
    runtime.set_default(rt)
    server = build_server(rt)
    if args.transport == "stdio":
        server.run(transport="stdio", show_banner=False)
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port, show_banner=False)


# ---------- setup ----------


def _choose(items: list[dict], label: Any) -> dict:
    if len(items) == 1:
        return items[0]
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label(item)}")
    while True:
        answer = input(f"Choose 1-{len(items)}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(items):
            return items[int(answer) - 1]


async def _issue_key(base_url: str) -> str:
    login = input("YouGile login (email): ").strip()
    password = getpass.getpass("YouGile password (not stored): ")
    creds = {"login": login, "password": password}
    async with YouGileClient(None, base_url) as client:
        companies = (await client.request("POST", "/auth/companies", json=creds, auth=False)) or {}
        items = companies.get("content", []) if isinstance(companies, dict) else []
        if not items:
            raise YouGileError(0, "this account has no companies")
        company = _choose(
            items, lambda c: f"{c.get('name')}{' (admin)' if c.get('isAdmin') else ''}"
        )
        body = {**creds, "companyId": company["id"]}
        keys = await client.request("POST", "/auth/keys/get", json=body, auth=False) or []
        live = sorted(
            (k for k in keys if not k.get("deleted") and k.get("companyId") == company["id"]),
            key=lambda k: k.get("timestamp") or 0,
        )
        if live:
            print(
                f"\nThis account already has {len(live)} key(s) for {company.get('name')} "
                "(YouGile allows at most 30 per account)."
            )
            if (
                input("Reuse the newest one instead of creating another? [Y/n] ").strip().lower()
                != "n"
            ):
                return live[-1]["key"]
        created = await client.request("POST", "/auth/keys", json=body, auth=False)
        return created["key"]


def cmd_setup(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    try:
        key = asyncio.run(_issue_key(settings.base_url))
    except YouGileError as exc:
        sys.exit(f"yougile-mcp setup: {exc}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("\ncancelled")
    base = (
        ""
        if settings.base_url == "https://ru.yougile.com"
        else f" -e YOUGILE_BASE_URL={settings.base_url}"
    )
    print("\nYour API key (keep it secret, it acts with your YouGile rights):\n")
    print(f"  {key}\n")
    print("Claude Code (all projects of this user):\n")
    print(
        f"  claude mcp add yougile --scope user -e YOUGILE_API_KEY={key}{base} -- uvx yougile-mcp\n"
    )
    print("Claude Desktop / other clients (mcpServers entry):\n")
    print(
        '  "yougile": {"command": "uvx", "args": ["yougile-mcp"], '
        f'"env": {{"YOUGILE_API_KEY": "{key}"}}}}\n'
    )


# ---------- check ----------


async def _check(settings: Settings, config: Any) -> None:
    rt = runtime.build_local_runtime(settings, config)
    async with rt.client:
        me = await rt.client.request("GET", "/users/me")
        company = await rt.client.request("GET", "/companies")
        structure = await rt.directory.structure()
    admin = " (admin)" if me.get("isAdmin") else ""
    print(f"Version:  yougile-mcp {__version__}")
    print(f"User:     {me.get('realName') or '-'} <{me.get('email')}>{admin}")
    print(f"Company:  {company.get('title')} ({company.get('id')})")
    print(
        f"Visible:  {len(structure.projects)} projects, {len(structure.boards)} boards, "
        f"{len(structure.columns)} columns"
    )
    print(f"Policy:   {rt.policy.summary()}")
    print(f"Timezone: {config.timezone}")
    print(f"Config:   {', '.join(config.sources) or 'none (defaults)'}")
    for warning in config.warnings:
        print(f"Warning:  {warning}")
    print(f"Requests: {rt.client.requests_made} used for this check")


def cmd_check(args: argparse.Namespace) -> None:
    settings, config = _load()
    if not settings.api_key:
        sys.exit("yougile-mcp: YOUGILE_API_KEY is not set")
    try:
        asyncio.run(_check(settings, config))
    except YouGileError as exc:
        sys.exit(f"yougile-mcp check: {exc}")


def main(argv: list[str] | None = None) -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="yougile-mcp", description="MCP server for YouGile")
    parser.add_argument("--version", action="version", version=f"yougile-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the MCP server (default)")
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)
    sub.add_parser("setup", help="issue an API key with your YouGile login").set_defaults(
        func=cmd_setup
    )
    sub.add_parser("check", help="verify the key, company and config").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["serve", *(argv or [])])
    args.func(args)


if __name__ == "__main__":
    main()
