#!/usr/bin/env bash
# Optional explicit companion; never sourced by scaffold-init or its traps.
set -u
export LC_ALL=C
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" || exit 2
# shellcheck source=.github/scripts/feedback-lib.sh
source "$script_dir/feedback-lib.sh"
feedback_report "$@"
