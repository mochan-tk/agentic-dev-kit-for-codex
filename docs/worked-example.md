# Worked example: characterize a small report formatter

This is an **illustrative** workflow and a locally runnable reference, **not a
live Codex** experiment or a record of accepted GitHub work. The example Issue,
claim, plan and PR text below has not been published for an adopter. References
in angle brackets are placeholders; never present them as real evidence.

## 1. Inspect the reference locally

From a reviewed checkout of this kit, with Python 3.11 or later, run these two
commands separately:

```bash
python3 -I -m unittest discover -s docs/examples/report-summary/before -p 'test_report.py'
python3 -I -m unittest discover -s docs/examples/report-summary/after -p 'test_report.py'
```

The supplied [before source](examples/report-summary/before/report.py) has
[one baseline test](examples/report-summary/before/test_report.py). The
[after source](examples/report-summary/after/report.py) is byte-identical;
[the reference test file](examples/report-summary/after/test_report.py) contains
five tests. Expected output is `Ran 1 test` / `Ran 5 tests` and `OK`, respectively.
Each command starts a separate process so the two `report` modules cannot be
confused. No packages, network requests, model calls or GitHub writes are needed.

The four added tests capture empty input, trimming/blank removal, duplicate
retention and input order/non-mutation. The intended input is a sequence of
strings; this does not define arbitrary-type validation or a new feature.
Characterization tests describe existing behavior, so passing immediately is
expected. This is not a red/green production-bug demonstration, and the supplied
after-version is not claimed to have been produced by an evaluated agent.

## 2. Prepare a real exercise only if you choose to run one

The remaining steps are instructions for a future owner-authorized exercise,
not actions performed by opening this guide.

1. Follow the [prerequisites and preparation](../README.md#prerequisites),
   including the **Codex desktop app**, a GitHub repository and authenticated
   tools. Prepare the specification context in ChatGPT Chat or Work first,
   then explicitly supply the relevant material to Codex. A chat link alone
   does not establish that Codex has read the specification.
2. With the owner's permission, use a separate disposable application
   repository. Place the two **before** files at its root as `report.py` and
   `test_report.py`, and establish a committed baseline. Do not use this kit's
   source checkout as the application or put both example versions in it.
   Record the actual baseline SHA; none is invented here.
3. Create a Codex project with that application repository as its **primary
   folder**, then follow the [installation and onboarding sequence](../README.md#quick-start).
   The primary folder is the documented default for Git and automatic local
   instruction/Skill discovery; merely adding a secondary folder does not load
   its instructions. See [Codex local projects](https://learn.chatgpt.com/docs/projects#use-local-projects-for-folders-and-codebases).
   Record the actual client/version and explicitly load the installed
   `AGENTS.md` and the required Skills. Do not claim automatic discovery was
   tested by this example.
4. Complete the real onboarding decisions and review gate before starting the
   Task. Projects/Rulesets choices remain real human decisions: this guide
   neither declines nor authorizes them for you. Verify the baseline command
   below in the application repository. If onboarding is incomplete, tools are
   missing, or there is no test baseline, stop and follow the applicable installed
   procedure rather than silently assuming the example's prerequisites.

```bash
python3 -I -m unittest discover -s . -p 'test_report.py'
```

## 3. Turn the specification into durable work

The prepared specification can be short: users need predictable plain-text
reports; preserve the observed string trimming, blank removal, duplicates and
order; add tests only; do not add I/O, sorting, validation or a new output format.
Record unresolved choices explicitly rather than inferring approval. Link the
actual reviewed specification from the real Issue.

Read the installed `plan-management` and `session-orchestration` Skills. The
[Epic template](../.github/distribution/payload/.agents/skills/plan-management/templates/epic-body.md)
and [Task template](../.github/distribution/payload/.agents/skills/plan-management/templates/task-body.md)
are the source for these shapes. Reuse an appropriate existing Epic; create one
only with the applicable authority. An optional Projects board is a projection,
not a substitute for the Issue graph. Publishing any Issue or comment is an
explicit write; the following blocks do not publish anything.

Illustrative Epic body:

```markdown
## Outcome
Make existing report behavior easier to maintain without changing its output.

## Success criteria
The bounded characterization Task has exact-head verification and a recorded
human acceptance decision; CI alone is not acceptance.

## Scope & non-goals
Characterization of the existing formatter. No new report features or deployment.

## Phase outline
1. Characterize the small area with an existing baseline test.
2. Review evidence and request the human decision.

## References
<REVIEWED_SPECIFICATION_REFERENCE>
<ACTUAL_TASK_ISSUE_URL>
```

Illustrative Task body (replace every placeholder before publishing):

```markdown
## Objective
Add four characterization tests for the existing render_report behavior.

## Context & references
Parent: <ACTUAL_EPIC_ISSUE_URL>
Specification: <REVIEWED_SPECIFICATION_REFERENCE>
Baseline: <ACTUAL_BASE_SHA>, with one passing baseline test.

## Acceptance criteria
1. Keep the baseline test and cover empty input, whitespace/blank removal,
   duplicate retention and input order/non-mutation with four additional tests.
2. Keep report.py byte-identical to the agreed base; change only test_report.py.
3. Verify the exact candidate head, review the diff and record evidence before
   requesting human acceptance. Do not treat test success as merge permission.

## Out of scope
Application behavior changes, new dependencies, broad cleanup, other files,
external services, deployment, configuration and automatic merge.

## File ownership
- `test_report.py`

## Verification
Run: python3 -I -m unittest discover -s . -p 'test_report.py'
Expect five tests passing. Compare report.py and the changed-path list against
the agreed base. Inspect each assertion against the specification, not merely
the implementation. Preserve any other required repository checks.
Attach exact HEAD/tree, commands, results and available CI links to the PR.
Missing or stale proof is non-success; current status: NOT_RUN.

## Routing
exec:app
default
standard
Use the project's recorded model preference; record the actual observed model
when available rather than inferring it from a requested setting.

## Handoff notes
One active writer owns the declared branch/worktree. Bounded small-task
exemption: the supervisor may implement this test-only change; no worker will
be spawned. Human final acceptance and merge decisions: PENDING.
```

This example deliberately starts in an area with a test baseline. It does not
override the installed handling of untuned projects or uncharacterized areas.
If your case is larger, needs other files or has new risks, replan before editing;
the small-task exemption is not a general permission to bypass worker separation.

## 4. Claim, plan, then add the tests

Confirm the actual Task, branch, worktree, base and ownership. The required
chronology is **claim → plan → first commit**. The first line of a real claim is
shaped like this (replace the session and Task-specific branch before posting):

```text
Starting in session <SESSION_NAME_OR_LINK>, branch codex/task-<TASK_NUMBER>-report-tests
```

After that claim, publish a separate plan comment before implementation:

```markdown
## Plan
Base: <ACTUAL_BASE_SHA>; branch: <ACTUAL_BRANCH>; owner: <ACTUAL_WRITER_REFERENCE>.
Own only test_report.py. Run the existing baseline test, add the four agreed
characterization cases and keep report.py unchanged. Verify five tests plus
the base comparison and all existing required checks on the candidate head.
Risk: tests may encode accidental assumptions; review against the agreed spec.
Bounded test-only exemption: no worker will be spawned.
Human acceptance and merge remain PENDING.
```

The real PR's `Plan:` must link to that actual comment on the same Task. Do not
retroactively edit a claim or plan to make an old commit appear compliant; if
scope changes, post a new plan and follow the installed replan procedure.
The installed [session orchestration procedure](../.github/distribution/payload/.agents/skills/session-orchestration/SKILL.md)
and its helper `--help` are authoritative for concrete invocations. Rendering a
draft is local preparation; a read-only preflight neither publishes it nor
grants write permission.

The reference after-test file shows one possible implementation. In a real
exercise the writer must produce and check its own candidate, within ownership,
and record what actually ran. Do not copy the reference's expected output into
an evidence receipt as though a command had been executed.

## 5. Review and request the human decision

Read the installed [verification Skill](../.github/distribution/payload/.agents/skills/verification/SKILL.md)
and use the installed [PR template](../.github/distribution/payload/.github/PULL_REQUEST_TEMPLATE.md).
This illustrative PR is intentionally unfilled and has no completed checklist:

```markdown
Closes #<TASK_NUMBER>
Plan: <ACTUAL_PLAN_COMMENT_URL>

## Summary
Add four characterization tests; application behavior remains unchanged.

## Evidence
| Criterion | Evidence (command / link) | Result |
| --- | --- | --- |
| Five tests and exact-head required checks | <ACTUAL_HEAD_TREE_COMMANDS_AND_CI_REFERENCES> | NOT_RUN |
| Ownership and unchanged report.py | <ACTUAL_BASE_COMPARISON_AND_REVIEW> | NOT_RUN |
| Post-PR ritual sensor | <ACTUAL_PR_NUMBER_HEAD_BASE_AND_SENSOR_RESULT> | NOT_RUN |

## Deviations
PENDING: record actual deviations, or confirm none after review.

## Follow-ups
Human final acceptance and merge decision: PENDING.

## Checklist
- [ ] Scope, ownership and current evidence reviewed.
- [ ] Human acceptance decision recorded separately from technical checks.
```

This single-PR sample has pre-merge criteria, so it uses the ordinary `Closes`
relationship; closure takes effect only upon an authorized merge. Use `Refs`
instead when the actual Task has post-merge acceptance steps or this is a
non-final stacked layer. Pending human review alone does not make a Task's
criteria post-merge or authorize a merge.

After the real PR exists, run the installed read-only sensor from the adopter
repository before ready-for-review. Replace the placeholder with its numeric
PR number, and record the observed head/base and actual result in the table:

```bash
bash .github/scripts/check-task-ritual.sh <ACTUAL_PR_NUMBER>
```

This GET-only sensor does not replace implementation tests, current-head CI,
independent review or human acceptance. Missing, stale or uncheckable evidence
is non-success; rerun the sensor if the head or Task/plan evidence changes.
Replace `NOT_RUN` only with observed results bound to the actual candidate head.
An independent review can be advisory; neither model praise nor green CI is a
human acceptance/merge decision.

Before the final narrative report, the supervisor records the structured Task
outcome comment and updates the PR evidence using the installed session
orchestration format. State actual results, deviations, pending decisions and
next steps. Do not record `Outcome: completed` while required evidence or an
applicable human acceptance decision is missing; use the appropriate non-success
outcome with the concrete blocker. No outcome is prefilled as completed here.

An optional handoff at a **normal completed checkpoint** should leave the
current Issue/plan, branch/base/head, owned paths, evidence and pending decisions
in durable records. A successor re-reads those records, not just chat history.
This is **not crash recovery**, and the example does not claim any handoff ran.

For future agent measurements, use the [unrun evaluation cases](evaluation-cases.md).
For what has actually been demonstrated, consult [evidence status](evidence-status.md).
