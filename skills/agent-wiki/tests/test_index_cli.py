import json
import os
import subprocess
import sys
from pathlib import Path

from agent_wiki import config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


def _topic(vault: Path, name: str, meta: dict) -> Path:
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, "body"), encoding="utf-8")
    return path


# --- 2.1 init creates / backfills index ------------------------------------

def test_init_creates_empty_index(tmp_path):
    payload = json.loads(run_cli("init", "--vault", str(tmp_path)).stdout)
    index = config.index_path(tmp_path)
    assert "wiki/.wiki-index.json" in payload["created"]
    assert json.loads(index.read_text(encoding="utf-8")) == {
        "version": 1, "generated_at": "1970-01-01T00:00:00Z",
        "topics": {}, "queries": {}, "alias_index": {},
    }


def test_init_backfills_missing_index(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    config.index_path(tmp_path).unlink()
    payload = json.loads(run_cli("init", "--vault", str(tmp_path)).stdout)
    assert payload["status"] == "already_initialized"
    assert payload["created"] == ["wiki/.wiki-index.json"]
    assert config.index_path(tmp_path).exists()


# --- 2.2 index subcommand ---------------------------------------------------

def test_index_subcommand_rebuilds(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "A.md", {"title": "A", "authors": ["x"]})
    result = run_cli("index", "--vault", str(tmp_path))
    payload = json.loads(result.stdout)
    assert payload == {"ok": True, "topics": 1, "errors": []}
    index = json.loads(config.index_path(tmp_path).read_text(encoding="utf-8"))
    assert index["topics"]["A.md"]["authors"] == ["x"]
    assert not (tmp_path / "wiki" / "index.base").exists()


def test_index_reports_partial_errors(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "ok.md", {"title": "ok"})
    (config.topics_dir(tmp_path) / "bad.md").write_text("---\nx: [\n---\nb", encoding="utf-8")
    payload = json.loads(run_cli("index", "--vault", str(tmp_path)).stdout)
    assert payload["topics"] == 1
    assert {"path": "bad.md", "error": "frontmatter_parse_failed"} in payload["errors"]


def test_index_requires_init(tmp_path):
    result = run_cli("index", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "wiki_not_initialized", "hint": "run init first"}


# --- 2.3 gen-base rebuilds index --------------------------------------------

def test_gen_base_rebuilds_index_and_keeps_two_files(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md", {"title": "T"})
    payload = json.loads(run_cli("gen-base", "--name", "Notions", "--vault", str(tmp_path)).stdout)
    assert set(payload["written"]) == {"wiki/index.base", "Notions.base"}
    index = json.loads(config.index_path(tmp_path).read_text(encoding="utf-8"))
    assert "T.md" in index["topics"]


# --- 2.4 status index metrics -----------------------------------------------

def test_status_reports_index_metrics(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "A.md", {"title": "A"})
    run_cli("index", "--vault", str(tmp_path))
    payload = json.loads(run_cli("status", "--vault", str(tmp_path)).stdout)
    assert payload["index_exists"] is True
    assert payload["index_topics"] == 1
    assert payload["index_size_bytes"] > 0
    assert payload["index_errors"] == []


def test_status_stale_absent_equal_newer(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    topic = _topic(tmp_path, "A.md", {"title": "A"})
    run_cli("index", "--vault", str(tmp_path))
    index = config.index_path(tmp_path)

    # absent
    index.unlink()
    p = json.loads(run_cli("status", "--vault", str(tmp_path)).stdout)
    assert p["index_exists"] is False and p["index_stale"] is True

    run_cli("index", "--vault", str(tmp_path))
    base = index.stat().st_mtime_ns

    # equal -> not stale
    os.utime(topic, ns=(base, base))
    os.utime(index, ns=(base, base))
    assert json.loads(run_cli("status", "--vault", str(tmp_path)).stdout)["index_stale"] is False

    # newer topic -> stale
    os.utime(topic, ns=(base + 1_000_000_000, base + 1_000_000_000))
    assert json.loads(run_cli("status", "--vault", str(tmp_path)).stdout)["index_stale"] is True


def test_status_never_writes_index(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "A.md", {"title": "A"})
    config.index_path(tmp_path).unlink()  # stale/missing
    run_cli("status", "--vault", str(tmp_path))
    assert not config.index_path(tmp_path).exists()


def test_status_robust_to_corrupt_index(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "A.md", {"title": "A"})
    config.index_path(tmp_path).write_text("[1, 2, 3]", encoding="utf-8")  # non-dict top level
    result = run_cli("status", "--vault", str(tmp_path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["index_exists"] is True
    assert payload["index_topics"] == 0
