"""Maintenance worklists: wanted (broken link targets) and stale (low-quality/outdated) topics."""

from __future__ import annotations

import contextlib
import unicodedata
from pathlib import Path
from typing import Any

from . import cache, config, links, scanner, wiki_index


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def compute_worklist(vault: str | Path) -> dict[str, Any]:
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

    # --- WANTED: missing dedicated page targets ---
    target_sources: dict[str, set[str]] = {}
    ambiguous_sources: dict[str, tuple[set[str], set[str]]] = {}
    topic_keys = set(data["topics"])
    query_keys = set(data["queries"])
    alias_index = data.get("alias_index", {})

    all_entries = list(data["topics"].items()) + list(data["queries"].items())
    for page_key, entry in all_entries:
        for ref in links.from_entry(entry):
            resolution = links.resolve(ref.target, topic_keys, query_keys, alias_index)
            if resolution.status == "missing":
                target_sources.setdefault(ref.target, set()).add(page_key)
            elif resolution.status == "ambiguous":
                candidates, sources = ambiguous_sources.setdefault(ref.target, (set(resolution.candidates), set()))
                candidates.update(resolution.candidates)
                sources.add(page_key)

    wanted: list[dict[str, Any]] = []
    for target, sources in target_sources.items():
        linked_from = sorted(sources, key=lambda x: _nfc(x))
        wanted.append({
            "target": target,
            "inbound": len(sources),
            "linked_from": linked_from,
        })
    wanted.sort(key=lambda x: (-x["inbound"], _nfc(x["target"])))

    unresolved = [
        {
            "target": target,
            "status": "ambiguous",
            "candidates": sorted(candidates, key=_nfc),
            "linked_from": sorted(sources, key=_nfc),
        }
        for target, (candidates, sources) in ambiguous_sources.items()
    ]
    unresolved.sort(key=lambda item: _nfc(str(item["target"])))

    # --- STALE: low-tier or index-stale topics ---

    stale = []

    # A source change is a knowledge-review signal, not an index/cache signal.
    changed_paths: set[str] = set()
    changed_derived_topics: set[str] = set()
    try:
        classified = scanner.classify(vault, cache.load(vault))
    except (OSError, ValueError):
        classified = {}
    for bucket in ("new", "modified", "deleted"):
        for item in classified.get(bucket, []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                changed_paths.add(config.normalize_relpath(item["path"]))
                derived = item.get("derived_topics", [])
                if isinstance(derived, list):
                    changed_derived_topics.update(
                        config.normalize_relpath(str(topic)) for topic in derived
                    )

    def source_changed(page_key: str, entry: dict[str, Any]) -> bool:
        if entry.get("kind") == "topic" and page_key in changed_derived_topics:
            return True
        return any(
            isinstance(source, str)
            and not source.lower().startswith(("http://", "https://"))
            and config.normalize_relpath(source) in changed_paths
            for source in entry.get("sources", [])
        )

    review = [
        {"path": key, "kind": entry.get("kind", "topic"), "reason": "source_changed"}
        for key, entry in all_entries
        if source_changed(key, entry)
    ]
    review.sort(key=lambda item: _nfc(str(item["path"])))

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
        is_source_changed = source_changed(topic_key, entry)

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

        reasons = []
        if is_low_tier:
            reasons.append("low_tier")
        if is_source_changed:
            reasons.append("source_changed")
        if is_index_stale:
            reasons.append("index_stale")
        if reasons:
            primary = "low_tier" if is_low_tier else "source_changed" if is_source_changed else "index_stale"
            stale.append({
                "path": topic_key,
                "tier": tier,
                "reason": primary,
                "reasons": reasons,
            })

    return {
        "wanted": wanted,
        "unresolved": unresolved,
        "review": review,
        "stale": stale,
    }
