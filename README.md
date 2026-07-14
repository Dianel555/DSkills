# DSkills

CLI tools skills for AI coding assistants (Claude Code, Codex, Antigravity CLI).

## Skills

| Skill | Description |
|-------|-------------|
| [grok-search](skills/grok-search/) | Enhanced web search via Grok API |
| [sequential-think](skills/sequential-think/) | Iterative thinking engine for complex problem-solving |
| [exa](skills/exa/) | High-precision semantic search via Exa API |
| [time](skills/time/) | Time and timezone utilities |
| [Serena](skills/serena/) | Semantic code understanding with IDE-like symbol operations |
| [ontoly](skills/ontoly/) | Deterministic Software Graph analysis via Ontoly CLI and MCP |
| [ace-tool](skills/ace-tool/) | Semantic code search and AI-powered prompt enhancement |
| [agent-wiki](skills/agent-wiki/) | Incremental LLM-friendly wiki generator for Obsidian note vaults |
| [capability-evolver](skills/capability-evolver/) | Self-evolution engine for AI agents (EvoMap A2A, local Proxy mailbox) |
| [cc-agy](skills/cc-agy/) | Delegate coding/research tasks to Google Antigravity CLI (agy) for external-model execution |
| [cc-codex](skills/cc-codex/) | Delegate coding tasks to Codex CLI for prototyping, debugging, and code review (multi-turn SESSION_ID, sandbox=read-only) |
| [github-trending-analyzer](skills/github-trending-analyzer/) | Crawl GitHub trending repos, analyze with LLM for Chinese insights, categorize by themes, diff against history, generate Markdown reports |
| [context7](skills/context7/) | Fetch up-to-date library/framework/API docs from Context7 (bypass training cutoff); two-skill split (main + forked fetcher) cuts token use on API calls |

### Python Skill Dependencies

Some skills provide Python CLIs. Install skill-specific dependencies before use:

```bash
pip install PyYAML
```

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
| Antigravity CLI (agy) | `~/.gemini/antigravity-cli/builtin/skills/` | `agy plugin import\|install` |

### Codex Platform

```bash
# Clone repository
git clone https://github.com/Dianel555/DSkills.git

# Copy skills to Codex directory
cp -r DSkills/skills/grok-search ~/.codex/skills/

# Verify installation
codex --list-skills
```

### Antigravity CLI (agy) Platform

```bash
# Clone repository
git clone https://github.com/Dianel555/DSkills.git

# Import a skill as an agy plugin (supports gemini/claude plugin format)
agy plugin import DSkills/skills/grok-search

# Or install from a marketplace (plugin@marketplace form)
agy plugin install grok-search@Dianel555/DSkills

# List imported plugins and verify
agy plugin list
```

Note: agy auto-loads MCP servers from `~/.gemini/antigravity/mcp_config.json` and the memory doc at `~/.gemini/GEMINI.md`. Use the [cc-agy](skills/cc-agy/) skill to drive agy from Claude Code.

## Directory Structure

```
DSkills/
├── README.md
├── skills/                            # All skills
│   ├── grok-search/
│   ├── sequential-think/
│   ├── exa/
│   ├── time/
│   ├── serena/
│   ├── ontoly/
│   ├── ace-tool/
│   ├── agent-wiki/
│   ├── capability-evolver/
│   ├── cc-agy/
│   ├── cc-codex/
│   ├── github-trending-analyzer/
│   └── context7/
└── .claude-plugin/
    └── marketplace.json               # Metadata
```

## Adding New Skills

1. Create `skills/<skill-name>/SKILL.md`
2. Update `.claude-plugin/marketplace.json`

## License

MIT
