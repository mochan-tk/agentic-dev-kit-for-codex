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
configuration-recognition probe. Release class is derived from exact version
syntax. A stable client becomes `match` only when every semantic capability,
configuration, and explicit shell-environment probe passes; the full sensor is
rerun and reconciled immediately before the one live worker.

## Security and privacy consequences

- The worker has `workspace-write`, approval `never`, network disabled, no
  additional writable roots, ephemeral history, hooks/apps/agents/web search/
  feedback/memory disabled, strict config, and ignored user config.
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
  attempt/digest marker with full same-attempt scanning and read-back
  reconciliation for uncertain POST outcomes.
- Linux `/proc` start ticks or Darwin high-resolution `proc_pidinfo` birth
  tokens bind descendant signals across reparenting/setsid and reject PID
  reuse. This process-table tracking closes the deterministic escaped-session
  regression but is not kernel-enforced containment. Live `match` remains
  `UNCHECKABLE` unless a separate containment probe passes.

## Limitations

The three `.codex/agents/*.toml` files are K09-partial static role guidance.
T11 does not prove named-agent runtime selection, authenticated role identity,
full K09 parity, hooks, a generalized Task ritual, installation, upgrade,
feedback transport, or release readiness. Offline fixtures do not constitute a
live Codex run. Only an exact-head supported-profile run and read-back receipt
can supply T11 live evidence; owner merge remains the acceptance gate.
