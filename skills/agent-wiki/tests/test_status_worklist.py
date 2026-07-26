"""Tests for status command worklist metrics."""

import json
from pathlib import Path

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


def test_status_includes_wanted_count(tmp_path, capsys):
    """status includes wanted_count metric."""
    _init(tmp_path)

    # Create topic with broken link
    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Missing1]] and [[Missing2]].")

    # Save index
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    import agent_wiki_cli

    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert "wanted_count" in result
    assert result["wanted_count"] == 2  # Missing1 and Missing2


def test_status_includes_stale_count(tmp_path, capsys):
    """status includes stale_count metric."""
    _init(tmp_path)

    # Create stub and basic topics (low tier)
    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")
    _topic(tmp_path, "basic.md", {"title": "Basic"}, "## Section\n\nSome content.")

    # Save index
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    import agent_wiki_cli

    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert "stale_count" in result
    assert result["stale_count"] == 2  # stub and basic


def test_status_worklist_counts_are_non_negative(tmp_path, capsys):
    """status worklist counts are always >= 0."""
    _init(tmp_path)

    # Empty vault
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    import agent_wiki_cli

    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert result["wanted_count"] >= 0
    assert result["stale_count"] >= 0


def test_status_worklist_metrics_graceful_on_error(tmp_path, capsys):
    """status worklist metrics gracefully fallback to 0 on errors."""
    _init(tmp_path)

    # Create topic but don't save index (will trigger some internal errors)
    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import agent_wiki_cli

    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    # Should have graceful fallback
    assert "wanted_count" in result
    assert "stale_count" in result
    assert isinstance(result["wanted_count"], int)
    assert isinstance(result["stale_count"], int)
