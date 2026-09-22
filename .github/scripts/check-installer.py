#!/usr/bin/env python3
"""Validate the closed adopter payload; no installation or external service."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

SOURCE_COMMIT = "fd265ddef150fab86cd54d0e383c2c25fe297ffb"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"
PARITY = ".github/distribution/source-parity.v1.json"
FRONTIER_PATHS = (".agents/skills/plan-management/scripts/frontier.sh", ".github/scripts/check-task-ritual.sh")
FRONTIER_TARGETS = tuple(PAYLOAD + "/" + path for path in FRONTIER_PATHS) + (
    "tests/conformance/test_frontier_cache.py", "docs/parity-status.md")
FRONTIER_BASELINE = "tests/fixtures/frontier-cache-baseline.json"
FRONTIER_BASELINE_SHA256 = "f3cf28b75db5b960bbed78697515690800ffb301cb13c1e1445ccada964587d6"
FRONTIER_DIGESTS = ('0f988399ca9f0d8a197964a8a5a5efec91bf1c1ccd18effb69544e3e238a7ca6', '319710322bbc97984bd6c5f17c81730cc4cbf400702f16b1f88a12ba5c8a33f7')
FRONTIER_CONTRACT = {
    "schema": "source-first-frontier-cache/v1",
    "source_repository": "mochan-tk/agentic-dev-kit-for-copilot",
    "source_commit": "446071c76f14f5fbda37a0eef1b6eafa0a3ab897",
    "source_files": {
        ".github/skills/plan-management/scripts/frontier.sh": "d3386d123e1b7ebff6d5df1822dcf8c012532369",
        ".github/scripts/tests/test-frontier.sh": "0ace3374ecd28c0db79105cbcfbeec6fae5cc337",
    },
    "product_base": "00b27d7b4ec5310d9a8890a885536b0a437a454d",
    "product_base_tree": "4ec7f4c168463abf1991d9b44b747ef2755f4718",
    "delivery": "47-fixed-paths-two-engine-adaptations-other-45-unchanged",
    "cache": "parent-shell-indexed-arrays-canonical-host-repository-issue-valid-OPEN-CLOSED-invocation-only",
    "evidence": "real-bash-jq-synthetic-github-disposable-install-upgrade-rollback",
    "limits": "no-atomic-snapshot-lock-live-request-performance-or-runtime-claim",
}
WORKFLOW_PAYLOAD_PATHS = (
    ".agents/skills/plan-management/SKILL.md", ".agents/skills/project-onboarding/SKILL.md",
    ".agents/skills/session-orchestration/SKILL.md", ".github/codex-instructions.md",
    ".github/scripts/check-task-ritual.sh", ".github/scripts/setup-ruleset.sh",
)
WORKFLOW_EXPORT_PATHS = tuple(sorted([PAYLOAD + "/" + name for name in WORKFLOW_PAYLOAD_PATHS] + [
    INVENTORY, ".github/scripts/governance-status.sh", "tests/conformance/test_source_first_governance.py",
]))
WORKFLOW_TARGETS = (*WORKFLOW_EXPORT_PATHS, "tests/conformance/test_installer.py", "tests/conformance/test_workflow_parity.py")
WORKFLOW_BASELINE = "tests/fixtures/workflow-parity-baseline.json"
WORKFLOW_BASELINE_SHA256 = "77a8ce370b7fbaec16e66bd69d9d4c391c6a0b8222276230f81dd95ed3607ad3"
WORKFLOW_CONTRACT = {
    "schema": "source-first-workflow-parity/v1",
    "source_repository": "mochan-tk/agentic-dev-kit-for-copilot",
    "source_commit": "446071c76f14f5fbda37a0eef1b6eafa0a3ab897",
    "source_files": {
        ".github/copilot-instructions.md": "4089b5c5e6ba81a31562b85b88c643c27967bc24",
        ".github/scripts/governance-status.sh": "05514a395f41a9bc0528c749df4ad72c91d110fa",
        ".github/scripts/setup-ruleset.sh": "8115b16cc2aa58a9fc8afe7ba94bddba1c0a9957",
        ".github/scripts/task-ritual-lib.sh": "02a72d70a980db0666f6e7c74f927737a07dcba2",
        ".github/scripts/task-ritual.sh": "9f6ce7b6cd11d55e8f0c9e3f10b913e872c4778b",
        ".github/skills/plan-management/SKILL.md": "e397470e9c069e6c0f54cacdc02a350bee97076e",
        ".github/skills/project-onboarding/SKILL.md": "d0ed839f95a90308e5f97aa3dca17b35f37b8685",
        ".github/skills/session-orchestration/SKILL.md": "e0c1ce5f0ccc6a8e4016f2a6d2bf9f8cc9b4b363",
    },
    "product_base": "abd7a4fba7ef5ff484efff625e2474cc32d6ef7b",
    "product_base_tree": "417aefd9caca78c76fac8040b069b70525750c7a",
    "delivery": "47-paths-six-explicit-payload-adaptations-installed-ritual-subcommands",
    "evidence": "real-bash-jq-disposable-git-synthetic-github;startup-and-disposition-document-contracts",
    "limits": "no-live-governance-worker-runtime-identity-lock-or-release-claim;separate-publication-authority",
}
GOVERNANCE_PROCEDURE_PATHS = (
    ".github/scripts/governance-status.sh", ".github/scripts/worktree-preflight.sh",
    "tests/conformance/test_source_first_governance.py", "tests/conformance/test_source_first_procedures.py",
    ".github/distribution/payload/.github/scripts/setup-ruleset.sh",
    ".github/distribution/payload/.agents/skills/session-orchestration/SKILL.md",
    ".github/distribution/payload/.agents/skills/retro/SKILL.md",
    ".github/distribution/payload/.agents/skills/project-onboarding/SKILL.md",
)
GOVERNANCE_PROCEDURE_CONTRACT = {
    "schema": "governance-worktree-retro-procedures/v1",
    "source_files": {
        ".github/scripts/governance-status.sh": "5011dd461523eb72916a930db58ae2d35d99fbf3",
        ".github/scripts/tests/test-governance-status.sh": "ce0bef43fcc3b53fd97f5ba6c5aea543d49aff1b",
        ".github/scripts/setup-ruleset.sh": "c36e2cf098cab29851d5da2eb0f340b0dd5f1940",
        ".github/scripts/tests/test-setup-ruleset.sh": "f9a33237d1a353083a1a1d7b9494aafd55f5424e",
        ".github/skills/session-orchestration/SKILL.md": "d50002b5a95fef18fb651cd4fe31b459593bedb0",
        ".github/skills/retro/SKILL.md": "e0f059e8b98d9692c4ae47d45c9da49a9ab711f3",
        ".github/skills/project-onboarding/SKILL.md": "20643ee9c8f5c3e0221db41e05b0abe3e1b22943",
    },
    "integration": "explicit-governance-and-worktree-companions-outside-47-payload;existing-retro-skill-blocks",
    "baseline_commit": "bb9a55973d2cbbe640472691d239f85ce8d59449",
    "baseline_tree": "05ec8c5ccfb711e104c656d05d1109c6e9ba28fe",
    "clauses": ["G-002", "G-003", "G-004", "G-005", "G-006", "G-007", "G-008", "G-009", "W-003", "W-004", "W-005", "P-007", "P-012"],
    "adaptations": [
        "Reuse source sensor aggregation, status/exit precedence and raw fixture semantics; require explicit repository, check contexts and source-template/adopter posture without assuming donor CI names.",
        "Validate bounded complete raw API pages, typed common App IDs and canonical existing rules before setup; legacy no-profile writes refuse and reviewed intent must persist before any ruleset write.",
        "Observe actual Git branch/worktree occupancy and declared claims read-only; detached push and conflicts refuse, archive always warns without treating local links as durable authority.",
        "Execute named candidate and retirement-diff blocks in the existing retro Skill; count distinct supporting occurrences and bind the requested retirement to the exact current blob/path/line and recorded decision.",
        "Execute installed onboarding consent/profile/new-or-canonical commands against the real helper; distinguish offline and GET-only previews and observe lawful actor-type-specific null IDs without approving bypass.",
    ],
    "limits": [
        "Companions are invoked from a reviewed kit checkout and are not installed or wired into adopter CI; exactly four payload contents change including onboarding, the other forty-three and all classes/Git modes remain unchanged.",
        "Real Bash/jq, synthetic GitHub and disposable Git tests are bounded evidence, not live governance changes, authenticated roles, actual owner approval, runtime learning or product/release acceptance.",
        "Conservative merge_group syntax recognition can return UNKNOWN for unsupported YAML; CODEOWNERS membership/coverage and occurrence independence still require human inspection.",
        "No push/delete/force/unlock/prune, process-stop, native archive or exclusive-lock guarantee; no automatic retirement application, scheduler, feedback delivery or upstream publication.",
    ],
    "evidence": "offline-real-bash-jq-raw-fake-github-real-disposable-git-and-extracted-skill-blocks",
}
RITUAL_PATHS = (".github/scripts/check-task-ritual.sh", ".agents/skills/verification/SKILL.md")
RITUAL_CONTRACT = {
    "schema": "ordinary-ritual-observation/v1",
    "source_files": {
        ".github/scripts/check-task-ritual.sh": "9365796d80e80e6ee1a94bc6e0cb08686682852c",
        ".github/scripts/tests/test-task-ritual.sh": "de5ae5b2265c8ae8c8aa406586259bf70d427551",
        ".github/scripts/tests/test-ritual-chronology.sh": "f4e7a5805d940ac00db3c2fafa29f27936a56f28",
        ".github/scripts/tests/test-ritual-linkage.sh": "478c514b3ce9245395baf3c8c3772ca7c2be041c",
        ".github/scripts/tests/lib.sh": "afa5384e9fde7f42f0551a3a6668c1d2e3e2a164",
        ".github/skills/verification/SKILL.md": "6d0916437bf490116cefaf71e234a6f1aa3eaf6a",
    },
    "commit_limit": 250,
    "timestamp_profile": "whole-second-utc-calendar",
    "adaptations": [
        "Bind ordinary PR, Task, complete comment membership and selected plan observations before/after the verdict; retain narrow bot/bootstrap and source execution/reference semantics.",
        "Consume all comment rows during exact plan membership matching so early grep exit cannot turn a valid long history into a pipefail mismatch; retain complete pages and final read-back.",
        "Require 1-250 unique typed commits including observed head, metadata count agreement and every valid selected date; preserve null/missing committer author fallback and equal-second chronology.",
        "Reach the installed mode-0644 sensor explicitly through Bash after PR creation; sensor observations do not replace CI/review/acceptance or authenticate chronology.",
    ],
    "evidence": "offline-installed-bash-real-jq-stateful-paginated-fake-gh-only",
}
TASK_SELECTION_PATHS = (
    ".agents/skills/plan-management/SKILL.md",
    ".agents/skills/plan-management/scripts/frontier.sh",
    ".github/scripts/ownership-overlap.sh",
    ".github/scripts/check-task-ritual.sh",
)
TASK_SELECTION_CONTRACT = {
    "schema": "task-selection-observation/v1",
    "accepted_commit": "d396865c0f5e23fa01bb790242835dda482d679d",
    "accepted_tree": "17cf82b1cc305b3263e8a84e18beecdea91c32e5",
    "source_files": {
        ".github/skills/plan-management/SKILL.md": "4c76ec1a95516358b038f915668e01eac7f126e5",
        ".github/skills/plan-management/scripts/frontier.sh": "af0905cb90626001c50c2937d35ba7ea5f9d077c",
        ".github/scripts/ownership-overlap.sh": "7ed866ebd4baaf5d73f2a3ebcb1dedb35638a52a",
        ".github/scripts/check-task-ritual.sh": "9365796d80e80e6ee1a94bc6e0cb08686682852c",
    },
    "adaptations": [
        "Refuse interior-dot and repeated-separator lexical ownership aliases before conservative prefix comparison; no filesystem alias or process-isolation claim.",
        "Normalize bare, repository-only and URL dependency identities to the selected host/repository/number before duplicate checks; preserve same-host cross-repository blockers and refuse unsupported foreign hosts without partial output.",
        "Derive fake GitHub creation and label state from actual argv and body-file bytes; verify unchanged production Task snapshot/readback with deliberate broken copies.",
        "Add only the exact current frontier blob to the ritual anchor allowlist; retain historical anchors, equal base/head anchors and complete exact-tree/readback guards.",
    ],
    "evidence": "offline-real-bash-disposable-adopters-stateful-fake-gh-only",
}
SOURCE_PREPARATION_PATH = ".github/scripts/setup-sources.sh"
SOURCE_PREPARATION_CONTRACT = {
    "schema": "source-registry-preparation/v1",
    "source_files": {".github/scripts/setup-sources.sh": "e60fe75c1fd47f5ca7ccfb8ae80f395162f196ff"},
    "integration": "explicit-existing-setup-sources-helper",
    "adaptations": [
        "Refuse unsafe repository-relative invocation ancestry and symlinked, obstructed or special registry paths before inspection or writing; no automatic repair or same-user race guarantee.",
        "Preserve regular create/append, exact-heading duplicate no-op, write-free dry-run, bytes/modes, original preflight and pending-activation semantics; resolve specs pin from repository root for nested invocation.",
        "Exercise installed registry-to-Task-to-unchanged-frontier flow only in stateful fake-GitHub fixtures; preparation proves neither activation nor context sufficiency nor dispatch authority.",
    ],
    "evidence": "offline-real-bash-disposable-adopters-and-stateful-fake-gh-only",
}
TASK_CREATION_PATHS = (
    ".agents/skills/plan-management/SKILL.md",
    ".agents/skills/plan-management/scripts/new-task.sh",
)
TASK_CREATION_CONTRACT = {
    "schema": "task-creation-readback/v1",
    "source_files": {
        ".github/skills/plan-management/SKILL.md": "4c76ec1a95516358b038f915668e01eac7f126e5",
        ".github/skills/plan-management/scripts/new-task.sh": "1156b004fd554b12cdccf55bc5b62a98e3a82bda",
    },
    "cli_source": "cli/cli@b300f2ec7ec9dc9addc39b2ad88c54097ded7ca0",
    "cli_version": "2.96.0",
    "strategy": "single-create-without-ready-verify-graph-optional-ready-verify-again",
    "adaptations": [
        "Retain source parent/blocker create flags and ready ownership validation; remove initial ai:ready because deferred linking is not atomic.",
        "Bind repository and issue URLs, exact body/title, typed complete parent/blockers and labels before readiness, then verify the same identity and graph again.",
        "Preserve uncertain write outcomes without automatic retry, deletion or repair; ai:ready means a complete brief, not closed blockers.",
        "Bound and snapshot inputs; use real CLI export shapes with at most 50 complete blockers and fewer than 100 labels; keep private scratch data out of diagnostics.",
    ],
    "evidence": "offline-real-bash-fake-gh-and-disposable-adopters-only",
}
KICKOFF_PATHS = (
    ".agents/skills/context-collection/SKILL.md",
    ".github/connectors/builtin.md",
    "README.md",
)
KICKOFF_CONTRACT = {
    "schema": "builtin-context-kickoff/v1",
    "source_files": {
        ".github/prompts/kickoff-context.prompt.md": "9b565657def003a3c04cfd9ec6e67578ff7d2906",
        ".github/skills/context-collection/SKILL.md": "cead6452f8a7015ef2070596bde26da3e2ae2cfd",
        ".github/connectors/builtin.md": "3bf19026be22f7d167f9c26d82410c4b9b9ca022",
        "README.md": "76480f3ae0458926d854e62f51d10958ff229bd3",
    },
    "prompt_sha256": "f11922e1f96ccf5f9e827a77db1f06455f05991d63c20b0ef95fc2ce8b46228c",
    "integration": "explicit-route-in-existing-context-collection-skill",
    "adaptations": [
        "Reuse frozen kickoff routing into builtin.retrieve and collection; retain the existing normative builtin procedure and ordinary collection path.",
        "Replace Copilot prompt aliases and topic interpolation with explicit installed Skill/resource guidance and a chosen topic; no ninth Skill or implicit preload.",
        "Preserve iterative candidate drafts, bounded questions, human stop, provenance, redaction and the human-reviewed distillation promotion gate.",
        "Document optional registry preparation separately from reviewed activation and sufficiency; preserve existing adopter README and tuned files.",
    ],
    "evidence": "offline-installed-instructions-and-disposable-bash-fixtures-only",
}
FEEDBACK_PATHS = (
    ".github/scripts/feedback-lib.sh",
    ".github/scripts/report-installer-failure.sh",
    "tests/conformance/test_installer_feedback.py",
)
FEEDBACK_SOURCES = {
    ".github/scripts/feedback-lib.sh": "b09747ae0bc8ffa2183fec48b578b97cdb45c67b",
    ".github/scripts/tests/test-feedback-lib.sh": "fce1632234b8e9f64ab374130cb39c667eafb7b5",
    ".github/scripts/scaffold-init.sh": "7236d06b901da97c2a1a37fd4a51f6fbd89a75d1",
    "docs/agreements/adr/ADR-0002-consent-gated-adopter-feedback.md": "65c4c20ee9fd2c91d0738a38fa8558be8761dc42",
    "docs/context/feedback-loop/privacy-posture.md": "d417b2c7114913aaea80b03014f3c5f7e5458fe8",
}
FEEDBACK_FIELDS = ["Script", "Failing line", "Exit code", "OS / arch", "bash version",
                   "gh version", "jq version", "Scaffold version"]
FEEDBACK_ADAPTATIONS = [
    "Reuse source bounded fields, TTY/CI gates, preview-before-consent and one create attempt; standalone opt-in replaces automatic ERR/EXIT integration.",
    "Fixed public github.com recipient replaces adopter changelog routing; Scaffold version is unknown and caller failure metadata is user-reported, not historical proof.",
    "Draft requires no gh/account; no auth, labels, retry or receiving workflow. Failed/lost/invalid create response is submission-unconfirmed, never confirmed absence.",
    "Narrow version/system grammars and bounded tool-output capture reject unsafe observations; actual Bash/fake-gh/PTY tests replace the source TTY override seam.",
    "Literal terminal consent and tool-output limits preserve byte distinctions before Bash string normalization.",
]
CONNECTOR_PATHS = (
    ".github/scripts/check-connectors.sh",
    "tests/conformance/test_connector_validation.py",
)
CONNECTOR_CONTRACT = {
    "schema": "connector-validation-companion/v1",
    "source_files": {
        ".github/scripts/check-connectors.sh": "8a598ab8fd5b54f0fe48b5daf3dc91abc86cadf9",
        ".github/scripts/tests/test-connectors.sh": "ee17fa9a52d9e0b5cef3428360f0407a8cda59a1",
    },
    "integration": "explicit-target-read-only-outside-payload",
    "fields": ["name", "access", "reach", "trust-default", "status"],
    "operations": ["discover", "retrieve", "pin", "verify"],
    "statuses": ["core", "community", "experimental"],
    "adaptations": [
        "Reuse source err/check_connector, framework checks, Metadata extraction, field/heading grammar and twelve fixture cases; payload builtin/speckit supplies separate smoke evidence.",
        "Require an explicit existing target; reject empty names, symlink/non-regular inputs, failed enumeration/reads and NUL before Bash normalization; include hidden Markdown definitions.",
        "Limit each input to 1 MiB, definitions to 128 and itemized diagnostics to 32; publish fixed field/role labels instead of filenames or raw values.",
        "Standalone Bash companion is not installed or automatically wired into adopter CI; no Git, network, auth, model, activation, auto-fix or writes.",
        "Trusted local tools and no concurrent writer; no hostile namespace-race guarantee, full Markdown parser, content sufficiency, pin authenticity, reachability or runtime proof.",
    ],
    "evidence": "offline-real-bash-disposable-fixtures-only",
}
INSTALLER_LIMITS = [
    "Local-source explicit install/known-old upgrade and operation-scoped rollback; no auto download/init/stage/commit/force.",
    "Source class dispatch and two-version preservation tests are reused; old-byte/mode checks, prewrite backups and explicit rollback are Codex-target safety adaptations, not source-provided transactions.",
    "Rollback preserves unrelated edits and refuses changed affected files; exclusive-writer local fixtures do not prove power-loss atomicity or malicious same-user race resistance.",
    "No live Codex, Windows or GitHub-helper execution proof; no VM prerequisite.",
    "Development-only AGENTS/PIN/Task IDs/governance/results are excluded.",
]
EXPECTED = {
    ".agents/skills/context-collection/SKILL.md": [
        ".github/skills/context-collection/SKILL.md",
        "cead6452f8a7015ef2070596bde26da3e2ae2cfd"
    ],
    ".agents/skills/context-distillation/SKILL.md": [
        ".github/skills/context-distillation/SKILL.md",
        "4f2e57a7f613cdadb7c7d76306c3a04458ca7b08"
    ],
    ".agents/skills/plan-management/SKILL.md": [
        ".github/skills/plan-management/SKILL.md",
        "4c76ec1a95516358b038f915668e01eac7f126e5"
    ],
    ".agents/skills/plan-management/scripts/frontier.sh": [
        ".github/skills/plan-management/scripts/frontier.sh",
        "af0905cb90626001c50c2937d35ba7ea5f9d077c"
    ],
    ".agents/skills/plan-management/scripts/new-task.sh": [
        ".github/skills/plan-management/scripts/new-task.sh",
        "1156b004fd554b12cdccf55bc5b62a98e3a82bda"
    ],
    ".agents/skills/plan-management/templates/epic-body.md": [
        ".github/skills/plan-management/templates/epic-body.md",
        "b01a35256b48f1c1e1c31c4d1e35822767bd5551"
    ],
    ".agents/skills/plan-management/templates/task-body.md": [
        ".github/skills/plan-management/templates/task-body.md",
        "2338d2e79db0afad54e498d5582b80ad63fa198f"
    ],
    ".agents/skills/project-onboarding/SKILL.md": [
        ".github/skills/project-onboarding/SKILL.md",
        "20643ee9c8f5c3e0221db41e05b0abe3e1b22943"
    ],
    ".agents/skills/retro/SKILL.md": [
        ".github/skills/retro/SKILL.md",
        "e0f059e8b98d9692c4ae47d45c9da49a9ab711f3"
    ],
    ".agents/skills/session-orchestration/SKILL.md": [
        ".github/skills/session-orchestration/SKILL.md",
        "d50002b5a95fef18fb651cd4fe31b459593bedb0"
    ],
    ".agents/skills/task-routing/SKILL.md": [
        ".github/skills/task-routing/SKILL.md",
        "30a6b0123f82b15f6379a4b1e62f5c6d30c7e984"
    ],
    ".agents/skills/verification/SKILL.md": [
        ".github/skills/verification/SKILL.md",
        "6d0916437bf490116cefaf71e234a6f1aa3eaf6a"
    ],
    ".codex/agents/orchestrator.toml": [
        ".github/agents/orchestrator.agent.md",
        "5574a1422f53651330a204dce08dce49ea4c1f59"
    ],
    ".codex/agents/planner.toml": [
        ".github/agents/planner.agent.md",
        "7227835f359f3383cd2ddbc47ffb69e5e1ce867e"
    ],
    ".codex/agents/reviewer.toml": [
        ".github/agents/reviewer.agent.md",
        "36901b4a8835ebe8f0989994bf3847bcd2809beb"
    ],
    ".gitattributes": [
        ".gitattributes",
        "beda7eb8fb0d073281b23f758094da7348e92ee8"
    ],
    ".github/ISSUE_TEMPLATE/ai-task.yml": [
        ".github/ISSUE_TEMPLATE/ai-task.yml",
        "f8d70b3d44f53de307d88284f192da79cdf45fdd"
    ],
    ".github/ISSUE_TEMPLATE/config.yml": [
        ".github/ISSUE_TEMPLATE/config.yml",
        "a3649e71ac42fee71010da2292893c900536e650"
    ],
    ".github/ISSUE_TEMPLATE/epic.yml": [
        ".github/ISSUE_TEMPLATE/epic.yml",
        "2fd09aceddf192a2d2c1816dcdc2a25873340da4"
    ],
    ".github/PULL_REQUEST_TEMPLATE.md": [
        ".github/PULL_REQUEST_TEMPLATE.md",
        "145a05bbc0050c215b397e7d7c029507c7f065fa"
    ],
    ".github/codex-instructions.md": [
        ".github/copilot-instructions.md",
        "c2ec9fb4c156b5139b7d88624593216c69a800f0"
    ],
    ".github/connectors/CONNECTOR-TEMPLATE.md": [
        ".github/connectors/CONNECTOR-TEMPLATE.md",
        "997e2dc5825d2cabeafbbbe01ab997ae86b958d4"
    ],
    ".github/connectors/README.md": [
        ".github/connectors/README.md",
        "386639f24f8323ce92bed53c5ea6518bc50c2dc5"
    ],
    ".github/connectors/builtin.md": [
        ".github/connectors/builtin.md",
        "3bf19026be22f7d167f9c26d82410c4b9b9ca022"
    ],
    ".github/connectors/speckit.md": [
        ".github/connectors/speckit.md",
        "441b1c8e639813a49dcc200ae4c1c2b018f91a5a"
    ],
    ".github/docs/agreements/README.md": [
        ".github/docs/agreements/README.md",
        "413054a2fb8f80406c62491fdb558efa302c43f0"
    ],
    ".github/docs/agreements/adr/ADR-0000-template.md": [
        ".github/docs/agreements/adr/ADR-0000-template.md",
        "269f127a929cf24e2f9979c189a725b2683bb80d"
    ],
    ".github/docs/agreements/glossary.md": [
        ".github/docs/agreements/glossary.md",
        "cc5336086dd24145067be37c4282288cd2fa8709"
    ],
    ".github/docs/agreements/non-goals.md": [
        ".github/docs/agreements/non-goals.md",
        "abd4ca28ba184f6aa5173b383afab873038577f0"
    ],
    ".github/docs/agreements/requirements.md": [
        ".github/docs/agreements/requirements.md",
        "f68e5804e54c7e71ce65775794685bab70270676"
    ],
    ".github/docs/agreements/retro-log.md": [
        ".github/docs/agreements/retro-log.md",
        "f401f268702fd21efeb8db85e7b380ef69f3de5d"
    ],
    ".github/docs/context/README.md": [
        ".github/docs/context/README.md",
        "3b915dda3cd9968757c90d8d3a03f11e6378e0b6"
    ],
    ".github/instructions/code-review.instructions.md": [
        ".github/instructions/code-review.instructions.md",
        "1336728a7d8f72520bec2b97a2ed25568e17d0b3"
    ],
    ".github/instructions/docs.instructions.md": [
        ".github/instructions/docs.instructions.md",
        "68ff889b87df96282cdb014f1ee88a1922dfc072"
    ],
    ".github/scripts/check-task-ritual.sh": [
        ".github/scripts/check-task-ritual.sh",
        "9365796d80e80e6ee1a94bc6e0cb08686682852c"
    ],
    ".github/scripts/ownership-overlap.sh": [
        ".github/scripts/ownership-overlap.sh",
        "7ed866ebd4baaf5d73f2a3ebcb1dedb35638a52a"
    ],
    ".github/scripts/run.ps1": [
        ".github/scripts/run.ps1",
        "269b798e1d163b0832a3036114c9550684a1aa76"
    ],
    ".github/scripts/setup-labels.sh": [
        ".github/scripts/setup-labels.sh",
        "f76b67dcbe9563cfb61bd56451f7c51a68f8afca"
    ],
    ".github/scripts/setup-project.sh": [
        ".github/scripts/setup-project.sh",
        "4dd5b61186b8488e5e8fff143e5b40d3958087ca"
    ],
    ".github/scripts/setup-ruleset.sh": [
        ".github/scripts/setup-ruleset.sh",
        "c36e2cf098cab29851d5da2eb0f340b0dd5f1940"
    ],
    ".github/scripts/setup-sources.sh": [
        ".github/scripts/setup-sources.sh",
        "e60fe75c1fd47f5ca7ccfb8ae80f395162f196ff"
    ],
    ".github/scripts/tuning-status.sh": [
        ".github/scripts/tuning-status.sh",
        "1b764f3bd67e897e64c11c98503e5750d73746dd"
    ],
    ".gitignore": [
        ".gitignore",
        "8b8c60b83d8d879d40b0c803931a1d68d76ab742"
    ],
    "AGENTS.md": [
        "AGENTS.md",
        "d575018d2d456c9376144495467cfcf8ac498b96"
    ],
    "README.md": [
        "README.md",
        "76480f3ae0458926d854e62f51d10958ff229bd3"
    ],
    "SCAFFOLD-CHANGELOG.md": [
        "SCAFFOLD-CHANGELOG.md",
        "c0898a331200d0a332c5c4423fefc9017531a95f"
    ],
    "docs/agreements/adr/ADR-0003-two-tier-task-execution.md": [
        "docs/agreements/adr/ADR-0003-two-tier-task-execution.md",
        "f07906ce7eea7dc45b04cbdd1b739557ec018df8"
    ]
}

def preservation_class(name):
    if name in {"README.md", ".gitignore", ".gitattributes"}:
        return "seed"
    if name == "SCAFFOLD-CHANGELOG.md" or name.startswith(".github/docs/"):
        return "instance"
    if name in {"AGENTS.md", ".github/codex-instructions.md"} or name.startswith(".github/instructions/"):
        return "tuned"
    return "engine"

def layout_bytes():
    return "".join(name + "\t" + preservation_class(name) + "\n" for name in sorted(EXPECTED)).encode()

def regular_bytes(root, name):
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symlink")
    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
        raise ValueError("not bounded regular file")
    with path.open("rb") as handle:
        data = handle.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("input too large")
    return data

def validate_context_kickoff(payload_data, parity):
    """Guard reviewed instruction boundaries, not model adherence or sufficiency."""
    errors = []
    record = parity.get("context_kickoff")
    if not isinstance(record, dict) or set(record) != set(KICKOFF_CONTRACT) | {"target_files"}:
        errors.append("kickoff provenance fields are missing or unreviewed")
    elif any(record.get(key) != value for key, value in KICKOFF_CONTRACT.items()):
        errors.append("kickoff source/routing/evidence contract drifted")
    targets = record.get("target_files") if isinstance(record, dict) else None
    if (not isinstance(targets, list) or any(not isinstance(item, dict) for item in targets)
            or [item.get("path") for item in targets] != list(KICKOFF_PATHS)):
        errors.append("kickoff target inventory drifted")
    else:
        for item in targets:
            if (set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644"
                    or item.get("sha256") != hashlib.sha256(payload_data[item["path"]]).hexdigest()):
                errors.append("kickoff target digest/mode/fields drifted")

    # These selected source-derived phrases are reviewed static guard anchors.
    # They reject accidental routing/promotion regressions even after rehashing;
    # they are not a general natural-language safety or Markdown validator.
    required = {
        KICKOFF_PATHS[0]: ("routing", (
            "For ordinary collection or an existing source", "Only for explicit builtin kickoff",
            "`builtin.retrieve`", "builtin.md#retrieve)",
            "read the builtin procedure only when this route is selected",
            "never present a generated candidate as a source fact",
            "Do not write to `.github/docs/agreements/` during kickoff",
            "human-reviewed PR gate",
        )),
        KICKOFF_PATHS[1]: ("boundary", (
            "provenance headers", "sensitivity marking", "redaction first",
            "EARS form", "`REQ-C##`", "[NEEDS CLARIFICATION]", "**Assumptions**",
            "3–5 questions per round", "one at a time", "dated Q&A file",
            "Repeat the draft and question rounds", "human says stop",
            "Do not write to `.github/docs/agreements/`", "promotion-worthy candidates and why",
            "human-reviewed distillation PR",
        )),
        KICKOFF_PATHS[2]: ("boundary", (
            "Registry preparation is not activation or context sufficiency",
            "Activation requires the agreements PR and human review",
            "Do not write to `.github/docs/agreements/` during kickoff",
            "human-reviewed distillation PR",
        )),
    }
    for name, (reason, fragments) in required.items():
        text = payload_data[name].decode("utf-8")
        normalized = " ".join(text.split())
        if any(fragment not in normalized for fragment in fragments) or "/kickoff-context" in text:
            errors.append("kickoff " + reason + " instructions drifted: " + name)
        for reference in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            target, _, anchor = reference.partition("#")
            parts = list(PurePosixPath(name).parent.parts)
            safe = bool(target) and not target.startswith("/") and ":" not in target
            for part in target.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                    else:
                        safe = False
                elif part not in {"", "."}:
                    parts.append(part)
            destination = "/".join(parts)
            if (not safe or destination not in payload_data
                    or (anchor and "## " + anchor not in payload_data[destination].decode().splitlines())):
                errors.append("kickoff dangling installed resource: " + name)
    return errors

def validate_task_creation(payload_data, parity):
    """Pin the bounded helper adaptation; actual Bash fixtures test behavior."""
    errors = []
    record = parity.get("task_creation")
    if not isinstance(record, dict) or set(record) != set(TASK_CREATION_CONTRACT) | {"target_files"}:
        return ["task creation provenance fields are missing or unreviewed"]
    if any(record.get(key) != value for key, value in TASK_CREATION_CONTRACT.items()):
        errors.append("task creation source/readback/evidence contract drifted")
    targets = record.get("target_files")
    if (not isinstance(targets, list) or any(not isinstance(item, dict) for item in targets)
            or [item.get("path") for item in targets] != list(TASK_CREATION_PATHS)):
        return errors + ["task creation target inventory drifted"]
    for item in targets:
        if (set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644"
                or item.get("sha256") != hashlib.sha256(payload_data[item["path"]]).hexdigest()):
            errors.append("task creation target digest/mode/fields drifted")
    script = payload_data[TASK_CREATION_PATHS[1]].decode()
    if (script.count("gh issue create") != 1 or '--label "type:task,exec:$EXEC" --parent "$PARENT"' not in script
            or '"$DEPS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$' not in script
            or 'read_back false || unconfirmed "Task read-back"' not in script
            or 'read_back true || unconfirmed "Task readiness read-back"' not in script):
        errors.append("task creation single-create/readiness guard drifted")
    skill = payload_data[TASK_CREATION_PATHS[0]].decode()
    if "dependencies atomically" in skill or 'exec:cloud,ai:ready"' in skill or "One CLI call is not atomic" not in skill:
        errors.append("task creation Skill atomicity/readiness boundary drifted")
    return errors

def validate_source_preparation(payload_data, parity):
    record = parity.get("source_preparation")
    if not isinstance(record, dict) or set(record) != set(SOURCE_PREPARATION_CONTRACT) | {"target_files"}:
        return ["source preparation provenance fields are missing or unreviewed"]
    errors = []
    if any(record.get(key) != value for key, value in SOURCE_PREPARATION_CONTRACT.items()):
        errors.append("source preparation source/behavior/evidence contract drifted")
    expected = [{"path": SOURCE_PREPARATION_PATH, "mode": "100644",
                 "sha256": hashlib.sha256(payload_data[SOURCE_PREPARATION_PATH]).hexdigest()}]
    if record.get("target_files") != expected:
        errors.append("source preparation target digest/mode/fields drifted")
    script = payload_data[SOURCE_PREPARATION_PATH].decode()
    if 'if (.private | type) == "boolean" then .private else error("uncheckable repository visibility") end' not in script:
        errors.append("source preparation typed visibility guard drifted")
    if (script.count("\ncheck_registry_path\n") != 3
            or any(value not in script for value in ('[ -L "$path" ]', '[ -L "$REGISTRY" ]',
                   '[ ! -L "$LOGICAL_ROOT" ]', '[ ! -L "$INVOCATION" ]',
                   'status: pending-activation', 'git -C "$REPO_ROOT" log'))):
        errors.append("source preparation path/pending-activation guard drifted")
    return errors

def validate_task_selection(payload_data, parity):
    record = parity.get("task_selection")
    if not isinstance(record, dict) or set(record) != set(TASK_SELECTION_CONTRACT) | {"target_files"}:
        return ["task selection provenance fields are missing or unreviewed"]
    errors = []
    if any(record.get(key) != value for key, value in TASK_SELECTION_CONTRACT.items()):
        errors.append("task selection source/observation/evidence contract drifted")
    expected = [{"path": name, "mode": "100644", "sha256":
                 "7f23226c2edd0e2e5c943fa19a0b2f575e3d72e42aed9a02700d0ba091f128b9"
                 if name == ".github/scripts/check-task-ritual.sh" else hashlib.sha256(payload_data[name]).hexdigest()}
                for name in TASK_SELECTION_PATHS]
    if record.get("target_files") != expected:
        errors.append("task selection target digest/mode/fields drifted")
    frontier = payload_data[TASK_SELECTION_PATHS[1]]
    blob = hashlib.sha1(b"blob " + str(len(frontier)).encode() + b"\0" + frontier).hexdigest()
    ritual = payload_data[TASK_SELECTION_PATHS[3]].decode()
    anchor = ritual.split("reviewed_adoption_anchor() {", 1)[-1].split("\n}", 1)[0]
    matches = re.findall(r"100644\\tblob\\t([0-9a-f]{40})", anchor)
    if (matches != ["f66d3aa5e73abf24052c70f557cd6df9177ca012", "cc888c829bc5957871376004cb59a93b4980b50f",
                    "5017ee6979eec83c867a2da02118e6b03205040c", blob]
            or '*) return 1 ;;' not in anchor
            or '[[ "$base_anchor" == "$head_anchor" ]] || return 1' not in ritual):
        errors.append("task selection exact ritual anchor compatibility drifted")
    ownership = payload_data[TASK_SELECTION_PATHS[2]].decode()
    if '.|./*|*/.|*/./*|*//*) invalid=1; continue ;;' not in ownership:
        errors.append("task selection lexical alias refusal drifted")
    if any(value not in frontier.decode() for value in (
            '($url.host | ascii_downcase) == $host', '($repo // $selected)',
            'unique_by([.[0], (.[1] | ascii_downcase)])')):
        errors.append("task selection normalized identity guard drifted")
    return errors

def validate_ritual_verification(payload_data, parity):
    record = parity.get("ritual_verification")
    if not isinstance(record, dict) or set(record) != set(RITUAL_CONTRACT) | {"target_files"}:
        return ["ordinary ritual provenance fields are missing or unreviewed"]
    errors = []
    if any(record.get(key) != value for key, value in RITUAL_CONTRACT.items()):
        errors.append("ordinary ritual source/observation/evidence contract drifted")
    expected = [{"path": name, "mode": "100644", "sha256": hashlib.sha256(payload_data[name]).hexdigest()}
                for name in RITUAL_PATHS]
    if record.get("target_files") != expected:
        errors.append("ordinary ritual target digest/mode/fields drifted")
    helper = payload_data[RITUAL_PATHS[0]].decode()
    required = ('for attempt in 1 2 3;', 'length == 40', 'length != 40',
                'selected_repo=$(api "repos/{owner}/{repo}"', 'observation_fail repository-identity',
                'valid_timestamp "$timestamp" || observation_fail commit-date',
                'valid_timestamp "$created" && valid_timestamp "$updated"',
                'commit_count <= 250', '"$actual_commits" == "$commit_count"',
                '"$unique_commits" == "$commit_count"', 'grep -Fxq "$observed_head"',
                '.commit.committer.date == null', 'if ! has_marker CLAIM;',
                'if has_marker DISPATCH;', 'elif has_marker EXEMPT;',
                '"$actual_comments" == "$comment_count"', '"$unique_comments" == "$comment_count"',
                "exact_line_membership()",
                "awk 'NR == 1 { wanted = $0; next } $0 == wanted { found = 1 } END { exit !found }'",
                "printf '%s\\n' \"${plan_snapshot%$'\\t'*}\"",
                '} | exact_line_membership; then',
                '"$final_pr" == "$pr_snapshot"', '"$final_task" == "$task_snapshot"',
                '"$final_comments" == "$comment_snapshot"', '"$final_plan" == "$plan_snapshot"')
    if any(token not in helper for token in required):
        errors.append("ordinary ritual completeness/date/snapshot guard drifted")
    skill = payload_data[RITUAL_PATHS[1]].decode()
    if any(token not in skill for token in ('bash .github/scripts/check-task-ritual.sh 123',
            'After PR creation, before ready-for-review', 'not atomic', 'owner acceptance')):
        errors.append("ordinary ritual installed sensor handoff drifted")
    return errors

def reject_duplicate_json_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate provenance key")
        value[key] = item
    return value


def validate(root):
    errors = []
    root = Path(root)
    try:
        if root.is_symlink():
            raise ValueError("root symlink")
        inventory = regular_bytes(root, INVENTORY).decode()
        rows = [line.split("\t") for line in inventory.splitlines() if line and not line.startswith("#")]
        names = [row[0] for row in rows]
        if names != sorted(EXPECTED) or any(len(row) != 3 for row in rows):
            return ["installer inventory paths/order/columns differ from the exact reviewed set"]
        actual = {str(p.relative_to(root / PAYLOAD)) for p in (root / PAYLOAD).rglob("*") if not p.is_dir() or p.is_symlink()}
        if actual != set(EXPECTED):
            errors.append("installer payload has missing, extra or symlink entries")
        payload_data = {}
        for name, kind, digest in rows:
            if kind != preservation_class(name) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                errors.append("installer inventory class/digest is invalid: " + name)
            data = regular_bytes(root, PAYLOAD + "/" + name)
            payload_data[name] = data
            if hashlib.sha256(data).hexdigest() != digest:
                errors.append("installer payload digest drift: " + name)
            if (root / PAYLOAD / name).stat().st_mode & 0o7111:
                errors.append("installer payload mode must be non-executable 100644: " + name)
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        if set(parity) != {"schema", "source_repository", "source_commit", "files", "installer_source", "limits", "feedback_companion", "connector_companion", "context_kickoff", "task_creation", "source_preparation", "task_selection", "ritual_verification", "governance_procedures", "bootstrap", "explicit_update", "workflow_parity", "frontier_cache", "boundary_repair"}:
            errors.append("installer provenance fields drifted")
        errors.extend(validate_context_kickoff(payload_data, parity))
        errors.extend(validate_task_creation(payload_data, parity))
        errors.extend(validate_source_preparation(payload_data, parity))
        errors.extend(validate_task_selection(payload_data, parity))
        errors.extend(validate_ritual_verification(payload_data, parity))
        if parity.get("schema") != "source-first-installer-parity/v1" or parity.get("source_repository") != "mochan-tk/agentic-dev-kit-for-copilot" or parity.get("source_commit") != SOURCE_COMMIT:
            errors.append("installer frozen source provenance drifted")
        if parity.get("limits") != INSTALLER_LIMITS:
            errors.append("installer known-old/operation-scoped preservation boundary drifted")
        if parity.get("installer_source") != {
            "scaffold-init.sh": "7236d06b901da97c2a1a37fd4a51f6fbd89a75d1",
            "scaffold-init.ps1": "6baa8ca94535d25c3b3b1cc1e4ac4ba95542321f",
            "test-scaffold-init.sh": "e060e59ef1fc4c8dabdae2de091ed8eabafba8a9",
        }:
            errors.append("installer source script/test provenance drifted")
        companion = parity.get("feedback_companion")
        expected = {
            "schema": "installer-feedback-companion/v1",
            "source_files": FEEDBACK_SOURCES,
            "fields": FEEDBACK_FIELDS,
            "recipient": "https://github.com/mochan-tk/agentic-dev-kit-for-codex",
            "integration": "standalone-opt-in-outside-payload",
            "adaptations": FEEDBACK_ADAPTATIONS,
            "evidence": "offline-real-bash-fake-gh-pty-only",
        }
        if not isinstance(companion, dict) or set(companion) != set(expected) | {"target_files"}:
            errors.append("feedback companion fields are missing or unreviewed")
        elif any(companion.get(key) != value for key, value in expected.items()):
            errors.append("feedback companion source/consent/privacy/evidence contract drifted")
        if isinstance(companion, dict):
            targets = companion.get("target_files")
            if not isinstance(targets, list) or [item.get("path") for item in targets] != list(FEEDBACK_PATHS):
                errors.append("feedback companion target inventory drifted")
            else:
                for item in targets:
                    name = item["path"]
                    data = regular_bytes(root, name)
                    if set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644" or (root / name).stat().st_mode & 0o7111:
                        errors.append("feedback companion mode/fields drifted: " + name)
                    if item.get("sha256") != hashlib.sha256(data).hexdigest():
                        errors.append("feedback companion target digest drifted: " + name)
        files = parity.get("files", [])
        if not isinstance(files, list) or any(not isinstance(row, dict) for row in files) or [row.get("destination") for row in files] != sorted(EXPECTED):
            errors.append("installer source parity omits, reorders or adds files")
        else:
            for row in files:
                name = row["destination"]
                source, blob = EXPECTED[name]
                if set(row) != {"destination", "source_path", "source_blob", "target_sha256", "adaptations"} or row.get("source_path") != source or row.get("source_blob") != blob:
                    errors.append("installer source blob/path drift: " + name)
                if row.get("target_sha256") != hashlib.sha256(payload_data[name]).hexdigest():
                    errors.append("installer parity target digest drift: " + name)
                if not isinstance(row.get("adaptations"), list) or not row["adaptations"] or any(not isinstance(x, str) or not x.strip() for x in row["adaptations"]):
                    errors.append("installer adaptation/limitation record missing: " + name)
        skill_names = []
        for name, data in payload_data.items():
            text = data.decode("utf-8")
            if name.endswith("/SKILL.md"):
                match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n(?:\n)?---\n", text)
                if not match or match.group(1) != PurePosixPath(name).parent.name:
                    errors.append("installer Skill frontmatter malformed: " + name)
                else:
                    skill_names.append(match.group(1))
            if name.startswith(".codex/agents/"):
                role = PurePosixPath(name).stem
                if not text.startswith('name = "' + role + '"\ndescription = "') or text.count('"""') != 2:
                    errors.append("installer native role structure drift: " + name)
                if re.search(r"^(model|sandbox_mode|approval_policy|permissions|mcp_servers)\s*=", text, re.M):
                    errors.append("installer native role must not override permissions/runtime: " + name)
            # Only concrete mandatory repository file references are checked.
            # Glob/placeholder/producer-created paths are not installed inputs.
            for reference in re.findall(r"`((?:\.agents/|\.codex/|\.github/)[A-Za-z0-9_./-]+\.(?:md|sh|ps1|toml|yml))`", text):
                optional = {".github/workflows/ci.yml", ".github/docs/context/SOURCES.md"}
                if reference not in EXPECTED and reference not in optional:
                    errors.append("installer dangling concrete resource: " + name + " -> " + reference)
            if re.search(r"\bPIN-000[12]\b|phase-task-ownership|codex-runtime-profile|t11-colima|T12 sole active", text):
                errors.append("installer payload leaks kit-development truth: " + name)
        if len(skill_names) != 8 or len(set(skill_names)) != 8:
            errors.append("installer must contain exactly eight unique Skills")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        errors.append("installer payload/provenance is missing, malformed or uncheckable")
    return errors


def validate_connector_companion(root):
    """Strict companion component, always composed by the production CLI.

    Keep validate()'s payload/feedback component API for existing callers;
    partial fixtures are not evidence that this production component passed.
    """
    errors = []
    root = Path(root)
    try:
        if root.is_symlink():
            raise ValueError("root symlink")
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        companion = parity.get("connector_companion")
        if not isinstance(companion, dict) or set(companion) != set(CONNECTOR_CONTRACT) | {"target_files"}:
            return ["connector companion fields are missing or unreviewed"]
        if any(companion.get(key) != value for key, value in CONNECTOR_CONTRACT.items()):
            errors.append("connector companion source/structure/safety/evidence contract drifted")
        targets = companion.get("target_files")
        if not isinstance(targets, list) or any(not isinstance(item, dict) for item in targets) or [item.get("path") for item in targets] != list(CONNECTOR_PATHS):
            return errors + ["connector companion target inventory drifted"]
        for item in targets:
            name = item["path"]
            data = regular_bytes(root, name)
            if set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644" or (root / name).stat().st_mode & 0o7111:
                errors.append("connector companion mode/fields drifted: " + name)
            if item.get("sha256") != hashlib.sha256(data).hexdigest():
                errors.append("connector companion target digest drifted: " + name)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        errors.append("connector companion is missing, malformed or uncheckable")
    return errors


def validate_governance_procedures(root):
    """Closed provenance and delivery boundary, composed unconditionally."""
    errors = []
    root = Path(root)
    try:
        if root.is_symlink():
            raise ValueError("root symlink")
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity.get("governance_procedures")
        if not isinstance(record, dict) or set(record) != set(GOVERNANCE_PROCEDURE_CONTRACT) | {"target_files"}:
            return ["governance/procedure companion fields missing or unreviewed"]
        if any(record.get(k) != v for k, v in GOVERNANCE_PROCEDURE_CONTRACT.items()):
            errors.append("governance/procedure companion source, delivery or limits drifted")
        targets = record.get("target_files")
        if not isinstance(targets, list) or any(not isinstance(x, dict) for x in targets) or [x.get("path") for x in targets] != list(GOVERNANCE_PROCEDURE_PATHS):
            return errors + ["governance/procedure companion target inventory drifted"]
        for item in targets:
            path = item["path"]
            data = regular_bytes(root, path)
            mode = (root / path).lstat().st_mode
            if set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644" or mode & 0o7111:
                errors.append("governance/procedure companion mode or fields drifted")
            if item.get("sha256") != hashlib.sha256(data).hexdigest():
                errors.append("governance/procedure companion target digest drifted")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        errors.append("governance/procedure companion missing, unsafe or malformed")
    return errors



BOOTSTRAP_PATHS = (".github/scripts/scaffold-init.sh", ".github/scripts/scaffold-init.ps1",
                   ".github/scripts/scaffold-install.sh")
BOOTSTRAP_CONTRACT = {
    "source_files": {
        ".github/scripts/scaffold-init.sh": "7236d06b901da97c2a1a37fd4a51f6fbd89a75d1",
        ".github/scripts/scaffold-init.ps1": "6baa8ca94535d25c3b3b1cc1e4ac4ba95542321f",
    },
    "transport": "public-https-pinned-bare-git-object-projection-no-checkout",
    "external": "default-apply-stage-only-created-raw-blobs",
    "local": "reviewed-current-engine-default-dry-run-no-stage",
    "trust": "initial-bootstrap-trusted-code-hashes-are-integrity-not-authentication",
    "limits": "exclusive-target-partial-failure-manual-recovery-native-windows-unmeasured",
}
LOCAL_ENGINE_SHA256 = "3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284"


def validate_bootstrap(root):
    """Always required by CLI; legacy component APIs do not prove this passed."""
    root = Path(root)
    errors = []
    try:
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity.get("bootstrap")
        if not isinstance(record, dict) or set(record) != set(BOOTSTRAP_CONTRACT) | {"target_files"}:
            return ["bootstrap provenance fields missing or unreviewed"]
        if any(record.get(k) != v for k, v in BOOTSTRAP_CONTRACT.items()):
            errors.append("bootstrap source, transport, staging or trust contract drifted")
        expected = []
        for path in BOOTSTRAP_PATHS:
            data = regular_bytes(root, path)
            if (root / path).stat().st_mode & 0o7111:
                errors.append("bootstrap entry mode must be 100644: " + path)
            expected.append({"path": path, "mode": "100644", "sha256": hashlib.sha256(data).hexdigest()})
        if record.get("target_files") != expected:
            errors.append("bootstrap target digest, inventory or mode drifted")
        if expected[-1]["sha256"] != LOCAL_ENGINE_SHA256:
            errors.append("local engine differs from exact reviewed current bytes")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        errors.append("bootstrap missing, unsafe or malformed")
    return errors


UPDATE_PATHS = (".github/scripts/scaffold-update.sh", ".github/scripts/scaffold-update.ps1",
                "tests/conformance/test_installer_update.py")
UPDATE_CONTRACT = {
    "source_repository": "mochan-tk/agentic-dev-kit-for-codex",
    "source_commit": "2a016af9993b1e86905d34fdf51b01fbc64c222f",
    "source_tree": "38847c8d1349dec8fbab0af8833d60e194c63125",
    "source_files": {
        ".github/scripts/scaffold-init.sh": "d02e068f100dc03a401a9b1608f13d39c88e5861",
        ".github/scripts/scaffold-init.ps1": "ce1804cfed061133f8b82a22edfd163d91fb6028",
        ".github/scripts/scaffold-install.sh": "b903817e17f40f25c2a7fa41e58d003ae19cebfd"
    },
    "transport": "anonymous-https-exact-old-new-commits-bare-git-object-projection",
    "engine_sha256": "3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284",
    "preservation": "fixed-47-path-class-layout-known-old-engine-only-no-stage-commit-push",
    "preview": "default-owned-scratch-only-target-index-requested-recovery-unchanged",
    "recovery": "fresh-private-root-retained-old-new-transaction-siblings-offline-bound-rollback",
    "trust": "downloaded-entry-trusted-code-selected-updaters-never-executed-hashes-not-authentication",
    "limits": "explicit-versions-exclusive-target-no-force-no-auto-update-native-windows-unmeasured",
    "fixture_adaptation": {
        "path": "tests/conformance/test_connector_validation.py",
        "export_source_repository": "mochan-tk/agentic-dev-kit-for-codex-pre",
        "export_source_commit": "609362b327a4362b5f5eadcf5f8bdc8935948b98",
        "export_source_blob": "6b1cd8446b382c37157903fbdb0ffbd2556443db",
        "export_sha256": "3e03f1436d33fec448b23b3cc51b1a354c7f91cbdc3b5bf9f9a4f99c34ddd778",
        "export_mode": "100644",
        "target_blob": "97269ed19fb5a387452bc50bcf50ea73442ca545",
        "target_sha256": "0b231321cce78040848a563e5936f64d3f4bbc9c78f5cf1d962a8ea458949255",
        "target_mode": "100644",
        "scope": "copy-required-update-and-workflow-inputs-and-assert-complete-fixture"
    }
}


def validate_explicit_update(root):
    """Mandatory current-product extension; predecessor/export records stay frozen."""
    root = Path(root)
    errors = []
    try:
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity.get("explicit_update")
        if not isinstance(record, dict) or set(record) != set(UPDATE_CONTRACT) | {"target_files"}:
            return ["explicit update provenance fields missing or unreviewed"]
        if any(record.get(key) != value for key, value in UPDATE_CONTRACT.items()):
            errors.append("explicit update source, preservation or recovery contract drifted")
        expected = []
        for path in UPDATE_PATHS:
            data = regular_bytes(root, path)
            if (root / path).stat().st_mode & 0o7111:
                errors.append("explicit update mode must be 100644: " + path)
            expected.append({"path": path, "mode": "100644", "sha256": hashlib.sha256(data).hexdigest()})
        if record.get("target_files") != expected:
            errors.append("explicit update target digest, inventory or mode drifted")
        engine = regular_bytes(root, ".github/scripts/scaffold-install.sh")
        if hashlib.sha256(engine).hexdigest() != LOCAL_ENGINE_SHA256:
            errors.append("explicit update engine differs from exact reviewed current bytes")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        errors.append("explicit update missing, unsafe or malformed")
    return errors


def validate_workflow_parity(root):
    """Current bounded adaptation; original export and history are immutable."""
    errors = []
    root = Path(root)
    try:
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity["workflow_parity"]
        if set(record) != set(WORKFLOW_CONTRACT) | {"target_files", "export_adaptations", "baseline_sha256"} or any(
                record.get(k) != v for k, v in WORKFLOW_CONTRACT.items()):
            return ["workflow parity source, scope or evidence contract drifted"]
        baseline_data = regular_bytes(root, WORKFLOW_BASELINE)
        if hashlib.sha256(baseline_data).hexdigest() != WORKFLOW_BASELINE_SHA256 or record["baseline_sha256"] != WORKFLOW_BASELINE_SHA256:
            errors.append("workflow parity immutable baseline changed")
        baseline = json.loads(baseline_data, object_pairs_hook=reject_duplicate_json_keys)
        if (set(baseline) != {"schema", "repository", "commit", "tree", "entries"}
                or baseline["schema"] != "workflow-parity-baseline/v1"
                or baseline["repository"] != "mochan-tk/agentic-dev-kit-for-codex"
                or baseline["commit"] != WORKFLOW_CONTRACT["product_base"]
                or baseline["tree"] != WORKFLOW_CONTRACT["product_base_tree"]
                or [row["path"] for row in baseline["entries"]] != list(WORKFLOW_PAYLOAD_PATHS)):
            errors.append("workflow parity baseline identity or inventory changed")
        for row in baseline["entries"]:
            data = base64.b64decode(row["base64"], validate=True)
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if set(row) != {"path", "mode", "sha256", "blob", "base64"} or row["mode"] != "100644" or row["sha256"] != hashlib.sha256(data).hexdigest() or row["blob"] != blob:
                errors.append("workflow parity baseline bytes changed")
        expected = [{"path": p, "mode": "100644", "sha256": hashlib.sha256(regular_bytes(root, p)).hexdigest()} for p in WORKFLOW_TARGETS]
        if record["target_files"] != expected:
            errors.append("workflow parity target digest, mode or inventory changed")
        export = json.loads(regular_bytes(root, ".github/distribution/export-provenance.v1.json"), object_pairs_hook=reject_duplicate_json_keys)
        original = {row["path"]: row for row in export["frozen_files"]}
        adaptations = []
        for path in WORKFLOW_EXPORT_PATHS:
            data = regular_bytes(root, path)
            adaptations.append({"path": path, "export": original[path], "target_mode": "100644",
                "target_sha256": hashlib.sha256(data).hexdigest(),
                "target_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
        if record["export_adaptations"] != adaptations:
            errors.append("workflow parity export adaptation boundary changed")
        helper = regular_bytes(root, PAYLOAD + "/.github/scripts/check-task-ritual.sh").decode()
        for token in ("record_mode()", 'case "${1:-}" in render|preflight)', "--method GET", "first-dispatch-after-commit",
                      "exact-plan-membership", "task-readback", "comments-readback", "plan-readback", "pr-readback", "ritual_dispatch_rows"):
            if token not in helper:
                errors.append("workflow parity installed record guard missing")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        errors.append("workflow parity missing, unsafe or malformed")
    return errors


def validate_frontier_cache(root):
    """Exact current cache/anchor adaptation, separate from immutable old seals."""
    errors = []
    try:
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity["frontier_cache"]
        if (set(record) != set(FRONTIER_CONTRACT) | {"target_files", "baseline_sha256", "export_adaptation"}
                or any(record.get(key) != value for key, value in FRONTIER_CONTRACT.items())):
            return ["frontier cache source/scope/evidence contract drifted"]
        baseline_data = regular_bytes(root, FRONTIER_BASELINE)
        if (hashlib.sha256(baseline_data).hexdigest() != FRONTIER_BASELINE_SHA256
                or record["baseline_sha256"] != FRONTIER_BASELINE_SHA256):
            errors.append("frontier cache immutable baseline changed")
        baseline = json.loads(baseline_data, object_pairs_hook=reject_duplicate_json_keys)
        if (set(baseline) != {"schema", "repository", "commit", "tree", "entries"}
                or baseline["schema"] != "frontier-cache-baseline/v1"
                or baseline["repository"] != "mochan-tk/agentic-dev-kit-for-codex"
                or baseline["commit"] != FRONTIER_CONTRACT["product_base"]
                or baseline["tree"] != FRONTIER_CONTRACT["product_base_tree"]
                or [row["path"] for row in baseline["entries"]] != list(FRONTIER_PATHS)):
            errors.append("frontier cache baseline identity/inventory changed")
        for row in baseline["entries"]:
            data = base64.b64decode(row["base64"], validate=True)
            if (set(row) != {"path", "mode", "sha256", "blob", "base64"} or row["mode"] != "100644"
                    or row["sha256"] != hashlib.sha256(data).hexdigest()
                    or row["blob"] != hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()):
                errors.append("frontier cache baseline bytes changed")
        expected = [{"path": path, "mode": "100644", "sha256": hashlib.sha256(regular_bytes(root, path)).hexdigest()}
                    for path in FRONTIER_TARGETS]
        if record["target_files"] != expected:
            errors.append("frontier cache target digest/mode/inventory changed")
        for path, digest in zip(FRONTIER_TARGETS, FRONTIER_DIGESTS):
            if hashlib.sha256(regular_bytes(root, path)).hexdigest() != digest:
                errors.append("frontier cache exact reviewed engine changed")
        export = json.loads(regular_bytes(root, ".github/distribution/export-provenance.v1.json"), object_pairs_hook=reject_duplicate_json_keys)
        path = FRONTIER_TARGETS[0]
        original = next(row for row in export["frozen_files"] if row["path"] == path)
        data = regular_bytes(root, path)
        adaptation = {"path": path, "export": original, "target_mode": "100644",
                      "target_sha256": hashlib.sha256(data).hexdigest(),
                      "target_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
        if record["export_adaptation"] != adaptation:
            errors.append("frontier cache exact export adaptation changed")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, StopIteration):
        errors.append("frontier cache missing, unsafe or malformed")
    return errors


BOUNDARY_BASELINE = "tests/fixtures/boundary-repair-baseline.json"
BOUNDARY_BASELINE_SHA256 = "19443f641f0f4973b69ed976cad1bf5889c28759d42590823fcc4296000d587b"
BOUNDARY_BASE_PATHS = tuple(sorted((
    ".github/scripts/scaffold-install.sh", ".github/scripts/scaffold-init.sh", ".github/scripts/scaffold-update.sh",
    PAYLOAD + "/.github/scripts/check-task-ritual.sh", ".github/distribution/adopter-ci/check-adopter-ci.py",
)))
BOUNDARY_EXPORT_PATHS = (".github/scripts/scaffold-init.sh", ".github/scripts/scaffold-install.sh")
BOUNDARY_TARGETS = tuple(sorted((*BOUNDARY_BASE_PATHS, INVENTORY,
    "tests/conformance/test_installer.py", "tests/conformance/test_installer_bootstrap.py", "tests/conformance/test_installer_update.py",
    "tests/conformance/test_workflow_parity.py", "tests/conformance/test_adopter_ci.py", "tests/conformance/test_product.py",
    "docs/distribution/source-first-installer.md", "docs/distribution/adopter-ci.md", "docs/known-limitations.md",
    "docs/provenance.md", "docs/product-scope.md",
)))
BOUNDARY_DIGESTS = {
    ".github/distribution/adopter-ci/check-adopter-ci.py": "0bed9fa2501864eb68330bd6d6aecf228695320faaa146be5c47a5bda082a4fd",
    ".github/distribution/payload.v1.tsv": "b0a18e6e04d76d411dd3fcd725933db8bd3fe9cb226144a1438804193f7f745e",
    ".github/distribution/payload/.github/scripts/check-task-ritual.sh": "319710322bbc97984bd6c5f17c81730cc4cbf400702f16b1f88a12ba5c8a33f7",
    ".github/scripts/scaffold-init.sh": "6cf321e259d57fd0f8f84322e54096933be4909834cfab27800dc3f58c0761b0",
    ".github/scripts/scaffold-install.sh": "3a4c87a4427172cd9e30d897d807df7c4b721aa62884c8c772a69d77d1467284",
    ".github/scripts/scaffold-update.sh": "aeba5b903b9688c3741dc99135a886083e60aaa65fc2e094a43a334262f0ff18",
    "docs/distribution/adopter-ci.md": "70208c82a1d2447cb9ddf8338540981bfba4ac8ac51ca36e2b945607e5df03d9",
    "docs/distribution/source-first-installer.md": "9013219967f19667a4467e8c2d4f3b96613cff87f239724e78790a273f0eda68",
    "docs/known-limitations.md": "dfd34e7173bd4d1fbcc838d3c123f547bfcd720885d9d78d01a7d67da3447508",
    "docs/product-scope.md": "4e980dc49043b706517e59f223a5ec169567290f8c20b463a9f8c85350ce90e1",
    "docs/provenance.md": "1503369b5ed6b34c8157323ea58394bacca0e41a1d27b3b68791ed109f0292a1",
    "tests/conformance/test_adopter_ci.py": "5c31532a3540f45c4b75f51fdc7a8c829584b73fc817be5d241fc0740e64c2e3",
    "tests/conformance/test_installer.py": "f6fa0fd6d3f7f1b43294882133eff498bae0321607cdaa6be55851ad2a8178f1",
    "tests/conformance/test_installer_bootstrap.py": "d04626dfea8b0f0b3b8da87ae207356da5935b28770f04f2531a334d05afc01e",
    "tests/conformance/test_installer_update.py": "34f4c2030e54e936c5836a8a54a9863e7e02ce843020a2834410b2ef1be2f3b6",
    "tests/conformance/test_product.py": "462396d32154cc633811514fa82e352264cf56b2722ab3f459dd87f24be161df",
    "tests/conformance/test_workflow_parity.py": "9795c1e6ce3e2e9c7a113bead9e2f7d44849ce2db5038b1d2db19d195f122636"
}
BOUNDARY_CONTRACT = {
    "schema": "source-first-boundary-repair/v1",
    "product_base": "c86064de19d6ddbeb61f5cf3633bb9fb52cac882",
    "product_base_tree": "81940d779a12ccb82587859cdf6cc07227db7721",
    "delivery": "47-fixed-paths-ritual-only-payload-change-other-46-unchanged",
    "git_context": "reject-inherited-repository-overrides-before-local-observation",
    "update": "from-exact-previous-or-current-engine-data;to-exact-current-engine-only;execute-new-only",
    "previous_engine_sha256": "3c582e519c91a85641f672379f1513126ec209e7ce11c8ed1b3c20aa550f12b2",
    "operation": "unchanged-local-upgrade/v1-retained-source-identity-offline-rollback",
    "command": "owned-posix-session-group-cleanup-on-every-return;30-seconds-combined-2-MiB",
    "input": "strict-UTF8-NUL-refusal-byte-roundtrip-262144-byte-limit-no-new-dependency",
    "evidence": "real-local-tools-disposable-fixtures-synthetic-transport",
    "limits": "no-escaped-group-control-native-Windows-live-adopter-runtime-or-release-claim",
}


def validate_boundary_repair(root):
    """Closed current adaptation with exact old fixture and independently pinned bytes."""
    errors = []
    try:
        parity = json.loads(regular_bytes(root, PARITY), object_pairs_hook=reject_duplicate_json_keys)
        record = parity["boundary_repair"]
        if (set(record) != set(BOUNDARY_CONTRACT) | {"target_files", "baseline_sha256", "export_adaptations"}
                or any(record.get(key) != value for key, value in BOUNDARY_CONTRACT.items())):
            return ["boundary repair scope or contract drifted"]
        baseline_data = regular_bytes(root, BOUNDARY_BASELINE)
        if (hashlib.sha256(baseline_data).hexdigest() != BOUNDARY_BASELINE_SHA256
                or record["baseline_sha256"] != BOUNDARY_BASELINE_SHA256):
            errors.append("boundary repair immutable baseline changed")
        baseline = json.loads(baseline_data, object_pairs_hook=reject_duplicate_json_keys)
        if (set(baseline) != {"schema", "repository", "commit", "tree", "files"}
                or baseline["schema"] != "boundary-repair-baseline/v1"
                or baseline["repository"] != "mochan-tk/agentic-dev-kit-for-codex"
                or baseline["commit"] != BOUNDARY_CONTRACT["product_base"]
                or baseline["tree"] != BOUNDARY_CONTRACT["product_base_tree"]
                or [row["path"] for row in baseline["files"]] != list(BOUNDARY_BASE_PATHS)):
            errors.append("boundary repair baseline identity or inventory changed")
        for row in baseline["files"]:
            data = base64.b64decode(row["base64"], validate=True)
            if (set(row) != {"path", "mode", "sha256", "blob", "base64"} or row["mode"] != "100644"
                    or row["sha256"] != hashlib.sha256(data).hexdigest()
                    or row["blob"] != hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()):
                errors.append("boundary repair baseline bytes changed")
        expected = [{"path": path, "mode": "100644", "sha256": hashlib.sha256(regular_bytes(root, path)).hexdigest()}
                    for path in BOUNDARY_TARGETS]
        if record["target_files"] != expected or set(BOUNDARY_DIGESTS) != set(BOUNDARY_TARGETS):
            errors.append("boundary repair target inventory or binding changed")
        for row in expected:
            if row["sha256"] != BOUNDARY_DIGESTS.get(row["path"]):
                errors.append("boundary repair exact reviewed bytes changed: " + row["path"])
        export = json.loads(regular_bytes(root, ".github/distribution/export-provenance.v1.json"), object_pairs_hook=reject_duplicate_json_keys)
        original = {row["path"]: row for row in export["frozen_files"]}
        adaptations = []
        for path in BOUNDARY_EXPORT_PATHS:
            data = regular_bytes(root, path)
            adaptations.append({"path": path, "export": original[path], "target_mode": "100644",
                "target_sha256": hashlib.sha256(data).hexdigest(),
                "target_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
        if record["export_adaptations"] != adaptations:
            errors.append("boundary repair exact export adaptation changed")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        errors.append("boundary repair missing, unsafe or malformed")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = (validate(args.root) + validate_connector_companion(args.root)
              + validate_governance_procedures(args.root) + validate_bootstrap(args.root)
              + validate_explicit_update(args.root) + validate_workflow_parity(args.root)
              + validate_frontier_cache(args.root) + validate_boundary_repair(args.root))
    for error in errors:
        print("ERROR: " + error)
    if errors:
        return 1
    print("Installer inventory/parity: 47 files, 8 Skills, 3 role definitions; standalone feedback, connector-validation, governance and worktree companions; existing retro procedures; offline structural evidence only.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
