#!/usr/bin/env python3
"""Working-directory-independent launcher for the sibling exa_cli package."""
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS_DIR.parent
if Path(os.getcwd()).resolve() != _SKILL_DIR:
    os.chdir(_SKILL_DIR)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from exa_cli.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
