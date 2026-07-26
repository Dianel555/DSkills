import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_wiki import cache, commands, config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def test_cleanup_preserves_utf8_bom_when_rewriting_topic(tmp_path):
    (tmp_path / "wiki" / "topics").mkdir(parents=True)
    topic = tmp_path / "wiki" / "topics" / "T.md"
    body = frontmatter.dump({"sources": ["a.md", "b.md"]}, "# Body\n")
    topic.write_text("﻿" + body, encoding="utf-8")
    data = cache.empty_schema()
    cache.upsert(data, "a.md", "old", 1000000000000000000, 1, ["T.md"])
    cache.save(tmp_path, data)

    result = run_cli("cleanup", "--vault", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert topic.read_text(encoding="utf-8").startswith("﻿---")


def test_cleanup_reports_stable_frontmatter_parse_error_and_keeps_cache(tmp_path):
    (tmp_path / "wiki" / "topics").mkdir(parents=True)
    topic = tmp_path / "wiki" / "topics" / "Bad.md"
    topic.write_text("---\nsources: [\n---\nbody", encoding="utf-8")
    data = cache.empty_schema()
    cache.upsert(data, "missing.md", "old", 1000000000000000000, 1, ["Bad.md"])
    cache.save(tmp_path, data)

    result = run_cli("cleanup", "--vault", str(tmp_path))
    payload = json.loads(result.stdout)

    assert payload["removed"] == 0
    assert payload["errors"] == [{"path": "Bad.md", "error": "frontmatter_parse_failed"}]
    assert "missing.md" in cache.load(tmp_path)["sources"]


def test_init_fails_before_partial_state_when_preflight_rejects(tmp_path, monkeypatch, capsys):
    class Args:
        vault = str(tmp_path)

    monkeypatch.setattr(commands, "_ensure_wiki_writable", lambda vault: commands.fail({"error": "wiki_not_writable"}, 1))

    with pytest.raises(SystemExit):
        commands.cmd_init(Args())

    assert json.loads(capsys.readouterr().err) == {"error": "wiki_not_writable"}
    assert not (tmp_path / "wiki").exists()
