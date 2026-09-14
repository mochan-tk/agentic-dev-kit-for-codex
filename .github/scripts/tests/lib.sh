#!/usr/bin/env bash
# Minimal TAP-like helpers for offline guard regression tests.

TESTS_RUN=0
TESTS_FAILED=0

t_ok() {
  TESTS_RUN=$((TESTS_RUN + 1))
  echo "ok - $1"
}

t_fail() {
  TESTS_RUN=$((TESTS_RUN + 1))
  TESTS_FAILED=$((TESTS_FAILED + 1))
  echo "not ok - $1"
}

expect_rc() {
  local wanted="$1" name="$2" rc=0 output
  shift 2
  output=$("$@" 2>&1) || rc=$?
  if [ "$rc" -eq "$wanted" ]; then
    t_ok "$name"
  else
    t_fail "$name (rc=$rc, want $wanted)"
    printf '%s\n' "$output" | sed 's/^/    # /'
  fi
}

expect_rc_grep() {
  local wanted="$1" pattern="$2" name="$3" rc=0 output
  shift 3
  output=$("$@" 2>&1) || rc=$?
  if [ "$rc" -eq "$wanted" ] && printf '%s\n' "$output" | grep -Eq "$pattern"; then
    t_ok "$name"
  else
    t_fail "$name (rc=$rc, want $wanted; pattern: $pattern)"
    printf '%s\n' "$output" | sed 's/^/    # /'
  fi
}

t_summary() {
  echo "# $TESTS_RUN case(s), $TESTS_FAILED failed"
  [ "$TESTS_FAILED" -eq 0 ]
}

init_sandbox_repo() {
  mkdir -p "$1"
  git -c init.defaultBranch=main init -q "$1"
}

stage_all() {
  git -C "$1" add -A
}
