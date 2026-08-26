---
name: task-routing
description: Recommend a bounded execution route from evidence. Use when a planned Task needs placement. Do not use to claim runtime support or dispatch.
---

# Task Routing

Recommend an execution surface and review path from current evidence. Keep the
recommendation separate from dispatch.

## Inputs

- Read the Task objective, acceptance criteria, ownership, dependencies,
  sensitivity, risk, local dependencies, expected parallelism, and reasoning
  needs.
- Observe named-client capabilities, versions, dates, permissions, and data
  boundaries when those facts matter.
- Read existing routing constraints and failures from durable Task records.

## Outputs and durable records

- Record a routing recommendation, rationale, required capabilities, risk,
  fallback, reviewer needs, and unresolved evidence in the Task plan.
- Record observed client, version, date, and evidence class for any capability
  claim.
- Keep route metadata opaque to future execution-envelope or event contracts.

## Procedure and chronology

1. Classify ambiguity, local dependency, parallelism value, sensitivity,
   reasoning depth, mutation scope, and review risk.
2. Match requirements only to capabilities observed for the named surface.
3. Derive review needs from ambiguity, risk, sensitivity, evidence quality,
   agreement impact, and mutation scope. Require human review when authority or
   judgment is retained; use a dated named-client advisory review only when
   its client, version, date, and evidence class are recorded.
4. Reject any route that cannot enforce ownership, data, or approval bounds.
5. Record the recommendation and fallback before dispatch.
6. Obtain human approval for high-risk or externally mutating routes.
7. Let the authorized supervisor perform dispatch and read back durable state.
8. Re-route only after releasing the prior writer and recording why the route
   failed.

## Failure states, escalation, and human gates

- Use `UNKNOWN` for unavailable capability state and `UNCHECKABLE` when the
  observation cannot be trusted. Both block routing that depends on it.
- Stop on privacy conflict, unsupported hardware, broad permissions,
  overlapping writers, or an unbounded external actor.
- Escalate high-risk exceptions and any request to send sensitive material
  outside its approved boundary.

## Verification

- Check that every required capability is supported by current named evidence
  rather than product assumptions.
- Confirm route, ownership, branch, data boundary, and reviewer path are
  mutually compatible.
- After authorized dispatch, verify the durable Task/PR relationship; command
  submission alone is not proof.

## Capability boundaries

This Skill does not dispatch work or implement live runtime routing. It makes
no cross-surface support guarantee and provides no cloud, SDK, worktree,
custom-agent, hook, envelope, event, or adapter implementation. Model choice
does not grant authority. The frozen source's custom reviewer, Rubber Duck,
and role-picker behavior is deferred; this Skill records a review need and
observed advisory capability, but does not instantiate a reviewer role.
