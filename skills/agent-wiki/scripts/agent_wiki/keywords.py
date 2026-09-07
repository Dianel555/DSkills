"""Keyword inventory for topic categorization (read-only).

Surfaces per-keyword frequency and per-topic keyword lists so the Agent can
归纳 a small set of subject categories (e.g. 材料 / 器件 / 方法 …) and
assign each topic a ``topic_category``. No file writes, no LLM, no network.
"""

from __future__ import annotations

from typing import Any

from . import config, wiki_index


def compute_keywords(vault: str | Any) -> dict[str, Any]:
    """Inventory keywords across all indexed topics.

    Returns:
        {
            "ok": True,
            "keywords": [{"keyword": str, "count": int, "topics": [str]}, ...],
            "uncategorized": [str],  # topic keys with no keywords
        }
        ``keywords`` is frequency-descending (NFC tiebreak), so the most common
        terms the Agent should base categories on come first.
    """
    if not config.wiki_root(vault).exists():
        raise ValueError("wiki_not_initialized")

    data, _ = wiki_index.rebuild(vault)

    freq: dict[str, dict[str, Any]] = {}
    uncategorized: list[str] = []
    for key, entry in data.get("topics", {}).items():
        # Dedup within a topic (preserving order) and drop empty keywords so
        # they neither inflate counts nor pollute the keyword set; a topic whose
        # only keywords were empty/duplicate lands in uncategorized.
        kws = list(dict.fromkeys(
            str(k) for k in (entry.get("keywords") or []) if str(k).strip()
        ))
        if not kws:
            uncategorized.append(key)
            continue
        for kw in kws:
            slot = freq.setdefault(kw, {"keyword": kw, "count": 0, "topics": []})
            slot["count"] += 1
            slot["topics"].append(key)

    for slot in freq.values():
        slot["topics"].sort()

    keywords = sorted(freq.values(), key=lambda s: (-s["count"], s["keyword"]))
    uncategorized.sort()

    return {"ok": True, "keywords": keywords, "uncategorized": uncategorized}
