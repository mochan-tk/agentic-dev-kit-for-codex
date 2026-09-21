# Opt-in adopter PR checks

This separate source-checkout companion connects the installed Task ritual to
adopter pull requests. It also observes verification freshness after a base
retarget and detects detached controls within a deliberately limited workflow
form. It does not install application tests or change GitHub settings.

## Preview and installation

Use a reviewed kit checkout, Python 3.11+, Bash, Git, jq, gh and base64 on
macOS or Linux. Install the kit's accepted 47-file payload first. The existing
`.github/scripts/check-task-ritual.sh` must match the supported version; tuned
or unknown helper bytes refuse. Work alone in the adopter checkout during
setup. Use a physical directory path without symlink ancestors.

From the reviewed kit checkout, run the complete product gate and then name
the actual adopter repository, its existing application workflow and the job
names that the owner intends to require:

```sh
python3 -I .github/scripts/check-product.py
python3 -I .github/scripts/setup-adopter-ci.py \
  --target /path/to/adopter \
  --code-workflow .github/workflows/application.yml \
  --check quality --check tests
```

The default is a read-only preview. Repeat with `--apply` to create exactly:

- `.github/workflows/task-ritual.yml`
- `.github/scripts/check-adopter-ci.py`
- `.github/adopter-ci.json`

Setup validates every dependency, workflow and destination before writing.
Existing application CI, unrelated files, tuned configuration and the Git
index remain unchanged. An identical complete installation is a no-op.
Unknown bytes, collisions, symlinks and partially present addons refuse;
there is no force option. A creation failure reports only the finite new paths
already created and retains them for inspection. It never deletes unknown
files, stages, commits, pushes or changes a service. It is not a filesystem
transaction or protection against a malicious concurrent writer.

## Supported application workflow

Version 1 supports exactly one existing application workflow, plus this addon
after installation. Extra workflows refuse because this bounded parser cannot
establish their producer and cancellation interactions. Move neither your
existing CI nor its jobs merely to make setup pass; review an explicit future
adaptation if your project requires a broader form.

The application workflow must use the following structural form. Replace the
sample commands with your real commands before opting in. Every `--check`
names a unique static job ID, whose optional `name` is identical to that ID.
Additional static jobs may be optional; their failures do not substitute for
or invalidate successful required jobs during the retarget observation.

```yaml
name: Application checks
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
concurrency:
  group: application-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Application lint
        run: python3 tools/lint.py
  tests:
    runs-on: ubuntu-latest
    steps:
      - name: Application tests
        run: python3 -m unittest discover
```

These examples show structure, not a complete application checkout/test recipe.
Action steps use a full 40-character commit pin. Supported runner labels are
`ubuntu-latest`, `macos-latest` and `windows-latest`. Steps may contain `name`,
`uses`, `with`, `run`, `env`, `shell` and `working-directory`; each has either
`uses` or `run`. `with` belongs only to action steps; `shell` and
`working-directory` belong only to run steps. `name` and `working-directory`
must be nonempty single-line strings, and `env`/`with` must map keys to string
values. Every job must contain a run command. After surrounding whitespace,
blank lines and full-line comments are ignored, a body with no meaningful
lines or only standalone `true`, `:` and `echo` placeholders refuses. The owner
still reviews command meaning: the sensor is not a shell interpreter or proof
that a command tests software.
Explicit shells are limited to `bash`, `sh`, `pwsh` and `python`.

The parser supports two-space mapping indentation, mapping items in step
sequences, simple scalars, explicit flow lists, full-line comments and literal
`|`/`|-` command bodies. It rejects duplicate keys, anchors, aliases, folded
blocks, inline comments, complex quoted scalars and unsupported structures.
Explicit PR types are required; implicit default event semantics are not
supported. Push, manual and reusable triggers, paths/branch filters, matrices,
job dependencies, conditions, failure tolerance and job concurrency are outside
this version's supported form. Application workflow grants are exactly
`contents: read`. Its concurrency group is a fixed ASCII prefix followed by
`${{ github.event.pull_request.number }}`, with cancellation enabled; prefixes
beginning with `adopter-metadata-` are reserved case-insensitively.

Setup refuses unsupported wiring with a bounded reason. It does not patch
existing CI. Supported command edits in later PRs can pass structural checking;
application workflow bytes are not frozen by addon configuration.

## Activation and observation

Review the three-file installation PR first. Its metadata run deliberately
fails with installation guidance if the trusted base lacks the sensor. Do not
require `task-ritual` before that installation has been accepted and reached
the base branch. After acceptance, evaluate a normal Task PR and separately
review the observed application and metadata checks. The owner then decides
whether and how to require them through an explicit GitHub settings operation.
This companion performs none of those settings writes or initial rollout steps.

The fixed metadata workflow uses `pull_request` with opened, synchronize,
reopened and edited actions. It has a separate cancellation domain, one
`task-ritual` job, an immutable checkout Action pin, no persisted credentials,
and exactly contents/issues/pull-requests/checks/actions read grants. It checks
out the event's base SHA and runs the base's sensor and installed ritual.
PR-controlled strings only enter data/environment fields, not shell commands.
No application code executes in the metadata job and it never emits application
check names, including skipped placeholders.

The sensor validates the base's bounded configuration and control inventory,
then reads the PR head's Git trees and file contents as data. Tree modes must
prove regular files and directory parents; Contents API symlink dereferencing
is not treated as proof. Missing, commented, misplaced, conditional or softened
metadata guards fail the fixed-template binding. The actual installed ritual
retains its claim/plan/dispatch, chronology, exemption, pagination and final
readback semantics. Its existing exemptions remain narrowly scoped; the addon
does not introduce waivers or authenticate comment authors/session IDs.

Retarget freshness observes the exact current PR/head/base and complete bounded
timeline. The latest `base_ref_changed` timestamp wins even after moving away
and back. A base-edit webhook only vetoes success until timeline evidence is
visible; it never supplies positive evidence. With no retarget, `NO_RETARGET`
does not claim application CI success: the owner must still require application
checks independently.

After retargeting, the unique latest attributable original application run must
have been created strictly after the retarget. A rerun cannot refresh an old
original, and an older success cannot replace a newer failure. Every configured
required job must be present in the current attempt and match a direct check ID,
suite, head, name, GitHub Actions App ID/slug, success status and chronology.
Optional-job failure may make a completed overall run fail without invalidating
successful required jobs. The selected run must reference the same base
repository/ref; a later normal advance of that base SHA does not by itself
invalidate the historical run. This is not strict current-base code freshness.
The metadata event itself must nevertheless name the current base SHA, because
its checkout selects the trusted control code. If that base advances after the
event, rerunning the old metadata event refuses even with unchanged base ref
and otherwise fresh code checks. A new supported PR event with the current base
SHA is required; merely rerunning the old metadata execution cannot refresh its
event payload. The sensor never generates that event or changes the binding.

The sensor rereads relevant PR, timeline, workflow, run, attempt, check and
control observations before reporting success. Missing/empty PR association,
malformed or duplicate JSON, partial pagination, failed reads, ambiguity, drift
and resource limits are non-success. It never polls, reopens, reruns, publishes
statuses or repairs controls. Exit 0 means the named observation passed; exit 1
means stale/refused evidence; exit 2 means uncheckable input or observation.
Local `drift --root /path/to/adopter` reads files only and does not check GitHub.

Only GitHub.com and its Actions App issuer are supported. API reads explicitly
use GET and version `2022-11-28`. Each command has a 30-second bound and combined
2 MiB output bound. Guarded files are at most 1 MiB, pages at most 100 items,
listings at most 20 pages/2,000 records, Actions run results below 1,000, each
Git tree at most 2,000 entries, and workflows at most 16 static jobs. Hitting a
bound refuses; no truncated observation becomes success. Hosted API limitations,
including empty run PR associations, may make an otherwise ordinary PR
uncheckable. No fallback infers identity from branch names.

Metadata can finish before new application CI succeeds; an operator may need
to reevaluate metadata after code checks finish. Task/comment edits without a
PR event are not continuously watched. Finite reads are not atomic GitHub
snapshots or permanent merge locks. Workflow definitions are themselves mutable
reviewable PR code, including the outer job that invokes this sensor; trusted
base checkout and hashes do not make them an immutable security boundary.

## Separate update and removal boundary

This addon is outside the legacy 47-file installer, updater and rollback
inventory. Those operations neither install nor recover its three files.
Changing its guarded config, helper or template is intentionally unsupported
by this version's setup and will fail the existing metadata gate. There is no
automatic migration or instruction to bypass that gate. A future change or
removal needs an owner-reviewed transition plan, including any required-check
policy change before guarded files disappear. Retain and review the exact old
files; do not overwrite unknown bytes or assume legacy rollback includes them.
An installed ritual upgrade can likewise require such an addon transition.

Conformance executes the actual setup/sensor and installed ritual with real
local tools and synthetic GitHub. Product CI validates this addon separately
and preserves all 47 payload files. This is not live-adopter Actions rollout,
native Windows qualification, Codex worker E2E, runtime parity or release
acceptance. See [provenance](../provenance.md) for exact source attribution.
