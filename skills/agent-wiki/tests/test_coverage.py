"""Tests for coverage and gap reporting."""

import json
from pathlib import Path

import pytest

from agent_wiki import config, frontmatter, wiki_index


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _source(vault: Path, rel_path: str, content: str = "# Source") -> Path:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _init(vault: Path) -> None:
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


# --- 2.5 Coverage tests ---


def test_coverage_reports_covered_and_gaps(tmp_path):
    """coverage distinguishes covered sources from gaps."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "notes/covered.md", "Covered source.")
    _source(tmp_path, "notes/gap.md", "Uncovered gap.")

    _topic(tmp_path, "topic.md", {"title": "Topic", "sources": ["notes/covered.md"]}, "Content.")

    result = coverage.compute_coverage(tmp_path)

    assert result["ok"] is True
    assert result["covered"] == 1
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["path"] == "notes/gap.md"


def test_coverage_partition_scan_set(tmp_path):
    """covered + gaps = scan set (disjoint)."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "a.md", "A")
    _source(tmp_path, "b.md", "B")
    _source(tmp_path, "c.md", "C")

    _topic(tmp_path, "t1.md", {"title": "T1", "sources": ["a.md"]}, "Content.")
    _topic(tmp_path, "t2.md", {"title": "T2", "sources": ["b.md"]}, "Content.")

    result = coverage.compute_coverage(tmp_path)

    # a.md, b.md covered; c.md gap
    assert result["covered"] == 2
    assert len(result["gaps"]) == 1


def test_coverage_ratio_bounds(tmp_path):
    """coverage_ratio ∈ [0, 1]."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "source.md", "Source.")

    # 0% coverage
    result_zero = coverage.compute_coverage(tmp_path)
    assert 0.0 <= result_zero["coverage_ratio"] <= 1.0

    # 100% coverage
    _topic(tmp_path, "topic.md", {"title": "Topic", "sources": ["source.md"]}, "Content.")
    result_full = coverage.compute_coverage(tmp_path)
    assert result_full["coverage_ratio"] == 1.0


def test_coverage_empty_scan_set_is_one(tmp_path):
    """coverage_ratio = 1.0 when scan set empty (vacuously covered)."""
    from agent_wiki import coverage

    _init(tmp_path)
    # No sources

    result = coverage.compute_coverage(tmp_path)

    assert result["coverage_ratio"] == 1.0


def test_coverage_is_read_only(tmp_path):
    """coverage does not modify any files."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "source.md", "Source.")

    before_files = {f: f.read_bytes() for f in tmp_path.rglob("*.md")}

    coverage.compute_coverage(tmp_path)

    after_files = {f: f.read_bytes() for f in tmp_path.rglob("*.md")}

    assert before_files == after_files


def test_coverage_requires_initialized_wiki(tmp_path):
    """coverage fails when wiki/ missing."""
    from agent_wiki import coverage

    # No wiki/ directory

    with pytest.raises(Exception) as exc_info:
        coverage.compute_coverage(tmp_path)

    assert "wiki_not_initialized" in str(exc_info.value).lower() or not (tmp_path / "wiki").exists()


def test_coverage_nfc_normalized_matching(tmp_path):
    """coverage matches by NFC-normalized paths."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "café.md", "Source.")  # NFC form

    _topic(tmp_path, "topic.md", {"title": "Topic", "sources": ["café.md"]}, "Content.")

    result = coverage.compute_coverage(tmp_path)

    # Should match despite Unicode normalization
    assert result["covered"] == 1
    assert len(result["gaps"]) == 0


def test_coverage_gaps_nfc_sorted(tmp_path):
    """gaps list is NFC-sorted."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "z.md", "Z")
    _source(tmp_path, "a.md", "A")
    _source(tmp_path, "m.md", "M")

    result = coverage.compute_coverage(tmp_path)

    gap_paths = [g["path"] for g in result["gaps"]]
    assert gap_paths == sorted(gap_paths)


def test_coverage_deterministic(tmp_path):
    """coverage output identical across runs."""
    from agent_wiki import coverage

    _init(tmp_path)
    _source(tmp_path, "a.md", "A")
    _source(tmp_path, "b.md", "B")

    result1 = coverage.compute_coverage(tmp_path)
    result2 = coverage.compute_coverage(tmp_path)

    assert result1["gaps"] == result2["gaps"]
    assert result1["coverage_ratio"] == result2["coverage_ratio"]


# --- 6.3 Property-based / invariant tests (coverage) ---


def test_coverage_partition_invariant(tmp_path):
    """INVARIANT: covered ∪ gaps == scan_set, covered ∩ gaps == ∅."""
    from agent_wiki import coverage, scanner

    _init(tmp_path)
    _source(tmp_path, "notes/a.md", "A")
    _source(tmp_path, "notes/b.md", "B")
    _source(tmp_path, "notes/c.md", "C")
    _source(tmp_path, "docs/d.md", "D")

    _topic(tmp_path, "t1.md", {"title": "T1", "sources": ["notes/a.md", "docs/d.md"]}, "Content.")
    _topic(tmp_path, "t2.md", {"title": "T2", "sources": ["notes/b.md"]}, "Content.")

    result = coverage.compute_coverage(tmp_path)

    # Get actual scan set (convert Path to string for comparison)
    scan_set = {str(p.relative_to(tmp_path)).replace("\\", "/") for p in scanner.walk_sources(tmp_path)}

    # Build covered set from all topic sources
    data, _ = wiki_index.rebuild(tmp_path)
    covered_set = set()
    for kind in ["topics", "queries"]:
        for entry in data.get(kind, {}).values():
            for src in entry.get("sources", []):
                if src.endswith(".md"):
                    covered_set.add(src)

    # Build gaps set
    gaps_set = {g["path"] for g in result["gaps"]}

    # INVARIANT 1: covered ∪ gaps == scan_set
    union = covered_set | gaps_set
    assert union == scan_set

    # INVARIANT 2: covered ∩ gaps == ∅
    intersection = covered_set & gaps_set
    assert len(intersection) == 0

    # INVARIANT 3: result counts match
    assert result["covered"] == len(covered_set)
    assert len(result["gaps"]) == len(gaps_set)


def test_coverage_ratio_bounds_comprehensive(tmp_path):
    """INVARIANT: coverage_ratio ∈ [0, 1] for all scenarios."""
    from agent_wiki import coverage

    _init(tmp_path)

    # Empty scan set => 1.0
    result_empty = coverage.compute_coverage(tmp_path)
    assert result_empty["coverage_ratio"] == 1.0

    # All gaps => 0.0
    _source(tmp_path, "gap1.md", "Gap 1")
    _source(tmp_path, "gap2.md", "Gap 2")
    result_zero = coverage.compute_coverage(tmp_path)
    assert result_zero["coverage_ratio"] == 0.0

    # Partial coverage => (0, 1)
    _topic(tmp_path, "t1.md", {"title": "T1", "sources": ["gap1.md"]}, "Content.")
    result_partial = coverage.compute_coverage(tmp_path)
    assert 0.0 < result_partial["coverage_ratio"] < 1.0

    # Full coverage => 1.0
    _topic(tmp_path, "t2.md", {"title": "T2", "sources": ["gap2.md"]}, "Content.")
    result_full = coverage.compute_coverage(tmp_path)
    assert result_full["coverage_ratio"] == 1.0
