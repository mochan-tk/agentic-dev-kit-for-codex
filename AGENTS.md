# Operating constitution

This file governs every agent and execution surface working in this
repository. GitHub records and committed files are authoritative; prompts,
threads, subagents, local transcripts, and model memory are replaceable
transport. If a lower-precedence instruction conflicts with this constitution,
stop the affected work and record the conflict.

Phase 0 is complete.
This tree satisfies the Phase 1 portable-core implementation gate.
The current durable acceptance outcome is external GitHub
state authoritative in Issue #12 and Epic #2; this immutable tree records only
its creation-time snapshot. The Epic, Task, and pull-request ledger contracts,
connector-neutral context contracts, and all eight repository Skills exist.
Custom agents, hooks, task-execution-envelope/v1, loop-event/v1, the
`codex exec` adapter, installer/upgrade, the live Task ritual, runtime parity,
and release remain incomplete. The overall repository implementation remains
incomplete, and `release_blocked` remains `true`.

## Canonical invariants

The statement column is canonical. CI hashes sorted UTF-8 lines in the form
`ID<TAB>statement<LF>` and rejects drift from the reviewed digest.

| ID | Statement |
|---|---|
| I01 | GitHub is durable truth; thread and session history are replaceable transport. |
| I02 | The Issue graph (repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence) is canonical; a GitHub Projects board is an optional projection and never outranks it. |
| I03 | One Task has one active supervisor responsibility. |
| I04 | One PR has one active writer, branch, and worktree. |
| I05 | A durable record exists before a narrative report. |
| I06 | Acceptance evidence is verified before completion. |
| I07 | Overlapping ownership is blocked or serialized. |
| I08 | Unknown or uncheckable governance and evidence states fail closed. |
| I09 | Humans retain agreement, high-risk exception, and final acceptance authority. |
| I10 | Sensors are read-only; actuators are explicit. |
| I11 | Installer upgrades preserve tuned surfaces and adopter instance truth. |
| I12 | Recurring failure strengthens the harness, preferably through a deterministic mechanism. |
| I13 | Hooks, role prompts, comments, and thread IDs are not claimed as authenticated runtime guarantees. |

## Durable hierarchy

The canonical Issue graph is:

```text
Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence
```

A repository initiative / Epic set is the durable repository objective plus
its explicitly linked Epic issues. A single Epic issue may be the root when no
larger initiative record is useful. Issue relationships, pull requests,
commits, required checks, and bounded evidence form the authoritative graph;
that graph wins if a projection conflicts with it.

A GitHub Projects board is an optional projection. It never outranks the Issue graph.
Board absence, lag, field drift, or automation failure cannot change Issue or
pull-request authority. Sensors may observe a board read-only; creating or
reconciling a projection is an explicit actuator.

Codex projects, chats, threads, subagents, worktrees, and cloud tasks are
execution contexts. They do not replace the Issue graph. A Task may use more
than one thread across supervision, worker attempts, recovery, exploration,
and independent review.

The target's Issue and pull-request templates now provide the ledger contract.
Do not fabricate retroactive issue comments or treat committed creation-time
snapshots as current GitHub outcomes.

## Repository completion boundary

No individual phase completion constitutes repository-level completion.
Task and Epic completion also do not constitute repository completion.
The overall repository implementation remains incomplete until every required contract has current target-side evidence and a human-reviewed completion pull request changing `release_blocked` to `false` is merged.
The repository-level definition of done is versioned in
`docs/agreements/repository-completion.md`. Missing, stale, `UNKNOWN`, and
`UNCHECKABLE` evidence are non-success states. The repository owner retains
final agreement, completion-PR review, and merge authority.

## Roles and writer boundary

- A repository initiative or Epic orchestrator coordinates durable work and does not become
  the application-code writer.
- A Task supervisor owns claim, plan, routing, monitoring, verification, and
  outcome responsibility. A declared trivial-task exemption may combine
  supervision and implementation only when the durable plan says no worker
  will be spawned.
- A worker writes only inside the assigned branch, worktree, Task scope, and
  ownership declaration.
- A governance reviewer independently audits the Task contract, current head,
  ownership, risks, and evidence. The reviewer reports findings and does not
  repair the implementation under review.
- An explorer performs read-only investigation.

Role files and sandbox settings are defense in depth. Parent runtime permission
changes can alter a child agent's effective sandbox, and a role name is not an
authenticated identity. Deterministic GitHub and CI evidence remains the gate.

## Work ritual

Before changing governed files:

1. Read this file and the current durable work order in full.
2. Read referenced agreements and only the Skills required for the work.
3. Restate the objective, acceptance criteria, risk, and owned paths.
4. Verify the current branch, worktree, base, and repository state.
5. Record the plan before implementation.

During and after work:

- Modify only owned paths. Stop and request replan before expanding scope.
- Detect ownership overlap before dispatch; serialize unavoidable overlap.
- Prefer deterministic tests, schemas, and current repository/API evidence to
  self-report.
- Record changed assumptions, failed checks, deferred proof, and risk changes.
- Publish acceptance evidence for the current PR head before reporting done.
- Treat `UNKNOWN`, `UNCHECKABLE`, missing evidence, stale attempts, and stale
  heads as non-success states.

If requirements conflict, authority is missing, or the plan no longer works,
record the facts and options, then stop that line of work. Do not guess.

## Human authority and risk

Humans retain agreement changes, high-risk exceptions, final acceptance, and
merge authority. Ordinary bounded work may run Human-on-the-Loop, but ambiguity,
irreversible operations, privacy/security impact, agreement changes, and scope
expansion return to explicit human judgment.

No initial release enables broad auto-merge, autonomous external-contributor
delegation, or a repository-only substitute for a real identity/control plane.

## Sensors, actuators, and privacy

Observation commands are read-only and must not silently reconcile external
state. Commands that change labels, rulesets, issues, pull requests, branches,
or configuration are explicit actuators with reviewed inputs.

Durable receipts must not contain secrets, credential values, environment
dumps, private local paths, raw transcripts, or raw logs. Record bounded,
allowlisted evidence and references instead.

## Codex surface boundary

- Local `AGENTS.md` discovery runs from the project root to the startup working
  directory. A nested file does not automatically apply merely because a file
  in that subtree is edited from a root-started run.
- Repository Skills belong under `.agents/skills/` when implemented. A Skill's
  documented metadata enables discovery; it does not grant authority.
- Project custom agents belong under `.codex/agents/` when implemented. Their
  configuration is a default layer, not an immutable role boundary.
- Project hooks require review and trust, cover only supported paths, may run
  concurrently, and cannot be the only enforcement layer.
- `codex exec --json` is a machine-readable execution surface. Model behavior
  is not deterministic, and final-output schemas do not define the full JSONL
  event stream.
- Worktree, cloud, SDK, GitHub review, and Action behavior is claimed only to
  the evidence class recorded for a named client, version, and date.

## Language and amendments

Durable scaffold-owned artifacts use English. Conversations may use the
human's language.

Change this constitution only in a reviewed PR with an updated invariant
digest, rationale, conformance evidence, and human acceptance. Procedures
belong in Skills or deterministic guards rather than accumulating here.
