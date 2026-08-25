# Onboarding procedure

Read this resource only for a new adoption, a legacy migration, or an explicit
re-tuning pass.

## P0 — Status

Identify whether the repository is new, previously tuned, partially tuned, or
legacy. Record the default branch, current head, dirty state, remotes, active
work, and missing authority. Do not infer completion from file presence.

Fetch and resolve the remote default branch, then prove that it reaches the
exact kit-baseline commit or its reviewed adoption commit. Distinguish a never
committed baseline, an unpushed commit, and a commit reachable only from a
non-default branch. If the baseline is not reachable, record the blocker and
resume instruction. Read-only assessment and proposal may continue, but all
application and GitHub actuators stop.

Do not perform any GitHub write, including labels, Ruleset changes, or Epic
creation, until the kit baseline is reachable from the remote default branch.

## P1 — Inventory

Observe repository structure, languages, build and test commands, governance
files, CI, permissions, branch Rulesets, Issues, pull requests, context
sources, and existing owner conventions. Keep this pass read-only. Cite exact
paths and external URLs; do not store environment dumps or private local
paths.

Maintain a Codex-native synchronization invariant among the documented local
commands, the versioned quality-command registry and workflow steps, and the
named execution-environment evidence. Observe and record current evidence
before proposing command changes. Onboarding aligns those surfaces; it does
not build product features or silently repair product behavior.

## P2 — Interview and intent

Ask for choices that observation cannot settle: objective, non-goals, context
authority, privacy constraints, human gates, accepted risk, model-neutral
execution expectations, and migration boundaries. Convert answers into a
versioned proposal, not an immediate mutation.

Produce durable review-only proposals for the repository initiative or Epic
set and initial Epic bodies from the approved objective and bounded material.
Mark them as proposals, preserve dependency order, and do not create Issues or
invoke GitHub actuators. Generalize source intake to connector-neutral source
references and a model-neutral execution preference; do not require a concrete
connector, upload surface, or runtime model selector.

## P3 — Verify by running

Use a clean checkout. Run candidate deterministic commands safely in dependency
order and capture bounded results. For every candidate command, record the exact
command, environment prerequisites, runtime, and result from a clean checkout.
Record missing, failing, `UNKNOWN`, and `UNCHECKABLE` states as non-success.
Capture a bounded failure and workaround when available, without repairing
unrelated failures during inventory. Never promote an unrun command.

## P4 — Apply

This Skill ships no installer or automatic actuator. Application belongs to a
separately owned and explicitly approved repository work item. The Skill may
guide that executor and verify its evidence; it does not assume writer or
actuator ownership.

Require the P0 remote-default precondition and every P3 evidence record before
application. For each approved change, show the exact target and difference.
Treat files as repository actuators and GitHub mutations as external actuators.
Preserve adopter-owned data and tuned surfaces. Stop before any target, scope,
permission, or authority not covered by the approval.

Do not assume the source scaffold's `CUSTOMIZE`, CODEOWNERS, source-activation,
model-block, or AGENTS application steps exist in the adopter. Map reviewed
intent to actual adopter surfaces, and leave every mutation to the approved
executor.

## P5 — Prove

Re-run relevant checks in the recorded environment, inspect the final diff,
and re-read external state. Confirm that documented commands, the versioned
quality-command registry, and workflow steps remain synchronized. Bind evidence
to the exact commit, tree, command record, and check URLs. Validate that
required contexts keep their reviewed names. Do not claim source-specific
tuning-status or cloud-setup workflow proof that was not run.

## P6 — Record

Put durable outcomes in the Issue graph and reviewed repository artifacts.
Create an evidence PR containing the inventory, approved intent, applied diff,
clean-checkout execution evidence, risks, and limitations. If PR creation is
blocked, record the blocker and exact creation command in the Issue graph and
keep the outcome explicitly blocked.

Put project-agnostic improvement observations in the evidence PR as bounded
candidate records. Do not append an absent retro-log, transmit feedback, or
open an upstream record automatically.

Onboarding is not complete until an evidence PR exists or an exact blocked-PR
receipt and creation command are durably recorded.

Collect every unfinished or unverified command, external operation, declined
consent, missing prerequisite, and deferred proof with its reason. Write every
unfinished or unverified item to a durable `## Deferred from onboarding` ledger
in the first active Epic or evidence PR. Chat is not a carrier for deferred
work. Never reconstruct old plan comments, labels, approvals, or chronology as
if they happened.

Replace the source Project-session step with a Codex-native durable handoff to
the first approved Epic/Task frontier. The handoff names the accepted evidence
PR or blocked receipt, the first approved Epic, the current Task frontier, its
dependencies, and the human gate for beginning work. Do not claim or create a
live Project session; live Task ritual and runtime orchestration are not
implemented. Work cannot begin from a half-applied onboarding state.

The following load-bearing contracts remain visible here and in `SKILL.md`:

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

## Legacy and re-tuning path

Treat existing repository conventions as adopter truth until explicitly
superseded. Prefer additive proposals and migrations with rollback. During
re-tuning, compare current effective behavior with the prior accepted intent,
preserve local customization, and ask again before broadening permissions or
external automation. Before a semantic migration in a legacy repository,
propose characterization tests that capture current observable behavior and
have the owner review the intended compatibility boundary.
