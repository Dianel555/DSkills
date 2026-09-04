import json
import os

import pytest
from agent_wiki import cache


def test_load_missing_returns_empty_schema(tmp_path):
    assert cache.load(tmp_path) == cache.empty_schema()


def test_load_corrupt_json_degrades_to_empty_schema(tmp_path, capsys):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".wiki-cache.json").write_text("not-json", encoding="utf-8")

    assert cache.load(tmp_path) == cache.empty_schema()
    assert json.loads(capsys.readouterr().err)["warning"] == "cache_parse_failed"


def test_save_is_atomic_and_round_trips(tmp_path):
    data = cache.empty_schema()
    cache.upsert(data, "笔记/a.md", "abc", 1500000000000000000, 12, ["topic.md"])

    cache.save(tmp_path, data)

    assert cache.load(tmp_path)["sources"]["笔记/a.md"]["sha256"] == "abc"
    assert not (tmp_path / "wiki" / ".wiki-cache.json.tmp").exists()


def test_save_replace_failure_leaves_existing_cache(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    target = wiki / ".wiki-cache.json"
    target.write_text('{"version": 1, "sources": {}}', encoding="utf-8")

    def fail_replace(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(cache.CacheWriteError):
        cache.save(tmp_path, {"version": 1, "sources": {"a.md": {}}})

    assert target.read_text(encoding="utf-8") == '{"version": 1, "sources": {}}'


def test_sha256_file_streams_content(tmp_path):
    path = tmp_path / "empty.md"
    path.write_bytes(b"")

    assert cache.sha256_file(path) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_stat_signature_and_remove(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("hello", encoding="utf-8")
    mtime, size = cache.stat_signature(path)
    data = cache.empty_schema()

    cache.upsert(data, "note.md", "sha", mtime, size, [])
    assert data["sources"]["note.md"]["size"] == 5

    cache.remove(data, "note.md")
    assert "note.md" not in data["sources"]
