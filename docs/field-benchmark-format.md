# Minimal field-benchmark record

Version 1, 2026-11-09. One Markdown record per real adopter attempt or explicitly
identified maintainer cycle. Record completion and friction without inventing a
speed score. This format starts no run and has no collector, schema or validator.
See the [T10 retrospective](evaluation-results/field-t10-maintainer-mode-2026.md).

## Timing authority

T2 is the sole definition of the milestones and interval boundaries:
`docs/introduction.md`, section “Lead-time record in the P6 evidence PR”, at
local commit `9ef9d3b9fa16232384128f25b633b9c78b011473`
(blob `101792f8305700e3dd3b53e16584ae76d7b71268`). Inspect it with:

```sh
git show 9ef9d3b9fa16232384128f25b633b9c78b011473:docs/introduction.md
```

T2 is a separate local branch, absent from this main-based tree; its source is a
review dependency, not a published URL or a file supplied by T3. If that source
is unavailable, mark definitions unverified and do not infer timings. Reconcile
the reference when T2 is integrated; this document does not redefine endpoints.
T2 has four milestones yielding three adjacent durations plus total, not four
sequential intervals. The tables below reuse only its field names and labels.

For observed times use ISO 8601 with timezone and a reviewable evidence
reference for each endpoint. For an unrecoverable value write **unrecorded**
(T2 `unknown`) and a reason; use `pending` only for a genuinely future event.
An inapplicable adoption milestone in a maintainer cycle is unrecorded with
that applicability reason, never a fabricated onboarding event. Compute elapsed
wall-clock durations only from observed, evidenced, nondecreasing endpoints
under T2; include waits, normalize timezones and state units. Missing endpoints
make durations unknown/pending, never zero. Do not sum the total into itself.

## Copy per run

- Record date and run ID:
- Run kind, target, task/objective and bounded completion criterion:
- Kit/base/candidate identity and evidence class/platform (unknown if absent):
- Authorization/source references, observation cutoff and recording method:

| T2 milestone | ISO 8601 timestamp or unrecorded/pending | Evidence reference and reason/limits |
|---|---|---|
| adoption_started | Fill | Fill |
| scaffold_on_default | Fill | Fill |
| onboarding_completed | Fill | Fill |
| first_task_closed | Fill | Fill |

| T2 duration label | Elapsed value with units or unrecorded/pending | Endpoint evidence references / caveat |
|---|---|---|
| Installation/landing | Fill | Fill |
| Onboarding | Fill | Fill |
| First Task | Fill | Fill |
| Total introduction lead time | Fill | Fill |

- First Task completion: yes/no/unrecorded, evidence and remaining work. For
  maintainer development, report local implementation/verification and local
  close-out separately from the T2 first post-onboarding Task. Never use a
  passing test or a local commit as proof of required Task close-out.

| Blocked location / impact | Elapsed duration (units) or unrecorded | Cause category and evidence | Resolution / remaining work |
|---|---|---|---|
| Fill; if no blockage was recorded, say so rather than asserting none occurred | Fill | Environment, permissions, specification/decision, workflow/tooling, product defect, or unknown | Fill |

- What this run proves:
- What this run does not prove:

Every populated record must fill all fields, including missing-data reasons.
Use source identifiers or sanitized public references; do not publish raw logs,
transcripts, credentials, recovery data or private paths. A retrospective source
date or Git commit time is not a substitute for an unrecorded run milestone.
The format's completeness and the Task's success are different judgments.
