from concurrent.futures import Future
from types import SimpleNamespace

import httpx
import pytest

from groksearch.http import _WaitWithRetryAfter


@pytest.mark.parametrize("header", ["999999999", "Wed, 01 Jan 2099 00:00:00 GMT"])
def test_retry_after_respects_configured_wait_limit(header):
    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(429, headers={"Retry-After": header}, request=request)
    outcome = Future()
    outcome.set_exception(httpx.HTTPStatusError("limited", request=request, response=response))
    outcome.failed = True
    wait = _WaitWithRetryAfter(multiplier=1, max_wait=5)
    assert 0 <= wait(SimpleNamespace(outcome=outcome)) <= 5
