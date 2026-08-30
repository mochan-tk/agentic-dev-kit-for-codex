# Minimal Codex execution loop

This document is the human-readable companion to the T11 runtime schemas. The
machine schemas are authoritative for record shape; deterministic code and
current Git/GitHub evidence are authoritative for execution facts.

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

## Runtime isolation

The live argv selects the approved exact binary, model, and reasoning effort;
uses `codex exec --json --ephemeral --strict-config --ignore-user-config` in a
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
details or the raw report. A warning or failure blocks T11 only for a required
auth, config, runtime, or sandbox check; unrelated advisory warnings produce
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

The approved T11 outer containment boundary is one fresh, attempt-only Colima
Linux VM using the VZ backend and native `aarch64`. Its profile name is
`t11-e2e-<exact-public-head-first-12>-01`. The host Mac, default Colima
profile, any existing VM/container/volume, and PID tracking alone are not the
approved boundary. The repository is cloned from GitHub onto the VM private
disk and checked against the exact public PR head/tree; the host repository,
HOME, Codex/GitHub credentials, SSH agent, Docker socket, private TMPDIR, and
unrelated paths are not shared.

For T11, the outer containment claim consists only of that fresh disposable
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
keeps the dedicated private VM `CODEX_HOME` unauthenticated. Stage B, if later
approved after Stage A.1 review, uses a separate fresh VM and device
authorization in its own dedicated private `CODEX_HOME`; credential values,
device codes, and authentication files never enter artifacts or durable
output.

### Stage A.1 Git and bubblewrap prerequisites

The current bounded attempt qualifies the documented Git and bubblewrap
prerequisites inside a fresh disposable Colima VM before any Codex shell-
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
and hooks, and expected clean checkout. The adapter recomputes that digest and
then proves the resulting checkout head/tree/status. This cross-binding checks
the reviewed contract and post-clone equality; because repository code is not
available before clone, it does not independently authenticate that the outer
owner/controller executed the asserted pre-clone chronology.

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
stronger control is deferred to T12. The approved disposable Colima VM is the
outer containment boundary. No raw output is copied into the durable result.

Immediately around the worker, one private execution root contains only the
target repository, private HOME, and private TMPDIR. A bounded descriptor-
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

## Runtime profile states

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
Immediately before a
live worker, the full sensor runs again and must equal the supplied semantic
profile except for its observation timestamp.

Exact-worker-argv construction fails safely with a fixed `stage` and
`reason_code`, never exception text, raw argv, or a private path. The only
allowed stages are `load-envelope`, `load-static-role`,
`environment-contract`, `build-argv`, `argv-policy`, `schema-binding`, and
`filesystem-binding`.

## Offline and live evidence

Required CI uses only fixtures, a fake process, private synthetic Git
repositories, schemas, and deterministic tests. It has no Codex authentication,
network, model spend, live mode, or GitHub write. Live execution and receipt
`--apply` require separate explicit modes and all T11 gates.

The next live-path attempt is Stage A.1 only. It uses a fresh unauthenticated
Colima VM, performs no device authentication or model invocation, qualifies
Git before the private-disk clone, and then qualifies bubblewrap. Only after
the direct smoke passes may it run the Codex shell-environment and sandbox/
network probes. It does not start a live worker or run a runtime-receipt dry-
run/application.

Device-code authentication remains disabled throughout Stage A.1. Stage A.1
appends only closed, allowlisted probe evidence to Issue #23 and PR
#24. That evidence binds the exact head/tree/checks, no-auth/no-model facts,
prerequisite outcome, separate lane statuses, and destruction/absence
read-back without a live result bundle or runtime-receipt claim. The VM is
destroyed, profile/runtime-data/process absence is read back, and the attempt
stops for owner judgment. A successful Stage A.1 record is not a runtime
`match`, live Task evidence, a live runtime receipt, or authority to start
Stage B; it cannot consume the exactly-once Stage B receipt marker.

Stage B requires that later review and uses a different fresh Colima VM. Only
for that attempt may device-code authentication be enabled temporarily. The
adapter must classify authentication through the exact allowlist above and
must observe the complete profile as `match` before starting exactly one live
worker. Receipt dry-run/application and destruction follow only that live
success, after which device-code authentication is disabled again.

The receipt actuator reads one `runtime-receipt-request/v1` on stdin containing
the actual bounded `runtime-profile/v1`, `task-execution-envelope/v1`,
`execution-result/v1`, and verifier artifacts. It validates each native
artifact, calculates canonical artifact digests itself, checks the
profile/envelope/verifier -> result digest graph, and only then derives the
allowlisted `runtime-receipt/v1` projection. Caller-authored evidence
projections are rejected. The artifacts are unsigned JSON, so their provenance
is explicitly `unsigned-unverified`; this slice does not claim authentication
or attestation. The actuator rejects private/raw material including raw JSONL
and requires a fresh matching runtime observation. Limitations
are a closed structured object, not arbitrary prose. Dry-run is canonical.
The receipt projects only safe provider classifications, booleans, public Git
bindings, timestamps, and digests. It excludes raw mount inventories and
paths, doctor reports, environment values, credentials, JSONL, stderr,
transcripts, and reasoning. At receipt time the pre-live provider record must
say `destroy_required=true`, `destroy_requested=false`,
`destroy_completed=false`, and `profile_absence_readback=not-run`. Receipt
application precedes VM destruction, so destroy completion and the final
profile-absence read-back are recorded only afterward as separate append-only
owner/adapter evidence; the receipt must not claim them early.
`--apply` preflights a bounded comment set using a stable attempt/digest marker:
the same receipt is idempotent without POST, any marker for a different attempt
fails because T11 permits exactly one durable runtime receipt, a conflicting
same-attempt marker fails, and an uncertain POST is reconciled by read-back before any retry. POST
body bytes travel only on stdin; comments are never edited or deleted. Exact
read-back and a second post-write head/tree/check read are required. The receipt does not change `release_blocked`, scenario
states, a Ruleset, a tag, or a release.

After that runtime receipt is posted, destruction uses a separate closed
`t11-colima-lifecycle-receipt-request/v1` actuator. `--lifecycle-dry-run`
renders canonical Issue #23 and PR #24 copies; `--lifecycle-apply` appends each
copy with a target-specific stable marker and idempotent read-back. Its input
includes the original validated native runtime-receipt request. The lifecycle
validator regenerates the safe canonical `runtime-receipt/v1` projection and
its exact rendered comment rather than trusting caller-authored marker/body
bytes, then retains only that safe projection and request digest. It binds the
exact runtime-receipt URL, body/record digests and GitHub `created_at`, the
same attempt/profile/instance/control-plane digest, PR head/tree/checks,
destroy request/completion timestamps, and both profile/runtime-data absence
read-backs. Validation requires runtime-receipt posting before destroy request,
then destroy completion before both absence observations. Every timestamp is
bounded to at most 300 seconds in the future and the latest absence read-back
must be at most 3600 seconds old when the actuator validates it. Raw provider state,
paths, credentials, auth files, device codes, environment, JSONL, stderr,
transcripts, and reasoning are rejected.
