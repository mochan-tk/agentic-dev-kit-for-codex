# ADR-0008: Minimal Codex execution loop

- Status: T11 deterministic offline harness accepted; T12 live-runtime
  qualification is the sole active frontier in this tree
- Decision date: 2026-08-28
- Bounded amendment date: 2026-08-30
- Agreement-v2 date: 2026-08-31
- Task: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23>
- Active Task: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25>
- Agreement-v2 decision: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-5472720734>
- T12 activation amendment: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25#issuecomment-5480062206>
- Parent Epic: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/22>

## Context

Phase 1 established portable contracts and repository Skills, but it deliberately
did not implement an execution envelope, loop events, a Codex adapter, custom
runtime roles, or a live Task ritual. Implementing each surface independently
would postpone evidence that a bounded Task can traverse a complete loop.

## Decision

T11 implements one deliberately narrow deterministic offline harness:

```text
human-authored envelope
-> deterministic Python controller
-> deterministic fake logical worker
-> adapter-normalized loop events and execution result
-> fresh deterministic read-only verifier
-> receipt validation, dry-run, zero-write, idempotency, conflict, and read-back fixtures
```

The Python adapter is the only supervisor/controller. The model authors only a
bounded `codex-final-response/v1` value. The adapter, not the model, establishes
process, event, Git, digest, and verifier facts. Receipt publication is a
separate explicit actuator.

The representative offline target is a private synthetic Git repository whose only
worktree entry is regular mode-`100644` `work-item.txt`. Its exact bytes change
from `status=pending\n` to `status=complete\n`; all other filesystem or Git
change is a failure. The adapter's deterministic offline mode starts exactly
one fake logical worker and a fresh Python verifier process. T11 does not claim
real-Codex-worker success from that fixture.

The accepted T11 agreement-v2 historical status is exact:

```text
runtime_harness = minimal-offline-implemented
live_codex_execution = deferred-to-T12
sandbox_compatibility = unresolved-non-success
runtime_receipt_apply = deferred-to-T12
Phase 2 = incomplete
repository = incomplete
release_blocked = true
```

This tree activates T12 while preserving the Phase 2 phase origin at commit
`36c7eabecf7a56eb2a1c2c8f2c4d8fcb371c31c2` and tree
`1c1f46ad20dd289a713663c84eaf1dbb62840deb`. T12 alone is based on accepted
T11 merge `4a85a007ed62795b48bcbce04f6b7e5482e71e82` and tree
`49afe003de2bbb04249d6f4c36ea6462c271c26f`. Current live evidence is external
GitHub state and is not embedded as mutable truth in this tree.

AC-01 through AC-12 remain applicable only inside their offline/static
boundary. AC-13 is superseded for T11 and deferred to T12; it is neither passed
nor omitted. AC-14 is unchanged, and AC-15 remains the owner merge gate for
the deterministic offline harness. Full K09, K10, K11, and K12 are not claimed.

All dynamic Task and context bytes travel on stdin. Worker argv may include the
static reviewed `task_worker` developer-instruction string, bound by SHA-256,
but contains no Task prompt. Commands use argv arrays with `shell=false`, an
exact cwd, a minimal environment, bounded output/time, process-group
TERM/KILL/reap handling, and pre/post Git-state verification.

Before any later T12 live execution, a sensor must prove a supported runtime
profile. `profile-drift`, `unsupported-client` (including an unapproved
prerelease), `UNKNOWN`, and `UNCHECKABLE` are non-success and block the worker.
Help output alone is not a
configuration-recognition probe, and `codex doctor --json` is diagnostic
health evidence rather than an effective-configuration attestation. Only
allowlisted check ID, category, and status fields leave the diagnostic probe;
warning or failure blocks only when it belongs to a T11-required auth, config,
runtime, or sandbox check. An unrelated advisory warning yields
`pass-with-advisory-warning`. The adapter records its reviewed documented-key
intent and digest as adapter-authored evidence with
`effective_configuration_proven=false`.

The sensor keeps `provider_isolation_status`, `mount_boundary_status`,
`process_cleanup_status`, `codex_sandbox_network_status`,
`shell_environment_status`, `config_status`, and `auth_status` as independent
lanes. A failure in shell, config, auth, or Codex sandbox/network evidence does
not rewrite a separately observed provider-isolation fact. Release class is
derived from exact version syntax. A stable client becomes `match` only when
every independently required lane passes; the full sensor is rerun and
reconciled immediately before the one T12 live worker.

Authentication classification is derived from a dedicated bounded probe of
`codex login status`. The official 0.150.1 client writes its successful status
to stderr, so the adapter classifies only exact allowlisted success bytes:
`Logged in using ChatGPT` is `signed-in-client`, and the documented exact
API-key success form is `api-key`. A nonzero exit is `unavailable`; a zero exit
with any other output is `unknown`. Only that safe classification is durable;
raw stdout/stderr, credential material, and private paths are discarded.

The no-model sandbox probe adopts Option B for official 0.150.1. Its exact
slice is `codex <reviewed-runtime-overrides> sandbox --permission-profile
:read-only -C <synthetic-root> -- <probe-argv>`. The managed `:read-only`
profile supplies a read-only filesystem and restricted network, while `-C`
binds the synthetic root. T11 requires the explicit `--` delimiter. The argv-
policy gate rejects state flags mixed with Option B, `-C` without a permission
profile, an omitted delimiter, bypass arguments, and unsupported or conflicting
arguments.

The Stage A qualification boundary used one fresh T11-only Colima Linux VM per
attempt with VZ and native `aarch64`, named from the exact public head. The
guest clones that head onto its private disk. It neither mounts the host repository
nor reuses the default profile, existing runtime data, or host credentials.
The sole permitted host mount is Colima 0.10.1's unavoidable provider-internal
cache entry, redirected to a fresh attempt-only root and proven read-only; no
other shared mount is permitted. Raw paths remain local-only. The closed
provider evidence is adapter/owner-authored and explicitly not a Codex-issued
authenticated attestation. The bounded outer-containment evidence is
established by this fresh VM, the closed mount boundary, exact PR head/tree, a
dedicated `CODEX_HOME`, exact lifecycle destruction, and profile-absence
read-back.

Owner-authored control-plane evidence must prove pre-create absence of both
the exact profile and its runtime data. The attempt reuses no existing VM,
container, volume, default profile, or additional disk; activation remains
unchanged and repository/runtime data stays on the private VM disk. A closed
safe-field canonical digest binds Colima 0.10.1, chronology, profile,
backend/architecture, configuration, and instance identity without raw paths.

The candidate client is exactly official stable `codex-cli 0.150.1` for Linux
ARM64. Its archive must match SHA-256
`5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264`,
and the extracted binary is digested independently. The runtime uses a private
guest `CODEX_HOME`; credentials and device-authorization material remain out
of every artifact and receipt.

The next bounded attempt first qualifies the documented bubblewrap
prerequisite inside a fresh, unauthenticated disposable Colima VM. The
controller, never a model, observes only allowlisted guest distribution,
version, kernel, architecture, and AppArmor fields and then invokes fixed
shell-free package-manager argv. A passing boundary is Ubuntu 24.04 `noble`
on Linux `aarch64`, with AppArmor enabled and
`kernel.apparmor_restrict_unprivileged_userns=1`. The controller pins
`bubblewrap=0.9.0-1ubuntu0.1`, `apparmor` and `apparmor-profiles` at
`4.0.1really4.0.1-0ubuntu0.24.04.7`, and
`git=1:2.43.0-1ubuntu7.3`, all for Ubuntu Noble `arm64`. It verifies
`/usr/bin/bwrap` as `bubblewrap 0.9.0` with SHA-256
`ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8`.
It also records a bounded help-output digest rather than the output.

The fixed package operation and Git observation occur before the repository
clone. The guest clone uses the exact `/usr/bin/git` binding only after its
version is exactly `git version 2.43.0` and its SHA-256 is
`aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942`.
Only allowlisted package, architecture, version, and digest facts are durable.
The exact public PR head/tree is then cloned and checked out on the VM private
disk; the host repository is never mounted as a substitute. Those pre-clone
facts are carried by the closed owner/controller-authored
`repository.git_bootstrap` stdin record. Before the adapter's first repository
Git operation, it re-observes the exact package/architecture and both fixed and
PATH-resolved executable bindings; any mismatch stops before repository Git.
Every later provider Git operation revalidates the root-owned, non-group/world-
writable `/usr`, `/usr/bin`, and `/usr/bin/git` namespace and invokes the fixed
path without PATH re-resolution. A head/tree-derived clone-contract digest binds
the reviewed shell-free clone/checkout/verification templates and expected clean
result. This is owner/controller-authored pre-clone evidence plus deterministic
post-clone equality checking; repository code does not authenticate the asserted
pre-clone chronology itself.

Because the approved Ubuntu 24.04 AppArmor restriction is active, the
controller installs the packaged official `bwrap-userns-restrict` profile
from `/usr/share/apparmor/extra-profiles/bwrap-userns-restrict` to
`/etc/apparmor.d/bwrap-userns-restrict`, verifies source and installed
SHA-256
`11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9`,
loads it with `apparmor_parser --replace`, and confirms the profile is in
enforce mode by requiring both source-defined profiles, `bwrap (enforce)` and
`unpriv_bwrap (enforce)`. A transient `bwrap//&unpriv_bwrap` execution label
cannot substitute for either loaded profile. T11 does not enable
`features.use_legacy_landlock` and does not globally disable the AppArmor
unprivileged-user-namespace restriction.

Every reviewed clone, checkout, and Git verification argv is prefixed by a
static shell-free `python3 -I` wrapper restricted to `/usr/bin/git`. The wrapper
sets private process umask `0077` before `execve`, projecting tracked
non-executable files as `0600` even when the guest SSH session defaults to
`0002`. Provider-bound Stage A/live evidence requires exact `0600`; ordinary
offline/checker reads may also accept `0644`. Both projections are single-link
and reject group/world writes, Git tree mode `100644` remains canonical, and
the repository JSON non-writable guard is unchanged.

The outer controller supplies an inherited-none environment to that wrapper.
Only reviewed fixed Git/locale/path values plus one absolute private-VM home
path are accepted; any extra controller key is a bounded failure. The home is
opened no-follow and must be empty, current-uid, mode `0700`, and binding-stable;
Git receives only its inherited descriptor projection. Global Git config is
fixed to `/dev/null`, and system config/attributes are disabled. The fresh-image
`/usr/bin/python3` is an explicit provider-side pre-clone TCB, not an
independently pinned T11 attestation.

The prerequisite is successful only when the controller runs this exact
direct smoke argv without `sudo`, as the guest non-root user, with
`shell=false` and exit zero:

```text
/usr/bin/bwrap --unshare-user --unshare-net --ro-bind / / /bin/true
```

The canonical fixed controller-argv list has SHA-256
`3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff`;
its pre-clone Git qualification subset has SHA-256
`a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc`;
the smoke argv alone has SHA-256
`8e8d9907189e3b2dbcf3170d20d3dad2cfe6269da5148946ae79c4aa06843f08`.

Raw stderr is discarded and failure is reduced to a fixed reason code. Codex
shell-environment and sandbox/network probes are not invoked unless this
direct smoke passes. Stage A.1 remains bounded non-success evidence; only this
narrow prerequisite set is qualified and frozen. Stage A.2 does not alter its
package, AppArmor, sysctl, smoke, or Codex-version inputs. The prerequisite is
distinct gate evidence: it does not
overwrite provider isolation, mount boundary, process cleanup, Codex
sandbox/network, shell environment, configuration, or authentication status.

## Security and privacy consequences

### T12 bounded sandbox-launch remediation (2026-09-05)

The [bounded owner plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25#issuecomment-5550009263)
authorizes offline investigation and safety-preserving remediation only. Both
T12 Stage A attempts remain non-success; the retry allowance is exhausted.
No third attempt, renamed diagnostic VM, authentication, model, live worker,
receipt application, Stage B, or merge is authorized by this correction.

Static review of official Codex 0.150.1 source commit
`90854393966b21e9ebfd21b122334eb09a20c93d`, `codex-rs/cli/src/main.rs`
blob `455682e14248c73e76adc72cce97b6c1bff46402`, established a sufficient
shared launch incompatibility: the CLI rejects `--strict-config` for `sandbox`
before dispatch. Its `debug_sandbox` loader intentionally uses
`strict_config=false`. Only the sandbox configuration argv omits that flag;
doctor and the live worker retain strict configuration. All reviewed `-c`
overrides, environment values, Option B, configuration-intent digest, image
binding, provider isolation, network policy, pinned client, and qualified
AppArmor/bubblewrap prerequisites are unchanged.

This source-proven defect does not recover the prior discarded stderr or
prove it was the sole failure. Self-validation, synthetic processes, and green
offline CI do not prove real CLI acceptance or resolved sandbox compatibility.

Optional `profile --probe-only --launch-diagnostics` emits a separate
adapter-authored `t12-sandbox-launch-diagnostics/v1` transport wrapper around
the unchanged, closed `runtime-profile/v1`. It requires the approved provider
and an exact unavailable-auth classification before diagnostic capture. The
existing auth observation is reused, and each shell/network lane still
launches at most its one existing process. Only these unauthenticated,
no-model probes may transiently capture at most 4096 stderr bytes in memory.
The adapter immediately classifies/discards them before the existing lane
classifiers; raw stderr, exception text, argv, private paths, and environment
values never enter either record. Diagnostic status, fixed stage/reason,
numeric exit code, and numeric signal are supplemental facts, not a new
runtime gate or authenticated attestation. Unknown stderr stays unclassified
non-success. Timeout, overflow, signal, spawn failure, and incomplete reap
remain distinct; only a failure at the actual process-spawn boundary is
called a spawn failure. Existing profile statuses and lane semantics remain
unchanged, and no launch classification promotes a profile or lane.

Any future minimal measurement needs a separate owner replan against the
exhausted attempt allowance. The proposed measurement is the existing exact
unauthenticated profile command plus `--launch-diagnostics`, preserving all
provider/prerequisite gates and one process per shell/network lane. It would
distinguish pre-dispatch rejection from unclassified process failure using
only the safe wrapper. No such command is executed by this remediation.

- The worker has `workspace-write`, approval `never`, network disabled, no
  additional writable roots, ephemeral history, hooks/apps/agents/web search/
  feedback/memory disabled, strict config, and ignored user config. Its argv
  never disables execpolicy rules and never uses a dangerous bypass flag; the
  private runtime home supplies the reviewed rules surface.
- The shell environment begins empty and adds only the verified executable
  path, private HOME/TMPDIR, locale/timezone, and deterministic Git/Python
  values. No credential, proxy, or unrelated host value is copied.
- Shell observation uses a closed status/reason record. It stores only the
  unexpected-key count, canonical sorted key-name digest, and secret-shaped
  count. Official Codex 0.150.1 source commit
  `90854393966b21e9ebfd21b122334eb09a20c93d` supports only
  `CODEX_SANDBOX_NETWORK_DISABLED` as an injected key on this Linux debug-
  sandbox path; the marker must equal `1` and the forbidden sentinel must be
  absent.
- Network evidence requires an accepted-and-closed unsandboxed control
  connection, different hashed parent/sandbox network namespaces, the exact
  marker, a denied sandboxed `connect(2)`, and bounded process reap. Only
  `EPERM`, `EACCES`, `ENETUNREACH`, `EHOSTUNREACH`, and `ECONNREFUSED` are
  accepted under all gates. Raw namespace IDs, stdout, stderr, and environment
  output are never durable.
- Unexpected project config, hooks, agents, Skills, AGENTS guidance, MCP data,
  symlinks, or extra files prevent invocation.
- Durable records contain allowlisted digests and outcomes, never raw JSONL,
  reasoning, stderr, transcripts, credentials, environment dumps, or private
  local paths.
- Exact-worker-argv validation records no exception text, raw argv, or private
  path. Failure records contain only a fixed reason code and one of these
  stages: `load-envelope`, `load-static-role`, `environment-contract`,
  `build-argv`, `argv-policy`, `schema-binding`, or `filesystem-binding`.
- Separate no-follow `.git` content and same-target device/inode binding
  inventories plus independent semantic verification reject hidden refs,
  byte-identical namespace replacement, unreachable objects, split/shared
  indexes, config/hooks, and other Git-internal changes even if a caller forges
  its pre-state.
- A single private execution root encloses the target, HOME, and TMPDIR. Its
  bounded no-follow before/after inventory includes persistent membership,
  bytes, bindings, modes, timestamps, xattr names/value digests, and `st_flags`
  where exposed, allowing only the exact owned-leaf transition. It does not
  observe arbitrary host paths or prove transient create/delete activity,
  portable ACL equivalence, or kernel containment.
- The append-only receipt implementation validates four native artifacts and derives its
  cross-bound projection. Native JSON provenance remains unsigned/unverified.
  It uses a fresh observation, structured limitations, and an idempotent
  attempt/digest marker with bounded all-attempt scanning. An exact existing
  receipt is idempotent, while a different-attempt marker or conflicting
  same-attempt marker fails closed. Read-back reconciles uncertain POST
  outcomes without creating a second durable runtime receipt. T11 validates
  these behaviors with deterministic fixtures only; it does not apply a
  runtime receipt.
- Linux `/proc` start ticks or Darwin high-resolution `proc_pidinfo` birth
  tokens bind observed descendant signals across reparenting/setsid and reject
  PID reuse. This process-table tracking is best-effort cleanup evidence, not
  kernel-enforced containment. T11 does not claim full escaped-descendant
  process-lifetime containment; that stronger control is deferred to T13. The
  approved disposable-VM outer boundary remains mandatory for live `match`.
- Any T12 runtime receipt application occurs before provider destruction. The receipt
  records the pre-live destruction obligation without claiming completion;
  destroy request/completion and profile-absence read-back are later,
  append-only owner/adapter evidence.
- The T11 lifecycle actuator was fixture-tested against Issue #23 and PR #24
  and was not applied. T12 dynamically binds its exact same-repository PR,
  non-fork head branch, head, tree, and checks through GitHub read-back before
  live actuation. Runtime `--apply` requires the exact deterministic digest
  emitted by the preceding `--dry-run`; this binds the two operations but is
  not an authenticated attestation that a human ran either command. After the
  single runtime receipt is canonically read back, the T12 lifecycle actuator
  accepts a separate completion record and appends one Issue #25 comment, not
  a second runtime receipt or a PR copy. It requires receipt -> destroy request
  -> destroy completion -> profile, runtime-data, and tracked-process absence
  read-backs. All lifecycle timestamps have a 300-second maximum future skew,
  and every absence observation must independently be no more than 3600
  seconds old at validation.

T12 preserves this exact chronology: Stage B live worker; deterministic
verification; receipt dry-run; exact head/tree/check read-back; exactly one
runtime-receipt apply; canonical receipt read-back; provider/runtime
destruction; profile/runtime-data/process absence read-back; one append-only
lifecycle-completion evidence comment; owner merge judgment. The lifecycle
comment is not a second runtime receipt. Changing this order requires a
separate agreement change.

This slice advances only a bounded source-parity contribution from
`mochan-tk/agentic-dev-kit-for-copilot` commit
`fd265ddef150fab86cd54d0e383c2c25fe297ffb`: capability-aware routing for one
exact profile, bounded worker execution, a durable attempt/receipt trail,
independent verification rather than worker self-claim, and privacy by
reference. It does not complete K09, K10, K11, K12, or full runtime parity.

The single Stage A.2 attempt completed fail-closed. Its aggregate runtime
profile was `UNCHECKABLE`: provider isolation, mount boundary, process cleanup,
and configuration passed; shell environment failed with `process-nonzero`;
sandbox/network was `UNCHECKABLE` with `process-nonzero`; authentication was
unavailable. It performed no device authentication, model invocation, live
worker, runtime-receipt dry-run, or receipt application. Its VM, runtime data,
and tracked processes were destroyed with absence read-back. This remains
bounded non-success evidence and is not rewritten as pass. T11 performs no
Stage A.3.

The agreement-v2 decision moved live compatibility and receipt proof to T12,
which is active in this tree. Stage B requires a separate fresh VM; only
then may device-code authentication be enabled temporarily. A Stage B worker remains
blocked unless exact auth classification and the complete runtime profile are
`match`. The Stage A.2 non-success record is immutable historical qualification evidence, not
live-execution or runtime-receipt evidence, and cannot consume or impersonate
the one later T12 receipt.

## Limitations

The three `.codex/agents/*.toml` files are K09-partial static role guidance.
T11 does not prove named-agent runtime selection, authenticated role identity,
full K09/K10/K11/K12 parity, hooks, a generalized Task ritual, installation,
upgrade, feedback transport, full escaped-descendant process-lifetime
containment, or release readiness. Offline fixtures and Stage A.1/A.2
probe-only evidence do not
constitute a live Codex run. Only an exact-head supported-profile T12 Stage B
run and read-back receipt can supply live evidence. T12 intentionally
qualifies official stable Codex CLI `0.150.1` as one bounded compatibility
baseline, not as the current latest stable and not as proof for every stable
version. It proves exactly one owner-triggered logical `codex exec` worker-
process invocation and does not claim a count of backend model requests. T11 owner merge
remains only the acceptance gate for the deterministic offline harness; it
does not complete Phase 2, the repository, or a release.
