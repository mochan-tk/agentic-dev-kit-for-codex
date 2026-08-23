#!/usr/bin/env bash
# Offline regression tests for check-workflow-permissions.sh.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
# shellcheck source=/dev/null
. "$HERE/lib.sh"

GUARD="$REPO_ROOT/.github/scripts/check-workflow-permissions.sh"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/workflow-permissions.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

new_workflow() {
  CASE_DIR="$WORK/$1"
  mkdir -p "$CASE_DIR"
  {
    printf 'name: test\non: [push]\npermissions:\n  contents: read\njobs:\n'
    printf '%s\n' "$2"
  } > "$CASE_DIR/workflow.yml"
}

new_workflow missing '  ritual:
    runs-on: ubuntu-latest
    permissions:
      issues: read
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 1 "grants no usable 'contents' scope" \
  "job with permissions and checkout but no contents fails" \
  bash "$GUARD" "$CASE_DIR"

new_workflow read '  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 0 "1 job[(]s[)] checked" \
  "contents read passes and counts only jobs" bash "$GUARD" "$CASE_DIR"

new_workflow write '  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 0 "check-workflow-permissions: OK" \
  "explicit contents write is a usable grant" bash "$GUARD" "$CASE_DIR"

new_workflow none '  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: none
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 1 "grants no usable 'contents' scope" \
  "contents none fails" bash "$GUARD" "$CASE_DIR"

new_workflow blank '  quality:
    runs-on: ubuntu-latest
    permissions:
      contents:
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 1 "grants no usable 'contents' scope" \
  "blank contents fails" bash "$GUARD" "$CASE_DIR"

new_workflow inherit '  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 0 "check-workflow-permissions: OK" \
  "job without a permissions block inherits" bash "$GUARD" "$CASE_DIR"

new_workflow no-checkout '  label:
    runs-on: ubuntu-latest
    permissions:
      issues: write
    steps:
      - run: echo label'
expect_rc_grep 0 "check-workflow-permissions: OK" \
  "narrow permissions without checkout pass" bash "$GUARD" "$CASE_DIR"

new_workflow mixed '  good:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
  bad:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: read
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000'
expect_rc_grep 1 "job 'bad'" \
  "one bad job among good jobs fails" bash "$GUARD" "$CASE_DIR"

CASE_DIR="$WORK/alternate-indent"
mkdir -p "$CASE_DIR"
cat > "$CASE_DIR/workflow.yml" <<'EOF'
name: alternate indentation
on: [push]
jobs:
    quality:
        runs-on: ubuntu-latest
        permissions:
            contents: none
        steps:
            - uses: actions/checkout@0000000000000000000000000000000000000000
EOF
expect_rc_grep 1 "canonical block-style jobs" \
  "unsupported job indentation fails closed" bash "$GUARD" "$CASE_DIR"

expect_rc_grep 0 "check-workflow-permissions: OK" \
  "repository workflow passes" bash "$GUARD" "$REPO_ROOT/.github/workflows"

t_summary
