# Sequential Think CLI

Standalone iterative thinking engine for complex problem-solving. No MCP dependency required.

## Installation

No external dependencies required - uses Python standard library only.

```bash
# Verify Python 3.7+
python --version
```

## Quick Start

```bash
# Start a thinking chain
python sequential_think_cli.py think -t "Analyzing the problem..." -n 1 -T 5

# Continue thinking
python sequential_think_cli.py think -t "Based on analysis, I hypothesize..." -n 2 -T 5

# Complete the chain
python sequential_think_cli.py think -t "Conclusion: the solution is..." -n 5 -T 5 --no-next

# View history
python sequential_think_cli.py history

# Clear history
python sequential_think_cli.py clear
```

## Commands

### think - Process a Thought

```bash
python sequential_think_cli.py think [options]

Required:
  -t, --thought          Current thinking step content
  -n, --thought-number   Current position in sequence (1-based)
  -T, --total-thoughts   Estimated total thoughts needed

Optional:
  --no-next              Mark as final thought (no more thinking needed)
  --is-revision          This thought revises previous thinking
  --revises-thought N    Which thought number is being reconsidered
  --branch-from N        Branching point thought number
  --branch-id ID         Identifier for current branch
  --needs-more           Signal more thoughts needed beyond estimate
  -q, --quiet            Suppress formatted output to stderr
```

### history - View Thought History

```bash
python sequential_think_cli.py history [options]

Options:
  -f, --format           Output format: json or text (default: text)
```

### clear - Clear History

```bash
python sequential_think_cli.py clear
```

## Examples

### Basic Thinking Chain

```bash
# Step 1: Problem identification
python sequential_think_cli.py think \
  -t "The API is returning 500 errors. Need to identify root cause." \
  -n 1 -T 4

# Step 2: Hypothesis
python sequential_think_cli.py think \
  -t "Hypothesis: Database connection pool exhaustion based on error logs." \
  -n 2 -T 4

# Step 3: Verification
python sequential_think_cli.py think \
  -t "Verified: Connection pool max=10, active=10, waiting=50. Pool exhausted." \
  -n 3 -T 4

# Step 4: Conclusion
python sequential_think_cli.py think \
  -t "Solution: Increase pool size to 50 and add connection timeout." \
  -n 4 -T 4 --no-next
```

### Revision Example

```bash
# Initial thought
python sequential_think_cli.py think \
  -t "The bug is in the authentication module." \
  -n 1 -T 3

# Revise after new evidence
python sequential_think_cli.py think \
  -t "Correction: Bug is in session management, not auth." \
  -n 2 -T 3 --is-revision --revises-thought 1
```

### Branching Example

```bash
# Main path
python sequential_think_cli.py think -t "Approach A: Refactor the service" -n 1 -T 3
python sequential_think_cli.py think -t "Approach A requires 3 weeks" -n 2 -T 3

# Branch to explore alternative
python sequential_think_cli.py think \
  -t "Alternative: Use existing library instead" \
  -n 3 -T 4 --branch-from 1 --branch-id "lib-approach"
```

## Output Format

### think command

```json
{
  "thoughtNumber": 2,
  "totalThoughts": 5,
  "nextThoughtNeeded": true,
  "branches": [],
  "thoughtHistoryLength": 2
}
```

### history command (JSON)

```json
{
  "history": [
    {
      "thought": "...",
      "thought_number": 1,
      "total_thoughts": 5,
      "next_thought_needed": true,
      "is_revision": false,
      "timestamp": "2024-01-15T10:30:00"
    }
  ],
  "branches": {},
  "totalThoughts": 1
}
```

## Data Storage

Thought history is persisted to:
- **Location**: `~/.config/sequential-think/thought_history.json`
- **Format**: JSON
- **Persistence**: Survives across sessions until cleared

## When to Use

| Scenario | Recommended |
|----------|-------------|
| Complex debugging (3+ components) | ✅ Yes |
| Architectural analysis | ✅ Yes |
| Root cause investigation | ✅ Yes |
| Multi-step problem solving | ✅ Yes |
| Simple bug fix | ❌ No |
| Single-file change | ❌ No |
| Quick explanation | ❌ No |

## Best Practices

1. **Start with reasonable estimate** - Adjust `totalThoughts` as you learn more
2. **Use revisions explicitly** - Mark `--is-revision` when reconsidering
3. **Branch for alternatives** - Explore different approaches with `--branch-from`
4. **Don't rush completion** - Only use `--no-next` when truly done
5. **Clear between sessions** - Run `clear` when starting new problem
