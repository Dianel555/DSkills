"""get_config_info command — show config + optional connectivity probe."""

from __future__ import annotations

import httpx

from ..client import ExaClient
from ..config import Config
from ..output import output_json


async def cmd_get_config_info(args) -> None:
    cfg = Config()
    info = cfg.get_config_info()

    if not args.no_test:
        test_result = {"status": "Not tested", "message": ""}
        try:
            client = ExaClient(
                cfg.exa_api_url,
                cfg.exa_api_key,
                max_retry_wait=cfg.max_retry_wait,
                debug=cfg.debug_enabled,
            )
            await client.search({"query": "test", "numResults": 1})
            test_result["status"] = "OK"
            test_result["message"] = "API connection successful"
        except ValueError as exc:
            test_result["status"] = "Error"
            test_result["message"] = str(exc)
        except httpx.HTTPStatusError as exc:
            test_result["status"] = "Error"
            test_result["message"] = f"HTTP {exc.response.status_code}"
        except Exception as exc:  # network / timeout / parse
            test_result["status"] = "Error"
            test_result["message"] = str(exc)
        info["connection_test"] = test_result

    output_json(info)
