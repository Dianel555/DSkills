---
name: exa-agent
description: Orchestrate Exa Agent runs for open-ended, multi-step research, structured list building, retained-run recovery, and evidence-aware coverage validation.
context: fork
---

# Exa Agent Orchestration

Use `agent_run` for open-ended discovery, multi-hop research, structured list building, or a follow-up that benefits from retained Agent context. Use `web_search_exa` or `web_search_advanced_exa` for deterministic single-pass searches.

## Choose Agent or a Deterministic Script

- Use Agent when the universe is not already enumerated, the work requires iterative discovery, or later steps depend on earlier evidence.
- For homogeneous enrichment over known input rows, use a deterministic script with bounded concurrency, retry backoff, a checkpoint, and a stable output file. Do not launch many manual Agent runs for that case.
- Use `web_fetch_exa` when the URLs are already known and only their contents are needed.

## Define the Run Contract First

Before creating a billable run, define all of the following:

- **objective**: the decision or deliverable the run must support
- **universe**: the bounded population when one is known
- **segments**: categories, geographies, time windows, or other required strata
- **coverage target**: expected count or minimum coverage per segment
- **output fields**: exact fields required for every result row
- **evidence requirements**: acceptable sources, citation fields, and recency
- **exclusions**: entities or conditions that must not appear

If any item is unknown, state the uncertainty in the query and require the result to report gaps.

## Prefer a Bounded Output Schema

For lists and repeatable work, use `--output-schema` with a top-level object; the CLI sends it as upstream `outputSchema`. Put rows in a bounded array property and include fields for identity, segment, evidence, and exclusion rationale. Avoid a bare top-level array.

Example `schema.json`:

```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "segment": {"type": "string"},
          "evidenceUrl": {"type": "string"},
          "evidenceSummary": {"type": "string"}
        },
        "required": ["name", "segment", "evidenceUrl"]
      }
    },
    "coverage": {"type": "object"},
    "gaps": {"type": "array"}
  },
  "required": ["items", "coverage", "gaps"]
}
```

`--input-data` and `--input-exclusion` accept UTF-8 JSON arrays of objects. Use them to supply seed rows and known exclusions without embedding large JSON in a shell command.

## Create a Run

```bash
python scripts/exa_cli.py agent_run \
  --query "Find qualified companies by segment and cite evidence" \
  --system-prompt "Follow the schema and disclose coverage gaps" \
  --output-schema schema.json \
  --input-data seeds.json \
  --input-exclusion exclusions.json \
  --data-source fiber \
  --data-source similarweb \
  --effort low \
  --wait-seconds 750 \
  --poll-interval 4 \
  --out run.json
```

The create POST is single-shot. If its response is lost or returns a transient error, the CLI does not retry because the upstream run may already exist. Record the `agent_run_created` JSON event emitted on stderr as soon as an ID is available.

## Resume Versus Continue

- Use `--run-id agent_run_...` to poll the same unfinished run. Resume mode performs GET requests only and never creates a replacement.
- Use `--previous-run-id agent_run_...` together with a new `--query` only after the earlier run is complete. This creates a new run ID with the completed run as context.
- Never use `--previous-run-id` to replace a run that is still queued or running.

```bash
# Continue waiting for the same run
python scripts/exa_cli.py agent_run --run-id agent_run_123 --wait-seconds 750

# Ask a follow-up based on a completed run; this creates a new ID
python scripts/exa_cli.py agent_run \
  --query "Validate the weakest-evidence rows" \
  --previous-run-id agent_run_123
```

Ctrl-C after an ID is known emits `agent_run_interrupted` with the same ID and a resume command on stderr, then exits 130.

## Interpret Lifecycle Output

- `completed`: `success=true`, `outputReady=true`, and `output` is ready; optional `usage` and `costDollars` are preserved.
- `running`: the wait deadline ended on a nonterminal state; `outputReady=false`, the same ID is returned, and exit code is 0.
- `failed` or `cancelled`: `success=false`, `outputReady=false`, the same ID is retained, and exit code is 1.

When `output.grounding` is present, treat it as the final citation evidence rather than a transient source preview.

## Validate Coverage and Evidence

Before presenting results:

1. Check row count against the coverage target.
2. Check every required segment and report missing or under-covered segments.
3. Dedup by stable identity, not only display name.
4. Inspect evidence quality, source recency, and whether each claim is supported.
5. Preserve exclusions and explain any ambiguous exclusion decisions.
6. Report unresolved gaps and the searches or data sources already attempted.

Do not claim complete or exhaustive coverage unless the universe, segment coverage, count, deduplication, evidence, and gaps have all been verified. Otherwise describe the result as **best-effort discovery** and state the known limitations.

## ZDR Limitation

The standalone CLI does not implement SSE and therefore does not support Zero Data Retention (ZDR) streaming. It preserves upstream ZDR/streaming errors and does not retry Agent creation. Use an upstream streaming-capable client when ZDR is mandatory.
