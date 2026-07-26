import json
import os
import subprocess
import sys
from pathlib import Path

from agent_wiki import authors, config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(vault, *args):
    env = os.environ.copy()
    env["AGENT_WIKI_VAULT"] = str(vault)
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True, env=env)


def _build_vault(tmp_path):
    (tmp_path / "量子力学.md").write_text("# 量子力学\n\n| **作者:** 张三; 李四 | 期刊: Nature |\n", encoding="utf-8")
    (tmp_path / "相对论.md").write_text("# 相对论\n\n| 作者：王五 et al. | DOI: 10.1 |\n", encoding="utf-8")
    (tmp_path / "量子场论.md").write_text("# 量子场论\n\n| 作者: 张三 | 标签: physics |\n", encoding="utf-8")
    topics = config.topics_dir(tmp_path)
    topics.mkdir(parents=True, exist_ok=True)
    (topics / "T.md").write_text(
        frontmatter.dump({"title": "T", "sources": ["量子力学.md", "相对论.md", "量子场论.md"]}, "x"),
        encoding="utf-8",
    )


def test_extract_pulls_author_row(tmp_path):
    _build_vault(tmp_path)
    extracted = authors.extract(tmp_path)
    rows = extracted["T.md"]
    assert [r["file"] for r in rows] == ["量子力学.md", "相对论.md", "量子场论.md"]
    assert rows[0]["authors"].endswith("张三; 李四")
    assert "期刊" not in rows[0]["authors"]


def test_aggregate_dedupes_first_author(tmp_path):
    _build_vault(tmp_path)
    aggregated = authors.aggregate(authors.extract(tmp_path))
    assert aggregated["T.md"] == ["张三", "王五"]


def test_cli_extract_and_aggregate(tmp_path):
    _build_vault(tmp_path)
    extract = json.loads(run_cli(tmp_path, "extract-authors").stdout)
    assert extract["ok"] is True
    assert "T.md" in extract["topics"]

    aggregate = json.loads(run_cli(tmp_path, "aggregate-authors").stdout)
    assert aggregate["ok"] is True
    assert aggregate["authors"]["T.md"] == ["张三", "王五"]


def test_cli_requires_init(tmp_path):
    result = run_cli(tmp_path, "extract-authors")
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "wiki_not_initialized"
