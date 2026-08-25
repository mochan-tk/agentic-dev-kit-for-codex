# ADR-0007: Connector-neutral exact context contract

- Status: Proposed; accepted when Issue #10's dedicated pull request is owner-merged
- Date: 2026-08-25
- Decision owner: repository owner
- Task: https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/10
- Decision record: `docs/agreements/decisions/DEC-0001.json`
- Supersedes: none

## Context

The portable core needs stable requirements and decisions that remain reachable
from local, worktree, cloud, and future adapter surfaces. The ledger delivered
by T07 has a generic References field but no context-pin-specific field. Its
ownership is not reopened by this Task.

The frozen source is
`mochan-tk/agentic-dev-kit-for-copilot@fd265ddef150fab86cd54d0e383c2c25fe297ffb`
(tree `88f96493ec167602750c8dfec044629bd494a586`). Its pluggable context
contract requires stable requirement IDs, append-only decisions, cross-surface
reachability, and pinned references. The supplied research archive has SHA-256
`55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7`.
These provenance values are evidence inputs, not runtime authority.

The exact frozen source inputs are:

| Source path | Blob ID |
|---|---|
| `.github/connectors/README.md` | `386639f24f8323ce92bed53c5ea6518bc50c2dc5` |
| `.github/docs/agreements/requirements.md` | `f68e5804e54c7e71ce65775794685bab70270676` |
| `.github/docs/agreements/adr/ADR-0000-template.md` | `269f127a929cf24e2f9979c189a725b2683bb80d` |
| `.github/docs/context/README.md` | `3b915dda3cd9968757c90d8d3a03f11e6378e0b6` |
| `docs/agreements/adr/ADR-0001-pluggable-context-connectors.md` | `5c201dec9ad2a14b3d3556b78129eaed41650f55` |

Intentional target deviations are explicit:

- source `REQ-###` becomes fixed-width target `REQ-####`;
- source ADR history is split into machine `DEC-####` plus a human ADR;
- `retrieve` returns bounded in-memory material, while repository landing is a
  separate explicit proposal actuator;
- connector metadata and concrete connector validation are deferred;
- the immutable highest `PIN-####` ID selects the current pin without editing
  historical pins; and
- live labels and the runtime Task ritual remain deferred.

## Decision

Adopt `portable-context-contract/v1` and `context-pin/v1`. Requirements and
decisions are immutable after their introducing Task base; semantic changes
are new records with explicit earlier-only supersedes links. One selected pin
binds exact repository paths to a commit, tree, blobs, per-source digests, and
an aggregate digest. The selected pin must match the exact `HEAD` tree, Git
index, and bounded no-follow live worktree bytes and modes at both the
decomposition and execution gates.

Expose exactly four connector-neutral operations: `discover`, `retrieve`,
`pin`, and `verify`. No external service, credential, or concrete connector is
required or activated by this decision.

The new REQ/DEC records use `accepted-on-owner-merge`: this is a prospective
status on the branch and becomes authoritative only through owner merge to the
default branch. It does not claim pre-merge human acceptance.

Use the Task References field only as a durable link to the commit and pin
record. Linkage does not establish pin validity or freshness; deterministic
Git-object verification does.

## Consequences

- Historical decisions and requirements cannot be edited in place after they
  are present at an active Task base.
- Historical pins remain valid when their exact objects remain available even
  if they become stale. Only the selected pin is compared with the current
  tree.
- Missing or uncheckable objects yield non-success evidence instead of a guess.
- Durable machine records exclude sensitive raw material through closed field
  schemas.
- The checker defines and tests the gates but does not prove that a future live
  Task ritual invoked them at every runtime boundary.
- K10, K11, feedback transport, external connectors, and a runtime adapter
  remain unimplemented.
- `retrieve` observes a source and returns bounded in-memory material. Landing
  that material in the repository is a separate explicit proposal actuator.

## Completion boundary

This decision advances Phase 1 portable contracts only. `results` remains
empty, `release_blocked` remains `true`, and repository implementation remains
incomplete.
