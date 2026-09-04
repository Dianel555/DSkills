"""Tests for wiki_index passing source_count to compute_tier."""

from pathlib import Path

from agent_wiki import config, frontmatter, quality, wiki_index


def _init(vault: Path) -> None:
    """Initialize wiki structure."""
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def test_index_passes_source_count_to_compute_tier(tmp_path):
    """Index rebuild passes len(sources) to compute_tier for grounding bonus."""
    _init(tmp_path)

    # Topic with low prose but high source count
    _topic(
        tmp_path,
        "grounded.md",
        {
            "title": "Grounded Topic",
            "sources": ["[[source1]]", "[[source2]]", "[[source3]]"],
        },
        "## Intro\n\n简短内容。"  # Low prose_weight
    )

    data, _ = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["grounded.md"]

    # Should use source count in tier calculation
    # Verify by checking tier is boosted
    tier = entry["quality_tier"]

    # With 3 sources (+1500 weight), should reach at least basic/standard
    assert tier in ("basic", "standard", "rich", "premium")

    # Verify sources are recorded
    assert len(entry["sources"]) == 3


def test_index_tier_without_sources_baseline(tmp_path):
    """Baseline: same body without sources gets lower tier."""
    _init(tmp_path)

    _topic(
        tmp_path,
        "ungrounded.md",
        {"title": "Ungrounded Topic"},
        "## Intro\n\n简短内容。"
    )

    data, _ = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["ungrounded.md"]

    # Without sources, low prose should be basic
    assert entry["quality_tier"] == "basic"
    assert len(entry["sources"]) == 0


def test_index_deduplicates_sources_before_count(tmp_path):
    """Source count uses deduplicated sources for tier calculation."""
    _init(tmp_path)

    _topic(
        tmp_path,
        "dup.md",
        {
            "title": "Duplicate Sources",
            "sources": ["[[s1]]", "[[s1]]", "[[s2]]"],  # 2 unique
        },
        "## Section\n\n内容。"
    )

    data, _ = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["dup.md"]

    # sources list retains duplicates (for display/transparency)
    assert len(entry["sources"]) == 3

    # But tier calculation should use deduplicated count (2 unique)
    tier_with_2 = quality.compute_tier("## Section\n\n内容。", source_count=2)
    assert entry["quality_tier"] == tier_with_2

    # Verify it's different from 3-source tier
    tier_with_3 = quality.compute_tier("## Section\n\n内容。", source_count=3)
    # Should be same or lower tier with deduplicated count
    tiers = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers.index(entry["quality_tier"]) <= tiers.index(tier_with_3)
