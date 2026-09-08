#!/usr/bin/env bash
# Source-derived local installer: Copilot scaffold-init.sh at fd265ddef150fab86cd54d0e383c2c25fe297ffb.
# Retains ordered planning, seed/tuned/instance preservation and collision refusal.
# Codex adaptation: a closed payload, local sources only, and explicit apply.
set -euo pipefail
export LC_ALL=C

usage() {
  printf '%s\n' 'Usage: scaffold-init.sh [--dry-run | --apply] [target-directory]' \
    'SCAFFOLD_SOURCE_DIR selects a local kit checkout; default is the adjacent checkout.' \
    'Default: dry-run. Apply requires an existing Git repository root.' \
    'No network, Git init/add/commit, overwrite, upgrade, model or GitHub operation.'
}
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }
MODE=dry-run
MODE_SET=0
DEST_ARG=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run|--apply)
      [ "$MODE_SET" -eq 0 ] || { usage >&2; exit 2; }
      MODE="${1#--}"; MODE_SET=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$DEST_ARG" ] || { usage >&2; exit 2; }; DEST_ARG="$1" ;;
  esac
  shift
done

# Check lexical ancestors before canonicalizing: cd -P alone hides root links.
no_links() {
  local p="$1"
  while :; do
    [ ! -L "$p" ] || return 1
    [ "$p" = / ] && break
    case "$p" in */*) p="${p%/*}"; [ -n "$p" ] || p=/ ;; *) break ;; esac
  done
}
absolute() {
  local converted
  case "$1" in
    [A-Za-z]:/*|[A-Za-z]:\\*)
      command -v cygpath >/dev/null 2>&1 || fail 'Windows drive paths require Git Bash cygpath'
      converted="$(cygpath -u -- "$1")" || fail 'Windows drive path conversion failed'
      case "$converted" in /*) printf '%s\n' "$converted" ;; *) fail 'Windows drive path did not resolve to an absolute Git Bash path' ;; esac ;;
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd -P)" "$1" ;;
  esac
}
SRC_INPUT="${SCAFFOLD_SOURCE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../..}"
SRC_INPUT="$(absolute "$SRC_INPUT")"
no_links "$SRC_INPUT" || fail 'source root or ancestor is a symlink'
[ -d "$SRC_INPUT" ] || fail 'source directory is missing'
SRC="$(cd "$SRC_INPUT" && pwd -P)"
DEST="$(absolute "${DEST_ARG:-.}")"
no_links "$DEST" || fail 'target root or ancestor is a symlink'
if [ -d "$DEST" ]; then DEST="$(cd "$DEST" && pwd -P)"; fi
case "$DEST/" in "$SRC/"*) fail 'target overlaps source checkout' ;; esac
case "$SRC/" in "$DEST/"*) fail 'source overlaps target checkout' ;; esac
[ ! -e "$DEST" ] || [ -d "$DEST" ] || fail 'target is not a directory'
if [ "$MODE" = apply ]; then
  [ -d "$DEST" ] || fail 'apply requires an existing Git repository root; initialize it explicitly first'
  git -C "$DEST" rev-parse --git-dir >/dev/null 2>&1 || fail 'target is not a Git repository'
  PREFIX="$(git -C "$DEST" rev-parse --show-prefix)" || fail 'target Git root is uncheckable'
  [ -z "$PREFIX" ] || fail 'target must be the Git repository root'
fi

PAYLOAD="$SRC/.github/distribution/payload"
MANIFEST="$SRC/.github/distribution/payload.v1.tsv"
if ! no_links "$MANIFEST" || ! no_links "$PAYLOAD"; then fail 'source inventory binding is a symlink'; fi
[ -f "$MANIFEST" ] && [ -d "$PAYLOAD" ] || fail 'local source lacks the reviewed payload inventory'
if command -v sha256sum >/dev/null 2>&1; then
  digest() { sha256sum "$1" | cut -d ' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
  digest() { shasum -a 256 "$1" | cut -d ' ' -f1; }
else
  fail 'sha256sum or shasum is required'
fi
safe_relative() {
  [[ "$1" =~ ^[A-Za-z0-9._/-]+$ ]] || return 1
  case "$1" in /*|*/|*//*|.|..|./*|../*|*/./*|*/../*|*/.|*/..|.git|.git/*) return 1 ;; esac
}
# The path/class digest is anchored in this reviewed executable, not supplied
# by a possibly modified local source. File digests can change only within it.
EXPECTED_LAYOUT_SHA256=763ea43ca7f79b9774867e012ec92f742bc2cbb382f8fe46736f18cf945fc987
NAMES=()
CLASSES=()
HASHES=()
ACTIONS=()
SEEN=$'\n'
COUNT=0
LAYOUT=""
while IFS=$'\t' read -r name class sha extra || [ -n "${name:-}" ]; do
  case "$name" in '#'*|'') continue ;; esac
  safe_relative "$name" || fail 'unsafe payload path'
  [[ "$sha" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || fail 'malformed payload inventory row'
  case "$class" in engine|tuned|instance|seed) ;; *) fail 'unknown preservation class' ;; esac
  folded="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
  case "$SEEN" in *$'\n'"$folded"$'\n'*) fail 'duplicate or case-colliding payload path' ;; esac
  SEEN+="$folded"$'\n'
  no_links "$PAYLOAD/$name" || fail 'source payload symlink'
  [ -f "$PAYLOAD/$name" ] || fail 'source payload is missing or not regular'
  [ "$(digest "$PAYLOAD/$name")" = "$sha" ] || fail 'source payload digest drift'
  no_links "$DEST/$name" || fail 'target payload path or ancestor is a symlink'
  parent="$(dirname "$DEST/$name")"
  while [ "$parent" != / ]; do
    [ ! -e "$parent" ] || [ -d "$parent" ] || fail 'target ancestor is not a directory'
    [ "$parent" = "$DEST" ] && break
    parent="${parent%/*}"; [ -n "$parent" ] || parent=/
  done
  action=install
  if [ -e "$DEST/$name" ]; then
    [ -f "$DEST/$name" ] || fail 'target file/directory collision'
    if cmp -s "$PAYLOAD/$name" "$DEST/$name"; then action=identical
    elif [ "$class" != engine ]; then action=preserve
    else fail "differing engine collision: $name"; fi
  fi
  NAMES+=("$name"); CLASSES+=("$class"); HASHES+=("$sha"); ACTIONS+=("$action")
  LAYOUT+="$name"$'\t'"$class"$'\n'
  COUNT=$((COUNT + 1))
done < "$MANIFEST"
[ "$COUNT" -eq 47 ] || fail 'expected exactly 47 reviewed payload files'
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_LAYOUT="$(printf '%s' "$LAYOUT" | sha256sum | cut -d ' ' -f1)"
else
  ACTUAL_LAYOUT="$(printf '%s' "$LAYOUT" | shasum -a 256 | cut -d ' ' -f1)"
fi
[ "$ACTUAL_LAYOUT" = "$EXPECTED_LAYOUT_SHA256" ] || fail 'unreviewed payload path/class layout'
# find never follows directory links. Extra files, special entries and links refuse.
# Capture status in the main shell: process substitution would hide find errors.
ACTUAL_ENTRIES="$(find "$PAYLOAD" -mindepth 1 ! -type d -print)" || fail 'payload enumeration failed'
ACTUAL=0
while IFS= read -r found; do
  relative="${found#"$PAYLOAD"/}"
  [ ! -L "$found" ] && [ -f "$found" ] || fail 'unexpected nonregular payload entry'
  folded="$(printf '%s' "$relative" | tr '[:upper:]' '[:lower:]')"
  case "$SEEN" in *$'\n'"$folded"$'\n'*) ;; *) fail 'unreviewed extra payload entry' ;; esac
  ACTUAL=$((ACTUAL + 1))
done <<< "$ACTUAL_ENTRIES"
[ "$ACTUAL" -eq "$COUNT" ] || fail 'payload inventory is incomplete'

PROVENANCE=unknown
if git -C "$SRC" rev-parse --verify HEAD >/dev/null 2>&1 && [ -z "$(git -C "$SRC" rev-parse --show-prefix)" ]; then
  dirty="$(git -C "$SRC" status --porcelain --untracked-files=all)" || fail 'source Git state is uncheckable'
  if [ -z "$dirty" ]; then PROVENANCE="$(git -C "$SRC" rev-parse HEAD)"; fi
fi
printf 'mode=%s source-commit=%s payload-files=%s\n' "$MODE" "$PROVENANCE" "$COUNT"
for ((i=0; i<COUNT; i++)); do printf '%s\t%s\t%s\n' "${ACTIONS[$i]}" "${CLASSES[$i]}" "${NAMES[$i]}"; done
if [ "$MODE" = dry-run ]; then printf '%s\n' 'No files or Git state were changed.'; exit 0; fi

# The adopter must keep this tree exclusively owned during apply. This is a
# bounded copy operation, not a concurrent filesystem transaction or upgrade.
# Never overwrite: noclobber protects a newly appeared regular destination.
for ((i=0; i<COUNT; i++)); do
  [ "${ACTIONS[$i]}" = install ] || continue
  name="${NAMES[$i]}"
  if ! no_links "$DEST/$name" || ! no_links "$PAYLOAD/$name"; then fail 'binding changed before copy; stop and review partial installation'; fi
  [ ! -e "$DEST/$name" ] || fail 'destination appeared before copy; stop and review partial installation'
  [ "$(digest "$PAYLOAD/$name")" = "${HASHES[$i]}" ] || fail 'source changed before copy'
  mkdir -p "$(dirname "$DEST/$name")"
  (set -o noclobber; cat "$PAYLOAD/$name" > "$DEST/$name") || fail 'copy failed; review partial installation'
  chmod 644 "$DEST/$name"
  [ "$(digest "$DEST/$name")" = "${HASHES[$i]}" ] || fail 'copied bytes differ; review partial installation'
done
# shellcheck disable=SC2016 # The dollar-prefixed Skill name is a literal Codex invocation.
printf '%s\n' 'Installed without staging or committing. Review the diff and preserve your existing AGENTS.md instructions.' \
  'If AGENTS.md was preserved, explicitly link .github/codex-instructions.md and the installed Skills from your own instructions.' \
  'Land the reviewed adoption on the remote default branch before GitHub onboarding writes.' \
  'Then invoke $project-onboarding in Codex. No VM or automatic model execution is required by this installer.'
