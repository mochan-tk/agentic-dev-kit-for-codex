# Introduction: prerequisites, handoff and lead time

The [registry](../.github/distribution/prerequisites.v1.json) declares the
prerequisites; the [README Tier table](../README.md#prerequisites) exposes every
entry ID. Tiers are cumulative, not separate supported products:

| Tier | Reach | Additional prerequisites |
|---|---|---|
| 0 — Install & inspect | Install/stage the scaffold and read documentation. | GitHub repository/local checkout, Git, Bash 3.2+ (Git Bash on Windows), jq, gh and repository access. |
| 1 — Onboard & run Tasks | Complete onboarding and run authorized Tasks locally. | Codex desktop app, prepared specification context, adopter Codex project, scaffold on the remote default branch. |
| 2 — Full operation | Operate the roadmap and perform required close-out. | Projects query/write permissions and a board, or the existing durable scoped exceptions for environmental inability or explicit owner decline. |

Tier 0 may precede desktop/context readiness. The desktop app remains mandatory
for operating this kit; terminal diagnostics do not replace it. Projects remains
required by default. Tier 1 does not waive Task close-out: pending board/date
consent or a date-only decline is not an exception. Otherwise authorized local
work can continue, but close-out requires the exact Project item's Kind `Task`
and both authorized dates, or its scoped exception. Missing permissions do not
create or authenticate an exception; the owner decides and records it.

## Read-only preflight

On a diagnostics machine with Python 3.11+ and a reviewed kit source checkout:

```sh
python3 -I /path/to/reviewed-kit/.github/scripts/check-prerequisites.py /path/to/adopter
```

The argument is the adopter directory; omission uses the current directory.
This companion is outside the installed payload and does not change the public
installation route. Python is a diagnostic prerequisite, not a new installer
requirement. The registry's detection commands describe the observations;
placeholder values come from the checked origin and remote metadata. The
diagnostic runs fixed commands, never arbitrary registry text as shell code.

Output names each ID under its Tier, its status, and the impact/remedy for any
unconfirmed prerequisite. Cumulative readiness includes lower tiers:

- `OK`: the stated observation succeeded. Tool versions are reported; Bash
  must be at least 3.2. No other minimum tool version is newly imposed.
- `MISSING`: the observed prerequisite is unmet, for example a missing jq,
  old Bash, rejected authentication or explicitly insufficient OAuth scopes.
- `UNVERIFIED`: a command, response, authentication or network observation could
  not establish the prerequisite. Failure is not proof of absence.
- `PROCEDURE`: a person must confirm the prerequisite. Desktop availability,
  prepared context, Codex project and board/exception evidence are not checked
  by inference from files or an unrelated app process.

Exit 0 means all entries were observed OK; exit 1 means something is missing or
unconfirmed; exit 2 is an input/diagnostic error. Because procedural entries
remain unconfirmed, a normal run returns 1 even on a well-prepared machine.
These statuses inform the owner, not an onboarding gate. Do not use this as
an automatic CI approval or claim that Tier 1/2 is verified.

The current automated GitHub probe supports canonical github.com `origin`
URLs (HTTPS, SSH or SCP form); aliases, other remotes and Enterprise hosts
require procedural checks. It isolates inherited Git repository overrides,
uses bounded-time read-only `gh api --method GET` requests and captures raw
responses privately without printing auth output or raw errors. It does not
fetch, stage, write GitHub records, change credentials or refresh authentication.
Active user authentication and repository access are observed separately;
installation-token authentication may remain unverified even if the repository
is readable. A default-branch instruction anchor is a P0 signal, not proof
that all 47 files landed correctly; retain P0's exact adoption commit/tree review.

Classic/OAuth `project` includes `read:project`; `read:project` alone does not
permit writes. Missing/unexposed scope headers do not establish a failure or
success for fine-grained/environment credentials: confirm their permissions
procedurally. The owner may use `gh auth refresh -s project` for stored gh
credentials, or update the relevant token permissions. No refresh is automatic,
and a scope check never grants board creation or date-application consent.

## Material handoff: presence only

From that same reviewed source, inspect one or more UTF-8 Markdown/text files:

```sh
python3 -I /path/to/reviewed-kit/.github/scripts/check-spec-handoff.py /path/to/spec.md
```

The README's six groups become seven observations by separating scope and
non-goals: **goal**, **intended users**, **scope**, **non-goals**, **constraints**,
**acceptance criteria**, **unresolved questions**. English or Japanese labels
in headings or clear mentions are recognized, case-insensitively; this is a
small label recognizer, not a semantic reader for every language or synonym.
If material is split across files, pass all paths in one invocation; their
observations are combined. Already committed sources are read in place.

The output gives `Observed points: n/7` and names every missing point. Exit 0
means all labels are present; exit 1 means one or more are missing; exit 2
means input could not be read as text. Empty named sections and an explicit
`Unresolved questions: none` count as present. Nothing here judges quality,
length, completeness of the content or approval of an agreement.

P2 presents missing observations as **warnings** and leaves progression to
the owner. It must not abort automatically on exit 1, treat exit 2 as success,
or bypass the interview's explicit-answer wait. If the kit-side script or
Python is unavailable, use the same seven-point procedural checklist and
label that result as manual. Do not install another payload helper just to
run it. This is separate from consent, material receipt and planning quality.

## Lead-time record in the P6 evidence PR

Use the onboarding evidence PR as the durable record. These are four
**milestones**, yielding three adjacent intervals and an overall elapsed time;
they are not four sequential intervals. Use ISO 8601 with a timezone, such as
`2026-11-08T10:30:00Z` or `2026-11-08T19:30:00+09:00`, plus a reviewable evidence
link for every observed point. Publish only bounded evidence, never private
material, credentials or raw logs. The following table is also in P6:

<!-- BEGIN introduction-lead-time -->
| Milestone | Definition | ISO 8601 timestamp (with timezone) | Evidence link |
|---|---|---|---|
| `adoption_started` | Owner explicitly starts this adoption attempt, before scaffold installation. | pending | pending |
| `scaffold_on_default` | Reviewed scaffold first reaches the remote default branch; cite the adoption commit/tree. | pending | pending |
| `onboarding_completed` | P0–P6 evidence and handoff are recorded and the onboarding evidence PR exists; this is not owner acceptance or merge. | pending | pending |
| `first_task_closed` | The first post-onboarding Task completes its required close-out, including Project proof or its scoped exception. | pending | pending |
<!-- END introduction-lead-time -->

Record `pending` for future events and `unknown` with a reason for an event
whose time/evidence cannot be recovered. Never infer a past timestamp from
the current clock or fill a future event optimistically. At P6 the first Task
will normally be pending; update this same PR's record when close-out occurs.
Record onboarding completion only once P6 actually completes; PR creation
blocked by permissions/approval is still pending. Owner acceptance/merge
remains separate and must precede first Epic execution under the existing ritual.

Calculate durations only when both endpoints have observed timestamps and
evidence, in nondecreasing time order (normalize timezones before subtraction):

- Installation/landing: `scaffold_on_default - adoption_started`.
- Onboarding: `onboarding_completed - scaffold_on_default`.
- First Task: `first_task_closed - onboarding_completed`.
- Total introduction lead time: `first_task_closed - adoption_started`.

Use elapsed wall-clock time, including waits; record duration units (for
example minutes) and any caveat beside the table. Unknown/pending endpoints
produce unknown/pending durations, never zero. This is a manual recording
format, not automatic telemetry, a speed target or a release/acceptance claim.
For a re-tuning pass, label a separate attempt instead of overwriting the
original adoption record or counting re-tuning as the first Task.
