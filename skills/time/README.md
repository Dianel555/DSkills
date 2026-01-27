# Time Skill

Time and timezone utilities for AI coding assistants.

## Features

- Get current time in any IANA timezone
- Convert time between timezones
- Automatic DST detection
- Standalone CLI (no MCP dependency)

## Installation

### As Claude Code Skill
```bash
claude mcp add-from-claude-plugin https://github.com/Dianel555/DSkills
```

### Standalone CLI
```bash
pip install pytz  # Python < 3.9
# or use built-in zoneinfo for Python 3.9+
```

## Usage

### CLI Commands

```bash
# Get current time
python scripts/time_cli.py get --timezone "Asia/Shanghai"

# Convert time
python scripts/time_cli.py convert --time "16:30" --from "America/New_York" --to "Asia/Tokyo"

# List timezones
python scripts/time_cli.py list --filter "America"
```

### MCP Tools

If MCP server is configured:
- `mcp__time__get_current_time`
- `mcp__time__convert_time`

## License

MIT
