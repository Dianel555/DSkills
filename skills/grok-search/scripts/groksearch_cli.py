#!/usr/bin/env python3
"""GrokSearch CLI - Standalone command-line interface for Grok web search."""

import asyncio

from groksearch.cli import build_parser
from groksearch.config import Config, config
from groksearch.env import load_dotenv
from groksearch.formatting import extract_json, merge_search_results
from groksearch.http import (
    RETRYABLE_STATUS_CODES,
    _WaitWithRetryAfter,
    _is_retryable_exception,
    close_http_client,
    get_http_client,
    retry_attempts,
)
from groksearch.prompts import FETCH_PROMPT, SEARCH_PROMPT
from groksearch.provider import GrokSearchProvider
from groksearch.tavily import (
    _call_tavily_extract as _call_tavily_extract_impl,
    _call_tavily_map as _call_tavily_map_impl,
    _call_tavily_search as _call_tavily_search_impl,
    _tavily_unavailable_reason as _tavily_unavailable_reason_impl,
)
from groksearch.commands import (
    cmd_get_config_info as _cmd_get_config_info_impl,
    cmd_switch_model as _cmd_switch_model_impl,
    cmd_toggle_builtin_tools as _cmd_toggle_builtin_tools_impl,
    cmd_web_fetch as _cmd_web_fetch_impl,
    cmd_web_map as _cmd_web_map_impl,
    cmd_web_search as _cmd_web_search_impl,
)


load_dotenv()


def _sync_internal_modules() -> None:
    import groksearch.commands as commands_module
    import groksearch.http as http_module
    import groksearch.provider as provider_module
    import groksearch.tavily as tavily_module

    http_module.get_http_client = get_http_client
    http_module.close_http_client = close_http_client
    http_module.retry_attempts = retry_attempts

    provider_module.config = config
    provider_module.get_http_client = get_http_client
    provider_module.retry_attempts = retry_attempts

    tavily_module.config = config
    tavily_module.get_http_client = get_http_client
    tavily_module.retry_attempts = retry_attempts
    tavily_module._tavily_unavailable_reason = _tavily_unavailable_reason

    commands_module.config = config
    commands_module.GrokSearchProvider = GrokSearchProvider
    commands_module.merge_search_results = merge_search_results
    commands_module._call_tavily_search = _call_tavily_search
    commands_module._call_tavily_extract = _call_tavily_extract
    commands_module._call_tavily_map = _call_tavily_map
    commands_module._tavily_unavailable_reason = _tavily_unavailable_reason


async def _call_tavily_search(query: str, max_results: int = 6):
    _sync_internal_modules()
    return await _call_tavily_search_impl(query, max_results)


async def _call_tavily_extract(url: str):
    _sync_internal_modules()
    return await _call_tavily_extract_impl(url)


async def _call_tavily_map(url: str, instructions: str = "", max_depth: int = 1,
                           max_breadth: int = 20, limit: int = 50, timeout: int = 150):
    _sync_internal_modules()
    return await _call_tavily_map_impl(url, instructions, max_depth, max_breadth, limit, timeout)


_tavily_unavailable_reason = _tavily_unavailable_reason_impl


async def cmd_web_search(args):
    _sync_internal_modules()
    return await _cmd_web_search_impl(args)


async def cmd_web_fetch(args):
    _sync_internal_modules()
    return await _cmd_web_fetch_impl(args)


async def cmd_web_map(args):
    _sync_internal_modules()
    return await _cmd_web_map_impl(args)


async def cmd_get_config_info(args):
    _sync_internal_modules()
    return await _cmd_get_config_info_impl(args)


async def cmd_switch_model(args):
    _sync_internal_modules()
    return await _cmd_switch_model_impl(args)


async def cmd_toggle_builtin_tools(args):
    _sync_internal_modules()
    return await _cmd_toggle_builtin_tools_impl(args)


async def _run_command(args):
    commands = {
        "web_search": cmd_web_search,
        "web_fetch": cmd_web_fetch,
        "web_map": cmd_web_map,
        "get_config_info": cmd_get_config_info,
        "switch_model": cmd_switch_model,
        "toggle_builtin_tools": cmd_toggle_builtin_tools,
    }
    try:
        await commands[args.command](args)
    finally:
        await close_http_client()


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.api_url or args.api_key:
        config.set_overrides(args.api_url, args.api_key)

    asyncio.run(_run_command(args))


__all__ = [
    "Config",
    "FETCH_PROMPT",
    "GrokSearchProvider",
    "RETRYABLE_STATUS_CODES",
    "SEARCH_PROMPT",
    "_WaitWithRetryAfter",
    "_call_tavily_extract",
    "_call_tavily_map",
    "_call_tavily_search",
    "_is_retryable_exception",
    "_tavily_unavailable_reason",
    "build_parser",
    "cmd_get_config_info",
    "cmd_switch_model",
    "cmd_toggle_builtin_tools",
    "cmd_web_fetch",
    "cmd_web_map",
    "cmd_web_search",
    "close_http_client",
    "config",
    "extract_json",
    "get_http_client",
    "load_dotenv",
    "main",
    "merge_search_results",
    "retry_attempts",
]


if __name__ == "__main__":
    main()
