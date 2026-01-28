# Serena Skill

Semantic code understanding with IDE-like symbol operations. MCP-independent CLI for code navigation, editing, and project memory.

## Features

- **Symbol Operations**: Find, rename, replace, insert symbols with language-aware precision
- **Cross-file References**: Track symbol usages across entire codebase
- **Project Memory**: Persist and retrieve project knowledge across sessions
- **Extended Tools**: Shell commands, config file operations

## Installation

```bash
pip install serena-agent
```

## Quick Start

```bash
# Set project path (optional, defaults to current directory)
export SERENA_PROJECT=/path/to/project

# Find a symbol
python -m skills.serena.tools find-symbol MyClass --body

# List symbols in file
python -m skills.serena.tools symbols-overview src/main.py

# Find references
python -m skills.serena.tools find-refs MyClass/method

# List available tools
python -m skills.serena.tools list-tools
```

## CLI Commands

### Symbol Operations
| Command | Description |
|---------|-------------|
| `find-symbol <name>` | Find symbols by name |
| `symbols-overview <path>` | List symbols in file |
| `find-refs <name>` | Find symbol references |
| `replace-symbol <name> --path <file>` | Replace symbol body |
| `insert-after <name> --path <file>` | Insert after symbol |
| `insert-before <name> --path <file>` | Insert before symbol |
| `rename-symbol <name> <new> --path <file>` | Rename symbol |

### Memory Operations
| Command | Description |
|---------|-------------|
| `list-memories` | List all memories |
| `read-memory <name>` | Read memory content |
| `write-memory <name> --content <text>` | Create/update memory |
| `edit-memory <name> --content <text>` | Edit memory |
| `delete-memory <name>` | Delete memory |

### File Operations
| Command | Description |
|---------|-------------|
| `list-dir [--path <dir>]` | List directory |
| `find-file <pattern>` | Find files by pattern |
| `search <pattern>` | Search for pattern |

### Extended Tools
| Command | Description |
|---------|-------------|
| `run-command <cmd>` | Execute shell command |
| `run-script <path>` | Execute script file |
| `read-config <path>` | Read JSON/YAML config |
| `update-config <path> <key> <value>` | Update config value |

## Python API

```python
from skills.serena.tools import SerenaCore

core = SerenaCore(project="/path/to/project")
result = core.call_tool("find_symbol", name_path="MyClass")
tools = core.list_tools(scope="all")
core.shutdown()
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

## Documentation

- [SKILL.md](SKILL.md) - Core usage instructions
- [references/symbol-tools.md](references/symbol-tools.md) - Symbol tools reference
- [references/memory-tools.md](references/memory-tools.md) - Memory tools reference
- [references/file-tools.md](references/file-tools.md) - File tools reference
- [references/workflow-tools.md](references/workflow-tools.md) - Workflow tools reference

## Project Structure

```
skills/serena/
├── SKILL.md              # Core skill instructions
├── README.md             # This file
├── .env.example          # Environment config template
├── tools/
│   ├── __init__.py       # Package exports
│   ├── __main__.py       # CLI entry point
│   ├── cli.py            # CLI implementation
│   ├── core.py           # SerenaCore wrapper
│   ├── cmd_tools.py      # Command execution tools
│   ├── config_tools.py   # Config file tools
│   ├── symbol_tools.py   # Symbol tool wrappers
│   ├── memory_tools.py   # Memory tool wrappers
│   ├── file_tools.py     # File tool wrappers
│   ├── workflow_tools.py # Workflow tool wrappers
│   └── test_agent_init.py # Diagnostic script
└── references/           # Detailed documentation
```

## License

MIT
