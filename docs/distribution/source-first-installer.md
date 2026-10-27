# One-command installation and update

Read [product scope](../product-scope.md), [limitations](../known-limitations.md) and
[source provenance](../provenance.md) for shipped behavior and historical acceptance.

## Prepare context and the desktop project

**This kit requires the ChatGPT Codex desktop app**, not only for this
walkthrough but for onboarding, coordination and development. Meet all
[product prerequisites](../../README.md#prerequisites), including the GitHub
repository, authenticated `gh`, `jq`, Git/Bash and Windows-specific tools,
before starting. Codex CLI or the IDE extension alone does not satisfy the
desktop requirement.

For the required-by-default Projects roadmap, repository authentication alone is not
enough: queries need `read:project`, and creation/updates need `project` with
classic/OAuth credentials. See [Projects prerequisites](../../README.md#prerequisites).
Onboarding checks access early and records a scope failure separately from an
absent or declined board. `gh auth refresh -s project` is an owner-operated
remedy for stored `gh` credentials, never an automatic setup step. Board writes
still need consent. Record a scoped exception for an environment that cannot
create/use Projects or an explicit owner decline of Projects; Issue-based work
can then proceed without fabricated board proof. Pending creation/date consent
does not become an exception. Approved implementation may continue while an
answer is pending, but required Task close-out must wait.

If the desktop app offers ChatGPT and Codex in its product selector, choose
Codex for the kit's installation/onboarding/development work. ChatGPT Chat or
Work is the preparation surface below, not a substitute for the local Codex
project. Shell installers and helpers can run in a terminal, but that does
not make a terminal-only workflow a supported way to operate the kit. The
installer does not detect the app or enforce this product requirement, and
the requirement does not qualify every app version or operating system.

### Prepare the specification before adoption

Before using the kit, prepare your specification context in **ChatGPT Chat
or Work**. Use Chat to discuss goals, compare options and clarify requirements;
use Work when you want notes or multiple sources organized into a reviewable
document. Review the output yourself. If you already have suitable requirements
or design material, reuse it rather than regenerating it just for onboarding.
Unresolved choices should remain explicit questions, not invented decisions.

The handoff should identify:

- the problem, goal and intended users;
- in-scope behavior and explicit non-goals;
- technical, operational or other relevant constraints;
- observable acceptance criteria and priorities;
- open questions, assumptions and links or file names for source material.

Save a readable copy you can provide to Codex, for example a Markdown/text
file or an attachment. Supply the path, attachment or relevant text during
onboarding's material step; for already committed documents, point to their
repository paths and keep the existing files in place. Confirm the receiving
chat can actually read the material. A source-chat link alone is not a promise
of access, and Chat/Work history is not automatically the Codex project's
context. Do not include credentials or material you are not authorized to
share. Reference drafts inform planning but do not become approved agreements
without human review. This preparation is guidance, not an installer-enforced
gate, a required external connector, or automatic context synchronization.

### Create the Codex project before the first kit command

1. Prepare or clone the **adopter Git repository**: the application you intend
   to build. The kit installer does not initialize Git or create the GitHub
   repository. Do not select this kit's source checkout as your application.
2. In the desktop app's Codex view, create a project for that repository, or
   select its existing project. Attach the local repository root and make it
   the **primary folder**. In versions with these controls, use the project's
   **Edit project**, **Add folder**, and **Make primary** actions. New chats
   use the primary folder for Git operations and automatic discovery of
   `AGENTS.md`, Skills and configuration; do not rely on a secondary folder
   for that discovery.
3. Start a **local chat inside that Codex project**. Confirm the working
   directory and Git root name the adopter repository, then use a terminal
   at that root for the **public one-command installation** below. Do not
   clone the kit or run installer scripts from a kit checkout for adoption.
   Keep one writer and review existing changes before installation.
4. Review and land the installed files on the remote default branch, as
   described below. Start a new local chat in the same project for the
   installed onboarding Skill, with the prepared context ready. Answer its
   material and model questions explicitly; no answer is not `auto`.

The Codex project is an execution context, distinct from a ChatGPT project
used to prepare documents and from the GitHub Projects roadmap projection. The
kit neither creates those app projects nor transfers conversation history.
GitHub records and reviewed repository files remain the durable work record.

Official UI references (checked 2026-10-05): [desktop app and mode selection](https://learn.chatgpt.com/docs/app),
[local projects and primary folders](https://learn.chatgpt.com/docs/projects#use-local-projects-for-folders-and-codebases),
and [Chat, Work and Codex](https://learn.chatgpt.com/docs/use-chatgpt#choose-how-you-want-to-work).
Labels and availability can vary by client, plan and workspace; follow the
controls available to you without assuming automatic cross-surface access.

## One-command first installation

Use the [README Bash or PowerShell command](../../README.md#1-install-in-your-project)
from an existing adopter Git root. This is the only adopter installation route
and needs no kit clone. The public installer defaults to apply and stages only
files created in that invocation. Explicit --dry-run changes neither adopter files
nor index; disposable acquisition scratch is separate and removed on exit.
Applying an install or known-old upgrade, recorded rollback and the public
updater require the physical top level of a non-bare Git worktree.
Git administration directories and bare repositories
refuse, even when a public bootstrap finds every payload file already identical.
Normal roots, linked worktrees and real submodules remain supported.

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
payload digests and the exact current local engine digest must validate before
executing selected code or touching the adopter. No archive extraction,
checkout, filters, hooks, credential helper, GitHub authentication or new
package is required. Only the selected revision's wrapper then dispatches its
engine and stages; an older initial wrapper never applies its stage policy to
a different selected revision. The private dispatch mode is a process routing
boundary, not an authenticated identity or a general recursive bootstrap API.

The current bootstrap refuses selected revisions with either previous engine,
including the accepted pre-repair revision. To install that historical revision,
separately review and pin its own historical entry and selected revision together.
A new entry is available through `main` only after its PR is merged; an unmerged
repair does not change the public `main` download. The installer rejects
inherited repository/configuration context overrides before Git observations,
including empty values. Genuine linked worktrees with `.git` files remain
supported; call from a shell without those overrides.

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
the interactive session. WSL is never substituted. PowerShell-host synthetic
tests are separate from native Windows execution, which remains unmeasured.

Before apply, the reviewed local planner validates every source and target
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

Review `git diff --cached` and land the reviewed adoption on the remote default
branch before onboarding makes GitHub changes. Then open or select the adopter checkout in Codex
in the desktop project prepared above. Start a new local chat and invoke
`$project-onboarding` using that project's installed
`.agents/skills/project-onboarding/SKILL.md`, with the prepared context ready.
Confirm the chat reads the installed file in your application repository, not
the kit's contributor checkout. Setup helpers are never run by the installer.

The preserved [payload workflow guide](../../.github/distribution/payload/README.md)
describes the internal engine when it says the installer does not stage files.
For adoption, follow this public guide: the one-command installer stages only
newly installed paths. The internal-engine statement does not change that
staging policy or provide an alternate installation route.

## Installed startup and Task records

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

**Older onboarding checker affected by #65:** prefer
the [explicit update](#one-command-explicit-update) with reviewed revisions,
then verify the installed checker against the current onboarding PR. If that
specific old-checker defect remains, follow the installed
[P6 owner-disposition procedure](../../.github/distribution/payload/.agents/skills/project-onboarding/SKILL.md#p6--record).
It requires exact PR/checker bindings, bounded failure evidence, supervisor
assessment and an explicit scoped human decision before the requested operation.
Failure remains **FAIL**; unrelated failures are ineligible and protections stay
unchanged. Retire the exception only after the corrected installed checker
passes the current PR, retaining the earlier failure/decision history. An
upstream fix alone does not establish an installed correction.

Read the installed session-orchestration Skill's startup decision table before
starting onboarding. A scoped, unrevoked owner decline must have a durable
reference; it is not inferred and does not authorize unrelated work. Preserve
the distinction between tuning-status exit 0, exit 1, and observation errors.
Upgrades keep tuned `.github/codex-instructions.md` and `AGENTS.md` unchanged:
new Skills must surface a conflicting adopter agreement, not overrule it.

The supervisor can prepare a bounded comment without posting it:

```sh
bash .github/scripts/check-task-ritual.sh render claim --input claim.json > claim.md
bash .github/scripts/check-task-ritual.sh preflight claim --repo owner/repository --task 123 --body-file claim.md --branch feature/task
```

`claim.json` contains `task` (positive integer), `session` (actual supervisor
label), and `branch` (actual branch). `render --help` documents all four kinds:
claim, resume, plan and dispatch. Dispatch uses the real worker reference,
including supported `/root/...` references; never convert it to an invented
UUID. Plan prose still requires human review; syntactic validation does not
judge its adequacy. Check the render exit status before using the resulting
file: redirection can leave an empty file even when render fails. Preflight
rejects malformed UTF-8 and NUL before any API read, while preserving valid
Japanese, emoji, literal U+FFFD and terminal newlines. Both input routes retain
the 262144-byte limit with no additional dependency. Preflight reads actual body
bytes and makes GETs
only. Add `--pr NUMBER` when there is already a PR; failed PR observation must
not be retried without that argument to obtain a pass.

Posting is a separate authorized operation. After posting, read back the exact
body before continuing; a passing preflight cannot predate a later dispatch or
prevent remote drift. Historical branch mismatch is ignored only for a valid
released-and-replaced worker, never for malformed or edited records. The
existing numeric PR checker remains the final PR ritual sensor.

Onboarding requires an explicit choice of `solo`, `team`, or
`single-maintainer`, and distinguishes new creation from canonical reconcile.
Single-maintainer retains PR/check requirements with zero approvals and no
bypass; it is not an implicit default. Preview before the explicit setup write.
The installed onboarding Skill contains the complete consent/reconcile paths.

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

The public installer defaults to apply; `--dry-run` previews without installing
or staging files. Unrelated adopter files are never selected. Source/target/
ancestor/leaf symlinks, broken links, path escapes, unlisted payload files,
missing inputs, modified inventory layouts, and file/
directory collisions fail closed. A failing inventory enumeration is not an
empty or successful inventory. The public entry stages newly installed paths
only. It does not overwrite existing files, force an operation, initialize Git
or commit changes.
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

### Observe Project values without changing the board

`gh project item-list --format json` can omit populated single-select/date
values (reported with gh 2.102.0). A null `Kind`, `Start date` or `Target date`
there is not evidence that the board is unset, and must not trigger corrective
writes. From the installed application repository, use:

```sh
bash .github/scripts/setup-project.sh readback --owner OWNER --project 7 --issue 23 -R OWNER/REPO
```

Replace the owner, Project and Issue numbers with the selected identities.
This query-only command resolves the exact repository Issue and Project,
enumerates Project items, and reads the selected item's typed GraphQL
`fieldValues`. Both connections are paginated independently, with a limit of
10 pages/1,000 entries each and 1 MiB per response. It skips explicitly typed
DraftIssue/PullRequest items; null/redacted content, duplicate identities,
partial errors, changing anchors and incomplete pagination are uncheckable.
It neither invokes setup writes nor refreshes credentials, and does not retry.

The `project-field-readback/v1` JSON record contains Project/Issue identities,
`item_id`, and `fields` keyed by `Kind`, `Start date`, and `Target date`, each
with `field_id`, `type`, and `value`. Exit 0 / `state: observed` means all three
values were observed, **not that they match the agreed Kind or schedule**.
Compare each value with the current durable plan before recording verification.
Exit 1 / `state: missing` emits explicit null fields and a `missing` list (or
`item` if no matching item exists); missing values are non-success, not permission
to invent dates. GraphQL lists set values, so absence does not distinguish an
unset value from a missing field definition. Exit 2 is invalid usage, and exit 3
is an uncheckable observation without a partial success record. Tool/authentication
preflight failures are also non-success and may have no JSON record.

This is a bounded observation, not an atomic snapshot, live adoption proof or
write authority. If access, size or schema limits prevent readback, stop the
affected verification. An explicit alternative is to open that exact Project
item in GitHub's UI and inspect all three fields, recording the item/Issue link,
observed values and comparison outcome; do not substitute an ambiguous CLI null.
See GitHub's [typed Project field schema](https://docs.github.com/en/graphql/reference/projects).

### Verify required Task close-out

Before reporting Task completion, compare the exact item's Kind `Task`, Start
date and Target date with the current authorized schedule record:

```sh
bash .github/scripts/setup-project.sh verify --owner OWNER --project 7 --issue 23 -R OWNER/REPO \
  --expect-kind Task --expect-start YYYY-MM-DD --expect-target YYYY-MM-DD
```

Replace the placeholders with the real identities and authorized dates; never
invent values to pass. Expected dates must be valid calendar dates in order.
The verifier calls the existing typed reader once, without writing or retrying.
Its `project-field-verification/v1` JSON contains `expected`, the complete
reader `observation`, and `differences`. Exit 0 / `match` means all three values
match; exit 1 is `mismatch` or `missing`; exit 2 rejects invalid inputs before
queries; exit 3 is `uncheckable` with no trusted observation. A match does not
prove schedule authorization, final acceptance, or future board state.

Record the command, current PR head, observation time, exact identities,
expected/observed values, comparison and schedule-decision link in the Task and
PR evidence. The exact-item UI alternative needs the same complete comparison.
The two Project exceptions are documented environmental inability and explicit
owner Project decline: record the scoped reason/evidence or decision link
instead of a fake match. No helper bypass flag accepts an exception. An
unanswered date question or a date-only defer/decline leaves close-out pending,
even if implementation continues; it does not waive Project use. Resolve the
specific schedule decision or work order with the owner.

Run this under existing authorized Projects access, never unconditionally from
ordinary repository-token CI. Text in an evidence table is not a substitute
for actual observations. The Issue graph remains authoritative, and neither
the verifier nor this policy grants board-write or permission-change authority.

## Upgrade preservation and operation-scoped rollback

Use the [one-command explicit update](#one-command-explicit-update) with reviewed
old/new commit IDs. Its engine uses engine/tuned/instance class dispatch,
known-old checks, prewrite backups and explicit operation rollback. It does
not blindly overwrite engine files, stage changes or replace the changelog.
Both selected revisions must contain exactly the supported 47 ordered payload
paths/classes, with single-link regular mode-0644 payload files and valid
SHA-256 digests. A self-consistent manifest is integrity relative to the chosen
input, **not source authenticity**.

Standard BSD/GNU `stat`, `cp`, `sort`, `wc`, `rmdir`, and `sync` supplement the
installation prerequisites; no new Python, jq, service, or package installation
is required.

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
is part of the upgrade or rollback engine.

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
payload enumeration, Git blob hashes and payload SHA-256 values must pass for
both revisions. FROM accepts either exact previously reviewed engine or current
reviewed engine as retained data. TO requires the current reviewed engine, and
only that new engine executes; selected
updater or bootstrap code is not projected or executed. Integrity checks do not
authenticate a publisher. Normal trusted Git, Bash and Unix tools are required.

The current updater deliberately refuses a legacy-engine TO revision. A separate
reviewed, pinned historical updater remains the route for the old engine family;
do not assume the current entry accepts every historical source. The one-file
ritual transition described in the [boundary-repair provenance](../provenance.md#current-boundary-repair)
and exercised by its regression fixture is a historical case, not a guarantee
for every accepted-old to current update. The later final-boundary correction
also changed `tuning-status.sh`. The payload delta depends on the exact selected
FROM/TO revisions; review their preview instead of assuming only the ritual
helper changes. Current to current already-new updates are a separate no-op
case. The `local-upgrade/v1` format is unchanged; current local
code can read retained old-engine operations using their original source roots.

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

### Offline recovery of a previous public update

These commands only roll back an existing one-command update; they are not an
installation route. For a completed or modeled interrupted update with a
complete transaction, run its retained engine without a network connection
(Git Bash on Windows). Use only the sources already retained by that update;
do not substitute a kit checkout:

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
Both revisions need the fixed supported layout and role-appropriate engine. Native Windows is
unmeasured even when PowerShell-host synthetic tests pass.

The focused regression command is:

```sh
python3 -I -m unittest discover -s tests/conformance -p 'test_installer_update.py'
```

The mandatory product/installer guards bind updater provenance and include this
module in the existing full conformance discovery; the CI workflow is unchanged.

## Optional local installer failure report

Use the standalone, explicitly invoked companion **outside the 47-file
installed payload**. The [feedback guide](feedback.md) provides a pinned,
two-file no-clone command and a public manual form. Installer failures only
print fixed guide/form links: no automatic collection, reporting download,
prompt or submission. This manual handoff preserves failure status and cleanup;
review partial files and staging locally before sharing any public-safe report.
The first HTTP failure before Bash starts still requires caller `pipefail`.
Alternatively, use the reviewed kit checkout's mode-0644 Bash entrypoint:

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

Alternatively, use the [complete-download-and-verify command](companion-checks.md#connectors-validate-local-definition-structure)
without a kit clone. That route runs the same fixed helper; only its retrieval
uses the network. The helper's structural validation remains local.

```sh
bash /path/to/reviewed-kit/.github/scripts/check-connectors.sh --target /path/to/adopter
```

An explicit existing target is mandatory; there is no current-directory or
kit-root fallback. This Bash 3.2+ command uses standard find/head/tr/grep/sed/awk
only. It never calls Git, GitHub, authentication, a model or a network service,
changes files, applies fixes, writes an activation registry or modifies CI.
Running this checker never changes the 47 installed payload files;
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
The [fixed-revision no-clone commands](companion-checks.md) provide explicitly
pinned helper versions without a checkout; they add no setup or repair operation.
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
requires an explicitly selected or reviewed existing `solo`/`team`/`single-maintainer` profile,
and distinguishes new creation from `--reconcile` of a canonical same-name
ruleset. Its named command blocks run the installed setup helper; unrecognized
choices and malformed evidence do not grant write consent. No-profile and new
solo/single-maintainer dry-runs are offline body previews. New team dry-runs read repository,
issuer and CODEOWNERS evidence without proving same-name absence. Reconcile
previews read list/detail for every profile, and team evidence as needed;
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
