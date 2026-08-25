---
name: retro
description: Convert failures into stronger controls. Use after recurrence, a material incident or rejected PR, or scheduled hygiene. Do not use for one-off repair or feedback transport.
---

# Retrospective Strengthening

Turn repeated, linked failures into the smallest durable mechanism that would
have prevented recurrence.

## Inputs

- Collect two durable occurrences of the same failure class, or one material
  incident, rejected agent-authored pull request, or scheduled hygiene finding
  that warrants immediate review.
- Read the affected Task, pull request, acceptance evidence, agreements,
  checks, and existing candidate Issue before proposing a new record.
- Identify whether the cause is missing knowledge, a weak procedure, a missing
  deterministic guard, or an external platform limitation.

## Outputs and durable records

- Link occurrences to one candidate Issue rather than duplicating candidates.
- Propose the smallest suitable asset: agreement clarification, Skill change,
  deterministic test or checker, template adjustment, or documented
  limitation.
- Record rationale, affected scope, verification, limitations, and the
  reviewed pull request for an accepted improvement.
- When a platform capability checkpoint matters, record the named client or
  surface, version, observation date, evidence class, and bounded reference;
  do not generalize one observation to other surfaces.

## Procedure and chronology

1. Search the Issue graph for an existing candidate.
2. Record a first ordinary occurrence without changing the harness
   immediately; link the second before promotion.
3. For a material incident or rejected agent pull request, record why immediate
   promotion is warranted. During scheduled hygiene, identify stale always-on
   guidance for demotion as well as missing controls.
4. Classify the root cause and select the narrowest preventative asset.
5. Add a deterministic regression first when the failure can be reproduced.
6. Propose the change, obtain the required human review, verify it at the exact
   head, and read the durable result back.
7. Link the accepted mechanism to all known occurrences and defer unrelated
   improvements.
8. Use one Option-B candidate Issue as the retrospective index: link every
   occurrence, the reviewed pull request and accepted mechanism, and any
   optional upstream or adopter Issue. Do not create a separate retro log,
   fabricate upstream delivery, or auto-promote the candidate.

## Failure states, escalation, and human gates

- Stop if occurrences are unrelated, an immediate-promotion rationale is
  missing, the proposal embeds a private payload, or the change exceeds the
  candidate's scope.
- Escalate changes to canonical invariants, human authority, broad
  permissions, or security/privacy policy.
- A human approves changes that alter how future agents work.

## Verification

- Reproduce the prior failure where safe and prove the new mechanism rejects
  it.
- Run unaffected checks and confirm the improvement does not fabricate past
  chronology.
- Bind evidence to the exact pull-request head and record any platform proof
  that remains unavailable.
- For platform observations, verify client or surface, version, date, evidence
  class, and limitation before using the checkpoint in a proposal.

## Capability boundaries

This Skill defines a retrospective procedure only. It does not implement
consent or feedback transport, automatic issue promotion, an installer,
authenticated roles, hooks, runtime events, or repository completion. One-off
failures may justify a direct fix, but do not justify a recurring-harness
claim.
