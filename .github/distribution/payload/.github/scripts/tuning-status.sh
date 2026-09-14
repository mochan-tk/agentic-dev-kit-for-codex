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
#   bash .github/scripts/tuning-status.sh --quiet    no output; exit code only (0 tuned / 1 not)
#
# Used by: .agents/skills/project-onboarding/SKILL.md (P0/P5) and ci.yml.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="report"
case "${1:-}" in
  --ci) MODE="ci" ;;
  --quiet) MODE="quiet" ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

TARGETS=(
  ".github/codex-instructions.md"
  ".github/workflows/ci.yml"
  ".github/CODEOWNERS"
)
if [[ -d .github/instructions ]]; then
  while IFS= read -r f; do TARGETS+=("$f"); done \
    < <(find .github/instructions -name '*.instructions.md' | sort)
fi

FINDINGS=()
add_hits() { # $1=pattern (fixed string) $2=file
  while IFS= read -r hit; do FINDINGS+=("$hit"); done \
    < <(grep -HnF "$1" "$2" 2>/dev/null || true)
}

for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] || continue
  add_hits "CUSTOMIZE:" "$f"
done
# ci.yml carries no distinct placeholder step, so its CUSTOMIZE: marker (added
# in the loop above) is its onboarding sentinel. copilot-setup-steps.yml keeps
# a placeholder run step whose text survives CUSTOMIZE removal, so match it too.


NOTES=()
while IFS= read -r hit; do NOTES+=("$hit"); done \
  < <(grep -RHnF "(example — replace)" .github/docs/agreements 2>/dev/null || true)

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
