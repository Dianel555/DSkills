import json
import os
import unicodedata
from pathlib import Path

import pytest
from agent_wiki import config, frontmatter, wiki_index


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _init(vault: Path) -> None:
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


# --- 1.1 empty schema -------------------------------------------------------

def test_empty_schema_shape():
    assert wiki_index.empty_schema() == {
        "version": wiki_index.INDEX_VERSION,
        "generated_at": "1970-01-01T00:00:00Z",
        "topics": {},
        "queries": {},
        "alias_index": {},
    }


def test_index_path_under_wiki(tmp_path):
    assert config.index_path(tmp_path) == config.wiki_root(tmp_path) / ".wiki-index.json"


# --- 1.2 normalization ------------------------------------------------------

def test_backward_compatible_minimal_frontmatter(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "T.md", {"title": "T", "sources": ["a.md"], "last_updated": "2026-01-01"})
    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["T.md"]
    assert errors == []
    assert entry["title"] == "T"
    assert entry["sources"] == ["a.md"]
    assert entry["year_start"] is None
    assert entry["year_end"] is None
    assert entry["authors"] == []
    assert entry["source_type"] == "markdown"
    assert entry["summary"] == ""


def test_scalar_list_null_coercion(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "S.md", {
        "authors": "Solo",
        "institutions": ["MIT", "CERN"],
        "year_start": "published 2019 ed",
        "summary": ["one", "two"],
    })
    entry = wiki_index.rebuild(tmp_path)[0]["topics"]["S.md"]
    assert entry["authors"] == ["Solo"]
    assert entry["institutions"] == ["MIT", "CERN"]
    assert entry["source_type"] == ""
    assert entry["year_start"] == 2019
    assert entry["summary"] == "one; two"


def test_int_year_passthrough_and_unparseable_null(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "Y.md", {"year_start": 2021})
    _topic(tmp_path, "N.md", {"year_start": "no digits"})
    topics = wiki_index.rebuild(tmp_path)[0]["topics"]
    assert topics["Y.md"]["year_start"] == 2021
    assert topics["N.md"]["year_start"] is None


def test_year_wrong_type_is_null_not_repr_scanned(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "D.md", {"year_start": {"note": 2019}})
    _topic(tmp_path, "F.md", {"year_start": 2019.5})
    topics = wiki_index.rebuild(tmp_path)[0]["topics"]
    assert topics["D.md"]["year_start"] is None
    assert topics["F.md"]["year_start"] is None


def test_year_start_end_coerced_to_int_or_null(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "R.md", {"year_start": 2021, "year_end": "2026"})
    _topic(tmp_path, "B.md", {"title": "B"})
    topics = wiki_index.rebuild(tmp_path)[0]["topics"]
    assert topics["R.md"]["year_start"] == 2021
    assert topics["R.md"]["year_end"] == 2026
    assert topics["B.md"]["year_start"] is None
    assert topics["B.md"]["year_end"] is None


def test_list_order_preserved_and_nfc(tmp_path):
    _init(tmp_path)
    nfd = unicodedata.normalize("NFD", "café")
    _topic(tmp_path, "L.md", {"keywords": [nfd, "b", "a", "b"]})
    keywords = wiki_index.rebuild(tmp_path)[0]["topics"]["L.md"]["keywords"]
    assert keywords == ["café", "b", "a", "b"]
    assert all(unicodedata.normalize("NFC", k) == k for k in keywords)


def test_title_falls_back_to_stem_when_missing(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "量子.md", {"sources": []})
    assert wiki_index.rebuild(tmp_path)[0]["topics"]["量子.md"]["title"] == "量子"


def test_summary_truncated_to_1000(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "Big.md", {"summary": "あ" * 5000})
    summary = wiki_index.rebuild(tmp_path)[0]["topics"]["Big.md"]["summary"]
    assert len(summary) == 1000


# --- 1.3 determinism --------------------------------------------------------

def test_generated_at_is_max_topic_mtime(tmp_path):
    _init(tmp_path)
    p1 = _topic(tmp_path, "A.md", {"title": "A"})
    p2 = _topic(tmp_path, "B.md", {"title": "B"})
    os.utime(p1, ns=(1_000_000_000, 1_000_000_000))
    os.utime(p2, ns=(2_000_000_000, 2_000_000_000))
    data = wiki_index.rebuild(tmp_path)[0]
    assert data["generated_at"] == "1970-01-01T00:00:02Z"


def test_empty_topics_uses_epoch(tmp_path):
    _init(tmp_path)
    data = wiki_index.rebuild(tmp_path)[0]
    assert data["generated_at"] == "1970-01-01T00:00:00Z"
    assert data["topics"] == {}


def test_rebuild_is_byte_identical(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "中.md", {"title": "中", "authors": ["x", "y"], "summary": "s"})
    first = wiki_index.serialize(wiki_index.rebuild(tmp_path)[0])
    second = wiki_index.serialize(wiki_index.rebuild(tmp_path)[0])
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["version"] == wiki_index.INDEX_VERSION


# --- 1.4 atomic write -------------------------------------------------------

def test_save_index_atomic(tmp_path):
    _init(tmp_path)
    wiki_index.save_index(tmp_path, wiki_index.empty_schema())
    path = config.index_path(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["topics"] == {}
    assert not path.with_name(path.name + ".tmp").exists()


def test_save_index_preserves_old_bytes_on_replace_failure(tmp_path, monkeypatch):
    _init(tmp_path)
    path = config.index_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = wiki_index.serialize(wiki_index.empty_schema())
    path.write_text(original, encoding="utf-8")

    def boom(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(wiki_index.IndexWriteError):
        wiki_index.save_index(tmp_path, {"version": 1, "generated_at": "x", "topics": {"new": {}}})
    assert path.read_text(encoding="utf-8") == original


# --- 1.5 resilient partial rebuild -----------------------------------------

def test_frontmatter_parse_error_is_reported_not_fatal(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "ok.md", {"title": "ok"})
    (config.topics_dir(tmp_path) / "bad.md").write_text("---\nkey: [\n---\nbody", encoding="utf-8")
    data, errors = wiki_index.rebuild(tmp_path)
    assert "ok.md" in data["topics"]
    assert "bad.md" not in data["topics"]
    assert {"path": "bad.md", "error": "frontmatter_parse_failed"} in errors


def test_decode_error_is_reported(tmp_path):
    _init(tmp_path)
    (config.topics_dir(tmp_path) / "raw.md").write_bytes(b"\xff\xfe\x00bad")
    data, errors = wiki_index.rebuild(tmp_path)
    assert {"path": "raw.md", "error": "topic_decode_failed"} in errors
    assert data["topics"] == {}


def test_normalized_path_collision_is_fatal(tmp_path):
    _init(tmp_path)
    topics = config.topics_dir(tmp_path)
    (topics / unicodedata.normalize("NFC", "café.md")).write_bytes(
        frontmatter.dump({"title": "c"}, "b").encode("utf-8"))
    nfd_name = unicodedata.normalize("NFD", "café.md")
    nfd_path = topics / nfd_name
    if nfd_path.name == unicodedata.normalize("NFC", "café.md"):
        pytest.skip("filesystem normalizes unicode filenames")
    nfd_path.write_bytes(frontmatter.dump({"title": "c2"}, "b").encode("utf-8"))
    with pytest.raises(wiki_index.NormalizedPathCollisionError) as exc:
        wiki_index.rebuild(tmp_path)
    assert exc.value.path == "café.md"


def test_incremental_rebuild(tmp_path):
    """Incremental rebuild reuses existing index and doesn't crash."""
    _init(tmp_path)

    # Create initial topics
    _topic(tmp_path, "topic1.md", {"title": "Topic 1"}, "Initial content")
    _topic(tmp_path, "topic2.md", {"title": "Topic 2"}, "More content")

    # Full rebuild
    data1, errors1 = wiki_index.rebuild(tmp_path, incremental=False)
    assert len(data1["topics"]) == 2
    assert len(errors1) == 0

    # Save index
    wiki_index.save_index(tmp_path, data1)

    # Incremental rebuild with no changes should succeed
    data2, errors2 = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data2["topics"]) == 2
    assert len(errors2) == 0

    # Add new topic
    _topic(tmp_path, "topic3.md", {"title": "Topic 3"}, "New topic")

    # Incremental rebuild should pick up new topic
    data3, errors3 = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data3["topics"]) == 3
    assert len(errors3) == 0
    assert "topic3.md" in data3["topics"]


def test_incremental_rebuild_without_existing_index(tmp_path):
    """Incremental rebuild falls back to full rebuild if index missing."""
    _init(tmp_path)
    _topic(tmp_path, "topic1.md", {"title": "Topic 1"}, "Content")

    # Incremental rebuild without saved index should not crash
    data, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data["topics"]) == 1
    assert len(errors) == 0


def test_incremental_rebuild_with_corrupted_index(tmp_path):
    """Incremental rebuild falls back to full rebuild if index corrupted."""
    _init(tmp_path)
    _topic(tmp_path, "topic1.md", {"title": "Topic 1"}, "Content")

    # Create corrupted index file
    index_path = config.index_path(tmp_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("not valid json", encoding="utf-8")

    # Incremental rebuild should fall back to full rebuild
    data, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data["topics"]) == 1
    assert len(errors) == 0


# --- 1.6 mtime-based incremental reuse ---------------------------------------

def test_incremental_skips_parse_for_unchanged_files(tmp_path, monkeypatch):
    """Unchanged files are reused from the existing index without re-parsing."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "A"})
    _topic(tmp_path, "b.md", {"title": "B"})
    data1, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data1)

    def boom(text):
        raise AssertionError("unchanged file was re-parsed")

    monkeypatch.setattr(wiki_index.frontmatter, "parse", boom)
    data2, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert errors == []
    assert data2["topics"] == data1["topics"]




def test_incremental_reparses_changed_file_only(tmp_path, monkeypatch):
    """Only the changed file is re-parsed; unchanged entries are reused."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "A"})
    b = _topic(tmp_path, "b.md", {"title": "B"})
    data1, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data1)

    parsed: list[str] = []
    real_parse = wiki_index.frontmatter.parse

    def spy(text):
        parsed.append(text)
        return real_parse(text)

    monkeypatch.setattr(wiki_index.frontmatter, "parse", spy)
    b.write_text(frontmatter.dump({"title": "B2"}, "changed"), encoding="utf-8")
    data2, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert errors == []
    assert data2["topics"]["b.md"]["title"] == "B2"
    assert data2["topics"]["a.md"] == data1["topics"]["a.md"]
    assert len(parsed) == 1
    assert "changed" in parsed[0]


def test_legacy_entry_without_mtime_is_reparsed(tmp_path):
    """Index entries saved before mtime tracking are re-parsed once."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "A"})
    data1, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data1)

    legacy = json.loads(config.index_path(tmp_path).read_text(encoding="utf-8"))
    legacy_entry = legacy["topics"]["a.md"]
    del legacy_entry["mtime_ns"]
    config.index_path(tmp_path).write_text(json.dumps(legacy), encoding="utf-8")

    data2, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert errors == []
    assert "mtime_ns" in data2["topics"]["a.md"]
    assert data2["topics"]["a.md"]["mtime_ns"] > 0


def test_incremental_with_null_index_falls_back(tmp_path):
    """A JSON-null index file must not crash incremental rebuild; it falls back to full."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"})
    index_path = config.index_path(tmp_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("null", encoding="utf-8")
    data, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data["topics"]) == 1
    assert errors == []


def test_incremental_with_array_index_falls_back(tmp_path):
    """A JSON-array index file must not crash incremental rebuild."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"})
    index_path = config.index_path(tmp_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("[1, 2, 3]", encoding="utf-8")
    data, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert len(data["topics"]) == 1
    assert errors == []


def test_incremental_non_dict_entry_is_reparsed(tmp_path):
    """A corrupt (non-dict) cached entry is re-parsed instead of crashing or being reused."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"})
    data1, _ = wiki_index.rebuild(tmp_path)
    data1["topics"]["A.md"] = "not a dict"
    wiki_index.save_index(tmp_path, data1)
    data2, errors = wiki_index.rebuild(tmp_path, incremental=True)
    assert errors == []
    assert isinstance(data2["topics"]["A.md"], dict)
    assert data2["topics"]["A.md"]["title"] == "A"
