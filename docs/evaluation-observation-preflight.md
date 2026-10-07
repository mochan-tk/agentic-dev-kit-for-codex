# Observation readiness before an evaluation trial

Version 1, dated 2026-10-07. This non-executable checklist does not authorize a trial
or implement a collector, runner or record validator. It supports a separate,
bounded human decision about a proposed trial and the evidence it can produce.
No hooks, telemetry, services, permissions or trust settings are enabled here.

The [EC05/EC06 pilot](evaluation-results/ec05-ec06-pilot-20261007.md) produced
useful answer observations, while C4 and both overall outcomes remained
UNCHECKABLE. Its records did not establish action attribution and coverage for
the required finite execution surfaces throughout each attempt, and did not
preserve separate monitoring-poll timestamps. A future trial must define its
own required evidence before dispatch; this page cannot repair the old gaps.

## Review before dispatch

Keep a dated evidence reference, responsible observer and explicit gap for each
applicable item. An unchecked box or an unsupported assertion is not success.

- [ ] **Authorization and budget.** Link the actual human decision, exact
  target, permitted operations, owned paths, data publication scope, surface,
  trial count and spending/time limits. Define retry, refusal, invalid-input,
  timeout and stop rules, including whether an attempt is consumed. Preserve
  every disposition; a proposed plan, default, elapsed wait or this checklist
  is not consent. A known-limited pilot needs explicit authorization for its
  limits and must retain them in its results.
- [ ] **Exact bindings and exposure.** Freeze the pack commit/tree, case
  version, inputs/source/oracle/rubric bytes and digests, full prompt and
  instruction bindings before answers are seen. Record the actual starting
  state and independent output snapshot method for a no-commit trial. Record
  prior oracle/answer exposure and reviewer involvement; fresh context does
  not make public teaching material blind. Do not populate the source template.
- [ ] **Requested and observed conditions.** Record requested identity,
  model/reasoning and permissions separately from observed identity and
  effective capabilities, with their observation sources. Record client/version,
  platform and tools to the extent actually known. Role names, requested
  settings and inherited defaults cannot fill missing runtime observations.
  Unknown identity, tokens and billed cost remain null, never assumed or zero.
- [ ] **Full attempt boundary and attribution.** Declare the finite action
  surfaces needed by each criterion, and cover the attempt boundary from input
  delivery/dispatch through completion or stop and final disposition. Account
  for candidate, child and harness actions, including delegates, background
  processes and any continuation. Distinguish preparer/reviewer checks from
  candidate actions. Cover transient actions and relevant side effects, not
  only the final response or final files. If a relevant surface cannot be
  observed or attributed, name the affected criterion and preserve the gap.
- [ ] **Observer provenance and integrity.** Identify who or what produced
  each observation, its client/version, clock and attempt association. Record
  observer provenance, source integrity and attribution limits: original vs
  manually copied/normalized material, sequence boundaries, truncation,
  dropped events, restarts and retention failures. Bind retained artifacts to
  digests; a digest detects byte changes but does not authenticate origin or
  establish complete coverage. Record whether the candidate can modify the
  source or observer, and how that affects the supported claim.
- [ ] **Coverage and explicit gaps.** List each source's declared coverage,
  excluded tools/surfaces, filters and failure modes. Separate that declaration
  from independently established completeness for the required attempt and
  surfaces. Explain the evidence for each claimed capability, including any
  appropriate separately authorized control check; a plausible design or
  successful setup is insufficient. Hook presence, status messages, answers
  and a clean final workspace cannot alone establish the complete action
  boundary. Do not infer coverage for hosted, child or specialized paths from
  a local-tool record.
- [ ] **Start/end and measured polling timestamps.** Record actual start/end
  observations, their clock/timezone and the exact boundary they measure.
  Retain measured polling timestamps, observed states and gaps if a cadence
  is required. A requested wait duration is not a measured poll interval.
  Distinguish supervisory wall-time bounds from exact inference latency and
  platform-enforced budgets. Never backfill absent timestamps from a plan.
- [ ] **Failure, timeout and stop handling.** Predeclare how source errors,
  lost observations, attribution ambiguity, clock gaps, failure or timeout
  affect the attempt and criteria. Preserve status at the last observation,
  the stop request and any observed termination separately. A request to stop
  is not proof of stopped execution. Record retries/replacements and child
  dispositions with their own boundaries; do not silently replace failed or
  uncheckable attempts with successful ones.
- [ ] **Zero-event claims.** Distinguish source-backed zero-event evidence
  from no events observed. An empty list can support a scoped zero count only
  when the named source was operating throughout the required interval,
  covered every relevant action surface, attributed actions to the attempt,
  and has adequate sequence/integrity evidence for that claim. Otherwise
  report missing or limited observations. An answer saying no action occurred
  or identical before/after files cannot establish that absence alone.
- [ ] **Safe publication and retention.** Predeclare private retention scope,
  access, duration and disposal responsibility, and the allowlisted public
  fields/references. Publish bounded summaries and digests without secrets,
  private paths or raw transcripts/logs. Record redaction/normalization and
  availability limits. A narrow path/token scan is not comprehensive privacy
  verification. Obtain separate authority before changing collection or
  publication scope; do not bypass permissions, trust or service restrictions.

## Hook coverage is a source limit, not an action guarantee

Official [Codex hook-coverage documentation](https://learn.chatgpt.com/docs/hooks#tool-coverage),
checked 2026-10-07, says hooks cover many local function paths, including nested
calls, but exclude hosted tools such as WebSearch. Some specialized paths may
opt out. A `write_stdin` continuation does not create a new `PreToolUse` event.
This is a dated source description, not a claim that hooks were enabled or
qualified in the pilot, and not proof of coverage on a particular future
client/version or attempt.

Any future design using hooks must still account for the required surfaces,
attribution, attempt boundaries, source health and the documented gaps. Do not
weaken a no-unauthorized-action criterion to match only the events available
from a chosen source. A known-limited observation can support a bounded claim;
it cannot establish an unobserved action boundary.

## Disposition and future tooling boundary

Record which observations are ready and which remain unavailable before seeking
trial authorization. Missing, UNKNOWN or UNCHECKABLE evidence stays non-success.
If complete criterion coverage is required and cannot be established, do not
claim readiness for that criterion. A separately authorized known-limited pilot
may still produce useful response observations, with the corresponding action
criteria and overall outcome remaining non-success unless adequate evidence
actually becomes available. An observed violation is FAIL even when other
evidence is missing. Human acceptance remains a separate attributable decision.

The separate [offline EC05/EC06 record checker](evaluation-result-record.md)
now checks a closed record format's fields, declared bindings, references,
timestamps and consistency. A record validator is not collection or proof of
action coverage, source truthfulness or non-action. Its VALID result and the
documentation tests do not grade candidate semantics or collect actions.
The earlier pilot is unchanged. Any collector, new experiment or extension of
the checker needs its own bounded work order and authorization.

See the [blank result record](evaluation-cases.md#result-record-template),
[comparison protocol](evaluation-cases.md#fair-comparison-protocol-for-a-future-experiment)
and [evidence map](evidence-status.md).
