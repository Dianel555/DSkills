---
name: plan-ledger-tasks-yylo
description: Create a concise Product Development Requirement and one or more implementation-sized YYLO Ledger tasks when the user explicitly asks to plan or register work.
argument-hint: "[Required Features] [Constraints] [Acceptance Criteria]"
enable-shell-directives: true
---

# Plan Kanban work

1. Read the project instructions and relevant product code from the integration or feature worktree. Read existing task/spec metadata through the canonical controller; do not assume `.juno_task/plan.md` exists.
2. Produce one concise PDR covering the goal, current behavior, scope, exclusions, risks, dependencies, acceptance criteria, and focused tests. Draft it in a fresh external file; do not place it in the product tree or a task body.
3. Preflight `yy ledger --help` and `yy ledger artifact --help`. Capture the PDR as a local immutable `report` Artifact Record with task/request provenance, then verify its ID, digest, size, retention, retrieval, and history. If the artifact API is unavailable, stop with the external draft intact and request an upgrade; never fall back to product `docs/`, task bodies/responses, new `.juno_task/specs`, or direct store edits.
4. Split only when pieces can be implemented and validated independently. Concurrent tasks must have explicit path ownership and dependencies.
5. Create tasks through routed `yy ledger` commands. Put concise durable requirements and acceptance criteria in each task body, record the PDR artifact ID in supported task fields/provenance, and relate follow-ups instead of reopening archived IDs.
6. Product documentation is only documentation shipped with the product. Never create controller-private tasks, ledger, state, artifacts, objects, specs, or receipts inside a product or feature worktree.
7. Do not start implementation, create worktrees, push, deploy, or mutate production unless the user separately asks.

Use `--id`, not legacy `--ID`, for Kanban mutations. Return the task IDs and a short dependency/order summary.

## Retrieve the PDR by ID

Preflight `yy ledger get --help`; use `yy ledger get RECORD_ID -f json` to read
back a known PDR without guessing its storage type. If installed get is task-only,
use `yy ledger record get RECORD_ID -f json` after checking native help; stop for
an upgrade if unavailable. New PDRs remain artifact/report (`artifact_` IDs on
supporting runtimes); historical document/pdr remains readable. Existing IDs
remain unchanged: do not invent `pdr_` or rewrite stored references.

Unknown IDs require bounded `record search --projection summary --limit 20`, not
trial-and-error typed gets. Exact reads include hot/archive in the selected
project; cold discovery needs explicit scope. Metadata/history alone is not byte
round-trip proof. Verify included text or explicitly retrieve local/inline bytes
with `--content --max-content-bytes N` (64 KiB default, 16 MiB maximum). Check exit
status and digest/size; never download external payloads implicitly. If exact-byte
retrieval is unavailable, retain the draft and request a compatible runtime.

## User-facing Record results

After creation, update, discovery, or handoff, report the Record kind/profile,
actual immutable Record ID, and actual Ledger slug from the returned Record or a
native get readback. Never invent a slug from the title or confuse it with the ID.
If the selected API omits a field, say it is unavailable rather than fabricate it.
IDs remain authoritative for relations and lifecycle operations; slugs aid discovery.

$ARGUMENTS
