---
name: task-routing
description: Decide where and with what each Task issue should run — execution surface (exec:cloud / exec:app / exec:cli / exec:ide label), suggested agent role, and suggested model/reasoning effort. Use this while decomposing an Epic, when filling the Routing block of ai-task issues, when a task changes nature mid-flight and needs re-routing, and whenever someone asks which tool (cloud agent, Codex app, CLI, IDE) should handle a piece of work.
---

# Task Routing

Every Task issue carries exactly one `exec:*` label plus a filled Routing
block. Routing is decided at planning time so that dispatch is mechanical:
orchestrators and humans read the label and act, instead of re-debating tool
choice per task.

**Routing is decided per worker** (ADR-0003): the `exec:*` label routes the
*implementation* — the worker session(s) that write the PR — not the
supervisor, which may run on a different surface (e.g., an `exec:cloud`
task's supervisor lives in an app session while its worker is the cloud
coding agent). When a supervisor implements directly under the declared
small-task exemption, the label routes that single session.

**A Task supervisor runs on the default agent** with
`.agents/skills/session-orchestration/SKILL.md` as its manual — the ritual is
fully described there, so no separate role definition exists. Do not pick
`orchestrator` for it: that role conducts the Project and Epic layers, and
its loop is written for a different job.

## Routing inputs

Score the task on five axes before choosing:

1. **Ambiguity** — is the brief fully specified, or will it need human
   judgment calls mid-task?
2. **Local dependency** — does it need physical hardware (flash, serial, HIL),
   local credentials, or a specific machine?
3. **Parallelism value** — is it one of many independent tasks worth running
   concurrently?
4. **Sensitivity** — does it expose data that must not leave the machine?
5. **Reasoning depth** — mechanical transformation, or design-grade thinking?

## Surface matrix

| Label | Surface | Strengths | Choose when |
|---|---|---|---|
| `exec:cloud` | Codex cloud task, only when available | Fully async, parallel at scale, ephemeral clean env, delivers a draft PR, iterates on CI failures | Brief is self-contained and unambiguous; no local/hardware needs; ideal for tests, refactors, docs, well-specified features |
| `exec:app` | Codex app task/worktree, only when available | Steerable in real time, session tree for orchestration, per-session model/agent choice, local checkout | Orchestration itself; tasks needing occasional steering; parallel local work isolated by worktrees; when model choice matters per task |
| `exec:cli` | Codex CLI | Scriptable, composable with `gh`, runs in CI/automation | Batch/repetitive repo operations, plan-graph manipulation at scale, scheduled or pipeline-triggered agent work |
| `exec:ide` | Codex IDE integration, only when available | Human-in-the-loop, full local toolchain, hardware access (e.g., PlatformIO upload/monitor) | Ambiguous or exploratory work; design spikes; anything touching physical devices |

## Hard rules

- **Hardware rule.** Building firmware and running `native`-env tests can go
  anywhere; flashing, serial monitoring, and hardware-in-the-loop verification
  route to `exec:ide` (or an `exec:app` session on the machine physically
  connected to the device). Never let a cloud task carry a hardware-verified
  acceptance criterion.
- **Sensitivity rule.** Tasks handling data that must stay local route to
  `exec:app`/`exec:ide` only if the chosen service/data policy actually permits it; local execution does not mean an on-device model.
- **Ambiguity rule.** If you cannot write objectively checkable acceptance
  criteria, the task is not `exec:cloud` yet — either sharpen the brief or
  route to an interactive surface.

## Dispatch using the available Codex surface

The labels express requested placement, not proof of capability. Before
dispatch, inspect the actual documented tools/client and record the chosen
workspace, branch, role, model preference and limitations. No Copilot
assignment or Copilot session API is a Codex implementation.

- App: use documented task/worktree controls exposed in the current client;
  verify the created task and its durable start claim before implementation.
- CLI: run the approved Task interactively or through a separately approved
  CLI execution path. This installed workflow adds no autonomous adapter.
- Cloud/IDE: use only a surface actually available to the adopter with
  reviewed data/tool access; otherwise choose manual local handoff.
- Missing creation/control capability: give the owner an exact kickoff with
  Task URL, plan URL, ownership, verification and branch, then wait for the
  actual worker. Do not invent calls or convert missing evidence to success.

The supervisor may use the declared small-task exemption where appropriate.
Otherwise worker creation, steering, result inspection and cleanup follow
`.agents/skills/session-orchestration/SKILL.md`; application writes stay
with the assigned worker.

## Model / reasoning suggestion

The Routing block's model suggestion is advisory (pickers and availability
change), but the effort tier is meaningful:

| Tier | Use for | Examples of intent |
|---|---|---|
| `high-reasoning` | Planning, architecture, replanning, review, tricky debugging | frontier-class model, extended/high reasoning effort |
| `standard` | Ordinary implementation with good briefs | default model settings |
| `fast` | Mechanical edits, renames, formatting, boilerplate | smaller/faster model |
| `local` | Local tools or sensitive data | require explicit service/data-policy compatibility; no on-device model is assumed |

Which model fills an implementation tier is the adopter's answer,
recorded in codex-instructions' **Models** block — read it there rather
than naming one here.

## Role suggestion

Suggest a role when a specialized definition exists in `.codex/agents/`
(e.g., `planner`, `orchestrator`, `reviewer`) or in the client's agent picker
(e.g., security- or docs-focused agents). Leave as `default` otherwise; do not
invent role names that no surface provides.

## Review routing

- On `exec:app` / `exec:cli`, use a separately available advisory reviewer for in-loop critique
  after checking the current surface (`verification`, layer 3). Never infer the
  same support for `exec:cloud` or every IDE from CLI/app documentation.
- Use the custom `reviewer` for every `risk:high` Task and every Task that
  changes governance surfaces (agreements, `AGENTS.md`, agents/skills,
  workflows/rulesets, CODEOWNERS, or CI guard scripts). It is optional for
  ordinary Tasks with complete deterministic evidence.
- When a routed surface lacks that review capability and a cross-model critique matters,
  name that independent review in the Task's Handoff notes. Choose it per
  Task and surface; never freeze one reviewer model repository-wide.

## Re-routing

A task changes surface when its nature changes: an `exec:cloud` task that
turns ambiguous comes back as `exec:ide`/`exec:app`; an exploratory task whose
outcome is now a crisp spec goes out again as `exec:cloud`. Re-routing is a
plan change: swap the `exec:*` label, adjust the Routing block, note one line
of rationale on the issue.
