import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from agent_wiki import config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def _topic(vault, name, meta=None):
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)
    p = config.topics_dir(vault) / name
    p.write_text(frontmatter.dump(meta or {"title": name}, "b"), encoding="utf-8")
    return p


def _status(vault):
    return json.loads(run_cli("status", "--vault", str(vault)).stdout)


# --- capture / graph counts ------------------------------------------------

def test_status_reports_capture_and_graph_counts(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    (config.queries_dir(tmp_path) / "q1.md").write_text(frontmatter.dump({"title": "q"}, "x"), encoding="utf-8")
    (config.graphs_dir(tmp_path) / "g1.canvas").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    payload = _status(tmp_path)
    assert payload["queries_total"] == 1
    assert payload["graphs_count"] == 1


# --- graphs_stale: absent / equal / newer / no-topics ----------------------

def test_graphs_stale_false_when_no_topics(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    assert _status(tmp_path)["graphs_stale"] is False


def test_graphs_stale_true_when_topic_lacks_canvas(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md")
    assert _status(tmp_path)["graphs_stale"] is True


def test_graphs_stale_absent_equal_newer(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    topic = _topic(tmp_path, "T.md")
    run_cli("gen-canvas", "--topic", "T", "--vault", str(tmp_path))
    canvas = config.graphs_dir(tmp_path) / "T.canvas"

    base = canvas.stat().st_mtime_ns
    os.utime(topic, ns=(base, base))
    os.utime(canvas, ns=(base, base))
    assert _status(tmp_path)["graphs_stale"] is False  # equal -> not stale

    os.utime(topic, ns=(base + 1_000_000_000, base + 1_000_000_000))
    assert _status(tmp_path)["graphs_stale"] is True  # newer topic -> stale


# --- index_stale watches capture dirs --------------------------------------

def test_index_stale_watches_queries(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md")
    run_cli("index", "--vault", str(tmp_path))
    index = config.index_path(tmp_path)
    base = index.stat().st_mtime_ns

    query = config.queries_dir(tmp_path) / "Q.md"
    query.write_text(frontmatter.dump({"title": "Q"}, "x"), encoding="utf-8")
    os.utime(query, ns=(base + 2_000_000_000, base + 2_000_000_000))
    os.utime(config.topics_dir(tmp_path) / "T.md", ns=(base - 1_000_000_000, base - 1_000_000_000))
    assert _status(tmp_path)["index_stale"] is True


# --- status writes nothing -------------------------------------------------

def test_status_never_writes_any_artifact(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md")
    config.index_path(tmp_path).unlink()  # stale/missing index
    tree = {p: (hashlib.sha256(p.read_bytes()).digest(), p.stat().st_mtime_ns)
            for p in config.wiki_root(tmp_path).rglob("*") if p.is_file()}
    before = sorted(p for p in config.wiki_root(tmp_path).rglob("*"))

    run_cli("status", "--vault", str(tmp_path))

    after = sorted(p for p in config.wiki_root(tmp_path).rglob("*"))
    assert before == after  # no new files (no index rebuild written)
    for p, fp in tree.items():
        assert (hashlib.sha256(p.read_bytes()).digest(), p.stat().st_mtime_ns) == fp
