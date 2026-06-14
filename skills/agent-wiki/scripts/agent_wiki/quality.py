"""Quality tier scoring for wiki topics.

Computes deterministic structural metrics and assigns a five-tier rating
(stub/basic/standard/rich/premium) based on content richness. No LLM calls,
no network access, no I/O side effects.
"""

from __future__ import annotations

import re
import unicodedata


def _nfc(text: str) -> str:
    """Normalize to NFC Unicode form."""
    return unicodedata.normalize("NFC", text)


def compute_metrics(body: str) -> dict:
    """Compute structural quality metrics from topic body.

    Metrics:
    - sections: count of ## to ###### ATX headings (excluding level-1)
    - evidence_lines: count of lines starting with "> "
    - prose_chars: NFC character length of paragraph lines
    - has_image: bool, body contains image embed
    - has_lead: bool, first non-blank line is a paragraph

    Returns dict with all five metrics.
    """
    lines = body.splitlines()

    sections = 0
    evidence_lines = 0
    prose_chars = 0
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
            # It's a paragraph if it's NOT a heading, list, quote, table, comment, or image-only
            if not (
                stripped.startswith("#") or
                re.match(r"^[-*+]\s", stripped) or
                re.match(r"^\d+[.)\]]\s", stripped) or
                stripped.startswith(">") or
                stripped.startswith("|") or
                stripped.startswith("<!--") or
                (stripped.startswith("![[") and stripped.endswith("]]")) or
                (stripped.startswith("![") and ")" in stripped)
            ):
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

        # Count prose characters
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

    return {
        "sections": sections,
        "evidence_lines": evidence_lines,
        "prose_chars": prose_chars,
        "has_image": has_image,
        "has_lead": has_lead,
    }


def compute_tier(body: str) -> str:
    """Assign quality tier based on metrics.

    Tiers (top-down first-match):
    - premium: sections >= 6 AND prose_chars >= 3000 AND evidence_lines >= 3
    - rich: sections >= 4 AND prose_chars >= 1500 AND (evidence_lines >= 1 OR has_image)
    - standard: sections >= 2 AND prose_chars >= 600
    - basic: prose_chars >= 200 OR sections >= 1
    - stub: otherwise

    Returns tier string.
    """
    metrics = compute_metrics(body)

    sections = metrics["sections"]
    prose_chars = metrics["prose_chars"]
    evidence_lines = metrics["evidence_lines"]
    has_image = metrics["has_image"]

    # Premium
    if sections >= 6 and prose_chars >= 3000 and evidence_lines >= 3:
        return "premium"

    # Rich
    if sections >= 4 and prose_chars >= 1500 and (evidence_lines >= 1 or has_image):
        return "rich"

    # Standard
    if sections >= 2 and prose_chars >= 600:
        return "standard"

    # Basic
    if prose_chars >= 200 or sections >= 1:
        return "basic"

    # Stub
    return "stub"
