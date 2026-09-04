"""Detect Obsidian community plugins relevant to homepage rendering.

Read-only inspection of the Obsidian config directory (the ``.obsidian`` folder
found by walking up from the vault). gen-home uses this to decide whether it can
emit a live Dataview card block or must fall back to a static list. Any missing
file or parse error is treated as "not available" — detection never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def obsidian_config_dir(vault: str | Path) -> Path | None:
    """The ``.obsidian`` directory at or above ``vault``; None when none exists."""
    current = Path(vault).expanduser().resolve()
    while True:
        candidate = current / ".obsidian"
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def dataview_installed(vault: str | Path) -> bool:
    """True when ``dataview`` appears in ``.obsidian/community-plugins.json``."""
    cfg = obsidian_config_dir(vault)
    if cfg is None:
        return False
    data = _read_json(cfg / "community-plugins.json")
    return isinstance(data, list) and "dataview" in data


def dataviewjs_enabled(vault: str | Path) -> bool:
    """True when Dataview's ``enableDataviewJs`` setting is on (required for the
    ``dataviewjs`` card block to execute)."""
    cfg = obsidian_config_dir(vault)
    if cfg is None:
        return False
    data = _read_json(cfg / "plugins" / "dataview" / "data.json")
    return isinstance(data, dict) and data.get("enableDataviewJs") is True


def cards_available(vault: str | Path) -> bool:
    """True only when Dataview is installed *and* its JavaScript queries are on —
    both are needed to render the dynamic card grid."""
    return dataview_installed(vault) and dataviewjs_enabled(vault)
