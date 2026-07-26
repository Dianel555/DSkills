import hashlib
import json
import subprocess
import sys
from pathlib import Path

from agent_wiki import config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True, encoding="utf-8", capture_output=True,
    )


def _page(directory: Path, name: str, meta: dict, body: str = "正文 [[别处]]\n") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _log_lines(vault: Path) -> list[str]:
    log = config.wiki_root(vault) / "log.md"
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]


# --- init creates / backfills capture & graph dirs -------------------------

def test_init_creates_capture_and_graph_dirs(tmp_path):
    payload = json.loads(run_cli("init", "--vault", str(tmp_path)).stdout)
    for sub in ("queries", "graphs"):
        assert (config.wiki_root(tmp_path) / sub).is_dir()
        assert f"wiki/{sub}" in payload["created"]


def test_init_backfills_missing_capture_dirs(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    import shutil
    shutil.rmtree(config.queries_dir(tmp_path))
    shutil.rmtree(config.graphs_dir(tmp_path))
    payload = json.loads(run_cli("init", "--vault", str(tmp_path)).stdout)
    assert payload["status"] == "already_initialized"
    assert set(payload["created"]) == {"wiki/queries", "wiki/graphs"}
    assert config.queries_dir(tmp_path).is_dir()
    assert config.graphs_dir(tmp_path).is_dir()


# --- save-report placement + kind ------------------------------------------

def test_save_report_registers_and_sets_kind(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _page(config.queries_dir(tmp_path), "报告.md", {"title": "报告", "sources": ["a.pdf"]})
    payload = json.loads(run_cli("save-report", "报告", "--vault", str(tmp_path)).stdout)
    assert payload == {"ok": True, "path": "queries/报告.md", "kind": "query"}
    meta, _ = frontmatter.parse((config.queries_dir(tmp_path) / "报告.md").read_text(encoding="utf-8"))
    assert meta["kind"] == "query"
    log = _log_lines(tmp_path)
    assert log[-1].endswith("capture | save_report | queries/报告.md")


def test_save_report_appends_md_suffix_and_sanitizes_name(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _page(config.queries_dir(tmp_path), "plain.md", {"title": "p", "sources": []})
    # malicious traversal + missing suffix both collapse to plain.md
    payload = json.loads(run_cli("save-report", "../../plain", "--vault", str(tmp_path)).stdout)
    assert payload["path"] == "queries/plain.md"


# --- byte-unchanged when kind already correct ------------------------------

def test_capture_leaves_correct_kind_byte_unchanged(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    page = _page(config.queries_dir(tmp_path), "已标注.md", {"title": "t", "sources": [], "kind": "query"})
    before = page.read_bytes()
    payload = json.loads(run_cli("save-report", "已标注", "--vault", str(tmp_path)).stdout)
    assert payload["ok"] is True
    assert page.read_bytes() == before  # not rewritten
    assert len([ln for ln in _log_lines(tmp_path) if "capture" in ln]) == 1  # exactly one log entry


def test_capture_logs_exactly_one_entry_per_call(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    _page(config.queries_dir(tmp_path), "s.md", {"title": "s", "sources": []})
    run_cli("save-report", "s", "--vault", str(tmp_path))
    run_cli("save-report", "s", "--vault", str(tmp_path))
    capture_lines = [ln for ln in _log_lines(tmp_path) if "capture |" in ln]
    assert len(capture_lines) == 2


# --- guards ----------------------------------------------------------------

def test_capture_requires_initialized_wiki(tmp_path):
    result = run_cli("save-report", "x", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "wiki_not_initialized", "hint": "run init first"}


def test_capture_missing_page_errors(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    result = run_cli("save-report", "ghost", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert json.loads(result.stderr) == {"error": "capture_not_found", "path": "queries/ghost.md"}


def test_capture_bad_frontmatter_no_side_effects(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    bad = config.queries_dir(tmp_path) / "bad.md"
    bad.write_text("---\nkey: [\n---\nbody", encoding="utf-8")
    before = bad.read_bytes()
    log_before = _log_lines(tmp_path)
    result = run_cli("save-report", "bad", "--vault", str(tmp_path))
    assert result.returncode == 1
    assert "error" in json.loads(result.stderr)
    assert bad.read_bytes() == before  # not rewritten
    assert _log_lines(tmp_path) == log_before  # no log entry


# --- source-note immutability ----------------------------------------------

def test_capture_never_modifies_sources(tmp_path):
    run_cli("init", "--vault", str(tmp_path))
    note = tmp_path / "笔记" / "source.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Source\n[[link]]\n", encoding="utf-8")
    fp = (hashlib.sha256(note.read_bytes()).digest(), note.stat().st_mtime_ns)
    _page(config.queries_dir(tmp_path), "s.md", {"title": "s", "sources": ["笔记/source.md"]})
    run_cli("save-report", "s", "--vault", str(tmp_path))
    assert (hashlib.sha256(note.read_bytes()).digest(), note.stat().st_mtime_ns) == fp
