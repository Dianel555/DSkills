#!/usr/bin/env python3
"""Sequential Think CLI - Standalone iterative thinking engine for complex problem-solving."""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ThoughtData:
    thought: str
    thought_number: int
    total_thoughts: int
    next_thought_needed: bool = True
    is_revision: bool = False
    revises_thought: Optional[int] = None
    branch_from_thought: Optional[int] = None
    branch_id: Optional[str] = None
    needs_more_thoughts: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Thought History Manager
# ============================================================================

class ThoughtHistoryManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._history: List[ThoughtData] = []
            cls._instance._branches: Dict[str, List[ThoughtData]] = {}
            cls._instance._history_file: Optional[Path] = None
        return cls._instance

    @property
    def history_file(self) -> Path:
        if self._history_file is None:
            config_dir = Path.home() / ".config" / "sequential-think"
            config_dir.mkdir(parents=True, exist_ok=True)
            self._history_file = config_dir / "thought_history.json"
        return self._history_file

    def _load_history(self) -> None:
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._history = [ThoughtData(**t) for t in data.get("history", [])]
                    self._branches = {
                        k: [ThoughtData(**t) for t in v]
                        for k, v in data.get("branches", {}).items()
                    }
            except (json.JSONDecodeError, IOError, TypeError):
                self._history = []
                self._branches = {}

    def _save_history(self) -> None:
        data = {
            "history": [asdict(t) for t in self._history],
            "branches": {k: [asdict(t) for t in v] for k, v in self._branches.items()}
        }
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_thought(self, thought: ThoughtData) -> Dict:
        self._load_history()

        # Auto-adjust total if thought_number exceeds it
        if thought.thought_number > thought.total_thoughts:
            thought.total_thoughts = thought.thought_number

        self._history.append(thought)

        # Track branches
        if thought.branch_from_thought and thought.branch_id:
            if thought.branch_id not in self._branches:
                self._branches[thought.branch_id] = []
            self._branches[thought.branch_id].append(thought)

        self._save_history()

        return {
            "thoughtNumber": thought.thought_number,
            "totalThoughts": thought.total_thoughts,
            "nextThoughtNeeded": thought.next_thought_needed,
            "branches": list(self._branches.keys()),
            "thoughtHistoryLength": len(self._history)
        }

    def get_history(self) -> Dict:
        self._load_history()
        return {
            "history": [asdict(t) for t in self._history],
            "branches": {k: [asdict(t) for t in v] for k, v in self._branches.items()},
            "totalThoughts": len(self._history)
        }

    def clear_history(self) -> Dict:
        self._history = []
        self._branches = {}
        if self.history_file.exists():
            self.history_file.unlink()
        return {"status": "cleared", "message": "Thought history cleared"}


manager = ThoughtHistoryManager()


# ============================================================================
# Formatters
# ============================================================================

def format_thought_text(thought: ThoughtData) -> str:
    prefix = ""
    context = ""

    if thought.is_revision:
        prefix = "🔄 Revision"
        context = f" (revising thought {thought.revises_thought})"
    elif thought.branch_from_thought:
        prefix = "🌿 Branch"
        context = f" (from thought {thought.branch_from_thought}, ID: {thought.branch_id})"
    else:
        prefix = "💭 Thought"

    header = f"{prefix} {thought.thought_number}/{thought.total_thoughts}{context}"
    border = "─" * max(len(header), min(len(thought.thought), 60)) + "────"

    return f"""
┌{border}┐
│ {header.ljust(len(border) - 2)} │
├{border}┤
│ {thought.thought[:len(border) - 2].ljust(len(border) - 2)} │
└{border}┘"""


def format_history_text(history: Dict) -> str:
    if not history["history"]:
        return "No thoughts recorded yet."

    lines = ["=" * 60, "THOUGHT HISTORY", "=" * 60, ""]

    for t in history["history"]:
        thought = ThoughtData(**t)
        lines.append(format_thought_text(thought))

    if history["branches"]:
        lines.extend(["", "-" * 60, "BRANCHES:", "-" * 60])
        for branch_id, thoughts in history["branches"].items():
            lines.append(f"\n[{branch_id}]")
            for t in thoughts:
                lines.append(f"  Thought {t['thought_number']}: {t['thought'][:50]}...")

    return "\n".join(lines)


# ============================================================================
# Commands
# ============================================================================

def cmd_think(args) -> None:
    thought = ThoughtData(
        thought=args.thought,
        thought_number=args.thought_number,
        total_thoughts=args.total_thoughts,
        next_thought_needed=not args.no_next,
        is_revision=args.is_revision,
        revises_thought=args.revises_thought,
        branch_from_thought=args.branch_from,
        branch_id=args.branch_id,
        needs_more_thoughts=args.needs_more
    )

    result = manager.add_thought(thought)

    # Print formatted thought to stderr for visibility
    if not args.quiet:
        print(format_thought_text(thought), file=sys.stderr)

    # Output JSON result
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_history(args) -> None:
    history = manager.get_history()

    if args.format == "json":
        print(json.dumps(history, ensure_ascii=False, indent=2))
    else:
        print(format_history_text(history))


def cmd_clear(args) -> None:
    result = manager.clear_history()
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="sequential_think_cli",
        description="Sequential Think CLI - Iterative thinking engine for complex problem-solving"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # think command
    p_think = subparsers.add_parser("think", help="Process a thought in the chain")
    p_think.add_argument("--thought", "-t", required=True, help="Current thinking step content")
    p_think.add_argument("--thought-number", "-n", type=int, required=True, help="Current position (1-based)")
    p_think.add_argument("--total-thoughts", "-T", type=int, required=True, help="Estimated total thoughts")
    p_think.add_argument("--no-next", action="store_true", help="Mark as final thought (no more needed)")
    p_think.add_argument("--is-revision", action="store_true", help="This thought revises previous thinking")
    p_think.add_argument("--revises-thought", type=int, help="Which thought number is being reconsidered")
    p_think.add_argument("--branch-from", type=int, help="Branching point thought number")
    p_think.add_argument("--branch-id", help="Identifier for current branch")
    p_think.add_argument("--needs-more", action="store_true", help="Signal more thoughts needed beyond estimate")
    p_think.add_argument("--quiet", "-q", action="store_true", help="Suppress formatted output to stderr")

    # history command
    p_history = subparsers.add_parser("history", help="View thought history")
    p_history.add_argument("--format", "-f", choices=["json", "text"], default="text", help="Output format")

    # clear command
    subparsers.add_parser("clear", help="Clear thought history")

    args = parser.parse_args()

    commands = {
        "think": cmd_think,
        "history": cmd_history,
        "clear": cmd_clear,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
