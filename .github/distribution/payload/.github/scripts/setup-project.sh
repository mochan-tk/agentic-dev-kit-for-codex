#!/usr/bin/env bash
# setup-project.sh — bootstrap a GitHub Projects (v2) roadmap board, add
# Task/Epic issues, and set dates only when real schedule spans exist.
#
# Idempotent: `init` reuses an open project with the same title, skips
# date fields that already exist, and re-links safely; `add` and `dates`
# reuse the project item when the issue is already on the board.
#
# Usage:
#   bash .github/scripts/setup-project.sh init  [--owner <login>] [--title <title>] [-R owner/repo]
#   bash .github/scripts/setup-project.sh add   --project <number> --issue <n>
#                          [--owner <login>] [-R owner/repo]
#   bash .github/scripts/setup-project.sh dates --project <number> --issue <n>
#                          --start YYYY-MM-DD --target YYYY-MM-DD
#                          [--owner <login>] [-R owner/repo]
#   bash .github/scripts/setup-project.sh readback --project <number> --issue <n>
#                          [--owner <login>] [-R owner/repo]
#   bash .github/scripts/setup-project.sh verify --project <number> --issue <n>
#                          --expect-kind Task --expect-start YYYY-MM-DD --expect-target YYYY-MM-DD
#                          [--owner <login>] [-R owner/repo]
#   bash .github/scripts/setup-project.sh --help
#
# Subcommands:
#   init   Create (or reuse) a Projects v2 board titled "<repo> roadmap" by
#          default, add DATE fields `Start date` and `Target date` and a
#          SINGLE_SELECT field `Kind` (options Epic, Task) if missing, create
#          the `Roadmap`, `Kanban` and `Backlog` views if missing, link
#          the project to the repository, and print the project number and
#          URL. Re-running is a no-op. Projects v2 boards are always
#          user/org-owned (repo-owned boards no longer exist); the repo
#          link makes the board show up in the repository's Projects tab.
#   add    Add issue <n> to project <number> without inventing dates. Also
#          sets `Kind` from `type:epic` / `type:task` when available.
#   dates  Add issue <n> to project <number> (reusing the item when already
#          present) and set both date fields. Dates must be YYYY-MM-DD; a
#          target date earlier than the start date is rejected. Also sets
#          the `Kind` field from the issue's labels (`type:epic` -> Epic,
#          `type:task` -> Task) when the field and a matching label exist.
#   readback Observe one exact Issue item's Kind, Start date and Target date
#          through paginated typed GraphQL queries, without writes. Exit 0
#          means populated observations, not a match to expected values or
#          authority; exit 1 reports missing values/item, 2 invalid arguments,
#          and 3 uncheckable responses. See the installation guide for limits.
#   verify Compare one readback with the supplied durable-plan Kind and dates.
#          Exit 0 means an exact match, 1 mismatch/missing, 2 invalid inputs,
#          3 uncheckable. Expectations do not prove consent or acceptance.
#
# Options:
#   --owner <login>          Project owner login (user or org). Default: the
#                            owner of the target repository.
#   --title <title>          init: board title. Default: "<repo> roadmap".
#   --project <number>       add/dates/readback/verify: project number.
#   --issue <n>              add/dates/readback/verify: issue number.
#   --start <YYYY-MM-DD>     dates: start date.
#   --target <YYYY-MM-DD>    dates: target date (not earlier than start).
#   --expect-kind <kind>     verify: Task or Epic (Task for per-Task close-out).
#   --expect-start <date>    verify: authorized Start date (YYYY-MM-DD).
#   --expect-target <date>   verify: authorized Target date (not before start).
#   -R, --repo <owner/repo>  Target repository. Default: the repository the
#                            current directory belongs to (via `gh repo view`).
#   -h, --help               Show this help and exit.
#
# Views are created by name (`Roadmap`, `Kanban`, `Backlog`) and matched by
# name on re-runs, so an adopter's own views are never renamed or removed.
# What stays manual: `createProjectV2View` takes only a name and a layout —
# its `configuration` input carries `visibleFieldIds` alone — so the Roadmap
# view's date fields and "Group by: Kind" must be set once in the UI.
#
# Requires: gh >= 2.45 (`gh project link`), jq, and authenticated credentials.
# Readback needs Project read access (read:project for classic/OAuth tokens);
# writes need project scope and separate authority.
# Compatible with bash 3.2 (macOS /bin/bash).

set -euo pipefail

# Consent-gated adopter feedback (ADR-0002): on an unguarded failure in an
# interactive run, offer - default no, full preview, allowlist-only - to
# file the failure upstream. Lib absent or any gate closed: byte-identical.

# Print the header comment above (everything from line 2 to the first blank
# line), stripped of the leading `# ` — same self-documenting pattern as the
# other .github/scripts/ bootstrap scripts.
usage() { sed -n '2,/^$/{s/^# \{0,1\}//p;}' "$0"; }

fail() { echo "error: $*" >&2; exit 1; }

usage_error() {
  echo "error: $*" >&2
  echo "Run 'bash .github/scripts/setup-project.sh --help' for usage." >&2
  exit 2
}

require_tools() {
  command -v gh >/dev/null 2>&1 || fail "gh CLI not found on PATH"
  command -v jq >/dev/null 2>&1 || fail "jq not found on PATH"
  # Probe the token, not just the binary: an unauthenticated gh otherwise
  # fails later inside a project API call, where the error names the call
  # rather than the cause. Same probe and wording as the sibling setup
  # scripts.
  gh api user --jq .login >/dev/null 2>&1 \
    || fail "gh is not authenticated
  fix: run: gh auth login"
}

REPO=""
REPO_NAME=""
REPO_OWNER=""

resolve_repo() {
  if [[ -z "$REPO" ]]; then
    REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
  fi
  [[ "$REPO" == */* ]] || usage_error "repository must be owner/repo, got: $REPO"
  REPO_NAME="${REPO##*/}"
  REPO_OWNER="${REPO%%/*}"
}

# Print the ID of the field named "$3" in project "$1" of owner "$2", or
# nothing when the field does not exist.
# `$name` below is a jq variable, not a shell expansion.
# shellcheck disable=SC2016
field_id() {
  gh project field-list "$1" --owner "$2" --limit 100 --format json \
    | jq -r --arg name "$3" \
        '[.fields[] | select(.name == $name) | .id] | first // empty'
}

# Print the ID of option "$4" of the single-select field named "$3" in
# project "$1" of owner "$2", or nothing when field or option is missing.
# `$name`/`$opt` below are jq variables, not shell expansions.
# shellcheck disable=SC2016
option_id() {
  gh project field-list "$1" --owner "$2" --limit 100 --format json \
    | jq -r --arg name "$3" --arg opt "$4" \
        '[.fields[] | select(.name == $name) | .options[]?
          | select(.name == $opt) | .id] | first // empty'
}

# Shared context for `add` and `dates`. Bash 3.2 has no namerefs, so these
# values are deliberately scoped with a prefix rather than returned through
# caller-owned variables.
PROJECT_NODE_ID=""
PROJECT_ITEM_ID=""
PROJECT_ISSUE_URL=""
PROJECT_ISSUE_LABELS=""

load_project_issue() {
  local project="$1" owner="$2" issue="$3" issue_json
  # Resolving the URL via the API also fails fast when the issue is missing.
  issue_json="$(gh issue view "$issue" --repo "$REPO" --json url,labels)"
  PROJECT_ISSUE_URL="$(jq -r '.url' <<<"$issue_json")"
  PROJECT_ISSUE_LABELS="$(jq -r '.labels[].name' <<<"$issue_json")"
  PROJECT_NODE_ID="$(gh project view "$project" --owner "$owner" \
    --format json --jq '.id')"
}

ensure_project_item() {
  local project="$1" owner="$2"
  # item-add is idempotent: when the issue is already on the board it
  # returns the existing item's ID instead of failing or duplicating.
  PROJECT_ITEM_ID="$(gh project item-add "$project" --owner "$owner" \
    --url "$PROJECT_ISSUE_URL" --format json --jq '.id')"
}

apply_kind() {
  local project="$1" owner="$2" issue="$3" kind=""
  if printf '%s\n' "$PROJECT_ISSUE_LABELS" | grep -Fxq "type:epic"; then
    kind="Epic"
  elif printf '%s\n' "$PROJECT_ISSUE_LABELS" | grep -Fxq "type:task"; then
    kind="Task"
  fi
  if [[ -z "$kind" ]]; then
    echo "Note: issue #$issue has neither 'type:epic' nor 'type:task' label;" \
      "leaving 'Kind' unset."
    return 0
  fi

  # Older boards (init run before the Kind field existed) stay usable:
  # setting Kind is best-effort, with a pointer to re-run init.
  local kind_field_id kind_option_id
  kind_field_id="$(field_id "$project" "$owner" "Kind")"
  if [[ -z "$kind_field_id" ]]; then
    echo "Note: project #$project has no 'Kind' field;" \
      "re-run 'bash .github/scripts/setup-project.sh init' to add it."
    return 0
  fi
  kind_option_id="$(option_id "$project" "$owner" "Kind" "$kind")"
  [[ -n "$kind_option_id" ]] \
    || fail "field 'Kind' on project #$project has no '$kind' option"

  gh project item-edit --id "$PROJECT_ITEM_ID" \
    --project-id "$PROJECT_NODE_ID" --field-id "$kind_field_id" \
    --single-select-option-id "$kind_option_id" >/dev/null
  echo "Set Kind = $kind for issue #$issue."
}

cmd_init() {
  local owner="" title=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --owner)
        [[ -n "${2:-}" ]] || usage_error "--owner requires a login argument"
        owner="$2"; shift 2 ;;
      --title)
        [[ -n "${2:-}" ]] || usage_error "--title requires a value"
        title="$2"; shift 2 ;;
      -R|--repo)
        [[ -n "${2:-}" ]] || usage_error "$1 requires an owner/repo argument"
        REPO="$2"; shift 2 ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        usage_error "unknown argument for init: $1" ;;
    esac
  done
  require_tools
  resolve_repo
  # Projects v2 boards are user/org-owned, so default to the repo owner to
  # keep the board next to the repository it visualizes.
  [[ -n "$owner" ]] || owner="$REPO_OWNER"
  [[ -n "$title" ]] || title="$REPO_NAME roadmap"

  # Select strictly by exact title match among the owner's open projects, so
  # the script never touches a project it did not create or select itself.
  # `$title` is a jq variable, not a shell expansion.
  local number
  # shellcheck disable=SC2016
  number="$(gh project list --owner "$owner" --limit 100 --format json \
    | jq -r --arg title "$title" \
        '[.projects[] | select(.title == $title) | .number] | first // empty')"

  if [[ -n "$number" ]]; then
    echo "Reusing project #$number ('$title') owned by $owner."
  else
    # `gh project list` hides closed projects, so a same-title board that
    # was closed would otherwise be recreated as a duplicate (or, where the
    # org refuses API creation, dead-end). Detect it and instruct instead:
    # reopening a board a human deliberately closed is not this script's
    # call to make.
    local closed_number
    # shellcheck disable=SC2016
    closed_number="$(gh project list --owner "$owner" --closed --limit 100 \
      --format json | jq -r --arg title "$title" \
        '[.projects[] | select(.title == $title and .closed == true) | .number] | first // empty')"
    if [[ "$closed_number" =~ ^[1-9][0-9]*$ ]]; then
      fail "project '$title' owned by '$owner' exists but is closed \
(#$closed_number); reopen it with 'gh project close $closed_number --owner \
$owner --undo' and re-run init"
    fi
    number="$(gh project create --owner "$owner" --title "$title" \
      --format json --jq '.number')"
    # gh unmarshals API responses into Go structs, so a number missing from
    # a degraded response surfaces as Go's zero value 0 instead of an error
    # — and gh's project commands treat 0 as "no number supplied". The
    # create above just guaranteed a project with this exact title exists,
    # so re-resolve by title instead of trusting an unusable answer.
    if ! [[ "$number" =~ ^[1-9][0-9]*$ ]]; then
      # shellcheck disable=SC2016
      number="$(gh project list --owner "$owner" --limit 100 --format json \
        | jq -r --arg title "$title" \
            '[.projects[] | select(.title == $title) | .number] | first // empty')"
    fi
    echo "Created project #$number ('$title') owned by $owner."
  fi

  # Both paths above parse gh output; never hand follow-up commands a
  # number that cannot address a project.
  [[ "$number" =~ ^[1-9][0-9]*$ ]] || fail "could not determine the number \
of project '$title' owned by '$owner'. Inspect 'gh project list --owner \
$owner --closed'. Some orgs/enterprises silently refuse API project \
creation while the web UI works — in that case create (or rename) a \
board titled exactly '$title' in the web UI and re-run init; init will \
reuse it and complete the fields and the repository link"

  # Creating a field whose name is taken fails, so check before creating.
  local existing_fields field_name
  existing_fields="$(gh project field-list "$number" --owner "$owner" \
    --limit 100 --format json | jq -r '.fields[].name')"
  for field_name in "Start date" "Target date"; do
    if printf '%s\n' "$existing_fields" | grep -Fxq "$field_name"; then
      echo "Field '$field_name' already exists; skipping."
    else
      gh project field-create "$number" --owner "$owner" \
        --name "$field_name" --data-type DATE >/dev/null
      echo "Created DATE field '$field_name'."
    fi
  done

  # Single-select field distinguishing Epics from Tasks on the board.
  if printf '%s\n' "$existing_fields" | grep -Fxq "Kind"; then
    echo "Field 'Kind' already exists; skipping."
  else
    gh project field-create "$number" --owner "$owner" \
      --name "Kind" --data-type SINGLE_SELECT \
      --single-select-options "Epic,Task" >/dev/null
    echo "Created SINGLE_SELECT field 'Kind' (Epic, Task)."
  fi

  # Working views. `createProjectV2View` takes a name and a layout; its
  # `configuration` input carries only `visibleFieldIds`, so grouping and the
  # roadmap's date fields cannot be set through the API and stay manual.
  # Matched by name, so an adopter's own views are never renamed or removed.
  local project_id existing_views view_spec view_name view_layout
  project_id="$(gh project view "$number" --owner "$owner" --format json --jq '.id')"
  # shellcheck disable=SC2016  # $id is a GraphQL variable, not a shell expansion
  existing_views="$(gh api graphql -f query='
    query($id: ID!) {
      node(id: $id) { ... on ProjectV2 { views(first: 50) { nodes { name } } } }
    }' -f id="$project_id" --jq '.data.node.views.nodes[].name' 2>/dev/null || true)"

  for view_spec in "Roadmap:ROADMAP_LAYOUT" "Kanban:BOARD_LAYOUT" "Backlog:TABLE_LAYOUT"; do
    view_name="${view_spec%%:*}"
    view_layout="${view_spec##*:}"
    if printf '%s\n' "$existing_views" | grep -Fxq "$view_name"; then
      echo "View '$view_name' already exists; skipping."
      continue
    fi
    # A board still sets up without its views: Projects permissions vary by
    # account and organization, so a refusal here warns rather than aborts.
    # shellcheck disable=SC2016  # $p/$n/$l are GraphQL variables, not shell expansions
    if gh api graphql -f query='
      mutation($p: ID!, $n: String!, $l: ProjectV2ViewLayout!) {
        createProjectV2View(input: {projectId: $p, name: $n, layout: $l}) {
          projectV2View { id }
        }
      }' -f p="$project_id" -f n="$view_name" -f l="$view_layout" >/dev/null 2>&1; then
      echo "Created '$view_name' view ($view_layout)."
    else
      echo "warning: could not create the '$view_name' view; add it in the"
      echo "         project UI (New view -> ${view_layout%%_*} layout)."
    fi
  done

  # Safe to repeat: linking an already-linked repository succeeds silently.
  gh project link "$number" --owner "$owner" --repo "$REPO"
  echo "Linked project #$number to $REPO."
  echo "The board is owned by '$owner' (Projects v2 boards are always"
  echo "user/org-owned) and, via this link, is visible in the repository's"
  echo "Projects tab: https://github.com/$REPO/projects"

  local url
  url="$(gh project view "$number" --owner "$owner" --format json --jq '.url')"
  echo "Project number: $number"
  echo "Project URL:    $url"
  echo "Remaining manual step: open the Roadmap view and pick 'Start date' /"
  echo "'Target date' as its date fields, then set 'Group by' to 'Kind' to"
  echo "separate Epics from Tasks — the API creates views but cannot configure"
  echo "grouping or date fields."
}

cmd_add() {
  local owner="" project="" issue=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --owner)
        [[ -n "${2:-}" ]] || usage_error "--owner requires a login argument"
        owner="$2"; shift 2 ;;
      --project)
        [[ -n "${2:-}" ]] || usage_error "--project requires a project number"
        project="$2"; shift 2 ;;
      --issue)
        [[ -n "${2:-}" ]] || usage_error "--issue requires an issue number"
        issue="$2"; shift 2 ;;
      -R|--repo)
        [[ -n "${2:-}" ]] || usage_error "$1 requires an owner/repo argument"
        REPO="$2"; shift 2 ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        usage_error "unknown argument for add: $1" ;;
    esac
  done
  [[ -n "$project" && -n "$issue" ]] \
    || usage_error "add requires --project and --issue"

  local num_re='^[0-9]+$'
  [[ "$project" =~ $num_re ]] \
    || usage_error "--project must be a number, got: $project"
  [[ "$issue" =~ $num_re ]] \
    || usage_error "--issue must be a number, got: $issue"

  require_tools
  resolve_repo
  [[ -n "$owner" ]] || owner="$REPO_OWNER"

  load_project_issue "$project" "$owner" "$issue"
  ensure_project_item "$project" "$owner"
  echo "Added/reused issue #$issue ($REPO) on project #$project."
  apply_kind "$project" "$owner" "$issue"
}

cmd_dates() {
  local owner="" project="" issue="" start="" target=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --owner)
        [[ -n "${2:-}" ]] || usage_error "--owner requires a login argument"
        owner="$2"; shift 2 ;;
      --project)
        [[ -n "${2:-}" ]] || usage_error "--project requires a project number"
        project="$2"; shift 2 ;;
      --issue)
        [[ -n "${2:-}" ]] || usage_error "--issue requires an issue number"
        issue="$2"; shift 2 ;;
      --start)
        [[ -n "${2:-}" ]] || usage_error "--start requires a YYYY-MM-DD date"
        start="$2"; shift 2 ;;
      --target)
        [[ -n "${2:-}" ]] || usage_error "--target requires a YYYY-MM-DD date"
        target="$2"; shift 2 ;;
      -R|--repo)
        [[ -n "${2:-}" ]] || usage_error "$1 requires an owner/repo argument"
        REPO="$2"; shift 2 ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        usage_error "unknown argument for dates: $1" ;;
    esac
  done
  [[ -n "$project" && -n "$issue" && -n "$start" && -n "$target" ]] \
    || usage_error "dates requires --project, --issue, --start and --target"

  # Patterns live in variables: quoted regexes break on bash 3.2.
  local num_re='^[0-9]+$' date_re='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  [[ "$project" =~ $num_re ]] || usage_error "--project must be a number, got: $project"
  [[ "$issue" =~ $num_re ]] || usage_error "--issue must be a number, got: $issue"
  [[ "$start" =~ $date_re ]] || usage_error "--start must be YYYY-MM-DD, got: $start"
  [[ "$target" =~ $date_re ]] || usage_error "--target must be YYYY-MM-DD, got: $target"
  # ISO dates order correctly as strings, so [[ < ]] compares dates.
  if [[ "$target" < "$start" ]]; then
    usage_error "--target ($target) is earlier than --start ($start)"
  fi

  require_tools
  resolve_repo
  [[ -n "$owner" ]] || owner="$REPO_OWNER"

  local start_field_id target_field_id
  load_project_issue "$project" "$owner" "$issue"
  start_field_id="$(field_id "$project" "$owner" "Start date")"
  target_field_id="$(field_id "$project" "$owner" "Target date")"
  [[ -n "$start_field_id" && -n "$target_field_id" ]] \
    || fail "project #$project has no 'Start date'/'Target date' fields — run 'bash .github/scripts/setup-project.sh init' first"

  ensure_project_item "$project" "$owner"

  gh project item-edit --id "$PROJECT_ITEM_ID" --project-id "$PROJECT_NODE_ID" \
    --field-id "$start_field_id" --date "$start" >/dev/null
  gh project item-edit --id "$PROJECT_ITEM_ID" --project-id "$PROJECT_NODE_ID" \
    --field-id "$target_field_id" --date "$target" >/dev/null

  echo "Scheduled issue #$issue ($REPO) on project #$project:" \
    "Start date $start, Target date $target."

  apply_kind "$project" "$owner" "$issue"
}

# Reader failures never enter the existing setup actuators. Suppress raw API
# diagnostics, which can contain private board data, and retain at most one
# bounded page. No retries, pagination auto-following or gh --jq projections.
readback_error() { echo "error: Project readback is uncheckable: $*" >&2; exit 3; }

RB_REPLY=""
# Shared validation for observed dates and offline comparison expectations.
# shellcheck disable=SC2016
PROJECT_DATE_JQ='def date: type == "string" and test("^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
  and (split("-") | map(tonumber) | .[0] as $year | .[1] as $month | .[2] as $day
    | (if ($year % 400 == 0 or ($year % 4 == 0 and $year % 100 != 0)) then 29 else 28 end) as $feb
    | $year >= 1 and $day <= [31,$feb,31,30,31,30,31,31,30,31,30,31][$month - 1]);'

readback_query() {
  RB_REPLY="$(gh api graphql "$@" 2>/dev/null | head -c 1048577 | jq -Rsc '
    if utf8bytelength > 1048576 or index("\u0000") != null then error("size/bytes")
    else fromjson end
    | if type == "object" and ((has("errors") | not) or .errors == [])
         and (.data | type == "object") then . else error("response") end' 2>/dev/null)" \
    || readback_error "transport, size, JSON or GraphQL error"
}

# $variables inside the single-quoted query/validators belong to GraphQL/jq.
# shellcheck disable=SC2016
cmd_readback() {
  local project="" issue="" owner="" project_id query common data anchor="" candidate=""
  local cursor="" cursors='[]' all='[]' page=0 total="" connection count more next observed result
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --project|--issue|--owner|-R|--repo)
        [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || usage_error "missing value for $1"
        case "$1" in
          --project) project="$2" ;; --issue) issue="$2" ;;
          --owner) owner="$2" ;; -R|--repo) REPO="$2" ;;
        esac
        shift 2 ;;
      -h|--help) usage; return 0 ;;
      *) usage_error "unknown readback option: $1" ;;
    esac
  done
  [[ "$project" =~ ^[1-9][0-9]{0,8}$ && "$issue" =~ ^[1-9][0-9]{0,8}$ ]] \
    || usage_error "readback requires positive --project and --issue numbers"
  require_tools
  resolve_repo
  owner="${owner:-$REPO_OWNER}"
  [[ "$REPO_OWNER" =~ ^[A-Za-z0-9-]+$ && "$REPO_NAME" =~ ^[A-Za-z0-9_.-]+$ \
     && "$owner" =~ ^[A-Za-z0-9-]+$ ]] || usage_error "invalid repository or owner"
  project_id="$(gh project view "$project" --owner "$owner" --format json --jq '.id' 2>/dev/null | head -c 513)" \
    || readback_error "cannot resolve Project"
  [[ ${#project_id} -le 512 && "$project_id" =~ ^[A-Za-z0-9_=-]+$ ]] || readback_error "invalid Project identity"

  common="$PROJECT_DATE_JQ"'def text: type == "string" and length > 0 and length <= 512 and (test("[\u0000-\u001f\u007f]") | not);
    def number: type == "number" and . > 0 and floor == .;
    def issue: .__typename == "Issue" and (.id | text) and (.number | number)
      and (.url | text) and (.repository.nameWithOwner | text);
    def connection: type == "object" and (.nodes | type == "array" and length <= 100)
      and (.totalCount | type == "number" and floor == . and . >= 0 and . <= 1000)
      and (.pageInfo | type == "object" and (.hasNextPage | type == "boolean")
        and has("endCursor") and (if .hasNextPage then (.endCursor | text)
          else (.endCursor == null or (.endCursor | text)) end));'
  query='query ProjectReadbackItems($id: ID!, $repoOwner: String!, $repoName: String!, $issue: Int!, $after: String) {
    repository(owner: $repoOwner, name: $repoName) { nameWithOwner issue(number: $issue) {
      __typename id number url repository { nameWithOwner } } }
    node(id: $id) { __typename ... on ProjectV2 { id number url
      owner { __typename ... on User { login } ... on Organization { login } }
      items(first: 100, after: $after) { totalCount pageInfo { hasNextPage endCursor }
        nodes { id updatedAt content { __typename ... on Issue { id number url repository { nameWithOwner } }
          ... on DraftIssue { id } ... on PullRequest { id } } } } } } }'
  while :; do
    page=$((page + 1)); [[ "$page" -le 10 ]] || readback_error "item page limit"
    if [[ -z "$cursor" ]]; then
      readback_query -f "query=$query" -f "id=$project_id" -f "repoOwner=$REPO_OWNER" -f "repoName=$REPO_NAME" -F "issue=$issue"
    else
      readback_query -f "query=$query" -f "id=$project_id" -f "repoOwner=$REPO_OWNER" -f "repoName=$REPO_NAME" -F "issue=$issue" -f "after=$cursor"
    fi
    data="$(jq -ce --arg id "$project_id" --arg owner "$owner" --arg repo "$REPO" \
      --argjson project "$project" --argjson issue "$issue" "$common"'
      .data | select(.repository.nameWithOwner == $repo and (.repository.issue | issue)
        and .repository.issue.number == $issue and .repository.issue.repository.nameWithOwner == $repo
        and .node.__typename == "ProjectV2" and .node.id == $id and .node.number == $project
        and (.node.url | text) and (.node.owner.__typename == "User" or .node.owner.__typename == "Organization")
        and .node.owner.login == $owner and (.node.items | connection)
        and all(.node.items.nodes[]; (.id | text) and (.updatedAt | text) and
          (.content | type == "object" and
            (if .__typename == "Issue" then issue
             elif .__typename == "DraftIssue" or .__typename == "PullRequest" then (.id | text)
             else false end))))' <<<"$RB_REPLY" 2>/dev/null)" || readback_error "Project, Issue or item identity"
    observed="$(jq -c '{project: (.node | {id,number,url,owner:.owner.login}), repository:.repository.nameWithOwner,
      issue:(.repository.issue | {id,number,url})}' <<<"$data")"
    [[ -z "$anchor" || "$anchor" == "$observed" ]] || readback_error "identity changed between pages"
    anchor="$observed"
    connection="$(jq -c '.node.items' <<<"$data")"
    count="$(jq -r '.totalCount' <<<"$connection")"
    [[ -z "$total" || "$total" == "$count" ]] || readback_error "item count changed"
    total="$count"
    all="$(jq -cn --argjson old "$all" --argjson new "$connection" '$old + $new.nodes')"
    jq -e --argjson total "$total" 'length <= $total and ([.[].id] | length == (unique | length))' <<<"$all" >/dev/null \
      || readback_error "duplicate or excessive items"
    more="$(jq -r '.pageInfo.hasNextPage' <<<"$connection")"
    if [[ "$more" == false ]]; then
      [[ "$(jq length <<<"$all")" == "$total" ]] || readback_error "incomplete item enumeration"
      break
    fi
    next="$(jq -r '.pageInfo.endCursor' <<<"$connection")"
    [[ "$(jq '.nodes | length' <<<"$connection")" -gt 0 && "$(jq length <<<"$all")" -lt "$total" ]] \
      || readback_error "inconsistent item pagination"
    jq -e --arg next "$next" 'index($next) == null' <<<"$cursors" >/dev/null || readback_error "item cursor repeated"
    cursors="$(jq -c --arg next "$next" '. + [$next]' <<<"$cursors")"; cursor="$next"
  done
  # An Issue number alone is not an identity. Check every matching ID against
  # the resolved repository, number and URL before selecting exactly one item.
  candidate="$(jq -c --argjson anchor "$anchor" '[.[] | select(.content.__typename == "Issue" and
    (.content.id == $anchor.issue.id or (.content.number == $anchor.issue.number and
      .content.repository.nameWithOwner == $anchor.repository)))]' <<<"$all")"
  count="$(jq length <<<"$candidate")"
  if [[ "$count" == 0 ]]; then
    jq -c '. + {schema:"project-field-readback/v1",state:"missing",item_id:null,
      fields:{"Kind":null,"Start date":null,"Target date":null},missing:["item"]}' <<<"$anchor"
    return 1
  fi
  [[ "$count" == 1 ]] || readback_error "duplicate Issue items"
  jq -e --argjson anchor "$anchor" '.[0].content | .id == $anchor.issue.id and .number == $anchor.issue.number
    and .url == $anchor.issue.url and .repository.nameWithOwner == $anchor.repository' <<<"$candidate" >/dev/null \
    || readback_error "mismatched Issue item"
  candidate="$(jq -c '.[0]' <<<"$candidate")"
  local item_id updated_at
  item_id="$(jq -r '.id' <<<"$candidate")"; updated_at="$(jq -r '.updatedAt' <<<"$candidate")"
  query='query ProjectReadbackValues($id: ID!, $after: String) {
    node(id: $id) { __typename ... on ProjectV2Item { id updatedAt project { id }
      content { __typename ... on Issue { id number url repository { nameWithOwner } } }
      fieldValues(first: 100, after: $after) { totalCount pageInfo { hasNextPage endCursor }
        nodes { __typename
          ... on ProjectV2ItemFieldValueCommon { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldLabelValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldMilestoneValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldPullRequestValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldRepositoryValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldReviewerValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldUserValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemIssueFieldValue { field { ... on ProjectV2FieldCommon { id name dataType } } }
          ... on ProjectV2ItemFieldSingleSelectValue { name }
          ... on ProjectV2ItemFieldDateValue { date }
        } } } } }'
  all='[]'; cursor=""; cursors='[]'; page=0; total=""
  while :; do
    page=$((page + 1)); [[ "$page" -le 10 ]] || readback_error "field page limit"
    if [[ -z "$cursor" ]]; then
      readback_query -f "query=$query" -f "id=$item_id"
    else
      readback_query -f "query=$query" -f "id=$item_id" -f "after=$cursor"
    fi
    connection="$(jq -ce --arg id "$item_id" --arg updated "$updated_at" --argjson anchor "$anchor" "$common"'
      .data.node | select(.__typename == "ProjectV2Item" and .id == $id and .updatedAt == $updated
        and .project.id == $anchor.project.id and (.content | issue) and .content.id == $anchor.issue.id
        and .content.number == $anchor.issue.number and .content.url == $anchor.issue.url
        and .content.repository.nameWithOwner == $anchor.repository)
      | .fieldValues | select(connection and all(.nodes[]; (.__typename | text) and (.field.id | text)
        and (.field.name | text) and (.field.dataType | text)
        and (if .field.name == "Kind" then .__typename == "ProjectV2ItemFieldSingleSelectValue"
          and .field.dataType == "SINGLE_SELECT" and (.name | text)
        elif .field.name == "Start date" or .field.name == "Target date" then
          .__typename == "ProjectV2ItemFieldDateValue" and .field.dataType == "DATE"
          and (.date | date)
        else true end)))' <<<"$RB_REPLY" 2>/dev/null)" || readback_error "field metadata, value or item changed"
    count="$(jq -r '.totalCount' <<<"$connection")"
    [[ -z "$total" || "$total" == "$count" ]] || readback_error "field count changed"
    total="$count"
    # Retain only allowlisted metadata/values after validation, not unrelated
    # Project field content. Both connections are bounded independently.
    all="$(jq -cn --argjson old "$all" --argjson new "$connection" '$old + [$new.nodes[] |
      {id:.field.id,name:.field.name,type:.field.dataType,value:(if .field.name == "Kind" then .name
        elif .field.name == "Start date" or .field.name == "Target date" then .date else null end)}]')"
    jq -e --argjson total "$total" 'length <= $total and ([.[].id] | length == (unique | length))
      and ([.[] | select(.name == "Kind" or .name == "Start date" or .name == "Target date") | .name]
        | length == (unique | length))' <<<"$all" >/dev/null || readback_error "duplicate or excessive fields"
    more="$(jq -r '.pageInfo.hasNextPage' <<<"$connection")"
    if [[ "$more" == false ]]; then
      [[ "$(jq length <<<"$all")" == "$total" ]] || readback_error "incomplete field enumeration"
      break
    fi
    next="$(jq -r '.pageInfo.endCursor' <<<"$connection")"
    [[ "$(jq '.nodes | length' <<<"$connection")" -gt 0 && "$(jq length <<<"$all")" -lt "$total" ]] \
      || readback_error "inconsistent field pagination"
    jq -e --arg next "$next" 'index($next) == null' <<<"$cursors" >/dev/null || readback_error "field cursor repeated"
    cursors="$(jq -c --arg next "$next" '. + [$next]' <<<"$cursors")"; cursor="$next"
  done
  result="$(jq -cn --argjson anchor "$anchor" --arg id "$item_id" --argjson values "$all" '
    ["Kind","Start date","Target date"] as $names | $anchor + {schema:"project-field-readback/v1",item_id:$id,
      fields:($names | map(. as $name | {key:$name,value:([$values[] | select(.name == $name) |
        {field_id:.id,type,value}] | first // null)}) | from_entries),
      missing:[$names[] as $name | select(all($values[]; .name != $name)) | $name]}
    | . + {state:(if .missing == [] then "observed" else "missing" end)}')"
  printf '%s\n' "$result"
  jq -e '.missing == []' <<<"$result" >/dev/null
}

# Comparison is separate from observation and authority. A fresh Bash process
# keeps readback's errexit/pipefail behavior even though its status is captured.
# There is exactly one acquisition, and no exception or repair bypass.
# shellcheck disable=SC2016
cmd_verify() {
  local kind="" start="" target="" expected observation result status=0
  local read_args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --expect-kind|--expect-start|--expect-target|--project|--issue|--owner|-R|--repo)
        [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || usage_error "missing value for $1"
        case "$1" in
          --expect-kind) [[ -z "$kind" ]] || usage_error "duplicate --expect-kind"; kind="$2" ;;
          --expect-start) [[ -z "$start" ]] || usage_error "duplicate --expect-start"; start="$2" ;;
          --expect-target) [[ -z "$target" ]] || usage_error "duplicate --expect-target"; target="$2" ;;
          *) read_args+=("$1" "$2") ;;
        esac
        shift 2 ;;
      -h|--help) usage; return 0 ;;
      *) usage_error "unknown verify option: $1" ;;
    esac
  done
  [[ "$kind" == Task || "$kind" == Epic ]] || usage_error "--expect-kind must be Task or Epic"
  [[ ${#read_args[@]} -gt 0 ]] || usage_error "verify requires --project and --issue"
  command -v jq >/dev/null 2>&1 || readback_error "jq CLI not found"
  jq -ne --arg start "$start" --arg target "$target" "$PROJECT_DATE_JQ"'
    ($start | date) and ($target | date) and $start <= $target' >/dev/null 2>&1 \
    || usage_error "expected dates must be real YYYY-MM-DD dates with start <= target"
  expected="$(jq -cn --arg kind "$kind" --arg start "$start" --arg target "$target" \
    '{"Kind":$kind,"Start date":$start,"Target date":$target}')"
  observation="$(bash "$0" readback "${read_args[@]}")" || status=$?
  [[ "$status" != 2 ]] || return 2
  if [[ "$status" == 0 || "$status" == 1 ]]; then
    result="$(jq -ce --argjson expected "$expected" --argjson status "$status" '
      select(.schema == "project-field-readback/v1" and
        (($status == 0 and .state == "observed" and .missing == []) or
         ($status == 1 and .state == "missing" and (.missing | length > 0))))
      | . as $observation | {schema:"project-field-verification/v1",expected:$expected,observation:$observation,
          differences:["Kind","Start date","Target date"] | map(. as $name |
            select($observation.fields[$name] == null or $observation.fields[$name].value != $expected[$name]))}
      | . + {state:(if .observation.state == "missing" then "missing"
          elif .differences == [] then "match" else "mismatch" end)}' <<<"$observation" 2>/dev/null)" || result=""
    if [[ -n "$result" ]]; then
      printf '%s\n' "$result"
      jq -e '.state == "match"' <<<"$result" >/dev/null
      return
    fi
  fi
  jq -cn --argjson expected "$expected" '{schema:"project-field-verification/v1",state:"uncheckable",
    expected:$expected,observation:null,differences:null}'
  return 3
}

case "${1:-}" in
  init)      shift; cmd_init "$@" ;;
  add)       shift; cmd_add "$@" ;;
  dates)     shift; cmd_dates "$@" ;;
  readback)  shift; cmd_readback "$@" ;;
  verify)    shift; cmd_verify "$@" ;;
  -h|--help) usage; exit 0 ;;
  "")        usage_error "missing subcommand (init, add, dates, readback or verify)" ;;
  *)         usage_error "unknown subcommand: $1" ;;
esac
