# Maintainer mode

Maintainer mode lets contributors explicitly read the kit's canonical workflow
Skills and locate their resources without installing the kit into itself. Work
from the kit repository root. The repository's contributor instructions and the
current authorized work order govern changes; payload instructions describe the
workflow distributed to adopters, not a second contributor configuration.

## Why not self-install?

The installed layout and contributor layout intentionally differ. In particular,
root `AGENTS.md` and `README.md` are contributor/product documents; their payload
counterparts are adopter seeds. Installing over the kit can collide with existing
files and confuse which instructions apply. Copying Skills into a second root
`.agents/skills/` tree would create duplicate sources and ambiguous provenance.
Do not copy, symlink, tune or install payload files into the contributor layout
as a maintainer-mode setup step. Keep the 47 canonical files under
`.github/distribution/payload/` and use the map to find them.

## Start a session

1. Confirm the working directory is this kit's Git root. Read root `AGENTS.md`,
   `CONTRIBUTING.md`, `docs/product-scope.md`, `docs/provenance.md`, this guide,
   and the current Issue or PR in full. If the owner has explicitly scoped work
   to a local task specification with no Issue/PR publication, use that work
   order and record the boundary in local commits; do not create public records
   merely to enter maintainer mode.
2. Record the objective, acceptance criteria, verification, risks and owned
   files before implementation. Check existing changes and keep a single writer
   for each branch, worktree and overlapping scope. Contributor rules and the
   work order retain authority over uncustomized adopter examples.
3. Validate the checked-in map before using its paths:

   ```sh
   python3 .github/scripts/check-maintainer-map.py
   ```

4. Read the selected Skill explicitly as described below. Read linked resources
   as needed through the map. Loading a Skill does not execute its examples or
   authorize publishing, setup, Project writes, acceptance or merge.

## Use the path map

The machine-readable source of truth for translation is
[`maintainer-map.v1.json`](../.github/distribution/maintainer-map.v1.json).
Its schema is `maintainer-map/v1`. Each `files` entry contains:

- `installed_path`: a destination from `payload.v1.tsv`.
- `payload_path`: `.github/distribution/payload/` followed by that destination,
  relative to this kit's repository root.

The map is generated solely from
[`payload.v1.tsv`](../.github/distribution/payload.v1.tsv), never from a second
hand-maintained inventory. Its `source_sha256` binds the complete TSV bytes, so
even an inventory change that retains the destination set requires regeneration.
Both missing and extra installed paths fail validation. Every mapped payload
file must exist; an existing contributor file at the installed path is not a
substitute. A digest detects drift, not authority to change the product.

For example, resolve and read plan-management from the map:

```sh
python3 - <<'PY'
import json
from pathlib import Path

record = json.loads(Path('.github/distribution/maintainer-map.v1.json').read_text())
paths = {entry['installed_path']: entry['payload_path'] for entry in record['files']}
path = Path(paths['.agents/skills/plan-management/SKILL.md'])
print(f'Read the complete Skill at {path}:')
print(path.read_text())
PY
```

Have the session actually read the full output/file, including continuation
sections if its reader truncates output. Merely locating the file or reading
its frontmatter does not load the procedure. The expected frontmatter is
`name: plan-management`, followed by the `Plan Management` heading.

## Explicitly load the four core Skills

Ask the session to resolve the following installed path through the map and
read the complete resulting file. These are the current expected translations;
check the map instead of maintaining a second copy of any Skill.

| Skill | Installed path | Payload file to read |
| --- | --- | --- |
| plan-management | `.agents/skills/plan-management/SKILL.md` | [plan-management](../.github/distribution/payload/.agents/skills/plan-management/SKILL.md) |
| session-orchestration | `.agents/skills/session-orchestration/SKILL.md` | [session-orchestration](../.github/distribution/payload/.agents/skills/session-orchestration/SKILL.md) |
| verification | `.agents/skills/verification/SKILL.md` | [verification](../.github/distribution/payload/.agents/skills/verification/SKILL.md) |
| retro | `.agents/skills/retro/SKILL.md` | [retro](../.github/distribution/payload/.agents/skills/retro/SKILL.md) |

A session-start request can be:

> Use maintainer mode in this kit checkout. Read the contributor documents and
> current work order listed in docs/maintainer-mode.md. Validate the map, then
> explicitly resolve and read all of plan-management, session-orchestration,
> verification and retro using their installed paths in the table. Report the
> payload paths you read and follow the applicable procedures within the work
> order's scope. Do not self-install or execute setup/publication examples as
> part of loading. Keep contributor policy and human authority in force.

The same procedure works for the remaining Skills and the three role TOMLs.
For a Skill-relative reference such as `templates/task-body.md`, join it to
the installed parent `.agents/skills/plan-management/`, then look up the full
installed path. Sibling links such as `../verification/SKILL.md` use the same
rule: normalize `..` against the source file's installed parent without escaping
the installed root. A `#section` suffix identifies a section, not a different file.
Directory and wildcard references describe the corresponding mapped files;
they do not imply additional installed artifacts.

Payload citations such as `AGENTS.md §4` refer to the mapped payload seed for
understanding the distributed workflow. Root contributor `AGENTS.md` remains
the governing policy for work on this kit; do not substitute the seed for it.

## Translate script invocations

Translate only the installed executable/resource path via the map, keep the
working directory at the kit Git root, and preserve the reviewed arguments.
Invoke shell files with `bash`, since shipped shell files have mode 0644.
For example, the installed command:

```sh
bash .agents/skills/plan-management/scripts/frontier.sh --help
```

becomes this read-only help command after looking up that exact map entry:

```sh
bash .github/distribution/payload/.agents/skills/plan-management/scripts/frontier.sh --help
```

Likewise `.github/scripts/check-task-ritual.sh` maps to
`.github/distribution/payload/.github/scripts/check-task-ritual.sh`, and
`.github/codex-instructions.md` maps to the payload copy for reference reading.
Do not replace the root contributor rules with that uncustomized adopter file.

Mapping is static path resolution, not a runtime adapter: it does not rewrite
paths inside scripts, retarget Git tree lookups, remap their inputs/outputs, or
make adopter startup/tuning checks meaningful for this contributor checkout.
For example, `new-task.sh` locates its sibling ownership validator relative to
its source, while the ritual's PR checks inspect installed paths in Git trees.
Inspect the selected helper's requirements before any actual operation. Use
the contributor validation commands for kit verification. Setup, Issue/PR
publication and other writes still require the current work order's scope;
path existence alone is not evidence of runtime compatibility or permission.

## Checker coverage and limits

The checker uses Python's standard library without network access. It scans
all payload `.md`, `.sh`, `.toml` and `.yml` files, including hidden directories,
for installed `.github/`, `.agents/` and `.codex/` references. It also resolves
relative Markdown links and Skill `templates/` and `scripts/` resources. Files,
directories, globs (including recursive `**`) and brace lists resolve through
mapped entries. Unknown paths or substitutions fail with source, line,
reference and reason. This does not evaluate arbitrary shell expressions,
validate Markdown section anchors, or qualify execution of the helpers.

Each textual occurrence counts once, even when repeated or expanded into
multiple brace/glob targets; every expanded target must resolve. Success reports
the total, resolved and allowlisted counts separately. Exact source/reference
exceptions and reasons live in the checker: adopter intake examples, new ADR
and scoped-instruction placeholders, application CI/CODEOWNERS, the generated
source registry, and the explicitly excluded contributor test directory.
These exceptions are not additional map entries or permissions to create files.

Skill auto-discovery is not assumed in maintainer mode. Explicit loading is
required, retaining the installed workflow's explicit-load boundary. This cycle
does not automate maintainer setup for GitHub Projects or promise universal
client/runtime parity. The installer and existing checker validation logic stay
unchanged; the product checker's closed test inventory includes the new
conformance module. Run the new checker alongside the contributor checks.

## Maintain the map

After an authorized product change to `payload.v1.tsv`, regenerate the map in
the same change. Do not edit its entries by hand or alter the TSV to hide a
missing reference:

```sh
python3 .github/scripts/check-maintainer-map.py --write
python3 .github/scripts/check-maintainer-map.py
python3 .github/scripts/check-product.py
python3 .github/scripts/check-installer.py
umask 022
python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'
git diff --check
```

`--write` deterministically generates the map from the TSV and then validates
it; a failed validation still requires correction before the result is usable.
Review changes to the inventory, map, provenance and relevant tests under the
product-change rules. The map cannot authorize payload changes. Retain the
conformance suite's ordinary `022` umask, including on hosts defaulting to
`0007`, and complete the other local checks in `CONTRIBUTING.md`.
