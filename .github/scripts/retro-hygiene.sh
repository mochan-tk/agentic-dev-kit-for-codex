#!/usr/bin/env bash
# Explicit source-checkout companion. No installation or scheduled activation.
set -euo pipefail
export LC_ALL=C
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -I "$script_dir/ongoing-improvement.py" retro "$@"
