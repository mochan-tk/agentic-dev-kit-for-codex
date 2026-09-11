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
