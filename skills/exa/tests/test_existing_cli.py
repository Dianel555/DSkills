from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from _support import SKILL_ROOT, command_module
from exa_cli.__main__ import build_parser
from exa_cli.config import Config, load_dotenv
from exa_cli.output import output_error, output_json


class _HandlerClient(SimpleNamespace):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class ExistingCliTests(unittest.TestCase):
    def setUp(self) -> None:
        Config._reset_for_testing()

    def tearDown(self) -> None:
        Config._reset_for_testing()

    def test_four_existing_commands_and_global_option_placement(self) -> None:
        parser = build_parser()
        subparsers = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertTrue({
            "web_search_exa", "web_fetch_exa",
            "web_search_advanced_exa", "get_config_info",
        }.issubset(subparsers.choices))
        args = parser.parse_args([
            "--api-key", "test-key", "web_search_exa",
            "--query", "hello", "--num-results", "3",
        ])
        self.assertEqual((args.api_key, args.query, args.num_results),
                         ("test-key", "hello", 3))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args([
                    "web_search_exa", "--query", "hello",
                    "--api-key", "too-late",
                ])

    def test_existing_payload_builders_are_exact(self) -> None:
        search = command_module("search")
        advanced = command_module("advanced")
        self.assertEqual(
            search.extract_category("category:company  Acme AI"),
            ("Acme AI", "company"),
        )
        args = SimpleNamespace(
            query="agents", type="fast", category=None, num_results=2,
            include_domains=["example.com"], exclude_domains=None,
            include_text=None, exclude_text=["noise"],
            start_date="2026-01-01", end_date=None, max_age_hours=24,
            text=True, highlights=True, summary=False, max_chars=900,
        )
        self.assertEqual(advanced._build_payload(args), {
            "query": "agents",
            "type": "fast",
            "numResults": 2,
            "includeDomains": ["example.com"],
            "excludeText": ["noise"],
            "startPublishedDate": "2026-01-01",
            "maxAgeHours": 24,
            "contents": {
                "text": {"maxCharacters": 900},
                "highlights": True,
            },
        })

    def test_search_and_fetch_handlers_send_preserved_payloads(self) -> None:
        fake_config = SimpleNamespace(
            exa_api_url="https://example.test",
            exa_api_key="secret",
            max_retry_wait=1,
            debug_enabled=False,
            auth_scheme="x-api-key",
        )
        search_client = _HandlerClient(search=AsyncMock(return_value={"ok": 1}))
        search = command_module("search")
        with patch.object(search, "Config", return_value=fake_config), \
             patch.object(search, "ExaClient", return_value=search_client), \
             contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(search.cmd_web_search_exa(SimpleNamespace(
                query="category:news launch", num_results=4,
            )))
        search_client.search.assert_awaited_once_with({
            "query": "launch",
            "numResults": 4,
            "contents": {"highlights": True},
            "category": "news",
        })

        fetch_client = _HandlerClient(
            get_contents=AsyncMock(return_value={"ok": 1})
        )
        fetch = command_module("fetch")
        with patch.object(fetch, "Config", return_value=fake_config), \
             patch.object(fetch, "ExaClient", return_value=fetch_client), \
             contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(fetch.cmd_web_fetch_exa(SimpleNamespace(
                urls=["https://a", "https://b"], max_chars=123, out=None,
            )))
        fetch_client.get_contents.assert_awaited_once_with(
            ["https://a", "https://b"],
            extras={"contents": {"text": {"maxCharacters": 123}}},
        )

    def test_output_stream_and_file_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "result.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                output_json({"value": "测试"}, str(out_path))
            self.assertEqual(json.loads(out_path.read_text(encoding="utf-8")),
                             {"value": "测试"})
            self.assertEqual(json.loads(stdout.getvalue()),
                             {"status": "ok", "file": str(out_path)})

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            output_error("broken", code=7)
        self.assertEqual(raised.exception.code, 7)
        self.assertEqual(json.loads(stderr.getvalue()), {"error": "broken"})

    def test_config_override_and_dotenv_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"EXA_API_KEY": "process-key"}, clear=True):
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "EXA_API_KEY=file-key\nEXA_API_URL=https://file.test\n",
                encoding="utf-8",
            )
            self.assertTrue(load_dotenv(env_file))
            cfg = Config()
            self.assertEqual(cfg.exa_api_key, "process-key")
            self.assertEqual(cfg.exa_api_url, "https://file.test")
            cfg.set_overrides(api_key="cli-key", api_url="https://cli.test")
            self.assertEqual(cfg.exa_api_key, "cli-key")
            self.assertEqual(cfg.exa_api_url, "https://cli.test")

    def test_launcher_is_independent_of_cwd_and_ignores_cwd_dotenv(self) -> None:
        launcher = SKILL_ROOT / "scripts" / "exa_cli.py"
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text(
                "EXA_API_URL=https://cwd.invalid\n", encoding="utf-8"
            )
            env = os.environ.copy()
            env.pop("EXA_API_URL", None)
            completed = subprocess.run(
                [sys.executable, str(launcher), "get_config_info", "--no-test"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=20,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotEqual(json.loads(completed.stdout)["EXA_API_URL"],
                            "https://cwd.invalid")


if __name__ == "__main__":
    unittest.main()
