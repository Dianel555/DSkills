"""Batched ingest planning.

Splits the sources still needing ingest (scan ``new`` + ``modified``) into
fixed-size batches so the Agent processes a bounded number of documents per round
instead of loading the whole vault at once. Persists a machine-readable plan
(``wiki/.wiki-batch.json``) plus a human-readable checklist report under the
archive directory; each round is gated behind an explicit completion check.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import cache, config, scanner

DEFAULT_BATCH_SIZE = 20
STATE_VERSION = 1


class BatchStateError(OSError):
    pass


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def report_path(vault: str | Path) -> Path:
    return config.archive_dir(vault) / "ingest-tasks.md"


def _pending_paths(vault: str | Path) -> list[str]:
    classified = scanner.classify(vault, cache.load(vault))
    items = classified.get("new", []) + classified.get("modified", [])
    return sorted(item["path"] for item in items)


def _chunk(paths: list[str], size: int) -> list[list[str]]:
    return [paths[i:i + size] for i in range(0, len(paths), size)]


def build_plan(vault: str | Path, batch_size: int) -> dict[str, Any]:
    paths = _pending_paths(vault)
    batches = [
        {"id": index + 1, "status": "pending", "items": chunk}
        for index, chunk in enumerate(_chunk(paths, batch_size))
    ]
    return {
        "version": STATE_VERSION,
        "generated_at": _now(),
        "batch_size": batch_size,
        "total": len(paths),
        "report": config.to_rel_posix(report_path(vault), vault),
        "batches": batches,
    }


def load_state(vault: str | Path) -> dict[str, Any] | None:
    path = config.batch_path(vault)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_state(vault: str | Path, data: dict[str, Any]) -> None:
    path = config.batch_path(vault)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise BatchStateError(str(exc)) from exc


def render_report(state: dict[str, Any]) -> str:
    lines = [
        "# Ingest Task Report",
        "",
        f"- generated_at: {state['generated_at']}",
        f"- batch_size: {state['batch_size']}",
        f"- total_documents: {state['total']}",
        f"- batches: {len(state['batches'])}",
        "",
    ]
    for batch in state["batches"]:
        mark = "x" if batch["status"] == "done" else " "
        lines.append(f"## Batch {batch['id']} ({len(batch['items'])}) [{mark}] {batch['status']}")
        for item in batch["items"]:
            lines.append(f"- [{mark}] {item}")
        lines.append("")
    return "\n".join(lines)


def write_report(vault: str | Path, state: dict[str, Any]) -> Path:
    path = report_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(state), encoding="utf-8")
    return path


def is_ingested(vault: str | Path, rel: str, tracked: dict[str, Any]) -> bool:
    """A batch item counts as done only if its current content is cached."""
    entry = tracked.get(config.normalize_relpath(rel))
    if not entry:
        return False
    source = config.source_path(vault, rel)
    if not source.is_file():
        return False
    try:
        return bool(cache.sha256_file(source) == entry.get("sha256"))
    except OSError:
        return False
