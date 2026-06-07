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

from . import config, frontmatter

INDEX_VERSION = 1
EPOCH = "1970-01-01T00:00:00Z"
_SUMMARY_LIMIT = 1000
_YEAR_RE = re.compile(r"\d{4}")


class NormalizedPathCollision(Exception):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(path)


class IndexWriteError(OSError):
    pass


def empty_schema() -> dict:
    return {"version": INDEX_VERSION, "generated_at": EPOCH, "topics": {}}


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


def _entry(rel: str, meta: dict, stem: str) -> dict:
    return {
        "path": rel,
        "title": _title(meta.get("title"), stem),
        "sources": _sources(meta.get("sources")),
        "last_updated": _str_field(meta.get("last_updated")),
        "year_start": _year(meta.get("year_start")),
        "year_end": _year(meta.get("year_end")),
        "authors": _str_list(meta.get("authors")),
        "source_type": _str_field(meta.get("source_type")),
        "institutions": _str_list(meta.get("institutions")),
        "methods": _str_list(meta.get("methods")),
        "technical_routes": _str_list(meta.get("technical_routes")),
        "research_trends": _str_list(meta.get("research_trends")),
        "summary": _summary(meta.get("summary")),
        "keywords": _str_list(meta.get("keywords")),
    }


def _iso_utc(mtime_ns: int) -> str:
    seconds = mtime_ns // 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rebuild(vault: str | Path) -> tuple[dict, list[dict]]:
    """Build the index from topic frontmatter.

    Returns ``(data, errors)``. Decode/parse failures are skipped and reported;
    a normalized-key collision is fatal and raises ``NormalizedPathCollision``.
    """
    topics_root = config.topics_dir(vault)
    files = list(topics_root.glob("*.md")) if topics_root.exists() else []
    files.sort(key=lambda p: config.normalize_relpath(p.relative_to(topics_root).as_posix()))

    topics: dict[str, dict] = {}
    errors: list[dict] = []
    max_mtime = 0
    seen: set[str] = set()

    for path in files:
        rel = config.normalize_relpath(path.relative_to(topics_root).as_posix())
        if rel in seen:
            raise NormalizedPathCollision(rel)
        seen.add(rel)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            errors.append({"path": rel, "error": "topic_decode_failed"})
            continue
        try:
            meta, _ = frontmatter.parse(text)
        except frontmatter.FrontmatterError:
            errors.append({"path": rel, "error": "frontmatter_parse_failed"})
            continue
        topics[rel] = _entry(rel, meta, path.stem)
        try:
            max_mtime = max(max_mtime, path.stat().st_mtime_ns)
        except OSError:
            pass

    data = {
        "version": INDEX_VERSION,
        "generated_at": _iso_utc(max_mtime) if topics else EPOCH,
        "topics": topics,
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
