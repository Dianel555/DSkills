---
name: serena
description: |
  Semantic code understanding with IDE-like symbol operations. Use when: (1) Large codebase analysis (>50 files), (2) Symbol-level operations (find, rename, refactor), (3) Cross-file reference tracking, (4) Project memory and session persistence, (5) Multi-language semantic navigation. Triggers: "find symbol", "rename function", "find references", "symbol overview", "project memory". IMPORTANT: Prioritize Serena's symbolic tools over file-based grep/read for code exploration.
---

# Serena - Semantic Code Understanding

IDE-like semantic code operations. Provides symbol-level code navigation, editing, and project memory.

## Execution Methods

### Method 1: MCP Tools (if available)
Use `mcp__serena__*` tools directly.

### Method 2: CLI (MCP-Independent)
Run via `python -m skills.serena.tools`:

```bash
# Prerequisites: pip install serena-agent
# Environment: SERENA_PROJECT (default: current directory)

# Symbol operations
python -m skills.serena.tools find-symbol MyClass --body
python -m skills.serena.tools symbols-overview src/main.py
python -m skills.serena.tools find-refs MyClass/method
python -m skills.serena.tools rename-symbol OldName NewName --path src/file.py

# Memory operations
python -m skills.serena.tools list-memories
python -m skills.serena.tools read-memory project_overview
python -m skills.serena.tools write-memory api_notes --content "..."

# File operations
python -m skills.serena.tools list-dir --recursive
python -m skills.serena.tools find-file "**/*.py"
python -m skills.serena.tools search "TODO:.*" --path src

# Extended tools
python -m skills.serena.tools run-command "git status"
python -m skills.serena.tools read-config config.json
```

## Tool Routing Policy

### Prefer Serena Over Built-in Tools

| Task | Avoid | Use Serena |
|------|-------|------------|
| Find function | `grep "def func"` | `find_symbol(name="func")` |
| List file structure | `cat file.py` | `get_symbols_overview(file)` |
| Find usages | `grep "func("` | `find_referencing_symbols(func)` |
| Edit function | `Edit` tool | `replace_symbol_body` |
| Rename | Manual find/replace | `rename_symbol` |

### When to Use Built-in Tools
- Simple text search (non-code patterns)
- Configuration files (JSON, YAML)
- Documentation files (Markdown)

## Tool Capability Matrix

### Symbol Tools
| Tool | Parameters | Output |
|------|------------|--------|
| `find_symbol` | `name_path`(required), `relative_path`/`include_body`/`depth`(optional) | Symbol info with optional body |
| `get_symbols_overview` | `relative_path`(required) | List of symbols in file |
| `find_referencing_symbols` | `name_path`(required), `relative_path`/`include_code_snippets`(optional) | Reference locations |
| `replace_symbol_body` | `name_path`, `relative_path`, `new_body`(all required) | Edit confirmation |
| `insert_after_symbol` | `name_path`, `relative_path`, `content`(all required) | Insert confirmation |
| `insert_before_symbol` | `name_path`, `relative_path`, `content`(all required) | Insert confirmation |
| `rename_symbol` | `name_path`, `relative_path`, `new_name`(all required) | Rename confirmation |

### Memory Tools
| Tool | Parameters | Output |
|------|------------|--------|
| `write_memory` | `name`, `content`(required) | Write confirmation |
| `read_memory` | `name`(required) | Memory content |
| `list_memories` | - | List of memory names |
| `edit_memory` | `name`, `content`(required) | Edit confirmation |
| `delete_memory` | `name`(required) | Delete confirmation |

### Extended Tools
| Tool | Parameters | Output |
|------|------------|--------|
| `run_command` | `command`(required), `cwd`/`timeout`(optional) | Command output |
| `run_script` | `script_path`(required), `args`(optional) | Script output |
| `read_config` | `path`(required), `format`(optional) | Config content |
| `update_config` | `path`, `key`, `value`(all required) | Update confirmation |

## Workflow

### Phase 1: Exploration
1. Use `get_symbols_overview` to understand file structure
2. Use `find_symbol` with `depth=1` to explore class members
3. Use `find_symbol` with `include_body=True` for implementation details

### Phase 2: Analysis
1. Use `find_referencing_symbols` for impact analysis
2. Use `list_memories` to check existing project knowledge
3. Use `read_memory` to retrieve context

### Phase 3: Modification
1. Verify target with `find_symbol(include_body=True)`
2. Use `replace_symbol_body` for edits
3. Use `insert_after_symbol`/`insert_before_symbol` for additions
4. Use `rename_symbol` for refactoring

## Error Handling

### CLI Error Codes
```json
{"error": {"code": "ERROR_CODE", "message": "description"}}
```

| Error Code | Meaning | Recovery |
|------------|---------|----------|
| `INVALID_ARGS` | Invalid arguments | Check `--help` |
| `TOOL_NOT_FOUND` | Unknown tool | Use `list-tools` |
| `INIT_FAILED` | Init failed | Check serena-agent |
| `RUNTIME_ERROR` | Execution failed | Check message |

### Common Issues
| Error | Recovery |
|-------|----------|
| Symbol not found | Use `search_for_pattern` as fallback |
| Project not activated | Call `onboarding` |
| Language server error | Use `restart_language_server` |

## Anti-Patterns

| Prohibited | Correct |
|------------|---------|
| Read entire file to find function | Use `find_symbol` |
| Grep for function calls | Use `find_referencing_symbols` |
| Manual search-replace rename | Use `rename_symbol` |
| Skip impact analysis | Check references before editing |
