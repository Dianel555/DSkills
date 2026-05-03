"""argparse routing for exa_cli with global options + 4 subcommands."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .commands import (
    cmd_get_config_info,
    cmd_web_fetch_exa,
    cmd_web_search_advanced_exa,
    cmd_web_search_exa,
)
from .config import Config, load_dotenv


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-url", help="Override EXA_API_URL")
    parser.add_argument("--api-key", help="Override EXA_API_KEY")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to stderr (sets EXA_DEBUG=true)")
    parser.add_argument("--max-retry-wait", type=int, default=None,
                        help="Cap (seconds) for single retry wait and exponential backoff "
                             "(default: 60, env: EXA_MAX_RETRY_WAIT)")


def _num_results_in_range(value: str) -> int:
    n = int(value)
    if n < 1 or n > 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return n


def _positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return n


def _build_search_parser(sub) -> None:
    p = sub.add_parser("web_search_exa", help="Semantic web search (highlights always on)")
    p.add_argument("--query", "-q", required=True, help="Search query (may embed category:<type>)")
    p.add_argument("--num-results", "-n", type=_num_results_in_range, default=10,
                   help="Number of results 1-100 (default: 10)")


def _build_fetch_parser(sub) -> None:
    p = sub.add_parser("web_fetch_exa", help="Batch URL extraction via /contents")
    p.add_argument("--urls", action="append", required=True,
                   help="URL to fetch (repeat flag for multiple URLs)")
    p.add_argument("--max-chars", type=_positive_int, default=3000,
                   help="Max characters per page (default: 3000)")
    p.add_argument("--out", "-o", help="Write JSON to file instead of stdout")


def _build_advanced_parser(sub) -> None:
    p = sub.add_parser("web_search_advanced_exa", help="Advanced search with filters")
    p.add_argument("--query", "-q", required=True, help="Search query")
    p.add_argument("--type", choices=["auto", "fast", "instant"], default="auto",
                   help="Search type (default: auto)")
    p.add_argument("--category", help="Category filter")
    p.add_argument("--num-results", "-n", type=_num_results_in_range, default=10)
    p.add_argument("--include-domains", action="append", default=None,
                   help="Domain to include (repeat flag for multiple)")
    p.add_argument("--exclude-domains", action="append", default=None,
                   help="Domain to exclude (repeat flag for multiple)")
    p.add_argument("--include-text", action="append", default=None,
                   help="Required text snippet (repeat flag for multiple)")
    p.add_argument("--exclude-text", action="append", default=None,
                   help="Excluded text snippet (repeat flag for multiple)")
    p.add_argument("--start-date", help="ISO 8601 start date (publishedDate)")
    p.add_argument("--end-date", help="ISO 8601 end date (publishedDate)")
    p.add_argument("--max-age-hours", type=int, help="Max content age in hours")
    p.add_argument("--text", action="store_true", help="Include text content")
    p.add_argument("--highlights", action="store_true", help="Include highlights")
    p.add_argument("--summary", action="store_true", help="Include summary")
    p.add_argument("--max-chars", type=_positive_int,
                   help="Max characters for text (only effective with --text)")
    p.add_argument("--out", "-o", help="Write JSON to file instead of stdout")


def _build_config_info_parser(sub) -> None:
    p = sub.add_parser("get_config_info", help="Show config + optional connectivity probe")
    p.add_argument("--no-test", action="store_true", help="Skip connectivity probe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exa_cli",
        description="Exa Search CLI — semantic search via Exa API",
    )
    _add_global_options(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    _build_search_parser(sub)
    _build_fetch_parser(sub)
    _build_advanced_parser(sub)
    _build_config_info_parser(sub)
    return parser


COMMAND_DISPATCH = {
    "web_search_exa": cmd_web_search_exa,
    "web_fetch_exa": cmd_web_fetch_exa,
    "web_search_advanced_exa": cmd_web_search_advanced_exa,
    "get_config_info": cmd_get_config_info,
}


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    if args.debug:
        os.environ["EXA_DEBUG"] = "true"

    cfg = Config()
    cfg.set_overrides(
        api_url=args.api_url,
        api_key=args.api_key,
        max_retry_wait=args.max_retry_wait,
    )

    handler = COMMAND_DISPATCH[args.command]
    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
