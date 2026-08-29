# Known limitations

Observed and documentation-derived statements are current through
`2026-08-28`. Phase 0 is complete. This tree satisfies the **Phase 1
portable-core implementation gate**. Its committed status is a creation-time
snapshot. The current durable owner-acceptance outcome is external GitHub state
authoritative in Issue #12 and Epic #2; a later post-merge outcome is not
embedded in this tree.
The overall repository implementation remains incomplete, the repository is
not installable, and it is not a parity release. `release_blocked` remains `true`.

## The minimal execution slice is not the operating harness

Phase 1 contains the Option B agreement, frozen/live policy split,
conformance catalog, pinned CI/toolchain policy, Epic/Task/PR ledger templates,
connector-neutral context contracts, and all eight repository Skills. These
are static repository contracts and accepted external-state receipts, not a
universal runtime control plane.

Phase 2 T11 adds three static role definitions, minimal envelope/event/final-
response/result/profile/receipt contracts, a deterministic Python controller,
bounded process and Git verification, an offline fake process, and an
append-only Task-receipt actuator. This is a minimal/partial offline slice. The
static TOML files do not prove native named-agent selection or identity, and
required CI cannot run real Codex, enter live mode, or apply a receipt.

The Task-start observation found `codex-cli 0.150.0-alpha.8`. That prerelease
is `unsupported-client` under the approved live gate. Consequently this tree
does not claim a completed live representative Task, a successful live runtime
profile, or a posted runtime receipt. A later exact-head owner-run observation
must be `match` on an approved supported non-prerelease before those actions
are permitted.

The approved live boundary is a new exact-head T11-only Colima Linux VM using
VZ and native `aarch64`, not the everyday host Mac. The historical task-start
profile predates that decision, so its provider lane remains `not-run` with
non-claiming sentinels rather than fabricated Colima/VM evidence. A live
`match` requires official stable `codex-cli 0.150.1`, the approved archive and
extracted-binary digests, exact public head/tree, a clean guest clone, passing
configuration/network/process probes, and a closed mount inventory. Colima's
one unavoidable attempt-only provider-cache mount must be read-only; any other
shared mount blocks the run. Provider evidence is adapter/owner-authored, not
a Codex-authenticated attestation.

The closed control-plane record also requires pre-create profile/runtime-data
absence, no reuse of an existing VM, container, volume, default profile, or
additional disk, unchanged activation context, and private-VM-disk placement
for the clone and runtime root. Its digest covers normalized safe fields only;
raw paths and provider configuration remain local transport.

Receipt application happens before the disposable VM is destroyed. The
receipt therefore records only the destruction obligation and does not claim
destroy completion or profile absence. Those outcomes require a later
append-only read-back after the attempt. Until that record exists, destruction
evidence is incomplete rather than implicitly successful.
The separate lifecycle actuator binds the already-posted runtime receipt and
its GitHub creation time, exact PR #24 head/tree/checks, destroy chronology,
and both profile/runtime-data absence read-backs. It regenerates the exact
canonical runtime-receipt body from the original validated native request;
caller-authored marker/body text is not proof. Every lifecycle timestamp is
bounded to at most 300 seconds of future skew and the latest absence read-back
must be no more than 3600 seconds old at validation. A runtime receipt by
itself does not prove teardown. T11 permits one durable runtime receipt: only
an exact same-attempt receipt is idempotent, while a different attempt is a
closed conflict rather than a second receipt.

`codex doctor --json` is treated only as a redacted diagnostic support report.
It does not expose or attest the exact T11 override set. The documented config
keys and their stable digest are adapter-authored intent evidence with
`effective_configuration_proven=false`; separate behavior probes and exact
worker-argv validation are still required. Live argv does not use
`--ignore-rules` or a `--dangerously-bypass-*` flag.

The final six-role topology, native runtime routing, hooks, recovery,
installer/upgrade, live generalized Task ritual, consent feedback transport,
cross-surface runtime probes, and adopter migration remain incomplete. A
constitution, Skill, schema, manifest, static role file, or green offline CI
run does not make those controls active and does not prove an individual
conformance scenario.

The release-level conformance result set is empty and `release_blocked` is
true. The Phase 1 scorecard inventories 136 scenarios, all `not-run`, with zero
scenario-action passes. Source CI, source test results, static target tests,
and family aggregates are related evidence only; they are not a substitute
for executing each scenario's exact action.

The Phase 0 workflow guards intentionally accept only the reviewed canonical
block-style YAML shape and fail closed on unsupported syntax. They are not a
general YAML parser. The exact Phase 0 workflow digest is an accidental-drift
tripwire, not an authenticity root; canonical structure checks, focused
negative tests, external `actionlint`, independent review, and branch policy
remain separate layers.

## Roles and identifiers are not authenticated identity

A custom-agent name, TOML file, declared role, issue comment, thread ID,
session ID, or subagent `agent_id` is not authenticated identity. These values
can be useful receipts, but receipts are not authority. GitHub permissions,
the current PR head, deterministic checks, independent review, and human
acceptance remain authoritative.

The source ritual itself cannot verify that a declared worker session exists.
The target will not describe a comment trail as proof of a live or unique
runtime actor.

## Sandboxes do not enforce Task ownership

Custom-agent sandbox configuration is a default layer. Official OpenAI
documentation states that a parent turn's live permission overrides are
reapplied to a child. `read-only` and `workspace-write` reduce capability but
do not bind an agent to a GitHub Task, ownership glob, branch, or assigned
worktree.

Ownership and single-writer safety therefore require deterministic diff,
branch, envelope, and CI checks in addition to role configuration.

Reference: [Subagent approvals and sandbox controls](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls).

## Hooks are defense in depth

Project hooks require repository trust and exact-definition review. Changed
non-managed hooks are skipped until trusted. Matching command hooks can run
concurrently; only command handlers execute today. Hosted tools and some
specialized tool paths do not pass through local tool hooks.

`SubagentStart` cannot veto creation through `continue: false`. `SessionEnd` is
advisory, runs only for the main thread, and cannot keep a session open or
require a handoff. Unsupported `PreToolUse` output can fail while the tool call
continues. A target parser may reject malformed input, but a platform hook
configuration or parse failure is not a universal fail-closed boundary.

Hooks will supplement, never replace, final ownership and CI validation.

Reference: [Official hooks documentation](https://learn.chatgpt.com/docs/hooks).

## `AGENTS.md` behavior differs by surface

Local Codex builds its project instruction chain once per run, from the Git
root to the startup working directory. A nested `.github/AGENTS.md` does not
automatically apply merely because a root-started task edits a workflow file.
GitHub Code Review has separate file-specific guidance discovery. These
surfaces require separate probes.

Reference: [Official AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md#how-codex-discovers-guidance).

## Skills and custom agents are not cross-surface verified

Repository Skill discovery is documented for local desktop, CLI, and IDE
clients. Project custom-agent TOML is documented for local clients. Cloud,
GitHub review, and Action loading of repository Skills, custom agents, or local
hooks is unverified. There is no documented Skill preload field, and
`templates/` is not a documented special Skill resource directory.

Duplicate Skill names may both appear in Codex; rejecting duplicates is a
stricter target policy, not native behavior.

References: [Build Skills](https://learn.chatgpt.com/docs/build-skills) and
[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## The bounded adapter does not make model execution deterministic

`codex exec --json` emits JSONL events, but model behavior is not deterministic.
`--output-schema` constrains the final model response; it does not define or
validate the full JSONL event stream. No exhaustive versioned upstream event
schema was found in official documentation.

The T11 adapter therefore normalizes only bounded recognized semantics and
treats unknown, malformed, conflicting, interrupted, excessive, or
inconsistent streams as non-success. Its offline tests use a fake process and
synthetic repositories. They do not prove that the currently installed alpha
client can safely execute the live profile. Resume behavior remains outside
the T11 slice and unverified.

Reference: [Official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

## Worktree and cloud controls remain application-level

Managed worktrees start detached and need a branch before ordinary push/PR
work. Git permits a branch to be checked out in only one worktree. Native
snapshot/restore behavior does not establish a target policy that blocks
archive before evidence.

Cloud environment identity, setup revision, internet posture, secret handling,
branch, PR, and check receipt fields are target contracts and remain
unverified as an automatic platform receipt. No cross-surface verification has
been completed.

References: [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)
and [cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment).

## No universal runtime control plane

This repository does not provide immutable actor identity, authoritative
heartbeat, universal pause/resume/cancel, time/token/credit budget circuit
breakers, a unified live supervision console, or authenticated state
transitions across every Codex surface.

It also does not initially provide broad auto-merge or autonomous delegation
to external contributors. These require a separately reviewed identity and
control plane, GitHub permissions, Rulesets, and a threat model.

## SDK, Action, review, and plugins remain optional

The SDK is deferred until the CLI and event-normalization contract is stable.
GitHub Code Review is additional code-quality evidence, not governance review.
The Codex GitHub Action must be pinned by full Action SHA and explicit Codex CLI
version; read-only mode alone is not a secrets boundary.

Plugin support is documented, but plugin-only distribution is deferred until
repository activation, update, removal, and every claimed surface are proven.
The portable repository installer remains the planned initial authority.

References: [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk),
[GitHub integration](https://learn.chatgpt.com/docs/third-party/github), and
[Codex GitHub Action](https://learn.chatgpt.com/docs/github-action).

## Model-neutral core

Core contracts, role identity, issue schemas, installer behavior, and
acceptance logic are model-neutral. Model availability and names change. A
selected model belongs in a dated runtime/evaluation ledger and must not alter
the governance contract.

## Source defects are not silently reproduced

The frozen source contains known stale references, an overstated changelog
reference guard, a floating source-only MCP dependency, and additional guard
gaps recorded in the Phase 0 orientation. Each later port must either fix the
behavior with regression evidence or describe the remaining limitation
exactly.
