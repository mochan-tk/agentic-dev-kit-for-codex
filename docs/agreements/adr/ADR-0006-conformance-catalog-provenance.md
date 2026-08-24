# ADR-0006: Durable conformance catalog provenance

- Status: Proposed; accepted when the Task 6 pull request is merged
- Date: 2026-08-24
- Decision owner: repository owner
- Task: https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/6

## Context

Phase 0 recorded the research-pack and scenario-source hashes and the family
counts, but the 136 scenario definitions were not yet durable in the target
repository. The hierarchy agreement in Task 7 needs to cite C-004 without
depending on a local download or a replaceable conversation.

The supplied research archive is identified by SHA-256
`55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7`.
Its
`agentic-dev-kit-codex-research-pack/05_CONFORMANCE_SCENARIOS.md` member is
identified by SHA-256
`21d12a287f536188355e75a9d563d4da329eb934f3ce7836db48b62bfd10faa0`.
No private source-machine path is part of repository provenance.

The research pack was derived from the frozen source baseline
`mochan-tk/agentic-dev-kit-for-copilot` at commit
`fd265ddef150fab86cd54d0e383c2c25fe297ffb` (tree
`88f96493ec167602750c8dfec044629bd494a586`). The Phase conformance manifest
retains the wider baseline audit record; the source manifest links back to it.

## Decision

Commit the verified scenario member byte-for-byte under
`tests/conformance/source/`. Maintain three deliberately separate update
authorities:

1. `catalog.json` contains source definitions only. It retains source order,
   exact scenario bodies, optional parsed precondition and action clauses, and
   the required expected clause. The importer reconstructs the entire source
   byte-for-byte from this representation.
2. `coverage.json` independently contains target dispositions only. Every entry starts with
   `verification_state=not-run`. A-002 and W-008 carry target specializations
   without changing their source bodies. C-004 remains `pending-agreement` and
   points to Task 7. The checker also admits a later `agreement-decision` only
   when it remains bound to Task 7 and names a repository-relative agreement
   ADR; this Task does not choose that decision.
3. `results.json` independently contains result evidence only and binds to the
   immutable catalog definitions, not to mutable coverage. It is empty in this
   Task and keeps `release_blocked=true`; catalog presence is not evidence of a
   pass.

The `import` command owns only the frozen source manifest, `catalog.json`, and
`catalog.schema.json`. It never writes coverage, results, their schemas, or the
human view. The `render` command owns only the human Markdown projection and
depends only on canonical catalog definitions. Consequently a later C-004
disposition update does not require generated-document ownership, and source
re-import cannot erase a reviewed disposition or result.

The A-002 specialization records the documented target discovery boundary:
nested discovery follows the repository root to the session startup working
directory. Editing a `.github` path from a root-started session does not itself
load `.github/AGENTS.md`; a probe must start inside that hierarchy or explicitly
read and apply the nested policy.

The W-008 specialization binds JSONL assertions to a named client, version, and
observation date. It distinguishes the `codex exec --json` event stream from
`--output-schema`, which constrains only the final structured output. Unknown
event types must be preserved or explicitly handled, while malformed,
interrupted, or unrecognized required events remain non-pass states.

One standard-library tool performs deterministic import, render, and check:

```text
python3 .github/scripts/conformance-catalog.py import
python3 .github/scripts/conformance-catalog.py render
python3 .github/scripts/conformance-catalog.py import --check
python3 .github/scripts/conformance-catalog.py render --check
python3 .github/scripts/conformance-catalog.py check
```

The generated Markdown is a definitions-only human-readable projection. The
canonical JSON and frozen source remain authoritative. An independent full-text
comparison is useful advisory evidence, but it is not a mandatory approver or a
substitute for deterministic hash, reconstruction, schema, and current-head CI
checks.

Managed import/render reads and writes canonicalize benign repository-root
ancestor links while preserving the final root component, then open the root
from `/` and every output-parent component descriptor-relatively with
`O_DIRECTORY` and `O_NOFOLLOW`. Target reads also use `O_NONBLOCK` and require a
regular-file `fstat`. Temporary-file creation, comparison, cleanup, and POSIX
atomic `rename` remain relative to the verified parent descriptor. The complete
root-to-parent identity is rechecked immediately before and after rename, and
the parent directory is `fsync`ed after rename. Both check and write modes fail
closed when the required descriptor operations are unavailable. A failed
temporary cleanup is a bounded non-success diagnostic. Diagnostics identify
repository assets without including raw operating-system errors or
source-machine paths. Untrusted JSON keys and values are never reflected;
syntax failures expose only numeric line/column coordinates, and private-path
findings use bounded numeric structural locations. Frozen source identity,
size, encoding, line endings, and normalization are gated before parsing, so
unreviewed headings or scenario text cannot enter diagnostics.

The three import outputs are updated sequentially; the command is not a
multi-file transaction. Each changed file is individually atomic and durable,
but a later failure may leave earlier deterministic outputs updated until the
command is safely rerun. Descriptor closes are attempted on every normal and
exception path. POSIX close failures are not retried because a reused descriptor
could be closed incorrectly; this CLI relies on process lifetime for final
reclamation and does not report raw close errors.

## Consequences

- Scenario loss, reordering, duplicate keys, family gaps, line-ending drift,
  Unicode normalization drift, coverage gaps, synthetic results, and asset-hash
  drift can fail closed.
- Later Tasks can add evidence only by explicitly taking ownership of the
  results surface and the T04 checker policy that currently requires an empty
  store; Task 6 cannot synthesize passes. Import never resets that future state.
- The Phase 0 compatibility `results: []` sentinel remains intact in the Phase
  manifest.
- The meaning of I01-I13, including I02, is unchanged. C-004 is evidence for
  the separate human-reviewed hierarchy decision in Task 7.
- `release_blocked` remains `true`. Completing this catalog does not complete
  Phase 1 or the repository implementation.

ADR number 0005 is reserved for the issue-graph authority decision in Task 7;
using 0006 here keeps the two decisions independent.
