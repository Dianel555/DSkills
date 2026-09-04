"""Boundary constraint for derived topic paths (cache-put / cleanup)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from agent_wiki import config

CLI = Path(__file__).resolve().parents[1] / "scripts" / "agent_wiki_cli.py"


def _run(args, vault):
    return subprocess.run(
        [sys.executable, str(CLI), *args, "--vault", str(vault)],
        capture_output=True, text=True, encoding="utf-8",
    )


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "note.md").write_text("# n", encoding="utf-8")
    _run(["init"], tmp_path)
    return tmp_path


def test_topic_path_accepts_plain_name(vault):
    resolved = config.topic_path(vault, "topic1.md")
    assert resolved.parent == config.topics_dir(vault)


@pytest.mark.parametrize("bad", ["../../evil.md", "../queries/r.md", "C:/evil.md", "/etc/x.md"])
def test_topic_path_rejects_escapes(vault, bad):
    with pytest.raises(ValueError):
        config.topic_path(vault, bad)


def test_cache_put_rejects_out_of_bounds_topic(vault):
    result = _run(["cache-put", "note.md", "--topics", "../escape.md"], vault)
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "invalid_topic_path"


def test_cleanup_reports_invalid_cached_topic(vault):
    ok = _run(["cache-put", "note.md", "--topics", "t.md"], vault)
    assert ok.returncode == 0
    cache_file = config.cache_path(vault)
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["sources"]["note.md"]["derived_topics"] = ["../../outside.md"]
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    (vault / "note.md").unlink()

    outside = vault.parent / "outside.md"
    outside.write_text("---\ntitle: x\nsources: [note.md]\n---\nbody", encoding="utf-8")

    result = _run(["cleanup"], vault)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert {"path": "../../outside.md", "error": "invalid_topic_path"} in payload["errors"]
    assert outside.read_text(encoding="utf-8").startswith("---\ntitle: x")
    # entry with invalid topic is kept in cache (not silently dropped)
    kept = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "note.md" in kept["sources"]
