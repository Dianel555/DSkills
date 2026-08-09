"""Exa Agent request validation and retained-run lifecycle."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from .client import ExaClient, RETRYABLE_STATUS_CODES, RUN_ID_RE
from .config import Config
from .output import output_error, output_json, redact_secret

AGENT_PROVIDERS = (
    "fiber", "financial_datasets", "similarweb", "baselayer",
    "affiliate", "particle", "jinko",
)
AGENT_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "auto")
CREATE_ONLY_FIELDS = (
    "system_prompt", "output_schema", "input_data", "input_exclusion",
    "data_source", "previous_run_id", "effort",
)
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ZDR_LIMITATION = "Standalone agent_run does not support Zero Data Retention streaming."


class AgentCreateUncertainError(RuntimeError):
    pass


def run_id_arg(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise ValueError("run ID must match ^agent_run_[A-Za-z0-9_-]+$")
    return value


def validate_agent_args(args) -> None:
    if bool(args.query) == bool(args.run_id):
        raise ValueError("provide exactly one of --query or --run-id")
    if args.run_id:
        run_id_arg(args.run_id)
        invalid = [name for name in CREATE_ONLY_FIELDS if getattr(args, name)]
        if invalid:
            flags = ", ".join("--" + name.replace("_", "-") for name in invalid)
            raise ValueError(f"resume mode does not accept create-only options: {flags}")
    if args.previous_run_id:
        run_id_arg(args.previous_run_id)
    if args.wait_seconds < 0:
        raise ValueError("--wait-seconds must be a non-negative integer")
    if args.poll_interval <= 0:
        raise ValueError("--poll-interval must be a positive integer")
    providers = args.data_source or []
    if len(providers) > 5:
        raise ValueError("--data-source accepts at most 5 providers")
    if len(set(providers)) != len(providers):
        raise ValueError("--data-source providers must be unique")
    unsupported = [provider for provider in providers if provider not in AGENT_PROVIDERS]
    if unsupported:
        raise ValueError(f"unsupported data source: {unsupported[0]}")


def _read_json(path: str, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON file: {exc}") from exc


def _object_array(path: str, label: str) -> list:
    value = _read_json(path, label)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a JSON array of objects")
    return value


def build_agent_body(args) -> Dict[str, Any]:
    validate_agent_args(args)
    if not args.query:
        raise ValueError("create body requires --query")
    body: Dict[str, Any] = {"query": args.query}
    if args.system_prompt:
        body["systemPrompt"] = args.system_prompt
    if args.output_schema:
        schema = _read_json(args.output_schema, "output schema")
        if not isinstance(schema, dict):
            raise ValueError("output schema must be a top-level JSON object")
        body["outputSchema"] = schema
    input_value: Dict[str, Any] = {}
    if args.input_data:
        input_value["data"] = _object_array(args.input_data, "input data")
    if args.input_exclusion:
        input_value["exclusion"] = _object_array(
            args.input_exclusion, "input exclusion"
        )
    if input_value:
        body["input"] = input_value
    if args.data_source:
        body["dataSources"] = [
            {"provider": provider} for provider in args.data_source
        ]
    if args.previous_run_id:
        body["previousRunId"] = args.previous_run_id
    body["effort"] = args.effort or "low"
    return body


def _resume_command(run_id: str) -> str:
    return f"python scripts/exa_cli.py agent_run --run-id {run_id}"


def _event(name: str, **fields) -> None:
    print(json.dumps({"event": name, **fields}, ensure_ascii=False), file=sys.stderr)


def normalize_agent_result(run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    status = str(payload.get("status", "unknown")).lower()
    if status == "completed":
        result = {
            "success": True, "id": run_id, "status": status,
            "outputReady": True, "output": payload.get("output"),
        }
        for key in ("usage", "costDollars"):
            if key in payload:
                result[key] = payload[key]
        return result
    if status in {"failed", "cancelled"}:
        result = {
            "success": False, "id": run_id, "status": status,
            "outputReady": False,
        }
        if "error" in payload:
            result["error"] = payload["error"]
        return result
    return {
        "success": True,
        "id": run_id,
        "status": "running",
        "outputReady": False,
        "resumeCommand": _resume_command(run_id),
    }


async def run_agent(
    args,
    client: ExaClient,
    *,
    monotonic=time.monotonic,
    sleep=asyncio.sleep,
) -> Dict[str, Any]:
    validate_agent_args(args)
    run_id = args.run_id
    try:
        if args.query:
            try:
                created = await client.agent_create(build_agent_body(args))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in RETRYABLE_STATUS_CODES:
                    raise AgentCreateUncertainError(
                        f"{_http_error_message(exc, getattr(client, 'api_key', ''))}. "
                        "Agent create may have succeeded upstream, but no run ID was "
                        "received; it cannot be safely resumed and was not retried."
                    ) from exc
                raise
            except httpx.RequestError as exc:
                raise AgentCreateUncertainError(
                    "Agent create may have succeeded upstream, but no run ID was "
                    "received; it cannot be safely resumed and was not retried."
                ) from exc
            run_id = created.get("id")
            run_id_arg(run_id or "")
            if args.previous_run_id and run_id == args.previous_run_id:
                raise ValueError("Agent continuation returned the previous run ID")
            _event(
                "agent_run_created", id=run_id,
                resumeCommand=_resume_command(run_id),
            )

        start = monotonic()
        deadline = start + args.wait_seconds
        while True:
            payload = await client.agent_get(run_id)
            status = str(payload.get("status", "unknown")).lower()
            result = normalize_agent_result(run_id, payload)
            if status in TERMINAL_STATUSES:
                return result
            now = monotonic()
            if now >= deadline:
                return result
            await sleep(min(args.poll_interval, deadline - now))
    except (asyncio.CancelledError, KeyboardInterrupt):
        if run_id:
            _event(
                "agent_run_interrupted", id=run_id,
                resumeCommand=_resume_command(run_id),
            )
        else:
            _event(
                "agent_run_interrupted", state="unknown",
                message="The run may exist upstream, but no run ID was received.",
            )
        raise


def _http_error_message(exc: httpx.HTTPStatusError, secret: str = "") -> str:
    text = redact_secret(exc.response.text[:500], secret)
    message = f"API error: {exc.response.status_code} - {text}"
    lowered = text.casefold()
    if any(token in lowered for token in ("zdr", "zero data retention", "streaming")):
        message = f"{message}. {ZDR_LIMITATION}"
    return message


async def cmd_agent_run(args) -> None:
    api_key = ""
    try:
        validate_agent_args(args)
        cfg = Config()
        api_key = cfg.exa_api_key
        async with ExaClient(
            cfg.exa_api_url,
            api_key,
            max_retry_wait=cfg.max_retry_wait,
            debug=cfg.debug_enabled,
            auth_scheme=cfg.auth_scheme,
        ) as client:
            result = await run_agent(args, client)
        result = redact_secret(result, api_key)
        output_json(result, args.out)
        if not result["success"]:
            raise SystemExit(1)
    except AgentCreateUncertainError as exc:
        output_error(str(exc))
    except ValueError as exc:
        output_error(str(exc))
    except httpx.HTTPStatusError as exc:
        output_error(_http_error_message(exc, api_key))
    except httpx.RequestError as exc:
        output_error(redact_secret(f"Network error: {exc}", api_key))
