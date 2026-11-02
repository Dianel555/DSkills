"""Cache management for incremental processing."""

from __future__ import annotations

import copy
import hashlib
import json
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import boundary, config

SCHEMA_VERSION = 1
_SCHEMA = {"version": SCHEMA_VERSION, "sources": {}}


class CacheWriteError(OSError):
    pass


class CacheNotWritableError(CacheWriteError):
    pass


class CacheConflictError(CacheWriteError):
    pass


class CacheReplaceError(CacheWriteError):
    pass


def empty_schema() -> dict[str, Any]:
    return copy.deepcopy(_SCHEMA)


def file_signature(path: str | Path) -> tuple[int, int] | None:
    path = Path(path)
    # A BoundaryError is deliberately not swallowed: it means the path is outside
    # every authorized vault, and reporting "no signature" would make the caller's
    # conflict check look like "cache absent" and skip the guard entirely.
    st = boundary.stat(path)
    if st is None:
        return None
    return st.st_mtime_ns, st.st_size


def load(vault: str | Path) -> dict[str, Any]:
    boundary.bind(vault)
    return load_with_signature(vault)[0]


def load_with_signature(vault: str | Path) -> tuple[dict[str, Any], tuple[int, int] | None]:
    boundary.bind(vault)
    path = config.cache_path(vault)
    if not path.exists():
        return empty_schema(), None
    signature = file_signature(path)
    try:
        text = boundary.read_text(path, encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError, boundary.BoundaryError) as exc:
        if isinstance(exc, boundary.BoundaryError):
            print(
                json.dumps(
                    {"warning": "cache_outside_vault", "path": str(path)}, ensure_ascii=False
                ),
                file=sys.stderr,
            )
            return empty_schema(), None
        print(json.dumps({"warning": "cache_parse_failed", "path": str(path)}, ensure_ascii=False), file=sys.stderr)
        return empty_schema(), signature
    if not isinstance(data, dict):
        return empty_schema(), signature
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("sources", {})
    return data, signature


def is_cache_writable(path: str | Path) -> bool:
    path = Path(path)
    parent = path.parent
    try:
        parent_st = boundary.stat(parent)
    except boundary.BoundaryError:
        return False
    if parent_st is None or not (parent_st.st_mode & stat.S_IWRITE):
        return False
    st = boundary.stat(path)
    return st is None or bool(st.st_mode & stat.S_IWRITE)


def save(vault: str | Path, data: dict[str, Any], expected_signature: tuple[int, int] | None = None) -> None:
    """Persist the cache, refusing to clobber a concurrent writer's version.

    ``expected_signature`` is the (mtime_ns, size) pair returned by
    ``load_with_signature``; a mismatch raises ``CacheConflictError`` before anything is
    written. The check runs twice - once lexically, once inside the verified directory
    handle immediately before the exclusive-temp publish - to close as much of the
    check/use window as the platform allows; the publish itself is atomic, so the
    worst residual outcome of two writers that both pass is "last complete write
    wins", never a torn file. ``expected_signature=None`` means the caller explicitly
    opts out of conflict detection and accepts that contract.
    """
    boundary.bind(vault)
    path = config.cache_path(vault)
    boundary.ensure_directory(path.parent)
    if not is_cache_writable(path):
        raise CacheNotWritableError("cache_not_writable")
    if expected_signature is not None and file_signature(path) != expected_signature:
        raise CacheConflictError("cache_conflict")

    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # Publish through the verified cache directory so the conflict re-check and the
    # replacement happen relative to one opened directory, never through a link.
    with boundary.fs_for(path).open_directory(path.parent) as handle:
        if expected_signature is not None and file_signature(path) != expected_signature:
            raise CacheConflictError("cache_conflict")
        try:
            handle.write_atomic(path.name, payload)
        except OSError as exc:
            raise CacheReplaceError(str(exc)) from exc


def sha256_file(path: str | Path) -> str:
    """Hash the bytes of a verified regular file below the authorized root."""
    h = hashlib.sha256()
    with boundary.open_read(path) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_signature(path: str | Path) -> tuple[int, int]:
    stat_result = boundary.stat(path)
    if stat_result is None:
        raise FileNotFoundError(2, "No such file or directory", str(path))
    return stat_result.st_mtime_ns, stat_result.st_size


def upsert(data: dict[str, Any], relpath: str, sha: str, mtime_ns: int, size: int, derived_topics: list[str]) -> None:
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("sources", {})
    data["sources"][config.normalize_relpath(relpath)] = {
        "sha256": sha,
        "mtime_ns": mtime_ns,
        "size": size,
        "last_ingest_at": datetime.now(UTC).isoformat(),
        "derived_topics": [config.normalize_relpath(topic) for topic in derived_topics],
    }


def remove(data: dict[str, Any], relpath: str) -> None:
    data.setdefault("sources", {}).pop(config.normalize_relpath(relpath), None)
