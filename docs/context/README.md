# Durable context records

This directory contains bounded repository-owned context pins, not raw
transcripts or logs. Normative semantics are in
`docs/agreements/portable-context-contract.md`.

`pins/PIN-0001.context-pin.v1.json` is the selected T08 pin. Selection is
derived from the numerically highest immutable `PIN-####` ID, so a later pin is
added without editing history. The current record binds a closed set of
pre-existing regular Git blobs at the exact T08 base commit and tree, so
the record never includes or hashes itself.
Its purpose is a bootstrap governance-input pin. Passing it proves only the
three listed source bindings. It proves neither context completeness nor the
Epic-decomposition sufficiency test, and it intentionally does not bind T08's
new records (which would create a self-referential pin).

Validity and freshness are separate:

- validity recomputes each historical Git-object binding and aggregate digest;
- freshness compares only the selected pin's sources with the exact `HEAD`
  tree, the Git index, and bounded no-follow live worktree bytes and modes; and
- an unselected historical pin may be valid and stale.

The checker evaluates the selected pin for both `decomposition` and
`execution`. Only `pass` succeeds. Drift, `UNKNOWN`, `UNCHECKABLE`, or `fail`
blocks both gates.

Issue #10 predates the current Issue Form. Its durable Task receipt may cite
the exact commit containing this path through the existing References
vocabulary. Such a reference provides linkage only. It does not prove that
this record is valid, selected, or fresh; Git-object verification supplies
that evidence.
