"""Derive a topic's ``source_type`` from the file formats of its sources.

Maps each source reference (path or URL) in a topic's ``sources`` list to a
coarse format category, then reduces the set to a single value (``"mixed"`` only
when a topic genuinely spans multiple formats). ``source_type`` is always
format-derived and lowercase ASCII; the frontmatter value is a materialized copy
that ``normalize-source-type`` rewrites in place.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from . import config, frontmatter

_EXTENSION_TYPES = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
    ".doc": "word",
    ".docx": "word",
    ".rtf": "word",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".xlsm": "spreadsheet",
    ".csv": "spreadsheet",
    ".tsv": "spreadsheet",
    ".ppt": "slides",
    ".pptx": "slides",
    ".txt": "text",
}


def _nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


def classify_ref(ref: str) -> str:
    """Format category of a single source reference (path or URL)."""
    text = _nfc(ref).strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        return "web"
    ext = PurePosixPath(lowered.replace("\\", "/")).suffix
    return _EXTENSION_TYPES.get(ext, "other")


def classify_sources(sources: Any) -> str:
    """Reduce a topic's ``sources`` to one format, ``"mixed"``, or ``""``."""
    if not isinstance(sources, list):
        sources = [sources] if sources else []
    kinds = {classify_ref(str(item)) for item in sources}
    kinds.discard("")
    if not kinds:
        return ""
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def backfill(vault: str | Path) -> dict[str, Any]:
    """Rewrite each topic's ``source_type`` frontmatter to its ``sources[]``
    format, in place. Topics already matching, or with no sources to derive a
    format from, are left untouched (no mtime churn). Returns changed/skipped/errors."""
    topics_dir = config.topics_dir(vault)
    changed: list[dict[str, Any]] = []
    skipped = 0
    errors: list[dict[str, Any]] = []
    for path in sorted(topics_dir.glob("*.md")):
        rel = config.normalize_relpath(path.name)
        try:
            raw = path.read_bytes()
            has_bom = raw.startswith(b"\xef\xbb\xbf")
            meta, body = frontmatter.parse(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, frontmatter.FrontmatterError):
            errors.append({"path": rel, "error": "topic_parse_failed"})
            continue
        derived = classify_sources(meta.get("sources"))
        current = meta.get("source_type")
        current_str = _nfc(current).strip() if current is not None else ""
        if not derived or current_str == derived:
            skipped += 1
            continue
        meta["source_type"] = derived
        text = frontmatter.dump(meta, body)
        if has_bom:
            text = "﻿" + text
        path.write_bytes(text.encode("utf-8"))
        changed.append({"path": rel, "source_type": derived})
    return {"changed": changed, "skipped": skipped, "errors": errors}
