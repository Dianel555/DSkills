"""Tests for quality CLI subcommand."""

import json
from pathlib import Path

import pytest
from agent_wiki import commands, config, frontmatter


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


class Args:
    """Mock argparse args."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


# --- 1.4 quality subcommand tests ---


def test_quality_subcommand_emits_tiers_and_metrics(tmp_path, capsys):
    """quality subcommand outputs tiers dict, distribution, and errors."""
    _init(tmp_path)

    # Create topics with different quality levels
    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Just a line.")
    _topic(tmp_path, "basic.md", {"title": "Basic"}, "## Section\n\nSome content here.")
    _topic(tmp_path, "standard.md", {"title": "Standard"},
           "## S1\n## S2\n\n" + ("Prose content. " * 50))

    args = Args(vault=str(tmp_path))
    commands.cmd_quality(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert result["ok"] is True
    assert "tiers" in result
    assert "distribution" in result
    assert "errors" in result

    # Check tiers structure
    assert "stub.md" in result["tiers"]
    assert result["tiers"]["stub.md"]["tier"] == "stub"
    assert "metrics" in result["tiers"]["stub.md"]

    assert "basic.md" in result["tiers"]
    assert result["tiers"]["basic.md"]["tier"] == "basic"

    assert "standard.md" in result["tiers"]
    assert result["tiers"]["standard.md"]["tier"] == "standard"

    # Check distribution
    dist = result["distribution"]
    assert all(tier in dist for tier in ["stub", "basic", "standard", "rich", "premium"])
    assert dist["stub"] == 1
    assert dist["basic"] == 1
    assert dist["standard"] == 1
    assert dist["rich"] == 0
    assert dist["premium"] == 0


def test_quality_includes_has_lead_in_metrics(tmp_path, capsys):
    """quality subcommand includes has_lead metric."""
    _init(tmp_path)

    _topic(tmp_path, "with_lead.md", {"title": "With Lead"},
           "This is a lead sentence.\n\n## Section\n\nContent.")
    _topic(tmp_path, "no_lead.md", {"title": "No Lead"},
           "## Section\n\nStarts with heading.")

    args = Args(vault=str(tmp_path))
    commands.cmd_quality(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert result["tiers"]["with_lead.md"]["metrics"]["has_lead"] is True
    assert result["tiers"]["no_lead.md"]["metrics"]["has_lead"] is False


def test_quality_requires_initialized_wiki(tmp_path, capsys):
    """quality fails when wiki/ does not exist."""
    # Don't initialize - no wiki/ directory
    args = Args(vault=str(tmp_path))

    with pytest.raises(SystemExit) as exc_info:
        commands.cmd_quality(args)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    result = json.loads(captured.err)

    assert result["error"] == "wiki_not_initialized"
    assert "hint" in result


def test_quality_reports_malformed_topics_in_errors(tmp_path, capsys):
    """Malformed topics excluded from tiers/distribution, reported in errors."""
    _init(tmp_path)

    # Valid topic
    _topic(tmp_path, "valid.md", {"title": "Valid"}, "Content here.")

    # Malformed frontmatter
    bad = config.topics_dir(tmp_path) / "bad.md"
    bad.write_text("---\ntitle: [\n---\nBody", encoding="utf-8")

    # Non-UTF8
    binary = config.topics_dir(tmp_path) / "binary.md"
    binary.write_bytes(b"\xff\xfe Invalid UTF-8")

    args = Args(vault=str(tmp_path))
    commands.cmd_quality(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    # Valid topic scored
    assert "valid.md" in result["tiers"]

    # Malformed topics not scored
    assert "bad.md" not in result["tiers"]
    assert "binary.md" not in result["tiers"]

    # Errors reported
    assert len(result["errors"]) == 2
    error_paths = {e["path"] for e in result["errors"]}
    assert "bad.md" in error_paths
    assert "binary.md" in error_paths


def test_quality_is_read_only(tmp_path, capsys):
    """quality subcommand does not modify any files."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## Section\n\nContent.")

    # Capture file states before
    topics_dir = config.topics_dir(tmp_path)
    before_files = {f.name: (f.stat().st_mtime_ns, f.read_bytes())
                    for f in topics_dir.glob("*.md")}

    args = Args(vault=str(tmp_path))
    commands.cmd_quality(args)

    # Check file states after
    after_files = {f.name: (f.stat().st_mtime_ns, f.read_bytes())
                   for f in topics_dir.glob("*.md")}

    assert before_files == after_files  # No files modified


def test_quality_handles_empty_topics_directory(tmp_path, capsys):
    """quality works with zero topics."""
    _init(tmp_path)
    # No topics created

    args = Args(vault=str(tmp_path))
    commands.cmd_quality(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert result["ok"] is True
    assert result["tiers"] == {}
    assert all(count == 0 for count in result["distribution"].values())
    assert result["errors"] == []
