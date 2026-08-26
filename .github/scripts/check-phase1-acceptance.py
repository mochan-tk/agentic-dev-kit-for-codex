#!/usr/bin/env python3
"""Validate the bounded, non-release Phase 1 acceptance package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
PHASE1_PATH = "tests/conformance/results/phase-1.json"
RELEASE_RESULTS_PATH = "tests/conformance/results.json"
CATALOG_PATH = "tests/conformance/catalog.json"
COVERAGE_PATH = "tests/conformance/coverage.json"
MANIFEST_PATH = "tests/conformance/manifest.json"
OWNERSHIP_PATH = ".github/governance/phase-task-ownership.v1.json"
WORKFLOW_PATH = ".github/workflows/ci.yml"
ACCEPTANCE_DOC_PATH = "docs/planning/phase-1-acceptance.md"
SCORECARD_DOC_PATH = "docs/conformance/phase-1-scorecard.md"
README_PATH = "README.md"
LIMITATIONS_PATH = "docs/known-limitations.md"
AGENTS_PATH = "AGENTS.md"

REQUIRED_INPUT_PATHS = (
    PHASE1_PATH,
    RELEASE_RESULTS_PATH,
    CATALOG_PATH,
    COVERAGE_PATH,
    MANIFEST_PATH,
    OWNERSHIP_PATH,
    WORKFLOW_PATH,
    ACCEPTANCE_DOC_PATH,
    SCORECARD_DOC_PATH,
    README_PATH,
    LIMITATIONS_PATH,
    AGENTS_PATH,
    "docs/agreements/adr/ADR-0005-issue-graph-authority.md",
    ".agents/skills/verification/SKILL.md",
    ".github/governance/ledger-contracts.v1.json",
    ".agents/skills/session-orchestration/SKILL.md",
    ".github/scripts/check-repository-policy.py",
    "docs/agreements/portable-context-contract.v1.json",
    ".github/scripts/check-portable-contracts.py",
    ".github/scripts/check-ledger-templates.py",
    "docs/agreements/skill-parity.v1.json",
    ".github/scripts/check-skills.py",
    ".github/governance/ci-tools.lock.v1.json",
    ".agents/skills/retro/SKILL.md",
    "docs/planning/phase-0-orientation.md",
)

MAX_FILE_BYTES = 262_144
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 20_000
MAX_JSON_STRING_LENGTH = 16_384
BASE_COMMIT = "509362e6e12cf0160e58853b0d6c0b6871aa895c"
BASE_TREE = "69c808a7afc59858213ee68dc89cb6a5a20e3e09"
INVARIANT_DIGEST = "a084a123e16d2fd42619b09161efdaf49bda0ea0ca4a1e076254bd1902aa63f6"
COMPATIBILITY_MANIFEST_SHA256 = (
    "aa86970e10e615e89e2e313cb16a45e9d71dc0584060db69403d9e8800e9a3be"
)
ACCEPTANCE_COMMAND = "python3 -I .github/scripts/check-phase1-acceptance.py"
EXPECTED_TASK_IDS = [f"T{number:02d}" for number in range(1, 10)]
EXPECTED_CONTRACT_IDS = [f"K{number:02d}" for number in range(1, 21)]
ALLOWED_SCENARIO_STATES = {
    "pass",
    "fail",
    "skipped",
    "unverified",
    "approved-deviation",
    "not-run",
    "UNKNOWN",
    "UNCHECKABLE",
}
ACTION_EVIDENCE_CLASSES = {
    "static-scenario-action",
    "runtime-scenario-action",
    "external-state-scenario-action",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ACTION_URL = re.compile(
    rf"{re.escape(REPOSITORY_URL)}/actions/runs/[1-9][0-9]*/job/[1-9][0-9]*\Z"
)
ISO_UTC = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
INVARIANT_ROW = re.compile(r"^\|\s*(I\d{2})\s*\|\s*(.*?)\s*\|\s*$")
PRIVATE_PATH = re.compile(
    r"(?i)(?:^|[\s'\"])(?:/users/|/home/|/root/|/tmp/|/private/tmp/|"
    r"/var/folders/|~/|[a-z]:[\\/]|\\\\)"
)
SECRET = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?i:authorization\s*:\s*bearer\s+\S+))"
)

T10_OWNED_PATHS = [
    ".github/governance/phase-task-ownership.v1.json",
    ".github/scripts/check-phase1-acceptance.py",
    ".github/scripts/check-repository-policy.py",
    ".github/workflows/ci.yml",
    "README.md",
    "docs/conformance/phase-1-scorecard.md",
    "docs/known-limitations.md",
    "docs/planning/phase-1-acceptance.md",
    "tests/conformance/manifest.json",
    "tests/conformance/results/phase-1.json",
    "tests/conformance/test_phase1_acceptance.py",
    "tests/conformance/test_repository_policy.py",
]

EXPECTED_EVIDENCE_CLASSES = {
    "pre_merge": {
        "state": "candidate",
        "binding": "external-pr-and-issue-receipt",
        "success_requires": [
            "exact-head",
            "exact-tree",
            "direct-commands",
            "quality-url",
            "conformance-url",
            "mergeable-pr",
            "owner-judgment",
        ],
    },
    "post_merge": {
        "state": "pending",
        "binding": "future-post-merge-receipt",
        "success_requires": [
            "merge-commit",
            "merge-tree",
            "both-parents",
            "post-merge-quality-url",
            "post-merge-conformance-url",
            "issue-outcome",
            "epic-outcome",
        ],
    },
    "later_repository": {
        "state": "non-pass",
        "binding": "future-reviewed-tasks",
        "includes": [
            "custom-agents",
            "task-execution-envelope",
            "loop-events",
            "hooks",
            "codex-exec-adapter",
            "installer-upgrade",
            "live-task-ritual",
            "feedback-transport",
            "clean-adopter-e2e",
            "full-source-parity",
            "release",
        ],
    },
}

EXPECTED_TASK_EVIDENCE = {
    "T01": {
        "title": "Observe branch governance and publish versioned intent",
        "issue": 3,
        "plan": "issues/3#issuecomment-5388861150",
        "receipt": "issues/3#issuecomment-5388863356",
        "head": "32615344ad4f0310948bc59d234a84718741788a",
        "tree": "33259721ec9f378fa67392ef8e1c7645db1321f9",
        "quality": "actions/runs/32663677641/job/97253594482",
        "conformance": "actions/runs/32663677641/job/97253594322",
    },
    "T02": {
        "title": "Activate and verify the approved solo-profile main Ruleset",
        "issue": 4,
        "plan": "issues/4",
        "receipt": "issues/4#issuecomment-5388863497",
        "head": "32615344ad4f0310948bc59d234a84718741788a",
        "tree": "33259721ec9f378fa67392ef8e1c7645db1321f9",
        "quality": "actions/runs/32663677641/job/97253594482",
        "conformance": "actions/runs/32663677641/job/97253594322",
    },
    "T03": {
        "title": "Separate frozen Phase 0 verification from live repository policy",
        "issue": 5,
        "plan": "issues/5#issuecomment-5388869324",
        "receipt": "issues/5#issuecomment-5389844185",
        "pr": 13,
        "head": "94f92af978839efc48f0ca6afd77514bf291b9f6",
        "tree": "f7132c5867023a2b971e0383d95a6c4184e20f35",
        "merge": "3065afcf80ee348796a7d159f6aaefeeac65ad10",
        "parents": [
            "32615344ad4f0310948bc59d234a84718741788a",
            "94f92af978839efc48f0ca6afd77514bf291b9f6",
        ],
        "quality": "actions/runs/32681407695/job/97298627355",
        "conformance": "actions/runs/32681407695/job/97298627165",
    },
    "T04": {
        "title": "Persist the complete 136-scenario conformance catalog",
        "issue": 6,
        "plan": "issues/6#issuecomment-5389938555",
        "receipt": "issues/6#issuecomment-5392427841",
        "pr": 14,
        "head": "95ad638787047194a1bcf6ca074c1b0a9309f1da",
        "tree": "b63d34ed4dabc81c6a4914af017cbe7de3d25739",
        "merge": "7cd36f3b2e5711b1cf127e69731951cf9604b4d5",
        "parents": [
            "3065afcf80ee348796a7d159f6aaefeeac65ad10",
            "95ad638787047194a1bcf6ca074c1b0a9309f1da",
        ],
        "quality": "actions/runs/32704901829/job/97363797952",
        "conformance": "actions/runs/32704901829/job/97363798203",
    },
    "T05": {
        "title": "Resolve canonical hierarchy terminology and repository completion",
        "issue": 7,
        "plan": "issues/7#issuecomment-5396759095",
        "receipt": "issues/7#issuecomment-5398125586",
        "pr": 15,
        "head": "562818ee902fb089dcdd8077b4dace0dd94c341c",
        "tree": "85153f261e574d1287970d7ce14c3446e4e0d020",
        "merge": "1c949b01a25208d91e0c7380facfd6ed9d48f833",
        "parents": [
            "7cd36f3b2e5711b1cf127e69731951cf9604b4d5",
            "562818ee902fb089dcdd8077b4dace0dd94c341c",
        ],
        "quality": "actions/runs/32750264886/job/97505301794",
        "conformance": "actions/runs/32750264886/job/97505301455",
    },
    "T06": {
        "title": "Harden the required CI toolchain",
        "issue": 8,
        "plan": "issues/8#issuecomment-5402644687",
        "receipt": "issues/8#issuecomment-5403935064",
        "pr": 16,
        "head": "0ef66c2d0baf9b7dee30dee8d1e4744ba4b7f75c",
        "tree": "fe96b1eb5c825be6b4d936fa4850e26a51b7b3d0",
        "merge": "0e863f610267ca1ea454c19db2983ec4039d5d6b",
        "parents": [
            "1c949b01a25208d91e0c7380facfd6ed9d48f833",
            "0ef66c2d0baf9b7dee30dee8d1e4744ba4b7f75c",
        ],
        "quality": "actions/runs/32798682441/job/97655150831",
        "conformance": "actions/runs/32798682441/job/97655150672",
    },
    "T07": {
        "title": "Add synchronized Epic, Task, and pull-request ledger templates",
        "issue": 9,
        "plan": "issues/9#issuecomment-5404518469",
        "receipt": "issues/9#issuecomment-5409052229",
        "pr": 17,
        "head": "952fb273fd6eb2811dd0ad6ebfea062e682c1155",
        "tree": "e755dfba299b73d06f97fe7caeba6d520225c202",
        "merge": "0adb4ef232ebd853df8af788db96c02bde6576ae",
        "parents": [
            "0e863f610267ca1ea454c19db2983ec4039d5d6b",
            "952fb273fd6eb2811dd0ad6ebfea062e682c1155",
        ],
        "quality": "actions/runs/32836943638/job/97767808961",
        "conformance": "actions/runs/32836943638/job/97767808627",
    },
    "T08": {
        "title": "Establish connector-neutral agreements and context contracts",
        "issue": 10,
        "plan": "issues/10#issuecomment-5409182342",
        "receipt": "issues/10#issuecomment-5412449204",
        "pr": 18,
        "head": "557c1086351e08f56b3d5c7ad2ab538fc5b6d4f8",
        "tree": "f006ed8963d600a2a9bbf1b3917dc57e6f6a41d8",
        "merge": "539c01822c005e639438331e70c592891e136430",
        "parents": [
            "0adb4ef232ebd853df8af788db96c02bde6576ae",
            "557c1086351e08f56b3d5c7ad2ab538fc5b6d4f8",
        ],
        "quality": "actions/runs/32863505284/job/97853005307",
        "conformance": "actions/runs/32863505284/job/97853005518",
    },
    "T09": {
        "title": "Port and verify the eight repository Skills",
        "issue": 11,
        "plan": "issues/11#issuecomment-5412882001",
        "receipt": "issues/11#issuecomment-5419149972",
        "pr": 19,
        "head": "19879ed8f4608399058ea3ecffea30ab6a5924e3",
        "tree": "69c808a7afc59858213ee68dc89cb6a5a20e3e09",
        "merge": BASE_COMMIT,
        "parents": [
            "539c01822c005e639438331e70c592891e136430",
            "19879ed8f4608399058ea3ecffea30ab6a5924e3",
        ],
        "quality": "actions/runs/32917569601/job/98024375395",
        "conformance": "actions/runs/32917569601/job/98024375513",
    },
}

FUTURE_LANES = {
    "portable-residual": {
        "state": "unassigned",
        "lane": "future-runtime-distribution-and-governance",
        "activation_gate": "future-human-reviewed-phase-epic-or-task-required",
    },
    "repository-release": {
        "state": "unassigned",
        "lane": "future-repository-release-and-parity",
        "activation_gate": "future-human-reviewed-phase-epic-or-task-required",
    },
}

EXPECTED_CONTRACT_DETAILS = {
    "K01": {
        "status": "phase-1-static-advanced",
        "evidence": [
            "AGENTS.md",
            "docs/agreements/adr/ADR-0005-issue-graph-authority.md",
        ],
        "advanced": "Option B hierarchy and accepted Task evidence are durable.",
        "remaining": "Runtime recovery and live ritual evidence remain absent.",
        "lane": "portable-residual",
    },
    "K02": {
        "status": "phase-1-static-advanced",
        "evidence": [
            ".agents/skills/verification/SKILL.md",
            ".github/governance/ledger-contracts.v1.json",
        ],
        "advanced": "Static record, evidence, and escalation contracts are present.",
        "remaining": "Live orchestration and current-attempt enforcement remain absent.",
        "lane": "portable-residual",
    },
    "K03": {
        "status": "partial-incomplete",
        "evidence": [
            "AGENTS.md",
            ".agents/skills/session-orchestration/SKILL.md",
        ],
        "advanced": "Policy and orchestration guidance define the topology.",
        "remaining": "Authenticated roles and six custom agents remain unimplemented.",
        "lane": "portable-residual",
    },
    "K04": {
        "status": "phase-1-static-advanced",
        "evidence": [
            ".github/governance/phase-task-ownership.v1.json",
            ".github/scripts/check-repository-policy.py",
        ],
        "advanced": "Versioned exact-path ownership and overlap rejection are active in CI.",
        "remaining": "Envelope and cross-surface runtime enforcement remain absent.",
        "lane": "portable-residual",
    },
    "K05": {
        "status": "phase-1-static-advanced",
        "evidence": [
            "AGENTS.md",
            ".github/governance/ledger-contracts.v1.json",
        ],
        "advanced": "Human gates and risk fields are durable static contracts.",
        "remaining": "Runtime identity and universal control-plane enforcement remain absent.",
        "lane": "portable-residual",
    },
    "K06": {
        "status": "phase-1-static-advanced",
        "evidence": [
            "docs/agreements/portable-context-contract.v1.json",
            ".github/scripts/check-portable-contracts.py",
        ],
        "advanced": "Stable requirements, decisions, context pins, and connector-neutral operations are checked.",
        "remaining": "External connectors and cross-surface runtime reachability are not proven.",
        "lane": "portable-residual",
    },
    "K07": {
        "status": "phase-1-static-advanced",
        "evidence": [
            ".github/governance/ledger-contracts.v1.json",
            ".github/scripts/check-ledger-templates.py",
        ],
        "advanced": "Epic, Task, and PR human/machine contracts are synchronized and checked.",
        "remaining": "Live Task ritual and GitHub-body equality require later runtime work.",
        "lane": "portable-residual",
    },
    "K08": {
        "status": "phase-1-static-advanced",
        "evidence": [
            "docs/agreements/skill-parity.v1.json",
            ".github/scripts/check-skills.py",
        ],
        "advanced": "Exactly eight Skills and source-to-target parity records are statically checked.",
        "remaining": "Runtime invocation, implicit selection, and cross-surface evidence remain not-run.",
        "lane": "portable-residual",
    },
    "K09": {
        "status": "incomplete-later-phase",
        "evidence": ["AGENTS.md"],
        "advanced": "Role semantics exist only as policy.",
        "remaining": "Six custom agents and authenticated role evidence are unimplemented.",
        "lane": "portable-residual",
    },
    "K10": {
        "status": "incomplete-later-phase",
        "evidence": ["docs/known-limitations.md"],
        "advanced": "No Phase 1 implementation claim is made.",
        "remaining": "task-execution-envelope/v1 is unimplemented.",
        "lane": "portable-residual",
    },
    "K11": {
        "status": "incomplete-later-phase",
        "evidence": ["docs/known-limitations.md"],
        "advanced": "No Phase 1 implementation claim is made.",
        "remaining": "loop-event/v1 is unimplemented.",
        "lane": "portable-residual",
    },
    "K12": {
        "status": "incomplete-later-phase",
        "evidence": ["docs/known-limitations.md"],
        "advanced": "The machine-readable surface boundary is documented.",
        "remaining": "The codex exec adapter and normalized stream handling are unimplemented.",
        "lane": "portable-residual",
    },
    "K13": {
        "status": "incomplete-later-phase",
        "evidence": ["AGENTS.md", "docs/known-limitations.md"],
        "advanced": "Upgrade preservation remains a canonical invariant.",
        "remaining": "Installer, upgrade, adoption, and rollback behavior are unimplemented.",
        "lane": "portable-residual",
    },
    "K14": {
        "status": "incomplete-later-phase",
        "evidence": [".github/governance/ledger-contracts.v1.json"],
        "advanced": "Ledger fields provide a static foundation only.",
        "remaining": "The live Task ritual and current-attempt enforcement are unimplemented.",
        "lane": "portable-residual",
    },
    "K15": {
        "status": "partial-incomplete",
        "evidence": [
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/4#issuecomment-5388863497"
        ],
        "advanced": "The solo-fast Ruleset used sensor, intent, explicit actuator, and verification.",
        "remaining": "General adopter governance activation and reconciliation remain later work.",
        "lane": "portable-residual",
    },
    "K16": {
        "status": "incomplete-later-phase",
        "evidence": [".agents/skills/retro/SKILL.md"],
        "advanced": "The Retro Skill provides static failure-to-harness guidance.",
        "remaining": "Consent-aware feedback transport and telemetry are unimplemented.",
        "lane": "portable-residual",
    },
    "K17": {
        "status": "phase-1-static-advanced",
        "evidence": [
            ".github/workflows/ci.yml",
            ".github/governance/ci-tools.lock.v1.json",
        ],
        "advanced": "Pinned tools, least privilege, stable required jobs, and deterministic discovery are checked.",
        "remaining": "Release, clean-adopter E2E, and all runtime matrices remain later work.",
        "lane": "repository-release",
    },
    "K18": {
        "status": "phase-1-static-advanced",
        "evidence": [
            "docs/planning/phase-0-orientation.md",
            "docs/agreements/skill-parity.v1.json",
        ],
        "advanced": "Known defects and Codex-native adaptations have durable records and regressions.",
        "remaining": "Full source parity reconciliation remains later work.",
        "lane": "repository-release",
    },
    "K19": {
        "status": "phase-1-static-advanced",
        "evidence": ["AGENTS.md", "docs/known-limitations.md"],
        "advanced": "Core contracts remain model-neutral and control-plane limits are explicit.",
        "remaining": "No universal authenticated runtime identity or control plane exists.",
        "lane": "portable-residual",
    },
    "K20": {
        "status": "blocked-release",
        "evidence": ["tests/conformance/results.json"],
        "advanced": "The canonical catalog and empty result store make the release boundary explicit.",
        "remaining": "Full static/runtime parity, 136 scenario passes, clean-adopter E2E, and release evidence are absent.",
        "lane": "repository-release",
    },
}


class DuplicateKeyError(ValueError):
    pass


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def valid_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if value.startswith(("/", "//")) or "\\" in value:
        return False
    if unicodedata.normalize("NFC", value) != value:
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    path = PurePosixPath(value)
    return value == path.as_posix() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _snapshot(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_regular_bytes(root: Path, relative: str) -> bytes:
    """Read one bounded fixed input descriptor-relatively without symlink follow."""

    if not valid_relative_path(relative):
        raise ValueError(f"unsafe repository path: {relative!r}")
    flags: dict[str, int] = {}
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise ValueError(f"required safe filesystem flag is unavailable: {name}")
        flags[name] = value
    if os.open not in getattr(os, "supports_dir_fd", set()):
        raise ValueError("descriptor-relative open is unavailable")
    if os.stat not in getattr(os, "supports_dir_fd", set()):
        raise ValueError("descriptor-relative stat is unavailable")
    if os.stat not in getattr(os, "supports_follow_symlinks", set()):
        raise ValueError("no-follow stat is unavailable")

    descriptors: list[int] = []
    bindings: list[tuple[int, str, tuple[int, int, int]]] = []
    try:
        root_before = os.lstat(os.fspath(root))
        if not stat.S_ISDIR(root_before.st_mode) or stat.S_ISLNK(root_before.st_mode):
            raise ValueError("repository root must be a non-symlink directory")
        current = os.open(
            os.fspath(root),
            os.O_RDONLY | flags["O_DIRECTORY"] | flags["O_NOFOLLOW"] | flags["O_CLOEXEC"],
        )
        descriptors.append(current)
        root_open = os.fstat(current)
        if _identity(root_before) != _identity(root_open):
            raise ValueError("repository root binding changed before read")
        root_identity = _identity(root_open)

        parts = relative.split("/")
        for part in parts[:-1]:
            observed = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode):
                raise ValueError(f"repository parent is not a regular directory: {relative}")
            child = os.open(
                part,
                os.O_RDONLY
                | flags["O_DIRECTORY"]
                | flags["O_NOFOLLOW"]
                | flags["O_CLOEXEC"],
                dir_fd=current,
            )
            descriptors.append(child)
            opened = os.fstat(child)
            if _identity(observed) != _identity(opened):
                raise ValueError(f"directory binding changed while opening {relative}")
            bindings.append((current, part, _identity(opened)))
            current = child

        name = parts[-1]
        observed_file = os.stat(name, dir_fd=current, follow_symlinks=False)
        if not stat.S_ISREG(observed_file.st_mode):
            raise ValueError(f"repository input is not a regular file: {relative}")
        file_fd = os.open(
            name,
            os.O_RDONLY | flags["O_NOFOLLOW"] | flags["O_NONBLOCK"] | flags["O_CLOEXEC"],
            dir_fd=current,
        )
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or _identity(before) != _identity(observed_file):
            raise ValueError(f"file binding changed while opening {relative}")
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError(f"repository input exceeds {MAX_FILE_BYTES} bytes: {relative}")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(65_536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError(f"repository input exceeds {MAX_FILE_BYTES} bytes: {relative}")
        after = os.fstat(file_fd)
        if _snapshot(before) != _snapshot(after):
            raise ValueError(f"repository input changed while reading: {relative}")
        live_file = os.stat(name, dir_fd=current, follow_symlinks=False)
        if _snapshot(after) != _snapshot(live_file):
            raise ValueError(f"file namespace binding changed while reading: {relative}")
        live_root = os.lstat(os.fspath(root))
        if _identity(live_root) != root_identity or not stat.S_ISDIR(live_root.st_mode):
            raise ValueError("repository root binding changed while reading")
        for parent_fd, part, expected in bindings:
            live = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if _identity(live) != expected or not stat.S_ISDIR(live.st_mode):
                raise ValueError(f"directory namespace binding changed while reading: {relative}")
        return b"".join(chunks)
    except (OSError, TypeError, ValueError, NotImplementedError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(str(exc)) from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def decode_text(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} is not UTF-8: {exc}") from exc


def validate_json_limits(value: Any) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError(f"JSON exceeds {MAX_JSON_NODES} nodes")
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"JSON exceeds depth {MAX_JSON_DEPTH}")
        if isinstance(current, str):
            if len(current) > MAX_JSON_STRING_LENGTH:
                raise ValueError(
                    f"JSON string exceeds {MAX_JSON_STRING_LENGTH} characters"
                )
        elif isinstance(current, dict):
            for key, item in current.items():
                if len(key) > MAX_JSON_STRING_LENGTH:
                    raise ValueError("JSON key is too long")
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def parse_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        value = json.loads(
            decode_text(raw, label),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, DuplicateKeyError, RecursionError, ValueError) as exc:
        raise ValueError(f"{label} is invalid JSON: {exc}") from exc
    validate_json_limits(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} JSON must contain an object")
    return value


def exact_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict) or set(value) != expected:
        errors.append(f"{label} has unsupported or missing fields")
        return False
    return True


def validate_task_index(tasks: Any, errors: list[str]) -> None:
    if not isinstance(tasks, list) or [item.get("id") for item in tasks if isinstance(item, dict)] != EXPECTED_TASK_IDS:
        errors.append("Task evidence index must contain T01-T09 exactly once in order")
        return
    common = {
        "id",
        "title",
        "issue_url",
        "issue_state",
        "issue_state_reason",
        "plan_or_intent_url",
        "receipt_url",
        "pull_request",
        "revision_evidence_class",
        "reviewed_head",
        "reviewed_tree",
        "merge_commit",
        "merge_tree",
        "parents",
        "checks",
    }
    for entry in tasks:
        task_id = entry["id"]
        if not exact_keys(entry, common, f"{task_id} evidence", errors):
            continue
        expected = EXPECTED_TASK_EVIDENCE[task_id]
        exact_values = {
            "title": expected["title"],
            "issue_url": f"{REPOSITORY_URL}/issues/{expected['issue']}",
            "issue_state": "CLOSED",
            "issue_state_reason": "COMPLETED",
            "plan_or_intent_url": f"{REPOSITORY_URL}/{expected['plan']}",
            "receipt_url": f"{REPOSITORY_URL}/{expected['receipt']}",
        }
        for field, value in exact_values.items():
            if entry.get(field) != value:
                errors.append(f"{task_id} {field} does not match accepted evidence")
        if task_id in {"T01", "T02"}:
            marker = "not-applicable-external-state-task"
            for field in (
                "pull_request",
                "merge_commit",
                "merge_tree",
            ):
                if entry.get(field) != marker:
                    errors.append(f"{task_id} {field} must explicitly be not applicable")
            if entry.get("parents") != []:
                errors.append(f"{task_id} parents must be empty for an external-state Task")
            if entry.get("revision_evidence_class") != "baseline-pre-actuator-observation":
                errors.append(f"{task_id} revision must be labeled as a baseline observation")
            if entry.get("reviewed_head") != expected["head"]:
                errors.append(f"{task_id} observed baseline commit is invalid")
            if entry.get("reviewed_tree") != expected["tree"]:
                errors.append(f"{task_id} observed baseline tree is invalid")
            checks = entry.get("checks")
            if not exact_keys(checks, {"quality", "conformance"}, f"{task_id} checks", errors):
                continue
            for name in ("quality", "conformance"):
                evidence = checks.get(name)
                expected_check = {
                    "evidence_class": "baseline-pre-actuator-check",
                    "target_commit": expected["head"],
                    "target_tree": expected["tree"],
                    "result": "success",
                    "url": f"{REPOSITORY_URL}/{expected[name]}",
                }
                if evidence != expected_check:
                    errors.append(
                        f"{task_id} {name} must match the exact baseline check evidence"
                    )
            continue

        expected_fields = {
            "pull_request": f"{REPOSITORY_URL}/pull/{expected['pr']}",
            "reviewed_head": expected["head"],
            "reviewed_tree": expected["tree"],
            "merge_commit": expected["merge"],
            "merge_tree": expected["tree"],
            "parents": expected["parents"],
        }
        for field, value in expected_fields.items():
            if entry.get(field) != value:
                errors.append(f"{task_id} {field} does not match accepted evidence")
        if entry.get("revision_evidence_class") != "reviewed-pr-head":
            errors.append(f"{task_id} revision must be labeled as a reviewed PR head")
        checks = entry.get("checks")
        if not exact_keys(checks, {"quality", "conformance"}, f"{task_id} checks", errors):
            continue
        for name in ("quality", "conformance"):
            evidence = checks.get(name)
            if not exact_keys(evidence, {"result", "url"}, f"{task_id} {name}", errors):
                continue
            if evidence.get("result") != "success":
                errors.append(f"{task_id} {name} result must be success")
            expected_url = f"{REPOSITORY_URL}/{expected[name]}"
            if evidence.get("url") != expected_url or ACTION_URL.fullmatch(
                str(evidence.get("url", ""))
            ) is None:
                errors.append(f"{task_id} {name} evidence URL is invalid")


def validate_contracts(
    contracts: Any,
    canonical_contracts: Any,
    snapshots: dict[str, bytes],
    errors: list[str],
) -> None:
    if not isinstance(canonical_contracts, list):
        errors.append("conformance manifest contract inventory is invalid")
        return
    expected_names = {
        item.get("id"): item.get("contract")
        for item in canonical_contracts
        if isinstance(item, dict)
    }
    if not isinstance(contracts, list) or [item.get("id") for item in contracts if isinstance(item, dict)] != EXPECTED_CONTRACT_IDS:
        errors.append("contract disposition must contain K01-K20 exactly once in order")
        return
    fields = {
        "id",
        "contract",
        "status",
        "evidence",
        "advanced",
        "remaining",
        "later_owner",
    }
    for entry in contracts:
        contract_id = entry["id"]
        if not exact_keys(entry, fields, f"{contract_id} disposition", errors):
            continue
        detail = EXPECTED_CONTRACT_DETAILS[contract_id]
        expected_entry = {
            "id": contract_id,
            "contract": expected_names.get(contract_id),
            "status": detail["status"],
            "evidence": detail["evidence"],
            "advanced": detail["advanced"],
            "remaining": detail["remaining"],
            "later_owner": FUTURE_LANES[detail["lane"]],
        }
        if entry != expected_entry:
            errors.append(f"{contract_id} exact reviewed disposition drifted")
        for reference in detail["evidence"]:
            if valid_relative_path(reference) and reference not in snapshots:
                errors.append(
                    f"{contract_id} repository evidence is missing or unreadable: {reference}"
                )


def validate_scenario_action_evidence(
    evidence: Any, scenario_id: str, status_value: str, errors: list[str]
) -> None:
    if not isinstance(evidence, list) or not evidence:
        errors.append(
            f"scenario {scenario_id} {status_value} requires exact scenario-action evidence"
        )
        return
    expected_result = "success" if status_value == "pass" else "failure"
    fields = {
        "command",
        "execution_class",
        "target_commit",
        "target_tree",
        "result",
        "url",
        "observed_at",
    }
    for index, item in enumerate(evidence):
        label = f"scenario {scenario_id} evidence {index}"
        if not exact_keys(item, fields, label, errors):
            continue
        command = item.get("command")
        if (
            not isinstance(command, str)
            or not command.strip()
            or len(command) > 4096
            or any(unicodedata.category(character).startswith("C") for character in command)
            or PRIVATE_PATH.search(command)
            or SECRET.search(command)
        ):
            errors.append(f"{label} command must be a bounded public exact action")
        if item.get("execution_class") not in ACTION_EVIDENCE_CLASSES:
            errors.append(f"{label} must distinguish static, runtime, or external-state action")
        for field in ("target_commit", "target_tree"):
            value = item.get(field)
            if SHA.fullmatch(str(value or "")) is None or value == "0" * 40:
                errors.append(f"{label} {field} must be a nonzero exact Git object")
        if item.get("result") != expected_result:
            errors.append(f"{label} result must be {expected_result}")
        if ACTION_URL.fullmatch(str(item.get("url", ""))) is None:
            errors.append(f"{label} URL must be a same-repository durable check URL")
        if ISO_UTC.fullmatch(str(item.get("observed_at", ""))) is None:
            errors.append(f"{label} observed_at must be an exact UTC timestamp")


def validate_scenarios(
    scenarios: Any,
    catalog: dict[str, Any],
    coverage: dict[str, Any],
    summary: Any,
    errors: list[str],
) -> None:
    expected: list[tuple[str, str]] = []
    expected_families: dict[str, dict[str, Any]] = {}
    families = catalog.get("families")
    if not isinstance(families, list):
        errors.append("canonical catalog families are invalid")
        return
    for family in families:
        if not isinstance(family, dict) or not isinstance(family.get("scenarios"), list):
            errors.append("canonical catalog family is invalid")
            return
        family_id = family.get("id")
        title = family.get("title")
        if not isinstance(family_id, str) or not isinstance(title, str):
            errors.append("canonical catalog family identity is invalid")
            return
        expected_families[family_id] = {
            "title": title,
            "total": len(family["scenarios"]),
            "pass": 0,
            "non_pass": len(family["scenarios"]),
            "state": "not-run",
        }
        for scenario in family["scenarios"]:
            if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
                errors.append("canonical catalog scenario identity is invalid")
                return
            expected.append((scenario["id"], family_id))
    coverage_entries = coverage.get("entries")
    if not isinstance(coverage_entries, list):
        errors.append("canonical coverage entries are invalid")
        return
    dispositions = {
        item.get("scenario"): item.get("disposition")
        for item in coverage_entries
        if isinstance(item, dict)
    }
    actual_ids = [
        item.get("scenario") for item in scenarios if isinstance(item, dict)
    ] if isinstance(scenarios, list) else []
    if actual_ids != [item[0] for item in expected] or len(actual_ids) != len(set(actual_ids)):
        errors.append("scenario inventory must exactly match the 136 canonical catalog IDs")
        return
    fields = {"scenario", "family", "scope_disposition", "status", "evidence"}
    status_counts: Counter[str] = Counter()
    family_counts: dict[str, dict[str, int]] = {
        family: {"pass": 0, "non_pass": 0} for family in expected_families
    }
    for entry, (scenario_id, family_id) in zip(scenarios, expected):
        if not exact_keys(entry, fields, f"scenario {scenario_id}", errors):
            continue
        if entry.get("family") != family_id:
            errors.append(f"scenario {scenario_id} family does not match the catalog")
        if entry.get("scope_disposition") != dispositions.get(scenario_id):
            errors.append(f"scenario {scenario_id} scope disposition does not match coverage")
        status_value = entry.get("status")
        evidence = entry.get("evidence")
        if status_value not in ALLOWED_SCENARIO_STATES:
            errors.append(f"scenario {scenario_id} has an unsupported evidence state")
            continue
        status_counts[status_value] += 1
        if status_value == "pass":
            family_counts[family_id]["pass"] += 1
            validate_scenario_action_evidence(
                evidence, scenario_id, status_value, errors
            )
        else:
            family_counts[family_id]["non_pass"] += 1
            if status_value == "fail":
                validate_scenario_action_evidence(
                    evidence, scenario_id, status_value, errors
                )
            elif status_value == "not-run" and evidence != []:
                errors.append(
                    f"scenario {scenario_id} not-run evidence must remain an empty result list"
                )
        if status_value != "not-run":
            errors.append(
                f"T10 candidate scenario {scenario_id} must remain exactly not-run"
            )

    successful = sum(counts["pass"] for counts in family_counts.values())
    non_pass = sum(counts["non_pass"] for counts in family_counts.values())
    for family_id, expected_summary in expected_families.items():
        counts = family_counts[family_id]
        expected_summary["pass"] = counts["pass"]
        expected_summary["non_pass"] = counts["non_pass"]
        expected_summary["state"] = (
            "pass" if counts["pass"] == expected_summary["total"] else "not-run"
        )
    expected_summary = {
        "successful_scenarios": successful,
        "non_pass_scenarios": non_pass,
        "states": dict(status_counts),
        "families": expected_families,
    }
    if summary != expected_summary:
        errors.append("scenario summary does not match per-scenario evidence states")
    if successful != 0 or non_pass != 136 or status_counts != Counter({"not-run": 136}):
        errors.append("T10 candidate must contain exactly 136 not-run scenario records")


def validate_document_bindings(
    bindings: Any, snapshots: dict[str, bytes], errors: list[str]
) -> None:
    expected_paths = [ACCEPTANCE_DOC_PATH, SCORECARD_DOC_PATH]
    if not isinstance(bindings, list) or [
        item.get("path") for item in bindings if isinstance(item, dict)
    ] != expected_paths:
        errors.append("document bindings must contain the acceptance record and scorecard")
        return
    for entry in bindings:
        if not exact_keys(entry, {"path", "sha256"}, "document binding", errors):
            continue
        path = entry["path"]
        actual = hashlib.sha256(snapshots[path]).hexdigest()
        if entry.get("sha256") != actual:
            errors.append(f"document digest mismatch: {path}")


def validate_live_documents(
    snapshots: dict[str, bytes], phase1: dict[str, Any], errors: list[str]
) -> None:
    texts: dict[str, str] = {}
    for path in (ACCEPTANCE_DOC_PATH, SCORECARD_DOC_PATH, README_PATH, LIMITATIONS_PATH):
        try:
            texts[path] = decode_text(snapshots[path], path)
        except ValueError as exc:
            errors.append(str(exc))
            texts[path] = ""
    combined = "\n".join(texts.values())
    required_markers = (
        "Phase 1 portable-core acceptance candidate",
        "implementation-complete gate",
        "Phase 1 portable-core implementation is complete in that exact tree",
        "exact-head `quality` and `conformance` checks",
        "no blocking finding remains",
        "durable owner acceptance remains pending merge and exact post-merge receipt",
        "overall repository implementation remains incomplete",
        "`release_blocked` remains `true`",
        "post-merge receipt",
        "not installable",
        "not a parity release",
    )
    for marker in required_markers:
        if marker not in combined:
            errors.append(f"Phase 1 documentation marker is missing: {marker}")
    per_document_status = (
        "Phase 0 is complete.",
        "This exact T10 tree is the **Phase 1 portable-core acceptance candidate**.",
        "When its exact-head `quality` and `conformance` checks are green and no blocking finding remains, the Phase 1 portable-core implementation is complete in that exact tree; durable owner acceptance remains pending merge and exact post-merge receipt.",
        "overall repository implementation remains incomplete",
        "not installable",
        "not a parity release",
        "`release_blocked` remains `true`",
    )
    for path in (README_PATH, LIMITATIONS_PATH):
        normalized = " ".join(texts[path].split())
        for marker in per_document_status:
            if marker not in normalized:
                errors.append(f"{path} status marker is missing: {marker}")
    forbidden = (
        "repository implementation is complete",
        "`release_blocked` is `false`",
        "all 136 scenarios pass",
        "full parity is complete",
        "Phase 1 portable-core implementation is complete in this reviewed T10 tree",
    )
    for marker in forbidden:
        if marker in combined:
            errors.append(f"unsupported completion claim is present: {marker}")
    scorecard = texts[SCORECARD_DOC_PATH]
    acceptance = texts[ACCEPTANCE_DOC_PATH]
    summary = phase1.get("summary")
    families = summary.get("families") if isinstance(summary, dict) else None
    if not isinstance(families, dict):
        errors.append("scenario summary families must be an object")
        families = {}
    for family_id, family in families.items():
        if not isinstance(family, dict):
            errors.append(f"scorecard family summary is invalid: {family_id}")
            continue
        row = (
            f"| {family_id} | {str(family.get('title', '')).replace('`', '')} | "
            f"{family.get('total')} | {family.get('pass')} | "
            f"{family.get('non_pass')} | `not-run` |"
        )
        normalized = scorecard.replace("`AGENTS.md`", "AGENTS.md")
        if row not in normalized:
            errors.append(f"scorecard family row is not synchronized: {family_id}")
    scenarios = phase1.get("scenarios")
    for entry in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(entry, dict):
            continue
        row = (
            f"| {entry.get('scenario')} | {entry.get('family')} | "
            f"`{entry.get('scope_disposition')}` | `{entry.get('status')}` | "
            "none; exact action not run |"
        )
        if scorecard.count(row) != 1:
            errors.append(
                f"scorecard scenario row is not synchronized: {entry.get('scenario')}"
            )
    contracts = phase1.get("contracts")
    for entry in contracts if isinstance(contracts, list) else []:
        if not isinstance(entry, dict):
            continue
        later_owner = entry.get("later_owner")
        lane = later_owner.get("lane") if isinstance(later_owner, dict) else ""
        owner_state = (
            later_owner.get("state") if isinstance(later_owner, dict) else ""
        )
        row = (
            f"| {entry.get('id')} | `{entry.get('status')}` | "
            f"{entry.get('advanced')} | {entry.get('remaining')} | "
            f"`{lane}` (`{owner_state}`) |"
        )
        if scorecard.count(row) != 1:
            errors.append(
                f"scorecard exact contract row is not synchronized: {entry.get('id')}"
            )
    tasks = phase1.get("task_index")
    for entry in tasks if isinstance(tasks, list) else []:
        if not isinstance(entry, dict):
            continue
        task_id = entry.get("id")
        required = [
            f"| {task_id} |",
            str(entry.get("issue_url", "")),
            str(entry.get("plan_or_intent_url", "")),
            str(entry.get("receipt_url", "")),
            str(entry.get("reviewed_head", "")),
        ]
        if task_id in {"T01", "T02"}:
            checks = entry.get("checks")
            required.append(str(entry.get("reviewed_tree", "")))
            if isinstance(checks, dict):
                required.extend(
                    str(checks.get(name, {}).get("url", ""))
                    for name in ("quality", "conformance")
                    if isinstance(checks.get(name), dict)
                )
        else:
            required.append(str(entry.get("pull_request", "")))
        if any(marker not in acceptance for marker in required):
            errors.append(f"acceptance document Task row is not synchronized: {task_id}")
    for path, text in texts.items():
        if PRIVATE_PATH.search(text) or SECRET.search(text):
            errors.append(f"{path} contains a private-path or secret-shaped value")


def validate_ownership_and_workflow(
    ownership: dict[str, Any], workflow_text: str, errors: list[str]
) -> None:
    phase = ownership.get("phase")
    if not isinstance(phase, dict) or phase.get("release_blocked") is not True:
        errors.append("ownership phase release_blocked must remain true")
    tasks = ownership.get("tasks")
    active = [
        item
        for item in tasks
        if isinstance(item, dict) and item.get("state") == "active"
    ] if isinstance(tasks, list) else []
    if len(active) != 1 or active[0].get("id") != "T10":
        errors.append("T10 must be the sole active ownership Task")
    else:
        task = active[0]
        if task.get("branch") != "codex/phase-1-acceptance":
            errors.append("T10 branch is incorrect")
        if task.get("base_commit") != BASE_COMMIT or task.get("base_tree") != BASE_TREE:
            errors.append("T10 exact Task base is incorrect")
        owned = [
            item.get("path")
            for item in task.get("owned_paths", [])
            if isinstance(item, dict)
        ]
        if owned != T10_OWNED_PATHS:
            errors.append("T10 owned paths are not the exact reviewed 12-path boundary")
    if isinstance(tasks, list):
        owners: Counter[str] = Counter(
            item.get("path")
            for task in tasks
            if isinstance(task, dict)
            for item in task.get("owned_paths", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        )
        duplicates = sorted(path for path, count in owners.items() if count != 1)
        if duplicates:
            errors.append("ownership paths overlap: " + ", ".join(duplicates))
    policy = ownership.get("policy")
    if not isinstance(policy, dict):
        errors.append("ownership policy is missing")
        return
    if policy.get("required_jobs") != ["quality", "conformance"]:
        errors.append("required job contexts must remain quality and conformance")
    commands = policy.get("required_quality_commands")
    if not isinstance(commands, list) or commands.count(ACCEPTANCE_COMMAND) != 1:
        errors.append("Phase 1 acceptance checker must be registered exactly once")
    if workflow_text.count(f"run: {ACCEPTANCE_COMMAND}") != 1:
        errors.append("Phase 1 acceptance checker must be reachable exactly once from quality")
    if "  quality:\n" not in workflow_text or "  conformance:\n" not in workflow_text:
        errors.append("required job contexts must remain quality and conformance")


def validate_compatibility_manifest(
    manifest: dict[str, Any], snapshots: dict[str, bytes], errors: list[str]
) -> None:
    if hashlib.sha256(snapshots[MANIFEST_PATH]).hexdigest() != COMPATIBILITY_MANIFEST_SHA256:
        errors.append("Phase 0 compatibility manifest must remain exact and pin-fresh")
    if manifest.get("results") != [] or manifest.get("release_blocked") is not True:
        errors.append("conformance manifest must remain empty and release-blocked")
    invariants = manifest.get("invariants")
    if not isinstance(invariants, dict) or invariants.get("digest") != INVARIANT_DIGEST:
        errors.append("conformance manifest invariant digest drifted")


def validate_invariants(agents_text: str, errors: list[str]) -> None:
    rows: list[tuple[str, str]] = []
    for line in agents_text.splitlines():
        match = INVARIANT_ROW.fullmatch(line)
        if match:
            rows.append((match.group(1), match.group(2)))
    if [item[0] for item in rows] != [f"I{number:02d}" for number in range(1, 14)]:
        errors.append("AGENTS.md must contain I01-I13 exactly once in order")
        return
    canonical = "".join(f"{identifier}\t{statement}\n" for identifier, statement in sorted(rows))
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != INVARIANT_DIGEST:
        errors.append("AGENTS.md invariant digest drifted")


def validate_repository(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    snapshots: dict[str, bytes] = {}
    for relative in REQUIRED_INPUT_PATHS:
        try:
            snapshots[relative] = read_regular_bytes(root, relative)
        except ValueError as exc:
            label = (
                "Phase 1 acceptance record" if relative == PHASE1_PATH else relative
            )
            errors.append(f"cannot read {label}: {exc}")
    if len(snapshots) != len(REQUIRED_INPUT_PATHS):
        return errors

    parsed: dict[str, dict[str, Any]] = {}
    for relative in (
        PHASE1_PATH,
        RELEASE_RESULTS_PATH,
        CATALOG_PATH,
        COVERAGE_PATH,
        MANIFEST_PATH,
        OWNERSHIP_PATH,
    ):
        try:
            parsed[relative] = parse_json(snapshots[relative], relative)
        except ValueError as exc:
            errors.append(str(exc))
    if len(parsed) != 6:
        return errors

    phase1 = parsed[PHASE1_PATH]
    phase1_text = decode_text(snapshots[PHASE1_PATH], PHASE1_PATH)
    if PRIVATE_PATH.search(phase1_text) or SECRET.search(phase1_text):
        errors.append("Phase 1 acceptance record contains private-path or secret-shaped data")
    expected_top = {
        "schema",
        "repository",
        "phase",
        "task",
        "issue_url",
        "task_base",
        "compatibility_layer",
        "evidence_classes",
        "governance",
        "catalog",
        "task_index",
        "contracts",
        "scenarios",
        "summary",
        "later_handoffs",
        "document_bindings",
        "completion",
    }
    exact_keys(phase1, expected_top, "Phase 1 acceptance record", errors)
    if (
        phase1.get("schema") != "phase-1-acceptance/v1"
        or phase1.get("repository") != REPOSITORY
        or phase1.get("phase") != "phase-1"
        or phase1.get("task") != "T10"
        or phase1.get("issue_url") != f"{REPOSITORY_URL}/issues/12"
    ):
        errors.append("Phase 1 acceptance identity is invalid")
    if phase1.get("task_base") != {
        "commit": BASE_COMMIT,
        "tree": BASE_TREE,
        "source": "accepted-main-after-T09",
    }:
        errors.append("Phase 1 acceptance exact Task base is invalid")
    expected_compatibility = {
        "phase0_manifest": {
            "path": MANIFEST_PATH,
            "sha256": COMPATIBILITY_MANIFEST_SHA256,
            "state": "unchanged-pin-fresh",
            "selected_pin": "docs/context/pins/PIN-0001.context-pin.v1.json",
        },
        "replan_url": f"{REPOSITORY_URL}/issues/12#issuecomment-5419726866",
        "phase1_discovery": [
            README_PATH,
            ".github/scripts/check-phase1-acceptance.py",
            OWNERSHIP_PATH,
            WORKFLOW_PATH,
        ],
    }
    if phase1.get("compatibility_layer") != expected_compatibility:
        errors.append("Phase 0 compatibility and standalone discovery record drifted")
    if phase1.get("evidence_classes") != EXPECTED_EVIDENCE_CLASSES:
        errors.append("pre-merge, post-merge, and later evidence classes drifted")

    governance = phase1.get("governance")
    expected_governance = {
        "main": {"commit": BASE_COMMIT, "tree": BASE_TREE},
        "ruleset": {
            "id": 21254123,
            "name": "solo-fast main protection",
            "enforcement": "active",
            "target": "refs/heads/main",
            "observed_on": "2026-08-26",
            "receipt_url": f"{REPOSITORY_URL}/issues/4#issuecomment-5388863497",
            "rules": [
                "deletion",
                "non_fast_forward",
                "pull_request",
                "required_status_checks",
            ],
            "required_approving_reviews": 0,
            "required_checks": [
                {"context": "quality", "integration_id": 15368},
                {"context": "conformance", "integration_id": 15368},
            ],
            "strict_required_status_checks_policy": False,
        },
    }
    if governance != expected_governance:
        errors.append("accepted main or Ruleset evidence snapshot drifted")

    catalog = parsed[CATALOG_PATH]
    coverage = parsed[COVERAGE_PATH]
    catalog_binding = phase1.get("catalog")
    expected_catalog_binding = {
        "path": CATALOG_PATH,
        "sha256": hashlib.sha256(snapshots[CATALOG_PATH]).hexdigest(),
        "coverage_path": COVERAGE_PATH,
        "coverage_sha256": hashlib.sha256(snapshots[COVERAGE_PATH]).hexdigest(),
        "scenario_count": 136,
        "family_count": 14,
    }
    if catalog_binding != expected_catalog_binding:
        errors.append("Phase 1 catalog or coverage binding drifted")
    catalog_families = catalog.get("families")
    if (
        catalog.get("scenario_count") != 136
        or not isinstance(catalog_families, list)
        or len(catalog_families) != 14
    ):
        errors.append("canonical catalog must contain 136 scenarios in 14 families")

    validate_task_index(phase1.get("task_index"), errors)
    validate_contracts(
        phase1.get("contracts"),
        parsed[MANIFEST_PATH].get("contracts"),
        snapshots,
        errors,
    )
    validate_scenarios(
        phase1.get("scenarios"),
        catalog,
        coverage,
        phase1.get("summary"),
        errors,
    )
    validate_document_bindings(
        phase1.get("document_bindings"), snapshots, errors
    )

    handoffs = phase1.get("later_handoffs")
    expected_areas = [
        "custom-agents-and-role-runtime",
        "execution-envelope-and-loop-events",
        "hooks-and-codex-exec-adapter",
        "installer-upgrade-and-live-task-ritual",
        "consent-feedback-transport",
        "clean-adopter-e2e-and-full-parity-release",
    ]
    expected_handoffs = []
    for area in expected_areas:
        lane_key = (
            "repository-release"
            if area == "clean-adopter-e2e-and-full-parity-release"
            else "portable-residual"
        )
        expected_handoffs.append(
            {
                "area": area,
                "state": "task-not-created",
                "later_owner": FUTURE_LANES[lane_key],
            }
        )
    if handoffs != expected_handoffs:
        errors.append("later Phase 1 handoffs must remain explicit and unactivated")

    completion = phase1.get("completion")
    expected_completion = {
        "phase0_complete": True,
        "phase1_portable_core": "pre-merge-candidate",
        "repository_complete": False,
        "release_blocked": True,
        "release_result_count": 0,
        "release_results": [],
        "owner_merge_required": True,
        "post_merge_receipt_required": True,
    }
    if completion != expected_completion:
        errors.append("Phase 1 completion boundary is invalid")

    release = parsed[RELEASE_RESULTS_PATH]
    if (
        release.get("schema") != "conformance-results/v1"
        or release.get("result_count") != 0
        or release.get("results") != []
        or release.get("release_blocked") is not True
        or release.get("catalog")
        != {"path": CATALOG_PATH, "sha256": expected_catalog_binding["sha256"]}
    ):
        errors.append("release result store must remain empty and blocked")

    validate_compatibility_manifest(parsed[MANIFEST_PATH], snapshots, errors)
    try:
        workflow_text = decode_text(snapshots[WORKFLOW_PATH], WORKFLOW_PATH)
        agents_text = decode_text(snapshots[AGENTS_PATH], AGENTS_PATH)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    validate_ownership_and_workflow(parsed[OWNERSHIP_PATH], workflow_text, errors)
    validate_invariants(agents_text, errors)
    validate_live_documents(snapshots, phase1, errors)
    return errors


def main() -> int:
    try:
        errors = validate_repository(Path.cwd())
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        RecursionError,
    ) as exc:
        errors = [f"bounded validation failed: {exc}"]
    if errors:
        print(f"phase1-acceptance: FAIL — {len(errors)} finding(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "phase1-acceptance: PASS — T01-T09 evidence, K01-K20 disposition, "
        "136 not-run scenario records, and the release blocker are exact"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
