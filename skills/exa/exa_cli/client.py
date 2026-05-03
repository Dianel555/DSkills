"""HTTP client with retry + Retry-After cap for Exa API."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_base, wait_random_exponential

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return False


def _debug_log(event: dict) -> None:
    """Emit a single JSON line to stderr; never includes auth values."""
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr)


class _WaitWithRetryAfter(wait_base):
    """tenacity wait that prefers `Retry-After` on 429, capped to `max_wait`."""

    def __init__(self, max_wait: int, debug: bool = False):
        self._max_wait = max_wait
        self._base_wait = wait_random_exponential(multiplier=1, max=max_wait)
        self._debug = debug

    def __call__(self, retry_state) -> float:
        wait_seconds = self._base_wait(retry_state)
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                parsed = self._parse_retry_after(exc.response)
                if parsed is not None:
                    wait_seconds = min(parsed, float(self._max_wait))
        wait_seconds = min(float(wait_seconds), float(self._max_wait))
        if self._debug:
            _debug_log({
                "event": "retry_wait",
                "attempt": retry_state.attempt_number,
                "wait_seconds": wait_seconds,
                "max_wait": self._max_wait,
            })
        return wait_seconds

    def _parse_retry_after(self, response: httpx.Response) -> Optional[float]:
        header = response.headers.get("Retry-After")
        if not header:
            return None
        header = header.strip()
        if header.isdigit():
            return float(header)
        try:
            retry_dt = parsedate_to_datetime(header)
            if retry_dt.tzinfo is None:
                retry_dt = retry_dt.replace(tzinfo=timezone.utc)
            delay = (retry_dt - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, delay)
        except (TypeError, ValueError):
            return None


class ExaClient:
    """Async client wrapping POST/GET to Exa API with retry + Retry-After cap."""

    def __init__(self, api_url: str, api_key: str, max_retry_wait: int = 60, debug: bool = False):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.max_retry_wait = max_retry_wait
        self.debug = debug
        self.timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=None)

    async def _request_json(
        self, method: str, path: str, json_body: Optional[Dict] = None
    ) -> Dict[str, Any]:
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        url = f"{self.api_url}{path}"
        if self.debug:
            _debug_log({"event": "request", "method": method.upper(), "url": url})
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=_WaitWithRetryAfter(self.max_retry_wait, debug=self.debug),
                retry=retry_if_exception(_is_retryable_exception),
                reraise=True,
            ):
                with attempt:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers)
                    else:
                        response = await client.post(url, headers=headers, json=json_body or {})
                    response.raise_for_status()
                    return response.json()

    async def search(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request_json("POST", "/search", body)

    async def get_contents(self, ids: List[str], extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Upstream payload field is `ids`, not `urls` (see webFetch.ts:64).
        body: Dict[str, Any] = {"ids": ids}
        if extras:
            body.update(extras)
        return await self._request_json("POST", "/contents", body)
