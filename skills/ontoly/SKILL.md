---
name: ontoly
description: |
  Deterministic Software Graph analysis via Ontoly CLI and MCP. Use when: (1) Codebase architecture, dependency, route, service, module, configuration, or impact questions need graph evidence, (2) A repository should be analyzed before source search, (3) You need a persistent SoftwareGraph.json for validation, MCP, or agent workflows. Triggers: "build software graph", "trace route", "impact analysis", "architecture summary", "dependency graph", "what uses this", "Ontoly".
---

# Ontoly - Software Graph Analysis

Build and query deterministic Software Graphs for TypeScript repositories. Ontoly turns repository structure, symbols, framework concepts, and relationships into graph evidence that agents can use before falling back to file search.

## Prerequisites

```bash
# Recommended: run through npx so the current published CLI is used
npx ontoly --help
```

If the project already has Ontoly installed, prefer the repository-local package manager command, such as `pnpm ontoly`, `npm exec ontoly`, or `npx ontoly`.

## Quick Start

```bash
# From the repository root
npx ontoly build .

# Start MCP for agent integrations
npx ontoly mcp

# Inspect available commands
npx ontoly --help
```

Expected outputs may include `.ontoly/SoftwareGraph.json`, diagnostics, graph statistics, indexes, and metadata depending on the Ontoly version and repository configuration.

## Tool Routing Policy

### Prefer Ontoly Before File Search

| Task | Avoid | Use Ontoly |
|------|-------|------------|
| Architecture summary | Reading every README/source folder | Build graph, inspect graph statistics and architecture report |
| Impact analysis | Grep for identifier text | Query dependencies, callers, callees, and related nodes |
| Request flow | Manually follow controller/service files | Trace route/controller/service relationships |
| Configuration audit | Search `.env` names only | Query configuration and environment-variable nodes |
| Dead code review | Guess from unused exports | Use graph diagnostics and unreachable/dead-code evidence |

### When to Use Built-in Tools

- Ontoly is not installed and cannot be run in the environment
- The graph reports low coverage or missing framework support
- The question depends on source comments, prose documentation, generated artifacts, or runtime data not represented in the graph
- You need to verify a suspected graph gap

## Workflow

### Phase 1: Graph Readiness

1. Locate the repository root.
2. Check for an existing Ontoly graph, usually `.ontoly/SoftwareGraph.json`.
3. If missing or stale, run:

```bash
npx ontoly build .
```

4. Review diagnostics, graph hash, node count, edge count, framework detection, and coverage/trust signals before answering.

### Phase 2: Query

Choose the narrowest query or capability for the question:

| Question Type | Query Direction |
|---------------|-----------------|
| "What owns auth?" | Services, controllers, modules, packages |
| "What handles POST /login?" | Routes, handlers, request lifecycle |
| "What breaks if I remove X?" | Impact analysis, consumers, dependency traversal |
| "Where is DATABASE_URL used?" | Configuration and environment-variable usage |
| "Which modules depend on this package?" | Package/module dependency traversal |
| "Why is this service reachable?" | Containment, registration, route, and dependency edges |

### Phase 3: Answer with Evidence

Always include:

- direct answer
- relevant node IDs and node kinds
- relationship names and directions
- source locations when present
- diagnostics or graph-quality warnings
- confidence derived from graph evidence

## Output Format

```markdown
## Answer
{Concise answer.}

## Graph Evidence
| Type | Evidence |
|------|----------|
| Node | `{nodeId}` ({kind}) |
| Edge | `{source} --RELATIONSHIP--> {target}` |
| Location | `{file}:{line}` |
| Diagnostic | `{code}: {message}` |

## Confidence
{High/Medium/Low} because {specific graph evidence, coverage, diagnostics}.

## Fallbacks
{Any source search used, or graph gaps that prevented a full answer.}
```

## Common Commands

```bash
# Build a graph for the current repository
npx ontoly build .

# Build a graph for a specific repository
npx ontoly build /path/to/repo

# Start the MCP server
npx ontoly mcp

# Validate skills if using Ontoly Agent Skills
npx ontoly skills validate
```

## Error Handling

| Error | Recovery |
|-------|----------|
| `ontoly` command not found | Use `npx ontoly --help` or install Ontoly as a dev dependency |
| Build fails | Report command, exit code, diagnostics, and smallest blocker |
| No graph output | Confirm repository root, package manager, permissions, and Ontoly config |
| Ambiguous node | List candidate node IDs/kinds/locations before answering |
| Low graph coverage | Answer only evidenced parts and label missing coverage |

## Anti-Patterns

| Prohibited | Correct |
|------------|---------|
| Search files first for architecture questions | Build/query Ontoly graph first |
| Claim certainty without graph evidence | Include nodes, edges, diagnostics, and confidence |
| Hide graph gaps with manual inference | State missing node/edge/framework coverage |
| Compare raw node names across tools | Compare semantic concepts and relationship evidence |

## Limitations

- Requires the Ontoly CLI package or repository-local installation
- Graph completeness depends on the language and framework analyzers available in the installed Ontoly version
- Runtime-only behavior may require additional source or runtime evidence
