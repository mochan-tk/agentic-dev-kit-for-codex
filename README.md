# Agentic Development Kit for Codex

> [!WARNING]
> **Current status:** Phase 0 is complete. This tree satisfies the **Phase 1 portable-core implementation gate**.
> The current durable owner-acceptance outcome is external GitHub state, authoritative in [Issue #12](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12) and [Epic #2](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2); this immutable tree records only its creation-time snapshot and does not embed a later post-merge outcome.
> Accepted [T11 / Issue #23](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23) delivers a deterministic offline execution harness. Live qualification in [T12 / Issue #25](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25) and PR #26 is paused, open, and unaccepted. It is not a prerequisite for the separately approved source-first local installation in [T14 / Issue #27](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/27).
> Stage A.1 and Stage A.2 remain bounded non-success evidence. Stage A.1
> qualified only its narrow prerequisite set; Stage A.2's aggregate profile was
> `UNCHECKABLE`, with shell-environment `fail` and sandbox/network
> `UNCHECKABLE`. No successful real Codex worker or applied runtime receipt is
> claimed.
> The overall repository implementation remains incomplete. The source-first kit supports local-source installation; it is not a parity release.
> `release_blocked` remains `true`.

This project is the Codex-native edition of the governed agentic-development
harness in
[`mochan-tk/agentic-dev-kit-for-copilot`](https://github.com/mochan-tk/agentic-dev-kit-for-copilot).
It preserves product-independent behavior and governance while building
toward later verified Codex-native replacements for Copilot-specific execution
surfaces. The usable local-source payload reuses the source workflows with
minimal Codex adaptations, independently of the bounded offline adapter.
Broader runtime qualification, cross-surface parity, automatic upgrades, and
a release distribution system remain incomplete.

The frozen behavioral source is commit
[`fd265ddef150fab86cd54d0e383c2c25fe297ffb`](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/commit/fd265ddef150fab86cd54d0e383c2c25fe297ffb).
The port does not copy the source wholesale and does not silently reproduce
known source defects.

## Install the source-first kit locally

Review a local checkout, then run the explicit dry-run before applying to an
existing adopter Git repository that you own exclusively during installation:

```sh
bash .github/scripts/scaffold-init.sh --dry-run /path/to/adopter
bash .github/scripts/scaffold-init.sh --apply /path/to/adopter
```

Windows uses the adjacent `scaffold-init.ps1` Git Bash entrypoint with the same
arguments. No download, VM, authentication, automatic Git init/stage/commit, or
GitHub write occurs. The payload contains eight source-derived Skills, three
native Codex role definitions, issue/PR templates, optional explicit helpers,
and empty adopter agreement/context seeds. Existing tuned and adopter-owned
files are preserved; conflicting engine files and symlinks are refused.

Inspect the changes, commit/push them yourself, and invoke
`$project-onboarding` in Codex. Read the
[installer guide and limits](docs/distribution/source-first-installer.md).
The kit-development `AGENTS.md`, Task IDs, context pins, sole-active ownership
policy, and Colima qualification infrastructure are never exported.

### Preserve configuration while updating, or undo just one update

Use reviewed local old/new distribution roots with the same fixed 47-file
inventory. Only exact known-old engine bytes/modes are replaced; existing
tuned/instance/seed files remain yours. Select a new private operation directory
outside both sources and the adopter (its parent must already exist):

```sh
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --dry-run /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --apply /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --dry-run /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --apply /path/to/adopter
```

Keep the private operation record/backups. Rollback is not a repository reset:
unrelated later edits stay, while edits to affected files refuse the entire
preflight. No force or automatic rollback is available. Supported interrupted
apply recovery is tested in disposable local fixtures, not a power-loss or
concurrent-writer guarantee. See the guide for exact refusal and recovery rules.

## Durable operating model

```text
Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence
```

The Issue graph is durable truth. A repository initiative / Epic set is a
durable repository objective with explicitly linked Epic issues; a single Epic
issue may serve as the root. A GitHub Projects board is an optional projection. It never outranks the Issue graph.
Codex threads and subagents are execution contexts, not the hierarchy. One Task
has one active supervisor responsibility; one PR has one active writer, branch,
and worktree. Completion requires current acceptance evidence, not an agent
narrative.

The authority decision and its alternatives are recorded in
[ADR-0005](docs/agreements/adr/ADR-0005-issue-graph-authority.md). The
[repository-level definition of done](docs/agreements/repository-completion.md)
defines the overall completion gate.

The reviewed invariant table lives in [`AGENTS.md`](AGENTS.md). The initial
audit and file-ownership plan lives in
[`docs/planning/phase-0-orientation.md`](docs/planning/phase-0-orientation.md).

## What the accepted foundation provides

- a compact, product-independent operating constitution;
- exact source commit, tree, research-pack, and scenario-catalog provenance;
- a machine-readable conformance manifest with an explicit release blocker;
- a dated Codex capability audit that separates documented behavior from
  local and cross-surface verification;
- prominent known limitations;
- offline negative tests for baseline, invariant, workflow, and ownership
  drift;
- minimal SHA-pinned, least-privilege `quality` and `conformance` CI jobs.

The Phase 1 portable core adds:

- the accepted Option B hierarchy and repository-completion agreement;
- a frozen Phase 0 verifier plus an extensible, fail-closed live policy;
- the complete, provenance-bound 136-scenario catalog;
- exact pinned CI tools, semantic permissions checks, and deterministic
  repository-wide test discovery;
- synchronized Epic, Task, and pull-request ledger contracts;
- connector-neutral requirement, decision, and context-pin contracts;
- all eight repository Skills with source-to-target parity records; and
- a machine-readable acceptance package and human scorecard.

The current Phase 2 T11 tree adds, at a deliberately narrow offline evidence
level:

- three static role-definition files that are configuration layers, not
  authenticated identities or proof of native named-agent selection;
- minimal `task-execution-envelope/v1`, `loop-event/v1`, final-response,
  execution-result, runtime-profile, and runtime-receipt contracts;
- a deterministic Python controller, bounded JSONL/process/Git validation,
  a fresh deterministic verifier, and an append-only Task-receipt actuator;
- a frozen verifier for the exact accepted Phase 1 snapshot, separate from
  the Phase 2 live repository policy; and
- fake-process and synthetic-repository coverage reachable from required CI.

Together these form the deterministic offline harness. Its durable status is:

```text
runtime_harness = minimal-offline-implemented
live_codex_execution = deferred-to-T12
sandbox_compatibility = unresolved-non-success
runtime_receipt_apply = deferred-to-T12
Phase 2 = incomplete
repository = incomplete
release_blocked = true
```

Required CI proves only the offline/static boundary. The current Stage A.2
evidence remains non-success and is not rewritten as runtime-profile `match`,
sandbox compatibility, live-worker success, or receipt evidence. A real
`codex exec` worker, live compatibility qualification, receipt dry-run/apply,
and exact read-back are T12 acceptance work. T11 claims only deterministic
fixture-based receipt validation, dry-run, zero-write, idempotency, conflict,
and read-back behavior.

## What remains outside the portable core

- automated upgrades, rollback, or release installation;
- a final custom-agent topology or verified native named-agent selection;
- hooks, recovery orchestration, or a general runtime control plane;
- a production-complete execution envelope, loop-event protocol, or `codex
  exec` adapter beyond the bounded T11 slice;
- the live Task ritual, consent feedback transport, and general adopter
  governance activation;
- local/worktree/cloud parity claims;
- clean-adopter live runtime E2E, upgrade, and rollback evidence;
- authenticated runtime roles, universal heartbeat/budget/control, or
  automatic merge.

See [`docs/known-limitations.md`](docs/known-limitations.md) before relying on
any capability.

## Port sequence

1. **Phase 0:** constitution, audit provenance, limitations, conformance
   vocabulary, and bootstrap CI.
2. **Portable core:** GitHub ledger/contracts and all eight Codex repository
   Skills.
3. **Codex adapter:** accept the T11 deterministic offline Task envelope,
   event, controller/fake-worker/verifier, and receipt-validation harness; then
   use T12 to qualify live Codex compatibility and obtain an exact-head live
   receipt before hardening roles, recovery, hooks, and runtime parity.
4. **Source-first delivery:** local dry-run/apply and preservation are
   independent of paused live qualification. Automatic upgrade, Task ritual
   enforcement, and general governance activation retain their own evidence
   and approval boundaries.
5. **Parity release:** static and runtime probes, all 136 conformance
   scenarios, adopter migration, and independently reviewed evidence.

Phase 0 is complete. This tree satisfies the Phase 1 portable-core
implementation gate. The immutable tree records its creation-time acceptance
snapshot; Issue #12 and Epic #2 are the authoritative records for the current
durable acceptance outcome, including any later post-merge receipt. Later Tasks
remain subject to their own scoped evidence and owner merge gates. An
unavailable runtime probe is `unverified`, `not-run`, `UNKNOWN`, or
`UNCHECKABLE`, never passed.

For the runtime sensor, observable client drift is `profile-drift`, an
unsupported feature or unapproved prerelease is `unsupported-client`, and only
unobservable evidence is `UNKNOWN` or `UNCHECKABLE`. The committed task-start
alpha snapshot remains `unsupported-client`. The later Stage A.2 observation
also remains non-success; neither record is a successful live runtime result.
The approved [T11 agreement-v2 decision](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-5472720734)
makes AC-13 `deferred-to-T12-by-approved-agreement-replan`, not passed or
silently omitted.

## Repository completion boundary

No individual phase completion constitutes repository-level completion.
Task and Epic completion do not complete the repository either.
The overall repository implementation remains incomplete until every required contract has current target-side evidence and a human-reviewed completion pull request changing `release_blocked` to `false` is merged.
Until then, completed Tasks and Phases are accepted foundations within an
incomplete implementation, not a release claim.

## Repository validation

```sh
python3 -I .github/scripts/check-phase0-contracts.py
python3 -I .github/scripts/check-repository-policy.py
python3 -I .github/scripts/check-phase1-accepted-snapshot.py
python3 -I .github/scripts/check-runtime-contracts.py
python3 -I .github/scripts/check-portable-contracts.py
python3 -I .github/scripts/check-ledger-templates.py
python3 -I .github/scripts/check-skills.py
python3 -I .github/scripts/conformance-catalog.py check
python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'
bash .github/scripts/tests/test-action-pins.sh
bash .github/scripts/tests/test-workflow-permissions.sh
git diff --check
```

These are repository validation entry points, not a transport guarantee.
The static GitHub Actions workflow invokes its versioned CI subset. It is not claimed to be shell-free or network-free.
`git diff --check` is local evidence, not a GitHub Actions step. T11's
shell-free and network-bounded requirements
apply to its reviewed execution contract; [Issue #23](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23)
remains authoritative if broader shell or network terminology is ambiguous.

The frozen source's 23-suite result is baseline evidence, not target parity.
The Phase 1 scorecard inventories all 136 scenarios and records zero exact
scenario-action passes. The release-level result store remains empty. See the
[Phase 1 acceptance record](docs/planning/phase-1-acceptance.md) and
[scorecard](docs/conformance/phase-1-scorecard.md); their canonical standalone
machine package is
[`tests/conformance/results/phase-1.json`](tests/conformance/results/phase-1.json).

## License

Licensed under the [MIT License](LICENSE).
