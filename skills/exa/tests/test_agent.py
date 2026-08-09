from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from _support import SKILL_ROOT  # noqa: F401
from exa_cli import __main__ as main_module
from exa_cli.__main__ import build_parser
from exa_cli.agent import (
    build_agent_body,
    cmd_agent_run,
    normalize_agent_result,
    run_agent,
    validate_agent_args,
)
from exa_cli.client import ExaClient


def agent_args(**overrides):
    values = {
        "query": "Find companies",
        "run_id": None,
        "system_prompt": None,
        "output_schema": None,
        "input_data": None,
        "input_exclusion": None,
        "data_source": None,
        "previous_run_id": None,
        "effort": None,
        "wait_seconds": 0,
        "poll_interval": 4,
        "out": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AgentParserTests(unittest.TestCase):
    def test_agent_parser_modes_defaults_and_bounds(self) -> None:
        parser = build_parser()
        subparsers = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertIn("agent_run", subparsers.choices)
        args = parser.parse_args(["agent_run", "--query", "x"])
        self.assertEqual((args.effort, args.wait_seconds, args.poll_interval),
                         (None, 750, 4))
        for argv in (
            ["agent_run"],
            ["agent_run", "--query", "x", "--run-id", "agent_run_1"],
            ["agent_run", "--run-id", "bad/id"],
            ["agent_run", "--query", "x", "--wait-seconds", "-1"],
            ["agent_run", "--query", "x", "--poll-interval", "0"],
            ["agent_run", "--query", "x", "--data-source", "unknown"],
        ):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    parser.parse_args(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_resume_rejects_create_only_options_before_network(self) -> None:
        for field, value in (
            ("system_prompt", "x"), ("output_schema", "schema.json"),
            ("input_data", "data.json"), ("input_exclusion", "exclude.json"),
            ("data_source", ["fiber"]), ("previous_run_id", "agent_run_old"),
            ("effort", "high"),
        ):
            args = agent_args(query=None, run_id="agent_run_1", **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_agent_args(args)

    def test_provider_duplicates_and_limit_are_rejected(self) -> None:
        for providers in (["fiber", "fiber"], ["fiber"] * 6):
            with self.subTest(providers=providers), self.assertRaises(ValueError):
                validate_agent_args(agent_args(data_source=providers))


class AgentBodyTests(unittest.TestCase):
    def test_utf8_files_map_to_exact_camel_case_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "schema.json"
            data = root / "data.json"
            exclusion = root / "exclusion.json"
            schema.write_text('{"type":"object","title":"公司"}', encoding="utf-8")
            data.write_text('[{"name":"甲"}]', encoding="utf-8")
            exclusion.write_text('[{"name":"乙"}]', encoding="utf-8")
            body = build_agent_body(agent_args(
                system_prompt="Be precise",
                output_schema=str(schema),
                input_data=str(data),
                input_exclusion=str(exclusion),
                data_source=["fiber", "similarweb"],
                previous_run_id="agent_run_old",
                effort="high",
            ))
        self.assertEqual(body, {
            "query": "Find companies",
            "systemPrompt": "Be precise",
            "outputSchema": {"type": "object", "title": "公司"},
            "input": {
                "data": [{"name": "甲"}],
                "exclusion": [{"name": "乙"}],
            },
            "dataSources": [{"provider": "fiber"}, {"provider": "similarweb"}],
            "previousRunId": "agent_run_old",
            "effort": "high",
        })

    def test_invalid_json_shapes_fail_before_client_use(self) -> None:
        invalid_values = ("[]", "null", '"text"')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "value.json"
            for value in invalid_values:
                path.write_text(value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    build_agent_body(agent_args(output_schema=str(path)))
            path.write_text('[{"ok":1}, 2]', encoding="utf-8")
            with self.assertRaises(ValueError):
                build_agent_body(agent_args(input_data=str(path)))


class AgentClientTests(unittest.TestCase):
    def test_create_is_single_shot_and_get_retries_four_times(self) -> None:
        async def no_sleep(_seconds):
            return None

        for failure_status in (408, 429, 500, 502, 503, 504):
            create_calls = []

            async def create_handler(request, status=failure_status):
                create_calls.append(request)
                return httpx.Response(status, request=request, json={"error": "busy"})

            async def create_case():
                client = ExaClient(
                    "https://example.test", "key",
                    transport=httpx.MockTransport(create_handler),
                    retry_sleep=no_sleep,
                )
                async with client:
                    with self.assertRaises(httpx.HTTPStatusError):
                        await client.agent_create({"query": "x"})
                self.assertTrue(client.is_closed)

            with self.subTest(status=failure_status):
                asyncio.run(create_case())
                self.assertEqual(len(create_calls), 1)

        get_calls = []

        async def get_handler(request):
            get_calls.append(request)
            status = 200 if len(get_calls) == 4 else 503
            return httpx.Response(
                status, request=request,
                json={"id": "agent_run_1", "status": "running"},
            )

        async def get_case():
            client = ExaClient(
                "https://example.test", "key",
                transport=httpx.MockTransport(get_handler),
                retry_sleep=no_sleep,
            )
            async with client:
                return await client.agent_get("agent_run_1")

        self.assertEqual(asyncio.run(get_case())["id"], "agent_run_1")
        self.assertEqual(len(get_calls), 4)
        self.assertEqual(get_calls[-1].url.raw_path,
                         b"/agent/runs/agent_run_1")

    def test_one_scoped_client_covers_create_and_poll(self) -> None:
        methods = []

        async def handler(request):
            methods.append(request.method)
            payload = (
                {"id": "agent_run_1"}
                if request.method == "POST"
                else {"id": "agent_run_1", "status": "completed", "output": {}}
            )
            return httpx.Response(200, request=request, json=payload)

        async def exercise():
            client = ExaClient(
                "https://example.test", "key",
                transport=httpx.MockTransport(handler),
            )
            async with client:
                created = await client.agent_create({"query": "x"})
                result = await client.agent_get(created["id"])
            return client, result

        client, result = asyncio.run(exercise())
        self.assertEqual(methods, ["POST", "GET"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(client.is_closed)

    def test_create_network_error_is_not_retried(self) -> None:
        calls = []

        async def handler(request):
            calls.append(request)
            raise httpx.ConnectError("offline", request=request)

        async def exercise():
            async with ExaClient(
                "https://example.test", "key",
                transport=httpx.MockTransport(handler),
            ) as client:
                await client.agent_create({"query": "x"})

        with self.assertRaises(httpx.ConnectError):
            asyncio.run(exercise())
        self.assertEqual(len(calls), 1)


class _FakeAgentClient:
    def __init__(self, create=None, gets=None, create_error=None, get_error=None):
        self.create_response = {"id": "agent_run_new"} if create is None else create
        self.gets = list(gets or [])
        self.create_error = create_error
        self.get_error = get_error
        self.create_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def agent_create(self, body):
        self.create_calls.append(body)
        if self.create_error:
            raise self.create_error
        return self.create_response

    async def agent_get(self, run_id):
        self.get_calls.append(run_id)
        if self.get_error:
            raise self.get_error
        return self.gets.pop(0)


class _Clock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class AgentLifecycleTests(unittest.TestCase):
    def test_main_maps_keyboard_interrupt_to_exit_130(self) -> None:
        args = SimpleNamespace(
            debug=False, api_url=None, api_key=None, max_retry_wait=None,
            auth_scheme=None, command="agent_run",
        )
        parser = SimpleNamespace(parse_args=lambda: args)

        async def interrupted(_args):
            raise KeyboardInterrupt

        with patch.object(main_module, "load_dotenv"), \
             patch.object(main_module, "build_parser", return_value=parser), \
             patch.dict(main_module.COMMAND_DISPATCH, {"agent_run": interrupted}, clear=True), \
             self.assertRaises(SystemExit) as raised:
            main_module.main()
        self.assertEqual(raised.exception.code, 130)

    def test_wait_zero_still_gets_once_and_hands_off_same_id(self) -> None:
        client = _FakeAgentClient(gets=[{"id": "agent_run_new", "status": "queued"}])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = asyncio.run(run_agent(
                agent_args(), client, monotonic=_Clock([0, 0]),
                sleep=lambda _seconds: None,
            ))
        self.assertEqual(client.get_calls, ["agent_run_new"])
        self.assertEqual((result["id"], result["status"], result["outputReady"]),
                         ("agent_run_new", "running", False))
        event = json.loads(stderr.getvalue())
        self.assertEqual((event["event"], event["id"]),
                         ("agent_run_created", "agent_run_new"))

    def test_deadline_clips_sleep_and_terminal_fields_are_preserved(self) -> None:
        sleeps = []

        async def record_sleep(seconds):
            sleeps.append(seconds)

        client = _FakeAgentClient(gets=[
            {"id": "agent_run_1", "status": "running"},
            {
                "id": "agent_run_1", "status": "completed",
                "output": {"grounding": [{"url": "https://e"}]},
                "usage": {"searches": 2}, "costDollars": 0.12,
            },
        ])
        result = asyncio.run(run_agent(
            agent_args(query=None, run_id="agent_run_1", wait_seconds=5),
            client, monotonic=_Clock([0, 1]), sleep=record_sleep,
        ))
        self.assertEqual(sleeps, [4])
        self.assertEqual(result, {
            "success": True,
            "id": "agent_run_1",
            "status": "completed",
            "outputReady": True,
            "output": {"grounding": [{"url": "https://e"}]},
            "usage": {"searches": 2},
            "costDollars": 0.12,
        })

    def test_missing_or_reused_create_id_fails_without_polling(self) -> None:
        for response, previous in (({}, None), ({"id": "agent_run_old"}, "agent_run_old")):
            client = _FakeAgentClient(create=response)
            with self.subTest(response=response), self.assertRaises(ValueError):
                asyncio.run(run_agent(
                    agent_args(previous_run_id=previous), client,
                    monotonic=_Clock([0]), sleep=lambda _seconds: None,
                ))
            self.assertEqual(client.get_calls, [])

    def test_normalization_and_interruption_contract(self) -> None:
        self.assertEqual(normalize_agent_result(
            "agent_run_1", {"status": "failed", "error": "nope"}
        ), {
            "success": False, "id": "agent_run_1", "status": "failed",
            "outputReady": False, "error": "nope",
        })
        self.assertEqual(normalize_agent_result(
            "agent_run_1", {"status": "cancelled"}
        )["success"], False)

        async def interrupted_sleep(_seconds):
            raise asyncio.CancelledError

        client = _FakeAgentClient(gets=[{"status": "running"}])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(asyncio.CancelledError):
            asyncio.run(run_agent(
                agent_args(query=None, run_id="agent_run_1", wait_seconds=5),
                client, monotonic=_Clock([0, 1]), sleep=interrupted_sleep,
            ))
        event = json.loads(stderr.getvalue())
        self.assertEqual((event["event"], event["id"]),
                         ("agent_run_interrupted", "agent_run_1"))

        pre_id = _FakeAgentClient(create_error=asyncio.CancelledError())
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(asyncio.CancelledError):
            asyncio.run(run_agent(
                agent_args(), pre_id, monotonic=_Clock([0]),
                sleep=lambda _seconds: None,
            ))
        event = json.loads(stderr.getvalue())
        self.assertEqual((event["event"], event["state"]),
                         ("agent_run_interrupted", "unknown"))

    def test_local_validation_performs_no_http_requests(self) -> None:
        client = _FakeAgentClient()
        with self.assertRaises(ValueError):
            asyncio.run(run_agent(
                agent_args(data_source=["fiber", "fiber"]), client,
                monotonic=_Clock([0]), sleep=lambda _seconds: None,
            ))
        self.assertEqual((client.create_calls, client.get_calls), ([], []))

    def test_command_writes_failed_result_then_exits_one(self) -> None:
        fake = _FakeAgentClient(gets=[{"status": "failed", "error": "bad"}])

        config = SimpleNamespace(
            exa_api_url="https://example.test", exa_api_key="key",
            max_retry_wait=1, debug_enabled=False, auth_scheme="x-api-key",
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "agent.json"
            stdout = io.StringIO()
            with patch("exa_cli.agent.Config", return_value=config), \
                 patch("exa_cli.agent.ExaClient", return_value=fake), \
                 contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                asyncio.run(cmd_agent_run(agent_args(
                    query=None, run_id="agent_run_1", wait_seconds=0,
                    out=str(out_path),
                )))
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "ok")
            self.assertFalse(json.loads(out_path.read_text(encoding="utf-8"))["success"])

    def test_zdr_error_is_explained_without_leaking_api_key(self) -> None:
        request = httpx.Request("GET", "https://example.test/agent/runs/agent_run_1")
        response = httpx.Response(
            400, request=request, text="streaming required for top-secret-key"
        )
        fake = _FakeAgentClient(get_error=httpx.HTTPStatusError(
            "bad", request=request, response=response
        ))
        config = SimpleNamespace(
            exa_api_url="https://example.test", exa_api_key="top-secret-key",
            max_retry_wait=1, debug_enabled=False, auth_scheme="x-api-key",
        )
        stderr = io.StringIO()
        with patch("exa_cli.agent.Config", return_value=config), \
             patch("exa_cli.agent.ExaClient", return_value=fake), \
             contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            asyncio.run(cmd_agent_run(agent_args(
                query=None, run_id="agent_run_1", wait_seconds=0,
            )))
        error = json.loads(stderr.getvalue())["error"]
        self.assertIn("Zero Data Retention", error)
        self.assertNotIn("top-secret-key", error)


if __name__ == "__main__":
    unittest.main()
