"""Configuration and vault path resolution."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any


def nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


def atomic_write_text(path: Path, data: str | bytes) -> None:
    """Write via same-dir temp file + ``os.replace``; the old file survives any failure."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        if isinstance(data, bytes):
            tmp.write_bytes(data)
        else:
            tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _json_stderr(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def resolve_vault(args_vault: str | None) -> Path:
    raw = args_vault or os.getenv("AGENT_WIKI_VAULT", "")
    if not raw:
        _json_stderr({"error": "vault path required", "hint": "pass --vault PATH or set AGENT_WIKI_VAULT"})
        sys.exit(2)

    vault = Path(nfc(raw)).expanduser().resolve()
    if not vault.is_dir():
        _json_stderr({"error": "vault not found", "path": str(vault)})
        sys.exit(2)
    return vault


def wiki_root(vault: str | Path) -> Path:
    return Path(vault).expanduser().resolve() / "wiki"


def cache_path(vault: str | Path) -> Path:
    return wiki_root(vault) / ".wiki-cache.json"


def index_path(vault: str | Path) -> Path:
    return wiki_root(vault) / ".wiki-index.json"


def batch_path(vault: str | Path) -> Path:
    return wiki_root(vault) / ".wiki-batch.json"


def topics_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "topics"


def queries_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "queries"


def graphs_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "graphs"


def archive_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "_archived"


def normalize_relpath(path: str | Path) -> str:
    value = str(path).replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        raise ValueError(f"absolute drive path not allowed: {path!r}")
    return nfc(value)


def to_rel_posix(abs_path: str | Path, vault: str | Path) -> str:
    path = Path(abs_path).expanduser().resolve()
    root = Path(vault).expanduser().resolve()
    return normalize_relpath(path.relative_to(root).as_posix())


def source_path(vault: str | Path, relpath: str | Path) -> Path:
    rel = normalize_relpath(relpath)
    path = (Path(vault).expanduser().resolve() / Path(rel)).resolve()
    path.relative_to(Path(vault).expanduser().resolve())
    return path


def topic_path(vault: str | Path, relpath: str | Path) -> Path:
    """Resolve a derived-topic relpath, constrained to wiki/topics (raises ValueError outside)."""
    rel = normalize_relpath(relpath)
    root = topics_dir(vault)
    path = (root / Path(rel)).resolve()
    path.relative_to(root)
    return path
