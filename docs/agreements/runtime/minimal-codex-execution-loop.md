# Minimal Codex execution loop

This document is the human-readable companion to the accepted T11 deterministic
offline harness and active T12 live-qualification frontier. The machine schemas are authoritative for
record shape; deterministic code and current Git/GitHub evidence are
authoritative for execution facts. The approved
[T11 agreement v2](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-5472720734)
deferred live Codex compatibility and runtime-receipt application to
[T12](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25), which
is the sole active frontier in this tree under its
[activation amendment](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25#issuecomment-5480062206).

```text
runtime_harness = minimal-offline-implemented
live_codex_execution = deferred-to-T12
sandbox_compatibility = unresolved-non-success
runtime_receipt_apply = deferred-to-T12
Phase 2 = incomplete
repository = incomplete
release_blocked = true
```

That block is the immutable accepted T11 history. The Phase 2 origin remains
commit `36c7eabecf7a56eb2a1c2c8f2c4d8fcb371c31c2`, tree
`1c1f46ad20dd289a713663c84eaf1dbb62840deb`; only T12 uses accepted T11 merge
`4a85a007ed62795b48bcbce04f6b7e5482e71e82`, tree
`49afe003de2bbb04249d6f4c36ea6462c271c26f`, as its Task base. Current T12
live outcomes are external GitHub state rather than mutable truth embedded in
this tree.

## Authority boundaries

| Record | Author | May prove | Must not prove |
|---|---|---|---|
| `task-execution-envelope/v1` | human / Task supervisor | intended Task, ownership, limits, requested runtime | process or acceptance outcome |
| `codex-final-response/v1` | model worker | bounded outcome narrative and claimed changed path | process, Git, events, digests, verifier, receipt |
| `loop-event/v1` | adapter | normalized attempt-scoped stream facts | raw reasoning or authenticated identity |
| `execution-result/v1` | adapter | bounded process, event, Git, and verifier result | owner acceptance |
| verifier record | fresh Python process | exact representative-file and Git checks | model quality or human acceptance |
| `runtime-receipt-request/v1` -> `runtime-receipt/v1` | explicit receipt actuator | validated native artifacts and their derived allowlisted projection | authenticated artifact provenance, raw stream, secrets, or repository completion |

Opaque envelope or event links in an Issue are linkage only. They do not prove
validity, freshness, execution, or acceptance.

## Shell-free command contract

Every verification or worker command is a structured `shell-free-command/v1`
record with an argv array, exact bound cwd, minimal environment profile,
timeout, expected exit codes, stdout/stderr byte limits, `shell=false`,
process-group TERM/KILL/grace/reap policy, and pre/post branch/head/tree/status/
worktree-binding checks. Every command cwd commit/tree must equal the envelope
harness commit/tree. The adapter uses direct process APIs and never joins
argv into a command string. Shell metacharacters remain inert argument bytes.

T11 fixes exactly the ten Issue-enumerated verification command records. This
registry is the T11 execution-envelope contract; it does not claim that every
accepted CI YAML step is shell-free or network-free, nor does it replace the
versioned quality/conformance registries.

Dynamic Task and context data are stdin-only. The sole developer-instruction
value permitted in worker argv is the exact static reviewed `task_worker`
string, identified by its recorded SHA-256.

## Deferred live runtime isolation contract

The T12 live argv contract selects the approved exact binary, model, and
reasoning effort; uses
`codex exec --json --ephemeral --strict-config --ignore-user-config` in a
private synthetic worktree; selects `workspace-write` and approval `never`;
and provides these reviewed overrides:

```text
sandbox_workspace_write.network_access=false
hide_agent_reasoning=true
show_raw_agent_reasoning=false
history.persistence="none"
features.hooks=false
features.apps=false
agents.enabled=false
tools.web_search=false
feedback.enabled=false
memories.generate_memories=false
memories.use_memories=false
shell_environment_policy.inherit="none"
```

The last setting is usable only after an actual capability probe confirms the
required set/filter behavior. The adapter validates the documented config-key
allowlist and records a stable adapter-authored intent digest, with
`effective_configuration_proven=false`; it is not a Codex-issued attestation.
A no-model runtime probe must separately exercise the reviewed settings that
the selected client can prove behaviorally. Help output and successful parsing
of an unknown `-c` key are not recognition evidence. `codex doctor --json` is
a redacted diagnostic support report only. The adapter retains only
allowlisted check ID, category, and status fields and never persists report
details or the raw report. A warning or failure blocks qualification for a
required auth, config, runtime, or sandbox check; unrelated advisory warnings produce
`pass-with-advisory-warning`. This bounded diagnostic status is never promoted
to effective-configuration evidence. The explicit environment contains
bounded PATH, private HOME, its exact private CODEX_HOME, and private TMPDIR,
`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `TZ=UTC`,
`PYTHONHASHSEED=0`, `GIT_CONFIG_NOSYSTEM=1`, and
`GIT_TERMINAL_PROMPT=0`. It excludes credential-, token-, secret-, proxy-, and
unrelated host variables. `GIT_OPTIONAL_LOCKS=0` makes read-only verification
avoid optional index writes.
Git and Codex executable discovery uses only the explicit reviewed PATH;
selected executables are direct no-follow regular-file bindings and are
digested rather than resolved through the ambient host environment.
The private runtime home supplies the reviewed execpolicy surface. Live and
probe argv must not contain `--ignore-rules` or any
`--dangerously-bypass-*` argument.

The official 0.150.1 no-model sandbox probe uses reviewed Option B. Its exact
sandbox slice is `codex <reviewed-runtime-overrides> sandbox
--permission-profile :read-only -C <synthetic-root> -- <probe-argv>`. The
managed `:read-only` profile provides a read-only filesystem and restricted
network, and `-C` binds the synthetic root. T11 requires the explicit `--`
delimiter before the probe argv. Validation rejects state flags mixed with
Option B, `-C` without a permission profile, an omitted delimiter, bypass
arguments, and unsupported or conflicting sandbox arguments.

Authentication has a dedicated bounded `codex login status` capture. Official
0.150.1 success output is read from stderr and compared as exact bytes:
`Logged in using ChatGPT` maps to `signed-in-client`, and the documented exact
API-key success form maps to `api-key`. A nonzero exit maps to `unavailable`;
a zero exit with any other output maps to `unknown`. The adapter records only
the safe classification. It never persists raw stdout/stderr, authentication
files, credential material, or private paths.

### T12 sandbox-launch diagnosis, not runtime acceptance

The 2026-09-05 [bounded remediation](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25#issuecomment-5550009263)
is offline only. Official 0.150.1 source commit
`90854393966b21e9ebfd21b122334eb09a20c93d` rejects global `--strict-config`
for `sandbox` before dispatch; `debug_sandbox` intentionally sets
`strict_config=false`. The sandbox prefix therefore omits that flag, while
doctor and live exec keep it. Reviewed overrides and their intent digest,
Option B, environment, image/provider, network, and AppArmor/bubblewrap
contracts are unchanged. This fixes a source-demonstrated incompatibility;
prior discarded stderr is unknown, and real sandbox compatibility remains
unproven by offline checks.

The opt-in command `profile --probe-only --launch-diagnostics` retains the
existing closed `runtime-profile/v1` unchanged inside a separate
`t12-sandbox-launch-diagnostics/v1` wrapper. Its only outer fields are
`schema`, `authority` (`adapter-authored`), `runtime_profile`, and
`launch_diagnostics` (exactly `shell` and `network`). Each diagnostic lane
contains only `status`, fixed `stage`, fixed `reason_code`, `exit_code`
(integer 0-255 or null), and `signal` (integer 1-64 or null). Exit and signal
cannot both be present. This wrapper is not a runtime profile, receipt,
attestation, or replacement acceptance gate.

An unavailable-auth status is checked before enabling capture, then reused;
diagnostics is rejected outside probe-only mode or with available/unknown
auth. All existing provider and prerequisite gates remain. There is no extra
sandbox launch: the same one process per lane temporarily captures at most
4096 stderr bytes, classifies them in memory, and strips them before the
original lane classifier. No bytes, environment values, paths, exception
text, or raw argv are exported. A source-exact strict-flag rejection maps to
`cli-dispatch` / `unsupported-strict-config`; unrecognized errors stay
`unclassified`, without a guessed config-loader or sandbox-launcher cause.
Signal, timeout, overflow, spawn failure, and incomplete reap are distinct
safe classifications. Supplemental launch success cannot promote environment,
network, or profile results. Normal profile output is unchanged.

Both T12 Stage A attempts remain non-success and no third attempt is
authorized. A future measurement using this option requires a separate owner
replan against the exhausted retry allowance; calling it a diagnostic run
does not bypass that limit. This correction executes no VM, Codex probe,
authentication, model, live worker, receipt, or Stage B.

The qualification boundary is one fresh, attempt-only Colima
Linux VM using the VZ backend and native `aarch64`. Its profile name is
`t11-e2e-<exact-public-head-first-12>-01`. The host Mac, default Colima
profile, any existing VM/container/volume, and PID tracking alone are not the
approved boundary. The repository is cloned from GitHub onto the VM private
disk and checked against the exact public PR head/tree; the host repository,
HOME, Codex/GitHub credentials, SSH agent, Docker socket, private TMPDIR, and
unrelated paths are not shared.

The outer containment claim consists only of that fresh disposable
VM, the closed no-sensitive/unapproved-mount boundary, the exact public PR
head/tree, a dedicated private `CODEX_HOME`, exact lifecycle destruction, and
profile-absence read-back. These provider facts are independent of Codex
configuration, sandbox/network, shell-environment, authentication, and
best-effort process-cleanup results.

Before creation, owner-authored control-plane evidence must observe both the
named profile and its runtime-data root as absent. The created instance is
fresh: it reuses no VM, container, volume, default profile, or additional
disk; activation context remains unchanged; the repository and runtime root
reside on the VM private disk. A closed
`t11-colima-control-plane-evidence/v1` record binds the observations, Colima
`0.10.1`, profile/backend/architecture, instance and configuration digests,
and chronology. Its normalized digest is independently recomputed from safe
canonical fields, with raw paths excluded. This is owner-authored evidence,
not a Codex-authenticated attestation.

Colima 0.10.1 adds one provider-internal cache mount even when configured with
`--mount none`. T11 redirects that cache to a fresh attempt-only provider root
outside host HOME/private TMPDIR and requires the effective Lima mount
inventory to contain exactly that one read-only entry and no other shared
mount. Durable evidence records only the canonical inventory and entry
digests, classification `provider-internal-cache`, count, read-only/absence
booleans, and SSH-isolation booleans; it never records the raw source or guest
path. SSH-agent forwarding and host `.ssh` public-key loading are disabled,
and the user's SSH configuration is not modified.

The VM installs official stable `codex-cli 0.150.1` from
`codex-aarch64-unknown-linux-musl.tar.gz`. Both the approved archive SHA-256
`5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264`
and a separately calculated extracted-binary digest are required. Stage A.1
keeps the dedicated private VM `CODEX_HOME` unauthenticated. T12 Stage B, if
later approved after the required unauthenticated qualification, uses a
separate fresh VM and device
authorization in its own dedicated private `CODEX_HOME`; credential values,
device codes, and authentication files never enter artifacts or durable
output.

### Qualified Stage A.1 Git and bubblewrap prerequisites

Stage A.1 remains a bounded non-success attempt. It qualified only the
documented Git and bubblewrap prerequisites inside a fresh disposable Colima
VM before any Codex shell-
environment or sandbox/network probe. The provider controller uses fixed argv
arrays with `shell=false`; package installation is never delegated to a model.
It first records only these allowlisted guest facts: distribution ID/version/
codename, kernel, architecture, AppArmor enabled state, and the
`kernel.apparmor_restrict_unprivileged_userns` state. A passing platform is
Ubuntu 24.04 `noble`, Linux `aarch64`, AppArmor enabled, with that restriction
set to `1`.

The controller pins the Ubuntu packages and expected installed facts below:

| Artifact | Exact accepted value |
|---|---|
| `bubblewrap` package | `0.9.0-1ubuntu0.1` / `arm64` |
| `/usr/bin/bwrap` version | `bubblewrap 0.9.0` |
| `/usr/bin/bwrap` SHA-256 | `ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8` |
| `apparmor` and `apparmor-profiles` packages | `4.0.1really4.0.1-0ubuntu0.24.04.7` |
| `bwrap-userns-restrict` profile SHA-256 | `11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9` |
| `git` package | `1:2.43.0-1ubuntu7.3` / `arm64` |
| `/usr/bin/git` version | `git version 2.43.0` |
| `/usr/bin/git` SHA-256 | `aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942` |

It records the bubblewrap help digest, not raw help. When the Ubuntu 24.04
AppArmor unprivileged-user-namespace restriction is active, it installs the
packaged official profile from
`/usr/share/apparmor/extra-profiles/bwrap-userns-restrict` at
`/etc/apparmor.d/bwrap-userns-restrict`, verifies both profile digests, loads
it with `/usr/sbin/apparmor_parser --replace`, and confirms enforce status.
The load sensor requires the two source-defined kernel profiles
`bwrap (enforce)` and `unpriv_bwrap (enforce)`. The transient stacked
execution label `bwrap//&unpriv_bwrap` is not treated as a separately loaded
profile and cannot substitute for either source-defined profile.
The fixed package/setup argv and their canonical digest are part of
`t11-bubblewrap-prerequisite-evidence/v1`.

Git installation and its closed evidence precede the repository clone. The
controller records only the exact package status/version/architecture,
`/usr/bin/git --version` classification, and executable digest; raw command
output is not durable. Only after those facts match may `/usr/bin/git` clone
the exact public PR head/tree onto the VM private disk. The host repository is
not mounted or copied in as a substitute, and Git package work is never
delegated to a model. The owner/controller-authored pre-clone facts enter the
adapter through the closed `repository.git_bootstrap` stdin record. Before its
first repository Git command, the adapter re-observes the package, architecture,
fixed `/usr/bin/git`, and PATH-resolved Git version/digest and requires exact
equality with that trust anchor. Each provider Git operation then revalidates
the root-owned, non-group/world-writable `/usr` -> `/usr/bin` ->
`/usr/bin/git` binding and invokes that fixed path without PATH re-resolution.

The fixed pre-clone qualification argv have SHA-256
`a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc`.
The owner input also carries a reviewed clone-contract digest derived from the
exact repository URL, branch, public head/tree, pinned Git, private-disk
destination placeholder, shell-free argv templates, disabled credential helper
and hooks, process umask `0077`, and expected clean checkout. Each template uses
a static `python3 -I` wrapper that accepts only `/usr/bin/git`, sets that process
umask, and immediately `execve`s the fixed Git argv; it does not invoke a shell.
The private umask projects tracked non-executable files as `0600`. Provider-
bound Stage A and live argv evidence requires that exact private projection;
`0644` remains valid only for ordinary offline/checker use. Both projections
must be single-link regular and non-group/world-writable, and Git tree mode
`100644` remains canonical. The adapter's repository JSON non-writable check is
unchanged. The adapter
recomputes the clone-contract
digest and then proves the resulting checkout head/tree/status. This
cross-binding checks the reviewed contract and post-clone equality; because
repository code is not available before clone, it does not independently
authenticate that the outer owner/controller executed the asserted pre-clone
chronology.

The controller launches the wrapper with an environment-replacement policy,
not inherited shell state. Only reviewed fixed Git/locale/path values and one
absolute private-VM home path reach the wrapper. That home must open no-follow
as an empty, current-uid, mode-`0700` directory whose binding remains stable;
Git receives only its inherited descriptor projection. Global Git config is
fixed to `/dev/null`, system config and attributes are disabled, and any extra
controller key is rejected. This keeps Git redirection, config/credential
injection, askpass/SSH-agent variables, and arbitrary loader variables out of
the Git child. `/usr/bin/python3` remains trusted fresh-image provider
infrastructure for this pre-clone boundary; T11 does not claim an independently
pinned interpreter attestation.

The same controller then invokes this exact smoke test directly as the guest
non-root user:

```text
/usr/bin/bwrap --unshare-user --unshare-net --ro-bind / / /bin/true
```

The canonical fixed controller-argv list has SHA-256
`3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff`;
the smoke argv alone has SHA-256
`8e8d9907189e3b2dbcf3170d20d3dad2cfe6269da5148946ae79c4aa06843f08`.

Success requires exit zero, no signal, timeout, output overflow, unexpected
output, or unreaped process. Raw stdout/stderr is not durable; non-success is
classified with a fixed reason code. Missing or drifting platform, package,
profile, binary, or observation evidence fails closed. T11 neither sets
`features.use_legacy_landlock=true` nor globally disables the AppArmor userns
restriction.

Only a passing `bubblewrap_prerequisite` permits the adapter to invoke the
Codex shell-environment and sandbox/network probes. This additional gate does
not merge evidence lanes: `provider_isolation_status`,
`mount_boundary_status`, `process_cleanup_status`,
`codex_sandbox_network_status`, `shell_environment_status`, `config_status`,
and `auth_status` remain independent observations.

### Stage A.2 shell and network classification

Stage A.2 freezes the qualified Stage A.1 package, AppArmor profile, direct
bubblewrap smoke, guest sysctl, and Codex 0.150.1 inputs. It changes only the
probe classification and then runs one fresh unauthenticated, no-model Colima
attempt.

The shell probe records a closed `t11-shell-environment-evidence/v1` object.
Its status is paired with a fixed reason code. Unexpected environment data is
reduced to a count, SHA-256 of the canonical sorted key-name set, and a
secret-shaped-key count; names, values, stdout, stderr, argv, and private paths
are not durable. Required configured values remain exact, the forbidden
sentinel must be absent, and `CODEX_SANDBOX_NETWORK_DISABLED` must equal `1`.
Official Codex 0.150.1 source at commit
`90854393966b21e9ebfd21b122334eb09a20c93d` establishes that this debug-sandbox
path adds only that network marker. `PWD`, `SHLVL`, `_`, proxy keys, and Darwin
compatibility variables are therefore not allowlisted on the Linux aarch64
probe.

The network probe records a closed `t11-network-sandbox-evidence/v1` object.
Before sandbox execution, a loopback control connection must succeed, be
accepted, and have both accepted endpoints closed. Parent and sandbox network
namespace identities are hashed independently and must differ. The sandbox
child must observe the exact network marker, attempt an actual `connect(2)` to
the still-listening control endpoint, and be reaped under the bounded process
contract. Only `EPERM`, `EACCES`, `ENETUNREACH`, `EHOSTUNREACH`, or
`ECONNREFUSED` is accepted, and only when the control, namespace, marker, and
cleanup evidence also passes. Successful connection is failure; missing
namespace/control evidence, socket-creation failure, arbitrary errno, timeout,
overflow, malformed output, or incomplete reap is non-success. Durable output
contains only normalized states, fixed reasons, and non-private digests.

Before worker invocation, descriptor-aware checks require the worktree root and
`work-item.txt` to keep their directory/file bindings. The only permitted
worktree entry is a non-symlink regular file named `work-item.txt`, mode
`100644`, with exact initial bytes `status=pending\n`. An unexpected
`.codex/config.toml`, project hook setting, `.codex/agents/**`, project Skill,
AGENTS file, MCP configuration, symlink, extra file, or namespace swap is a
fail-closed preflight with zero worker invocations.

The runtime readers require descriptor-relative and no-follow filesystem
capabilities plus bounded descriptor xattr metadata reads. Missing
`O_NOFOLLOW`, `O_DIRECTORY`, `dir_fd`, `follow_symlinks`, xattr enumeration,
or xattr value support fails before stdin, a temporary root, a process, Git,
or Codex is touched. `st_flags` is also recorded where the platform exposes it.

## Bounded execution and normalization

### T12 finite native-state boundary (owner amendment, 2026-09-08)

This table supersedes private-HOME byte/metadata equality only for the named
native classes. Paths are relative to the private HOME; `.codex` is the exact
CODEX_HOME. All are current-uid/current-gid, descriptor-relative/no-follow, bounded, and
inside the approved disposable VM. They are not adopter payload or durable
artifacts. Unknown entries fail; the adapter never deletes entries to pass.

| Relative path / finite pattern | Source at official 0.150.1 commit `90854393966b21e9ebfd21b122334eb09a20c93d` | Type / mode / limits | Allowed lifecycle and cleanup |
|---|---|---|---|
| `.codex/tmp`, `.codex/tmp/arg0` | `codex-rs/arg0/src/lib.rs`, startup helper dispatch | directories `0700` | creation; child-induced time/link-count changes only; existing inode/owner/mode/flags/xattrs remain exact; whole VM destruction |
| `.codex/tmp/arg0/codex-arg0[A-Za-z0-9]{6}` | arg0 `tempfile::Builder` prefix and default six-character suffix | at most 4 directories `0700` | create/drop; names are never used as authority; whole VM destruction |
| each arg0 directory's `.lock` | arg0 process guard | one regular file `0600`, exactly zero bytes | create/drop under its bounded parent; never written; whole VM destruction |
| each arg0 directory's `apply_patch`, `applypatch`, `codex-linux-sandbox`, `codex-execve-wrapper` | arg0 helper aliases | four single-link symlinks, current-uid, exact target equals the already pinned Codex executable | create/drop; no general symlink traversal or alternate target; whole VM destruction |
| `.codex/state_5.sqlite`, `.codex/logs_2.sqlite`, `.codex/goals_1.sqlite`, `.codex/memories_1.sqlite`, `.codex/queue_1.sqlite` | `codex-rs/state/src/sqlite.rs` versioned filenames; `state/src/runtime.rs` eager initialization | each single-link regular `0600`, at most 16 MiB | create/update; stable inode if persistent; whole VM destruction |
| each of those five exact filenames plus `-wal` | SQLite WAL mode in `state/src/sqlite.rs` | five distinct single-link regular `0600`, at most 16 MiB each | create/update/drop, never an arbitrary database; whole VM destruction |
| each of those five exact filenames plus `-shm` | SQLite WAL shared-memory sidecar | five distinct single-link regular `0600`, at most 1 MiB each | create/update/drop; whole VM destruction |
| `.codex/models_cache.json` | `codex-rs/models-manager/src/manager.rs` and `cache.rs`, direct model catalog cache write | one regular `0600`, at most 4 MiB | create/update; whole VM destruction |
| `.codex/installation_id` | `core/src/installation_id.rs`, explicitly forces `0644` | one regular `0644`, exactly 36 UUID bytes; still enclosed by `0700` HOME/CODEX_HOME | create once; existing bytes and inode exact; whole VM destruction |
| `.codex/shell_snapshots` | `core/src/shell_snapshot.rs`, default shell-snapshot feature | directory `0700` | creation and bounded child lifecycle; existing identity/mode exact; whole VM destruction |
| `.codex/shell_snapshots/<lowercase UUID>.<decimal nanoseconds>.sh` and `<lowercase UUID>.tmp-<decimal nanoseconds>` | `core/src/shell_snapshot.rs`, session snapshot temporary/write/rename/drop | at most 8 files total, each single-link regular `0600`, at most 1 MiB | create/update/rename/drop inside this one directory; whole VM destruction |
| `.codex`, private HOME `.` | existing dedicated root plus above child lifecycle | directories `0700` | existing identities/owners/modes/flags/xattrs exact; `.codex` times/link count may reflect approved children; HOME remains exact |
| `.codex/rules`, `.codex/rules/t11-reviewed.rules` | existing reviewed rules materializer | `0700` / single-link regular `0600`, exact reviewed bytes | protected, not native mutable state; whole VM destruction |
| `.codex/auth.json`, when separately owner-authenticated | existing device-auth lifecycle, not ordinary state | single-link regular `0600`, at most 1 MiB | baseline only after manual authentication; exact presence/bytes/inode/metadata throughout probes and worker; whole VM destruction |

The whole inventory remains capped at 128 entries and 64 MiB of regular data.
Count and byte caps are this repository's fail-closed safety policy, not an
upstream promise that every Codex session fits them. Snapshot nanoseconds also
must fit the source's unsigned 128-bit integer. The six-character arg0 suffix
is grounded in pinned `tempfile` 3.27.0 default generation, not a broad glob.
Mutable native classes require zero platform flags and no xattrs. Protected
baseline metadata remains exact. Offline macOS fixture tests explicitly model
the approved Linux empty-xattr condition; that seam is not runtime evidence.
All unknown paths, arbitrary TMPDIR output, config changes, credential changes,
history/session rollout paths, lazy thread-history databases, special files,
hardlinks, escaping links, excess counts/sizes, and namespace drift fail.
Directory timestamp changes are allowed only for declared mutable directories;
directories are never silently rebound. Source behavior can put prompts, tool
or diagnostic content in internal SQLite data, and shell snapshots can contain
environment/shell values. History `none`, ephemeral sessions, disabled memory
generation/use, and export exclusions remain mandatory but are not claims that
these files are non-sensitive. No native bytes, filenames, private paths, or
native inventory leave the VM; only bounded classification/count/digest evidence
may do so. This is pre/post persistence observation, not transient-write proof.

### Immutable pinned-client builtin cache (same native-state amendment)

The exact default embedded Skills cache is classified as protected pinned-client
contents, not mutable runtime data, new project Skills, a configuration override,
or authorization to install anything. Official source `codex-rs/core/src/thread_manager.rs`
loads the host Skills service; `codex-rs/ext/skills/src/host_service.rs` and
`codex-rs/config/src/skills_config.rs` default bundled Skills on. The pinned
`codex-rs/skills/src/lib.rs` writes embedded bytes without transformations;
`skills/build.rs` only marks source inputs for rebuild. The source
[embedded tree](https://github.com/openai/codex/tree/90854393966b21e9ebfd21b122334eb09a20c93d/codex-rs/skills/src/assets/samples)
is Git tree `dd83abff11d7be56fc9fc10330fc686d1a48ab01`.

If any cache path exists, the complete set must exist: exactly the following
59 regular files (384736 total bytes), their 26 directory ancestors, the private
`.codex/skills` and `.codex/skills/.system` roots, and the one marker. Files are
single-link `0600`, directories `0700`, current-uid/current-gid, no flags/xattrs,
with exact file lengths and SHA-256 below. Paths are relative to
`.codex/skills/.system/`. There is no `skills/**` wildcard permission. The cache
may be created once; after its first complete inventory all content, membership,
bindings and metadata are immutable. Cleanup is the existing whole-VM deletion.
The marker `.codex-system-skills.marker` is one single-link `0600` file of
1–16 lowercase hex characters plus LF. Its implementation-specific hash is
explicitly non-authoritative: its presence/value NEVER bypasses complete asset
hashing, and its bytes remain exact after the first baseline. No external source
is installed or loaded by this allowance. The aggregate 128-entry/64-MiB bound
still takes precedence over the individual class maxima.

| Exact relative path | Bytes | SHA-256 |
|---|---:|---|
| `imagegen/LICENSE.txt` | 10776 | `4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9` |
| `imagegen/SKILL.md` | 19201 | `681ddb4ad6d06a2acc78a3535b583f8d0c1ea800ecda3d56370d3310fd2cd4ba` |
| `imagegen/agents/openai.yaml` | 275 | `9ca574af14580dc7a2a3dc37a1796d17f93cb8850be66501f0799ef8603e9dc0` |
| `imagegen/assets/imagegen-small.svg` | 2889 | `cff5f34f57ff60b3ee92eaedd17b15e96dd4b9e776df3e78936c9e00d42be294` |
| `imagegen/assets/imagegen.png` | 1711 | `95952f644064eb9e890f98d8db07216347186526e4c41ad66d3420629eb86e20` |
| `imagegen/references/cli.md` | 9655 | `ecfc2e09261a0feb3482517a5fa0ff410cb7d1958e3cbd2ac6b61586f5b81405` |
| `imagegen/references/codex-network.md` | 1779 | `c88298ca4481f6116a16fa7987434fc977f8b311c1bbc0c3d862ffd0c5981148` |
| `imagegen/references/image-api.md` | 6072 | `dc975d7af8a4888967251a0276014b4a71ea30455294944b762256373ce3e569` |
| `imagegen/references/prompting.md` | 8282 | `b210b051c775860267080941eba968212bf0ac7fce581d75c5dcc217d8293f8b` |
| `imagegen/references/sample-prompts.md` | 17617 | `70474177d151855b175c6133de2aae1d90b7f146b0dab50ec830972c47d72183` |
| `imagegen/scripts/image_gen.py` | 34271 | `35e8f9fa47deca111e46c63c4ac2008e09198ef664c0926a9dfdcd6745aa37ed` |
| `imagegen/scripts/remove_chroma_key.py` | 13836 | `3f7b9b14ad5c90f37618bc1c16a039a2076abca12ddc41b3ae470e2b1cad6c0e` |
| `openai-docs/LICENSE.txt` | 10776 | `4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9` |
| `openai-docs/SKILL.md` | 5446 | `7cb8fa1b2a0c635b5c61ffe1da7b8594a7ea0fce5b71e8d523e2025d88b2a05e` |
| `openai-docs/agents/openai.yaml` | 370 | `44b9efac6be1bae32d869aa2942fecbe4dcae82682ee03e4120f2f9b7d4658ec` |
| `openai-docs/assets/openai-small.svg` | 1091 | `45be1f0757eb18889eefb1e7db79668ef46a275dc4e0e78e8df5ebd7f6cdeadc` |
| `openai-docs/assets/openai.png` | 1429 | `156cc84d7332bfe95b310350bd470b690d22aa33d65340cc6c2e06022946194c` |
| `openai-docs/references/codex-self-knowledge.md` | 7417 | `8c8fb00e6e5cb1977924f5164684a6095427fa828bbc765225f17d9aeb79a912` |
| `openai-docs/references/latest-model.md` | 2094 | `f25e351e522dd6e30e82d482f31f44c992e794b11031cdcb6ac7c0e6b20c9d5d` |
| `openai-docs/references/mcp-diagnostics.md` | 2318 | `49bbd2f73df7bbd7f86c80425dea4da2d301c22046080399a36bfc0ca49509e9` |
| `openai-docs/references/model-migration.md` | 5054 | `5f20c38fbbb10319767b216d91ba74bae49c68fc1bfd6d1abd7c9b4cc9cb9ab0` |
| `openai-docs/references/model-selection.md` | 1344 | `ba2d164abbca30435a460a0bc3a7d82398dce2bdf092705c98ba55b3f3af38a8` |
| `openai-docs/references/official-docs.md` | 3337 | `7962f2dce55089b93bde4115bb89fd42f20993c1597a2b13edd4956f463875b9` |
| `openai-docs/references/prompting-guide.md` | 15747 | `db913884cfe0fabf29bee1a139918f56e299decfa0a14d61c48596f23f76621d` |
| `openai-docs/references/upgrade-guide.md` | 1050 | `ed1b75a89b8ec4d67787774ef6c4e8b98eace16c63348f42e969e6ffa67cb656` |
| `openai-docs/references/upgrading-to-gpt-5p6-sol.md` | 23093 | `9a918a0c8dd051d574f2fd0309201afa8a9b9c08241c11ca1fb0ac2f4724e7ac` |
| `openai-docs/scripts/fetch-codex-manual.mjs` | 16085 | `f53eb6d2f286e9efcc397e8bee93a938e37296c90953e4e06e94899ef1b6c363` |
| `openai-docs/scripts/resolve-latest-model-info` | 1038 | `7354dbb030ca0736dd633a7ca1b930cf640abd40370725dea3a458cb51d49523` |
| `openai-docs/scripts/resolve-latest-model-info.cjs` | 3937 | `eeb1bb486018e16b37edfc06b1a37179dbc672982d501040d4f7142f29dd2e64` |
| `plugin-creator/SKILL.md` | 11467 | `71b95b8219644f95d633721e7f7cd3c469edfc8fe50f8415d400dfb2d74bc7b9` |
| `plugin-creator/agents/openai.yaml` | 339 | `fecaf35d692bd3d33d1a065648258d12e393afa9055d78adf6e57b42f4142f6d` |
| `plugin-creator/assets/plugin-creator-small.svg` | 1319 | `6591bf8ea9bb9435890dbdea299e0d2bd05f3aa893a335d26e4c535e93c8e7fb` |
| `plugin-creator/assets/plugin-creator.png` | 1563 | `a4024b0306ddb05847e1012879d37aaf1e658205199da596f5145ed7a88d9162` |
| `plugin-creator/references/installing-and-updating.md` | 6000 | `91c4781d48568fcc708b45566b08fb610ad1c88672720ae512f9525a1cf9cb20` |
| `plugin-creator/references/plugin-json-spec.md` | 9179 | `eeb640130f69636affaa299d4170d5a7ae6a0ff978296ddf75c409ce6dd87b91` |
| `plugin-creator/scripts/create_basic_plugin.py` | 11495 | `46f532721079f6de6443f30f9362d77f1d879f57c0559250ef9433867414eb93` |
| `plugin-creator/scripts/identifier_validation.py` | 784 | `a6d51ce4a9a7e8f85626ff5808a467a67574e7f8cdf1167ffb467c5f67e57223` |
| `plugin-creator/scripts/read_marketplace_name.py` | 1644 | `ba24e6d91eed6f778bde022a967be335c6253983b5ecd1c5e30c8483385887fd` |
| `plugin-creator/scripts/update_plugin_cachebuster.py` | 3043 | `97c5ecab5ad85d871f0ebfc9bdf25d4b9e1a1680128fd3deb18a8c64f15f85c5` |
| `plugin-creator/scripts/validate_plugin.py` | 21533 | `6ff4bc1cc8ca94827c30c8299951efdac900ff38a5069c03e9a6554fc194a723` |
| `review-agent/SKILL.md` | 2661 | `07079efd0dc76f05fade424e5dfb048dce1de2df7626e1a4f56292a4f3f92228` |
| `review-agent/agents/openai.yaml` | 252 | `4d867a46d15e36ac880176484aae160f59855340c6059b2ea6ab9fbc9af084de` |
| `skill-creator/SKILL.md` | 15311 | `6656e54755638e8efcf275a472b9672eaa8a9a1b9e59dc210e275b03b59e1e66` |
| `skill-creator/agents/openai.yaml` | 183 | `d07d21b93fcf3d4dc8d9a3399c05fc226a49a333a96d3e1c68b451b8dd9eade6` |
| `skill-creator/assets/skill-creator-small.svg` | 1319 | `6591bf8ea9bb9435890dbdea299e0d2bd05f3aa893a335d26e4c535e93c8e7fb` |
| `skill-creator/assets/skill-creator.png` | 1563 | `a4024b0306ddb05847e1012879d37aaf1e658205199da596f5145ed7a88d9162` |
| `skill-creator/license.txt` | 11358 | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `skill-creator/references/openai_yaml.md` | 2356 | `ffac39318e408108141d40f820968e59f70434a891694f9bf1d25be8237b150c` |
| `skill-creator/scripts/generate_openai_yaml.py` | 6619 | `ddaf9abdfb3e762ed3c82571e9c607ce964188f49f2146281beb2cb8a553a93d` |
| `skill-creator/scripts/init_skill.py` | 10160 | `bc04fae1e671aa1e5104212674e7f22c9665a791fafa2fc2b3897187a89801b2` |
| `skill-creator/scripts/quick_validate.py` | 4227 | `1fd66498c219616fd9249eacdf16c458412ea9065a9d887fd716aeef03907762` |
| `skill-installer/LICENSE.txt` | 11358 | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `skill-installer/SKILL.md` | 3367 | `d68b77e5bbb34dedab89d134da52855f140fc4b4299b80104f534e3b9e98f8ee` |
| `skill-installer/agents/openai.yaml` | 221 | `5ce223d8b1070b82c42298538f1b8d376f788eb9e7a42a987e8c094070d73f0e` |
| `skill-installer/assets/skill-installer-small.svg` | 923 | `3928703ff00dc1a681e7a22401843b7edcbd4b2051651ce4c43b75f7e140504e` |
| `skill-installer/assets/skill-installer.png` | 1086 | `d0a230b1a79b71b858b7c215a0fbb0768d6459c14ea4ef80c61592629bf0e605` |
| `skill-installer/scripts/github_utils.py` | 659 | `61c1bbe2ae217433b4b6f9f09f21aca4df52c12598068343ade719f706e4859b` |
| `skill-installer/scripts/install-skill-from-github.py` | 11790 | `3569ac8c0b3a525515c2e0e27c4f48e6aef9f2ff04029dcb3f622b280fa8c25e` |
| `skill-installer/scripts/list-skills.py` | 2967 | `e4e1f78ca3d045827f2a05cfd99fae57cc7c1a1bfeba8704029108834debff35` |

### T12 complete runtime-profile comparison classification

Every descendant of a listed group has the group's classification; no fallback
classification exists. Each full observation first passes the unchanged closed
profile validator, including nested exact-key and derived-digest checks.

| Exact field/group | Class and comparison |
|---|---|
| `schema`, `repository`, `scope`, `status`, `reason`, `platform`, `client`, `capabilities`, `auth`, `request`, `shell_environment`, `live_run_allowed` (all descendants) | stable compatibility/security: exact; includes binary/version/help, model/effort, auth class, sandbox/approval, environment intent, capability/status gates |
| `evidence.configuration_intent`, `evidence.exact_worker_argv`, `evidence.shell_environment_behavior`, `evidence.bubblewrap_prerequisite`, `evidence.lane_statuses` (all descendants) | stable compatibility/security: exact; all source/config/rules/argv/prerequisite/key-name digests exact |
| `evidence.diagnostic_health` (all descendants) | fresh observation: independently valid current required-category success; unrelated advisory status does not replace a required lane |
| `evidence.network_sandbox_behavior` (all descendants) | fresh observation: independently valid accepted/closed control, nonzero unequal parent/sandbox namespace digests, exact marker, allowed denial, successful reap; no cross-observation identifier novelty/equality requirement |
| `evidence.containment_provider.schema`, `authority`, `codex_authenticated_attestation`, `status`, `provider_kind`, `vm_backend`, `architecture`, `native_architecture`, `guest_os`, `guest_kernel`, `host_mount_count`, `host_mount_classifications`, `all_host_mounts_read_only`, `provider_cache_only`, `host_sensitive_mounts_absent`, `unapproved_mounts_absent`, `ssh_agent_forwarding`, `dot_ssh_public_key_loading`, `user_ssh_config_modified`, `public_head`, `public_tree`, `repository_clean`, `repository_git_bootstrap`, `repository_git_bootstrap_runtime_match`, `repository_git_clone_contract_sha256`, `codex_version_output`, `approved_archive_sha256`, `observed_archive_sha256`, `extracted_binary_sha256` (all descendants) | stable compatibility/security: exact |
| `evidence.containment_provider.profile_name`, `created_at`, `provider_configuration_sha256`, `effective_mount_inventory_sha256`, `provider_cache_mount_sha256`, `provider_cache_guest_mountpoint_sha256`, `vm_instance_identity_sha256`, `runtime_root_binding_sha256`, `dedicated_codex_home_binding_sha256`, `control_plane`, `lifecycle` (all descendants, including normalized control-plane digest and timestamps) | attempt/VM: exact within Stage B; Stage A identity never substitutes for Stage B; lifecycle remains pre-live until separately recorded teardown |
| `observed_at` | fresh observation: the fresh observation is later than the supplied one, inside the local sensor start/finish window, neither stale nor future; replay/equal time fails closed |
| Original full-observation canonical SHA-256 values (comparison evidence only, not new profile fields) | derived fresh bindings: each recomputed from its complete unmodified profile; both are retained, not replaced by normalized/constants-only profiles |

The adapter executes the sensor again immediately before the one worker and
emits both original observations through a required live comparison-evidence
sink. The external integration must retain that sanitized record even on a
later failure. Independently valid profiles are also retained on comparison
failure; invalid/unsanitized profile records are not exported. After comparison
succeeds, the native result and receipt bind the immediate pre-worker fresh
profile, while comparison evidence retains both original canonical digests.
This record does not extend or substitute for native profile,
event, result or receipt schemas. Failed/missing lanes, unknown fields, old
timestamps, supplied/replayed observations, or stable/same-VM drift block the
worker. Identifiers alone do not authenticate freshness; the adapter-owned
sensor call window and finite attempt claim supply the execution chronology.

The controller drains stdout and stderr concurrently under independent byte
limits, bounds every JSONL line and total event count, rejects invalid UTF-8,
partial JSON, scalar events, excessive JSON depth/nodes/string size, unknown
terminal meaning, duplicate JSON keys, non-finite numbers, zero/multiple raw
terminal occurrences, and attempt drift. Raw terminal occurrences are counted
before duplicate collapse. Identical nonterminal duplicates may be collapsed
only under the documented event identity;
conflicting duplicates and stale attempts fail.

Timeout, signal, output overflow, or an observed surviving descendant triggers
bounded TERM/KILL cleanup. The controller tracks Linux `/proc` start ticks or
Darwin `proc_pidinfo` start seconds/microseconds as immutable birth tokens;
PPID/PGID are discovery topology, not identity. It refreshes that token before
each individual signal, so a reused PID receives no signal while a captured
setsid/reparented descendant remains identifiable. Missing birth-identity
support is `UNCHECKABLE` for the process-cleanup lane. This process-table
sensor is best-effort cleanup evidence, not kernel-enforced containment. T11
does not claim full escaped-descendant process-lifetime containment; that
stronger control is deferred to T13. The approved disposable Colima VM is the
outer containment boundary. No raw output is copied into the durable result.

Immediately around the offline worker, one private execution root contains only the
target repository, private HOME, and private TMPDIR. The live path uses a separate
target execution root and the existing persistent private HOME/TMPDIR. The
amendment's finite native-state table supersedes whole-HOME equality only;
the target root and TMPDIR remain exact. A bounded descriptor-
relative, no-follow pre/post inventory covers its membership, file bytes,
device/inode bindings, mode, timestamps, xattr names and bounded value digests,
and platform `st_flags`; only the exact `work-item.txt` initial-to-final byte
transition is allowed. Persistent TMPDIR/sibling output and `.git/HEAD` xattr
drift therefore fail. This is not an observation of arbitrary host paths,
does not prove transient create/delete activity, portable ACL equivalence, or
kernel write containment, and supplies no live-match proof.

After the worker, Git and filesystem checks reject branch/head/base/tree/
device/inode drift, staged or untracked data, unsafe diff kinds, mode or link
changes, and any path beyond `work-item.txt`. A bounded descriptor-relative
content inventory of `.git` plus a distinct same-target device/inode/type/mode
binding inventory, semantic ref, index/stage, config, shared/split-state, and
unreachable-object checks makes hidden Git changes and byte-identical
replacement of `.git/HEAD` or the `.git` namespace fail. Fresh-baseline
comparison uses content normalization only; before/after binding comparison
uses the original target namespace. Success requires
that one file's exact bytes equal `status=complete\n`. A new read-only verifier
reasserts the exact base/branch/tree/index/ref/object facts itself and compares
against a private canonical baseline; it does not trust caller pre-state as
base truth. Worker/event/final/exit/verifier inconsistency is failure.

## Runtime profile states for active T12 qualification

Only `match` permits live execution. `profile-drift`, `unsupported-client`,
`UNKNOWN`, and `UNCHECKABLE` are non-success. An unapproved alpha, beta, release
candidate, or other prerelease is `unsupported-client`. The committed
task-start profile is a historical sensor snapshot, not a promise that a later
client matches. Release class is derived from exact version output rather than
trusted as caller metadata. Runtime evidence has independent
`provider_isolation_status`, `mount_boundary_status`,
`process_cleanup_status`, `codex_sandbox_network_status`,
`shell_environment_status`, `config_status`, and `auth_status` lanes. A
failure or unknown in one lane never overwrites observations in another. A
stable client can reach `match` only after the bubblewrap prerequisite, every
independently required lane, the exact-worker-argv policy, and the bounded
diagnostic-health policy have their required success evidence. An
adapter-authored intent digest or doctor health result alone never proves
effective configuration. `match` additionally requires a closed
`containment_provider` record with
adapter/owner-authored authority, `codex_authenticated_attestation=false`, the
exact approved Colima/VZ/aarch64/profile/client/archive boundary, passing
provider and mount isolation, exact public head/tree binding, a clean
guest checkout, and the closed mount/SSH isolation claims above. This lane is
not a Codex-issued or authenticated attestation. Configuration, shell,
sandbox/network, auth, and best-effort process-cleanup statuses remain separate
and cannot degrade or upgrade the provider-isolation claim. The historical
task-start profile uses an exact `not-run` sentinel with zero digests and no
fabricated provider, VM, or creation-time observation.
Immediately before a T12
live worker, the full sensor runs again and follows the complete comparison
classification above, superseding whole-profile equality except timestamp.
The T12 integration calls `execute_slice` with a durable comparison-evidence
sink; a live caller without that sink fails before the fresh sensor or worker.

Exact-worker-argv construction fails safely with a fixed `stage` and
`reason_code`, never exception text, raw argv, or a private path. The only
allowed stages are `load-envelope`, `load-static-role`,
`environment-contract`, `build-argv`, `argv-policy`, `schema-binding`, and
`filesystem-binding`.

## T11 offline acceptance and active T12 live-evidence boundary

Required CI uses only fixtures, a fake process, private synthetic Git
repositories, schemas, and deterministic tests. It has no Codex authentication,
network, model spend, live mode, or GitHub write. T11 accepts only this
deterministic offline boundary, including fixture-based receipt validation,
dry-run, zero-write, idempotency, conflict, and read-back behavior.

The single Stage A.2 attempt completed with aggregate status `UNCHECKABLE`.
Provider isolation, mount boundary, process cleanup, and configuration passed;
shell environment failed with `process-nonzero`; sandbox/network was
`UNCHECKABLE` with `process-nonzero`; authentication was unavailable. Device
authentication remained disabled, and no logical `codex exec` worker process, runtime-receipt
dry-run, or receipt application ran. The VM, runtime data, and tracked
processes were destroyed and absence was read back. Stage A.2 remains bounded
non-success evidence; it is not converted to runtime-profile `match`, sandbox
compatibility, live-worker success, or receipt evidence. T11 performs no Stage
A.3.

AC-13 is `deferred-to-T12-by-approved-agreement-replan`, not pass and not
omitted. T12 owns shell-environment and sandbox/network compatibility,
supported runtime-profile qualification, unauthenticated Stage A success,
authenticated Stage B, exactly one owner-triggered logical `codex exec` worker-
process invocation, receipt dry-run/apply/read-
back, and exact head/tree/check binding. Stage B is conditionally authorized
only after Stage A fully passes and must use a different fresh Colima VM. Only
for that attempt may device-code authentication be enabled temporarily. The
adapter must classify authentication through the exact allowlist above and
must observe the complete profile as `match` before starting that one logical
worker process. This does not claim exactly one backend model request. After
the worker, the governed sequence is deterministic verification, receipt dry-
run, exact head/tree/check read-back, exactly one runtime-receipt apply,
canonical receipt read-back, provider/runtime destruction, profile/runtime-
data/process absence read-back, and one append-only lifecycle-completion
evidence comment. The lifecycle comment is not a second runtime receipt.
Device-code authentication is disabled after the attempt.

The offline-tested receipt actuator reads one `runtime-receipt-request/v1` on
stdin containing the actual bounded `runtime-profile/v1`, `task-execution-envelope/v1`,
`execution-result/v1`, and verifier artifacts. It validates each native
artifact, calculates canonical artifact digests itself, checks the
profile/envelope/verifier -> result digest graph, and only then derives the
allowlisted `runtime-receipt/v1` projection. Caller-authored evidence
projections are rejected. The artifacts are unsigned JSON, so their provenance
is explicitly `unsigned-unverified`; this slice does not claim authentication
or attestation. The actuator rejects private/raw material including raw JSONL
and requires a fresh matching runtime observation. Limitations
are a closed structured object, not arbitrary prose. Dry-run is canonical and
emits a deterministic binding digest. Runtime `--apply` requires that exact
digest through `--dry-run-proof-sha256`; the digest binds the same validated
receipt and rendered body but is not an authenticated attestation.
The receipt projects only safe provider classifications, booleans, public Git
bindings, timestamps, and digests. It excludes raw mount inventories and
paths, doctor reports, environment values, credentials, JSONL, stderr,
transcripts, and reasoning. At receipt time the pre-live provider record must
say `destroy_required=true`, `destroy_requested=false`,
`destroy_completed=false`, and `profile_absence_readback=not-run`. Receipt
application precedes VM destruction, so destroy completion and the final
profile-absence read-back are recorded only afterward as separate append-only
owner/adapter evidence; the receipt must not claim them early.
When separately authorized in T12, `--apply` preflights a bounded comment set
using a stable attempt/digest marker:
the same receipt is idempotent without POST, any marker for a different attempt
fails because the bounded live attempt permits exactly one durable runtime
receipt, a conflicting same-attempt marker fails, and an uncertain POST is
reconciled by read-back before any retry. POST body bytes travel only on stdin;
comments are never edited or deleted. Exact read-back and a second post-write
head/tree/check read are required. The receipt does not change
`release_blocked`, scenario states, a Ruleset, a tag, or a release.

The T11 lifecycle actuator was fixture-tested against Issue #23 and PR #24 and
was not applied. T12 dynamically binds its own exact Task plus a same-
repository, non-fork PR on `codex/phase-2-live-codex-runtime` through GitHub
read-back rather than a guessed static PR number. The
`t12-colima-lifecycle-completion-request/v1` path uses
`--lifecycle-dry-run` to render one canonical Issue #25 completion comment and
`--lifecycle-apply` to append that one comment with a stable marker and exact
idempotent read-back. The completion comment is not a second runtime receipt
and is not duplicated on the PR. Its input includes the original validated
native runtime-receipt request. The lifecycle validator regenerates the safe
canonical `runtime-receipt/v1` projection and exact rendered receipt rather
than trusting caller-authored marker/body bytes, then retains only that safe
projection and request digest. It binds the exact runtime-receipt URL,
body/record digests and GitHub `created_at`, the same
attempt/profile/instance/control-plane digest, PR head/tree/checks, destroy
request/completion timestamps, and profile, runtime-data, and tracked-process
absence read-backs. Validation requires runtime-receipt posting before destroy
request, then destroy completion before every absence observation. Every
timestamp is bounded to at most 300 seconds in the future, and each absence
read-back must independently be at most 3600 seconds old when the actuator
validates it. Raw provider state, paths, credentials, auth files, device codes,
environment, JSONL, stderr, transcripts, and reasoning are rejected.

T12 intentionally qualifies official stable Codex CLI `0.150.1` as one exact
receipt-bound compatibility baseline. It does not describe that version as the
current latest stable, generalize to every stable version, or permit a switch
to `0.151.0` without an ownership and source-review replan. The bounded source-
parity contribution is capability-aware routing for this one exact profile,
bounded worker execution, a durable attempt/receipt trail, independent
verification over worker self-claim, and privacy by reference. It does not
complete K09, K10, K11, K12, or full runtime parity.
