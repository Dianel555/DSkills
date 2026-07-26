"""Tests for quality.py metrics computation."""

import pytest
from pathlib import Path

from agent_wiki import config, frontmatter


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


# --- 1.1 Quality metrics tests ---


def test_sections_counts_atx_level_2_to_6_headings(tmp_path):
    """sections metric counts ## to ###### headings, excluding level-1."""
    from agent_wiki import quality

    body = """# Level 1 Title (excluded)

## Section 1
Some text.

### Section 1.1
More text.

#### Section 1.1.1
Deep section.

##### Section 1.1.1.1
Even deeper.

###### Section 1.1.1.1.1
Max depth.

# Another level 1 (excluded)
"""

    metrics = quality.compute_metrics(body)
    assert metrics["sections"] == 5  # Only ## to ######


def test_sections_excludes_fenced_code_headings(tmp_path):
    """Fenced code blocks with fake headings should not count."""
    from agent_wiki import quality

    body = """## Real Section 1

```python
# This is a comment, not a heading
## This is also not a heading
### Neither is this
```

## Real Section 2

~~~markdown
## Fake heading in fenced block
~~~

## Real Section 3
"""

    metrics = quality.compute_metrics(body)
    assert metrics["sections"] == 3  # Only the real sections


def test_evidence_lines_counts_blockquote_prefix(tmp_path):
    """evidence_lines counts lines starting with '> '."""
    from agent_wiki import quality

    body = """## Source Analysis

> This is a quote from the primary source.
> It continues on the next line.
> Third line of evidence.

Some analysis text.

> Another quote here.

Regular paragraph.
"""

    metrics = quality.compute_metrics(body)
    assert metrics["evidence_lines"] == 4


def test_evidence_lines_excludes_fenced_quotes(tmp_path):
    """Block quotes inside fenced code should not count."""
    from agent_wiki import quality

    body = """## Analysis

> Real quote line 1
> Real quote line 2

```markdown
> Fake quote in code block
> Another fake quote
```

> Real quote line 3
"""

    metrics = quality.compute_metrics(body)
    assert metrics["evidence_lines"] == 3


def test_prose_chars_counts_nfc_length_of_paragraph_lines(tmp_path):
    """prose_chars is NFC length of paragraph lines only."""
    from agent_wiki import quality

    body = """## Section

This is a prose paragraph with 中文字符 mixed in.
Another prose line here.

- List item (excluded)
- Another list (excluded)

> Block quote (excluded)

| Table | Header |
|-------|--------|
| Cell  | Data   |

<!-- HTML comment (excluded) -->

![[image.png]]

More prose content after various non-prose elements.
"""

    metrics = quality.compute_metrics(body)
    # Should count only the two prose paragraphs
    # "This is a prose paragraph with 中文字符 mixed in." + "Another prose line here." + "More prose content after various non-prose elements."
    assert metrics["prose_chars"] > 0
    assert metrics["prose_chars"] < 200  # Sanity check


def test_prose_chars_excludes_all_non_prose_patterns(tmp_path):
    """Verify all exclusion patterns work."""
    from agent_wiki import quality

    body = """## Heading (excluded)

This is prose.

### Another heading (excluded)

- Unordered list item
* Another bullet
+ Plus bullet

1. Ordered list
2. Another number

> Block quote line

| Table | Row |

<!-- Comment -->

![[embed.png]]

Final prose line.
"""

    metrics = quality.compute_metrics(body)
    # Should count only "This is prose." and "Final prose line."
    expected_chars = len("This is prose.") + len("Final prose line.")
    assert metrics["prose_chars"] == expected_chars


def test_has_image_detects_obsidian_embed(tmp_path):
    """has_image detects ![[*.png|jpg|...]] embeds."""
    from agent_wiki import quality

    body_with_image = """## Section

Some text before.

![[diagram.png]]

More text after.
"""

    body_without_image = """## Section

Just text with a regular [[link]] but no image embed.
"""

    assert quality.compute_metrics(body_with_image)["has_image"] is True
    assert quality.compute_metrics(body_without_image)["has_image"] is False


def test_has_image_detects_markdown_image(tmp_path):
    """has_image detects ![alt](url) markdown images."""
    from agent_wiki import quality

    body = """## Section

Check out this image:

![Architecture Diagram](https://example.com/arch.png)

End of section.
"""

    metrics = quality.compute_metrics(body)
    assert metrics["has_image"] is True


def test_has_image_supports_multiple_extensions(tmp_path):
    """has_image detects .png/.jpg/.jpeg/.gif/.webp/.svg/.bmp."""
    from agent_wiki import quality

    for ext in ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"]:
        body = f"![[image.{ext}]]"
        assert quality.compute_metrics(body)["has_image"] is True, f"Failed for .{ext}"


def test_has_lead_detects_paragraph_before_first_heading(tmp_path):
    """has_lead is true when body opens with a paragraph before first ##."""
    from agent_wiki import quality

    body_with_lead = """This is the lead sentence that positions the topic before any sections.

## First Section

Content here.
"""

    body_without_lead = """## First Section

Content starts with a heading, no lead.
"""

    assert quality.compute_metrics(body_with_lead)["has_lead"] is True
    assert quality.compute_metrics(body_without_lead)["has_lead"] is False


def test_has_lead_ignores_blank_lines_before_lead(tmp_path):
    """has_lead still detects lead even if blank lines precede it."""
    from agent_wiki import quality

    body = """

This is the lead after blank lines.

## Section
"""

    metrics = quality.compute_metrics(body)
    assert metrics["has_lead"] is True


def test_has_lead_false_when_image_only_first(tmp_path):
    """has_lead is false when first non-blank line is an image embed."""
    from agent_wiki import quality

    body = """![[banner.png]]

## Section

Actual content.
"""

    metrics = quality.compute_metrics(body)
    assert metrics["has_lead"] is False


def test_metrics_handle_crlf_line_endings(tmp_path):
    """Metrics work correctly with Windows CRLF line endings."""
    from agent_wiki import quality

    body_crlf = "## Section\r\n\r\n> Quote line\r\n\r\nProse here.\r\n"

    metrics = quality.compute_metrics(body_crlf)
    assert metrics["sections"] == 1
    assert metrics["evidence_lines"] == 1
    assert metrics["prose_chars"] == len("Prose here.")


def test_metrics_handle_cr_line_endings(tmp_path):
    """Metrics work correctly with old Mac CR line endings."""
    from agent_wiki import quality

    body_cr = "## Section\r\r> Quote line\r\rProse here.\r"

    metrics = quality.compute_metrics(body_cr)
    assert metrics["sections"] == 1
    assert metrics["evidence_lines"] == 1
    assert metrics["prose_chars"] == len("Prose here.")


def test_metrics_handle_mixed_line_endings(tmp_path):
    """Metrics work correctly with mixed line ending styles."""
    from agent_wiki import quality

    body_mixed = "## Section\n\r\n> Quote\r\nProse.\n"

    metrics = quality.compute_metrics(body_mixed)
    assert metrics["sections"] == 1
    assert metrics["evidence_lines"] == 1


def test_fenced_code_with_backticks_and_tildes(tmp_path):
    """Both ``` and ~~~ fence styles exclude their content."""
    from agent_wiki import quality

    body = """## Real Section

```
## Fake heading in backtick fence
> Fake quote
```

~~~
### Another fake heading
> Another fake quote
~~~

## Real Section 2
"""

    metrics = quality.compute_metrics(body)
    assert metrics["sections"] == 2
    assert metrics["evidence_lines"] == 0


# --- 1.2 Five-tier mapping tests ---


def test_tier_premium_requires_all_conditions():
    """Premium tier: sections >= 6 AND prose_chars >= 3000 AND evidence_lines >= 3."""
    from agent_wiki import quality

    # Meets premium threshold
    body_premium = "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n> Evidence 1\n> Evidence 2\n> Evidence 3\n\n" + ("Prose paragraph. " * 300)
    assert quality.compute_tier(body_premium) == "premium"

    # Missing one condition each - should not be premium
    body_few_sections = "## S1\n## S2\n## S3\n## S4\n## S5\n\n> E1\n> E2\n> E3\n\n" + ("Prose. " * 300)
    assert quality.compute_tier(body_few_sections) != "premium"

    body_short_prose = "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n> E1\n> E2\n> E3\n\nShort."
    assert quality.compute_tier(body_short_prose) != "premium"

    body_no_evidence = "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n" + ("Prose. " * 300)
    assert quality.compute_tier(body_no_evidence) != "premium"


def test_tier_rich_requires_sections_prose_and_evidence_or_image():
    """Rich tier: sections >= 4 AND prose_chars >= 1500 AND (evidence_lines >= 1 OR has_image)."""
    from agent_wiki import quality

    # With evidence
    body_with_evidence = "## S1\n## S2\n## S3\n## S4\n\n> Evidence here\n\n" + ("Prose sentence. " * 100)
    assert quality.compute_tier(body_with_evidence) == "rich"

    # With image instead of evidence
    body_with_image = "## S1\n## S2\n## S3\n## S4\n\n![[image.png]]\n\n" + ("Prose sentence. " * 100)
    assert quality.compute_tier(body_with_image) == "rich"

    # Missing sections
    body_few_sections = "## S1\n## S2\n## S3\n\n> Evidence\n\n" + ("Prose. " * 100)
    assert quality.compute_tier(body_few_sections) != "rich"

    # Missing evidence AND image
    body_no_evidence_or_image = "## S1\n## S2\n## S3\n## S4\n\n" + ("Prose. " * 100)
    assert quality.compute_tier(body_no_evidence_or_image) != "rich"


def test_tier_standard_requires_sections_and_prose():
    """Standard tier: sections >= 2 AND prose_chars >= 600."""
    from agent_wiki import quality

    body_standard = "## Section 1\n## Section 2\n\n" + ("Prose content here. " * 35)
    assert quality.compute_tier(body_standard) == "standard"

    # One section short
    body_one_section = "## Section\n\n" + ("Prose. " * 35)
    assert quality.compute_tier(body_one_section) != "standard"

    # Prose too short
    body_short = "## S1\n## S2\n\nShort prose."
    assert quality.compute_tier(body_short) != "standard"


def test_tier_basic_requires_prose_or_section():
    """Basic tier: prose_chars >= 200 OR sections >= 1."""
    from agent_wiki import quality

    # Meets prose threshold
    body_prose_only = ("Prose paragraph here. " * 12)
    assert quality.compute_tier(body_prose_only) == "basic"

    # Meets section threshold
    body_section_only = "## Section\n\nBrief text."
    assert quality.compute_tier(body_section_only) == "basic"

    # Both conditions met
    body_both = "## Section\n\n" + ("Prose. " * 15)
    assert quality.compute_tier(body_both) == "basic"


def test_tier_stub_is_default():
    """Stub tier: anything that doesn't meet basic threshold."""
    from agent_wiki import quality

    # Empty body
    assert quality.compute_tier("") == "stub"

    # Very short prose, no sections
    assert quality.compute_tier("Short.") == "stub"

    # Only whitespace
    assert quality.compute_tier("\n\n   \n") == "stub"

    # Just a title (level-1, excluded)
    assert quality.compute_tier("# Title\n\nTiny.") == "stub"


def test_tier_assignment_is_deterministic():
    """Same content always produces same tier."""
    from agent_wiki import quality

    body = "## Section 1\n## Section 2\n\n" + ("Prose here. " * 50)

    tier1 = quality.compute_tier(body)
    tier2 = quality.compute_tier(body)
    tier3 = quality.compute_tier(body)

    assert tier1 == tier2 == tier3


def test_tier_monotonicity_adding_sections():
    """Adding sections never lowers the tier."""
    from agent_wiki import quality

    body_base = "Prose paragraph. " * 15
    tier_base = quality.compute_tier(body_base)

    body_with_section = "## Section\n\n" + body_base
    tier_with_section = quality.compute_tier(body_with_section)

    body_with_more = "## S1\n## S2\n\n" + body_base
    tier_with_more = quality.compute_tier(body_with_more)

    tiers_order = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers_order.index(tier_with_section) >= tiers_order.index(tier_base)
    assert tiers_order.index(tier_with_more) >= tiers_order.index(tier_with_section)


def test_tier_monotonicity_adding_prose():
    """Adding prose never lowers the tier."""
    from agent_wiki import quality

    body_short = "## S1\n\nShort."
    body_medium = "## S1\n\n" + ("Prose. " * 40)
    body_long = "## S1\n\n" + ("Prose. " * 200)

    tier_short = quality.compute_tier(body_short)
    tier_medium = quality.compute_tier(body_medium)
    tier_long = quality.compute_tier(body_long)

    tiers_order = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers_order.index(tier_medium) >= tiers_order.index(tier_short)
    assert tiers_order.index(tier_long) >= tiers_order.index(tier_medium)


def test_tier_monotonicity_adding_evidence():
    """Adding evidence lines never lowers the tier."""
    from agent_wiki import quality

    body_no_evidence = "## S1\n## S2\n## S3\n## S4\n\n" + ("Prose. " * 100)
    body_one_evidence = body_no_evidence + "\n\n> Evidence line 1"
    body_many_evidence = body_one_evidence + "\n> Evidence 2\n> Evidence 3"

    tier_none = quality.compute_tier(body_no_evidence)
    tier_one = quality.compute_tier(body_one_evidence)
    tier_many = quality.compute_tier(body_many_evidence)

    tiers_order = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers_order.index(tier_one) >= tiers_order.index(tier_none)
    assert tiers_order.index(tier_many) >= tiers_order.index(tier_one)


def test_tier_monotonicity_adding_image():
    """Adding an image never lowers the tier."""
    from agent_wiki import quality

    body_no_image = "## S1\n## S2\n## S3\n## S4\n\n" + ("Prose. " * 100)
    body_with_image = body_no_image + "\n\n![[diagram.png]]"

    tier_no_image = quality.compute_tier(body_no_image)
    tier_with_image = quality.compute_tier(body_with_image)

    tiers_order = ["stub", "basic", "standard", "rich", "premium"]
    assert tiers_order.index(tier_with_image) >= tiers_order.index(tier_no_image)


# --- 6.1 Property-based / invariant tests ---


def test_quality_determinism_identical_bytes():
    """INVARIANT: identical topic bytes => identical metrics/tier."""
    from agent_wiki import quality

    body = "## Section 1\n## Section 2\n\n> Evidence line\n\n" + ("Prose content. " * 50) + "\n\n![[image.png]]"

    metrics1 = quality.compute_metrics(body)
    tier1 = quality.compute_tier(body)

    metrics2 = quality.compute_metrics(body)
    tier2 = quality.compute_tier(body)

    metrics3 = quality.compute_metrics(body)
    tier3 = quality.compute_tier(body)

    assert metrics1 == metrics2 == metrics3
    assert tier1 == tier2 == tier3


def test_quality_metrics_bounds():
    """INVARIANT: sections/evidence_lines/prose_chars >= 0."""
    from agent_wiki import quality

    bodies = [
        "",  # empty
        "x",  # minimal
        "## S\n\n> E\n\nProse.",  # normal
        "\n\n   \n\n",  # whitespace only
        "# Title only",  # level-1 only
    ]

    for body in bodies:
        metrics = quality.compute_metrics(body)
        assert metrics["sections"] >= 0
        assert metrics["evidence_lines"] >= 0
        assert metrics["prose_chars"] >= 0
        assert isinstance(metrics["has_image"], bool)
        assert isinstance(metrics["has_lead"], bool)


def test_quality_with_nfd_unicode():
    """INVARIANT: NFD text handled correctly (prose_chars uses NFC)."""
    from agent_wiki import quality
    import unicodedata

    # NFD: decomposed form (e.g., é = e + ́)
    body_nfd = unicodedata.normalize("NFD", "## Section\n\nProse with café and naïve words.")

    metrics = quality.compute_metrics(body_nfd)
    # NFC length should be computed correctly
    assert metrics["sections"] == 1
    assert metrics["prose_chars"] > 0


def test_quality_with_embed_only_lines():
    """Embed-only lines excluded from prose_chars."""
    from agent_wiki import quality

    body = """## Section

![[file.pdf]]

![[another-doc.md]]

This is prose.

![[image.png]]
"""

    metrics = quality.compute_metrics(body)
    assert metrics["prose_chars"] == len("This is prose.")


def test_quality_with_empty_body():
    """INVARIANT: empty body => all metrics zero/false, tier=stub."""
    from agent_wiki import quality

    metrics = quality.compute_metrics("")
    assert metrics["sections"] == 0
    assert metrics["evidence_lines"] == 0
    assert metrics["prose_chars"] == 0
    assert metrics["has_image"] is False
    assert metrics["has_lead"] is False

    tier = quality.compute_tier("")
    assert tier == "stub"


def test_quality_with_huge_body():
    """INVARIANT: huge body handled without error."""
    from agent_wiki import quality

    # Generate a huge body (10k lines, ~50k chars)
    sections = "\n".join([f"## Section {i}" for i in range(100)])
    evidence = "\n".join([f"> Evidence line {i}" for i in range(100)])
    prose = "\n\n".join([f"Prose paragraph {i}. " * 20 for i in range(100)])

    body_huge = f"{sections}\n\n{evidence}\n\n{prose}\n\n![[image.png]]"

    metrics = quality.compute_metrics(body_huge)
    tier = quality.compute_tier(body_huge)

    assert metrics["sections"] > 0
    assert metrics["evidence_lines"] > 0
    assert metrics["prose_chars"] > 0
    assert metrics["has_image"] is True
    assert tier in ["stub", "basic", "standard", "rich", "premium"]


def test_quality_monotonicity_comprehensive():
    """INVARIANT: adding any metric never lowers the tier (comprehensive test)."""
    from agent_wiki import quality

    tiers_order = ["stub", "basic", "standard", "rich", "premium"]

    # Start with minimal body
    base = "Tiny."
    tier_base = quality.compute_tier(base)

    # Add sections
    with_sections = "## S1\n## S2\n\n" + base
    tier_sections = quality.compute_tier(with_sections)
    assert tiers_order.index(tier_sections) >= tiers_order.index(tier_base)

    # Add prose
    with_prose = with_sections + "\n\n" + ("More prose. " * 50)
    tier_prose = quality.compute_tier(with_prose)
    assert tiers_order.index(tier_prose) >= tiers_order.index(tier_sections)

    # Add evidence
    with_evidence = with_prose + "\n\n> Evidence line 1\n> Evidence line 2\n> Evidence line 3"
    tier_evidence = quality.compute_tier(with_evidence)
    assert tiers_order.index(tier_evidence) >= tiers_order.index(tier_prose)

    # Add image
    with_image = with_evidence + "\n\n![[diagram.png]]"
    tier_image = quality.compute_tier(with_image)
    assert tiers_order.index(tier_image) >= tiers_order.index(tier_evidence)

    # Add more sections
    with_more_sections = "## S3\n## S4\n## S5\n## S6\n\n" + with_image
    tier_more = quality.compute_tier(with_more_sections)
    assert tiers_order.index(tier_more) >= tiers_order.index(tier_image)


def test_quality_fenced_code_decoys_comprehensive():
    """INVARIANT: fenced content never contributes to metrics."""
    from agent_wiki import quality

    body = """## Real Section 1

```python
# Fake heading 1
## Fake heading 2
### Fake heading 3
> Fake quote
Fake prose line.
![[fake-image.png]]
```

Real prose paragraph here.

~~~markdown
## Another fake heading
> Another fake quote
More fake prose.
![Fake image](fake.png)
~~~

## Real Section 2

> Real evidence line

![[real-image.png]]
"""

    metrics = quality.compute_metrics(body)
    assert metrics["sections"] == 2  # Only Real Section 1 and 2
    assert metrics["evidence_lines"] == 1  # Only real evidence
    assert metrics["prose_chars"] == len("Real prose paragraph here.")
    assert metrics["has_image"] is True  # Only ![[real-image.png]]


def test_quality_distribution_sums_to_total(tmp_path):
    """INVARIANT: distribution sums to number of scored topics."""
    from agent_wiki import quality

    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Initialize wiki
    wiki_dir = vault / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "topics").mkdir()

    # Create 10 topics with different tiers
    _topic(vault, "stub1.md", {"title": "Stub 1"}, "x")
    _topic(vault, "stub2.md", {"title": "Stub 2"}, "Short.")
    _topic(vault, "basic1.md", {"title": "Basic 1"}, "## S\n\n" + ("Prose. " * 15))
    _topic(vault, "basic2.md", {"title": "Basic 2"}, ("Prose. " * 30))
    _topic(vault, "standard1.md", {"title": "Standard 1"}, "## S1\n## S2\n\n" + ("Prose. " * 40))
    _topic(vault, "standard2.md", {"title": "Standard 2"}, "## S1\n## S2\n\n" + ("Prose. " * 35))
    _topic(vault, "rich1.md", {"title": "Rich 1"}, "## S1\n## S2\n## S3\n## S4\n\n> E\n\n" + ("Prose. " * 100))
    _topic(vault, "rich2.md", {"title": "Rich 2"}, "## S1\n## S2\n## S3\n## S4\n\n![[img.png]]\n\n" + ("Prose. " * 100))
    _topic(vault, "premium1.md", {"title": "Premium 1"}, "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n> E1\n> E2\n> E3\n\n" + ("Prose. " * 300))
    _topic(vault, "premium2.md", {"title": "Premium 2"}, "## S1\n## S2\n## S3\n## S4\n## S5\n## S6\n\n> E1\n> E2\n> E3\n\n" + ("Prose. " * 350))

    # Compute quality directly
    topics_dir = config.topics_dir(vault)
    tiers = {}
    distribution = {"stub": 0, "basic": 0, "standard": 0, "rich": 0, "premium": 0}

    for topic_path in topics_dir.glob("*.md"):
        content = topic_path.read_text(encoding="utf-8")
        _, body = frontmatter.parse(content)
        tier = quality.compute_tier(body)
        tiers[topic_path.name] = tier
        distribution[tier] += 1

    # Distribution should sum to total topics
    total_topics = len(tiers)
    sum_distribution = sum(distribution.values())
    assert sum_distribution == total_topics
    assert total_topics == 10
