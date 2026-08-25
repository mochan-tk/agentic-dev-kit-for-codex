---
name: verification
description: Verify acceptance against exact current evidence. Use when defining Verification sections, triaging CI, or judging a Task or pull request. Do not use to approve agreements or final completion.
---

# Verification

Test the current implementation against its durable acceptance contract and
report non-success states honestly.

## Inputs

- Read the Task acceptance criteria, verification commands, ownership, risk,
  dependencies, cited requirements and decisions, and pull request.
- Resolve the exact current head, tree, diff, required checks, and effective
  external state relevant to acceptance.
- Identify evidence that is deferred, unavailable, advisory, or human-only.
- Prefer acceptance criteria encoded as a failing deterministic test before
  implementation. When that is impossible, record the observable evidence and
  human gate instead of pretending prose is executable.

## Outputs and durable records

- Produce a criterion-by-criterion evidence table with command or observation,
  exact target, result, and bounded reference.
- Record failures, drift, `UNKNOWN`, `UNCHECKABLE`, deferred evidence, risks,
  and limitations without converting them to success.
- Bind pre-merge evidence to the current head and post-merge evidence to the
  exact merge commit and tree.

## Procedure and chronology

1. Validate that the acceptance criteria are current and testable; establish
   the measuring test before implementation where feasible.
2. For implementation work, run the documented local deterministic checks and
   let the required CI jobs establish their authoritative repository record.
   For reviewer verification, read the current CI/check records first and
   rerun only evidence that is missing, stale, contradictory, or not equivalent
   to the acceptance environment.
3. Run applicable security checks without exposing raw logs or credentials.
4. Use AI review as advisory evidence and separate its findings from
   deterministic results.
5. Inspect ownership, diff, permissions, and required-check reachability.
6. Classify a CI failure before repair: fix an environment failure at its
   environment boundary, fix a defect in the implementation, and stop for
   replan on a specification mismatch. Never weaken the wall to make it green.
7. Map each criterion to current evidence; rerun only evidence that fails the
   currentness or equivalence test.
8. Present the bounded record for human judgment and read back any accepted
   outcome.

## Failure states, escalation, and human gates

- Treat missing, stale, failed, deferred, `UNKNOWN`, and `UNCHECKABLE` evidence
  as non-success.
- Stop on head changes during verification, out-of-scope diff, disabled or
  skipped required checks, or fabricated evidence.
- Diagnose whether the work order, plan, diff, or evidence/check quadrant is
  wrong before changing anything; each has a different durable owner.
- Humans retain agreement approval, high-risk exceptions, final Task
  acceptance, and repository completion authority.

## Verification

- Verify evidence URLs and check results are bound to the same exact head.
- Confirm required job names remain `quality` and `conformance` when they are
  part of the Task contract.
- Re-read merged state before issuing a post-merge receipt.

## Capability boundaries

This Skill verifies; it does not merge, approve an agreement, or change
external state. It does not implement authenticated review roles, hooks, an
execution envelope, loop events, a runtime adapter, an installer, or a
repository-level completion decision.
