import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

from .config import config
from .http import RETRYABLE_STATUS_CODES, get_http_client, retry_attempts


def _split_csv(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _tavily_unavailable_reason() -> str | None:
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


def _status_message(action: str, status: int, body: str) -> str:
    if status == 401:
        return "ERROR: TAVILY_API_KEY invalid or missing"
    if status == 429:
        return "ERROR: Tavily quota exceeded (rate limit or usage cap)"
    if status == 432:
        return "ERROR: Tavily account suspended or payment required"
    if status == 400:
        return f"ERROR: Tavily rejected {action} parameters: {body[:200]}"
    return f"ERROR: Tavily {action} HTTP {status}: {body[:200]}"


def _report_terminal_failure(action: str, exc: Exception) -> None:
    """Report a failure that terminated Tavily execution.

    Only annotate retry exhaustion when the failure was actually retryable — 401/403/400/432
    are attempted exactly once, so claiming "after N attempts" there would be a false report.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        msg = _status_message(action, status, exc.response.text)
        if status in RETRYABLE_STATUS_CODES:
            msg = f"{msg} (after {config.retry_max_attempts} attempts)"
        print(msg, file=sys.stderr)
    else:
        print(
            f"ERROR: Tavily {action} failed after {config.retry_max_attempts} attempts: {exc}",
            file=sys.stderr,
        )


def _report_retry(retry_state) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    delay = retry_state.next_action.sleep if retry_state.next_action else 0
    print(
        f"WARNING: Tavily attempt {retry_state.attempt_number} failed ({exc}); retrying in {delay:.1f}s",
        file=sys.stderr,
    )


async def _post_tavily_json(endpoint: str, body: dict, request_timeout: httpx.Timeout | None = None) -> dict:
    client = await get_http_client()
    request_kwargs = {"headers": _tavily_headers(), "json": body}
    if request_timeout is not None:
        request_kwargs["timeout"] = request_timeout

    # retry_attempts uses reraise=True, so the loop either returns or raises.
    async for attempt in retry_attempts(config, before_sleep=_report_retry):
        with attempt:
            response = await client.post(endpoint, **request_kwargs)
            response.raise_for_status()
            return response.json()


async def _call_tavily_search(query: str, max_results: int = 6) -> list[dict] | None:
    if _tavily_unavailable_reason():
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/search"
    body = {
        "query": query,
        "max_results": max_results,
        "search_depth": config.tavily_search_depth,
        "chunks_per_source": config.tavily_chunks_per_source,
        "include_raw_content": False,
        "include_answer": config.tavily_include_answer,
    }
    # Optional filters: omitted entirely when unset so the API defaults apply.
    for key, value in (
        ("topic", config.tavily_topic),
        ("time_range", config.tavily_time_range),
        ("include_domains", config.tavily_include_domains),
        ("exclude_domains", config.tavily_exclude_domains),
        ("include_usage", config.tavily_include_usage),
    ):
        if value:
            body[key] = value
    # include_domains_mode requires include_domains; sending it alone is a 400.
    if config.tavily_include_domains:
        body["include_domains_mode"] = config.tavily_include_domains_mode
    try:
        data = await _post_tavily_json(endpoint, body)
        results = data.get("results", [])
        # Lift usage out even when there are no results, so credits spent on an empty
        # search are not silently dropped.
        out = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in results
        ]
        # Surfaced as a sibling key so merge_search_results (which treats this as a result
        # list) can lift it out without mistaking it for a result.
        if data.get("usage"):
            out.append({"usage": data["usage"]})
        return out or None
    except httpx.HTTPStatusError as e:
        _report_terminal_failure("search", e)
        return None
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        _report_terminal_failure("search", e)
        return None


async def _call_tavily_extract(url: str) -> str | None:
    if _tavily_unavailable_reason():
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/extract"
    body = {
        "urls": [url],
        "format": "markdown",
        "extract_depth": config.tavily_extract_depth,
        "timeout": config.tavily_extract_timeout,
    }
    try:
        # Tavily's own `timeout` (max 60s) reports a clean per-URL failure; give the client
        # headroom beyond it so Tavily's diagnosable error wins over an opaque read timeout.
        request_timeout = httpx.Timeout(connect=10.0, read=config.tavily_extract_timeout + 10.0, write=15.0, pool=None)
        data = await _post_tavily_json(endpoint, body, request_timeout)
        results = data.get("results", [])
        failed = data.get("failed_results", [])
        if failed:
            print(f"WARNING: Tavily extract failed for {len(failed)} URL(s): {failed}", file=sys.stderr)
        if results:
            content = results[0].get("raw_content", "")
            return content if content and content.strip() else None
        return None
    except httpx.HTTPStatusError as e:
        _report_terminal_failure("extract", e)
        return None
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        _report_terminal_failure("extract", e)
        return None


async def _call_tavily_crawl(
    url: str,
    instructions: str = "",
    max_depth: int | None = None,
    max_breadth: int | None = None,
    limit: int | None = None,
    timeout: int | None = None,
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> str:
    reason = _tavily_unavailable_reason()
    if reason:
        return f"Configuration error: {reason}"
    endpoint = f"{config.tavily_api_url.rstrip('/')}/crawl"
    timeout = config.tavily_crawl_timeout if timeout is None else timeout
    body = {
        "url": url,
        "max_depth": config.tavily_crawl_max_depth if max_depth is None else max_depth,
        "max_breadth": config.tavily_crawl_max_breadth if max_breadth is None else max_breadth,
        "limit": config.tavily_crawl_limit if limit is None else limit,
        "allow_external": config.tavily_crawl_allow_external,
        "extract_depth": config.tavily_extract_depth,
        "format": "markdown",
        "timeout": timeout,
    }
    if config.tavily_include_usage:
        body["include_usage"] = True
    if instructions:
        body["instructions"] = instructions
    for key, value in (
        ("select_paths", _split_csv(config.tavily_crawl_select_paths if select_paths is None else select_paths)),
        ("exclude_paths", _split_csv(config.tavily_crawl_exclude_paths if exclude_paths is None else exclude_paths)),
    ):
        if value:
            body[key] = value
    try:
        # `timeout` here bounds the crawl server-side, so the client must wait longer.
        request_timeout = httpx.Timeout(connect=10.0, read=float(timeout) + 10.0, write=15.0, pool=None)
        data = await _post_tavily_json(endpoint, body, request_timeout)
        payload = {
            "base_url": data.get("base_url", ""),
            "results": data.get("results", []),
            "response_time": data.get("response_time", 0),
        }
        if data.get("usage"):
            payload["usage"] = data["usage"]
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except httpx.TimeoutException:
        return f"Crawl timeout: request exceeded {timeout}s after {config.retry_max_attempts} attempts"
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        retry_note = f" (after {config.retry_max_attempts} attempts)" if status in RETRYABLE_STATUS_CODES else ""
        return f"HTTP error: {status} - {e.response.text[:200]}{retry_note}"
    except Exception as e:
        return f"Crawl error: {str(e)}"


_SCHEMA_TYPES = ("object", "string", "integer", "number", "array")


def _validate_output_schema(schema: dict) -> str | None:
    """Return an error message if `schema` would be rejected, else None.

    The API requires a 'properties' object; each property needs a type (one of
    object/string/integer/number/array) and a description. 'items' is required when
    type is array, 'properties' when type is object.
    """
    if not isinstance(schema, dict):
        return "output_schema must be a JSON object"
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return "output_schema must include a non-empty 'properties' object"

    def check(name: str, spec: dict, depth: int = 0) -> str | None:
        if not isinstance(spec, dict):
            return f"property '{name}' must be an object"
        ptype = spec.get("type")
        if ptype not in _SCHEMA_TYPES:
            return f"property '{name}' needs a type in {_SCHEMA_TYPES} (got {ptype!r})"
        if not spec.get("description"):
            return f"property '{name}' needs a description"
        if ptype == "array":
            items = spec.get("items")
            if not isinstance(items, dict) or "type" not in items:
                return f"property '{name}' of type array needs 'items' with a type"
        if ptype == "object":
            nested = spec.get("properties")
            if not isinstance(nested, dict) or not nested:
                return f"property '{name}' of type object needs non-empty 'properties'"
            if depth < 8:
                for child, child_spec in nested.items():
                    err = check(child, child_spec, depth + 1)
                    if err:
                        return err
        return None

    for name, spec in props.items():
        err = check(name, spec)
        if err:
            return err
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not required:
            return "'required' must be a non-empty array when present"
        unknown = [r for r in required if r not in props]
        if unknown:
            return f"'required' names not present in properties: {unknown}"
    return None


def _load_output_schema() -> dict | None:
    """Read TAVILY_RESEARCH_OUTPUT_SCHEMA (a JSON file path). Raises ValueError if invalid."""
    path = config.tavily_research_output_schema
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            schema = json.load(f)
    except OSError as e:
        raise ValueError(f"Cannot read TAVILY_RESEARCH_OUTPUT_SCHEMA file {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"TAVILY_RESEARCH_OUTPUT_SCHEMA file {path} is not valid JSON: {e}") from e
    error = _validate_output_schema(schema)
    if error:
        raise ValueError(f"Invalid TAVILY_RESEARCH_OUTPUT_SCHEMA ({path}): {error}")
    return schema


async def _call_tavily_research(
    input_text: str,
    model: str | None = None,
    output_length: str | None = None,
    citation_format: str | None = None,
    output_schema: dict | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    reason = _tavily_unavailable_reason()
    if reason:
        return f"Configuration error: {reason}"
    if output_schema is None:
        try:
            output_schema = _load_output_schema()
        except ValueError as e:
            return f"Configuration error: {e}"
    elif isinstance(output_schema, str):
        # CLI passes a file path; resolve and validate it the same way.
        try:
            schema = json.loads(Path(output_schema).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return f"Configuration error: cannot read output_schema file {output_schema}: {e}"
        if error := _validate_output_schema(schema):
            return f"Configuration error: invalid output_schema ({output_schema}): {error}"
        output_schema = schema
    elif error := _validate_output_schema(output_schema):
        return f"Configuration error: invalid output_schema: {error}"
    base = config.tavily_api_url.rstrip("/")
    body = {
        "input": input_text,
        "model": config.tavily_research_model if model is None else model,
        "citation_format": config.tavily_research_citation_format if citation_format is None else citation_format,
        "output_length": config.tavily_research_output_length if output_length is None else output_length,
    }
    if output_schema is not None:
        body["output_schema"] = output_schema
    for key, value in (
        ("include_domains", _split_csv(config.tavily_include_domains if include_domains is None else include_domains)),
        ("exclude_domains", _split_csv(config.tavily_exclude_domains if exclude_domains is None else exclude_domains)),
    ):
        if value:
            body[key] = value

    try:
        created = await _post_tavily_json(f"{base}/research", body)
    except httpx.HTTPStatusError as e:
        return f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        return f"Research submit failed: {e}"

    request_id = created.get("request_id")
    if not request_id:
        return json.dumps({"error": "Research task rejected", "response": created}, ensure_ascii=False, indent=2)

    # Research is asynchronous: poll until completed/failed or the budget runs out.
    deadline = time.monotonic() + config.tavily_research_timeout
    client = await get_http_client()
    while True:
        await asyncio.sleep(min(config.tavily_research_poll_interval, max(0.0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            return json.dumps(
                {
                    "request_id": request_id,
                    "status": "timeout",
                    "message": f"Not finished within {config.tavily_research_timeout}s",
                },
                ensure_ascii=False,
                indent=2,
            )
        params = {"include_usage": "true"} if config.tavily_include_usage else None
        try:
            response = await client.get(
                f"{base}/research/{request_id}",
                headers=_tavily_headers(),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return json.dumps(
                {
                    "request_id": request_id,
                    "status": "poll_error",
                    "error": f"HTTP {e.response.status_code} - {e.response.text[:200]}",
                },
                ensure_ascii=False,
                indent=2,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            # The task was created and may still be consuming credits; the caller needs
            # request_id to re-fetch it, so poll failures keep the JSON contract too.
            return json.dumps(
                {
                    "request_id": request_id,
                    "status": "poll_error",
                    "error": f"{e}",
                },
                ensure_ascii=False,
                indent=2,
            )

        data = response.json()
        status = data.get("status")
        if status in ("completed", "failed"):
            if config.tavily_include_usage and not data.get("usage"):
                print("WARNING: Tavily research usage unavailable for this request", file=sys.stderr)
            return json.dumps(data, ensure_ascii=False, indent=2)


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
    body = {
        "url": url,
        "max_depth": max_depth,
        "max_breadth": max_breadth,
        "limit": limit,
        "timeout": timeout,
    }
    if config.tavily_include_usage:
        body["include_usage"] = True
    if instructions:
        body["instructions"] = instructions
    try:
        request_timeout = httpx.Timeout(connect=10.0, read=float(timeout) + 5.0, write=15.0, pool=None)
        data = await _post_tavily_json(endpoint, body, request_timeout)
        payload = {
            "base_url": data.get("base_url", ""),
            "results": data.get("results", []),
            "response_time": data.get("response_time", 0),
        }
        if data.get("usage"):
            payload["usage"] = data["usage"]
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except httpx.TimeoutException:
        return f"Map timeout: request exceeded {timeout}s after {config.retry_max_attempts} attempts"
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        retry_note = f" (after {config.retry_max_attempts} attempts)" if status in RETRYABLE_STATUS_CODES else ""
        return f"HTTP error: {status} - {e.response.text[:200]}{retry_note}"
    except Exception as e:
        return f"Map error: {str(e)}"
