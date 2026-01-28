# File Tools Reference

Detailed documentation for Serena's file operation tools.

## list_dir

List files and directories.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | No | Directory to list (default: project root) |
| `recursive` | bool | No | Include subdirectories (default: false) |
| `max_depth` | int | No | Maximum recursion depth |

### Usage

```python
# List project root
list_dir()

# List specific directory
list_dir(relative_path="src/services")

# Recursive listing
list_dir(relative_path="src", recursive=True, max_depth=2)
```

### Output Format

```json
{
  "path": "src/services",
  "entries": [
    {"name": "user.py", "type": "file", "size": 2048},
    {"name": "auth.py", "type": "file", "size": 1536},
    {"name": "utils", "type": "directory"}
  ]
}
```

## find_file

Find files matching a pattern.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Glob pattern (e.g., `"*.py"`, `"**/*.ts"`) |
| `relative_path` | string | No | Directory to search in |

### Usage

```python
# Find all Python files
find_file(pattern="**/*.py")

# Find in specific directory
find_file(pattern="*.ts", relative_path="src/components")

# Find specific filename
find_file(pattern="**/config.json")
```

### Output Format

```json
{
  "pattern": "**/*.py",
  "files": [
    "src/main.py",
    "src/services/user.py",
    "src/services/auth.py",
    "tests/test_user.py"
  ]
}
```

## search_for_pattern

Search for text patterns in files (regex supported).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Search pattern (regex) |
| `relative_path` | string | No | Restrict search to path |
| `file_pattern` | string | No | Filter files (glob) |
| `case_sensitive` | bool | No | Case sensitivity (default: true) |

### Usage

```python
# Find TODO comments
search_for_pattern(pattern="TODO:.*")

# Find function definitions
search_for_pattern(
  pattern="def\\s+\\w+\\s*\\(",
  relative_path="src",
  file_pattern="*.py"
)

# Case-insensitive search
search_for_pattern(
  pattern="error",
  case_sensitive=False
)
```

### Output Format

```json
{
  "pattern": "TODO:.*",
  "matches": [
    {
      "file": "src/services/user.py",
      "line": 42,
      "content": "# TODO: Add caching",
      "context_before": ["def getData(self):"],
      "context_after": ["    return self._fetch()"]
    }
  ]
}
```

## read_file

Read file contents.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | Path to file |
| `start_line` | int | No | Start reading from line |
| `end_line` | int | No | Stop reading at line |

### Usage

```python
# Read entire file
read_file(relative_path="src/config.py")

# Read specific lines
read_file(
  relative_path="src/services/user.py",
  start_line=40,
  end_line=60
)
```

### Output Format

```json
{
  "file": "src/config.py",
  "content": "...",
  "lines": 150,
  "encoding": "utf-8"
}
```

## File Editing Tools

### create_text_file

Create or overwrite a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | Path for new file |
| `content` | string | Yes | File content |

### replace_content

Replace text in a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | File to modify |
| `old_content` | string | Yes | Text to find |
| `new_content` | string | Yes | Replacement text |
| `use_regex` | bool | No | Treat as regex (default: false) |

### replace_lines

Replace a range of lines.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | File to modify |
| `start_line` | int | Yes | First line to replace |
| `end_line` | int | Yes | Last line to replace |
| `new_content` | string | Yes | Replacement content |

### delete_lines

Delete a range of lines.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | File to modify |
| `start_line` | int | Yes | First line to delete |
| `end_line` | int | Yes | Last line to delete |

### insert_at_line

Insert content at a specific line.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | File to modify |
| `line` | int | Yes | Line number for insertion |
| `content` | string | Yes | Content to insert |

## When to Use File Tools vs Symbol Tools

| Task | Use File Tools | Use Symbol Tools |
|------|----------------|------------------|
| Read config files | ✅ | ❌ |
| Find text patterns | ✅ | ❌ |
| Edit function body | ❌ | ✅ |
| Rename variable | ❌ | ✅ |
| Add new file | ✅ | ❌ |
| Modify class method | ❌ | ✅ |
| Search in Markdown | ✅ | ❌ |
| Find function usages | ❌ | ✅ |

## Best Practices

1. **Prefer symbol tools for code**
   - More precise
   - Language-aware
   - Handles edge cases

2. **Use file tools for**
   - Configuration files
   - Documentation
   - Non-code text files
   - When symbol structure unknown

3. **Combine tools effectively**
   ```
   find_file("*.py") → get_symbols_overview → find_symbol
   ```

4. **Use relative_path to narrow scope**
   - Faster searches
   - More relevant results
