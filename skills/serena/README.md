# Serena CLI

Semantic code understanding with IDE-like symbol operations and Web Dashboard. MCP-independent CLI for code navigation, editing, and project memory.

## Features

- **Web Dashboard**: Real-time configuration monitoring and management
- **Symbol Operations**: Find, rename, replace, insert symbols with language-aware precision
- **Cross-file References**: Track symbol usages across entire codebase
- **Project Memory**: Persist and retrieve project knowledge across sessions
- **Extended Tools**: Shell commands, config file operations
- **Auto Project Registration**: Automatically registers projects in global Serena config

## Installation

```bash
pip install serena-agent typer pyyaml
```

## Quick Start

**First-time setup**: Launch the Web Dashboard to initialize and register the project:

```bash
# Start Web Dashboard (recommended for first-time use)
python -m tools dashboard serve --open-browser

# Or manually open browser after starting
python -m tools dashboard serve
# Then open: http://127.0.0.1:24282/dashboard/index.html
```

**Configuration**: Create `.env` file in `skills/serena/` directory:

```bash
SERENA_CONTEXT=claude-code
SERENA_MODES=interactive,editing,onboarding
SERENA_PROJECT=.
SERENA_DASHBOARD_ENABLED=true
SERENA_DASHBOARD_PORT=24282
```

**Basic Usage**:

```bash
# Find a symbol
python -m tools symbol find MyClass --body

# List symbols in file
python -m tools symbol overview src/main.py

# Find references
python -m tools symbol refs MyClass/method

# List available tools
python -m tools workflow tools
```

## CLI Commands

### Dashboard Commands
| Command | Description |
|---------|-------------|
| `dashboard serve [--open-browser] [--browser-cmd <path>]` | Start Web Dashboard server |
| `dashboard info` | Show current configuration overview |
| `dashboard tools` | List active and available tools |
| `dashboard modes` | List active and available modes |
| `dashboard contexts` | List active and available contexts |

**Dashboard Options**:
- `--open-browser` / `--no-open-browser`: Auto-open browser (default: False)
- `--browser-cmd <path>`: Specify browser executable path
- `--host <address>`: Listen address (default: 127.0.0.1)
- `--port <number>`: Listen port (default: 24282, 0 for auto-select)
- `SERENA_BROWSER_CMD`: Environment variable for browser command

### Symbol Operations
| Command | Description |
|---------|-------------|
| `symbol find <name>` | Find symbols by name |
| `symbol overview <path>` | List symbols in file |
| `symbol refs <name>` | Find symbol references |
| `symbol replace <name> --path <file> --body <code>` | Replace symbol body |
| `symbol insert-after <name> --path <file> --content <code>` | Insert after symbol |
| `symbol insert-before <name> --path <file> --content <code>` | Insert before symbol |
| `symbol rename <name> <new> --path <file>` | Rename symbol |

### Memory Operations
| Command | Description |
|---------|-------------|
| `memory list` | List all memories |
| `memory read <name>` | Read memory content |
| `memory write <name> --content <text>` | Create/update memory |
| `memory edit <name> --content <text>` | Edit memory |
| `memory delete <name>` | Delete memory |

### File Operations
| Command | Description |
|---------|-------------|
| `file list [--path <dir>]` | List directory |
| `file find <pattern>` | Find files by pattern |
| `file search <pattern>` | Search for pattern |

### Extended Tools
| Command | Description |
|---------|-------------|
| `cmd run <cmd>` | Execute shell command |
| `cmd script <path>` | Execute script file |
| `config read <path>` | Read JSON/YAML config |
| `config update <path> <key> <value>` | Update config value |

### Workflow
| Command | Description |
|---------|-------------|
| `workflow onboarding` | Run project onboarding |
| `workflow check` | Check onboarding status |
| `workflow tools` | List available tools |

## Global Options

```bash
python -m tools [OPTIONS] <command>

Options:
  -p, --project PATH    Project directory (default: ., env: SERENA_PROJECT)
  -c, --context TEXT    Context: agent, claude-code, ide, codex (env: SERENA_CONTEXT)
  -m, --mode TEXT       Operation modes (can repeat)
```

## Output Format

All CLI output is JSON:

```json
// Success
{"result": <data>}

// Error
{"error": {"code": "ERROR_CODE", "message": "description"}}
```

Error codes: `INVALID_ARGS`, `TOOL_NOT_FOUND`, `INIT_FAILED`, `RUNTIME_ERROR`

## Project Structure

```
skills/serena/
├── SKILL.md
├── README.md
├── .env.example
└── tools/
    ├── core.py           # SerenaCore wrapper
    ├── paths.py          # Path utilities
    ├── output.py         # JSON output utilities
    ├── cli/              # Typer CLI commands
    │   ├── __init__.py   # Main CLI entry
    │   ├── dashboard.py  # Dashboard commands
    │   ├── symbol.py
    │   ├── memory.py
    │   ├── file.py
    │   ├── workflow.py
    │   ├── cmd.py
    │   └── config.py
    ├── server/           # Web Dashboard server
    │   ├── __init__.py
    │   └── dashboard_server.py  # Flask HTTP server
    └── extended/         # Extended tools
        ├── cmd_tools.py
        └── config_tools.py
```

## Web Dashboard Features

The Web Dashboard provides:
- **Real-time Configuration**: View active context, modes, and tools
- **Project Management**: See registered projects and active project
- **Tool Monitoring**: Track active and available tools
- **Configuration Editing**: Edit `.env` file directly from browser
- **Auto Registration**: Automatically adds project to `~/.serena/serena_config.yml`

Access the dashboard at: `http://127.0.0.1:24282/dashboard/index.html`

## License

MIT
