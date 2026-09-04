"""Tests for the doctor health-check module."""

from pathlib import Path

from agent_wiki import config, doctor, frontmatter, wiki_index


def _init(vault: Path) -> None:
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def _topic(vault: Path, name: str, meta: dict) -> Path:
    path = config.topics_dir(vault) / name
    path.write_text(frontmatter.dump(meta, "body"), encoding="utf-8")
    return path


def _indexed(vault: Path) -> None:
    data, _ = wiki_index.rebuild(vault)
    wiki_index.save_index(vault, data)


def test_uninitialized_vault_fails(tmp_path):
    report = doctor.run(tmp_path)
    assert report["ok"] is False
    assert report["checks"][0] == {
        "name": "wiki_initialized",
        "status": "error",
        "detail": "wiki/ missing — run init",
    }


def test_healthy_vault_passes(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A", "sources": ["a.md"]})
    _indexed(tmp_path)
    report = doctor.run(tmp_path)
    assert report["ok"] is True
    assert report["summary"] == "healthy"
    assert all(check["status"] == "ok" for check in report["checks"])


def test_orphan_topic_warns_but_passes(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"})
    _indexed(tmp_path)
    report = doctor.run(tmp_path)
    names = {check["name"]: check for check in report["checks"]}
    assert names["orphan_topics"]["status"] == "warn"
    assert report["ok"] is True


def test_unreadable_topic_errors(tmp_path):
    _init(tmp_path)
    (config.topics_dir(tmp_path) / "bad.md").write_text("---\nkey: [\n---\nbody", encoding="utf-8")
    _indexed(tmp_path)
    report = doctor.run(tmp_path)
    names = {check["name"]: check for check in report["checks"]}
    assert names["topics"]["status"] == "error"
    assert names["index_consistent"]["status"] == "error"
    assert report["ok"] is False


def test_corrupted_index_errors(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A", "sources": ["a.md"]})
    config.index_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    config.index_path(tmp_path).write_text("not json", encoding="utf-8")
    report = doctor.run(tmp_path)
    names = {check["name"]: check for check in report["checks"]}
    assert names["index"]["status"] == "error"
    assert report["ok"] is False


def test_deleted_topic_makes_index_stale(tmp_path):
    """A topic deleted after the index was built must surface as index_fresh warn."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A", "sources": ["a.md"]})
    _topic(tmp_path, "B.md", {"title": "B", "sources": ["b.md"]})
    _indexed(tmp_path)
    (config.topics_dir(tmp_path) / "B.md").unlink()
    report = doctor.run(tmp_path)
    names = {c["name"]: c for c in report["checks"]}
    assert names["index_fresh"]["status"] == "warn"


def test_cache_null_json_is_error(tmp_path):
    """A cache file containing JSON null must be reported as a cache error, not silently skipped."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A", "sources": ["a.md"]})
    _indexed(tmp_path)
    cache_file = config.cache_path(tmp_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("null", encoding="utf-8")
    report = doctor.run(tmp_path)
    names = {c["name"]: c for c in report["checks"]}
    assert names["cache"]["status"] == "error"
    assert report["ok"] is False


def test_cache_array_json_is_error(tmp_path):
    """A cache file containing a JSON array must be reported as a cache error."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A", "sources": ["a.md"]})
    _indexed(tmp_path)
    cache_file = config.cache_path(tmp_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("[1, 2, 3]", encoding="utf-8")
    report = doctor.run(tmp_path)
    names = {c["name"]: c for c in report["checks"]}
    assert names["cache"]["status"] == "error"
