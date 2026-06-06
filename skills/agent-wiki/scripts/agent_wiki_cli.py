"""Agent Wiki CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from agent_wiki import __version__
from agent_wiki import commands


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_wiki")
    parser.add_argument("--version", action="version", version=f"agent-wiki {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_vault(p: argparse.ArgumentParser) -> None:
        p.add_argument("--vault", help="Obsidian vault root path")

    init = sub.add_parser("init")
    add_vault(init)
    init.set_defaults(func=commands.cmd_init)

    scan = sub.add_parser("scan")
    add_vault(scan)
    scan.set_defaults(func=commands.cmd_scan)

    cache_get = sub.add_parser("cache-get")
    cache_get.add_argument("path")
    add_vault(cache_get)
    cache_get.set_defaults(func=commands.cmd_cache_get)

    cache_put = sub.add_parser("cache-put")
    cache_put.add_argument("path")
    cache_put.add_argument("--topics", default="")
    add_vault(cache_put)
    cache_put.set_defaults(func=commands.cmd_cache_put)

    cleanup = sub.add_parser("cleanup")
    add_vault(cleanup)
    cleanup.set_defaults(func=commands.cmd_cleanup)

    status = sub.add_parser("status")
    add_vault(status)
    status.set_defaults(func=commands.cmd_status)

    gen_base = sub.add_parser("gen-base")
    gen_base.add_argument("--name", default="sources", help="Master table base filename (without .base)")
    add_vault(gen_base)
    gen_base.set_defaults(func=commands.cmd_gen_base)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
