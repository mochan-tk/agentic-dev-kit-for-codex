---
name: verification
description: Prove that work meets its Task issue — layered verification gates, implementer and supervisor checklists, the acceptance-criteria evidence table, and CI-failure triage. Use this before marking any PR ready for review, when writing the Verification section of a task brief, when a CI check fails, or when reviewing whether someone else's evidence actually proves their claim.
---

# Verification

Agent-produced work is verified in layers, cheapest and most deterministic
first. Each layer exists because the one after it is more expensive: a linter
catches in seconds what a human notices in minutes. The corollary that shapes
this whole repository: **automated checks are the ceiling on agent autonomy** —
work that only a human can verify can never be safely delegated, so investing
in layer 1 is investing in delegation itself.

## Test-first work orders

Acceptance criteria land as **executable tests before implementation**. The
planner's motto: *slice late, measure early* — rolling-wave keeps task detail
late, but the measuring stick arrives first. A criterion without a command is
an opinion; the wall judges, not the worker's account of the work. Retries
against the wall are budgeted: the same failure three times hands the work up
one tier of the escalation ladder (`session-orchestration` skill) — the ladder
is the cap and the exit, not an invitation to grind until green.

## The layers

1. **Deterministic** — formatters, linters, type checks, unit/integration
   tests, build. Runs locally and in CI. Binary outcomes only.
2. **Security** — secret scanning, dependency review, code scanning. Never
   ship "temporary" suppressions without a linked issue.
3. **AI review** — advisory only. Use an available Codex review surface or
   independent read-only reviewer and record its actual client/role and
   limitations. The custom `reviewer` audits Task linkage, evidence, CI and
   ownership; it is not an authenticated identity. No Copilot Rubber Duck or
   automatic code-review service is installed or assumed.

4. **Human review** — judgment: is this the *right* change? Apply the adopter
   ruleset actually observed; installing these files does not enable one.

Never compensate for a lower layer at a higher one ("reviewer will catch it")
and never weaken a lower layer to pass ("delete the flaky test"). A failing
gate is information; removing the gate destroys the information.

**The layers run once, not once per session tier.** Layer 1 runs twice by
design — the implementer runs it, then CI runs it — and CI's run is the
authoritative one, which every session above reads through `gh pr checks`. So
a supervising session verifies the **record**: the evidence table, the CI
verdict, the diff against the ownership paths. It does not rebuild the
artifact. Re-run a command only to resolve something specific — records that
contradict each other or CI, evidence that is absent, a claim implausible on
its face — and say which contradiction you were resolving. This sharpens
verify-before-done rather than relaxing it: every ground truth `AGENTS.md` §3
names (`git status`, `gh issue view`, `gh pr view`, `gh pr checks`) is a read
of the record, not a build. Reading the record *is* the check, never a way
around it — an absent or hand-waved evidence table still goes back to the
child with one instruction: record first.

## Pre-PR checklist (implementer)

1. Run every command in the Task issue's **Verification** section; capture
   real output.
2. `git status --short` clean; diff confined to the issue's File-ownership
   paths.
3. New logic has tests at the appropriate level (firmware logic: `native`
   env, when those tests actually exist).
4. Fill the PR template's evidence table — every acceptance criterion gets a
   row:

```markdown
| Criterion | Evidence (command / link) | Result |
|---|---|---|
| REQ-012: pairing completes < 5 s | `npm test -- pairing.spec` -> 8 passed | pass |
| Docs updated | .github/docs/agreements/requirements.md diff in this PR | pass |
| HIL verified on device | n/a in this task -> follow-up #<n> (exec:ide) | deferred |
```

`deferred` is legal only when a follow-up issue exists and is linked, and it
blocks `Outcome: completed` until the requester revises the work order
(session-orchestration skill, Outcome notes); "pass (untested)" is not a
result.

## Known-defect pins

When a characterization intentionally asserts known-wrong behavior, declare
`Known-defect pins: required` as an active line in the Task **Verification**
section, outside comments and code fences. Ordinary Tasks omit this declaration.
For each pin, add the following five ordered fields under the PR **Evidence**
subsection `### Known-defect pins` (at most 32 records, 2048 characters per value):

```markdown
- Defect: Per-line and aggregate tax rounding disagree
  Test: tests/test_tax.py::test_known_tax_discrepancy
  Pinned: Stored total is 562; report total is 563
  Expected: Both totals agree under the approved tax rule
  Follow-up: https://github.com/example/notes-app/issues/124
```

Replace the example URL with a canonical same-repository Task or Epic Issue
responsible for fixing the defect and replacing the pin with a regression.
No placeholders, empty fields, foreign repositories, or PR references are valid.
The installed ritual checker validates declared records, reads the follow-up
Issue type, and compares final observations; unavailable or changed evidence is
non-success. Comments and fenced examples are not declarations or evidence.
This check proves traceability, not the expected behavior or test quality.
A passing characterization does **not** mean the defect is fixed: keep that
limitation explicit in the evidence, and do not close its follow-up on pin PASS.

## Required Project close-out

GitHub Projects is required by default. Before a Task is reported complete,
follow [required per-Task Project close-out](../plan-management/SKILL.md#required-per-task-project-close-out)
and record either the exact-item Kind `Task` plus authorized Start/Target date
comparison, or a scoped durable exception for environmental inability to
create/use Projects or an explicit owner decision declining Projects.

Use the installed `setup-project.sh verify` under existing authorized access;
it acquires one fresh typed readback and compares all three expectations. An
exact-item UI observation can substitute only with the same complete identity,
values and comparison. Record the current PR head, observation time,
repository/Project/Issue/item identity, expected and observed values, result,
and schedule-decision reference in the Task and PR evidence. A present Status,
CLI-null, successful write or unchecked evidence text is insufficient.

Creation consent and date consent are separate. Pending answers or a date-only
defer/decline do not become a Project exception; keep required close-out pending
while otherwise authorized implementation can continue. Missing/mismatched
values and incomplete/uncheckable reads are non-success. Cite the actual scoped
exception when one applies; never manufacture a matching result or infer a
decline from silence. The Issue graph remains authoritative.

Do not add unconditional Projects queries to repository-token CI, widen scopes,
or repair fields to make a check pass. The verifier proves comparison only,
not the expected values' authorization, final acceptance, or merge permission.

## After PR creation, before ready-for-review

Once the PR has its actual number, run the installed read-only ritual sensor
from the adopter repository, replacing `123` with that number:

```sh
bash .github/scripts/check-task-ritual.sh 123
```

The helper is installed as mode 0644, so invoke it with Bash. Record its result
and observed head/base in the existing evidence table; rerun if that head or
the Task/plan evidence changes. Ordinary success requires complete evidence
for 1-250 PR commits, valid whole-second UTC dates, the Task/plan relationship,
and matching final PR/Task/comment observations. Unavailable, malformed,
incomplete or changed evidence is non-success, not a deferred PASS.

This sensor does not replace implementation tests, current-head CI,
independent review or owner acceptance. Matching before/after API reads are
not atomic and Git dates do not authenticate worker actions. Installation
enables neither a CI workflow nor a Ruleset; consult the adopter's actual
required checks separately. No Issue, label or PR mutation is performed.

**Reference, don't paste.** Evidence sometimes involves real data. PII,
credentials, and customer records never land in issues, PRs, or commit
messages — they live in access-controlled storage and the ledger links to
them. A redacted excerpt plus a link beats a raw paste; a leaked ledger
cannot be unleaked.

## Supervisor verification checklist

For each Task PR, inspect the evidence below and record bounded links, observed
identities, results and observation time in the existing Task/PR evidence table.
Worker narrative and checked boxes alone are not proof.

1. **Bind the review.** Read the current Task, plan and PR from GitHub; record
   repository, PR number, exact head/base SHAs and tested checkout commit/clean
   state. If CI tests a generated merge commit, identify its head/base mapping;
   a different or unmapped revision cannot prove this PR. Refresh affected
   evidence after head, base or work-order changes.
2. **Check scope.** Inspect the actual PR diff against the Task's owned paths
   and accepted plan. Unplanned files or behavior require replan. Confirm any
   [known-defect pins](#known-defect-pins) remain explicit limitations with
   follow-ups; passing characterization does not prove the defect fixed.
3. **Inspect platform CI.** Open actual check/run and job links, not just the
   PR's “CI passes” text. Compare observed results with the current workflow's
   expected matrix and the repository's required checks. Record tested SHA and
   each required job's status; missing, pending, cancelled, skipped or failed
   required coverage is not PASS. An aggregate green badge cannot fill a gap.
4. **Reconcile tests.** Compare the Task's expected suites/counts with actual
   commands, environment, passed/failed/skipped counts and clean-checkout proof
   from local/CI results. Explain count changes and skips against the acceptance
   criteria; unexplained differences withhold completion. Green exit status
   alone does not establish that the intended tests ran.
5. **Inspect the ritual result.** Check the installed
   [after-PR sensor](#after-pr-creation-before-ready-for-review) result and its
   current head/base and Task/plan binding. Missing, stale or uncheckable ritual
   evidence is non-success; it cannot be replaced by a CI badge.
6. **Check Project close-out.** Follow
   [required Project close-out](#required-project-close-out): inspect exact-item
   Kind `Task` and authorized Start/Target date comparison, identities and
   schedule-decision link, or the actual scoped permitted exception. Board
   presence, CLI-null or pending date consent is not sufficient.
7. **Disposition every gap.** Map each acceptance criterion to current proof;
   name missing/contradictory evidence and its next check/owner. Record independent
   review against the same revision, reviewer/client and limitations. Unresolved
   findings or required deferred proof block completion; a follow-up alone does
   not waive them. Human final acceptance and merge permission remain separate.

Reuse credible exact-revision CI evidence of a fresh/clean checkout and actual
suite results; do not rebuild at every session tier. Missing, stale,
contradictory or untrustworthy **test evidence** blocks completion until the
relevant checks run from a fresh/clean checkout at the current revision; run
the full suite when the accepted plan requires it. Authoritative fresh/clean
CI may supply this proof without a duplicate supervisor-local rebuild. If CI
cannot supply credible proof, perform an independent fresh-clone rerun. Record
the gap/reason, checkout SHA/clean state, commands, counts/skips and results.
A clone without running checks is not test evidence. Scope, platform-job,
ritual, Project and review gaps need their own current evidence; local test
success cannot substitute for it. A complete checklist supports a review
recommendation, never self-authorized acceptance or merge.

## Four-quadrant diagnosis

Every task leaves four artifacts on the ledger: the **work order** (issue
body), the **plan comment** (issue timeline), the **diff** (PR), and the
**evidence & checks** (evidence table + CI). When an outcome is wrong, locate
the failure before fixing anything — each quadrant has a different owner and
a different address:

| Wrong artifact | Question | Address |
|---|---|---|
| Work order | Was the wrong thing ordered? | Requester fixes the issue body + change comment; replan downstream (`plan-management`) |
| Plan comment | Right order, wrong approach? | Post a revised-plan comment — the comment sequence is the plan's history |
| Diff | Right approach, wrong execution? | Fix the code; ordinary rework inside the task |
| Evidence & checks | Wrong thing passed the wall? | Strengthen the checks (a test gap is a retro candidate); never weaken them |

CI-failure triage (below) is the entry point for the evidence quadrant.

## CI failure triage

When a check fails, classify before touching anything:

- **Environment** (missing tool, network, flake): fix the environment —
  usually the documented local setup or existing adopter CI — and note
  it as a retro candidate.
- **Defect** (the code is wrong): fix the code.
- **Specification mismatch** (the test encodes a requirement the task was
  told to change, or the requirement itself is wrong): **stop patching.**
  Apply `needs:replan`, record the mismatch on the issue, and let the plan —
  or the agreement — be corrected first. Making a wrong test pass is the most
  damaging "fix" an agent can make.

## Writing good Verification sections (planner)

- Commands must run in the task's routed environment (`exec:cloud` tasks get
  no hardware — split HIL criteria into an `exec:ide` follow-up).
- Prefer commands over prose: "run X, expect Y" beats "make sure it works".
- Include the negative case when it matters ("`grep -R <secret-pattern>`
  returns nothing").
