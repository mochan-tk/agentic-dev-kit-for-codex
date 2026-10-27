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
