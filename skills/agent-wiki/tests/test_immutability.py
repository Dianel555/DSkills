import hashlib
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


def _fingerprint(path: Path) -> tuple[bytes, int]:
    return hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns


def test_index_gen_base_status_never_touch_sources_or_attachments(tmp_path):
    run_cli("init", "--vault", str(tmp_path))

    note = tmp_path / "笔记" / "source.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Source\n[[link]]\n", encoding="utf-8")
    attachment = tmp_path / "attachments" / "image.png"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"\x89PNG\r\n\x1a\n binary blob")

    topic = config.topics_dir(tmp_path) / "T.md"
    topic.write_text(frontmatter.dump({"title": "T", "sources": ["笔记/source.md"]}, "b"), encoding="utf-8")

    guarded = {p: _fingerprint(p) for p in (note, attachment)}

    for cmd in (("index",), ("gen-base", "--name", "sources"), ("status",)):
        assert run_cli(*cmd, "--vault", str(tmp_path)).returncode == 0
        for path, original in guarded.items():
            assert _fingerprint(path) == original, f"{path} changed after {cmd[0]}"
