#!/usr/bin/env bash
# tuning-status.sh — is this scaffold instance tuned to its project yet?
#
# Scans only the *tunable targets* (the Sync Triangle, CODEOWNERS, and area
# instructions) for CUSTOMIZE markers and known placeholder sentinels, and
# notes example rows left in .github/docs/agreements. Mentions of the word CUSTOMIZE elsewhere
# (skills, prompts, README) are documentation, not findings.
#
# Usage:
#   bash .github/scripts/tuning-status.sh            human report; exit 1 if markers remain
#   bash .github/scripts/tuning-status.sh --ci       emit ::warning:: lines; always exit 0. When
#                               GITHUB_STEP_SUMMARY names a file and findings
#                               exist, also append a markdown summary block
#                               there (tuned trees append nothing).
#   bash .github/scripts/tuning-status.sh --quiet    no output; 0 tuned / 1 not / 2 observation error
#
# Used by: .agents/skills/project-onboarding/SKILL.md (P0/P5) and ci.yml.

set -euo pipefail
MODE="report"
case "${1:-}" in
  --ci) MODE="ci" ;;
  --quiet) MODE="quiet" ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

observation_failure() {
  case "$MODE" in
    quiet) exit 2 ;;
    ci) printf '::warning::scaffold observation error — %s\n' "$1"; exit 0 ;;
    *) printf 'OBSERVATION ERROR: %s\n' "$1"; exit 2 ;;
  esac
}
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || observation_failure 'project root unavailable'
cd "$ROOT" 2>/dev/null || observation_failure 'project root unavailable'
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tuning-status.XXXXXX" 2>/dev/null)" || observation_failure 'inspection scratch unavailable'
trap 'rm -rf -- "$WORK" 2>/dev/null || :' EXIT
# Opening scratch streams is an observation too. A shell redirect failure
# otherwise looks like grep's ordinary no-match status or set -e's exit 1.
open_output() {
  { exec 3> "$1"; } 2>/dev/null || observation_failure 'inspection scratch write unavailable'
}
open_input() {
  { exec 4< "$1"; } 2>/dev/null || observation_failure 'inspection scratch read unavailable'
}
ERRORS=()
FINDINGS=()
NOTES=()

TARGETS=(
  ".github/codex-instructions.md"
  ".github/workflows/ci.yml"
  ".github/CODEOWNERS"
)
if [[ -e .github/instructions || -L .github/instructions ]]; then
  if [[ ! -d .github/instructions ]]; then
    ERRORS+=("area instructions target is not a directory")
  else
    # Preserve NUL-delimited names until controls have been refused. BSD sort
    # then receives one unambiguous name per line; GNU sort -z is not required.
    open_output "$WORK/names"
    if ! find -H .github/instructions -name '*.instructions.md' -print0 >&3 2>/dev/null; then
      ERRORS+=("area instruction enumeration failed")
    fi
    open_input "$WORK/names"
    open_output "$WORK/sort-input"
    while IFS= read -r -d '' f; do
      case "$f" in
        *$'\n'*|*$'\r'*|*$'\t'*) ERRORS+=("unsupported control character in instruction filename") ;;
        *) printf '%s\n' "$f" >&3 || observation_failure 'inspection scratch write failed' ;;
      esac
    done <&4
    open_output "$WORK/sorted"
    if ! LC_ALL=C sort "$WORK/sort-input" >&3 2>/dev/null; then
      ERRORS+=("area instruction ordering failed")
    fi
    open_input "$WORK/sorted"
    while IFS= read -r f; do TARGETS+=("$f"); done <&4
  fi
fi

add_hits() { # $1=pattern (fixed string) $2=file
  local status=0
  open_output "$WORK/hits"
  grep -HnF "$1" "$2" >&3 2>/dev/null || status=$?
  if [[ "$status" -gt 1 ]]; then ERRORS+=("target search failed: $2"); fi
  open_input "$WORK/hits"
  while IFS= read -r hit; do FINDINGS+=("$hit"); done <&4
}

for f in "${TARGETS[@]}"; do
  if [[ ! -e "$f" && ! -L "$f" && "$f" != .github/codex-instructions.md ]]; then continue; fi
  if [[ ! -f "$f" ]]; then ERRORS+=("required or present target unavailable: $f"); continue; fi
  add_hits "CUSTOMIZE:" "$f"
done
# ci.yml carries no distinct placeholder step, so its CUSTOMIZE: marker (added
# in the loop above) is its onboarding sentinel. copilot-setup-steps.yml keeps
# a placeholder run step whose text survives CUSTOMIZE removal, so match it too.


# Agreements are advisory: absence/read failures do not block onboarding.
if [[ -d .github/docs/agreements ]]; then
  note_status=0
  open_output "$WORK/notes"
  grep -RHnF "(example — replace)" .github/docs/agreements >&3 2>/dev/null || note_status=$?
  open_input "$WORK/notes"
  while IFS= read -r hit; do NOTES+=("$hit"); done <&4
  if [[ "$note_status" -gt 1 ]]; then NOTES+=("Advisory agreement notes unavailable."); fi
fi

# A partial marker never turns a failed observation into an ordinary decline-
# eligible untuned state. CI remains warning-only, including observation errors.
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  case "$MODE" in
    quiet) exit 2 ;;
    ci) for error in "${ERRORS[@]}"; do printf '::warning::scaffold observation error — %s\n' "$error"; done; exit 0 ;;
    report) printf 'OBSERVATION ERROR: %s\n' "${ERRORS[@]}"; exit 2 ;;
  esac
fi

case "$MODE" in
  quiet)
    [[ ${#FINDINGS[@]} -eq 0 ]] && exit 0 || exit 1 ;;
  ci)
    for h in ${FINDINGS[@]+"${FINDINGS[@]}"}; do
      echo "::warning::scaffold not onboarded — ${h}"
    done
    # On GitHub Actions, mirror the findings into the job's step summary so
    # the nudge is visible on the run page without opening logs. A tuned
    # tree appends nothing (silence is the healthy state); with
    # GITHUB_STEP_SUMMARY unset the behavior above is unchanged. The
    # `|| true` keeps the always-exit-0 contract even if the summary path
    # is unwritable (set -e would otherwise abort on the failed redirect).
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" && ${#FINDINGS[@]} -gt 0 ]]; then
      {
        echo "## ⚠️ Scaffold not onboarded"
        echo
        echo "Run \`\$project-onboarding\` (the installed project-onboarding Skill) to tune"
        echo "this scaffold to its project. Findings:"
        echo
        echo '```text'
        printf '%s\n' "${FINDINGS[@]}"
        echo '```'
      } >> "$GITHUB_STEP_SUMMARY" || true
    fi
    exit 0 ;;
  report)
    if [[ ${#FINDINGS[@]} -eq 0 ]]; then
      echo "TUNED: no CUSTOMIZE markers or placeholders in tunable targets."
    else
      echo "NOT TUNED — run .agents/skills/project-onboarding/SKILL.md:"
      printf '  %s\n' "${FINDINGS[@]}"
    fi
    if [[ ${#NOTES[@]} -gt 0 ]]; then
      echo "Notes (distillation-phase, not onboarding blockers):"
      printf '  %s\n' "${NOTES[@]}"
    fi
    [[ ${#FINDINGS[@]} -eq 0 ]] && exit 0 || exit 1 ;;
esac
