<!-- ledger-rendered-record: task/v1 -->
<!-- Submitted Issue body oracle: type:markdown groups are displayed in the form but not submitted; persisted field-label headings follow. -->
Record URL: https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9

### Objective

Add synchronized Epic, Task, and pull-request ledger contracts and static validation.

### Scope

```json
[
  "Version issue forms, the pull-request template, the machine contract, fixtures, and deterministic tests.",
  "Exclude live Task ritual, labels, Rulesets, Skills, agents, hooks, envelopes, events, and runtime adapters."
]
```

### Acceptance criteria

```json
[
  {
    "id": "AC-01",
    "criterion": "The contract, human templates, rendered fixtures, and semantic validator remain synchronized."
  },
  {
    "id": "AC-02",
    "criterion": "Malformed ownership, dependencies, risk, relationships, and evidence fail closed."
  }
]
```

### Parent Epic Issue URL

https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2

### Dependencies

```json
[
  "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
]
```

### References

```json
[
  "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9#issuecomment-5404518469"
]
```

### Owned paths

```json
[
  {
    "pattern": ".github/ISSUE_TEMPLATE/**",
    "mode": "100644"
  },
  {
    "pattern": ".github/PULL_REQUEST_TEMPLATE.md",
    "mode": "100644"
  },
  {
    "pattern": "tests/ledger/**",
    "mode": "100644"
  }
]
```

### Risk tier

B

### Risk rationale

The Task changes the durable interface for future work but is reversible through one reviewed pull request.

### Risk constraints

```json
[
  "Preserve I01-I13, release_blocked=true, and empty conformance results.",
  "Do not modify Rulesets or implement later runtime surfaces."
]
```

### Verification commands

```json
[
  "python3 -I .github/scripts/check-ledger-templates.py",
  "python3 -I -m unittest discover -s tests/conformance -p 'test_ledger_templates.py'"
]
```

### Evidence requirements

```json
[
  "Record the exact pull-request head SHA and the quality and conformance check URLs.",
  "Treat missing, stale, UNKNOWN, and UNCHECKABLE evidence as non-success."
]
```

### Routing

One Task supervisor coordinates one isolated implementation writer and independent read-only review.

### Execution

Use branch codex/phase-1-ledger-templates, one worktree, one pull request, and no unapproved external actuator.

### Completion conditions

```json
[
  "Both required check contexts pass for the exact pull-request head.",
  "Task completion does not constitute Epic, Phase, or repository completion."
]
```

### Relationships

```json
{
  "epic_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2",
  "primary_pr": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/999"
}
```

### Task execution envelope reference (optional and opaque)

_No response_

### Loop event reference (optional and opaque)

_No response_
