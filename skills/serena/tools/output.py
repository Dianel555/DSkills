"""JSON output utilities for CLI."""
import json
import sys
from typing import Any


def output_json(data: Any, indent: int = 2) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=indent, ensure_ascii=False))


def output_error(code: str, message: str) -> None:
    """Print error JSON and exit."""
    output_json({"error": {"code": code, "message": message}})
    sys.exit(1)
