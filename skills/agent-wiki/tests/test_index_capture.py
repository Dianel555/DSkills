import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

from agent_wiki import config, frontmatter, wiki_index

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def _write(directory: Path, name: str, meta: dict, body: str = "x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


# --- queries indexed under their own dict ----------------------------------

def test_index_picks_up_queries_under_own_dict(tmp_path):
    _write(config.topics_dir(tmp_path), "T.md", {"title": "T", "sources": ["a.md"]})
    _write(config.queries_dir(tmp_path), "Q.md", {"title": "Q", "sources": ["b.pdf"]}, body="见 [[T]]\n")
    data, errors = wiki_index.rebuild(tmp_path)
    assert errors == []
    assert set(data["topics"]) == {"T.md"}
    assert set(data["queries"]) == {"queries/Q.md"}
    assert data["topics"]["T.md"]["kind"] == "topic"
    assert data["queries"]["queries/Q.md"]["kind"] == "query"
    assert data["queries"]["queries/Q.md"]["path"] == "queries/Q.md"
    assert data["queries"]["queries/Q.md"]["links"] == ["T"]


# --- links parsing ---------------------------------------------------------

def test_links_strip_alias_heading_block_and_dedup_nfc(tmp_path):
    nfd = unicodedata.normalize("NFD", "café")
    body = f"[[{nfd}]] [[A|别名]] [[A#标题]] ![[B]] [[C^块]] [[A]]\n"
    _write(config.topics_dir(tmp_path), "L.md", {"title": "L"}, body=body)
    links = wiki_index.rebuild(tmp_path)[0]["topics"]["L.md"]["links"]
    assert links == ["café", "A", "B", "C"]
    assert all(unicodedata.normalize("NFC", k) == k for k in links)


def test_index_does_not_rewrite_bodies(tmp_path):
    page = _write(config.topics_dir(tmp_path), "T.md", {"title": "T"}, body="保留 [[X|y]] ![[img.png]]\n")
    before = page.read_bytes()
    wiki_index.rebuild(tmp_path)
    assert page.read_bytes() == before


# --- cmd_index topic count + aggregated errors -----------------------------

def test_cmd_index_topic_count_excludes_captures(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _write(config.topics_dir(tmp_path), "T1.md", {"title": "T1"})
    _write(config.topics_dir(tmp_path), "T2.md", {"title": "T2"})
    _write(config.queries_dir(tmp_path), "Q.md", {"title": "Q"})
    payload = json.loads(run_cli("index", "--vault", str(tmp_path)).stdout)
    assert payload["topics"] == 2
    index = json.loads(config.index_path(tmp_path).read_text(encoding="utf-8"))
    assert len(index["queries"]) == 1


def test_cmd_index_aggregates_errors_across_dirs(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    (config.topics_dir(tmp_path) / "bad.md").write_text("---\nk: [\n---\nb", encoding="utf-8")
    (config.queries_dir(tmp_path) / "bad2.md").write_text("---\nk: [\n---\nb", encoding="utf-8")
    payload = json.loads(run_cli("index", "--vault", str(tmp_path)).stdout)
    paths = {e["path"] for e in payload["errors"]}
    assert "bad.md" in paths
    assert "queries/bad2.md" in paths


# --- determinism with capture pages ----------------------------------------

def test_rebuild_byte_identical_with_captures(tmp_path):
    _write(config.topics_dir(tmp_path), "中.md", {"title": "中"}, body="[[Q]]\n")
    _write(config.queries_dir(tmp_path), "Q.md", {"title": "Q"}, body="[[中]]\n")
    first = wiki_index.serialize(wiki_index.rebuild(tmp_path)[0])
    second = wiki_index.serialize(wiki_index.rebuild(tmp_path)[0])
    assert first == second
    assert first.endswith("\n")


def test_generated_at_max_mtime_across_all_dirs(tmp_path):
    t = _write(config.topics_dir(tmp_path), "T.md", {"title": "T"})
    q = _write(config.queries_dir(tmp_path), "Q.md", {"title": "Q"})
    os.utime(t, ns=(1_000_000_000, 1_000_000_000))
    os.utime(q, ns=(5_000_000_000, 5_000_000_000))
    data = wiki_index.rebuild(tmp_path)[0]
    assert data["generated_at"] == "1970-01-01T00:00:05Z"


def test_malformed_capture_contributes_no_mtime(tmp_path):
    t = _write(config.topics_dir(tmp_path), "T.md", {"title": "T"})
    os.utime(t, ns=(2_000_000_000, 2_000_000_000))
    bad = config.queries_dir(tmp_path) / "bad.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("---\nk: [\n---\nb", encoding="utf-8")
    os.utime(bad, ns=(9_000_000_000, 9_000_000_000))
    data = wiki_index.rebuild(tmp_path)[0]
    assert data["generated_at"] == "1970-01-01T00:00:02Z"
