import argparse
import asyncio

from .config import config
from .http import close_http_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groksearch_cli",
        description="GrokSearch CLI - Standalone web search via Grok API",
    )
    parser.add_argument("--api-url", help="Override GROK_API_URL")
    parser.add_argument("--api-key", help="Override GROK_API_KEY")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("web_search", help="Perform web search")
    p_search.add_argument("--query", "-q", required=True, help="Search query")
    p_search.add_argument("--platform", "-p", default="", help="Focus platforms (e.g., 'GitHub,Reddit')")
    p_search.add_argument("--min-results", type=int, default=3, help="Minimum results")
    p_search.add_argument("--max-results", type=int, default=10, help="Maximum results")
    p_search.add_argument(
        "--extra-sources",
        type=int,
        default=0,
        help="Number of additional Tavily results merged into output (requires TAVILY_API_KEY)",
    )
    p_search.add_argument("--raw", action="store_true", help="Output raw response without JSON parsing")

    p_fetch = subparsers.add_parser("web_fetch", help="Fetch webpage content")
    p_fetch.add_argument("--url", "-u", required=True, help="URL to fetch")
    p_fetch.add_argument("--out", "-o", help="Output file path")
    p_fetch.add_argument("--via", choices=["grok", "tavily"], default="grok", help="Fetch backend (default: grok)")

    p_map = subparsers.add_parser("web_map", help="Map a website's structure (Tavily)")
    p_map.add_argument("--url", "-u", required=True, help="Root URL to map")
    p_map.add_argument("--instructions", default="", help="Natural language filter for crawler")
    p_map.add_argument("--max-depth", type=int, default=1, help="Max traversal depth (1-5)")
    p_map.add_argument("--max-breadth", type=int, default=20, help="Max links per page")
    p_map.add_argument("--limit", type=int, default=50, help="Total link limit")
    p_map.add_argument("--timeout", type=int, default=150, help="Operation timeout (seconds)")

    p_crawl = subparsers.add_parser("web_crawl", help="Crawl a website's pages (Tavily)")
    p_crawl.add_argument("--url", "-u", required=True, help="Root URL to crawl")
    p_crawl.add_argument("--instructions", default="", help="Natural language filter for crawler")
    p_crawl.add_argument(
        "--max-depth", type=int, default=None, help="Max crawl depth (default: TAVILY_CRAWL_MAX_DEPTH)"
    )
    p_crawl.add_argument(
        "--max-breadth", type=int, default=None, help="Max links per page (default: TAVILY_CRAWL_MAX_BREADTH)"
    )
    p_crawl.add_argument("--limit", type=int, default=None, help="Total page limit (default: TAVILY_CRAWL_LIMIT)")
    p_crawl.add_argument("--timeout", type=int, default=None, help="Operation timeout (default: TAVILY_CRAWL_TIMEOUT)")
    p_crawl.add_argument("--select-paths", default=None, help="Comma-separated path regexes to include")
    p_crawl.add_argument("--exclude-paths", default=None, help="Comma-separated path regexes to exclude")

    p_research = subparsers.add_parser("web_research", help="Run a cited research task (Tavily, async)")
    p_research.add_argument("--input", "-i", required=True, help="Research question or task")
    p_research.add_argument(
        "--model", default=None, help="Research model: mini|pro|auto (default: TAVILY_RESEARCH_MODEL)"
    )
    p_research.add_argument(
        "--output-length", default=None, help="short|standard|long (default: TAVILY_RESEARCH_OUTPUT_LENGTH)"
    )
    p_research.add_argument("--citation-format", default=None, help="numbered|mla|apa|chicago")
    p_research.add_argument(
        "--output-schema",
        default=None,
        help="Path to a JSON Schema file for structured output (default: TAVILY_RESEARCH_OUTPUT_SCHEMA)",
    )

    p_config = subparsers.add_parser("get_config_info", help="Show configuration and test connection")
    p_config.add_argument("--no-test", action="store_true", help="Skip connection test")

    p_model = subparsers.add_parser("switch_model", help="Switch Grok model")
    p_model.add_argument("--model", "-m", required=True, help="Model ID to switch to")

    p_toggle = subparsers.add_parser("toggle_builtin_tools", help="Toggle built-in WebSearch/WebFetch")
    p_toggle.add_argument("--action", "-a", default="status", help="Action: on/off/status")
    p_toggle.add_argument("--root", "-r", help="Project root path (default: auto-detect via .git)")

    return parser


async def run_command(args, commands: dict):
    try:
        await commands[args.command](args)
    finally:
        await close_http_client()


def parse_and_run(commands: dict) -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.api_url or args.api_key:
        config.set_overrides(args.api_url, args.api_key)

    asyncio.run(run_command(args, commands))
