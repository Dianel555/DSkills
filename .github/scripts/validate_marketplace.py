"""Validate .claude-plugin/marketplace.json for CI.

Checks: JSON parses, every plugin has a source dir reachable from the repo
root, every skill path contains a SKILL.md, and every skill dir on disk is
registered. Exits nonzero on failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SKILLS_DIR = ROOT / "skills"


def main() -> int:
    try:
        data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"marketplace.json invalid: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        print("marketplace.json: 'plugins' must be a non-empty list", file=sys.stderr)
        return 1

    seen: set[str] = set()
    declared: set[Path] = set()

    for plugin in plugins:
        name = plugin.get("name", "<unnamed>")
        if name in seen:
            failures.append(f"plugin '{name}': duplicate name")
        seen.add(name)

        if not plugin.get("description", "").strip():
            failures.append(f"plugin '{name}': 'description' must be non-empty")

        source = plugin.get("source", "")
        if not source.startswith("./skills/"):
            failures.append(f"plugin '{name}': source '{source}' must start with './skills/'")
            continue
        source_dir = (ROOT / source).resolve()
        if not source_dir.is_dir():
            failures.append(f"plugin '{name}': source '{source}' does not exist")
            continue

        skills = plugin.get("skills", [])
        if not isinstance(skills, list) or not skills:
            failures.append(f"plugin '{name}': 'skills' must be a non-empty list")
            continue
        for skill in skills:
            skill_dir = (source_dir / skill).resolve()
            if not (skill_dir / "SKILL.md").is_file():
                failures.append(f"plugin '{name}': missing SKILL.md at '{source}/{skill}'")
            declared.add(skill_dir)

    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if (entry / "SKILL.md").is_file() and entry.resolve() not in declared:
            failures.append(f"skill '{entry.name}': has SKILL.md but is not registered in marketplace.json")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"marketplace.json OK: {len(plugins)} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
