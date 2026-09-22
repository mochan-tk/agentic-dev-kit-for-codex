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
and any operation record outside the adopter, and supports the retained
engine's offline rollback. It never stages or detects the installed version.
The current entry accepts the exact previous engine only as FROM data, requires
the current engine for TO, and executes only the latter. Local calls reject
inherited Git context; linked worktrees remain supported.

Four companions can run explicitly from a reviewed kit checkout:
`governance-status.sh`, `worktree-preflight.sh`, `check-connectors.sh` and
`report-installer-failure.sh`. They are outside the installed payload. The
feedback companion also uses `feedback-lib.sh`. The three read-only checks
also have [no-clone Bash commands](distribution/companion-checks.md): complete
fixed-revision download, reviewed SHA-256 verification, then explicit execution.
This is a delivery route to explicitly pinned helpers, not an installer mode or
automatic CI integration. The failure reporter has its own
[two-file pinned no-clone route and public form](distribution/feedback.md).
It defaults to a draft; sending requires explicit invocation and original
terminal consent. Installer failures print fixed guide/form links as a manual
handoff, with no reporting download, metadata collection, prompt or submission.
Installation does not create
CI, configure GitHub, commit, push, run onboarding or invoke a model.

A separate [adopter CI companion](distribution/adopter-ci.md), invoked from a
reviewed source checkout, previews or explicitly creates three addon files.
It preserves existing application CI and the Git index, supports a documented
limited workflow form, and refuses collisions or unsupported wiring. A fixed
read-only metadata workflow executes trusted-base controls, reuses the actual
installed Task ritual, checks retarget freshness and observes control drift in
base and PR-head data. Application checks remain independent. This addon is
outside the unchanged 47-file installer/update/rollback inventory. Activation,
required-check settings and later guarded-file transitions remain explicit
owner decisions; no live adopter rollout is claimed.

Two more [ongoing improvement companions](distribution/ongoing-improvement.md)
observe retrospective candidates, per-file instruction budgets and optional
official Codex documentation content checkpoints, and classify existing reporter
feedback. Defaults are read-only; separate flags permit a bounded monthly Issue
publication or exact feedback label. Two templates remain inert outside active
workflows. They require their own owner-reviewed activation and do not expand
the adopter CI addon's accepted workflow inventory or any installed payload.

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
It never posts a comment. Malformed UTF-8 and NUL refuse before body validation;
valid Unicode, terminal newlines and the 262144-byte bound remain supported.
Preflight validates the actual body and complete
current ledger, with optional PR-bound chronology and final readbacks; it is
an observation, not authority or a guarantee that a later write is unchanged.

The frontier reuses validated blocker states only within one invocation, keyed
by canonical host/repository/Issue identity. It still validates each Task's full
dependency observation and refuses the complete result on any later failure.
It persists no cache and provides neither an atomic snapshot nor a real-time
lock. The [source-parity disposition](parity-status.md) separates shipped code,
synthetic checks, historical use, deliberate differences and pending live proof.

Governance offers three explicit profiles: `solo`, `team`, and
`single-maintainer` (PR and checks, zero approving reviews, no bypass).
Selection never silently downgrades another profile. Unknown preimages,
conflicting review gates, bypasses or incomplete observations remain
non-success. Setup is an explicit consent-gated actuator; the sensor stays
read-only and considers all contributing Rulesets.

This clean product root preserves the accepted 47-path payload layout and
operation-scoped upgrade/rollback format; bounded current adaptations are recorded separately from
the original export seal. It does not import the predecessor's research ledger,
runtime adapter, historical Tasks or repository release criteria as adopter
authority. Historical acceptance and original unfinished work remain in the
[predecessor records](provenance.md). Product checks here validate the shipped
scope; they do not establish runtime parity or whole-project completion.

See the [installation guide](distribution/source-first-installer.md),
[known limitations](known-limitations.md), and
[contributor validation](../CONTRIBUTING.md).
