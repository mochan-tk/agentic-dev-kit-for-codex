#!/usr/bin/env bash
# Small CLI contract checks; the complete disposable-adopter suite is in conformance.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
. "$ROOT/.github/scripts/tests/lib.sh"
SCRIPT="$ROOT/.github/scripts/scaffold-init.sh"
expect_rc_grep 0 'Usage:' 'installer help works without a target' bash "$SCRIPT" --help
expect_rc 2 'force is not an overwrite escape hatch' bash "$SCRIPT" --force
expect_rc 2 'upgrade requires explicit old source and transaction' bash "$SCRIPT" --upgrade
expect_rc 2 'rollback requires an explicit transaction and target' bash "$SCRIPT" --rollback
expect_rc 2 'upgrade and rollback cannot be combined' bash "$SCRIPT" --upgrade --rollback
expect_rc 2 'old source is not accepted by plain install' bash "$SCRIPT" --old-source one
expect_rc 2 'transaction is not accepted by plain install' bash "$SCRIPT" --transaction one
expect_rc_grep 0 'known-old' 'help states the bounded update contract' bash "$SCRIPT" --help
expect_rc 2 'conflicting execution intent refuses' bash "$SCRIPT" --apply --dry-run
expect_rc 2 'unknown options refuse' bash "$SCRIPT" --unknown
expect_rc 2 'multiple destinations refuse' bash "$SCRIPT" one two
expect_rc 0 'installer Bash syntax' bash -n "$SCRIPT"
t_summary
