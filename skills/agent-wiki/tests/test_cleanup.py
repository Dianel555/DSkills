from datetime import date

from agent_wiki import cleanup, config, frontmatter


def write_topic(vault, name, sources, body="# Topic\n"):
    topic = config.topics_dir(vault) / name
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text(frontmatter.dump({"title": name, "sources": sources}, body), encoding="utf-8")
    return topic


def test_remove_source_from_topic_keeps_remaining_sources(tmp_path):
    topic = write_topic(tmp_path, "T.md", ["a.md", "b.md"])

    has_sources = cleanup.remove_source_from_topic(topic, "a.md")

    meta, body = frontmatter.parse(topic.read_text(encoding="utf-8"))
    assert has_sources is True
    assert meta["sources"] == ["b.md"]
    assert body == "# Topic\n"


def test_remove_source_from_topic_returns_false_when_orphaned(tmp_path):
    topic = write_topic(tmp_path, "T.md", ["a.md"])

    assert cleanup.remove_source_from_topic(topic, "a.md") is False


def test_archive_topic_moves_to_date_directory(tmp_path):
    topic = write_topic(tmp_path, "T.md", [])

    archived = cleanup.archive_topic(topic, config.archive_dir(tmp_path), date(2026, 6, 4))

    assert archived == config.archive_dir(tmp_path) / "2026-06-04" / "T.md"
    assert archived.exists()
    assert not topic.exists()
