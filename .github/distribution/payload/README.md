# Agentic development workflow for Codex

This installed scaffold adapts the Copilot kit's Issue-first workflow to
Codex Skills and role files. GitHub is durable authority; threads are
replaceable transport. This is a local-source workflow payload, not a claim
of complete autonomous execution or full runtime parity.

## Start

1. Review the installation diff. If your existing AGENTS.md was preserved,
   explicitly link `.github/codex-instructions.md` and the installed Skills.
2. Stage and land the reviewed adoption on the remote default branch before
   onboarding performs GitHub writes. The installer never stages or commits.
3. Open this repository in your available Codex client and explicitly invoke
   `$project-onboarding`. Existing commands are verified in a clean checkout;
   unverified work goes into the evidence PR or first Epic deferred ledger.
4. Use `$context-collection`, `$context-distillation` and `$plan-management`
   when material and an approved goal are ready. Use `$task-routing`,
   `$session-orchestration`, `$verification` and `$retro` for bounded work.

## Collect context and prepare requirements

1. Collect existing material with the
   [context-collection Skill](.agents/skills/context-collection/SKILL.md) and the
   appropriate source connector. If you have no requirements source, explicitly
   choose builtin kickoff. In Codex CLI or IDE, for example:
   `$context-collection Start builtin kickoff for <topic>; I have no existing requirements source.`
   On another surface, explicitly request that installed Skill file and the
   builtin route. It reads [builtin retrieve](.github/connectors/builtin.md#retrieve)
   for draft-first candidates and bounded questions, retaining drafts,
   provenance, assumptions and unanswered questions under `.github/docs/context/`.
   Stop the interview at any time; ordinary collection does not start it.
2. Optionally prepare a source registry with the reviewed
   [setup-sources helper](.github/scripts/setup-sources.sh):
   `bash .github/scripts/setup-sources.sh` from the adopter root. Inspect its
   diff and the [connector contract](.github/connectors/README.md) before use.
   Registry preparation is not activation or context sufficiency. Activation
   requires the agreements PR and human review; a generated placeholder proves
   neither. No helper runs during collection or installation automatically.
3. When candidates warrant agreements, use the
   [context-distillation Skill](.agents/skills/context-distillation/SKILL.md) to
   prepare the source-linked proposal for human review. Do not write to
   `.github/docs/agreements/` during kickoff; promotion uses a human-reviewed
   distillation PR. Apply the connector's verification and sufficiency test
   before decomposition.

Existing adopter README files are preserved by install and upgrade. The
installed context-collection Skill links directly to builtin retrieve, so
explicit kickoff remains available through that Skill even with your own README.
These are installed instructions; client invocation and successful elicitation
need evidence from the actual Codex surface. No implicit preload is assumed.

## Scope and prerequisites

Local files require Git, Bash and a SHA-256 utility. The GitHub helpers
require authenticated gh with the features they invoke; inspect `--help`
first. GitHub writes, rulesets, boards and source activation are explicit
owner-approved actions, never installer side effects. The PowerShell helper
selects Git Bash, not WSL. Real Windows/Codex orchestration must be verified
on the chosen client; offline file tests do not prove it.

No VM, mandatory connector, model, Rulesync, global configuration or account
setup is required by installation. Keep your existing CI, CODEOWNERS,
editor files, application and instance agreements. No kit-development Task
IDs, pins, sole-active policy, conformance results or qualification
infrastructure is shipped.

## Roles and topology

Optional `.codex/agents/{orchestrator,planner,reviewer}.toml` defines guidance
only. A Project coordinator observes the Epic set; Epic threads are siblings.
Epic -> Task -> Worker remains the delegation intent when the actual surface
supports it. No API or child isolation is assumed; explicit owner-created
tasks and durable manual kickoffs remain usable fallback.

The installed `check-task-ritual.sh` is an explicit sensor, not an enabled
CI wall. Installing files does not create workflows, rulesets or reviewers.

## The sufficiency test

A Task is executable when a fresh worker can read its objective, acceptance,
references, ownership, verification and routing without chat history.
Promote reusable decisions to agreements only when owner review warrants it.

## Attribution

The derived scaffold is MIT-licensed, Copyright (c) 2026 Takashi Kawamoto
(Mr.Mo). The full notice accompanies the always-installed engine helper
`.agents/skills/plan-management/scripts/frontier.sh`; your application's own
LICENSE is neither installed nor changed.
