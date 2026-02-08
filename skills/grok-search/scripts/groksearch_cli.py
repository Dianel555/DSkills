#!/usr/bin/env python3
"""GrokSearch CLI - Standalone command-line interface for Grok web search."""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Optional

try:
    import httpx
    from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random_exponential
    from tenacity.wait import wait_base
except ImportError:
    print("Error: Required packages not installed. Run: pip install httpx tenacity", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# .env File Support
# ============================================================================

def load_dotenv(env_path: Optional[Path] = None) -> bool:
    """Load environment variables from .env file."""
    search_paths = []
    if env_path:
        search_paths.append(env_path)
    else:
        # Search in current directory and script directory
        search_paths.append(Path.cwd() / ".env")
        search_paths.append(Path(__file__).parent / ".env")
        search_paths.append(Path(__file__).parent.parent / ".env")

    for path in search_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, _, value = line.partition('=')
                            key = key.strip()
                            value = value.strip()
                            # Remove quotes if present
                            if (value.startswith('"') and value.endswith('"')) or \
                               (value.startswith("'") and value.endswith("'")):
                                value = value[1:-1]
                            # Only set if not already in environment
                            if key and key not in os.environ:
                                os.environ[key] = value
                return True
            except IOError:
                continue
    return False


# Load .env on module import
load_dotenv()


# ============================================================================
# Configuration
# ============================================================================

class Config:
    _instance = None
    _DEFAULT_MODEL = "grok-4-fast"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config_file = None
            cls._instance._cached_model = None
            cls._instance._override_url = None
            cls._instance._override_key = None
        return cls._instance

    @property
    def config_file(self) -> Path:
        if self._config_file is None:
            config_dir = Path.home() / ".config" / "grok-search"
            config_dir.mkdir(parents=True, exist_ok=True)
            self._config_file = config_dir / "config.json"
        return self._config_file

    def _load_config_file(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_config_file(self, config_data: dict) -> None:
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

    def set_overrides(self, api_url: Optional[str], api_key: Optional[str]):
        self._override_url = api_url
        self._override_key = api_key

    @property
    def debug_enabled(self) -> bool:
        return os.getenv("GROK_DEBUG", "false").lower() in ("true", "1", "yes")

    @property
    def grok_api_url(self) -> str:
        if self._override_url:
            return self._override_url
        url = os.getenv("GROK_API_URL")
        if not url:
            raise ValueError("GROK_API_URL not configured. Set environment variable or use --api-url")
        return url.rstrip('/')

    @property
    def grok_api_key(self) -> str:
        if self._override_key:
            return self._override_key
        key = os.getenv("GROK_API_KEY")
        if not key:
            raise ValueError("GROK_API_KEY not configured. Set environment variable or use --api-key")
        return key

    @property
    def grok_model(self) -> str:
        if self._cached_model is not None:
            return self._cached_model
        config_data = self._load_config_file()
        file_model = config_data.get("model")
        if file_model:
            self._cached_model = file_model
            return file_model
        self._cached_model = self._DEFAULT_MODEL
        return self._DEFAULT_MODEL

    def set_model(self, model: str) -> str:
        previous = self.grok_model
        config_data = self._load_config_file()
        config_data["model"] = model
        self._save_config_file(config_data)
        self._cached_model = model
        return previous

    @staticmethod
    def _mask_api_key(key: str) -> str:
        if not key or len(key) <= 8:
            return "***"
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"

    def get_config_info(self) -> dict:
        try:
            api_url = self.grok_api_url
            api_key_raw = self.grok_api_key
            api_key_masked = self._mask_api_key(api_key_raw)
            config_status = "✅ Configuration Complete"
        except ValueError as e:
            api_url = "Not configured"
            api_key_masked = "Not configured"
            config_status = f"❌ Error: {str(e)}"

        return {
            "GROK_API_URL": api_url,
            "GROK_API_KEY": api_key_masked,
            "GROK_MODEL": self.grok_model,
            "GROK_DEBUG": self.debug_enabled,
            "config_status": config_status
        }


config = Config()


# ============================================================================
# Prompts
# ============================================================================

SEARCH_PROMPT = """# Role: Search Assistant

Return search results as a JSON array. Each result must have exactly these fields:
- "title": string, result title
- "url": string, valid URL
- "description": string, 20-50 word summary

Output ONLY valid JSON array, no markdown, no explanation.

Example:
[
  {"title": "Example", "url": "https://example.com", "description": "Brief description"}
]
"""

FETCH_PROMPT = """# Role: Web Content Fetcher

Fetch the webpage content and convert to structured Markdown:
- Preserve all headings, paragraphs, lists, tables, code blocks
- Include metadata header: source URL, title, fetch timestamp
- Do NOT summarize - return complete content
- Use UTF-8 encoding
"""


# ============================================================================
# Retry Strategy
# ============================================================================

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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


# ============================================================================
# Connection Pool
# ============================================================================

_http_client: Optional[httpx.AsyncClient] = None
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=15.0, pool=None)


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
    return _http_client


async def close_http_client():
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


# ============================================================================
# Grok Provider
# ============================================================================

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
        "当前", "现在", "今天", "最新", "最近"
    ]
    query_lower = query.lower()
    return any(kw in query_lower or kw in query for kw in keywords)


class GrokSearchProvider:
    def __init__(self, api_url: str, api_key: str, model: str):
        self.api_url = api_url.rstrip('/')
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
        """Execute request: try non-streaming first, fallback to streaming on failure."""
        try:
            return await self._execute_non_stream(payload)
        except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
            if config.debug_enabled:
                print(f"[DEBUG] Non-streaming failed: {e}, falling back to streaming", file=sys.stderr)
            return await self._execute_stream(payload)

    async def _execute_non_stream(self, payload: dict) -> str:
        """Non-streaming request (preferred, faster for short responses)."""
        payload_copy = {**payload, "stream": False}
        client = await get_http_client()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=_WaitWithRetryAfter(1, 8),
            retry=retry_if_exception(_is_retryable_exception),
            reraise=True,
        ):
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
        """Streaming request (fallback for large responses)."""
        payload_copy = {**payload, "stream": True}
        client = await get_http_client()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=_WaitWithRetryAfter(1, 8),
            retry=retry_if_exception(_is_retryable_exception),
            reraise=True,
        ):
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


# ============================================================================
# JSON Extraction
# ============================================================================

def extract_json(text: str) -> str:
    """Extract JSON from text, handling markdown code blocks."""
    # Try to extract from markdown code block
    match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if match:
        text = match.group(1).strip()

    # Try to parse as JSON
    try:
        data = json.loads(text)
        # Standardize field names
        if isinstance(data, list):
            standardized = []
            for item in data:
                if isinstance(item, dict):
                    standardized.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", item.get("link", "")),
                        "description": item.get("description", item.get("content", item.get("snippet", item.get("summary", ""))))
                    })
            return json.dumps(standardized, ensure_ascii=False, indent=2)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse JSON", "raw": text[:500]}, ensure_ascii=False, indent=2)


# ============================================================================
# Commands
# ============================================================================

async def cmd_web_search(args):
    try:
        provider = GrokSearchProvider(config.grok_api_url, config.grok_api_key, config.grok_model)
        result = await provider.search(args.query, args.platform, args.min_results, args.max_results)
        if args.raw:
            print(result)
        else:
            print(extract_json(result))
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": f"API error: {e.response.status_code}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


async def cmd_web_fetch(args):
    try:
        provider = GrokSearchProvider(config.grok_api_url, config.grok_api_key, config.grok_model)
        result = await provider.fetch(args.url)
        if args.out:
            Path(args.out).write_text(result, encoding='utf-8')
            print(f"Content saved to {args.out}")
        else:
            print(result)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code}", file=sys.stderr)
        sys.exit(1)


async def cmd_get_config_info(args):
    config_info = config.get_config_info()

    if not args.no_test:
        test_result = {"status": "Not tested", "message": "", "response_time_ms": 0}
        try:
            api_url = config.grok_api_url
            api_key = config.grok_api_key
            models_url = f"{api_url}/models"

            start_time = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                )
                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    test_result["status"] = "✅ Connection Successful"
                    test_result["response_time_ms"] = round(response_time, 2)
                    try:
                        models_data = response.json()
                        if "data" in models_data:
                            model_count = len(models_data["data"])
                            test_result["message"] = f"Retrieved {model_count} models"
                            test_result["available_models"] = [m.get("id") for m in models_data["data"] if isinstance(m, dict)]
                    except:
                        pass
                else:
                    test_result["status"] = "⚠️ Connection Issue"
                    test_result["message"] = f"HTTP {response.status_code}"

        except httpx.TimeoutException:
            test_result["status"] = "❌ Connection Timeout"
            test_result["message"] = "Request timed out (10s)"
        except Exception as e:
            test_result["status"] = "❌ Connection Failed"
            test_result["message"] = str(e)

        config_info["connection_test"] = test_result

    print(json.dumps(config_info, ensure_ascii=False, indent=2))


async def cmd_switch_model(args):
    try:
        previous = config.set_model(args.model)
        result = {
            "status": "✅ Success",
            "previous_model": previous,
            "current_model": args.model,
            "config_file": str(config.config_file)
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "❌ Failed", "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


async def cmd_toggle_builtin_tools(args):
    # Find project root
    if args.root:
        root = Path(args.root)
        if not root.exists():
            print(json.dumps({"error": f"Specified root does not exist: {args.root}"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        root = Path.cwd()
        while root != root.parent and not (root / ".git").exists():
            root = root.parent
        if not (root / ".git").exists():
            print(json.dumps({
                "error": "No .git directory found. Use --root to specify project root.",
                "hint": "Run this command from within a git repository or specify --root PATH"
            }, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)

    settings_path = root / ".claude" / "settings.json"
    tools = ["WebFetch", "WebSearch"]

    # Load or initialize
    if settings_path.exists():
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
    else:
        settings = {"permissions": {"deny": []}}

    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    blocked = all(t in deny for t in tools)

    # Execute action
    action = args.action.lower()
    if action in ["on", "enable"]:
        for t in tools:
            if t not in deny:
                deny.append(t)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        msg = "Built-in tools disabled"
        blocked = True
    elif action in ["off", "disable"]:
        deny[:] = [t for t in deny if t not in tools]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        msg = "Built-in tools enabled"
        blocked = False
    else:
        msg = f"Built-in tools currently {'disabled' if blocked else 'enabled'}"

    print(json.dumps({
        "blocked": blocked,
        "deny_list": deny,
        "file": str(settings_path),
        "message": msg
    }, ensure_ascii=False, indent=2))


# ============================================================================
# Main
# ============================================================================

async def _run_command(args):
    """Run command with proper cleanup."""
    commands = {
        "web_search": cmd_web_search,
        "web_fetch": cmd_web_fetch,
        "get_config_info": cmd_get_config_info,
        "switch_model": cmd_switch_model,
        "toggle_builtin_tools": cmd_toggle_builtin_tools,
    }
    try:
        await commands[args.command](args)
    finally:
        await close_http_client()


def main():
    parser = argparse.ArgumentParser(
        prog="groksearch_cli",
        description="GrokSearch CLI - Standalone web search via Grok API"
    )
    parser.add_argument("--api-url", help="Override GROK_API_URL")
    parser.add_argument("--api-key", help="Override GROK_API_KEY")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # web_search
    p_search = subparsers.add_parser("web_search", help="Perform web search")
    p_search.add_argument("--query", "-q", required=True, help="Search query")
    p_search.add_argument("--platform", "-p", default="", help="Focus platforms (e.g., 'GitHub,Reddit')")
    p_search.add_argument("--min-results", type=int, default=3, help="Minimum results")
    p_search.add_argument("--max-results", type=int, default=10, help="Maximum results")
    p_search.add_argument("--raw", action="store_true", help="Output raw response without JSON parsing")

    # web_fetch
    p_fetch = subparsers.add_parser("web_fetch", help="Fetch webpage content")
    p_fetch.add_argument("--url", "-u", required=True, help="URL to fetch")
    p_fetch.add_argument("--out", "-o", help="Output file path")

    # get_config_info
    p_config = subparsers.add_parser("get_config_info", help="Show configuration and test connection")
    p_config.add_argument("--no-test", action="store_true", help="Skip connection test")

    # switch_model
    p_model = subparsers.add_parser("switch_model", help="Switch Grok model")
    p_model.add_argument("--model", "-m", required=True, help="Model ID to switch to")

    # toggle_builtin_tools
    p_toggle = subparsers.add_parser("toggle_builtin_tools", help="Toggle built-in WebSearch/WebFetch")
    p_toggle.add_argument("--action", "-a", default="status", help="Action: on/off/status")
    p_toggle.add_argument("--root", "-r", help="Project root path (default: auto-detect via .git)")

    args = parser.parse_args()

    # Apply overrides
    if args.api_url or args.api_key:
        config.set_overrides(args.api_url, args.api_key)

    asyncio.run(_run_command(args))


if __name__ == "__main__":
    main()
