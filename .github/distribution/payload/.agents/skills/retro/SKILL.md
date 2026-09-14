---
name: retro
description: Convert repeated failures, recurring review comments, and incidents into permanent system improvements — targeted diffs to instructions, skills, agreements, templates, or CI, delivered as small `retro:` PRs and logged. Use this when the same class of mistake or review nit appears a second time, after any incident or rejected agent PR worth learning from, and during periodic reviews of whether the always-on instruction files have gone stale.
---

# Retro

Every guidance file in this repository (`AGENTS.md`, instructions, skills,
templates, workflows) is itself version-controlled and PR-reviewable — which
means the system can learn. Retro is the loop that makes it happen: a failure
observed twice is not bad luck, it is a missing asset. Fixing the instance
helps once; fixing the asset helps every future session of every agent.

## Trigger

- The same failure class or review comment appears for the **second** time
  (twice is the threshold: once may be noise, and encoding noise bloats the
  always-on budget).
- An agent PR is rejected, an incident occurs, or a task fails twice —
  regardless of repetition.
- Scheduled hygiene: periodically ask "which always-on lines have not mattered
  recently?" and demote them (see Budget rule).

## Candidate ledger

The trigger fires at the second occurrence — so first occurrences must be
counted somewhere durable. That ledger is `retro:candidate` issues (AGENTS.md
§1: GitHub, never chat or local notes).

1. **Search before filing:**
   `gh issue list --label retro:candidate --search "<keyword>"`.
2. **File** if absent: title `retro-candidate: <one-line friction>`, body =
   link to the occurrence plus one line of context, label `retro:candidate`.
3. **+1** if present: comment on the candidate with the new occurrence link.
   The comment body must **start with `Occurrence:`** — that marker is what
   the hygiene script counts; ordinary discussion never increments the count.
   The filing and `Occurrence:` comments are inputs, not unconditional votes:
   count only distinct incidents with distinct supporting evidence. Repeated
   links or rephrased copies never increment the count.
4. **Promote** at count >= 2: run the Procedure below; the `retro:` PR closes
   the candidate with a comment linking the fix.

During an explicit review, list candidates overdue for promotion. No monthly
job is installed.

### Reproduce the candidate review

Set `RETRO_INPUT` to a bounded JSON readback with `origin` (`github-readback`
or `synthetic`), `candidate`, `friction`, and `occurrences`. Each occurrence
contains `id`, the same `friction`, an `evidence` URL and its `root_cause`.
Examples and test records are explicitly synthetic from creation; they are
never presented as actual incidents or actual owner decisions.

Run this Bash block to derive evidence-linked candidate state. Different URLs
alone do not prove independent incidents: a human must inspect the records
and confirm independence before promotion through the Procedure below.
`promotion-ready` marks an overdue review, not an adopted permanent rule.

<!-- BEGIN retro-candidate-review -->
```bash
set -euo pipefail
test -f "$RETRO_INPUT" && test ! -L "$RETRO_INPUT"
test "$(wc -c < "$RETRO_INPUT")" -le 1048576
jq -es '
  def text: type=="string" and length>0 and length<=4096 and (test("[[:cntrl:]]")|not);
  def link: text and test("^https://[^ /]+/[^ ]+$");
  select(length==1)|.[0]
  | select((.origin=="synthetic" or .origin=="github-readback") and (.candidate|text) and (.friction|text)
      and (.occurrences|type)=="array" and (.occurrences|length)<=128)
  | . as $record
  | select(all(.occurrences[];(.id|text) and .friction==$record.friction and (.evidence|link) and (.root_cause|text)))
  | (.occurrences|unique_by(.id)|unique_by(.evidence)) as $events
  | {origin,candidate,friction,occurrences:($events|length),
     state:(if ($events|length)>=2 then "promotion-ready" else "candidate" end),
     evidence:[$events[]|{id,evidence,root_cause}],
     review:"pending-human-independence-and-adoption-review"}
' "$RETRO_INPUT"
```
<!-- END retro-candidate-review -->

Then classify the root cause, select the missing asset, prepare the smallest
preventive diff, append the review/log reference and obtain human agreement
review. The computed count does not select or apply a rule.

### Review obsolete or redundant controls

Retirement receives the same evidence and agreement scrutiny as addition.
Without original rationale, current evidence of obsolescence/redundancy and
an explicit owner decision, retain the control.

Set `RETRO_TARGET` to the reviewed repository and `RETRO_INPUT` to a raw
record containing `origin`, `control` (`id`, relative `path`, current Git
`blob`, exact single `line`, `reason`, supporting `evidence` URLs), `decision`
(`action: "retire"`, matching `control` ID, `path`, `blob` and exact `line`, `actor`, durable
`reference`), and an existing `log_path`. Read back the decision from the
actual owner record. A URL or actor string does not prove authority: human
review of identity, evidence and scope remains required.

This block emits a bounded diff: remove one exact control line and append one
log row. It checks the actual Git blob and leaves current files and history
unchanged. Review the diff before a separately authorized PR applies it.
The conformance example applies it only inside an explicitly synthetic,
disposable Git repository. No real control, Ruleset or original DoD is retired;
no engine, scheduler, feedback send or upstream publication runs.

<!-- BEGIN retro-retirement-diff -->
```bash
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0
test -d "$RETRO_TARGET"
test -f "$RETRO_INPUT" && test ! -L "$RETRO_INPUT"
test "$(wc -c < "$RETRO_INPUT")" -le 1048576
jq -es '
  def text: type=="string" and length>0 and length<=4096 and (test("[[:cntrl:]|]")|not);
  def link: text and test("^https://[^ /]+/[^ ]+$");
  def path: text and test("^[A-Za-z0-9._/][A-Za-z0-9._/-]*$") and (startswith("/")|not) and (test("(^|/)\\.\\.?(/|$)|//")|not);
  length==1 and (.[0]|(.origin=="synthetic" or .origin=="github-readback")
    and (.control.id|text) and (.control.path|path) and (.control.blob|test("^[0-9a-f]{40}$"))
    and (.control.line|text) and (.control.reason|text)
    and (.control.evidence|type)=="array" and (.control.evidence|length)>0 and all(.control.evidence[];link)
    and .decision.action=="retire" and .decision.control==.control.id and .decision.path==.control.path and .decision.blob==.control.blob and .decision.line==.control.line
    and (.decision.actor|text) and (.decision.reference|link) and (.log_path|path) and .log_path!=.control.path)
' "$RETRO_INPUT" >/dev/null
CONTROL_PATH="$(jq -r .control.path "$RETRO_INPUT")"
LOG_PATH="$(jq -r .log_path "$RETRO_INPUT")"
EXPECTED_BLOB="$(jq -r .control.blob "$RETRO_INPUT")"
LINE="$(jq -r .control.line "$RETRO_INPUT")"
cd "$RETRO_TARGET"
test "$(git rev-parse --show-toplevel)" = "$(pwd -P)"
for item in "$CONTROL_PATH" "$LOG_PATH"; do
  test -f "$item" && test ! -L "$item"
  ancestor="$item"
  while [[ "$ancestor" == */* ]]; do
    ancestor="${ancestor%/*}"; test ! -L "$ancestor"
  done
  test "$(wc -c < "$item")" -le 1048576
  test "$(git hash-object -- "$item")" = "$(git rev-parse "HEAD:$item")"
done
test "$(git hash-object -- "$CONTROL_PATH")" = "$EXPECTED_BLOB"
test "$(grep -Fxc -- "$LINE" "$CONTROL_PATH")" = 1
LINE_NUMBER="$(grep -Fnx -- "$LINE" "$CONTROL_PATH" | cut -d: -f1)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/retro-review.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
sed "${LINE_NUMBER}d" "$CONTROL_PATH" > "$SCRATCH/control"
cp "$LOG_PATH" "$SCRATCH/log"
jq -r '"| " + .origin + " | retire " + .control.id + " at " + .control.blob + " | " + .control.reason + " | " + (.control.evidence|join(" ")) + " | " + .decision.actor + " " + .decision.reference + " |"' "$RETRO_INPUT" >> "$SCRATCH/log"
diff -u --label "a/$CONTROL_PATH" --label "b/$CONTROL_PATH" "$CONTROL_PATH" "$SCRATCH/control" || test "$?" = 1
diff -u --label "a/$LOG_PATH" --label "b/$LOG_PATH" "$LOG_PATH" "$SCRATCH/log" || test "$?" = 1
```
<!-- END retro-retirement-diff -->

## Classify the root cause, then pick the asset

| Root cause | Fix lands in |
|---|---|
| Agents lacked a fact or decision | `.github/docs/agreements/` (via the agreements PR process) |
| A rule existed only in someone's head or a review thread | `.github/instructions/*.instructions.md` or `AGENTS.md` (mind the tier — see `context-distillation` §Tiering) |
| A multi-step procedure was improvised inconsistently | a skill under `.agents/skills/` (new or amended) |
| The brief allowed the mistake | `.github/ISSUE_TEMPLATE/ai-task.yml` or the planner quality bar |
| Nothing would have caught it automatically | a CI check / lint rule / test in `.github/workflows/` or the codebase |

Prefer the **most deterministic** asset that can host the fix: a CI check
beats an instruction line, because instructions are advice and checks are
walls.

## Source-template-only behavior not installed

The source template's platform-baseline polling and monthly hygiene job are
not adopter workflow dependencies and are not shipped here. Review candidate
issues manually or use a separately approved scheduler; do not claim a job
ran or counted occurrences merely because these instructions exist.

## Procedure

1. Gather the evidence: links to the ≥2 occurrences (PR review threads,
   failed runs, issue comments).
2. Write the **smallest diff** that would have prevented the latest
   occurrence. Resist writing an essay; one sharp rule outperforms three
   vague ones.
3. Apply the **Budget rule** for always-on files (`AGENTS.md`,
   `codex-instructions.md`): they must stay lean (target well under ~150
   lines each). When adding a line, look for a line to remove or demote to a
   scoped/on-demand tier. Unbounded growth of always-on context is how the
   system gets slowly worse while everyone follows the process.
4. Open a PR titled `retro: <what it prevents>`, containing the asset diff
   plus one appended row to `.github/docs/agreements/retro-log.md`:

```markdown
| 2026-07-03 | Cloud tasks kept claiming HIL criteria | verification skill + ai-task template: hardware criteria must defer to exec:ide follow-up | #142 #155 |
```

5. Human review approves — a retro PR changes how all agents behave, so it
   gets the same scrutiny as an agreement.

## Upstreaming project-agnostic fixes

When the root cause is scaffold-generic — it would bite any project built
from this template, not just this one — land the fix here first, then propose a
matching PR on the scaffold **template repository** with explicit permission and prefix the retro-log
Fix cell with `[upstreamed]`. Project tunings (Sync Triangle content, globs,
layout maps) never go upstream. This closes the second improvement loop:
instances feed the template that future projects inherit
(`SCAFFOLD-CHANGELOG.md` documents versions and the upgrade path back down).

## Anti-patterns

- **Scar tissue rules**: encoding a one-off into always-on instructions.
- **Vague morals** ("be more careful with tests") — if it cannot change a
  concrete next action, it is not a fix.
- **Fix-without-log**: the retro-log row is what lets future hygiene passes
  see why a rule exists; a rule with no traceable origin cannot be safely
  removed later.
