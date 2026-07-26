import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_wiki import commands, config, frontmatter, home

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    # Strip API env so subprocess gen-home is deterministically atomic regardless of the dev shell.
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_WIKI_OBSIDIAN_API")}
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True, env=env)


def _read_home(vault: Path) -> str:
    return (config.wiki_root(vault) / "index.md").read_text(encoding="utf-8")


def _write_home(vault: Path, text: str) -> None:
    (config.wiki_root(vault) / "index.md").write_text(text, encoding="utf-8")


def _seed_topics(vault: Path):
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)
    (config.topics_dir(vault) / "B主题.md").write_text(
        frontmatter.dump({"title": "B", "sources": ["a.md", "b.md"]}, "x"), encoding="utf-8")
    (config.topics_dir(vault) / "A主题.md").write_text(
        frontmatter.dump({"title": "A", "sources": ["c.md"]}, "x"), encoding="utf-8")


def _seed_captures(vault: Path):
    config.queries_dir(vault).mkdir(parents=True, exist_ok=True)
    (config.queries_dir(vault) / "b报告.md").write_text(frontmatter.dump({"title": "b"}, "x"), encoding="utf-8")
    (config.queries_dir(vault) / "a报告.md").write_text(frontmatter.dump({"title": "a"}, "x"), encoding="utf-8")
    config.graphs_dir(vault).mkdir(parents=True, exist_ok=True)
    (config.graphs_dir(vault) / "图.canvas").write_text('{"nodes": [], "edges": []}\n', encoding="utf-8")


# --- skeleton on a fresh vault ---------------------------------------------

def test_gen_home_writes_skeleton(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    payload = json.loads(run_cli("gen-home", "--vault", str(tmp_path)).stdout)
    assert payload["ok"] is True
    assert payload["path"] == "wiki/index.md"
    assert payload["write_via"] == "atomic"
    assert payload["cards"] is False  # tmp_path has no .obsidian/Dataview
    text = _read_home(tmp_path)
    assert text.startswith("# Wiki Index")
    assert home.EMBED in text
    for heading in ("## 🧭 动态视图（Bases）", "## 📚 主题导航", "## 🔗 主题关系图谱", "## 🗂 工作区"):
        assert heading in text
    assert home.AUTO_START in text and home.AUTO_END in text
    assert text.endswith("\n")


def test_skeleton_nav_table_lists_topics_with_counts(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _seed_topics(tmp_path)
    run_cli("gen-home", "--vault", str(tmp_path))
    text = _read_home(tmp_path)
    assert "| 主题 | 篇数 | 范围 |" in text
    assert "| [[A主题]] | 1 | _待补充_ |" in text
    assert "| [[B主题]] | 2 | _待补充_ |" in text
    assert text.index("A主题") < text.index("B主题")  # NFC-lexicographic order


def test_gen_home_deterministic(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _seed_topics(tmp_path)
    _seed_captures(tmp_path)
    run_cli("gen-home", "--vault", str(tmp_path))
    first = _read_home(tmp_path)
    run_cli("gen-home", "--vault", str(tmp_path))
    assert _read_home(tmp_path) == first
    assert first.endswith("\n")


# --- cards on/off ----------------------------------------------------------

def test_cards_on_emits_centered_dataviewjs(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    payload = json.loads(run_cli("gen-home", "--cards", "on", "--vault", str(tmp_path)).stdout)
    assert payload["cards"] is True
    text = _read_home(tmp_path)
    assert "```dataviewjs" in text
    assert "aw-card" in text
    assert "justify-content:center" in text  # balanced/centered grid (the fix)


def test_cards_off_emits_static_list(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _seed_captures(tmp_path)
    payload = json.loads(run_cli("gen-home", "--cards", "off", "--vault", str(tmp_path)).stdout)
    assert payload["cards"] is False
    text = _read_home(tmp_path)
    assert "```dataviewjs" not in text
    assert "静态" in text
    assert "[a报告](queries/a报告.md)" in text
    assert "[图](graphs/图.canvas)" in text


# --- merge: preserve agent prose, never clobber ----------------------------

def test_preserves_prose_and_refreshes_managed_block(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    custom = (
        "# Wiki Index\n\n"
        "## 📚 主题导航\n\n我亲手写的分组与范围。\n\n"
        f"{home.AUTO_START}\n\nSTALE\n\n{home.AUTO_END}\n"
    )
    _write_home(tmp_path, custom)
    run_cli("gen-home", "--cards", "on", "--vault", str(tmp_path))
    text = _read_home(tmp_path)
    assert "我亲手写的分组与范围。" in text   # prose preserved
    assert "STALE" not in text               # managed block refreshed
    assert "```dataviewjs" in text
    assert text.index("我亲手写的分组与范围。") < text.index(home.AUTO_START)


def test_appends_block_to_unmarked_curated_index(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    curated = "# Wiki Index\n\n## 📚 主题导航\n\n精排内容，无标记。\n"
    _write_home(tmp_path, curated)
    run_cli("gen-home", "--cards", "on", "--vault", str(tmp_path))
    text = _read_home(tmp_path)
    assert "精排内容，无标记。" in text          # never clobbered
    assert home.AUTO_START in text and home.AUTO_END in text
    assert text.index("精排内容") < text.index(home.AUTO_START)


def test_stray_end_marker_in_prose_does_not_corrupt_refresh(tmp_path):
    # An AUTO_END literal in agent prose BEFORE the real block must not match as
    # the block's end (which would duplicate the block and leave STALE behind).
    run_cli("init", "--vault", str(tmp_path))
    poisoned = (
        "# Wiki Index\n\n"
        f"## 🔗 关系\n\n说明：托管区止于 `{home.AUTO_END}`。\n\n"
        f"{home.AUTO_START}\n\nSTALE\n\n{home.AUTO_END}\n"
    )
    _write_home(tmp_path, poisoned)
    run_cli("gen-home", "--cards", "off", "--vault", str(tmp_path))
    text = _read_home(tmp_path)
    assert text.count(home.AUTO_START) == 1   # exactly one managed block
    assert "STALE" not in text                # real block refreshed
    assert "说明：托管区止于" in text          # prose preserved


# --- index.base / gen-base contract untouched ------------------------------

def test_gen_home_does_not_touch_base(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    (config.topics_dir(tmp_path) / "T.md").write_text(
        frontmatter.dump({"title": "T", "sources": []}, "b"), encoding="utf-8")
    run_cli("gen-base", "--name", "sources", "--vault", str(tmp_path))
    index_base = config.wiki_root(tmp_path) / "index.base"
    before = index_base.read_bytes()
    files_before = sorted(p.name for p in tmp_path.rglob("*.base"))
    run_cli("gen-home", "--vault", str(tmp_path))
    assert index_base.read_bytes() == before
    assert sorted(p.name for p in tmp_path.rglob("*.base")) == files_before
    assert len(files_before) == 2


def test_gen_home_requires_init(tmp_path):
    result = run_cli("gen-home", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "wiki_not_initialized", "hint": "run init first"}


def test_atomic_write_text_cleans_tmp_and_preserves_old_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "index.md"
    path.write_text("OLD", encoding="utf-8")

    def boom(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        commands._atomic_write_text(path, "NEW")
    assert path.read_text(encoding="utf-8") == "OLD"
    assert not path.with_name(path.name + ".tmp").exists()
