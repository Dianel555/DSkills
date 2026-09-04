"""Tests for worklist CLI subcommand."""

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


def test_worklist_cli_requires_initialized_wiki(tmp_path, capsys):
    """worklist CLI fails when wiki not initialized."""
    import agent_wiki_cli

    with pytest.raises(SystemExit) as exc_info:
        agent_wiki_cli.main(["worklist", "--vault", str(tmp_path)])

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    output = json.loads(captured.err)
    assert output["error"] == "wiki_not_initialized"


def test_worklist_cli_returns_wanted_and_stale(tmp_path, capsys):
    """worklist CLI returns wanted and stale lists."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Missing]].")
    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")

    # Save index
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    import agent_wiki_cli

    result = agent_wiki_cli.main(["worklist", "--vault", str(tmp_path)])
    assert result == 0

    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert output["ok"] is True
    assert "wanted" in output
    assert "stale" in output

    # Check wanted
    assert len(output["wanted"]) == 1
    assert output["wanted"][0]["target"] == "Missing"

    # Check stale
    stale_paths = [s["path"] for s in output["stale"]]
    assert "stub.md" in stale_paths
