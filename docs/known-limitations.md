# Known limitations

Observed and documentation-derived statements are current through
`2026-08-26`. Phase 0 is complete. This tree satisfies the **Phase 1
portable-core implementation gate**. Its committed status is a creation-time
snapshot. The current durable owner-acceptance outcome is external GitHub state
authoritative in Issue #12 and Epic #2; a later post-merge outcome is not
embedded in this tree.
The overall repository implementation remains incomplete, the repository is
not installable, and it is not a parity release. `release_blocked` remains `true`.

## The portable core is not the operating harness

Phase 1 now contains the Option B agreement, frozen/live policy split,
conformance catalog, pinned CI/toolchain policy, Epic/Task/PR ledger templates,
connector-neutral context contracts, and all eight repository Skills. These
are static repository contracts and accepted external-state receipts, not a
universal runtime control plane.

The six custom agents, hooks, execution envelope, loop-event schema, CLI
adapter, installer/upgrade, live Task ritual, consent feedback transport,
runtime probes, and adopter migration are not implemented. A constitution,
Skill, schema, manifest, or green generic CI run does not make those controls
active and does not prove an individual conformance scenario.

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

## Machine-readable execution is not deterministic execution

`codex exec --json` emits JSONL events, but model behavior is not deterministic.
`--output-schema` constrains the final model response; it does not define or
validate the full JSONL event stream. No exhaustive versioned event schema was
found in official documentation.

The later adapter must pin the Codex CLI version, preserve safe raw unknown
events, normalize only recognized fields, and treat interrupted streams as
incomplete. Resume IDs are opaque until a named-client probe verifies Task
binding and compatibility.

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
