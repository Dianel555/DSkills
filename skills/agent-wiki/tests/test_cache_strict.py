import json
import os

import pytest

from agent_wiki import cache


def test_save_raises_cache_conflict_when_expected_signature_changes(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    target = wiki / ".wiki-cache.json"
    target.write_text('{"version": 1, "sources": {}}', encoding="utf-8")
    expected = cache.file_signature(target)
    target.write_text('{"version": 1, "sources": {"newer.md": {}}}', encoding="utf-8")

    with pytest.raises(cache.CacheConflictError):
        cache.save(tmp_path, {"version": 1, "sources": {"ours.md": {}}}, expected_signature=expected)

    assert "newer.md" in target.read_text(encoding="utf-8")


def test_save_raises_cache_not_writable_before_tmp_write(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    target = wiki / ".wiki-cache.json"
    target.write_text('{"version": 1, "sources": {}}', encoding="utf-8")
    monkeypatch.setattr(cache, "is_cache_writable", lambda path: False)

    with pytest.raises(cache.CacheNotWritableError):
        cache.save(tmp_path, {"version": 1, "sources": {"a.md": {}}})

    assert not (wiki / ".wiki-cache.json.tmp").exists()


def test_save_replace_failure_is_distinct_from_conflict(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    target = wiki / ".wiki-cache.json"
    target.write_text('{"version": 1, "sources": {}}', encoding="utf-8")
    expected = cache.file_signature(target)

    def fail_replace(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(cache.CacheReplaceError):
        cache.save(tmp_path, {"version": 1, "sources": {"a.md": {}}}, expected_signature=expected)


def test_load_with_signature_returns_signature(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".wiki-cache.json").write_text('{"version": 1, "sources": {}}', encoding="utf-8")

    data, signature = cache.load_with_signature(tmp_path)

    assert data == {"version": 1, "sources": {}}
    assert signature == cache.file_signature(wiki / ".wiki-cache.json")
