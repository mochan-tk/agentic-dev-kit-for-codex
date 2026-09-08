#!/usr/bin/env bash
# Small CLI contract checks; the complete disposable-adopter suite is in conformance.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
. "$ROOT/.github/scripts/tests/lib.sh"
SCRIPT="$ROOT/.github/scripts/scaffold-init.sh"
expect_rc_grep 0 'Usage:' 'installer help works without a target' bash "$SCRIPT" --help
expect_rc 2 'force is not an overwrite escape hatch' bash "$SCRIPT" --force
expect_rc 2 'upgrade is not silently implemented' bash "$SCRIPT" --upgrade
expect_rc 2 'conflicting execution intent refuses' bash "$SCRIPT" --apply --dry-run
expect_rc 2 'unknown options refuse' bash "$SCRIPT" --unknown
expect_rc 2 'multiple destinations refuse' bash "$SCRIPT" one two
expect_rc 0 'installer Bash syntax' bash -n "$SCRIPT"
t_summary
