#!/usr/bin/env bash
# Source-derived from mochan-tk/agentic-dev-kit-for-copilot at
# fd265ddef150fab86cd54d0e383c2c25fe297ffb, feedback-lib.sh blob
# b09747ae0bc8ffa2183fec48b578b97cdb45c67b: _fb_field, _fb_isatty,
# fixed-field rendering and preview-before-consent. This standalone adaptation
# does not arm traps, read adopter markers, infer an adopter identity or log in.
# Sourcing this library defines functions only; it performs no operation.

_fb_field() {
  case "$1" in *$'\n'*|*$'\r'*) printf unknown; return 0 ;; esac
  local expression="$2"
  if [ "${#1}" -le "$3" ] && [[ "$1" =~ $expression ]]; then
    printf '%s' "$1"
  else
    printf unknown
  fi
}

_fb_isatty() { [ -t 0 ] && [ -t 2 ]; }

# Bound captured tool output in memory; discard stderr. A tool failure or
# overflow produces no field value. This is not a general process supervisor.
_fb_capture() {
  local captured
  # Sentinel retains terminal newlines until after the byte bound is checked.
  # Map NUL to a rejected one-byte control character before Bash can discard it.
  captured="$(set -o pipefail; { "$@" </dev/null | head -c 257 | tr '\000' '\001'; } 2>/dev/null; status=$?; printf .; exit "$status")" || return 1
  captured="${captured%.}"
  [ "${#captured}" -le 256 ] || return 1
  printf '%s' "$captured"
}

_fb_gh_version() {
  local raw first rest expression
  raw="$(_fb_capture gh --version)" || { printf unknown; return 0; }
  first="${raw%%$'\n'*}"
  # Official gh output has a version line and may include its public release
  # URL. Do not promote a valid-looking first line of arbitrary multiline data.
  if [ "$raw" != "$first" ]; then
    rest="${raw#*$'\n'}"
    expression='^https://github[.]com/cli/cli/releases/tag/v[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}$'
    [[ "$rest" =~ $expression ]] || { printf unknown; return 0; }
  fi
  expression='^gh version ([0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3})( [(][0-9]{4}-[0-9]{2}-[0-9]{2}[)])?$'
  if [[ "$first" =~ $expression ]]; then printf '%s' "${BASH_REMATCH[1]}"; else printf unknown; fi
}

_fb_render() {
  local line="$1" exit_code="$2" os arch bash_version gh_version jq_version
  os="$(_fb_capture uname -s)" || os=unknown
  case "$os" in Darwin|Linux|FreeBSD|OpenBSD|NetBSD) ;; *) os=unknown ;; esac
  arch="$(_fb_capture uname -m)" || arch=unknown
  case "$arch" in x86_64|aarch64|arm64|i386|i686|armv7l|ppc64le|s390x|riscv64) ;; *) arch=unknown ;; esac
  bash_version="$(_fb_field "${BASH_VERSION:-}" '^[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}([(][0-9]{1,3}[)])?(-release)?$' 40)"
  gh_version=unknown
  if command -v gh >/dev/null 2>&1; then gh_version="$(_fb_gh_version)"; fi
  jq_version=unknown
  if command -v jq >/dev/null 2>&1; then
    jq_version="$(_fb_capture jq --version)" || jq_version=unknown
    jq_version="$(_fb_field "$jq_version" '^jq-[0-9]{1,3}[.][0-9]{1,3}([.][0-9]{1,3})?(-[0-9]{1,3}-apple-g[0-9a-f]{7,12}-dirty)?$' 40)"
  fi
  # These globals are always constructed here, never inherited configuration.
  FB_TITLE="[adopter-feedback] scaffold-init failed (exit $exit_code)"
  FB_BODY="<!-- adopter-feedback:v1 -->

User-reported local installer failure context, not proof of a historical run.
Only the eight allowlisted fields below are included; no logs, paths,
repository identity, credentials or free-form failure text are collected.

| Field | Value |
|---|---|
| Script | scaffold-init |
| Failing line | $line |
| Exit code | $exit_code |
| OS / arch | $os / $arch |
| bash version | $bash_version |
| gh version | $gh_version |
| jq version | $jq_version |
| Scaffold version | unknown |"
}

_fb_preview() {
  printf 'Destination: https://github.com/mochan-tk/agentic-dev-kit-for-codex\n'
  printf 'Sending creates a PUBLIC issue under your existing GitHub account.\n'
  printf 'Title: %s\n\n%s\n' "$FB_TITLE" "$FB_BODY"
}

feedback_report() {
  local mode=draft mode_seen='' line=unknown exit_code=unknown answer='' response='' expression
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --draft|--send)
        [ -z "$mode_seen" ] || { _fb_usage; return 2; }
        mode="${1#--}"; mode_seen=1; shift ;;
      --line)
        [ "$#" -ge 2 ] && [ "$line" = unknown ] || { _fb_usage; return 2; }
        expression='^[1-9][0-9]{0,5}$'
        [[ "$2" =~ $expression ]] || { _fb_usage; return 2; }
        line="$2"; shift 2 ;;
      --exit-code)
        [ "$#" -ge 2 ] && [ "$exit_code" = unknown ] || { _fb_usage; return 2; }
        expression='^[1-9][0-9]{0,2}$'
        [[ "$2" =~ $expression ]] && [ "$2" -le 255 ] || { _fb_usage; return 2; }
        exit_code="$2"; shift 2 ;;
      *) _fb_usage; return 2 ;;
    esac
  done
  if [ "$mode" = send ]; then
    if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ] || ! _fb_isatty || ! command -v gh >/dev/null 2>&1; then
      printf 'result=send-unavailable\n' >&2; return 4
    fi
  fi
  _fb_render "$line" "$exit_code"
  if [ "$mode" = draft ]; then
    _fb_preview
    printf 'result=drafted\n' >&2; return 0
  fi
  _fb_preview >&2
  printf 'Send this public report? [y/N] ' >&2
  # Bash read/variables discard NUL. Encode the bounded first line before
  # touching a shell variable: accept only literal y/Y followed by newline.
  # Normal terminal EOF declines; unknown bytes/errors cannot become consent.
  answer="$(set -o pipefail; { head -n 1 | head -c 3 | od -An -tx1; } 2>/dev/null)" || answer=''
  printf '\n' >&2
  expression='^[[:space:]]*(79|59)[[:space:]]+0a[[:space:]]*$'
  [[ "$answer" =~ $expression ]] || { printf 'result=declined\n' >&2; return 3; }
  # Full github.com destination plus fixed gh hints; no labels, auth or retry.
  # Never project raw response/stderr: even a failure may have created an Issue.
  response="$(GH_HOST=github.com GH_REPO=mochan-tk/agentic-dev-kit-for-codex GH_DEBUG='' GH_PROMPT_DISABLED=1 \
    _fb_capture gh issue create --repo https://github.com/mochan-tk/agentic-dev-kit-for-codex \
      --title "$FB_TITLE" --body "$FB_BODY")" || {
    printf 'result=submission-unconfirmed\n' >&2; return 5;
  }
  expression='^https://github[.]com/mochan-tk/agentic-dev-kit-for-codex/issues/[1-9][0-9]{0,19}$'
  if [[ "$response" =~ $expression ]]; then
    printf '%s\n' "$response"
    printf 'result=confirmed\n' >&2; return 0
  fi
  printf 'result=submission-unconfirmed\n' >&2; return 5
}

_fb_usage() {
  printf 'Usage: bash report-installer-failure.sh [--draft|--send] [--line 1..999999] [--exit-code 1..255]\n' >&2
}
