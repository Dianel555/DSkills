from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx
from tenacity.wait import wait_base
from tenacity import retry_if_exception, stop_after_attempt, wait_random_exponential
from tenacity import AsyncRetrying as _AsyncRetrying


RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=15.0, pool=None)
_http_client: Optional[httpx.AsyncClient] = None


def _is_retryable_exception(exc) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return False


class _WaitWithRetryAfter(wait_base):
    def __init__(self, multiplier: float, max_wait: int):
        self._base_wait = wait_random_exponential(multiplier=multiplier, max=max_wait)

    def __call__(self, retry_state):
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                retry_after = self._parse_retry_after(exc.response)
                if retry_after is not None:
                    return retry_after
        return self._base_wait(retry_state)

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


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


async def close_http_client():
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def retry_attempts(config):
    return _AsyncRetrying(
        stop=stop_after_attempt(config.retry_max_attempts),
        wait=_WaitWithRetryAfter(config.retry_multiplier, config.retry_max_wait),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
