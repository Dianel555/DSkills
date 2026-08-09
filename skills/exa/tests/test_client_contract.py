from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx

from _support import SKILL_ROOT  # noqa: F401
from exa_cli import client as client_module
from exa_cli.client import ExaClient


class _FakeAsyncClient:
    statuses = []
    requests = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    async def aclose(self):
        self.closed = True

    async def get(self, url, headers=None):
        return self._response("GET", url, headers, None)

    async def post(self, url, headers=None, json=None):
        return self._response("POST", url, headers, json)

    def _response(self, method, url, headers, body):
        self.__class__.requests.append((method, url, headers, body))
        status = self.__class__.statuses.pop(0) if self.__class__.statuses else 200
        request = httpx.Request(method, url)
        return httpx.Response(status, request=request, json={"status": status})


async def _run_search(client):
    if hasattr(client, "__aenter__"):
        async with client:
            return await client.search({"query": "x"})
    return await client.search({"query": "x"})


async def _run_search_and_agent_requests(client):
    async with client:
        await client.search({"query": "x"})
        await client.agent_create({"query": "x", "effort": "low"})
        await client.agent_get("agent_run_header_test")


class ClientContractTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeAsyncClient.statuses = []
        _FakeAsyncClient.requests = []

    def test_bearer_auth_header_never_uses_x_api_key(self) -> None:
        with patch.object(client_module.httpx, "AsyncClient", _FakeAsyncClient):
            result = asyncio.run(_run_search(ExaClient(
                "https://example.test", "top-secret", auth_scheme="bearer"
            )))
        self.assertEqual(result, {"status": 200})
        headers = _FakeAsyncClient.requests[0][2]
        self.assertEqual(headers["Authorization"], "Bearer top-secret")
        self.assertNotIn("x-api-key", headers)

    def test_beta_header_is_scoped_to_agent_requests(self) -> None:
        with patch.object(client_module.httpx, "AsyncClient", _FakeAsyncClient):
            asyncio.run(_run_search_and_agent_requests(ExaClient(
                "https://example.test", "top-secret"
            )))
        search_headers = _FakeAsyncClient.requests[0][2]
        create_headers = _FakeAsyncClient.requests[1][2]
        get_headers = _FakeAsyncClient.requests[2][2]
        self.assertNotIn("Exa-Beta", search_headers)
        self.assertEqual(create_headers["Exa-Beta"], "agent-2026-05-07")
        self.assertEqual(get_headers["Exa-Beta"], "agent-2026-05-07")

    def test_retryable_status_stops_after_four_attempts(self) -> None:
        _FakeAsyncClient.statuses = [503, 503, 503, 503, 200]
        with patch.object(client_module.httpx, "AsyncClient", _FakeAsyncClient), \
             patch.object(client_module._WaitWithRetryAfter, "__call__", return_value=0):
            with self.assertRaises(httpx.HTTPStatusError):
                asyncio.run(_run_search(ExaClient(
                    "https://example.test", "top-secret", max_retry_wait=1
                )))
        self.assertEqual(len(_FakeAsyncClient.requests), 4)


if __name__ == "__main__":
    unittest.main()
