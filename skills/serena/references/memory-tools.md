# Memory Tools Reference

Detailed documentation for Serena's project memory system.

## Overview

Serena's memory system persists project knowledge across sessions. Memories are stored as Markdown files in `.serena/memories/` within the project directory.

## write_memory

Create or update a named memory.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Memory identifier (becomes filename) |
| `content` | string | Yes | Memory content (Markdown supported) |

### Usage

```python
write_memory(
  name="api_architecture",
  content="""# API Architecture

## Endpoints
- `/api/v1/users` - User management
- `/api/v1/auth` - Authentication

## Patterns
- All endpoints return JSON
- Authentication via JWT in Authorization header
- Rate limiting: 100 req/min per user
"""
)
```

### Best Practices

**Good memory names:**
- `project_structure` - Overall codebase organization
- `coding_conventions` - Style and patterns
- `api_endpoints` - API documentation
- `database_schema` - Data model overview
- `build_commands` - How to build/test/deploy
- `known_issues` - Current bugs or limitations

**Memory content guidelines:**
- Use Markdown for structure
- Keep focused on single topic
- Include concrete examples
- Update when patterns change

## read_memory

Retrieve a stored memory.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Memory identifier |

### Usage

```python
read_memory(name="api_architecture")
```

### Output

Returns the full content of the memory file.

## list_memories

List all available memories for the current project.

### Parameters

None required.

### Usage

```python
list_memories()
```

### Output Format

```json
{
  "memories": [
    "api_architecture",
    "coding_conventions",
    "database_schema",
    "project_structure"
  ]
}
```

## edit_memory

Modify an existing memory.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Memory identifier |
| `content` | string | Yes | New content (replaces existing) |

### Usage

```python
edit_memory(
  name="api_architecture",
  content="# Updated API Architecture\n..."
)
```

## delete_memory

Remove a memory.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Memory identifier |

### Usage

```python
delete_memory(name="outdated_notes")
```

## Memory Workflow

### Initial Project Setup

```
1. onboarding() - Auto-generates initial memories
2. list_memories() - Review what was created
3. read_memory() - Check content accuracy
4. edit_memory() - Correct any issues
```

### During Development

```
1. list_memories() - Check available context
2. read_memory("relevant_topic") - Load needed context
3. [Do work]
4. write_memory() - Save new insights
```

### Recommended Memories

| Memory Name | Content |
|-------------|---------|
| `project_overview` | High-level description, tech stack |
| `directory_structure` | Key folders and their purposes |
| `coding_patterns` | Common patterns used in codebase |
| `testing_guide` | How to run tests, test patterns |
| `deployment_process` | Build and deploy steps |
| `api_reference` | Endpoint documentation |
| `database_models` | Schema and relationships |
| `common_tasks` | Frequently performed operations |

## Integration with Onboarding

The `onboarding` tool automatically creates initial memories:

```python
# Check if onboarding was done
check_onboarding_performed()

# If not, run onboarding
onboarding()

# Onboarding typically creates:
# - project_overview
# - directory_structure
# - build_commands
# - testing_guide
```

## Memory File Location

Memories are stored at:
```
<project_root>/.serena/memories/<name>.md
```

You can also manually edit these files with any text editor.

## Best Practices

1. **Keep memories focused**
   - One topic per memory
   - Split large memories into multiple files

2. **Update regularly**
   - Refresh after major changes
   - Remove outdated information

3. **Use consistent naming**
   - snake_case for names
   - Descriptive but concise

4. **Include examples**
   - Code snippets
   - Command examples
   - File paths

5. **Cross-reference**
   - Link related memories in content
   - Mention relevant files/symbols
