# Run the read-only checks without a kit clone

Choose one check below, set its explicit inputs, then run its Bash block. Each
block downloads **one explicitly pinned helper**, verifies its SHA-256, and only
then executes the complete file. Governance is bound to the implementation
revision written in its block; worktree and connector checks remain at accepted
revision `2213860cbb16bf80d80d1c388c31bc75ae12bb7e`. Moving the governance pin is
a reviewed product change, not automatic tracking of main. No installer,
dispatcher, automatic repair or kit
clone is needed. These helpers remain outside the 47 installed files.

Use Bash 3.2+ on macOS/Linux, trusted `curl`, `mktemp`, `rm`, `rmdir`, and either
`sha256sum` or `shasum`. Governance additionally needs existing authenticated
`gh` and `jq`; worktree needs Git and `jq`; connectors need standard Unix text
tools. These commands never log in or change permissions/settings for you.
Native Windows execution is unmeasured; there is no new PowerShell launcher.

Read the fixed helper before trusting it. Hashes check reviewed bytes, not
publisher identity, and do not sandbox the helper or trusted local tools.
The temporary parent (`TMPDIR`, or `/tmp`) must be trusted and outside the
target. Keep the target and claims unchanged during observation. This is not
protection from a hostile same-user writer or atomic filesystem observation.

## Governance: observe GitHub settings

Set actual repository, required check contexts, declared profile and posture:

```bash
export CHECK_REPO='owner/repository'
export CHECK_CONTEXTS='actual-check-one,actual-check-two'
export CHECK_PROFILE='single-maintainer' # explicitly select solo, team or single-maintainer
export CHECK_POSTURE='adopter' # or source-template, only when applicable
```

This sensor uses your existing `gh` authorization for **GET-only** observations.
Do not grant new access merely to obtain a successful result. Missing access or
incomplete evidence stays `UNKNOWN`/`UNCHECKABLE`; observations do not approve
bypass actors, change Rulesets or grant permission to write. Output can name
observed actors/checks: review it locally before sharing; do not post raw output.
Single-maintainer expects PR/check requirements, zero approving reviews and
no bypass across all contributing Rulesets. Missing structured review data or
conflicting residual gates are not treated as success.

<!-- BEGIN companion-governance -->
```bash
(
  set -eu
  : "${CHECK_REPO:?set the actual repository}" "${CHECK_CONTEXTS:?set actual checks}" "${CHECK_PROFILE:?select solo, team or single-maintainer}" "${CHECK_POSTURE:?select the actual posture}"
  export LC_ALL=C
  umask 077
  scratch=$(mktemp -d "${TMPDIR:-/tmp}/codex-companion.XXXXXX") || exit $?
  cleanup() {
    status=$?
    trap - EXIT
    if ! rm -f -- "$scratch/helper.sh" || ! rmdir -- "$scratch"; then
      printf '%s\n' 'Companion scratch cleanup incomplete; inspect locally.' >&2
      [ "$status" -ne 0 ] || status=3
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  revision=2213860cbb16bf80d80d1c388c31bc75ae12bb7e
  expected=ebd7d548506797edc5ee04c7203b468d7ec69417b0bcb06d7fde88fb53593624
  curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 --output "$scratch/helper.sh" "https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/$revision/.github/scripts/governance-status.sh" || exit $?
  [ -f "$scratch/helper.sh" ] && [ ! -L "$scratch/helper.sh" ] || exit 3
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$scratch/helper.sh") || exit $?
  else
    actual=$(shasum -a 256 "$scratch/helper.sh") || exit $?
  fi
  [ "${actual%% *}" = "$expected" ] || { printf '%s\n' 'Companion digest mismatch; nothing executed.' >&2; exit 3; }
  bash "$scratch/helper.sh" -R "$CHECK_REPO" --checks "$CHECK_CONTEXTS" --profile "$CHECK_PROFILE" --posture "$CHECK_POSTURE"
)
```
<!-- END companion-governance -->

## Worktree: check a planned action without doing it

Supply the actual Git worktree root, planned branch, actual writer reference
and a current claim readback file. The JSON shape is `{"claims":[...]}`; each
entry has `branch`, `worktree`, `writer`, and `state` (`active` or `released`).
Do not invent a claim or automatically derive authority from a local branch.
The supervisor must verify the current durable records and actual worker state.

```bash
export CHECK_TARGET='/path/to/project worktree'
export CHECK_BRANCH='feature/planned-change'
export CHECK_WRITER='actual-writer-reference'
export CHECK_CLAIMS='/path/to/current claim readback.json'
export CHECK_ACTION='push' # push, claim or archive; observation only
```

The helper neither pushes nor claims, archives, removes, prunes or unlocks.
Detached push, occupied branch and conflicting declared claims refuse.
`archive` always returns a warning/non-success pending human evidence review.
Success is no observed conflict, **not an exclusive lock or write approval**.

<!-- BEGIN companion-worktree -->
```bash
(
  set -eu
  : "${CHECK_TARGET:?set the actual worktree root}" "${CHECK_BRANCH:?set the planned branch}" "${CHECK_WRITER:?set the actual writer}" "${CHECK_CLAIMS:?supply the current claim readback}" "${CHECK_ACTION:?select the planned action}"
  export LC_ALL=C
  umask 077
  scratch=$(mktemp -d "${TMPDIR:-/tmp}/codex-companion.XXXXXX") || exit $?
  cleanup() {
    status=$?
    trap - EXIT
    if ! rm -f -- "$scratch/helper.sh" || ! rmdir -- "$scratch"; then
      printf '%s\n' 'Companion scratch cleanup incomplete; inspect locally.' >&2
      [ "$status" -ne 0 ] || status=3
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  revision=2213860cbb16bf80d80d1c388c31bc75ae12bb7e
  expected=5a6d3cfa7260e641380cf78766afd60198c9af4968bb8238afa3f2c684589c20
  curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 --output "$scratch/helper.sh" "https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/$revision/.github/scripts/worktree-preflight.sh" || exit $?
  [ -f "$scratch/helper.sh" ] && [ ! -L "$scratch/helper.sh" ] || exit 3
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$scratch/helper.sh") || exit $?
  else
    actual=$(shasum -a 256 "$scratch/helper.sh") || exit $?
  fi
  [ "${actual%% *}" = "$expected" ] || { printf '%s\n' 'Companion digest mismatch; nothing executed.' >&2; exit 3; }
  bash "$scratch/helper.sh" --target "$CHECK_TARGET" --branch "$CHECK_BRANCH" --writer "$CHECK_WRITER" --claims "$CHECK_CLAIMS" --action "$CHECK_ACTION"
)
```
<!-- END companion-worktree -->

## Connectors: validate local definition structure

```bash
export CHECK_TARGET='/path/to/project with connectors'
```

The explicit existing target must contain `.github/connectors/`, its framework
files and at least one definition. This checks structural text only. It does
not connect to a service, activate a connector, establish context sufficiency
or verify source authenticity. Only the helper download uses the network.

<!-- BEGIN companion-connectors -->
```bash
(
  set -eu
  : "${CHECK_TARGET:?set the actual target directory}"
  export LC_ALL=C
  umask 077
  scratch=$(mktemp -d "${TMPDIR:-/tmp}/codex-companion.XXXXXX") || exit $?
  cleanup() {
    status=$?
    trap - EXIT
    if ! rm -f -- "$scratch/helper.sh" || ! rmdir -- "$scratch"; then
      printf '%s\n' 'Companion scratch cleanup incomplete; inspect locally.' >&2
      [ "$status" -ne 0 ] || status=3
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  revision=2213860cbb16bf80d80d1c388c31bc75ae12bb7e
  expected=a9c4941b5802f5607d9dc0d37f87b7658a3b798c85c511ae3042ef27f10f413d
  curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 --output "$scratch/helper.sh" "https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/$revision/.github/scripts/check-connectors.sh" || exit $?
  [ -f "$scratch/helper.sh" ] && [ ! -L "$scratch/helper.sh" ] || exit 3
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$scratch/helper.sh") || exit $?
  else
    actual=$(shasum -a 256 "$scratch/helper.sh") || exit $?
  fi
  [ "${actual%% *}" = "$expected" ] || { printf '%s\n' 'Companion digest mismatch; nothing executed.' >&2; exit 3; }
  bash "$scratch/helper.sh" --target "$CHECK_TARGET"
)
```
<!-- END companion-connectors -->

## Results and limits

The block preserves the helper's stdout, stderr and exit status: 0 is the
helper's bounded success, 1 an observed refusal, 2 a usage/dependency error,
and 3 unknown/uncheckable evidence. Download/hash/setup failures are also
non-success and never execute downloaded content. Do not interpret a transport
failure as a helper verdict. Nothing is retried automatically.

An EXIT trap removes only the invocation-owned downloaded file and attempts
`rmdir` on its private scratch. Unexpected additional entries are retained,
not recursively deleted. Failed cleanup turns an otherwise successful run
into non-success; it does not hide an existing helper failure. The helpers
retain their existing temporary-file behavior. Abrupt termination/power loss
may leave scratch; no guaranteed crash cleanup is claimed.

Regressions extract and execute these exact documentation blocks with real
Bash/Git/filesystems and synthetic HTTP/GitHub. This is not live governance,
Windows qualification or runtime parity. The selected fixed source is not
automatically advanced when main changes. See the
[detailed helper semantics](source-first-installer.md#governance-worktree-and-retro-procedures),
[connector scope](source-first-installer.md#optional-offline-connector-definition-validation)
and [known limitations](../known-limitations.md). The separate consent-gated
failure reporter still requires a reviewed checkout; it is not part of these
read-only commands.
