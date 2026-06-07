"""Configuration and vault path resolution."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _json_stderr(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def resolve_vault(args_vault: str | None) -> Path:
    raw = args_vault or os.getenv("AGENT_WIKI_VAULT", "")
    if not raw:
        _json_stderr({"error": "vault path required", "hint": "pass --vault PATH or set AGENT_WIKI_VAULT"})
        sys.exit(2)

    vault = Path(_nfc(raw)).expanduser().resolve()
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


def topics_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "topics"


def archive_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / "_archived"


def url_cache_dir(vault: str | Path) -> Path:
    return wiki_root(vault) / ".wiki-url-cache"


def normalize_relpath(path: str | Path) -> str:
    value = str(path).replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return _nfc(value)


def to_rel_posix(abs_path: str | Path, vault: str | Path) -> str:
    path = Path(abs_path).expanduser().resolve()
    root = Path(vault).expanduser().resolve()
    return normalize_relpath(path.relative_to(root).as_posix())


def source_path(vault: str | Path, relpath: str | Path) -> Path:
    rel = normalize_relpath(relpath)
    path = (Path(vault).expanduser().resolve() / Path(rel)).resolve()
    path.relative_to(Path(vault).expanduser().resolve())
    return path
