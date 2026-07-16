"""
Codex Bridge Script for Claude Agent Skills.
Wraps the Codex CLI to provide a JSON-based interface for Claude.
"""
from __future__ import annotations

import json
import re
import os
import sys
import queue
import subprocess
import threading
import time
import shutil
import argparse
import tempfile
from pathlib import Path
from typing import Generator, List, Optional


def _get_windows_npm_paths() -> List[Path]:
    """Return candidate directories for npm global installs on Windows."""
    if os.name != "nt":
        return []
    paths: List[Path] = []
    env = os.environ
    if prefix := env.get("NPM_CONFIG_PREFIX") or env.get("npm_config_prefix"):
        paths.append(Path(prefix))
    if appdata := env.get("APPDATA"):
        paths.append(Path(appdata) / "npm")
    if localappdata := env.get("LOCALAPPDATA"):
        paths.append(Path(localappdata) / "npm")
    if programfiles := env.get("ProgramFiles"):
        paths.append(Path(programfiles) / "nodejs")
    return paths


def _augment_path_env(env: dict) -> None:
    """Prepend npm global directories to PATH if missing."""
    if os.name != "nt":
        return
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_entries = [p for p in env.get(path_key, "").split(os.pathsep) if p]
    lower_set = {p.lower() for p in path_entries}
    for candidate in _get_windows_npm_paths():
        if candidate.is_dir() and str(candidate).lower() not in lower_set:
            path_entries.insert(0, str(candidate))
            lower_set.add(str(candidate).lower())
    env[path_key] = os.pathsep.join(path_entries)


def _resolve_executable(name: str, env: dict) -> str:
    """Resolve executable path, checking npm dirs for .cmd/.bat on Windows."""
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return name
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_val = env.get(path_key)
    win_exts = {".exe", ".cmd", ".bat", ".com"}
    if resolved := shutil.which(name, path=path_val):
        if os.name == "nt":
            suffix = Path(resolved).suffix.lower()
            if not suffix:
                resolved_dir = str(Path(resolved).parent)
                for ext in (".cmd", ".bat", ".exe", ".com"):
                    candidate = Path(resolved_dir) / f"{name}{ext}"
                    if candidate.is_file():
                        return str(candidate)
            elif suffix not in win_exts:
                return resolved
        return resolved
    if os.name == "nt":
        for base in _get_windows_npm_paths():
            for ext in (".cmd", ".bat", ".exe", ".com"):
                candidate = base / f"{name}{ext}"
                if candidate.is_file():
                    return str(candidate)
    return name


def _prepare_popen_cmd(cmd: List[str], env: dict):
    """Resolve executable and wrap Windows .cmd/.bat via cmd.exe."""
    popen_cmd = cmd.copy()
    exe_path = _resolve_executable(cmd[0], env)
    popen_cmd[0] = exe_path

    if os.name == "nt" and Path(exe_path).suffix.lower() in {".cmd", ".bat"}:
        # cmd.exe truncates argv at embedded \n/\r/\t; escape as literals here only.
        popen_cmd = [windows_escape(a) for a in popen_cmd]

        def _cmd_quote(arg: str) -> str:
            if not arg:
                return '""'
            arg = arg.replace('%', '%%')
            arg = arg.replace('^', '^^')
            if any(c in arg for c in '&|<>()^" \t'):
                escaped = arg.replace('"', '"^""')
                return f'"{escaped}"'
            return arg

        cmdline = " ".join(_cmd_quote(a) for a in popen_cmd)
        comspec = env.get("COMSPEC", "cmd.exe")
        popen_cmd = f'"{comspec}" /d /s /c "{cmdline}"'
    return popen_cmd


def run_shell_command(cmd: List[str], idle_timeout: float = 600.0,
                      stderr_sink: Optional[List[str]] = None) -> Generator[str, None, None]:
    """Execute a command and stream its output line-by-line.

    idle_timeout: terminate the process if no line is produced for this many
    seconds (0 disables). On timeout a synthetic `_bridge_fatal` error line is
    yielded so callers can report a hard failure instead of hanging forever.
    stderr_sink: if provided, the child's stderr is drained into it on a separate
    thread (kept off stdout so it cannot corrupt the JSON stream).
    """
    env = os.environ.copy()
    _augment_path_env(env)
    popen_cmd = _prepare_popen_cmd(cmd, env)

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )

    output_queue: queue.Queue[Optional[str]] = queue.Queue()
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_turn_completed(line: str) -> bool:
        try:
            data = json.loads(line)
            return data.get("type") == "turn.completed"
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                output_queue.put(stripped)
                if is_turn_completed(stripped):
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    process.terminate()
                    break
            process.stdout.close()
        output_queue.put(None)

    def read_stderr() -> None:
        if process.stderr:
            for line in iter(process.stderr.readline, ""):
                if stderr_sink is not None:
                    stderr_sink.append(line.rstrip("\n"))
            process.stderr.close()

    thread = threading.Thread(target=read_output)
    thread.start()
    err_thread = threading.Thread(target=read_stderr, daemon=True)
    err_thread.start()

    last_activity = time.monotonic()
    while True:
        try:
            line = output_queue.get(timeout=0.5)
            last_activity = time.monotonic()
            if line is None:
                break
            yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break
            if idle_timeout and (time.monotonic() - last_activity) > idle_timeout:
                process.terminate()
                yield json.dumps({
                    "type": "error",
                    "message": f"[bridge] idle timeout after {idle_timeout:.0f}s with no output",
                    "_bridge_fatal": True,
                })
                break

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    thread.join(timeout=5)
    err_thread.join(timeout=5)

    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


def windows_escape(prompt):
    """Windows style string escaping for newlines and special chars in prompt text."""
    result = prompt.replace('\n', '\\n')
    result = result.replace('\r', '\\r')
    result = result.replace('\t', '\\t')
    return result


def configure_windows_stdio() -> None:
    """Configure stdout/stderr to use UTF-8 encoding on Windows."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def emit(result: dict) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))


def run_passthrough(subcommand: str, extra: List[str], timeout: float = 120.0) -> None:
    """Thin passthrough to `codex <subcommand> ...` (mcp / plugin management)."""
    env = os.environ.copy()
    _augment_path_env(env)
    cmd = ["codex", subcommand] + extra
    popen_cmd = _prepare_popen_cmd(cmd, env)
    try:
        cp = subprocess.run(
            popen_cmd,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        emit({
            "success": cp.returncode == 0,
            "output": cp.stdout or "",
            "error": cp.stderr or "",
            "returncode": cp.returncode,
        })
    except subprocess.TimeoutExpired:
        emit({"success": False, "output": "", "error": f"codex {subcommand} timed out", "returncode": -1})
    except FileNotFoundError:
        emit({"success": False, "output": "", "error": "codex binary not found in PATH", "returncode": 127})


def build_exec_cmd(args) -> List[str]:
    """Build `codex exec ...` argv from parsed run args."""
    last_fd, last_msg_path = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
    os.close(last_fd)

    cmd = ["codex", "exec", "--sandbox", args.sandbox, "--cd", args.cd, "--json",
           "--output-last-message", last_msg_path]

    if args.image:
        cmd.extend(["--image", ",".join(args.image)])

    if args.model:
        cmd.extend(["--model", args.model])

    if args.profile:
        cmd.extend(["--profile", args.profile])

    if args.yolo:
        cmd.append("--yolo")

    if args.skip_git_repo_check:
        cmd.append("--skip-git-repo-check")

    if args.ignore_user_config:
        cmd.append("--ignore-user-config")

    if args.dangerously_bypass_hook_trust:
        cmd.append("--dangerously-bypass-hook-trust")

    if args.SESSION_ID:
        cmd.extend(["resume", args.SESSION_ID])

    cmd += ['--', args.PROMPT]
    return cmd, last_msg_path


def cmd_run(args) -> None:
    cmd, last_msg_path = build_exec_cmd(args)

    all_messages = []
    agent_messages = ""
    success = True
    err_message = ""
    thread_id = None
    timed_out = False
    stderr_sink: List[str] = []

    # Persist the raw JSONL stream incrementally so partial output survives a
    # crash/kill/timeout (the in-memory result is only printed once at the end).
    if args.stream_file:
        stream_path = args.stream_file
        stream_fp = open(stream_path, "w", encoding="utf-8")
    else:
        sfd, stream_path = tempfile.mkstemp(prefix="codex_stream_", suffix=".jsonl")
        stream_fp = os.fdopen(sfd, "w", encoding="utf-8")

    for line in run_shell_command(cmd, idle_timeout=args.idle_timeout, stderr_sink=stderr_sink):
        stream_fp.write(line + "\n")
        stream_fp.flush()
        try:
            line_dict = json.loads(line.strip())
            all_messages.append(line_dict)
            item = line_dict.get("item", {})
            item_type = item.get("type", "")
            if item_type == "agent_message":
                # codex emits one agent_message per preamble between tool calls
                # plus a final one; only the last non-empty text is the answer
                # (same semantics as --output-last-message). Concatenating them
                # pollutes the result with intermediate narration.
                agent_messages = item.get("text", "") or agent_messages
            if line_dict.get("thread_id") is not None:
                thread_id = line_dict.get("thread_id")
            if line_dict.get("_bridge_fatal"):
                timed_out = True
                success = False
            # Error/reconnect events appear either top-level (codex <= 0.130) or
            # item-level (codex 0.136: item.completed + item.type == "error").
            top_type = line_dict.get("type", "")
            err_text = ""
            if "fail" in top_type:
                err_text = (line_dict.get("error") or {}).get("message", "") or line_dict.get("message", "")
            elif "error" in top_type:
                err_text = line_dict.get("message", "")
            elif item_type == "error":
                err_text = item.get("message", "")
            if err_text:
                is_reconnecting = bool(re.match(r'^Reconnecting\.\.\.\s+\d+/\d+(\s|$)', err_text))
                if not is_reconnecting:
                    success = False if len(agent_messages) == 0 else success
                    err_message += "\n\n[codex error] " + err_text

        except json.JSONDecodeError:
            err_message += "\n\n[json decode error] " + line
            continue

        except Exception as error:
            err_message += "\n\n[unexpected error] " + f"Unexpected error: {error}. Line: {line!r}"
            success = False if len(agent_messages) == 0 else success
            continue

    stream_fp.close()

    # Parse-independent fallback: codex wrote the final answer to a file via
    # --output-last-message, so a corrupted/dropped agent_message line is recoverable.
    if len(agent_messages) == 0:
        try:
            file_msg = Path(last_msg_path).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            file_msg = ""
        if file_msg:
            agent_messages = file_msg

    if thread_id is None:
        success = False
        err_message = "Failed to get `SESSION_ID` from the codex session. \n\n" + err_message

    if len(agent_messages) == 0:
        success = False
        err_message = "Failed to get `agent_messages` from the codex session. \n\n You can try to set `return_all_messages` to `True` to get the full reasoning information. " + err_message
    elif thread_id is not None and not timed_out:
        # Turn completed with both thread_id and agent_messages → transient errors
        # mid-stream (reconnects, decode noise) must not bury the final answer.
        # A hard idle timeout (timed_out) is exempt: never report it as success.
        success = True
        err_message = ""

    if success:
        result = {
            "success": True,
            "SESSION_ID": thread_id,
            "agent_messages": agent_messages,
        }
    else:
        result = {"success": False, "error": err_message}

    result["stream_file"] = stream_path
    if stderr_sink:
        result["stderr"] = "\n".join(stderr_sink)

    if args.return_all_messages:
        result["all_messages"] = all_messages

    try:
        os.unlink(last_msg_path)
    except OSError:
        pass

    emit(result)


def main():
    configure_windows_stdio()

    # Subcommand passthrough must bypass argparse so trailing args stay intact
    # (e.g. `mcp list`, `plugin marketplace list`).
    if len(sys.argv) > 1 and sys.argv[1] in ("mcp", "plugin"):
        run_passthrough(sys.argv[1], sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="Codex Bridge")
    parser.add_argument("--PROMPT", required=True, help="Instruction for the task to send to codex.")
    parser.add_argument("--cd", required=True, help="Set the workspace root for codex before executing the task.")
    parser.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"], help="Sandbox policy for model-generated commands. Defaults to `read-only`.")
    parser.add_argument("--SESSION_ID", default="", help="Resume the specified session of the codex. Defaults to `None`, start a new session.")
    parser.add_argument("--skip-git-repo-check", action="store_true", default=True, help="Allow codex running outside a Git repository (useful for one-off directories).")
    parser.add_argument("--return-all-messages", action="store_true", help="Return all messages (e.g. reasoning, tool calls, etc.) from the codex session. Set to `False` by default, only the agent's final reply message is returned.")
    parser.add_argument("--image", action="append", default=[], help="Attach one or more image files to the initial prompt. Separate multiple paths with commas or repeat the flag.")
    parser.add_argument("--model", default="", help="The model to use for the codex session. This parameter is strictly prohibited unless explicitly specified by the user.")
    parser.add_argument("--yolo", action="store_true", help="Run every command without approvals or sandboxing. Only use when `sandbox` couldn't be applied.")
    parser.add_argument("--profile", default="", help="Configuration profile name to load from `~/.codex/config.toml`. This parameter is strictly prohibited unless explicitly specified by the user.")
    parser.add_argument("--stream-file", default="", help="Append each raw JSONL line here as it arrives so partial output survives a crash/kill/timeout. Empty -> auto temp file; the path is reported in the result.")
    parser.add_argument("--idle-timeout", type=float, default=600.0, help="Terminate codex if no output is received for this many seconds (0 disables).")
    parser.add_argument("--ignore-user-config", action="store_true", help="Do not load `$CODEX_HOME/config.toml` (auth still uses CODEX_HOME). Isolates the session from user global config.")
    parser.add_argument("--dangerously-bypass-hook-trust", action="store_true", help="Run enabled Codex hooks without requiring persisted hook trust. DANGEROUS; only for vetted automation.")

    # Document subcommands in --help without going through argparse positional parse.
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("mcp", help="Thin passthrough to `codex mcp` (list/get/add/remove/login/logout).")
    sub.add_parser("plugin", help="Thin passthrough to `codex plugin` (add/list/remove/marketplace).")

    args = parser.parse_args()
    cmd_run(args)


if __name__ == "__main__":
    main()
