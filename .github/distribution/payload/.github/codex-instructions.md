# Codex Repository Instructions

Trust these instructions. Search the codebase only when something here is
missing or demonstrably wrong — and when that happens, propose a fix to this
file as part of your PR (see the retro skill).

## First contact

At the start of a session, run `bash .github/scripts/tuning-status.sh --quiet`
— on Windows, `pwsh .github/scripts/run.ps1 tuning-status.sh --quiet` instead,
because typing `bash` there reaches the WSL launcher rather than Git Bash even
when Git for Windows is correctly installed.

Read the exit code as three answers, not two. **0** means tuned. **1** means
`CUSTOMIZE` markers remain: this scaffold is **not onboarded**, so your first
reply must say so, offer to run `$project-onboarding` (the project-onboarding
skill), and wait for an explicit yes or no before taking on any other task.
**Anything else** — a usage error, a missing interpreter, a script that is not
there — means the check did not run. Say that plainly and say what you will do
next; never report it as either answer, and never carry on as though the
scaffold were tuned.

`AGENTS.md` at the repository root defines the operating protocol
(persistence rule, record-before-report, verify-before-done, unit of work,
single-writer rule, Ambiguity rule). It applies to you in full. This file adds the operational
details Codex needs to work efficiently in this repository.

## Repository layout

The scaffold supplies only its explicit installed inventory under `.github/`,
`.agents/skills/`, `.codex/agents/` and the documented root seeds. Existing
adopter files remain adopter truth; no whole directory is owned implicitly.

<!-- CUSTOMIZE: Keep this map accurate; it saves agents expensive exploration.
     Example:
     - `firmware/`  — PlatformIO project. Envs defined in `firmware/platformio.ini`.
     - `server/`    — API server. Entry point `server/src/index.ts`.
     - `app/`       — client app.
     - `.github/docs/context/`    — raw collected material (read for background).
     - `.github/docs/agreements/` — reviewed decisions (read before designing anything).
-->
- `.github/docs/context/` — raw collected material.
- `.github/docs/agreements/` — reviewed requirements, ADRs, glossary, non-goals.
- `.agents/skills/` — procedures. `.github/instructions/` — path-scoped rules.
- `.codex/agents/` — role definitions (orchestrator, planner, reviewer).

## Environment setup and validated commands

If `CUSTOMIZE` markers remain below, **First contact** (top of file) applies.

Run steps in this order. Do not improvise alternative commands when these work.

Scaffold inventory: run `bash .github/scripts/tuning-status.sh`; exit 1 means
project tuning remains, not an installer failure. Source development tests and
qualification controllers are not installed or required by the adopter.

<!-- CUSTOMIZE: Replace with commands verified to work in a clean environment,
     including known failures and workarounds. Keep this in sync with
     the adopter CI and documented local environment. No cloud setup workflow
     or runtime environment is installed by this kit. Example:

     1. `npm ci`               — install server/app dependencies (~2 min).
     2. `pip install platformio` — required before any firmware command.
     3. `npm test`             — full unit test suite; must pass before any PR.
     4. `pio test -e native -d firmware` — firmware logic tests on the host.
        Note: `pio test` without `-e native` tries to reach real hardware and
        will fail in cloud environments — never use it there.
-->

## Models

Recorded during onboarding (P2); `auto` means the app decides.

- **Implementation:** `auto`

Use it when dispatching implementation work. Review behavior is selected
per Task and surface (`task-routing`, `verification`), not frozen here.

## Working a Task issue

The Task issue body is your work order: you read it, you never edit it
(AGENTS.md §5). It follows
`.github/ISSUE_TEMPLATE/ai-task.yml` and contains: Objective, Context &
references, Acceptance criteria, Out of scope, File ownership, Verification,
and Routing. Read all of it before writing code.

1. The supervisor records the claim, plan and dispatch on the Task,
   using `.agents/skills/session-orchestration/SKILL.md` before implementation.
   A worker follows that approved plan and reports evidence to the supervisor;
   it does not invent a second claim or supervisory plan. A declared
   trivial-task exemption may combine these roles only as that Skill permits.
2. Read the durable claim, plan and dispatch. If the plan changes materially,
   stop for the supervisor's durable update before continuing affected work.
3. Use the branch and worktree assigned by the durable plan (normally
   `codex/task-<issue-number>-<short-slug>`). Touch only paths listed under
   **File ownership**.
4. Keep the PR description synchronized with reality: map each acceptance
   criterion to evidence using the table in the PR template, and link the
   plan comment (auto-written plan text in the description is a copy — the
   issue comment stays authoritative).
5. Run every command in the issue's **Verification** section before marking the
   PR ready. If a command fails, fix the cause or report the blocker — never
   delete or weaken the check.
6. If the task turns out to be materially different from its description,
   follow the Ambiguity rule in `AGENTS.md` (comment, label `needs:human` or
   `needs:replan`, stop).
7. The worker returns evidence, deviations and follow-ups; the supervisor
   verifies them and records the record-before-report outcome on the issue
   using `.agents/skills/session-orchestration/SKILL.md`. Missing post-merge
   acceptance remains pending, not completed.

## Pull request conventions

- Title: imperative mood, mirrors the Task issue title.
- Body: fill `.github/PULL_REQUEST_TEMPLATE.md` completely, including
  the evidence table and authorized Task relationship. Use `Refs #<n>` when
  acceptance requires post-merge evidence or this is a non-final/stacked PR.
  Use `Closes #<n>` only for the authorized final relationship when merge may
  complete the Task, following `AGENTS.md` and the session-orchestration Skill.
- Keep PRs reviewable: one Task issue per PR; split only when ownership or review scope becomes unbounded; a source port
  may legitimately exceed a small line-count heuristic.

## Things that will get your PR rejected

- Diff touches paths outside the issue's File ownership section.
- Acceptance criteria without evidence, or verification commands not run.
- Secrets, tokens, or credentials in code or config.
- PII, credentials, or customer data pasted into issues, PRs, or commit
  messages — reference access-controlled storage instead (verification
  skill, "Reference, don't paste").
- Modified CI workflows, rulesets, or checks without an explicit mandate.
- Non-English persistent artifacts (code comments, docs, commit messages).
