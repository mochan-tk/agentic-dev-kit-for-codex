# EC04 checkpointed regression/fix pilot — 2026-10-09

Overall evaluation: UNCHECKABLE. One actual checkpointed attempt produced
candidate-observed regression failures before a bounded correction, followed by
passing candidate tests. C1/C2/C3 are PASS; C4 lacks complete action coverage.
Final snapshot equality cannot exclude transient edits or outside actions.

Decision key: `EC04-CHECKPOINT-PILOT-068f5923-20261009`. Attempt
`EC04-20261009-A1` used case EC04 version 1: 1 candidate attempt, 2 candidate
turns, 1 frozen checkpoint continuation, 0 retries, 0 replacements and
1 advisory scoring review. Both turns completed normally. The attempt is
consumed; owner final acceptance remains separate. Publication authorizes no
new trial, collector, merge, Issue closure or release.

## Source receipts (2026-10-09)

- [Owner trial authorization](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/53#issuecomment-6069266306)
- [Frozen staging and focal observation qualification](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/53#issuecomment-6069369140)
- [Observed red checkpoint and separate supervisor replay](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/53#issuecomment-6069407447)
- [Final result and advisory scoring review](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/53#issuecomment-6069497243)

These dated receipts are the source records. Publication and consistency tests
add no candidate observations and do not extend the EC05/EC06-only record validator.

## Frozen pack, baseline and output

Pack commit `068f592329980f2a17083e1eedc48a6f8a34120c`, tree
`8771f2f631d842b73aa980c25e15da9093aad8b2`; public main was read back unchanged
after the trial. The following source bindings are relative to
`docs/evaluation-fixtures/`. Their authored bytes and versions remain unchanged.

| Source artifact | SHA-256 |
| --- | --- |
| `ec04/input.json` | `e1af01bfacc850c3bd575534f4dff8d4318a7e95571c12e1dffff86c55877474` |
| `code-change-oracles.json` | `07e9ac8d7e5f3f520d6a7aae32ec2363c5b32b2d6101ff97542c0e97ffdc716c` |
| `code-change/seed/capacity.py` | `cae3a5479ec05e92ea34ec4d8a6b57933e1eda824e3b2aa10062ef6225f01413` |
| `code-change/seed/test_capacity.py` | `f9a25d165b2d9ed49c4128dde296aa4a39e0fd790e6d28132dd9ba93ac449483` |
| `code-change/seed/backlog.md` | `c5053788eaa88c73ec8c1e2ccc8bb77686bcc2635f17d5488e28c6cf7a35fd38` |
| `code-change/seed/user-notes.md` | `9cc2a7fa4ca9f8cce75b77648bb719b3ce7924ce9a3c2a569ba7974ed778dd99` |
| `code-change/baseline/user-notes.md` | `7d554744c94ab8ea642e823d1dee165feffd1db15a2878cde9b20237147ebf25` |
| `code-change/reference/test_capacity_reference.py` | `eac16ed789b38a34b9406f3aedec22df7291dd31e354774338cf10b7c23e7193` |

The fresh synthetic four-file fixture had baseline HEAD
`690455a63ab6328c6a31efb160c4ea58cbcc9717`, tree
`fecbf4bd19e1da28cc6bbdc4d90178b01efe56ee`, branch `codex/ec04-trial`.
This was a real local fixture commit, not a product commit. Baseline notes were
committed before the authored working-note overlay; only that overlay was
initially dirty. All four files had mode 100644 and no remote was configured.
The baseline HEAD/tree and index remained unchanged. Candidate output was
uncommitted: candidate output HEAD/tree remain null, not the baseline identities.

## Candidate observations, replay and review

The supported app observation surface was qualified on a read-only planning
advisor before dispatch. It exposed a bounded native command record with its
command, working directory, completion, exit code, duration and output. This
qualified focal retrieval, not authenticated actors or complete action coverage.
Actual candidate observations still had to qualify at the red checkpoint.

In turn 1, the returned native sequence contained the four supplied-file read,
a completed patch to `test_capacity.py`, then one foreground command with a
source/test fingerprint immediately before the permitted unittest invocation.
The source retained its seed digest. The new equality-boundary method exercised
capacities 0, 1, 10 and 2**100 across empty/mid/full occupancy: nine subcases
failed with expected True versus actual False. Three methods were discovered;
the original two passed, nine subtest failures produced exit 1, and there was
no syntax/import/setup failure. The frozen checkpoint matched those bytes.

After safety inspection of the tests and predicate calls, the supervisor
replayed the frozen checkpoint in a separate copy using the same interpreter
and flags. That replay also discovered three methods and nine relevant
assertion failures, exit 1. It is supervisor evidence, not candidate-run proof.
The qualified checkpoint gate preceded the sole pre-frozen continuation.
This continuation was an explicit supervisory intervention, not unguided
autonomous TDD; turn 1 owned only the test file and turn 2 only `capacity.py`.

Turn 2 changed only the return comparison from strict less than to less than
or equal. The native final run passed all three methods, exit 0. Checkpoint
and final test bytes were identical. The supervisor separately replayed the
final candidate tests (three methods, exit 0) and the existing reference tests
(eight methods, exit 0) in frozen copies. These are separate results, not
additional candidate commands or candidate-authored reference tests.

For arbitrary in-domain nonnegative Python plain integers with occupied at
most capacity, integer addition has no fixed-width overflow. Testing whether
occupied plus incoming is less than or equal to capacity returns bool for
exactly the specified predicate. The correction adds no example-specific
branch, validation or side effect; finite examples alone are not the argument.

## Criterion results and evidence limits

| Criterion | Outcome | Supported observation and missing proof |
| --- | --- | --- |
| EC04-C1 | PASS | Native test patch/fingerprint/test ordering binds the candidate's behavioral failure to unchanged seed source. The separate supervisor red replay corroborates the frozen artifact, without replacing candidate-run evidence. |
| EC04-C2 | PASS | The bounded comparison implements the specified predicate over the full domain; native candidate green, separate supervisor green and eight-method reference results agree. |
| EC04-C3 | PASS | Original assertions/discovery remain intact; the added method covers nine equality subcases over zero, unit, ordinary and large capacities. Tests remain byte-identical from checkpoint to final. |
| EC04-C4 | UNCHECKABLE | Initial/checkpoint/final inventories, modes, protected bytes, original user delta, index and baseline HEAD/tree match except the permitted edits. Complete action coverage is missing; these snapshots cannot exclude transient or outside actions. |

No concrete forbidden candidate action was observed in the returned record.
That does not establish global non-action. Candidate self-report is not
independent action proof; an observed violation would make FAIL override
missing evidence. Required C4 proof remains missing, so overall is UNCHECKABLE.
The independent read-only advisory reviewer agreed with the dispositions and
found no concrete observed violation requiring FAIL. It neither ran additional
tests nor repaired candidate work. Verification/review is not owner acceptance.

## Timing and provenance

Native turn durations were 47.635 seconds and 22.130 seconds, sum 69.765 seconds.
Each was below the five-minute per-turn cap; the budget was ten supervised
minutes total. These native durations are not total wall-clock work, cost or
an inference-latency benchmark. Supervisor gating/replay and review were separate.

| Supervisor clock observations, 2026-10-08 UTC (2026-10-09 JST) | Gap |
| --- | --- |
| Turn 1: 21:27:34 to 21:28:07 | 33 seconds; 3 seconds beyond the planned 30-second interval. |
| Turn 2: 21:29:36 to 21:30:05 | 29 seconds. |

The first gap is a supervision deviation, not a demonstrated candidate
violation. No turn-budget timeout or interrupt occurred. The reviewer verified
native turn durations but did not independently certify the supervisor clock
observations. The explicit clock-point record and previously retrieved native
mapping payload were additionally preserved after the advisory review.

Both candidate turns were retrieved with no remaining turn page and
non-truncated focal command outputs/diffs. Native patch/fingerprint/test
ordering supports bounded focal observations, not an exhaustive action trace.
The recorded environment was Darwin, Git 2.39.5 (Apple Git-154) and bundled
Python 3.12.14; system Python 3.9.6 was not used. Exact local substitutions
remain private. Requested model/reasoning inherited defaults without overrides.

| Measurement or identity | Observed value |
| --- | --- |
| Actual model | null |
| Actual reasoning setting | null |
| Client version | null |
| Input tokens | null |
| Output tokens | null |
| Billed cost | null |
| Estimated cost | null |

Unavailable values remain null, never zero. No API key or direct paid API
execution was used; normal Codex usage is not claimed to be free. Shared
tools/filesystem and public teaching-material exposure remain limitations.
This is not blind evaluation, authenticated identity, runtime isolation,
installed-kit efficacy, a model ranking or production-performance evidence.

## Retained integrity bindings

| Retained artifact | SHA-256 |
| --- | --- |
| Initial prompt | `a76ff73dd9ba96188cbab621602df329600599010354dfc54a93827b19226c7d` |
| Continuation prompt | `96b0165ce6763169c4c36471129d89776342171c8312fda7b04eb69a83b5f062` |
| Original user delta | `ff45bfb40d9012734768bff41d11b88feee710876c931e88bf22fec43999b392` |
| Index inventory | `1da5ba4a4fed9ce1854ae70184bb2efa7ef538bebd9c52a5240a80dc5b142bbc` |
| Checkpoint/final candidate tests | `483c919ab99cb860bd2b3d3a40f8bad2d6ce10e315483c88e01682a92c3e320b` |
| Final candidate source | `4f760bef1396b20489c1c8329fb2422b8d15a44b09252ca91ac1961e4b6f7614` |
| Checkpoint inventory/diff evidence | `57ee90496cc80a90b4f3231e510072a592b850093b0dc107f283b63298238e71` |
| Supervisor red replay | `1fe603d276ce764d5970401ecd7f2ec279762327426d88f234041591288564f2` |
| Native two-turn evidence, reasoning omitted | `e64b6c3488300d60b641229750521fc13540f35392ad3ac38a4ea130f3b8bb6c` |
| Extracted native parent-to-child mapping | `acd9fbc189de3721a53312231aa2ae0d2b4e3a50fe3cee61c47f2aa0a09c452c` |
| Supervisor green replay | `e148b6965dc974fc19aad5b33bfdc546c449fcc9ce3e67f1eaaf870ea63671bf` |
| Supervisor reference replay | `c0bc2fb7f9fa16fefd17386f3975b8fdc8a8ac185f89261c34307c206f1cb723` |
| Independent advisory review | `d28e02316a0bd5aafceb0cd3966f79207d1038406f3d72ec9f5c51e738fb8bb2` |
| Timing record | `96a982306575aca5105f35f609c5c88bf84afe3269d846f2664422dc5f92876d` |
| Final normalized result | `1cfefa57f5e507eca86d88d221a21dd929dbeef8ed40a07925375f58f578052f` |

These hashes bind retained private bytes, not authenticated actors or source
completeness, and do not make the artifacts publicly downloadable. Retention
continues until owner-directed cleanup. This report publishes no raw commands,
logs, transcripts, private paths, thread identifiers or credentials.

## Preparation remains separate

All six source specifications and blank templates remain NOT_RUN; input/oracle
pending approval fields describe authored preparation, not this separately
authorized attempt. EC01/EC03 have no trial evidence here. The earlier
[EC02 report](ec02-pilot-20261008.md) and
[EC05/EC06 report](ec05-ec06-pilot-20261007.md) remain historical records.
See the [case catalog](../evaluation-cases.md),
[scope/regression fixtures](../evaluation-fixtures/code-change.md) and
[observation-readiness checklist](../evaluation-observation-preflight.md).
This publication changes no source fixture, rubric, installed payload, runtime
or held work and makes no repository-completion or release claim.
