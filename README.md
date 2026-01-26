# DSkills

CLI tools skills for AI coding assistants (Claude Code, Codex, Gemini CLI).

## Skills

| Skill | Description |
|-------|-------------|
| [grok-search](skills/grok-search/) | Enhanced web search via Grok API |

## Installation

### Claude Code (Native)

```bash
/plugin marketplace add Dianel555/DSkills
```

Then browse and install via `/plugin`.

### agent-skills-cli

```bash
# List available skills
npx skills add Dianel555/DSkills --list

# Install specific skill
npx skills add Dianel555/DSkills -s grok-search
```

### Manual

```bash
git clone https://github.com/Dianel555/DSkills.git
cp -r DSkills/skills/grok-search ~/.claude/skills/
```

## Platform Support

| Platform | Skills Directory | Config |
|----------|------------------|--------|
| Claude Code | `~/.claude/skills/` | `.claude-plugin/marketplace.json` |
| Codex | `~/.codex/skills/` | Copy from `skills/` |
| Gemini CLI | `~/.gemini/skills/` | Copy from `skills/` |

### Codex Platform

```bash
# Clone repository
git clone https://github.com/Dianel555/DSkills.git

# Copy skills to Codex directory
cp -r DSkills/skills/grok-search ~/.codex/skills/

# Verify installation
codex --list-skills
```

### Gemini CLI Platform

```bash
# Clone repository
git clone https://github.com/Dianel555/DSkills.git

# Copy skills to Gemini directory
cp -r DSkills/skills/grok-search ~/.gemini/skills/

# Verify installation
gemini --list-skills
```

## Directory Structure

```
DSkills/
├── skills/                    # SSoT - All skills
│   └── grok-search/
│       ├── SKILL.md
│       ├── README.md
│       └── scripts/
├── .claude-plugin/
│   └── marketplace.json
└── .claude/skills/            # Auto-synced (deprecated)
```

## Adding New Skills

1. Create `skills/<skill-name>/SKILL.md`
2. Update `.claude-plugin/marketplace.json`
3. Run `python scripts/sync_skills.py`

## License

MIT
