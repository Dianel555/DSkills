import json
import math
import os
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest
from agent_wiki import canvas, config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def _entry(sources=None, links=None, title="", summary=""):
    return {"sources": sources or [], "links": links or [], "title": title, "summary": summary}


def _index(topics):
    return {"version": 1, "topics": topics, "queries": {}}


def _topic(vault, name, meta, body="x"):
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)
    (config.topics_dir(vault) / name).write_text(frontmatter.dump(meta, body), encoding="utf-8")


# --- schema validity -------------------------------------------------------

def test_canvas_schema_validity_and_edge_closure():
    data = _index({"T.md": _entry(["a.md", "https://x.io"], ["N"], "T", "Summary"), "N.md": _entry(title="N")})
    graph = canvas.build_canvas("T.md", data)
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids))  # unique ids
    for node in graph["nodes"]:
        assert {"id", "type", "x", "y", "width", "height"} <= node.keys()
        assert isinstance(node["x"], int) and isinstance(node["y"], int)
        assert isinstance(node["width"], int) and node["width"] > 0
        assert isinstance(node["height"], int) and node["height"] > 0
        assert (node["type"] == "text") == ("text" in node)
        assert (node["type"] == "link") == ("url" in node)
    node_ids = set(ids)
    for edge in graph["edges"]:
        assert {"id", "fromNode", "toNode"} <= edge.keys()
        assert edge["fromNode"] in node_ids and edge["toNode"] in node_ids
        assert edge["toEnd"] == "arrow"


def test_url_source_is_link_file_source_is_text_node():
    data = _index({"T.md": _entry(["notes/a.md", "https://example.com/p"], title="Topic")})
    graph = canvas.build_canvas("T.md", data, prefix="vault")
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["source:notes/a.md"]["type"] == "text"
    assert "[[vault/notes/a" in by_id["source:notes/a.md"]["text"]
    assert by_id["source:https://example.com/p"]["type"] == "link"
    assert by_id["source:https://example.com/p"]["url"] == "https://example.com/p"
    assert by_id["topic:T.md"]["type"] == "text"
    assert "# Topic" in by_id["topic:T.md"]["text"]


def test_color_mapping():
    data = _index({"T.md": _entry(["a.md"], ["N"], "T"), "N.md": _entry(title="N")})
    by_id = {n["id"]: n for n in canvas.build_canvas("T.md", data)["nodes"]}
    assert by_id["topic:T.md"]["color"] == "#2563EB"
    assert by_id["source:a.md"]["color"] == "#D97706"
    assert by_id["neighbor:N.md"]["color"] == "#0D9488"


# --- coordinates -----------------------------------------------------------

def test_target_centered_top_left():
    data = _index({"T.md": _entry(title="T")})
    topic = canvas.build_canvas("T.md", data)["nodes"][0]
    assert (topic["x"], topic["y"]) == (-240, -130)


def test_single_source_on_inner_ring_theta_zero():
    data = _index({"T.md": _entry(["a.md"], title="T")})
    src = next(n for n in canvas.build_canvas("T.md", data)["nodes"] if n["id"] == "source:a.md")
    assert (src["x"], src["y"]) == (canvas.R1_BASE - 210, -95)


def test_scaled_radius_non_overlap():
    sources = [f"s{i}.md" for i in range(8)]
    graph = canvas.build_canvas("T.md", _index({"T.md": _entry(sources, title="T")}))
    centers = [(n["x"] + canvas.RING_WIDTH / 2, n["y"] + canvas.RING_HEIGHT / 2)
               for n in graph["nodes"] if n["id"].startswith("source:")]
    for (ax, ay), (bx, by) in combinations(centers, 2):
        assert math.hypot(ax - bx, ay - by) >= canvas._RING_DIAG


# --- neighbor derivation ---------------------------------------------------

def test_neighbor_by_shared_source():
    data = _index({"T.md": _entry(["s1.md"]), "N.md": _entry(["s1.md", "s2.md"]), "X.md": _entry(["s3.md"])})
    assert canvas.neighbors("T.md", data) == {"N.md"}


def test_neighbor_by_outbound_and_inbound_links():
    data = _index({"T.md": _entry(links=["A"]), "A.md": _entry(), "B.md": _entry(links=["T"]), "C.md": _entry()})
    assert canvas.neighbors("T.md", data) == {"A.md", "B.md"}


def test_neighbor_dangling_link_excluded():
    data = _index({"T.md": _entry(links=["Ghost"]), "N.md": _entry()})
    assert canvas.neighbors("T.md", data) == set()


def test_source_stem_equal_topic_stem_keeps_ids_unique():
    data = _index({"T.md": _entry(["N.md"], title="T"), "N.md": _entry(["N.md"], title="N")})
    graph = canvas.build_canvas("T.md", data)
    ids = [n["id"] for n in graph["nodes"]]
    assert "source:N.md" in ids and "neighbor:N.md" in ids
    assert len(ids) == len(set(ids))


def test_topic_links_remain_visible_before_long_summary():
    long_summary = "x " * 600
    data = _index({"T.md": _entry(["a.md"], ["N"], "T", long_summary), "N.md": _entry(title="N", summary=long_summary)})
    by_id = {n["id"]: n for n in canvas.build_canvas("T.md", data)["nodes"]}
    assert by_id["topic:T.md"]["text"].split("\n\n", 2)[:2] == ["# T", "[[wiki/topics/T|阅读全文 →]]"]
    assert by_id["neighbor:N.md"]["text"].split("\n\n", 2)[:2] == ["## N", "[[wiki/topics/N|查看主题 →]]"]


# --- determinism -----------------------------------------------------------

def test_canvas_byte_identical():
    data = _index({"T.md": _entry(["b.md", "a.md", "a.md"], ["N"], "T", "Sum"), "N.md": _entry(title="N")})
    first = canvas.serialize(canvas.build_canvas("T.md", data))
    second = canvas.serialize(canvas.build_canvas("T.md", data))
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["nodes"]  # valid JSON


# --- atomic write ----------------------------------------------------------

def test_write_canvas_atomic_no_tmp(tmp_path):
    path = tmp_path / "g" / "T.canvas"
    canvas.write_canvas(path, {"nodes": [], "edges": []})
    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


def test_write_canvas_preserves_old_bytes_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "T.canvas"
    path.write_text("OLD", encoding="utf-8")

    def boom(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(canvas.CanvasWriteError):
        canvas.write_canvas(path, {"nodes": [], "edges": []})
    assert path.read_text(encoding="utf-8") == "OLD"
    assert not path.with_name(path.name + ".tmp").exists()


# --- CLI -------------------------------------------------------------------

def test_gen_canvas_topic_writes_file(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md", {"title": "T", "sources": ["a.md"]}, body="见 [[N]]\n")
    _topic(tmp_path, "N.md", {"title": "N", "sources": []})
    payload = json.loads(run_cli("gen-canvas", "--topic", "T", "--vault", str(tmp_path)).stdout)
    assert payload["path"] == "wiki/graphs/T.canvas"
    assert payload["nodes"] == 3 and payload["edges"] == 2
    written = json.loads((config.graphs_dir(tmp_path) / "T.canvas").read_text(encoding="utf-8"))
    assert {n["id"] for n in written["nodes"]} == {"topic:T.md", "source:a.md", "neighbor:N.md"}


def test_gen_canvas_all_writes_one_per_topic(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _topic(tmp_path, "T.md", {"title": "T", "sources": []})
    _topic(tmp_path, "N.md", {"title": "N", "sources": []})
    payload = json.loads(run_cli("gen-canvas", "--all", "--vault", str(tmp_path)).stdout)
    assert payload["count"] == 2
    assert (config.graphs_dir(tmp_path) / "T.canvas").exists()
    assert (config.graphs_dir(tmp_path) / "N.canvas").exists()


def test_gen_canvas_requires_init(tmp_path):
    result = run_cli("gen-canvas", "--topic", "T", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "wiki_not_initialized", "hint": "run init first"}


def test_gen_canvas_unknown_topic_errors(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    result = run_cli("gen-canvas", "--topic", "ghost", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "topic_not_found", "topic": "ghost.md"}
