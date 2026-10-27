Closes #<!-- Task issue number (required — AGENTS.md, unit of work) -->
<!-- Replace Closes with Refs when acceptance includes post-merge work. -->

Plan: <!-- link to the plan comment on the Task issue (plan of record —
session-orchestration skill; plan text auto-written here is a copy) -->

## Summary

<!-- 2–4 sentences: what changed and why, in terms of the Task's Objective. -->

## Evidence

<!-- One row per acceptance criterion of the Task issue. "pass (untested)" is
     not a result; "deferred" requires a linked follow-up issue
     (.agents/skills/verification/SKILL.md). -->

| Criterion | Evidence (command / link) | Result |
|---|---|---|
|  |  |  |
| Project close-out | Exact Project/Issue/item identity, observation time/current head, Kind `Task` and authorized Start/Target comparison + schedule-decision link; or scoped environmental-inability / explicit-Project-decline exception link | match / exception / pending / non-success |

<!-- Projects is required by default; the Issue graph remains authoritative.
     Pending creation/date consent or date-only defer/decline is not a Project
     exception. Do not report Task completion while required close-out is pending.
     Use the installed setup-project.sh verify (or complete exact-item UI proof)
     under existing authorized access; prose and write success are not live proof.
     No unconditional Projects API call from repository-token CI is implied. -->

<!-- Only for a Task whose Verification declares Known-defect pins: required:
     add this active subsection under Evidence. Repeat the five ordered fields
     for each pin (maximum 32 records; each value at most 2048 characters).
     Replace every placeholder; use a canonical same-repository Task/Epic URL.
     A passing characterization is not a defect fix. Do not close the defect
     merely because this pin passes; the follow-up replaces it with a regression.

### Known-defect pins

- Defect: <known defect>
  Test: <test file and case>
  Pinned: <current known-wrong behavior>
  Expected: <correct behavior under the agreed requirement>
  Follow-up: https://github.com/<owner>/<repo>/issues/<number>
-->

## Deviations

<!-- Anything that differs from the Task brief, and why. Silent deviations are
     the most expensive class of agent error — "None" must be literally true. -->

None.

## Follow-ups

<!-- Suggested downstream issue changes (feeds the replanning procedure), or
     "None". Scaffold friction observed? File or +1 a retro:candidate issue
     (retro skill, Candidate ledger). -->

None.

## Checklist

- [ ] Plan was posted as a Task-issue comment before implementation and is
      linked above.
- [ ] Diff stays inside the issue's **File ownership** paths (single-writer
      rule, or a declared agreements wording rider).
- [ ] Every command in the issue's **Verification** section was run; output captured above.
- [ ] No test, lint rule, or CI check was deleted, skipped, or weakened.
- [ ] Record-before-report comment posted on the Task issue.
- [ ] Required Project close-out has matching Kind/authorized-date evidence or a
      linked scoped environment / explicit owner Project-decline exception.
- [ ] All persistent artifacts in this PR are English-only.
