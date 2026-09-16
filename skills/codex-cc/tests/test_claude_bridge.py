"""Regression tests for claude_bridge.py.

Run: python -m pytest skills/codex-cc/tests/test_claude_bridge.py
These tests mock subprocess execution; no real Claude process is launched.
"""

import importlib.util
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "claude_bridge.py"
_spec = importlib.util.spec_from_file_location("claude_bridge", _SRC)
cb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cb)


def _run_main(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["claude_bridge.py", *argv])
    cb.main()
    return json.loads(capsys.readouterr().out)


def _stream_event(event):
    return json.dumps(event, ensure_ascii=False)


def test_build_claude_cmd_new_session_generates_uuid(monkeypatch, tmp_path):
    fixed_uuid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cb.uuid, "uuid4", lambda: fixed_uuid)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=600.0,
    )

    cmd, session_id = cb.build_claude_cmd(args)

    workspace = str(tmp_path.resolve())
    assert cmd[:7] == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--add-dir",
        workspace,
    ]
    assert cmd[cmd.index("--session-id") + 1] == str(fixed_uuid)
    assert cmd[-1] == "Analyze auth"
    assert session_id == str(fixed_uuid)
    assert "--resume" not in cmd
    assert "--safe-mode" not in cmd
    assert "--bare" not in cmd
    assert "--disable-slash-commands" not in cmd
    assert "--strict-mcp-config" not in cmd
    assert "--permission-mode" not in cmd
    assert "--dangerously-skip-permissions" not in cmd


def test_build_claude_cmd_resume_preserves_session_and_opt_in_flags(tmp_path):
    session_id = "22222222-2222-2222-2222-222222222222"
    args = SimpleNamespace(
        PROMPT="Continue",
        cd=tmp_path,
        SESSION_ID=session_id,
        model="sonnet",
        permission_mode="plan",
        dangerously_skip_permissions=True,
        timeout=42.0,
    )

    cmd, returned_session = cb.build_claude_cmd(args)

    assert cmd[cmd.index("--resume") + 1] == session_id
    assert "--session-id" not in cmd
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"
    assert "--dangerously-skip-permissions" in cmd
    assert returned_session == session_id


def test_missing_workspace_fails_without_launch(monkeypatch, capsys, tmp_path):
    launched = {"value": False}

    def fake_stream(*args, **kwargs):
        launched["value"] = True
        raise AssertionError("Claude should not be called")

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path / "missing",
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=600.0,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False
    assert "does not exist" in out["error"]
    assert "agent_messages" not in out
    assert launched["value"] is False


def test_success_envelope_and_workspace_coherence(monkeypatch, capsys, tmp_path):
    fixed_uuid = uuid.UUID("33333333-3333-3333-3333-333333333333")
    captured = {}
    stream_file = tmp_path / "claude-stream.jsonl"

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        captured["popen_cmd"] = popen_cmd
        captured["workspace"] = workspace
        captured["timeout"] = timeout
        stderr_sink.append("warning")
        yield _stream_event(
            {"type": "system", "subtype": "init", "session_id": str(fixed_uuid)}
        )
        yield _stream_event(
            {
                "type": "assistant",
                "session_id": str(fixed_uuid),
                "message": {"content": [{"type": "text", "text": "intermediate"}]},
            }
        )
        yield _stream_event(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": str(fixed_uuid),
                "result": "final answer",
            }
        )

    monkeypatch.setattr(cb.uuid, "uuid4", lambda: fixed_uuid)
    monkeypatch.setattr(cb, "_prepare_popen_cmd", lambda cmd, env: cmd)
    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=600.0,
        stream_file=str(stream_file),
        return_all_messages=True,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)
    workspace = str(tmp_path.resolve())

    assert out["success"] is True
    assert out["SESSION_ID"] == str(fixed_uuid)
    assert out["agent_messages"] == "final answer"
    assert out["stream_file"] == str(stream_file)
    assert [item["type"] for item in out["all_messages"]] == [
        "system",
        "assistant",
        "result",
    ]
    assert out["stderr"] == "warning"
    assert captured["workspace"] == workspace
    assert (
        captured["popen_cmd"][captured["popen_cmd"].index("--add-dir") + 1] == workspace
    )
    assert stream_file.read_text(encoding="utf-8").count("\n") == 3


def test_result_error_is_not_masked_by_assistant_message(monkeypatch, capsys, tmp_path):
    session_id = "33333333-3333-3333-3333-333333333333"

    def fake_stream(*args, **kwargs):
        yield _stream_event(
            {
                "type": "assistant",
                "session_id": session_id,
                "message": {"content": [{"type": "text", "text": "Working on it"}]},
            }
        )
        yield _stream_event(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "session_id": session_id,
                "result": "upstream failed",
            }
        )

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID=session_id,
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=None,
        stream_file="",
        return_all_messages=False,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["success"] is False
    assert out["SESSION_ID"] == session_id
    assert out["error"] == "upstream failed"
    assert "agent_messages" not in out
    assert Path(out["stream_file"]).is_file()


def test_timeout_failure_is_not_reported_as_success(monkeypatch, capsys, tmp_path):
    fixed_uuid = uuid.UUID("44444444-4444-4444-4444-444444444444")

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        yield _stream_event(
            {"type": "system", "subtype": "init", "session_id": str(fixed_uuid)}
        )
        stderr_sink.append("still running")
        raise subprocess.TimeoutExpired(
            cmd=popen_cmd, timeout=5, stderr="still running"
        )

    monkeypatch.setattr(cb.uuid, "uuid4", lambda: fixed_uuid)
    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=5.0,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False
    assert out["SESSION_ID"] == str(fixed_uuid)
    assert "timed out" in out["error"]
    assert "agent_messages" not in out
    assert Path(out["stream_file"]).read_text(encoding="utf-8").count("\n") == 1


def test_timeout_reports_last_transport_error(monkeypatch, capsys, tmp_path):
    """A 502 during retry must be visible in the timeout envelope, not just the stream."""

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        yield _stream_event(
            {
                "type": "system",
                "subtype": "api_retry",
                "attempt": 1,
                "max_retries": 10,
                "retry_delay_ms": 576,
                "error_status": 502,
                "error": "server_error",
            }
        )
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=5)

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=5.0,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["success"] is False
    assert "timed out" in out["error"]
    assert "HTTP 502" in out["error"]
    assert "server_error" in out["error"]
    assert "attempt 1/10" in out["error"]


def test_timeout_without_retry_events_keeps_plain_error(monkeypatch, capsys, tmp_path):
    """Absent transport failures the timeout message stays unembellished."""

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=5)

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=5.0,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["error"] == "claude timed out after 5.0s"


def test_omitted_timeout_disables_bridge_deadline(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        captured["timeout"] = timeout
        session_id = popen_cmd[popen_cmd.index("--session-id") + 1]
        yield _stream_event(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": session_id,
                "result": "done",
            }
        )

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)

    out = _run_main(
        monkeypatch,
        capsys,
        ["--PROMPT", "Analyze auth", "--cd", str(tmp_path)],
    )

    assert captured["timeout"] is None
    assert out["success"] is True


def test_interrupt_preserves_resume_session_id(monkeypatch, capsys, tmp_path):
    session_id = "55555555-5555-5555-5555-555555555555"

    def fake_stream(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Continue",
        cd=tmp_path,
        SESSION_ID=session_id,
        model="",
        permission_mode="plan",
        dangerously_skip_permissions=False,
        timeout=None,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["success"] is False
    assert out["SESSION_ID"] == session_id
    assert out["error"] == "claude interrupted"
    assert Path(out["stream_file"]).is_file()


def test_empty_stdout_is_a_failure(monkeypatch, capsys, tmp_path):
    def fake_stream(*args, **kwargs):
        if False:
            yield ""

    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=5.0,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False
    # D5: claude never started, so the pre-generated uuid is a phantom session
    # and must not be advertised as resumable.
    assert out["SESSION_ID"] == ""
    assert "without a result event" in out["error"].lower()
    assert "agent_messages" not in out
    assert Path(out["stream_file"]).is_file()


@pytest.mark.parametrize(
    ("subcommand", "extra"),
    [
        ("mcp", ["list", "--json"]),
        ("plugin", ["marketplace", "list"]),
    ],
)
def test_passthrough_argument_integrity(monkeypatch, capsys, subcommand, extra):
    captured = {}

    def fake_run(popen_cmd, **kwargs):
        captured["cmd"] = popen_cmd
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(cb, "_prepare_popen_cmd", lambda cmd, env: cmd)
    monkeypatch.setattr(cb.subprocess, "run", fake_run)

    out = _run_main(monkeypatch, capsys, [subcommand, *extra])
    assert captured["cmd"] == ["claude", subcommand, *extra]
    assert out["success"] is True
    assert out["returncode"] == 0
    assert out["output"] == "ok\n"


def test_passthrough_timeout_returns_failure(monkeypatch, capsys):
    def fake_run(popen_cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=1)

    monkeypatch.setattr(cb, "_prepare_popen_cmd", lambda cmd, env: cmd)
    monkeypatch.setattr(cb.subprocess, "run", fake_run)

    out = _run_main(monkeypatch, capsys, ["plugin", "list"])
    assert out["success"] is False
    assert "timed out" in out["error"]


def test_windows_resolution_falls_back_to_bin_dirs(monkeypatch, tmp_path):
    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    claude_cmd = npm_dir / "claude.cmd"
    claude_cmd.write_text("@echo off\n", encoding="utf-8")

    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_get_windows_bin_paths", lambda: [npm_dir])
    monkeypatch.setattr(cb.shutil, "which", lambda name, path=None: None)

    resolved = cb._resolve_executable("claude", {"PATH": ""})
    assert resolved == str(claude_cmd)


def test_windows_bin_paths_prioritize_native_installer():
    """The native installer dir must be probed before npm dirs.

    Guards the regression where the candidate list held only npm locations, so a
    machine whose launcher lives in ~/.local/bin fell through to a bare name.
    """
    env = {
        "NPM_CONFIG_PREFIX": "C:\\npm-prefix",
        "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
        "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local",
        "ProgramFiles": "C:\\Program Files",
    }

    candidates = cb._windows_bin_dir_candidates("C:\\Users\\test", env)

    native = candidates[0]
    assert native.endswith("bin") and ".local" in native
    npm_index = next(i for i, c in enumerate(candidates) if "npm-prefix" in c)
    assert 0 < npm_index


def test_windows_bin_dir_candidates_skip_unset_env():
    candidates = cb._windows_bin_dir_candidates(r"C:\Users\test", {})

    assert len(candidates) == 1
    assert candidates[0].endswith("bin")
    assert ".local" in candidates[0]


def test_prepare_popen_cmd_escapes_windows_prompt(monkeypatch, tmp_path):
    claude_cmd = tmp_path / "claude.cmd"
    prompt = 'line 1\nline 2\t"quoted" 100%'

    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(cb, "_resolve_executable", lambda name, env: str(claude_cmd))

    popen_cmd = cb._prepare_popen_cmd(
        ["claude", "-p", prompt], {"PATH": "", "COMSPEC": "cmd.exe"}
    )

    assert isinstance(popen_cmd, str)
    assert "claude.cmd" in popen_cmd
    assert "line 1\\nline 2\\t" in popen_cmd
    assert "100%%" in popen_cmd
    assert "quoted" in popen_cmd
    assert "\n" not in popen_cmd
    assert "\t" not in popen_cmd


def test_repository_catalog_registers_codex_cc():
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")
    marketplace = json.loads(
        (root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )

    assert "[codex-cc](skills/codex-cc/)" in readme
    entry = next(
        (item for item in marketplace["plugins"] if item["name"] == "codex-cc"), None
    )
    assert entry is not None
    assert entry["source"] == "./skills/codex-cc"
    assert "Claude Code" in entry["description"]


# --- Windows .cmd shim: BatBadBut quoting, stdin prompt delivery, tree-kill ---


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
        self.stdout = iter([])
        self.stderr = iter([])
        self.kwargs = {}

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


def test_cmd_quote_rust_bat_encoding(monkeypatch):
    """Embedded quotes must survive the npm .cmd shim re-parse: a prompt holding
    "Out of scope" arrives as ONE argv entry, not three (the `of` argv leak)."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(
        cb, "_resolve_executable", lambda name, env: r"C:\npm\claude.cmd"
    )
    command = cb._prepare_popen_cmd(
        ["claude", "-p", 'A "Out of scope" B 100% done'], {"COMSPEC": "cmd.exe"}
    )
    assert command.startswith('"cmd.exe" /d /s /c "')
    assert '"A ""Out of scope"" B 100' in command
    assert '"^""' not in command
    assert "100%%cd:~,% done" in command
    assert "100%% done" not in command


def test_cmd_quote_trailing_backslash(monkeypatch):
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(
        cb, "_resolve_executable", lambda name, env: r"C:\npm\claude.cmd"
    )
    command = cb._prepare_popen_cmd(["claude", "-p", "\\"], {})
    assert command.endswith('"-p" "\\\\""')


def test_shim_run_moves_prompt_to_stdin(monkeypatch, capsys, tmp_path):
    """On the Windows shim path the PROMPT positional is dropped and delivered
    via stdin, so an 8k+ prompt cannot hit the cmd.exe limit and embedded quotes
    never reach cmd.exe."""
    captured = {}

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        captured["cmd"] = popen_cmd
        captured["stdin_prompt"] = stdin_prompt
        yield _stream_event(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": "77777777-7777-7777-7777-777777777777",
                "result": "ok",
            }
        )

    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(
        cb, "_resolve_executable", lambda name, env: r"C:\npm\claude.cmd"
    )
    monkeypatch.setattr(cb, "_prepare_popen_cmd", lambda cmd, env: cmd)
    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT='A "Out of scope" B',
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=600.0,
        stream_file="",
        return_all_messages=False,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["success"] is True
    assert captured["stdin_prompt"] == 'A "Out of scope" B'
    assert captured["cmd"][1] == "-p"
    assert 'A "Out of scope" B' not in captured["cmd"]


def test_shim_stdin_prompt_bytes_are_delivered(monkeypatch):
    proc = _FakeProcess()

    def fake_popen(command, **kwargs):
        proc.kwargs = kwargs
        return proc

    monkeypatch.setattr(cb.subprocess, "Popen", fake_popen)

    list(cb._stream_claude_output("cmdline", ".", {}, None, [], "x" * 9000))

    for _ in range(100):
        if proc.stdin.closed:
            break
        time.sleep(0.01)
    assert "".join(proc.stdin.chunks) == "x" * 9000
    assert proc.stdin.closed
    assert proc.kwargs["stdin"] is subprocess.PIPE


def test_posix_run_keeps_prompt_positional(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_stream(popen_cmd, workspace, env, timeout, stderr_sink, stdin_prompt=None):
        captured["cmd"] = popen_cmd
        captured["stdin_prompt"] = stdin_prompt
        yield _stream_event(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": "88888888-8888-8888-8888-888888888888",
                "result": "ok",
            }
        )

    monkeypatch.setattr(cb, "_is_windows", lambda: False)
    monkeypatch.setattr(cb, "_prepare_popen_cmd", lambda cmd, env: cmd)
    monkeypatch.setattr(cb, "_stream_claude_output", fake_stream)
    args = SimpleNamespace(
        PROMPT="Analyze auth",
        cd=tmp_path,
        SESSION_ID="",
        model="",
        permission_mode="",
        dangerously_skip_permissions=False,
        timeout=600.0,
        stream_file="",
        return_all_messages=False,
    )

    cb.cmd_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["success"] is True
    assert captured["stdin_prompt"] is None
    assert captured["cmd"][-1] == "Analyze auth"


def test_windows_termination_kills_process_tree(monkeypatch):
    """terminate() on the cmd.exe wrapper orphans node/claude; taskkill /T /F is required."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
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
        calls.append(command)
        proc.exited = True

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    cb._stop_process(proc)

    assert ["taskkill", "/T", "/F", "/PID", "4321"] in calls


def test_posix_termination_uses_terminate(monkeypatch):
    monkeypatch.setattr(cb, "_is_windows", lambda: False)
    seen = {"terminate": False}

    class _Proc(_FakeProcess):
        def __init__(self):
            super().__init__()
            self.exited = False

        def poll(self):
            return 0 if self.exited else None

        def terminate(self):
            seen["terminate"] = True
            self.exited = True

    cb._stop_process(_Proc())

    assert seen["terminate"] is True


def test_passthrough_keeps_stdin_detached_on_windows(monkeypatch, capsys):
    """mcp/plugin passthrough must never take the stdin-prompt path: its argv has
    no PROMPT and cmd[1] is not -p, so stdin stays detached even on Windows."""
    captured = {}

    def fake_run(popen_cmd, **kwargs):
        captured["cmd"] = popen_cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    monkeypatch.setattr(
        cb, "_resolve_executable", lambda name, env: r"C:\npm\claude.cmd"
    )
    monkeypatch.setattr(cb.subprocess, "run", fake_run)

    out = _run_main(monkeypatch, capsys, ["mcp", "list"])

    assert out["success"] is True
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL


def test_stop_process_falls_back_to_kill(monkeypatch):
    """When tree termination does not finish the process, kill() is the fallback."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    seen = {"kill": False}

    class _Proc(_FakeProcess):
        def __init__(self):
            super().__init__(pid=5555)
            self.waits = 0

        def poll(self):
            return None

        def kill(self):
            seen["kill"] = True

        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("cmd", timeout)
            return 0

    proc = _Proc()
    monkeypatch.setattr(cb.subprocess, "run", lambda command, **kwargs: None)

    cb._stop_process(proc)

    assert seen["kill"] is True


def test_normal_completion_wait_timeout_triggers_tree_kill(monkeypatch):
    """A completion whose wrapper never exits must not hang the bridge: the wait
    timeout falls back to the same tree-kill."""
    monkeypatch.setattr(cb, "_is_windows", lambda: True)
    killed = []

    class _Proc(_FakeProcess):
        def __init__(self):
            super().__init__(pid=6666)

        def poll(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("cmd", timeout)
            return 0

    proc = _Proc()
    monkeypatch.setattr(cb.subprocess, "Popen", lambda command, **kwargs: proc)
    monkeypatch.setattr(
        cb.subprocess, "run", lambda command, **kwargs: killed.append(command)
    )

    list(cb._stream_claude_output("cmdline", ".", {}, None, []))

    assert ["taskkill", "/T", "/F", "/PID", "6666"] in killed
