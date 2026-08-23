#!/usr/bin/env bash
# Fail when a job-level permissions block cannot authorize checkout.

set -euo pipefail

DIR="${1:-.github/workflows}"
[ -d "$DIR" ] || { echo "error: $DIR not found" >&2; exit 2; }

findings=""
checked=0

for workflow in "$DIR"/*.yml "$DIR"/*.yaml; do
  [ -e "$workflow" ] || continue
  report="$(awk '
    /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
    in_jobs && /^[^[:space:]#]/ {
      if (job != "") print job "\t" hasperm "\t" validcontents "\t" invalidcontents "\t" hascheckout
      job = ""
      in_jobs = 0
      next
    }
    !in_jobs { next }
    /^  [a-zA-Z_][a-zA-Z0-9_-]*:[[:space:]]*$/ {
      if (job != "") print job "\t" hasperm "\t" validcontents "\t" invalidcontents "\t" hascheckout
      job = $1
      sub(/:$/, "", job)
      hasperm = 0
      validcontents = 0
      invalidcontents = 0
      hascheckout = 0
      inperm = 0
      next
    }
    job == "" && /^[[:space:]]+[^[:space:]#]/ {
      print "__PARSE_ERROR__\t0\t0\t0\t0"
      exit
    }
    /^  [^[:space:]#]/ {
      print "__PARSE_ERROR__\t0\t0\t0\t0"
      job = ""
      exit
    }
    job == "" { next }
    /^    permissions:[[:space:]]*$/ { hasperm = 1; inperm = 1; next }
    /^    permissions:/ {
      print "__PARSE_ERROR__\t0\t0\t0\t0"
      job = ""
      exit
    }
    /^    [a-zA-Z]/ { inperm = 0 }
    inperm && /^      contents:/ {
      value = $0
      sub(/^      contents:[[:space:]]*/, "", value)
      sub(/[[:space:]]*#.*/, "", value)
      sub(/[[:space:]]+$/, "", value)
      if (value == "read" || value == "write") validcontents = 1
      else invalidcontents = 1
      next
    }
    /actions\/checkout/ { hascheckout = 1 }
    END {
      if (job != "") print job "\t" hasperm "\t" validcontents "\t" invalidcontents "\t" hascheckout
    }
  ' "$workflow")"

  workflow_checked=0
  while IFS=$'\t' read -r job hasperm validcontents invalidcontents hascheckout; do
    [ -n "$job" ] || continue
    if [ "$job" = "__PARSE_ERROR__" ]; then
      findings="${findings}${workflow}: unsupported YAML shape; expected canonical block-style jobs and permissions."$'\n'
      continue
    fi
    checked=$((checked + 1))
    workflow_checked=$((workflow_checked + 1))
    if [ "$hasperm" = "1" ] && [ "$hascheckout" = "1" ] \
      && { [ "$validcontents" = "0" ] || [ "$invalidcontents" = "1" ]; }; then
      findings="${findings}${workflow}: job '${job}' declares permissions and checks out"$'\n'"    the repository, but grants no usable 'contents' scope (expected read or write)."$'\n'
    fi
  done <<EOF
$report
EOF
  if [ "$workflow_checked" -eq 0 ]; then
    findings="${findings}${workflow}: no canonical block-style jobs could be classified."$'\n'
  fi
done

if [ -n "$findings" ]; then
  printf 'FAIL: %s' "$findings"
  echo "      A job-level permissions block replaces the workflow-level one."
  echo "      Add an explicit 'contents: read' grant unless write is genuinely required."
  exit 1
fi

echo "check-workflow-permissions: OK — $checked job(s) checked; every checkout job with job-level permissions grants contents."
