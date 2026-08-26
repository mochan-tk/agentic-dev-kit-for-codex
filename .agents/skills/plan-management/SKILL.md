---
name: plan-management
description: Maintain the canonical Issue graph and rolling plan. Use when decomposing or replanning durable work. Do not use to execute a Task.
---

# Plan Management

Maintain a just-in-time plan in the canonical Issue graph. Read the
[Issue graph procedure](references/issue-graph-procedure.md) before creating,
reordering, splitting, or closing planned work.

## Inputs

- Read the repository initiative or Epic set, linked Epic and Task Issues,
  accepted requirements and decisions, and the selected fresh context pin.
- Read the current ledger contract, ownership manifest, dependencies, risk,
  and current external-state observations.
- Identify which planned operation is a read-only sensor and which would be an
  actuator.

## Outputs and durable records

- Produce an Option B Issue graph: repository initiative or Epic set, Epic
  Issues, Task Issues, pull requests, commits, checks, and evidence.
- Record goals, non-goals, dependencies, acceptance criteria, ownership,
  risks, verification, routing constraints, and completion relationships.
- Record rationale for every material replan and link replaced or added work.
- Keep a GitHub Projects board optional; it is never planning authority.

## Procedure and chronology

1. Verify context freshness and accepted agreements before decomposition.
2. Outline Epics broadly, then decompose only the next useful frontier into
   reviewable Tasks.
3. Partition ownership before parallel dispatch and serialize unavoidable
   overlap.
4. Validate dependency links, acceptance evidence, risk, and exact file or
   external-state ownership.
5. Observe external state read-only, prepare intent and a dry-run difference,
   obtain approval for an actuator, apply it explicitly, and read back the
   result.
6. Replan from durable facts when scope, order, authority, or evidence changes.

## Failure states, escalation, and human gates

- Stop on stale context, dependency cycles, ownership overlap, missing
  authority, incompatible acceptance criteria, or an uncheckable actuator.
- Return to human judgment for agreement changes, Epic scope expansion,
  high-risk work, new external actuators, or changed acceptance meaning.
- Ordinary rolling-wave additions may proceed only inside the approved Epic,
  with low or normal risk, disjoint ownership, and no agreement change.

## Verification

- Read every created or edited Issue back and compare its relationships and
  body with the proposed plan.
- Confirm the frontier contains only unblocked, adequately specified Tasks.
- Confirm each Task can be verified independently and does not imply
  repository completion.

## Capability boundaries

This Skill is planning guidance. It does not itself create Issues, labels,
boards, Rulesets, or branches; those are explicit actuators. It does not
implement live runtime routing, an execution envelope, loop events, a runtime
adapter, an installer, or an authenticated supervisor identity.
