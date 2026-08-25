---
name: project-onboarding
description: Assess and propose repository onboarding safely. Use when adopting or re-tuning this kit. Do not use for ordinary feature implementation.
---

# Project Onboarding

Establish an evidence-backed onboarding proposal without silently tuning the
repository. Read the [onboarding procedure](references/onboarding-procedure.md)
before changing any adopter surface.

## Inputs

- Obtain the repository URL, default branch, objective, existing governance,
  code and documentation inventory, and named human authority.
- Identify current Issues, pull requests, checks, Rulesets, secrets exposure
  risk, context sources, and any legacy conventions that must be preserved.
- Separate observable facts from preferences that require an interview.

## Outputs and durable records

- Produce a read-only inventory with evidence references and gaps.
- Produce explicit onboarding intent, deferred items, risk, and a dry-run diff
  for each proposed actuator.
- Propose the repository initiative or Epic set and initial Epic Issues without
  fabricating historical records.
- Record verification and read-back evidence only after authorized changes.

## Procedure and chronology

1. Follow status, inventory, interview, verify-by-running, apply, prove, and
   record in that order.
2. Keep inventory and verification sensors read-only.
3. Ask only decisions that observation cannot answer.
4. Apply bounded changes only after the relevant human approval.
5. Re-read effective repository and GitHub state, then record exact evidence.

## Failure states, escalation, and human gates

- Stop on ambiguous authority, destructive migration, secret exposure,
  unsupported branch governance, or a conflict with adopter truth.
- Escalate agreement changes, broad permission changes, and irreversible
  cleanup.
- Do not treat repository access, a prompt, or a previous installation as
  consent.

## Verification

- Compare every proposed change with the original inventory and approved
  intent.
- Confirm checks and branch governance from effective GitHub state.
- Confirm tuned surfaces preserve adopter-owned truth and that repository
  completion remains separately gated.

## Capability boundaries

This Skill does not provide an installer or upgrade mechanism and does not
enable broad automation. It does not authenticate roles, guarantee hooks,
create a runtime adapter, or prove cross-surface execution. It produces an
onboarding procedure and bounded proposals only.
