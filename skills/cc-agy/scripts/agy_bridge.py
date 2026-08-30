"""
Antigravity (agy) Bridge for Claude Agent Skills.
Wraps the Google Antigravity CLI (`agy`) to provide a JSON-based interface.

agy `--print` writes nothing to stdout; the assistant reply is persisted in a
SQLite conversation DB at ~/.gemini/antigravity-cli/conversations/<UUID>.db,
inside the last step_type=15 row's step_payload protobuf (field f20 -> f1).
When a run fails upstream, agy writes no reply text and instead records the
executor error in a step_type=17 row (f24 -> f3: f1 user-facing line, f2
status detail).
This bridge runs agy, discovers the conversation DB, extracts the reply, and
returns JSON isomorphic to gemini_bridge.py.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

CONVERSATIONS_DIR = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
SETTINGS_FILE = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

AGY_BIN_CANDIDATES = [
    "agy",
    str(Path.home() / "AppData/Local/agy/bin/agy.exe"),
    str(Path.home() / "AppData/Local/agy/bin/agy"),
    str(Path.home() / ".local/bin/agy"),
    "/opt/antigravity/bin/agy",
    "/usr/local/bin/agy",
]

MODEL_ALIASES = {
    "flash-low": "Gemini 3.5 Flash (Low)",
    "flash-medium": "Gemini 3.5 Flash (Medium)",
    "flash-med": "Gemini 3.5 Flash (Medium)",
    "flash": "Gemini 3.5 Flash (High)",
    "flash-high": "Gemini 3.5 Flash (High)",
    "pro-low": "Gemini 3.1 Pro (Low)",
    "pro": "Gemini 3.1 Pro (High)",
    "pro-high": "Gemini 3.1 Pro (High)",
    "sonnet": "Claude Sonnet 4.6 (Thinking)",
    "claude-sonnet": "Claude Sonnet 4.6 (Thinking)",
    "opus": "Claude Opus 4.6 (Thinking)",
    "claude-opus": "Claude Opus 4.6 (Thinking)",
    "gpt-oss": "GPT-OSS 120B (Medium)",
    "gpt-oss-120b": "GPT-OSS 120B (Medium)",
}
CANONICAL_MODELS = set(MODEL_ALIASES.values())

INSTALL_HINT = "install with: curl -fsSL https://antigravity.google/cli/install.sh | bash"

OUTPUT_PROTOCOL = (
    "\n\nOUTPUT PROTOCOL: The complete deliverable (full code, analysis, or "
    "report) MUST appear in your final text reply. Tool receipts, status "
    "messages like 'WROTE <n>', and brief acknowledgements alone are NOT "
    "valid final answers."
)


# --- protobuf parsing (verified against agy v1.0.10 conversation DBs) ---

def read_varint(b: bytes, i: int) -> Tuple[int, int]:
    shift = val = 0
    while i < len(b):
        c = b[i]
        i += 1
        val |= (c & 0x7F) << shift
        if not (c & 0x80):
            break
        shift += 7
    return val, i


def scan_protobuf(b: bytes) -> List[Tuple[int, int, object]]:
    i = 0
    out = []
    while i < len(b):
        try:
            tag, i = read_varint(b, i)
        except IndexError:
            break
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = read_varint(b, i)
            out.append((fn, 0, v))
        elif wt == 2:
            ln, i = read_varint(b, i)
            out.append((fn, 2, b[i:i + ln]))
            i += ln
        elif wt == 1:
            out.append((fn, 1, b[i:i + 8]))
            i += 8
        elif wt == 5:
            out.append((fn, 5, b[i:i + 4]))
            i += 4
        else:
            break
    return out


def max_step_idx(db_path: Path) -> int:
    """Return the latest idx of any step in a DB, or -1 when absent.

    Spans every step type, not just 15: a failed run's type=17 error row
    lands after its last type=15 step, so a type=15-only boundary would
    re-attribute that stale error to the next run on resume.
    """
    if not db_path.is_file():
        return -1
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute("SELECT MAX(idx) FROM steps").fetchone()
    finally:
        con.close()
    return row[0] if row and row[0] is not None else -1


def extract_answer(db_path: Path, include_reasoning: bool = False,
                   after_idx: int = -1
                   ) -> Tuple[str, str, List[dict]]:
    """Return (answer, reasoning, all_messages) from an agy conversation DB.

    Only step_type=15 rows with idx > after_idx belong to this run; the
    assistant's reply is ALL non-empty f20.f1 fragments of the run joined
    with blank lines (agy may split a deliverable across several steps and
    end with a short closing line; last-wins would drop the deliverable).
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    rows = cur.execute(
        "SELECT idx, step_payload FROM steps "
        "WHERE step_type=15 AND idx > ? ORDER BY idx",
        (after_idx,),
    ).fetchall()
    con.close()

    answers = []
    reasoning = ""
    all_msgs = []
    for idx, blob in rows:
        if not blob:
            continue
        top = scan_protobuf(blob)
        f20 = next((v for fn, wt, v in top if fn == 20 and wt == 2), None)
        if f20 is None:
            continue
        f1 = f3 = ""
        for fn, wt, v in scan_protobuf(f20):
            if wt == 2 and fn in (1, 3, 8):
                try:
                    s = v.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if fn in (1, 8) and s:
                    f1 = s  # f8 is a duplicate of f1
                elif fn == 3:
                    f3 = s
        if f1:
            answers.append(f1)
        if f3:
            reasoning = f3
        all_msgs.append({"idx": idx, "answer": f1, "reasoning": f3})
    return "\n\n".join(answers), reasoning, all_msgs


def extract_run_error(db_path: Path, after_idx: int = -1) -> str:
    """Return agy's own upstream failure for this run, or "" when absent.

    step_type=17 is agy's error channel: f24.f3 holds f1 (user-facing line),
    f2 (status detail, e.g. "FAILED_PRECONDITION (code 400): ...") and f9 (a
    duplicate of f2). Uses the same idx window as extract_answer so a resumed
    session cannot resurface the previous run's error.

    An error row that cannot be decoded still returns a non-empty string: the
    row's mere existence proves the run failed upstream, and reporting "" here
    would send the caller to extract_answer() over an error-channel change.
    """
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT step_payload FROM steps "
            "WHERE step_type=17 AND idx > ? ORDER BY idx",
            (after_idx,),
        ).fetchall()
    finally:
        con.close()

    for (blob,) in rows:
        if not blob:
            continue
        f24 = next((v for fn, wt, v in scan_protobuf(blob)
                    if fn == 24 and wt == 2), None)
        if f24 is None:
            continue
        f3 = next((v for fn, wt, v in scan_protobuf(f24)
                   if fn == 3 and wt == 2), None)
        if f3 is None:
            continue
        parts = {}
        for fn, wt, v in scan_protobuf(f3):
            if wt == 2 and fn in (1, 2, 9):
                try:
                    parts[fn] = v.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        detail = parts.get(2) or parts.get(9) or parts.get(1)
        if detail:
            return detail
    if rows:
        return ("agy recorded an error step whose detail could not be decoded "
                "(fix: extract_run_error())")
    return ""


# --- agy binary resolution ---

def find_agy() -> Optional[str]:
    for candidate in AGY_BIN_CANDIDATES:
        resolved = shutil.which(candidate) if candidate == "agy" else None
        if resolved:
            return resolved
        p = Path(candidate)
        if p.is_file():
            return str(p)
    return None


def auth_status() -> str:
    if os.environ.get("ANTIGRAVITY_API_KEY"):
        return "api-key"
    if (Path.home() / ".config/antigravity").is_dir() or \
            (Path.home() / ".gemini/antigravity-cli").is_dir():
        return "oauth"
    return "missing"


def resolve_model_alias(user_input: str) -> str:
    if user_input in CANONICAL_MODELS:
        return user_input
    return MODEL_ALIASES.get(user_input.lower(), user_input)


# --- conversation DB discovery ---

def snapshot_db_uuids() -> set:
    if not CONVERSATIONS_DIR.is_dir():
        return set()
    return {p.stem for p in CONVERSATIONS_DIR.glob("*.db")}


def new_db_uuid(before: set, after: set) -> Optional[str]:
    new_uuids = after - before
    if not new_uuids:
        return None
    if len(new_uuids) == 1:
        return next(iter(new_uuids))
    # >1 new DB: pick newest by mtime, log warning via stderr
    candidates = [CONVERSATIONS_DIR / f"{u}.db" for u in new_uuids]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"[agy_bridge] warning: {len(new_uuids)} new conversation DBs detected; "
          f"picking newest: {candidates[0].stem}", file=sys.stderr)
    return candidates[0].stem


# --- model / timeout helpers ---

def current_default_model() -> str:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("model", "")
    except (OSError, json.JSONDecodeError):
        return ""


def parse_timeout_to_seconds(s: str) -> int:
    """Parse agy-style durations (e.g. '5m', '30s', '2h', '90'). Default 5m."""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d+)\s*(s|m|h)?", s, re.IGNORECASE)
    if not m:
        return 300
    n = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    return n * {"s": 1, "m": 60, "h": 3600}[unit]


# --- core run ---

def short_answer_note(answer: str, all_msgs: List[dict]) -> Optional[str]:
    """Warn when the reply is very short but the run had thinking-only steps."""
    if len(answer) < 60 and any(m["reasoning"] and not m["answer"] for m in all_msgs):
        return ("This run produced a very short text reply and contained thinking-only "
                "steps; the full deliverable may be in tool outputs rather than the reply.")
    return None


def run_agy_print(cmd: List[str], cwd: str, timeout_s: int
                  ) -> Tuple[int, str, str, bool]:
    try:
        cp = subprocess.run(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
        )
        return (cp.returncode,
                cp.stdout.decode("utf-8", "replace"),
                cp.stderr.decode("utf-8", "replace"),
                False)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if e.stdout else ""
        err = (e.stderr or b"").decode("utf-8", "replace") if e.stderr else ""
        return (-1, out, err, True)
    except FileNotFoundError:
        return (127, "", "agy binary not found", False)


def build_agy_cmd(agy_path: str, args) -> List[str]:
    cmd = [
        agy_path,
        "--print",
        args.PROMPT + OUTPUT_PROTOCOL,
        "--print-timeout",
        args.print_timeout,
        "--add-dir",
        str(args.cd),
    ]
    if not args.no_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if args.model:
        cmd += ["--model", resolve_model_alias(args.model)]
    if args.SESSION_ID:
        cmd += ["--conversation", args.SESSION_ID]
    if args.sandbox:
        cmd.append("--sandbox")
    return cmd


def configure_windows_stdio() -> None:
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


# --- subcommands ---

def cmd_check() -> None:
    path = find_agy()
    if not path:
        emit({"installed": False, "path": "", "version": "", "auth": "unknown",
              "model": current_default_model(),
              "conversations_dir": str(CONVERSATIONS_DIR),
              "error": f"agy binary not found; {INSTALL_HINT}"})
        return
    try:
        version = subprocess.run(
            [path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=15, text=True).stdout.strip().splitlines()[0]
    except (subprocess.TimeoutExpired, IndexError, OSError):
        version = "unknown"
    emit({"installed": True, "path": path, "version": version,
          "auth": auth_status(), "model": current_default_model(),
          "conversations_dir": str(CONVERSATIONS_DIR), "error": ""})


def cmd_plugin(extra: List[str]) -> None:
    path = find_agy()
    if not path:
        emit({"success": False, "output": "", "error": f"agy not installed; {INSTALL_HINT}"})
        return
    cmd = [path, "plugin"] + extra
    try:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=120, text=True)
        emit({"success": cp.returncode == 0, "output": cp.stdout,
              "error": cp.stderr})
    except subprocess.TimeoutExpired:
        emit({"success": False, "output": "", "error": "agy plugin timed out"})


# --- main run path ---

def cmd_run(args) -> None:
    cd: Path = args.cd
    if not cd.exists():
        emit({"success": False,
              "error": f"The workspace root directory `{cd.absolute()}` does not exist. "
                       f"Please check the path and try again."})
        return

    agy_path = find_agy()
    if not agy_path:
        emit({"success": False,
              "error": f"agy is not installed; {INSTALL_HINT}"})
        return
    if auth_status() == "missing":
        emit({"success": False,
              "error": "agy is not authenticated. Run `agy` once interactively, "
                       "or export ANTIGRAVITY_API_KEY."})
        return

    before = snapshot_db_uuids()
    after_idx = max_step_idx(
        CONVERSATIONS_DIR / f"{args.SESSION_ID}.db"
    ) if args.SESSION_ID else -1
    cmd = build_agy_cmd(agy_path, args)
    outer_timeout = parse_timeout_to_seconds(args.print_timeout) + 60
    rc, out, err, timed_out = run_agy_print(cmd, cwd=str(cd.absolute()),
                                            timeout_s=outer_timeout)

    if args.SESSION_ID:
        target_uuid = args.SESSION_ID
    else:
        target_uuid = new_db_uuid(before, snapshot_db_uuids())

    if target_uuid is None:
        if timed_out:
            emit({"success": False,
                  "error": f"agy timed out after {outer_timeout}s with no conversation DB "
                           f"created. stderr: {err}"})
        else:
            emit({"success": False,
                  "error": f"agy exited (rc={rc}) but created no conversation DB. "
                           f"stderr: {err}"})
        return

    db_path = CONVERSATIONS_DIR / f"{target_uuid}.db"
    if not db_path.exists():
        emit({"success": False, "SESSION_ID": target_uuid,
              "error": f"conversation DB not found: {db_path}"})
        return

    answer, reasoning, all_msgs = extract_answer(
        db_path, include_reasoning=args.return_all_messages, after_idx=after_idx)
    note = short_answer_note(answer, all_msgs)

    # Persist every extracted step as JSONL so partial results survive a
    # crash/timeout and the raw run can be audited later (mirrors the
    # codex_bridge stream_file pattern).
    sfd, stream_path = tempfile.mkstemp(prefix="agy_steps_", suffix=".jsonl")
    with os.fdopen(sfd, "w", encoding="utf-8") as fp:
        for m in all_msgs:
            fp.write(json.dumps({"SESSION_ID": target_uuid, **m},
                                ensure_ascii=False) + "\n")

    result = {"success": bool(answer), "SESSION_ID": target_uuid}
    if answer:
        result["agent_messages"] = answer
        if args.return_all_messages:
            result["all_messages"] = all_msgs
            result["reasoning"] = reasoning
    else:
        upstream = extract_run_error(db_path, after_idx=after_idx)
        if upstream:
            result["error"] = (
                f"agy produced no reply because the run failed upstream (rc={rc}): "
                f"{upstream}"
            )
        elif timed_out:
            result["error"] = (
                f"agy timed out after {outer_timeout}s before producing a reply in DB "
                f"{target_uuid}. stderr: {err}"
            )
        else:
            result["error"] = (
                f"agy exited rc={rc} and DB {target_uuid} contained no extractable assistant "
                f"reply after idx {after_idx} (0 new type=15 steps with non-empty f1), and no "
                f"type=17 error row explains it. This may indicate agy performed only tool "
                f"calls, or that the protobuf schema changed (fix: extract_answer()). "
                f"stderr: {err}"
            )
    if note:
        result["note"] = note
    result["steps_file"] = stream_path
    if err.strip():
        result["stderr"] = err.strip()
    emit(result)


def main() -> None:
    configure_windows_stdio()
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity (agy) Bridge")
    parser.add_argument("--PROMPT", help="Instruction for the task to send to agy.")
    parser.add_argument("--cd", type=Path, help="Workspace root for agy (cwd + --add-dir).")
    parser.add_argument("--model", default="",
                        help="Model alias (flash-low/medium/high, pro-low/high, sonnet, "
                             "opus, gpt-oss) or canonical string. Omit to use settings default.")
    parser.add_argument("--SESSION_ID", default="",
                        help="Resume a conversation by UUID. Maps to agy --conversation.")
    parser.add_argument("--sandbox", action="store_true", help="Run in agy sandbox mode.")
    parser.add_argument("--no-skip-permissions", action="store_true",
                        help="Do NOT pass --dangerously-skip-permissions. WARNING: with "
                             "default toolPermission=request-review, print mode WILL HANG.")
    parser.add_argument("--print-timeout", default="10m",
                        help="agy --print-timeout (e.g. 5m, 10m). Default 10m.")
    parser.add_argument("--return-all-messages", action="store_true",
                        help="Include reasoning + all type=15 steps in the response.")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("check", help="Probe agy install / version / auth / current model.")
    sub.add_parser("plugin", help="Thin passthrough to `agy plugin`.")

    args = parser.parse_args()

    if args.subcommand == "check":
        cmd_check()
        return
    if args.subcommand == "plugin":
        # re-parse to capture plugin's own args verbatim
        rest = sys.argv[sys.argv.index("plugin") + 1:]
        cmd_plugin(rest)
        return

    if not args.PROMPT or not args.cd:
        parser.error("the following arguments are required: --PROMPT, --cd")
    cmd_run(args)


if __name__ == "__main__":
    main()
