"""web_fetch_exa command — batch URL extraction via POST /contents."""

from __future__ import annotations

import httpx

from .client import ExaClient
from .config import Config
from .output import output_error, output_json


async def cmd_web_fetch_exa(args) -> None:
    cfg = Config()
    try:
        async with ExaClient(
            cfg.exa_api_url,
            cfg.exa_api_key,
            max_retry_wait=cfg.max_retry_wait,
            debug=cfg.debug_enabled,
            auth_scheme=cfg.auth_scheme,
        ) as client:
            # Upstream payload field is `ids` (see webFetch.ts:64).
            extras = {"contents": {"text": {"maxCharacters": args.max_chars}}}
            result = await client.get_contents(args.urls, extras=extras)
        output_json(result, args.out)
    except ValueError as exc:
        output_error(str(exc))
    except httpx.HTTPStatusError as exc:
        output_error(
            f"API error: {exc.response.status_code} - {exc.response.text[:200]}"
        )
