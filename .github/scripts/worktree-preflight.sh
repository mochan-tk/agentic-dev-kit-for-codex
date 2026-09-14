#!/usr/bin/env bash
# Read-only companion for the shipped session-orchestration procedure.
# Git occupancy and declared claims are evidence, not an authenticated lock.
set -euo pipefail
usage() { echo 'Usage: bash worktree-preflight.sh --target DIR --branch BRANCH --writer REF --claims JSON --action push|claim|archive' >&2; exit 2; }
TARGET="" BRANCH="" WRITER="" CLAIMS="" ACTION=""
while [ "$#" -gt 0 ]; do
  [ -n "${2:-}" ] || usage
  case "$1" in
    --target) TARGET="$2";; --branch) BRANCH="$2";; --writer) WRITER="$2";;
    --claims) CLAIMS="$2";; --action) ACTION="$2";; *) usage;;
  esac
  shift 2
done
case "$ACTION" in push|claim|archive);; *) usage;; esac
[ -d "$TARGET" ] && [ -n "$BRANCH" ] && [ -n "$WRITER" ] || usage
for tool in git jq; do command -v "$tool" >/dev/null || usage; done
export GIT_OPTIONAL_LOCKS=0
TARGET="$(cd "$TARGET" && pwd -P)"
ROOT="$(git -C "$TARGET" rev-parse --show-toplevel)" || { echo 'UNKNOWN: repository unavailable'; exit 3; }
[ "$TARGET" = "$ROOT" ] || { echo 'REFUSED: target must be the actual worktree root'; exit 1; }
git -C "$TARGET" check-ref-format "refs/heads/$BRANCH" >/dev/null || usage
HEAD_BRANCH="$(git -C "$TARGET" symbolic-ref --quiet --short HEAD)" || HEAD_BRANCH=""
if [ "$ACTION" = push ] && [ -z "$HEAD_BRANCH" ]; then
  echo 'REFUSED: detached HEAD. Preserve commits and changes, then explicitly create or attach the planned branch before a new preflight.'
  exit 1
fi
# Every archive check deliberately remains non-success: a local URL, file or
# declared boolean does not establish current durable evidence or approval.
if [ "$ACTION" = archive ]; then
  echo 'WARNING: durable evidence and handoff are unverified. Preserve tracked/untracked files, diffs, commits and recovery material. Human review of current records and explicit cleanup authority are required.'
  exit 3
fi
WORK="$(mktemp -d "${TMPDIR:-/tmp}/worktree-preflight.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
git -C "$TARGET" worktree list --porcelain -z > "$WORK/worktrees" || { echo 'UNKNOWN: worktree inventory unavailable'; exit 3; }
CURRENT="" OCCUPIED=0 RECORDS=0 TARGETS=0 HAVE_HEAD=0 HAVE_BRANCH=0 INVENTORY_BAD=0
while IFS= read -r -d '' field; do
  case "$field" in
    'worktree '*)
      [ -z "$CURRENT" ] || INVENTORY_BAD=1
      CURRENT="${field#worktree }"; HAVE_HEAD=0; HAVE_BRANCH=0
      [[ "$CURRENT" == /* ]] || INVENTORY_BAD=1;;
    'HEAD '*)
      [ -n "$CURRENT" ] && [ "$HAVE_HEAD" = 0 ] || INVENTORY_BAD=1
      [[ "${field#HEAD }" =~ ^[0-9a-f]{40}$ ]] || INVENTORY_BAD=1
      HAVE_HEAD=1;;
    'branch '*)
      [ -n "$CURRENT" ] && [ "$HAVE_BRANCH" = 0 ] || INVENTORY_BAD=1
      [[ "${field#branch }" == refs/heads/* ]] && git -C "$TARGET" check-ref-format "${field#branch }" >/dev/null || INVENTORY_BAD=1
      HAVE_BRANCH=1
      if [ "${field#branch }" = "refs/heads/$BRANCH" ] && [ "$CURRENT" != "$TARGET" ]; then OCCUPIED=1; fi
      if [ "$CURRENT" = "$TARGET" ] && [ "${field#branch }" != "refs/heads/$HEAD_BRANCH" ]; then INVENTORY_BAD=1; fi;;
    detached) [ -n "$CURRENT" ] && [ "$HAVE_BRANCH" = 0 ] || INVENTORY_BAD=1; HAVE_BRANCH=1
      if [ "$CURRENT" = "$TARGET" ] && [ -n "$HEAD_BRANCH" ]; then INVENTORY_BAD=1; fi;;
    locked|'locked '*|prunable|'prunable '*) [ -n "$CURRENT" ] || INVENTORY_BAD=1;;
    '')
      [ -n "$CURRENT" ] && [ "$HAVE_HEAD" = 1 ] && [ "$HAVE_BRANCH" = 1 ] || INVENTORY_BAD=1
      RECORDS=$((RECORDS+1))
      if [ "$CURRENT" = "$TARGET" ]; then TARGETS=$((TARGETS+1)); fi
      CURRENT="";;
    *) INVENTORY_BAD=1;;
  esac
done < "$WORK/worktrees"
if [ "$INVENTORY_BAD" != 0 ] || [ "$RECORDS" = 0 ] || [ "$TARGETS" != 1 ] || [ -n "$CURRENT" ] || [ -n "$field" ]; then
  echo 'UNKNOWN: incomplete or malformed worktree inventory'; exit 3
fi
if [ "$OCCUPIED" = 1 ]; then
  echo 'REFUSED: planned branch is occupied by another worktree. Obtain a durable release/handoff or choose an unoccupied branch; never steal it with force.'
  exit 1
fi
if [ "$ACTION" = push ] && [ "$HEAD_BRANCH" != "$BRANCH" ]; then
  echo 'REFUSED: current branch differs from the planned push branch'; exit 1
fi
[ -f "$CLAIMS" ] && [ ! -L "$CLAIMS" ] && [ "$(wc -c < "$CLAIMS")" -le 1048576 ] || { echo 'UNKNOWN: bounded claim readback unavailable'; exit 3; }
if ! jq -es --arg target "$TARGET" --arg branch "$BRANCH" --arg writer "$WRITER" '
  length==1 and (.[0]|type=="object" and (keys==["claims"]) and (.claims|type)=="array" and (.claims|length)<=128
    and all(.claims[];type=="object" and (keys|sort)==["branch","state","worktree","writer"]
      and ([.branch,.worktree,.writer]|all(.[];type=="string" and length>0 and (test("[[:cntrl:]]")|not)))
      and (.worktree|startswith("/") and (test("//|/\\.(/|$)|/\\.\\.(/|$)")|not))
      and (.state=="active" or .state=="released"))
    and ([.claims[]|select(.state=="active" and (.worktree==$target or .branch==$branch))] as $active
      | ($active|length)==1 and $active[0].writer==$writer and $active[0].worktree==$target and $active[0].branch==$branch))' "$CLAIMS" >/dev/null 2>&1; then
  echo 'REFUSED: missing, malformed, conflicting or mismatched declared writer claims'; exit 1
fi
echo 'OBSERVED: planned branch and declared writer have no observed worktree conflict. Supervisor must verify current durable ownership and actual worker state; this is not an exclusive lock or push authorization.'
