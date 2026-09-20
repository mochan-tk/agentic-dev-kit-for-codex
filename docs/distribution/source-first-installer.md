# Source-first installer

Read [product scope](../product-scope.md), [limitations](../known-limitations.md) and
[source provenance](../provenance.md) for shipped behavior and historical acceptance.

## One-command first installation

From an existing adopter Git root, the README Bash and PowerShell pipelines
need no kit clone. External invocation defaults to apply and stages only files
created in that invocation. Explicit --dry-run changes neither adopter files
nor index; disposable acquisition scratch is separate and removed on exit.

For an immutable reviewed revision, replace FULL_COMMIT_SHA with its full
40-character SHA in both places, so initial entry and selected source agree:

```sh
set -o pipefail; curl -fsSL https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/FULL_COMMIT_SHA/.github/scripts/scaffold-init.sh | SCAFFOLD_REF=FULL_COMMIT_SHA bash
```

The standard main command follows the current branch; use
set -o pipefail before the pipeline when the calling shell must detect an
initial HTTP failure. Plain curl | bash reports the last command's status:
if curl supplies no script, Bash may return zero without executing anything.
The bootstrap cannot detect its own absence. Canonical Git acquisition or
validation failures after entry execution always return nonzero.

SCAFFOLD_REF selects a branch, lightweight/annotated tag or full commit.
Branch lookup precedes peeled and lightweight tags. Resolution happens once,
then the exact commit is fetched into a private bare repository. FETCH_HEAD,
Git object integrity, regular-blob modes, exact path/class layout, all 47
payload digests and the unchanged local engine digest must validate before
executing selected code or touching the adopter. No archive extraction,
checkout, filters, hooks, credential helper, GitHub authentication or new
package is required. Only the selected revision's wrapper then dispatches its
engine and stages; an older initial wrapper never applies its stage policy to
a different selected revision. The private dispatch mode is a process routing
boundary, not an authenticated identity or a general recursive bootstrap API.

The initial downloaded script remains trusted executable code. A floating main
URL can change; use reviewed immutable URLs when needed. Commit/blob/hash checks
establish integrity and consistent provenance, not publisher authentication.
Source payload, inventory, wrapper and engine all originate in the reported
exact SHA. Fixed-SHA examples must select that same SHA, including PowerShell:

```powershell
$env:SCAFFOLD_REF = 'FULL_COMMIT_SHA'
irm https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/FULL_COMMIT_SHA/.github/scripts/scaffold-init.ps1 | iex
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/FULL_COMMIT_SHA/.github/scripts/scaffold-init.ps1))) --dry-run 'C:\path with spaces\adopter'
```

PowerShell only locates Git for Windows Bash, downloads/dispatches the Bash
entry, forwards an argument array and surfaces its failure; iex does not exit
the interactive session. A saved local shim dispatches its adjacent entry.
WSL is never substituted. PowerShell-host synthetic tests are separate from
native Windows execution, which remains unmeasured.

Before apply, the unchanged local planner validates every source and target
path. Missing tracked paths, staged deletions, other conflicting index state,
ignored new paths and unsafe/locked index refuse before file writes. Staging
uses exact raw blobs through hash-object --no-filters and one update-index
operation, preserving unrelated index entries and partial staging. Configured
clean/process filters are masked for that one index update: Git can
otherwise invoke them while rechecking existing index entries. This changes no
adopter configuration. Failed or malformed filter-key enumeration refuses.
Existing preserved files and rerun no-op paths are not selected. No Git init, commit,
push, force or automatic cleanup of adopter files occurs. Copy or stage failure
is non-success and may leave partial installed files; inspect files and index
for manual recovery. Keep the adopter exclusively owned during installation.

Review git diff --cached, land the reviewed adoption on the remote default
branch, then invoke the installed project-onboarding Skill. Setup helpers are
never run by the installer.

The preserved [payload workflow guide](../../.github/distribution/payload/README.md)
describes the local engine when it says the installer does not stage files.
That remains true for local invocation below. The public external bootstrap is
the separate default-apply entry that stages only newly installed paths; do not
interpret the payload's local-engine statement as its external staging policy.

## Local use

Inspect the local source checkout first. Create an adopter Git repository
yourself if needed. Do not run concurrently with another writer in it.

```sh
bash .github/scripts/scaffold-init.sh --dry-run /path/to/adopter
bash .github/scripts/scaffold-init.sh --apply /path/to/adopter
```

The default is dry-run. `SCAFFOLD_SOURCE_DIR` optionally selects a local
checkout or distribution root containing `.github/distribution/`; relative
paths resolve before changing directories. An explicit invalid local source
never falls back to network acquisition.
Windows uses `.github/scripts/scaffold-init.ps1 --dry-run TARGET` and
`--apply TARGET` through adjacent Git Bash. Bash 3.2+, Git, find, standard Unix
utilities (including GNU/BSD stat), and either sha256sum or shasum are needed;
public Bash acquisition additionally uses curl. No Python package or Rulesync
is required. Later GitHub helper use separately needs authenticated gh and jq.
Drive-form source and target paths use Git Bash's existing `cygpath -u`;
missing or unsuccessful conversion fails rather than prepending the current
directory. This boundary is mocked in offline tests, not measured on Windows.

Review the plan before apply. Review the resulting Git diff, then stage,
commit, and push explicitly. Then open or select the adopter checkout in Codex
and invoke `$project-onboarding` from its installed
`.agents/skills/project-onboarding/SKILL.md`, using the installed file in that project. Keep the
remote-default-before-GitHub-write, clean-checkout verify-by-running,
evidence-PR, and durable deferred-work ledger gates from the source workflow.
The installer itself runs none of the optional GitHub setup helpers.

Shipped shell files have Git mode 100644: invoke the documented helpers with
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

Local missing files are copied only by `--apply`; external invocation defaults to apply. Unrelated adopter files are never
selected. Source/target/ancestor/leaf symlinks, broken links, path escapes,
unlisted payload files, missing inputs, modified inventory layouts, and file/
directory collisions fail closed. A failing inventory enumeration is not an
empty or successful inventory. The local engine leaves Git metadata and index untouched.
External entry stages newly installed paths only. Neither mode supports overwrite,
force, automatic init or commit.
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

## Context, planning and verification

The eight installed Skills cover onboarding, context collection and builtin
drafting, human-reviewed distillation, Epic/Task planning, task routing,
supervision/handoff, verification and retrospective proposals. Start builtin
drafting explicitly with the installed context-collection Skill. Registry
preparation is separate from activation and context sufficiency; drafts stay
under context until a human-reviewed agreements PR.

The installed new-task helper creates once without readiness, verifies exact
identity, body, parent and complete blockers, optionally adds readiness and
verifies again. Uncertain writes stop without retry, deletion or repair.
Readiness describes a complete brief; frontier membership also requires closed
dependencies. Ownership overlap and lexical aliases refuse conservatively.
After PR creation, invoke `bash .github/scripts/check-task-ritual.sh 123` in
the adopter. Complete observations, commit chronology and final readbacks
remain mandatory. Its commit limit is 250; sensor output does not replace CI,
review, owner acceptance or authenticate a worker session.

## Preservation-safe local upgrade and operation-scoped rollback

Local upgrade uses engine/tuned/instance class dispatch and
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

## One-command explicit update

The [README update commands](../../README.md#5-update-explicitly-when-you-choose)
invoke `scaffold-update.sh` or its thin PowerShell/Git Bash entry. No advance
kit clone is needed. `--from` and `--to` require full lowercase 40-character
commit IDs, and `--recovery` requires a fresh directory with an existing parent
outside the adopter. The optional final target defaults to the current directory,
which must be the Git repository root. Branches, tags, short SHAs, duplicate flags and local-source
overrides refuse. Preview is the default; `--apply` is explicit.

The downloaded entry itself is trusted code. Select its reviewed revision
separately from the two payload pins. For Bash, substitute the reviewed entry
commit for `main` in the README URL. For PowerShell, use that commit in the
PowerShell URL **and** set `$env:SCAFFOLD_UPDATE_REF` to the same commit so the
thin entry downloads the corresponding Bash code. `SCAFFOLD_REPO` selects one
public owner/repository for both payloads (default this repository). There is
no authentication or automatic retry. `SCAFFOLD_REF` does not select updater
payloads or entry code. Keep caller-side `pipefail` for Bash download failures.

Both exact commits are fetched into a private bare Git object store using
anonymous HTTPS, an empty transport home, and disabled user configuration,
credential helpers, templates and hooks. Unsupported Git context and client
certificate/TLS override variables refuse. Strict object checks precede bounded
projection: exact regular-blob modes, the fixed 47-path/class layout, complete
payload enumeration, Git blob hashes, payload SHA-256 values and the fixed engine
hash must pass for both revisions. Only that unchanged engine executes; selected
updater or bootstrap code is not projected or executed. Integrity checks do not
authenticate a publisher. Normal trusted Git, Bash and Unix tools are required.

Preview acquires sources in owned temporary scratch and removes that scratch
on exit. It changes no target bytes, index entries or requested recovery path.
Apply exclusively creates a mode-0700 recovery root. `old`, `new`, `objects.git`,
`transport-home` and, when changes are required, `transaction` are separate
children. All retained payload files have mode 0644. The engine validates the
complete inventory before any target write, preserves existing tuned/instance/
seed content, and replaces engine files only when they match the old version.
Missing payload files can be installed. Already-new files are unchanged.

Recovery inputs remain at their final paths after wrapper exit on success or
failure. No files are staged, committed or pushed; HEAD and unrelated index
state are preserved. Inspect the diff and follow your normal review process.
An already-new operation retains sources without creating a transaction. A
failure during acquisition or record preparation may need manual inspection;
retained inputs alone are not proof of a complete rollback record.

For a completed or modeled interrupted update with a complete transaction,
run the retained engine without a network connection (Git Bash on Windows):

```sh
RECOVERY=/path/to/the-original-private-recovery
TARGET=/path/to/adopter
SCAFFOLD_SOURCE_DIR="$RECOVERY/new" bash "$RECOVERY/new/.github/scripts/scaffold-install.sh" --rollback --transaction "$RECOVERY/transaction" --dry-run "$TARGET"
SCAFFOLD_SOURCE_DIR="$RECOVERY/new" bash "$RECOVERY/new/.github/scripts/scaffold-install.sh" --rollback --transaction "$RECOVERY/transaction" --apply "$TARGET"
```

Do not move, replace or delete retained source roots or the transaction; rollback
checks paths and filesystem identities as well as bytes. The existing
[recovery refusal rules](#recovery-and-refusal) apply: later affected edits or
unknown partial bytes refuse; unrelated later edits are preserved. Keep recovery
inputs private and out of public reports. This is operation-scoped recovery,
without whole-repository reset, power-loss atomicity or concurrent-writer safety.
Both revisions need the fixed supported layout and engine. Native Windows is
unmeasured even when PowerShell-host synthetic tests pass.

The focused regression command is:

```sh
python3 -I -m unittest discover -s tests/conformance -p 'test_installer_update.py'
```

The mandatory product/installer guards bind updater provenance and include this
module in the existing full conformance discovery; the CI workflow is unchanged.

## Optional local installer failure report

Use the standalone, explicitly invoked companion **outside the 47-file
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

## Governance, worktree and retro procedures

Two standalone companions run from the reviewed kit checkout. They are not
copied into the adopter's 47-file payload and are not automatically CI gates.
Use the target's actual contexts; no Copilot or donor CI names are defaults:

```bash
bash "$REVIEWED_KIT/.github/scripts/governance-status.sh" \
  -R owner/repository --checks lint,test --posture adopter --profile solo
bash "$REVIEWED_KIT/.github/scripts/worktree-preflight.sh" \
  --target "$TASK_WORKTREE" --branch "$PLANNED_BRANCH" \
  --writer "$ACTUAL_WORKER" --claims "$CLAIM_READBACK" --action push
```

Omit the sensor's profile only to read the exact persisted governance intent;
missing/invalid intent remains UNKNOWN. `--posture source-template` explicitly
reports ownership tuning N/A; absent changelog markers never imply template
posture. The sensor makes only GET observations. Team controls require typed
common App IDs, complete evidence and resolved ownership entries. Unsupported
workflow syntax remains UNKNOWN; actual CODEOWNERS membership/coverage needs
human review. Setup retains dry-run previews, refuses legacy writes without
`--profile`, validates canonical reconciliation and persists intent before a
Ruleset write. Tests exercise these writes only against synthetic GitHub.

The installed onboarding Skill preserves Enable now / Create disabled / Skip,
requires an explicitly selected or reviewed existing `solo`/`team` profile,
and distinguishes new creation from `--reconcile` of a canonical same-name
ruleset. Its named command blocks run the installed setup helper; unrecognized
choices and malformed evidence do not grant write consent. No-profile and new
solo dry-runs are offline body previews. New team dry-runs read repository,
issuer and CODEOWNERS evidence without proving same-name absence. Reconcile
previews read list/detail for either profile, and team evidence as needed;
all previews make zero writes.

Bypass observations use actor-specific ID types: DeployKey accepts null only,
and OrganizationAdmin accepts null or a numeric ID only on organization repos.
The other four recognized actor types require numeric IDs. Complete actor
records are required even where the API ignores an ID; missing fields remain
UNKNOWN rather than presumed absent. Only `always` and applicable
`pull_request` modes are supported; documented `exempt` remains non-success.
Observed actors do not imply human approval of bypass or permission to change it.

Worktree preflight inspects actual Git state and declared claim readbacks.
Detached push, occupied branches and competing claims refuse. Archive always
warns/non-succeeds pending human inspection of durable evidence and handoff;
no cleanup, force, unlock, push or client-native operation is performed.

The existing retro Skill now contains named executable candidate review and
retirement-diff blocks. They process raw occurrence/control/decision records,
retain evidence and history, and emit candidate state or a bounded diff.
Distinct URLs are not authenticated independent incidents, and matching
decision fields are not actual owner approval. Synthetic cases prove the
procedure mechanics only; human independence, agreement and adoption review
remain mandatory. No scheduler, retro engine or upstream send is installed.

## Evidence boundary

Mandatory product and installer checks validate the shipped scope and complete
companion bindings. Behavioral tests use real Bash, Git and jq, disposable
adopters and synthetic GitHub/HTTP transport. Historical comparisons use only
20 immutable checked-in file entries, without predecessor Git objects or old
Issue retrieval. They do not prove native Windows, live Codex E2E, named-agent
selection or cross-client runtime parity. Earlier research and unfinished
release obligations remain in [provenance](../provenance.md).
