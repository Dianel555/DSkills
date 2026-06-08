"""Agent Wiki CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from agent_wiki import __version__
from agent_wiki import batch
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

    plan = sub.add_parser("plan")
    plan.add_argument("--batch-size", type=int, default=batch.DEFAULT_BATCH_SIZE, help="Documents per ingest round")
    add_vault(plan)
    plan.set_defaults(func=commands.cmd_plan)

    batch_done = sub.add_parser("batch-done")
    batch_done.add_argument("--batch", type=int, required=True, help="Batch id to mark complete")
    add_vault(batch_done)
    batch_done.set_defaults(func=commands.cmd_batch_done)

    extract_authors = sub.add_parser("extract-authors")
    add_vault(extract_authors)
    extract_authors.set_defaults(func=commands.cmd_extract_authors)

    aggregate_authors = sub.add_parser("aggregate-authors")
    add_vault(aggregate_authors)
    aggregate_authors.set_defaults(func=commands.cmd_aggregate_authors)

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

    save_session = sub.add_parser("save-session")
    save_session.add_argument("name")
    add_vault(save_session)
    save_session.set_defaults(func=commands.cmd_save_session)

    save_report = sub.add_parser("save-report")
    save_report.add_argument("name")
    add_vault(save_report)
    save_report.set_defaults(func=commands.cmd_save_report)

    status = sub.add_parser("status")
    add_vault(status)
    status.set_defaults(func=commands.cmd_status)

    index = sub.add_parser("index")
    add_vault(index)
    index.set_defaults(func=commands.cmd_index)

    normalize_source_type = sub.add_parser("normalize-source-type")
    add_vault(normalize_source_type)
    normalize_source_type.set_defaults(func=commands.cmd_normalize_source_type)

    gen_base = sub.add_parser("gen-base")
    gen_base.add_argument("--name", default="sources", help="Master table base filename (without .base)")
    add_vault(gen_base)
    gen_base.set_defaults(func=commands.cmd_gen_base)

    gen_canvas = sub.add_parser("gen-canvas")
    scope = gen_canvas.add_mutually_exclusive_group(required=True)
    scope.add_argument("--topic", help="Topic page name (one canvas)")
    scope.add_argument("--all", action="store_true", help="One canvas per topic")
    add_vault(gen_canvas)
    gen_canvas.set_defaults(func=commands.cmd_gen_canvas)

    gen_home = sub.add_parser("gen-home")
    gen_home.add_argument("--cards", choices=["auto", "on", "off"], default="auto",
                          help="Workspace cards: auto-detect Dataview (default), force dataviewjs (on), or static list (off)")
    gen_home.add_argument("--no-rest", action="store_true",
                          help="Always write index.md directly (skip the Obsidian Local REST API)")
    add_vault(gen_home)
    gen_home.set_defaults(func=commands.cmd_gen_home)
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
