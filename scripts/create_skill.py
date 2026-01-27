#!/usr/bin/env python3
"""Create a new skill from template"""
import json
import re
import sys
from pathlib import Path

SKILLS_DIR = Path("skills")
MARKETPLACE_JSON = Path(".claude-plugin/marketplace.json")

SKILL_TEMPLATE = '''---
name: {name}
description: |
  {description}
---

# {title}

## Usage

[Describe how to use this skill]

## Examples

- Example 1
- Example 2
'''

def validate_name(name: str) -> bool:
    """Validate skill name: lowercase, numbers, hyphens, 1-64 chars"""
    pattern = r'^[a-z][a-z0-9-]{{0,62}}[a-z0-9]$|^[a-z]$'
    if not re.match(pattern, name):
        return False
    if '--' in name:
        return False
    return True

def create_skill(name: str, description: str = "A new skill"):
    if not validate_name(name):
        print(f"Error: Invalid skill name '{name}'", file=sys.stderr)
        print("Rules: lowercase, numbers, hyphens, 1-64 chars, no consecutive hyphens", file=sys.stderr)
        sys.exit(1)

    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        print(f"Error: Skill '{name}' already exists", file=sys.stderr)
        sys.exit(1)

    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        SKILL_TEMPLATE.format(
            name=name,
            description=description,
            title=name.replace('-', ' ').title()
        ),
        encoding='utf-8'
    )

    with open(MARKETPLACE_JSON, 'r', encoding='utf-8') as f:
        marketplace = json.load(f)

    plugins = marketplace.setdefault("plugins", [])
    if not any(p.get("name") == name for p in plugins):
        plugins.append({
            "name": name,
            "description": description,
            "source": f"./skills/{name}",
            "strict": False,
            "skills": ["./"]
        })

    with open(MARKETPLACE_JSON, "w", encoding='utf-8') as f:
        json.dump(marketplace, f, ensure_ascii=False, indent=2)

    print(f"Created skill: {skill_dir}")
    print(f"Updated: {MARKETPLACE_JSON}")
    print(f"Next: Edit {skill_dir}/SKILL.md")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_skill.py <name> [description]", file=sys.stderr)
        sys.exit(1)
    name = sys.argv[1]
    desc = sys.argv[2] if len(sys.argv) > 2 else "A new skill"
    create_skill(name, desc)
