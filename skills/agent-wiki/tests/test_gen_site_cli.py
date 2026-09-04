"""Tests for gen-site CLI subcommand and status site metrics."""

import json
from pathlib import Path

import pytest
from agent_wiki import config, frontmatter


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


def test_gen_site_cli_requires_initialized_wiki(tmp_path, capsys):
    """gen-site CLI fails when wiki not initialized."""
    import agent_wiki_cli

    with pytest.raises(SystemExit) as exc_info:
        agent_wiki_cli.main(["gen-site", "--vault", str(tmp_path)])

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    output = json.loads(captured.err)
    assert output["error"] == "wiki_not_initialized"


def test_gen_site_cli_generates_site(tmp_path, capsys):
    """gen-site CLI generates static site."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import agent_wiki_cli

    result = agent_wiki_cli.main(["gen-site", "--vault", str(tmp_path)])
    assert result == 0

    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert output["ok"] is True
    assert output["pages"] >= 1
    assert "out" in output
    assert isinstance(output["degraded"], bool)

    # Verify site directory exists
    site_dir = config.wiki_root(tmp_path) / "site"
    assert site_dir.exists()
    assert (site_dir / "index.html").exists()


def test_status_includes_site_exists(tmp_path, capsys):
    """status includes site_exists metric."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import agent_wiki_cli

    # Before gen-site
    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])
    captured = capsys.readouterr()
    result_before = json.loads(captured.out)

    assert "site_exists" in result_before
    assert result_before["site_exists"] is False

    # Generate site
    agent_wiki_cli.main(["gen-site", "--vault", str(tmp_path)])
    capsys.readouterr()  # Clear gen-site output

    # After gen-site
    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])
    captured = capsys.readouterr()
    result_after = json.loads(captured.out)

    assert result_after["site_exists"] is True


def test_status_includes_site_stale(tmp_path, capsys):
    """status includes site_stale metric."""
    _init(tmp_path)

    topic_path = _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import agent_wiki_cli

    # Generate site
    agent_wiki_cli.main(["gen-site", "--vault", str(tmp_path)])
    capsys.readouterr()  # Clear gen-site output

    # Check status - should not be stale
    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert "site_stale" in result
    assert result["site_stale"] is False

    # Touch topic to make it newer
    import time
    time.sleep(0.01)
    topic_path.touch()

    # Check status again - should be stale
    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])
    captured = capsys.readouterr()
    result_stale = json.loads(captured.out)

    assert result_stale["site_stale"] is True


def test_status_site_metrics_graceful_when_no_site(tmp_path, capsys):
    """status site metrics are graceful when site doesn't exist."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import agent_wiki_cli

    agent_wiki_cli.main(["status", "--vault", str(tmp_path)])
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert result["site_exists"] is False
    assert result["site_stale"] is False  # Not stale if doesn't exist
