"""Tests for worklist.py - wanted and stale topic identification."""

import json
from pathlib import Path

import pytest
from agent_wiki import config, frontmatter, wiki_index, worklist


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


# --- 4.1 Worklist tests ---


def test_wanted_lists_broken_link_targets(tmp_path):
    """wanted lists wikilink targets with no matching page."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Content linking [[B]] and [[C]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Target exists.")

    result = worklist.compute_worklist(tmp_path)

    # C is wanted (no matching page), B is not (page exists)
    assert len(result["wanted"]) == 1
    assert result["wanted"][0]["target"] == "C"


def test_wanted_ranked_by_inbound_descending(tmp_path):
    """wanted targets are ranked by descending inbound link count."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[X]] and [[Y]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Links [[Y]] and [[Z]].")
    _topic(tmp_path, "C.md", {"title": "C"}, "Links [[Y]].")

    result = worklist.compute_worklist(tmp_path)

    # Y has 3 inbound, X and Z have 1 each
    assert result["wanted"][0]["target"] == "Y"
    assert result["wanted"][0]["inbound"] == 3


def test_wanted_inbound_equals_linked_from_length(tmp_path):
    """wanted inbound count equals length of linked_from array."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Target]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Links [[Target]].")

    result = worklist.compute_worklist(tmp_path)

    wanted_target = result["wanted"][0]
    assert wanted_target["target"] == "Target"
    assert wanted_target["inbound"] == 2
    assert len(wanted_target["linked_from"]) == 2
    assert wanted_target["inbound"] == len(wanted_target["linked_from"])


def test_wanted_secondary_sort_by_target_nfc_ascending(tmp_path):
    """wanted targets with same inbound count are sorted by NFC target ascending."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Zebra]] and [[Apple]].")

    result = worklist.compute_worklist(tmp_path)

    # Both have inbound=1, sorted by target name
    assert result["wanted"][0]["target"] == "Apple"
    assert result["wanted"][1]["target"] == "Zebra"


def test_wanted_linked_from_sorted(tmp_path):
    """wanted linked_from array is NFC-sorted."""
    _init(tmp_path)

    _topic(tmp_path, "Z.md", {"title": "Z"}, "Links [[Target]].")
    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Target]].")
    _topic(tmp_path, "M.md", {"title": "M"}, "Links [[Target]].")

    result = worklist.compute_worklist(tmp_path)

    linked_from = result["wanted"][0]["linked_from"]
    assert linked_from == ["A.md", "M.md", "Z.md"]


def test_wanted_target_satisfied_by_any_page_type(tmp_path):
    """A target is satisfied if a topic or query page matches its stem."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[TopicExists]], [[QueryExists]], [[Missing]].")
    _topic(tmp_path, "TopicExists.md", {"title": "Topic"}, "Content.")

    # Create query page
    queries = config.queries_dir(tmp_path)
    queries.mkdir(parents=True, exist_ok=True)
    (queries / "QueryExists.md").write_text(frontmatter.dump({"title": "Query"}, "Content."), encoding="utf-8")

    result = worklist.compute_worklist(tmp_path)

    # Only "Missing" should be wanted
    assert len(result["wanted"]) == 1
    assert result["wanted"][0]["target"] == "Missing"


def test_stale_includes_low_tier_topics(tmp_path):
    """stale includes topics with tier stub or basic."""
    _init(tmp_path)

    stub_body = "Short."
    basic_body = "## Section\n\nSome content here."
    standard_body = "## S1\n## S2\n\n" + ("Prose content here. " * 40)  # ~800 chars for standard tier

    _topic(tmp_path, "stub.md", {"title": "Stub"}, stub_body)
    _topic(tmp_path, "basic.md", {"title": "Basic"}, basic_body)
    _topic(tmp_path, "standard.md", {"title": "Standard"}, standard_body)

    # Save index so topics are not index-stale
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    result = worklist.compute_worklist(tmp_path)

    stale_paths = [s["path"] for s in result["stale"]]
    assert "stub.md" in stale_paths
    assert "basic.md" in stale_paths
    assert "standard.md" not in stale_paths


def test_stale_reason_low_tier_for_stub_basic(tmp_path):
    """stale topics with tier stub/basic have reason: low_tier."""
    _init(tmp_path)

    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")

    result = worklist.compute_worklist(tmp_path)

    stale_item = next(s for s in result["stale"] if s["path"] == "stub.md")
    assert stale_item["reason"] == "low_tier"
    assert stale_item["tier"] in ["stub", "basic"]


def test_stale_includes_topics_newer_than_index(tmp_path):
    """stale includes topics modified after index."""
    _init(tmp_path)

    # Create topic with standard tier (not low_tier)
    topic_path = _topic(tmp_path, "topic.md", {"title": "Topic"}, "## S1\n## S2\n\n" + ("Prose content here. " * 40))
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    # Touch the topic to make it newer
    import time
    time.sleep(0.01)
    topic_path.touch()

    result = worklist.compute_worklist(tmp_path)

    # Should be stale due to mtime
    stale_item = next((s for s in result["stale"] if s["path"] == "topic.md"), None)
    assert stale_item is not None
    assert stale_item["reason"] == "index_stale"


def test_stale_index_absent_means_all_topics_stale(tmp_path):
    """When index is absent, all topics are stale with reason index_stale."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## S1\n## S2\n\n" + ("Prose content here. " * 40))

    # Don't save index
    result = worklist.compute_worklist(tmp_path)

    stale_item = next(s for s in result["stale"] if s["path"] == "topic.md")
    assert stale_item["reason"] == "index_stale"


def test_stale_reason_precedence_low_tier_over_index_stale(tmp_path):
    """When both conditions hold, reason is low_tier (precedence)."""
    _init(tmp_path)

    # Create stub topic (low tier)
    topic_path = _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")

    # Build and save index
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    # Touch topic to make it index-stale
    import time
    time.sleep(0.01)
    topic_path.touch()

    result = worklist.compute_worklist(tmp_path)

    stale_item = next(s for s in result["stale"] if s["path"] == "stub.md")
    # low_tier takes precedence
    assert stale_item["reason"] == "low_tier"


def test_worklist_is_deterministic(tmp_path):
    """Running worklist twice produces identical output."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[X]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Links [[X]].")
    _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")

    result1 = worklist.compute_worklist(tmp_path)
    result2 = worklist.compute_worklist(tmp_path)

    # Serialize and compare
    assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)


def test_worklist_is_read_only(tmp_path):
    """worklist does not modify any files."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Missing]].")

    # Snapshot filesystem
    before_files = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}

    worklist.compute_worklist(tmp_path)

    # Check nothing changed
    after_files = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    assert before_files == after_files


def test_worklist_requires_initialized_wiki(tmp_path):
    """worklist raises error when wiki not initialized."""
    # Don't initialize
    with pytest.raises(ValueError, match="wiki_not_initialized"):
        worklist.compute_worklist(tmp_path)


# --- 6.3 Property-based / invariant tests (worklist) ---


def test_worklist_wanted_total_order_stability(tmp_path):
    """INVARIANT: wanted list has stable total order (inbound desc → target asc → linked_from sorted)."""
    _init(tmp_path)

    # Create complex link graph
    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[High]] [[Mid]] [[Low1]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Links [[High]] [[Mid]] [[Low2]].")
    _topic(tmp_path, "C.md", {"title": "C"}, "Links [[High]].")
    _topic(tmp_path, "D.md", {"title": "D"}, "Links [[Low1]].")

    # Expected order:
    # - High: 3 inbound
    # - Mid: 2 inbound
    # - Low1: 2 inbound (but "Low1" < "Low2" alphabetically)
    # - Low2: 1 inbound

    result = worklist.compute_worklist(tmp_path)

    targets = [w["target"] for w in result["wanted"]]
    inbounds = [w["inbound"] for w in result["wanted"]]

    # Primary sort: inbound descending
    assert targets[0] == "High"
    assert inbounds[0] == 3

    # Secondary sort: among equal inbound, NFC target ascending
    mid_low1_low2 = [(w["target"], w["inbound"]) for w in result["wanted"] if w["inbound"] <= 2]
    for i in range(len(mid_low1_low2) - 1):
        if mid_low1_low2[i][1] == mid_low1_low2[i + 1][1]:  # Same inbound
            assert mid_low1_low2[i][0] < mid_low1_low2[i + 1][0]  # Target ascending

    # Tertiary sort: linked_from is sorted
    for w in result["wanted"]:
        linked_from = w["linked_from"]
        assert linked_from == sorted(linked_from)


def test_worklist_wanted_inbound_consistency(tmp_path):
    """INVARIANT: wanted.inbound == len(wanted.linked_from) for all entries."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[X]] [[Y]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Links [[X]] [[Z]].")
    _topic(tmp_path, "C.md", {"title": "C"}, "Links [[X]].")

    result = worklist.compute_worklist(tmp_path)

    for wanted_item in result["wanted"]:
        assert wanted_item["inbound"] == len(wanted_item["linked_from"])


def test_worklist_stale_reason_precedence_invariant(tmp_path):
    """INVARIANT: low_tier takes precedence over index_stale when both conditions hold."""
    _init(tmp_path)

    # Create topics with different tier levels
    stub_path = _topic(tmp_path, "stub.md", {"title": "Stub"}, "Short.")  # stub tier
    # Standard tier requires: sections >= 2 AND prose_chars >= 600
    standard_body = "## Section 1\n\n" + ("Prose content here. " * 35) + "\n\n## Section 2\n\n" + ("More prose content. " * 35)
    standard_path = _topic(tmp_path, "standard.md", {"title": "Standard"}, standard_body)

    # Save index
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    # Touch both to make them index-stale
    import time
    time.sleep(0.01)
    stub_path.touch()
    standard_path.touch()

    result = worklist.compute_worklist(tmp_path)

    # stub: low_tier + index_stale → reason should be low_tier
    stub_item = next((s for s in result["stale"] if s["path"] == "stub.md"), None)
    assert stub_item is not None
    assert stub_item["reason"] == "low_tier"

    # standard: only index_stale → reason should be index_stale
    standard_item = next((s for s in result["stale"] if s["path"] == "standard.md"), None)
    assert standard_item is not None
    assert standard_item["reason"] == "index_stale"


def test_worklist_deterministic_across_file_order(tmp_path):
    """INVARIANT: worklist output is deterministic regardless of file creation order."""
    _init(tmp_path)

    # Create in random order
    _topic(tmp_path, "Z.md", {"title": "Z"}, "Links [[Missing1]].")
    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[Missing2]].")
    _topic(tmp_path, "M.md", {"title": "M"}, "Links [[Missing1]].")

    result1 = worklist.compute_worklist(tmp_path)

    # Rebuild - should be identical
    result2 = worklist.compute_worklist(tmp_path)

    assert json.dumps(result1["wanted"], sort_keys=True) == json.dumps(result2["wanted"], sort_keys=True)
    assert json.dumps(result1["stale"], sort_keys=True) == json.dumps(result2["stale"], sort_keys=True)
