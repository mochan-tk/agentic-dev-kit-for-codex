# Repository-level definition of done

## Current status

The repository implementation is incomplete and `release_blocked` is `true`.
Phase 0 is complete and Phase 1 is in progress, but accepted foundations are
not a parity or release claim.

No individual phase completion constitutes repository-level completion.
No Task or Epic completion constitutes repository-level completion either.
The overall repository implementation remains incomplete until every required contract has current target-side evidence and a human-reviewed completion pull request changing `release_blocked` to `false` is merged.

## Normative completion requirements

Repository completion requires all of the following at one current target
head. These are normative gates, not progress checkboxes:

1. All eight repository Skills are implemented, documented, and validated on
   their supported Codex surfaces.
2. All six custom agents are implemented and validated without being claimed
   as authenticated identities or immutable permission boundaries.
3. The project hooks and handlers are implemented and validated for their
   supported paths as defense in depth, without claiming universal or
   authenticated enforcement.
4. The Epic, Task, and PR ledger schemas and their deterministic validation are
   implemented.
5. The Task execution envelope and loop-event schemas are implemented with
   bounded, machine-readable receipts.
6. The Codex execution adapter is implemented and validated against its named,
   pinned client surface.
7. The installer and upgrade behavior are implemented and proven to preserve
   tuned surfaces and adopter instance truth.
8. The Task ritual, ownership, and governance sensors and explicit actuators
   are implemented and validated fail closed.
9. A clean-repository installation and end-to-end Task exercise succeeds with
   current target-side evidence.
10. Evidence for all 136 conformance scenarios is current target-side evidence
    satisfying each scenario's expected target behavior and any
    release-required pass or status criterion; no release-required scenario
    remains merely planned, `not-run`, failed, or otherwise non-successful.
11. Every contract K01 through K20 has current target-side evidence satisfying
    its reviewed acceptance contract.
12. The repository owner reviews and merges a dedicated completion pull
    request whose evidence is bound to its exact head and whose only authorized
    release transition changes `release_blocked` from `true` to `false`.

## Evidence semantics

Evidence must be target-side, current for the completion pull-request head,
bounded, and reproducible or independently inspectable. Missing, stale,
`UNKNOWN`, `UNCHECKABLE`, `fail`, `failed`, unverified, skipped, and synthetic
evidence are non-success states. A narrative report, thread, agent assertion,
board field, Phase result, or Task result cannot substitute for the required
evidence.

Every K01-K20 prerequisite remains required even if a later implementation
groups contracts under one artifact or check. Evidence may be shared only when
it demonstrably satisfies each named contract without weakening its meaning.

## Authority and transition

Humans retain agreement, high-risk exception, final acceptance, and merge
authority. CI and agents may verify that the prerequisites are present, but
they cannot declare repository completion on their own. Only the merged,
human-reviewed completion pull request described above may change
`release_blocked` to `false`.

Until that transition, completion of any Task, Epic, or Phase leaves the
overall repository implementation incomplete.
