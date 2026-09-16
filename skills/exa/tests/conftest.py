"""Put tests/ and scripts/ on sys.path so pytest collection finds `_support` and `exa_cli`."""

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_SCRIPTS = _TESTS.parent / "scripts"
for path in (str(_TESTS), str(_SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)
