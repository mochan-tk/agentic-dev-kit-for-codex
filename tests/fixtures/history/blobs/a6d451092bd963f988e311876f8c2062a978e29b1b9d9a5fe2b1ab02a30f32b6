#!/usr/bin/env bash
# MIT License
#
# Copyright (c) 2026 Takashi Kawamoto (Mr.Mo)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Source-derived frontier: open type:task + ai:ready, all blockers CLOSED.
# Requires gh with the blockedBy JSON field; unsupported/missing data refuses.
# Usage: bash .agents/skills/plan-management/scripts/frontier.sh [-R owner/repo] [--all]
set -euo pipefail
REPO_ARGS=()
SHOW_ALL=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    -R|--repo) [ -n "${2:-}" ] || exit 2; REPO_ARGS=(--repo "$2"); shift 2 ;;
    --all) SHOW_ALL=true; shift ;;
    -h|--help) printf '%s\n' 'Usage: bash .agents/skills/plan-management/scripts/frontier.sh [-R owner/repo] [--all]'; exit 0 ;;
    *) printf '%s\n' 'error: unknown option' >&2; exit 2 ;;
  esac
done
fail() { printf 'UNCHECKABLE: %s\n' "$1" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || fail 'gh CLI not found'
# Main-shell capture: a command failure cannot masquerade as an empty list.
LIST="$(gh issue list ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --state open --label type:task --label ai:ready \
  --limit 200 --json number,title --template '{{range .}}{{.number}}{{"\t"}}{{.title}}{{"\n"}}{{end}}')" \
  || fail 'Task list retrieval failed'
if [ -z "$LIST" ]; then printf '%s\n' 'No open Task issues labeled ai:ready.'; exit 0; fi
READY=""
BLOCKED=""
COUNT=0
while IFS= read -r line; do
  num="${line%%$'\t'*}"
  title="${line#*$'\t'}"
  [[ "$num" =~ ^[1-9][0-9]*$ ]] && [ "$title" != "$line" ] || fail 'malformed Task list'
  COUNT=$((COUNT + 1))
  [ "$COUNT" -lt 200 ] || fail 'Task list may be truncated; inspect the frontier manually'
  # gh parses JSON; valid empty array is distinct from missing or failed data.
  # shellcheck disable=SC2016
  refs="$(gh issue view "$num" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json blockedBy \
    --jq 'if (.blockedBy | type) == "array" then .blockedBy[] | if (.number | type) == "number" then .number else error("invalid blocker") end else error("missing blockers") end')" \
    || fail 'dependency retrieval failed or unsupported; inspect the Issue graph manually'
  blocked=false
  if [ -n "$refs" ]; then
    while IFS= read -r ref; do
      [[ "$ref" =~ ^[1-9][0-9]*$ ]] || fail 'malformed blocker reference'
      state="$(gh issue view "$ref" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json state --jq .state)" \
        || fail 'blocker state retrieval failed'
      case "$state" in CLOSED) ;; OPEN) blocked=true ;; *) fail 'unknown blocker state' ;; esac
    done <<< "$refs"
  fi
  if "$blocked"; then BLOCKED+="#$num"$'\t'"$title"$'\n'
  else READY+="#$num"$'\t'"$title"$'\n'; fi
done <<< "$LIST"
# Publish no partial actionable list when a later observation fails.
printf '%s\n' '== Actionable frontier (all dependency observations succeeded) =='
printf '%s' "$READY"
if "$SHOW_ALL" && [ -n "$BLOCKED" ]; then
  printf '%s\n' '== Blocked =='
  printf '%s' "$BLOCKED"
fi
