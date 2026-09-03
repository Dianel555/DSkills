import json
import os
import subprocess
import sys
from pathlib import Path

from agent_wiki import frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=full_env,
    )


def test_cli_missing_vault_returns_json_error(monkeypatch, tmp_path):
    # Create an isolated environment without vault config
    env = os.environ.copy()
    env.pop("AGENT_WIKI_VAULT", None)
    env["DOTENV_DISABLE"] = "1"  # Disable .env loading for this test

    result = subprocess.run(
        [sys.executable, str(CLI), "status"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=tmp_path,  # Run from temp dir
    )

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "vault path required"


def test_cli_version():
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == "agent-wiki 0.1.0"


def test_init_fresh_partial_and_idempotent(tmp_path):
    result = run_cli("init", "--vault", str(tmp_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "wiki" / "topics").is_dir()
    assert (tmp_path / "wiki" / ".wiki-url-cache").is_dir()

    second = run_cli("init", "--vault", str(tmp_path))
    assert json.loads(second.stdout) == {"status": "already_initialized", "created": []}


def test_cache_put_get_round_trip(tmp_path):
    (tmp_path / "note.md").write_text("hello", encoding="utf-8")
    assert run_cli("init", "--vault", str(tmp_path)).returncode == 0

    put = run_cli("cache-put", "note.md", "--topics", "topic.md, other.md ", "--vault", str(tmp_path))
    assert put.returncode == 0, put.stderr
    put_payload = json.loads(put.stdout)
    assert put_payload["ok"] is True
    assert put_payload["path"] == "note.md"

    get = run_cli("cache-get", "note.md", "--vault", str(tmp_path))
    payload = json.loads(get.stdout)
    assert payload["path"] == "note.md"
    assert payload["derived_topics"] == ["topic.md", "other.md"]


def test_scan_reports_new_modified_deleted(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    run_cli("init", "--vault", str(tmp_path))
    run_cli("cache-put", "a.md", "--topics", "A.md", "--vault", str(tmp_path))
    (tmp_path / "a.md").write_text("a2", encoding="utf-8")
    (tmp_path / "中文.md").write_text("new", encoding="utf-8")

    scan = run_cli("scan", "--vault", str(tmp_path))
    payload = json.loads(scan.stdout)

    assert [item["path"] for item in payload["modified"]] == ["a.md"]
    assert [item["path"] for item in payload["new"]] == ["中文.md"]

    (tmp_path / "a.md").unlink()
    deleted = json.loads(run_cli("scan", "--vault", str(tmp_path)).stdout)
    assert deleted["deleted"] == [{"path": "a.md", "derived_topics": ["A.md"]}]


def test_cleanup_archives_orphaned_topic_and_updates_cache(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    run_cli("init", "--vault", str(tmp_path))
    topic = tmp_path / "wiki" / "topics" / "A.md"
    topic.write_text(frontmatter.dump({"title": "A", "sources": ["a.md"]}, "# A\n"), encoding="utf-8")
    run_cli("cache-put", "a.md", "--topics", "A.md", "--vault", str(tmp_path))
    (tmp_path / "a.md").unlink()

    result = run_cli("cleanup", "--vault", str(tmp_path))
    payload = json.loads(result.stdout)

    assert payload["removed"] == 1
    assert payload["archived"] == 1
    assert (tmp_path / "wiki" / "_archived").exists()
    assert json.loads(run_cli("cache-get", "a.md", "--vault", str(tmp_path)).stdout)["status"] == "absent"

    second = json.loads(run_cli("cleanup", "--vault", str(tmp_path)).stdout)
    assert second["removed"] == 0
    assert second["archived"] == 0


def test_status_reports_health(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    topic = tmp_path / "wiki" / "topics" / "orphan.md"
    topic.write_text(frontmatter.dump({"sources": []}, "body"), encoding="utf-8")

    result = run_cli("status", "--vault", str(tmp_path))
    payload = json.loads(result.stdout)

    assert payload["topics_total"] == 1
    assert payload["topics_orphaned"] == 1
    assert payload["sources_tracked"] == 0
    assert "last_log_entry" in payload
