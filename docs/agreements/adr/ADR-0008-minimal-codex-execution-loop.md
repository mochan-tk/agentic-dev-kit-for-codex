# ADR-0008: Minimal Codex execution loop

- Status: accepted for T11 implementation; live evidence pending
- Decision date: 2026-08-28
- Task: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23>
- Parent Epic: <https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/22>

## Context

Phase 1 established portable contracts and repository Skills, but it deliberately
did not implement an execution envelope, loop events, a Codex adapter, custom
runtime roles, or a live Task ritual. Implementing each surface independently
would postpone evidence that a bounded Task can traverse a complete loop.

## Decision

T11 implements one deliberately narrow vertical slice:

```text
human-authored envelope
-> deterministic Python controller
-> one direct logical-worker codex exec
-> adapter-normalized loop events and execution result
-> fresh deterministic read-only verifier
-> allowlisted append-only GitHub receipt
```

The Python adapter is the only supervisor/controller. The model authors only a
bounded `codex-final-response/v1` value. The adapter, not the model, establishes
process, event, Git, digest, and verifier facts. Receipt publication is a
separate explicit actuator.

The representative target is a private synthetic Git repository whose only
worktree entry is regular mode-`100644` `work-item.txt`. Its exact bytes change
from `status=pending\n` to `status=complete\n`; all other filesystem or Git
change is a failure. The adapter starts exactly one direct logical worker and a
fresh Python verifier process.

All dynamic Task and context bytes travel on stdin. Worker argv may include the
static reviewed `task_worker` developer-instruction string, bound by SHA-256,
but contains no Task prompt. Commands use argv arrays with `shell=false`, an
exact cwd, a minimal environment, bounded output/time, process-group
TERM/KILL/reap handling, and pre/post Git-state verification.

Before live execution a sensor must prove a supported runtime profile.
`profile-drift`, `unsupported-client` (including an unapproved prerelease), `UNKNOWN`, and
`UNCHECKABLE` are non-success and block the worker. Help output alone is not a
configuration-recognition probe, and `codex doctor --json` is diagnostic
health evidence rather than an effective-configuration attestation. The
adapter records its reviewed documented-key intent and digest as
adapter-authored evidence with `effective_configuration_proven=false`, then
keeps shell-environment, network/sandbox behavior, containment, and exact
worker-argv evidence separate. Release class is derived from exact version
syntax. A stable client becomes `match` only when every independently required
lane passes; the full sensor is rerun and reconciled immediately before the
one live worker.

The separately approved containment lane uses one fresh T11-only Colima Linux
VM with VZ and native `aarch64`, named from the exact public head. The guest
clones that head onto its private disk. It neither mounts the host repository
nor reuses the default profile, existing runtime data, or host credentials.
The sole permitted host mount is Colima 0.10.1's unavoidable provider-internal
cache entry, redirected to a fresh attempt-only root and proven read-only; no
other shared mount is permitted. Raw paths remain local-only. The closed
provider evidence is adapter/owner-authored and explicitly not a Codex-issued
authenticated attestation.

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

## Security and privacy consequences

- The worker has `workspace-write`, approval `never`, network disabled, no
  additional writable roots, ephemeral history, hooks/apps/agents/web search/
  feedback/memory disabled, strict config, and ignored user config. Its argv
  never disables execpolicy rules and never uses a dangerous bypass flag; the
  private runtime home supplies the reviewed rules surface.
- The shell environment begins empty and adds only the verified executable
  path, private HOME/TMPDIR, locale/timezone, and deterministic Git/Python
  values. No credential, proxy, or unrelated host value is copied.
- Unexpected project config, hooks, agents, Skills, AGENTS guidance, MCP data,
  symlinks, or extra files prevent invocation.
- Durable records contain allowlisted digests and outcomes, never raw JSONL,
  reasoning, stderr, transcripts, credentials, environment dumps, or private
  local paths.
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
- The append-only receipt validates four native artifacts and derives its
  cross-bound projection. Native JSON provenance remains unsigned/unverified.
  It uses a fresh observation, structured limitations, and an idempotent
  attempt/digest marker with bounded all-attempt scanning. An exact existing
  receipt is idempotent, while a different-attempt marker or conflicting
  same-attempt marker fails closed. Read-back reconciles uncertain POST
  outcomes without creating a second durable runtime receipt.
- Linux `/proc` start ticks or Darwin high-resolution `proc_pidinfo` birth
  tokens bind descendant signals across reparenting/setsid and reject PID
  reuse. This process-table tracking closes the deterministic escaped-session
  regression but is not kernel-enforced containment. Live `match` remains
  `UNCHECKABLE` unless the approved disposable-VM containment lane passes.
- Runtime receipt application occurs before provider destruction. The receipt
  records the pre-live destruction obligation without claiming completion;
  destroy request/completion and profile-absence read-back are later,
  append-only owner/adapter evidence.
- Final destruction uses a distinct lifecycle actuator after the ordinary
  runtime receipt. It posts stable idempotent copies to Issue #23 and PR #24,
  regenerates the canonical receipt projection/comment from the original
  validated native request, cross-binds the linked receipt's GitHub creation
  time, and requires the sequence receipt -> destroy request -> destroy
  completion -> profile and runtime-data absence read-backs. All lifecycle
  timestamps have a 300-second maximum future skew, and the latest absence
  observation must be no more than 3600 seconds old at validation.

## Limitations

The three `.codex/agents/*.toml` files are K09-partial static role guidance.
T11 does not prove named-agent runtime selection, authenticated role identity,
full K09 parity, hooks, a generalized Task ritual, installation, upgrade,
feedback transport, or release readiness. Offline fixtures do not constitute a
live Codex run. Only an exact-head supported-profile run and read-back receipt
can supply T11 live evidence; owner merge remains the acceptance gate.
