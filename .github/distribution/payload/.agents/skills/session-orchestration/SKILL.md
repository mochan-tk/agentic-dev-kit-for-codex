---
name: session-orchestration
description: Coordinate parent/child work sessions, Task startup and handoff, completion/blocked/failed reports, and plan.md versus GitHub records. Also use for a requested optional desktop chat-tree display inside a Codex project; display organization does not dispatch work.

---

# Session Orchestration

Session trees and inter-session messages are powerful but **app-local**: a
cloud agent, a teammate, another machine, or you-next-week cannot see them.
GitHub is the only shared memory. Every rule below exists to keep the durable
record on GitHub while using sessions for speed.

## Mapping (two-tier, per ADR-0003)

| Plan object | Session object | Workspace object |
|---|---|---|
| The Epic set (whole project) | One Project coordination responsibility (optional sibling thread) | — |
| Epic issue | Parent (orchestrator) session | — |
| Task issue | One supervisor session (ritual only, no code edits) | — |
| Pull request | One active worker session | One worktree + branch `codex/task-<n>-<slug>` (or accepted tool-prefixed variant) |

One Task issue per supervisor session — never batch several issues into one
session (reports become unattributable) and never split one issue across
supervisors without replanning first. A PR has exactly one active worker at
a time; use a separate worktree per concurrent worker so parallel sessions
cannot write to the same checkout. For trivial tasks **a Task supervisor**
may implement directly (small-task exemption), declared in its plan comment;
conductors have no such exemption — see Role boundaries.

**Verify execution context, not transport names.** Codex subagents and
threads have surface-specific workspace/lifetime behavior. Do not infer an
isolated worktree from a child name. Before assigning a writer, establish
the actual branch, worktree and exclusive ownership. A same-worktree helper
may perform bounded read-only work; a single assigned writer may work there
when the Task explicitly declares it and no other writer competes.

A created object is not proof of execution. Check the supervisor's durable
claim and the actual worker state. If dispatch is unavailable, record the
exact manual kickoff or use the declared small-task exemption; do not invent
a started worker or silently let a conductor implement.

**Role boundaries.** A session's role is fixed when it is created; it is not
something a session reasons its way out of mid-run. A conductor (Project or
Epic) that finds itself about to edit application files, check out a Task
branch, or commit has met the boundary, whatever the justification: file or
locate the Task issue, dispatch it, and verify — or escalate (§6). "It is
small" is not a route around this; the small-task exemption belongs to Task
supervisors, whose job is that one Task, and it does not extend to a
conductor deciding to do the work itself.

**What enforces this, and what does not.** The three Codex role files contain
guidance only, with no permission overrides. Installed procedures and
comments do not authenticate roles or prove exclusive writes. Verify actual
Git state and ownership; use the current client's documented restrictions
where available. The included ritual script is an explicitly invoked sensor,
not an installed CI wall. Its output is evidence only when actually run
against the current PR; no workflow or ruleset is automatically installed.

**Who posts what:** claim, plan, worker-dispatch, and outcome comments on
the Task issue belong to the **supervisor**; the PR is opened and iterated
by the **worker**. Before a worker starts, the supervisor **creates the
worker session, confirms it exists, and only then** posts a worker-dispatch
comment naming it — session name, actual tool reference, and branch, plus the
Task scope and target PR when one exists. No verified worker, no implementation: a dispatch comment for a
session that was never created records a split that did not happen, which is
the one thing this trail exists to show (ADR-0003). A supervisor that cannot
raise a worker either declares the small-task exemption in its plan comment
and implements directly, or escalates — it does not write the comment
anyway. A replacement
worker is preceded by a comment releasing the old worker and naming its
successor.

### Worker disposition

Before irreversible teardown, branch/worktree reuse or replacement, the
supervisor records the actual worker stop/release state, uncommitted/untracked
work and exact worker HEAD SHA, PR and verification links, and where recovery evidence is
preserved (or an explicit authorized discard decision with reason). Name the
single authority responsible for that disposition. Unknown ownership or an
unconfirmed stop blocks destructive action. A release comment is a declaration,
not process-absence proof or cleanup permission; preserve evidence on failure.
Reusing retained artifacts requires current authorization and reverification
against the new Task/plan; preservation or old approval alone is insufficient.

**Sensor-compatible format:** the worker-dispatch comment's *first line* must
match the regex `^Dispatching worker`, and the release comment's *first
line* must match `^Releasing worker` — no leading blank line, greeting, or
Markdown heading before either — as checked when explicitly invoked by
`.github/scripts/check-task-ritual.sh`. That first line also carries the
worker's reference, in this shape (synthetic example):

```
Dispatching worker: Task #12 worker (session /root/example_supervisor/example_worker), branch codex/task-12-fix
```

The branch is compared against the PR's head ref, so a dispatch written for
one task cannot satisfy another's trail. Copy the actual identifier returned
by the available tool; do not invent a UUID or hash alias. Keep the display
name and optional navigation link separate from this reference. No future PR
number is required. The first line ends after the branch; scope and links go
on following lines.

The sensor accepts whole legacy hex/hyphen IDs of 8–128 characters (starting
and ending in hex, without repeated hyphens), or canonical `/root/` references
with 1–16 slash-separated segments of 1–63 lowercase letters, digits or
underscores, and at most 256 characters overall. Empty segments, placeholders
(`unknown`, `none`, `null`, `tbd`, `todo`, `placeholder`), controls and ambiguous
delimiters fail. These are tool-scoped identifiers, not filesystem paths or
authenticated identities. The sensor validates the recorded syntax and branch;
the supervisor verifies the actual worker before recording it. The same sensor expects every task to
declare its execution mode (ADR-0003): either a dispatch trail (earliest
dispatch after the earliest plan and before the PR's first commit, a release
between successive dispatches, dispatch and release comments unedited) or a
plan comment carrying the small-task exemption phrase
"no worker will be spawned" (matched case-insensitively; AGENTS.md §4) — a
task showing neither fails the wall.

## Child session protocol

### Chat-tree choice at handoff

Before an Epic hands a Task to a supervisor or sibling Task coordinator,
read the applicable durable display decision. If none exists, offer the owner
the optional sidebar projection of this Task's supervisor and worker, and
record the reply on the Epic handoff or Task plan. Use `apply`, `declined`, or
`unavailable` with a reason; an unanswered or ambiguous choice stays `pending`.
An unavailable capability is not an owner decline. Keep ordinary authorized
execution moving unless the owner explicitly made the display a prerequisite.

Use a compact record, not a new ritual or runtime protocol:

```text
Chat-tree: <apply | declined | unavailable | pending>
Decision: <owner decision reference and covered repository/Epic/Task scope>
Display authority: <selected roles/chats, permitted creation/fork sources,
  title/order changes, and messaging directions; none unless authorized>
Shared preferences: <manual order already observed, or separate consent/reference>
Projection owner: <responsible coordinator; capability or blocking reason>
```

Carry the Issue and this record's link through Project -> Epic -> Task and
supervisor -> worker kickoffs. At Task coordinator/supervisor startup, read it
back and reference it in the plan body without changing ritual first lines.
Reuse a current, scoped decision; do not re-ask merely because transport
changed. Missing, revoked, unreadable or out-of-scope authority permits no
display writes; ask only for missing authority, never infer it from `apply`.
An offer alone authorizes neither a new chat nor shared-sort changes.

The named projection owner invokes the optional display procedure below as
the actual supervisor/worker becomes known. Keep executing references in
claim/plan/dispatch records; a separate private mapping connects each to its
native display-chat ID and logical parent. If a Task coordinator chat is
already the Task row, project the supervisor beneath it and the worker beneath
that supervisor; reuse a verified native executor rather than duplicating it.
Do not count a display-only fork as a second supervisor or writer, or send it
an execution prompt. Declined/unavailable/pending decisions cause no UI
mutation. Partial display failure is recorded separately from Task status.

### Startup decision

Quiet/report `tuning-status.sh` has three states; warning-only CI mode is not
a startup probe. Read a decline from the current work order/kickoff and
relevant Issue timeline; check repository, work scope, revocation and later
instructions. Never reconstruct consent from transport history.

| Observed situation | Required action |
|---|---|
| Exit 0, no new onboarding request | Continue authorized Task work; re-tune only for an actual change. |
| Exit 1, no applicable decline | Acknowledge untuned, offer onboarding and wait for explicit yes/no. |
| Exit 1, readable scoped unrevoked owner decline | Cite it; keep CUSTOMIZE and continue only covered, already-authorized work without inventory/tuning. |
| Child, replacement or resume covered by the same decline | Read and carry its link/scope; no repeat onboarding question or new readiness gate. |
| Missing, unreadable, unrelated, revoked or contradictory decline | No reusable opt-out; ask for exit 1, escalate conflicting authority. Marker/fork/unknown version/chat memory is insufficient. |
| Any other exit or failure to execute | Report error and diagnose; do not classify tuned/untuned or continue using a decline. |
| New explicit request to onboard | Enter project-onboarding; an old decline is not permanent. |

### Installed record preparation

The installed mode-0644 helper runs through Bash. It renders only supplied
facts and performs GET-only draft/ledger checks; it never posts a comment:

```bash
bash .github/scripts/check-task-ritual.sh render claim --input claim.json > claim.txt
bash .github/scripts/check-task-ritual.sh preflight claim --repo owner/repo \
  --task 12 --body-file claim.txt --branch codex/task-12-fix
```

Use `render --help` for the input schema; the same route supports `resume`,
`plan` and `dispatch`. Inspect the exact rendered body, run preflight, then
publish it separately only under the Task's authorization. Read the posted
body back before using its URL. Failure stops publication; recheck changed
inputs instead of editing history or inventing a timestamp. Preflight is not
publication, approval, authenticated identity, atomic locking or future CI.
With an existing PR pass `--pr`; unreadable PR evidence must not fall back to
pre-PR mode. The ordinary numeric-PR sensor remains the final ritual check.

This ritual is executed by the **supervisor** session for its Task issue
(steps 1–5); the implementation itself runs in a worker session dispatched
afterwards (see Worker protocol below). Under the declared small-task
exemption, the supervisor performs both parts single-session.

**Start ritual** (do this before touching any file):
1. `gh issue view <n>` — read the full brief: Objective, Context & references,
   Acceptance criteria, Out of scope, File ownership, Verification, Routing.
2. Open every agreement the issue cites (`REQ-###`, ADR links) — many tasks
   cite none, which is normal. If a cited reference is missing, note it and
   proceed on the issue body; stop and apply the Ambiguity rule
   (`AGENTS.md` §6) only when a reference **contradicts** the issue — do
   not fill gaps with guesses.
3. Write `plan.md` in the implementing session's worktree root (the
   worker's, once dispatched; yours only under the declared small-task
   exemption): restate the acceptance criteria, the
   ownership paths, the verification commands, and your step plan. `plan.md`
   is a **session cache** — convenient, disposable, never authoritative, and
   never a substitute for updating the issue. Do not commit it
   (add to `.gitignore` if needed).
4. Comment one line on the issue: `Starting in session <name/link>, branch
   codex/task-<n>-<slug>` (or the accepted tool-prefixed variant, AGENTS.md §4) —
   the branch is the worker's *intended* branch, forward-looking, and is
   named again in the worker-dispatch comment.
   Now the world knows this task is taken.
   **Sensor-compatible format:** the claim comment's *first line* must match
   the regex `^(Starting|Resuming) in session` — no leading blank line,
   greeting, or Markdown heading before it — as checked when explicitly invoked by
   `.github/scripts/check-task-ritual.sh` (this exact wording has failed CI
   twice when paraphrased).
5. Post the plan as a comment on the Task issue **before your first
   commit**: goal restated, intended approach, files you expect to touch,
   verification you will run.
   **Sensor-compatible format:** the plan comment must contain a `## Plan`
   heading or have a body starting with `Plan:` — literal strings checked
   by `.github/scripts/check-task-ritual.sh`; a plan titled anything else
   does not count. When explicitly invoked, the included ritual sensor rejects
   any PR whose linked Task lacks a claim and a plan comment, shows them
   out of chronological order (claim → plan → first commit, committer
   date), shows either comment edited after posting, lacks the `type:task`
   label, or whose PR `Plan:` line does not link a real plan comment on
   that issue in this repository. This comment —
   not `plan.md`, not the PR description — is the plan of record. The
   timeline then reads work order (body) → start → plan → outcome, which is
   what makes deviations diagnosable from one page.

Surfaces that write a plan into the PR description automatically (e.g. the
cloud agent) produce a convenient copy: link the plan comment from the PR
description and treat the issue timeline as authoritative.

**Risk gate** (`risk:high` tasks only): stop after posting the plan comment
and wait for an explicit approval comment from the requester/orchestrator
before the first commit. The default is pass-through — a posted plan on an
unlabeled task is actionable immediately (lazy consensus); the gate exists
only for tasks whose blast radius warrants a pre-flight human eye
(`plan-management`, Intervening).
One scoped approval covers routine implementation, red/green tests and repairs;
only material authority, ownership, criteria or production-impact changes
return for a new decision. Existing merge and irreversible-action gates remain.

**Work loop** (the implementing session — the worker, or the supervisor
under a declared exemption): stay inside the ownership paths; commit early
and often;
update `plan.md` freely. A material change is escalated to the supervisor;
the worker does not post or approve a supervisory plan. The supervisor records
a fresh plan comment (never edits history), obtains any required owner approval,
then releases the affected work. The worker reads and acknowledges the current
Task and plan before continuing. A cache edit is not authorization.

**Verify** (before any completion claim): run every command in the issue's
Verification section; then confirm external state with commands, e.g.
`gh pr view <pr> --json state,statusCheckRollup`, `gh pr checks <pr>`,
`git status --short` (must be clean). Projects is required by default: apply
[required per-Task Project close-out](../plan-management/SKILL.md#required-per-task-project-close-out).
Record the exact-item `verify` result for Kind `Task` and both authorized dates
(or the complete exact-item UI comparison), with schedule decision, observation
time and current PR head. Alternatively cite a scoped durable exception for
environmental inability to create/use Projects or explicit owner Project decline.
Pending creation/date decisions and date-only decline/defer are not Project
exceptions; authorized implementation may continue but required close-out stays
pending. `gh project item-list --format json`, Status alone and write success
cannot prove Kind/date equality. Missing, mismatched or uncheckable fields are
non-success, never permission to repair fields or approve dates. Do not report
`Outcome: completed` until this disposition and all other criteria are met.
The Issue graph remains authoritative; verifier equality is not acceptance.

**Record before report** — the supervisor posts this comment on the Task issue, then (and
only then) message the parent:

```markdown
## Outcome: <completed | blocked | failed | needs-replan>
**PR:** #<pr-number>
**Evidence:**
| Criterion | Evidence (command / link) | Result |
|---|---|---|
| AC1 ... | `pio test -e native` -> 12 passed | pass |
| Project close-out | <exact-item Kind/date comparison + schedule record, or scoped Project exception link> | <match / exception / pending / non-success> |
**Deviations:** <none, or what differs from the brief and why>
**Follow-ups:** <suggested downstream issue changes, or none>
**Scaffold friction:** <none | retro:candidate issue link>
```

The **Scaffold friction** line is optional: fill it when you filed or +1'd a
`retro:candidate` issue during the task (retro skill, §Candidate ledger).

Any `deferred` row in the Evidence table prohibits `Outcome: completed`: the
outcome stays `blocked` or `needs-replan` until the requester revises the
work order (body edit + change comment) to remove or re-home that criterion.
The executor may propose the revision, never make it.

**Post-merge acceptance:** when criteria include steps that happen only
after the merge (a tag, a release, a deploy check), the PR links the issue
with `Refs #<n>`, never `Closes` (AGENTS.md §4). Order: merge → post-merge
steps → outcome comment → close the issue manually. Auto-close would end
the record before the work it certifies exists.

The message to the parent is a pointer, not a payload: outcome word + issue
and PR links. If the parent session is gone, the record still stands — that
is the point. Reports climb one hop at a time: the **worker** reports to its
**supervisor** (PR link, CI status, verification output, deviations); the
supervisor independently verifies against ground truth (`gh pr view/checks`,
diff vs. ownership), posts the outcome comment, and only then reports to the
**Epic orchestrator**. A worker never posts the ritual comments and never
reports past its supervisor.

## Worker protocol (ADR-0003)

A worker session implements exactly one PR from its kickoff. It runs the
plan of record in **autopilot with no plan gate of its own** — plan
approval, where required at all (`risk:high`), happened at the supervisor
tier; lazy consensus otherwise. PR review is the output checkpoint. If the
plan does not survive contact with reality (ownership
too narrow, contradiction with the referenced agreements), the worker stops
and escalates to its supervisor per AGENTS.md §6 — it never replans alone
and never posts comments on the Task issue. When done: PR open, CI green,
report to the supervisor, stop. Rework may return to the same worker or a
fresh replacement — the plan and history live on the issue, so replacements
start cheap.

**Worker kickoff template** — a worker sees only its kickoff and the
ledger, so the kickoff must be complete (kickoff completeness is
load-bearing, ADR-0003):

```markdown
You are the WORKER session for Task issue #<n> in <owner>/<repo>.
- Startup context: <current owner onboarding-decline decision link and covered scope, or none; read it, never infer from chat>.
- Chat-tree context: <durable display-decision link; read its scope and projection owner, keep actual execution separate>.
- Issue: <issue URL> — read it in full (`gh issue view <n> --comments`).
- Plan of record (execute it; no plan gate of your own): <plan comment URL>
- File ownership (verbatim from the issue — touch EXACTLY these):
  <paths, copied verbatim>
- Verification (run ALL before marking the PR ready):
  <commands, copied verbatim>
- Branch: codex/task-<n>-<slug> (or managed-prefix equivalent). One PR,
  `Closes #<n>` (`Refs #<n>` instead for stacked non-final layers and
  post-merge acceptance, per AGENTS.md §4 and ADR-0003 Decision 3).
- Environment notes: <OS/shell quirks, tool constraints, anything not in the repo docs>
- Do NOT post comments on the issue; report to your supervisor session and stop.
```

## Project session protocol

One Project coordination responsibility per project, durably handed off by onboarding
(`project-onboarding` P6) once the phase Epics exist, and kept for the life
of the plan. It conducts conductors: it never decomposes, dispatches Tasks,
or edits code itself. Its first move waits for the onboarding evidence PR to
merge — a phase started against a half-tuned repository verifies nothing.

1. **Start an Epic's session when that phase's turn comes** — when its
   `blocked-by` Epics are closed, or the frontier has run dry. Hand it the
   Epic number and the applicable durable chat-tree decision link; the Epic
   is the brief. Name it `Epic #<n>`
   (session naming: §Codex topology and lifecycle).
2. **Epic sessions are siblings, not descendants.** An Epic session that
   sees the next phase becoming actionable reports that to the Project
   session rather than starting a peer itself: sessions spawning their
   successors nest one level deeper per phase, and after a few phases the
   tree is unreadable. Epics are siblings in the issue graph; their sessions
   mirror that.
3. **Watch across Epics, not within one.** Phase-spanning trouble is the
   Project session's business: an Epic whose blockers never clear, a
   dependency that turns out to be backwards, repeated escalations of the
   same shape. Within an Epic, its own session decides.
4. **Replan across phases** (`plan-management` skill) when reality diverges
   from the outline — reordering phases, splitting one, dropping another.
   Record the rationale on the affected Epic, not in session memory.
5. **Ending.** Project sessions die like any other: before one ends, the
   state of play must be legible from GitHub alone — each Epic's status
   visible from its issue, its comments, and the board. Whoever restarts a
   Project session reads the graph, not the transcript.

## Parent session protocol

1. Dispatch only from the frontier (`plan-management` skill), after checking
   that concurrently dispatched tasks have disjoint File-ownership paths.
   Use the available Codex surface or the explicit manual handoff described
   by task-routing. Observe CI records: queued/action-required is not failure
   or success, and owner approval may be needed for actual repository policy.
   Never bypass that policy or fabricate a worker result.



2. **Issue-first, dedicated-session — no exceptions for infra/ops.** Ad-hoc
   requests (e.g. a human asking "can you deploy this?"), and cloud/deploy/
   infra work in general (provisioning, secrets, deploy unblocking), get a
   Task issue created *before* any work begins, and run in a dedicated child
   session like any other task — never inline in the parent. No issue, no
   work: evidence recorded after the fact on a closed issue does not count.
3. When dispatching a **supervisor** (including through a sibling Task
   coordinator), pass the issue number and durable chat-tree decision link
   from the handoff procedure above — the issue is the brief. Name the
   supervisor session `Task #<n> supervisor`
   (workers: `PR #<n> worker`; naming rule in §Codex topology and lifecycle). If
   you feel the need to add substantial instructions in the dispatch message,
   the brief is incomplete: fix the issue first. Supervisor→worker kickoffs
   are the exception: they use the complete Worker kickoff template above,
   because kickoff completeness is load-bearing (ADR-0003) and the worker
   never re-derives scope from the issue alone.
4. Steer with short course-correction messages when session logs show drift;
   prefer steering over restarting.
5. On receiving a report: verify the record exists on the issue and spot-check
   the evidence with your own `gh` calls before updating labels/Project state
   or dispatching dependents — `gh` calls are the whole of it, because the
   artifact is CI's to verify and not yours to rebuild (`verification`
   §The layers). An unrecorded report is returned to the child
   with one instruction: record first. **Silence is checked the same way.** A
   child that wakes its parent having written nothing on the issue has not
   been quietly productive — it has not started, or it has died. Read the
   issue before concluding anything about a child that never spoke.
6. Route `needs-replan` outcomes to the planner procedure
   (`plan-management` §Replanning) and post the rationale on the Epic.
7. When the Epic's phase is done — its Tasks closed, their PRs merged, the
   Epic's own state line current — tell the Project session so the next
   phase gets a session, then stop. Do not start that session yourself and
   do not carry on as it: the Project session keeps Epic sessions siblings
   (see Project session protocol), and a session that continues into the
   next phase makes the tree a single thread again. Stay open until the
   Epic closes — rework and late questions come back here. If
   no Project session is running, say so in the Epic's closing comment and
   name the next Epic, so a human or a fresh Project session can pick it up.

## Codex topology and lifecycle

The source Project-parent nesting was a Copilot-app platform workaround,
not a parity requirement. Keep one Project coordination responsibility across
the Epic set, with Epic threads as siblings. A Project strategy/navigation
thread is optional and may itself be a sibling. The Issue graph remains
durable authority regardless of replaceable thread transport.

Prefer an explicit Project controller that creates/manages sibling Epic
threads only after a capability probe proves a documented thread-management
surface is available. Do not assume an agent in one thread can control peers.
Preserve Epic -> Task -> Worker delegation and complete kickoffs; when native
control is absent, supply a durable manual handoff rather than invented API
names. Name navigation surfaces Project, Epic #<n>, Task #<n> supervisor and
PR #<n> worker where the available UI permits.

Inspect the actual result and durable record before advancing the graph.
Stop/release the old worker before replacement. Keep workers available for
review rework when possible, then clean up only owned resources through
documented controls. No creator-scoped archive behavior is assumed.
Project coordination lasts while the plan needs it; an Epic coordinator lasts
until the Epic closes. A dead thread can be replaced from GitHub records.

### Optional desktop chat-tree display

Invoke this procedure for a direct explicit request or a current scoped
`apply` decision carried by the handoff above. Use the available documented
app controls to project the logical relationships as titles and manual order
inside the existing Codex project. Native Fork chats are user-visible chats,
not collaboration subagents. Neither Fork ancestry nor title indentation
authenticates a role, isolates a worktree or changes the GitHub Issue graph.
Project-parent display is optional; keep Epics siblings. This is a display
convention, not native nesting, folding, or an automatic background service.

1. **Observe before writing.** Discover the current app tools and their schemas;
   read the exact host, project and thread IDs, project display grouping and
   sort preference. Require manual chat order for this convention. Recents
   and project chats share that preference: explain its wider effect and
   obtain explicit human consent before changing it. Obtain consent for any
   necessary grouping change too. If declined or the required capability is
   unavailable, leave the UI untouched and offer a plain hierarchy in chat.
   Do not move the tree into a custom section, out of its project, or change
   unrelated pins/order. No filesystem/app-state scraping substitutes for a
   missing documented control.
2. **Resolve identity and authority.** Keep a replaceable local mapping of
   exact host/project/thread IDs, logical parent ID, sibling order and prior
   titles; reconcile it with current observations before each update. Titles
   are labels, never IDs: two different Epics can each have a `Task3`. Resolve
   ambiguous parentage with the user. Creating/forking a chat needs an explicit
   human request; fork only the verified source ID. Record the returned child
   ID and confirm project membership. Inherited history is not a new work
   assignment. A display-only fork receives no execution prompt. Messaging
   needs human authorization for each intended direction (including reports
   back); a child request alone does not authorize a reply. Actual work still
   needs the Task, ownership, branch/worktree and complete kickoff above.
3. **Prepare the bounded display change.** Use concise role/Issue labels.
   The root has no prefix; its children use `├─ ` or final-sibling `└─ `.
   For each deeper level, prepend three U+2800 BRAILLE PATTERN BLANK characters
   (`⠀⠀⠀`); omit vertical continuation bars. Keep the hierarchy in preorder
   (parent, then each child's whole subtree). If font rendering or accessibility
   makes blank indentation unsuitable, offer plain labels with explicit parent
   references instead; do not promise pixel alignment.
4. **Insert locally.** Place a new child after its preceding sibling's entire
   subtree (or directly after the parent for the first child), before the next
   outside anchor when known. Use same-project insertion controls and exact
   IDs; preserve existing descendants and unrelated chats. With only a known
   predecessor and a documented insert-before control, insert the new chat
   before that predecessor, confirm success, then move the predecessor before
   the new chat. Use the subtree's last row, not its root, as predecessor.
   Recompute affected sibling `├─`/`└─` markers. Do not infer an unknown anchor
   from a recency list or move an existing subtree as though it were one row.
5. **Verify and stop honestly.** Record each mutation result and read back
   exact titles/project membership. Distinguish that from a manual-order
   readback and from an authorized visual check: `list_threads.threads` is
   recency-ordered, not proof of project display order. If no order/visual
   observation is available, report that limit. On partial failure, refusal
   or an ambiguous result, stop affected mutations, retain known IDs/results
   and report the partial state. Do not duplicate Forks, blindly retry, switch
   tools to bypass refusal, or loop on settings. UI failure does not change
   the durable Task status. Restore exact prior titles only when requested;
   restoring a shared preference requires its own current consent.

Examples and user-facing invocation are in the optional
[desktop chat-tree guide](https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/docs/distribution/chat-tree.md).
The essential procedure above is installed; the public guide is not another
payload file. Completed illustrative experiments or static checks do not prove
the current client's rendering, message delivery or model compliance.

## Resume protocol (crash-only)

### Reproducible worktree preflight

Before a planned push or claim, use the installed observation block and manual
comparison below. No kit checkout, download or uninstalled helper is required.
Set `TASK_WORKTREE` to the actual worktree root, `PLANNED_BRANCH` to its intended
branch, `ACTUAL_WORKER` to the verified worker reference, `PREFLIGHT_ACTION` to
`push` or `claim`, and `CLAIM_READBACK` to a current local JSON readback of
the durable declarations (at most 1 MiB and 128 claims):
`{"claims":[{"writer":"actual-reference","branch":"planned-branch","worktree":"/actual/worktree","state":"active"}]}`.
Use physical absolute worktree paths and `released` only for an observed
release. Do not manufacture this readback from the branch you hope to use.
Keep the target and claims unchanged while observing. Output contains local
paths: inspect locally and publish only a bounded conclusion and ledger links.

<!-- BEGIN installed-worktree-observations -->
```bash
(
  set -eu
  : "${TASK_WORKTREE:?set the actual worktree root}" "${PLANNED_BRANCH:?set the planned branch}"
  : "${ACTUAL_WORKER:?set the verified worker}" "${CLAIM_READBACK:?supply current claims}" "${PREFLIGHT_ACTION:?select push or claim}"
  case "$PREFLIGHT_ACTION" in
    push|claim) ;;
    archive) printf '%s\n' 'UNKNOWN: archive needs current evidence and explicit human cleanup authority.'; exit 3 ;;
    *) exit 2 ;;
  esac
  for context in GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS; do
    [ -z "${!context+x}" ] || { printf '%s\n' 'UNKNOWN: inherited Git context can redirect observation; use a clean shell.'; exit 3; }
  done
  export GIT_OPTIONAL_LOCKS=0
  target=$(cd "$TASK_WORKTREE" && pwd -P) || exit $?
  root=$(git -C "$target" rev-parse --show-toplevel) || exit $?
  [ "$target" = "$root" ] || { printf '%s\n' 'REFUSED: target is not the worktree root.'; exit 1; }
  git -C "$target" check-ref-format "refs/heads/$PLANNED_BRANCH" || exit $?
  head_branch=$(git -C "$target" symbolic-ref --quiet --short HEAD) || {
    code=$?; [ "$code" = 1 ] || exit "$code"; head_branch='';
  }
  if [ "$PREFLIGHT_ACTION" = push ] && [ "$head_branch" != "$PLANNED_BRANCH" ]; then
    printf '%s\n' 'REFUSED: detached HEAD or current branch differs from planned push.'; exit 1
  fi
  [ -f "$CLAIM_READBACK" ] && [ ! -L "$CLAIM_READBACK" ] && [ "$(wc -c < "$CLAIM_READBACK")" -le 1048576 ] || exit 3
  jq -es --arg target "$target" --arg branch "$PLANNED_BRANCH" --arg writer "$ACTUAL_WORKER" '
    length==1 and (.[0]|type=="object" and keys==["claims"] and (.claims|type)=="array" and (.claims|length)<=128
      and all(.claims[];type=="object" and (keys|sort)==["branch","state","worktree","writer"]
        and ([.branch,.worktree,.writer]|all(.[];type=="string" and length>0 and (test("[[:cntrl:]]")|not)))
        and (.worktree|startswith("/") and (test("//|/\\.(/|$)|/\\.\\.(/|$)")|not))
        and (.state=="active" or .state=="released"))
      and ([.claims[]|select(.state=="active" and (.worktree==$target or .branch==$branch))] as $active
        | ($active|length)==1 and $active[0].writer==$writer and $active[0].worktree==$target and $active[0].branch==$branch))' \
    "$CLAIM_READBACK" >/dev/null || { printf '%s\n' 'REFUSED: invalid, missing or conflicting declared claims.'; exit 1; }
  printf '%s\n' "Target: $target" "Current branch: ${head_branch:-DETACHED}" "Planned branch: $PLANNED_BRANCH"
  git -C "$target" rev-parse --verify HEAD || exit $?
  git -C "$target" -c core.quotePath=true status --short --untracked-files=all || exit $?
  git -C "$target" -c core.quotePath=true worktree list --porcelain || exit $?
  jq . "$CLAIM_READBACK" || exit $?
  printf '%s\n' 'Observations collected; manual comparison required. This is not a verdict or action authority.'
)
```
<!-- END installed-worktree-observations -->

**The supervisor must complete the comparison before proceeding.** Exit 0
means observations were collected, not that ownership or occupancy passed:

- Compare the physical root, HEAD, current/planned branch and tracked/untracked
  state with the Task plan and intended action. Detached pushes stop.
- Inspect the complete worktree inventory: the target appears exactly once;
  every record is complete; no other worktree occupies `refs/heads/<planned
  branch>`. Decode Git-quoted paths when comparing. A missing, truncated or
  ambiguous record is `UNKNOWN`, not an empty/available branch. Any conflicting
  occupant stops; never force, unlock or prune to take another worker's branch.
- Compare the claim readback with the **current Issue/PR ledger and actual
  worker state**: exactly one active writer owns the target/branch, and any
  predecessor has a verified release/handoff. JSON validity does not prove
  freshness, authority or termination. Missing access, stale claims, uncertain
  worker state or any failed command stops the action.
- Record the bounded comparison and links before the separately authorized
  action. Preserve commits and tracked/untracked changes when resolving a
  mismatch; create or attach a branch only after ownership is resolved.

Archive/delete remains non-success until a human inspects current evidence,
handoff and recovery material and explicitly authorizes the exact cleanup.
A nonempty URL or local file is not that evidence. These observations supply
no exclusive lock, process-stop or client-native archive guarantee.

For optional automated inventory parsing, use the
[pinned worktree companion procedure](https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/docs/distribution/companion-checks.md#worktree-check-a-planned-action-without-doing-it).
It specifies the fixed revision, digest, inputs and inspect-before-execute
steps; it is outside the installed payload and never fetched implicitly.
Its success still requires the supervisor's current durable ownership check.

Sessions die without warning — network, quota, machine sleep, closed laptop.
The scaffold has **no dedicated resume machinery** on purpose: the ordinary
start ritual *is* the resume path (crash-only design — recovery and startup
are the same code path).

- **Successor session**: run the start ritual (AGENTS.md §9) exactly as for a
  fresh task, then derive the current position from the ledger + ground
  truth: the issue timeline (start / plan / latest comments), the branch
  (`git log`, `git status`), and the PR (`gh pr view/checks`). What is not on
  GitHub did not happen — do not reconstruct intent from memory or chat.
- **Role-specific resume**: a successor supervisor records the new resume
  claim and any revised plan. A successor worker reads the current Task/plan,
  confirms its actual branch/worktree/ownership and acknowledges to the
  supervisor; it never duplicates the supervisor claim or posts a new plan.
  Apply the startup decision table, including a covered decline. Verify the
  previous worker's disposition before reuse; dispatch the actually created
  successor only after the release and any required revised plan.
- **Claim before touching**: post a *resume comment* on the Task issue
  (`Resuming in session <name/link>, branch codex/task-<n>-<slug>`) before any
  commit (supervisor only, not the worker). The claim records responsibility;
  it is not an exclusion lock. If
  the timeline shows another live claim, stop and escalate instead.
- **Orphan detection is the parent's duty**: a task with a start comment, no
  Outcome comment, and a dead session is an orphan. The parent (or any
  orchestrator sweeping the frontier) either dispatches a successor supervisor,
  which claims as above, or comments the task back to the frontier. A replacement
  worker follows its supervisor's recorded plan/dispatch and never claims anew.
- **Repeat failure**: if the resumed attempt dies the same way the first one
  did, the supervisor applies `needs:human` and stops; a worker reports to the
  supervisor, not past it. Two identical session deaths signal
  infrastructure, not approach — crash-resume is exempt from the three-strike
  ladder (Escalation below).

## Escalation

Execution failures climb a three-tier ladder. The boundary at every tier is
the **same failure three times**: then the work hands up one tier.

An attempt counts toward the *same failure* only when both the command or
check **and** the observed root-cause signature match. The counter resets
only after a materially different intervention grounded in new evidence —
changed code, configuration, inputs, ownership, or approach. A plain retry,
restart, or fresh session never resets it.

1. **Agent** — self-correction inside the session; vary the approach between
   attempts. Three identical failures spend this tier's budget.
2. **Parent session** — rephrase the work order, split it, or re-route it to
   a different surface or model. The same three-failure budget applies.
3. **Human** — label `needs:human` and stop the affected line of work.

Judgment and trust failures skip the ladder and go straight to a human: an
agreement in `.github/docs/agreements/` turns out wrong; credentials/security issues
appear; or two sessions claim the same ownership paths. These are not
execution failures — humans own those.
