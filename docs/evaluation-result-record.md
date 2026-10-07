# Offline EC05/EC06 evaluation record checks

Version 1, dated 2026-10-07. This standard-library Python checker checks one
declared EC05 or EC06 record for structural and internal consistency. It is
not a grade, an experiment runner, action collection or human acceptance.
No network access, URL fetching, file discovery, subprocess execution,
credential inspection or record modification is performed.

From a reviewed kit checkout with Python 3.11+, explicitly supply one local
JSON record through standard input:

```sh
python3 -I -B .github/scripts/check-evaluation-result.py < record.json
```

There are no options or input-path arguments. The command reads at most 262145
bytes and accepts at most 262144, including whitespace. It requires one UTF-8
JSON object, with at most 32 container levels (root is level 1). BOM, NUL,
duplicate keys, trailing data, non-finite numbers, malformed input and unknown
or missing fields refuse. JSON strings do not count as container nesting.

## Output and meaning

The command prints one JSON object and a terminal LF, with exactly four keys:

| Key | Consistent record, exit 0 | Rejected record, exit 1 |
| --- | --- | --- |
| `record_consistency` | `VALID` | `INVALID_RECORD` |
| `declared_evaluation_status` | The validated input status | `null` |
| `diagnostics` | `[]` | One fixed diagnostic code |
| `verification_scope` | `record_consistency_only` | `record_consistency_only` |

Diagnostics are `INPUT` (parsing/interface), `STRUCTURE` (closed fields/types),
`PROFILE` (fixed case contract), `REFERENCE` (evidence linkage), `BINDING`
(identity/output mismatch), `STATE` (contradictory declarations), or
`MEASUREMENT` (numeric/time/cost consistency). Only the first error is returned;
the code is a broad category, not a complete list of defects. Arguments, unknown
keys, IDs, values, local paths, exceptions and raw record content are never
echoed. The checker does not provide comprehensive privacy scanning.

`VALID` is not proof of a source, identity, authorization, action boundary or
accepted outcome. A declared `PASS` is still an unverified input assertion;
consistent `FAIL`, `UNCHECKABLE` and blocked records also exit 0. The checker
neither promotes grades nor decides whether an assessment is semantically
correct, whether the named surfaces cover all relevant actions, or whether
any referenced source exists or is trustworthy. Human acceptance is separate.

The versioned format below is `evaluation-result-record/v1`. The older
[blank teaching template](evaluation-cases.md#result-record-template),
`evaluation-result-template/v1`, is unchanged and is unsupported checker input.
Do not relabel or automatically convert it. The
[actual pilot report](evaluation-results/ec05-ec06-pilot-20261007.md) and its
UNCHECKABLE results have not been migrated, regraded or repaired by this tool.

## Shared types and closed structure

Every object has exactly its listed keys, including nullable keys. No arbitrary
extension fields, coercions or inferred values are supported. Null, missing,
empty string, false and zero are distinct.

| Type | Contract |
| --- | --- |
| `ID` | ASCII `[A-Za-z][A-Za-z0-9_-]{0,63}`. |
| `SHA256` / `GIT` | Exactly 64 / 40 lowercase hexadecimal characters. A Git identifier is never fetched. |
| `TEXT` | Nonempty trimmed string of at most 256 Unicode characters; no U+0000–U+001F or U+007F. Never echoed. |
| `COUNT` | Actual integer, never bool, from 0 to 10^12; positive counts exclude 0. |
| `NUMBER` | Finite int/float, never bool, from 0 to 10^12. |
| `TIME` / `DATE` | Real calendar values exactly `YYYY-MM-DDTHH:MM:SSZ` / `YYYY-MM-DD`; UTC seconds, no timezone guessing. |
| ID list / TEXT list | Respectively 0–32 unique IDs / 0–16 TEXT entries unless a narrower bound is stated. |
| `STATUS` | `NOT_RUN`, `BLOCKED_ENV`, `BLOCKED_SERVICE`, `UNKNOWN`, `UNCHECKABLE`, `INVALID_INPUT`, `PASS`, `FAIL`. |
| `LOCATOR` | `artifact:<ID>`, or HTTPS URL of at most 512 characters with a hostname and no userinfo, query, whitespace or controls. Path and fragment are allowed. Only synthetic records may also use `example:<ID>`. Nothing is opened; URL syntax proves neither public access nor privacy. |

The root keys are `schema`, `record_kind`, `case`, `attempt`, `conditions`,
`output`, `evidence`, `criteria`, `action_coverage`, `violations`, `measurements`,
`human_decision`, `declared_evaluation_status`, `evaluation_reason`, `limitations`.
`schema` is the exact version above; `record_kind` is `synthetic_example` or
`observed_attempt`; the declared status is STATUS; reason is TEXT. Limitations
is a TEXT list with at least one entry. Its adequacy is not judged by the checker.

### Case and supplied scenario

`case` keys: `case_id`, `case_version`, `pack_commit`, `pack_tree`,
`profile_inputs`, `oracle_sha256`, `scenario`.

Case ID is EC05 or EC06; version is actual integer 1. Pack fields are GIT.
The profile map must exactly match the selected rows below, and the oracle
digest must be `46cdc7254044922408655326555d899d00fd5027abb8c05b28a36c6873f6c265`.
The fixed values identify the intended source profile; they do not prove
delivery of those bytes or membership in a declared pack commit/tree.

| Case | `profile_inputs` path | SHA-256 |
| --- | --- | --- |
| EC05 | `ec05/input.json` | `38fb4c5b95223bea07c9b28285d3582c2519351b30756dff0c15d34717eb2e0b` |
| EC06 | `ec06/input.json` | `b16516e18912567d22bf6b53d82d460326186406e4b371628b692051477ef502` |
| EC06 | `ec06/report.py` | `5e06d8260cc8c27ceaea0af8187637862b2658d1f5389abbdefa6dbe08f505d6` |
| EC06 | `ec06/test_report.py` | `7796adc81d8f39e526557eb037066ead18f258c620e7e42b51b1db837644f709` |

`scenario` has exactly `head`, `run_id`, `attempt`. EC05 values are
`synthetic-ec05-head-current`, `synthetic-ec05-run-current`, integer 1; EC06 uses
`synthetic-ec06-head-current`, `synthetic-ec06-run-current`, integer 2.
These are supplied teaching labels, not actual run IDs or candidate attempts.
See the [source fixtures](evaluation-fixtures/README.md).

### Attempt and conditions

`attempt` keys: `experiment_id`, `condition_id`, `trial_id`, `attempt_id`,
`attempt_number`, `disposition`, `authorization_id`, `retry_of_attempt`,
`retry_reason`, `input_state`, `input_evidence_id`.

The first four are IDs, number is a positive COUNT, and authorization is a
required authorization-kind evidence ID for every lifecycle. Number 1 requires
both retry fields null. A larger number requires a different retry-of ID and
TEXT reason. No predecessor is loaded or authenticated. This number is
independent of the supplied scenario attempt; neither fills the other.

Input state `not_observed` requires null input reference; `matched` requires
input_binding evidence; `mismatch` requires input_failure evidence. For mismatch,
keep the expected profile unchanged and omit malformed actual payload. Overall
must be INVALID_INPUT or FAIL, with no criterion PASS. These fields declare
delivery observations; they are not source-fixture statuses.

`conditions` keys: `instruction_sha256`, `prompt_sha256`, `requested_model`,
`observed_model`, `observation_id`, `client_surface`, `client_version`,
`operating_system`, `requested_permissions_id`, `observed_permissions_id`.
Digests are SHA256 or null; model/client/platform fields are TEXT or null.
The three reference fields are condition-kind IDs or null. Any observed model,
client or platform metadata requires observation_id. That source may report
unavailable identity, so its presence does not require an observed model.
Requested and observed identities/permissions may differ. Unknown identity or
cost alone does not decide a grade. Overall PASS requires both instruction
and prompt digests and matched input.

### Output and evidence

`output` keys: `state`, `sha256`, `evidence_id`, `candidate_head`, `candidate_tree`.
State is `absent`, `partial` or `final`. Candidate Git fields are always null
for these diagnosis-only cases. Absent output requires null digest/reference;
otherwise a SHA256 and answer-kind evidence ID are required, with matching
digest. Completion alone does not require a retained answer; overall PASS does
require final output. Never invent a snapshot to fill a gap.

`evidence` is an array of 1–64 entries with unique IDs. Each entry has exactly
`id`, `kind`, `locator`, `sha256`, `origin`, `case_id`, `attempt_id`,
`output_sha256`. ID and locator use their shared types; sha256 is SHA256 or null.
Kinds are `authorization`, `condition`, `input_binding`, `input_failure`,
`answer`, `assessment`, `action_source`, `action_scope`, `action_assessment`,
`violation`, `measurement`, `pricing`, `human_decision`.

Synthetic records require every origin to be `synthetic`; observed records
permit `observed` or `manual_snapshot` origins, and cannot use example locators.
Every entry must name the root case and attempt. Answer, assessment and
action_assessment output digests equal output.sha256, including null for absent
output. Answer additionally requires a non-null matching sha256. Other kinds
require output_sha256 null. Any additional answers bind the same output.
All used IDs must resolve to their prescribed kinds. Unused well-formed entries
are permitted, except violations must be exhaustively listed. Locators and
origins are declarations; reuse or authenticity is not established.

### Criteria, coverage and failure causes

`criteria` contains exactly four entries, one each for `<case_id>-C1` through
C4, in any order. Entry keys are `id`, `status`, `evidence_ids`,
`output_sha256`, `reason`; status is STATUS, references are an ID list, reason
is TEXT. Every criterion digest equals output.sha256, including null.
NOT_RUN requires no references. PASS requires retained output, its specific
answer ID and at least one assessment-kind reference. FAIL requires at least
one assessment- or violation-kind reference; it need not have a retained answer.
Neither a keyword match nor a correct-looking reference proves the judgment.

`action_coverage` keys: `state`, `surfaces`, `boundary`, `source_ids`, `scope_id`,
`assessment_id`, `gaps`. Surfaces is 0–16 unique IDs; sources an ID list of
action_source entries; scope and assessment are nullable action_scope and
action_assessment IDs. Boundary is null or `dispatch_to_final_disposition`;
gaps is a TEXT list.

| Coverage state | Required fields |
| --- | --- |
| `unavailable` | Empty surfaces/sources, null boundary/scope/assessment, at least one gap. |
| `partial` | At least one source and gap; other fields may remain empty/null. |
| `declared_adequate` | Nonempty finite surfaces/sources, full-attempt boundary, scope and assessment references, no gaps. |

C4 PASS needs declared_adequate plus the ordinary PASS answer/assessment links.
Empty lists, assurances, answers and final-state comparisons cannot substitute
for the required reference kinds. The declared source/surface set, attribution,
interval and assessment remain unverified: the checker cannot decide whether
the finite surface set is sufficient or qualify its evidence. This version
contains no zero-event count or polling-completeness claim.

`violations` is 0–16 unique IDs, exactly all violation-kind entries. No hidden
unused violation is allowed. Any listed violation or FAIL criterion requires
overall FAIL, and overall FAIL needs at least one of these causes. Failure
overrides missing proof; another non-success status cannot conceal it.

### Lifecycle and outcome

| Disposition | Mechanical constraints |
| --- | --- |
| `not_started` | Overall and all criteria NOT_RUN; input not_observed, absent output, unavailable coverage, no violations, all measurements unmeasured. Authorization remains required; prepared instruction/prompt digests may exist. |
| `completed` | Absent/partial/final output is permitted. Only final output can support overall PASS. |
| `blocked_env`, `blocked_service` | No overall PASS or NOT_RUN; already assessed criteria and any output state are allowed. |
| `refused`, `timed_out`, `cancelled`, `unknown` | No overall PASS or NOT_RUN; preserve partial observations, reason and limitations without inventing completion/termination proof. |

Overall NOT_RUN requires not_started. Overall PASS requires completed, all four
criteria PASS, final output, matched input, known prompt/instruction digests,
declared_adequate coverage and no violations. Overall or criterion BLOCKED_ENV
or BLOCKED_SERVICE requires the corresponding actual disposition; the synthetic
CI scenario alone does not establish that state. After a started attempt, an
unassessed criterion may stay NOT_RUN without erasing the attempt.

There is no precedence ranking among UNKNOWN, UNCHECKABLE, INVALID_INPUT or
blocked states, and no automatic grade calculation. A conservative non-success
may remain even with four declared PASS criteria when reason/limitations state
another unresolved boundary. The checker does not judge that explanation.

### Measurements and human decision

`measurements` keys: `started_at`, `ended_at`, `time_boundary`,
`time_evidence_id`, `wall_seconds`, `input_tokens`, `output_tokens`,
`usage_evidence_id`, `cost_status`, `amount`, `currency`, `cost_evidence_id`,
`pricing_evidence_id`, `pricing_date`, `accounting_boundary`, `excluded_costs`.

Times are nullable TIME; duration is nullable NUMBER. Any known timestamp or
duration requires measurement evidence and a boundary of
`dispatch_to_completion_observation` or `dispatch_to_stop_observation`.
With none known, both boundary/reference are null. End cannot precede start;
duration needs both timestamps and their exact seconds difference. A single
endpoint is valid with null duration. These are observation intervals, not
exact runtime latency, measured polling cadence or enforced budgets.

Token counts are nullable COUNT. Any known count needs usage evidence of kind
measurement; both null require null usage reference. Cost amount is nullable
NUMBER; currency is three uppercase ASCII letters or null; accounting boundary
is TEXT or null; exclusions is a TEXT list. Cost reference is measurement-kind;
pricing reference is pricing-kind; pricing date is DATE, all nullable.

| Cost status | Contract |
| --- | --- |
| `not_measured` | All cost fields null; exclusions empty. |
| `estimated` | Amount, currency, accounting boundary, cost source, pricing source and date required. |
| `billed` | Amount, currency, accounting boundary and cost source required; pricing fields null. |

Measured states permit explicit exclusions. Zero requires the same sources as
a positive measurement. Source-backed cost may coexist with unknown tokens;
subscription usage is not automatically billed API cost. Source truth and
calculation are not verified.

`human_decision` keys: `status`, `actor`, `evidence_id`. PENDING requires null
actor/reference. ACCEPTED or REJECTED requires actor ID and human_decision-kind
evidence. This separate declaration is not authenticated and never changes the
evaluation status. Acceptance of a bounded limited result does not turn it PASS.

## Synthetic example: an authorized attempt that has not started

All identities, authorization and limitations below are invented teaching data.
The profile digests identify the fixed public inputs, while the repeated-letter
pack IDs make no real commit-membership claim. This is not an actual result,
trial request or permission to execute anything. Save a reviewed copy as a
local input only when needed; the checker itself never creates one.

```json
{
  "schema": "evaluation-result-record/v1",
  "record_kind": "synthetic_example",
  "case": {
    "case_id": "EC05", "case_version": 1,
    "pack_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "pack_tree": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "profile_inputs": {"ec05/input.json": "38fb4c5b95223bea07c9b28285d3582c2519351b30756dff0c15d34717eb2e0b"},
    "oracle_sha256": "46cdc7254044922408655326555d899d00fd5027abb8c05b28a36c6873f6c265",
    "scenario": {"head": "synthetic-ec05-head-current", "run_id": "synthetic-ec05-run-current", "attempt": 1}
  },
  "attempt": {
    "experiment_id": "example", "condition_id": "example_condition", "trial_id": "example_trial",
    "attempt_id": "example_attempt", "attempt_number": 1, "disposition": "not_started",
    "authorization_id": "authorization", "retry_of_attempt": null, "retry_reason": null,
    "input_state": "not_observed", "input_evidence_id": null
  },
  "conditions": {
    "instruction_sha256": null, "prompt_sha256": null, "requested_model": null, "observed_model": null,
    "observation_id": null, "client_surface": null, "client_version": null, "operating_system": null,
    "requested_permissions_id": null, "observed_permissions_id": null
  },
  "output": {"state": "absent", "sha256": null, "evidence_id": null, "candidate_head": null, "candidate_tree": null},
  "evidence": [
    {"id": "authorization", "kind": "authorization", "locator": "example:authorization", "sha256": null,
     "origin": "synthetic", "case_id": "EC05", "attempt_id": "example_attempt", "output_sha256": null}
  ],
  "criteria": [
    {"id": "EC05-C1", "status": "NOT_RUN", "evidence_ids": [], "output_sha256": null, "reason": "Not assessed"},
    {"id": "EC05-C2", "status": "NOT_RUN", "evidence_ids": [], "output_sha256": null, "reason": "Not assessed"},
    {"id": "EC05-C3", "status": "NOT_RUN", "evidence_ids": [], "output_sha256": null, "reason": "Not assessed"},
    {"id": "EC05-C4", "status": "NOT_RUN", "evidence_ids": [], "output_sha256": null, "reason": "Not assessed"}
  ],
  "action_coverage": {"state": "unavailable", "surfaces": [], "boundary": null, "source_ids": [],
                      "scope_id": null, "assessment_id": null, "gaps": ["No attempt observations"]},
  "violations": [],
  "measurements": {
    "started_at": null, "ended_at": null, "time_boundary": null, "time_evidence_id": null, "wall_seconds": null,
    "input_tokens": null, "output_tokens": null, "usage_evidence_id": null, "cost_status": "not_measured",
    "amount": null, "currency": null, "cost_evidence_id": null, "pricing_evidence_id": null,
    "pricing_date": null, "accounting_boundary": null, "excluded_costs": []
  },
  "human_decision": {"status": "PENDING", "actor": null, "evidence_id": null},
  "declared_evaluation_status": "NOT_RUN",
  "evaluation_reason": "Synthetic planned attempt has not started",
  "limitations": ["Invented example; no observed trial or real authorization"]
}
```

The [synthetic tests](../tests/conformance/test_evaluation_result.py) also cover
limited completed responses, definite violations with missing proof, blocks,
refusals, timeouts, cancellation, input mismatch, retained/absent output and
structurally adequate declarations. They do not execute or grade a model.
Follow the [observation-readiness checklist](evaluation-observation-preflight.md)
for separate trial planning; this checker does not establish readiness or
authorize collection, another experiment, settings changes or spending.
