# Phase 1 portable-core acceptance record

## Status and authority

This tree is a **Phase 1 portable-core acceptance candidate** for T10 / Issue
#12. Phase 0 is complete. This exact T10 tree is a Phase 1 portable-core
acceptance candidate. When its exact-head `quality` and `conformance` checks
are green and no blocking finding remains, it satisfies the portable-core
implementation-complete gate: the Phase 1 portable-core implementation is
complete in that exact tree. Durable owner acceptance remains pending merge
and exact post-merge receipt. Phase 1 becomes accepted only after the repository
owner merges the exact reviewed T10 head and the receipt verifies the
merge tree and required checks. The overall repository implementation remains incomplete,
is not installable, and is not a parity release. `release_blocked` remains `true`.

The canonical machine record is
[`tests/conformance/results/phase-1.json`](../../tests/conformance/results/phase-1.json).
This human record explains its boundaries; it is not a substitute for the
machine record, GitHub evidence, or owner judgment.

## Evidence classes

| Class | State in this tree | Success boundary |
|---|---|---|
| `pre_merge` | `candidate` | Exact T10 head, tree, direct commands, and `quality` / `conformance` URLs must be recorded in the PR and Issue #12 receipt. |
| `post_merge` | `pending` | A later receipt must bind the merge commit/tree, both parents, post-merge checks, Issue #12 outcome, and Epic #2 outcome. |
| `later_repository` | `non-pass` | Later reviewed Tasks must implement and verify runtime, distribution, migration, and release contracts. |

A tracked file cannot contain its own final commit or tree without changing
that object. The committed package therefore binds immutable Git objects and
check-run receipts for T01–T09, records observed links to mutable Issue, PR,
and comment records, and binds the exact T10 base. Mutable GitHub records
require a current read-back at owner judgment. The exact T10 PR head/tree and
CI URLs are an external GitHub binding. Missing, stale, `UNKNOWN`,
`UNCHECKABLE`, deferred, and not-run evidence are non-success states.

## Compatibility-layer replan

The Phase 0 compatibility manifest remains byte-identical at SHA-256
`aa86970e10e615e89e2e313cb16a45e9d71dc0584060db69403d9e8800e9a3be`.
It is a selected `PIN-0001` source and must stay fresh; adding a Phase 1 member
would cross the approved T10 boundary into context-pin ownership. The
[bounded replan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12#issuecomment-5419726866)
therefore keeps `tests/conformance/results/phase-1.json` standalone. It is
deterministically discovered by the README, the fixed-path acceptance checker,
and exactly-once quality registry/workflow execution. No T08 pin or
portable-contract guard was weakened.

## Exact base and governance observation

- Repository: `mochan-tk/agentic-dev-kit-for-codex`
- T10 base commit: `509362e6e12cf0160e58853b0d6c0b6871aa895c`
- T10 base tree: `69c808a7afc59858213ee68dc89cb6a5a20e3e09`
- Base state: accepted T09 merge on `main`
- Ruleset: `solo-fast main protection`, ID `21254123`, active
- Ruleset target: `refs/heads/main`
- Effective rules: deletion protection, non-fast-forward protection, pull
  request enforcement with zero required approvals, and required `quality` /
  `conformance` checks from GitHub Actions App ID `15368`
- Accepted actuator receipt: [Issue #4 receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/4#issuecomment-5388863497)
- Ruleset observation used by this record: `2026-08-26`, read-only; the
  versioned snapshot does not replace a current GitHub read-back at merge time

## Accepted Phase 1 Task evidence

| Task | Issue | Plan or intent | PR / outcome | Reviewed head | Merge / external receipt |
|---|---|---|---|---|---|
| T01 | [#3](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/3) | [intent v3](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/3#issuecomment-5388861150) | External-state sensor; no PR | Baseline observation `32615344ad4f0310948bc59d234a84718741788a` / tree `33259721ec9f378fa67392ef8e1c7645db1321f9`; [quality](https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/32663677641/job/97253594482), [conformance](https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/32663677641/job/97253594322) | [completion receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/3#issuecomment-5388863356) |
| T02 | [#4](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/4) | [Task record](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/4) | Explicit Ruleset actuator; no PR | Pre-actuator baseline `32615344ad4f0310948bc59d234a84718741788a` / tree `33259721ec9f378fa67392ef8e1c7645db1321f9`; [quality](https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/32663677641/job/97253594482), [conformance](https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/32663677641/job/97253594322) | [actuator receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/4#issuecomment-5388863497) |
| T03 | [#5](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/5) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/5#issuecomment-5388869324) | [PR #13](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/13) | `94f92af978839efc48f0ca6afd77514bf291b9f6` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/5#issuecomment-5389844185) |
| T04 | [#6](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/6) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/6#issuecomment-5389938555) | [PR #14](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/14) | `95ad638787047194a1bcf6ca074c1b0a9309f1da` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/6#issuecomment-5392427841) |
| T05 | [#7](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7#issuecomment-5396759095) | [PR #15](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/15) | `562818ee902fb089dcdd8077b4dace0dd94c341c` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7#issuecomment-5398125586) |
| T06 | [#8](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8#issuecomment-5402644687) | [PR #16](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/16) | `0ef66c2d0baf9b7dee30dee8d1e4744ba4b7f75c` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8#issuecomment-5403935064) |
| T07 | [#9](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9#issuecomment-5404518469) | [PR #17](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/17) | `952fb273fd6eb2811dd0ad6ebfea062e682c1155` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9#issuecomment-5409052229) |
| T08 | [#10](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/10) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/10#issuecomment-5409182342) | [PR #18](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/18) | `557c1086351e08f56b3d5c7ad2ab538fc5b6d4f8` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/10#issuecomment-5412449204) |
| T09 | [#11](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/11) | [plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/11#issuecomment-5412882001) | [PR #19](https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/19) | `19879ed8f4608399058ea3ecffea30ab6a5924e3` | [receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/11#issuecomment-5419149972) |

Every T03–T09 row has an exact reviewed tree, merge commit/tree, both parents,
and successful post-merge `quality` and `conformance` URLs in the machine
record. Every Issue is recorded as `CLOSED` with state reason `COMPLETED`.
These are accepted Task outcomes, not scenario-action passes or a release.

## Portable-core disposition

Phase 1 advanced the canonical hierarchy and completion agreement, frozen and
live policy separation, the 136-scenario catalog, pinned and reachable CI,
ledger templates, connector-neutral context contracts, the eight repository
Skills, and this acceptance wall. K01–K08, K15, and K17–K19 have substantial
static or external-state foundations. None of those statements converts an
unrun runtime scenario into a pass.

K09–K16 and K20 remain incomplete. In particular, the repository has no six
custom-agent implementation, authenticated role boundary, task-execution
envelope/v1, loop-event/v1, hooks, `codex exec` adapter, installer/upgrade,
live Task ritual, feedback transport, clean-adopter E2E, or full source-parity
evidence. Epic #2 does not own that out-of-scope remainder and closes only the
portable-core acceptance frontier. No later owner is currently assigned. The
machine record separates a future runtime/distribution/governance lane from a
future repository-release/parity lane; a human-reviewed Phase, Epic, or Task
must claim either lane before implementation.

## Scenario result boundary

The Phase 1 scorecard inventories all 136 canonical scenario IDs exactly once.
All are `not-run` because no existing record executes and binds each scenario's
exact precondition, action, and expected result. Green generic CI, a checker,
a static artifact, or a family aggregate is related evidence only. It is not
scenario-action evidence. See
[`docs/conformance/phase-1-scorecard.md`](../conformance/phase-1-scorecard.md).

## T10 pre-merge gate

Before owner judgment, the exact final T10 head must pass:

```sh
python3 -I .github/scripts/check-phase1-acceptance.py
python3 -I .github/scripts/check-repository-policy.py
python3 -I -m unittest discover -s tests/conformance -p 'test_phase1_acceptance.py'
python3 -I -m unittest discover -s tests/conformance -p 'test_repository_policy.py'
python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'
```

Every command in the versioned quality registry must also pass, `git diff
--check` must be clean, the PR must be mergeable, and the exact-head `quality`
and `conformance` checks must succeed. The PR body and Issue #12 receipt carry
that self-referential exact-head evidence.

## Post-merge gate

After an owner-approved merge, and not before, read back the merge commit,
tree, both parents, post-merge required checks, Issue #12, and Epic #2. Record a
post-merge receipt. Close the Task and Epic only when their exact criteria are
satisfied. Do not tag, release, change `release_blocked`, or activate later
work as part of this acceptance.
