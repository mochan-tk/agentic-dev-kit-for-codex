# Ongoing improvement companions

These optional companions run from a reviewed source checkout with Python
3.11+, Bash, and an already authenticated `gh` CLI. Optional official checkpoint
reads also require curl. They do not install anything, invoke a model, change
the 47-file payload, or activate a workflow. Run the Bash entrypoints explicitly;
do not source them. Select the exact repository and local target yourself.

```bash
bash .github/scripts/retro-hygiene.sh --repo OWNER/REPOSITORY --target /absolute/target
bash .github/scripts/retro-hygiene.sh --repo OWNER/REPOSITORY --target /absolute/target --platform
bash .github/scripts/feedback-triage.sh --repo OWNER/REPOSITORY --issue 123
```

The target must contain regular, non-symlink `AGENTS.md` and
`.github/codex-instructions.md`. Every path component must be non-symlink; use
the physical absolute path on hosts with temporary-directory aliases.
Target bytes and the Git index are preserved. No installed-version,
current-repository, scaffold-marker or source-template inference is performed.

Default invocations use only GitHub GET and print one fixed-field JSON result
after complete validation and final readbacks. They never print Issue titles,
bodies, comments, fetched page text, local paths or credentials. An empty
candidate ledger is `observed-empty`; unavailable, malformed, truncated,
excessive or changing observations produce no successful JSON. Exit 0 is a
completed observation or confirmed operation; exit 2 means `uncheckable` (or
`platform-unknown`); exit 3 means `submission-unconfirmed`. After exit 3, inspect
the exact target before another invocation: the write may already exist. There
is no automatic write retry.

## Report interpretation

The report reads open `retro:candidate` Issues, complete comments and final
Issue/list readbacks. Existing filings need an evidence link and context as
described by the installed retrospective Skill; no new field prefix is required.
An occurrence comment must start at byte zero with `Occurrence:`; its evidence
link may follow on a later line. Bare and Markdown links are recognized.
Quoted lines and fenced examples do not supply evidence. Ordinary discussion,
quoted markers and mid-body markers do not increment a signal.

Recognized evidence is a canonical github.com Issue, PR, Issue comment, PR
review/thread, Actions run/job or full-SHA commit link. Other hosts, unsupported
URL forms, missing evidence, or a marked occurrence without recognized evidence
are uncheckable, never silently counted as zero. Exact references are
deduplicated across filing and comments. Different references can describe one
incident: `independent_incidents` remains `unverified` for human review.

Age is whole UTC days since Issue creation. Inactivity is whole UTC days since
the latest Issue or comment update, including ordinary discussion. Two unique
references or 30 inactive days produce `human-review`; otherwise the status is
`watch`. These are advisory thresholds, not automatic promotion, retirement,
Task creation or incident confirmation. Missing/invalid timestamps refuse.
The period defaults to the current UTC month; `--period YYYY-MM` changes
grouping only. Every invocation observes current data, not a historical
snapshot or backdated measurement.

The always-on budget counts LF-delimited lines in each file separately,
including a final line without a newline. Up to 150 lines is `within-target`;
151 or more is `over-target`. About 150 lines per file is a source-derived
advisory target, not a new agreement, acceptance gate or deletion rule. Files
are bounded to 256 KiB; missing, special, hard-linked, symlink, oversized or
changing files refuse. Counts do not claim token usage or model attention.

## Official content checkpoint

`--platform` validates the closed
[baseline](../../.github/distribution/ongoing-improvement/platform-baseline.v1.json)
before reading only `https://learn.chatgpt.com/docs/changelog`. The earlier
developers.openai.com changelog redirects there; runtime redirects are refused.
The baseline records an anonymous HTML observation on 2026-09-22, SHA-256
`93031b9b56613d0a026d2aaee3218a410f8363431a7e50da0714e0f66ccd2f50`.
It is neither an installed Codex version nor a feature/model/runtime pin.

The result is `changed`, `unchanged`, or non-success `platform-unknown`.
Comparison is exact HTML content, so layout or unrelated ChatGPT changes may
alert. It cannot prove semantic feature availability or runtime parity. HTML
type/structure, HTTPS URL, response size, status and redirect restrictions are
checked; unknown never becomes unchanged. Raw remote content is never rendered.
Baselines are never rewritten. A baseline advance needs a reviewed change
explaining adopt, retire a local mechanism, watch, or not-relevant, plus human
relevance and applicable runtime review. No tool/model configuration follows.
`--baseline /absolute/reviewed-baseline.json` selects another reviewed record
with the same closed schema and exact official URL; credentials and arbitrary
hosts refuse.

## Explicit publication and routing

```bash
bash .github/scripts/retro-hygiene.sh --repo OWNER/REPOSITORY --target /absolute/target --publish
bash .github/scripts/feedback-triage.sh --repo OWNER/REPOSITORY --issue 123 --apply-label
```

`--publish` may create one Issue titled `Retro hygiene review YYYY-MM` with the
fixed report body and pre-existing `needs:human` label. It inspects all bounded
Issue/PR pages, including closed records, before final observation and POST.
An existing same-period report is a verified no-op only when exact identity,
schema, repository, period, content and required label match. Changed counts,
ages or checkpoints therefore require human review of the existing report;
there is no automatic overwrite. Conflicting same-period titles/markers refuse.
Prior periods do not count as the current report. POST requires exact Issue
readback. No labels are auto-created.

`--apply-label` may add only the existing `from:adopter` label to the exact
Issue. Signals are a byte-zero `<!-- adopter-feedback:v1 -->` body marker
followed by newline/end, or `[adopter-feedback]` title prefix followed by
space/end. An unknown version, quoted or mid-body helper marker prevents
positive classification even alongside a form-style title. Current content is
reread before the single label POST and verified after it. Already classified
Issues are verified no-ops. Tests use the unchanged failure reporter's actual
draft. Routing does not authenticate the sender, prove consent or a historical
execution, accept an agreement, or create Task/incident authority.

The [public form and pinned no-clone sender](feedback.md) are separate delivery
routes. The form accepts user-entered text with public-data warnings and an
explicit confirmation, while the reporter retains its closed eight fields.
Neither route activates this classifier, applies labels, or starts a workflow
or schedule. A recognized title is not consent or identity proof.

Finite readbacks are observations, not atomic snapshots or locks. Use a single
operator. Each request has a 20-second process bound (curl has 15 seconds);
each invocation has 120 seconds, 512 commands and 16 MiB aggregate output.
Responses allow 2 MiB plus 16 KiB framing; HTML itself allows 2 MiB. Pages have
50 records, at most 11 pages with a final short page, 500 Issues and 200 comments
per Issue. Any bound is non-success, not a partial report. Large repositories
may need a separately reviewed scope change before publication is usable.

## Inert workflow templates and later activation

The [retro template](../../.github/distribution/ongoing-improvement/retro-hygiene.yml)
and [feedback template](../../.github/distribution/ongoing-improvement/adopter-feedback.yml)
live outside `.github/workflows/`. Nothing copies or activates them. Manual
source-checkout use works without adding a workflow.

A later owner-reviewed activation chooses the destination, reviews templates
and companions, and configures `ONGOING_IMPROVEMENT_KIT_REVISION` to a reviewed
full 40-character commit of this public kit. Checkout Actions are pinned and
credentials are not persisted. Execution uses that trusted kit checkout;
target files and Issue numbers are data. No PR-head code or Issue body/title
enters shell source. Supply both always-on files, the pre-existing labels
needed by the selected operation, and the token permissions in the template.

The retro template requires `ONGOING_IMPROVEMENT_ENABLED=true` and manual
`workflow_dispatch`; platform and publication inputs default to false. There
is no installed or active monthly schedule. Adding a schedule or advancing the
kit revision is another reviewed owner action. The default report job has
`issues: read`; only the explicit publication job has `issues: write`.
Feedback activation requires
`FEEDBACK_TRIAGE_ENABLED=true`; after explicit activation it performs the fixed
label operation for opened Issues. Enable variables grant operation scope, not
authenticated identity or proof of reporter consent.

The existing adopter CI addon accepts a narrow workflow inventory. Adding
either workflow to an adopter with that guard requires its own owner-reviewed
transition. This batch does not expand that inventory or change setup. Merely
copying these templates into such an adopter can make its existing guard refuse.
Product CI and the installed payload are unchanged.

## Local verification

```bash
python3 -I -m unittest discover -s tests/conformance -p test_ongoing_improvement.py
python3 -I .github/scripts/check-product.py
python3 -I .github/scripts/check-installer.py
bash -n .github/scripts/retro-hygiene.sh .github/scripts/feedback-triage.sh
shellcheck .github/scripts/retro-hygiene.sh .github/scripts/feedback-triage.sh
actionlint .github/distribution/ongoing-improvement/retro-hygiene.yml .github/distribution/ongoing-improvement/adopter-feedback.yml
```

Tests execute actual Bash/Python/Git with small disposable targets and
argument-checking synthetic GitHub/HTTP processes, without live credentials or
live Issue operations. Results establish bounded local behavior, not live
rollout, client/runtime parity or release completion.
