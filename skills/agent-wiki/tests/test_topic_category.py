"""Subject-category grouping (topic_category) + keyword inventory.

Covers the patch-3 contract: ``topic_category`` in the index, static-site
grouping keyed on it (falling back to ``type``), the ``keywords`` subcommand,
and the Bases 按主题 view.
"""

import json
import subprocess
import sys
from pathlib import Path

from agent_wiki import bases, config, frontmatter, wiki_index

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def _write(directory: Path, name: str, meta: dict, body: str = "x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _topic(tmp_path, name, meta, body="x"):
    return _write(config.topics_dir(tmp_path), name, {"title": name[:-3], **meta}, body)


def _run(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True
    )


# --- index carries topic_category ------------------------------------------

def test_index_normalizes_topic_category(tmp_path):
    _topic(tmp_path, "a.md", {"topic_category": "cat-alpha"})
    _topic(tmp_path, "b.md", {"type": "paper"})  # no category -> ""
    data, errors = wiki_index.rebuild(tmp_path)
    assert errors == []
    assert data["topics"]["a.md"]["topic_category"] == "cat-alpha"
    assert data["topics"]["b.md"]["topic_category"] == ""


def test_index_reuse_rejects_entry_without_topic_category(tmp_path):
    # A v2 entry lacking topic_category must not be reused as current.
    _topic(tmp_path, "a.md", {"topic_category": "cat-beta"})
    data, _ = wiki_index.rebuild(tmp_path)
    stale = dict(data["topics"]["a.md"])
    del stale["topic_category"]
    assert not wiki_index._cache_entry_is_current(stale, "topic")


# --- keywords subcommand ----------------------------------------------------

def test_keywords_inventory_frequency_desc(tmp_path):
    _topic(tmp_path, "a.md", {"keywords": ["kw-alpha", "kw-gamma"]})
    _topic(tmp_path, "b.md", {"keywords": ["kw-alpha"]})
    _topic(tmp_path, "c.md", {"keywords": ["kw-beta"]})
    _topic(tmp_path, "d.md", {})  # no keywords -> uncategorized
    result = _run("keywords", "--vault", str(tmp_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    counts = [(k["keyword"], k["count"]) for k in payload["keywords"]]
    assert counts == [("kw-alpha", 2), ("kw-beta", 1), ("kw-gamma", 1)]
    assert payload["keywords"][0]["topics"] == ["a.md", "b.md"]
    assert payload["uncategorized"] == ["d.md"]


def test_keywords_not_initialized(tmp_path):
    result = _run("keywords", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "wiki_not_initialized"


def test_keywords_dedup_within_topic_and_drop_empty(tmp_path):
    # duplicate keyword in one topic must count once; empty strings are dropped,
    # and a topic whose only keywords were empty lands in uncategorized.
    _topic(tmp_path, "a.md", {"keywords": ["kw-alpha", "kw-alpha", ""]})
    _topic(tmp_path, "b.md", {"keywords": ["  "]})  # whitespace-only -> uncategorized
    result = _run("keywords", "--vault", str(tmp_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    counts = [(k["keyword"], k["count"]) for k in payload["keywords"]]
    assert counts == [("kw-alpha", 1)]
    assert payload["keywords"][0]["topics"] == ["a.md"]
    assert sorted(payload["uncategorized"]) == ["b.md"]


# --- bases 按主题 view --------------------------------------------------------

def test_bases_has_topic_category_view(tmp_path):
    text = bases.build_index_base("")
    assert "topic_category:" in text
    assert "displayName: 主题" in text
    assert "name: 按主题" in text


# --- site grouping falls back to type ---------------------------------------

def test_group_key_prefers_category_then_type():
    from agent_wiki import site
    assert site._group_key({"topic_category": "cat-alpha", "type": "paper"}) == "cat-alpha"
    assert site._group_key({"type": "paper"}) == "paper"
    assert site._group_key({"kind": "query"}) == "query"
    assert site._group_key({}) == ""
