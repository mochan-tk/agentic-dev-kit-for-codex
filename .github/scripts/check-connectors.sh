#!/usr/bin/env bash
# Frozen Copilot fd265ddef150fab86cd54d0e383c2c25fe297ffb:
# .github/scripts/check-connectors.sh, blob 8a598ab8fd5b54f0fe48b5daf3dc91abc86cadf9.
# Reuse err(), check_connector(), five-field/four-heading grammar and framework
# enumeration. Adapt explicit target, empty-name refusal, safe diagnostics and
# checked bounded reads. Structural text validation only; never activate a source.
# Bash 3.2+ and standard find/head/tr/grep/sed/awk; no Git, network or file writes.
set -euo pipefail
export LC_ALL=C

usage() {
  printf '%s\n' 'Usage: bash check-connectors.sh --target EXISTING_DIRECTORY' >&2
}
uncheckable() {
  printf 'check-connectors: UNCHECKABLE %s\n' "$1" >&2
  exit 3
}
if [ "$#" -eq 1 ] && [ "$1" = --help ]; then usage; exit 0; fi
if [ "$#" -ne 2 ] || [ "$1" != --target ] || [ -z "$2" ]; then usage; exit 2; fi

# Resolve lexically one component at a time; do not resolve away a symlink.
# Trusted exclusive local use, not a hostile same-user namespace-race barrier.
TARGET=$2
case "$TARGET" in /*) : ;; *) TARGET="$PWD/$TARGET" ;; esac
remaining=${TARGET#/}
ROOT=
while [ -n "$remaining" ]; do
  part=${remaining%%/*}
  if [ "$part" = "$remaining" ]; then remaining=; else remaining=${remaining#*/}; fi
  case "$part" in ''|.) continue ;; ..) uncheckable target:unsafe-path ;; esac
  ROOT="$ROOT/$part"
  [ ! -L "$ROOT" ] && [ -d "$ROOT" ] && [ -r "$ROOT" ] && [ -x "$ROOT" ] || uncheckable target:uncheckable
done
[ -n "$ROOT" ] || ROOT=/
for directory in "${ROOT%/}/.github" "${ROOT%/}/.github/connectors"; do
  [ ! -L "$directory" ] && [ -d "$directory" ] && [ -r "$directory" ] && [ -x "$directory" ] || uncheckable connector-directory:uncheckable
done
DIR="${ROOT%/}/.github/connectors"
# Check the real enumeration command's status, never equate an error to an
# unmatched glob. The subsequent glob is safe under the stated no-concurrent-
# writer boundary, not an atomic filesystem snapshot.
find "$DIR" -mindepth 1 -maxdepth 1 -print >/dev/null 2>&1 || uncheckable enumeration-failed

FAIL=0
ERRORS=0
FOUND=0
DATA=
err() {
  FAIL=1
  ERRORS=$((ERRORS + 1))
  if [ "$ERRORS" -le 32 ]; then
    printf 'check-connectors: ERROR %s\n' "$1" >&2
  elif [ "$ERRORS" -eq 33 ]; then
    printf '%s\n' 'check-connectors: ERROR diagnostic-limit' >&2
  fi
}

read_file() {
  local file=$1 role=$2
  if [ -L "$file" ]; then uncheckable "$role:unsafe-file"; fi
  if [ ! -e "$file" ]; then err "$role:missing"; DATA=; return 1; fi
  [ -f "$file" ] && [ -r "$file" ] || uncheckable "$role:unsafe-file"
  # Preserve newline/byte limits before command-substitution normalization.
  # Translate NUL before Bash can silently discard it, then reject that marker.
  DATA=$( { head -c 1048577 "$file" | tr '\000' '\001' || exit 3; printf '.'; } 2>/dev/null) || uncheckable "$role:read-failed"
  DATA=${DATA%.}
  [ "${#DATA}" -le 1048576 ] || uncheckable "$role:input-limit"
  case "$DATA" in *$'\001'*) uncheckable "$role:nontext-input" ;; esac
}

# Unlike grep || true, distinguish absent matches (1) from tool/read errors.
match() {
  local pattern=$1 text=$2 rc
  if printf '%s\n' "$text" | grep -E "$pattern" >/dev/null 2>&1; then return 0; else rc=$?; fi
  [ "$rc" -eq 1 ] || uncheckable parser-read-failed
  return 1
}

for framework in README.md CONNECTOR-TEMPLATE.md; do
  case "$framework" in README.md) role='framework-readme' ;; *) role='framework-template' ;; esac
  read_file "$DIR/$framework" "$role" || :
done

# check_connector <file> — original section extraction and textual grammar.
# Only fixed field/role labels reach diagnostics; filenames/values remain local.
check_connector() {
  local file=$1 stem section field count rc name_val status_line status_val sec label
  label="definition-$FOUND"
  read_file "$file" "$label" || return 0
  stem=${file##*/}; stem=${stem%.md}
  if ! match '^## Metadata[[:space:]]*$' "$DATA"; then
    err "$label:metadata-section-missing"
  else
    section=$(printf '%s\n' "$DATA" | awk '/^## Metadata[[:space:]]*$/{f=1; next} /^## /{f=0} f' 2>/dev/null) || uncheckable parser-read-failed
    for field in name access reach trust-default status; do
      if count=$(printf '%s\n' "$section" | grep -cE "^- ${field}:" 2>/dev/null); then :
      else rc=$?; [ "$rc" -eq 1 ] || uncheckable parser-read-failed; fi
      case "$count" in ''|*[!0-9]*) uncheckable parser-count-invalid ;; esac
      if [ "$count" -eq 0 ]; then err "$label:metadata-missing:$field"
      elif [ "$count" -gt 1 ]; then err "$label:metadata-duplicate:$field"; fi
    done
    # Source checks undeclared bullet lines only inside Metadata; continuation
    # prose, exact-name heading trailing whitespace and operation bodies remain.
    if printf '%s\n' "$section" | awk '/^- / && !/^- (name|access|reach|trust-default|status):/{bad=1} END{exit bad ? 1 : 0}' 2>/dev/null; then :
    else rc=$?; [ "$rc" -eq 1 ] || uncheckable parser-read-failed; err "$label:metadata-undeclared"; fi
    name_val=$(printf '%s\n' "$section" | sed -n 's/^- name:[[:space:]]*//p' 2>/dev/null | sed -n '1{s/[[:space:]]*$//;p;}' 2>/dev/null) || uncheckable parser-read-failed
    if [ -z "$name_val" ]; then err "$label:name-empty"
    elif [ "$name_val" != "$stem" ]; then err "$label:name-filename-mismatch"; fi
    status_line=$(printf '%s\n' "$section" | sed -n '/^- status:/{p;}' 2>/dev/null | sed -n '1p' 2>/dev/null) || uncheckable parser-read-failed
    if [ -n "$status_line" ]; then
      status_val=$(printf '%s\n' "$status_line" | sed -e 's/^- status:[[:space:]]*//' -e 's/[[:space:]]*$//' 2>/dev/null) || uncheckable parser-read-failed
      case "$status_val" in core|community|experimental) : ;; *) err "$label:status-invalid" ;; esac
    fi
  fi
  for sec in discover retrieve pin verify; do
    if ! match "^## ${sec}[[:space:]]*$" "$DATA"; then err "$label:operation-missing:$sec"; fi
  done
}

shopt -s nullglob dotglob
for file in "$DIR"/*.md; do
  case "${file##*/}" in README.md|CONNECTOR-TEMPLATE.md) continue ;; esac
  FOUND=$((FOUND + 1))
  [ "$FOUND" -le 128 ] || uncheckable definition-limit
  check_connector "$file"
done
if [ "$FOUND" -eq 0 ]; then err definitions-missing; fi
if [ "$FAIL" -ne 0 ]; then
  printf '%s\n' 'check-connectors: FAIL structural-definition-errors' >&2
  exit 1
fi
printf 'check-connectors: OK %s connector definition(s); structural evidence only.\n' "$FOUND"
