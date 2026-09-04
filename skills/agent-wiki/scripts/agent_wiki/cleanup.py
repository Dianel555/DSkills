"""Cleanup operations for deleted sources."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from . import config, frontmatter


class TopicError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _read_topic(topic_path: Path) -> tuple[dict[str, Any], str, bool]:
    try:
        raw = topic_path.read_bytes()
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
    path.write_bytes(text.encode("utf-8"))
    return bool(meta["sources"])


def archive_topic(topic_path: str | Path, archive_dir: str | Path, today: date | str) -> Path:
    source = Path(topic_path)
    date_text = today.isoformat() if hasattr(today, "isoformat") else str(today)
    target_dir = Path(archive_dir) / date_text
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.move(str(source), str(target))
    return target
