# Phase 1 conformance scorecard

## Result

This is the human-readable view of the Phase 1 portable-core acceptance
candidate. It covers all 136 canonical scenarios across all 14 families, but
records **zero scenario-action passes**. Every scenario remains `not-run`.
That is an explicit non-pass state, not a failure hidden by an aggregate.

Phase 1 portable-core implementation is complete in this reviewed T10 tree;
durable owner acceptance remains pending merge and exact post-merge receipt.

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

| Contract | Phase 1 disposition | Later boundary |
|---|---|---|
| K01 | Static hierarchy and durable-truth foundation advanced | Runtime recovery and ritual evidence remain later work. |
| K02 | Static record/verify/escalate contracts advanced | Live orchestration remains later work. |
| K03 | Constitution and Skill guidance advanced | Authenticated supervisor/worker runtime is absent. |
| K04 | Deterministic ownership and single-writer policy advanced | Envelope/runtime enforcement is absent. |
| K05 | Human authority and risk gates advanced | Runtime identity/control-plane enforcement is absent. |
| K06 | Connector-neutral context contract advanced | Cross-surface connector runtime is not proven. |
| K07 | Epic/Task/PR ledger schemas advanced | Live Task ritual is not implemented. |
| K08 | Eight repository Skills statically verified | Runtime invocation and cross-surface evidence remain not-run. |
| K09 | Policy only | Six custom agents and role-runtime evidence are unimplemented. |
| K10 | Incomplete | `task-execution-envelope/v1` is unimplemented. |
| K11 | Incomplete | `loop-event/v1` is unimplemented. |
| K12 | Incomplete | The `codex exec` adapter is unimplemented. |
| K13 | Incomplete | Installer and upgrade safety are unimplemented. |
| K14 | Incomplete | Live Task ritual and current-attempt enforcement are unimplemented. |
| K15 | Ruleset sensor/intent/actuator evidence advanced | General adopter governance activation remains later work. |
| K16 | Retro Skill static guidance only | Consent feedback transport is unimplemented. |
| K17 | Pinned least-privilege CI and deterministic registry advanced | Release and adopter E2E validation remain later work. |
| K18 | Source-deviation records and regressions advanced | Full source parity audit remains later work. |
| K19 | Model-neutral contracts and limits documented | No universal runtime identity/control plane exists. |
| K20 | Blocked | Full static/runtime parity, 136 scenario passes, and release evidence are absent. |

All incomplete items remain owned by the rolling-wave frontier under
[Epic #2](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2).
No later implementation is authorized merely by this scorecard.

## Evidence boundary

T01–T09 exact Task/PR/merge/check evidence is indexed in the machine record
and the [acceptance record](../planning/phase-1-acceptance.md). T10 exact-head
evidence belongs in the PR and Issue #12 receipt because embedding a commit's
own identifier in that commit is impossible. Post-merge evidence remains
pending until a later read-back. The release-level result store remains empty:
`result_count: 0`, `results: []`, and `release_blocked: true`.
