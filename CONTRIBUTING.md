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
