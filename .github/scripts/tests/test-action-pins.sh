#!/usr/bin/env bash
# Offline regression tests for check-action-pins.sh.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
# shellcheck source=/dev/null
. "$HERE/lib.sh"

SANDBOX_N=0
WORK=$(mktemp -d "${TMPDIR:-/tmp}/action-pins.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

new_case() {
  SANDBOX_N=$((SANDBOX_N + 1))
  CASE="$WORK/case$SANDBOX_N"
  init_sandbox_repo "$CASE"
  mkdir -p "$CASE/.github/scripts" "$CASE/.github/workflows"
  cp "$REPO_ROOT/.github/scripts/check-action-pins.sh" "$CASE/.github/scripts/"
}

new_case
cat > "$CASE/.github/workflows/good.yml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-node@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # v4.0.2
      - uses: ./.github/actions/local-thing
EOF
stage_all "$CASE"
expect_rc 0 "pinned refs and local action pass" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
cat > "$CASE/.github/workflows/tag.yml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@v7
EOF
stage_all "$CASE"
expect_rc 1 "tag-pinned reference fails" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
cat > "$CASE/.github/workflows/no-comment.yml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
EOF
stage_all "$CASE"
expect_rc 1 "SHA without version comment fails" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
cat > "$CASE/.github/workflows/short.yml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@3d3c42e # v7.0.1
EOF
stage_all "$CASE"
expect_rc 1 "short SHA fails" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
cat > "$CASE/.github/workflows/bare.yml" <<'EOF'
jobs:
  build:
    steps:
      - name: wrapped
        uses: actions/cache@v4
EOF
stage_all "$CASE"
expect_rc 1 "bare uses line with tag fails" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
cat > "$CASE/.github/workflows/good.yml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
EOF
cat > "$CASE/.github/workflows/bad.yaml" <<'EOF'
jobs:
  build:
    steps:
      - uses: actions/checkout@main
EOF
stage_all "$CASE"
expect_rc 1 "one unpinned file among pinned ones fails" bash "$CASE/.github/scripts/check-action-pins.sh"

new_case
rmdir "$CASE/.github/workflows"
stage_all "$CASE"
expect_rc 0 "repository without workflow files passes" bash "$CASE/.github/scripts/check-action-pins.sh"

t_summary
