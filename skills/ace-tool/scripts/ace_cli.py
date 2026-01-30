#!/usr/bin/env python3
"""ACE-Tool CLI - Semantic code search and prompt enhancement."""

import argparse
import json
import sys
from pathlib import Path

import httpx

try:
    from .utils import load_env
    from .client import AceToolClient
    from .web_ui import run_interactive_enhance
except ImportError:
    from utils import load_env
    from client import AceToolClient
    from web_ui import run_interactive_enhance

load_env()


def cmd_search_context(args):
    """Handle search_context command."""
    client = AceToolClient(args.api_url, args.token, args.endpoint)
    result = client.search_context(args.project_root, args.query)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_enhance_prompt(args):
    """Handle enhance_prompt command."""
    client = AceToolClient(args.api_url, args.token, args.endpoint)

    history = args.history
    if args.history_file:
        history = Path(args.history_file).read_text(encoding="utf-8")

    if not args.no_interactive:
        result = run_interactive_enhance(
            client, args.prompt, history, args.port,
            auto_open_browser=not args.no_browser
        )
        if result:
            print(json.dumps({"enhanced_prompt": result}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"cancelled": True}), file=sys.stderr)
            sys.exit(1)
    else:
        result = client.enhance_prompt(args.prompt, history, args.project_root)
        print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_get_config(args):
    """Handle get_config command."""
    client = AceToolClient(args.api_url, args.token, args.endpoint)
    result = client.get_config()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="ACE-Tool CLI - Semantic code search and prompt enhancement"
    )
    parser.add_argument("--api-url", help="API base URL")
    parser.add_argument("--token", help="API authentication token")
    parser.add_argument(
        "--endpoint",
        choices=["new", "old", "claude", "openai", "gemini"],
        help="Enhancer endpoint type",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("search_context", help="Search codebase with natural language")
    p_search.add_argument("-p", "--project-root", required=True, help="Project root path")
    p_search.add_argument("-q", "--query", required=True, help="Natural language query")
    p_search.set_defaults(func=cmd_search_context)

    p_enhance = subparsers.add_parser("enhance_prompt", help="Enhance prompt with context")
    p_enhance.add_argument("-p", "--prompt", required=True, help="Original prompt")
    p_enhance.add_argument("-H", "--history", default="", help="Conversation history")
    p_enhance.add_argument("--history-file", help="File containing conversation history")
    p_enhance.add_argument("--project-root", help="Project root path (optional)")
    p_enhance.add_argument("--no-interactive", action="store_true", help="Disable web UI, output JSON directly")
    p_enhance.add_argument("--no-browser", action="store_true", help="Don't auto-open browser, just print URL")
    p_enhance.add_argument("--port", type=int, default=8765, help="Port for interactive web server (default: 8765)")
    p_enhance.set_defaults(func=cmd_enhance_prompt)

    p_config = subparsers.add_parser("get_config", help="Show current configuration")
    p_config.set_defaults(func=cmd_get_config)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": str(e), "status_code": e.response.status_code}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
