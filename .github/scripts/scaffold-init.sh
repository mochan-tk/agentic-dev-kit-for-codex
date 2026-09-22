#!/usr/bin/env bash
# Source-derived public bootstrap; frozen Copilot source fd265ddef150fab86cd54d0e383c2c25fe297ffb.
# Git object projection replaces tar/checkout; only the reviewed current engine runs.
set -euo pipefail
export LC_ALL=C GIT_OPTIONAL_LOCKS=0
SELECTED=0; OWNED_WORK=""; GUIDANCE_SHOWN=0
failure_guidance() {
  if [ "$BASH_SUBSHELL" -eq 0 ] && [ "$GUIDANCE_SHOWN" -eq 0 ] && [ "$SELECTED" -eq 0 ] && [ "${SCAFFOLD_FAILURE_GUIDANCE_OWNER:-}" != powershell ]; then
    GUIDANCE_SHOWN=1
    printf '%s\n' 'Optional public feedback (review privacy before sharing):' \
      'https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/new?template=feedback.yml' \
      'https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/docs/distribution/feedback.md' >&2 || :
  fi
}
finish() {
  status=$?
  trap - EXIT
  if [ -n "$OWNED_WORK" ]; then rm -rf -- "$OWNED_WORK" || :; fi
  if [ "$status" -ne 0 ]; then failure_guidance; fi
  builtin exit "$status"
}
trap finish EXIT
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }
usage() {
  printf '%s\n' 'Usage: scaffold-init.sh [--dry-run | --apply] [target-directory]' \
    'External saved/piped entry: fetch SCAFFOLD_REF (default main), apply and stage new files.' \
    'Local checkout or explicit SCAFFOLD_SOURCE_DIR: default dry-run, never stage.' \
    'SCAFFOLD_REPO: public owner/name, default mochan-tk/agentic-dev-kit-for-codex.' \
    'SCAFFOLD_REF: branch, tag, or full 40-character commit SHA.' \
    'Local known-old update: --upgrade --old-source DIR --transaction DIR [--dry-run | --apply] TARGET' \
    'Local rollback: --rollback --transaction DIR [--dry-run | --apply] TARGET' \
    'No force, Git init, commit or push. Review adoption before onboarding.'
}
ENTRY="${BASH_SOURCE[0]:-}"
if [ "${1:-}" = --_selected ]; then
  [ "$#" -ge 3 ] || fail 'invalid selected dispatch'
  PIN="$2"; WORK="$3"; shift 3
  [[ "$PIN" =~ ^[0-9a-f]{40}$ ]] && [ "$ENTRY" = "$WORK/src/.github/scripts/scaffold-init.sh" ] && [ -d "$WORK/objects.git" ] || fail 'invalid selected dispatch binding'
  SELECTED=1
fi
if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then usage; exit 0; fi
# Preserve the local engine's drive-path conversion boundary before PATH-dependent helpers.
case "${SCAFFOLD_SOURCE_DIR:-}" in
  [A-Za-z]:/*|[A-Za-z]:\\*)
    command -v cygpath >/dev/null 2>&1 || fail 'Windows drive paths require Git Bash cygpath'
    converted="$(cygpath -u -- "$SCAFFOLD_SOURCE_DIR")" || fail 'Windows drive path conversion failed'
    case "$converted" in /*) export SCAFFOLD_SOURCE_DIR="$converted" ;; *) fail 'Windows drive path did not resolve to an absolute Git Bash path' ;; esac ;;
esac
if command -v sha256sum >/dev/null 2>&1; then digest() { sha256sum | cut -d ' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then digest() { shasum -a 256 | cut -d ' ' -f1; }
else fail 'sha256sum or shasum is required'; fi
if [ "$SELECTED" -eq 0 ]; then
  LOCAL=0
  if [ "${SCAFFOLD_SOURCE_DIR+x}" = x ]; then
    [ -n "$SCAFFOLD_SOURCE_DIR" ] && [ -d "$SCAFFOLD_SOURCE_DIR" ] || fail 'explicit local source is invalid'
    LOCAL=1
  elif [ -n "$ENTRY" ] && { [ -e "$(dirname "$ENTRY")/../distribution/payload.v1.tsv" ] || [ -e "$(dirname "$ENTRY")/scaffold-install.sh" ]; }; then LOCAL=1; fi
  if [ "$LOCAL" -eq 1 ]; then
    ENGINE=""
    if [ -n "$ENTRY" ]; then ENGINE="$(dirname "$ENTRY")/scaffold-install.sh"; fi
    if [ ! -f "$ENGINE" ] && [ "${SCAFFOLD_SOURCE_DIR+x}" = x ]; then
      ENGINE="$SCAFFOLD_SOURCE_DIR/.github/scripts/scaffold-install.sh"
    fi
    [ -f "$ENGINE" ] && [ ! -L "$ENGINE" ] || fail 'adjacent local engine is missing or unsafe'
    ancestor="$ENGINE"
    while [ "$ancestor" != / ]; do
      [ ! -L "$ancestor" ] || fail 'local engine ancestor is a symlink'
      case "$ancestor" in */*) ancestor="${ancestor%/*}"; [ -n "$ancestor" ] || ancestor=/ ;; *) break ;; esac
    done
    [ "$(digest < "$ENGINE")" = 3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284 ] || fail 'unreviewed local engine bytes'
    # Keep the engine in this PID so terminating the entry cannot leave a
    # child installing. The verified engine's BASH_SOURCE and stdin stay intact.
    # Its operation_finish EXIT trap retains cleanup and calls this exit last.
    # shellcheck disable=SC2329 # Invoked by the verified sourced engine and its EXIT cleanup.
    exit() {
      local code="${1:-$?}"
      if [ "$code" -ne 0 ]; then failure_guidance; fi
      builtin exit "$code"
    }
    # shellcheck disable=SC1090 # Exact hash verified above; covered by engine regression tests.
    source "$ENGINE" "$@"
    exit "$?"
  fi
fi
MODE=apply; MODE_SET=0; TARGET=.; TARGET_SET=0
for arg in "$@"; do
  case "$arg" in
    --apply|--dry-run) [ "$MODE_SET" -eq 0 ] || { usage >&2; exit 2; }; MODE="${arg#--}"; MODE_SET=1 ;;
    -*) usage >&2; exit 2 ;;
    *) [ "$TARGET_SET" -eq 0 ] && [ -n "$arg" ] || { usage >&2; exit 2; }; TARGET="$arg"; TARGET_SET=1 ;;
  esac
done
case "$TARGET" in
  [A-Za-z]:/*|[A-Za-z]:\\*)
    command -v cygpath >/dev/null 2>&1 || fail 'Windows drive paths require Git Bash cygpath'
    TARGET="$(cygpath -u -- "$TARGET")" || fail 'Windows drive path conversion failed'
    case "$TARGET" in /*) ;; *) fail 'Windows drive path did not resolve to an absolute Git Bash path' ;; esac ;;
esac
for var in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS; do
  [ -z "${!var+x}" ] || fail 'Git context override is not supported by external installation'
done
command -v git >/dev/null || fail 'Git is required'
if [ "$SELECTED" -eq 0 ]; then
  REPO="${SCAFFOLD_REPO:-mochan-tk/agentic-dev-kit-for-codex}"; REF="${SCAFFOLD_REF:-main}"
  [[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail 'invalid public source repository'
  git check-ref-format "refs/heads/$REF" >/dev/null 2>&1 || fail 'invalid source ref'
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/scaffold-bootstrap.XXXXXX")"
  OWNED_WORK="$WORK"
  # Resolve OS temporary-directory aliases only for this newly owned scratch.
  # Explicit local sources and adopter targets retain their no-symlink checks.
  PHYSICAL_WORK="$(cd "$WORK" && pwd -P)" || fail 'fresh scratch physical path is uncheckable'
  WORK="$PHYSICAL_WORK"
  OWNED_WORK="$WORK"
  # Acquisition excludes user credential helpers, rewrites, templates and hooks.
  public_git() {
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
      git -c credential.helper= -c core.hooksPath=/dev/null -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 "$@"
  }
  public_git init --bare --template= -q "$WORK/objects.git" || fail 'private Git object store creation failed'
  URL="https://github.com/$REPO"; PIN=""
  if [[ "$REF" =~ ^[0-9a-f]{40}$ ]]; then PIN="$REF"
  else
    for requested in "refs/heads/$REF" "refs/tags/$REF^{}" "refs/tags/$REF"; do
      response="$(public_git --git-dir="$WORK/objects.git" ls-remote "$URL" "$requested")" || fail 'source ref resolution failed'
      [ -n "$response" ] || continue
      IFS=$'\t' read -r PIN returned extra <<< "$response"
      [[ "$PIN" =~ ^[0-9a-f]{40}$ ]] && [ "$returned" = "$requested" ] && [ -z "$extra" ] && [ "$(printf '%s\n' "$response" | wc -l | tr -d ' ')" = 1 ] || fail 'ambiguous source ref response'
      break
    done
  fi
  [ -n "$PIN" ] || fail 'source ref could not be resolved'
  printf 'Acquiring %s source-commit=%s\n' "$REPO" "$PIN"
  public_git --git-dir="$WORK/objects.git" fetch --no-tags --depth=1 "$URL" "$PIN" || fail 'pinned source fetch failed'
  object_git() { public_git --git-dir="$WORK/objects.git" "$@"; }
  [ "$(object_git rev-parse --verify 'FETCH_HEAD^{commit}')" = "$PIN" ] || fail 'fetched commit differs from resolved commit'
  object_git fsck --strict --no-reflogs >/dev/null 2>&1 || fail 'source Git objects are corrupt or incomplete'
  mkdir "$WORK/src"
  project() {
    local path="$1" row mode type blob actual size
    row="$(object_git ls-tree "$PIN" -- "$path")" || fail 'source tree lookup failed'
    IFS=$' \t' read -r mode type blob actual <<< "$row"
    [ "$mode" = 100644 ] && [ "$type" = blob ] && [ "$actual" = "$path" ] && [[ "$blob" =~ ^[0-9a-f]{40}$ ]] || fail 'selected source path is missing or not a regular blob'
    size="$(object_git cat-file -s "$blob")" || fail 'source blob size unavailable'
    [ "$size" -le 1048576 ] || fail 'source blob exceeds size bound'
    mkdir -p "$WORK/src/$(dirname "$path")"
    object_git cat-file blob "$blob" > "$WORK/src/$path" || fail 'source blob read failed'
    [ "$(object_git hash-object --no-filters "$WORK/src/$path")" = "$blob" ] || fail 'projected source blob hash mismatch'
    chmod 644 "$WORK/src/$path"
  }
  project .github/distribution/payload.v1.tsv
  MANIFEST="$WORK/src/.github/distribution/payload.v1.tsv"
  NAMES=(); LAYOUT=""; EXPECTED=""
  while IFS=$'\t' read -r name class hash extra || [ -n "${name:-}" ]; do
    case "$name" in ''|'#'*) continue ;; esac
    [[ "$name" =~ ^[A-Za-z0-9._/-]+$ ]] && [[ "$hash" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || fail 'invalid payload inventory'
    case "$name" in /*|*/|*//*|.|..|./*|../*|*/./*|*/../*|*/.|*/..|.git|.git/*) fail 'unsafe payload path' ;; esac
    case "$class" in engine|tuned|instance|seed) ;; *) fail 'invalid preservation class' ;; esac
    NAMES+=("$name"); LAYOUT+="$name"$'\t'"$class"$'\n'; EXPECTED+=".github/distribution/payload/$name"$'\n'
  done < "$MANIFEST"
  [ "${#NAMES[@]}" -eq 47 ] && [ "$(printf '%s' "$LAYOUT" | digest)" = 763ea43ca7f79b9774867e012ec92f742bc2cbb382f8fe46736f18cf945fc987 ] || fail 'unreviewed payload layout'
  actual="$(object_git ls-tree -r --name-only "$PIN" -- .github/distribution/payload/)" || fail 'payload enumeration failed'
  [ "$actual" = "${EXPECTED%$'\n'}" ] || fail 'unexpected or missing payload entries'
  while IFS=$'\t' read -r name class hash extra || [ -n "${name:-}" ]; do
    case "$name" in ''|'#'*) continue ;; esac
    project ".github/distribution/payload/$name"
    [ "$(digest < "$WORK/src/.github/distribution/payload/$name")" = "$hash" ] || fail 'payload digest mismatch'
  done < "$MANIFEST"
  for path in .github/scripts/scaffold-init.sh .github/scripts/scaffold-init.ps1 .github/scripts/scaffold-install.sh; do project "$path"; done
  [ "$(digest < "$WORK/src/.github/scripts/scaffold-install.sh")" = 3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284 ] || fail 'unreviewed local engine bytes'
  # All selected objects, layout and hashes passed before selected code runs.
  bash "$WORK/src/.github/scripts/scaffold-init.sh" --_selected "$PIN" "$WORK" "$@"
  exit "$?"
fi
# The canonical selected revision owns planner dispatch and staging together.
SOURCE="$WORK/src"; ENGINE="$SOURCE/.github/scripts/scaffold-install.sh"
printf 'Selected source-commit=%s\n' "$PIN"
if [ "$MODE" = dry-run ]; then SCAFFOLD_SOURCE_DIR="$SOURCE" bash "$ENGINE" --dry-run "$TARGET"; exit "$?"; fi
PLAN="$(SCAFFOLD_SOURCE_DIR="$SOURCE" bash "$ENGINE" --dry-run "$TARGET")" || fail 'local engine preflight failed'
target_git() { git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C "$TARGET" "$@"; }
if [ ! -d "$TARGET" ] || ! target_git rev-parse --git-dir >/dev/null 2>&1; then fail 'apply requires an existing Git repository root'; fi
[ -z "$(target_git rev-parse --show-prefix)" ] || fail 'target must be the Git repository root'
INDEX="$(target_git rev-parse --git-path index)" || fail 'target index is uncheckable'
case "$INDEX" in /*|[A-Za-z]:/*) ;; *) INDEX="$TARGET/$INDEX" ;; esac
[ ! -L "$INDEX" ] && { [ ! -e "$INDEX" ] || [ -f "$INDEX" ]; } && [ ! -e "$INDEX.lock" ] && [ ! -L "$INDEX.lock" ] || fail 'target index is unsafe or locked'
CREATED=()
while IFS=$'\t' read -r action class name extra; do
  [ "$action" = install ] || continue
  [ -z "$extra" ] && [ -f "$SOURCE/.github/distribution/payload/$name" ] || fail 'unexpected engine plan'
  CREATED+=("$name")
done <<< "$PLAN"
if [ "${#CREATED[@]}" -eq 0 ]; then printf '%s\n' 'Already installed: no files or index entries changed.'; exit 0; fi
# Staged deletions need the HEAD comparison as well as index membership.
staged="$(target_git diff --cached --name-only -- "${CREATED[@]}")" || fail 'target staged state is uncheckable'
tracked="$(target_git ls-files -- "${CREATED[@]}")" || fail 'target tracked state is uncheckable'
[ -z "$staged" ] || fail 'planned new paths intersect pre-existing staged changes'
[ -z "$tracked" ] || fail 'planned new paths are already tracked'
ignored=0; target_git check-ignore -- "${CREATED[@]}" >/dev/null || ignored="$?"
[ "$ignored" -eq 1 ] || fail 'planned new paths are ignored or ignore state is uncheckable'
# Git may recheck racy existing entries during index writes and run their clean
# filters, even with --index-info. Mask configured drivers for this one command.
filter_status=0
target_git config --null --name-only --get-regexp '^filter\..*\.(clean|process|required)$' > "$WORK/filter-keys" || filter_status="$?"
[ "$filter_status" -le 1 ] || fail 'filter configuration is uncheckable'
FILTER_CONFIG=()
filter_count=0
while :; do
  key=""
  if ! IFS= read -r -d '' key; then
    [ -z "$key" ] || fail 'truncated filter configuration'
    break
  fi
  case "$key" in *$'\n'*|*$'\r'*|*$'\t'*) fail 'unsafe filter configuration key' ;; esac
  case "$key" in filter.*.clean|filter.*.process|filter.*.required) ;; *) fail 'unexpected filter configuration key' ;; esac
  filter_count=$((filter_count + 1))
  [ "$filter_count" -le 1024 ] || fail 'filter configuration exceeds bound'
  driver="${key%.*}"
  FILTER_CONFIG+=(-c "$driver.clean=" -c "$driver.process=" -c "$driver.required=false")
done < "$WORK/filter-keys"
if [ "$filter_status" -eq 1 ]; then
  [ "$filter_count" -eq 0 ] || fail 'contradictory filter configuration status'
else
  [ "$filter_count" -gt 0 ] || fail 'empty successful filter configuration'
fi
SCAFFOLD_SOURCE_DIR="$SOURCE" bash "$ENGINE" --apply "$TARGET" || fail 'installation failed; review partial files manually; nothing was staged by this wrapper'
# Raw-byte staging avoids clean filters and preserves unrelated index entries.
: > "$WORK/index-info"
for name in "${CREATED[@]}"; do
  cmp -s "$SOURCE/.github/distribution/payload/$name" "$TARGET/$name" || fail 'copied bytes changed; review partial installation manually'
  blob="$(target_git hash-object -w --no-filters "$name")" || fail 'staging failed; installed files remain for manual review'
  printf '100644 %s\t%s\n' "$blob" "$name" >> "$WORK/index-info"
done
target_git ${FILTER_CONFIG[@]+"${FILTER_CONFIG[@]}"} update-index --index-info < "$WORK/index-info" || fail 'staging failed; installed files remain; inspect the index and recover manually'
printf '%s newly installed files staged; nothing committed. source-commit=%s\n' "${#CREATED[@]}" "$PIN"
# shellcheck disable=SC2016 # Literal installed Skill invocation.
printf '%s\n' 'Review git diff --cached. Land adoption on the remote default branch before invoking $project-onboarding.'
