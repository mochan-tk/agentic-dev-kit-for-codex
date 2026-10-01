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
contradictory records refuse. Ordinary read/write permission variation is
supported. Its bytes and identity are read back before output; mutation
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

The whole invocation is bounded to 120 seconds, 512 commands and 16 MiB of
combined transport output. Each command has a 20-second deadline and a
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
acquisition and cleanup retain ownership. An interrupted observation returns
non-success with fixed diagnostics; prior signal handlers are restored.

Exit status is 0 for a complete observation (including action required or
waiting), 1 for a global `UNCONFIRMED` observation, and 2 for invalid input or
an invalid previous report before network access. Diagnostics are fixed and
never disclose raw external text or private local paths. Synthetic fake-gh
and real local-file tests validate these boundaries; passing them is not
model/runtime, notification or live adopter qualification.
