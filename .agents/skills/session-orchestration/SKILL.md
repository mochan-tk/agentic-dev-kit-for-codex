---
name: session-orchestration
description: Coordinate durable Task attempts and recovery. Use when supervising bounded execution contexts. Do not use as a runtime identity guarantee.
---

# Session Orchestration

Coordinate replaceable execution contexts around durable GitHub records. Read
the [orchestration protocols](references/orchestration-protocols.md) before
dispatch, replacement, or recovery.

## Inputs

- Read the exact Task Issue, plan, acceptance criteria, dependencies,
  ownership, risk, routing constraints, current branch and pull request, and
  fresh context pin.
- Identify the one active supervisor responsibility and the one active writer,
  branch, and worktree for the Task.
- Treat threads, sessions, subagents, and worktrees as replaceable contexts,
  never as durable authority.

## Outputs and durable records

- Record or verify a durable Task plan before implementation.
- Record bounded dispatch intent, execution-context references when useful,
  current-attempt evidence, outcome, blockers, deviations, and exact-head
  verification in the Issue graph or pull request.
- Release failed or abandoned attempts before authorizing replacements.

## Procedure and chronology

1. Claim the Task responsibility and verify plan, ownership, base, and branch.
2. Choose or confirm a bounded route without claiming unsupported runtime
   capabilities.
3. Dispatch one writer or record a reviewed trivial-task exemption.
4. Monitor durable evidence and bounded progress, not private transcript
   content.
5. Steer unchanged scope; replan changed scope through plan management.
6. Verify acceptance at the current head before recording the outcome.
7. On crash or replacement, rebuild state from GitHub and committed files,
   release the old attempt, and continue with a new bounded context.

## Failure states, escalation, and human gates

- Stop on ownership overlap, stale context, missing authority, conflicting
  writers, destructive recovery, or `UNKNOWN`/`UNCHECKABLE` acceptance state.
- Escalate agreement changes, high-risk exceptions, repeated failures that
  exhaust bounded alternatives, and final acceptance.
- Human authority is retained even when execution is monitored asynchronously.

## Verification

- Confirm plan-before-work chronology from durable timestamps and links when
  available; do not fabricate missing historical records.
- Confirm the branch diff stays within owned paths and the result is bound to
  the exact head, tree, and checks.
- Confirm a replacement does not leave two active writers or supervisors.

## Capability boundaries

This Skill is procedural guidance. It does not authenticate a supervisor,
worker, role, thread, or worktree; enforce a live Task ritual; implement an
execution envelope or loop-event schema; or provide a runtime adapter. A
thread ID or prompt is not a security boundary.
