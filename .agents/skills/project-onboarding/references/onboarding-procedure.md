# Onboarding procedure

Read this resource only for a new adoption, a legacy migration, or an explicit
re-tuning pass.

## P0 — Status

Identify whether the repository is new, previously tuned, partially tuned, or
legacy. Record the default branch, current head, dirty state, remotes, active
work, and missing authority. Do not infer completion from file presence.

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

## P3 — Verify by running

Run the repository's documented deterministic checks safely and capture
bounded results. Record missing, failing, `UNKNOWN`, and `UNCHECKABLE` states
as non-success. Do not repair unrelated failures during inventory.

## P4 — Apply

For each approved change, show the exact target and difference. Treat files as
repository actuators and GitHub mutations as external actuators. Preserve
adopter-owned data and tuned surfaces. T09 supplies no installer, so apply
through separately reviewed repository work.

## P5 — Prove

Re-run relevant checks, inspect the final diff, and re-read external state.
Bind evidence to the exact commit, tree, and check URLs. Validate that required
contexts keep their reviewed names.

## P6 — Record

Put durable outcomes in the Issue graph and reviewed repository artifacts.
Record limitations and deferred proof. Never reconstruct old plan comments,
labels, approvals, or chronology as if they happened.

## Legacy and re-tuning path

Treat existing repository conventions as adopter truth until explicitly
superseded. Prefer additive proposals and migrations with rollback. During
re-tuning, compare current effective behavior with the prior accepted intent,
preserve local customization, and ask again before broadening permissions or
external automation. Before a semantic migration in a legacy repository,
propose characterization tests that capture current observable behavior and
have the owner review the intended compatibility boundary.
