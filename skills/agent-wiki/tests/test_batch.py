import json
import os
import subprocess
import sys
from pathlib import Path

from agent_wiki import config

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(vault, *args):
    env = os.environ.copy()
    env["AGENT_WIKI_VAULT"] = str(vault)
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True, env=env)


def _vault_with_sources(tmp_path, count=5):
    for name in "abcde"[:count]:
        (tmp_path / f"{name}.md").write_text(name, encoding="utf-8")
    assert run_cli(tmp_path, "init").returncode == 0


def test_plan_splits_into_batches_and_writes_report(tmp_path):
    _vault_with_sources(tmp_path)
    payload = json.loads(run_cli(tmp_path, "plan", "--batch-size", "2").stdout)

    assert payload["ok"] is True
    assert payload["total"] == 5
    assert payload["batch_size"] == 2
    assert [b["count"] for b in payload["batches"]] == [2, 2, 1]
    assert payload["batches"][0]["items"] == ["a.md", "b.md"]

    report = config.archive_dir(tmp_path) / "ingest-tasks.md"
    assert report.exists()
    assert "Batch 1" in report.read_text(encoding="utf-8")
    assert config.batch_path(tmp_path).exists()


def test_plan_requires_init(tmp_path):
    result = run_cli(tmp_path, "plan")
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "wiki_not_initialized"


def test_batch_done_gates_on_completion(tmp_path):
    _vault_with_sources(tmp_path)
    run_cli(tmp_path, "plan", "--batch-size", "2")

    incomplete = run_cli(tmp_path, "batch-done", "--batch", "1")
    assert incomplete.returncode == 1
    err = json.loads(incomplete.stderr)
    assert err["error"] == "batch_incomplete"
    assert err["missing"] == ["a.md", "b.md"]

    run_cli(tmp_path, "cache-put", "a.md", "--topics", "A.md")
    run_cli(tmp_path, "cache-put", "b.md", "--topics", "B.md")

    done = json.loads(run_cli(tmp_path, "batch-done", "--batch", "1").stdout)
    assert done["ok"] is True
    assert done["remaining"] == [2, 3]
    assert done["complete"] is False

    report = (config.archive_dir(tmp_path) / "ingest-tasks.md").read_text(encoding="utf-8")
    assert "## Batch 1 (2) [x] done" in report


def test_batch_done_unknown_batch(tmp_path):
    _vault_with_sources(tmp_path)
    run_cli(tmp_path, "plan", "--batch-size", "2")
    result = run_cli(tmp_path, "batch-done", "--batch", "9")
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"] == "batch_not_found"


def test_status_reports_batch_progress(tmp_path):
    _vault_with_sources(tmp_path)
    run_cli(tmp_path, "plan", "--batch-size", "2")
    run_cli(tmp_path, "cache-put", "a.md", "--topics", "A.md")
    run_cli(tmp_path, "cache-put", "b.md", "--topics", "B.md")
    run_cli(tmp_path, "batch-done", "--batch", "1")

    status = json.loads(run_cli(tmp_path, "status").stdout)
    assert status["batch"]["batches_total"] == 3
    assert status["batch"]["batches_done"] == 1
    assert status["batch"]["batches_pending"] == 2
    assert status["topics_archived"] == 0
