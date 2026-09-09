"""In-process tests for gen-home: atomic write, cards resolution, managed-block
merge, and ``--emit-only`` (content handed to the agent for an MCP-side write).

These monkeypatch ``commands.plugins`` / ``commands.emit``; the subprocess
``run_cli`` path in test_home.py cannot reach in-process patches.
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


def _args(vault, cards="auto", emit_only=False):
    return types.SimpleNamespace(vault=str(vault), cards=cards, emit_only=emit_only)


@pytest.fixture
def initialized(tmp_path):
    commands.cmd_init(_args(tmp_path))
    return tmp_path


@pytest.fixture
def capture_emit(monkeypatch):
    payloads = []
    monkeypatch.setattr(commands, "emit", lambda payload: payloads.append(payload))
    return payloads


def _idx(vault):
    return (config.wiki_root(vault) / "index.md").read_text(encoding="utf-8")


def test_atomic_write_by_default(initialized, capture_emit):
    commands.cmd_gen_home(_args(initialized))
    payload = capture_emit[-1]
    assert payload["write_via"] == "atomic"
    assert payload["path"] == "wiki/index.md"
    assert payload["cards"] is False  # no .obsidian under tmp_path
    text = _idx(initialized)
    assert text == home.render_skeleton(initialized, False)
    assert home.AUTO_START in text


# --- cards resolution -------------------------------------------------------

def test_cards_auto_follows_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: True)
    commands.cmd_gen_home(_args(initialized, cards="auto"))
    assert capture_emit[-1]["cards"] is True
    assert "```dataviewjs" in _idx(initialized)


def test_cards_off_overrides_positive_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: True)
    commands.cmd_gen_home(_args(initialized, cards="off"))
    assert capture_emit[-1]["cards"] is False
    assert "```dataviewjs" not in _idx(initialized)


def test_cards_on_overrides_negative_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: False)
    commands.cmd_gen_home(_args(initialized, cards="on"))
    assert capture_emit[-1]["cards"] is True
    assert "```dataviewjs" in _idx(initialized)


def test_merge_preserves_prose_in_process(initialized, capture_emit):
    custom = f"# Wiki Index\n\n手写散文。\n\n{home.AUTO_START}\n\nSTALE\n\n{home.AUTO_END}\n"
    (config.wiki_root(initialized) / "index.md").write_text(custom, encoding="utf-8")
    commands.cmd_gen_home(_args(initialized, cards="on"))
    text = _idx(initialized)
    assert "手写散文。" in text
    assert "STALE" not in text
    assert "```dataviewjs" in text


# --- emit-only ---------------------------------------------------------------

def test_emit_only_returns_content_without_writing(initialized, capture_emit):
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
