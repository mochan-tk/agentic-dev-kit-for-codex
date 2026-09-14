#!/usr/bin/env bash
# Offline regression tests for fail-closed effective workflow permissions.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
# shellcheck source=/dev/null
. "$HERE/lib.sh"

GUARD="$REPO_ROOT/.github/scripts/check-workflow-permissions.sh"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/workflow-permissions.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

write_workflow() {
  local name="$1" top="$2" jobs="$3"
  CASE_DIR="$WORK/$name"
  mkdir -p "$CASE_DIR"
  {
    printf 'name: test\non: [push]\n'
    if [ "$top" != "__ABSENT__" ]; then
      printf '%s\n' "$top"
    fi
    printf 'jobs:\n%s\n' "$jobs"
  } > "$CASE_DIR/workflow.yml"
}

expect_guard_fail() {
  expect_rc 1 "$1" bash "$GUARD" "$CASE_DIR"
}

canonical_job='  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo checked'

write_workflow canonical 'permissions: {}' "$canonical_job"
expect_rc_grep 0 "effective permissions.*contents: read" \
  "canonical empty workflow plus explicit job read passes" \
  bash "$GUARD" "$CASE_DIR"

write_workflow inherited 'permissions:
  contents: read' '  quality:
    runs-on: ubuntu-latest
    steps:
      - run: echo inherited'
expect_rc_grep 0 "effective permissions.*contents: read" \
  "job inherits approved workflow contents read" bash "$GUARD" "$CASE_DIR"

write_workflow explicit-without-top '__ABSENT__' "$canonical_job"
expect_rc_grep 0 "effective permissions.*contents: read" \
  "explicit job mapping replaces an absent workflow mapping" \
  bash "$GUARD" "$CASE_DIR"

write_workflow replacement 'permissions:
  issues: read' '  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo replacement'
expect_rc_grep 0 "effective permissions.*contents: read" \
  "job mapping replaces rather than merges workflow permissions" \
  bash "$GUARD" "$CASE_DIR"

write_workflow mixed 'permissions: {}' '  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo good
  conformance:
    runs-on: ubuntu-latest
    permissions:
      contents: none
    steps:
      - run: echo bad'
expect_guard_fail "one unsafe job among safe jobs fails"

write_workflow absent '__ABSENT__' '  quality:
    runs-on: ubuntu-latest
    steps:
      - run: echo unknown'
expect_guard_fail "absent workflow and job permissions fail closed"

write_workflow inherited-empty 'permissions: {}' '  quality:
    runs-on: ubuntu-latest
    steps:
      - run: echo effective-empty'
expect_guard_fail "workflow empty mapping is valid but inherited effective permissions are empty"

for shorthand in read-all write-all; do
  write_workflow "shorthand-${shorthand//[^a-z]/x}" "permissions: $shorthand" '  quality:
    runs-on: ubuntu-latest
    steps:
      - run: echo shorthand'
  expect_guard_fail "workflow permissions shorthand '$shorthand' fails closed"
done

# The final value is intentionally a literal GitHub expression fixture.
# shellcheck disable=SC2016
for value in none write read-all write-all true false null '"read"' '${{ github.ref }}'; do
  write_workflow "value-${value//[^a-zA-Z0-9]/x}" 'permissions: {}' "  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: $value
    steps:
      - run: echo value"
  expect_guard_fail "unsupported contents value '$value' fails closed"
done

approved_scopes=(
  actions artifact-metadata attestations checks code-quality contents deployments
  discussions id-token issues models packages pages pull-requests security-events
  statuses vulnerability-alerts
)
for scope in "${approved_scopes[@]}"; do
  write_workflow "write-${scope}" 'permissions: {}' "  mutate:
    runs-on: ubuntu-latest
    permissions:
      $scope: write
    steps:
      - run: echo no-checkout"
  expect_guard_fail "write grant for '$scope' fails even without checkout"
done

for scope in issues pull-requests actions checks id-token mystery-scope; do
  write_workflow "read-${scope}" 'permissions: {}' "  observe:
    runs-on: ubuntu-latest
    permissions:
      $scope: read
    steps:
      - run: echo observe"
  expect_guard_fail "unapproved or unknown read scope '$scope' fails"
done

write_workflow overridden-write 'permissions:
  issues: write' "$canonical_job"
expect_guard_fail "a declared workflow write fails even when a job replaces it"

write_workflow post-jobs-write '__ABSENT__' "$canonical_job
permissions:
  issues: write"
expect_guard_fail "a post-jobs workflow write grant fails even with an explicit safe job"

ambiguous_cases=(
  $'permissions: &safe\n  contents: read'
  $'permissions: *safe'
  $'permissions:\n  <<: *safe'
  $'permissions: {contents: read}'
  $'permissions:\n  contents: read\n  contents: read'
  $'permissions:\n  "contents": read'
  $'permissions:\n   contents: read'
)
for index in "${!ambiguous_cases[@]}"; do
  write_workflow "ambiguous-$index" "${ambiguous_cases[$index]}" '  quality:
    runs-on: ubuntu-latest
    steps:
      - run: echo ambiguous'
  expect_guard_fail "ambiguous workflow permissions shape $index fails closed"
done

job_permission_shapes=(
  $'permissions: read-all'
  $'permissions: write-all'
  $'permissions: {contents: read}'
  $'permissions: &job_permissions\n      contents: read'
  $'permissions: *job_permissions'
  $'permissions:\n      contents: read\n      contents: read'
  $'permissions:\n      "contents": read'
  $'permissions: ${{ github.ref }}'
)
for index in "${!job_permission_shapes[@]}"; do
  write_workflow "job-shape-$index" 'permissions: {}' "  quality:
    runs-on: ubuntu-latest
    ${job_permission_shapes[$index]}
    steps:
      - run: echo ambiguous-job"
  expect_guard_fail "ambiguous job permissions shape $index fails closed"
done

write_workflow quoted-workflow-key '"permissions":
  issues: write' "$canonical_job"
expect_guard_fail "quoted workflow permissions key cannot hide a write grant"

write_workflow quoted-job-key 'permissions:
  contents: read' '  quality:
    runs-on: ubuntu-latest
    "permissions":
      issues: write
    steps:
      - run: echo quoted-job-key'
expect_guard_fail "quoted job permissions key cannot hide a write grant"

write_workflow escaped-workflow-key '"permiss\u0069ons":
  issues: write' "$canonical_job"
expect_guard_fail "escaped workflow permissions key cannot hide a write grant"

write_workflow escaped-job-key 'permissions:
  contents: read' '  quality:
    runs-on: ubuntu-latest
    "permiss\u0069ons":
      issues: write
    steps:
      - run: echo escaped-job-key'
expect_guard_fail "escaped job permissions key cannot hide a write grant"

decorated_workflow_permissions=(
  $'!!str permissions:\n  issues: write'
  $'!<tag:yaml.org,2002:str> permissions:\n  issues: write'
  $'&permission_key permissions:\n  issues: write'
  $'&9 permissions:\n  issues: write'
  $'? permissions\n: {issues: write}'
)
for index in "${!decorated_workflow_permissions[@]}"; do
  write_workflow "decorated-workflow-$index" \
    "${decorated_workflow_permissions[$index]}" "$canonical_job"
  expect_guard_fail "decorated workflow permissions key $index fails closed"
done

decorated_job_permissions=(
  $'!!str permissions:\n      issues: write'
  $'!<tag:yaml.org,2002:str> permissions:\n      issues: write'
  $'&permission_key permissions:\n      issues: write'
  $'&9 permissions:\n      issues: write'
  $'? permissions\n    : {issues: write}'
)
for index in "${!decorated_job_permissions[@]}"; do
  write_workflow "decorated-job-$index" 'permissions:
  contents: read' "  quality:
    runs-on: ubuntu-latest
    ${decorated_job_permissions[$index]}
    steps:
      - run: echo decorated-job-key"
  expect_guard_fail "decorated job permissions key $index fails closed"
done

write_workflow merged-job-permissions 'permissions:
  contents: read' '  quality:
    runs-on: ubuntu-latest
    <<: *unsafe_permissions
    steps:
      - run: echo merged-job-permissions'
expect_guard_fail "job-level YAML merge alias fails closed"

CASE_DIR="$WORK/noncanonical-job"
mkdir -p "$CASE_DIR"
printf '%s\n' 'name: test' 'on: [push]' 'permissions: {}' 'jobs:' \
  '    quality:' '        runs-on: ubuntu-latest' '        permissions:' \
  '            contents: read' '        steps:' '            - run: echo bad' \
  > "$CASE_DIR/workflow.yml"
expect_guard_fail "unsupported job indentation fails closed"

expect_rc_grep 0 "effective permissions.*contents: read" \
  "repository workflows pass effective-permission policy" \
  bash "$GUARD" "$REPO_ROOT/.github/workflows"

write_workflow isolated-python 'permissions: {}' "$canonical_job"
SHADOW_ROOT="$WORK/python-shadow-root"
mkdir -p "$SHADOW_ROOT/workflows"
cp "$CASE_DIR/workflow.yml" "$SHADOW_ROOT/workflows/workflow.yml"
printf '%s\n' 'import os' 'os._exit(0)' > "$SHADOW_ROOT/re.py"
# Positional parameters must expand inside the child bash, not in this shell.
# shellcheck disable=SC2016
expect_rc_grep 0 "effective permissions.*contents: read" \
  "isolated embedded Python ignores a repository-root re.py shadow" \
  bash -c 'cd "$1" && exec bash "$2" workflows' \
  _ "$SHADOW_ROOT" "$GUARD"

t_summary
