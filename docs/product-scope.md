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
This is a delivery route to the unchanged helpers, not an installer mode or
automatic CI integration. The failure reporter is excluded from that route.
Installation does not create
CI, configure GitHub, commit, push, run onboarding or invoke a model.

The installed workflow covers onboarding, context collection and builtin
drafting, human-reviewed distillation, Epic/Task planning and readiness,
ownership and routing, supervision and handoff, verification, and retrospective
proposals. Humans retain agreement, exceptions, acceptance and merge authority.

This clean product root preserves the accepted source's 47 payload files and
installer engine. It does not import the predecessor's research ledger,
runtime adapter, historical Tasks or repository release criteria as adopter
authority. Historical acceptance and original unfinished work remain in the
[predecessor records](provenance.md). Product checks here validate the shipped
scope; they do not establish runtime parity or whole-project completion.

See the [installation guide](distribution/source-first-installer.md),
[known limitations](known-limitations.md), and
[contributor validation](../CONTRIBUTING.md).
