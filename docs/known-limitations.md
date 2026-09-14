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

## Workflow and helpers

Skill discovery, named roles, delegation and handoffs depend on the selected
Codex client. There is no verified cross-client runtime parity, universal
automatic discovery, authenticated supervision, crash recovery, budget circuit
breaker or immutable identity/control plane. Use explicit installed-file
instructions and available tools; report unsupported or uncheckable states.

Governance/worktree/connector/failure-report companions run only when explicitly
invoked from a reviewed kit checkout. They are not installed or wired into an
adopter's CI. Governance requires actual repository/check/posture inputs and
can return `UNKNOWN` for incomplete API data or unsupported workflow syntax.
CODEOWNERS coverage, bypass approval, independent incident evidence and
retirement authority still need human inspection. Worktree preflight makes no
lock or cleanup guarantee; archive always warns pending human review.

Registry preparation and structural connector checks prove neither activation,
source reachability, context sufficiency nor pin authenticity. Builtin drafts
remain candidates until human-reviewed distillation. Readiness describes a
complete Task brief; it does not imply closed dependencies or dispatch authority.

Failure reports require explicit `--send`, a terminal and literal consent.
An uncertain create response may have created an Issue; inspect before another
invocation. No automatic retry or receiving-triage service is supplied.
Retrospective blocks produce proposals or bounded diffs, not owner approval,
automatic policy retirement, runtime learning or upstream publication.

## Evidence scope

Product conformance uses real Bash, Git and jq with disposable local fixtures
and synthetic external transport. It is not live Codex E2E, live governance,
native Windows qualification, original scenario passes or release acceptance.
The predecessor's unfinished runtime and release work remains historical in
[provenance](provenance.md). This migration does not declare it completed.

The [installation guide](distribution/source-first-installer.md) explains
operations and trust boundaries; [product scope](product-scope.md) lists what
ships, and [CONTRIBUTING](../CONTRIBUTING.md) lists current validation commands.
