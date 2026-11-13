# Field record: T10 maintainer-mode cycle

Recorded **2026-11-09**, using the [minimal field format](../field-benchmark-format.md).
Run ID: `field-t10-maintainer-mode-2026`. This is a retrospective local
maintainer-development cycle, not an adopter onboarding run or an EC trial.
The authoritative verification checkpoint is dated **2026-11-08**; exact
checkpoint time is **unrecorded**. This record does not convert that date into
an ISO timestamp or update the earlier checkpoint with later assumptions.

## Identity, objective and sources

Target: this kit's T10 maintainer-mode implementation. Objective: enable explicit
use of canonical payload Skills from the kit source without self-installation,
with a checked installed-to-source path map and maintainer guidance. The bounded
local implementation criterion is delivery of that map/checker, regression
coverage and guide, with product checks and payload preservation evidence.

The source checkpoint identifies implementation commit `f434498` plus then
uncommitted maintainer documentation and contributor-guide additions on
`claude/t10-maintainer-mode`. A complete frozen candidate commit/tree and exact
run-start base are **unrecorded in the primary verification receipt**; the
implementation commit alone does not identify all verified candidate bytes.
Verification instead used a disposable byte-matched copy of the tracked files
plus the new guide, checked by readback. Evidence class: local maintainer
implementation and independent verification, not live adopter operation.
Platform context: VM with a desktop input/X-stack failure; exact OS/client/model
identity is unrecorded in the primary receipt.

Primary source identifiers below refer to workspace documents retained outside
this repository. They are not publicly downloadable artifacts. Hashes identify
the read sources, not authenticated authors or public availability. No private
paths, raw logs or transcripts are reproduced.

| Source | Role | SHA-256 |
|---|---|---|
| S1: `01-maintainer-mode-spec-20261108.md` | Cycle problem, intended approach and constraints | `08c0574f0fee23c031d633aea905752655c8a6ca1f12decbdca3c00b5510ddd4` |
| S2: `04-t10-codex-task-20261108.md` | Delegated objective, acceptance and ownership | `df32c8e34c1a1a3f92cd16e8b0af76bf7d795d75d32e515f85c28e8140a1520d` |
| S3: `05-t10-verification-20261108.md` | Independent verification and unfinished close-out at the checkpoint | `dc6ea69ebd253f2f62779a75241978495be1c5f77d95e1b81e070c1c29286b35` |

Authorization for this retrospective is the owner's T3 work order; S1/S2
describe T10's scope. No new trial, adopter action or GitHub publication is
authorized by this record. Recording method: bounded extraction from S1–S3,
with unknowns retained. Source dates have day precision only.

## T2 timing fields

The [format's fixed T2 source](../field-benchmark-format.md#timing-authority)
owns the definitions. “Unrecorded” maps to T2 `unknown`, with the reason below.
T10 implementation is not evidence that the corresponding adoption event took place.

| T2 milestone | ISO 8601 timestamp or unrecorded/pending | Evidence reference and reason/limits |
|---|---|---|
| adoption_started | unrecorded | S1/S2 describe maintainer development, not an owner-started scaffold adoption attempt. No qualifying timestamp/evidence. |
| scaffold_on_default | unrecorded | S2/S3 concern local implementation. No adoption scaffold landing on the remote default branch is recorded. |
| onboarding_completed | unrecorded | S1–S3 do not record completed P0–P6 or an onboarding evidence PR; not an onboarding run. |
| first_task_closed | unrecorded | No first post-onboarding Task with required close-out is recorded; S3 also leaves local docs commit/final reporting unfinished. |

| T2 duration label | Elapsed value with units or unrecorded/pending | Endpoint evidence references / caveat |
|---|---|---|
| Installation/landing | unrecorded | Both qualifying endpoints absent in S1–S3. |
| Onboarding | unrecorded | Both qualifying endpoints absent in S1–S3. |
| First Task | unrecorded | Both qualifying endpoints absent in S1–S3. |
| Total introduction lead time | unrecorded | Both qualifying endpoints absent in S1–S3; no zero-duration or speed claim. |

## Completion and bounded verification

- First post-onboarding Task completion: **unrecorded / not established**;
  this cycle is not an adoption run and has no qualifying T2 close-out receipt.
- T10 local implementation/verification: **yes at S3's candidate checkpoint**.
  S3 records map/checker/tests and the completed guide/contributor additions.
- T10 local close-out: **no at S3's checkpoint**; the documentation commit and
  Codex final report remained unfinished because desktop input failed. This is
  a checkpoint-specific statement, not an assertion that they remain unfinished today.

S3 reports map validation of 47 entries and 260 references in 44 text files
(238 resolved, 22 reasoned exceptions); a missing-entry negative test refused
with exit 1; product/installer checks passed; 14 map tests passed. Full
conformance ran **648 tests in 1262.7 seconds, OK with seven environment-dependent
skips**, under umask 022. The receipt does not enumerate those seven skips;
they are not silently promoted to coverage. It records no difference in the
47 payload files plus inventory and verifies the inventory hash binding.
The product-check integration was a single approved test-module inventory entry.
The guide's required topics and append-only contributor instructions were verified.

These are S3's historical independent results, not tests rerun by T3. The
1262.7 seconds measures the conformance command only, not cycle lead time,
blockage duration, inference latency or cost.

## Blockages

| Blocked location / impact | Elapsed duration (units) or unrecorded | Cause category and evidence | Resolution / remaining work |
|---|---|---|---|
| Maintainer startup/path resolution | unrecorded | Workflow/tooling: installed-path instructions lacked kit-root counterparts (S1). | S3 verifies the map/checker and guide; actual general maintainer workflow efficacy is not measured. |
| Product-check integration | unrecorded | Specification/decision: scope wording conflicted with required test registration (S3 item 8). | Explicit scoped exception approved for the one-line test-module addition; verified by S3. |
| Documentation commit and final reporting | unrecorded | Environment: VM keyboard/X-stack failure (S3 unfinished section). | Input recovery attempts had not restored operation at the checkpoint; local close-out remained pending there. |

## What this run proves and does not prove

This retrospective demonstrates that the minimal format can represent one
maintainer cycle's bounded implementation/check evidence, friction and missing
measurements without fabricating timings or completion. It identifies the next
measurement need: collect qualifying milestone evidence prospectively in an
authorized applicable run.

It does not establish adoption speed, adopter completion rate, a completed
first post-onboarding Task, live model compliance, automatic Skill discovery,
authenticated roles, native Windows or cross-client parity, full test coverage,
owner acceptance, merge or release. The record is complete as a record of knowns
and unknowns; its timing coverage is explicitly incomplete.
