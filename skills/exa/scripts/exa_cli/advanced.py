"""web_search_advanced_exa command — filtered search core subset."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from .client import ExaClient
from .config import Config
from .output import output_error, output_json, output_warning


def _build_payload(args) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "query": args.query,
        "type": args.type,
        "numResults": args.num_results,
    }
    if args.category:
        body["category"] = args.category
    if args.include_domains:
        body["includeDomains"] = list(args.include_domains)
    if args.exclude_domains:
        body["excludeDomains"] = list(args.exclude_domains)
    if args.include_text:
        body["includeText"] = list(args.include_text)
    if args.exclude_text:
        body["excludeText"] = list(args.exclude_text)
    if args.start_date:
        body["startPublishedDate"] = args.start_date
    if args.end_date:
        body["endPublishedDate"] = args.end_date
    if args.max_age_hours is not None:
        body["maxAgeHours"] = args.max_age_hours

    contents: Dict[str, Any] = {}
    if args.text:
        if args.max_chars is not None:
            contents["text"] = {"maxCharacters": args.max_chars}
        else:
            contents["text"] = True
    elif args.max_chars is not None:
        output_warning("--max-chars ignored without --text")
    if args.highlights:
        contents["highlights"] = True
    if args.summary:
        contents["summary"] = True
    if contents:
        body["contents"] = contents
    return body


async def cmd_web_search_advanced_exa(args) -> None:
    cfg = Config()
    try:
        async with ExaClient(
            cfg.exa_api_url,
            cfg.exa_api_key,
            max_retry_wait=cfg.max_retry_wait,
            debug=cfg.debug_enabled,
            auth_scheme=cfg.auth_scheme,
        ) as client:
            body = _build_payload(args)
            result = await client.search(body)
        output_json(result, args.out)
    except ValueError as exc:
        output_error(str(exc))
    except httpx.HTTPStatusError as exc:
        output_error(
            f"API error: {exc.response.status_code} - {exc.response.text[:200]}"
        )
