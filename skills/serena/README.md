# Serena CLI

Semantic code understanding with IDE-like symbol operations. MCP-independent CLI for code navigation, editing, and project memory.

## Features

- **Symbol Operations**: Find, rename, replace, insert symbols with language-aware precision
- **Cross-file References**: Track symbol usages across entire codebase
- **Project Memory**: Persist and retrieve project knowledge across sessions
- **Extended Tools**: Shell commands, config file operations

## Installation

```bash
pip install serena-agent typer
```

## Quick Start

```bash
# Set project path (optional, defaults to current directory)
export SERENA_PROJECT=/path/to/project

# Find a symbol
python -m skills.serena.tools symbol find MyClass --body

# List symbols in file
python -m skills.serena.tools symbol overview src/main.py

# Find references
python -m skills.serena.tools symbol refs MyClass/method

# List available tools
python -m skills.serena.tools workflow tools
```

## CLI Commands

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
python -m skills.serena.tools [OPTIONS] <command>

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
    ├── output.py         # JSON output utilities
    ├── cli/              # Typer CLI commands  
    │   ├── symbol.py     
    │   ├── memory.py     
    │   ├── file.py       
    │   ├── workflow.py   
    │   ├── cmd.py        
    │   └── config.py     
    └── extended/         # Extended tools
        ├── cmd_tools.py
        └── config_tools.py
```

## License

MIT
