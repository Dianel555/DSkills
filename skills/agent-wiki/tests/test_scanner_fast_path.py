"""Test scanner fast-path via mtime_ns+size signature."""

from pathlib import Path
from unittest.mock import patch

from agent_wiki import cache, scanner


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_signature_match_skips_hash(tmp_path):
    """Unchanged file (signature match) should not be hashed."""
    write(tmp_path / "unchanged.md", "content")
    file_path = tmp_path / "unchanged.md"
    st = file_path.stat()

    data = cache.empty_schema()
    cache.upsert(data, "unchanged.md", "fake-sha", st.st_mtime_ns, st.st_size, [])

    with patch("agent_wiki.cache.sha256_file") as mock_hash:
        mock_hash.side_effect = AssertionError("hash should not be called")
        result = scanner.classify(tmp_path, data)

    assert len(result["unchanged"]) == 1
    assert result["unchanged"][0]["path"] == "unchanged.md"
    assert len(result["new"]) == 0
    assert len(result["modified"]) == 0


def test_signature_miss_triggers_hash(tmp_path):
    """File with different mtime_ns or size triggers hash."""
    write(tmp_path / "modified.md", "new content")
    file_path = tmp_path / "modified.md"
    st = file_path.stat()

    data = cache.empty_schema()
    cache.upsert(data, "modified.md", "old-sha", st.st_mtime_ns - 1000000, st.st_size, [])

    result = scanner.classify(tmp_path, data)

    assert len(result["modified"]) == 1
    assert result["modified"][0]["path"] == "modified.md"
    assert "sha256" in result["modified"][0]


def test_legacy_cache_without_mtime_ns_triggers_hash(tmp_path):
    """Legacy cache entry without mtime_ns should trigger hash once."""
    write(tmp_path / "file.md", "content")

    data = cache.empty_schema()
    data["sources"]["file.md"] = {
        "sha256": cache.sha256_file(tmp_path / "file.md"),
        "mtime": 1234567890.5,
        "size": 7,
        "derived_topics": []
    }

    result = scanner.classify(tmp_path, data)

    assert len(result["unchanged"]) == 1
    item = result["unchanged"][0]
    assert "mtime_ns" in item
    assert item["sha256"] == cache.sha256_file(tmp_path / "file.md")


def test_touched_but_identical_content(tmp_path):
    """File with new mtime but same content should be unchanged."""
    write(tmp_path / "file.md", "content")
    file_path = tmp_path / "file.md"
    sha = cache.sha256_file(file_path)

    data = cache.empty_schema()
    old_st = file_path.stat()
    cache.upsert(data, "file.md", sha, old_st.st_mtime_ns - 1000000, old_st.st_size, [])

    result = scanner.classify(tmp_path, data)

    assert len(result["unchanged"]) == 1
    item = result["unchanged"][0]
    assert item["sha256"] == sha
    assert item["mtime_ns"] == old_st.st_mtime_ns


def test_new_file(tmp_path):
    """New file not in cache should be classified as new."""
    write(tmp_path / "new.md", "content")
    data = cache.empty_schema()

    result = scanner.classify(tmp_path, data)

    assert len(result["new"]) == 1
    assert result["new"][0]["path"] == "new.md"
    assert "sha256" in result["new"][0]
    assert "mtime_ns" in result["new"][0]


def test_deleted_file(tmp_path):
    """File in cache but not on disk should be deleted."""
    data = cache.empty_schema()
    cache.upsert(data, "deleted.md", "sha", 1234567890000000000, 10, ["topic.md"])

    result = scanner.classify(tmp_path, data)

    assert len(result["deleted"]) == 1
    assert result["deleted"][0]["path"] == "deleted.md"
