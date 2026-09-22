# Known limitations

The kit supplies workflow instructions and bounded helpers. Role files, Skills,
comments and session IDs do not authenticate an actor or enforce Task ownership.
Human review, a single writer, current GitHub records and checks remain required.

## Installation and recovery

The initial download executes trusted code. Use an inspected fixed revision
when appropriate; hashes prove consistency with that selected input, not
publisher authenticity. Use caller-side `pipefail` to detect an initial failed
Bash download. The bootstrap cannot detect a script that was never downloaded.

External installation stages only new files; local installation and local
upgrade/rollback do not stage. Copy/staging failures may leave partial files
and require manual review. Recovery is limited to one recorded local update,
recognizes only recorded pre/post states, and refuses later edits to affected
files. It is not whole-repository reset, automatic update, power-loss atomicity,
an exclusive lock or protection from a malicious concurrent local writer.

Native Windows installation is unmeasured. PowerShell-host tests use synthetic
HTTP responses and Git Bash path conversion fixtures. They do not qualify
Git for Windows, Windows filesystem behavior or every shell environment.

The network updater requires exact old/new commit IDs supplied by the caller;
there is no version registry, automatic detection, scheduled update or force.
Both revisions must use the fixed 47-file layout and the supported unchanged
engine. Arbitrary historical or upstream versions are not supported. The entry
code revision is a separate trust choice from those payload revisions.
Anonymous Git acquisition uses an empty private transport home, disables user
configuration and credential helpers, and refuses authentication/TLS overrides;
this does not protect the caller's initial download of the entry code.

Apply creates a fresh private recovery root and retains it on success or failure.
Do not move, replace or delete its old/new source roots or transaction; rollback
binds the new source's path and filesystem identity. An acquisition/preparation
failure can leave retained inputs without a complete rollback record. An
already-new update retains sources but creates no transaction. Recovery records
are private local data, not bug-report attachments. Preview uses owned temporary
scratch and does not create the requested recovery directory. Exclusive access
is required; neither updates nor rollback promise power-loss atomicity.

## Workflow and helpers

Skill discovery, named roles, delegation and handoffs depend on the selected
Codex client. There is no verified cross-client runtime parity, universal
automatic discovery, authenticated supervision, crash recovery, budget circuit
breaker or immutable identity/control plane. Use explicit installed-file
instructions and available tools; report unsupported or uncheckable states.

Governance/worktree/connector companions run only when explicitly invoked from
a reviewed kit checkout or the [fixed-revision commands](distribution/companion-checks.md).
The latter require trusted Bash/curl/hash tools, validate the complete download
before execution and clean only their owned scratch. This adds no sandbox,
automatic update, crash-cleanup or hostile-concurrent-writer guarantee. Checks
preserve their original exit semantics and require actual inputs; a download
failure is not a sensor verdict. The failure reporter still uses a reviewed
checkout. None are installed or wired into an adopter's CI.
Governance requires actual repository/check/posture inputs and
can return `UNKNOWN` for incomplete API data or unsupported workflow syntax.
CODEOWNERS coverage, bypass approval, independent incident evidence and
retirement authority still need human inspection. Worktree preflight makes no
lock or cleanup guarantee; archive always warns pending human review.

Registry preparation and structural connector checks prove neither activation,
source reachability, context sufficiency nor pin authenticity. Builtin drafts
remain candidates until human-reviewed distillation. Readiness describes a
complete Task brief; it does not imply closed dependencies or dispatch authority.
Within one frontier invocation, a shared blocker is observed once and that valid
state is reused; a later GitHub change is not re-observed until another invocation.
All dependency lists and later errors are still checked. This optimization is
not an atomic snapshot, TTL cache, lock or network-performance measurement.

Failure reports require explicit `--send`, a terminal and literal consent.
An uncertain create response may have created an Issue; inspect before another
invocation. No automatic retry or active receiving-triage service is supplied.
Retrospective blocks produce proposals or bounded diffs, not owner approval,
automatic policy retirement, runtime learning or upstream publication.

The [ongoing improvement companions](distribution/ongoing-improvement.md) offer
explicit reports and receiving-side routing with synthetic transport evidence.
Exact HTML checkpoint changes can include layout or unrelated ChatGPT changes;
they do not establish semantic capability or runtime availability. Distinct
evidence links do not prove independent incidents. Finite final readbacks cannot
make GitHub observations atomic, and bounded pages/time/output may refuse large
repositories. Unknown is non-success. Monthly report no-ops require exact
content, so a later changed observation needs human review rather than overwrite.
Templates are inert and have no active schedule; deployment into a guarded
adopter requires a separate reviewed workflow-inventory transition. Classification
does not authenticate the sender or prove consent, execution or Task authority.

## Evidence scope

The [opt-in adopter CI addon](distribution/adopter-ci.md) supports one static
application workflow in a deliberately narrow YAML subset. Unsupported
workflows, incomplete API identity, pagination/resource bounds or changing
observations refuse. It requires a separate reviewed installation and later
owner check activation. Its three files are outside legacy update/rollback;
guarded-file changes need an owner-reviewed transition and cannot be forced
through setup. Initial installation cannot run missing trusted-base code.
Metadata may require manual reevaluation after code CI completes; Task/comment
edits alone are not continuously watched. Read-only permissions, pinned Actions,
trusted-base execution and consistent digests do not make mutable workflow
definitions an immutable security boundary or make finite API reads atomic.
NO_RETARGET is not application-code success. A normal base-SHA advance without
retarget is outside historical run freshness, but metadata retains an exact
event/current-base SHA binding for trusted control checkout. An old metadata
event can therefore require a new PR event after base advancement; rerunning
that old event does not refresh its payload. Live adopter Actions deployment
and native Windows addon setup are unmeasured.

Product conformance uses real Bash, Git and jq with disposable local fixtures
and synthetic external transport. It is not live Codex E2E, live governance,
native Windows qualification, original scenario passes or release acceptance.
The predecessor's unfinished runtime and release work remains historical in
[provenance](provenance.md). This migration does not declare it completed.
The [source-parity disposition](parity-status.md) explicitly retains manual
installed-revision recording, source-checkout feedback and inert scheduling as
intentional differences. Current-version live adopter/worker/CI integration is
pending; accepted old use and new synthetic checks are different evidence.

The [installation guide](distribution/source-first-installer.md) explains
operations and trust boundaries; [product scope](product-scope.md) lists what
ships, and [CONTRIBUTING](../CONTRIBUTING.md) lists current validation commands.
