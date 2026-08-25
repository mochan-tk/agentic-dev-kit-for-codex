<!-- ledger-rendered-record: epic/v1 -->
<!-- Submitted Issue body oracle: type:markdown groups are displayed in the form but not submitted; persisted field-label headings follow. -->
Record URL: https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2

### Goal

Build the portable Codex-native core while preserving human final authority.

### Scope

```json
[
  "Deliver reviewed Phase 1 contracts through bounded Task pull requests.",
  "Retain exact-head target-side evidence and deterministic governance checks."
]
```

### Non-goals

```json
[
  "Declaring repository-level completion before the reviewed completion pull request.",
  "Creating or reconciling an optional board projection."
]
```

### Task graph

```json
[
  {
    "task_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8",
    "dependencies": "None"
  },
  {
    "task_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9",
    "dependencies": [
      "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
    ]
  }
]
```

### Dependency policy

A Task starts only after every declared blocked-by Task is merged; scope or agreement changes return to owner judgment.

### Acceptance criteria

```json
[
  {
    "id": "AC-01",
    "criterion": "Every bounded Task has one pull request and exact-head acceptance evidence.",
    "evidence_required": "Required GitHub checks and a durable Task receipt bound to the pull-request head."
  },
  {
    "id": "AC-02",
    "criterion": "Repository-level completion remains blocked until every K01-K20 contract has current target-side evidence.",
    "evidence_required": "A human-reviewed completion pull request is the only release transition."
  }
]
```

### Evidence requirements

```json
[
  "The quality and conformance contexts succeed for each exact Task head.",
  "The repository owner reviews and merges each bounded pull request."
]
```

### Planning owner

Repository owner

### Control policy

Rolling-wave Tasks may proceed under solo-fast only inside the approved Epic; agreement, high-risk, actuator, and final acceptance authority remain human gates.
