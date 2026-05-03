"""stdout/stderr JSON output helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


def output_json(data: Any, out_file: Optional[str] = None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print(json.dumps({"status": "ok", "file": out_file}, ensure_ascii=False))
    else:
        print(text)


def output_error(message: str, code: int = 1) -> None:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def output_warning(message: str) -> None:
    print(json.dumps({"warning": message}, ensure_ascii=False), file=sys.stderr)
