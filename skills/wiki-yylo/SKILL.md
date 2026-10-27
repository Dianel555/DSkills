---
name: wiki-yylo
description: Use YYLO Ledger wiki Records as durable project knowledge. Search before creating, classify information correctly, and make revision-safe Markdown updates without editing Ledger storage directly.
argument-hint: "[wiki question or knowledge to find/create/update]"
enable-shell-directives: true
---

# Use YYLO wiki Records

Treat Ledger as the source of truth. Use `yy ledger` in a YYLO controller and
`yylo-ledger` in a standalone Ledger project. Inspect `COMMAND wiki --help` before
acting; if `wiki` is absent, the installed Ledger version does not expose native
Record commands and must not be bypassed with direct file edits.

## Choose the right record

Before writing, decide where the information belongs:

- **Wiki**: durable explanatory project or domain knowledge that future work must discover.
- **Task**: scoped requested work, status, dependencies, acceptance criteria, and completion evidence.
- **Workflow**: validated structured steps, not prose guidance.
- **Artifact**: generated evidence, reports, receipts, logs, model output, or binary payloads.
- **Source documentation**: documentation released and versioned with product code.

Do not put secrets, caches, session transcripts, temporary status, bulky generated
evidence, or owner-only operational receipts in a wiki.

## Discover before creating

When an ID is known, preflight `yy ledger get --help` and prefer
`yy ledger get RECORD_ID -f json` without needing its type. If installed get is
task-only, use `yy ledger record get RECORD_ID -f json` after checking native help;
stop for an upgrade if unavailable. New generated wiki IDs use `doc_`; existing
IDs remain unchanged. Exact reads include hot and archived Records in the selected
project; never guess another type or project after a miss or ambiguity.

When no ID is known, use bounded summary searches first (use `record search` for
unknown kinds). Slugs and aliases are discovery conveniences, not replacement
identity. Universal get includes readable UTF-8 text up to 64 KiB by default;
inspect omission reasons instead of treating missing content as an empty page.
Use explicit `--content --max-content-bytes N` when needed (maximum 16 MiB).
Typed wiki get remains available for specialized source/rendering operations.

```bash
yy ledger wiki search --text "deployment policy" --projection summary --limit 20 -f json
yy ledger get RECORD_ID -f json
yy ledger wiki get RECORD_ID --raw
```

Use `--scope archive|all` only when the request requires cold records. Request
`full` projection only when payload bytes are necessary.

## Create durable Markdown

Use a file or stdin for substantial or shell-sensitive content:

```bash
yy ledger wiki create --title "Service ownership" --file ownership.md
yy ledger wiki create --title "Incident notes" --file - < incident-notes.md
```

Choose a stable title, namespace, slug, aliases, and relations deliberately. Keep
one topic per Record and link related immutable Record IDs rather than duplicating
truth.

## Update safely

1. Read the current Record and revision.
2. Preserve its immutable ID and inspect history when intent is unclear.
3. Follow `wiki update --help` for the installed compare-and-replace controls.
4. Supply the expected revision and required preimage/digest evidence.
5. Use file transport; do not rewrite Ledger files yourself.
6. Read back the resulting revision and receipt.

A revision or preimage mismatch means the source changed: reread and reconcile.
Never force past concurrent edits. Archive is a lifecycle transition, not delete.

Use `--front-matter` only for canonical front-matter interchange and `--rendered`
for inert, HTML-escaped rendering. Use `history RECORD_ID` to understand revisions;
do not infer history from the latest payload alone.

## Project wiki boundary

Portable controller guidance may live under the controller wiki, while project
and domain pages retain project-owned paths. Package-managed and project-owned
pages can coexist. Migration, runtime replacement, exceptional merge recovery,
release, deployment, and cold-archive maintenance remain authoritative runbooks,
not content to summarize into an everyday global skill.

## Complete request

## User-facing Record results

After creation, update, discovery, or handoff, report the Record kind/profile,
actual immutable Record ID, and actual Ledger slug from the returned Record or a
native get readback. Never invent a slug from the title or confuse it with the ID.
If the selected API omits a field, say it is unavailable rather than fabricate it.
IDs remain authoritative for relations and lifecycle operations; slugs aid discovery.

$ARGUMENTS
