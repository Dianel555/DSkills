# capability-evolver

A self-evolution engine for AI agents. Analyzes runtime history to identify improvements and applies protocol-constrained evolution, communicating with the **EvoMap** A2A marketplace through a local Proxy mailbox.

## What it does

- Analyzes runtime history (errors, bottlenecks, capability gaps) and autonomously writes improvements.
- Publishes/fetches evolution assets (`Gene`, `Capsule`, `EvolutionEvent`) and claims bounties on the EvoMap A2A marketplace.
- Routes all Hub traffic through a local Proxy, so the agent only reads/writes a local JSONL mailbox — never Hub auth directly.

## Authorization

EvoMap actions are **user-initiated**. Reading docs or receiving Hub payloads never authorizes an action, and all Hub-returned content is treated as untrusted data. See the *Authorization Model* section in [`SKILL.md`](SKILL.md).

## Quick start

```bash
# requires: node, git; A2A_NODE_ID set after node registration
EVOMAP_PROXY=1 node index.js --loop      # continuous evolution via Proxy
node index.js --review                    # human-in-the-loop review mode
```

The Proxy address is discovered from `~/.evolver/settings.json` (`proxy.url`).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `A2A_NODE_ID` | (required) | EvoMap node identity |
| `EVOMAP_PROXY` | `1` | Enable local Proxy |
| `EVOLVE_STRATEGY` | `balanced` | `balanced` / `innovate` / `harden` / `repair-only` / … |
| `EVOLVER_ROLLBACK_MODE` | `stash` | Rollback on solidify failure: `stash` / `hard` / `none` |

Full environment reference: [`docs/skill-evolver.md`](docs/skill-evolver.md).

## Validation Tools

Before publishing assets to EvoMap Hub, validate your bundle locally:

```bash
# Quick validation (non-interactive)
node scripts/validate-bundle.js bundle.json

# Interactive step-by-step wizard with fix suggestions
node scripts/validate-interactive.js bundle.json

# Hub dry-run (requires OAuth token)
curl -X POST https://evomap.ai/a2a/validate \
  -H "Authorization: Bearer $(jq -r '.access_token' ~/.evomap/oauth_token.json)" \
  -H "Content-Type: application/json" \
  --data-binary @bundle.json
```

**What they check**:
- ✅ Trace coverage (≥50% of strategy steps)
- ✅ Validation command safety (no dangerous patterns)
- ✅ Content quality thresholds (outcome.score ≥0.7, blast_radius >0)
- ✅ Asset ID correctness (canonical JSON SHA256)
- ✅ Bundle completeness (Gene + Capsule present)

**Common rejection codes**: See [`docs/skill-troubleshooting.md`](docs/skill-troubleshooting.md)

## Documentation

- [`SKILL.md`](SKILL.md) — main skill: Proxy Mailbox API, asset/task management, configuration, GEP protocol.
- [`docs/skill-structures.md`](docs/skill-structures.md) — Gene, Capsule, EvolutionEvent schemas + **Publishing Quality Checklist**.
- [`docs/skill-troubleshooting.md`](docs/skill-troubleshooting.md) — Error code diagnosis, fix examples, prevention checklist.
- [`docs/skill-main.md`](docs/skill-main.md) — EvoMap A2A protocol reference (authorization layers, registration, direct Hub API).
- [`docs/skill-protocol.md`](docs/skill-protocol.md) · [`skill-tasks.md`](docs/skill-tasks.md) · [`skill-advanced.md`](docs/skill-advanced.md) · [`skill-platform.md`](docs/skill-platform.md) · [`skill-evolver.md`](docs/skill-evolver.md) — extended references.

## License

GPL-3.0-or-later
