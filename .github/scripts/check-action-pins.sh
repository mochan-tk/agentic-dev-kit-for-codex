#!/usr/bin/env bash
# Fail when a GitHub Action is not pinned to a full commit SHA and version comment.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

files=$(git ls-files '.github/workflows/*.yml' '.github/workflows/*.yaml')
if [ -z "$files" ]; then
  echo "All action references are SHA-pinned (no workflow files to scan)."
  exit 0
fi

bad=$(printf '%s\n' "$files" \
  | xargs grep -nE '^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]' \
  | grep -vE 'uses:[[:space:]]+\./' \
  | grep -vE '@[0-9a-f]{40}[[:space:]]+#[[:space:]]*v[0-9]+\.[0-9]+\.[0-9]+[[:space:]]*$' || true)

if [ -n "$bad" ]; then
  printf '%s\n' "$bad"
  echo "::error::Unpinned uses: reference above — pin to a full 40-hex commit SHA with a trailing '# vX.Y.Z' comment."
  exit 1
fi

echo "All action references are SHA-pinned."
