# ADR-0004: Freeze the source contract and port by behavior

- **Status:** accepted for bootstrap
- **Date:** 2026-08-24
- **Decision owner:** repository owner through the Codex port handoff
- **Supersedes:** none

## Context

The target repository began empty. The reference implementation is
`mochan-tk/agentic-dev-kit-for-copilot`, frozen at commit
`fd265ddef150fab86cd54d0e383c2c25fe297ffb` and tree
`88f96493ec167602750c8dfec044629bd494a586`.

The source is a GitHub-native Human-on-the-Loop control harness, not a prompt
collection. Its product-independent contract combines a durable GitHub ledger,
Project/Epic/Task/PR hierarchy, role separation, single-writer ownership,
record-before-report, verify-before-done, fail-closed governance, safe
installation/upgrades, and retrospective strengthening of the harness.

A mechanical Copilot-to-Codex rename would retain false assumptions about
session topology, instruction discovery, sandbox authority, hooks, event
schemas, and execution surfaces. The supplied research pack is a high-quality
audit but is not authoritative where frozen source code or current official
behavior differs.

## Decision

1. Treat source commit `fd265ddef150fab86cd54d0e383c2c25fe297ffb` as
   the frozen behavioral baseline. Never modify the source repository while
   building the target.
2. Preserve product-independent contracts by behavior. Adapt or replace only
   the execution adapter and product-specific paths.
3. Keep GitHub as durable truth. Codex threads, subagents, worktrees, and cloud
   tasks are one-to-many execution contexts attached to a Task, not the Task
   graph itself.
4. Make the thirteen invariant statements in root `AGENTS.md` canonical and
   guard their reviewed SHA-256 digest.
5. Record Codex capabilities using the evidence classes `documented`,
   `locally-verified`, `cross-surface-verified`, `unverified`, `unsupported`,
   and `deferred`. No documentation claim alone becomes a runtime pass.
6. Use repository Skills under `.agents/skills/` and project custom agents
   under `.codex/agents/` only in later reviewed phases. Do not claim a Skill
   preload mechanism that official documentation does not define.
7. Treat custom-agent sandbox settings and hooks as defense in depth. Parent
   runtime permissions can change a child's effective sandbox; hooks require
   trust, do not cover every path, and are not a complete fail-closed wall.
8. Build the first programmatic adapter around a pinned `codex exec --json`
   contract. Preserve raw unknown events and distinguish a final-output schema
   from the JSONL event envelope. Defer a mandatory SDK.
9. Record source defects and fix or document each with regression evidence.
   Behavioral parity does not require repeating a defect silently.
10. Keep Phase 0 intentionally incomplete and blocked from release. Later
    implementation starts only after independent review and human acceptance.

## Source deviations recorded at bootstrap

The target will not silently carry these source defects or guard gaps:

- ADR-0003's stale bare `#89` reference;
- the changelog guard's numeric-ceiling check described as existence proof;
- source-only Playwright MCP using a floating `@latest` dependency;
- workflow-permission validation accepting `contents: none` or a blank value;
- Task branch matching that accepts arbitrary suffix collisions;
- adopter-feedback labeling that assumes a missing label is auto-created;
- a case-sensitivity comment inconsistent with implementation and tests;
- stale one-Task/one-session wording after the supervisor/worker split.

The exact audit evidence and intended dispositions are in the Phase 0
orientation record. Later Tasks must add regressions before marking a
deviation resolved.

## Consequences

### Benefits

- The target can evolve independently without losing the source contract.
- Current Codex behavior is dated, sourced, and separated from runtime proof.
- Known uncertainty and unsupported guarantees remain visible.
- The first implementation change is small enough for independent review.

### Costs

- Phase 0 is not installable and provides no operational agent harness.
- Full parity requires porting or replacing the source's 23 guard suites and
  producing results for 136 conformance scenarios.
- Runtime claims require named-client probes across each supported surface.
- GitHub comments, hooks, and thread identifiers remain receipts rather than
  authenticated authority without a separate control plane.

## Verification

Phase 0 CI validates the baseline fields, invariant checksum, release blocker,
ownership allowlist, Action pins, workflow permissions, known-limitations
language, and negative fixtures. A separate read-only governance reviewer must
audit the PR's current head before a human decides whether to merge.

## References

- [Frozen source commit](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/commit/fd265ddef150fab86cd54d0e383c2c25fe297ffb)
- [Source authenticity boundary](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/issues/6)
- [Official AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Official Skills documentation](https://learn.chatgpt.com/docs/build-skills)
- [Official subagent/custom-agent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Official hooks documentation](https://learn.chatgpt.com/docs/hooks)
- [Official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)

