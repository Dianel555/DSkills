"""Derived retrieval index (``wiki/.wiki-index.json``).

The index normalizes common research metadata from ``wiki/topics/*.md``
frontmatter into a deterministic JSON cache for fast Agent routing. Topic
markdown stays the single source of truth; the index is never written back
into topic files.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import config, frontmatter, quality, source_type

INDEX_VERSION = 1
EPOCH = "1970-01-01T00:00:00Z"
_SUMMARY_LIMIT = 1000
_YEAR_RE = re.compile(r"\d{4}")
_WIKILINK_RE = re.compile(r"!?\[\[(.+?)\]\]")


class NormalizedPathCollisionError(Exception):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(path)


class IndexWriteError(OSError):
    pass


def empty_schema() -> dict[str, Any]:
    return {"version": INDEX_VERSION, "generated_at": EPOCH, "topics": {}, "queries": {}, "alias_index": {}}


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", str(value))


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    return [_nfc(value)]


def _str_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return _nfc(value[0]) if value else ""
    return _nfc(value)


def _title(value: Any, stem: str) -> str:
    if value is None:
        return _nfc(stem)
    if isinstance(value, list):
        return _nfc(" ".join(str(item) for item in value))
    return _nfc(value)


def _sources(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [config.normalize_relpath(str(item)) for item in items]


def _year(value: Any) -> int | None:
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


def _summary(value: Any) -> str:
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


def _entry(rel: str, meta: dict[str, Any], stem: str, kind: str, links: list[str], body: str = "", mtime_ns: int = 0) -> dict[str, Any]:
    """Build an index entry. Topic entries include extended fields; query entries preserve their current schema."""
    sources = _sources(meta.get("sources"))
    entry: dict[str, Any] = {
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
        "mtime_ns": mtime_ns,
    }

    # Add topic-only fields
    if kind == "topic":
        # Optional page kind (orthogonal to derived source_type)
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
    return datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_doc(job: tuple[str, Path, str]) -> tuple[str, int, dict[str, Any] | None, dict[str, Any] | None]:
    """Parse one topic/query file into ``(rel, mtime_ns, entry, error)``. Runs in worker threads.

    Stats the file here (tight against ``read_text``) so the entry's
    ``mtime_ns`` tracks the content actually read, not the earlier stat done
    in ``_index_dir`` for the reuse decision — closes the bulk of the TOCTOU
    window; a residual stat→read gap self-heals on the next rebuild.
    """
    rel, path, kind = job
    try:
        st = path.stat()
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return rel, 0, None, {"path": rel, "error": "topic_decode_failed"}
    mtime_ns = st.st_mtime_ns
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError:
        return rel, mtime_ns, None, {"path": rel, "error": "frontmatter_parse_failed"}
    return rel, mtime_ns, _entry(rel, meta, path.stem, kind, _parse_links(body), body, mtime_ns), None


def _index_dir(
    directory: Path,
    key_root: Path,
    kind: str,
    entries: dict[str, Any],
    errors: list[dict[str, Any]],
    mtimes: list[int],
    *,
    existing_index: dict[str, Any] | None = None,
    workers: int = 8,
) -> None:
    """Index every ``*.md`` under ``directory`` into ``entries`` keyed by its NFC
    POSIX path relative to ``key_root``; per-directory collision detection.

    When ``existing_index`` is provided, entries whose stored ``mtime_ns``
    matches the file's current mtime are reused without re-parsing. Changed and
    new files are parsed in parallel with a bounded thread pool."""
    files = list(directory.glob("*.md")) if directory.exists() else []
    files.sort(key=lambda p: config.normalize_relpath(p.relative_to(key_root).as_posix()))
    seen: set[str] = set()
    jobs: list[tuple[str, Path, str]] = []
    for path in files:
        rel = config.normalize_relpath(path.relative_to(key_root).as_posix())
        if rel in seen:
            raise NormalizedPathCollisionError(rel)
        seen.add(rel)
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            # Same code the parse path would have reported
            errors.append({"path": rel, "error": "topic_decode_failed"})
            continue
        cached = existing_index.get(rel) if existing_index else None
        if isinstance(cached, dict) and cached.get("mtime_ns") == mtime_ns:
            entries[rel] = cached
            mtimes.append(mtime_ns)
        else:
            jobs.append((rel, path, kind))

    if len(jobs) < 2:
        parsed = [_parse_doc(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
            parsed = list(pool.map(_parse_doc, jobs))
    for rel, mtime_ns, entry, error in parsed:
        if entry is not None:
            entries[rel] = entry
            mtimes.append(mtime_ns)
        if error is not None:
            errors.append(error)


def rebuild(vault: str | Path, *, incremental: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build the index from topic and query frontmatter.

    When ``incremental=True``, reuses existing index entries whose stored
    mtime matches the file on disk; only changed and new files are re-parsed.
    Topic keys are ``wiki/topics/``-relative (bare ``<name>.md``); query
    keys are ``wiki/``-relative (``queries/<name>.md``). Returns ``(data,
    errors)``. Decode/parse failures are skipped and reported; a normalized-key
    collision within a directory is fatal and raises ``NormalizedPathCollisionError``.
    """
    wiki = config.wiki_root(vault)
    topics_root = config.topics_dir(vault)

    # Load existing index if incremental mode. Validate top-level shape and the
    # topics/queries maps so a corrupted/hand-edited index (null, array, or a
    # non-dict entry) falls back to a full rebuild instead of crashing.
    existing_topics: dict[str, Any] | None = None
    existing_queries: dict[str, Any] | None = None
    if incremental:
        index_path = config.index_path(vault)
        if index_path.exists():
            try:
                existing_data = json.loads(index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                existing_data = None
            if isinstance(existing_data, dict):
                topics_field = existing_data.get("topics", {})
                queries_field = existing_data.get("queries", {})
                if isinstance(topics_field, dict):
                    existing_topics = topics_field
                if isinstance(queries_field, dict):
                    existing_queries = queries_field

    topics: dict[str, Any] = {}
    queries: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    mtimes: list[int] = []

    _index_dir(topics_root, topics_root, "topic", topics, errors, mtimes, existing_index=existing_topics)
    _index_dir(config.queries_dir(vault), wiki, "query", queries, errors, mtimes, existing_index=existing_queries)

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
            target_key = target_stem + ".md" if not target_stem.endswith(".md") else target_stem

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


def serialize(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def save_index(vault: str | Path, data: dict[str, Any]) -> None:
    path = config.index_path(vault)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(serialize(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise IndexWriteError(str(exc)) from exc
