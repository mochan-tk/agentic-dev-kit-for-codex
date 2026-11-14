#!/usr/bin/env bash
# Source-derived local installer: Copilot scaffold-init.sh at fd265ddef150fab86cd54d0e383c2c25fe297ffb.
# Retains ordered planning, seed/tuned/instance preservation and collision refusal.
# Codex adaptation: a closed payload, local sources only, and explicit apply.
set -euo pipefail
export LC_ALL=C
export GIT_OPTIONAL_LOCKS=0

usage() {
  printf '%s\n' 'Usage: scaffold-init.sh [--dry-run | --apply] [target-directory]' \
    '       scaffold-init.sh --upgrade --old-source DIR --transaction DIR [--dry-run | --apply] TARGET' \
    '       scaffold-init.sh --rollback --transaction DIR [--dry-run | --apply] TARGET' \
    'SCAFFOLD_SOURCE_DIR selects a local kit checkout; default is the adjacent checkout.' \
    'Default: dry-run. Apply requires an existing Git repository root.' \
    'Upgrade replaces only known-old engines. Rollback affects only its recorded operation.' \
    'No network, force, Git init/add/commit, model or GitHub operation.'
}
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }
MODE=dry-run
MODE_SET=0
DEST_ARG=""
OP=install
OLD_INPUT=""
TX_INPUT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run|--apply)
      [ "$MODE_SET" -eq 0 ] || { usage >&2; exit 2; }
      MODE="${1#--}"; MODE_SET=1 ;;
    --upgrade|--rollback)
      [ "$OP" = install ] || { usage >&2; exit 2; }; OP="${1#--}" ;;
    --old-source|--transaction)
      option="$1"; shift; [ "$#" -gt 0 ] && [ -n "$1" ] || { usage >&2; exit 2; }
      if [ "$option" = --old-source ]; then
        [ -z "$OLD_INPUT" ] || { usage >&2; exit 2; }; OLD_INPUT="$1"
      else [ -z "$TX_INPUT" ] || { usage >&2; exit 2; }; TX_INPUT="$1"; fi ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$DEST_ARG" ] || { usage >&2; exit 2; }; DEST_ARG="$1" ;;
  esac
  shift
done
case "$OP" in
  install) [ -z "$OLD_INPUT$TX_INPUT" ] || { usage >&2; exit 2; } ;;
  upgrade) [ -n "$OLD_INPUT" ] && [ -n "$TX_INPUT" ] && [ -n "$DEST_ARG" ] || { usage >&2; exit 2; } ;;
  rollback) [ -z "$OLD_INPUT" ] && [ -n "$TX_INPUT" ] && [ -n "$DEST_ARG" ] || { usage >&2; exit 2; } ;;
esac

# Git's -C does not cancel inherited repository or configuration selection.
# Refuse before any source/target observation, including preview and rollback.
for var in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_NAMESPACE GIT_SHALLOW_FILE GIT_REPLACE_REF_BASE; do
  [ -z "${!var+x}" ] || fail 'Git context override is not supported by local installation'
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
if [ "$MODE" = apply ] || [ "$OP" = rollback ]; then
  [ -d "$DEST" ] || fail 'apply requires an existing Git repository root; initialize it explicitly first'
  [ "$(git -C "$DEST" rev-parse --is-inside-work-tree)" = true ] || fail 'target is not a Git worktree'
  [ "$(git -C "$DEST" rev-parse --is-bare-repository)" = false ] || fail 'target is a bare repository'
  TOP="$(git -C "$DEST" rev-parse --show-toplevel)" || fail 'target Git root is uncheckable'
  TOP="$(cd "$TOP" && pwd -P)" || fail 'target Git root is unavailable'
  [ "$TOP" = "$DEST" ] || fail 'target must be the physical Git worktree root'
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
# These bounded local operations require an exclusive writer, not adversarial
# same-user race resistance. BSD and GNU stat are both supported explicitly.
if stat -f '%d:%i' "$SRC" >/dev/null 2>&1; then
  identity() { stat -f '%d:%i' "$1"; }
  attributes() { stat -f '%Lp:%l:%z' "$1"; }
else
  identity() { stat -c '%d:%i' "$1"; }
  attributes() { stat -c '%a:%h:%s' "$1"; }
fi
hash_text() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d ' ' -f1
  else shasum -a 256 | cut -d ' ' -f1; fi
}
bounded_file() {
  local values mode links size
  no_links "$1" && [ -f "$1" ] || fail 'input is not a no-link regular file'
  values="$(attributes "$1")" || fail 'file metadata unavailable'
  IFS=: read -r mode links size <<< "$values"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] && [[ "$size" =~ ^[0-9]+$ ]] && [ "$links" = 1 ] || fail 'ambiguous file metadata or hardlink'
  [ "$size" -le "$2" ] || fail 'bounded file size exceeded'
  FILE_MODE="$mode"
}
disjoint() {
  case "$1/" in "$2/"*) fail 'source/target/transaction roots overlap' ;; esac
  case "$2/" in "$1/"*) fail 'source/target/transaction roots overlap' ;; esac
}
TX=""; OLD=""; OLD_HASHES=(); BEFORE=(); CHANGES=(); DIRS=()
if [ "$OP" != install ]; then
  TX="$(absolute "$TX_INPUT")"
  no_links "$TX" || fail 'transaction root or ancestor is a symlink'
  tx_parent="$(dirname "$TX")"
  [ -d "$tx_parent" ] || fail 'transaction parent must already exist'
  TX="$(cd "$tx_parent" && pwd -P)/$(basename "$TX")"
  disjoint "$TX" "$SRC"; disjoint "$TX" "$DEST"
  if [ "$OP" = upgrade ]; then
    [ ! -e "$TX" ] || fail 'transaction directory must be exclusively new'
    OLD="$(absolute "$OLD_INPUT")"
    no_links "$OLD" && [ -d "$OLD" ] || fail 'old source root is invalid'
    OLD="$(cd "$OLD" && pwd -P)"
    disjoint "$OLD" "$DEST"; disjoint "$OLD" "$TX"
  else [ -d "$TX" ] || fail 'transaction directory missing'; fi
fi
# Install and upgrade require the selected source's current layout declaration.
# Historical retained rollback sources predate parity projection. Rollback binds
# the complete manifest to local-upgrade/v1's sealed new-inventory and new-root;
# all payload, record and backup no-link/size/digest checks still apply.
if [ "$OP" != rollback ]; then
  PARITY="$SRC/.github/distribution/source-parity.v1.json"
  bounded_file "$PARITY" 1048576
  EXPECTED_LAYOUT_SHA256="$(sed -n 's/.*"payload_layout_sha256": "\([0-9a-f]\{64\}\)".*/\1/p' "$PARITY")"
  [[ "$EXPECTED_LAYOUT_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail 'missing or ambiguous payload layout digest'
fi
contains() { grep -Fxq -- "$1" <<< "$2"; }
bounded_file "$MANIFEST" 16384
NAMES=()
CLASSES=()
HASHES=()
ACTIONS=()
SEEN=$'\n'
COUNT=0
LAYOUT=""
SORTED_MANIFEST="$(LC_ALL=C sort "$MANIFEST")" || fail 'payload inventory sort failed'
while IFS=$'\t' read -r name class sha extra || [ -n "${name:-}" ]; do
  case "$name" in '#'*|'') continue ;; esac
  safe_relative "$name" || fail 'unsafe payload path'
  [[ "$sha" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || fail 'malformed payload inventory row'
  case "$class" in engine|tuned|instance|seed) ;; *) fail 'unknown preservation class' ;; esac
  folded="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
  contains "$folded" "$SEEN" && fail 'duplicate or case-colliding payload path'
  SEEN+="$folded"$'\n'
  no_links "$PAYLOAD/$name" || fail 'source payload symlink'
  bounded_file "$PAYLOAD/$name" 1048576
  [ "$FILE_MODE" = 644 ] || fail 'source payload mode must be 0644'
  [ "$(digest "$PAYLOAD/$name")" = "$sha" ] || fail 'source payload digest drift'
  no_links "$DEST/$name" || fail 'target payload path or ancestor is a symlink'
  parent="$(dirname "$DEST/$name")"
  while [ "$parent" != / ]; do
    [ ! -e "$parent" ] || [ -d "$parent" ] || fail 'target ancestor is not a directory'
    [ "$parent" = "$DEST" ] && break
    parent="${parent%/*}"; [ -n "$parent" ] || parent=/
  done
  action=install
  before=-
  if [ -e "$DEST/$name" ]; then
    [ -f "$DEST/$name" ] || fail 'target file/directory collision'
    if [ "$OP" = rollback ]; then action=recorded
    elif [ "$OP" = upgrade ] && [ "$class" = engine ]; then
      bounded_file "$DEST/$name" 1048576
      [ "$FILE_MODE" = 644 ] || fail 'unknown engine mode'
      before="$(digest "$DEST/$name")"
      if [ "$before" = "$sha" ]; then action=identical; else action=upgrade; fi
    elif cmp -s "$PAYLOAD/$name" "$DEST/$name"; then action=identical
    elif [ "$class" != engine ]; then action=preserve
    else fail "differing engine collision: $name"; fi
  fi
  NAMES+=("$name"); CLASSES+=("$class"); HASHES+=("$sha"); ACTIONS+=("$action")
  BEFORE+=("$before")
  LAYOUT+="$name"$'\t'"$class"$'\n'
  COUNT=$((COUNT + 1))
done <<< "$SORTED_MANIFEST"
if [ "$OP" != rollback ]; then
  ACTUAL_LAYOUT="$(printf '%s' "$LAYOUT" | LC_ALL=C sort | hash_text)"
  [ "$ACTUAL_LAYOUT" = "$EXPECTED_LAYOUT_SHA256" ] || fail 'unreviewed payload path/class layout'
fi
# find never follows directory links. Extra files, special entries and links refuse.
# Capture status in the main shell: process substitution would hide find errors.
ACTUAL_ENTRIES="$(find "$PAYLOAD" -mindepth 1 ! -type d -print)" || fail 'payload enumeration failed'
ACTUAL=0
while IFS= read -r found; do
  [ -n "$found" ] || continue
  relative="${found#"$PAYLOAD"/}"
  [ ! -L "$found" ] && [ -f "$found" ] || fail 'unexpected nonregular payload entry'
  folded="$(printf '%s' "$relative" | tr '[:upper:]' '[:lower:]')"
  contains "$folded" "$SEEN" || fail 'unreviewed extra payload entry'
  ACTUAL=$((ACTUAL + 1))
done <<< "$ACTUAL_ENTRIES"
[ "$ACTUAL" -eq "$COUNT" ] || fail 'payload inventory is incomplete'

REMOVE_DIRS=()
if [ "$OP" = upgrade ]; then
  # OLD is defined only by its inventory. Old parity is neither needed nor read.
  old_manifest="$OLD/.github/distribution/payload.v1.tsv"
  old_payload="$OLD/.github/distribution/payload"
  bounded_file "$old_manifest" 16384
  OLD_NAMES=(); OLD_CLASSES=(); OLD_SEEN=$'\n'
  while IFS=$'\t' read -r name class sha extra || [ -n "${name:-}" ]; do
    case "$name" in '#'*|'') continue ;; esac
    safe_relative "$name" || fail 'unsafe old payload path'
    [[ "$sha" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || fail 'old source malformed row'
    case "$class" in engine|tuned|instance|seed) ;; *) fail 'unknown old preservation class' ;; esac
    folded="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
    contains "$folded" "$OLD_SEEN" && fail 'duplicate or case-colliding old payload path'
    OLD_SEEN+="$folded"$'\n'
    bounded_file "$old_payload/$name" 1048576
    [ "$FILE_MODE" = 644 ] && [ "$(digest "$old_payload/$name")" = "$sha" ] || fail 'old source bytes/mode drift'
    OLD_NAMES+=("$name"); OLD_CLASSES+=("$class"); OLD_HASHES+=("$sha")
  done < "$old_manifest"
  old_entries="$(find "$old_payload" -mindepth 1 ! -type d -print)" || fail 'old source enumeration failed'
  old_count=0
  while IFS= read -r found; do
    [ -n "$found" ] || continue
    relative="${found#"$old_payload"/}"
    folded="$(printf '%s' "$relative" | tr '[:upper:]' '[:lower:]')"
    contains "$folded" "$OLD_SEEN" || fail 'old source extra entry'
    bounded_file "$found" 1048576; old_count=$((old_count + 1))
  done <<< "$old_entries"
  [ "$old_count" -eq "${#OLD_NAMES[@]}" ] || fail 'old source inventory is incomplete'
  NEW_NAMES=("${NAMES[@]}"); NEW_CLASSES=("${CLASSES[@]}")
  NEW_HASHES=("${HASHES[@]}"); NEW_ACTIONS=("${ACTIONS[@]}"); NEW_BEFORE=("${BEFORE[@]}")
  union="$(printf '%s\n' "${NAMES[@]}" "${OLD_NAMES[@]}" | LC_ALL=C sort -u)"
  NAMES=(); CLASSES=(); HASHES=(); ACTIONS=(); BEFORE=(); SEEN=$'\n'
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    folded="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
    contains "$folded" "$SEEN" && fail 'case-colliding old/new payload path'
    SEEN+="$folded"$'\n'
    new_index=-1; old_index=-1
    for ((j=0; j<${#NEW_NAMES[@]}; j++)); do [ "$name" != "${NEW_NAMES[$j]}" ] || new_index=$j; done
    for ((j=0; j<${#OLD_NAMES[@]}; j++)); do [ "$name" != "${OLD_NAMES[$j]}" ] || old_index=$j; done
    if [ "$new_index" -ge 0 ]; then
      class="${NEW_CLASSES[$new_index]}"; sha="${NEW_HASHES[$new_index]}"
      action="${NEW_ACTIONS[$new_index]}"; before="${NEW_BEFORE[$new_index]}"
      if [ "$old_index" -ge 0 ]; then
        [ "$class" = "${OLD_CLASSES[$old_index]}" ] || fail "old source class mismatch: $name"
      fi
      if [ "$action" = upgrade ]; then
        [ "$old_index" -ge 0 ] && [ "$before" = "${OLD_HASHES[$old_index]}" ] || fail 'unknown engine bytes; whole upgrade refused'
      fi
    else
      class="${OLD_CLASSES[$old_index]}"; sha=-; action=delete
      [ "$class" = engine ] || fail "removed non-engine path: $name"
      no_links "$DEST/$name" && [ -f "$DEST/$name" ] || fail "removed engine missing or unsafe: $name"
      bounded_file "$DEST/$name" 1048576
      before="$(digest "$DEST/$name")"
      [ "$FILE_MODE" = 644 ] && [ "$before" = "${OLD_HASHES[$old_index]}" ] || fail "removed engine modified: $name"
    fi
    case "$action" in install|upgrade|delete) CHANGES+=("${#NAMES[@]}") ;; esac
    NAMES+=("$name"); CLASSES+=("$class"); HASHES+=("$sha"); ACTIONS+=("$action"); BEFORE+=("$before")
  done <<< "$union"
  COUNT=${#NAMES[@]}
  # Remove only directories wholly emptied by these deletions. An unrelated
  # empty directory is still adopter content and keeps its ancestors alive.
  remove_seen=$'\n'
  for ((i=0; i<COUNT; i++)); do
    [ "${ACTIONS[$i]}" = delete ] || continue
    parent="$(dirname "${NAMES[$i]}")"
    while [ "$parent" != . ]; do
      removable=1
      for ((j=0; j<COUNT; j++)); do
        case "${NAMES[$j]}" in "$parent/"*) [ "${ACTIONS[$j]}" = delete ] || removable=0 ;; esac
      done
      contents="$(find "$DEST/$parent" -mindepth 1 -print)" || fail 'removal directory enumeration failed'
      while IFS= read -r found; do
        [ -n "$found" ] || continue
        related=0; relative="${found#"$DEST"/}"
        for ((j=0; j<COUNT; j++)); do
          [ "${ACTIONS[$j]}" = delete ] || continue
          if [ "$relative" = "${NAMES[$j]}" ]; then related=1
          elif [ -d "$found" ] && [ ! -L "$found" ]; then
            case "${NAMES[$j]}" in "$relative/"*) related=1 ;; esac
          fi
        done
        [ "$related" = 1 ] || removable=0
      done <<< "$contents"
      if [ "$removable" = 1 ] && ! contains "$parent" "$remove_seen"; then
        REMOVE_DIRS+=("$parent"); remove_seen+="$parent"$'\n'
      fi
      parent="$(dirname "$parent")"
    done
  done
fi

root_binding() {
  local observed
  no_links "$1" && [ -d "$1" ] || fail 'root binding unavailable'
  observed="$(identity "$1")" || fail 'root identity unavailable'
  [[ "$observed" =~ ^[0-9]+:[0-9]+$ ]] || fail 'invalid root identity'
  printf '%s\n%s\n' "$1" "$observed" | hash_text
}
target_binding() { root_binding "$DEST"; }
tx_binding() { root_binding "$TX"; }
check_bindings() {
  no_links "$DEST" && no_links "$TX" && [ -d "$DEST" ] && [ -d "$TX" ] || fail 'operation root binding changed'
  [ "$(target_binding)" = "$TARGET_BINDING" ] && [ "$(tx_binding)" = "$TX_BINDING" ] || fail 'operation root identity changed'
}
file_state() {
  no_links "$DEST/$1" || fail 'affected path binding changed'
  if [ ! -e "$DEST/$1" ]; then STATE=-; return; fi
  bounded_file "$DEST/$1" 1048576
  [ "$FILE_MODE" = 644 ] || fail 'affected file mode changed'
  STATE="$(digest "$DEST/$1")"
}
write_status() {
  check_bindings
  [ ! -e "$TX/status" ] || bounded_file "$TX/status" 128
  printf '%s\t%s\n' "$1" "$2" > "$TX/status"
}
record_digest() { cat "$TX/meta.tsv" "$TX/files.tsv" "$TX/directories.tsv" | hash_text; }
operation_finish() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "${OP_STARTED:-0}" = 1 ]; then
    write_status partial "${PROGRESS:-0}" || true
    printf '%s\n' 'Operation incomplete; retain the transaction and review explicit rollback.' >&2
  fi
  exit "$rc"
}
if [ "$OP" = rollback ]; then
  # Parse data only. Strict rows, closed paths, finite sizes and content hashes
  # reject malformed records; these hashes are NOT authenticated signatures.
  for f in meta.tsv files.tsv directories.tsv record.sha256 status; do bounded_file "$TX/$f" 16384; done
  [ "$(wc -l < "$TX/meta.tsv" | tr -d ' ')" = 7 ] || fail 'invalid operation metadata'
  { IFS=$'\t' read -r key schema; [ "$key" = schema ] && [ "$schema" = local-upgrade/v1 ] || fail 'unsupported operation record'
    IFS=$'\t' read -r key TARGET_BINDING; [ "$key" = target ] || fail 'invalid target binding'
    IFS=$'\t' read -r key TX_BINDING; [ "$key" = transaction ] || fail 'invalid transaction binding'
    IFS=$'\t' read -r key new_digest; [ "$key" = new-inventory ] || fail 'invalid new binding'
    IFS=$'\t' read -r key old_digest; [ "$key" = old-inventory ] || fail 'invalid old binding'
    IFS=$'\t' read -r key new_root; [ "$key" = new-root ] || fail 'invalid new root binding'
    IFS=$'\t' read -r key old_root; [ "$key" = old-root ] || fail 'invalid old root binding'
  } < "$TX/meta.tsv"
  for value in "$TARGET_BINDING" "$TX_BINDING" "$new_digest" "$old_digest" "$new_root" "$old_root"; do [[ "$value" =~ ^[0-9a-f]{64}$ ]] || fail 'invalid binding digest'; done
  canonical_meta="$(printf 'schema\tlocal-upgrade/v1\ntarget\t%s\ntransaction\t%s\nnew-inventory\t%s\nold-inventory\t%s\nnew-root\t%s\nold-root\t%s\n' \
    "$TARGET_BINDING" "$TX_BINDING" "$new_digest" "$old_digest" "$new_root" "$old_root")"
  [ "$(printf '%s\n' "$canonical_meta" | hash_text)" = "$(digest "$TX/meta.tsv")" ] || fail 'noncanonical operation metadata'
  check_bindings
  [ "$new_digest" = "$(digest "$MANIFEST")" ] || fail 'rollback source inventory mismatch'
  [ "$new_root" = "$(root_binding "$SRC")" ] || fail 'rollback source root mismatch'
  read -r sealed < "$TX/record.sha256"
  [ "$(wc -l < "$TX/record.sha256" | tr -d ' ')" = 1 ] && [ "$(wc -c < "$TX/record.sha256" | tr -d ' ')" = 65 ] || fail 'malformed record seal'
  [[ "$sealed" =~ ^[0-9a-f]{64}$ ]] && [ "$sealed" = "$(record_digest)" ] || fail 'operation record digest mismatch'
  IFS=$'\t' read -r status progress extra < "$TX/status"
  [ "$(wc -l < "$TX/status" | tr -d ' ')" = 1 ] || fail 'malformed operation status'
  case "$status" in prepared|applied|partial|rolled-back) ;; *) fail 'unknown operation status' ;; esac
  [[ "$progress" =~ ^[0-9]+$ ]] && [ -z "$extra" ] || fail 'invalid operation progress'
  [ "$(printf '%s\t%s\n' "$status" "$progress" | hash_text)" = "$(digest "$TX/status")" ] || fail 'noncanonical operation status'
  R_NAMES=(); R_BEFORE=(); R_AFTER=(); R_STATE=(); R_DIRS=()
  # Deleted paths are absent from the new inventory, but their rows retain
  # their positions in the canonical union. Validate that union before writes.
  union="$(printf '%s\n' "${NAMES[@]}")"; deleted_seen=$'\n'
  while IFS=$'\t' read -r index name before after extra || [ -n "${index:-}" ]; do
    [ "$after" = - ] || continue
    safe_relative "$name" || fail 'unsafe removed operation path'
    folded="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
    if contains "$folded" "$SEEN" || contains "$folded" "$deleted_seen"; then fail 'duplicate removed operation path'; fi
    deleted_seen+="$folded"$'\n'; union+=$'\n'"$name"
  done < "$TX/files.tsv"
  union="$(printf '%s\n' "$union" | LC_ALL=C sort)"
  U_NAMES=()
  while IFS= read -r name; do [ -z "$name" ] || U_NAMES+=("$name"); done <<< "$union"
  previous=-1
  canonical_files=""
  expected_entries=$'\nmeta.tsv\nfiles.tsv\ndirectories.tsv\nrecord.sha256\nstatus\n'
  while IFS=$'\t' read -r index name before after extra || [ -n "${index:-}" ]; do
    [[ "$index" =~ ^(0|[1-9][0-9]*)$ ]] && [ "$index" -lt "${#U_NAMES[@]}" ] && [ "$index" -gt "$previous" ] || fail 'invalid operation index/order'
    [ "$name" = "${U_NAMES[$index]}" ] && [ -z "$extra" ] || fail 'unreviewed operation path/post-state'
    class=engine
    if [ "$after" = - ]; then
      [[ "$before" =~ ^[0-9a-f]{64}$ ]] || fail 'invalid deletion pre-state'
    else
      matched=0
      for ((j=0; j<COUNT; j++)); do
        if [ "$name" = "${NAMES[$j]}" ] && [ "$after" = "${HASHES[$j]}" ]; then matched=1; class="${CLASSES[$j]}"; fi
      done
      [ "$matched" = 1 ] || fail 'unreviewed operation path/post-state'
    fi
    [ "$before" = - ] || [[ "$before" =~ ^[0-9a-f]{64}$ ]] || fail 'invalid pre-state'
    if [ "$before" != - ]; then
      [ "$class" = engine ] && [ "$before" != "$after" ] || fail 'invalid replacement class/state'
      bounded_file "$TX/before-${#R_NAMES[@]}" 1048576
      [ "$(digest "$TX/before-${#R_NAMES[@]}")" = "$before" ] || fail 'missing/tampered backup'
      expected_entries+="before-${#R_NAMES[@]}"$'\n'
    fi
    file_state "$name"
    [ "$STATE" = "$before" ] || [ "$STATE" = "$after" ] || fail 'affected file is neither recorded pre-state nor post-state'
    [ "$status" != rolled-back ] || [ "$STATE" = "$before" ] || fail 'rolled-back target changed'
    R_NAMES+=("$name"); R_BEFORE+=("$before"); R_AFTER+=("$after"); R_STATE+=("$STATE")
    canonical_files+="$index"$'\t'"$name"$'\t'"$before"$'\t'"$after"$'\n'
    previous="$index"
  done < "$TX/files.tsv"
  [ "${#R_NAMES[@]}" -gt 0 ] && [ "$progress" -le "${#R_NAMES[@]}" ] || fail 'empty or inconsistent operation'
  [ "$(printf '%s' "$canonical_files" | hash_text)" = "$(digest "$TX/files.tsv")" ] || fail 'noncanonical operation files'
  dir_seen=$'\n'
  canonical_dirs=""; previous_dir=""; restore_dirs=$'\n'
  while IFS= read -r name || [ -n "${name:-}" ]; do
    safe_relative "$name" || fail 'unsafe operation directory'
    [[ "$name" > "$previous_dir" ]] || fail 'noncanonical operation directory order'
    case "$dir_seen" in *$'\n'"$name"$'\n'*) fail 'duplicate operation directory' ;; esac
    related=0
    for f in "${R_NAMES[@]}"; do case "$f" in "$name/"*) related=1 ;; esac; done
    [ "$related" = 1 ] || fail 'unrelated operation directory'
    no_links "$DEST/$name" || fail 'operation directory is a symlink'
    [ ! -e "$DEST/$name" ] || [ -d "$DEST/$name" ] || fail 'operation directory collision'
    for ((j=0; j<${#R_NAMES[@]}; j++)); do
      if [ "${R_AFTER[$j]}" = - ]; then
        case "${R_NAMES[$j]}" in "$name/"*) restore_dirs+="$name"$'\n'; break ;; esac
      fi
    done
    R_DIRS+=("$name"); dir_seen+="$name"$'\n'
    canonical_dirs+="$name"$'\n'; previous_dir="$name"
    [ "${#R_DIRS[@]}" -le 128 ] || fail 'too many operation directories'
  done < "$TX/directories.tsv"
  [ "$(printf '%s' "$canonical_dirs" | hash_text)" = "$(digest "$TX/directories.tsv")" ] || fail 'noncanonical operation directories'
  # Every extant entry under an operation-created directory must itself be
  # recorded. Unrelated additions stop rollback BEFORE any target write.
  for name in ${R_DIRS[@]+"${R_DIRS[@]}"}; do
    contains "$name" "$restore_dirs" && continue
    [ -d "$DEST/$name" ] || continue
    contents="$(find "$DEST/$name" -mindepth 1 -print)" || fail 'operation directory enumeration failed'
    while IFS= read -r found; do
      [ -n "$found" ] || continue
      relative="${found#"$DEST"/}"
      case "$dir_seen" in *$'\n'"$relative"$'\n'*) continue ;; esac
      related=0
      for ((j=0; j<${#R_NAMES[@]}; j++)); do
        [ "$relative" != "${R_NAMES[$j]}" ] || [ "${R_BEFORE[$j]}" != - ] || related=1
      done
      [ "$related" = 1 ] || fail 'unrelated entry in operation-created directory'
    done <<< "$contents"
  done
  for ((j=0; j<${#R_NAMES[@]}; j++)); do
    [ "${R_BEFORE[$j]}" != - ] || continue
    parent="$(dirname "${R_NAMES[$j]}")"
    while [ "$parent" != . ]; do
      [ -d "$DEST/$parent" ] || contains "$parent" "$restore_dirs" || fail 'unrecorded restoration directory missing'
      parent="$(dirname "$parent")"
    done
  done
  tx_entries="$(find "$TX" -mindepth 1 -maxdepth 1 -print)" || fail 'transaction enumeration failed'
  while IFS= read -r found; do
    case "$expected_entries" in *$'\n'"${found#"$TX"/}"$'\n'*) ;; *) fail 'unexpected transaction entry' ;; esac
  done <<< "$tx_entries"
  check_bindings
  printf 'operation=rollback mode=%s affected-files=%s\n' "$MODE" "${#R_NAMES[@]}"
  if [ "$MODE" = dry-run ] || [ "$status" = rolled-back ]; then printf '%s\n' 'No files or Git state were changed.'; exit 0; fi
  PROGRESS=0; OP_STARTED=1; trap operation_finish EXIT
  for name in ${R_DIRS[@]+"${R_DIRS[@]}"}; do
    contains "$name" "$restore_dirs" || continue
    check_bindings; no_links "$DEST/$name" || fail 'restoration directory binding changed'
    if [ ! -d "$DEST/$name" ]; then mkdir "$DEST/$name"; chmod 755 "$DEST/$name"; fi
  done
  for ((j=0; j<${#R_NAMES[@]}; j++)); do
    check_bindings; name="${R_NAMES[$j]}"; file_state "$name"
    [ "$STATE" = "${R_STATE[$j]}" ] || fail 'target changed after rollback preflight'
    if [ "$STATE" != "${R_BEFORE[$j]}" ]; then
      if [ "${R_BEFORE[$j]}" = - ]; then rm -- "$DEST/$name"
      else
        bounded_file "$TX/before-$j" 1048576
        [ "$(digest "$TX/before-$j")" = "${R_BEFORE[$j]}" ] || fail 'backup changed before restoration'
        cp "$TX/before-$j" "$DEST/$name"; chmod 644 "$DEST/$name"
      fi
    fi
    file_state "$name"; [ "$STATE" = "${R_BEFORE[$j]}" ] || fail 'rollback verification failed'
    PROGRESS=$((PROGRESS + 1)); write_status partial "$PROGRESS"
  done
  for ((j=${#R_DIRS[@]}-1; j>=0; j--)); do
    name="${R_DIRS[$j]}"; contains "$name" "$restore_dirs" && continue
    check_bindings; no_links "$DEST/$name" || fail 'directory binding changed'
    [ ! -d "$DEST/$name" ] || rmdir "$DEST/$name" || fail 'created directory is not empty'
  done
  write_status rolled-back "$PROGRESS"; sync || fail 'rollback status flush failed'; OP_STARTED=0
  printf '%s\n' 'Recorded upgrade rolled back; unrelated files and Git state were not selected.'
  exit 0
fi

PROVENANCE=unknown
if git -C "$SRC" rev-parse --verify HEAD >/dev/null 2>&1 && [ -z "$(git -C "$SRC" rev-parse --show-prefix)" ]; then
  dirty="$(git -C "$SRC" status --porcelain --untracked-files=all)" || fail 'source Git state is uncheckable'
  if [ -z "$dirty" ]; then PROVENANCE="$(git -C "$SRC" rev-parse HEAD)"; fi
fi
printf 'mode=%s source-commit=%s payload-files=%s\n' "$MODE" "$PROVENANCE" "$COUNT"
for ((i=0; i<COUNT; i++)); do printf '%s\t%s\t%s\n' "${ACTIONS[$i]}" "${CLASSES[$i]}" "${NAMES[$i]}"; done
if [ "$MODE" = dry-run ]; then printf '%s\n' 'No files or Git state were changed.'; exit 0; fi

if [ "$OP" = upgrade ]; then
  if [ "${#CHANGES[@]}" -eq 0 ]; then printf '%s\n' 'Already new: no transaction or target write.'; exit 0; fi
  # Prepare the complete recovery record and ALL backups before target writes.
  # mkdir is exclusive; operation records never live inside an adopter/source.
  umask 077
  mkdir "$TX" || fail 'exclusive transaction creation failed'
  TARGET_BINDING="$(target_binding)"; TX_BINDING="$(tx_binding)"
  NEW_BINDING="$(root_binding "$SRC")"; OLD_BINDING="$(root_binding "$OLD")"
  printf 'schema\tlocal-upgrade/v1\ntarget\t%s\ntransaction\t%s\nnew-inventory\t%s\nold-inventory\t%s\nnew-root\t%s\nold-root\t%s\n' \
    "$TARGET_BINDING" "$TX_BINDING" "$(digest "$MANIFEST")" "$(digest "$old_manifest")" "$NEW_BINDING" "$OLD_BINDING" > "$TX/meta.tsv"
  : > "$TX/files.tsv"; : > "$TX/directories.tsv"
  PROGRESS=0; OP_STARTED=1; trap operation_finish EXIT
  dir_seen=$'\n'
  for ((j=0; j<${#CHANGES[@]}; j++)); do
    i="${CHANGES[$j]}"; name="${NAMES[$i]}"; check_bindings; file_state "$name"
    [ "$STATE" = "${BEFORE[$i]}" ] || fail 'target changed before backup'
    if [ "$STATE" != - ]; then
      cp "$DEST/$name" "$TX/before-$j" || fail 'backup failed before target mutation'
      bounded_file "$TX/before-$j" 1048576
      [ "$(digest "$TX/before-$j")" = "$STATE" ] || fail 'backup verification failed'
    fi
    printf '%s\t%s\t%s\t%s\n' "$i" "$name" "${BEFORE[$i]}" "${HASHES[$i]}" >> "$TX/files.tsv"
    parent="$(dirname "$name")"
    while [ "$parent" != . ]; do
      if [ ! -d "$DEST/$parent" ]; then
        case "$dir_seen" in *$'\n'"$parent"$'\n'*) ;; *) DIRS+=("$parent"); dir_seen+="$parent"$'\n' ;; esac
      fi
      parent="$(dirname "$parent")"
    done
  done
  for name in ${REMOVE_DIRS[@]+"${REMOVE_DIRS[@]}"}; do DIRS+=("$name"); done
  if [ "${#DIRS[@]}" -gt 0 ]; then printf '%s\n' "${DIRS[@]}" | sort > "$TX/directories.tsv"; fi
  # Do not mutate a target with a record that exceeds rollback's existing bounds.
  [ "${#DIRS[@]}" -le 128 ] || fail 'too many operation directories'
  for f in meta.tsv files.tsv directories.tsv; do bounded_file "$TX/$f" 16384; done
  record_digest > "$TX/record.sha256"
  write_status prepared 0
  sync || fail 'recovery record flush failed before target mutation'
  # Once prepared, the data-only record itself must remain unchanged.
  read -r sealed < "$TX/record.sha256"
  while IFS= read -r name; do
    contains "$name" "$remove_seen" && continue
    check_bindings; no_links "$DEST/$name" || fail 'directory link appeared'
    [ ! -e "$DEST/$name" ] || fail 'planned directory appeared'
    mkdir "$DEST/$name" || fail 'planned directory creation failed'
    chmod 755 "$DEST/$name"
  done < "$TX/directories.tsv"
  for ((j=0; j<${#CHANGES[@]}; j++)); do
    i="${CHANGES[$j]}"; name="${NAMES[$i]}"; check_bindings
    [ "$(record_digest)" = "$sealed" ] || fail 'operation record changed'
    file_state "$name"; [ "$STATE" = "${BEFORE[$i]}" ] || fail 'target changed after full preflight'
    if [ "${ACTIONS[$i]}" = delete ]; then
      rm -- "$DEST/$name" || fail 'recorded engine deletion failed'
    else
      bounded_file "$PAYLOAD/$name" 1048576
      [ "$FILE_MODE" = 644 ] && [ "$(digest "$PAYLOAD/$name")" = "${HASHES[$i]}" ] || fail 'source changed before upgrade'
      if [ "$STATE" = - ]; then
        (set -o noclobber; cat "$PAYLOAD/$name" > "$DEST/$name") || fail 'new-file copy failed'
      else cp "$PAYLOAD/$name" "$DEST/$name" || fail 'engine replacement failed'; fi
      chmod 644 "$DEST/$name"
    fi
    file_state "$name"; [ "$STATE" = "${HASHES[$i]}" ] || fail 'upgrade verification failed'
    PROGRESS=$((PROGRESS + 1)); write_status partial "$PROGRESS"
  done
  # Only directories sealed in directories.tsv are eligible for removal.
  while IFS= read -r name; do
    contains "$name" "$remove_seen" || continue
    check_bindings; no_links "$DEST/$name" || fail 'removal directory binding changed'
    rmdir "$DEST/$name" || fail 'recorded removal directory is not empty'
  done < <(LC_ALL=C sort -r "$TX/directories.tsv")
  write_status applied "$PROGRESS"; sync || fail 'operation status flush failed'; OP_STARTED=0
  printf '%s\n' 'Upgrade verified; retain the private operation record for explicit rollback. Review the Git diff; nothing was staged or committed.'
  exit 0
fi

# The adopter must keep this tree exclusively owned during apply. This is a
# bounded initial copy operation, not a concurrent filesystem transaction.
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
