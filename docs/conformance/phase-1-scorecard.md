# Phase 1 conformance scorecard

## Result

This is the human-readable view of the Phase 1 portable-core acceptance
candidate. It covers all 136 canonical scenarios across all 14 families, but
records **zero scenario-action passes**. Every scenario remains `not-run`.
That is an explicit non-pass state, not a failure hidden by an aggregate.

This exact T10 tree is the Phase 1 portable-core acceptance candidate. When
its exact-head `quality` and `conformance` checks are green and no blocking
finding remains, it satisfies the portable-core implementation-complete gate;
the Phase 1 portable-core implementation is complete in that exact tree.
Durable owner acceptance remains pending merge and exact post-merge receipt.

The overall repository implementation remains incomplete and
`release_blocked` remains `true`. A later post-merge receipt can accept the
Phase 1 portable core; it cannot convert unrun scenarios into passes or
establish repository completion.

## Family scorecard

| Family | Scope | Total | Pass | Non-pass | Canonical state |
|---|---|---:|---:|---:|---|
| C | Constitution and durable truth | 5 | 0 | 5 | `not-run` |
| A | AGENTS.md hierarchy | 6 | 0 | 6 | `not-run` |
| S | Repository Skills | 8 | 0 | 8 | `not-run` |
| R | Custom agents and subagents | 10 | 0 | 10 | `not-run` |
| E | Task Execution Envelope and loop events | 10 | 0 | 10 | `not-run` |
| H | Hooks | 10 | 0 | 10 | `not-run` |
| W | Local, worktree, cloud, and non-interactive execution | 12 | 0 | 12 | `not-run` |
| T | GitHub Task/PR ritual parity | 16 | 0 | 16 | `not-run` |
| O | Ownership | 7 | 0 | 7 | `not-run` |
| I | Installer and upgrade | 15 | 0 | 15 | `not-run` |
| G | Governance, Rulesets, and workflow safety | 13 | 0 | 13 | `not-run` |
| P | Feedback and retrospective | 12 | 0 | 12 | `not-run` |
| D | Source-defect regression scenarios | 4 | 0 | 4 | `not-run` |
| X | End-to-end release scenarios | 8 | 0 | 8 | `not-run` |
| **Total** |  | **136** | **0** | **136** | **non-pass** |

The per-scenario canonical inventory is
[`tests/conformance/results/phase-1.json`](../../tests/conformance/results/phase-1.json).
The checker compares its order and IDs directly with the canonical catalog,
rejects duplicates and omissions, and rejects any `pass` without exact
scenario-action evidence. `UNKNOWN`, `UNCHECKABLE`, deferred, skipped,
unverified, stale, and missing evidence are also non-success.

The legacy Phase 0 compatibility manifest remains unchanged and pin-fresh.
This standalone scorecard is discovered through the acceptance checker,
versioned quality registry/workflow, and README. The
[bounded T10 replan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12#issuecomment-5419726866)
records that compatibility boundary.

## Per-scenario scorecard

| Scenario | Family | Scope disposition | Status | Exact action evidence |
|---|---|---|---|---|
| C-001 | C | `planned` | `not-run` | none; exact action not run |
| C-002 | C | `planned` | `not-run` | none; exact action not run |
| C-003 | C | `planned` | `not-run` | none; exact action not run |
| C-004 | C | `agreement-decision` | `not-run` | none; exact action not run |
| C-005 | C | `planned` | `not-run` | none; exact action not run |
| A-001 | A | `planned` | `not-run` | none; exact action not run |
| A-002 | A | `target-specialization` | `not-run` | none; exact action not run |
| A-003 | A | `planned` | `not-run` | none; exact action not run |
| A-004 | A | `planned` | `not-run` | none; exact action not run |
| A-005 | A | `planned` | `not-run` | none; exact action not run |
| A-006 | A | `planned` | `not-run` | none; exact action not run |
| S-001 | S | `planned` | `not-run` | none; exact action not run |
| S-002 | S | `planned` | `not-run` | none; exact action not run |
| S-003 | S | `planned` | `not-run` | none; exact action not run |
| S-004 | S | `planned` | `not-run` | none; exact action not run |
| S-005 | S | `planned` | `not-run` | none; exact action not run |
| S-006 | S | `planned` | `not-run` | none; exact action not run |
| S-007 | S | `planned` | `not-run` | none; exact action not run |
| S-008 | S | `planned` | `not-run` | none; exact action not run |
| R-001 | R | `planned` | `not-run` | none; exact action not run |
| R-002 | R | `planned` | `not-run` | none; exact action not run |
| R-003 | R | `planned` | `not-run` | none; exact action not run |
| R-004 | R | `planned` | `not-run` | none; exact action not run |
| R-005 | R | `planned` | `not-run` | none; exact action not run |
| R-006 | R | `planned` | `not-run` | none; exact action not run |
| R-007 | R | `planned` | `not-run` | none; exact action not run |
| R-008 | R | `planned` | `not-run` | none; exact action not run |
| R-009 | R | `planned` | `not-run` | none; exact action not run |
| R-010 | R | `planned` | `not-run` | none; exact action not run |
| E-001 | E | `planned` | `not-run` | none; exact action not run |
| E-002 | E | `planned` | `not-run` | none; exact action not run |
| E-003 | E | `planned` | `not-run` | none; exact action not run |
| E-004 | E | `planned` | `not-run` | none; exact action not run |
| E-005 | E | `planned` | `not-run` | none; exact action not run |
| E-006 | E | `planned` | `not-run` | none; exact action not run |
| E-007 | E | `planned` | `not-run` | none; exact action not run |
| E-008 | E | `planned` | `not-run` | none; exact action not run |
| E-009 | E | `planned` | `not-run` | none; exact action not run |
| E-010 | E | `planned` | `not-run` | none; exact action not run |
| H-001 | H | `planned` | `not-run` | none; exact action not run |
| H-002 | H | `planned` | `not-run` | none; exact action not run |
| H-003 | H | `planned` | `not-run` | none; exact action not run |
| H-004 | H | `planned` | `not-run` | none; exact action not run |
| H-005 | H | `planned` | `not-run` | none; exact action not run |
| H-006 | H | `planned` | `not-run` | none; exact action not run |
| H-007 | H | `planned` | `not-run` | none; exact action not run |
| H-008 | H | `planned` | `not-run` | none; exact action not run |
| H-009 | H | `planned` | `not-run` | none; exact action not run |
| H-010 | H | `planned` | `not-run` | none; exact action not run |
| W-001 | W | `planned` | `not-run` | none; exact action not run |
| W-002 | W | `planned` | `not-run` | none; exact action not run |
| W-003 | W | `planned` | `not-run` | none; exact action not run |
| W-004 | W | `planned` | `not-run` | none; exact action not run |
| W-005 | W | `planned` | `not-run` | none; exact action not run |
| W-006 | W | `planned` | `not-run` | none; exact action not run |
| W-007 | W | `planned` | `not-run` | none; exact action not run |
| W-008 | W | `target-specialization` | `not-run` | none; exact action not run |
| W-009 | W | `planned` | `not-run` | none; exact action not run |
| W-010 | W | `planned` | `not-run` | none; exact action not run |
| W-011 | W | `planned` | `not-run` | none; exact action not run |
| W-012 | W | `planned` | `not-run` | none; exact action not run |
| T-001 | T | `planned` | `not-run` | none; exact action not run |
| T-002 | T | `planned` | `not-run` | none; exact action not run |
| T-003 | T | `planned` | `not-run` | none; exact action not run |
| T-004 | T | `planned` | `not-run` | none; exact action not run |
| T-005 | T | `planned` | `not-run` | none; exact action not run |
| T-006 | T | `planned` | `not-run` | none; exact action not run |
| T-007 | T | `planned` | `not-run` | none; exact action not run |
| T-008 | T | `planned` | `not-run` | none; exact action not run |
| T-009 | T | `planned` | `not-run` | none; exact action not run |
| T-010 | T | `planned` | `not-run` | none; exact action not run |
| T-011 | T | `planned` | `not-run` | none; exact action not run |
| T-012 | T | `planned` | `not-run` | none; exact action not run |
| T-013 | T | `planned` | `not-run` | none; exact action not run |
| T-014 | T | `planned` | `not-run` | none; exact action not run |
| T-015 | T | `planned` | `not-run` | none; exact action not run |
| T-016 | T | `planned` | `not-run` | none; exact action not run |
| O-001 | O | `planned` | `not-run` | none; exact action not run |
| O-002 | O | `planned` | `not-run` | none; exact action not run |
| O-003 | O | `planned` | `not-run` | none; exact action not run |
| O-004 | O | `planned` | `not-run` | none; exact action not run |
| O-005 | O | `planned` | `not-run` | none; exact action not run |
| O-006 | O | `planned` | `not-run` | none; exact action not run |
| O-007 | O | `planned` | `not-run` | none; exact action not run |
| I-001 | I | `planned` | `not-run` | none; exact action not run |
| I-002 | I | `planned` | `not-run` | none; exact action not run |
| I-003 | I | `planned` | `not-run` | none; exact action not run |
| I-004 | I | `planned` | `not-run` | none; exact action not run |
| I-005 | I | `planned` | `not-run` | none; exact action not run |
| I-006 | I | `planned` | `not-run` | none; exact action not run |
| I-007 | I | `planned` | `not-run` | none; exact action not run |
| I-008 | I | `planned` | `not-run` | none; exact action not run |
| I-009 | I | `planned` | `not-run` | none; exact action not run |
| I-010 | I | `planned` | `not-run` | none; exact action not run |
| I-011 | I | `planned` | `not-run` | none; exact action not run |
| I-012 | I | `planned` | `not-run` | none; exact action not run |
| I-013 | I | `planned` | `not-run` | none; exact action not run |
| I-014 | I | `planned` | `not-run` | none; exact action not run |
| I-015 | I | `planned` | `not-run` | none; exact action not run |
| G-001 | G | `planned` | `not-run` | none; exact action not run |
| G-002 | G | `planned` | `not-run` | none; exact action not run |
| G-003 | G | `planned` | `not-run` | none; exact action not run |
| G-004 | G | `planned` | `not-run` | none; exact action not run |
| G-005 | G | `planned` | `not-run` | none; exact action not run |
| G-006 | G | `planned` | `not-run` | none; exact action not run |
| G-007 | G | `planned` | `not-run` | none; exact action not run |
| G-008 | G | `planned` | `not-run` | none; exact action not run |
| G-009 | G | `planned` | `not-run` | none; exact action not run |
| G-010 | G | `planned` | `not-run` | none; exact action not run |
| G-011 | G | `planned` | `not-run` | none; exact action not run |
| G-012 | G | `planned` | `not-run` | none; exact action not run |
| G-013 | G | `planned` | `not-run` | none; exact action not run |
| P-001 | P | `planned` | `not-run` | none; exact action not run |
| P-002 | P | `planned` | `not-run` | none; exact action not run |
| P-003 | P | `planned` | `not-run` | none; exact action not run |
| P-004 | P | `planned` | `not-run` | none; exact action not run |
| P-005 | P | `planned` | `not-run` | none; exact action not run |
| P-006 | P | `planned` | `not-run` | none; exact action not run |
| P-007 | P | `planned` | `not-run` | none; exact action not run |
| P-008 | P | `planned` | `not-run` | none; exact action not run |
| P-009 | P | `planned` | `not-run` | none; exact action not run |
| P-010 | P | `planned` | `not-run` | none; exact action not run |
| P-011 | P | `planned` | `not-run` | none; exact action not run |
| P-012 | P | `planned` | `not-run` | none; exact action not run |
| D-001 | D | `planned` | `not-run` | none; exact action not run |
| D-002 | D | `planned` | `not-run` | none; exact action not run |
| D-003 | D | `planned` | `not-run` | none; exact action not run |
| D-004 | D | `planned` | `not-run` | none; exact action not run |
| X-001 | X | `planned` | `not-run` | none; exact action not run |
| X-002 | X | `planned` | `not-run` | none; exact action not run |
| X-003 | X | `planned` | `not-run` | none; exact action not run |
| X-004 | X | `planned` | `not-run` | none; exact action not run |
| X-005 | X | `planned` | `not-run` | none; exact action not run |
| X-006 | X | `planned` | `not-run` | none; exact action not run |
| X-007 | X | `planned` | `not-run` | none; exact action not run |
| X-008 | X | `planned` | `not-run` | none; exact action not run |

## Contract disposition

| Contract | Machine status | Advanced | Remaining | Later lane / owner state |
|---|---|---|---|---|
| K01 | `phase-1-static-advanced` | Option B hierarchy and accepted Task evidence are durable. | Runtime recovery and live ritual evidence remain absent. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K02 | `phase-1-static-advanced` | Static record, evidence, and escalation contracts are present. | Live orchestration and current-attempt enforcement remain absent. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K03 | `partial-incomplete` | Policy and orchestration guidance define the topology. | Authenticated roles and six custom agents remain unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K04 | `phase-1-static-advanced` | Versioned exact-path ownership and overlap rejection are active in CI. | Envelope and cross-surface runtime enforcement remain absent. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K05 | `phase-1-static-advanced` | Human gates and risk fields are durable static contracts. | Runtime identity and universal control-plane enforcement remain absent. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K06 | `phase-1-static-advanced` | Stable requirements, decisions, context pins, and connector-neutral operations are checked. | External connectors and cross-surface runtime reachability are not proven. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K07 | `phase-1-static-advanced` | Epic, Task, and PR human/machine contracts are synchronized and checked. | Live Task ritual and GitHub-body equality require later runtime work. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K08 | `phase-1-static-advanced` | Exactly eight Skills and source-to-target parity records are statically checked. | Runtime invocation, implicit selection, and cross-surface evidence remain not-run. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K09 | `incomplete-later-phase` | Role semantics exist only as policy. | Six custom agents and authenticated role evidence are unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K10 | `incomplete-later-phase` | No Phase 1 implementation claim is made. | task-execution-envelope/v1 is unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K11 | `incomplete-later-phase` | No Phase 1 implementation claim is made. | loop-event/v1 is unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K12 | `incomplete-later-phase` | The machine-readable surface boundary is documented. | The codex exec adapter and normalized stream handling are unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K13 | `incomplete-later-phase` | Upgrade preservation remains a canonical invariant. | Installer, upgrade, adoption, and rollback behavior are unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K14 | `incomplete-later-phase` | Ledger fields provide a static foundation only. | The live Task ritual and current-attempt enforcement are unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K15 | `partial-incomplete` | The solo-fast Ruleset used sensor, intent, explicit actuator, and verification. | General adopter governance activation and reconciliation remain later work. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K16 | `incomplete-later-phase` | The Retro Skill provides static failure-to-harness guidance. | Consent-aware feedback transport and telemetry are unimplemented. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K17 | `phase-1-static-advanced` | Pinned tools, least privilege, stable required jobs, and deterministic discovery are checked. | Release, clean-adopter E2E, and all runtime matrices remain later work. | `future-repository-release-and-parity` (`unassigned`) |
| K18 | `phase-1-static-advanced` | Known defects and Codex-native adaptations have durable records and regressions. | Full source parity reconciliation remains later work. | `future-repository-release-and-parity` (`unassigned`) |
| K19 | `phase-1-static-advanced` | Core contracts remain model-neutral and control-plane limits are explicit. | No universal authenticated runtime identity or control plane exists. | `future-runtime-distribution-and-governance` (`unassigned`) |
| K20 | `blocked-release` | The canonical catalog and empty result store make the release boundary explicit. | Full static/runtime parity, 136 scenario passes, clean-adopter E2E, and release evidence are absent. | `future-repository-release-and-parity` (`unassigned`) |

Epic #2 does not own the out-of-scope remainder. No later owner is currently
assigned. The machine record separates a future
`future-runtime-distribution-and-governance` lane from a future
`future-repository-release-and-parity` lane. A human-reviewed Phase, Epic, or
Task must claim a lane before implementation; this scorecard authorizes none.

## Evidence boundary

T01–T09 exact Task/PR/merge/check evidence is indexed in the machine record
and the [acceptance record](../planning/phase-1-acceptance.md). T10 exact-head
evidence belongs in the PR and Issue #12 receipt because embedding a commit's
own identifier in that commit is impossible. Post-merge evidence remains
pending until a later read-back. The release-level result store remains empty:
`result_count: 0`, `results: []`, and `release_blocked: true`.
