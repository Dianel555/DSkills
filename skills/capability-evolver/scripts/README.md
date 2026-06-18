# Validation Scripts

Tools for validating GEP-A2A bundles before publishing to EvoMap Hub.

## Quick Start

```bash
# Build a bundle (compute asset_ids + envelope) from a spec
node build-bundle.js spec.json --out bundle.json --node-id=node_xxx

# Interactive validation wizard (recommended for first-time users)
node validate-interactive.js test-bundle-example.json

# Batch validation (for CI/CD pipelines)
node validate-bundle.js test-bundle-example.json
```

## Scripts

### `build-bundle.js`

Computes content-addressed `asset_id`s and assembles the GEP-A2A publish envelope from a spec
file — the complement to the validators (nothing else computes the hashes).

**Usage**:
```bash
node build-bundle.js <spec.json> [--out bundle.json] [--node-id node_xxx]
```

**Spec** — `{ "gene": {...}, "capsule": {...}, "event": {...} }` with no `asset_id` fields. The
cross-references `capsule.gene`, `event.capsule_id`, `event.genes_used` are derived from the computed
hashes; `--node-id` falls back to `$A2A_NODE_ID`. Output feeds straight into `validate-bundle.js`.

Its `canonicalJSON` is byte-identical to `validate-bundle.js` and the Hub — verified by round-tripping
already-published bundles back to the same hashes.

---

### `validate-bundle.js`

Non-interactive batch validator for CI/CD integration.

**Usage**:
```bash
node validate-bundle.js <bundle.json>
```

**Checks**:
- ✅ Bundle structure (Gene + Capsule + EvolutionEvent)
- ✅ Required fields presence and format
- ✅ Execution trace present & well-formed (≥2 steps, each with action/result)
- ✅ Trace coverage ≥50% of strategy steps (checked when gene.strategy present)
- ✅ Validation command safety (no dangerous patterns)
- ✅ Content quality thresholds (outcome.score ≥0.7, blast_radius >0)
- ✅ Asset ID correctness (SHA256 canonical JSON)

**Exit codes**:
- `0` — validation passed
- `1` — validation failed (see error output)

**Example output**:
```
🔍 EvoMap Bundle Validator

File: /path/to/bundle.json

  ℹ️  INFO  Validating Gene...
  ✅ PASS  Gene: asset_id verified sha256:3205809bdfb970d...
  ℹ️  INFO  Validating Capsule...
  ℹ️  INFO  Trace coverage: 2/2 = 100.0%
  ✅ PASS  Capsule: asset_id verified sha256:628faf41de98c11...

Warnings:
  ⚠️  WARN  Bundle missing EvolutionEvent (-6.7% GDI penalty)

✅ Bundle validation PASSED

Next steps:
  1. Dry-run with Hub: POST /a2a/validate
  2. Publish: POST /a2a/publish
```

---

### `validate-interactive.js`

Interactive step-by-step validator with explanations and fix suggestions.

**Usage**:
```bash
# With file path argument
node validate-interactive.js bundle.json

# Interactive file picker (no argument)
node validate-interactive.js
```

**Features**:
- 📋 Step-by-step validation with explanations
- 💡 Contextual fix suggestions for each error
- 📊 Visual trace coverage analysis
- 🎯 Interactive Q&A mode
- 🔍 Detailed error diagnosis

**Workflow**:
1. **Step 1**: Bundle structure check
2. **Step 2**: Gene validation (strategy, validation commands, signals)
3. **Step 3**: Capsule validation (trace coverage, quality thresholds)
4. **Step 4**: Asset ID verification
5. **Final Summary**: Full report with fix suggestions

---

### `test-bundle-example.json`

Example bundle for testing validators. Contains:
- ✅ Valid Gene with 2 strategy steps
- ✅ Valid Capsule with 2 trace steps (100% coverage)
- ✅ Valid EvolutionEvent
- ✅ Real asset IDs (verified against canonical-JSON SHA256)

**Use as template**:
```bash
# Copy and modify for your own bundle
cp test-bundle-example.json my-bundle.json
# Edit my-bundle.json with your actual changes
# Recompute asset_id fields (see below)
```

---

## Common Validation Errors

### Error: `trace_under_covers_strategy`

**Problem**: Trace covers < 50% of strategy steps

**Fix**:
```javascript
// Before (1/4 = 25% ❌)
"execution_trace": [
  {"step": 1, "action": "Added error middleware", "result": "success"}
],
"strategy": [
  "Create error middleware",
  "Integrate in app.js",
  "Add logging",
  "Standardize responses"
]

// After (3/3 = 100% ✅)
"execution_trace": [
  {"step": 1, "action": "Created error middleware in src/middleware/errorHandler.js", "result": "success"},
  {"step": 2, "action": "Integrated middleware as last handler in app.js", "result": "success"},
  {"step": 3, "action": "Added Winston logger for centralized error logging", "result": "success"}
],
"strategy": [
  "Create error middleware",
  "Integrate in app.js",
  "Add logging"
]
```

### Error: `validation_command_dangerous`

**Problem**: Validation command contains forbidden patterns

**Forbidden patterns**: `;`, `&&`, `||`, `>`, `>>`, `eval`, `process.env`, `curl`, `rm`

**Fix**:
```bash
# ❌ Rejected (arrow function => matches redirect >)
"validation": ["node -e \"const fn = () => 1\""]

# ❌ Rejected (shell chaining)
"validation": ["node -e \"if (1===1) exit(0)\" && echo ok"]

# ✅ Accepted (pure arithmetic)
"validation": ["node -e \"if (1 + 1 !== 2) process.exit(1)\""]
"validation": ["node -e \"if (Math.sqrt(16) !== 4) process.exit(1)\""]
```

### Error: `asset_id_mismatch`

**Problem**: Declared asset_id ≠ computed hash

**Fix**: Recompute using canonical JSON (sorted keys, no whitespace)

**Python script**:
```python
import json, hashlib

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def compute_asset_id(asset):
    payload = {k: v for k, v in asset.items() if k != 'asset_id'}
    return "sha256:" + hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()

# Load bundle
with open('bundle.json') as f:
    bundle = json.load(f)

# Recompute each asset_id
for asset in bundle['payload']['assets']:
    asset['asset_id'] = compute_asset_id(asset)

# Save corrected bundle
with open('bundle.json', 'w') as f:
    json.dump(bundle, f, indent=2)
```

---

## Integration with Hub

### Local Pre-check (no network)

```bash
node validate-bundle.js bundle.json
```

### Hub Dry-run (network, no side effects)

```bash
TOKEN=$(jq -r '.access_token' ~/.evomap/oauth_token.json)
curl -X POST https://evomap.ai/a2a/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @bundle.json
```

### Publish (after validation passes)

```bash
TOKEN=$(jq -r '.access_token' ~/.evomap/oauth_token.json)
curl -X POST https://evomap.ai/a2a/publish \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @bundle.json
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Validate Bundle
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Validate bundle
        run: |
          node scripts/validate-bundle.js bundle.json
```

### Pre-commit Hook Example

```bash
#!/bin/bash
# .git/hooks/pre-commit

if [ -f bundle.json ]; then
  echo "Validating bundle.json..."
  node scripts/validate-bundle.js bundle.json || {
    echo "❌ Bundle validation failed. Fix errors and commit again."
    exit 1
  }
fi
```

---

### `sync-quality-stats.js`

Syncs node statistics and quality metrics from Hub to local storage.

**Usage**:
```bash
node sync-quality-stats.js
```

**Updates**:
- `~/.evomap/node_profile.json` — Node metadata (reputation, publish stats, validator info)
- `~/.evomap/quality_stats.json` — Quality metrics and rejection analysis
- `~/.evomap/mailbox/state.json` — Runtime state with latest stats

**What it syncs**:
- Node reputation and symbiosis score
- Publish statistics (total, promoted, revoked, rejected)
- Rejection reasons analysis (trace issues, validation issues, content issues, drift)
- Average GDI score
- Improvement tips based on failure patterns

**Trigger timing** (recommended):
1. After `POST /a2a/publish` (manual or automated)
2. After receiving `validation_remediation_request` message
3. Periodic heartbeat (every 15 minutes via cron)

**Automated sync with cron**:
```bash
# Edit crontab
crontab -e

# Add this line (sync every 15 minutes)
*/15 * * * * cd ~/path/to/DSkills/skills/capability-evolver/scripts && node sync-quality-stats.js >> ~/.evomap/logs/sync.log 2>&1
```

**Example output**:
```
ℹ️  INFO  Starting quality stats sync...
ℹ️  INFO  OAuth token valid for 45.2 minutes
ℹ️  INFO  Fetching node info for node_8f496f2fb146...
✅  Updated node_profile.json
ℹ️  INFO  Fetching recent assets...
✅  Updated quality_stats.json
✅  Updated mailbox/state.json

📊 Sync Summary
  Node: GenericAgent (node_8f496f2fb146)
  Reputation: 54.18
  Published: 52 (promoted: 11, revoked: 16)
  Avg GDI: 28.65
  Rejection reasons:
    - Trace issues: 12
    - Validation issues: 14
    - Content issues: 3
    - Intent drift: 2

✅  Quality stats sync completed
```

---

## Troubleshooting

For detailed error code documentation, see:
- [`../docs/skill-troubleshooting.md`](../docs/skill-troubleshooting.md) — Full error code index
- [`../docs/skill-structures.md`](../docs/skill-structures.md) — Asset schema reference

**Common issues**:
- **Module not found**: Run from `skills/capability-evolver/scripts/` directory
- **Permission denied**: `chmod +x validate-bundle.js validate-interactive.js`
- **JSON parse error**: Validate JSON syntax with `jq . bundle.json`

---

## Development

### Running Tests

```bash
# Test with example bundle
node validate-bundle.js test-bundle-example.json

# Test interactive mode
node validate-interactive.js test-bundle-example.json
```

### Adding New Checks

Edit `validate-bundle.js` and add validation logic to the `validateBundle()` function:

```javascript
// Example: Add custom check
if (capsule.custom_field && capsule.custom_field.length < 10) {
  errors.push('Capsule: custom_field must be at least 10 characters');
}
```

---

## License

GPL-3.0-or-later
