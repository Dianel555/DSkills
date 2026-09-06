"""Small, shared parser for Obsidian and Markdown links.

The wiki keeps the historical ``links`` string list for compatibility, while
``link_records`` carries the information needed by views that must preserve a
heading, block, or embed target. Parsing is deliberately syntax-only: it does
not try to emulate every Obsidian plugin.
"""

from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)(?:\r?\n)?$")
_CODE_RUN_RE = re.compile(r"`+")
_WIKILINK_RE = re.compile(r"!?\[\[([^\[\]]+?)\]\]")


@dataclass(frozen=True)
class LinkRef:
    """One link-like reference found outside fenced/inline code."""

    target: str
    label: str
    fragment: str
    embed: bool
    syntax: str


@dataclass(frozen=True)
class Resolution:
    """Canonical page resolution for a link target."""

    status: str
    target: str
    key: str | None = None
    candidates: tuple[str, ...] = ()


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def normalize_target(value: str) -> str:
    """Normalize a vault-relative target without changing URL semantics."""
    value = html.unescape(value).strip()
    if value.lower().startswith(("http://", "https://", "mailto:")):
        return _nfc(value)
    decoded = urllib.parse.unquote(value.replace("\\", "/"))
    while decoded.startswith("./"):
        decoded = decoded[2:]
    return _nfc(decoded)


def _split_target(value: str) -> tuple[str, str]:
    value = value.strip()
    for separator in ("#", "^"):
        if separator in value:
            target, fragment = value.split(separator, 1)
            fragment = html.unescape(fragment).strip()
            return normalize_target(target), separator + fragment if separator == "^" else fragment
    return normalize_target(value), ""


def _wikilink(raw: str) -> LinkRef:
    spec, separator, label = raw.partition("|")
    target, fragment = _split_target(spec)
    label = _nfc((label if separator else target).strip())
    return LinkRef(target=target, label=label, fragment=fragment, embed=False, syntax="wikilink")


def _embed_wikilink(raw: str) -> LinkRef:
    ref = _wikilink(raw)
    return LinkRef(ref.target, ref.label, ref.fragment, True, ref.syntax)


def _markdown_link(embed: str, label: str, destination: str) -> LinkRef:
    destination = destination[1:-1] if destination.startswith("<") and destination.endswith(">") else destination
    target, fragment = _split_target(destination)
    return LinkRef(target=target, label=_nfc(label.strip() or target), fragment=fragment,
                   embed=bool(embed), syntax="markdown")


def _code_ranges(line: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while opening := _CODE_RUN_RE.search(line, cursor):
        length = len(opening.group(0))
        closing = next(
            (candidate for candidate in _CODE_RUN_RE.finditer(line, opening.end())
             if len(candidate.group(0)) == length),
            None,
        )
        if closing is None:
            cursor = opening.end()
            continue
        ranges.append((opening.start(), closing.end()))
        cursor = closing.end()
    return ranges


def _outside_code(line: str) -> Iterable[tuple[int, int]]:
    """Yield non-inline-code ranges in a single line."""
    pos = 0
    for start, end in _code_ranges(line):
        if start > pos:
            yield pos, start
        pos = end
    if pos < len(line):
        yield pos, len(line)


def _markdown_destination(text: str, start: int) -> tuple[int, str] | None:
    """Return ``(exclusive end, destination)`` for one Markdown destination."""
    if start >= len(text):
        return None
    if text[start] == "<":
        close = text.find(">", start + 1)
        if close < 0:
            return None
        destination = text[start + 1:close]
        cursor = close + 1
    else:
        cursor = start
        depth = 0
        while cursor < len(text):
            char = text[cursor]
            if char == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    return cursor + 1, text[start:cursor]
                depth -= 1
            elif char.isspace() and depth == 0:
                break
            cursor += 1
        if cursor >= len(text):
            return None
        destination = text[start:cursor]

    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    quote_char = text[cursor] if cursor < len(text) and text[cursor] in "'\"" else None
    if quote_char:
        cursor += 1
        while cursor < len(text):
            if text[cursor] == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if text[cursor] == quote_char:
                cursor += 1
                break
            cursor += 1
        else:
            return None
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != ")":
            return None
        return cursor + 1, destination

    # Parenthesized or unquoted titles are accepted with balanced parentheses.
    depth = 0
    while cursor < len(text):
        char = text[cursor]
        if char == "\\" and cursor + 1 < len(text):
            cursor += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return cursor + 1, destination
            depth -= 1
        cursor += 1
    return None


def _markdown_matches(text: str) -> list[tuple[int, int, LinkRef]]:
    matches: list[tuple[int, int, LinkRef]] = []
    cursor = 0
    while cursor < len(text):
        if text.startswith("![", cursor):
            start, label_start, embed = cursor, cursor + 2, True
        elif text[cursor] == "[":
            start, label_start, embed = cursor, cursor + 1, False
        else:
            cursor += 1
            continue
        label_end = text.find("]", label_start)
        if label_end < 0 or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            cursor = label_start
            continue
        parsed = _markdown_destination(text, label_end + 2)
        if parsed is None:
            cursor = label_end + 1
            continue
        end, destination = parsed
        if _split_target(destination)[0]:
            matches.append((start, end, _markdown_link("!" if embed else "", text[label_start:label_end], destination)))
        cursor = end
    return matches


def _segment_refs(segment: str, offset: int) -> list[tuple[int, int, LinkRef]]:
    matches: list[tuple[int, int, LinkRef]] = []
    for match in _WIKILINK_RE.finditer(segment):
        raw = match.group(0)
        ref = _embed_wikilink(match.group(1)) if raw.startswith("!") else _wikilink(match.group(1))
        matches.append((offset + match.start(), offset + match.end(), ref))
    for start, end, ref in _markdown_matches(segment):
        absolute = (offset + start, offset + end, ref)
        # A Markdown match nested inside a Wikilink is not a second link.
        if any(not (absolute[1] <= a or absolute[0] >= b) for a, b, _ in matches):
            continue
        matches.append(absolute)
    return matches


def _line_refs(line: str, visible_ranges: Iterable[tuple[int, int]] | None = None) -> list[tuple[int, int, LinkRef]]:
    matches: list[tuple[int, int, LinkRef]] = []
    ranges = [(0, len(line))] if visible_ranges is None else visible_ranges
    for visible_start, visible_end in ranges:
        segment = line[visible_start:visible_end]
        for start, end in _outside_code(segment):
            matches.extend(_segment_refs(segment[start:end], visible_start + start))
    matches.sort(key=lambda item: (item[0], item[1]))
    return matches


def _fence_parts(line: str) -> tuple[str, str] | None:
    match = _FENCE_RE.match(line)
    return (match.group(1), match.group(2)) if match else None


def _comment_ranges(line: str, in_comment: bool) -> tuple[list[tuple[int, int]], bool]:
    """Return visible ranges while ignoring HTML comments across lines."""
    code_ranges = _code_ranges(line)
    visible: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(line):
        if in_comment:
            close = line.find("-->", cursor)
            if close < 0:
                return visible, True
            cursor, in_comment = close + 3, False
            continue
        start = line.find("<!--", cursor)
        while start >= 0:
            code_end = next((end for begin, end in code_ranges if begin <= start < end), None)
            if code_end is None:
                break
            cursor = code_end
            start = line.find("<!--", cursor)
        if start < 0:
            visible.append((cursor, len(line)))
            return visible, False
        visible.append((cursor, start))
        cursor, in_comment = start + 4, True
    return visible, in_comment


def iter_matches(body: str) -> Iterable[tuple[int, int, LinkRef]]:
    """Yield absolute offsets and references, excluding fences, code, and comments."""
    offset = 0
    in_fence = ""
    in_comment = False
    for line in body.splitlines(keepends=True):
        if in_comment:
            visible_ranges, in_comment = _comment_ranges(line, True)
            for start, end, ref in _line_refs(line, visible_ranges):
                yield offset + start, offset + end, ref
            offset += len(line)
            continue
        fence = _fence_parts(line)
        if in_fence:
            if fence and fence[0][0] == in_fence[0] and len(fence[0]) >= len(in_fence) and not fence[1].strip():
                in_fence = ""
            offset += len(line)
            continue
        if fence:
            in_fence = fence[0]
            offset += len(line)
            continue
        visible_ranges, in_comment = _comment_ranges(line, in_comment)
        for start, end, ref in _line_refs(line, visible_ranges):
            yield offset + start, offset + end, ref
        offset += len(line)


def parse(body: str) -> list[LinkRef]:
    """Parse links/embeds outside code, preserving order and duplicates."""
    return [ref for _start, _end, ref in iter_matches(body) if ref.target]


def unique_targets(refs: Iterable[LinkRef]) -> list[str]:
    """Return historical target strings, deduplicated in authored order."""
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref.target and ref.target not in seen:
            seen.add(ref.target)
            result.append(ref.target)
    return result


def serialize(refs: Iterable[LinkRef]) -> list[dict[str, Any]]:
    return [asdict(ref) for ref in refs if ref.target]


def from_entry(entry: dict[str, Any]) -> list[LinkRef]:
    """Read new records, falling back to legacy ``links`` entries."""
    records = entry.get("link_records")
    if isinstance(records, list):
        parsed: list[LinkRef] = []
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("target"), str):
                continue
            parsed.append(LinkRef(
                target=normalize_target(item["target"]),
                label=_nfc(str(item.get("label", item["target"]))),
                fragment=_nfc(str(item.get("fragment", ""))),
                embed=item.get("embed") is True,
                syntax=str(item.get("syntax", "wikilink")),
            ))
        if parsed:
            return parsed
    links = entry.get("links", [])
    if not isinstance(links, list):
        return []
    result: list[LinkRef] = []
    for value in links:
        if not str(value).strip():
            continue
        target, fragment = _split_target(str(value))
        result.append(LinkRef(target=target, label=target, fragment=fragment, embed=False, syntax="wikilink"))
    return result


def _page_candidates(target: str, page_keys: set[str]) -> list[str]:
    target = normalize_target(target)
    if not target or urllib.parse.urlsplit(target).scheme:
        return []
    candidates: set[str] = set()
    variants = {target}
    if target.lower().endswith(".md"):
        variants.add(target[:-3])
    else:
        variants.add(target + ".md")
    if target.startswith("wiki/topics/"):
        variants.add(target[len("wiki/topics/"):])
    for key in page_keys:
        key_nfc = _nfc(key)
        stem = key_nfc[:-3] if key_nfc.lower().endswith(".md") else key_nfc
        basename_stem = stem.rsplit("/", 1)[-1]
        if key_nfc in variants or stem in variants or ("/" not in target and basename_stem in variants):
            candidates.add(key_nfc)
    return sorted(candidates, key=_nfc)


def resolve(target: str, topic_keys: set[str], query_keys: set[str] | None = None,
            alias_index: dict[str, Any] | None = None) -> Resolution:
    """Resolve a target against topics/queries, reporting ambiguity explicitly."""
    target = normalize_target(target)
    scheme = urllib.parse.urlsplit(target).scheme.lower()
    if scheme in {"http", "https", "mailto"}:
        return Resolution("external", target)
    if scheme:
        return Resolution("unsafe", target)
    query_keys = query_keys or set()
    page_keys = set(topic_keys) | set(query_keys)
    candidates = _page_candidates(target, page_keys)
    if alias_index and target in alias_index and isinstance(alias_index[target], str):
        alias_target = _nfc(alias_index[target])
        if alias_target in topic_keys:
            candidates = sorted(set(candidates) | {alias_target}, key=_nfc)
    if len(candidates) > 1:
        return Resolution("ambiguous", target, candidates=tuple(candidates))
    if candidates:
        return Resolution("resolved", target, key=candidates[0])
    return Resolution("missing", target)


def fragment_id(fragment: str) -> str:
    """Best-effort static-site fragment while retaining block identity."""
    fragment = fragment.strip()
    if fragment.startswith("^"):
        return "block-" + re.sub(r"[^A-Za-z0-9_:-]+", "-", fragment[1:]).strip("-").lower()
    return "h-" + re.sub(r"[/\\:*?\"<>|\x00-\x1f\x7f]|\s+", "_", fragment).lower()


def rewrite(body: str, callback: Callable[[LinkRef], str]) -> str:
    """Replace parsed references while leaving code and fenced blocks bytewise intact."""
    replacements = list(iter_matches(body))
    if not replacements:
        return body
    out: list[str] = []
    pos = 0
    for start, end, ref in replacements:
        out.append(body[pos:start])
        out.append(callback(ref))
        pos = end
    out.append(body[pos:])
    return "".join(out)
