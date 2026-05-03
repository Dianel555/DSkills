#!/usr/bin/env python3
"""Shim launcher for exa_cli package.

If cwd is not skills/exa, chdir there so .env discovery & relative paths
behave the same regardless of where the user invokes the script from.
"""
import os
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
if Path(os.getcwd()).resolve() != _SKILL_DIR:
    os.chdir(_SKILL_DIR)
sys.path.insert(0, str(_SKILL_DIR))

from exa_cli.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
