# Share public feedback explicitly

Use the [public feedback form](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/new?template=feedback.yml)
for a concise problem and expected behavior. It publishes to
`mochan-tk/agentic-dev-kit-for-codex` under your existing GitHub account.
Everything submitted is **PUBLIC**. Review your text before submitting: omit
logs, attachments, credentials, private repository identifiers, local paths,
recovery records and adopter markers. The form requires your confirmation;
it does not redact text or technically prevent disclosure. Its manual text is
separate from the automatic reporter's eight-field draft.

## Draft an installer failure report without a clone

Use Bash 3.2+ on macOS/Linux, trusted `curl`, `mktemp`, `rm`, `rmdir`, and
`sha256sum` or `shasum`. Review the pinned
[reporter](https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/5ce4585fd9d52842423942fc64713fcd8748b47c/.github/scripts/report-installer-failure.sh)
and [library](https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/5ce4585fd9d52842423942fc64713fcd8748b47c/.github/scripts/feedback-lib.sh)
before trusting them. Both are unchanged accepted bytes. The block downloads
both complete files at that exact revision and verifies their SHA-256 before
executing the reporter. Hashes verify reviewed bytes, not publisher identity;
trusted tools and a trusted temporary parent (`TMPDIR` or `/tmp`) outside the
adopter are required. This is not a sandbox or protection from a hostile
same-user writer. No kit clone, installation or authentication change occurs.

The command below defaults to a local draft. It may observe OS/architecture,
Bash, gh and jq versions; it never reads adopter files or operation records.
No account, gh or jq is required for a draft. The eight fields are Script,
Failing line, Exit code, OS / arch, bash version, gh version, jq version and
Scaffold version. Missing values become `unknown`; the scaffold version is
always `unknown`. Optional line/exit values are a user report, not proof of an
earlier execution. No logs, free text, paths or repository identity are collected.

<!-- BEGIN feedback-delivery -->
```bash
(
  set -eu
  export LC_ALL=C
  umask 077
  scratch=$(mktemp -d "${TMPDIR:-/tmp}/codex-feedback.XXXXXX") || exit $?
  cleanup() {
    status=$?
    trap - EXIT
    if ! rm -f -- "$scratch/report-installer-failure.sh" "$scratch/feedback-lib.sh" || ! rmdir -- "$scratch"; then
      printf '%s\n' 'Feedback scratch cleanup incomplete; inspect locally.' >&2
      [ "$status" -ne 0 ] || status=3
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  revision=5ce4585fd9d52842423942fc64713fcd8748b47c
  for name in report-installer-failure.sh feedback-lib.sh; do
    case "$name" in
      report-installer-failure.sh) expected=9880d074c768c694816181af1f94e0288afa9a7cc15dc22537d701fcc9bd5e07 ;;
      feedback-lib.sh) expected=6dd41e7c3d5f7dea6e6735226cd794bf0d356e2b85bc637f2c027d50db756f20 ;;
    esac
    curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 --output "$scratch/$name" "https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/$revision/.github/scripts/$name" || exit $?
    [ -f "$scratch/$name" ] && [ ! -L "$scratch/$name" ] || exit 3
    if command -v sha256sum >/dev/null 2>&1; then
      actual=$(sha256sum "$scratch/$name") || exit $?
    else
      actual=$(shasum -a 256 "$scratch/$name") || exit $?
    fi
    [ "${actual%% *}" = "$expected" ] || { printf '%s\n' 'Feedback digest mismatch; nothing executed.' >&2; exit 3; }
  done
  bash "$scratch/report-installer-failure.sh" --draft
)
```
<!-- END feedback-delivery -->

To include a known failure, append `--line 42 --exit-code 7` to the final Bash
invocation, substituting canonical decimal line 1..999999 and exit code 1..255.
To send, replace only its `--draft` with `--send` and run the whole block from
your terminal. Do not pipe a `y` into it. Sending requires both the original
stdin and stderr terminals, existing authenticated `gh`, and empty `CI` and
`GITHUB_ACTIONS`. The reporter previews the fixed public destination, title
and exact body before asking `[y/N]`. Only a literal `y` or `Y` followed by
newline consents. Empty input, EOF or any other answer declines. No login,
permission change, labels, alternate recipient or automatic retry is offered.

Exit 0 means drafted or a confirmed public Issue URL; 2 is invalid usage;
3 is declined; 4 is send-unavailable; 5 is submission-unconfirmed. Acquisition,
integrity and cleanup errors are also non-success, not reporter verdicts.
An unconfirmed submission may have created an Issue: inspect your public
Issues before deciding whether to try again. The block never retries.

Cleanup removes only its two named downloads and attempts to remove the empty
private scratch directory. Unexpected entries remain for local inspection.
A cleanup failure makes an otherwise successful run non-success and preserves
an existing failure status. Abrupt termination may leave scratch. Neither
this command nor its cleanup changes adopter files or the Git index.

## Installation failures are a manual handoff

The Bash and thin PowerShell installation entrances print fixed links to this
guide and the form on failure. They do not load the reporting library, collect
metadata, download reporting code, prompt, or submit anything. Original failure
status and installation cleanup are retained; partial installation/staging
still requires the manual review described in the
[installation guide](source-first-installer.md). Success and help show no
failure advice. An initial HTTP failure before Bash starts cannot print these
links; a `curl | bash` caller still needs `pipefail` to observe that failure.

The form, guide and explicit sender are outside the unchanged 47-file payload.
The three [read-only checks](companion-checks.md) remain separate. Receiving
[classification and labels](ongoing-improvement.md) are explicit operations;
title recognition is not consent or identity proof. No receiver workflow or
schedule is active. This deliberately manual handoff is not the source's
automatic interactive installer offer. Tests execute this block with real
Bash/PTY and synthetic HTTP/GitHub; they do not submit live feedback, qualify
native Windows or establish current-version E01/runtime parity.
