"""Claude Bridge Script for Codex-facing DSkills.

Wraps the local Claude Code CLI in a stable JSON envelope so Codex can
delegate work while preserving Claude's normal runtime customizations.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import List, Sequence


PERMISSION_MODES = [
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "manual",
    "dontAsk",
    "plan",
]


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
    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
    path_entries = [entry for entry in env.get(path_key, "").split(os.pathsep) if entry]
    lower_set = {entry.lower() for entry in path_entries}
    for candidate in _get_windows_npm_paths():
        if candidate.is_dir() and str(candidate).lower() not in lower_set:
            path_entries.insert(0, str(candidate))
            lower_set.add(str(candidate).lower())
    env[path_key] = os.pathsep.join(path_entries)


def _resolve_executable(name: str, env: dict) -> str:
    """Resolve executable path, checking npm dirs for .cmd/.bat on Windows."""
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return name
    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
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


def windows_escape(value: str) -> str:
    """Escape control characters that cmd.exe would otherwise mangle."""
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    return value


def _prepare_popen_cmd(cmd: Sequence[str], env: dict):
    """Resolve executable and wrap Windows .cmd/.bat via cmd.exe."""
    popen_cmd = list(cmd)
    exe_path = _resolve_executable(popen_cmd[0], env)
    popen_cmd[0] = exe_path

    if os.name == "nt" and Path(exe_path).suffix.lower() in {".cmd", ".bat"}:
        popen_cmd = [windows_escape(arg) for arg in popen_cmd]

        def _cmd_quote(arg: str) -> str:
            if not arg:
                return '""'
            arg = arg.replace("%", "%%")
            arg = arg.replace("^", "^^")
            if any(ch in arg for ch in '&|<>()^" \t'):
                escaped = arg.replace('"', '"^""')
                return f'"{escaped}"'
            return arg

        cmdline = " ".join(_cmd_quote(arg) for arg in popen_cmd)
        comspec = env.get("COMSPEC", "cmd.exe")
        return f'"{comspec}" /d /s /c "{cmdline}"'
    return popen_cmd


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


def _normalize_workspace(path_value) -> Path:
    return Path(path_value).expanduser().resolve()


def build_claude_cmd(args) -> tuple[List[str], str]:
    """Build `claude -p ...` argv from parsed run args."""
    workspace = str(_normalize_workspace(args.cd))
    session_id = args.SESSION_ID or str(uuid.uuid4())

    cmd = ["claude", "-p", "--add-dir", workspace]

    if args.model:
        cmd.extend(["--model", args.model])
    if args.permission_mode:
        cmd.extend(["--permission-mode", args.permission_mode])
    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    if args.SESSION_ID:
        cmd.extend(["--resume", args.SESSION_ID])
    else:
        cmd.extend(["--session-id", session_id])

    cmd.append(args.PROMPT)
    return cmd, session_id


def _coerce_stream_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def run_passthrough(subcommand: str, extra: List[str], timeout: float = 120.0) -> None:
    """Thin passthrough to `claude <subcommand> ...` for management flows."""
    env = os.environ.copy()
    _augment_path_env(env)
    cmd = ["claude", subcommand] + extra
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
        emit(
            {
                "success": cp.returncode == 0,
                "output": cp.stdout or "",
                "error": cp.stderr or "",
                "returncode": cp.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        emit(
            {
                "success": False,
                "output": "",
                "error": f"claude {subcommand} timed out",
                "returncode": -1,
            }
        )
    except FileNotFoundError:
        emit(
            {
                "success": False,
                "output": "",
                "error": "claude binary not found in PATH",
                "returncode": 127,
            }
        )


def cmd_run(args) -> None:
    workspace = Path(args.cd).expanduser()
    if not workspace.exists():
        emit(
            {
                "success": False,
                "error": f"The workspace root directory `{workspace.resolve(strict=False)}` does not exist. Please check the path and try again.",
            }
        )
        return
    if not workspace.is_dir():
        emit(
            {
                "success": False,
                "error": f"The workspace root `{workspace.resolve()}` is not a directory.",
            }
        )
        return

    workspace = workspace.resolve()
    cmd, session_id = build_claude_cmd(args)
    env = os.environ.copy()
    _augment_path_env(env)
    popen_cmd = _prepare_popen_cmd(cmd, env)

    try:
        cp = subprocess.run(
            popen_cmd,
            shell=False,
            cwd=str(workspace),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "success": False,
            "error": f"claude timed out after {args.timeout}s",
        }
        stderr = _coerce_stream_text(getattr(exc, "stderr", None)).strip()
        if stderr:
            result["stderr"] = stderr
        emit(result)
        return
    except FileNotFoundError:
        emit({"success": False, "error": "claude binary not found in PATH"})
        return

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    if cp.returncode == 0 and stdout:
        result = {
            "success": True,
            "SESSION_ID": session_id,
            "agent_messages": stdout,
        }
        if stderr:
            result["stderr"] = stderr
        emit(result)
        return

    if cp.returncode != 0:
        error = stderr or stdout or f"claude exited with returncode {cp.returncode}"
    else:
        error = "Claude returned no assistant text."
    result = {"success": False, "error": error}
    if stderr:
        result["stderr"] = stderr
    emit(result)


def main() -> None:
    configure_windows_stdio()

    if len(sys.argv) > 1 and sys.argv[1] in ("mcp", "plugin"):
        run_passthrough(sys.argv[1], sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="Claude Bridge")
    parser.add_argument("--PROMPT", required=True, help="Instruction for the task to send to Claude Code.")
    parser.add_argument("--cd", required=True, type=Path, help="Workspace root for Claude Code (cwd + --add-dir).")
    parser.add_argument("--SESSION_ID", default="", help="Resume a conversation by session UUID.")
    parser.add_argument("--model", default="", help="Claude model override. Omit to inherit the configured default.")
    parser.add_argument(
        "--permission-mode",
        default="",
        choices=[""] + PERMISSION_MODES,
        help="Claude permission mode override. Omit to preserve the configured default.",
    )
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Bypass Claude permission checks. Use only when the caller explicitly requests it.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Hard timeout in seconds for the delegated Claude print-mode call.",
    )

    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("mcp", help="Thin passthrough to `claude mcp`.")
    sub.add_parser("plugin", help="Thin passthrough to `claude plugin`.")

    args = parser.parse_args()
    cmd_run(args)


if __name__ == "__main__":
    main()
