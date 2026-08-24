# ADR-0005: Issue graph authority and optional Project projection

- Status: Proposed; accepted when Issue #7's dedicated agreement pull request is owner-merged
- Date: 2026-08-24
- Decision owner: repository owner
- Task: https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7

## Context

The Phase 0 constitution used "GitHub Project" in the canonical hierarchy.
That wording can mean either a durable body of repository work or a GitHub
Projects board. The ambiguity could make an optional UI projection appear to
outrank the Issue and pull-request records that carry ownership, checks, and
acceptance evidence.

T04 in Issue #6 persisted all 136 conformance definitions. Scenario C-004 now permits a
reviewed hierarchy agreement to replace its pending disposition without
claiming that the scenario has been executed. This ADR makes that agreement and
binds it to Issue #7 and to
`docs/agreements/repository-completion.md`.

## Options considered

### Option A: GitHub Projects board authority

```text
GitHub Project -> Epic issue -> Task issue -> PR -> commits/checks/evidence
```

Rejected. Board absence, stale fields, automation drift, or access differences
would become an authority failure even when the underlying Issue and PR graph
remained intact. A presentation surface would be able to outrank its durable
records.

### Option B (selected): Issue graph authority with optional projection

```text
Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence
```

A GitHub Projects board is an optional projection. It never outranks the Issue graph.

A repository initiative / Epic set is a durable repository objective plus its
explicitly linked Epic issues. A single Epic issue may serve as the root when a
separate initiative record adds no value. Issue relationships, PRs, commits,
required checks, and bounded evidence remain authoritative. A projection may
lag or be absent without changing that authority.

Selected: Option B.

The cost is that projections can drift. A sensor may report that drift
read-only, but creating, updating, or reconciling a board is an explicit
actuator and requires the authority appropriate to that external-state change.

### Option C: Project Record terminology

```text
Project Record -> Epic issue -> Task issue -> PR -> commits/checks/evidence
```

Rejected. Defining "Project" as something other than GitHub Projects reduces
one ambiguity only by introducing an overloaded project-record concept. It
also obscures that a repository initiative may consist simply of one linked
Epic issue.

## Decision

Adopt Option B. The exact canonical hierarchy is:

```text
Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence
```

A GitHub Projects board is an optional projection. It never outranks the Issue graph.

The Issue graph wins every conflict with a projection. Codex projects, chats,
threads, subagents, worktrees, and cloud tasks remain execution contexts; they
do not replace a Task issue or the durable graph.

This decision is proposed on the T05 branch for Issue #7 and becomes accepted
only when the repository owner reviews and merges its dedicated pull request. Neither
the authoring thread nor CI can exercise that final agreement and merge
authority.

## Repository completion boundary

This hierarchy decision does not complete Phase 1 or the repository. The
normative completion requirements live in
`docs/agreements/repository-completion.md`. `release_blocked` remains `true`.

C-004 changes to `agreement-decision` and remains bound to Issue #7 and this
ADR. Its `verification_state` remains `not-run`; selecting terminology is not
evidence that a conformance scenario passed.

## Consequences

- Durable Issues, pull requests, commits, checks, and evidence remain usable
  without a GitHub Projects board.
- A board may provide planning and reporting views, but it is never an
  independent source of ownership, completion, or acceptance authority.
- Board observation remains a sensor; board mutation remains an explicit
  actuator.
- The historical Phase 0 snapshot and orientation retain their accepted
  wording. Only the reviewed live constitution and its live digest change.
- Missing or conflicting hierarchy evidence fails closed.

## Verification

The live repository policy pins the reviewed SHA-256 of this ADR, validates the
Option B structure in `AGENTS.md` and `README.md`, binds the Phase manifest to
Issue #7 and this path, and requires the exact C-004 agreement-decision object.
Negative tests cover Options A and C as authority, Projects-board authority,
synchronized manifest rehash drift, wrong C-004 bindings, and completion
conflation.
