# Evidence status

Updated on **2026-11-09** for T3 evaluation triage and a retrospective T10 field
record. Historical pilot results remain unchanged; the baseline CI row
retains its **2026-10-05** observation at commit
`9fdbf91d9980b5c632e0f3483c97098358ce519f`. This is a dated map of available
evidence, not a live dashboard or a product-completion claim. GitHub records
and exact-head checks remain authoritative; consult a later Task/PR for later
candidate results. Baseline CI does not validate this documentation change.

## Current evaluation design

The [2026 triage](evaluation-triage-2026.md) inventories all 24 v1 criteria and
reduces EC01–EC06 to observable artifact, response and focal-check questions.
The [v2 cases](evaluation-cases.md#version-2-scoring) give every started attempt
an overall PASS or FAIL; missing required evidence is FAIL with an evidence-gap
reason. Whole-surface non-action, unavailable write attribution and full
predecessor handoff are explicit non-claims. Unknown runtime identity/cost were
measurement limitations, not the historical pilots' C1–C4 blockers.

No v2 trial has run. The six specifications and blank templates remain NOT_RUN;
the v1 fixture/rubric/validator contracts and all three pilot reports are
unchanged. Their overall UNCHECKABLE results are not retroactively converted
to PASS or FAIL. EC01/EC03 still have no trial evidence.

The [field format](field-benchmark-format.md) references T2's four milestones
and three adjacent durations plus total. The
[T10 retrospective](evaluation-results/field-t10-maintainer-mode-2026.md) records
local implementation/verification and friction at the 2026-11-08 checkpoint,
including unfinished local close-out there and unrecorded adoption timings.
It demonstrates format use, not measured adoption speed or first-Task success.
The [11 Issue dispositions](evaluation-issue-disposition-2026.md) are proposals
only; no Issue was changed and no new run authorized.

## What the evidence supports

| Evidence class | Recorded result | What it does not establish |
| --- | --- | --- |
| Baseline product CI | [`quality` and `conformance` succeeded](https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/37250779904), attempt 1, for the exact base above on 2026-10-05. | A pass for a later commit, live model behavior, adopter deployment or owner acceptance. |
| Deterministic conformance | [The test method](../CONTRIBUTING.md#tests-and-provenance) uses real Bash/Git/jq, disposable local targets and synthetic external transport. CI requires a real PowerShell host; a local skip is not that evidence. | Native Windows end-to-end operation, live GitHub governance, or a live Codex workflow. A historical test count is not a current suite count. |
| Historical bounded E01 | [The dated public acceptance](parity-status.md#current-acceptance-as-of-2026-09-23) records acceptance on 2026-09-23 of one disposable macOS desktop exercise with explicitly loaded installed instructions/Skills, a test-first worker, a successor after normal completion, an ordinary PR, real application and metadata Actions, and owner-reviewed merge. | Automatic Skill/role discovery, authenticated identities, forced-stop/crash recovery, required-check merge enforcement, retarget freshness, Windows, or existing-addon migration. Onboarding, Projects and Rulesets were explicitly declined. |
| Later onboarding and planning changes | [Provenance](provenance.md#current-onboarding-answer-wait-correction) separates procedure/delivery tests and synthetic date-proposal scenarios from live observations. | Historical E01 acceptance does not remeasure later kit revisions. No live interview, Project-date execution or universal model-compliance result follows from those tests. |
| T10 retrospective field record, recorded 2026-11-09 | [Primary-source summary](evaluation-results/field-t10-maintainer-mode-2026.md): implementation/verification completed at the dated checkpoint; local docs commit/final report remained pending there. All adoption timings are explicitly unrecorded. | Adoption lead time, first post-onboarding Task close-out, adopter completion rate, live Skill efficacy or present-day close-out status. |
| EC05/EC06 pilot, 2026-10-07 | [Two actual diagnosis-only responses](evaluation-results/ec05-ec06-pilot-20261007.md) to synthetic inputs: C1-C3 PASS, C4 and both overall results UNCHECKABLE. A separate self-check passed 23 record-consistency assertions. | Complete action coverage, full polling-cadence conformance, runtime identity/cost, live CI behavior, kit efficacy, pass rate or owner acceptance. |
| EC02 pilot, 2026-10-08 | [One actual limited interaction](evaluation-results/ec02-pilot-20261008.md): C1 PASS; C2/C3/C4 and overall UNCHECKABLE. An unchanged checkpoint preceded an owner-authorized scripted reply; expected final date values were observed. | Attributable write chronology, whole-surface non-action, a new human UI selection, question-bubble behavior, runtime identity/cost, installed-kit benefit or owner acceptance. |
| EC04 pilot, 2026-10-09 | [One checkpointed regression/fix attempt](evaluation-results/ec04-checkpoint-pilot-20261009.md): C1/C2/C3 PASS; C4 and overall UNCHECKABLE. Native candidate red/green observations are distinct from supervisor replays and advisory review. | Complete action coverage, global non-action, unguided autonomous TDD, runtime identity/cost, inference speed, installed-kit efficacy or owner acceptance. A 33-second polling gap exceeded the planned interval by 3 seconds. |

The old E01 **Pending** row in the [parity checkpoint](parity-status.md#historical-implementation-checkpoint)
is retained historical state, not a denial of the later bounded acceptance.
This documentation update records **no new E01 run**. Private application
records, local paths, raw logs and transcripts are not published here; the
sanitized public acceptance receipt is linked from the dated parity section.

## Remaining boundaries

- The desktop app is required by the product's operating contract. That
  requirement is not proof of every desktop version, platform or workflow.
- Fresh-install and update tests check delivered files and preservation, not
  whether a model follows the instructions. Installed README is a `seed`;
  existing README files are not overwritten by an update. Existing adopters
  should review the [current public entry instructions](../README.md#quick-start)
  and reconcile their own guide explicitly.
- Receivers and schedules remain inactive. No live adopter update, integration,
  new model/API experiment or ongoing monitor is started by this page.
- T12 remains paused, `release_blocked=true` remains in force, and the original
  136 scenarios remain `not-run` with `results: []`. Bounded Task acceptance
  and CI success do not declare repository-level completion or release.

See [known limitations](known-limitations.md) for operational exclusions,
[product scope](product-scope.md) for shipped surfaces, and
[CONTRIBUTING](../CONTRIBUTING.md) for candidate verification commands.

## Try the reference material

- [Worked example](worked-example.md): a tiny Python formatter, one supplied
  baseline test and five reference characterization tests, with illustrative
  Epic/Task/plan/PR records. Running the reference tests is not a live Codex
  workflow or an accepted adopter exercise.
- [Evaluation cases](evaluation-cases.md): six reduced v2 **NOT_RUN** case
  specifications with binary scoring, a minimal Markdown attempt record, the
  preserved v1 blank teaching record and a comparison protocol. This is not a benchmark
  runner or evidence that a model passed these cases. Historical E01 and
  product conformance results do not populate them. The unchanged source status
  is distinct from the separately recorded pilot attempts.
- [EC05/EC06 pilot report](evaluation-results/ec05-ec06-pilot-20261007.md): dated
  authorization, results, self-check, bindings and limitations for both actual
  attempts.
- [EC02 pilot report](evaluation-results/ec02-pilot-20261008.md): one limited
  two-turn interaction, C1 PASS and C2/C3/C4 plus overall UNCHECKABLE. Correct
  final bytes do not prove write attribution.
- [EC04 checkpointed pilot report](evaluation-results/ec04-checkpoint-pilot-20261009.md):
  one two-turn regression/fix attempt, C1/C2/C3 PASS with C4 and overall
  UNCHECKABLE. Focal native observations do not establish complete action
  coverage. EC01/EC03 have no trial evidence here.
- [Observation-readiness checklist](evaluation-observation-preflight.md):
  non-executable preparation for separately authorized trials, with source
  coverage, timing, attribution, publication and retention gaps made explicit.
- [Offline CI-diagnosis fixtures](evaluation-fixtures/README.md): EC05/EC06
  have authored synthetic input packets and separate public reference rubrics.
  Offline checks validate fixture consistency, including an intentionally red
  seed test; they do not run a model or populate case results. These public
  answers are teaching/development material, not secret held-out evaluations.
- [Offline interaction fixtures](evaluation-fixtures/interaction.md): EC02/EC03
  have authored choice/context packets, a staged hypothetical reply and public
  reference rubrics. These are preparation artifacts, not observed waiting,
  predecessor completion or a full handoff. All six source specifications and
  blank templates remain NOT_RUN; future trials require separate authorization.
- [Offline scope/regression fixtures](evaluation-fixtures/code-change.md):
  EC01/EC04 have a shared defective seed, separate case packets, authored user
  notes and public reviewer references. Offline checks demonstrate fixture
  consistency and an initial-working-tree comparison method, not observed
  agent preservation or a candidate-authored regression/fix. All six source
  specifications and blank templates remain NOT_RUN; future trials require
  separate authorization.
