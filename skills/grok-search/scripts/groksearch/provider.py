import json
import sys
from datetime import datetime, timezone

import httpx

from .config import config
from .http import get_http_client, retry_attempts
from .prompts import FETCH_PROMPT, SEARCH_PROMPT


def _get_local_time_info() -> str:
    try:
        local_tz = datetime.now().astimezone().tzinfo
        local_now = datetime.now(local_tz)
    except Exception:
        local_now = datetime.now(timezone.utc)

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return (
        f"[Current Time Context]\n"
        f"- Date: {local_now.strftime('%Y-%m-%d')} ({weekdays[local_now.weekday()]})\n"
        f"- Time: {local_now.strftime('%H:%M:%S')}\n"
    )


def _needs_time_context(query: str) -> bool:
    keywords = [
        "current", "now", "today", "tomorrow", "yesterday",
        "this week", "last week", "next week",
        "latest", "recent", "recently", "up-to-date",
        "当前", "现在", "今天", "最新", "最近",
    ]
    query_lower = query.lower()
    return any(kw in query_lower or kw in query for kw in keywords)


class GrokSearchProvider:
    def __init__(self, api_url: str, api_key: str, model: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def search(self, query: str, platform: str = "", min_results: int = 3, max_results: int = 10) -> str:
        platform_prompt = f"\n\nFocus on platforms: {platform}" if platform else ""
        return_prompt = f"\n\nReturn {min_results}-{max_results} results as JSON array."
        time_context = _get_local_time_info() + "\n" if _needs_time_context(query) else ""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SEARCH_PROMPT},
                {"role": "user", "content": time_context + query + platform_prompt + return_prompt},
            ],
        }
        return await self._execute(payload)

    async def fetch(self, url: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": FETCH_PROMPT},
                {"role": "user", "content": f"{url}\n\nFetch and return structured Markdown."},
            ],
        }
        return await self._execute(payload)

    async def _execute(self, payload: dict) -> str:
        try:
            return await self._execute_non_stream(payload)
        except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
            if config.debug_enabled:
                print(f"[DEBUG] Non-streaming failed: {e}, falling back to streaming", file=sys.stderr)
            return await self._execute_stream(payload)

    async def _execute_non_stream(self, payload: dict) -> str:
        payload_copy = {**payload, "stream": False}
        client = await get_http_client()

        async for attempt in retry_attempts(config):
            with attempt:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers=self._headers,
                    json=payload_copy,
                )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""

    async def _execute_stream(self, payload: dict) -> str:
        payload_copy = {**payload, "stream": True}
        client = await get_http_client()

        async for attempt in retry_attempts(config):
            with attempt:
                async with client.stream(
                    "POST",
                    f"{self.api_url}/chat/completions",
                    headers=self._headers,
                    json=payload_copy,
                ) as response:
                    response.raise_for_status()
                    return await self._parse_streaming_response(response)

    async def _parse_streaming_response(self, response) -> str:
        content = ""
        full_body_buffer = []

        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                continue
            full_body_buffer.append(line)

            if line.startswith("data:"):
                if line in ("data: [DONE]", "data:[DONE]"):
                    continue
                try:
                    json_str = line[5:].lstrip()
                    data = json.loads(json_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if "content" in delta:
                            content += delta["content"]
                except (json.JSONDecodeError, IndexError):
                    continue

        if not content and full_body_buffer:
            try:
                full_text = "".join(full_body_buffer)
                data = json.loads(full_text)
                if "choices" in data and data["choices"]:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "")
            except json.JSONDecodeError:
                pass

        return content
