"""Cleanup operations for deleted sources."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from . import boundary, config, frontmatter


class TopicError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _read_topic(topic_path: Path) -> tuple[dict[str, Any], str, bool]:
    try:
        raw = boundary.read_bytes(topic_path)
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TopicError("topic_decode_failed") from exc
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as exc:
        raise TopicError("frontmatter_parse_failed") from exc
    return meta, body, has_bom


def remove_source_from_topic(topic_path: str | Path, deleted_rel: str) -> bool:
    path = Path(topic_path)
    meta, body, has_bom = _read_topic(path)
    deleted = config.normalize_relpath(deleted_rel)
    sources = [config.normalize_relpath(item) for item in meta.get("sources", [])]
    meta["sources"] = [source for source in sources if source != deleted]
    text = frontmatter.dump(meta, body)
    if has_bom:
        text = "﻿" + text
    boundary.write_text(path, text.encode("utf-8"))
    return bool(meta["sources"])


def archive_topic(topic_path: str | Path, archive_dir: str | Path, today: date | str) -> Path:
    """Move the source atomically through held directories without overwriting.

    Even an identical existing target is a conflict: comparing captured bytes then
    unlinking the source could delete a concurrent edit. Unsupported atomic moves
    and cross-filesystem moves fail closed, preserving both paths for reconciliation.
    """
    source = Path(topic_path)
    date_text = today.isoformat() if hasattr(today, "isoformat") else str(today)
    target_dir = Path(archive_dir) / date_text
    boundary.ensure_directory(target_dir)
    target = target_dir / source.name
    fs = boundary.fs_for(source)
    try:
        with fs.open_directory(source.parent) as src, fs.open_directory(target_dir) as dst:
            src.move_to(source.name, dst, target.name)
    except FileExistsError:
        raise TopicError("archive_target_conflict") from None
    except FileNotFoundError:
        raise TopicError("archive_source_missing") from None
    return target
