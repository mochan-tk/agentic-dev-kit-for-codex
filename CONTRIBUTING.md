# Contributing

Start with [AGENTS.md](AGENTS.md) and a bounded Issue describing the problem,
expected behavior, acceptance checks and owned files. Keep a single writer
for each overlapping scope, explain changes in the pull request, and leave
acceptance and merge to the maintainer.

## Local validation

Use Python 3.11+, Bash, Git and jq. No Python packages are required by the
product tests. Run from this kit's checkout:

```sh
python3 -I .github/scripts/check-product.py
python3 -I .github/scripts/check-installer.py
bash .github/scripts/tests/test-scaffold-init.sh
bash .github/scripts/check-action-pins.sh
bash .github/scripts/tests/test-action-pins.sh
bash .github/scripts/check-workflow-permissions.sh
bash .github/scripts/tests/test-workflow-permissions.sh
python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'
python3 -I -m compileall -q .github/scripts tests/conformance
git diff --check
```

The pinned Linux lint-tool installer used by CI is:

```sh
python3 -I .github/scripts/install-ci-tools.py --lock .github/governance/ci-tools.lock.v1.json --destination /path/to/new-private-ci-tools --check-repository
```

That command downloads the allowlisted tools and requires its supported Linux
platform. It is separate from kit installation. CI runs the `quality` and
`conformance` jobs using read-only repository permissions and pinned Actions.
PowerShell tests use a real PowerShell host with synthetic HTTP responses;
when that host is unavailable locally, the test explicitly skips. CI requires
PowerShell. Neither case proves native Windows installation.

## Contributor-only local installer development

The commands in this section are for developing and testing the kit in
**disposable repositories**, not for adopting it in an application. Adopters
must use the [public one-command installation](README.md#1-install-in-your-project)
from their application Git root. A kit clone and local-source invocation are
not alternative adoption routes.

Inspect the local kit checkout first. Run these commands from its root, with
an exclusively owned disposable Git repository as the target:

```sh
bash .github/scripts/scaffold-init.sh --dry-run /path/to/disposable-adopter
bash .github/scripts/scaffold-init.sh --apply /path/to/disposable-adopter
```

Local invocation defaults to dry-run and does **not** stage files. This differs
from the public installer, which defaults to apply and stages newly installed
paths. Inspect the plan before applying, then inspect the target diff and index.
`SCAFFOLD_SOURCE_DIR` optionally selects an inspected local checkout or
distribution root containing `.github/distribution/`; relative paths resolve
before changing directories. An invalid explicit local source never falls
back to network acquisition. Local dry-run retains its non-repository preview
behavior, while apply requires the physical root of a non-bare Git worktree.

Shipped shell files have Git mode 100644; invoke them with `bash`. Local source
payloads must retain the reviewed regular-file modes as well as their digests;
for example, a mode-0660 payload is not accepted as mode 0644. Do not relax the
mode guard to accommodate a development checkout's umask. Bash 3.2+, Git,
find, standard Unix tools (including GNU/BSD `stat`), and `sha256sum` or `shasum`
are required. Public Bash acquisition additionally uses curl.

For Windows development, the adjacent `.github/scripts/scaffold-init.ps1`
forwards `--dry-run TARGET` or `--apply TARGET` through Git Bash. Drive-form
paths use its existing `cygpath -u`; failed or missing conversion refuses.
This boundary is covered by synthetic tests, not native Windows evidence.

### Local upgrade and rollback fixtures

Use inspected old/new source roots, an exclusively owned disposable adopter
Git root, and a new private transaction directory whose parent already exists.
Sources and transaction must not overlap the target; the transaction must not
overlap either source. `SCAFFOLD_SOURCE_DIR` selects the new source and
`--old-source` is mandatory for upgrade. Old and new may be the same inspected
source for a no-op fixture. Both inventories must contain the fixed 47 ordered
paths/classes, single-link regular mode-0644 payload files and valid digests.
Run only a reviewed entry supporting these options; inventory validity does
not authenticate code.

```sh
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --dry-run /path/to/disposable-adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --upgrade --old-source /path/to/old-kit --transaction /path/to/private/update-1 --apply /path/to/disposable-adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --dry-run /path/to/disposable-adopter
SCAFFOLD_SOURCE_DIR=/path/to/new-kit bash .github/scripts/scaffold-init.sh --rollback --transaction /path/to/private/update-1 --apply /path/to/disposable-adopter
```

The adjacent PowerShell entry forwards the same arguments to Bash. Standard
BSD/GNU `stat`, `cp`, `sort`, `wc`, `rmdir`, and `sync` supplement the first-install
prerequisites. Upgrade and rollback do not stage, commit or push. Review the
[private recovery record and refusal rules](docs/distribution/source-first-installer.md#private-recovery-record)
before using the fixture; retain operation inputs at their original paths and
keep them out of public evidence. The supported interrupted-copy fixture does
not establish power-loss atomicity or concurrent-writer safety.

## Tests and provenance

Tests use real Bash, Git, jq and disposable adopter directories; GitHub/HTTP
transport in the regression suite is synthetic. No old Issue fetch or
predecessor Git object database is required. Twenty immutable old-file
fixtures retain old/new behavior and rollback regressions. Six predecessor
installer delta-history tests remain in the predecessor; one bootstrap
old-PR-delta assertion is replaced by the approved export integrity check.
The four ordinary-umask and unsafe-mode regressions also run here.

Keep all 47 payload entries and their preservation classes explicit. A future
intentional product change must update the inventory, relevant parity and
export records, checker bindings, documentation and behavior tests together.
A checksum is an integrity check, not permission to change scope or proof of
publisher identity. Inspect every file that will enter public Git history.

See [product scope](docs/product-scope.md), [limitations](docs/known-limitations.md)
and [source provenance](docs/provenance.md). Do not include private adopter
data or operation backups in a bug report.
