"""Extract and aggregate paper authors from topic sources (read-only).

Drives the batched authors backfill: ``extract`` resolves each topic's
``sources`` to the root-level source notes and pulls the ``作者:`` row from each
note's metadata table; ``aggregate`` deduplicates the first author per paper into
a per-topic list the Agent can write into frontmatter. Neither modifies files.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from . import config, frontmatter

_AUTHOR_RE = re.compile(r"作者[:：]\s*(.+)")
_FIELD_BREAK = re.compile(r"\s*(期刊|DOI|标签|摘要)[:：]")
_TAG_RE = re.compile(r"<[^>]+>")


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _root_notes(vault: Path) -> dict[str, Path]:
    # Root-level source notes only (wiki/ and attachments/ are subdirectories).
    return {_nfc(path.name): path for path in vault.glob("*.md")}


def _resolve(src: str, root_by_norm: dict[str, Path]) -> Path | None:
    name = _nfc(src)
    if name in root_by_norm:
        return root_by_norm[name]
    # sources[] entries may be truncated mid-title; match by longest common prefix.
    stem = name[:-3] if name.endswith(".md") else name
    pref = stem[:60]
    best: tuple[str, Path] | None = None
    for norm, path in root_by_norm.items():
        cand = norm[:-3] if norm.endswith(".md") else norm
        if (cand.startswith(pref) or stem.startswith(cand[:60])) and (best is None or len(cand) < len(best[0])):
            best = (cand, path)
    return best[1] if best else None


def _authors_row(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if "作者" in line and "|" in line:
            plain = _TAG_RE.sub("", line).replace("|", " ").strip()
            match = _AUTHOR_RE.search(plain)
            if match:
                return _FIELD_BREAK.split(match.group(1).strip())[0].strip()
    return ""


def extract(vault: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Per-topic raw author strings resolved from each source note."""
    vault = Path(vault)
    root_by_norm = _root_notes(vault)
    out: dict[str, list[dict[str, Any]]] = {}
    for topic in sorted(config.topics_dir(vault).glob("*.md")):
        meta, _ = frontmatter.parse(topic.read_text(encoding="utf-8-sig"))
        entries: list[dict[str, Any]] = []
        for src in meta.get("sources") or []:
            resolved = _resolve(str(src), root_by_norm)
            entries.append({
                "src": str(src)[:40],
                "file": resolved.name[:40] if resolved else None,
                "authors": _authors_row(resolved) if resolved else "",
            })
        out[_nfc(topic.name)] = entries
    return out


def first_author(raw: str) -> str:
    s = raw.lstrip("*").strip()
    if not s:
        return ""
    first = s.split(";")[0].strip()
    return first.replace("et al.", "").strip().strip(",").strip()


def aggregate(extracted: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    """Deduplicated first author per topic, order preserved."""
    out: dict[str, list[str]] = {}
    for topic, entries in extracted.items():
        seen: list[str] = []
        for entry in entries:
            name = first_author(entry.get("authors", ""))
            if name and name not in seen:
                seen.append(name)
        out[topic] = seen
    return out
