"""Deterministic JSON Canvas 1.0 knowledge-graph generation.

Builds a per-topic subgraph from the retrieval index: the topic at visual
center, its ``sources[]`` on an inner ring, and 1-hop neighbour topics on an
outer ring. Layout is closed-form (no randomness, no iteration) with ring radii
that scale with member count so same-ring boxes never overlap. The canvas is a
derived, regenerable artifact written only under ``wiki/graphs/``; topic
frontmatter remains the single source of truth.

Verified against the official JSON Canvas 1.0 spec (obsidianmd/jsoncanvas):
nodes require ``id``/``type``/``x``/``y``/``width``/``height`` with positive-int
sizes and integer coords; ``file`` nodes add ``file``, ``link`` nodes add
``url``; edges require ``id``/``fromNode``/``toNode`` (``toEnd`` optional);
``color`` is a preset ``"1"``–``"6"`` or hex.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path, PurePosixPath

# Node box geometry (positive-int width/height, integer coords).
WIDTH = 400
HEIGHT = 100
GAP = 80
_DIAG = math.ceil(math.hypot(WIDTH, HEIGHT))  # bounding-box diagonal
R1_BASE = 420
R2_BASE = 900

# Fixed JSON Canvas preset colors by node type.
TOPIC_COLOR = "4"
SOURCE_COLOR = "6"
NEIGHBOR_COLOR = "5"


class CanvasWriteError(OSError):
    pass


def _join(*parts: str) -> str:
    return "/".join(part for part in parts if part)


def _stem(name: str) -> str:
    base = PurePosixPath(name).name
    return base[:-3] if base.lower().endswith(".md") else base


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _file_node(node_id: str, x: int, y: int, file: str, color: str) -> dict:
    return {"id": node_id, "type": "file", "x": x, "y": y,
            "width": WIDTH, "height": HEIGHT, "file": file, "color": color}


def _link_node(node_id: str, x: int, y: int, url: str, color: str) -> dict:
    return {"id": node_id, "type": "link", "x": x, "y": y,
            "width": WIDTH, "height": HEIGHT, "url": url, "color": color}


def _edge(edge_id: str, from_node: str, to_node: str, color: str) -> dict:
    return {"id": edge_id, "fromNode": from_node, "toNode": to_node, "toEnd": "arrow", "color": color}


def _ring_radius(n: int, base: int) -> int:
    """Radius placing ``n`` boxes on a ring so adjacent centers are >= ``_DIAG +
    GAP`` apart. ``n<=1`` collapses to the base radius (no spacing constraint)."""
    if n <= 1:
        return base
    return max(base, math.ceil((_DIAG + GAP) / (2 * math.sin(math.pi / n))))


def _position(radius: int, k: int, n: int) -> tuple[int, int]:
    """Top-left corner of member ``k`` of ``n`` on ``radius`` (member centered on
    the ring point at ``theta = 2*pi*k/n``); ``n<=1`` uses ``theta=0``."""
    theta = 0.0 if n <= 1 else 2 * math.pi * k / n
    x = round(radius * math.cos(theta) - WIDTH / 2)
    y = round(radius * math.sin(theta) - HEIGHT / 2)
    return x, y


def neighbors(target_key: str, index_data: dict) -> set[str]:
    """Topic keys (excluding the target) sharing >=1 source with the target, or
    connected to it by a body wikilink in either direction (resolved by stem)."""
    topics = index_data.get("topics", {})
    target = topics[target_key]
    target_stem = _stem(target_key)
    target_sources = set(target["sources"])
    target_link_stems = {_stem(link) for link in target["links"]}
    result: set[str] = set()
    for key, entry in topics.items():
        if key == target_key:
            continue
        if (target_sources & set(entry["sources"])
                or _stem(key) in target_link_stems
                or target_stem in {_stem(link) for link in entry["links"]}):
            result.add(key)
    return result


def build_canvas(target_key: str, index_data: dict, prefix: str = "") -> dict:
    """JSON Canvas dict for ``target_key`` from the rebuilt index. ``prefix`` is
    the obsidian-vault-relative folder of the agent-wiki vault (``bases.obsidian_prefix``)."""
    target = index_data["topics"][target_key]
    topic_id = f"topic:{target_key}"
    nodes: list[dict] = [
        _file_node(topic_id, round(-WIDTH / 2), round(-HEIGHT / 2),
                   _join(prefix, "wiki", "topics", target_key), TOPIC_COLOR)
    ]
    edges: list[dict] = []

    sources = sorted(set(target["sources"]))
    r1 = _ring_radius(len(sources), R1_BASE)
    for k, src in enumerate(sources):
        x, y = _position(r1, k, len(sources))
        sid = f"source:{src}"
        if _is_url(src):
            nodes.append(_link_node(sid, x, y, src, SOURCE_COLOR))
        else:
            nodes.append(_file_node(sid, x, y, _join(prefix, src), SOURCE_COLOR))
        edges.append(_edge(f"edge:{topic_id}=>{sid}", topic_id, sid, SOURCE_COLOR))

    nbrs = sorted(neighbors(target_key, index_data))
    r2 = max(_ring_radius(len(nbrs), R2_BASE), r1 + _DIAG + GAP)
    for k, nb in enumerate(nbrs):
        x, y = _position(r2, k, len(nbrs))
        nid = f"neighbor:{nb}"
        nodes.append(_file_node(nid, x, y, _join(prefix, "wiki", "topics", nb), NEIGHBOR_COLOR))
        edges.append(_edge(f"edge:{topic_id}=>{nid}", topic_id, nid, NEIGHBOR_COLOR))

    return {"nodes": nodes, "edges": edges}


def serialize(canvas: dict) -> str:
    return json.dumps(canvas, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_canvas(path: Path, canvas: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(serialize(canvas), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise CanvasWriteError(str(exc)) from exc
