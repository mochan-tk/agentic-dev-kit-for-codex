---
name: context-collection
description: Collect bounded source context with provenance. Use when requirements must be gathered. Do not use to approve agreements or execute implementation.
---

# Context Collection

Collect reviewable source material without turning transport history into
authority. Keep discovery and retrieval read-only; make repository landing a
separate, explicit proposal.

## Inputs

- Identify the Task or Epic record, collection scope, and authorized source
  references.
- Read the connector-neutral `discover`, `retrieve`, `pin`, and `verify`
  contract when external context is involved.
- Confirm the selected context pin and its freshness before collection affects
  decomposition or execution.
- Identify sensitivity, retention, and disclosure constraints before reading
  source material.

## Outputs and durable records

- Produce bounded repository-relative source references, exact revision and
  digest bindings, provenance, and an explicit collection timestamp.
- Maintain a bounded source inventory through the context-pin file list and
  linked durable records. This replaces the frozen source's topic `INDEX.md`
  and free-form provenance header; it does not discard their provenance or
  conflict-tracking purpose.
- Record contradictions, unavailable sources, redactions, and unresolved
  questions without silently resolving them.
- Propose a context-pin update and, when landing is authorized, a reviewed
  repository diff. A retrieved in-memory value is not durable evidence.
- Keep requirement and decision candidates separate from accepted `REQ-####`
  and `DEC-####` records.

## Procedure and chronology

1. Discover only within the approved scope and record which source was
   consulted.
2. Retrieve a bounded value read-only; do not reconcile or write external
   state.
3. Exclude credentials, secrets, private local paths, raw transcripts, raw
   logs, and unnecessary personal data.
4. Record source, retrieval date, method, sensitivity, and whether content is
   original, extracted, or inferred. Preserve safe original wording where
   practical and mark every condensation or inference.
5. Record conflicting sources side by side in the bounded inventory with
   their provenance and open questions.
6. Pin exact repository-relative files, revision, mode, and digest; then
   verify the pin.
7. Propose any repository landing as an explicit actuator, obtain the required
   approval, and read the resulting durable record back.

## Failure states, escalation, and human gates

- Return `UNKNOWN` when required source state is unavailable and
  `UNCHECKABLE` when it cannot be observed reliably. Neither is success.
- Stop on secret exposure, unclear authority, unbounded retrieval, stale pins,
  or a request to fabricate provenance.
- Ask a human to decide disclosure, retention, agreement, and high-risk
  exceptions. Do not infer consent from connector access.

## Verification

- Verify every source reference, revision, digest, mode, and repository path.
- Confirm that each contradiction and excluded item is represented without its
  sensitive payload.
- Confirm the durable landing, if any, by read-back rather than by command
  success alone.

## Capability boundaries

This Skill needs no mandatory external connector or service. It does not
approve requirements or decisions, implement changes, authenticate an agent
or thread, or prove cross-surface runtime support. It provides a collection
procedure, not a transcript store or feedback transport.
