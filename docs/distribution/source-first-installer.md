# Source-first local installer

This bounded implementation follows the owner-approved course correction in
[Epic #22](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/22#issuecomment-5589963251)
and [T14 plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/27#issuecomment-5590011621).
The behavioral source is `mochan-tk/agentic-dev-kit-for-copilot` at
`fd265ddef150fab86cd54d0e383c2c25fe297ffb`.

## Local use

Inspect the local source checkout first. Create an adopter Git repository
yourself if needed. Do not run concurrently with another writer in it.

```sh
bash .github/scripts/scaffold-init.sh --dry-run /path/to/adopter
bash .github/scripts/scaffold-init.sh --apply /path/to/adopter
```

The default is dry-run. `SCAFFOLD_SOURCE_DIR` optionally selects a local
checkout or distribution root containing `.github/distribution/`; relative
paths resolve before changing directories. There is no network source mode.
Windows uses `.github/scripts/scaffold-init.ps1 --dry-run TARGET` and
`--apply TARGET` through adjacent Git Bash. Bash 3.2+, Git, find, and either
sha256sum or shasum are needed; no Python package or Rulesync is required.
Drive-form source and target paths use Git Bash's existing `cygpath -u`;
missing or unsuccessful conversion fails rather than prepending the current
directory. This boundary is mocked in offline tests, not measured on Windows.

Review the plan before apply. Review the resulting Git diff, then stage,
commit, and push explicitly. Invoke `$project-onboarding` in Codex. Keep the
remote-default-before-GitHub-write, clean-checkout verify-by-running,
evidence-PR, and durable deferred-work ledger gates from the source workflow.
The installer itself runs none of the optional GitHub setup helpers.

Installed shell files retain mode 0644: invoke the documented helpers with
`bash`, or the existing PowerShell Git Bash entrypoint. The optional ritual
sensor binds Task-less bootstrap exceptions to complete trees at the PR's
exact base/head commits and an exact installed frontier-engine blob. It does
not depend on a changelog marker: existing adopter changelog, README and AGENTS
remain preserved. P0 records the adoption commit/tree; P6 links those records
and verifies actual CUSTOMIZE removal plus bounded onboarding-only outputs.
Initial adoption requires confirmed file absence, never a failed API read.
An unrelated or unsupported PR uses the ordinary Task ritual. These are
structural Git fixture checks, not proof of live GitHub or native Codex runtime.

## Exact payload and preservation

`payload.v1.tsv` records the closed 47-file payload, preservation class, and
SHA-256. `source-parity.v1.json` records each frozen source path/blob and its
target digest/adaptation. The trusted installer pins the exact path/class
layout and checks every source digest before planning. The required
`check-installer.py` independently validates the same inventory and provenance.

| Class | Existing identical file | Existing changed file |
| --- | --- | --- |
| engine: Skills, roles, templates, helpers, connectors, protocol reference | no-op | refuse the whole preflight plan |
| tuned: AGENTS and project instructions | no-op | preserve |
| instance: agreement/context seeds and local changelog | no-op | preserve |
| seed: README, gitignore, gitattributes | no-op | preserve |

Missing files are copied only by `--apply`. Unrelated adopter files are never
selected. Source/target/ancestor/leaf symlinks, broken links, path escapes,
unlisted payload files, missing inputs, modified inventory layouts, and file/
directory collisions fail closed. A failing inventory enumeration is not an
empty or successful inventory. Existing Git metadata and index are untouched.
Plain installation supports no overwrite, force, automatic init, stage or commit.
After preflight, a copy error can leave a reported partial install; review it
before re-running. This is not atomic rollback or an adversarial concurrent
filesystem mutation guarantee.

Eight Skills preserve source workflow semantics using `.agents/skills`.
Three source role prompts become `.codex/agents/*.toml` instructions without
model/permission overrides. Project coordination observes sibling Epics;
Epic -> Task -> Worker is intended delegation, not a fabricated Codex API.
Use a supported, capability-checked thread surface or a durable manual handoff.
`.github/instructions` are explicit references, not claimed Codex auto-preload.

Development-only Task IDs, accepted context pins, sole-active policy,
conformance stores, CI workflows, CODEOWNERS, private MCP configuration,
runtime adapters and Colima infrastructure are excluded. Optional connector
and GitHub helper procedures are not mandatory services or install actuators.
The installed frontier helper refuses unavailable/malformed dependency reads;
manual graph review is needed when the installed `gh` lacks `blockedBy`.
The MIT notice is included in the mandatory engine frontier helper, even if
an adopter's existing README is preserved; the adopter's LICENSE is not replaced.

## Source reuse, fixes, and intentional differences

The Bash installer reuses local-copy planning, preservation classes,
collision refusal, source hashes, and no-commit behavior. Necessary fixes are
source-root binding before target traversal, explicit payload/unsafe-path
refusal, checked enumeration, and complete planning before mutation. The
source frontier's suppressed GitHub failures are corrected to fail closed.

Codex-native adaptations are native Skill paths and role TOML, explicit
instruction reading, verified available tools/manual handoffs, and replacing
the Copilot app's Project-parent workaround. Source onboarding P0/P3/P6 gates,
ownership, chronology, escalation, and verification remain load-bearing.
The source-specific monthly platform baseline and cloud setup are explicitly
not installed. Adopter CI/setup commands must be observed and run locally.

Intentional convenience differences are local-source only, dry-run by default,
explicit apply, existing Git root, no network bootstrap, no automatic staging,
and no force. PowerShell calls adjacent reviewed Bash rather than downloading a
moving main script. These limits avoid exporting kit development governance as
adopter truth.

## Builtin context kickoff entry

T22 restores the frozen source's `.github/prompts/kickoff-context.prompt.md`
entry through the existing installed context-collection Skill. The source
prompt blob is `9b565657def003a3c04cfd9ec6e67578ff7d2906` at the frozen source
commit above. The builtin draft-first procedure, source-selection helper and
context-distillation Skill already ship; this change repairs their navigation.
It adds no Skill, algorithm, helper, service or execution surface.

In Codex CLI or IDE, explicitly request
`$context-collection Start builtin kickoff for <topic>; I have no existing requirements source.`
On another client, explicitly ask to use the installed
`.agents/skills/context-collection/SKILL.md` for builtin kickoff. This is
instruction guidance, not evidence that invocation works on every client.
The Skill links to installed `.github/connectors/builtin.md#retrieve` and reads
that procedure only when builtin kickoff is selected. Ordinary collection and
existing-source connectors keep their original route.

The sequence is collect/draft, optionally prepare the source registry with
the existing `bash .github/scripts/setup-sources.sh`, then use reviewed
activation/distillation when appropriate. The optional helper has GitHub
preflights and writes a proposed registry; it does not activate the source,
prove context sufficiency or run automatically. It and context-distillation
remain byte-identical. No real helper or service is exercised for T22.

Candidate `REQ-C##` drafts remain under `.github/docs/context/<topic>/`, separate
from faithful source material and accepted `REQ-###` agreements. Preserve
provenance, redaction, unknown markers, assumptions and dated Q&A. Repeat bounded
draft/question rounds until resolved or the human stops, retaining unanswered
questions. Finish with promotion-worthy candidates and reasons. Kickoff does
not write agreements; the existing human-reviewed distillation PR is the
promotion gate, and activation/sufficiency retain their existing review gates.

T22 changed only the collection Skill, builtin definition and installed README.
All 47 paths, preservation classes and modes remained; the other 44 payload files
were byte-identical to accepted T21 at T22 acceptance. The README is a seed: existing adopter README
files stay intact, so the engine Skill and builtin links work independently of
the README. A known-old upgrade updates only the two changed engine files and
preserves existing seed/tuned/instance content; operation rollback restores the
old engines without changing unrelated files or Git state.

The existing parity record's `context_kickoff` section binds the additional
prompt blob/SHA-256, original collection/builtin/README source blobs and exact
three target digests/modes. The payload component `validate()` checks the
selected routing/review anchors and relative installed links; its public API
and the CLI composition with the existing companions remain compatible.
Self-consistent rehashed negative fixtures still fail for missing/misrouted
entry, missing human-stop/privacy/question/candidate boundaries, unsafe
promotion and dangling resources. This is a narrow instruction guard, not a
general natural-language or Markdown validator.

Disposable synthetic adopters run actual Bash install, known-old upgrade and
operation rollback against the accepted old/current bytes. These observations
verify distributed instructions, file preservation and guard behavior. They
do not establish model adherence, useful requirements, successful elicitation,
activation, human approval, sufficiency, authenticated roles or runtime parity.

## Task creation and verified readiness

T23 corrects the frozen source's Task creation atomicity assumption through the
existing installed planning Skill and mode-0644 helper:

```sh
bash .agents/skills/plan-management/scripts/new-task.sh -t "Task title" -b task-body.md -p 12 -e cli -d 14,15 --ready
```

The original `gh issue create --parent [--blocked-by]` flow remains one create
attempt. It sends `type:task` and the selected `exec:*` label without initial
`ai:ready`. A successful-looking create URL alone is insufficient. The helper
resolves the repository first, then reads back the exact issue URL/number/ID,
title and body, requested parent, complete unique blockers and required labels.
Only explicit `--ready` adds readiness after that verification, followed by a
second full read-back with the same issue and relationship IDs. No-ready verifies
without adding readiness. OPEN blockers are allowed: `ai:ready` describes the
brief, while the unchanged frontier determines whether execution may begin.

In [gh 2.96.0 create.go](https://github.com/cli/cli/blob/b300f2ec7ec9dc9addc39b2ad88c54097ded7ca0/pkg/cmd/issue/create/create.go#L410),
IssueCreate precedes DeferredUpdateIssue and URL printing. One CLI call is not
an atomic GitHub transaction. Create/link failures can leave an issue without
a returned URL; failed readiness edits can already have applied the label.
Every ambiguous write or failed read remains unconfirmed/non-success. The
helper prints a safely resolved known Task URL when available, then stops.
There is no automatic retry, deletion, repair, rollback or guess that zero
changes occurred. Inspect current state before another explicit invocation.

The helper uses gh's actual exported JSON: parent is an issue object, blockers
have nodes/totalCount (first 50), and labels are a flat array (first 100), as
shown in the [query builder](https://github.com/cli/cli/blob/b300f2ec7ec9dc9addc39b2ad88c54097ded7ca0/api/query_builder.go#L401)
and [export implementation](https://github.com/cli/cli/blob/b300f2ec7ec9dc9addc39b2ad88c54097ded7ca0/api/export_pr.go#L18).
No exported repository node is invented; canonical URLs bind the selected host
and repository. Require integral complete blocker counts of at most 50 and
fewer than 100 unique labels; 100 cannot prove completeness. Missing, malformed,
duplicate, mismatched or unsupported responses refuse success.

Inputs are bounded to a 256-byte non-control title, a regular non-symlink body
of 1..65536 bytes without NUL, and 50 unique positive same-repository dependency
numbers. Snapshot the body in private temporary storage before ownership
validation and creation. The existing ownership-body grammar still gates
`--ready`; an unfinished no-ready brief need not pass that readiness grammar.
Standard base64/head/cmp tools supplement Bash and gh; external jq or Python
is not required by this helper. Query projection output is capped at 128 KiB;
repository/create/edit output at 4 KiB. Raw body/tool output is not printed.
Scratch data is removed on ordinary exit; no general crash/process supervisor
or hostile same-user race guarantee is claimed.

With the owner-approved source-preparation supplement below, three engine
files change; the other 44 payload byte sequences
and all 47 paths/classes/modes remain unchanged from accepted T22. Existing
parity records bind original frozen helper/Skill blobs, the reviewed gh source
revision and new target digests. Actual Bash fake-gh fixtures test sequencing,
failure boundaries and real jq evaluation of the same query against raw CLI
shapes. Disposable install/known-old upgrade/operation rollback preserves
adopter README, tuned/instance/application content and Git state. No modified
helper is run against a live service, and no runtime or completion claim follows.

## Safe source preparation and the planning path

The same T23 package also updates the existing mode-0644
`.github/scripts/setup-sources.sh`. The
[frozen donor helper](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/blob/fd265ddef150fab86cd54d0e383c2c25fe297ffb/.github/scripts/setup-sources.sh)
follows registry symlinks when inspecting/appending and can create through a
dangling link. That is source-inherited behavior, not a reported real-adopter
incident. The target adds a bounded repository-relative refusal before registry
inspection and writing: reject symlinked invocation ancestry within the checkout,
symlinked registry parents or leaf (including dangling links), special-file or
directory destinations, and non-directory parent obstructions. Do not remove
or repair these entries. OS ancestors above the repository are outside this
check; no hostile same-user race, locking or power-loss transaction is claimed.

Ordinary root and nested invocation retain the existing remote/auth/plan checks,
connector choice, confirmation and pending-activation instructions. Speckit
history is now read from repository-root `specs/` even when invoked below root;
the inherited cwd-relative lookup otherwise missed that pin. New registry mode
continues to follow the caller's umask. Appending preserves existing bytes and
mode; an exact duplicate heading is a no-op. Dry-run previews even a duplicate
without writes or confirmation, but is not offline: preflight still makes
read-only GitHub queries. A registry is not collected material, reviewed
activation, a sufficient context package, or authority to dispatch a Task.

Actual installed Bash helpers are chained only by disposable tests, sharing a
stateful fake GitHub transport: prepare a pending registry, create and verify
the Task, then call the unchanged frontier. A ready Task remains blocked while
fixture blockers are OPEN and becomes actionable only when all observed
blockers are CLOSED. No-ready and failed/incomplete observations produce no
actionable Task. Unsafe registry preparation stops the test driver before any
Task call. The fake persists actual creation and label effects; frontier reads
those labels rather than a preloaded ready row. This is deterministic plumbing
evidence, not context quality, activation, real GitHub or runtime proof.

The combined 11-file scope retains all 47 payload paths/classes/modes and
changes only the planning Skill, Task helper and source-preparation helper;
the other 44 files remain byte-identical to accepted T22. Original source blobs
remain pinned beside new target digests. A real Bash known-old upgrade and
operation-scoped rollback covers all three engines while preserving adopter
registry, README, tuned/instance/application bytes and modes. No new production
orchestrator, Skill, frontier rule, Task ritual or activation actuator is added.

## Preservation-safe local upgrade and operation-scoped rollback

T19 reuses the frozen source's engine/tuned/instance class dispatch and
two-version preservation tests. It does **not** reuse blind engine overwrite,
automatic staging, changelog replacement or broad path discovery. Known-old
checks, prewrite backups and explicit operation rollback are target additions.
The 47 shipped payload paths/classes/bytes/modes and source blob IDs are unchanged.

Select inspected local old/new roots containing `.github/distribution/`, an
exclusively owned adopter Git root, and a new private transaction directory whose
parent already exists. Sources and transaction must not overlap the adopter;
the transaction must not overlap either source. The new root is selected with
`SCAFFOLD_SOURCE_DIR`; `--old-source` is mandatory for upgrade. Old and new may
be the same inspected source (a no-op if everything is present). Both inventories
must contain exactly the reviewed 47 ordered paths/classes, with single-link
regular mode-0644 payload files and valid SHA-256 digests. A self-consistent
manifest is integrity relative to the chosen input, **not source authenticity**.

```sh
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --dry-run /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --apply /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --dry-run /path/to/adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --apply /path/to/adopter
```

The reviewed script being executed must support these options; do not execute an
unreviewed script from a source merely because its inventory validates. The
unchanged PowerShell entrypoint forwards the same arguments to Bash. Standard
BSD/GNU `stat`, `cp`, `sort`, `wc`, `rmdir`, and `sync` supplement the installation
prerequisites; no new Python, jq, service, or package installation is required.

Upgrade preflights the **whole** fixed inventory before mutation. Existing
engine files must equal the old bytes/mode (replace), or the new bytes/mode
(no-op); all other engine states refuse. Existing tuned, instance and seed files
are preserved, including their custom modes. Missing files of any class may be
installed, recording original absence. Unrelated files are never selected.
Dry-run creates neither target nor transaction; an already-new apply creates no
transaction. A supplied pre-existing transaction is always refused by upgrade.

### Private recovery record

Before target writes, apply exclusively creates the mode-0700 transaction root,
then prepares and checks **all** necessary numbered byte backups and the complete
data-only `local-upgrade/v1` record, flushing it with `sync`. Records/backups stay
local; do not upload them as evidence. Fixed files are:

- `meta.tsv`: schema, digest of target canonical path/device/inode, digest of
  transaction canonical path/device/inode, old/new inventory digests, and
  old/new canonical source path/device/inode digests;
- `files.tsv`: strictly increasing fixed-inventory index, relative path, old
  SHA-256 or `-` for confirmed absence, and expected new SHA-256 (mode 0644);
- `directories.tsv`: sorted relative directories absent before this operation;
- `before-N`: exact original engine bytes for the Nth affected entry, when any;
- `record.sha256`: digest of metadata/files/directories; a self-consistency seal,
  not a signature or proof against a malicious record author;
- `status`: prepared/applied/partial/rolled-back plus completed-file progress.

Input/backup payload files are limited to 1 MiB each, record inputs to 16 KiB,
47 affected files and 128 directories. Links, special files, malformed/extra
records, escapes, wrong target/source binding and tampered backups refuse. Data
is parsed, never sourced/evaluated. Completion is reported only after affected
states are verified and the final operation status is written/flushed. No Git
HEAD/index operation, automatic staging, GitHub operation or credential access
is part of installation, upgrade or rollback.

### Recovery and refusal

Rollback requires the same new inventory, target root and transaction root. It
preflights the complete record, all backups and all affected target states
before writes. Only recorded pre/post bytes with exact 0644 mode (or recorded
absence) are recognized. A later affected-file edit, mode change, missing backup,
unknown partial bytes, symlink or identity drift stops without forcing a restore.
Unrelated later application/document edits remain unchanged.

Restore only overwritten engine bytes/modes; remove only files created by this
operation that still match its post-state. Remove only recorded operation-created
directories after checking they contain no unrelated entries, using `rmdir` when
empty. A later unrelated child in one of those directories refuses the whole
preflight and is preserved. Pre-existing directories are never removed. A
validated repeated rollback of an already restored operation is a zero-write
no-op; it does not reinterpret later changes as rollback targets.

The supported interrupted-apply test fails the second engine copy after the
first completed. The prewritten record/backups and partial progress remain;
explicit rollback restores recognized pre/post states. Errors before complete
record preparation leave the target unchanged and may require manual review of
the retained incomplete transaction. Unknown partial writes refuse, and errors
during rollback remain partial/non-success. There is no automatic crash recovery,
whole-project reset, power-loss atomicity, concurrent-writer guarantee or
malicious same-user race resistance. Keep exclusive ownership for the operation.

## Optional local installer failure report

T20 adds a standalone, explicitly invoked companion **outside the 47-file
installed payload**. Use the reviewed kit checkout's mode-0644 Bash entrypoint:

```sh
bash .github/scripts/report-installer-failure.sh --draft --line 42 --exit-code 1
bash .github/scripts/report-installer-failure.sh --send --line 42 --exit-code 1
```

The default is `--draft`. The only metadata options are `--line` (canonical
decimal 1..999999) and `--exit-code` (1..255); omitted values are `unknown`.
Invalid/duplicate arguments reject, including arbitrary script, title, body,
recipient, free text and `--yes`. A caller-supplied line/exit code is a user
report, **not measured proof of any earlier installer execution**. The helper
neither reads nor modifies adopter files, Git state, operation records or
backups, and cannot repair or change the earlier installer's exit/result.

The exact eight fields are Script (`scaffold-init`), Failing line, Exit code,
OS / arch, bash version, gh version, jq version, and Scaffold version
(`unknown`). Fixed field grammars reject oversized or unexpected observations
to `unknown`; OS/architecture use closed known values, tool versions use
numeric/version-specific forms. The canonical gh version line may include its
official public release-URL second line; unrelated extra content is rejected.
Terminal tool-output newlines are normalized only after checking the byte
bound, and NUL bytes become rejected controls rather than disappearing.
An unfamiliar platform/version
format is unknown, not a compatibility claim. Tool observation/creation stdout
is captured to a 256-byte bound, with overflow as non-success and stderr
discarded. There is no raw-log, command, path, environment dump, credential,
private repository identity, branch, transcript or free-form payload input.
The companion uses normally installed trusted shell/version/gh tools; it is
not a sandbox or general process-lifetime supervisor.

Draft prints the exact destination, title and body, never prompts or performs
an Issue operation, and requires neither `gh`, `jq` nor an account. Optional
version observations do not authenticate. Send additionally requires an
explicit `--send`, available `gh`, stdin **and** stderr TTYs, and empty `CI`
and `GITHUB_ACTIONS`; even `CI=false` blocks. The full **public** destination,
existing-account disclosure and exact in-memory title/body are shown before
`Send this public report? [y/N]`. Only the entire literal answer `y` or `Y`
allows one Issue-create attempt. Terminal consent bytes are checked before
Bash string normalization, so NUL-containing answers cannot become `y`.
Empty, EOF, other answers and piped consent
do not send; environment variables, changelog markers and config do not arm
consent or select the recipient.

The only destination is
`https://github.com/mochan-tk/agentic-dev-kit-for-codex`. The call uses this full
`--repo` and fixed `GH_HOST`/`GH_REPO` hints, neutralizing caller host/repository
overrides. It uses the user's already configured GitHub account; it does not
log in, create labels, use another repository or retry. Preview and request
share the same in-memory strings. No file is used as a draft carrier.

| Result | Exit | Meaning |
|---|---|---|
| `drafted` | 0 | Safe draft printed; no Issue operation. |
| argument rejection | 2 | Usage rejected; no Issue operation. |
| `declined` | 3 | No literal y/Y consent; no Issue operation. |
| `send-unavailable` | 4 | TTY/CI/tool gate closed; no Issue operation. |
| `confirmed` | 0 | Create returned a validated fixed-recipient Issue URL, printed on stdout. |
| `submission-unconfirmed` | 5 | Nonzero, oversized, missing or invalid create response; no raw response projected. |

A network/API failure can occur after server creation. Unconfirmed is **not**
proof that nothing was filed. Cancellation during creation is also uncertain;
inspect the public repository manually before considering another explicit
invocation. There is no automatic retry, deduplication, rollback, URL read-back
or receiving-triage service. Confirmation means a validated create response,
not a separate read-back or authenticated report provenance.

### Frozen reuse and bounded adaptations

`feedback-lib.sh` reuses the frozen Copilot `_fb_field` single-line bounds,
`_fb_isatty`, fixed-field rendering, preview/consent order and one-create flow.
The source's automatic `feedback_arm` ERR/EXIT wiring is intentionally not
ported: `scaffold-init.sh`, `operation_finish`, exit codes and backups remain
unchanged. Marker-derived recipient/version becomes the fixed public target
and unknown Scaffold version. Numeric version forms are narrower, draft is
available offline, and uncertain submission replaces the source's unsupported
“nothing was filed” failure statement. Source fake-GitHub tests are adapted to
actual bounded PTY fixtures, not a production TTY-bypass flag.

The existing parity JSON retains all 47 payload rows unchanged and adds a
separate `feedback_companion` record. It binds the source library/test/ADR/
privacy blobs at `fd265ddef150fab86cd54d0e383c2c25fe297ffb`, exact companion
file hashes/modes, closed fields, recipient and limitations. It does not turn
the source's ADR into target permission or copy development truth to adopters.
No automatic instrumentation, live-send proof, Windows execution, receiving
workflow, retrospective promotion or full K16 completion is claimed.

## Optional offline connector-definition validation

Use the source-derived standalone companion from a reviewed local kit checkout:

```sh
bash /path/to/reviewed-kit/.github/scripts/check-connectors.sh --target /path/to/adopter
```

An explicit existing target is mandatory; there is no current-directory or
kit-root fallback. This Bash 3.2+ command uses standard find/head/tr/grep/sed/awk
only. It never calls Git, GitHub, authentication, a model or a network service,
changes files, applies fixes, writes an activation registry or modifies CI.
No existing adopter is updated. The 47 installed payload files remain unchanged;
their README truthfully says this validator is not installed automatically.
The separate source-only companion provides the optional explicit invocation.

The frozen Copilot checker at `fd265ddef150fab86cd54d0e383c2c25fe297ffb`
supplies `err()`, `check_connector()`, framework checks, Metadata extraction,
definition enumeration and the twelve structural fixture cases. The target
requires readable regular `README.md` and `CONNECTOR-TEMPLATE.md` and at least
one other `.md` definition in `.github/connectors/`. Each definition needs
exactly one bullet per `name`, `access`, `reach`, `trust-default`, `status`
inside `## Metadata`, no undeclared Metadata bullet, a nonempty name equal to
its filename stem, `core|community|experimental` status, and headings
`## discover`, `## retrieve`, `## pin`, `## verify`.

The inherited textual grammar allows heading trailing whitespace and indented
continuations. It is not a full Markdown parser: operation bodies, other field
values, duplicate headings, service availability, requirement sufficiency and
pin authenticity are not proven. The source's empty-name bypass is corrected.
Hidden `.md` entries are included rather than silently skipped. Framework files
are checked for bounded readability, not parsed as definitions.

Target/ancestor/directory/leaf symlinks, non-regular inputs, unavailable reads
or enumeration fail closed. Inputs are limited to 1 MiB each and 128 definitions;
NUL cannot disappear during Bash capture. At most 32 itemized errors plus a
fixed truncation marker are printed. Diagnostic labels use `definition-N` and
fixed fields/reasons, never raw names, values or full private paths. Ordinary
trusted local tools and an unchanged target during the read are prerequisites;
these checks are not an atomic snapshot or hostile same-user race isolation.

| Exit | Meaning |
|---|---|
| 0 | Structural checks passed (or `--help` displayed); no activation proof. |
| 1 | Confirmed missing framework/definition or invalid structure. |
| 2 | Invalid or incomplete explicit command arguments. |
| 3 | Filesystem, read, tool or bounded-input state is uncheckable/unsafe. |

`connector_companion` in the existing parity JSON binds the exact frozen
checker/test blobs and the target checker/test bytes and mode 0644. Required
quality composes connector validation with the existing payload/feedback
components; calling only the legacy `validate()` component does not validate
this companion. Required conformance discovers `test_connector_validation.py`,
which executes the actual checker against disposable fixtures and shipped
builtin/speckit definitions. Live policy binds this exact execution edge; an
absent suite, missing discovery or absent quality provenance gate fails.
No workflow, registry, installed payload, existing feedback behavior or N1
limitation changes. These tests are not canonical scenario passes or full K06,
runtime, K16, Phase 2 or release completion evidence.

## Task selection observations

T24 retains the existing frontier and ownership sensors and planning Skill.
Readiness still describes a complete Task brief; frontier membership means the
observed dependencies are closed. Before delegating multiple Tasks, explicitly
check their ownership with
`bash .github/scripts/ownership-overlap.sh -R owner/repo 23 24` and apply the
Task's execution authority. Nothing here automatically dispatches work.

The ownership sensor rejects interior `.` components and redundant `/`
separators as `UNCHECKABLE` (exit 3) before comparing literal prefixes. One
leading `./`, ordinary paths and conservative glob overlap remain supported.
`OVERLAP` (exit 1) requires serialization or reviewed repartitioning;
`NO_OVERLAP` (exit 0) is only a supported declaration observation. No symlink,
inode, filesystem alias resolution or process isolation is claimed.

The frontier first resolves the selected repository through a read-only
`gh repo view`. Bare numbers, repository objects and URL references become
case-normalized host/repository/number identities before duplicate detection.
Valid cross-repository blockers on the selected host remain supported, including
identical numbers belonging to different repositories. Foreign-host references
are unsupported and refuse. Missing or contradictory identities, duplicate
aliases, incomplete connections, unknown states and failed reads produce no
partial actionable output. Complete gh connections and tested legacy arrays
retain their existing support and limits; an empty ready list remains a
successful observation distinct from a failed read.

The stateful fake GitHub fixture now creates its synthetic issue from actual
argv and actual body-file bytes, then applies explicit response defects. Label
edits likewise use the requested labels and exact target. Deliberate installed
helper copies sending an empty or wrong body file or incorrect readiness label
must fail. The unchanged production Task helper retains its private body
snapshot even if the caller file changes before creation. This is offline
transport fidelity evidence, not a live GitHub transaction claim.

The only ritual change adds the exact new frontier blob to the existing
adoption-anchor allowlist. Both accepted historical anchors remain; unknown
anchors, mixed base/head anchors, malformed or incomplete tree observations and
PR drift still refuse. Current-payload initial adoption and onboarding run
against the new anchor without substituting historical payload bytes.

This package retains all 47 payload paths, preservation classes and mode 0644.
Only the frontier, ownership and ritual engines and planning Skill change;
the remaining 43 payload files are byte-identical to the accepted T23 base.
Known-old upgrade and operation-scoped rollback fixtures prove preservation
of tuned surfaces, adopter registry bytes/modes and unrelated Git state.
`task_selection` in the existing parity JSON binds frozen source provenance
and exact target bytes. No existing adopter is migrated by these tests.

## Evidence boundary

Disposable local adopter tests cover real copy/dry-run/preservation, rejection,
Git-state invariance, source/inventory drift, and fail-closed frontier behavior.
The shell suite checks entrypoint arguments and syntax; required CI also runs
the full deterministic test registry and pinned Linux lint tools. Source file
parity is not runtime evidence. Windows, named-agent selection, sibling-thread
control, clean-adopter live E2E, automatic upgrade/rollback, and full parity
remain unmeasured or incomplete. T12 stays paused and unaccepted; no VM is
needed for this installer or its tests.

Phase 2 and the repository remain incomplete. All 136 scenarios remain
`not-run`, release-level `results: []`, and `release_blocked=true` remain intact.
