# Phase 0 orientation record

- Record version: `phase-0-orientation/v1`
- Observed at: `2026-08-24T01:53:31+09:00`
- Target repository: `mochan-tk/agentic-dev-kit-for-codex`
- Source repository: `mochan-tk/agentic-dev-kit-for-copilot`
- Frozen source commit: `fd265ddef150fab86cd54d0e383c2c25fe297ffb`
- Phase 0 status: implementation blocked until this record is committed and pushed

This is the required pre-implementation orientation record. It records the
empty target, verifies the frozen behavioral source, fixes the invariant
vocabulary, classifies current Codex assumptions, and defines the only file
ownership allowed for the first implementation pull request.

## 1. Target state and bootstrap exception

Before any target mutation, the local `main` branch was unborn, the index and
working tree had zero tracked files, `origin` exposed no refs, and the GitHub
repository API reported an empty public repository whose default branch name
was `main`.

GitHub cannot open a pull request without a base commit. The one-time bootstrap
exception therefore created and pushed this empty-tree commit directly to
`main`:

| Field | Value |
|---|---|
| Seed commit | `88179ec6a28393d7bf4cea96684e3af16b512484` |
| Seed tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| Subject | `chore: seed empty target for governed bootstrap` |
| Files owned or changed | none |

The seed preserves Git's canonical empty tree. It does not install policy,
templates, code, workflows, or configuration. This exception exists only to
make Phase 0 PR 1 possible and must not be reused after `AGENTS.md` lands.

## 2. Source and research-pack verification

### Frozen source

| Check | Result |
|---|---|
| Source `main` | resolves to `fd265ddef150fab86cd54d0e383c2c25fe297ffb` |
| Commit tree | `88f96493ec167602750c8dfec044629bd494a586` |
| Parents | `f5a0661d0a2e463ee311e9f0e0b3659961f33dd8`, `0a6537d54b9e250d361c109c25629f07eb27c93d` |
| PR head tree | `0a6537d54b9e250d361c109c25629f07eb27c93d` has the same tree |
| Tracked files | 135 |
| Checkout | detached and clean before and after the audit |
| Object integrity | `git fsck --full --strict` passed |
| Signature | GitHub API: `verified=true`, `reason=valid`; local GPG reproduction unverified because `gpg` is unavailable |
| Guard inventory | exactly 23 `test-*.sh` files |
| Local source suite | all 23 test files passed; 0 failed |
| Frozen PR CI | five jobs passed on the final PR-head run, including the [23-suite self-check](https://github.com/mochan-tk/agentic-dev-kit-for-copilot/actions/runs/32174711807/job/95833817713) |

The source checkout was read only. A passing source suite establishes the
frozen implementation baseline; it does not prove guarantees that the source
itself disclaims.

### Research pack

| Check | Result |
|---|---|
| ZIP SHA-256 | `55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7` |
| Supplied checksum manifest | all seven Markdown files passed |
| Conformance catalog SHA-256 | `21d12a287f536188355e75a9d563d4da329eb934f3ce7836db48b62bfd10faa0` |
| Conformance scenarios | 136 total: A 6, C 5, D 4, E 10, G 13, H 10, I 15, O 7, P 12, R 10, S 8, T 16, W 12, X 8 |

The pack is audit input, not authority. The differences discovered below take
precedence for the target until later evidence changes them.

## 3. Invariant checksum

The canonical checksum input is UTF-8, sorted by invariant ID, with each line
encoded as `ID<TAB>statement<LF>`. The digest is:

```text
sha256:ca7732a7f4d928f10fdb826b1a55e3c9ecf93008c5d2b210a35139956da8393c
```

Canonical input:

```text
I01	GitHub is durable truth; thread and session history are replaceable transport.
I02	GitHub Project -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.
I03	One Task has one active supervisor responsibility.
I04	One PR has one active writer, branch, and worktree.
I05	A durable record exists before a narrative report.
I06	Acceptance evidence is verified before completion.
I07	Overlapping ownership is blocked or serialized.
I08	Unknown or uncheckable governance and evidence states fail closed.
I09	Humans retain agreement, high-risk exception, and final acceptance authority.
I10	Sensors are read-only; actuators are explicit.
I11	Installer upgrades preserve tuned surfaces and adopter instance truth.
I12	Recurring failure strengthens the harness, preferably through a deterministic mechanism.
I13	Hooks, role prompts, comments, and thread IDs are not claimed as authenticated runtime guarantees.
```

Phase 0 will make the `AGENTS.md` invariant table authoritative and will have a
guard recompute this digest from that table. The checksum is a drift detector,
not an authentication mechanism.

## 4. Source-to-target contract parity

| ID | Product-independent contract and source evidence | Codex target | Disposition | Phase 0 state |
|---|---|---|---|---|
| K01 | Durable GitHub truth and canonical hierarchy: source `AGENTS.md`, `README.md` | Root constitution now; ledger templates later | ADAPT | foundation |
| K02 | Record, verify, and escalate: source `AGENTS.md` sections 2, 3, and 6 | Constitution now; Skills later | ADAPT | policy only |
| K03 | One supervisor responsibility, one PR writer, and declared trivial-task exemption: source `AGENTS.md` section 4 and ADR-0003 | Task/attempt topology without a 1:1 Task-thread claim | ADAPT | policy only |
| K04 | Disjoint ownership and serialization: source `AGENTS.md` section 5 and `ownership-overlap.sh` | Constitution plus later deterministic guard | COPY/ADAPT | policy only |
| K05 | Human-on-the-Loop authority and risk gates: source `README.md` | Human agreement, exception, acceptance, and merge authority | COPY | foundation |
| K06 | Context Contract: stable verifiable IDs, immutable append-only decisions, cross-surface reachability, stable pins | Connector-neutral context interface | COPY/ADAPT | planned |
| K07 | Epic/Task/PR schemas and template synchronization | GitHub ledger with Codex attempt/envelope fields | ADAPT | planned |
| K08 | Eight normative procedures under source Skills | Eight repository Skills under `.agents/skills/` | ADAPT | planned |
| K09 | Supervisor, worker, reviewer, explorer separation | Six project custom-agent definitions plus deterministic checks | REPLACE | planned |
| K10 | Bounded Task execution | `task-execution-envelope/v1` | REPLACE | planned |
| K11 | Durable comment/ritual receipts | `loop-event/v1` plus backward-compatible human records | REPLACE | planned |
| K12 | Product execution adapter | local/worktree/cloud routing and machine-readable `codex exec` adapter | REPLACE | planned |
| K13 | Installer ownership, dry-run, provenance, symlink, collision, and upgrade safety | Codex engine/tuned/instance manifest | ADAPT | planned |
| K14 | Ritual chronology, linkage, ownership, attempt, and branch checks | Hardened Task ritual with honest evidence limits | ADAPT | planned |
| K15 | Read-only governance sensors and explicit actuators | GitHub governance controls with Codex check contexts kept separate | COPY/ADAPT | planned |
| K16 | Consent-gated feedback and retro promotion | Privacy-equivalent target feedback and Codex capability checkpoints | ADAPT | later Task required |
| K17 | SHA-pinned, least-privilege CI and self-checks | Minimal Phase 0 quality/conformance gates; full topology later | COPY/REPLACE | minimal only |
| K18 | Known source defects and truthful deviations | Regression backlog and prominent limitations | ADAPT | recorded, not fixed |
| K19 | Model neutrality and no false control-plane claims | Runtime ledger outside core contracts | COPY/DEFER | foundation |
| K20 | 23 source suites and 136 target scenarios | Machine-readable conformance scorecard | ADAPT/REPLACE | empty results; release blocked |

No row is parity-complete in Phase 0 merely because policy text exists.

## 5. Current Codex capability assumptions

Evidence classes are `documented`, `locally-verified`,
`cross-surface-verified`, `unverified`, `unsupported`, and `deferred`. No
capability in this audit is cross-surface verified.

| Capability | Evidence class | Evidence observed on 2026-08-24 | Boundary carried into the target |
|---|---|---|---|
| Root and nested `AGENTS.md` | documented | [Official discovery rules](https://learn.chatgpt.com/docs/agent-configuration/agents-md#how-codex-discovers-guidance): one file per directory from project root to startup CWD, once per run; closer content comes later; default combined project limit 32 KiB | A nested file is not automatically loaded merely because a root-started task edits that subtree |
| GitHub Code Review guidance | documented | [GitHub integration](https://learn.chatgpt.com/docs/third-party/github#customize-what-codex-reviews) separately applies file-specific guidance | Keep GitHub review discovery distinct from local CWD discovery |
| Repository Skills | documented | [Skill discovery](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills), progressive disclosure, required `name`/`description`, followed symlinks | Duplicate rejection is target policy; cloud discovery is unverified |
| Skill preload and special `templates/` directory | unverified | No official preload field was found; documented resource conventions are `scripts/`, `references/`, and `assets/` | Do not claim preload; templates are ordinary explicitly referenced resources |
| Local subagent workflows | locally-verified | Three independent read-only subagents were run in the Codex desktop app for this audit | App evidence does not establish CLI, IDE, cloud, or custom-agent parity |
| Project custom-agent TOML | documented | [Custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) require `name`, `description`, and `developer_instructions` | Project/cloud loading and every role file remain runtime-unverified |
| Agent sandbox posture | documented | [Sandbox inheritance](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls): parent live permission overrides are reapplied to children | TOML is a default, not immutable identity or ownership enforcement |
| Hooks and trust | documented | [Hook trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks) is hash-specific; only command handlers run; matching commands may run concurrently | Hosted/specialized paths can bypass hooks; trust and activation must be reported, not assumed |
| Hook stopping and failure | documented | [Hook outputs](https://learn.chatgpt.com/docs/hooks#common-output-fields): `SubagentStart` cannot veto; unsupported `PreToolUse` output can fail while the tool continues; `SessionEnd` is main-thread-only and advisory | Target handler parsers can fail closed, but the platform hook layer is not a universal fail-closed wall |
| Local/worktree/cloud modes | documented | [Modes](https://learn.chatgpt.com/docs/environments/modes), [worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees), and [cloud](https://learn.chatgpt.com/docs/environments/cloud-environment) | Managed worktrees start detached; cloud receipt fields and cross-surface behavior remain unverified |
| `codex exec --json` | locally-verified | Bundled `codex-cli 0.149.0-alpha.4.1`; an ephemeral read-only run emitted `thread.started`, `turn.started`, `item.completed`, `turn.completed` and exited 0, consistent with [official JSONL documentation](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable) | Machine-readable does not mean deterministic model behavior; pin the CLI version and preserve unknown events |
| `--output-schema` | documented | [Structured output](https://learn.chatgpt.com/docs/non-interactive-mode#create-structured-outputs-with-a-schema) constrains the final response | It does not define or validate the JSONL event envelope |
| Resume by ID | documented | [Non-interactive resume](https://learn.chatgpt.com/docs/non-interactive-mode#resume-a-non-interactive-session) supports explicit ID and `--last` | Task binding is application-level; treat IDs as opaque until client-specific probes pass |
| Codex SDK | documented | [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) documents local TypeScript and Python thread control | Deferred until the CLI/event adapter is stable; do not generalize to cloud threads |
| GitHub Code Review | documented | [GitHub integration](https://learn.chatgpt.com/docs/third-party/github) requires cloud setup and is additional review evidence | It does not replace governance review and is not known to run repository Skills, TOMLs, or local hooks |
| Codex GitHub Action | documented | [Official Action configuration](https://learn.chatgpt.com/docs/github-action#configure-codex-exec) accepts `codex-version`; blank means latest | Pin both the Action SHA and Codex CLI version before depending on its event contract |
| Plugin-only distribution | deferred | Official plugin distribution exists, but repository-only activation, update, and all claimed surfaces were not verified here | Repository installer remains the initial authority |

## 6. Conflicts and corrections found during orientation

### Research-pack to current Codex behavior

1. Scenario A-002 must distinguish local startup-CWD discovery from GitHub
   Code Review's file-specific discovery. Editing `.github/workflows/*` from a
   root-started local run does not by itself load `.github/AGENTS.md`.
2. Custom-agent `sandbox_mode` is a configuration default. A parent turn's live
   permission override can replace it, and `workspace-write` does not enforce
   ownership globs or assigned-worktree identity.
3. No documented Skill preload field was found. `skills.config` enables or
   disables a Skill; `templates/` is not a documented special directory.
4. `SessionEnd` cannot require a handoff: it is advisory, runs only for the main
   thread, and cannot keep the session open. `SubagentStart continue:false`
   cannot veto creation.
5. A target hook handler may reject malformed input, but Codex hook parse or
   unsupported-output failures must not be described as universally fail
   closed.
6. Hook `agent_id` is an opaque subagent identifier until a named client proves
   that it maps to a durable or resumable thread.
7. `--output-schema` governs the final model response, not the JSONL stream.
   The adapter must tolerate unknown events, retain raw lines safely, and
   normalize only recognized fields.
8. Replace "deterministic automation" with "scripted, machine-readable
   automation" for `codex exec`; deterministic guards remain separate.
9. Pinning only `openai/codex-action` does not stabilize the embedded CLI.
   Record and pin `codex-version` too.
10. Cloud receipt fields, cloud loading of repository Skills/custom agents or
    hooks, and native archive-before-evidence blocking remain unverified.

### Research-pack to frozen source

1. The source permits a declared trivial-task no-worker exemption, so the
   statement that a supervisor never implements is too absolute.
2. The source ritual guard requires a session ID string but explicitly cannot
   verify the session. It proves a dispatch/release comment trail, not an
   authenticated active worker.
3. The Context Contract requires immutable, append-only decisions; "appendable
   and reviewable" is weaker than the source.
4. Committer timestamps are metadata-based chronology evidence. A rebase can
   move them, so they are not proof of when coding began.
5. The pack calls current PR #89 merged. It is closed and unmerged. It remains
   unrelated to the ADR's intended stacked-PR tracker, so the stale-reference
   diagnosis still stands.

### Frozen-source defects and guard gaps to avoid

| ID | Finding | Target disposition |
|---|---|---|
| SD-01 | ADR-0003's bare `#89` resolves to an unrelated closed, unmerged PR | repair with qualified provenance and a regression |
| SD-02 | `check-changelog-refs.sh` claims existence resolution but only checks a numeric ceiling in the changelog | rename the weaker check or implement fixture-backed existence validation across governed Markdown |
| SD-03 | Source-only `.vscode/mcp.json` floats `@playwright/mcp@latest` | do not install; pin any later reviewed tool dependency |
| SD-04 | Workflow-permissions guard treats `contents: none` or blank as a valid grant | harden the adapted guard and add negative cases |
| SD-05 | Task ritual accepts arbitrary suffix branch matches as managed prefixes | require an explicit approved prefix grammar and add collision cases |
| SD-06 | Adopter-feedback workflow assumes the add-label endpoint creates a missing label, while GitHub documents label creation separately | ensure the label first or fail/report explicitly; add a runtime/API fixture |
| SD-07 | Task-ritual comment says exemption matching is case-sensitive while implementation/tests are case-insensitive | align documentation and tests |
| SD-08 | Task issue and label descriptions retain stale one-Task/one-session wording after the supervisor/worker split | correct when ledger assets are ported |

For SD-06, the [GitHub labels API](https://docs.github.com/en/rest/issues/labels)
exposes distinct add-label and create-label operations and documents validation
failures for add-label requests. The target will not rely on implicit creation.

## 7. Smallest safe Phase 0 graph

```text
B0  empty-tree seed on main (complete; owns no files)
  -> E0  Freeze baseline and establish the Codex constitution
       -> T0.1  Build a self-verifying Phase 0 foundation
            -> PR 1  codex/phase-0-foundation
                 -> independent read-only governance review
                      -> human acceptance and merge
                           -> Phase 1 may start
```

`E0` and `T0.1` are logical bootstrap identifiers in this versioned record.
Issue and PR templates do not exist yet. After the ledger surface lands, the
historical bootstrap records will be migrated with links to the seed and PR;
the project must not fabricate Task comments that predate the work.

PR 1 uses the narrow onboarding/bootstrap exemption: no Task template,
Task-ritual guard, or CODEOWNERS control exists in the base. The exemption
lapses when PR 1 merges. Risk is Tier C because PR 1 introduces constitution
and workflow policy, so human review is required before merge.

### T0.1 ownership

One writer on branch `codex/phase-0-foundation` exclusively owns these paths:

```text
.gitattributes
.gitignore
LICENSE
README.md
AGENTS.md
docs/agreements/adr/ADR-0004-codex-port-baseline.md
docs/known-limitations.md
docs/planning/phase-0-orientation.md
tests/conformance/manifest.json
.github/scripts/check-phase0-contracts.py
tests/conformance/test_phase0_contracts.py
.github/scripts/check-action-pins.sh
.github/scripts/check-workflow-permissions.sh
.github/scripts/tests/lib.sh
.github/scripts/tests/test-action-pins.sh
.github/scripts/tests/test-workflow-permissions.sh
.github/workflows/ci.yml
```

No other target path may change in PR 1. Explicitly excluded are Skills,
custom agents, hooks, issue/PR templates, installer assets,
`SCAFFOLD-CHANGELOG.md`, runtime adapters, `.devcontainer`, `.vscode`, the
source design corpus, source logo, and Copilot execution surfaces.

### T0.1 acceptance criteria

1. The pre-mutation target state, empty seed, frozen source, research-pack
   checksums, and verification limits remain recorded exactly.
2. Source repository, commit, tree, tracked-file count, invariant digest,
   conformance counts, and release blocker are machine-readable.
3. `AGENTS.md` is the sole canonical invariant table, contains I01-I13, and
   recomputes to the recorded digest.
4. `README.md` prominently states that Phase 0 is not installable and not a
   parity release.
5. Known limitations include role/thread non-authenticity, hook incompleteness,
   hosted-path gaps, receipts-not-authority, no universal heartbeat/pause/
   budget, no broad auto-merge, no mandatory SDK, no plugin-only distribution,
   and model neutrality.
6. The conformance manifest records all family counts, has `results: []`, and
   has `release_blocked: true`; skipped, planned, and unverified work is never
   represented as passed.
7. Offline negative tests reject baseline drift, invariant drift, duplicate
   IDs, false passes, wrong scenario totals, missing limitations, unexpected
   paths, floating Actions/dependencies, and invalid workflow permissions.
8. CI exposes only minimum `quality` and `conformance` jobs, uses least
   privilege, pins Action refs to full SHAs with version comments, and disables
   persisted checkout credentials.
9. The PR diff equals this ownership allowlist, the frozen source checkout is
   still clean, and source-only/Copilot execution assets are absent.
10. A separate read-only reviewer verifies the current PR head and every
    criterion before human merge. Phase 1 stays blocked until merge.

### Test-first commit sequence

1. `test: define phase-0 contracts` — expected red state.
2. `docs: establish Codex constitution and provenance` — focused checks green.
3. `ci: enforce phase-0 safety gates` — all local checks green before push.

The first implementation does not claim v1 parity. It creates the vocabulary
and deterministic wall needed to make later parity work reviewable.
