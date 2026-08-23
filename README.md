# Agentic Development Kit for Codex

> [!WARNING]
> **Phase 0 bootstrap:** this repository is not installable and is not a parity release.
> It currently contains only the constitution, frozen-source
> provenance, limitations, and the first conformance wall.

This project is the Codex-native edition of the governed agentic-development
harness in
[`mochan-tk/agentic-dev-kit-for-copilot`](https://github.com/mochan-tk/agentic-dev-kit-for-copilot).
It preserves product-independent behavior and governance while replacing
Copilot-specific execution surfaces with verified Codex-native adapters.

The frozen behavioral source is commit
[`fd265ddef150fab86cd54d0e383c2c25fe297ffb`](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/commit/fd265ddef150fab86cd54d0e383c2c25fe297ffb).
Phase 0 does not copy the source wholesale and does not silently reproduce
known source defects.

## Durable operating model

```text
GitHub Project -> Epic issue -> Task issue -> PR -> commits/checks/evidence
```

GitHub is durable truth. Codex threads and subagents are execution contexts,
not the project hierarchy. One Task has one active supervisor responsibility;
one PR has one active writer, branch, and worktree. Completion requires current
acceptance evidence, not an agent narrative.

The reviewed invariant table lives in [`AGENTS.md`](AGENTS.md). The initial
audit and file-ownership plan lives in
[`docs/planning/phase-0-orientation.md`](docs/planning/phase-0-orientation.md).

## What Phase 0 provides

- a compact, product-independent operating constitution;
- exact source commit, tree, research-pack, and scenario-catalog provenance;
- a machine-readable conformance manifest with an explicit release blocker;
- a dated Codex capability audit that separates documented behavior from
  local and cross-surface verification;
- prominent known limitations;
- offline negative tests for baseline, invariant, workflow, and ownership
  drift;
- minimal SHA-pinned, least-privilege `quality` and `conformance` CI jobs.

## What Phase 0 deliberately does not provide

- an installer or upgrade path;
- GitHub Epic/Task/PR templates or the Task ritual guard;
- the eight repository Skills;
- Codex custom-agent definitions;
- hooks, execution envelopes, or normalized loop events;
- a `codex exec` task wrapper;
- governance setup, Ruleset reconciliation, or adopter feedback;
- local/worktree/cloud parity claims;
- authenticated runtime roles, universal heartbeat/budget/control, or
  automatic merge.

See [`docs/known-limitations.md`](docs/known-limitations.md) before relying on
any capability.

## Port sequence

1. **Phase 0:** constitution, audit provenance, limitations, conformance
   vocabulary, and bootstrap CI.
2. **Portable core:** GitHub ledger/contracts and all eight Codex repository
   Skills.
3. **Codex adapter:** custom agents, Task envelope, hooks/events, and the
   machine-readable CLI adapter.
4. **Enforcement and distribution:** installer/upgrade, Task ritual,
   ownership, and governance.
5. **Parity release:** static and runtime probes, all 136 conformance
   scenarios, adopter migration, and independently reviewed evidence.

Later work remains blocked until the Phase 0 PR is independently reviewed and
accepted by a human. An unavailable runtime probe is `unverified` or
`skipped`, never passed.

## Phase 0 validation

```sh
python3 -m unittest discover -s tests/conformance -p 'test_*.py'
python3 .github/scripts/check-phase0-contracts.py
bash .github/scripts/tests/test-action-pins.sh
bash .github/scripts/tests/test-workflow-permissions.sh
```

The frozen source's 23-suite result is baseline evidence, not target parity.
The target release remains blocked while the conformance manifest has no
verified results.

## License

Licensed under the [MIT License](LICENSE).
