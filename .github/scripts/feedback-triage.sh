#!/usr/bin/env bash
# Routing only; classification neither authenticates consent nor creates Tasks.
set -euo pipefail
export LC_ALL=C
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -I "$script_dir/ongoing-improvement.py" feedback "$@"
