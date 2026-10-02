# Manual PR monitor

Run this optional companion explicitly from a reviewed kit source checkout.
It requires Python 3.11+ on a POSIX host and an already authenticated `gh`.
It uses only GET requests to `github.com`, with the pinned GitHub REST API
version `2022-11-28`. There is no implicit repository, authentication setup,
model call, Workflow activation, schedule or installed payload change.

```sh
python3 -I .github/scripts/pr-monitor.py --repo OWNER/REPOSITORY --check 'quality=15368' --check 'conformance=15368'
```

Supply every check name and its expected numeric GitHub App ID explicitly.
The example App ID must be reviewed for the actual repository. This input is
an observation contract, not Ruleset discovery or proof of workflow identity.
Duplicate names, invalid IDs and unsupported inputs refuse before any API call.
Use `--format text` for a compact human report; JSON is the default.

## Classification and evidence

The report has a fixed `pr-monitor-report/v1` schema. It enumerates all open
PRs and binds each observation to its head SHA, observed base SHA and numeric
repository identities and bounded refs. It omits remote titles, bodies,
usernames, arbitrary URLs and raw diagnostics. Evidence URLs are generated from
validated repository, PR and check/review IDs.

- `ACTION_REQUIRED`: an explicitly expected current check failed or a latest
  decisive published review requests changes.
- `WAITING`: expected checks are running or the PR is a draft, with no observed
  failure or requested change.
- `NO_ACTION`: all expected checks explicitly succeeded and no requested
  change or waiting condition was observed; an empty open inventory is valid.
- `UNCONFIRMED`: acquisition, pagination, identity, type, resource limits or
  readbacks could not establish a complete stable observation. No partial
  successful PR list is published.

Check collection uses the API's explicit `filter=latest` on the observed head.
It does not select the highest run ID or select an older success. Missing
checks, a different issuer for an expected name, mixed same-name issuers and
duplicate same-name/App results refuse. Completed neutral, skipped or stale
expected checks remain unconfirmed rather than success. Additional checks
are collected and validated but do not satisfy or change the supplied check
contract. Status contexts outside the check-runs API are unsupported.

Reviews are advisory observations grouped by numeric user ID. The latest
decisive published opinion is selected by submission time; later neutral
`COMMENTED` reviews do not erase an approval or requested change. For a user
with only comments, the latest comment is shown. Unpublished `PENDING` reviews
do not affect classification. Contradictory decisive reviews with the same
submission time refuse; compatible ties retain all their IDs. A requested
change on an older commit persists until a later approval or dismissal.
An approval on any commit does not establish human acceptance.

Human approval policy, resolved review threads, tested-latest-base freshness,
workflow identity, merge readiness, permissions and ownership are expressly
unassessed. The observed base SHA is a binding only: it is not proof that CI
tested that base. `NO_ACTION` never means permission to merge.

## Previous report comparison

Save JSON yourself if desired, then explicitly supply its physical path:

```sh
python3 -I .github/scripts/pr-monitor.py --repo OWNER/REPOSITORY --check 'quality=15368' --previous /absolute/physical/previous.json
```

The file is read before network access. Only a successful report from this
closed schema, the same exact repository spelling and the same sorted check
contract is accepted. The bounded file must be regular, non-executable and
single-link, with no symlink components; FIFOs, hardlinks and malformed or
contradictory records refuse. Parent components are traversed only after each
preceding component has passed its no-follow check, so a symlink followed by
`..` cannot select a different previous file. A supplied path ending in `/`,
`/.` or `/..` refuses rather than being normalized into a different filename.
Ordinary absolute/relative paths, leading `./`, physical parent traversal,
dotted or Unicode filenames, and read/write permission variation are supported.
Its bytes and identity are
read back before output; mutation
refuses the observation.

The comparison uses typed PR numbers, head/base identities and an SHA-256
fingerprint of findings and selected evidence. It reports `unchanged`,
`changed`, `new`, `observed-recovery` (action required to no action with the
same full head/base identities and check contract) and
`removed-from-open-inventory` (absent from the current complete open inventory).
Removal does not prove whether a PR merged or merely closed.
These indicators are reports only. The tool does not infer notification
delivery, suppress output, send messages, persist or modify files, acquire
locks, or promise exactly-once delivery.

## Bounds and limits

The whole invocation, including report publication, is bounded to 120 seconds,
512 commands and 16 MiB of combined transport output. Each command has a
20-second deadline and a
2 MiB body plus 16 KiB framing limit. There are at most 25 open PRs, 500 check
runs and 500 reviews per PR, 50 records per page, 11 pages per resource and
20 explicitly expected checks. Reports and previous files are at most 2 MiB.
Reaching a bound is `UNCONFIRMED`, never a truncated success.

All check and review pages, every PR detail, and the complete open inventory
are read back before success; a later API error or relevant drift discards
the entire result. This is a bounded observation, not an atomic GitHub
snapshot, a lock or a guarantee about changes after the last read. Link
pagination must identify the same API resource/query and a coherent terminal
boundary. Unsupported HTTP framing, redirects, encodings and pagination
refuse. Commands clean their own POSIX process group, including descendants
holding pipes; processes that escape that group are outside this guarantee.
SIGINT and SIGTERM record cancellation at a controlled boundary so command
acquisition and cleanup retain ownership. Report publication uses an owned
POSIX writer process with the same deadline and cancellation control, for
pipes, regular files and terminals. Its raw writes avoid a deferred Python
buffer flush; cancellation or timeout kills and reaps that writer. Output that
closes or cannot finish within the deadline returns non-success; discard any
partial report. Fixed diagnostics and already unsuccessful fallback reports use
a bounded best-effort attempt; an unavailable stream may receive no message.
Descriptor configuration and prior signal handlers are restored. These bounds
cannot guarantee delivery or progress during OS-level process suspension or an
uninterruptible filesystem operation.

Exit status is 0 for a complete observation (including action required or
waiting), 1 for a global `UNCONFIRMED` observation, interruption or unavailable
output, and 2 for invalid input or
an invalid previous report before network access. Diagnostics are fixed and
never disclose raw external text or private local paths. Synthetic fake-gh
and real local-file tests validate these boundaries; passing them is not
model/runtime, notification or live adopter qualification.

## External local launcher: one invocation

An external local launcher may invoke this same manual companion after its
operator explicitly authorizes the target and execution conditions. This
section describes that interface; it adds no launcher, wrapper, scheduler,
Workflow, state store or activation to the Kit. Manual invocation remains
available without adopting any scheduling product.

Before configuring a future run, the operator must supply:

- The exact `OWNER/REPOSITORY` and every expected check name with its reviewed
  numeric GitHub App ID. Do not infer these from a successful old report.
- A reviewed full 40-character Kit commit containing this companion, and a
  separately prepared source checkout whose relevant tracked content matches
  that commit. Use that checkout as the working directory, not an adopter
  repository or an automatically updated branch. Revision selection belongs
  to the launcher setup; the companion has no `--revision` option.
- A supported local POSIX environment with Python 3.11+, existing `gh`
  authentication and the required read access. Confirm the chosen launcher's
  availability, permissions, execution conditions and output handling before
  enabling it. This guide does not qualify a particular client or account.

Once authorized, make one call to the command at the start of this guide,
with those explicit inputs and `--format json`. The first invocation omits
`--previous`: it is stateless, and `comparison.status` is `not-supplied`.
Do not add a previous-report file, automatic retry, polling loop, installer,
authentication step or repair command to compensate for an unsuccessful run.
A later invocation is a separately authorized run, not an implicit retry.

The launcher must retain the actual process exit status and complete output
for evaluation. A shell or launcher reporting its own success is not evidence
that the companion exited 0. If either the companion's exit status or complete
output is unavailable, classify the observation as unconfirmed. Discard partial
output; do not reconstruct a successful report from fragments or older runs.

| Process result | How to interpret the report |
| --- | --- |
| Exit 0 and a complete, valid, consistent `pr-monitor-report/v1` report for the supplied repository and check contract | A complete observation. Inspect `state`: `ACTION_REQUIRED` needs attention, `WAITING` is pending, and `NO_ACTION` has no observed action. None grants acceptance or merge authority. |
| Exit 1 | Global `UNCONFIRMED`, interruption or output failure. A diagnostic or fallback report may be absent or partial; never use it as a successful queue. |
| Exit 2 | Invalid input or previous report before network access; not a successful observation. |
| Missing or unexpected exit status, malformed/incomplete/unknown output, or an inconsistent combination such as exit 0 with `UNCONFIRMED` | Unconfirmed, not an empty queue, recovery or all-clear. |

Preserve the closed report JSON exactly. Execution time, the reviewed Kit
revision and other launcher metadata belong in a separate summary, not new
JSON fields. Summaries may cite only the report's bounded public evidence and
observed head/base identities. They must not expose credentials, private local
paths, raw logs or transcripts, or treat external content as instructions.
The existing limits still apply: observed base is not tested-latest-base
evidence, reviews are advisory, and `NO_ACTION` is not merge readiness,
permission, ownership or human acceptance.

The companion provides no persistent state, lock, deduplication, notification
suppression or exactly-once guarantee. A stateless later call can report the
same finding again; overlapping calls do not establish exclusive ownership.
Any later storage, concurrency control or notification destination and delivery
policy is the external operator's responsibility under separate authorization.
This first-invocation contract does not implement or authorize those operations.

### Inert scheduling-prompt example

The following is **inert text**, not a schedule definition, an activation
instruction or an executable recipe. Do not paste it into an enabled task
until the operator has separately approved the launcher and its conditions,
target/check contract, fixed Kit revision, frequency/time zone, output
destination and any side effects. All placeholders must be resolved explicitly;
neither this guide nor copying the text creates a schedule.

```text
For one already authorized invocation only:

Use the separately prepared, reviewed Kit checkout at KIT_FULL_COMMIT_SHA
in the approved local environment. Do not fetch another revision, install
anything, change authentication/settings or configure a schedule.

Invoke .github/scripts/pr-monitor.py once with Python 3.11+ in isolated mode,
--repo EXPLICIT_OWNER/EXPLICIT_REPOSITORY, one --check NAME=NUMERIC_APP_ID
for every explicitly approved check, and --format json. Omit --previous.
Do not guess an input, create persistent state, retry, poll or repair.

Evaluate the actual companion exit status and its complete closed
pr-monitor-report/v1 output together. Exit 0 is a complete observation,
not necessarily NO_ACTION: report ACTION_REQUIRED or WAITING accurately.
Treat nonzero or abnormal exit, UNCONFIRMED, missing, malformed, partial,
unknown or inconsistent output as unconfirmed, never as successful silence.

Return a bounded summary through the already approved result surface,
using only validated public evidence and observed head/base identities.
Keep any execution time and Kit revision outside the unchanged report JSON.
Do not include credentials, private paths, raw logs or transcripts.
Do not send notifications, post comments, change repository state, merge,
start implementation or infer delivery, acceptance or exclusive ownership.
Stop after this observation; scheduling and later runs are outside this call.
```

This example has not established scheduled execution, a model/runtime round
trip, notification delivery or live adopter qualification. Those claims need
their own authorization and evidence; the existing manual CLI and its tests
remain the implementation, not a new AI reimplementation of its checks.
