"""gen-home --emit-only: render index.md content without writing it.

The content is handed to the agent so an MCP-side conditional write can do the
replace; the CLI itself must stay off the file and off the REST API.
"""

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest
from agent_wiki import commands, config, home

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def _args(vault, cards="auto", no_rest=False, emit_only=False):
    return types.SimpleNamespace(
        vault=str(vault), cards=cards, no_rest=no_rest, emit_only=emit_only
    )


@pytest.fixture
def initialized(tmp_path):
    commands.cmd_init(_args(tmp_path))
    return tmp_path


@pytest.fixture
def capture_emit(monkeypatch):
    payloads = []
    monkeypatch.setattr(commands, "emit", lambda payload: payloads.append(payload))
    return payloads


def test_emit_only_returns_content_without_writing(initialized, capture_emit, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("--emit-only must not touch the REST API")

    monkeypatch.setattr(commands.obsidian_api, "available", forbidden)
    monkeypatch.setattr(commands.obsidian_api, "put_file", forbidden)

    commands.cmd_gen_home(_args(initialized, emit_only=True))

    payload = capture_emit[-1]
    assert payload["write_via"] == "none"
    assert payload["content"] == home.render_skeleton(initialized, False)
    assert payload["obsidian_path"] == "wiki/index.md"
    # init placeholder is untouched: the agent owns the write
    index_file = config.wiki_root(initialized) / "index.md"
    assert index_file.read_text(encoding="utf-8") == "# Wiki Index\n\n"


def test_emit_only_content_matches_merge_for_existing_page(initialized, capture_emit):
    custom = f"# Wiki Index\n\n手写散文。\n\n{home.AUTO_START}\n\nSTALE\n\n{home.AUTO_END}\n"
    index_file = config.wiki_root(initialized) / "index.md"
    index_file.write_text(custom, encoding="utf-8")

    commands.cmd_gen_home(_args(initialized, cards="on", emit_only=True))

    content = capture_emit[-1]["content"]
    assert content == home.merge(custom, initialized, True)
    assert "手写散文。" in content
    assert "STALE" not in content
    # still no write
    assert index_file.read_text(encoding="utf-8") == custom


def test_emit_only_obsidian_path_carries_scope_prefix(tmp_path, capture_emit):
    (tmp_path / ".obsidian").mkdir()
    vault = tmp_path / "记录"
    vault.mkdir()
    commands.cmd_init(_args(vault))

    commands.cmd_gen_home(_args(vault, emit_only=True))

    assert capture_emit[-1]["obsidian_path"] == "记录/wiki/index.md"


def test_emit_only_and_no_rest_are_mutually_exclusive(tmp_path):
    result = subprocess.run(
        [sys.executable, str(CLI), "gen-home", "--emit-only", "--no-rest",
         "--vault", str(tmp_path)],
        text=True, encoding="utf-8", capture_output=True,
    )
    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


def test_emit_only_payload_is_json_serializable(initialized):
    result = subprocess.run(
        [sys.executable, str(CLI), "gen-home", "--emit-only", "--vault", str(initialized)],
        text=True, encoding="utf-8", capture_output=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["write_via"] == "none"
    assert payload["content"].endswith("\n")
