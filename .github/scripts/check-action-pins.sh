#!/usr/bin/env bash
# Fail when a GitHub Action is not pinned to a full commit SHA and version comment.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

files=()
while IFS= read -r -d '' file; do
  files+=("$file")
done < <(git ls-files -z '.github/workflows/*.yml' '.github/workflows/*.yaml')

if [ "${#files[@]}" -eq 0 ]; then
  echo "All action references are SHA-pinned (no workflow files to scan)."
  exit 0
fi

uses_key_re="(^|[[:space:]{,])(\"uses\"|'uses'|uses)[[:space:]]*:"
external_re='^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]+[^@[:space:]#]+@[0-9a-f]{40}[[:space:]]+#[[:space:]]*v[0-9]+\.[0-9]+\.[0-9]+[[:space:]]*$'
local_re='^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]+\./[^[:space:]#]+([[:space:]]+#[^[:cntrl:]]*)?[[:space:]]*$'

bad=""
for file in "${files[@]}"; do
  line_number=0
  while IFS= read -r line || [ -n "$line" ]; do
    line_number=$((line_number + 1))
    trimmed="${line#"${line%%[![:space:]]*}"}"
    if [[ "$trimmed" == \#* ]] || [[ ! "$line" =~ $uses_key_re ]]; then
      continue
    fi
    if [[ "$line" =~ $external_re ]] || [[ "$line" =~ $local_re ]]; then
      continue
    fi
    bad="${bad}${file}:${line_number}:${line}"$'\n'
  done < "$file"
done

if [ -n "$bad" ]; then
  printf '%s' "$bad"
  echo "::error::Unsupported or unpinned uses: reference above — use canonical block YAML and pin external Actions to a full 40-hex SHA with '# vX.Y.Z'."
  exit 1
fi

echo "All action references are SHA-pinned."
