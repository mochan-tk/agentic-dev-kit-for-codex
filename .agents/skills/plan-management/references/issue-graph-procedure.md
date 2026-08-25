# Issue graph procedure

Read this resource only when creating, decomposing, or replanning durable work.

## Authority model

Use this order:

```text
Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> commits, checks, and evidence
```

The Issue graph wins over any projection. A GitHub Projects board may display
the graph, but board absence, lag, or field drift cannot change authority.

## Rolling-wave decomposition

1. Confirm the selected context pin is valid and fresh.
2. Record the repository objective and a broad Epic outline.
3. Select the next Epic from durable dependencies and observed state.
4. Create only enough Task proposals to expose a useful frontier.
5. Give each Task one objective, explicit non-goals, acceptance criteria,
   dependency links, exact ownership, risk, verification, and PR boundary.
6. Reject overlapping ownership or serialize it through an explicit transfer.
7. Read created relationships and bodies back before dispatch.

Do not create detailed future Tasks merely to fill a roadmap. Add them when
their inputs and acceptance conditions are current.

## Intervention and replan

Use the smallest durable change:

- Steer an unchanged objective through a linked Task comment.
- Change scope, criteria, or order through an edited Task proposal and record
  why downstream work remains valid or must be replaced.
- Put newly discovered independent work in a new linked Task.
- Split work when ownership, risk, or verification cannot remain bounded.
- Close obsolete work with relationships and rationale intact.

Walk every downstream dependency after a replan. Mark affected work as keep,
modify, split, add, or close, then re-evaluate the frontier.

## Sensor and actuator boundary

Observe Issues, checks, labels, boards, and Rulesets read-only first. Record the
desired state and a bounded difference. Applying any external change requires
explicit authority. After application, retrieve the effective state and
compare it with the approved intent. A successful command without read-back is
not evidence.

The frozen source `frontier.sh` and `new-task.sh` helpers are not copied in
T09. The former relied on source-specific label assumptions; the latter was a
GitHub actuator. The current ledger contract and the sensor-to-actuator
sequence above replace their procedural purpose without claiming a live Task
ritual.
