"""Regression tests for agy_bridge.py final-message extraction.

Run: python scripts/test_agy_bridge.py
Covers the two misjudgment modes seen in session 7f6edd35:
  A. deliverable split across steps, last one a short closing -> must join all
  B. resume run ending with a tool receipt ('WROTE 17253') -> short-answer note
Plus: resume with no new f1 must NOT fall back to the previous run's answer,
and the PROMPT sent to agy must carry OUTPUT_PROTOCOL.
"""

import sqlite3
import sys
import tempfile
import types
from pathlib import Path

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
    assert bridge.max_agent_step_idx(db) == 51
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
    snapshot = bridge.max_agent_step_idx(db)
    answer, _, _ = bridge.extract_answer(db, after_idx=snapshot)
    assert answer == "", "stale answer from previous run leaked into this run"
    print("PASS test_resume_no_fallback_to_old_answer")


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
    test_prompt_carries_output_protocol()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
