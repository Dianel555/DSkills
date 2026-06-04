"""Cache management for incremental processing."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config

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


def empty_schema() -> dict:
    return copy.deepcopy(_SCHEMA)


def file_signature(path: str | Path) -> tuple[int, int] | None:
    path = Path(path)
    if not path.exists():
        return None
    st = path.stat()
    return st.st_mtime_ns, st.st_size


def load(vault: str | Path) -> dict:
    return load_with_signature(vault)[0]


def load_with_signature(vault: str | Path) -> tuple[dict, tuple[int, int] | None]:
    path = config.cache_path(vault)
    if not path.exists():
        return empty_schema(), None
    signature = file_signature(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
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
    if path.exists() and not (path.stat().st_mode & stat.S_IWRITE):
        return False
    return parent.exists() and bool(parent.stat().st_mode & stat.S_IWRITE)


def save(vault: str | Path, data: dict, expected_signature: tuple[int, int] | None = None) -> None:
    path = config.cache_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not is_cache_writable(path):
        raise CacheNotWritableError("cache_not_writable")
    if expected_signature is not None and file_signature(path) != expected_signature:
        raise CacheConflictError("cache_conflict")

    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    try:
        if expected_signature is not None and file_signature(path) != expected_signature:
            raise CacheConflictError("cache_conflict")
        os.replace(tmp, path)
    except CacheConflictError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise CacheReplaceError(str(exc)) from exc


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_signature(path: str | Path) -> tuple[float, int]:
    stat_result = Path(path).stat()
    return stat_result.st_mtime, stat_result.st_size


def upsert(data: dict, relpath: str, sha: str, mtime: float, size: int, derived_topics: list[str]) -> None:
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("sources", {})
    data["sources"][config.normalize_relpath(relpath)] = {
        "sha256": sha,
        "mtime": mtime,
        "size": size,
        "last_ingest_at": datetime.now(timezone.utc).isoformat(),
        "derived_topics": [config.normalize_relpath(topic) for topic in derived_topics],
    }


def remove(data: dict, relpath: str) -> None:
    data.setdefault("sources", {}).pop(config.normalize_relpath(relpath), None)
