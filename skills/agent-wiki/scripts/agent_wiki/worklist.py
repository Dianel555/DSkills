"""Maintenance worklists: wanted (broken link targets) and stale (low-quality/outdated) topics."""

from __future__ import annotations

import contextlib
import unicodedata
from pathlib import Path

from . import config, wiki_index


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def compute_worklist(vault: str | Path) -> dict:
    """Compute wanted and stale worklists.

    Returns:
        {
            "wanted": [{"target": str, "inbound": int, "linked_from": [str]}],
            "stale": [{"path": str, "tier": str, "reason": str}]
        }

    Raises:
        ValueError: if wiki not initialized
    """
    vault = Path(vault)
    wiki_root = config.wiki_root(vault)

    if not wiki_root.exists():
        raise ValueError("wiki_not_initialized")

    # Rebuild index to get all pages and links
    data, _ = wiki_index.rebuild(vault)

    # --- WANTED: broken link targets ---

    # Collect all existing page stems (topics, queries)
    existing_stems = set()

    for topic_key in data["topics"]:
        # Strip .md to get stem
        stem = topic_key[:-3] if topic_key.endswith(".md") else topic_key
        existing_stems.add(_nfc(stem))

    for query_key in data["queries"]:
        # queries/name.md -> name
        stem = query_key.split("/")[-1]
        stem = stem[:-3] if stem.endswith(".md") else stem
        existing_stems.add(_nfc(stem))

    # Collect all link targets and their sources
    target_sources: dict[str, set[str]] = {}

    all_entries = [
        (k, v, "topic") for k, v in data["topics"].items()
    ] + [
        (k, v, "query") for k, v in data["queries"].items()
    ]

    for page_key, entry, _page_type in all_entries:
        for link in entry.get("links", []):
            # Extract stem (strip .md if present)
            link_stem = _nfc(link[:-3] if link.endswith(".md") else link)

            if link_stem not in existing_stems:
                if link_stem not in target_sources:
                    target_sources[link_stem] = set()
                target_sources[link_stem].add(page_key)

    # Build wanted list
    wanted = []
    for target, sources in target_sources.items():
        linked_from = sorted(sources, key=lambda x: _nfc(x))
        wanted.append({
            "target": target,
            "inbound": len(sources),
            "linked_from": linked_from
        })

    # Sort wanted: descending inbound, then ascending target, then linked_from already sorted
    wanted.sort(key=lambda x: (-x["inbound"], _nfc(x["target"])))

    # --- STALE: low-tier or index-stale topics ---

    stale = []

    # Check if index file exists and get its mtime
    index_path = config.index_path(vault)
    index_mtime = None
    if index_path.exists():
        with contextlib.suppress(OSError):
            index_mtime = index_path.stat().st_mtime_ns

    for topic_key, entry in data["topics"].items():
        tier = entry.get("quality_tier", "stub")
        topic_path = config.topics_dir(vault) / topic_key

        is_low_tier = tier in ["stub", "basic"]
        is_index_stale = False

        # Check index staleness
        if topic_path.exists():
            try:
                topic_mtime = topic_path.stat().st_mtime_ns
                # Topic is index-stale if:
                # - index doesn't exist, OR
                # - topic is newer than index
                if index_mtime is None or topic_mtime > index_mtime:
                    is_index_stale = True
            except OSError:
                pass

        # Determine reason (low_tier takes precedence over index_stale)
        if is_low_tier:
            stale.append({
                "path": topic_key,
                "tier": tier,
                "reason": "low_tier"
            })
        elif is_index_stale:
            stale.append({
                "path": topic_key,
                "tier": tier,
                "reason": "index_stale"
            })

    return {
        "wanted": wanted,
        "stale": stale
    }
