# Workflow Tools Reference

Detailed documentation for Serena's workflow and meta-operation tools.

## Onboarding Tools

### check_onboarding_performed

Check if project onboarding has been completed.

### Parameters

None required.

### Usage

```python
check_onboarding_performed()
```

### Output

```json
{
  "onboarding_performed": true,
  "memories_count": 5,
  "last_onboarding": "2024-01-15T10:30:00Z"
}
```

### onboarding

Perform initial project analysis and create memories.

### Parameters

None required (uses active project).

### Usage

```python
onboarding()
```

### What Onboarding Does

1. Analyzes project structure
2. Identifies programming languages
3. Finds build/test commands
4. Creates initial memories:
   - `project_overview`
   - `directory_structure`
   - `build_commands`
   - `testing_guide`
5. Reads existing documentation (README, etc.)

### When to Run

- First time using Serena on a project
- After major project restructuring
- When memories seem outdated

## Configuration Tools

### get_current_config

Get current Serena configuration.

### Parameters

None required.

### Usage

```python
get_current_config()
```

### Output

```json
{
  "active_project": {
    "name": "my-project",
    "path": "/path/to/project",
    "languages": ["python", "typescript"]
  },
  "context": "claude-code",
  "modes": ["interactive", "editing"],
  "enabled_tools": ["find_symbol", "replace_symbol_body", ...],
  "disabled_tools": ["execute_shell_command"]
}
```

### switch_modes

Change active operational modes.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `modes` | list[string] | Yes | Modes to activate |

### Available Modes

| Mode | Description |
|------|-------------|
| `planning` | Focus on analysis and planning |
| `editing` | Enable code modification tools |
| `interactive` | Conversational interaction style |
| `one-shot` | Single response completion |
| `no-onboarding` | Skip onboarding prompts |
| `no-memories` | Disable memory tools |

### Usage

```python
# Switch to planning mode
switch_modes(modes=["planning", "interactive"])

# Enable editing
switch_modes(modes=["editing", "interactive"])
```

### activate_project

Activate a different project.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | Yes | Project name or path |

### Usage

```python
# By name (if previously configured)
activate_project(project="my-project")

# By path (auto-creates if needed)
activate_project(project="/path/to/project")
```

### Note
Not available in single-project contexts (`claude-code`, `ide`).

## Thinking Tools

### think_about_collected_information

Reflect on whether enough information has been gathered.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context` | string | Yes | Current task context |
| `information` | string | Yes | Information collected so far |

### Usage

```python
think_about_collected_information(
  context="Implementing user authentication",
  information="Found UserService class, auth middleware, JWT utils..."
)
```

### Output

```json
{
  "assessment": "sufficient",
  "missing": [],
  "suggestions": []
}
```

### think_about_task_adherence

Check if current actions align with the task.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Original task description |
| `actions` | string | Yes | Actions taken so far |

### Usage

```python
think_about_task_adherence(
  task="Add caching to getUserData function",
  actions="Read UserService class, found getData method, analyzed dependencies..."
)
```

### think_about_whether_you_are_done

Determine if the task is complete.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Original task |
| `completed_actions` | string | Yes | What has been done |

### Usage

```python
think_about_whether_you_are_done(
  task="Add caching to getUserData function",
  completed_actions="Added cache dict, modified getData to check cache, added cache invalidation..."
)
```

## Utility Tools

### initial_instructions

Get Serena usage instructions.

### Parameters

None required.

### Usage

```python
initial_instructions()
```

### When to Use
- Client doesn't auto-read system prompt (e.g., Claude Desktop)
- Need reminder of available tools
- Troubleshooting tool usage

### prepare_for_new_conversation

Get instructions for continuing in a new conversation.

### Parameters

None required.

### Usage

```python
prepare_for_new_conversation()
```

### Output

Provides summary of:
- Current project state
- Recent changes made
- Recommended next steps
- Context to preserve

### summarize_changes

Get summary of changes made in current session.

### Parameters

None required.

### Usage

```python
summarize_changes()
```

### restart_language_server

Restart the language server (recovery tool).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `language` | string | No | Specific language server |

### Usage

```python
# Restart all
restart_language_server()

# Restart specific
restart_language_server(language="python")
```

### When to Use
- Symbol operations returning stale data
- After external file changes
- Language server errors

### open_dashboard

Open Serena web dashboard.

### Parameters

None required.

### Usage

```python
open_dashboard()
```

### Dashboard Features
- Session logs
- Tool usage statistics
- Language server status
- Configuration viewer

## Workflow Patterns

### Starting a New Session

```
1. check_onboarding_performed()
2. If not done: onboarding()
3. list_memories()
4. read_memory("project_overview")
5. get_current_config()
```

### Before Major Changes

```
1. think_about_collected_information()
2. find_referencing_symbols() - check impact
3. think_about_task_adherence()
4. [Make changes]
5. think_about_whether_you_are_done()
```

### Ending a Session

```
1. summarize_changes()
2. write_memory() - save insights
3. prepare_for_new_conversation()
```
