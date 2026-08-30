"""Regression tests for agy_bridge.py final-message extraction.

Run: python scripts/test_agy_bridge.py
Covers the two misjudgment modes seen in session 7f6edd35:
  A. deliverable split across steps, last one a short closing -> must join all
  B. resume run ending with a tool receipt ('WROTE 17253') -> short-answer note
Plus: resume with no new f1 must NOT fall back to the previous run's answer,
and the PROMPT sent to agy must carry OUTPUT_PROTOCOL.
Also covers session cc532d4c: an upstream failure (type=17 row) must be
reported instead of the protobuf-schema guess, and must not leak across runs.
"""

import sqlite3
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import agy_bridge as bridge


def write_varint(v: int) -> bytes:
    out = b""
    while True:
        b = v & 0x7F
        v >>= 7
        out += bytes([b | 0x80]) if v else bytes([b])
        if not v:
            return out


def field(fn: int, payload: bytes) -> bytes:
    return write_varint(fn << 3 | 2) + write_varint(len(payload)) + payload


def step_payload(text: str, reasoning: str = "") -> bytes:
    inner = field(1, text.encode("utf-8")) if text else b""
    if reasoning:
        inner += field(3, reasoning.encode("utf-8"))
    return field(20, inner)


def error_payload(line: str, detail: str = "") -> bytes:
    """A step_type=17 payload: f24 -> f3 -> {f1: line, f2: detail}."""
    f3 = field(1, line.encode("utf-8"))
    if detail:
        f3 += field(2, detail.encode("utf-8"))
    return field(24, field(3, f3))


def make_db(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    db = tmp / "conv.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE `steps` (`idx` integer,`step_type` integer NOT NULL DEFAULT 0,"
        "`status` integer NOT NULL DEFAULT 0,`has_subtrajectory` numeric NOT NULL DEFAULT false,"
        "`metadata` blob,`error_details` blob,`permissions` blob,`task_details` blob,"
        "`render_info` blob,`step_payload` blob,`step_format` integer NOT NULL DEFAULT 0,"
        "PRIMARY KEY (`idx`))"
    )
    return db, con


CSS = ".zg-panel { display: flex; flex-direction: column; width: 100%; " * 5 + "}"
CLOSING = "好的，上述 CSS 代码已经可以满足你所有的环境约束、功能要求并复原截图中反映的所有 UI 细节。\n\n如有其他地方需要细调，随时告诉我！"


def test_case_a_join_all_fragments(tmp: Path):
    db, con = make_db(tmp / "a")
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (39, 15, ?)",
                (sqlite3.Binary(step_payload(CSS)),))
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (42, 15, ?)",
                (sqlite3.Binary(step_payload(CLOSING)),))
    con.commit()
    con.close()
    answer, _, _ = bridge.extract_answer(db)
    assert CSS in answer and CLOSING in answer, "deliverable fragment was dropped"
    assert answer.index(CSS) < answer.index(CLOSING), "fragments out of order"
    print("PASS test_case_a_join_all_fragments")


def test_case_b_incremental_snapshot(tmp: Path):
    db, con = make_db(tmp / "b")
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (42, 15, ?)",
                (sqlite3.Binary(step_payload(CLOSING)),))
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (50, 15, ?)",
                (sqlite3.Binary(step_payload("", reasoning="thinking about file write")),))
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (51, 15, ?)",
                (sqlite3.Binary(step_payload("WROTE 17253")),))
    con.commit()
    con.close()
    assert bridge.max_step_idx(db) == 51
    answer, reasoning, all_msgs = bridge.extract_answer(db, after_idx=42)
    assert answer == "WROTE 17253", "resume leaked pre-snapshot content"
    assert bridge.short_answer_note(answer, all_msgs) is not None, "missing note"
    print("PASS test_case_b_incremental_snapshot")


def test_resume_no_fallback_to_old_answer(tmp: Path):
    db, con = make_db(tmp / "c")
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (39, 15, ?)",
                (sqlite3.Binary(step_payload(CSS)),))
    con.commit()
    con.close()
    snapshot = bridge.max_step_idx(db)
    answer, _, _ = bridge.extract_answer(db, after_idx=snapshot)
    assert answer == "", "stale answer from previous run leaked into this run"
    print("PASS test_resume_no_fallback_to_old_answer")


GEO_ERR = "FAILED_PRECONDITION (code 400): User location is not supported for the API use."
TERMINATED = "Agent execution terminated due to error."


def run_failed_session(db: Path, new_error: str = "") -> dict:
    """Drive cmd_run over a stubbed agy that fails without producing a reply.

    Asserting on cmd_run's emitted JSON (not extract_run_error's return) is
    the point: the defect being guarded is WHAT GETS REPORTED, and the
    misleading schema hint only ever appears in cmd_run.
    """
    emitted = []

    def fake_run_agy_print(cmd, cwd, timeout_s):
        con = sqlite3.connect(str(db))
        nxt = con.execute("SELECT COALESCE(MAX(idx), -1) + 1 FROM steps").fetchone()[0]
        # a type=15 row whose f20 holds only a varint (f12) -> no reply text
        con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (?, 15, ?)",
                    (nxt, sqlite3.Binary(field(20, write_varint(12 << 3) + write_varint(18)))))
        if new_error:
            con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (?, 17, ?)",
                        (nxt + 1, sqlite3.Binary(error_payload(TERMINATED, new_error))))
        con.commit()
        con.close()
        return 1, "", f"Error: {TERMINATED}", False

    args = types.SimpleNamespace(
        PROMPT="probe", cd=db.parent, no_skip_permissions=False, model="",
        SESSION_ID=db.stem, sandbox=False, print_timeout="10m",
        return_all_messages=False,
    )
    with patch.multiple(bridge,
                        CONVERSATIONS_DIR=db.parent,
                        find_agy=lambda: "agy",
                        auth_status=lambda: "oauth",
                        run_agy_print=fake_run_agy_print,
                        emit=emitted.append):
        bridge.cmd_run(args)

    assert len(emitted) == 1, f"expected one emit, got {len(emitted)}"
    Path(emitted[0]["steps_file"]).unlink()
    return emitted[0]


def test_upstream_error_is_reported(tmp: Path):
    """Session cc532d4c: upstream rejected the run, type=15 row carries no f1.

    The real cause sits in the type=17 row; cmd_run must report it instead of
    blaming its own (correct) protobuf parsing.
    """
    db, con = make_db(tmp / "d")
    con.close()

    result = run_failed_session(db, new_error=GEO_ERR)
    assert result["success"] is False
    assert GEO_ERR in result["error"], f"upstream cause not reported: {result['error']!r}"
    assert "protobuf schema changed" not in result["error"], \
        "misleading schema hint survived alongside a known upstream cause"
    print("PASS test_upstream_error_is_reported")


def test_schema_hint_kept_when_no_error_row(tmp: Path):
    """With no type=17 row, the schema-drift hint is the only honest guess."""
    db, con = make_db(tmp / "f")
    con.close()

    result = run_failed_session(db)
    assert "protobuf schema changed" in result["error"], \
        "schema hint must survive when nothing explains the empty reply"
    print("PASS test_schema_hint_kept_when_no_error_row")


def test_resume_does_not_resurface_old_error(tmp: Path):
    """A previous run's type=17 row must not be attributed to a new run."""
    db, con = make_db(tmp / "e")
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (1, 15, ?)",
                (sqlite3.Binary(step_payload("old answer")),))
    con.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (2, 17, ?)",
                (sqlite3.Binary(error_payload(TERMINATED, GEO_ERR)),))
    con.commit()
    con.close()

    assert bridge.max_step_idx(db) == 2, \
        "boundary must span all step types, not only type=15"
    result = run_failed_session(db)
    assert GEO_ERR not in result["error"], \
        "resume resurfaced the previous run's error as this run's cause"
    print("PASS test_resume_does_not_resurface_old_error")


def test_prompt_carries_output_protocol():
    args = types.SimpleNamespace(
        PROMPT="write CSS", cd=Path("."), no_skip_permissions=False, model="",
        SESSION_ID="", sandbox=False, print_timeout="10m",
    )
    cmd = bridge.build_agy_cmd("agy", args)
    assert "OUTPUT PROTOCOL" in cmd[2], "OUTPUT_PROTOCOL missing from PROMPT"
    print("PASS test_prompt_carries_output_protocol")


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_case_a_join_all_fragments(tmp)
        test_case_b_incremental_snapshot(tmp)
        test_resume_no_fallback_to_old_answer(tmp)
        test_upstream_error_is_reported(tmp)
        test_schema_hint_kept_when_no_error_row(tmp)
        test_resume_does_not_resurface_old_error(tmp)
    test_prompt_carries_output_protocol()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
