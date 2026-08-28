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
a redacted diagnostic support report only. The adapter records a bounded,
allowlisted health summary separately and never promotes it to effective-
configuration evidence. The explicit environment contains bounded PATH,
private HOME, its exact private CODEX_HOME, and private TMPDIR,
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
support is `UNCHECKABLE`. This process-table sensor is not kernel-enforced
containment. Therefore live `match` additionally requires a separately proven
`process_containment_probe=pass`; without that proof the profile is
`UNCHECKABLE` and live execution is blocked. No raw output is copied into the
durable result.

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
trusted as caller metadata. A stable client can reach `match` only after the
documented config-key intent, exact worker argv, diagnostic-health,
shell-environment, network/sandbox-behavior, and process-containment lanes have
their independently required success evidence. An adapter-authored intent
digest or doctor health result alone never proves effective configuration.
Immediately before a
live worker, the full sensor runs again and must equal the supplied semantic
profile except for its observation timestamp.

## Offline and live evidence

Required CI uses only fixtures, a fake process, private synthetic Git
repositories, schemas, and deterministic tests. It has no Codex authentication,
network, model spend, live mode, or GitHub write. Live execution and receipt
`--apply` require separate explicit modes and all T11 gates.

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
`--apply` preflights a bounded comment set using a stable attempt/digest marker:
the same receipt is idempotent without POST, a conflicting same-attempt marker
fails, and an uncertain POST is reconciled by read-back before any retry. POST
body bytes travel only on stdin; comments are never edited or deleted. Exact
read-back and a second post-write head/tree/check read are required. The receipt does not change `release_blocked`, scenario
states, a Ruleset, a tag, or a release.
