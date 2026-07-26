import hashlib
import subprocess
import sys
from pathlib import Path

from agent_wiki import config, frontmatter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_wiki_cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, encoding="utf-8", capture_output=True)


def _fingerprint(path: Path) -> tuple[bytes, int]:
    return hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns


def test_capture_canvas_home_status_never_touch_sources(tmp_path):
    run_cli("init", "--vault", str(tmp_path))

    # source notes (root + nested) and an attachment, all outside wiki/
    root_note = tmp_path / "root.md"
    root_note.write_text("# Root\n[[N]] ![[img.png]]\n", encoding="utf-8")
    nested = tmp_path / "笔记" / "deep.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# Deep\n", encoding="utf-8")
    attachment = tmp_path / "attachments" / "img.png"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"\x89PNG\r\n\x1a\n binary")

    # wiki artifacts referencing those sources
    (config.topics_dir(tmp_path) / "T.md").write_text(
        frontmatter.dump({"title": "T", "sources": ["root.md", "笔记/deep.md"]}, "见 [[N]]\n"), encoding="utf-8")
    (config.topics_dir(tmp_path) / "N.md").write_text(
        frontmatter.dump({"title": "N", "sources": []}, "b"), encoding="utf-8")
    (config.queries_dir(tmp_path) / "q.md").write_text(
        frontmatter.dump({"title": "q", "sources": []}, "b"), encoding="utf-8")

    guarded = {p: _fingerprint(p) for p in (root_note, nested, attachment)}

    commands = [
        ("save-report", "q"),
        ("save-report", "../root"),       # traversal escape attempt -> sanitized, capture_not_found
        ("gen-canvas", "--topic", "T"),
        ("gen-canvas", "--all"),
        ("gen-home",),
        ("gen-home", "--cards", "on"),
        ("gen-home", "--cards", "off"),
        ("status",),
    ]
    for cmd in commands:
        run_cli(*cmd, "--vault", str(tmp_path))
        for path, original in guarded.items():
            assert _fingerprint(path) == original, f"{path} changed after {cmd[0]}"

    # traversal never created/overwrote a sources/queries page outside its dir
    assert not (config.queries_dir(tmp_path) / "root.md").exists()
    assert root_note.read_text(encoding="utf-8") == "# Root\n[[N]] ![[img.png]]\n"
