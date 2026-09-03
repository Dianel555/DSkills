---
name: grill-me
description: Grill the user about a requirement, decision, or idea before implementation, then produce an actionable planning report without writing code. Use when the user wants to clarify requirements, stress-test an idea, compare approaches, or plan before coding.
---

# Grill Me

Turn an incomplete idea into an evidence-backed, actionable plan. Scale the depth to the work without adding unnecessary process.

## Boundaries

- Perform discovery, clarification, option analysis, and planning only.
- Do not write code, patches, or pseudocode; modify project files; install dependencies; or run commands with side effects.
- Do not invoke or depend on OC, OpenSpec, or their workflows.
- Facts are the agent's responsibility; material decisions belong to the user.
- Use read-only tools to inspect relevant code, configuration, and documentation. Use independent agents only when separate context boundaries materially reduce uncertainty.
- Deliver the planning report, then stop and wait for a separate implementation request.

## Adaptive Depth

Scale depth, not ceremony:

- **Lightweight:** For narrow, reversible, low-risk work, inspect only direct context, ask no questions when the input is sufficient, target zero to two rounds, and keep the report concise.
- **Medium:** For multi-module changes or integrations, cover boundaries, interfaces, data flow, failure behavior, dependencies, compatibility, testing, and rollback where relevant.
- **Large or high-risk:** For broad blast radius, migrations, sensitive data, or critical availability, define workstreams, contracts, milestones, rollout gates, observability, and recovery. Prefer an honest framework over false precision, and mark unresolved readiness gates explicitly.

Remain planning-only at every depth; do not silently switch workflows.

## Process

### 1. Frame and Investigate

Extract the desired outcome, target users, current state, deliverable, scope, non-goals, constraints, and observable acceptance criteria.

Investigate facts that can change the plan. Cite repository paths, configuration, documentation, or external sources when they support a conclusion, and distinguish verified facts from assumptions.

Cover only relevant planning dimensions:

- User flows, expected behavior, edge cases, and failure states
- Architecture, conventions, integrations, interfaces, data ownership, and migration
- Security, privacy, reliability, performance, accessibility, and compatibility
- Dependencies, rollout, rollback, observability, support, and maintenance

If the available information is sufficient, skip the interview and produce the report.

### 2. Build the Decision Tree

Model each material decision with its prerequisites, viable options, recommended answer, rationale, and downstream consequences.

The **frontier** is every unresolved decision whose prerequisites are settled. Questions depending on unresolved answers belong to a later round. Discoverable facts are not user questions; low-impact preferences receive a safe conventional default recorded as an assumption.

### 3. Work in Rounds

Ask the complete currently answerable frontier, number every question, and include a clear recommendation with a short reason. Then wait for the user's answers.

Use Pi's structured question tool for at most four closed-choice questions; otherwise use numbered text. If a fact lookup is pending, delay only the questions that depend on it and ask the rest of the frontier now.

After each response, update settled decisions, recompute the tree and frontier, investigate newly required facts, and ask only newly unblocked material questions.

If the user says "you decide," accepts the recommendations, or requests a one-shot result, adopt the recommended options and record them as delegated decisions or assumptions.

### 4. Select and Sequence the Solution

Compare viable approaches using the relevant criteria: goal fit, simplicity, consistency with the existing system, effort, compatibility, reversibility, operational risk, and maintainability.

Choose one recommended approach. Keep alternatives only when they represent a meaningful trade-off or fallback.

For every implementation step, name the intended outcome, affected boundary when known, prerequisites, concrete deliverable, and verification method. For larger work, group steps into ordered milestones or workstreams and state cross-boundary dependencies.

### 5. Close the Loop

Finish when goals, scope, non-goals, acceptance criteria, material decisions, relevant functional and non-functional requirements, dependencies, risks, and validation are actionable. Record every remaining unknown; do not continue merely to eliminate harmless uncertainty.

Assign one status:

- `Ready`: no unresolved blocker prevents implementation.
- `Conditional`: implementation depends on named assumptions or gates.
- `Blocked`: a critical fact or decision is missing; identify how to resolve it.

## Planning Report

Adapt the length to the request. Merge sections for lightweight work and include operational detail only when relevant; never pad the report with empty boilerplate.

```markdown
# Planning Report: <topic>

**Status:** Ready | Conditional | Blocked

## Executive Recommendation
<Recommended approach, reason, expected result, and primary trade-off.>

## 1. Goal and Scope
- Users and desired outcome:
- Current state and constraints:
- In scope / out of scope:
- Acceptance criteria:

## 2. Evidence and Requirements
- Verified facts and sources:
- Functional requirements:
- Relevant non-functional requirements, edge cases, and failure behavior:

## 3. Decisions and Options
- <Decision>: <selection and rationale>
- Alternatives: <meaningful rejected or fallback options>

## 4. Proposed Solution and Impact
- Solution outline:
- Affected boundaries, interfaces, data, and dependencies:

## 5. Execution Plan
1. <Step> -> Outcome: <result> -> Deliverable: <artifact> -> Verification: <check>
2. ...

For larger work, organize steps into ordered milestones or workstreams and identify cross-workstream dependencies.

## 6. Validation and Delivery
- Test and acceptance evidence:
- Migration, rollout, observability, rollback, and recovery when relevant:

## 7. Risks and Open Items
- Risks and mitigations:
- Assumptions:
- Remaining decisions or readiness gates:

## 8. Next Action
<The smallest concrete action that moves the plan forward.>
```

Before returning the report, verify that goals trace to requirements, planned work, and acceptance evidence; recommendations are grounded in facts or explicit assumptions; every step has an output and verification method; no blocker is hidden; and no implementation code or speculative architecture was added.
