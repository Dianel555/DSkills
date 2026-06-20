"""Derived retrieval index (``wiki/.wiki-index.json``).

The index normalizes common research metadata from ``wiki/topics/*.md``
frontmatter into a deterministic JSON cache for fast Agent routing. Topic
markdown stays the single source of truth; the index is never written back
into topic files.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import config, frontmatter, quality, source_type

INDEX_VERSION = 1
EPOCH = "1970-01-01T00:00:00Z"
_SUMMARY_LIMIT = 1000
_YEAR_RE = re.compile(r"\d{4}")
_WIKILINK_RE = re.compile(r"!?\[\[(.+?)\]\]")


class NormalizedPathCollision(Exception):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(path)


class IndexWriteError(OSError):
    pass


def empty_schema() -> dict:
    return {"version": INDEX_VERSION, "generated_at": EPOCH, "topics": {}, "queries": {}, "alias_index": {}}


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", str(value))


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    return [_nfc(value)]


def _str_field(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return _nfc(value[0]) if value else ""
    return _nfc(value)


def _title(value, stem: str) -> str:
    if value is None:
        return _nfc(stem)
    if isinstance(value, list):
        return _nfc(" ".join(str(item) for item in value))
    return _nfc(value)


def _sources(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [config.normalize_relpath(str(item)) for item in items]


def _year(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return _year(value[0]) if value else None
    if not isinstance(value, str):
        return None
    match = _YEAR_RE.search(value)
    return int(match.group()) if match else None


def _summary(value) -> str:
    if value is None:
        text = ""
    elif isinstance(value, list):
        text = "; ".join(str(item) for item in value)
    else:
        text = str(value)
    return _nfc(text)[:_SUMMARY_LIMIT]


def _parse_links(body: str) -> list[str]:
    """`[[Target]]`/`![[Target]]` targets from a page body, alias and
    heading/block suffixes stripped, NFC-normalized, order-preserved, deduped."""
    links: list[str] = []
    seen: set[str] = set()
    for match in _WIKILINK_RE.finditer(body):
        target = match.group(1)
        for sep in ("|", "#", "^"):
            target = target.split(sep, 1)[0]
        target = _nfc(target.strip())
        if target and target not in seen:
            seen.add(target)
            links.append(target)
    return links


def _entry(rel: str, meta: dict, stem: str, kind: str, links: list[str], body: str = "") -> dict:
    """Build an index entry. Topic entries include extended fields; query entries preserve their current schema."""
    sources = _sources(meta.get("sources"))
    entry = {
        "path": rel,
        "title": _title(meta.get("title"), stem),
        "sources": sources,
        "last_updated": _str_field(meta.get("last_updated")),
        "year_start": _year(meta.get("year_start")),
        "year_end": _year(meta.get("year_end")),
        "authors": _str_list(meta.get("authors")),
        "source_type": source_type.classify_sources(sources),
        "institutions": _str_list(meta.get("institutions")),
        "methods": _str_list(meta.get("methods")),
        "technical_routes": _str_list(meta.get("technical_routes")),
        "research_trends": _str_list(meta.get("research_trends")),
        "summary": _summary(meta.get("summary")),
        "keywords": _str_list(meta.get("keywords")),
        "kind": kind,
        "links": links,
    }

    # Add topic-only fields
    if kind == "topic":
        # type: optional page kind (orthogonal to derived source_type)
        type_value = meta.get("type")
        if isinstance(type_value, str):
            entry["type"] = _nfc(type_value)
        else:
            entry["type"] = ""

        # aliases: order-preserved list (not deduplicated)
        entry["aliases"] = _str_list(meta.get("aliases"))

        # quality_tier: computed from body with source grounding
        # Use deduplicated source count (per D3.3)
        unique_sources = len(set(sources))
        entry["quality_tier"] = quality.compute_tier(body, source_count=unique_sources)

        # featured: strict boolean coercion
        featured_value = meta.get("featured")
        entry["featured"] = featured_value is True

        # backlinks: initialized to 0, computed later in rebuild
        entry["backlinks"] = 0

    return entry


def _iso_utc(mtime_ns: int) -> str:
    seconds = mtime_ns // 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _index_dir(directory: Path, key_root: Path, kind: str, entries: dict, errors: list, mtimes: list) -> None:
    """Index every ``*.md`` under ``directory`` into ``entries`` keyed by its NFC
    POSIX path relative to ``key_root``; per-directory collision detection."""
    files = list(directory.glob("*.md")) if directory.exists() else []
    files.sort(key=lambda p: config.normalize_relpath(p.relative_to(key_root).as_posix()))
    seen: set[str] = set()
    for path in files:
        rel = config.normalize_relpath(path.relative_to(key_root).as_posix())
        if rel in seen:
            raise NormalizedPathCollision(rel)
        seen.add(rel)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            errors.append({"path": rel, "error": "topic_decode_failed"})
            continue
        try:
            meta, body = frontmatter.parse(text)
        except frontmatter.FrontmatterError:
            errors.append({"path": rel, "error": "frontmatter_parse_failed"})
            continue
        entries[rel] = _entry(rel, meta, path.stem, kind, _parse_links(body), body)
        try:
            mtimes.append(path.stat().st_mtime_ns)
        except OSError:
            pass


def rebuild(vault: str | Path) -> tuple[dict, list[dict]]:
    """Build the index from topic and query frontmatter.

    Topic keys are ``wiki/topics/``-relative (bare ``<name>.md``); query
    keys are ``wiki/``-relative (``queries/<name>.md``). Returns ``(data,
    errors)``. Decode/parse failures are skipped and reported; a normalized-key
    collision within a directory is fatal and raises ``NormalizedPathCollision``.
    """
    wiki = config.wiki_root(vault)
    topics_root = config.topics_dir(vault)
    topics: dict[str, dict] = {}
    queries: dict[str, dict] = {}
    errors: list[dict] = []
    mtimes: list[int] = []

    _index_dir(topics_root, topics_root, "topic", topics, errors, mtimes)
    _index_dir(config.queries_dir(vault), wiki, "query", queries, errors, mtimes)

    # Build alias_index from frontmatter aliases + optional .wiki-aliases.json
    alias_index: dict[str, str] = {}
    alias_sources: dict[str, list[str]] = {}  # Track sources for conflict detection

    # Collect frontmatter aliases
    for topic_key, topic_entry in topics.items():
        for alias in topic_entry.get("aliases", []):
            alias_nfc = _nfc(alias)
            if alias_nfc not in alias_sources:
                alias_sources[alias_nfc] = []
            alias_sources[alias_nfc].append(topic_key)

    # Merge optional .wiki-aliases.json
    aliases_file = wiki / ".wiki-aliases.json"
    if aliases_file.exists():
        try:
            aliases_text = aliases_file.read_text(encoding="utf-8")
            aliases_map = json.loads(aliases_text)
            if not isinstance(aliases_map, dict):
                errors.append({"error": "alias_map_invalid"})
            else:
                for alias, target in aliases_map.items():
                    if not isinstance(alias, str) or not isinstance(target, str):
                        errors.append({"error": "alias_map_invalid"})
                        continue
                    alias_nfc = _nfc(alias)
                    target_nfc = _nfc(target)
                    if alias_nfc not in alias_sources:
                        alias_sources[alias_nfc] = []
                    alias_sources[alias_nfc].append(target_nfc)
        except (json.JSONDecodeError, UnicodeDecodeError):
            errors.append({"error": "alias_map_invalid"})

    # Resolve aliases: check for conflicts and missing targets
    topic_keys = set(topics.keys())
    for alias_nfc, targets in alias_sources.items():
        # Deduplicate targets
        unique_targets = sorted(set(targets))

        # Check if alias conflicts with a real topic key
        if alias_nfc in topic_keys:
            unique_targets.append(alias_nfc)
            unique_targets = sorted(set(unique_targets))

        # Check for missing targets
        valid_targets = [t for t in unique_targets if t in topic_keys]

        # Report missing targets
        for target in unique_targets:
            if target not in topic_keys:
                errors.append({"alias": alias_nfc, "error": "alias_target_missing", "target": target})

        # Check for conflicts
        if len(valid_targets) > 1:
            errors.append({"alias": alias_nfc, "error": "alias_conflict", "candidates": valid_targets})
        elif len(valid_targets) == 1:
            alias_index[alias_nfc] = valid_targets[0]

    # Compute backlinks (inbound link count per topic)
    backlinks: dict[str, set[str]] = {key: set() for key in topic_keys}

    # Helper: extract stem from wikilink target (strip #heading and |alias)
    def _link_stem(link: str) -> str:
        link = link.split("#")[0]  # Strip heading
        link = link.split("|")[0]  # Strip alias
        return link.strip()

    # Collect all linkers (topics, queries)
    all_entries = list(topics.items()) + list(queries.items())

    for source_key, source_entry in all_entries:
        for link in source_entry.get("links", []):
            target_stem = _link_stem(link)
            # Resolve to topic key (add .md if needed)
            if not target_stem.endswith(".md"):
                target_key = target_stem + ".md"
            else:
                target_key = target_stem

            # Only count if target exists and is not self-link
            if target_key in topic_keys and target_key != source_key.split("/")[-1]:
                backlinks[target_key].add(source_key)

    # Update topic entries with backlink counts
    for topic_key in topic_keys:
        topics[topic_key]["backlinks"] = len(backlinks[topic_key])

    data = {
        "version": INDEX_VERSION,
        "generated_at": _iso_utc(max(mtimes)) if mtimes else EPOCH,
        "topics": topics,
        "queries": queries,
        "alias_index": dict(sorted(alias_index.items())),
    }
    return data, errors


def serialize(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def save_index(vault: str | Path, data: dict) -> None:
    path = config.index_path(vault)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(serialize(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise IndexWriteError(str(exc)) from exc
