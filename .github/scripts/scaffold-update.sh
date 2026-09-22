#!/usr/bin/env bash
# Explicit network update, adapted from the reviewed 2a016af public bootstrap.
# Selected source code never dispatches this wrapper; only the fixed engine runs.
set -euo pipefail
export LC_ALL=C GIT_OPTIONAL_LOCKS=0
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }
usage() {
  printf '%s\n' 'Usage: scaffold-update.sh --from SHA --to SHA --recovery DIR [--dry-run | --apply] [TARGET]' \
    'Both SHAs must be full lowercase 40-character commit IDs; TARGET defaults to cwd.' \
    'Default --dry-run leaves the target, index and requested recovery directory unchanged.' \
    '--apply retains old/new source roots and transaction under a fresh private DIR outside TARGET.' \
    'SCAFFOLD_REPO: public owner/name, default mochan-tk/agentic-dev-kit-for-codex.' \
    'No automatic version detection, staging, commit, push or GitHub configuration.'
}
FROM=""; TO=""; RECOVERY=""; TARGET=.; TARGET_SET=0; MODE=dry-run; MODE_SET=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --from|--to|--recovery)
      option="$1"; shift; [ "$#" -gt 0 ] && [ -n "$1" ] || { usage >&2; exit 2; }
      case "$option" in
        --from) [ -z "$FROM" ] || exit 2; FROM="$1" ;;
        --to) [ -z "$TO" ] || exit 2; TO="$1" ;;
        --recovery) [ -z "$RECOVERY" ] || exit 2; RECOVERY="$1" ;;
      esac ;;
    --dry-run|--apply) [ "$MODE_SET" -eq 0 ] || exit 2; MODE="${1#--}"; MODE_SET=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ "$TARGET_SET" -eq 0 ] && [ -n "$1" ] || exit 2; TARGET="$1"; TARGET_SET=1 ;;
  esac
  shift
done
[[ "$FROM" =~ ^[0-9a-f]{40}$ ]] && [[ "$TO" =~ ^[0-9a-f]{40}$ ]] && [ -n "$RECOVERY" ] || { usage >&2; exit 2; }
[ -z "${SCAFFOLD_SOURCE_DIR+x}" ] || fail 'local source override is not supported by network update'
for var in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_NAMESPACE GIT_SHALLOW_FILE GIT_REPLACE_REF_BASE GIT_SSL_CERT GIT_SSL_KEY GIT_SSL_NO_VERIFY GIT_SSL_CAINFO GIT_SSL_CAPATH GIT_PROXY_COMMAND NETRC; do
  [ -z "${!var+x}" ] || fail 'Git context override is not supported by network update'
done
command -v git >/dev/null || fail 'Git is required'
if command -v sha256sum >/dev/null 2>&1; then digest() { sha256sum | cut -d ' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then digest() { shasum -a 256 | cut -d ' ' -f1; }
else fail 'sha256sum or shasum is required'; fi
absolute() {
  local converted
  case "$1" in *$'\n'*|*$'\r'*|*$'\t'*) fail 'control characters in root argument' ;; esac
  case "$1" in
    [A-Za-z]:/*|[A-Za-z]:\\*)
      command -v cygpath >/dev/null 2>&1 || fail 'Windows drive paths require Git Bash cygpath'
      converted="$(cygpath -u -- "$1")" || fail 'Windows drive path conversion failed'
      case "$converted" in /*) printf '%s\n' "$converted" ;; *) fail 'Windows drive path did not resolve to an absolute Git Bash path' ;; esac ;;
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd -P)" "$1" ;;
  esac
}
no_links() {
  local path="$1"
  while :; do
    [ ! -L "$path" ] || fail 'root or ancestor is a symlink'
    [ "$path" = / ] && break
    path="${path%/*}"; [ -n "$path" ] || path=/
  done
}
disjoint() {
  case "$1/" in "$2/"*) fail 'target, recovery and scratch paths overlap' ;; esac
  case "$2/" in "$1/"*) fail 'target, recovery and scratch paths overlap' ;; esac
}
TARGET="$(absolute "$TARGET")"; no_links "$TARGET"
[ -d "$TARGET" ] || fail 'target must be an existing Git repository root'
TARGET="$(cd "$TARGET" && pwd -P)"
git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || fail 'target is not a Git repository'
prefix="$(git -c core.fsmonitor=false -C "$TARGET" rev-parse --show-prefix)" || fail 'target Git root is uncheckable'
[ -z "$prefix" ] || fail 'target must be the Git repository root'
RECOVERY="$(absolute "$RECOVERY")"; no_links "$RECOVERY"
case "$RECOVERY" in */|*/.|*/..) fail 'recovery directory must have a new leaf name' ;; esac
[ ! -e "$RECOVERY" ] || fail 'recovery directory must be exclusively new'
parent="$(dirname "$RECOVERY")"
[ -d "$parent" ] || fail 'recovery parent must already exist'
RECOVERY="$(cd "$parent" && pwd -P)/$(basename "$RECOVERY")"
disjoint "$RECOVERY" "$TARGET"
REPO="${SCAFFOLD_REPO:-mochan-tk/agentic-dev-kit-for-codex}"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail 'invalid public source repository'
# Never use adopter-owned scratch. OS aliases are resolved only for scratch.
if [ "$MODE" = dry-run ]; then
  scratch_parent="$(absolute "${TMPDIR:-/tmp}")"
  [ -d "$scratch_parent" ] || fail 'scratch parent must exist'
  scratch_parent="$(cd "$scratch_parent" && pwd -P)"
  case "$scratch_parent/" in "$TARGET/"*|"$RECOVERY/"*) fail 'scratch parent overlaps target or recovery' ;; esac
  WORK="$(mktemp -d "$scratch_parent/scaffold-update.XXXXXX")"
  trap 'rm -rf -- "$WORK"' EXIT
  WORK="$(cd "$WORK" && pwd -P)"
else
  (umask 077; mkdir "$RECOVERY") || fail 'exclusive recovery directory creation failed'
  WORK="$RECOVERY"
  # Keep final source root identities, including after any failure.
  trap 'printf "%s\n" "Recovery inputs retained at: $WORK" >&2' EXIT
fi
chmod 700 "$WORK"
mkdir "$WORK/transport-home"
public_git() {
  # Scope an empty home to transport children so Git cannot consume caller .netrc.
  env HOME="$WORK/transport-home" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    git -c credential.helper= -c core.hooksPath=/dev/null -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 "$@"
}
public_git init --bare --template= -q "$WORK/objects.git" || fail 'private Git object store creation failed'
object_git() { public_git --git-dir="$WORK/objects.git" "$@"; }
project() {
  local path="$1" row mode type blob actual size
  row="$(object_git ls-tree "$PIN" -- "$path")" || fail 'source tree lookup failed'
  IFS=$' \t' read -r mode type blob actual <<< "$row"
  [ "$mode" = 100644 ] && [ "$type" = blob ] && [ "$actual" = "$path" ] && [[ "$blob" =~ ^[0-9a-f]{40}$ ]] || fail 'selected source path is missing or not a regular blob'
  size="$(object_git cat-file -s "$blob")" || fail 'source blob size unavailable'
  [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le 1048576 ] || fail 'source blob exceeds size bound'
  mkdir -p "$SOURCE/$(dirname "$path")"
  object_git cat-file blob "$blob" > "$SOURCE/$path" || fail 'source blob read failed'
  [ "$(object_git hash-object --no-filters "$SOURCE/$path")" = "$blob" ] || fail 'projected source blob hash mismatch'
  chmod 644 "$SOURCE/$path"
}
acquire() {
  local PIN="$1" SOURCE="$2" role="$3" manifest name class hash extra layout expected actual count engine_hash
  printf 'Acquiring %s source-commit=%s\n' "$REPO" "$PIN"
  object_git fetch --no-tags --depth=1 "https://github.com/$REPO" "$PIN" || fail 'pinned source fetch failed'
  [ "$(object_git rev-parse --verify 'FETCH_HEAD^{commit}')" = "$PIN" ] || fail 'fetched commit differs from requested commit'
  object_git fsck --strict --no-reflogs >/dev/null 2>&1 || fail 'source Git objects are corrupt or incomplete'
  mkdir "$SOURCE"
  project .github/distribution/payload.v1.tsv
  manifest="$SOURCE/.github/distribution/payload.v1.tsv"
  layout=""; expected=""; count=0
  while IFS=$'\t' read -r name class hash extra || [ -n "${name:-}" ]; do
    case "$name" in ''|'#'*) continue ;; esac
    [[ "$name" =~ ^[A-Za-z0-9._/-]+$ ]] && [[ "$hash" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || fail 'invalid payload inventory'
    case "$name" in /*|*/|*//*|.|..|./*|../*|*/./*|*/../*|*/.|*/..|.git|.git/*) fail 'unsafe payload path' ;; esac
    case "$class" in engine|tuned|instance|seed) ;; *) fail 'invalid preservation class' ;; esac
    count=$((count + 1)); layout+="$name"$'\t'"$class"$'\n'; expected+=".github/distribution/payload/$name"$'\n'
  done < "$manifest"
  [ "$count" -eq 47 ] && [ "$(printf '%s' "$layout" | digest)" = 763ea43ca7f79b9774867e012ec92f742bc2cbb382f8fe46736f18cf945fc987 ] || fail 'unreviewed payload layout'
  actual="$(object_git ls-tree -r --name-only "$PIN" -- .github/distribution/payload/)" || fail 'payload enumeration failed'
  [ "$actual" = "${expected%$'\n'}" ] || fail 'unexpected or missing payload entries'
  while IFS=$'\t' read -r name class hash extra || [ -n "${name:-}" ]; do
    case "$name" in ''|'#'*) continue ;; esac
    project ".github/distribution/payload/$name"
    [ "$(digest < "$SOURCE/.github/distribution/payload/$name")" = "$hash" ] || fail 'payload digest mismatch'
  done < "$manifest"
  project .github/scripts/scaffold-install.sh
  engine_hash="$(digest < "$SOURCE/.github/scripts/scaffold-install.sh")"
  case "$role:$engine_hash" in
    from:3c582e519c91a85641f672379f1513126ec209e7ce11c8ed1b3c20aa550f12b2) ;; # Historical data only; never executed.
    from:3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284|to:3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284) ;;
    *) fail 'unreviewed engine bytes for selected source role' ;;
  esac
}
acquire "$FROM" "$WORK/old" from
acquire "$TO" "$WORK/new" to
printf 'Selected update from=%s to=%s mode=%s\n' "$FROM" "$TO" "$MODE"
SCAFFOLD_SOURCE_DIR="$WORK/new" bash "$WORK/new/.github/scripts/scaffold-install.sh" \
  --upgrade --old-source "$WORK/old" --transaction "$WORK/transaction" "--$MODE" "$TARGET"
