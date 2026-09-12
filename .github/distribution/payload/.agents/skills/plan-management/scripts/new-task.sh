#!/usr/bin/env bash
# new-task.sh — create once, verify the Task graph, then optionally mark ready.
#
# Usage: bash .agents/skills/plan-management/scripts/new-task.sh -t "Title" -b body.md -p <epic> -e <cloud|app|cli|ide>
#        [-d "14,15"] [-R [HOST/]OWNER/REPO] [--ready]
# --ready means the brief is complete; blockers may still be OPEN.
# Requires gh >= 2.94 and standard Bash/base64/head/cmp tools. JSON shapes are
# grounded in gh 2.96.0; unsupported or incomplete exports fail closed.
# One CLI create is not an atomic transaction: deferred links can fail after
# Issue creation. Never retry, delete or repair automatically on uncertainty.

set -euo pipefail
export LC_ALL=C
TITLE="" BODY="" PARENT="" EXEC="" DEPS="" REQUESTED_REPO="" READY=false
REPO_ARGS=()
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
OWNERSHIP_VALIDATOR="$ROOT/.github/scripts/ownership-overlap.sh"
bad_input() { echo "error: invalid or incomplete Task inputs (see --help)" >&2; exit 2; }
seen=" "
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -t|-b|-p|-e|-d|-R)
      [[ $# -ge 2 && -n "$2" && "$seen" != *" $1 "* ]] || bad_input
      seen+="$1 "
      case "$1" in
        -t) TITLE="$2" ;; -b) BODY="$2" ;; -p) PARENT="$2" ;;
        -e) EXEC="$2" ;; -d) DEPS="$2" ;; -R) REQUESTED_REPO="$2" ;;
      esac
      shift 2 ;;
    --ready) $READY && bad_input; READY=true; shift ;;
    *) bad_input ;;
  esac
done
number() { [[ "$1" =~ ^[1-9][0-9]*$ && ${#1} -le 10 ]] && [ "$1" -le 2147483647 ]; }
[[ -n "$TITLE" && ${#TITLE} -le 256 && ! "$TITLE" =~ [[:cntrl:]] && "$TITLE" =~ [^[:space:]] ]] || bad_input
number "$PARENT" || bad_input
case "$EXEC" in cloud|app|cli|ide) ;; *) bad_input ;; esac
[[ -n "$BODY" && -f "$BODY" && ! -L "$BODY" ]] || bad_input
case "$BODY" in /*) ;; *) BODY="$PWD/$BODY" ;; esac
if [[ -n "$REQUESTED_REPO" ]]; then
  [[ ${#REQUESTED_REPO} -le 256 && "$REQUESTED_REPO" =~ ^([A-Za-z0-9][A-Za-z0-9.-]*/)?[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+$ ]] || bad_input
  REPO_ARGS=("$REQUESTED_REPO")
fi
DEP_IDS=()
if [[ -n "$DEPS" ]]; then
  # Validate the entire value before read splits it (read stops at a newline).
  [[ ${#DEPS} -le 549 && "$DEPS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]] || bad_input
  IFS=, read -r -a DEP_IDS <<< "$DEPS"
  [[ ${#DEP_IDS[@]} -le 50 ]] || bad_input
  checked=","
  for dep in "${DEP_IDS[@]}"; do
    number "$dep" && [[ "$checked" != *",$dep,"* ]] || bad_input
    checked+="$dep,"
  done
fi
for tool in gh base64 head cmp tr wc mktemp; do
  command -v "$tool" >/dev/null 2>&1 || { echo "error: required local tool unavailable" >&2; exit 2; }
done
umask 077
WORK="$(mktemp -d "${TMPDIR:-/tmp}/new-task.XXXXXX")" || exit 2
trap 'rm -rf "$WORK"' EXIT
# Snapshot the bounded body before validation and creation; never upload a
# later edit of the caller's file. Scratch files stay private and are removed.
head -c 65537 "$BODY" > "$WORK/body" 2>/dev/null || bad_input
size="$(wc -c < "$WORK/body")"
[[ "$size" -gt 0 && "$size" -le 65536 ]] || bad_input
tr -d '\000' < "$WORK/body" > "$WORK/no-nul"
cmp -s "$WORK/body" "$WORK/no-nul" || bad_input
if $READY; then
  bash "$OWNERSHIP_VALIDATOR" --validate-body "$WORK/body" >/dev/null 2>&1 || {
    echo "error: ownership body is uncheckable; no Task creation attempted" >&2; exit 2; }
fi
TITLE64="$(printf '%s' "$TITLE" | base64 | tr -d '\n')"
BODY64="$(base64 < "$WORK/body" | tr -d '\n')"
# Bound tool output before shell capture; preserve failed command status and
# reject NUL before Bash can silently discard it. No raw tool logs are printed.
capture() {
  local limit="$1" file="$2" rc=0 size
  shift 2
  CAPTURE_SAFE=false
  "$@" 2>/dev/null | head -c "$((limit + 1))" > "$file" || rc=$?
  size="$(wc -c < "$file")" || return 1
  [[ "$size" -le "$limit" ]] || return 1
  tr -d '\000' < "$file" > "$WORK/no-nul" || return 1
  cmp -s "$file" "$WORK/no-nul" || return 1
  CAPTURE_SAFE=true
  return "$rc"
}
if ! capture 4096 "$WORK/repo" gh repo view ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} \
  --json nameWithOwner,url --jq 'if (.nameWithOwner|type) == "string" and (.url|type) == "string" then [.url,.nameWithOwner]|@tsv else error("uncheckable repository") end'; then
  echo "error: repository identity uncheckable; no Task creation attempted" >&2; exit 1
fi
IFS=$'\t' read -r REPO_URL CANONICAL_REPO EXTRA < "$WORK/repo" || bad_input
repo_pattern='^https://([A-Za-z0-9][A-Za-z0-9.-]*)/([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)$'
[[ "$REPO_URL" =~ $repo_pattern ]] || bad_input
HOST="${BASH_REMATCH[1]}"
[[ "$CANONICAL_REPO" = "${BASH_REMATCH[2]}/${BASH_REMATCH[3]}" && -z "$EXTRA" ]] || bad_input
case "${CANONICAL_REPO#*/}" in .|..) bad_input ;; esac
printf '%s\t%s\n' "$REPO_URL" "$CANONICAL_REPO" | cmp -s - "$WORK/repo" || bad_input
if [[ -n "$REQUESTED_REPO" ]]; then
  expected="$CANONICAL_REPO"
  case "$REQUESTED_REPO" in */*/*) expected="$HOST/$CANONICAL_REPO" ;; esac
  [[ "$(printf '%s' "$REQUESTED_REPO" | tr '[:upper:]' '[:lower:]')" = "$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')" ]] || bad_input
fi
REPO_ARGS=(--repo "$HOST/$CANONICAL_REPO")
URL="" NUM="" CREATED_ID="" CREATED_GRAPH=""
unconfirmed() {
  echo "error: $1 unconfirmed; the server may have changed. Inspect before another explicit invocation; no automatic retry or repair." >&2
  [[ -z "$URL" ]] || printf 'Known Task: %s\n' "$URL" >&2
  exit 1
}
# Retain the source creation/relationship flags, but NEVER send ai:ready here.
CREATE_ARGS=(--title "$TITLE" --body-file "$WORK/body" --label "type:task,exec:$EXEC" --parent "$PARENT")
[[ -z "$DEPS" ]] || CREATE_ARGS+=(--blocked-by "$DEPS")
created=false
if capture 4096 "$WORK/create" gh issue create "${REPO_ARGS[@]}" "${CREATE_ARGS[@]}"; then created=true; fi
if $CAPTURE_SAFE; then
  candidate="$(cat "$WORK/create")"
  case "$candidate" in
    "$REPO_URL"/issues/*)
      candidate_num="${candidate##*/}"
      if number "$candidate_num" && [[ "$candidate" = "$REPO_URL/issues/$candidate_num" ]]; then
        # At most the one normal terminal LF; extra lines are ambiguous.
        if [[ "$(wc -l < "$WORK/create")" -le 1 ]]; then URL="$candidate"; NUM="$candidate_num"; fi
      fi ;;
  esac
fi
$created && [[ -n "$URL" ]] || unconfirmed "Task creation/linking"
[[ "$NUM" != "$PARENT" ]] || unconfirmed "Task identity"
for dep in ${DEP_IDS[@]+"${DEP_IDS[@]}"}; do [[ "$NUM" != "$dep" ]] || unconfirmed "Task identity"; done

read_back() {
  local ready="$1" id number url graph title64 body64 extra
  # gh exports parent/blockers without repository fields and labels as a flat
  # first-100 array. Exactly 100 labels cannot prove completeness: refuse.
  local filter='
    def number: type == "number" and . == floor and . > 0 and . <= 2147483647;
    def link:
      type == "object" and (.id|type) == "string" and (.id|test("^[A-Za-z0-9_=-]{1,256}$"))
      and (.number|number) and (.title|type) == "string"
      and (.state == "OPEN" or .state == "CLOSED")
      and .url == ("'"$REPO_URL"'/issues/" + (.number|tostring));
    if (link and .number == '"$NUM"' and .state == "OPEN"
      and (.body|type) == "string"
      and (.parent|link) and .parent.number == '"$PARENT"'
      and (.blockedBy|type) == "object" and (.blockedBy.nodes|type) == "array"
      and (.blockedBy.totalCount|type) == "number" and .blockedBy.totalCount == (.blockedBy.nodes|length)
      and .blockedBy.totalCount <= 50 and all(.blockedBy.nodes[]; link)
      and ([.blockedBy.nodes[].id]|length) == ([.blockedBy.nodes[].id]|unique|length)
      and ([.blockedBy.nodes[].number]|sort) == (['"$DEPS"']|sort)
      and ([.blockedBy.nodes[].number]|length) == ([.blockedBy.nodes[].number]|unique|length)
      and (.labels|type) == "array" and (.labels|length) < 100
      and all(.labels[]; type == "object" and (.name|type) == "string" and (.name|length) > 0)
      and ([.labels[].name]|length) == ([.labels[].name]|unique|length)
      and ([.labels[].name]|index("type:task")) != null
      and ([.labels[].name|select(startswith("exec:"))] == ["exec:'"$EXEC"'"])
      and (([.labels[].name]|index("ai:ready")) != null) == '"$ready"')
    then [.id,.number,.url, ([.parent.id] + [.blockedBy.nodes|sort_by(.number)|.[].id]|join(",")),
          (.title|@base64),(.body|@base64)]|@tsv
    else error("uncheckable Task graph") end'
  capture 131072 "$WORK/view" gh issue view "$NUM" "${REPO_ARGS[@]}" \
    --json id,number,url,title,state,body,labels,parent,blockedBy --jq "$filter" || return 1
  IFS=$'\t' read -r id number url graph title64 body64 extra < "$WORK/view" || return 1
  [[ -n "$id" && "$number" = "$NUM" && "$url" = "$URL" && -z "$extra" ]] || return 1
  [[ "$title64" = "$TITLE64" && "$body64" = "$BODY64" ]] || return 1
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$number" "$url" "$graph" "$title64" "$body64" | cmp -s - "$WORK/view" || return 1
  [[ -z "$CREATED_ID" || "$CREATED_ID" = "$id" ]] || return 1
  [[ -z "$CREATED_GRAPH" || "$CREATED_GRAPH" = "$graph" ]] || return 1
  CREATED_ID="$id"
  CREATED_GRAPH="$graph"
}
read_back false || unconfirmed "Task read-back"
if $READY; then
  capture 4096 "$WORK/edit" gh issue edit "$NUM" "${REPO_ARGS[@]}" --add-label ai:ready || unconfirmed "Task readiness write"
  read_back true || unconfirmed "Task readiness read-back"
  printf 'Created and verified ready Task #%s: %s\n' "$NUM" "$URL"
else
  printf 'Created and verified Task #%s (not marked ready): %s\n' "$NUM" "$URL"
fi
echo "Readiness describes the brief. Dispatch only after frontier and ownership checks."
