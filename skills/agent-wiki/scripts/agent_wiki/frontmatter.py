"""YAML frontmatter parsing and serialization."""

from __future__ import annotations

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required: pip install PyYAML") from exc


class FrontmatterError(ValueError):
    pass


def parse(text: str) -> tuple[dict, str]:
    bom = "﻿" if text.startswith("﻿") else ""
    source = text[1:] if bom else text
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return {}, text

    raw_meta = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    try:
        meta = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(str(exc)) from exc
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter must be a mapping")
    return meta, body


def dump(meta: dict, body: str) -> str:
    yaml_text = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n\n{body}"
