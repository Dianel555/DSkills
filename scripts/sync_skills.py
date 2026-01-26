#!/usr/bin/env python3
"""Sync skills from SSoT (skills/) to legacy directory (.claude/skills/)"""
import shutil
import sys
from pathlib import Path

SSOT_DIR = Path("skills")
LEGACY_DIR = Path(".claude/skills")

def sync():
    """Sync skills from skills/ to .claude/skills/"""
    if not SSOT_DIR.exists():
        print(f"Error: {SSOT_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    if LEGACY_DIR.exists():
        shutil.rmtree(LEGACY_DIR)
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)

    (LEGACY_DIR / "README.txt").write_text(
        "AUTO-GENERATED: DO NOT EDIT\n"
        "This directory is auto-synced from /skills\n"
        "Edit files in /skills instead.\n",
        encoding='utf-8'
    )

    synced_count = 0
    for skill_dir in SSOT_DIR.iterdir():
        if skill_dir.is_dir():
            shutil.copytree(skill_dir, LEGACY_DIR / skill_dir.name)
            synced_count += 1
            print(f"Synced: {skill_dir.name}")

    print(f"\nTotal: {synced_count} skill(s) synced from skills/ → .claude/skills/")

if __name__ == "__main__":
    sync()
