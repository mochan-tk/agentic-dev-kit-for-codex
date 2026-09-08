# Source-first local installer

This bounded implementation follows the owner-approved course correction in
[Epic #22](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/22#issuecomment-5589963251)
and [T14 plan](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/27#issuecomment-5590011621).
The behavioral source is `mochan-tk/agentic-dev-kit-for-copilot` at
`fd265ddef150fab86cd54d0e383c2c25fe297ffb`.

## Local use

Inspect the local source checkout first. Create an adopter Git repository
yourself if needed. Do not run concurrently with another writer in it.

```sh
bash .github/scripts/scaffold-init.sh --dry-run /path/to/adopter
bash .github/scripts/scaffold-init.sh --apply /path/to/adopter
```

The default is dry-run. `SCAFFOLD_SOURCE_DIR` optionally selects a local
checkout or distribution root containing `.github/distribution/`; relative
paths resolve before changing directories. There is no network source mode.
Windows uses `.github/scripts/scaffold-init.ps1 --dry-run TARGET` and
`--apply TARGET` through adjacent Git Bash. Bash 3.2+, Git, find, and either
sha256sum or shasum are needed; no Python package or Rulesync is required.
Drive-form source and target paths use Git Bash's existing `cygpath -u`;
missing or unsuccessful conversion fails rather than prepending the current
directory. This boundary is mocked in offline tests, not measured on Windows.

Review the plan before apply. Review the resulting Git diff, then stage,
commit, and push explicitly. Invoke `$project-onboarding` in Codex. Keep the
remote-default-before-GitHub-write, clean-checkout verify-by-running,
evidence-PR, and durable deferred-work ledger gates from the source workflow.
The installer itself runs none of the optional GitHub setup helpers.

Installed shell files retain mode 0644: invoke the documented helpers with
`bash`, or the existing PowerShell Git Bash entrypoint. The optional ritual
sensor binds Task-less bootstrap exceptions to complete trees at the PR's
exact base/head commits and an exact installed frontier-engine blob. It does
not depend on a changelog marker: existing adopter changelog, README and AGENTS
remain preserved. P0 records the adoption commit/tree; P6 links those records
and verifies actual CUSTOMIZE removal plus bounded onboarding-only outputs.
Initial adoption requires confirmed file absence, never a failed API read.
An unrelated or unsupported PR uses the ordinary Task ritual. These are
structural Git fixture checks, not proof of live GitHub or native Codex runtime.

## Exact payload and preservation

`payload.v1.tsv` records the closed 47-file payload, preservation class, and
SHA-256. `source-parity.v1.json` records each frozen source path/blob and its
target digest/adaptation. The trusted installer pins the exact path/class
layout and checks every source digest before planning. The required
`check-installer.py` independently validates the same inventory and provenance.

| Class | Existing identical file | Existing changed file |
| --- | --- | --- |
| engine: Skills, roles, templates, helpers, connectors, protocol reference | no-op | refuse the whole preflight plan |
| tuned: AGENTS and project instructions | no-op | preserve |
| instance: agreement/context seeds and local changelog | no-op | preserve |
| seed: README, gitignore, gitattributes | no-op | preserve |

Missing files are copied only by `--apply`. Unrelated adopter files are never
selected. Source/target/ancestor/leaf symlinks, broken links, path escapes,
unlisted payload files, missing inputs, modified inventory layouts, and file/
directory collisions fail closed. A failing inventory enumeration is not an
empty or successful inventory. Existing Git metadata and index are untouched.
No force, upgrade, overwrite, automatic init, stage, or commit is supported.
After preflight, a copy error can leave a reported partial install; review it
before re-running. This is not atomic rollback or an adversarial concurrent
filesystem mutation guarantee.

Eight Skills preserve source workflow semantics using `.agents/skills`.
Three source role prompts become `.codex/agents/*.toml` instructions without
model/permission overrides. Project coordination observes sibling Epics;
Epic -> Task -> Worker is intended delegation, not a fabricated Codex API.
Use a supported, capability-checked thread surface or a durable manual handoff.
`.github/instructions` are explicit references, not claimed Codex auto-preload.

Development-only Task IDs, accepted context pins, sole-active policy,
conformance stores, CI workflows, CODEOWNERS, private MCP configuration,
runtime adapters and Colima infrastructure are excluded. Optional connector
and GitHub helper procedures are not mandatory services or install actuators.
The installed frontier helper refuses unavailable/malformed dependency reads;
manual graph review is needed when the installed `gh` lacks `blockedBy`.
The MIT notice is included in the mandatory engine frontier helper, even if
an adopter's existing README is preserved; the adopter's LICENSE is not replaced.

## Source reuse, fixes, and intentional differences

The Bash installer reuses local-copy planning, preservation classes,
collision refusal, source hashes, and no-commit behavior. Necessary fixes are
source-root binding before target traversal, explicit payload/unsafe-path
refusal, checked enumeration, and complete planning before mutation. The
source frontier's suppressed GitHub failures are corrected to fail closed.

Codex-native adaptations are native Skill paths and role TOML, explicit
instruction reading, verified available tools/manual handoffs, and replacing
the Copilot app's Project-parent workaround. Source onboarding P0/P3/P6 gates,
ownership, chronology, escalation, and verification remain load-bearing.
The source-specific monthly platform baseline and cloud setup are explicitly
not installed. Adopter CI/setup commands must be observed and run locally.

Intentional convenience differences are local-source only, dry-run by default,
explicit apply, existing Git root, no network bootstrap, no automatic staging,
and no force/upgrade. PowerShell calls adjacent reviewed Bash rather than
downloading a moving main script. These limits avoid exporting kit development
governance as adopter truth while leaving upgrade design for its own Task.

## Evidence boundary

Disposable local adopter tests cover real copy/dry-run/preservation, rejection,
Git-state invariance, source/inventory drift, and fail-closed frontier behavior.
The shell suite checks entrypoint arguments and syntax; required CI also runs
the full deterministic test registry and pinned Linux lint tools. Source file
parity is not runtime evidence. Windows, named-agent selection, sibling-thread
control, clean-adopter live E2E, automatic upgrade/rollback, and full parity
remain unmeasured or incomplete. T12 stays paused and unaccepted; no VM is
needed for this installer or its tests.

Phase 2 and the repository remain incomplete. All 136 scenarios remain
`not-run`, release-level `results: []`, and `release_blocked=true` remain intact.
