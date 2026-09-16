"""Regression tests for codex_bridge.py.

Run: python -m pytest skills/cc-codex/tests/test_codex_bridge.py
These mock run_shell_command / subprocess; no real codex process is launched.
"""

import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "codex_bridge.py"
_spec = importlib.util.spec_from_file_location("codex_bridge", _SRC)
cb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cb)


def test_no_test_mutates_the_shared_os_name():
    """Tests must patch codex_bridge._is_windows, never the shared os.<name>.

    On Linux + py3.11 pathlib.Path.__new__ picks its flavour from that value and
    pytest builds Paths mid-run, so leaking it surfaces as INTERNALERROR: cannot
    instantiate 'WindowsPath' on your system. It cannot reproduce on Windows,
    where the value is already "nt" -- hence a source check rather than a value
    comparison, which cannot see a no-op patch.
    """
    # split so this file does not match its own scan: the attribute spelling,
    # and the setattr form, which names the module and attribute as arguments
    needles = ("os." + "name", "os, " + '"name"')
    for path in sorted(Path(__file__).parent.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{path.name}: patch codex_bridge._is_windows, not the shared {needle}"


def _run_main(monkeypatch, capsys, fake_run, argv_extra):
    monkeypatch.setattr(cb, "run_shell_command", fake_run)
    monkeypatch.setattr(sys, "argv", ["codex_bridge.py", "--PROMPT", "x", "--cd", "."] + argv_extra)
    cb.main()
    return json.loads(capsys.readouterr().out)


def test_last_message_fallback_recovers_corrupted_answer(monkeypatch, capsys):
    """A+E: agent_message line is corrupted JSON, but --output-last-message holds the answer."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        path = cmd[cmd.index("--output-last-message") + 1]
        Path(path).write_text("hello world", encoding="utf-8")
        yield json.dumps({"type": "thread.started", "thread_id": "sess-123"})
        yield '{"item": {"type": "agent_message", "text": "hel'  # truncated/corrupt
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is True
    assert out["agent_messages"] == "hello world"
    assert out["SESSION_ID"] == "sess-123"


def test_stream_file_persists_every_line(monkeypatch, capsys, tmp_path):
    """B: every raw line is written to disk so a mid-run kill keeps partial output."""
    sf = tmp_path / "stream.jsonl"

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "s"})
        yield json.dumps({"item": {"type": "agent_message", "text": "hi"}})
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, ["--stream-file", str(sf)])
    lines = sf.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[1])["item"]["text"] == "hi"
    assert out["stream_file"] == str(sf)


def test_idle_timeout_not_swallowed_by_reconciliation(monkeypatch, capsys):
    """C + cross-check issue #1: a hard idle timeout AFTER a partial answer must
    still report success=False, not be cleared by the success reconciliation."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-9"})
        yield json.dumps({"item": {"type": "agent_message", "text": "partial..."}})
        yield json.dumps(
            {"type": "error", "message": "[bridge] idle timeout after 600s with no output", "_bridge_fatal": True}
        )

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is False
    assert "idle timeout" in out["error"]


def test_item_level_error_is_detected(monkeypatch, capsys):
    """E: codex 0.136 reports errors as item.completed/item.type==error (not top-level)."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-1"})
        yield json.dumps({"type": "item.completed", "item": {"type": "error", "message": "boom at item level"}})
        # no agent_message and codex wrote nothing to the last-message file

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is False
    assert "boom at item level" in out["error"]


def test_item_level_reconnect_is_tolerated(monkeypatch, capsys):
    """E: an item-level transient reconnect must NOT bury a real final answer."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-2"})
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "error", "message": "Reconnecting... 1/5 (stream disconnected before completion: x)"},
            }
        )
        yield json.dumps({"item": {"type": "agent_message", "text": "final answer"}})
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is True
    assert out["agent_messages"] == "final answer"


def test_happy_path_reports_stream_and_session(monkeypatch, capsys):
    """Baseline: normal turn still works after the changes."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-ok"})
        yield json.dumps({"item": {"type": "agent_message", "text": "hello"}})
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is True
    assert out["agent_messages"] == "hello"
    assert "stream_file" in out


def test_multiple_agent_messages_returns_only_last(monkeypatch, capsys):
    """Regression: codex emits one agent_message per preamble between tool
    calls plus a final one. Only the last is the answer; concatenating them
    pollutes the output (2MB file bug). Match --output-last-message semantics."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-multi"})
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "First I'll read the file."},
            }
        )
        yield json.dumps(
            {"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "ls"}}
        )
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "command_execution", "command": "ls", "exit_code": 0},
            }
        )
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_2", "type": "agent_message", "text": "Now checking the config."},
            }
        )
        yield json.dumps(
            {"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": "FINAL ANSWER: done."}}
        )
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is True
    assert out["agent_messages"] == "FINAL ANSWER: done."
    assert "First I'll read" not in out["agent_messages"]
    assert "Now checking" not in out["agent_messages"]


def test_empty_final_agent_message_keeps_prior_nonempty(monkeypatch, capsys):
    """A trailing empty agent_message text must not wipe the real answer
    (codex never writes an empty final message to --output-last-message)."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-empty-final"})
        yield json.dumps(
            {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "real answer"}}
        )
        yield json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": ""}})
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is True
    assert out["agent_messages"] == "real answer"


def test_turn_failed_after_preambles_reports_failure(monkeypatch, capsys):
    """Regression: a hard 429 failure (turn.failed, no turn.completed) must not
    report the last preamble narration as the final answer with success=true.
    Event sequence replayed from a captured real stream."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-429"})
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "I will locate the adapter first."},
            }
        )
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "Now converging the fix into two edits."},
            }
        )
        yield json.dumps({"type": "error", "message": "Reconnecting... 1/5 (stream disconnected before completion: x)"})
        yield json.dumps({"type": "error", "message": "exceeded retry limit, last status: 429 Too Many Requests"})
        yield json.dumps(
            {"type": "turn.failed", "error": {"message": "exceeded retry limit, last status: 429 Too Many Requests"}}
        )

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is False
    assert "429" in out["error"]
    assert "did not complete" in out["error"]
    assert "agent_messages" not in out


def test_truncated_stream_without_turn_event_reports_failure(monkeypatch, capsys):
    """A stream that dies after preambles (no turn.completed/turn.failed, no
    error event) must not be reported as success."""

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        yield json.dumps({"type": "thread.started", "thread_id": "sess-cut"})
        yield json.dumps({"item": {"type": "agent_message", "text": "Working on it..."}})

    out = _run_main(monkeypatch, capsys, fake_run, [])
    assert out["success"] is False
    assert "did not complete" in out["error"]
    assert "agent_messages" not in out


def test_ignore_user_config_and_hook_trust_flags_in_cmd(monkeypatch, capsys):
    captured = {}

    def fake_run(cmd, idle_timeout=300.0, stderr_sink=None):
        captured["cmd"] = cmd
        yield json.dumps({"type": "thread.started", "thread_id": "sess-flags"})
        yield json.dumps({"item": {"type": "agent_message", "text": "ok"}})
        yield json.dumps({"type": "turn.completed"})

    out = _run_main(
        monkeypatch,
        capsys,
        fake_run,
        ["--ignore-user-config", "--dangerously-bypass-hook-trust"],
    )
    assert out["success"] is True
    assert "--ignore-user-config" in captured["cmd"]
    assert "--dangerously-bypass-hook-trust" in captured["cmd"]
    assert captured["cmd"][:2] == ["codex", "exec"]


def test_build_exec_cmd_default_omits_isolation_flags():
    args = SimpleNamespace(
        PROMPT="p",
        cd=".",
        sandbox="read-only",
        image=[],
        model="",
        profile="",
        yolo=False,
        skip_git_repo_check=True,
        ignore_user_config=False,
        dangerously_bypass_hook_trust=False,
        SESSION_ID="",
    )
    cmd, last = cb.build_exec_cmd(args)
    assert "--ignore-user-config" not in cmd
    assert "--dangerously-bypass-hook-trust" not in cmd
    assert "--skip-git-repo-check" in cmd
    assert cmd[:2] == ["codex", "exec"]
    assert "--ask-for-approval" not in cmd
    assert "--approval-policy" not in cmd
    Path(last).unlink(missing_ok=True)


def test_build_exec_cmd_yolo_uses_canonical_bypass_flag():
    """The bridge's --yolo maps to Codex's canonical bypass option."""
    args = SimpleNamespace(
        PROMPT="p",
        cd=".",
        sandbox="read-only",
        image=[],
        model="",
        profile="",
        yolo=True,
        skip_git_repo_check=True,
        ignore_user_config=False,
        dangerously_bypass_hook_trust=False,
        SESSION_ID="",
    )
    cmd, last = cb.build_exec_cmd(args)
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--yolo" not in cmd
    assert "--ask-for-approval" not in cmd
    Path(last).unlink(missing_ok=True)


def test_mcp_passthrough(monkeypatch, capsys):
    def fake_run(popen_cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="mcp-list-ok\n", stderr="")

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["codex_bridge.py", "mcp", "list"])
    cb.main()
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
    assert "mcp-list-ok" in out["output"]


def test_plugin_passthrough_timeout(monkeypatch, capsys):
    def fake_run(popen_cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=1)

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["codex_bridge.py", "plugin", "list"])
    cb.main()
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False
    assert "timed out" in out["error"]


class _FakeStdin:
    def __init__(self):
        self.chunks = []
        self.closed = False

    def write(self, value):
        self.chunks.append(value)

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self, pid=4242):
        self.pid = pid
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


def test_cmd_quote_rust_bat_encoding(monkeypatch):
    """Embedded quotes must survive the npm .cmd shim's double re-parse:
    "A \"Out of scope\" B" arrives as ONE argv entry, not three."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    command = cb._prepare_popen_cmd(
        ["codex.cmd", "exec", "--", 'A "Out of scope" B 100% done'],
        {"COMSPEC": "cmd.exe"},
    )
    assert command.startswith('"cmd.exe" /d /s /c "')
    # quotes: doubled, never the broken quote-caret-quote-quote escape
    assert '"A ""Out of scope"" B 100' in command
    assert '"^""' not in command
    # percent: yt-dlp form, never a bare doubled % that survives to the child
    assert "100%%cd:~,% done" in command
    assert "100%% done" not in command


def test_cmd_quote_empty_and_trailing_backslashes(monkeypatch):
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    command = cb._prepare_popen_cmd(["codex.cmd", "exec", "--", "\\"], {})
    # trailing backslash run is doubled so the closing quote is not escaped
    assert command.endswith('"exec" "--" "\\\\""')


def test_passthrough_keeps_new_quoting_and_devnull_stdin(monkeypatch):
    """mcp/plugin passthrough must use the new quoting but never take the
    stdin-prompt path (its last arg is not a PROMPT)."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(cb.subprocess, "Popen", fake_popen)
    list(cb.run_shell_command(["codex.cmd", "mcp", "list"], idle_timeout=0))
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert '/d /s /c ""C:\\npm\\codex.cmd" "mcp" "list""' in captured["command"]


def test_shim_exec_prompt_goes_through_stdin(monkeypatch):
    """On the Windows shim path the PROMPT positional is rewritten to `-` and
    delivered via stdin, so an 8k+ prompt can't hit "command line too long"."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(cb.subprocess, "Popen", fake_popen)
    list(cb.run_shell_command(["codex", "exec", "--", "x" * 9000], idle_timeout=0))
    assert captured["kwargs"]["stdin"] is subprocess.PIPE
    assert captured["command"].endswith('"exec" "--" "-""')


def test_shim_exec_prompt_stdin_delivered(monkeypatch):
    """Same as above but asserts the prompt bytes actually reach stdin."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    proc = _FakeProcess()

    monkeypatch.setattr(cb.subprocess, "Popen", lambda command, **kwargs: proc)
    list(cb.run_shell_command(["codex", "exec", "--", "x" * 9000], idle_timeout=0))
    for _ in range(100):
        if proc.stdin.closed:
            break
        time.sleep(0.01)
    assert "".join(proc.stdin.chunks) == "x" * 9000
    assert proc.stdin.closed


def test_posix_exec_keeps_devnull_stdin(monkeypatch):
    monkeypatch.setattr(cb, "_is_windows", lambda: False)
    captured = {}

    def fake_popen(command, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(cb.subprocess, "Popen", fake_popen)
    list(cb.run_shell_command(["codex", "exec", "--", "prompt"], idle_timeout=0))
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL


def test_windows_termination_kills_process_tree(monkeypatch):
    """terminate() on the cmd.exe wrapper orphans node; taskkill /T /F is required."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: r"C:\npm\codex.cmd")
    calls = []

    class _Proc(_FakeProcess):
        def __init__(self):
            super().__init__(pid=4321)
            self.exited = False

        def poll(self):
            return 0 if self.exited else None

        def wait(self, timeout=None):
            if timeout is not None and not self.exited:
                raise subprocess.TimeoutExpired("cmd", timeout)
            self.exited = True
            return 0

    proc = _Proc()

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        proc.exited = True

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    monkeypatch.setattr(cb.subprocess, "Popen", lambda command, **kwargs: proc)
    list(cb.run_shell_command(["codex.cmd", "mcp", "list"], idle_timeout=0))
    assert ["taskkill", "/T", "/F", "/PID", "4321"] in [c[0] for c in calls]


def test_output_reader_is_daemon_thread(monkeypatch):
    """A blocked readline after a tree-kill that misses a grandchild must not
    keep the interpreter alive once the caller stops consuming."""
    monkeypatch.setattr(cb, "_is_windows", lambda: False)
    created = []
    real_thread = threading.Thread

    def factory(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        created.append(t)
        return t

    monkeypatch.setattr(cb.threading, "Thread", factory)
    monkeypatch.setattr(cb.subprocess, "Popen", lambda command, **kwargs: _FakeProcess())
    list(cb.run_shell_command(["codex", "exec", "--", "x"], idle_timeout=0))
    assert created and all(t.daemon for t in created)
