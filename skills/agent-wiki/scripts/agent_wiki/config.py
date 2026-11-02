"""Configuration and vault path resolution."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

from . import boundary


def nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


def atomic_write_text(path: Path, data: str | bytes) -> None:
    """Write inside the vault through a verified directory handle.

    The parent directory is opened without following links (see :mod:`boundary`), the
    payload goes to an exclusively created temporary file inside it, and the temporary
    file replaces the destination relative to that same directory. A link planted on
    the destination therefore never redirects the write, and neither does swapping the
    directory between the check and the write."""
    boundary.write_text(path, data)


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
    # Every derived path flows through here, so this is the single place where the vault
    # is registered as the authorized root for the boundary checks.
    boundary.bind(vault)
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
    """Express ``abs_path`` relative to ``vault``.

    The path is normalized lexically rather than resolved: resolving would follow a
    link and turn a path that is lexically inside the vault into one that is not, which
    makes the check depend on what the link points at instead of on the path itself.
    Link safety is the boundary module's job, at open time.
    """
    path = Path(os.path.normpath(Path(abs_path).expanduser()))
    root = Path(os.path.normpath(Path(vault).expanduser()))
    try:
        return normalize_relpath(path.relative_to(root).as_posix())
    except ValueError as exc:
        raise ValueError(f"{abs_path!r} is not inside the vault {vault!r}") from exc


def source_path(vault: str | Path, relpath: str | Path) -> Path:
    """A source path inside ``vault``; rejects traversal, not links."""
    rel = normalize_relpath(relpath)
    root = Path(os.path.normpath(Path(vault).expanduser()))
    path = Path(os.path.normpath(root / Path(rel)))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{relpath!r} escapes the vault {vault!r}") from exc
    return path


def topic_path(vault: str | Path, relpath: str | Path) -> Path:
    """Resolve a derived-topic relpath, constrained to wiki/topics (raises ValueError outside)."""
    rel = normalize_relpath(relpath)
    root = Path(os.path.normpath(topics_dir(vault)))
    path = Path(os.path.normpath(root / Path(rel)))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{relpath!r} is not inside wiki/topics") from exc
    return path
