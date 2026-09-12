#!/usr/bin/env bash
# check-task-ritual.sh — CI wall: a PR's linked Task must carry the start
# ritual, in order.
#
# The session-orchestration skill requires, before work starts on a Task:
#   - a claim comment: starts with "Starting in session" or "Resuming in session"
#   - a plan comment:  contains a "## Plan" heading or starts with "Plan:"
# This wall fails any PR whose primary linked issue — the first task link
# ("Closes #N"; close/fix/resolve variants accepted, as GitHub treats them
# alike; "Refs #N" accepted for tasks with post-merge acceptance, AGENTS.md
# §4) — lacks either comment. A PR with no task link at all fails too:
# the tracking graph makes an unlinked PR a defect, not a skip.
#
# Beyond existence, the wall proves chronology — artifacts posted after the
# fact do not count as a ritual:
#   - the earliest claim precedes the earliest plan comment;
#   - the earliest plan comment precedes the PR's earliest commit
#     (AGENTS.md §2: the plan is posted before implementation begins);
#   - claim and plan comments are unedited (updated_at == created_at) —
#     revisions belong in fresh comments, never edits of the record.
# Timestamps are second-resolution ISO-8601 UTC, so lexicographic
# comparison is chronological ordering. Equal stamps cannot prove an
# inversion, so ties pass: the wall fails only on provable violations.
#
# Beyond the start ritual, the wall enforces the execution mode (ADR-0003
# Decision 2) from comment content, order, and edit-state — never
# authorship, since all sessions share one GitHub login:
#   - a worker-dispatch comment starts with "Dispatching worker"; a release
#     comment starts with "Releasing worker" (first-line regexes, exactly
#     like the claim);
#   - a dispatch's first line names the worker session and its branch. The
#     branch must be the PR's head ref (managed prefixes allowed), which is
#     what stops one task's dispatch from satisfying another's trail. The
#     session ID is required but **not verified**: session trees are
#     app-local and no API reachable from CI can enumerate them, so it is a
#     durable record for humans and audits, not proof. This wall shows that
#     a specific session and branch were claimed — the supervisor is
#     responsible for having actually raised the session before writing it;
#   - any dispatch comment selects the two-tier path: the earliest dispatch
#     must not predate the earliest plan and must not postdate the PR's
#     first commit (committer date, ties pass), every dispatch after the
#     first needs a release comment timestamped between the previous
#     dispatch and the new one, and dispatch/release comments are unedited
#     like claim and plan. Declared exemptions are then ignored — a replan
#     from exemption to worker split is legitimate, and the dispatch trail
#     is the stronger signal of what actually happened;
#   - with no dispatch comment, at least one plan comment must declare the
#     small-task exemption with the phrase "no worker will be spawned",
#     matched case-insensitively (AGENTS.md §4);
#   - neither trail present fails: the task ran in an undeclared mode.
#
# Beyond chronology, the wall proves provenance and routing:
#   - the PR body carries a plan link ("Plan: …#issuecomment-ID") that
#     resolves to a real plan comment on the linked Task in this
#     repository — a dead link, a link to another repository or issue,
#     or a link to a non-plan comment (e.g. the claim) all fail (a dead
#     plan link shipped once and was caught by a human, not CI);
#   - the linked issue carries the 'type:task' label (plan-management:
#     Tasks enter the graph through the ai-task template, which labels
#     them; an unlabeled issue is invisible to frontier label queries).
#
# Usage:
#   bash .github/scripts/check-task-ritual.sh [<pr-number>]     # or set PR_NUMBER
#
# Exemptions — three, all narrow:
#   1. Allowlisted dependency bots skip the ritual (default: dependabot[bot]
#      renovate[bot] github-actions[bot]; override with RITUAL_EXEMPT_BOTS,
#      space-separated logins). Any other bot author — cloud coding agents
#      included — holds a session and is held to the full ritual.
#   2. Task-less onboarding: exact installed payload anchor in the base and
#      head, regular AGENTS/instructions, CUSTOMIZE removed in changed head
#      instructions, skill title and only bounded onboarding outputs changed.
#   3. Initial adoption: complete exact-base absence of AGENTS/instructions,
#      both regular files in the head and the exact installed payload anchor.
# These are structural exceptions, not runtime or installer attestations.
# Unsupported cases follow the ordinary Task ritual; read errors fail closed.
#
# Requires: GitHub CLI (gh), authenticated; git and base64 for bootstrap proof. Repo context comes from the
# checkout ({owner}/{repo} placeholders); set GH_REPO to override.

set -euo pipefail

PR="${1:-${PR_NUMBER:-}}"
if [[ -z "$PR" ]]; then
  echo "usage: bash .github/scripts/check-task-ritual.sh <pr-number>  (or set PR_NUMBER)" >&2
  exit 2
fi

command -v gh >/dev/null 2>&1 || { echo "error: gh CLI not found" >&2; exit 1; }

# GitHub occasionally answers with a transient HTML 5xx page ("invalid
# character '<'"); a deterministic wall must not flake on that, so every API
# read gets three attempts with a short pause. Offline fixtures set the pause
# to zero through RITUAL_API_RETRY_DELAY; production keeps the two-second
# default. The attempt count is never configurable.
api() {
  local attempt out delay="${RITUAL_API_RETRY_DELAY:-2}"
  for attempt in 1 2 3; do
    if out=$(gh api "$@" 2>&1); then
      printf '%s\n' "$out"
      return 0
    fi
    if [[ $attempt -lt 3 && "$delay" != "0" ]]; then
      sleep "$delay"
    fi
  done
  printf '%s\n' "$out" >&2
  return 1
}

# Ordinary verdicts bind one typed PR observation, not independent mutable
# field reads. Base64 preserves body bytes without evaluating shell content.
observation_fail() {
  echo "FAIL: PR #${PR} ritual observation unavailable, malformed or changed ($1)." >&2
  exit 1
}
[[ "$PR" =~ ^[1-9][0-9]*$ ]] || observation_fail pr-number
pr_query='
  def token: type == "string" and length > 0 and (test("[\\x00-\\x20\\x7f\\\\]") | not);
  def sha: type == "string" and length == 40 and test("^[0-9a-f]{40}$");
  if type != "object" or (.number | type != "number" or . < 1 or floor != .)
    or (.base.sha | sha | not) or (.head.sha | sha | not)
    or (.head.ref | token | not) or (.base.repo.full_name | token | not)
    or (.commits | type != "number" or . < 0 or floor != .)
    or (.user.login | token | not) or (.user.type | token | not)
    or (.body != null and (.body | type != "string"))
  then error("invalid PR observation") else
    [.number, .base.sha, .head.sha, .head.ref, .commits, .base.repo.full_name,
     ("b" + ((.body // "") | @base64)), .user.login, .user.type] | @tsv
  end'
observe_pr() { api "repos/{owner}/{repo}/pulls/${PR}" --jq "$pr_query" 2>/dev/null; }
pr_snapshot=$(observe_pr) || observation_fail pr-read
IFS=$'\t' read -r observed_pr observed_base observed_head head_ref commit_count repo_full body_encoded author author_type <<< "$pr_snapshot"
[[ "$observed_pr" == "$PR" ]] || observation_fail pr-identity
body=$(printf '%s' "${body_encoded#b}" | base64 -d) || observation_fail pr-body

# Only dependency bots are exempt — they do not hold sessions. Cloud coding
# agents also author PRs as bots (user.type == "Bot"), and those *do* run
# sessions, so exemption is an explicit allowlist, never a bot-type check.
if [[ "$author_type" == "Bot" || "$author" == *"[bot]" ]]; then
  case " ${RITUAL_EXEMPT_BOTS:-dependabot[bot] renovate[bot] github-actions[bot]} " in
    *" ${author} "*)
      echo "PASS: PR #${PR} is authored by allowlisted bot ${author}; dependency bots do not hold sessions."
      exit 0
      ;;
    *)
      echo "note: PR #${PR} author ${author} is a bot but not allowlisted; the full start ritual applies."
      ;;
  esac
fi

# Bootstrap exceptions use immutable PR commits and complete trees, not a
# mutable branch name, title alone, or a seed changelog. The installed frontier
# is a reviewed payload anchor; this is structural evidence, not attestation
# that a particular installer or runtime was executed.
ADOPTION_ANCHOR='.agents/skills/plan-management/scripts/frontier.sh'
reviewed_adoption_anchor() {
  case "$1" in
    # Accepted source-first/T18 payloads and reviewed T24 task-selection payload.
    $'100644\tblob\tf66d3aa5e73abf24052c70f557cd6df9177ca012'|\
    $'100644\tblob\tcc888c829bc5957871376004cb59a93b4980b50f'|\
    $'100644\tblob\t5017ee6979eec83c867a2da02118e6b03205040c') return 0 ;;
    *) return 1 ;;
  esac
}

proof_fail() { echo "FAIL: bootstrap proof is unreadable or invalid ($1)." >&2; exit 1; }
read_tree() {
  local commit="$1" tree header rows
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || return 1
  tree=$(api "repos/{owner}/{repo}/git/commits/${commit}" --jq '.tree.sha') || return 1
  [[ "$tree" =~ ^[0-9a-f]{40}$ ]] || return 1
  header=$(api "repos/{owner}/{repo}/git/trees/${tree}?recursive=1" \
    --jq '[.sha, (.sha | type), .truncated, (.truncated | type), (.tree | type)] | @tsv') || return 1
  [[ "$header" == "$tree"$'\tstring\tfalse\tboolean\tarray' ]] || return 1
  rows=$(api "repos/{owner}/{repo}/git/trees/${tree}?recursive=1" \
    --jq 'if all(.tree[]; ([.path, .mode, .type, .sha] | all(.[]; type == "string"))) then .tree[] | [.path, .mode, .type, .sha] | @tsv else error("invalid tree field type") end') || return 1
  # TSV projection must be lossless. Reject control/escaped paths, duplicates,
  # malformed objects and a truncated inventory; none is confirmed absence.
  printf '%s\n' "$rows" | LC_ALL=C awk -F '\t' '
    NF == 1 && $0 == "" { next }
    NF != 4 || $1 == "" || $1 ~ /[[:cntrl:]\\]/ || $1 ~ /^\// ||
      $1 ~ /(^|\/)\.\.?($|\/)/ || $1 ~ /\/\/|\/$/ || seen[$1]++ { bad=1 }
    length($4) != 40 || $4 ~ /[^0-9a-f]/ { bad=1 }
    !(($2 ~ /^100(644|755)$/ && $3 == "blob") ||
      ($2 == "120000" && $3 == "blob") || ($2 == "040000" && $3 == "tree") ||
      ($2 == "160000" && $3 == "commit")) { bad=1 }
    END { exit bad }
  ' || return 1
  printf '%s\n' "$rows"
}
entry() { printf '%s\n' "$1" | awk -F '\t' -v path="$2" '$1 == path { print $2 "\t" $3 "\t" $4 }'; }
regular_blob() { local pattern=$'^100644\tblob\t[0-9a-f]{40}$'; [[ "$1" =~ $pattern ]]; }
regular_output() { local pattern=$'^100(644|755)\tblob\t[0-9a-f]{40}$'; [[ "$1" =~ $pattern ]]; }
read_blob() {
  local oid="$1" encoding kind encoded observed
  encoding=$(api "repos/{owner}/{repo}/git/blobs/${oid}" --jq '.encoding') || return 1
  kind=$(api "repos/{owner}/{repo}/git/blobs/${oid}" --jq '.content | type') || return 1
  [[ "$encoding" == base64 && "$kind" == string ]] || return 1
  encoded=$(api "repos/{owner}/{repo}/git/blobs/${oid}" --jq '.content') || return 1
  observed=$(printf '%s' "$encoded" | base64 -d | git hash-object --stdin) || return 1
  [[ "$observed" == "$oid" ]] || return 1
  printf '%s' "$encoded" | base64 -d
}
bootstrap_exception() {
  local base head base_tree head_tree base_agents head_agents base_instructions head_instructions
  local base_anchor head_anchor title base_text head_text changed allowed path rebound output
  command -v git >/dev/null 2>&1 || proof_fail git-unavailable
  base=$(api "repos/{owner}/{repo}/pulls/${PR}" --jq '.base.sha') || proof_fail base-commit
  head=$(api "repos/{owner}/{repo}/pulls/${PR}" --jq '.head.sha') || proof_fail head-commit
  base_tree=$(read_tree "$base") || proof_fail base-tree
  head_tree=$(read_tree "$head") || proof_fail head-tree
  base_agents=$(entry "$base_tree" AGENTS.md) || proof_fail base-agents-lookup
  head_agents=$(entry "$head_tree" AGENTS.md) || proof_fail head-agents-lookup
  base_instructions=$(entry "$base_tree" .github/codex-instructions.md) || proof_fail base-instructions-lookup
  head_instructions=$(entry "$head_tree" .github/codex-instructions.md) || proof_fail head-instructions-lookup
  base_anchor=$(entry "$base_tree" "$ADOPTION_ANCHOR") || proof_fail base-anchor-lookup
  head_anchor=$(entry "$head_tree" "$ADOPTION_ANCHOR") || proof_fail head-anchor-lookup
  reviewed_adoption_anchor "$head_anchor" || return 1
  regular_blob "$head_agents" && regular_blob "$head_instructions" || return 1
  head_text=$(read_blob "${head_instructions##*$'\t'}") || proof_fail head-instructions

  if [[ -z "$base_agents" && -z "$base_instructions" ]]; then
    # Confirmed absence comes only from the complete exact-base tree. The
    # payload anchor distinguishes scaffold adoption from adding two filenames.
    rebound=$(api "repos/{owner}/{repo}/pulls/${PR}" --jq '[.base.sha, .head.sha] | @tsv') || proof_fail pr-readback
    [[ "$rebound" == "$base"$'\t'"$head" ]] || proof_fail pr-drift
    echo "PASS: PR #${PR} adopts the source-first scaffold; complete exact-base absence and installed payload anchor verified."
    return 0
  fi

  title=$(api "repos/{owner}/{repo}/pulls/${PR}" --jq '.title // ""') || proof_fail title
  [[ "$title" == 'scaffold: onboard '* ]] || return 1
  [[ "$base_anchor" == "$head_anchor" ]] || return 1
  regular_blob "$base_agents" && regular_blob "$base_instructions" || return 1
  [[ "$base_instructions" != "$head_instructions" ]] || return 1
  base_text=$(read_blob "${base_instructions##*$'\t'}") || proof_fail base-instructions
  [[ "$base_text" == *CUSTOMIZE* && "$head_text" != *CUSTOMIZE* ]] || return 1

  # P4 tuning / existing CI / P6 context and retro evidence only. Arbitrary
  # application work, AGENTS changes, and unsupported bootstrap combinations
  # require an ordinary planned Task instead of borrowing this exception.
  changed=$(printf '%s\n__TREE_SPLIT__\n%s\n' "$base_tree" "$head_tree" | awk -F '\t' '
    $0 == "__TREE_SPLIT__" { second=1; next }
    NF != 4 || $3 == "tree" { next }
    !second { before[$1]=$0; next }
    { after[$1]=$0 }
    END { for (p in before) if (before[p] != after[p]) print p
          for (p in after) if (!(p in before)) print p }
  ') || proof_fail tree-comparison
  allowed=true
  while IFS= read -r path; do
    case "$path" in
      .github/codex-instructions.md|.github/instructions/*.instructions.md|\
      .github/workflows/*.yml|.github/workflows/*.yaml|.github/docs/context/*|\
      .github/docs/agreements/retro-log.md) ;;
      *) allowed=false ;;
    esac
    output=$(entry "$head_tree" "$path") || proof_fail changed-output-lookup
    if [[ -z "$output" ]]; then
      # Removing an ordinary obsolete context/instruction file is permitted;
      # deleting a symlink/gitlink still needs the ordinary Task boundary.
      output=$(entry "$base_tree" "$path") || proof_fail deleted-output-lookup
    fi
    regular_output "$output" || allowed=false
  done <<< "$changed"
  $allowed || return 1
  rebound=$(api "repos/{owner}/{repo}/pulls/${PR}" --jq '[.base.sha, .head.sha] | @tsv') || proof_fail pr-readback
  [[ "$rebound" == "$base"$'\t'"$head" ]] || proof_fail pr-drift
  echo "PASS: PR #${PR} is the onboarding evidence PR; exact adopted base, changed tuned instructions, bounded outputs and unchanged PR bindings verified."
}

# A real Task relationship always follows the existing ordinary ritual path;
# bootstrap proof availability must not disable normal, already-planned work.
bootstrap_link=$(printf '%s\n' "$body" \
  | grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?|refs?)[[:space:]]+([A-Za-z]+[[:space:]]+)?#[0-9]+' \
  | head -n1 || true)
if [[ -z "$bootstrap_link" ]] && bootstrap_exception; then
  exit 0
fi

# The first task link names the primary Task under review. A qualifier may sit
# between the keyword and the number ("Refs Epic #2") — the phrasing is
# accurate and rejecting it buys no safety.
link=$(printf '%s\n' "$body" \
  | grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?|refs?)[[:space:]]+([A-Za-z]+[[:space:]]+)?#[0-9]+' \
  | head -n1 || true)
if [[ -z "$link" ]]; then
  echo "FAIL: PR #${PR} body has no task link (e.g. 'Closes #N', or 'Refs #N' for post-merge acceptance)."
  echo "      Every PR must declare the Task it lands (plan-management, tracking graph)."
  exit 1
fi
issue="${link##*#}"

# Preserve the source's selected-repository check: the PR response cannot
# define its own repository authority independently of the gh target.
selected_repo=$(api "repos/{owner}/{repo}" --jq '
  if (.full_name | type) == "string" then .full_name else error("invalid repository") end
' 2>/dev/null) || observation_fail repository-read
[[ "$(printf '%s' "$selected_repo" | tr '[:upper:]' '[:lower:]')" == "$(printf '%s' "$repo_full" | tr '[:upper:]' '[:lower:]')" ]] || observation_fail repository-identity

# Whole-second UTC is the API timestamp profile supported by this sensor.
# Validate calendar values explicitly: platform date parsers can normalize
# impossible dates and jq date functions differ between supported hosts.
valid_timestamp() {
  local value="$1" year month day hour minute second maximum
  local LC_ALL=C
  [[ ${#value} -eq 20 && "$value" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$ ]] || return 1
  year=$((10#${BASH_REMATCH[1]})); month=$((10#${BASH_REMATCH[2]})); day=$((10#${BASH_REMATCH[3]}))
  hour=$((10#${BASH_REMATCH[4]})); minute=$((10#${BASH_REMATCH[5]})); second=$((10#${BASH_REMATCH[6]}))
  ((year >= 1 && month >= 1 && month <= 12 && day >= 1 && hour < 24 && minute < 60 && second < 60)) || return 1
  case "$month" in
    4|6|9|11) maximum=30 ;;
    2) maximum=28; if ((year % 400 == 0 || (year % 4 == 0 && year % 100 != 0))); then maximum=29; fi ;;
    *) maximum=31 ;;
  esac
  ((day <= maximum))
}

task_query='
  if type != "object" or (.number | type != "number" or . < 1 or floor != .)
    or (.state != "open" and .state != "closed")
    or (.comments | type != "number" or . < 0 or floor != .)
    or (.body != null and (.body | type != "string"))
    or (.labels | type != "array")
    or any(.labels[]; type != "object" or (.name | type != "string" or length == 0))
  then error("invalid Task observation") else
    [.number, .state, .comments, ("b" + ((.body // "") | @base64)),
     ("b" + ([.labels[].name] | sort | tojson | @base64)),
     any(.labels[]; .name == "type:task")] | @tsv
  end'
observe_task() { api "repos/{owner}/{repo}/issues/${issue}" --jq "$task_query" 2>/dev/null; }
task_snapshot=$(observe_task) || observation_fail task-read
IFS=$'\t' read -r observed_issue _task_state comment_count _task_body _task_labels is_task <<< "$task_snapshot"
[[ "$observed_issue" == "$issue" ]] || observation_fail task-identity

# One pass over the issue's comments, emitting a TSV marker per ritual
# artifact: TYPE, created_at, updated_at. The API returns ascending
# created_at, but earliest-of is computed with an explicit sort anyway.
comment_query='
  if type != "array" then error("invalid comments page") else . end |
  .[] |
  if type != "object" or (.id | type != "number" or . < 1 or floor != .)
    or (.body | type != "string") or (.created_at | type != "string")
    or (.updated_at | type != "string") or (.issue_url | type != "string")
  then error("invalid comment") else . end |
  (["COMMENT", .id, .created_at, .updated_at, ("b" + (.body | @base64)), .issue_url] | @tsv),
  (if (.body | test("^(Starting|Resuming) in session")) then [ "CLAIM", .created_at, .updated_at ] | @tsv else empty end),
  (if ((.body | test("(^|\\n)## Plan\\b")) or (.body | startswith("Plan:"))) then [ "PLAN", .created_at, .updated_at ] | @tsv else empty end),
  (if (.body | test("^Dispatching worker")) then [ "DISPATCH", .created_at, .updated_at, (.body | split("\n")[0]) ] | @tsv else empty end),
  (if (.body | test("^Releasing worker")) then [ "RELEASE", .created_at, .updated_at ] | @tsv else empty end),
  (if (((.body | test("(^|\\n)## Plan\\b")) or (.body | startswith("Plan:"))) and (.body | ascii_downcase | contains("no worker will be spawned"))) then [ "EXEMPT", .created_at, .updated_at ] | @tsv else empty end)
'
observe_comments() { api "repos/{owner}/{repo}/issues/${issue}/comments?per_page=100" --paginate --jq "$comment_query" 2>/dev/null; }
comment_snapshot=$(observe_comments) || observation_fail comments-read
comment_rows=$(printf '%s\n' "$comment_snapshot" | awk -F '\t' '$1 == "COMMENT"')
actual_comments=$(printf '%s\n' "$comment_rows" | awk 'NF {n++} END {print n+0}')
unique_comments=$(printf '%s\n' "$comment_rows" | awk -F '\t' 'NF {print $2}' | sort -u | awk 'NF {n++} END {print n+0}')
[[ "$actual_comments" == "$comment_count" && "$unique_comments" == "$comment_count" ]] || observation_fail comments-completeness
while IFS=$'\t' read -r _kind _id created updated _encoded issue_url; do
  [[ -n "$_kind" ]] || continue
  if ! { valid_timestamp "$created" && valid_timestamp "$updated"; }; then
    observation_fail comment-date
  fi
  [[ "$(printf '%s' "$issue_url" | tr '[:upper:]' '[:lower:]')" == "https://api.github.com/repos/$(printf '%s' "$repo_full" | tr '[:upper:]' '[:lower:]')/issues/${issue}" ]] || observation_fail comment-identity
done <<< "$comment_rows"
markers=$(printf '%s\n' "$comment_snapshot" | awk -F '\t' '$1 != "COMMENT"')

ok=true
has_marker() { printf '%s\n' "$markers" | awk -F '\t' -v kind="$1" '$1 == kind {found=1} END {exit !found}'; }
if ! has_marker CLAIM; then
  echo "FAIL: issue #${issue} has no start claim comment ('Starting in session …' or 'Resuming in session …')."
  ok=false
fi
if ! has_marker PLAN; then
  echo "FAIL: issue #${issue} has no plan comment (a '## Plan' heading, or a body starting 'Plan:')."
  ok=false
fi

if ! $ok; then
  echo "      Post the missing comment(s) on #${issue} — session-orchestration start ritual, steps 4-5 — then re-run this check."
  exit 1
fi

# Immutability — ritual comments are append-only; a revision lives in a
# fresh comment (session-orchestration, work loop). An edited ritual
# comment breaks the audit trail. EXEMPT rows are skipped: an exemption
# marker always doubles a PLAN row for the same comment, which already
# reports any edit.
edited=$(printf '%s\n' "$markers" | awk -F '\t' '$1 != "EXEMPT" && $2 != $3 { print $1 " created " $2 ", updated " $3 }')
if [[ -n "$edited" ]]; then
  echo "FAIL: issue #${issue} has ritual comment(s) edited after posting:"
  printf '%s\n' "$edited" | sed 's/^/        /'
  echo "      Ritual comments (claim, plan, dispatch, release) are immutable; post a fresh comment instead of editing (session-orchestration, work loop)."
  ok=false
fi

earliest_claim=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "CLAIM" { print $2 }' | sort | head -n1)
earliest_plan=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "PLAN" { print $2 }' | sort | head -n1)

# Chronology 1 — claim, then plan (session-orchestration steps 4-5).
if [[ "$earliest_claim" > "$earliest_plan" ]]; then
  echo "FAIL: issue #${issue} ritual is out of order: earliest claim (${earliest_claim}) postdates earliest plan (${earliest_plan})."
  echo "      Claim the task first, then post the plan (session-orchestration, steps 4-5)."
  ok=false
fi

# Chronology 2 — the plan precedes the code (AGENTS.md §2). Committer date
# is primary: rebases rewrite it forward, which only widens the margin,
# while amends preserve the author date — an author date may predate the
# plan even when the code followed it. Author date is only a fallback for
# commit objects lacking a committer date.
# The PR commits endpoint caps its entire response at 250, even paginated.
# No empty/partial list is chronology, and no invalid row may be discarded.
if [[ ! "$commit_count" =~ ^[0-9]{1,3}$ ]] || ! ((commit_count >= 1 && commit_count <= 250)); then
  observation_fail commit-limit
fi
# shellcheck disable=SC2016 # $date is a jq binding, not a shell expansion.
commit_rows=$(api "repos/{owner}/{repo}/pulls/${PR}/commits?per_page=100" --paginate --jq '
  if type != "array" then error("invalid commits page") else . end | .[] |
  if type != "object" or (.sha | type != "string" or length != 40 or (test("^[0-9a-f]{40}$") | not))
    or (.commit | type != "object")
    or (.commit.committer != null and (.commit.committer | type != "object"))
  then error("invalid commit") else . end |
  (if .commit.committer.date == null then .commit.author.date else .commit.committer.date end) as $date |
  if ($date | type != "string") then error("missing commit date") else [.sha, $date] | @tsv end
' 2>/dev/null) || observation_fail commits-read
actual_commits=$(printf '%s\n' "$commit_rows" | awk 'NF {n++} END {print n+0}')
unique_commits=$(printf '%s\n' "$commit_rows" | cut -f1 | sort -u | awk 'NF {n++} END {print n+0}')
[[ "$actual_commits" == "$commit_count" && "$unique_commits" == "$commit_count" ]] || observation_fail commits-completeness
printf '%s\n' "$commit_rows" | cut -f1 | grep -Fxq "$observed_head" || observation_fail commit-head
while IFS=$'\t' read -r _sha timestamp; do
  valid_timestamp "$timestamp" || observation_fail commit-date
done <<< "$commit_rows"
first_commit=$(printf '%s\n' "$commit_rows" | cut -f2 | sort | head -n1)
if [[ "$earliest_plan" > "$first_commit" ]]; then
  echo "FAIL: PR #${PR}'s first commit (${first_commit}, committer date) predates the plan comment on issue #${issue} (${earliest_plan})."
  echo "      The plan of record is posted before implementation begins (AGENTS.md §2)."
  ok=false
fi

# Execution mode (ADR-0003 Decision 2) — every task shows either a
# worker-dispatch trail or a declared small-task exemption; an undeclared
# mode fails. Any dispatch comment selects the two-tier path and declared
# exemptions are then ignored: a replan from exemption to worker split is
# legitimate, and the dispatch trail is the stronger signal of what
# actually happened. The exemption marker is the exact phrase quoted in
# AGENTS.md §4, matched case-sensitively inside a plan comment.
mode_desc=""
valid_session_reference() {
  local value="$1" segment count=0 rest
  local LC_ALL=C
  # Legacy IDs remain opaque. Require whole bounded tokens, not a hex prefix.
  if [[ "$value" =~ ^[0-9a-fA-F][0-9a-fA-F-]{7,127}$ && "$value" != *--* && "$value" != *- ]]; then
    return 0
  fi
  # Canonical collaboration references are tool identifiers, never paths or
  # authenticated identities. Limit the full token and each of 1-16 segments.
  [[ ${#value} -le 256 && "$value" == /root/* ]] || return 1
  rest="${value#/root/}"
  while :; do
    segment="${rest%%/*}"
    [[ "$segment" =~ ^[a-z0-9_]{1,63}$ ]] || return 1
    case "$segment" in unknown|none|null|tbd|todo|placeholder) return 1 ;; esac
    count=$((count + 1))
    [[ $count -le 16 ]] || return 1
    [[ "$rest" == */* ]] || break
    rest="${rest#*/}"
  done
}
if has_marker DISPATCH; then
  earliest_dispatch=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "DISPATCH" { print $2 }' | sort | head -n1)
  mode_desc="two-tier (dispatch ${earliest_dispatch})"

  # Worker identity. The dispatch comment names the session it raised and the
  # branch that session works on. The branch is checkable — it must be the
  # PR's head ref, so a dispatch written for one task cannot satisfy
  # another's trail. The session ID is not: session trees are app-local and
  # no API here can enumerate them, so it is required as a durable record for
  # humans and audits, never treated as proof. What this wall can show is
  # that the supervisor claimed a specific session and a matching branch.
  while IFS=$'\t' read -r _kind _created _updated first_line; do
    [[ -n "$first_line" ]] || continue
    # Match one complete field and branch, rejecting delimiters, escaped TSV
    # controls and prefix/tail contamination. Extra scope belongs on later lines.
    dispatch_pattern='^Dispatching worker:[^()]+ \(session ([^()]*)\), branch ([^ ,()]+)$'
    if [[ "$first_line" == *\\* ]] || printf '%s' "$first_line" | LC_ALL=C grep -q '[[:cntrl:]]' ||
       [[ ! "$first_line" =~ $dispatch_pattern ]]; then
      echo "FAIL: issue #${issue} has a malformed worker-dispatch first line:"
      echo "        ${first_line}"
      echo "      Use 'Dispatching worker: Task worker (session <actual-reference>), branch <branch>'."
      ok=false
      continue
    fi
    session_reference="${BASH_REMATCH[1]}"
    dispatch_branch="${BASH_REMATCH[2]}"
    if ! valid_session_reference "$session_reference"; then
      echo "FAIL: issue #${issue} has a missing, invalid or unbounded worker session reference."
      ok=false
      continue
    fi
    if [[ -z "$dispatch_branch" ]]; then
      echo "FAIL: issue #${issue} has a worker-dispatch comment that names no branch:"
      echo "        ${first_line}"
      echo "      Record the worker's branch so the dispatch can be tied to this PR (session-orchestration skill)."
      ok=false
    elif [[ -n "$head_ref" && "$dispatch_branch" != "$head_ref" && "$head_ref" != *"$dispatch_branch" ]]; then
      # Managed surfaces prefix the branch they generate (AGENTS.md §4), so a
      # head ref ending in the dispatched name is the same branch.
      echo "FAIL: issue #${issue} dispatches branch '${dispatch_branch}', but PR #${PR} is from '${head_ref}'."
      echo "      A dispatch names the branch its worker actually works on (session-orchestration skill)."
      ok=false
    fi
  done <<EOF
$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "DISPATCH"')
EOF

  # Chronology 3 — the dispatch follows the plan of record: the supervisor
  # dispatches a worker to execute an already-posted plan (ADR-0003).
  if [[ "$earliest_plan" > "$earliest_dispatch" ]]; then
    echo "FAIL: issue #${issue} ritual is out of order: earliest worker dispatch (${earliest_dispatch}) predates earliest plan (${earliest_plan})."
    echo "      Post the plan first, then the worker-dispatch comment (session-orchestration skill; ADR-0003)."
    ok=false
  fi

  # Chronology 4 — workers only start after dispatch, so the earliest
  # dispatch precedes the PR's first commit. Committer-date semantics as
  # above: rebases move committer dates forward, which only widens the
  # margin; equal stamps prove nothing, so ties pass.
  if [[ "$earliest_dispatch" > "$first_commit" ]]; then
    echo "FAIL: PR #${PR}'s first commit (${first_commit}, committer date) predates the worker-dispatch comment on issue #${issue} (${earliest_dispatch})."
    echo "      The supervisor dispatches the worker before implementation begins (ADR-0003; session-orchestration skill)."
    ok=false
  fi

  # One active worker per PR — every dispatch after the first must be
  # preceded by a release comment timestamped between the previous
  # dispatch and the new one, inclusive on both ends: a release stamped
  # in the same second as either dispatch cannot prove a violation.
  releases=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "RELEASE" { print $2 }' | sort)
  dispatches=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "DISPATCH" { print $2 }' | sort)
  prev_dispatch=""
  while IFS= read -r d; do
    [[ -z "$d" ]] && continue
    if [[ -n "$prev_dispatch" ]]; then
      released=false
      while IFS= read -r r; do
        [[ -z "$r" ]] && continue
        if [[ ! "$r" < "$prev_dispatch" && ! "$r" > "$d" ]]; then
          released=true
          break
        fi
      done <<< "$releases"
      if ! $released; then
        echo "FAIL: issue #${issue} dispatches a replacement worker (${d}) with no release comment between it and the previous dispatch (${prev_dispatch})."
        echo "      Release the active worker first ('Releasing worker …'), then dispatch the successor (session-orchestration skill; ADR-0003)."
        ok=false
      fi
    fi
    prev_dispatch="$d"
  done <<< "$dispatches"
elif has_marker EXEMPT; then
  mode_desc="declared small-task exemption"

  # The exemption is a declaration made *before* implementing, mirroring
  # plan-before-commit. Without this, a plan carrying the phrase posted after
  # the work still satisfies the mode check — the exemption becomes something
  # claimed in hindsight rather than a decision the trail records.
  earliest_exempt=$(printf '%s\n' "$markers" | awk -F '\t' '$1 == "EXEMPT" { print $2 }' | sort | head -n1)
  if [[ "$earliest_exempt" > "$first_commit" ]]; then
    echo "FAIL: PR #${PR}'s first commit (${first_commit}, committer date) predates the small-task exemption on issue #${issue} (${earliest_exempt})."
    echo "      Declare the exemption in the plan comment before implementing (AGENTS.md §4; session-orchestration skill)."
    ok=false
  fi
else
  echo "FAIL: issue #${issue} declares no execution mode: no worker-dispatch comment ('Dispatching worker …' first line) and no plan comment containing 'no worker will be spawned'."
  echo "      Dispatch a worker or declare the small-task exemption in the plan comment (AGENTS.md §4; session-orchestration skill)."
  ok=false
fi

# Routing — the linked issue must be a Task in the tracking graph. The
# ai-task template applies 'type:task'; without it the issue is invisible
# to label-driven frontier queries, so a PR closing it lands untracked work.
if [[ "$is_task" != true ]]; then
  echo "FAIL: issue #${issue} lacks the 'type:task' label."
  ok=false
fi

# Provenance — the PR's plan link must resolve to the plan of record on the
# linked Task in this repository. The link is load-bearing for reviewers and
# future sessions; a dead link once passed CI and needed a human to catch.
plan_link=$(printf '%s\n' "$body" \
  | grep -oiE 'plan:[[:space:]]*https://github\.com/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+#issuecomment-[0-9]+' \
  | head -n1 || true)
if [[ -z "$plan_link" ]]; then
  echo "FAIL: PR #${PR} body has no plan link ('Plan: https://github.com/<owner>/<repo>/issues/N#issuecomment-ID')."
  echo "      Link the plan comment posted on the Task (session-orchestration step 5; the PR template's Plan line)."
  ok=false
else
  # Parse a lowercased copy: GitHub treats owner/repo case-insensitively,
  # and the numeric fields are unaffected.
  plan_link_lc=$(printf '%s' "$plan_link" | tr '[:upper:]' '[:lower:]')
  link_repo=$(printf '%s\n' "$plan_link_lc" | sed -E 's|.*github\.com/([^/]+/[^/]+)/issues/.*|\1|')
  link_issue=$(printf '%s\n' "$plan_link_lc" | sed -E 's|.*/issues/([0-9]+)#issuecomment-[0-9]+.*|\1|')
  comment_id=$(printf '%s\n' "$plan_link_lc" | sed -E 's|.*#issuecomment-([0-9]+).*|\1|')
  # The comment-id lookup below is repository-scoped, so a link naming a
  # foreign repository could otherwise resolve to an unrelated local
  # comment that happens to share the id — reject it outright.
  plan_query='
    if type != "object" or (.id | type != "number" or . < 1 or floor != .)
      or (.body | type != "string") or (.issue_url | type != "string")
      or (.created_at | type != "string") or (.updated_at | type != "string")
    then error("invalid plan") else
      ["COMMENT", .id, .created_at, .updated_at, ("b" + (.body | @base64)), .issue_url,
       (if ((.body | test("(^|\\n)## Plan\\b")) or (.body | startswith("Plan:"))) then "plan" else "other" end)] | @tsv
    end'
  observe_plan() { api "repos/{owner}/{repo}/issues/comments/${comment_id}" --jq "$plan_query" 2>/dev/null; }
  if [[ "$link_repo" != "$(printf '%s' "$repo_full" | tr '[:upper:]' '[:lower:]')" ]]; then
    echo "FAIL: PR #${PR}'s plan link points at repository ${link_repo}, but the linked task lives in ${repo_full}."
    echo "      Link the plan comment on the linked Task in this repository."
    ok=false
  elif [[ "$link_issue" != "$issue" ]]; then
    echo "FAIL: PR #${PR}'s plan link points at issue #${link_issue}, but the PR's task link is #${issue}."
    ok=false
  elif plan_snapshot=$(observe_plan); then
    IFS=$'\t' read -r _kind plan_id _created _updated _encoded _url comment_kind <<< "$plan_snapshot"
    if [[ "$plan_id" != "$comment_id" ]] || ! printf '%s\n' "$comment_rows" | grep -Fx -- "${plan_snapshot%$'\t'*}" >/dev/null; then
      echo "FAIL: PR #${PR}'s plan link does not match the observed Task comment."
      ok=false
    elif [[ "$comment_kind" != "plan" ]]; then
      echo "FAIL: PR #${PR}'s plan link resolves to a comment that is not a plan comment (no '## Plan' heading or 'Plan:' prefix)."
      echo "      Link the plan of record itself — not the claim comment or a status update."
      ok=false
    fi
  else
    echo "FAIL: PR #${PR}'s plan link does not resolve: comment ${comment_id} not found on this repository."
    ok=false
  fi
fi

$ok || exit 1

# Re-observe membership as well as selected IDs, so added/deleted/revised
# decisions cannot escape the final check. These are bounded API observations,
# not an atomic transaction or an authenticated account of worker actions.
final_task=$(observe_task) || observation_fail task-readback
[[ "$final_task" == "$task_snapshot" ]] || observation_fail task-drift
final_comments=$(observe_comments) || observation_fail comments-readback
[[ "$final_comments" == "$comment_snapshot" ]] || observation_fail comments-drift
final_plan=$(observe_plan) || observation_fail plan-readback
[[ "$final_plan" == "$plan_snapshot" ]] || observation_fail plan-drift
final_pr=$(observe_pr) || observation_fail pr-readback
[[ "$final_pr" == "$pr_snapshot" ]] || observation_fail pr-drift

echo "PASS: PR #${PR} at head ${observed_head} (base ${observed_base}) → issue #${issue} ritual in order: claim ${earliest_claim} → plan ${earliest_plan} → first commit ${first_commit}; ${commit_count} commits; mode: ${mode_desc}; stable Task/plan observation and type:task verified."
