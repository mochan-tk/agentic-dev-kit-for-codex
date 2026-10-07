<p align="center">
  <img src="https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-copilot/fd265ddef150fab86cd54d0e383c2c25fe297ffb/docs/logo.png" width="160" alt="Agentic Development Kit logo">
</p>

<h1 align="center">Agentic Development Kit for Codex</h1>

<p align="center">
  <strong>GitHub-native, Human-on-the-Loop workflows for development with Codex.</strong>
</p>

<p align="center">
  <a href="https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/workflows/ci.yml"><img src="https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/workflows/ci.yml/badge.svg" alt="Repository CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#prerequisites">Prerequisites</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#eight-skills-one-workflow">Skills</a> ·
  <a href="#safety-and-project-status">Safety and status</a> ·
  <a href="#documentation">Documentation</a>
</p>

Give Codex a repeatable way to prepare context, plan work, implement changes,
and return evidence. Keep plans and decisions in GitHub, rather than relying
on one conversation to remember everything.

Codex works inside a defined Task. Humans set direction, decide exceptions,
and retain agreement, acceptance, and merge authority. The kit supplies the
Skills, instructions, templates, and helpers for that workflow; it does not
replace your application, development tools, or delivery process.

Adapted from [Agentic Development Kit for GitHub Copilot](https://github.com/mochan-tk/agentic-dev-kit-for-copilot).
This edition uses Codex Skill and role files without assuming the Copilot app's
native session hierarchy or a complete autonomous runtime.

## Quick start

### Prerequisites

Using this kit requires:

- a GitHub repository with a local Git checkout;
- the **[ChatGPT Codex desktop app](https://learn.chatgpt.com/docs/app)**;
- authenticated [`gh`](https://cli.github.com/) with access to that repository;
- `jq`;
- Git and Bash 3.2 or later;
- on Windows, [Git for Windows](https://gitforwindows.org/), including Git Bash.

**The desktop app is required for this OSS, not just for this tutorial.**
Use Codex in the desktop app for onboarding, coordination and development.
Codex CLI or the IDE extension alone is not a supported way to operate the
kit. Running an installer or helper in a terminal does not replace this
requirement; those commands do not check whether the app is installed.

Before installation, prepare your specification context and create/select
the adopter's Codex project as described below. Platform-specific installation
utilities are listed in [step 1](#1-install-in-your-project).

### Before you start: prepare context and a Codex project

Use the required desktop app with your local application repository.
In desktop versions with a product selector,
select **Codex**, not ChatGPT Chat or Work, for installation and development.

1. **Prepare specification context before using the kit.** Use ChatGPT
   **Chat** for back-and-forth requirements clarification, or **Work** to
   assemble a reviewable specification from your notes and sources. Write
   down the goal, intended users, scope/non-goals, constraints, acceptance
   criteria, and unresolved questions. Review the result; reuse suitable
   existing specifications rather than recreating them. Prepare this handoff
   before adoption; the installer does not validate its contents and no
   external connector is required.
2. **First in Codex, create or select your project.** Attach the local Git
   repository where you will build your application and make its root the
   project's primary folder. This is the **adopter repository**, not this
   kit's source checkout. Prepare or clone the repository first if needed;
   creating an app project does not replace Git setup. Start a local chat
   inside that project and confirm its working directory before step 1 below.
3. **Bring the prepared context with you.** Save it in a readable file, attach
   it, or paste the relevant text when the onboarding Skill asks for material.
   For documents already committed in the adopter repository, give their
   paths instead of duplicating them. Do not assume Chat/Work history, a
   ChatGPT project, or a chat link automatically supplies context to Codex.
   Share only material you are authorized to use; drafts are not approved
   agreements until reviewed through the kit's human decision process.

A Codex project selects the execution context. It is not a ChatGPT preparation
project or a GitHub Projects board. See the [detailed preparation checklist](docs/distribution/source-first-installer.md#prepare-context-and-the-desktop-project)
and official guidance on [desktop mode selection](https://learn.chatgpt.com/docs/app),
[local project folders](https://learn.chatgpt.com/docs/projects#use-local-projects-for-folders-and-codebases),
and [Chat versus Work](https://learn.chatgpt.com/docs/use-chatgpt#choose-how-you-want-to-work).

### 1. Install in your project

Use the root of an **existing Git repository** that no other agent or person
is changing concurrently: the adopter root selected in your Codex desktop
project above. Run these commands from a terminal at that root. You do not
need to clone this kit first.

| Installation route | Additional utilities |
|---|---|
| macOS / Linux installation | curl, find, standard Unix utilities (including GNU/BSD `stat`), and `sha256sum` or `shasum` |
| Windows installation | PowerShell and the Unix utilities supplied by Git for Windows / Git Bash |

**macOS / Linux**

```sh
curl -fsSL https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-init.sh | bash
```

**Windows PowerShell**

```powershell
irm https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-init.ps1 | iex
```

Downloading the public kit needs no GitHub login. Operating the kit still
requires the authenticated `gh` listed above; anonymous acquisition is not
an alternative to the workflow prerequisites.
The Windows entry uses Git Bash, not WSL. It has synthetic-test coverage;
native Windows installation has not been measured.

The installer resolves a source revision, validates the payload, installs it,
and stages only newly installed files. It preserves existing project-owned
files and refuses conflicting engine files or unsafe paths. It does **not**
create a Git repository, commit, push, configure GitHub, or start onboarding.

To preview without changing project files or the Git index:

```sh
curl -fsSL https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-init.sh | bash -s -- --dry-run
```

These commands execute downloaded code. Review the source before trusting it.
For a fixed revision, caller-side `pipefail` to detect initial download failure,
PowerShell flags, or local-source installation, see the
[installation guide](docs/distribution/source-first-installer.md#one-command-first-installation).
If copying or staging fails, stop and review the reported partial state; do
not assume the installer has rolled it back.

### 2. Review and land the installation

Inspect the staged changes:

```sh
git diff --cached
```

Other changes may already have been staged before installation. Commit only
the adoption changes you have reviewed, and land them on the remote default
branch through your normal approval process. Do this before onboarding makes
GitHub changes.

Keep your project's existing README, AGENTS, CI, and other customizations.
If an existing `AGENTS.md` was preserved, explicitly connect the installed
`.github/codex-instructions.md` and Skills as described in the
[installed workflow guide](.github/distribution/payload/README.md).
Its no-staging description applies to the local source engine; the external
entry above stages new files. The public installation guide distinguishes both.

### 3. Onboard in Codex

Before invoking the Skill, open or select the adopter checkout in Codex—
**your project**, not this kit's repository. In the desktop app, start a new
local chat in the project prepared above so it can read the newly installed
files. Keep your prepared specification context ready for the material
question, and answer each pending question explicitly, including the model
preference (`auto` is an explicit choice, not a timeout default).

In the desktop project chat, invoke the installed Skill:

```text
$project-onboarding
```

If your desktop app version does not expose that invocation, use this
explicit installed-file fallback in the same chat:

```text
Read and follow .agents/skills/project-onboarding/SKILL.md in this project.
```

Confirm it reads the installed file, not the kit-development Skill. This is
an explicit handoff, not a guarantee of automatic discovery in every app version.

Onboarding inventories the project, verifies its existing commands, tunes
project instructions, and prepares an evidence-bearing onboarding PR and
planning handoff. It does not implement your application's next feature.
Review the PR, resolve or record deferred work, and accept onboarding before
moving on to ordinary development.

After the reviewed installation reaches the remote default branch, onboarding
runs canonical label setup and, when you supply a goal or material, drafts
phase Epic Issues for your review.
Those GitHub writes are distinct from optional Ruleset setup. Choose Enable
now, Create disabled, or Skip explicitly; the write choices require a reviewed
profile and separate consent. Skip performs no Ruleset operation.
The installer itself creates neither CI workflows nor branch protection. See the [onboarding Skill](.github/distribution/payload/.agents/skills/project-onboarding/SKILL.md).

To connect Task records to PR checks, a separate [opt-in adopter CI companion](docs/distribution/adopter-ci.md)
previews three addon files for explicitly named application checks. It requires
a supported existing workflow, preserves application CI and the Git index,
and adds no required-check settings. Accept its installation before separately
considering check activation; it is outside the legacy 47-file update path.

### 4. Complete one small Task

For an existing codebase, start with characterization tests for the area you
intend to change, before feature work. This follows the onboarding Skill's
legacy path and gives later changes an observed-behavior baseline. For example:

```text
Use the installed kit workflow to add characterization tests for the existing
report page. Capture its current behavior without adding a feature or changing
application behavior.

Inspect the code first. Propose the acceptance criteria, owned files,
verification commands, and Task plan. Ask me to resolve unclear requirements.
After the plan is agreed, implement and test the change, then open a PR
with the results and any remaining concerns. Leave the merge decision to me.
```

The [illustrative worked example](docs/worked-example.md) walks through a
first characterization Task with locally runnable reference tests. It is not a
record of accepted live work and is not installed into your project.

Review the Task, diff, and evidence—not only the final chat message. Accept,
redirect, or reject the result. Use the retrospective workflow when repeated
friction suggests a reusable improvement. After the characterization baseline
is accepted, plan a small feature Task separately. For a new codebase, agree
the initial behavior and tests in its first bounded Task.

### 5. Update explicitly when you choose

You do not need a kit clone. Supply the full 40-character commit IDs for the
version previously installed (`FROM`) and the reviewed new version (`TO`).
Use the previous installation's recorded `source-commit` or accepted adoption
record for `FROM`; if it is unknown, inspect that record before updating.
Choose a **new recovery directory outside your project**, with an existing
parent. Run from your project root; keep exclusive ownership during the update.

```sh
FROM=FULL_OLD_COMMIT_SHA
TO=FULL_NEW_COMMIT_SHA
RECOVERY=/path/to/new-private-recovery
set -o pipefail
curl -fsSL https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-update.sh | bash -s -- --from "$FROM" --to "$TO" --recovery "$RECOVERY"
```

The default previews the update without changing project files, the index, or
the requested recovery directory. Apply that explicit update with:

```sh
curl -fsSL https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-update.sh | bash -s -- --from "$FROM" --to "$TO" --recovery "$RECOVERY" --apply
```

PowerShell with Git Bash uses the same inputs and default preview:

```powershell
$From = 'FULL_OLD_COMMIT_SHA'
$To = 'FULL_NEW_COMMIT_SHA'
$Recovery = 'D:\private-recovery\new-update'
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-update.ps1))) --from $From --to $To --recovery $Recovery
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-update.ps1))) --from $From --to $To --recovery $Recovery --apply
```

Known-old engine files update; tuned instructions, instance records, existing
seed files and unrelated work are preserved. Unknown engine edits refuse the
whole update. Nothing is staged, committed or pushed. Keep the private recovery
directory at its original location, including after a failed apply. See
[offline rollback and fixed-entry selection](docs/distribution/source-first-installer.md#one-command-explicit-update)
before changing or deleting retained recovery inputs. Native Windows remains
unmeasured; updates are explicit and do not detect installed versions.

### 6. Check the project without cloning the kit

Use the [fixed-revision companion commands](docs/distribution/companion-checks.md)
to observe GitHub governance, check a planned worktree action, or validate
connector definitions. Choose the check and supply your actual inputs; each
Bash command downloads the complete unchanged helper, verifies its recorded
SHA-256, and runs it without installing extra files into your project.

Governance uses your existing authenticated `gh` for GET-only observations;
the other checks are local after downloading. No command repairs settings,
claims ownership, activates connectors or grants permission to push. Missing
evidence remains non-success. A successful check is not runtime qualification.

## How it works

GitHub is the durable work record. Codex sessions carry out the work; they do
not replace the Issue graph or the human decision to accept a result.

```mermaid
flowchart LR
    A[Context and agreements] --> B[Epic and Task Issues]
    B --> C[Scoped Codex work]
    C --> D[Pull request and checks]
    D --> E[Human acceptance]
    E --> F[Retrospective]
    F --> B
    D -->|Needs clarification or replanning| B
```

This diagram describes the workflow, not a guaranteed native session tree.
Use the tools actually available in the required Codex desktop app, or an explicit
handoff based on the committed files and GitHub records.

| Responsibility | Focus |
|---|---|
| Human owner | Intent, priorities, risk decisions, agreements, acceptance, and merge |
| Project / Epic coordination | The Issue graph, dependencies, next actionable Tasks, and replanning |
| Task supervision | Scope, plan, one active writer, verification, and escalation |
| Implementation worker | One scoped change, tests, commits, and evidence for a pull request |

The three shipped role definitions provide instructions. They do not establish
authenticated identities or guarantee native role selection. A GitHub Projects
board is optional; the Issue graph remains authoritative.

### Human-on-the-Loop by design

Routine, scoped work can proceed under the agreed plan without asking a human
to approve every edit. Ambiguity, high risk, scope changes, and insufficient
evidence return to human judgment. Agreement and merge authority stay with
the owner.

Four habits make that practical: record decisions before reporting them,
verify before claiming completion, keep one writer per owned scope, and
escalate rather than guess. Planned handoffs preserve the current Task,
plan, and committed checkpoint; they are not automatic crash recovery.

## Eight Skills, one workflow

These links show the **payload installed in your project**. Contributor
instructions for this kit are in [AGENTS.md](AGENTS.md).

| Skill | Use it to |
|---|---|
| [project-onboarding](.github/distribution/payload/.agents/skills/project-onboarding/SKILL.md) | Discover the project, verify its commands, and prepare its onboarding PR |
| [context-collection](.github/distribution/payload/.agents/skills/context-collection/SKILL.md) | Collect source material with provenance, or explicitly start builtin drafting |
| [context-distillation](.github/distribution/payload/.agents/skills/context-distillation/SKILL.md) | Propose durable requirements and decisions for human review |
| [plan-management](.github/distribution/payload/.agents/skills/plan-management/SKILL.md) | Build Epic / Task Issues and identify actionable work |
| [task-routing](.github/distribution/payload/.agents/skills/task-routing/SKILL.md) | Choose a suitable execution path for the bounded Task |
| [session-orchestration](.github/distribution/payload/.agents/skills/session-orchestration/SKILL.md) | Coordinate supervision, implementation, replanning, and handoffs |
| [verification](.github/distribution/payload/.agents/skills/verification/SKILL.md) | Check the diff, test results, and current records against acceptance criteria |
| [retro](.github/distribution/payload/.agents/skills/retro/SKILL.md) | Turn supported recurring problems into reviewed improvement proposals |

Use the Skill needed for the current step; do not restart onboarding for each
Task. Collected material and draft requirements are not automatically accepted
project truth. Distillation and review are separate decisions.

## Safety and project status

The kit is a workflow scaffold with explicit evidence and human gates—not an
autonomous service or a guarantee that generated code is correct.

| Boundary | What to expect |
|---|---|
| Existing project assets | Installation preserves project-owned content and stops on unsafe conflicts |
| Updates and recovery | Explicit old/new commit IDs support a one-command update with preserved customizations and retained offline operation rollback; no automatic or whole-repository recovery |
| Governance helpers | Reads report missing evidence as non-success; setup writes require separate, explicit authority |
| Feedback and retro | Reporting is consent-gated; retrospective proposals do not approve or retire controls automatically |
| Codex compatibility | The ChatGPT Codex desktop app is required; CLI-only/IDE-only operation is unsupported. Evidence remains version/path-specific; automatic Skill discovery and cross-client parity are not promised |
| Product and release | A source-first workflow kit with bounded product tests; native Windows and cross-client runtime parity remain unmeasured |

The explicit governance, worktree and connector companions can run from a
reviewed kit checkout or the [verified no-clone commands](docs/distribution/companion-checks.md).
They are not additional files installed by the one-command entry. The
consent-gated failure reporter also has a [verified no-clone draft/send guide](docs/distribution/feedback.md).
For manual text, use the [public feedback form](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/new?template=feedback.yml)
and review its privacy warning before submitting. Installation failures print
fixed links to these routes; reporting remains an explicit separate action. See the
[helper and procedure guide](docs/distribution/source-first-installer.md#governance-worktree-and-retro-procedures).

This repository has a clean product Git history and preserves the accepted
predecessor's 47-file payload and installer engine. See
[product scope](docs/product-scope.md) and [known limitations](docs/known-limitations.md)
for current behavior and evidence boundaries. Earlier acceptance, research and
unfinished runtime/release work remain in the [predecessor records](docs/provenance.md).
The [dated evidence status](docs/evidence-status.md) separates baseline CI,
synthetic conformance, the accepted historical desktop exercise and unmeasured
behavior. Historical acceptance does not establish live behavior of later revisions.

## Documentation

| You want to… | Read |
|---|---|
| Install, select a revision, update, or recover an operation | [Installation guide](docs/distribution/source-first-installer.md) |
| Check governance, worktrees or connector definitions without a kit clone | [Read-only companion commands](docs/distribution/companion-checks.md) |
| Draft installer feedback without a clone or share public-safe manual feedback | [Feedback guide and public form](docs/distribution/feedback.md) |
| Opt in to separate Task metadata, retarget freshness and control drift checks | [Adopter CI companion](docs/distribution/adopter-ci.md) |
| Review retrospective signals, official content checkpoints and feedback | [Ongoing improvement companions](docs/distribution/ongoing-improvement.md) |
| Observe open PR checks and reviews manually | [Manual PR monitor](docs/distribution/pr-monitor.md) |
| Understand the installed instructions and workflow | [Installed workflow guide](.github/distribution/payload/README.md) and [installed AGENTS](.github/distribution/payload/AGENTS.md) |
| Walk through a first characterization Task with runnable reference tests | [Illustrative worked example](docs/worked-example.md) |
| Understand Issue-graph authority | [Installed instructions](.github/distribution/payload/AGENTS.md) |
| Check evidence boundaries and compatibility limits | [Known limitations](docs/known-limitations.md) |
| Distinguish tested behavior, historical live acceptance and unmeasured claims | [Dated evidence status](docs/evidence-status.md) |
| Inspect the shipped scope | [Product scope](docs/product-scope.md) |
| Inspect earlier acceptance and development history | [Source provenance](docs/provenance.md) |
| Run checks or contribute to the kit | [Contributing](CONTRIBUTING.md) and [contributor instructions](AGENTS.md) |

## Contributing

Use a bounded Task with a recorded plan, explicit file ownership, and evidence
for the change. Preserve existing safeguards, add relevant regression tests,
and leave acceptance and merge decisions to the owner.

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and this repository's
[AGENTS.md](AGENTS.md). These instructions govern contributions to the kit.

A contributor quick check, from this kit's checkout:

```sh
python3 -I .github/scripts/check-product.py
python3 -I .github/scripts/check-installer.py
git diff --check
```

These are a starting subset; use the [full validation instructions](CONTRIBUTING.md#local-validation).
Product CI runs quality and conformance checks without predecessor history or
old Issue retrieval. Pinned lint-tool acquisition is a separate CI network step.

## Attribution and license

This project adapts [Agentic Development Kit for GitHub Copilot](https://github.com/mochan-tk/agentic-dev-kit-for-copilot).
The frozen behavioral source and target adaptations are recorded in
[source parity](.github/distribution/source-parity.v1.json).
The logo is reused from that same frozen source revision; it is an external
reference, not a claim of OpenAI endorsement.

Licensed under the [MIT License](LICENSE). Your application's license remains
yours; installing the kit does not replace it.
