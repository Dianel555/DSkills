import os
import subprocess
import sys
from pathlib import Path

import pytest
from agent_wiki import cache, scanner

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_scan_reports_symlinked_markdown_as_skipped(tmp_path):
    target = tmp_path / "real.md"
    target.write_text("real", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    result = scanner.classify(tmp_path, cache.empty_schema())
    report = scanner.format_report(result, tmp_path)

    assert [item["path"] for item in report["new"]] == ["real.md"]
    assert report["stats"]["skipped_symlinks"] == 1
    assert report["errors"] == [{"path": "link.md", "error": "skipped_symlink"}]


def test_scan_reports_normalized_path_collision_without_classifying(tmp_path):
    first = tmp_path / "café.md"
    second = tmp_path / "café.md"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    def fake_collect(root):
        return [first, second], []

    result = scanner.classify(tmp_path, cache.empty_schema(), collect=fake_collect)

    assert result["fatal"] == {"error": "normalized_path_collision", "path": "café.md"}
    assert result["new"] == []


def test_cli_scan_exits_nonzero_on_normalized_path_collision(tmp_path):
    first = tmp_path / "café.md"
    second = tmp_path / "café.md"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    def fake_collect(root):
        return [first, second], []

    result = scanner.classify(tmp_path, cache.empty_schema(), collect=fake_collect)
    report = scanner.format_report(result, tmp_path)

    assert report["error"] == "normalized_path_collision"
