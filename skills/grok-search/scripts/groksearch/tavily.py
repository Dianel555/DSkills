import json
from typing import List, Optional

import httpx

from .config import config
from .http import get_http_client, retry_attempts


def _tavily_unavailable_reason() -> Optional[str]:
    if not config.tavily_enabled:
        return "Tavily integration disabled"
    if not config.tavily_api_key:
        return "TAVILY_API_KEY not configured"
    return None


def _tavily_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.tavily_api_key}",
        "Content-Type": "application/json",
    }


async def _post_tavily_json(endpoint: str, body: dict, request_timeout: Optional[httpx.Timeout] = None) -> dict:
    client = await get_http_client()
    request_kwargs = {"headers": _tavily_headers(), "json": body}
    if request_timeout is not None:
        request_kwargs["timeout"] = request_timeout

    async for attempt in retry_attempts(config):
        with attempt:
            response = await client.post(endpoint, **request_kwargs)
            response.raise_for_status()
            return response.json()
    return {}


async def _call_tavily_search(query: str, max_results: int = 6) -> Optional[List[dict]]:
    if _tavily_unavailable_reason():
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/search"
    body = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_raw_content": False,
        "include_answer": False,
    }
    try:
        data = await _post_tavily_json(endpoint, body)
        results = data.get("results", [])
        if not results:
            return None
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in results
        ]
    except Exception:
        return None


async def _call_tavily_extract(url: str) -> Optional[str]:
    if _tavily_unavailable_reason():
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/extract"
    body = {"urls": [url], "format": "markdown"}
    try:
        data = await _post_tavily_json(endpoint, body)
        results = data.get("results", [])
        if results:
            content = results[0].get("raw_content", "")
            return content if content and content.strip() else None
        return None
    except Exception:
        return None


async def _call_tavily_map(
    url: str,
    instructions: str = "",
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    timeout: int = 150,
) -> str:
    reason = _tavily_unavailable_reason()
    if reason:
        return f"Configuration error: {reason}"
    endpoint = f"{config.tavily_api_url.rstrip('/')}/map"
    body = {"url": url, "max_depth": max_depth, "max_breadth": max_breadth, "limit": limit, "timeout": timeout}
    if instructions:
        body["instructions"] = instructions
    try:
        request_timeout = httpx.Timeout(connect=10.0, read=float(timeout) + 5.0, write=15.0, pool=None)
        data = await _post_tavily_json(endpoint, body, request_timeout)
        return json.dumps(
            {
                "base_url": data.get("base_url", ""),
                "results": data.get("results", []),
                "response_time": data.get("response_time", 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    except httpx.TimeoutException:
        return f"Map timeout: request exceeded {timeout}s"
    except httpx.HTTPStatusError as e:
        return f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"
    except Exception as e:
        return f"Map error: {str(e)}"
