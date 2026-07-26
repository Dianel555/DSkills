import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from agent_wiki import bases

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


def test_obsidian_prefix_detects_vault_root(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    sub = tmp_path / "文献阅读记录"
    sub.mkdir()
    assert bases.obsidian_prefix(sub) == "文献阅读记录"
    assert bases.obsidian_prefix(tmp_path) == ""


def test_obsidian_prefix_absent_returns_empty(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    assert bases.obsidian_prefix(notes) == ""


def test_index_base_is_valid_yaml_and_scoped():
    data = yaml.safe_load(bases.build_index_base("文献阅读记录"))
    assert data["filters"]["and"][0] == 'file.inFolder("文献阅读记录/wiki/topics")'
    assert data["formulas"]["source_count"]
    names = [v["name"] for v in data["views"]]
    assert names == ["主题总览", "精选", "按作者", "按机构", "按方法", "按来源类型", "按年份", "卡片视图"]


def test_index_base_per_dimension_views_surface_frontmatter_columns():
    data = yaml.safe_load(bases.build_index_base(""))
    for key in ("authors", "institutions", "methods", "source_type"):
        assert key in data["properties"]
    views = {v["name"]: v for v in data["views"]}
    assert views["按作者"]["order"][0] == "authors"
    assert views["按机构"]["order"][0] == "institutions"
    assert views["按方法"]["order"][0] == "methods"
    assert views["按来源类型"]["order"][0] == "source_type"
    assert views["按年份"]["order"][:2] == ["year_start", "year_end"]
    for key in ("year_start", "year_end"):
        assert key in data["properties"]
    # Only the existing source_count formula — no complex plugin-version-sensitive formulas.
    assert set(data["formulas"]) == {"source_count"}


def test_master_base_excludes_wiki_and_keeps_tags():
    data = yaml.safe_load(bases.build_master_base("文献阅读记录"))
    and_clause = data["filters"]["and"]
    assert 'file.inFolder("文献阅读记录")' in and_clause
    assert {"not": ['file.inFolder("文献阅读记录/wiki")']} in and_clause
    assert data["properties"]["tags"]["displayName"] == "标签"
    assert data["formulas"]["year"]


def test_master_base_root_vault_omits_include():
    data = yaml.safe_load(bases.build_master_base(""))
    and_clause = data["filters"]["and"]
    assert and_clause[0] == 'file.ext == "md"'
    assert {"not": ['file.inFolder("wiki")']} in and_clause


def test_gen_base_cli_writes_both_files(tmp_path):
    assert run_cli("init", "--vault", str(tmp_path)).returncode == 0
    result = run_cli("gen-base", "--name", "Notions", "--vault", str(tmp_path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert set(payload["written"]) == {"wiki/index.base", "Notions.base"}
    yaml.safe_load((tmp_path / "wiki" / "index.base").read_text(encoding="utf-8"))
    yaml.safe_load((tmp_path / "Notions.base").read_text(encoding="utf-8"))


def test_gen_base_default_name_and_path_traversal_guard(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    payload = json.loads(run_cli("gen-base", "--name", "../evil", "--vault", str(tmp_path)).stdout)
    assert "evil.base" in payload["written"]
    assert (tmp_path / "evil.base").exists()
    assert not (tmp_path.parent / "evil.base").exists()


def test_gen_base_requires_init(tmp_path):
    result = run_cli("gen-base", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "wiki_not_initialized"
