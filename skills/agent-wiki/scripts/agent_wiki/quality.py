"""Quality tier scoring for wiki topics.

Computes deterministic structural metrics and assigns a five-tier rating
(stub/basic/standard/rich/premium) based on content richness. No LLM calls,
no network access, no I/O side effects.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _nfc(text: str) -> str:
    """Normalize to NFC Unicode form."""
    return unicodedata.normalize("NFC", text)


def _count_cjk_and_latin(text: str) -> tuple[int, int]:
    r"""Count CJK characters and Latin words in NFC-normalized text.

    CJK characters: EAW in {W, F} AND category starts with L or N.
    Excludes wide/fullwidth punctuation, symbols, emoji.
    Halfwidth katakana (EAW=H) is normalized to fullwidth via NFKC first.

    Latin words: after replacing wide/fullwidth chars with spaces,
    count word runs via [^\W_]+ pattern.

    Returns (cjk_chars, latin_words).
    """
    # Apply NFC normalization
    text = _nfc(text)

    # Apply NFKC to normalize halfwidth katakana to fullwidth
    text = unicodedata.normalize("NFKC", text)

    cjk_count = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        cat = unicodedata.category(ch)
        # CJK: wide/fullwidth AND letter/number category
        if eaw in ('W', 'F') and cat[0] in ('L', 'N'):
            cjk_count += 1

    # Replace wide/fullwidth chars with spaces to prevent merge
    latin_text = ""
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):
            latin_text += " "
        else:
            latin_text += ch

    # Count word runs (letters/digits, excluding underscores)
    words = re.findall(r'[^\W_]+', latin_text, re.UNICODE)
    latin_count = len(words)

    return cjk_count, latin_count


def compute_metrics(body: str) -> dict[str, Any]:
    """Compute structural quality metrics from topic body.

    Metrics:
    - sections: count of ## to ###### ATX headings (excluding level-1)
    - evidence_lines: count of lines starting with "> "
    - prose_chars: NFC character length of paragraph lines (retained for transparency)
    - prose_weight: script-aware prose measure (10 × cjk_chars + 16 × latin_words)
    - cjk_chars: count of CJK ideographs (EAW W/F + category L/N)
    - latin_words: count of Latin/other word runs
    - has_image: bool, body contains image embed
    - has_lead: bool, first non-blank line is a paragraph

    Returns dict with all metrics.
    """
    lines = body.splitlines()

    sections = 0
    evidence_lines = 0
    prose_chars = 0
    cjk_total = 0
    latin_total = 0
    has_image = False
    has_lead = False

    in_fence = False
    first_content_line_checked = False
    seen_h1 = False

    for line in lines:
        stripped = line.strip()

        # Toggle fence state
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue

        # Skip fenced content
        if in_fence:
            continue

        # Skip blank lines
        if not stripped:
            continue

        # Skip the first level-1 heading (topic title)
        if not seen_h1 and re.match(r"^#\s+\S", stripped):
            seen_h1 = True
            continue

        # Check for has_lead (first non-blank, non-fenced line after optional h1)
        if not first_content_line_checked:
            first_content_line_checked = True
            # It's a paragraph if it's NOT a heading, list, quote, table, comment, or image
            is_heading = stripped.startswith("#")
            is_list = re.match(r"^[-*+]\s", stripped) or re.match(r"^\d+[.)\]]\s", stripped)
            is_quote_or_table = stripped.startswith(">") or stripped.startswith("|")
            is_comment = stripped.startswith("<!--")
            is_wikilink_image = stripped.startswith("![[") and stripped.endswith("]]")
            is_markdown_image = stripped.startswith("![") and ")" in stripped

            if not (is_heading or is_list or is_quote_or_table or is_comment or
                    is_wikilink_image or is_markdown_image):
                has_lead = True

        # Count sections (## to ######)
        if re.match(r"^#{2,6}\s+\S", stripped):
            sections += 1
            continue

        # Count evidence lines
        if stripped.startswith("> "):
            evidence_lines += 1
            continue

        # Check for images
        if not has_image:
            # Obsidian embed: ![[filename.ext]]
            obsidian_embed_match = re.search(r"!\[\[.+?\.(png|jpg|jpeg|gif|webp|svg|bmp)\]\]", stripped, re.IGNORECASE)
            if obsidian_embed_match:
                has_image = True
            # Markdown image: ![alt](url)
            markdown_image_match = re.match(r"!\[.*?\]\(.+?\)", stripped)
            if markdown_image_match:
                has_image = True

        # Count prose characters and compute prose_weight
        # Exclude: headings, lists, quotes, tables, comments, embed-only lines
        if not (
            stripped.startswith("#") or
            re.match(r"^[-*+]\s", stripped) or
            re.match(r"^\d+[.)\]]\s", stripped) or
            stripped.startswith(">") or
            stripped.startswith("|") or
            stripped.startswith("<!--") or
            (stripped.startswith("![[") and stripped.endswith("]]")) or
            (stripped.startswith("![") and ")" in stripped and not any(c.isalnum() for c in stripped.split(")", 1)[1] if len(stripped.split(")", 1)) > 1))
        ):
            prose_chars += len(_nfc(stripped))
            cjk, latin = _count_cjk_and_latin(stripped)
            cjk_total += cjk
            latin_total += latin

    prose_weight = 10 * cjk_total + 16 * latin_total

    return {
        "sections": sections,
        "evidence_lines": evidence_lines,
        "prose_chars": prose_chars,
        "prose_weight": prose_weight,
        "cjk_chars": cjk_total,
        "latin_words": latin_total,
        "has_image": has_image,
        "has_lead": has_lead,
    }


def compute_tier(body: str, source_count: int = 0) -> str:
    """Assign quality tier based on metrics and source grounding.

    Uses effective_prose = prose_weight + 500*source_count for tier gates.
    Tiers (top-down first-match):
    - premium: sections >= 6 AND effective_prose >= 3000 AND evidence_lines >= 3
    - rich: sections >= 4 AND effective_prose >= 1500 AND (evidence_lines >= 1 OR has_image)
    - standard: sections >= 2 AND effective_prose >= 600
    - basic: effective_prose >= 200 OR sections >= 1
    - stub: otherwise

    Args:
        body: Topic body markdown
        source_count: Number of deduplicated sources (default 0)

    Returns tier string.
    """
    metrics = compute_metrics(body)

    sections = metrics["sections"]
    prose_weight = metrics["prose_weight"]
    evidence_lines = metrics["evidence_lines"]
    has_image = metrics["has_image"]

    # Compute effective prose with source grounding bonus
    effective_prose = prose_weight + 500 * source_count

    # Premium
    if sections >= 6 and effective_prose >= 3000 and evidence_lines >= 3:
        return "premium"

    # Rich
    if sections >= 4 and effective_prose >= 1500 and (evidence_lines >= 1 or has_image):
        return "rich"

    # Standard
    if sections >= 2 and effective_prose >= 600:
        return "standard"

    # Basic (requires some prose OR structure; sources alone insufficient)
    if (effective_prose >= 200 and prose_weight > 0) or sections >= 1:
        return "basic"

    # Stub
    return "stub"
