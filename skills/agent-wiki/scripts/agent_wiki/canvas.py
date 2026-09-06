"""Deterministic JSON Canvas 1.0 knowledge-graph generation.

Builds a per-topic subgraph from the retrieval index: the topic at visual
center, its ``sources[]`` on an inner ring, and 1-hop neighbour topics on an
outer ring. Layout is closed-form (no randomness, no iteration) with ring radii
that scale with member count so same-ring boxes never overlap. The canvas is a
derived, regenerable artifact written only under ``wiki/graphs/``; topic
frontmatter remains the single source of truth.

Verified against the official JSON Canvas 1.0 spec (obsidianmd/jsoncanvas):
nodes require ``id``/``type``/``x``/``y``/``width``/``height`` with positive-int
sizes and integer coords; ``text`` nodes add ``text``, ``file`` nodes add
``file``, ``link`` nodes add
``url``; edges require ``id``/``fromNode``/``toNode`` (``toEnd`` optional);
``color`` is a preset ``"1"``–``"6"`` or hex.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

from . import links

# Node box geometry (positive-int width/height, integer coords).
CENTER_WIDTH = 480
CENTER_HEIGHT = 260
RING_WIDTH = 420
RING_HEIGHT = 190
GAP = 120
_CENTER_DIAG = math.ceil(math.hypot(CENTER_WIDTH, CENTER_HEIGHT))
_RING_DIAG = math.ceil(math.hypot(RING_WIDTH, RING_HEIGHT))
R1_BASE = 520
R2_BASE = 1100

# Hex colors for light/dark theme compatibility.
TOPIC_COLOR = "#2563EB"
SOURCE_COLOR = "#D97706"
NEIGHBOR_COLOR = "#0D9488"


class CanvasWriteError(OSError):
    pass


def _join(*parts: str) -> str:
    return "/".join(part for part in parts if part)


def _stem(name: str) -> str:
    base = PurePosixPath(name).name
    return base[:-3] if base.lower().endswith(".md") else base


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _text_node(node_id: str, x: int, y: int, width: int, height: int, text: str, color: str) -> dict[str, Any]:
    return {"id": node_id, "type": "text", "x": x, "y": y,
            "width": width, "height": height, "text": text, "color": color}


def _link_node(node_id: str, x: int, y: int, url: str, color: str) -> dict[str, Any]:
    return {"id": node_id, "type": "link", "x": x, "y": y,
            "width": RING_WIDTH, "height": RING_HEIGHT, "url": url, "color": color}


def _edge(edge_id: str, from_node: str, to_node: str, color: str, label: str = "") -> dict[str, Any]:
    edge = {"id": edge_id, "fromNode": from_node, "toNode": to_node, "toEnd": "arrow", "color": color}
    if label:
        edge["label"] = label
    return edge


def _wikilink_target(vault_path: str) -> str:
    """Strip .md extension from vault path for wikilink target."""
    return vault_path[:-3] if vault_path.lower().endswith(".md") else vault_path


def _center_card(title: str, summary: str, wikilink: str) -> str:
    """Markdown for center topic card: heading + link + optional summary."""
    parts = [f"# {title}", f"[[{wikilink}|阅读全文 →]]"]
    if summary:
        parts.append(summary)
    return "\n\n".join(parts)


def _neighbor_card(title: str, summary: str, wikilink: str) -> str:
    """Markdown for neighbor topic card: subheading + link + optional summary."""
    parts = [f"## {title}", f"[[{wikilink}|查看主题 →]]"]
    if summary:
        parts.append(summary)
    return "\n\n".join(parts)


def _source_card(stem: str, wikilink: str) -> str:
    """Markdown for file source card: bold stem + link."""
    return f"**{stem}**\n\n[[{wikilink}|打开来源 →]]"


def _ring_radius(n: int, base: int, diag: int) -> int:
    """Radius placing ``n`` boxes (with bounding diagonal ``diag``) on a ring so
    adjacent centers are >= ``diag + GAP`` apart. ``n<=1`` collapses to base."""
    if n <= 1:
        return base
    return max(base, math.ceil((diag + GAP) / (2 * math.sin(math.pi / n))))


def _position(radius: int, k: int, n: int, width: int, height: int) -> tuple[int, int]:
    """Top-left corner of member ``k`` of ``n`` on ``radius`` (box dims ``width``×``height``,
    centered on ring point at ``theta = 2*pi*k/n``); ``n<=1`` uses ``theta=0``."""
    theta = 0.0 if n <= 1 else 2 * math.pi * k / n
    x = round(radius * math.cos(theta) - width / 2)
    y = round(radius * math.sin(theta) - height / 2)
    return x, y


def neighbors(target_key: str, index_data: dict[str, Any]) -> set[str]:
    """Topic keys sharing sources or resolved links with ``target_key``."""
    topics = index_data.get("topics", {})
    queries = index_data.get("queries", {})
    target = topics[target_key]
    topic_keys = set(topics)
    query_keys = set(queries)
    alias_index = index_data.get("alias_index", {})
    target_sources = set(target.get("sources", []))
    linked_topics: set[str] = set()
    for ref in links.from_entry(target):
        resolution = links.resolve(ref.target, topic_keys, query_keys, alias_index)
        if resolution.status == "resolved" and resolution.key is not None and resolution.key in topic_keys:
            linked_topics.add(resolution.key)

    result: set[str] = linked_topics - {target_key}
    for key, entry in topics.items():
        if key == target_key:
            continue
        if target_sources & set(entry.get("sources", [])):
            result.add(key)
            continue
        for ref in links.from_entry(entry):
            resolution = links.resolve(ref.target, topic_keys, query_keys, alias_index)
            if resolution.status == "resolved" and resolution.key == target_key:
                result.add(key)
                break
    return result


def build_canvas(target_key: str, index_data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """JSON Canvas dict for ``target_key`` from the rebuilt index. ``prefix`` is
    the obsidian-vault-relative folder of the agent-wiki vault (``bases.obsidian_prefix``)."""
    target = index_data["topics"][target_key]
    topic_id = f"topic:{target_key}"
    topic_path = _join(prefix, "wiki", "topics", target_key)
    topic_wikilink = _wikilink_target(topic_path)
    center_text = _center_card(target["title"], target["summary"], topic_wikilink)
    nodes: list[dict[str, Any]] = [
        _text_node(topic_id, round(-CENTER_WIDTH / 2), round(-CENTER_HEIGHT / 2),
                   CENTER_WIDTH, CENTER_HEIGHT, center_text, TOPIC_COLOR)
    ]
    edges: list[dict[str, Any]] = []

    sources = sorted(set(target["sources"]))
    r1 = _ring_radius(len(sources), R1_BASE, _RING_DIAG)
    for k, src in enumerate(sources):
        x, y = _position(r1, k, len(sources), RING_WIDTH, RING_HEIGHT)
        sid = f"source:{src}"
        if _is_url(src):
            nodes.append(_link_node(sid, x, y, src, SOURCE_COLOR))
        else:
            src_path = _join(prefix, src)
            src_wikilink = _wikilink_target(src_path)
            src_text = _source_card(_stem(src), src_wikilink)
            nodes.append(_text_node(sid, x, y, RING_WIDTH, RING_HEIGHT, src_text, SOURCE_COLOR))
        edges.append(_edge(f"edge:{topic_id}=>{sid}", topic_id, sid, SOURCE_COLOR, "来源"))

    nbrs = sorted(neighbors(target_key, index_data))
    r2 = max(_ring_radius(len(nbrs), R2_BASE, _RING_DIAG), r1 + _CENTER_DIAG + GAP)
    for k, nb in enumerate(nbrs):
        x, y = _position(r2, k, len(nbrs), RING_WIDTH, RING_HEIGHT)
        nid = f"neighbor:{nb}"
        nb_entry = index_data["topics"][nb]
        nb_path = _join(prefix, "wiki", "topics", nb)
        nb_wikilink = _wikilink_target(nb_path)
        nb_text = _neighbor_card(nb_entry["title"], nb_entry["summary"], nb_wikilink)
        nodes.append(_text_node(nid, x, y, RING_WIDTH, RING_HEIGHT, nb_text, NEIGHBOR_COLOR))
        edges.append(_edge(f"edge:{topic_id}=>{nid}", topic_id, nid, NEIGHBOR_COLOR, "相关"))

    return {"nodes": nodes, "edges": edges}


def serialize(canvas: dict[str, Any]) -> str:
    return json.dumps(canvas, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_canvas(path: Path, canvas: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(serialize(canvas), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise CanvasWriteError(str(exc)) from exc
