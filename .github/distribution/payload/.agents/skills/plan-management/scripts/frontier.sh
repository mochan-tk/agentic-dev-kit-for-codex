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
  # gh 2.96.0 returns a connection capped at 50 nodes. Prove completeness
  # before publishing anything. Retain tested flat-array compatibility only;
  # it is not a claim about every gh version. Missing data is never empty.
  # shellcheck disable=SC2016
  refs="$(gh issue view "$num" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json blockedBy \
    --jq '
      def integer: type == "number" and . >= 0 and . == floor;
      def repo_name: type == "string" and length <= 140 and
        test("^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\\z");
      def repository:
        if has("repository") then .repository |
          if type != "object" then error("invalid repository")
          else
            (if has("name") or has("owner") then
              if (.name | type) != "string" or (.owner.login | type) != "string"
              then error("invalid repository fields") else .owner.login + "/" + .name end
             else null end) as $parts |
            (if has("nameWithOwner") then .nameWithOwner else $parts end) as $name |
            if ($name | repo_name) and ($parts == null or
                ($parts | ascii_downcase) == ($name | ascii_downcase))
            then $name else error("invalid or inconsistent repository") end
          end
        else null end;
      .blockedBy |
      (if type == "array" then .
       elif type == "object" and (.nodes | type) == "array" and
         (.totalCount | integer) and .totalCount == (.nodes | length) and .totalCount <= 50
       then .nodes else error("missing, malformed or incomplete blockers") end) |
      map(
        if type != "object" or ((.number | integer) | not) or .number < 1
        then error("invalid blocker") else . end |
        . as $node | repository as $repo |
        if has("url") then
          if (.url | type) != "string" or
            ((.url | test("^https://[A-Za-z0-9][A-Za-z0-9.-]{0,252}/[^/]+/[^/]+/issues/[1-9][0-9]*\\z")) | not)
          then error("invalid blocker URL") else
            (.url | capture("^https://(?<host>[^/]+)/(?<repo>[^/]+/[^/]+)/issues/(?<number>[0-9]+)\\z")) as $url |
            if ($url.repo | repo_name) and ($url.number | tonumber) == $node.number and
              ($repo == null or ($repo | ascii_downcase) == ($url.repo | ascii_downcase))
            then [$node.number, ($url.host + "/" + $url.repo)]
            else error("inconsistent blocker identity") end
          end
        else [$node.number, ($repo // "-")] end
      ) | if (unique | length) == length then .[] | @tsv
          else error("duplicate blocker identity") end')" \
    || fail 'dependency retrieval failed or unsupported; inspect the Issue graph manually'
  blocked=false
  if [ -n "$refs" ]; then
    while IFS=$'\t' read -r ref blocker_repo; do
      [[ "$ref" =~ ^[1-9][0-9]*$ ]] || fail 'malformed blocker reference'
      BLOCKER_REPO_ARGS=("${REPO_ARGS[@]+"${REPO_ARGS[@]}"}")
      if [ "$blocker_repo" != '-' ]; then BLOCKER_REPO_ARGS=(--repo "$blocker_repo"); fi
      state="$(gh issue view "$ref" ${BLOCKER_REPO_ARGS[@]+"${BLOCKER_REPO_ARGS[@]}"} --json state --jq .state)" \
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
