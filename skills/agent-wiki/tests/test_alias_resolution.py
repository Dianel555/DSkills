"""Tests for alias and disambiguation resolution in wiki index."""

import json
from pathlib import Path

import pytest

from agent_wiki import config, frontmatter, wiki_index


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _init(vault: Path) -> None:
    """Initialize wiki structure."""
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


# --- 2.1 Alias resolution tests ---


def test_frontmatter_aliases_populate_alias_index(tmp_path):
    """Frontmatter aliases[] create entries in top-level alias_index."""
    _init(tmp_path)

    _topic(tmp_path, "刘邦.md", {
        "title": "刘邦",
        "aliases": ["沛公", "汉王"]
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    assert "alias_index" in data
    assert data["alias_index"]["沛公"] == "刘邦.md"
    assert data["alias_index"]["汉王"] == "刘邦.md"


def test_per_topic_aliases_preserve_order(tmp_path):
    """Per-topic aliases[] field preserves authored order."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "aliases": ["Third", "First", "Second"]
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["topic.md"]

    # Order preserved
    assert entry["aliases"] == ["Third", "First", "Second"]


def test_alias_index_keys_are_deduplicated_and_sorted(tmp_path):
    """alias_index keys are deduplicated and NFC-sorted."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A", "aliases": ["Zebra", "Apple"]}, "Content.")
    _topic(tmp_path, "B.md", {"title": "B", "aliases": ["Banana"]}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    alias_keys = list(data["alias_index"].keys())
    assert alias_keys == sorted(alias_keys)  # Sorted
    assert len(alias_keys) == len(set(alias_keys))  # Deduplicated


def test_optional_wiki_aliases_json_merged(tmp_path):
    """Optional wiki/.wiki-aliases.json is merged into alias_index."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")

    # Create disambiguation map
    wiki_aliases = config.wiki_root(tmp_path) / ".wiki-aliases.json"
    wiki_aliases.write_text(json.dumps({"MapAlias": "target.md"}), encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    assert data["alias_index"]["MapAlias"] == "target.md"


def test_wiki_aliases_json_absent_is_graceful(tmp_path):
    """Missing .wiki-aliases.json is tolerated without error."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic", "aliases": ["Alias1"]}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    assert data["alias_index"]["Alias1"] == "topic.md"
    # No error for missing map file


def test_malformed_alias_map_is_reported(tmp_path):
    """Malformed .wiki-aliases.json is reported as alias_map_invalid."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    # Create malformed JSON
    wiki_aliases = config.wiki_root(tmp_path) / ".wiki-aliases.json"
    wiki_aliases.write_text("not valid json", encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    assert any(e["error"] == "alias_map_invalid" for e in errors)


def test_alias_map_non_object_is_reported(tmp_path):
    """Non-object .wiki-aliases.json (array, string) is reported."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    # Create array instead of object
    wiki_aliases = config.wiki_root(tmp_path) / ".wiki-aliases.json"
    wiki_aliases.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    assert any(e["error"] == "alias_map_invalid" for e in errors)


def test_alias_target_missing_is_reported(tmp_path):
    """Alias pointing to nonexistent topic is reported as alias_target_missing."""
    _init(tmp_path)

    _topic(tmp_path, "exists.md", {"title": "Exists", "aliases": ["GoodAlias"]}, "Content.")

    # Alias pointing to nonexistent target
    wiki_aliases = config.wiki_root(tmp_path) / ".wiki-aliases.json"
    wiki_aliases.write_text(json.dumps({"BadAlias": "nonexistent.md"}), encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    # GoodAlias should work
    assert data["alias_index"].get("GoodAlias") == "exists.md"

    # BadAlias should be omitted and reported
    assert "BadAlias" not in data["alias_index"]
    assert any(e["error"] == "alias_target_missing" and e["alias"] == "BadAlias" for e in errors)


def test_alias_conflict_is_reported(tmp_path):
    """Same alias → two targets is reported as alias_conflict with sorted candidates."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A", "aliases": ["Conflict"]}, "Content.")
    _topic(tmp_path, "B.md", {"title": "B", "aliases": ["Conflict"]}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Conflicting alias should be omitted
    assert "Conflict" not in data["alias_index"]

    # Error should list both candidates, NFC-sorted
    conflict_error = next((e for e in errors if e["error"] == "alias_conflict" and e["alias"] == "Conflict"), None)
    assert conflict_error is not None
    assert set(conflict_error["candidates"]) == {"A.md", "B.md"}
    assert conflict_error["candidates"] == sorted(conflict_error["candidates"])


def test_alias_equals_real_topic_key_is_conflict(tmp_path):
    """Alias that equals an existing topic's own key is a conflict."""
    _init(tmp_path)

    _topic(tmp_path, "Real.md", {"title": "Real"}, "Content.")
    _topic(tmp_path, "Other.md", {"title": "Other", "aliases": ["Real.md"]}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # "Real.md" as an alias should conflict
    assert any(e["error"] == "alias_conflict" and e["alias"] == "Real.md" for e in errors)


def test_alias_resolution_is_deterministic(tmp_path):
    """Rebuilding index twice produces identical alias_index."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A", "aliases": ["AliasA"]}, "Content.")
    _topic(tmp_path, "B.md", {"title": "B", "aliases": ["AliasB"]}, "Content.")

    data1, _ = wiki_index.rebuild(tmp_path)
    data2, _ = wiki_index.rebuild(tmp_path)

    # Serialize and compare
    json1 = wiki_index.serialize(data1)
    json2 = wiki_index.serialize(data2)

    assert json1 == json2


def test_frontmatter_alias_and_map_both_contribute(tmp_path):
    """Both frontmatter aliases and .wiki-aliases.json contribute to alias_index."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target", "aliases": ["FrontmatterAlias"]}, "Content.")

    wiki_aliases = config.wiki_root(tmp_path) / ".wiki-aliases.json"
    wiki_aliases.write_text(json.dumps({"MapAlias": "target.md"}), encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["alias_index"]["FrontmatterAlias"] == "target.md"
    assert data["alias_index"]["MapAlias"] == "target.md"


def test_aliases_nfc_normalized(tmp_path):
    """Alias text is NFC-normalized."""
    _init(tmp_path)

    # NFD (decomposed) form
    _topic(tmp_path, "topic.md", {"title": "Topic", "aliases": ["café"]}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Should be normalized to NFC
    alias_keys = list(data["alias_index"].keys())
    assert "café" in alias_keys  # NFC form
