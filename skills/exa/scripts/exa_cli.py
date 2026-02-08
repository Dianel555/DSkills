#!/usr/bin/env python3
"""Exa Search CLI - Standalone command-line interface for Exa semantic search."""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
    from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
    from tenacity.wait import wait_base, wait_random_exponential
except ImportError:
    print("Error: Required packages not installed. Run: pip install httpx tenacity", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# .env File Support
# ============================================================================

def load_dotenv(env_path: Optional[Path] = None) -> bool:
    search_paths = []
    if env_path:
        search_paths.append(env_path)
    else:
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
                            if (value.startswith('"') and value.endswith('"')) or \
                               (value.startswith("'") and value.endswith("'")):
                                value = value[1:-1]
                            if key and key not in os.environ:
                                os.environ[key] = value
                return True
            except IOError:
                continue
    return False


load_dotenv()


# ============================================================================
# Configuration
# ============================================================================

class Config:
    _instance = None
    _DEFAULT_API_URL = "https://api.exa.ai"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._override_url = None
            cls._instance._override_key = None
        return cls._instance

    def set_overrides(self, api_url: Optional[str], api_key: Optional[str]):
        self._override_url = api_url
        self._override_key = api_key

    @property
    def debug_enabled(self) -> bool:
        return os.getenv("EXA_DEBUG", "false").lower() in ("true", "1", "yes")

    @property
    def exa_api_url(self) -> str:
        if self._override_url:
            return self._override_url.rstrip('/')
        return os.getenv("EXA_API_URL", self._DEFAULT_API_URL).rstrip('/')

    @property
    def exa_api_key(self) -> str:
        if self._override_key:
            return self._override_key
        key = os.getenv("EXA_API_KEY")
        if not key:
            raise ValueError("EXA_API_KEY not configured. Set environment variable or use --api-key")
        return key

    @staticmethod
    def _mask_api_key(key: str) -> str:
        if not key or len(key) <= 8:
            return "***"
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"

    def get_config_info(self) -> dict:
        try:
            api_url = self.exa_api_url
            api_key_raw = self.exa_api_key
            api_key_masked = self._mask_api_key(api_key_raw)
            config_status = "OK"
        except ValueError as e:
            api_url = self.exa_api_url
            api_key_masked = "Not configured"
            config_status = f"Error: {str(e)}"

        return {
            "EXA_API_URL": api_url,
            "EXA_API_KEY": api_key_masked,
            "EXA_DEBUG": self.debug_enabled,
            "config_status": config_status
        }


config = Config()


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
    def __init__(self, multiplier: float = 1, max_wait: int = 30):
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
# Exa Client
# ============================================================================

class ExaClient:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=None)

    async def _request_json(self, method: str, path: str, json_body: Optional[Dict] = None) -> Dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        url = f"{self.api_url}{path}"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=_WaitWithRetryAfter(1, 30),
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

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        body = {"query": query}
        body.update({k: v for k, v in kwargs.items() if v is not None})
        return await self._request_json("POST", "/search", body)

    async def get_contents(self, urls: List[str], **kwargs) -> Dict[str, Any]:
        body = {"urls": urls}
        body.update({k: v for k, v in kwargs.items() if v is not None})
        return await self._request_json("POST", "/contents", body)

    async def get_context(self, query: str, **kwargs) -> Dict[str, Any]:
        body = {"query": query}
        body.update({k: v for k, v in kwargs.items() if v is not None})
        return await self._request_json("POST", "/context", body)

    async def start_research(self, instructions: str, model: str = "exa-research") -> Dict[str, Any]:
        body = {"instructions": instructions, "model": model}
        return await self._request_json("POST", "/research/v0/tasks", body)

    async def check_research(self, task_id: str) -> Dict[str, Any]:
        return await self._request_json("GET", f"/research/v0/tasks/{task_id}")


# ============================================================================
# Output Helpers
# ============================================================================

def output_json(data: Any, out_file: Optional[str] = None):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out_file:
        Path(out_file).write_text(text, encoding='utf-8')
        print(json.dumps({"status": "ok", "file": out_file}))
    else:
        print(text)


def output_error(message: str, code: int = 1):
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


# ============================================================================
# Commands
# ============================================================================

async def cmd_web_search_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {
            "numResults": args.num_results,
            "type": args.type,
            "livecrawl": args.livecrawl,
        }
        if args.context_max_chars:
            kwargs["contents"] = {"text": {"maxCharacters": args.context_max_chars}}
        result = await client.search(args.query, **kwargs)
        output_json(result)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_web_search_advanced_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {
            "numResults": args.num_results,
            "type": args.type,
            "category": args.category,
        }
        if args.include_domains:
            kwargs["includeDomains"] = [d.strip() for d in args.include_domains.split(",")]
        if args.exclude_domains:
            kwargs["excludeDomains"] = [d.strip() for d in args.exclude_domains.split(",")]
        if args.start_date:
            kwargs["startPublishedDate"] = args.start_date
        if args.end_date:
            kwargs["endPublishedDate"] = args.end_date

        contents = {}
        if args.text:
            contents["text"] = {"maxCharacters": args.max_chars} if args.max_chars else True
        if args.highlights:
            contents["highlights"] = True
        if args.summary:
            contents["summary"] = True
        if contents:
            kwargs["contents"] = contents

        result = await client.search(args.query, **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_deep_search_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {"type": "deep"}
        if args.additional_queries:
            kwargs["additionalQueries"] = [q.strip() for q in args.additional_queries.split("|")]
        result = await client.search(args.objective, **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_company_research_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {
            "numResults": args.num_results,
            "type": "keyword",
            "category": "company",
        }
        result = await client.search(args.company, **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_linkedin_search_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {
            "numResults": args.num_results,
            "includeDomains": ["linkedin.com"],
        }
        result = await client.search(args.query, **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_crawling_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {"livecrawl": args.livecrawl}
        if args.max_chars:
            kwargs["text"] = {"maxCharacters": args.max_chars}
        elif args.text:
            kwargs["text"] = True
        if args.highlights:
            kwargs["highlights"] = True
        if args.summary:
            kwargs["summary"] = True
        result = await client.get_contents([args.url], **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_get_code_context_exa(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        kwargs = {}
        if args.tokens_num:
            kwargs["tokensNum"] = max(1000, min(50000, args.tokens_num))
        result = await client.get_context(args.query, **kwargs)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_deep_researcher_start(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        result = await client.start_research(args.instructions, args.model)
        output_json(result)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_deep_researcher_check(args):
    try:
        client = ExaClient(config.exa_api_url, config.exa_api_key)
        result = await client.check_research(args.task_id)
        output_json(result, args.out)
    except ValueError as e:
        output_error(str(e))
    except httpx.HTTPStatusError as e:
        output_error(f"API error: {e.response.status_code} - {e.response.text[:200]}")


async def cmd_get_config_info(args):
    config_info = config.get_config_info()

    if not args.no_test:
        test_result = {"status": "Not tested", "message": ""}
        try:
            client = ExaClient(config.exa_api_url, config.exa_api_key)
            result = await client.search("test", numResults=1)
            test_result["status"] = "OK"
            test_result["message"] = "API connection successful"
        except ValueError as e:
            test_result["status"] = "Error"
            test_result["message"] = str(e)
        except httpx.HTTPStatusError as e:
            test_result["status"] = "Error"
            test_result["message"] = f"HTTP {e.response.status_code}"
        except Exception as e:
            test_result["status"] = "Error"
            test_result["message"] = str(e)
        config_info["connection_test"] = test_result

    output_json(config_info)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="exa_cli",
        description="Exa Search CLI - Semantic search via Exa API"
    )
    parser.add_argument("--api-url", help="Override EXA_API_URL")
    parser.add_argument("--api-key", help="Override EXA_API_KEY")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # web_search_exa
    p = subparsers.add_parser("web_search_exa", help="Semantic web search")
    p.add_argument("--query", "-q", required=True, help="Search query")
    p.add_argument("--num-results", "-n", type=int, default=10, help="Number of results (1-100)")
    p.add_argument("--type", choices=["auto", "keyword", "neural"], default="auto")
    p.add_argument("--livecrawl", choices=["always", "fallback", "never"], default="fallback")
    p.add_argument("--context-max-chars", type=int, help="Max characters for content")

    # web_search_advanced_exa
    p = subparsers.add_parser("web_search_advanced_exa", help="Advanced search with filters")
    p.add_argument("--query", "-q", required=True, help="Search query")
    p.add_argument("--num-results", "-n", type=int, default=10)
    p.add_argument("--type", choices=["auto", "keyword", "neural"], default="auto")
    p.add_argument("--category", help="Category filter")
    p.add_argument("--include-domains", help="Comma-separated domains to include")
    p.add_argument("--exclude-domains", help="Comma-separated domains to exclude")
    p.add_argument("--start-date", help="Start date (ISO 8601)")
    p.add_argument("--end-date", help="End date (ISO 8601)")
    p.add_argument("--max-chars", type=int, help="Max characters for text content")
    p.add_argument("--text", action="store_true", help="Include text content")
    p.add_argument("--highlights", action="store_true", help="Include highlights")
    p.add_argument("--summary", action="store_true", help="Include summary")
    p.add_argument("--out", "-o", help="Output file path")

    # deep_search_exa
    p = subparsers.add_parser("deep_search_exa", help="Deep search with query expansion")
    p.add_argument("--objective", required=True, help="Research objective")
    p.add_argument("--additional-queries", help="Pipe-separated additional queries")
    p.add_argument("--out", "-o", help="Output file path")

    # company_research_exa
    p = subparsers.add_parser("company_research_exa", help="Company research")
    p.add_argument("--company", required=True, help="Company name")
    p.add_argument("--num-results", "-n", type=int, default=10)
    p.add_argument("--out", "-o", help="Output file path")

    # linkedin_search_exa
    p = subparsers.add_parser("linkedin_search_exa", help="LinkedIn profile search")
    p.add_argument("--query", "-q", required=True, help="Search query")
    p.add_argument("--num-results", "-n", type=int, default=10)
    p.add_argument("--out", "-o", help="Output file path")

    # crawling_exa
    p = subparsers.add_parser("crawling_exa", help="Extract content from URL")
    p.add_argument("--url", "-u", required=True, help="URL to crawl")
    p.add_argument("--max-chars", type=int, help="Max characters")
    p.add_argument("--livecrawl", choices=["always", "fallback", "never"], default="fallback")
    p.add_argument("--text", action="store_true", help="Include text")
    p.add_argument("--highlights", action="store_true", help="Include highlights")
    p.add_argument("--summary", action="store_true", help="Include summary")
    p.add_argument("--out", "-o", help="Output file path")

    # get_code_context_exa
    p = subparsers.add_parser("get_code_context_exa", help="Get code context")
    p.add_argument("--query", "-q", required=True, help="Code query")
    p.add_argument("--tokens-num", type=int, help="Token limit (1000-50000)")
    p.add_argument("--out", "-o", help="Output file path")

    # deep_researcher_start
    p = subparsers.add_parser("deep_researcher_start", help="Start AI research task")
    p.add_argument("--instructions", required=True, help="Research instructions")
    p.add_argument("--model", choices=["exa-research", "exa-research-pro"], default="exa-research")

    # deep_researcher_check
    p = subparsers.add_parser("deep_researcher_check", help="Check research task status")
    p.add_argument("--task-id", required=True, help="Task ID")
    p.add_argument("--out", "-o", help="Output file path")

    # get_config_info
    p = subparsers.add_parser("get_config_info", help="Show configuration")
    p.add_argument("--no-test", action="store_true", help="Skip connection test")

    args = parser.parse_args()

    if args.api_url or args.api_key:
        config.set_overrides(args.api_url, args.api_key)

    commands = {
        "web_search_exa": cmd_web_search_exa,
        "web_search_advanced_exa": cmd_web_search_advanced_exa,
        "deep_search_exa": cmd_deep_search_exa,
        "company_research_exa": cmd_company_research_exa,
        "linkedin_search_exa": cmd_linkedin_search_exa,
        "crawling_exa": cmd_crawling_exa,
        "get_code_context_exa": cmd_get_code_context_exa,
        "deep_researcher_start": cmd_deep_researcher_start,
        "deep_researcher_check": cmd_deep_researcher_check,
        "get_config_info": cmd_get_config_info,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
