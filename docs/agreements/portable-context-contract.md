# Portable context contract

This agreement defines the repository-owned interface between context intake
and later planning or execution. It is connector-neutral: no external service,
account, credential, Skill, agent, hook, runtime adapter, or Task ritual is
required by this contract.

The machine-readable peer is
`docs/agreements/portable-context-contract.v1.json`. The two forms are one
reviewed contract; disagreement is a validation failure.

## Stable records

Requirements use `REQ-####`, decisions use `DEC-####`, and context pins use
`PIN-####`. An ID is permanent, its filename must contain that exact ID, and it
must never be reused or renumbered. A requirement or decision that already
exists at the active Task base is immutable byte-for-byte.

Semantic change is append-only. A replacement is a new record whose explicit
`supersedes` list names only earlier records of the same kind. Supersession must
be acyclic and non-forking: one historical record cannot be superseded by two
competing records. Historical records remain present and unchanged.

Records introduced in a pull request use status `accepted-on-owner-merge`.
That status is prospective on the branch and becomes authoritative only when
the repository owner merges the reviewed pull request to the default branch.

The frozen Context Contract has four conditions: requirements are individually
verifiable and have stable IDs; decisions are immutable and append-only; the
material is reachable from every declared execution surface; and a Task can
reference it through a stable exact pin. Behavioral sufficiency is a separate
Epic-decomposition test: attempt to decompose the next Epic and write every
Task acceptance criterion without returning to humans for missing fundamentals.
T08 defines that test but has not run or proven it.
The static checker enforces stable IDs, closed record shape, nonempty bounded
verification instructions, and immutable history. It does not prove that an
arbitrary requirement is semantically verifiable. Human review and the
explicitly not-run sufficiency test establish that stronger property.

## Exact context pins

A `context-pin/v1` record binds a closed, sorted set of normalized
repository-relative paths to:

- one full Git commit ID and its exact tree ID;
- the Git mode and blob ID of every regular-file source;
- one SHA-256 digest per source; and
- one canonical aggregate SHA-256 digest over the repository, revision, tree,
  and sorted source bindings.

`context-pin-v1-lines` is exact UTF-8 text with LF separators and a required
trailing LF. Its lines are, in order: literal `context-pin/v1`;
`repository<TAB>{repository}`; `revision<TAB>{revision}`;
`tree<TAB>{tree}`; then one
`{path}<TAB>{mode}<TAB>{blob}<TAB>{sha256}` line per source sorted by path.
No escaping, extra whitespace, blank line, BOM, or locale-sensitive ordering
is permitted.

Pins resolve only through Git objects. A worktree file is never a fallback for
a missing commit, tree, or blob. Absolute paths, `..`, non-NFC names, symlinks,
submodules, non-regular files, ambiguous Unicode/case collisions, and a pin
that includes itself are invalid.

Pin records are append-only. The record with the numerically highest `PIN-####`
ID is the selected pin, so adding a reviewed higher ID changes selection
without editing history. Pin validity and pin freshness are different facts.
Validity means the record matches its exact historical Git objects and digests. A valid historical pin
may be stale. Freshness is evaluated only for the one selected pin by comparing
its source bindings with the current `HEAD` tree, Git index, and bounded
no-follow live worktree. Drift blocks both decomposition and execution until a
reviewed new pin is added and selected.

Freshness is three-way: selected sources must match the exact `HEAD` tree, the
Git index, and bounded no-follow reads of live worktree bytes and modes.
Staged-only drift, unstaged drift, deletion, symlinks, and non-regular live
inputs all block both gates.

Only `pass` is success. `drift`, `UNKNOWN`, `UNCHECKABLE`, and `fail` are
non-success states. Missing Git objects are `UNKNOWN`; an environment that
cannot perform the required check is `UNCHECKABLE`. Neither state may be
guessed from cached prose or treated as evidence.

## Connector-neutral operations

The interface exposes exactly four operations:

1. `discover` identifies applicable sources without changing them.
2. `retrieve` obtains bounded source material with provenance.
3. `pin` writes a proposed exact binding for review.
4. `verify` checks validity and, for the selected pin, freshness.

Definitions and validation live under `.github/connectors/`, but T08 ships no
concrete or activated connector. Implementations may later use repository
files, APIs, or other reviewed transports. Core consumers depend only on these
four operations and their evidence states, never on connector-specific fields.
`retrieve` is read-only source observation with bounded in-memory output. Any
repository write that lands retrieved material is a separate explicit proposal actuator
and requires its own reviewed ownership.

## Task references and execution boundary

The current Task ledger has a generic `References` field and no dedicated
context-pin field. A Task reference may link durably to the commit containing a
pin and name its repository-relative record path. That is linkage only: the
reference does not prove pin validity or freshness. This checker supplies the
offline proof for the selected repository pin.

T08 defines and exercises both drift gates, and CI evaluates the selected pin.
It does not implement the live Task ritual that would prove every future
runtime invoked `verify` immediately before decomposition or execution.

## Durable-data exclusions

Machine records use closed field allowlists. They must not acquire fields for
secrets, credential values, access tokens, private keys, environment dumps,
raw transcripts, raw logs, or private absolute local paths. Connector
implementations must reduce source material to bounded reviewed records rather
than persisting those categories.
The checker rejects conservative high-confidence credential, private-key,
authorization-header, raw-payload, and private-local-path signatures in record
values. It cannot prove arbitrary secret absence; human review remains required.

## Implementation and completion boundary

T08 implements only the static contract portion of K06 and advances the portable portions of K01, K02,
K05, K18, and K19. K16 is boundary-only: feedback transport is not implemented.
K10 and K11 remain unimplemented. The scenario families C, D, I, P, S, and X
receive deterministic contract coverage, not completed runtime conformance
results.
The canonical scenario states remain `not-run`; T08 adds static contract
fixtures only. Connector metadata and concrete connector-definition validation
are deferred with the concrete connectors.

`results` remains empty and `release_blocked` remains `true`. Completion of
this Task does not complete Phase 1 or the repository.
