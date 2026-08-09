from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"

for path in reversed((str(SKILL_ROOT), str(SCRIPTS_DIR))):
    if path not in sys.path:
        sys.path.insert(0, path)


def command_module(name: str):
    flat_name = f"exa_cli.{name}"
    try:
        __import__(flat_name)
        return sys.modules[flat_name]
    except ModuleNotFoundError as exc:
        if exc.name != flat_name:
            raise
    legacy_name = f"exa_cli.commands.{name}"
    __import__(legacy_name)
    return sys.modules[legacy_name]
