# Product scope

This repository distributes the source-first Agentic Development Kit for
Codex: 47 installable files, eight Skills, three role instruction files,
Issue/PR templates, connectors, agreement/context seeds and Bash helpers.
The payload has 32 engine, four tuned, eight instance and three seed entries.

The public Bash/PowerShell entrance acquires a selected source revision,
validates it, installs into an existing Git repository and stages only newly
created files. A reviewed local checkout supports explicit install, known-old
upgrade and operation-scoped rollback. Existing project-owned content is
preserved; conflicting engine files and unsafe inputs refuse.

A separate public Bash and thin PowerShell/Git Bash updater needs no advance
clone. It requires exact old/new commit IDs and a fresh recovery directory,
defaults to preview, and updates only known-old engine files on explicit apply.
It preserves customized tuned/instance/seed files, retains validated sources
and any operation record outside the adopter, and supports the unchanged
engine's offline rollback. It never stages or detects the installed version.

Four companions can run explicitly from a reviewed kit checkout:
`governance-status.sh`, `worktree-preflight.sh`, `check-connectors.sh` and
`report-installer-failure.sh`. They are outside the installed payload. The
feedback companion also uses `feedback-lib.sh`. The three read-only checks
also have [no-clone Bash commands](distribution/companion-checks.md): complete
fixed-revision download, reviewed SHA-256 verification, then explicit execution.
This is a delivery route to explicitly pinned helpers, not an installer mode or
automatic CI integration. The failure reporter is excluded from that route.
Installation does not create
CI, configure GitHub, commit, push, run onboarding or invoke a model.

The installed workflow covers onboarding, context collection and builtin
drafting, human-reviewed distillation, Epic/Task planning and readiness,
ownership and routing, supervision and handoff, verification, and retrospective
proposals. Humans retain agreement, exceptions, acceptance and merge authority.

Startup distinguishes tuned (exit 0), untuned (exit 1), and an observation
error. A current scoped owner decline may be carried by an exact record link;
missing or revoked consent cannot be inferred from chat history. Supervisors
own claim/plan/dispatch and material replanning; workers acknowledge the
current Task and plan and stay inside assigned ownership. Stop/disposition
evidence precedes worktree teardown or artifact reuse. These are shipped
procedures and synthetic contract checks, not authenticated roles or measured
model compliance, worker termination, locks, or automatic recovery.

The installed `check-task-ritual.sh` provides offline `render` and GET-only
`preflight` for claim/resume/plan/dispatch, alongside its existing PR checker.
It never posts a comment. Preflight validates the actual body and complete
current ledger, with optional PR-bound chronology and final readbacks; it is
an observation, not authority or a guarantee that a later write is unchanged.

Governance offers three explicit profiles: `solo`, `team`, and
`single-maintainer` (PR and checks, zero approving reviews, no bypass).
Selection never silently downgrades another profile. Unknown preimages,
conflicting review gates, bypasses or incomplete observations remain
non-success. Setup is an explicit consent-gated actuator; the sensor stays
read-only and considers all contributing Rulesets.

This clean product root preserves the accepted 47-path payload layout and
installer engine; bounded current adaptations are recorded separately from
the original export seal. It does not import the predecessor's research ledger,
runtime adapter, historical Tasks or repository release criteria as adopter
authority. Historical acceptance and original unfinished work remain in the
[predecessor records](provenance.md). Product checks here validate the shipped
scope; they do not establish runtime parity or whole-project completion.

See the [installation guide](distribution/source-first-installer.md),
[known limitations](known-limitations.md), and
[contributor validation](../CONTRIBUTING.md).
