---
name: project-onboarding
description: Assess and propose repository onboarding safely. Use when adopting or re-tuning this kit. Do not use for ordinary feature implementation.
---

# Project Onboarding

Establish an evidence-backed onboarding contract without silently tuning the
repository. Read the [onboarding procedure](references/onboarding-procedure.md)
before proposing or guiding any adopter change. This Skill ships no installer
or automatic actuator. It may guide and verify a separately owned, explicitly
approved onboarding application; it does not own or silently perform that
application.

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
- Produce review-only repository initiative or Epic-set and initial Epic-body
  proposals; do not create Issues or invoke GitHub actuators.
- Record clean-checkout command evidence and distinguish run, failed,
  `UNKNOWN`, `UNCHECKABLE`, and unrun commands.
- Produce an evidence PR or a durable blocked-PR receipt with the exact creation
  command; never convert a blocked state into success.
- Record all unfinished work in the durable deferred ledger and hand the
  accepted state to the first approved Epic/Task frontier.

## Procedure and chronology

1. Resolve the remote default branch and the exact kit-baseline reachability
   before any application or GitHub actuator.
2. Keep status, inventory, interview, intent, and command discovery read-only.
3. Verify candidate commands in a clean checkout and record the complete
   execution tuple before allowing any command into durable guidance.
4. Let only the separately owned, explicitly approved application perform a
   bounded repository or GitHub change; guide it from reviewed intent.
5. Re-run checks, inspect the exact diff, and read external state back.
6. Create the evidence PR or durable blocked-PR receipt, write the deferred
   ledger, and publish the Codex-native durable frontier handoff.

The following gates are mandatory whenever application is performed:

- Do not perform any GitHub write, including labels, Ruleset changes, or Epic
  creation, until the kit baseline is reachable from the remote default branch.
- For every candidate command, record the exact command, environment
  prerequisites, runtime, and result from a clean checkout.
- Never promote an unrun command.
- Onboarding is not complete until an evidence PR exists or an exact blocked-PR
  receipt and creation command are durably recorded.
- Write every unfinished or unverified item to a durable
  `## Deferred from onboarding` ledger in the first active Epic or evidence PR.
- Chat is not a carrier for deferred work.
- Replace the source Project-session step with a Codex-native durable handoff to
  the first approved Epic/Task frontier.

## Failure states, escalation, and human gates

- Stop on ambiguous authority, destructive migration, secret exposure,
  unsupported branch governance, or a conflict with adopter truth.
- If the baseline is absent from the remote default branch, keep any continued
  work read-only and stop all application and GitHub writes.
- Treat an unrun command, missing evidence PR, absent durable blocked receipt,
  or missing deferred ledger as non-success.
- Escalate agreement changes, broad permission changes, and irreversible
  cleanup.
- Do not treat repository access, a prompt, or a previous installation as
  consent.

## Verification

- Confirm the remote default branch reaches the exact kit baseline before the
  first GitHub write.
- Compare every proposed change with the original inventory and approved intent.
- Check every promoted command against its clean-checkout command,
  prerequisites, runtime, and result record.
- Confirm checks and branch governance from effective GitHub state.
- Confirm the evidence PR or exact durable blocked-PR receipt, deferred ledger,
  and first approved Epic/Task frontier handoff exist on durable carriers.
- Confirm tuned surfaces preserve adopter-owned truth and repository completion
  remains separately gated.

## Capability boundaries

This Skill does not provide an installer, upgrade mechanism, automatic
actuator, authenticated role, guaranteed hook, runtime adapter, live Project
session, or cross-surface execution proof. It produces intent and evidence and
may guide and verify a separately owned, explicitly approved application. The
application owner retains mutation responsibility, and the human retains the
agreement and acceptance gates.
