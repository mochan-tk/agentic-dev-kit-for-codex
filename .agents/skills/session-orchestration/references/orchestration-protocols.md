# Orchestration protocols

Read this resource only when dispatching, monitoring, replacing, or recovering
execution contexts.

## Task supervisor protocol

1. Read the full Task and every cited agreement and context pin.
2. Verify the current base, branch, worktree, ownership, dependencies, and
   effective checks.
3. Record a durable plan before governed implementation.
4. Choose a route from observed capabilities and risk; do not infer support
   from a surface name.
5. Assign exactly one writer, or record a bounded trivial-task exemption.
6. Monitor progress with bounded status and GitHub evidence.
7. Verify the exact current head against every acceptance criterion.
8. Record `completed`, `blocked`, `failed`, or `needs-replan` with links and
   limitations. Only verified success can support completion.

One Task may use several contexts over time, but it retains one active
supervisor responsibility. Context references help recovery; they do not
authenticate identity.

## Worker protocol

Read the Task and cited agreements, restate scope and owned paths, verify the
branch and base, and write only within the assigned boundary. Add regressions
for deterministic defects. Report changed assumptions, failed checks, and
deferred proof. Do not mutate Issues, pull requests, Rulesets, or other
external state unless the explicit work order authorizes that actuator.

## Epic and initiative coordination

Select work only from the dependency frontier. Keep future decomposition
coarse until inputs are current. Coordinate across Tasks through durable links
and disjoint ownership. An Epic or phase outcome does not make the repository
complete.

The Issue graph replaces the frozen source's Project session, parent-session,
and app-session tree. Link every execution context from its Task or pull
request when a durable recovery reference is useful, and retain one supervisor
responsibility regardless of how many contexts are attempted. On release or
replacement, record the outcome, stop or verify completion of any mutation,
release the writer responsibility, and only then authorize another context.
Context names and thread links are advisory navigation aids; no app tool,
session-tree, naming convention, or teardown command is a runtime guarantee.
When no supported actuator exists, record manual context release and require
human confirmation before reassignment.

## Recovery and replacement

Reconstruct from the Task, pull request, branch, commits, checks, and committed
agreements. Treat missing local transcript or model memory as normal. Record
the old attempt's outcome, release its writer responsibility, verify that no
mutation is still running, and only then dispatch a replacement.

Count a repeated execution failure only when the command or check and observed
root-cause signature match. A materially different intervention grounded in
new evidence resets the counter; a plain retry, restart, or new context does
not. The writer may make at most three bounded, varied attempts at its tier.
After the third identical failure, hand the durable evidence to the supervisor.
The supervisor may make at most three materially different interventions
through rephrasing, splitting, or rerouting; the third identical failure at
that tier returns the line to human judgment. Do not loop indefinitely.

Crash recovery has the tighter source boundary: if a successor context dies in
the same way as the first, treat two identical context deaths as an
infrastructure signal and return directly to human judgment. Judgment,
security, privacy, agreement, and competing-ownership failures also skip the
retry ladder.

## Steering versus replanning

Steer an approach when objective, acceptance, ownership, and risk remain
unchanged. Replan when any of those meanings changes, when new work is
discovered, or when authority becomes unclear. Record the replan before
dispatching work under the new boundary.
