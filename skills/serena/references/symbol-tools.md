# Symbol Tools Reference

Detailed documentation for Serena's symbol-level code operations.

## find_symbol

Search for symbols (functions, classes, methods, variables) by name.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name_path` | string | Yes | Symbol name or path (e.g., `"MyClass"`, `"MyClass/method"`) |
| `relative_path` | string | No | Restrict search to specific file/directory |
| `include_body` | bool | No | Include symbol implementation (default: false) |
| `depth` | int | No | Include nested symbols up to depth (0=symbol only, 1=direct children) |
| `substring_matching` | bool | No | Enable partial name matching (default: true) |

### Name Path Patterns

```
# Class
find_symbol(name_path="UserService")

# Method in class
find_symbol(name_path="UserService/getData")

# Nested method
find_symbol(name_path="UserService/Inner/method")

# Constructor (Python)
find_symbol(name_path="UserService/__init__")

# Constructor (Java/TypeScript)
find_symbol(name_path="UserService/constructor")
```

### Usage Examples

```python
# Find class without body (overview)
find_symbol(name_path="UserService", include_body=False)
# Returns: class signature, location, docstring

# Find class with direct children
find_symbol(name_path="UserService", depth=1, include_body=False)
# Returns: class + all methods/properties (signatures only)

# Find specific method with implementation
find_symbol(name_path="UserService/getData", include_body=True)
# Returns: full method body

# Find in specific file
find_symbol(
  name_path="getData",
  relative_path="src/services/user.py",
  include_body=True
)
```

### Output Format

```json
{
  "symbols": [
    {
      "name": "getData",
      "name_path": "UserService/getData",
      "kind": "method",
      "relative_path": "src/services/user.py",
      "line_start": 42,
      "line_end": 55,
      "signature": "def getData(self, user_id: int) -> dict",
      "docstring": "Retrieve user data by ID",
      "body": "..."  // if include_body=True
    }
  ]
}
```

## get_symbols_overview

Get an overview of all top-level symbols in a file.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relative_path` | string | Yes | Path to file |

### Usage

```python
get_symbols_overview(relative_path="src/services/user.py")
```

### Output Format

```json
{
  "file": "src/services/user.py",
  "symbols": [
    {"name": "UserService", "kind": "class", "line": 10},
    {"name": "get_user", "kind": "function", "line": 85},
    {"name": "USER_CACHE", "kind": "variable", "line": 5}
  ]
}
```

## find_referencing_symbols

Find all symbols that reference a given symbol.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name_path` | string | Yes | Symbol to find references for |
| `relative_path` | string | No | File containing the symbol |
| `include_code_snippets` | bool | No | Include surrounding code (default: true) |

### Usage

```python
# Find all usages of a function
find_referencing_symbols(
  name_path="UserService/getData",
  relative_path="src/services/user.py"
)
```

### Output Format

```json
{
  "symbol": "UserService/getData",
  "references": [
    {
      "file": "src/api/users.py",
      "line": 23,
      "column": 15,
      "context": "result = user_service.getData(user_id)",
      "referencing_symbol": "get_user_endpoint"
    }
  ]
}
```

## replace_symbol_body

Replace the entire definition of a symbol.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name_path` | string | Yes | Symbol to replace |
| `relative_path` | string | Yes | File containing the symbol |
| `new_body` | string | Yes | Complete new definition |

### Usage

```python
replace_symbol_body(
  name_path="UserService/getData",
  relative_path="src/services/user.py",
  new_body="""def getData(self, user_id: int) -> dict:
    \"\"\"Get user data with caching.\"\"\"
    if user_id in self._cache:
        return self._cache[user_id]
    data = self._fetch_user(user_id)
    self._cache[user_id] = data
    return data"""
)
```

### Important Notes
- Include complete definition (signature + body)
- Preserve indentation matching the file
- Symbol must exist (use `find_symbol` first to verify)

## insert_after_symbol / insert_before_symbol

Insert code after or before a symbol definition.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name_path` | string | Yes | Reference symbol |
| `relative_path` | string | Yes | File containing the symbol |
| `content` | string | Yes | Code to insert |

### Usage

```python
# Add method after existing method
insert_after_symbol(
  name_path="UserService/getData",
  relative_path="src/services/user.py",
  content="""
    def setData(self, user_id: int, data: dict) -> None:
        \"\"\"Update user data.\"\"\"
        self._cache[user_id] = data
        self._persist_user(user_id, data)"""
)

# Add import at file start
insert_before_symbol(
  name_path="UserService",  # First class in file
  relative_path="src/services/user.py",
  content="from typing import Optional\n\n"
)
```

## rename_symbol

Rename a symbol across the entire codebase.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name_path` | string | Yes | Symbol to rename |
| `relative_path` | string | Yes | File containing the symbol |
| `new_name` | string | Yes | New name for the symbol |

### Usage

```python
rename_symbol(
  name_path="UserService/getData",
  relative_path="src/services/user.py",
  new_name="fetchUserData"
)
```

### Important Notes
- Updates all references automatically
- Requires language server support
- Preview changes with `find_referencing_symbols` first

## JetBrains-Specific Tools

When using JetBrains plugin backend, use these variants:

| Standard Tool | JetBrains Variant |
|---------------|-------------------|
| `find_symbol` | `jet_brains_find_symbol` |
| `get_symbols_overview` | `jet_brains_get_symbols_overview` |
| `find_referencing_symbols` | `jet_brains_find_referencing_symbols` |

Additional JetBrains tool:
- `jet_brains_type_hierarchy` - Get class inheritance hierarchy

## Best Practices

1. **Start broad, then narrow**
   ```
   get_symbols_overview → find_symbol(depth=1) → find_symbol(include_body=True)
   ```

2. **Verify before editing**
   ```
   find_symbol(include_body=True) → review → replace_symbol_body
   ```

3. **Check impact before renaming**
   ```
   find_referencing_symbols → review usages → rename_symbol
   ```

4. **Use relative_path when possible**
   - Speeds up search
   - Avoids ambiguous matches
