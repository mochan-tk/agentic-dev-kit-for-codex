---
name: context-distillation
description: Distill pinned context into reviewable agreements. Use when evidence must become requirements or decisions. Do not use for raw collection.
---

# Context Distillation

Turn verified context into concise, stable agreement proposals while
preserving disagreement and human authority.

## Inputs

- Start from an exact, selected context pin whose validity and freshness have
  been verified against HEAD, the Git index, and the live worktree.
- Read the bounded sources, existing `REQ-####` and `DEC-####` records, related
  ADRs, glossary terms, and non-goals.
- Identify the Task scope and the human agreement authority.

## Outputs and durable records

- Propose stable requirement IDs with bounded verification instructions.
- Propose append-only decision records with explicit, non-forking
  `supersedes` links.
- Preserve immutable historical records and express later changes in new
  records.
- Record conflicts, glossary changes, non-goals, source references, and the
  reviewed pull request that carries the agreement proposal.
- Leave most knowledge pinned, Task-local, or on-demand. Promote a candidate
  only when it is a cross-Task verifiable requirement, an expensive-to-reverse
  decision needing an ADR or decision record, an actually misread stable
  glossary term, or a tempting non-goal that must remain visible. Deciding not
  to create an agreement is a valid result, not a blocker.
- Classify delivery as always-on, scoped, or on-demand. Keep stable guidance
  needed for most work lean in `AGENTS.md`; link path- or Task-specific context
  only where it applies; keep large procedures in Skills or reviewed docs.

## Procedure and chronology

1. Verify the selected pin before reading it for a decision.
2. Extract candidate requirements, decisions, terms, assumptions, and
   non-goals without discarding conflicting evidence.
3. Apply the four-part promotion bar and retain every non-promoted item in its
   verified pin, Task record, or on-demand source.
4. Compare promoted candidates with existing stable IDs and history.
5. Draft new records and explicit supersession links; never edit accepted
   history in place.
6. Show material conflicts and options to the human agreement authority.
7. Select the narrowest delivery tier. Promote repeatedly missed stable
   guidance and demote stale always-on guidance through a reviewed diff.
8. Open a bounded agreement proposal, obtain human review, merge only through
   the authorized path, and read the merged records back.
9. Without mutating the immutable source, append a bounded
   consumption/distillation receipt or reviewed index entry that links the
   consumed pin, produced proposal or no-agreement result, and disposition.
10. Create a new pin or durable link for downstream use before decomposition
    or execution consumes the result.

## Failure states, escalation, and human gates

- Fail closed on drift, invalid digests, duplicate IDs, ambiguous
  supersession, missing source authority, or `UNKNOWN`/`UNCHECKABLE` evidence.
- Escalate competing interpretations, privacy-sensitive conclusions,
  irreversible decisions, and changes to canonical invariants.
- Only a human-reviewed agreement merge can accept semantic changes.

## Verification

- Check stable IDs, filename agreement, exact source references, acyclic
  earlier-only supersession, and immutable prior bytes.
- Confirm each requirement contains a bounded verification instruction, while
  leaving semantic sufficiency to review.
- Confirm Task-specific knowledge did not leak into always-on instructions and
  every scoped or on-demand record remains discoverable from durable work.
- Confirm the append-only receipt or index entry links the exact consumed pin
  and records whether material was promoted, retained locally, or left
  on-demand; do not rewrite the pinned source to mark it processed.
- Verify the default-branch record after merge; a draft file alone is not an
  accepted agreement.

## Capability boundaries

This Skill does not collect raw material, mutate external sources, implement
the planned change, or authenticate a role. It does not provide an execution
envelope, event schema, runtime adapter, installer, or live Task ritual.
