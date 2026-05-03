"""web_search_exa command — basic semantic search with category extraction."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import httpx

from ..client import ExaClient
from ..config import Config
from ..output import output_error, output_json

# Mirrors upstream webSearch.ts:47 — note the spec restricts to 5 values.
_CATEGORY_RE = re.compile(
    r"\bcategory:(company|research\s*paper|news|personal\s*site|people)\b",
    re.IGNORECASE,
)


def extract_category(query: str) -> Tuple[str, Optional[str]]:
    """Return (cleaned_query, category_or_None) per upstream semantics."""
    match = _CATEGORY_RE.search(query)
    if not match:
        return query, None
    category = match.group(1).lower()
    category = re.sub(r"\s+", " ", category)
    cleaned = query.replace(match.group(0), "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, category


async def cmd_web_search_exa(args) -> None:
    cfg = Config()
    try:
        client = ExaClient(
            cfg.exa_api_url,
            cfg.exa_api_key,
            max_retry_wait=cfg.max_retry_wait,
            debug=cfg.debug_enabled,
        )
        cleaned_query, category = extract_category(args.query)
        body = {
            "query": cleaned_query,
            "numResults": args.num_results,
            "contents": {"highlights": True},
        }
        if category is not None:
            body["category"] = category
        result = await client.search(body)
        output_json(result)
    except ValueError as exc:
        output_error(str(exc))
    except httpx.HTTPStatusError as exc:
        output_error(
            f"API error: {exc.response.status_code} - {exc.response.text[:200]}"
        )
