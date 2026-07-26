"""Tests for status command with quality metrics."""

import json
import subprocess
import sys
from pathlib import Path

from agent_wiki import config, frontmatter


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


# --- 1.7 Status with quality metrics tests ---


def test_status_includes_quality_distribution(tmp_path):
    """status output includes quality_distribution field."""
    _run_cli("init", "--vault", str(tmp_path))

    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")
    _topic(tmp_path, "basic.md", {"title": "Basic"}, "## Section\n\nSome prose content here.")
    _topic(tmp_path, "standard.md", {"title": "Standard"},
           "## S1\n## S2\n\n" + ("Prose content here. " * 40))

    result = _run_cli("status", "--vault", str(tmp_path))
    assert result.returncode == 0

    status = json.loads(result.stdout)
    assert "quality_distribution" in status

    dist = status["quality_distribution"]
    assert dist["stub"] == 1
    assert dist["basic"] == 1
    assert dist["standard"] == 1
    assert dist["rich"] == 0
    assert dist["premium"] == 0


def test_status_includes_featured_count(tmp_path):
    """status output includes featured_count field."""
    _run_cli("init", "--vault", str(tmp_path))

    _topic(tmp_path, "featured1.md", {"title": "Featured 1", "featured": True}, "Content.")
    _topic(tmp_path, "featured2.md", {"title": "Featured 2", "featured": True}, "Content.")
    _topic(tmp_path, "normal.md", {"title": "Normal"}, "Content.")

    result = _run_cli("status", "--vault", str(tmp_path))
    status = json.loads(result.stdout)

    assert "featured_count" in status
    assert status["featured_count"] == 2


def test_status_featured_count_zero_when_none(tmp_path):
    """featured_count is 0 when no topics are featured."""
    _run_cli("init", "--vault", str(tmp_path))

    _topic(tmp_path, "normal.md", {"title": "Normal"}, "Content.")

    result = _run_cli("status", "--vault", str(tmp_path))
    status = json.loads(result.stdout)

    assert status["featured_count"] == 0


def test_status_quality_metrics_non_negative(tmp_path):
    """All quality-related counts are non-negative."""
    _run_cli("init", "--vault", str(tmp_path))

    result = _run_cli("status", "--vault", str(tmp_path))
    status = json.loads(result.stdout)

    dist = status["quality_distribution"]
    assert all(count >= 0 for count in dist.values())
    assert status["featured_count"] >= 0


def test_status_never_writes_files(tmp_path):
    """status command does not create or modify any files."""
    _run_cli("init", "--vault", str(tmp_path))

    _topic(tmp_path, "topic.md", {"title": "Topic", "featured": True},
           "## Section\n\nContent.")

    # Capture file state before
    topics_dir = config.topics_dir(tmp_path)
    before_files = {f.name: (f.stat().st_mtime_ns, f.read_bytes())
                    for f in topics_dir.glob("*.md")}

    # Run status
    result = _run_cli("status", "--vault", str(tmp_path))
    assert result.returncode == 0

    # Check file state after
    after_files = {f.name: (f.stat().st_mtime_ns, f.read_bytes())
                   for f in topics_dir.glob("*.md")}

    assert before_files == after_files  # No files modified


def test_status_handles_malformed_topics_gracefully(tmp_path):
    """status reports quality metrics even with some malformed topics."""
    _run_cli("init", "--vault", str(tmp_path))

    # Valid topics
    _topic(tmp_path, "valid1.md", {"title": "Valid 1", "featured": True}, "Content.")
    _topic(tmp_path, "valid2.md", {"title": "Valid 2"}, "## Section\n\nMore content.")

    # Malformed topic
    bad = config.topics_dir(tmp_path) / "bad.md"
    bad.write_text("---\ntitle: [\n---\nBody", encoding="utf-8")

    result = _run_cli("status", "--vault", str(tmp_path))
    status = json.loads(result.stdout)

    # Should still report metrics for valid topics
    assert status["featured_count"] == 1
    assert status["quality_distribution"]["stub"] >= 0

    # Malformed topic should be in index_errors
    assert any(e["path"] == "bad.md" for e in status.get("index_errors", []))


def test_status_quality_metrics_computed_from_in_memory_rebuild(tmp_path):
    """status computes quality metrics from in-memory rebuild, not saved index."""
    _run_cli("init", "--vault", str(tmp_path))

    _topic(tmp_path, "topic.md", {"title": "Topic", "featured": True},
           "## Section\n\nContent.")

    # Delete the saved index to ensure status rebuilds in-memory
    index_file = config.index_path(tmp_path)
    if index_file.exists():
        index_file.unlink()

    result = _run_cli("status", "--vault", str(tmp_path))
    status = json.loads(result.stdout)

    # Should still have quality metrics
    assert "quality_distribution" in status
    assert "featured_count" in status
    assert status["featured_count"] == 1
