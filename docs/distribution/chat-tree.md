# Optional desktop chat trees

The installed `session-orchestration` Skill can organize explicitly selected
Codex desktop chats into a readable hierarchy using decorated titles and
manual ordering **inside their existing Codex project**. It can maintain that
display when an authorized new chat is added. It is optional, not onboarding
or installer behavior. No new installed helper, scheduler, or app extension
is involved.

**Manual sorting is required for this display convention.** Updated/recency
sorting can move a chat away from its parent as conversations advance. This
is not a prerequisite for using the rest of the kit. The shared sort setting
affects Recents and chats within projects, not just the selected tree; Codex
must explain that scope and obtain explicit consent before changing it.

## Ask for a display, not accidental execution

The normal Epic-to-Task handoff now offers this choice when no applicable
decision exists. The owner can apply the display or decline it; missing app
capability is recorded as unavailable, and an unanswered choice stays pending.
The Epic handoff or Task plan records the decision, its scope, permitted
display operations, separate shared-preference consent and projection owner.
Each following kickoff carries that record's link, so a new Task coordinator,
supervisor or worker reads the same decision rather than losing it in chat
history or asking the same question again. A choice of `apply` does not grant
operations omitted from the owner's decision.

For example, an owner can request a Task's existing coordinator chat plus
display-only supervisor/worker chats from a specified source, with title/order
changes inside the same project. Creating those chats requires that explicit
request; changing shared sorting requires separate consent. The coordinator
responsible for the projection reads back actual executor references first.
When the Task coordinator is already a native chat, a possible display is:

```text
Task #12 coordinator
└─ Task #12 supervisor
⠀⠀⠀└─ PR #34 worker
```

The supervisor and worker may still execute as collaboration subagents in
their assigned contexts. Their real references stay in claim/plan/dispatch
records; private display-chat IDs belong to a separate replaceable mapping.
No second supervisor/writer is created by this display. Declined, unavailable
or pending display work leaves the UI untouched and ordinary authorized Task
execution continues. A display failure is not a Task failure or completion.

In a local Codex desktop project chat, for example:

```text
Use $session-orchestration to organize these existing chats as an optional
chat-tree display in this project. Show the proposed parent/child mapping
first. Preserve project membership and unrelated chats. Do not create chats,
send work instructions, or change the shared sort preference without asking.
```

Identify the project and the particular chats or Issue links. If the Skill
invocation is unavailable, ask Codex to read the installed
`.agents/skills/session-orchestration/SKILL.md` explicitly. Existing adopters
can use the [reviewed update procedure](source-first-installer.md#one-command-explicit-update);
updating the Skill does not activate a tree or change any app settings.

The model first checks the documented tools available in the current app,
their input schemas, project grouping and current manual-order preference.
If grouping must change, that also needs consent. Declining or lacking a
required capability leaves existing UI state untouched: use a plain hierarchy
in the chat instead. Do not create a custom sidebar section as a workaround;
it may display chats away from their original project. Do not unpin unrelated
chats or change their order to make the tree fit.

Native Fork chats and collaboration subagents are different surfaces. Forking
copies conversation history; it does not supply a new assignment, branch,
isolated worktree, authenticated role or execution permission. Creating a new
chat needs an explicit human request. Messages need human authorization for
the intended sending and return directions; a child's request to report back
is not itself that authority. Display-only additions receive no work prompt.
For real work, the existing Issue-first plan, single writer, branch/worktree,
complete kickoff and independent evidence procedures still apply. Do not send
a generic "continue" into inherited history.

## Identity, layout and evidence

The GitHub Issue graph is the durable work hierarchy. This sidebar is only a
replaceable projection, not native nesting or a collapsible tree. Epics remain
siblings. A Project coordination chat can be the display root if requested,
but the kit does not require that parent topology.

Before a mutation, resolve the actual host/project/thread IDs with documented
app tools, not title matching. Keep a local transport mapping of those IDs,
logical parent ID, sibling order, exact prior titles and each operation's
result. Reconcile it with current observations; a lost map is not permission
to guess. Duplicate labels under different Epics are allowed; ambiguous
identity requires clarification. Keep this private app metadata out of public
GitHub receipts and do not scrape app storage to reconstruct it.

Use short role/Issue labels. The root is unprefixed; children use `├─ ` for
non-final siblings and `└─ ` for the final sibling. Indent each further level
with three U+2800 BRAILLE PATTERN BLANK characters (`⠀⠀⠀`). Do not draw vertical
continuation bars: proportional sidebar fonts need not align them. Blank
characters may render or be announced differently; offer plain labels such as
`Task #12 — parent Epic #2` when fonts, screen readers or truncation make this
convention unhelpful. Do not claim pixel-perfect alignment.

Keep preorder: parent, each child's whole subtree, next sibling. Only change
the selected titles and positions. Some app versions provide `fork_thread`,
`set_thread_title`, `list_projects`, `list_threads`,
`move_thread_to_project` with `beforeThreadId`, and shared sorting controls;
use a name only after discovering its current documented schema. A tool's
presence does not authorize its use. Current product guidance is available in
the [official changelog](https://learn.chatgpt.com/docs/changelog); client
capability and result observations, not a version guess, determine availability.

An applied API change, a title/project readback, a manual-order readback and a
visual confirmation are different evidence. In particular, the non-pinned
`list_threads.threads` array is in recency order, so sorting that response or
reading it back does not prove manual sidebar order. Report "placement applied;
visual order unconfirmed" when that is all the tools establish. Screenshots
require an available, authorized capture surface; never work around a denied
app-control or screenshot operation.

## Incremental additions

Recheck the selected parent and anchors by exact IDs. Only fork the verified
source named in the user's request, record the returned child ID, and confirm
its existing project membership before arranging it. A display title is not
the Fork parent or logical-parent identifier.

Insert after the preceding sibling's **entire subtree**, not directly after
that sibling's title. For the first child, the predecessor is the parent.
Prefer insertion before a known next row outside that subtree. If only the
predecessor is known and the app documents an insert-before operation within
the same project:

1. Insert the new chat immediately before the predecessor.
2. Only after the first operation confirms success, move that predecessor
   immediately before the new chat.

This yields predecessor → new chat without moving the predecessor's earlier
rows. The predecessor must be the subtree's last row; moving its root would
separate it from descendants. No known correct anchor means stop and resolve
the order, not infer it from recency. Update affected siblings' terminal
markers and keep all other descendants/unrelated rows in their existing order.

### Example: another worker under Epic2 / Task3

These labels are illustrative; operations use verified IDs. With worker5 as
Task3's last child, create worker6 only on request. Insert it after worker5
(after worker5's whole subtree if it has one). Change worker5 from `└─` to
`├─`; worker6 becomes `└─`. The relevant display is:

```text
Project
└─ Epic2
⠀⠀⠀└─ Task3
⠀⠀⠀⠀⠀⠀├─ worker5
⠀⠀⠀⠀⠀⠀└─ worker6
```

With no next outside row and a leaf worker5, the two moves are worker6 before
worker5, then worker5 before worker6. If either result is ambiguous, stop;
do not fork a replacement or assume the second move succeeded.

### Example: another Task3, this time under Epic1

Suppose Epic1 already has Task1 and Task2, and Epic2 already has Task3 with
workers5/6. A request for a new Epic1 / Task3 does not select the existing
Epic2 / Task3. Resolve Epic1's exact ID, then create the requested new chat
from that verified source. Insert after Task2's complete subtree, before
Epic2's row. Change Task2's marker to `├─`; the new Task3 is `└─`:

```text
Project
├─ Epic1
⠀⠀⠀├─ Task1
⠀⠀⠀⠀⠀⠀├─ worker1
⠀⠀⠀⠀⠀⠀└─ worker2
⠀⠀⠀├─ Task2
⠀⠀⠀⠀⠀⠀├─ worker3
⠀⠀⠀⠀⠀⠀└─ worker4
⠀⠀⠀└─ Task3
└─ Epic2
⠀⠀⠀└─ Task3
⠀⠀⠀⠀⠀⠀├─ worker5
⠀⠀⠀⠀⠀⠀└─ worker6
```

Task2's workers and Epic2's Task3 remain with their original parents. Existing
chat IDs, not identical `Task3` text, distinguish them. The example does not
create another GitHub Task or authorize work in either chat.

## Failure, restoration and limits

After each mutation, retain its result and the exact affected IDs. Read back
titles/project membership and whatever ordering evidence the client actually
provides. On refusal, partial success or an unknown result, stop the affected
UI changes and explain what is confirmed versus unknown. Do not blindly retry,
duplicate a Fork, change tools to evade a refusal, or loop settings changes.
Do not mark a GitHub Task failed/completed because its sidebar projection failed.

On an explicit restoration request, restore the recorded exact prior titles
for the selected IDs. Do not strip prefixes heuristically from every chat.
Reordering back needs verified prior positions; unavailable evidence is a
limit to report. Restoring the shared sorting preference requires current
consent because other chats may now rely on it. No cleanup or archive is implied.

The repository tests exercise actual disposable installation, known-old
single-Skill upgrade, rollback and preservation of adopter customizations.
They check link delivery and inventory integrity, not app rendering, parent/
child message delivery, model compliance or concurrent code ownership.
The two scenarios above are instruction-review examples, not executed UI tests
for the shipped revision. Earlier experiments inform this procedure but are
not current-client or cross-platform guarantees.
