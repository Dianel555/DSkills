"""JSON stdout, stderr, and file-output helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


def redact_secret(data: Any, secret: str) -> Any:
    if not secret:
        return data
    if isinstance(data, str):
        return data.replace(secret, "***")
    if isinstance(data, dict):
        return {key: redact_secret(value, secret) for key, value in data.items()}
    if isinstance(data, list):
        return [redact_secret(value, secret) for value in data]
    return data


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
