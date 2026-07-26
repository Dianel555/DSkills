import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agent_wiki import frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"
FIXTURE = ROOT / "tests" / "fixtures" / "sample_vault"


def run_cli(vault, *args):
    env = os.environ.copy()
    env["AGENT_WIKI_VAULT"] = str(vault)
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True, env=env)


def copy_fixture(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE, vault)
    return vault


def test_end_to_end_ingest_modify_delete_cleanup(tmp_path):
    vault = copy_fixture(tmp_path)

    init = run_cli(vault, "init")
    assert init.returncode == 0, init.stderr

    scan = json.loads(run_cli(vault, "scan").stdout)
    assert sorted(item["path"] for item in scan["new"]) == ["课程/双缝实验.md", "课程/量子力学.md"]
    assert not any("attachments" in item["path"] for item in scan["new"])

    topic = vault / "wiki" / "topics" / "量子叠加.md"
    topic.write_text(
        frontmatter.dump(
            {"title": "量子叠加", "sources": ["课程/量子力学.md"], "last_updated": "2026-06-04T00:00:00"},
            "> [!summary]\n> 量子叠加说明。\n\n保留 [[双缝实验]] 与 ![[image.png]]。\n",
        ),
        encoding="utf-8",
    )
    put = run_cli(vault, "cache-put", "课程/量子力学.md", "--topics", "量子叠加.md")
    assert put.returncode == 0, put.stderr

    (vault / "课程" / "量子力学.md").write_text("# 量子力学\n\n补充内容。\n", encoding="utf-8")
    modified = json.loads(run_cli(vault, "scan").stdout)
    assert [item["path"] for item in modified["modified"]] == ["课程/量子力学.md"]
    assert modified["modified"][0]["derived_topics"] == ["量子叠加.md"]

    (vault / "课程" / "量子力学.md").unlink()
    cleanup = json.loads(run_cli(vault, "cleanup").stdout)
    assert cleanup["removed"] == 1
    assert cleanup["archived"] == 1
    assert not topic.exists()
    assert list((vault / "wiki" / "_archived").glob("*/量子叠加.md"))


def test_cli_json_is_main_loop_consumable_with_env_vault(tmp_path):
    vault = copy_fixture(tmp_path)
    run_cli(vault, "init")

    result = run_cli(vault, "scan")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["version"] == 1
    assert payload["vault"] == str(vault.resolve())
    assert isinstance(payload["new"], list)
