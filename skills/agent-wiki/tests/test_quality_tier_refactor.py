"""Tests for compute_tier with prose_weight and source_count."""

import pytest
from agent_wiki import quality


def test_compute_tier_accepts_source_count_parameter():
    """compute_tier accepts optional source_count parameter."""
    body = "## Section\n\nSome prose content here."

    # Should work with and without source_count
    tier_no_sources = quality.compute_tier(body)
    tier_with_sources = quality.compute_tier(body, source_count=3)

    assert tier_no_sources in ("stub", "basic", "standard", "rich", "premium")
    assert tier_with_sources in ("stub", "basic", "standard", "rich", "premium")


def test_compute_tier_uses_prose_weight_not_prose_chars():
    """compute_tier uses prose_weight (script-aware) not prose_chars."""
    # CJK: 500 chars × 10 = 5000 weight
    body_cjk = "## S1\n## S2\n\n" + ("汉字" * 250)  # 500 CJK chars

    # Latin: 313 words × 16 = 5008 weight (≈ same as CJK)
    body_latin = "## S1\n## S2\n\n" + (" word" * 313)  # 313 words

    tier_cjk = quality.compute_tier(body_cjk)
    tier_latin = quality.compute_tier(body_latin)

    # Should tier equally due to similar prose_weight
    assert tier_cjk == tier_latin


def test_compute_tier_source_count_boosts_tier():
    """Source count provides grounding bonus to effective_prose."""
    # Body with low prose but high source count
    body = "## Intro\n\n简短内容。"  # ~40 weight

    tier_no_sources = quality.compute_tier(body, source_count=0)
    tier_with_sources = quality.compute_tier(body, source_count=3)  # +1500 weight

    # With sources should tier higher
    tiers = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers.index(tier_with_sources) >= tiers.index(tier_no_sources)


def test_compute_tier_source_count_does_not_bypass_structure():
    """Source count alone cannot skip from stub to basic without prose/structure."""
    # Empty body + sources should still be stub
    body_empty = ""
    tier_empty = quality.compute_tier(body_empty, source_count=10)
    assert tier_empty == "stub"

    # Minimal body + sources can reach basic
    body_minimal = "一些内容。"  # Some prose
    tier_minimal = quality.compute_tier(body_minimal, source_count=2)
    assert tier_minimal in ("basic", "standard", "rich", "premium")


def test_compute_tier_thresholds_use_effective_prose():
    """Tier gates use effective_prose = prose_weight + 500*source_count."""
    # Test boundary: standard tier needs effective_prose >= 600

    # Just below threshold with prose alone
    body_below = "## S1\n## S2\n\n" + ("word " * 35)  # ~560 weight
    tier_below = quality.compute_tier(body_below, source_count=0)
    assert tier_below == "basic"

    # Cross threshold with 1 source (+500)
    tier_above = quality.compute_tier(body_below, source_count=1)
    assert tier_above == "standard"


def test_compute_tier_maintains_five_tier_scale():
    """Tier output is one of the five ordinal values."""
    bodies = [
        "",
        "Short.",
        "## Section\n\nSome content here.",
        "## S1\n## S2\n\n" + ("Prose. " * 100),
        "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n" + ("Prose. " * 500) + "\n\n> Evidence\n> More\n> Lines",
    ]

    expected_tiers = {"stub", "basic", "standard", "rich", "premium"}

    for body in bodies:
        tier = quality.compute_tier(body, source_count=0)
        assert tier in expected_tiers


def test_compute_tier_monotonic_in_source_count():
    """Adding sources never lowers tier (monotonicity)."""
    body = "## Section\n\nSome prose content."

    tiers = ["stub", "basic", "standard", "rich", "premium"]
    prev_tier = quality.compute_tier(body, source_count=0)

    for sc in [1, 2, 3, 5, 10]:
        tier = quality.compute_tier(body, source_count=sc)
        assert tiers.index(tier) >= tiers.index(prev_tier)
        prev_tier = tier


def test_compute_tier_backwards_compatible_default_arg():
    """compute_tier works with no source_count (defaults to 0)."""
    body = "## Section\n\nContent."

    # Should work with original signature
    tier = quality.compute_tier(body)
    assert tier in ("stub", "basic", "standard", "rich", "premium")
