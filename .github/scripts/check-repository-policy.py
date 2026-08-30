#!/usr/bin/env python3
"""Validate live repository semantics against reviewed Phase/Task ownership."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


ROOT_MANIFEST = ".github/governance/phase-task-ownership.v1.json"
CONFORMANCE_MANIFEST = "tests/conformance/manifest.json"
COVERAGE = "tests/conformance/coverage.json"
CI_WORKFLOW = ".github/workflows/ci.yml"
ACCEPTED_PHASE0_COMMIT = "32615344ad4f0310948bc59d234a84718741788a"
ACCEPTED_PHASE0_TREE = "33259721ec9f378fa67392ef8e1c7645db1321f9"
ACCEPTED_PHASE1_COMMIT = "36c7eabecf7a56eb2a1c2c8f2c4d8fcb371c31c2"
ACCEPTED_PHASE1_TREE = "1c1f46ad20dd289a713663c84eaf1dbb62840deb"
PHASE2_EPIC = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/22"
T11_RECORD = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
T11_BRANCH = "codex/phase-2-minimal-execution-slice"
HISTORICAL_PHASE1_CHECKER = ".github/scripts/check-phase1-acceptance.py"
HISTORICAL_PHASE1_CHECKER_BLOB = "9e8cccbc824efbb11756ac72c5e1e5ec8726ef4d"
HISTORICAL_PHASE1_CHECKER_SHA256 = (
    "fd0bee66f857601b352cee62eb0f71f2a7f33b507bdb31c5f84e80cbfd64a9de"
)
FROZEN_PHASE1_WRAPPER = ".github/scripts/check-phase1-accepted-snapshot.py"
FROZEN_PHASE1_WRAPPER_SHA256 = (
    "fbbe99b079708db62aeb4674b30640433536c251d75751b4b7d7cee27e2cbc10"
)
FROZEN_PHASE1_COMMAND = f"python3 -I {FROZEN_PHASE1_WRAPPER}"
RUNTIME_CONTRACT_CHECKER = ".github/scripts/check-runtime-contracts.py"
RUNTIME_CONTRACT_CHECKER_SHA256 = (
    "616ea658a41749f8dd72816f81be082531b23a6fe48d5947a6824a2295a598f1"
)
RUNTIME_CONTRACT_COMMAND = f"python3 -I {RUNTIME_CONTRACT_CHECKER}"
RUNTIME_ADAPTER = ".github/scripts/codex-exec-adapter.py"
RUNTIME_ADAPTER_SHA256 = (
    "7c54a3414d78d8c9a0cac5cf2f6e53655c1f0d2c3993e7737aced886f77f2c22"
)
RUNTIME_RECEIPT_ACTUATOR = ".github/scripts/post-runtime-receipt.py"
RUNTIME_RECEIPT_ACTUATOR_SHA256 = (
    "881ba721357305af66232949d4fd8ef49dcb0d641a094810511cc3b3d4bbe815"
)
TARGET_REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
REVIEWED_INVARIANT_DIGEST = (
    "a084a123e16d2fd42619b09161efdaf49bda0ea0ca4a1e076254bd1902aa63f6"
)
HIERARCHY_AGREEMENT_PATH = (
    "docs/agreements/adr/ADR-0005-issue-graph-authority.md"
)
REPOSITORY_COMPLETION_PATH = "docs/agreements/repository-completion.md"
KNOWN_LIMITATIONS_PATH = "docs/known-limitations.md"
HIERARCHY_AGREEMENT_ISSUE = (
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7"
)
REVIEWED_HIERARCHY_AGREEMENT_SHA256 = (
    "2b33ba6b6b51cf3d88e35c6f8722bec7ba1406aabd0eed4e6657af9a96293b75"
)
REVIEWED_REPOSITORY_COMPLETION_SHA256 = (
    "c1cf6dbb1efd0438f1387b33416743433fb94bf376a4c0fa9ecf76a8da3f880d"
)
CANONICAL_I02 = (
    "The Issue graph (repository initiative / Epic set -> Epic issue -> Task issue "
    "-> PR -> commits, checks, and evidence) is canonical; a GitHub Projects board "
    "is an optional projection and never outranks it."
)
CANONICAL_HIERARCHY = (
    "Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> "
    "commits, checks, and evidence"
)
PROJECTS_PROJECTION = (
    "A GitHub Projects board is an optional projection. It never outranks the "
    "Issue graph."
)
NO_INDIVIDUAL_COMPLETION = (
    "No individual phase completion constitutes repository-level completion."
)
OVERALL_COMPLETION_CONDITION = (
    "The overall repository implementation remains incomplete until every "
    "required contract has current target-side evidence and a human-reviewed "
    "completion pull request changing `release_blocked` to `false` is merged."
)
REQUIRED_CONTRACT_IDS = [f"K{number:02d}" for number in range(1, 21)]
FORBIDDEN_LIVE_AUTHORITY_MARKERS = (
    "GitHub Project -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.",
    "A GitHub Projects board is authoritative.",
    "Project Record -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.",
    "Phase 1 completion completes the repository.",
)
EXPECTED_INVARIANT_IDS = [f"I{number:02d}" for number in range(1, 14)]
ALLOWED_MODES = {"100644", "100755"}
ALLOWED_TASK_STATES = {"accepted", "active"}
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".codex-log"}

INVARIANT_ROW = re.compile(r"^\|\s*(I\d{2})\s*\|\s*(.*?)\s*\|\s*$")
TASK_ID = re.compile(r"^[A-Z][0-9]{2}$")
BRANCH = re.compile(r"^codex/[a-z0-9][a-z0-9._/-]*$")
RECORD_URL = re.compile(
    r"^https://github\.com/mochan-tk/agentic-dev-kit-for-codex/"
    r"(?:issues|pull)/[1-9][0-9]*$"
)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FULL_ACTION_REF = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)(?:\s+#\s*(\S.*))?$")
USES_TOKEN = re.compile(r'''(?:^|[\s{,])(?:"uses"|'uses'|uses)\s*:''')
QUOTED_MAPPING_KEY = re.compile(r'''(?:"(?:[^"\\]|\\.)*"|'[^']*')\s*:''')
MODEL_SLUG = re.compile(r"\bgpt-[a-z0-9.-]+", re.IGNORECASE)

CI_PREAMBLE = """name: ci

on:
  pull_request:
  push:
    branches: [main]

permissions: {}

# NON-EXECUTABLE Phase 0 compatibility markers; isolated steps below are authoritative.
# run: python3 .github/scripts/check-phase0-contracts.py
# run: python3 .github/scripts/check-repository-policy.py
jobs:
"""
REVIEWED_QUALITY_ANCHORS = [
    "python3 -I .github/scripts/check-phase0-contracts.py",
    "python3 -I .github/scripts/check-repository-policy.py",
    "python3 -I .github/scripts/install-ci-tools.py --lock "
    ".github/governance/ci-tools.lock.v1.json --destination "
    '"$RUNNER_TEMP/agentic-ci-tools" --check-repository',
    "python3 -I .github/scripts/conformance-catalog.py check",
    "bash .github/scripts/check-action-pins.sh",
    "bash .github/scripts/tests/test-action-pins.sh",
    "bash .github/scripts/check-workflow-permissions.sh",
    "bash .github/scripts/tests/test-workflow-permissions.sh",
    "python3 -I -m compileall -q .github/scripts tests/conformance",
]
REQUIRED_QUALITY_GUARD_PREFIX = REVIEWED_QUALITY_ANCHORS[:2]
CANONICAL_CONFORMANCE_DISCOVERY = (
    "python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'"
)
REVIEWED_CONFORMANCE_ANCHORS = [CANONICAL_CONFORMANCE_DISCOVERY]
DIRECT_COMMAND = re.compile(
    r"^(python3 -I|bash) ((?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\.(?:py|sh))$"
)
GOVERNED_FILE = re.compile(r"^(?:check-|check_|test-|test_).+\.(?:py|sh)$")
DISCOVERABLE_CONFORMANCE_TEST = re.compile(r"^test_[A-Za-z0-9_]+\.py$")
EXPECTED_T11_PATHS = (
    ".codex/agents/task_supervisor.toml",
    ".codex/agents/task_verifier.toml",
    ".codex/agents/task_worker.toml",
    ".github/ISSUE_TEMPLATE/ai-task.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/governance/codex-runtime-profile.v1.json",
    ".github/governance/ledger-contracts.v1.json",
    ".github/governance/phase-task-ownership.v1.json",
    ".github/scripts/check-ledger-templates.py",
    FROZEN_PHASE1_WRAPPER,
    ".github/scripts/check-repository-policy.py",
    ".github/scripts/check-runtime-contracts.py",
    ".github/scripts/codex-exec-adapter.py",
    ".github/scripts/post-runtime-receipt.py",
    ".github/workflows/ci.yml",
    "README.md",
    "docs/agreements/adr/ADR-0008-minimal-codex-execution-loop.md",
    "docs/agreements/runtime/codex-final-response.v1.schema.json",
    "docs/agreements/runtime/execution-result.v1.schema.json",
    "docs/agreements/runtime/loop-event.v1.schema.json",
    "docs/agreements/runtime/minimal-codex-execution-loop.md",
    "docs/agreements/runtime/runtime-profile.v1.schema.json",
    "docs/agreements/runtime/runtime-receipt.v1.schema.json",
    "docs/agreements/runtime/task-execution-envelope.v1.schema.json",
    "docs/known-limitations.md",
    "tests/conformance/phase1-accepted-snapshot.v1.json",
    "tests/conformance/test_ledger_templates.py",
    "tests/conformance/test_phase1_acceptance.py",
    "tests/conformance/test_phase1_accepted_snapshot.py",
    "tests/conformance/test_repository_policy.py",
    "tests/conformance/test_runtime_receipt.py",
    "tests/conformance/test_runtime_vertical_slice.py",
    "tests/runtime/fixtures/codex-final-response-valid.v1.json",
    "tests/runtime/fixtures/codex-jsonl-interrupted.jsonl",
    "tests/runtime/fixtures/codex-jsonl-valid.jsonl",
    "tests/runtime/fixtures/envelope-valid.v1.json",
    "tests/runtime/fixtures/execution-result-valid.v1.json",
    "tests/runtime/fixtures/fake-codex.py",
    "tests/runtime/fixtures/loop-events-valid.v1.jsonl",
    "tests/runtime/fixtures/representative-task.v1.json",
    "tests/runtime/fixtures/runtime-profile-valid.v1.json",
    "tests/runtime/fixtures/runtime-receipt-valid.v1.json",
)


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate object key {key!r}")
        value[key] = item
    return value


def read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{label} is not valid UTF-8 JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must contain an object")
        return {}
    return value


def git_command(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(arguments, 127, b"", str(exc).encode())


def git_index_entries(root: Path) -> dict[str, str] | None:
    result = git_command(root, "ls-files", "--stage", "-z")
    if result.returncode != 0:
        return None
    entries: dict[str, str] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, _object_id, stage_number = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            return None
        if stage_number != "0" or path in entries:
            return None
        entries[path] = mode
    return entries


def git_tree_entries(root: Path, revision: str = "HEAD") -> dict[str, tuple[str, str]] | None:
    """Enumerate one Git tree NUL-safely as path -> (mode, object type)."""

    result = git_command(root, "ls-tree", "-r", "-z", revision)
    if result.returncode != 0:
        return None
    entries: dict[str, tuple[str, str]] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, _object_id = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            return None
        if path in entries:
            return None
        entries[path] = (mode, object_type)
    return entries


def git_tree_objects(
    root: Path, revision: str
) -> dict[str, tuple[str, str, str]] | None:
    """Enumerate one Git tree as path -> (mode, type, object ID)."""

    result = git_command(root, "ls-tree", "-r", "-z", revision)
    if result.returncode != 0:
        return None
    entries: dict[str, tuple[str, str, str]] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            return None
        if path in entries or not FULL_SHA.fullmatch(object_id):
            return None
        entries[path] = (mode, object_type, object_id)
    return entries


def discover_paths(root: Path, tracked: dict[str, str] | None = None) -> set[str]:
    paths: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.name in {".DS_Store", "Thumbs.db"}:
            continue
        if path.is_file() or path.is_symlink():
            if path.suffix not in {".pyc", ".pyo"}:
                paths.add(relative.as_posix())
    if tracked is not None:
        paths.update(tracked)
    return paths


def filesystem_mode(path: Path) -> str:
    try:
        value = path.lstat().st_mode
    except OSError:
        return "missing"
    if stat.S_ISLNK(value):
        return "120000"
    if not stat.S_ISREG(value):
        return "unsupported"
    return "100755" if value & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else "100644"


def symlink_component(root: Path, relative: str) -> str | None:
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return candidate.relative_to(root).as_posix()
    return None


def valid_relative_path(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    if unicodedata.normalize("NFC", value) != value:
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    pure = PurePosixPath(value)
    if value != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        return False
    return True


def collision_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def validate_path_collisions(
    paths: Iterable[str], label: str, errors: list[str]
) -> None:
    seen: dict[str, str] = {}
    for path in paths:
        key = collision_key(path)
        previous = seen.get(key)
        if previous is not None and previous != path:
            errors.append(
                f"{label} has a Unicode/case path collision: {previous!r} and {path!r}"
            )
        else:
            seen[key] = path


def exact_keys(
    payload: dict[str, Any], expected: set[str], label: str, errors: list[str]
) -> None:
    if set(payload) != expected:
        errors.append(f"{label} has unsupported or missing fields")


def validate_registry_commands(
    commands: Any,
    *,
    field: str,
    anchors: list[str],
    errors: list[str],
) -> list[str]:
    if (
        not isinstance(commands, list)
        or not commands
        or any(not isinstance(item, str) or not item for item in commands)
        or len(commands) != len(set(commands))
    ):
        errors.append(
            f"ownership policy {field} must be a non-empty unique string list"
        )
        return []
    positions: list[int] = []
    for anchor in anchors:
        if commands.count(anchor) != 1:
            errors.append(f"ownership policy {field} is missing a reviewed command anchor")
            continue
        positions.append(commands.index(anchor))
    if positions != sorted(positions):
        errors.append(f"ownership policy {field} changed reviewed command order")
    if (
        field == "required_quality_commands"
        and commands[: len(REQUIRED_QUALITY_GUARD_PREFIX)]
        != REQUIRED_QUALITY_GUARD_PREFIX
    ):
        errors.append(
            "ownership policy required_quality_commands must begin with the "
            "frozen and live policy guards"
        )
    for command in commands:
        if command in anchors:
            continue
        match = DIRECT_COMMAND.fullmatch(command)
        if match is None:
            errors.append(f"ownership policy {field} has an unsafe registry command")
            continue
        interpreter, path = match.groups()
        if (
            path.startswith("-")
            or not valid_relative_path(path)
            or GOVERNED_FILE.fullmatch(PurePosixPath(path).name) is None
        ):
            errors.append(f"ownership policy {field} has an unsafe registry command")
        elif (interpreter == "python3 -I") != path.endswith(".py"):
            errors.append(f"ownership policy {field} interpreter does not match its path")
        elif interpreter == "python3 -I" and re.fullmatch(
            r"check[-_].+\.py", PurePosixPath(path).name
        ) is None:
            errors.append(
                f"ownership policy {field} direct Python commands must be checkers"
            )
    return commands


def validate_registry_reachability(
    paths: set[str], policy: dict[str, Any], errors: list[str]
) -> None:
    """Require every governed checker/test to be directly reachable from CI."""

    quality = policy.get("required_quality_commands")
    conformance = policy.get("required_conformance_commands")
    commands = {
        command
        for registry in (quality, conformance)
        if isinstance(registry, list)
        for command in registry
        if isinstance(command, str)
    }
    canonical_discovery = CANONICAL_CONFORMANCE_DISCOVERY in commands
    for relative in sorted(paths):
        name = PurePosixPath(relative).name
        if relative.startswith("tests/conformance/") and relative.endswith(".py"):
            if (
                PurePosixPath(relative).parent
                != PurePosixPath("tests/conformance")
                or DISCOVERABLE_CONFORMANCE_TEST.fullmatch(name) is None
            ):
                errors.append(
                    "governed conformance Python tests must be top-level canonical "
                    f"test_*.py files: {relative}"
                )
                continue
        if (
            relative.endswith(".py")
            and re.fullmatch(r"test[-_].+\.py", name) is not None
            and not relative.startswith("tests/conformance/")
        ):
            errors.append(
                "governed Python tests must use canonical top-level conformance "
                f"discovery: {relative}"
            )
            continue
        if GOVERNED_FILE.fullmatch(name) is None:
            continue
        if relative == HISTORICAL_PHASE1_CHECKER:
            # The exact accepted T10 checker is intentionally historical. Its
            # bytes and sole reachability through the frozen snapshot wrapper
            # are validated separately; registering it against live HEAD would
            # reintroduce the Phase 1/T10 live-state lock.
            continue
        is_conformance = (
            relative.startswith("tests/conformance/")
            and name.startswith("test_")
            and relative.endswith(".py")
        )
        directly_discovered = (
            is_conformance
            and PurePosixPath(relative).parent == PurePosixPath("tests/conformance")
            and DISCOVERABLE_CONFORMANCE_TEST.fullmatch(name) is not None
        )
        if directly_discovered and canonical_discovery:
            continue
        command = (
            f"python3 -I {relative}"
            if relative.endswith(".py")
            else f"bash {relative}"
        )
        if command in commands:
            continue
        if is_conformance:
            errors.append(f"governed conformance test is not reachable: {relative}")
        else:
            errors.append(f"governed checker or test is not reachable: {relative}")


def validate_execution_root_surfaces(paths: set[str], errors: list[str]) -> None:
    """Reject ambiguous Python and shell files in execution-root directories."""

    fixed_scripts = {
        ".github/scripts/check-phase0-contracts.py",
        ".github/scripts/check-repository-policy.py",
        ".github/scripts/check-action-pins.sh",
        ".github/scripts/check-workflow-permissions.sh",
        ".github/scripts/conformance-catalog.py",
        ".github/scripts/install-ci-tools.py",
        ".github/scripts/codex-exec-adapter.py",
        ".github/scripts/post-runtime-receipt.py",
        ".github/scripts/tests/lib.sh",
    }
    scripts_root = PurePosixPath(".github/scripts")
    tests_root = scripts_root / "tests"
    for relative in sorted(paths):
        pure = PurePosixPath(relative)
        name = pure.name
        if name in {"action.yml", "action.yaml"}:
            errors.append(
                f"local Action metadata is unsupported pending recursive validation: {relative}"
            )
        if (
            relative.endswith(".py")
            and pure.parent == PurePosixPath(".")
            and GOVERNED_FILE.fullmatch(name) is None
        ):
            errors.append(f"Python execution-root shadow surface is forbidden: {relative}")
        if not relative.startswith(".github/scripts/"):
            continue
        if relative in fixed_scripts:
            continue
        valid = False
        if pure.parent == scripts_root:
            valid = re.fullmatch(r"check[-_].+\.(?:py|sh)", name) is not None
        elif pure.parent == tests_root:
            valid = re.fullmatch(r"test[-_].+\.sh", name) is not None
        if not valid:
            if relative.endswith(".py"):
                errors.append(
                    f"Python execution-root shadow surface is forbidden: {relative}"
                )
            errors.append(f"script execution-root surface is unsupported: {relative}")


def validate_manifest(
    payload: dict[str, Any], errors: list[str]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate the manifest and return path->mode plus policy."""

    exact_keys(
        payload,
        {"schema", "repository", "phase", "policy", "tasks"},
        "ownership manifest",
        errors,
    )
    if payload.get("schema") != "phase-task-ownership/v1":
        errors.append("ownership manifest schema must be phase-task-ownership/v1")
    if payload.get("repository") != TARGET_REPOSITORY:
        errors.append("ownership manifest repository is not the target repository")

    phase = payload.get("phase")
    if not isinstance(phase, dict):
        errors.append("ownership phase must be an object")
        phase = {}
    exact_keys(
        phase,
        {"id", "epic", "base_commit", "base_tree", "release_blocked"},
        "ownership phase",
        errors,
    )
    if phase.get("id") != "phase-2":
        errors.append("ownership phase.id must be phase-2")
    if phase.get("epic") != PHASE2_EPIC:
        errors.append("ownership phase.epic must reference Epic issue 22")
    if phase.get("base_commit") != ACCEPTED_PHASE1_COMMIT:
        errors.append("ownership phase base_commit must be the accepted Phase 1 merge")
    if phase.get("base_tree") != ACCEPTED_PHASE1_TREE:
        errors.append("ownership phase base_tree must be the accepted Phase 1 tree")
    if phase.get("release_blocked") is not True:
        errors.append("ownership phase release_blocked must remain true")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("ownership policy must be an object")
        policy = {}
    exact_keys(
        policy,
        {
            "invariant_digest",
            "required_jobs",
            "required_quality_commands",
            "required_conformance_commands",
        },
        "ownership policy",
        errors,
    )
    invariant_value = policy.get("invariant_digest")
    if not isinstance(invariant_value, str) or not re.fullmatch(
        r"[0-9a-f]{64}", invariant_value
    ):
        errors.append("ownership policy invariant_digest must be a SHA-256")
    if invariant_value != REVIEWED_INVARIANT_DIGEST:
        errors.append(
            "ownership policy invariant_digest does not match the reviewed live anchor"
        )
    required_jobs = policy.get("required_jobs")
    if required_jobs != ["quality", "conformance"]:
        errors.append("ownership policy required_jobs must be exactly quality and conformance")
    validate_registry_commands(
        policy.get("required_quality_commands"),
        field="required_quality_commands",
        anchors=REVIEWED_QUALITY_ANCHORS,
        errors=errors,
    )
    validate_registry_commands(
        policy.get("required_conformance_commands"),
        field="required_conformance_commands",
        anchors=REVIEWED_CONFORMANCE_ANCHORS,
        errors=errors,
    )

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("ownership tasks must be a non-empty list")
        tasks = []
    task_ids: list[str] = []
    task_states: dict[str, Any] = {}
    active_branches: list[str] = []
    ownership: dict[str, str] = {}
    modes: dict[str, str] = {}
    manifest_paths: list[str] = []
    transition_records: list[tuple[str, Any, Any, str]] = []
    for index, task in enumerate(tasks):
        label = f"ownership tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{label} must be an object")
            continue
        task_fields = {
            "id",
            "record",
            "state",
            "branch",
            "base_commit",
            "base_tree",
            "owned_paths",
        }
        if frozenset(task) not in {
            frozenset(task_fields),
            frozenset(task_fields | {"path_transitions"}),
        }:
            errors.append(f"{label} has unsupported or missing fields")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            errors.append(f"{label}.id must match one letter and two digits")
            task_id = f"invalid-{index}"
        task_ids.append(task_id)
        record = task.get("record")
        if not isinstance(record, str) or not RECORD_URL.fullmatch(record):
            errors.append(f"{label}.record must be a stable target issue or PR URL")
        state_value = task.get("state")
        if not isinstance(state_value, str) or state_value not in ALLOWED_TASK_STATES:
            errors.append(f"{label}.state is unsupported")
        task_states.setdefault(task_id, state_value)
        branch = task.get("branch")
        if not isinstance(branch, str) or not BRANCH.fullmatch(branch):
            errors.append(f"{label}.branch must use the codex/ prefix")
        elif state_value == "active":
            active_branches.append(branch)
        transition_records.append(
            (task_id, state_value, task.get("path_transitions"), label)
        )
        for field in ("base_commit", "base_tree"):
            value = task.get(field)
            if not isinstance(value, str) or not FULL_SHA.fullmatch(value):
                errors.append(f"{label}.{field} must be a full Git object ID")

        owned_paths = task.get("owned_paths")
        if not isinstance(owned_paths, list) or not owned_paths:
            errors.append(f"{label}.owned_paths must be a non-empty list")
            continue
        observed_task_paths: list[str] = []
        for path_index, entry in enumerate(owned_paths):
            path_label = f"{label}.owned_paths[{path_index}]"
            if not isinstance(entry, dict):
                errors.append(f"{path_label} must be an object")
                continue
            exact_keys(entry, {"path", "mode"}, path_label, errors)
            path = entry.get("path")
            mode = entry.get("mode")
            if not isinstance(path, str) or not valid_relative_path(path):
                errors.append(f"{path_label}.path is not a normalized repository path")
                continue
            observed_task_paths.append(path)
            manifest_paths.append(path)
            if not isinstance(mode, str) or mode not in ALLOWED_MODES:
                errors.append(f"{path_label}.mode is unsupported")
                continue
            if path in ownership:
                errors.append(
                    f"overlapping ownership for {path}: {ownership[path]} and {task_id}"
                )
                continue
            ownership[path] = task_id
            modes[path] = mode
        if observed_task_paths != sorted(observed_task_paths):
            errors.append(f"{label}.owned_paths must be sorted by path")
        if len(observed_task_paths) != len(set(observed_task_paths)):
            errors.append(f"{label}.owned_paths contains duplicate paths")

    for task_id, state_value, transitions, label in transition_records:
        if transitions is None:
            continue
        if not isinstance(transitions, list):
            errors.append(f"{label}.path_transitions must be a list")
            continue
        observed_keys: list[tuple[str, str, str]] = []
        fingerprints: list[str] = []
        task_transition_paths: list[str] = []
        for transition_index, transition in enumerate(transitions):
            transition_label = f"{label}.path_transitions[{transition_index}]"
            if not isinstance(transition, dict):
                errors.append(f"{transition_label} must be an object")
                continue
            operation = transition.get("operation")
            operation_valid = isinstance(operation, str) and operation in {
                "delete",
                "rename",
                "copy",
            }
            if not operation_valid:
                errors.append(f"{transition_label}.operation is unsupported")
                expected_fields = {
                    "operation",
                    "source_path",
                    "source_owner",
                    "source_mode",
                }
            else:
                expected_fields = {
                    "operation",
                    "source_path",
                    "source_owner",
                    "source_mode",
                }
                if operation in {"rename", "copy"}:
                    expected_fields |= {"destination_path", "destination_mode"}
            exact_keys(transition, expected_fields, transition_label, errors)
            source_path = transition.get("source_path")
            source_owner = transition.get("source_owner")
            source_mode = transition.get("source_mode")
            destination_path = transition.get("destination_path", "")
            destination_mode = transition.get("destination_mode")
            if not isinstance(source_path, str) or not valid_relative_path(source_path):
                errors.append(
                    f"{transition_label}.source_path is not a normalized repository path"
                )
                source_path = ""
            if source_owner not in task_ids:
                errors.append(f"{transition_label}.source_owner is not a known Task")
            elif (
                state_value == "active"
                and source_owner != task_id
                and task_states.get(str(source_owner)) != "accepted"
            ):
                errors.append(
                    f"{transition_label}.source_owner must be an accepted Task"
                )
            if not isinstance(source_mode, str) or source_mode not in ALLOWED_MODES:
                errors.append(f"{transition_label}.source_mode is unsupported")
            if operation_valid and operation in {"rename", "copy"}:
                if not isinstance(destination_path, str) or not valid_relative_path(
                    destination_path
                ):
                    errors.append(
                        f"{transition_label}.destination_path is not a normalized repository path"
                    )
                    destination_path = ""
                if (
                    not isinstance(destination_mode, str)
                    or destination_mode not in ALLOWED_MODES
                ):
                    errors.append(f"{transition_label}.destination_mode is unsupported")
                if source_path and destination_path and source_path == destination_path:
                    errors.append(f"{transition_label} source and destination must differ")
                if (
                    state_value == "active"
                    and destination_path
                    and ownership.get(destination_path) != task_id
                ):
                    errors.append(f"{transition_label} destination ownership is not active")
                if (
                    state_value == "active"
                    and destination_path
                    and modes.get(destination_path) != destination_mode
                ):
                    errors.append(f"{transition_label} destination mode does not match ownership")
                if destination_path:
                    task_transition_paths.append(destination_path)
            if (
                state_value == "active"
                and operation_valid
                and operation in {"delete", "rename"}
                and source_path in ownership
            ):
                errors.append(f"{transition_label} source must leave current ownership")
            if (
                state_value == "active"
                and operation == "copy"
                and source_path
                and ownership.get(source_path) != source_owner
            ):
                errors.append(f"{transition_label} copy source must remain with its source owner")
            if source_path:
                task_transition_paths.append(source_path)
            observed_keys.append((str(source_path), str(operation), str(destination_path)))
            fingerprints.append(
                json.dumps(transition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        if observed_keys != sorted(observed_keys):
            errors.append(f"{label}.path_transitions must be sorted")
        if len(fingerprints) != len(set(fingerprints)):
            errors.append(f"{label}.path_transitions contains duplicate transitions")
        validate_path_collisions(
            task_transition_paths, f"{label}.path_transitions", errors
        )
        if state_value == "active":
            duplicate_transition_paths = sorted(
                path
                for path, count in Counter(task_transition_paths).items()
                if count > 1
            )
            if duplicate_transition_paths:
                errors.append(
                    f"{label}.path_transitions contains duplicate source or "
                    "destination path(s): "
                    + ", ".join(duplicate_transition_paths)
                )

    duplicates = sorted(
        identifier for identifier in set(task_ids) if task_ids.count(identifier) > 1
    )
    if duplicates:
        errors.append(f"duplicate ownership task ID(s): {', '.join(duplicates)}")
    if len(active_branches) != len(set(active_branches)):
        errors.append("active ownership tasks must not share a branch")
    active_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("state") == "active"
    ]
    if len(active_tasks) != 1:
        errors.append("ownership manifest must contain exactly one active Task")
    if ROOT_MANIFEST not in ownership:
        errors.append("ownership manifest must own its own path")
    validate_path_collisions(manifest_paths, "ownership manifest", errors)
    return modes, policy


def validate_phase2_frontier(payload: dict[str, Any], errors: list[str]) -> None:
    """Pin the live Phase 2 work order without weakening generic schema tests."""

    tasks_value = payload.get("tasks")
    tasks = tasks_value if isinstance(tasks_value, list) else []
    task_by_id = {
        task.get("id"): task
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    t10 = task_by_id.get("T10")
    if not isinstance(t10, dict) or t10.get("state") != "accepted":
        errors.append("ownership T10 must remain accepted in Phase 2")
    t11 = task_by_id.get("T11")
    if not isinstance(t11, dict):
        errors.append("ownership manifest is missing T11")
        return
    if t11.get("state") != "active":
        errors.append("ownership T11 must be the active Task")
    if t11.get("record") != T11_RECORD:
        errors.append("ownership T11 must reference Issue 23")
    if t11.get("branch") != T11_BRANCH:
        errors.append("ownership T11 branch drifted")
    if t11.get("base_commit") != ACCEPTED_PHASE1_COMMIT:
        errors.append("ownership T11 base_commit drifted")
    if t11.get("base_tree") != ACCEPTED_PHASE1_TREE:
        errors.append("ownership T11 base_tree drifted")
    if t11.get("path_transitions") != []:
        errors.append("ownership T11 path_transitions must remain empty")
    entries = t11.get("owned_paths")
    actual_paths = (
        tuple(
            entry.get("path")
            for entry in entries
            if isinstance(entry, dict)
        )
        if isinstance(entries, list)
        else ()
    )
    if actual_paths != EXPECTED_T11_PATHS:
        errors.append("ownership T11 must declare exactly the reviewed 42 paths")
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) or entry.get("mode") != "100644"
        for entry in entries
    ):
        errors.append("ownership T11 paths must all use mode 100644")


def validate_git_anchor(
    root: Path, commit: str, tree: str, label: str, errors: list[str]
) -> None:
    if not FULL_SHA.fullmatch(commit) or not FULL_SHA.fullmatch(tree):
        return
    exists = git_command(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if exists.returncode != 0:
        errors.append(f"{label} commit object is missing or uncheckable")
        return
    resolved = git_command(root, "rev-parse", f"{commit}^{{tree}}")
    if resolved.returncode != 0 or resolved.stdout.decode("ascii", errors="replace").strip() != tree:
        errors.append(f"{label} tree does not match its commit")
    ancestry = git_command(root, "merge-base", "--is-ancestor", commit, "HEAD")
    if ancestry.returncode != 0:
        errors.append(f"{label} evidence is stale: base is not an ancestor of HEAD")


def validate_git_evidence(root: Path, payload: dict[str, Any], errors: list[str]) -> None:
    phase = payload.get("phase")
    if isinstance(phase, dict):
        validate_git_anchor(
            root,
            str(phase.get("base_commit", "")),
            str(phase.get("base_tree", "")),
            "phase",
            errors,
        )
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict):
                continue
            validate_git_anchor(
                root,
                str(task.get("base_commit", "")),
                str(task.get("base_tree", "")),
                f"task {task.get('id', '?')}",
                errors,
            )


def resolve_execution_context(
    root: Path, environment: Mapping[str, str], errors: list[str]
) -> tuple[str, str] | None:
    """Return (context, effective branch) or fail closed on ambiguous state."""

    head_result = git_command(root, "rev-parse", "HEAD")
    if head_result.returncode != 0:
        errors.append("cannot resolve checked HEAD for Task authorization")
        return None
    head = head_result.stdout.decode("ascii", errors="replace").strip()
    if not FULL_SHA.fullmatch(head):
        errors.append("checked HEAD is not a full Git object ID")
        return None

    actions_value = environment.get("GITHUB_ACTIONS", "")
    github_fields = {
        key: environment.get(key, "")
        for key in (
            "GITHUB_BASE_REF",
            "GITHUB_EVENT_NAME",
            "GITHUB_EVENT_PATH",
            "GITHUB_HEAD_REF",
            "GITHUB_REF",
            "GITHUB_REF_NAME",
            "GITHUB_REF_TYPE",
            "GITHUB_REPOSITORY",
            "GITHUB_SHA",
        )
    }
    if actions_value:
        if actions_value != "true":
            errors.append("GITHUB_ACTIONS must be exactly 'true' when present")
            return None
        if github_fields["GITHUB_SHA"] != head:
            errors.append("GITHUB_SHA does not match checked HEAD")
            return None
        if github_fields["GITHUB_REPOSITORY"] != TARGET_REPOSITORY:
            errors.append("GITHUB_REPOSITORY does not match the governed repository")
            return None
        event = github_fields["GITHUB_EVENT_NAME"]
        if event == "pull_request":
            branch = github_fields["GITHUB_HEAD_REF"]
            if not branch:
                errors.append("GitHub pull_request context is missing GITHUB_HEAD_REF")
                return None
            if github_fields["GITHUB_BASE_REF"] != "main":
                errors.append("GitHub pull_request GITHUB_BASE_REF must be main")
                return None
            if github_fields["GITHUB_REF_TYPE"] != "branch":
                errors.append("GitHub pull_request GITHUB_REF_TYPE must be branch")
                return None
            ref_name_match = re.fullmatch(
                r"([1-9][0-9]*)/merge", github_fields["GITHUB_REF_NAME"]
            )
            if ref_name_match is None:
                errors.append("GitHub pull_request GITHUB_REF_NAME is unsupported")
                return None
            expected_ref = f"refs/pull/{ref_name_match.group(1)}/merge"
            if github_fields["GITHUB_REF"] != expected_ref:
                errors.append(
                    "GitHub pull_request GITHUB_REF does not match GITHUB_REF_NAME"
                )
                return None
            return "pull_request", branch
        if event == "push":
            branch = github_fields["GITHUB_REF_NAME"]
            if (
                not branch
                or github_fields["GITHUB_HEAD_REF"]
                or github_fields["GITHUB_BASE_REF"]
            ):
                errors.append("GitHub push context has ambiguous branch fields")
                return None
            if github_fields["GITHUB_REF_TYPE"] != "branch":
                errors.append("GitHub push context is not a branch ref")
                return None
            reference = github_fields["GITHUB_REF"]
            if reference != f"refs/heads/{branch}":
                errors.append("GitHub push GITHUB_REF does not match GITHUB_REF_NAME")
                return None
            if branch != "main":
                errors.append("live policy supports GitHub push checks only for main")
                return None
            return "main_push", branch
        errors.append(f"unsupported GitHub Actions event for live policy: {event!r}")
        return None

    if any(github_fields.values()):
        errors.append("partial GitHub context is unsupported outside GitHub Actions")
        return None
    branch_result = git_command(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result.returncode != 0:
        errors.append("local live policy requires a symbolic current branch")
        return None
    branch = branch_result.stdout.decode("utf-8", errors="replace").strip()
    if not branch:
        errors.append("local current branch is empty or uncheckable")
        return None
    return ("local_main" if branch == "main" else "local_branch"), branch


def active_task_for_branch(
    payload: dict[str, Any], branch: str, errors: list[str]
) -> dict[str, Any] | None:
    tasks = payload.get("tasks")
    matches = (
        [
            task
            for task in tasks
            if isinstance(task, dict)
            and task.get("state") == "active"
            and task.get("branch") == branch
        ]
        if isinstance(tasks, list)
        else []
    )
    if len(matches) != 1:
        errors.append(
            f"effective branch {branch!r} must match exactly one active ownership Task"
        )
        return None
    return matches[0]


def active_owned_paths(task: dict[str, Any]) -> set[str]:
    entries = task.get("owned_paths")
    if not isinstance(entries, list):
        return set()
    return {
        entry["path"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def authorize_changed_paths(
    task: dict[str, Any], changed_paths: Iterable[str], errors: list[str]
) -> None:
    owned = active_owned_paths(task)
    changes = list(changed_paths)
    validate_path_collisions(changes, "Task diff", errors)
    for path in changes:
        if not valid_relative_path(path):
            errors.append(f"Task diff contains an unsupported path: {path!r}")
        elif path not in owned:
            errors.append(
                f"Task diff path is outside active Task {task.get('id', '?')} ownership: {path}"
            )


def git_diff_entries(
    root: Path,
    arguments: list[str],
    label: str,
    errors: list[str],
) -> list[tuple[str, str]] | None:
    """Return status/path pairs from one NUL-delimited, rename-disabled diff."""

    result = git_command(
        root,
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        *arguments,
        "--",
    )
    if result.returncode != 0:
        errors.append(f"cannot enumerate {label}")
        return None
    fields = result.stdout.split(b"\0")
    if fields and not fields[-1]:
        fields.pop()
    if len(fields) % 2:
        errors.append(f"{label} has malformed NUL-delimited status output")
        return None
    entries: list[tuple[str, str]] = []
    for index in range(0, len(fields), 2):
        try:
            status = fields[index].decode("ascii")
            path = fields[index + 1].decode("utf-8")
        except UnicodeError:
            errors.append(f"{label} contains a non-UTF-8 path or status")
            return None
        if not status:
            errors.append(f"{label} contains an empty change status")
            return None
        entries.append((status, path))
    return entries


def authorize_changed_entries(
    task: dict[str, Any], entries: Iterable[tuple[str, str]], errors: list[str]
) -> None:
    """Authorize additive/modifying entries; deletion and rename stay fail-closed."""

    observed = list(entries)
    for status, path in observed:
        if status == "D":
            errors.append(
                f"Task ownership does not support deletion in this phase: {path}"
            )
        elif status.startswith(("R", "C")):
            errors.append(
                f"Task ownership does not support rename or copy in this phase: {path}"
            )
        elif status not in {"A", "M"}:
            errors.append(
                f"Task diff has unsupported change status {status!r}: {path}"
            )
    authorize_changed_paths(task, (path for _status, path in observed), errors)


def manifest_ownership(payload: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Return structurally usable path ownership without granting on bad fields."""

    ownership: dict[str, tuple[str, str]] = {}
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return ownership
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        entries = task.get("owned_paths")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            mode = entry.get("mode")
            if (
                isinstance(path, str)
                and valid_relative_path(path)
                and isinstance(mode, str)
                and mode in ALLOWED_MODES
                and path not in ownership
            ):
                ownership[path] = (task["id"], mode)
    return ownership


def git_blob_bytes(root: Path, object_id: str) -> bytes | None:
    result = git_command(root, "cat-file", "blob", object_id)
    return result.stdout if result.returncode == 0 else None


def current_regular_bytes(root: Path, relative: str) -> bytes | None:
    if filesystem_mode(root / relative) not in ALLOWED_MODES:
        return None
    if symlink_component(root, relative) is not None:
        return None
    try:
        return (root / relative).read_bytes()
    except OSError:
        return None


def git_blob_object_id(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate_historical_phase1_checker_boundary(
    root: Path,
    payload: dict[str, Any],
    policy: dict[str, Any],
    errors: list[str],
) -> None:
    """Allow exactly one historical checker omission behind its frozen wrapper."""

    tasks = payload.get("tasks")
    usable_tasks = (
        [task for task in tasks if isinstance(task, dict)]
        if isinstance(tasks, list)
        else []
    )
    t10 = next((task for task in usable_tasks if task.get("id") == "T10"), None)
    t11 = next((task for task in usable_tasks if task.get("id") == "T11"), None)
    if t10 is None or t10.get("state") != "accepted":
        errors.append("historical Phase 1 checker exception requires accepted T10")
    if t11 is None or t11.get("state") != "active":
        errors.append("historical Phase 1 checker exception requires active T11")

    def owns(task: dict[str, Any] | None, relative: str) -> bool:
        entries = task.get("owned_paths") if isinstance(task, dict) else None
        return isinstance(entries, list) and any(
            isinstance(entry, dict)
            and entry.get("path") == relative
            and entry.get("mode") == "100644"
            for entry in entries
        )

    if not owns(t10, HISTORICAL_PHASE1_CHECKER):
        errors.append("accepted T10 must retain the historical Phase 1 checker")
    if not owns(t11, FROZEN_PHASE1_WRAPPER):
        errors.append("active T11 must own the frozen Phase 1 wrapper")

    commands = policy.get("required_quality_commands")
    if not isinstance(commands, list):
        return
    historical_command = f"python3 -I {HISTORICAL_PHASE1_CHECKER}"
    if historical_command in commands:
        errors.append("historical Phase 1 checker must not run against live HEAD")
    if commands.count(FROZEN_PHASE1_COMMAND) != 1:
        errors.append("frozen Phase 1 wrapper must be registered exactly once")
    if commands.count(RUNTIME_CONTRACT_COMMAND) != 1:
        errors.append("runtime contract checker must be registered exactly once")

    historical_bytes = current_regular_bytes(root, HISTORICAL_PHASE1_CHECKER)
    if historical_bytes is None:
        errors.append("historical Phase 1 checker is missing or unsafe")
    else:
        if hashlib.sha256(historical_bytes).hexdigest() != HISTORICAL_PHASE1_CHECKER_SHA256:
            errors.append("historical Phase 1 checker digest drifted")
        if git_blob_object_id(historical_bytes) != HISTORICAL_PHASE1_CHECKER_BLOB:
            errors.append("historical Phase 1 checker blob drifted")

    wrapper_bytes = current_regular_bytes(root, FROZEN_PHASE1_WRAPPER)
    if wrapper_bytes is None:
        errors.append("frozen Phase 1 wrapper is missing or unsafe")
        return
    if hashlib.sha256(wrapper_bytes).hexdigest() != FROZEN_PHASE1_WRAPPER_SHA256:
        errors.append("frozen Phase 1 wrapper digest drifted")
    try:
        wrapper = wrapper_bytes.decode("utf-8", errors="strict")
    except UnicodeError:
        errors.append("frozen Phase 1 wrapper is not UTF-8")
        return
    for marker in (
        ACCEPTED_PHASE1_COMMIT,
        ACCEPTED_PHASE1_TREE,
        HISTORICAL_PHASE1_CHECKER,
        HISTORICAL_PHASE1_CHECKER_BLOB,
        HISTORICAL_PHASE1_CHECKER_SHA256,
    ):
        if marker not in wrapper:
            errors.append(
                "frozen Phase 1 wrapper is not tied to the exact accepted checker evidence"
            )
            break


def ast_qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = ast_qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def parse_governed_python(
    root: Path, relative: str, label: str, errors: list[str]
) -> tuple[bytes, ast.Module] | None:
    payload = current_regular_bytes(root, relative)
    if payload is None:
        errors.append(f"{label} is missing or unsafe")
        return None
    try:
        text = payload.decode("utf-8", errors="strict")
        tree = ast.parse(text, filename=relative)
    except (UnicodeError, SyntaxError, ValueError):
        errors.append(f"{label} is not valid bounded UTF-8 Python")
        return None
    return payload, tree


def validate_python_imports(
    tree: ast.Module,
    *,
    direct: set[str],
    from_imports: dict[str, set[str]],
    label: str,
    errors: list[str],
) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in direct or alias.asname is not None:
                    errors.append(f"{label} has an unreviewed import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            allowed = from_imports.get(module, set())
            if (
                node.level != 0
                or not allowed
                or any(alias.name not in allowed or alias.asname is not None for alias in node.names)
            ):
                rendered = module or "<relative>"
                errors.append(f"{label} has an unreviewed from-import: {rendered}")


def dangerous_runtime_call(name: str) -> bool:
    if not name:
        return True
    if name in {"__import__", "eval", "exec", "compile"}:
        return True
    if name.startswith(
        (
            "subprocess.",
            "socket.",
            "urllib.",
            "http.",
            "ftplib.",
            "smtplib.",
            "webbrowser.",
            "asyncio.create_subprocess",
        )
    ):
        return True
    if name.startswith("importlib.") and name not in {
        "importlib.util.spec_from_file_location",
        "importlib.util.module_from_spec",
    }:
        return True
    if name.startswith("os."):
        operation = name.removeprefix("os.").split(".", 1)[0]
        if operation in {"system", "popen", "fork"} or operation.startswith(
            ("exec", "spawn", "posix_spawn")
        ):
            return True
    return False


def canonical_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or node.orelse or len(node.body) != 1:
        return False
    test = node.test
    if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    ):
        return False
    statement = node.body[0]
    if not isinstance(statement, ast.Raise) or not isinstance(statement.exc, ast.Call):
        return False
    outer = statement.exc
    return (
        ast_qualified_name(outer.func) == "SystemExit"
        and not outer.keywords
        and len(outer.args) == 1
        and isinstance(outer.args[0], ast.Call)
        and ast_qualified_name(outer.args[0].func) == "main"
        and not outer.args[0].args
        and not outer.args[0].keywords
    )


def definition_has_eager_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    eager_nodes: list[ast.AST] = [
        *node.decorator_list,
        *node.args.defaults,
        *(value for value in node.args.kw_defaults if value is not None),
    ]
    if node.returns is not None:
        eager_nodes.append(node.returns)
    eager_nodes.extend(
        argument.annotation
        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if argument.annotation is not None
    )
    if node.args.vararg is not None and node.args.vararg.annotation is not None:
        eager_nodes.append(node.args.vararg.annotation)
    if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
        eager_nodes.append(node.args.kwarg.annotation)
    return any(
        isinstance(candidate, ast.Call)
        for eager in eager_nodes
        for candidate in ast.walk(eager)
    )


def validate_import_time_structure(
    tree: ast.Module, label: str, errors: list[str]
) -> None:
    """Reject import-time behavior in adapter/actuator modules."""

    def validate_ctypes_structure(node: ast.ClassDef) -> bool:
        """Allow only the reviewed fixed Darwin kernel-identity record."""

        if (
            node.name != "_DarwinProcBSDInfo"
            or node.decorator_list
            or node.keywords
            or len(node.bases) != 1
            or ast_qualified_name(node.bases[0]) != "ctypes.Structure"
            or len(node.body) != 1
            or not isinstance(node.body[0], ast.Assign)
            or len(node.body[0].targets) != 1
            or not isinstance(node.body[0].targets[0], ast.Name)
            or node.body[0].targets[0].id != "_fields_"
            or not isinstance(node.body[0].value, ast.List)
        ):
            return False
        allowed_scalars = {
            "ctypes.c_char",
            "ctypes.c_int32",
            "ctypes.c_uint32",
            "ctypes.c_uint64",
        }
        names: list[str] = []
        for field in node.body[0].value.elts:
            if (
                not isinstance(field, ast.Tuple)
                or len(field.elts) != 2
                or not isinstance(field.elts[0], ast.Constant)
                or not isinstance(field.elts[0].value, str)
            ):
                return False
            names.append(field.elts[0].value)
            field_type = field.elts[1]
            if ast_qualified_name(field_type) in allowed_scalars:
                continue
            if not (
                isinstance(field_type, ast.BinOp)
                and isinstance(field_type.op, ast.Mult)
                and ast_qualified_name(field_type.left) == "ctypes.c_char"
                and isinstance(field_type.right, ast.Constant)
                and type(field_type.right.value) is int
                and field_type.right.value in {16, 32}
            ):
                return False
        return bool(names) and len(names) == len(set(names))

    def validate_class(node: ast.ClassDef) -> bool:
        if validate_ctypes_structure(node):
            return True
        if (
            node.decorator_list
            or node.keywords
            or any(
                not isinstance(base, ast.Name)
                or base.id not in {"Exception", "NamedTuple"}
                for base in node.bases
            )
        ):
            return False
        for statement in node.body:
            if isinstance(statement, ast.Expr) and isinstance(
                statement.value, ast.Constant
            ) and isinstance(statement.value.value, str):
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if definition_has_eager_call(statement):
                    return False
                continue
            if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Pass)):
                if any(isinstance(item, ast.Call) for item in ast.walk(statement)):
                    return False
                continue
            return False
        return True

    for index, statement in enumerate(tree.body):
        if (
            index == 0
            and isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if definition_has_eager_call(statement):
                errors.append(f"{label} contains import-time function metadata execution")
            continue
        if isinstance(statement, ast.ClassDef):
            if not validate_class(statement):
                errors.append(f"{label} contains import-time class execution")
            continue
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            calls = [item for item in ast.walk(statement) if isinstance(item, ast.Call)]
            if any(ast_qualified_name(call.func) != "re.compile" for call in calls):
                errors.append(f"{label} contains unreviewed import-time assignment execution")
            continue
        if canonical_main_guard(statement):
            continue
        errors.append(f"{label} contains unreviewed import-time executable syntax")


def validate_adapter_native_structure(
    tree: ast.Module, label: str, errors: list[str]
) -> None:
    """Pin native library loads used by capability probes to reviewed constants."""

    observed: list[str | None] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or ast_qualified_name(node.func) != "ctypes.CDLL":
            continue
        if (
            len(node.args) != 1
            or not isinstance(node.args[0], ast.Constant)
            or len(node.keywords) != 1
            or node.keywords[0].arg != "use_errno"
            or not isinstance(node.keywords[0].value, ast.Constant)
            or node.keywords[0].value.value is not True
        ):
            errors.append(f"{label} contains an unreviewed native library load")
            continue
        value = node.args[0].value
        if value is not None and not isinstance(value, str):
            errors.append(f"{label} contains an unreviewed native library load")
            continue
        observed.append(value)
    expected: list[str | None] = [
        None,
        "/usr/lib/libSystem.B.dylib",
        "/usr/lib/libproc.dylib",
        "/usr/lib/libproc.dylib",
    ]
    if sorted(observed, key=lambda value: "" if value is None else value) != sorted(
        expected, key=lambda value: "" if value is None else value
    ):
        errors.append(f"{label} native capability-probe libraries drifted")


def validate_reachable_module_calls(
    tree: ast.Module,
    entrypoints: set[str],
    forbidden_local_calls: set[str],
    label: str,
    errors: list[str],
) -> None:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    pending = list(entrypoints)
    observed: set[str] = set()
    while pending:
        function_name = pending.pop()
        if function_name in observed:
            continue
        function = functions.get(function_name)
        if function is None:
            errors.append(f"{label} is missing reviewed offline entrypoint {function_name}")
            continue
        observed.add(function_name)
        for node in ast.walk(function):
            if isinstance(node, ast.Attribute):
                qualified = ast_qualified_name(node)
                if dangerous_runtime_call(qualified):
                    errors.append(f"{label} reachable code references actuator {qualified}")
            if not isinstance(node, ast.Call):
                continue
            qualified = ast_qualified_name(node.func)
            if dangerous_runtime_call(qualified) or qualified in forbidden_local_calls:
                errors.append(f"{label} reachable code invokes actuator {qualified or '<dynamic>'}")
            if qualified in functions:
                pending.append(qualified)


def validate_offline_runtime_checker_boundary(
    root: Path, errors: list[str]
) -> None:
    """Prove that required CI reaches validation only, never a live actuator."""

    parsed = parse_governed_python(
        root, RUNTIME_CONTRACT_CHECKER, "offline runtime checker", errors
    )
    if parsed is None:
        return
    checker_bytes, checker_tree = parsed
    if hashlib.sha256(checker_bytes).hexdigest() != RUNTIME_CONTRACT_CHECKER_SHA256:
        errors.append("offline runtime checker digest drifted")
    validate_python_imports(
        checker_tree,
        direct={
            "ast",
            "datetime",
            "hashlib",
            "importlib.util",
            "json",
            "math",
            "os",
            "re",
            "stat",
            "sys",
        },
        from_imports={
            "__future__": {"annotations"},
            "pathlib": {"Path"},
            "typing": {"Any", "Dict", "Iterable", "List", "Mapping", "Tuple"},
        },
        label="offline runtime checker",
        errors=errors,
    )
    allowed_runtime_attributes = {
        "adapter.ProcessResult",
        "adapter.REQUIRED_OVERRIDES",
        "adapter.REQUIRED_OVERRIDES.items",
        "adapter.build_live_argv",
        "adapter.doctor_diagnostic_health",
        "adapter.parse_jsonl",
        "adapter.runtime_configuration_intent",
        "adapter.toml_literal",
        "adapter.validate_runtime_argv_policy",
        "adapter.validate_envelope",
        "adapter.validate_execution_result",
        "adapter.validate_final_response",
        "adapter.validate_runtime_profile",
        "adapter.validate_verifier_record",
    }
    for node in ast.walk(checker_tree):
        if isinstance(node, ast.Attribute):
            qualified = ast_qualified_name(node)
            if qualified.startswith(("adapter.", "receipt.")) and qualified not in allowed_runtime_attributes:
                errors.append(
                    f"offline runtime checker references unreviewed runtime callable {qualified}"
                )
        if not isinstance(node, ast.Call):
            continue
        qualified = ast_qualified_name(node.func)
        if dangerous_runtime_call(qualified):
            errors.append(
                f"offline runtime checker invokes a process, network, or dynamic actuator: "
                f"{qualified or '<dynamic>'}"
            )
    import_calls = []
    for node in ast.walk(checker_tree):
        if not isinstance(node, ast.Call) or ast_qualified_name(node.func) != "import_script":
            continue
        if (
            len(node.args) == 4
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and isinstance(node.args[2], ast.Constant)
            and isinstance(node.args[2].value, str)
        ):
            import_calls.append((node.args[1].value, node.args[2].value))
        else:
            import_calls.append(("<dynamic>", "<dynamic>"))
    if sorted(import_calls) != sorted(
        [
            (RUNTIME_ADAPTER, "t11_runtime_adapter"),
        ]
    ):
        errors.append("offline runtime checker dynamic imports drifted")

    imported_specs = (
        (
            RUNTIME_ADAPTER,
            RUNTIME_ADAPTER_SHA256,
            {
                "validate_envelope",
                "validate_execution_result",
                "validate_runtime_profile",
                "validate_verifier_record",
                "validate_final_response",
                "parse_jsonl",
                "build_live_argv",
                "doctor_diagnostic_health",
                "runtime_configuration_intent",
                "toml_literal",
                "validate_runtime_argv_policy",
            },
            {
                "descriptor_xattr_inventory",
                "execution_root_inventory",
                "execute_slice",
                "_ensure_private_child",
                "_open_absolute_directory_nofollow",
                "_read_identity_value",
                "_darwin_process_info",
                "_darwin_process_table_snapshot",
                "_linux_process_table_snapshot",
                "_xattr_name_blob",
                "_xattr_value",
                "auth_class",
                "bounded_capture",
                "cli_profile",
                "run_bounded_process",
                "run_git",
                "run_fresh_verifier",
                "observe_colima_provider_evidence",
                "observe_runtime_profile",
                "prepare_colima_runtime_layout",
                "process_table_snapshot",
                "probe_config_and_shell_environment",
                "probe_runtime_configuration",
                "probe_runtime_evidence",
                "materialize_reviewed_rules_profile",
                "network_sandbox_behavior_probe",
                "runtime_configuration_argv",
                "shell_environment_probe",
                "validate_execution_root_transition",
                "cli_run",
                "cli_verify",
                "main",
            },
        ),
    )
    adapter_direct_imports = {
        "argparse",
        "contextlib",
        "ctypes",
        "datetime",
        "hashlib",
        "json",
        "math",
        "os",
        "re",
        "signal",
        "socket",
        "stat",
        "subprocess",
        "sys",
        "tempfile",
        "threading",
        "time",
        "unicodedata",
    }
    adapter_from_imports = {
        "__future__": {"annotations"},
        "pathlib": {"Path"},
        "typing": {
            "Any",
            "Dict",
            "Iterable",
            "List",
            "Mapping",
            "NamedTuple",
            "Optional",
            "Sequence",
            "Tuple",
        },
    }
    for relative, expected_digest, entrypoints, forbidden in imported_specs:
        module = parse_governed_python(root, relative, relative, errors)
        if module is None:
            continue
        payload, tree = module
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            errors.append(f"{relative} runtime import digest drifted")
        validate_python_imports(
            tree,
            direct=adapter_direct_imports,
            from_imports=adapter_from_imports,
            label=relative,
            errors=errors,
        )
        validate_import_time_structure(tree, relative, errors)
        validate_adapter_native_structure(tree, relative, errors)
        validate_reachable_module_calls(tree, entrypoints, forbidden, relative, errors)

    # The receipt tool is an explicit actuator. Required CI may parse and hash
    # its source, but it must never import the module or make any of its
    # validation helpers (which intentionally load the adapter) reachable.
    receipt_module = parse_governed_python(
        root,
        RUNTIME_RECEIPT_ACTUATOR,
        RUNTIME_RECEIPT_ACTUATOR,
        errors,
    )
    if receipt_module is not None:
        receipt_payload, receipt_tree = receipt_module
        if hashlib.sha256(receipt_payload).hexdigest() != RUNTIME_RECEIPT_ACTUATOR_SHA256:
            errors.append(f"{RUNTIME_RECEIPT_ACTUATOR} runtime import digest drifted")
        validate_python_imports(
            receipt_tree,
            direct={
                "argparse",
                "datetime",
                "hashlib",
                "importlib.util",
                "json",
                "math",
                "os",
                "re",
                "stat",
                "subprocess",
                "sys",
            },
            from_imports={
                "__future__": {"annotations"},
                "pathlib": {"Path"},
                "typing": {
                    "Any",
                    "Dict",
                    "List",
                    "Mapping",
                    "Optional",
                    "Sequence",
                    "Tuple",
                },
            },
            label=RUNTIME_RECEIPT_ACTUATOR,
            errors=errors,
        )
        validate_import_time_structure(receipt_tree, RUNTIME_RECEIPT_ACTUATOR, errors)


def validate_accepted_transition_evidence(
    root: Path, payload: dict[str, Any], errors: list[str]
) -> None:
    """Recheck accepted inert transition intent against each Task's exact base."""

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict) or task.get("state") != "accepted":
            continue
        transitions = task.get("path_transitions")
        if not isinstance(transitions, list) or not transitions:
            continue
        task_id = task.get("id", "?")
        label = f"accepted Task {task_id} transition evidence"
        base_commit = task.get("base_commit")
        base_tree = task.get("base_tree")
        if not isinstance(base_commit, str) or not FULL_SHA.fullmatch(base_commit):
            errors.append(f"{label} base commit is invalid")
            continue
        if not isinstance(base_tree, str) or not FULL_SHA.fullmatch(base_tree):
            errors.append(f"{label} base tree is invalid")
            continue
        resolved = git_command(root, "rev-parse", f"{base_commit}^{{tree}}")
        if (
            resolved.returncode != 0
            or resolved.stdout.decode("ascii", errors="replace").strip() != base_tree
        ):
            errors.append(f"{label} base commit/tree is missing or inconsistent")
            continue
        base_entries = git_tree_objects(root, base_commit)
        if base_entries is None:
            errors.append(f"{label} base tree is uncheckable")
            continue
        manifest_entry = base_entries.get(ROOT_MANIFEST)
        if manifest_entry is None or manifest_entry[1] != "blob":
            errors.append(f"{label} base ownership manifest is absent")
            continue
        manifest_bytes = git_blob_bytes(root, manifest_entry[2])
        if manifest_bytes is None:
            errors.append(f"{label} base ownership manifest is uncheckable")
            continue
        try:
            base_payload = json.loads(
                manifest_bytes.decode("utf-8"),
                object_pairs_hook=reject_duplicate_json_keys,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError):
            errors.append(f"{label} base ownership manifest is invalid")
            continue
        if not isinstance(base_payload, dict):
            errors.append(f"{label} base ownership manifest must be an object")
            continue
        base_ownership = manifest_ownership(base_payload)
        for index, transition in enumerate(transitions):
            if not isinstance(transition, dict):
                continue
            record_label = f"{label}[{index}]"
            operation = transition.get("operation")
            source_path = transition.get("source_path")
            source_owner = transition.get("source_owner")
            source_mode = transition.get("source_mode")
            if (
                not isinstance(operation, str)
                or operation not in {"delete", "rename", "copy"}
                or not isinstance(source_path, str)
                or not valid_relative_path(source_path)
                or not isinstance(source_owner, str)
                or not isinstance(source_mode, str)
            ):
                continue
            source_entry = base_entries.get(source_path)
            source_ownership = base_ownership.get(source_path)
            if source_entry is None or source_entry[1] != "blob":
                errors.append(f"{record_label} source path is absent from the Task base")
                continue
            if source_ownership is None or source_ownership[0] != source_owner:
                errors.append(f"{record_label} source owner does not match the Task base")
            if source_ownership is None or source_ownership[1] != source_mode:
                errors.append(f"{record_label} source mode does not match base ownership")
            if source_entry[0] != source_mode:
                errors.append(f"{record_label} source mode does not match the base tree")
            if operation in {"rename", "copy"}:
                destination_path = transition.get("destination_path")
                if isinstance(destination_path, str) and (
                    destination_path in base_entries
                    or destination_path in base_ownership
                ):
                    errors.append(f"{record_label} destination exists in the Task base")


def validate_path_transitions(
    root: Path,
    payload: dict[str, Any],
    task: dict[str, Any],
    entries: Iterable[tuple[str, str]],
    errors: list[str],
) -> None:
    """Authorize the exact-base Task diff, including declared path transitions."""

    task_id = task.get("id")
    base_commit = task.get("base_commit")
    base_tree = task.get("base_tree")
    if not isinstance(base_commit, str) or not FULL_SHA.fullmatch(base_commit):
        errors.append("path transition base commit is invalid")
        return
    if not isinstance(base_tree, str) or not FULL_SHA.fullmatch(base_tree):
        errors.append("path transition base tree is invalid")
        return
    commit_exists = git_command(root, "cat-file", "-e", f"{base_commit}^{{commit}}")
    if commit_exists.returncode != 0:
        errors.append("path transition base commit is missing or uncheckable")
        return
    resolved_tree = git_command(root, "rev-parse", f"{base_commit}^{{tree}}")
    if (
        resolved_tree.returncode != 0
        or resolved_tree.stdout.decode("ascii", errors="replace").strip() != base_tree
    ):
        errors.append("path transition base tree does not match base commit")
        return
    base_entries = git_tree_objects(root, base_commit)
    if base_entries is None:
        errors.append("path transition Task base tree is uncheckable")
        return
    manifest_entry = base_entries.get(ROOT_MANIFEST)
    if manifest_entry is None or manifest_entry[1] != "blob":
        errors.append("ownership manifest is absent from the Task base")
        return
    base_manifest_bytes = git_blob_bytes(root, manifest_entry[2])
    if base_manifest_bytes is None:
        errors.append("ownership manifest blob in the Task base is uncheckable")
        return
    try:
        base_payload = json.loads(
            base_manifest_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicate_json_keys,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError):
        errors.append("ownership manifest in the Task base is not valid unique-key JSON")
        return
    if not isinstance(base_payload, dict):
        errors.append("ownership manifest in the Task base must contain an object")
        return

    current_ownership = manifest_ownership(payload)
    base_ownership = manifest_ownership(base_payload)
    active_owned = active_owned_paths(task)
    transitions = task.get("path_transitions", [])
    if not isinstance(transitions, list):
        transitions = []

    observed: dict[str, str] = {}
    observed_paths: list[str] = []
    for item in entries:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not all(isinstance(value, str) for value in item)
        ):
            errors.append("Task diff contains a malformed change entry")
            continue
        status, path = item
        observed_paths.append(path)
        previous = observed.get(path)
        if previous is None:
            observed[path] = status
        elif previous != status:
            errors.append(f"Task diff has conflicting change statuses for {path}")
    validate_path_collisions(observed_paths, "Task diff", errors)

    consumed: set[tuple[str, str]] = set()
    declared_destinations: set[str] = set()
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        label = f"Task {task_id or '?'} path transition[{index}]"
        operation = transition.get("operation")
        source_path = transition.get("source_path")
        source_owner = transition.get("source_owner")
        source_mode = transition.get("source_mode")
        if (
            not isinstance(operation, str)
            or operation not in {"delete", "rename", "copy"}
            or not isinstance(source_path, str)
            or not valid_relative_path(source_path)
            or not isinstance(source_owner, str)
            or not isinstance(source_mode, str)
        ):
            continue

        base_source = base_entries.get(source_path)
        base_source_ownership = base_ownership.get(source_path)
        if base_source is None or base_source[1] != "blob":
            errors.append(f"{label} source path is absent from the Task base")
            continue
        if base_source_ownership is None or base_source_ownership[0] != source_owner:
            errors.append(f"{label} source owner does not match the Task base")
        if base_source_ownership is None or base_source_ownership[1] != source_mode:
            errors.append(f"{label} source mode does not match base ownership")
        if base_source[0] != source_mode:
            errors.append(f"{label} source mode does not match the Task base tree")
        source_blob = git_blob_bytes(root, base_source[2])
        if source_blob is None:
            errors.append(f"{label} source blob in the Task base is uncheckable")
            continue

        destination_path = transition.get("destination_path")
        destination_mode = transition.get("destination_mode")
        required = {("D", source_path)}
        if operation == "copy":
            required.clear()
        if operation in {"rename", "copy"}:
            if not isinstance(destination_path, str) or not valid_relative_path(
                destination_path
            ):
                continue
            declared_destinations.add(destination_path)
            required.add(("A", destination_path))
            if destination_path in base_entries or destination_path in base_ownership:
                errors.append(f"{label} destination exists in the Task base")
            destination_owner = current_ownership.get(destination_path)
            if destination_owner is None or destination_owner[0] != task_id:
                errors.append(f"{label} destination ownership is not the active Task")
            if destination_owner is None or destination_owner[1] != destination_mode:
                errors.append(f"{label} destination ownership mode is inconsistent")
            actual_mode = filesystem_mode(root / destination_path)
            if actual_mode != destination_mode:
                errors.append(f"{label} destination mode does not match the declaration")
            destination_blob = current_regular_bytes(root, destination_path)
            if destination_blob is None or destination_blob != source_blob:
                errors.append(f"{label} destination blob does not match the base source")

        if operation in {"delete", "rename"}:
            if source_path in current_ownership or (root / source_path).exists() or (
                root / source_path
            ).is_symlink():
                errors.append(f"{label} source must be absent after {operation}")
        else:
            current_source = current_ownership.get(source_path)
            if current_source is None or current_source[0] != source_owner:
                errors.append(f"{label} copy source must remain with its source owner")
            if filesystem_mode(root / source_path) != source_mode:
                errors.append(f"{label} copy source must remain at its reviewed mode")
            if current_regular_bytes(root, source_path) != source_blob:
                errors.append(f"{label} copy source must remain at its reviewed blob")

        if not all(observed.get(path) == status for status, path in required):
            errors.append(f"{label} transition is not consumed by the Task diff")
        else:
            consumed.update(required)

    base_object_paths: dict[str, list[str]] = {}
    for base_path, (_mode, object_type, object_id) in base_entries.items():
        if object_type == "blob":
            base_object_paths.setdefault(object_id, []).append(base_path)

    for path, status in observed.items():
        if (status, path) in consumed:
            continue
        if not valid_relative_path(path):
            errors.append(f"Task diff contains an unsupported path: {path!r}")
            continue
        if status == "D":
            errors.append(f"undeclared deletion: {path}")
            errors.append(f"Task ownership does not support deletion in this phase: {path}")
            if path not in active_owned:
                errors.append(
                    f"Task diff path is outside active Task {task_id or '?'} ownership: {path}"
                )
        elif status == "A":
            if path not in active_owned:
                errors.append(f"undeclared addition: {path}")
                errors.append(
                    f"Task diff path is outside active Task {task_id or '?'} ownership: {path}"
                )
                continue
            if path not in declared_destinations and path not in base_entries:
                object_result = git_command(root, "hash-object", "--no-filters", "--", path)
                if object_result.returncode == 0:
                    object_id = object_result.stdout.decode(
                        "ascii", errors="replace"
                    ).strip()
                    if any(
                        base_path != path
                        for base_path in base_object_paths.get(object_id, [])
                    ):
                        errors.append(
                            f"addition appears to be an unconsumed transition: {path}"
                        )
        elif status == "M":
            if path not in active_owned:
                errors.append(f"undeclared modification: {path}")
                errors.append(
                    f"Task diff path is outside active Task {task_id or '?'} ownership: {path}"
                )
        else:
            errors.append(f"Task diff has unsupported change status {status!r}: {path}")


def validate_execution_authorization(
    root: Path,
    payload: dict[str, Any],
    environment: Mapping[str, str],
    errors: list[str],
) -> None:
    context = resolve_execution_context(root, environment, errors)
    if context is None:
        return
    context_name, branch = context
    if context_name in {"main_push", "local_main"}:
        return
    task = active_task_for_branch(payload, branch, errors)
    if task is None:
        return
    task_base = task.get("base_commit")
    if not isinstance(task_base, str) or not FULL_SHA.fullmatch(task_base):
        return
    if context_name == "pull_request":
        event_path = environment.get("GITHUB_EVENT_PATH", "")
        if not event_path:
            errors.append("GitHub pull_request context is missing GITHUB_EVENT_PATH")
            return
        event = read_json(Path(event_path), errors, "GitHub pull_request event")
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, dict):
            errors.append("GitHub event pull_request must be an object")
            return
        base = pull_request.get("base")
        head = pull_request.get("head")
        if not isinstance(base, dict) or not isinstance(head, dict):
            errors.append("GitHub pull_request base and head must be objects")
            return
        base_sha = base.get("sha")
        head_sha = head.get("sha")
        base_ref = base.get("ref")
        head_ref = head.get("ref")
        base_repo = base.get("repo")
        head_repo = head.get("repo")
        if not isinstance(base_sha, str) or not FULL_SHA.fullmatch(base_sha):
            errors.append("GitHub pull_request base.sha must be a full object ID")
            return
        if not isinstance(head_sha, str) or not FULL_SHA.fullmatch(head_sha):
            errors.append("GitHub pull_request head.sha must be a full object ID")
            return
        if base_ref != "main":
            errors.append("GitHub pull_request base.ref must be main")
            return
        if head_ref != branch:
            errors.append("GitHub pull_request head.ref does not match GITHUB_HEAD_REF")
            return
        if (
            not isinstance(base_repo, dict)
            or base_repo.get("full_name") != TARGET_REPOSITORY
        ):
            errors.append(
                "GitHub pull_request base.repo.full_name must match the governed repository"
            )
            return
        if (
            not isinstance(head_repo, dict)
            or head_repo.get("full_name") != TARGET_REPOSITORY
        ):
            errors.append(
                "GitHub pull_request head.repo.full_name must match the governed repository"
            )
            return
        if task_base != base_sha:
            errors.append("active Task base_commit does not match pull_request.base.sha")
            return
        checked_head = environment.get("GITHUB_SHA", "")
        parents_result = git_command(
            root, "rev-list", "--parents", "-n", "1", checked_head
        )
        parents = parents_result.stdout.decode(
            "ascii", errors="replace"
        ).strip().split()
        if (
            parents_result.returncode != 0
            or parents != [checked_head, base_sha, head_sha]
        ):
            errors.append(
                "checked pull_request HEAD must be the exact synthetic merge of "
                "event base.sha and head.sha"
            )
            return
        diff_sources = [
            (
                [f"{base_sha}...{head_sha}"],
                "pull_request Task diff from event base to head",
            )
        ]
    elif context_name == "local_branch":
        main_result = git_command(root, "rev-parse", "refs/heads/main")
        if main_result.returncode != 0:
            errors.append("local Task authorization cannot resolve refs/heads/main")
            return
        main_sha = main_result.stdout.decode("ascii", errors="replace").strip()
        merge_base_result = git_command(root, "merge-base", main_sha, "HEAD")
        if merge_base_result.returncode != 0:
            errors.append("local Task authorization cannot resolve the main merge-base")
            return
        merge_base = merge_base_result.stdout.decode("ascii", errors="replace").strip()
        if task_base != main_sha or merge_base != main_sha:
            errors.append(
                "active Task base_commit must equal current local main and its HEAD merge-base"
            )
            return
        diff_sources = [
            ([main_sha], "local Task diff from exact main base to the worktree"),
        ]
    else:
        errors.append(f"unsupported Task-diff execution context: {context_name}")
        return
    changed_entries: list[tuple[str, str]] = []
    for arguments, label in diff_sources:
        entries = git_diff_entries(root, arguments, label, errors)
        if entries is None:
            return
        changed_entries.extend(entries)
    validate_path_transitions(root, payload, task, changed_entries, errors)


def invariant_digest(invariants: Iterable[tuple[str, str]]) -> str:
    canonical = "".join(
        f"{identifier}\t{statement}\n"
        for identifier, statement in sorted(invariants, key=lambda item: item[0])
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_invariants(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    try:
        lines = (root / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read live AGENTS.md: {exc}")
        return
    invariants = [match.groups() for line in lines if (match := INVARIANT_ROW.match(line))]
    identifiers = [identifier for identifier, _statement in invariants]
    if identifiers != EXPECTED_INVARIANT_IDS or len(identifiers) != len(set(identifiers)):
        errors.append("live invariant IDs must be exactly I01 through I13 in order")
    if dict(invariants).get("I02") != CANONICAL_I02:
        errors.append("live I02 does not express the reviewed Option B hierarchy")
    digest = invariant_digest(invariants)
    if digest != REVIEWED_INVARIANT_DIGEST:
        errors.append("live invariant meanings do not match the reviewed live anchor")
    if policy.get("invariant_digest") != REVIEWED_INVARIANT_DIGEST:
        errors.append("live invariant meanings do not match the reviewed policy digest")

    manifest = read_json(root / CONFORMANCE_MANIFEST, errors, "conformance manifest")
    if manifest.get("release_blocked") is not True:
        errors.append("conformance manifest release_blocked must remain true")
    manifest_invariants = manifest.get("invariants")
    if (
        not isinstance(manifest_invariants, dict)
        or manifest_invariants.get("digest") != REVIEWED_INVARIANT_DIGEST
    ):
        errors.append("conformance manifest invariant digest does not match AGENTS.md")


def policy_file_sha256(
    root: Path, relative: str, label: str, errors: list[str]
) -> str | None:
    try:
        raw = (root / relative).read_bytes()
    except OSError:
        errors.append(f"cannot read {label}")
        return None
    return hashlib.sha256(raw).hexdigest()


def policy_text(
    root: Path, relative: str, label: str, errors: list[str]
) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors.append(f"cannot read {label} as UTF-8")
        return None


def validate_required_markers(
    text: str | None,
    markers: Iterable[str],
    diagnostic: str,
    errors: list[str],
) -> None:
    if text is not None and any(marker not in text for marker in markers):
        errors.append(diagnostic)


def validate_hierarchy_and_completion(root: Path, errors: list[str]) -> None:
    manifest = read_json(root / CONFORMANCE_MANIFEST, errors, "conformance manifest")

    hierarchy = manifest.get("hierarchy_agreement")
    if not isinstance(hierarchy, dict):
        errors.append("conformance manifest hierarchy agreement must be an object")
        hierarchy = {}
    exact_keys(
        hierarchy,
        {"decision", "issue", "path", "sha256"},
        "conformance manifest hierarchy agreement",
        errors,
    )
    expected_hierarchy = {
        "decision": "option-b",
        "issue": HIERARCHY_AGREEMENT_ISSUE,
        "path": HIERARCHY_AGREEMENT_PATH,
        "sha256": REVIEWED_HIERARCHY_AGREEMENT_SHA256,
    }
    if hierarchy != expected_hierarchy:
        errors.append("conformance manifest hierarchy agreement is not the reviewed Option B anchor")

    hierarchy_hash = policy_file_sha256(
        root,
        HIERARCHY_AGREEMENT_PATH,
        "hierarchy agreement ADR",
        errors,
    )
    if hierarchy_hash != REVIEWED_HIERARCHY_AGREEMENT_SHA256:
        errors.append("reviewed hierarchy agreement hash does not match ADR-0005")
    if hierarchy.get("sha256") != hierarchy_hash:
        errors.append("hierarchy agreement manifest hash does not match ADR-0005")

    completion = manifest.get("repository_completion")
    if not isinstance(completion, dict):
        errors.append("conformance manifest repository completion must be an object")
        completion = {}
    exact_keys(
        completion,
        {
            "state",
            "definition",
            "individual_phase_completion_satisfies_repository_completion",
            "required_contracts",
            "target_side_evidence_required",
            "human_reviewed_completion_pr_required",
        },
        "conformance manifest repository completion",
        errors,
    )
    definition = completion.get("definition")
    if not isinstance(definition, dict):
        errors.append("repository completion definition must be an object")
        definition = {}
    exact_keys(
        definition,
        {"path", "sha256"},
        "repository completion definition",
        errors,
    )
    expected_definition = {
        "path": REPOSITORY_COMPLETION_PATH,
        "sha256": REVIEWED_REPOSITORY_COMPLETION_SHA256,
    }
    if definition != expected_definition:
        errors.append("repository completion definition is not the reviewed anchor")

    if completion.get("state") != "incomplete":
        errors.append("repository completion state must remain incomplete")
    if (
        completion.get(
            "individual_phase_completion_satisfies_repository_completion"
        )
        is not False
    ):
        errors.append(
            "repository completion must not be satisfied by individual Phase completion"
        )
    if completion.get("required_contracts") != REQUIRED_CONTRACT_IDS:
        errors.append("repository completion required contracts must be exactly K01 through K20")
    if completion.get("target_side_evidence_required") is not True:
        errors.append("repository completion must require current target-side evidence")
    if completion.get("human_reviewed_completion_pr_required") is not True:
        errors.append("repository completion must require a human-reviewed completion PR")

    contracts = manifest.get("contracts")
    contract_ids = (
        [item.get("id") for item in contracts if isinstance(item, dict)]
        if isinstance(contracts, list)
        else []
    )
    if contract_ids != REQUIRED_CONTRACT_IDS:
        errors.append("repository completion contract records must be exactly K01 through K20")
    if completion.get("required_contracts") != contract_ids:
        errors.append("repository completion prerequisites do not match contract records")
    if manifest.get("results") != []:
        errors.append("repository completion requires the Phase compatibility results sentinel to remain empty")
    if manifest.get("release_blocked") is not True:
        errors.append("repository completion requires release_blocked to remain true")

    completion_hash = policy_file_sha256(
        root,
        REPOSITORY_COMPLETION_PATH,
        "repository completion definition",
        errors,
    )
    if completion_hash != REVIEWED_REPOSITORY_COMPLETION_SHA256:
        errors.append(
            "reviewed repository completion hash does not match the definition"
        )
    if definition.get("sha256") != completion_hash:
        errors.append("repository completion manifest hash does not match the definition")

    coverage = read_json(root / COVERAGE, errors, "conformance coverage")
    entries = coverage.get("entries")
    c004_entries = (
        [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("scenario") == "C-004"
        ]
        if isinstance(entries, list)
        else []
    )
    expected_c004 = {
        "scenario": "C-004",
        "disposition": "agreement-decision",
        "verification_state": "not-run",
        "agreement_issue": HIERARCHY_AGREEMENT_ISSUE,
        "agreement_adr": HIERARCHY_AGREEMENT_PATH,
    }
    if c004_entries != [expected_c004]:
        errors.append("canonical C-004 agreement decision is missing or drifted")
    if (
        hierarchy.get("issue") != expected_c004["agreement_issue"]
        or hierarchy.get("path") != expected_c004["agreement_adr"]
    ):
        errors.append("canonical C-004 agreement decision is not bound to the hierarchy manifest")

    agents = policy_text(root, "AGENTS.md", "live AGENTS.md", errors)
    readme = policy_text(root, "README.md", "live README.md", errors)
    agreement_text = policy_text(
        root,
        HIERARCHY_AGREEMENT_PATH,
        "hierarchy agreement ADR",
        errors,
    )
    completion_text = policy_text(
        root,
        REPOSITORY_COMPLETION_PATH,
        "repository completion definition",
        errors,
    )
    limitations = policy_text(
        root,
        KNOWN_LIMITATIONS_PATH,
        "known limitations",
        errors,
    )
    agents_markers = " ".join(agents.split()) if agents is not None else None
    readme_markers = " ".join(readme.split()) if readme is not None else None
    limitation_markers = (
        " ".join(limitations.split()) if limitations is not None else None
    )

    option_b_markers = (CANONICAL_HIERARCHY, PROJECTS_PROJECTION)
    validate_required_markers(
        agents_markers,
        option_b_markers
        + (
            "durable repository objective",
            "explicitly linked Epic issues",
            "A single Epic issue may be the root",
            "wins if a projection conflicts",
        ),
        "Option B hierarchy markers are missing from AGENTS.md",
        errors,
    )
    validate_required_markers(
        limitation_markers,
        (
            "minimal/partial offline slice",
            "codex-cli 0.150.0-alpha.8",
            "unsupported-client",
            "required CI cannot run real Codex",
            "does not claim a completed live representative Task",
            "posted runtime receipt",
            "release-level conformance result set is empty",
            "`release_blocked` remains `true`",
        ),
        "Phase 2 bounded runtime limitations are missing from docs/known-limitations.md",
        errors,
    )
    validate_required_markers(
        readme_markers,
        option_b_markers
        + (
            f"]({HIERARCHY_AGREEMENT_PATH})",
            f"]({REPOSITORY_COMPLETION_PATH})",
            "Phase 0 is complete",
            "Phase 1 portable-core implementation gate",
            "current durable owner-acceptance outcome is external GitHub state",
            "creation-time snapshot",
            "Issue #12",
            "Epic #2",
            "post-merge receipt",
            "Issue #23",
            "minimal/partial execution slice",
            "codex-cli 0.150.0-alpha.8",
            "unsupported-client",
            "does not embed or claim a successful live Codex run or runtime receipt",
            "No successful live run or receipt is claimed in this tree.",
            "not installable",
            "not a parity release",
            "`release_blocked` remains `true`",
        ),
        "Option B hierarchy or Phase 2 current-status markers are missing from README.md",
        errors,
    )
    validate_required_markers(
        agents_markers,
        (
            "Phase 0 is complete.",
            "This tree satisfies the Phase 1 portable-core implementation gate.",
            "Issue #12 and Epic #2",
            "Epic, Task, and pull-request ledger contracts",
            "connector-neutral context contracts",
            "all eight repository Skills exist",
            "Custom agents, hooks, task-execution-envelope/v1, loop-event/v1",
            "installer/upgrade",
            "live Task ritual",
            "runtime parity",
            "release remain incomplete",
            "overall repository implementation remains incomplete",
            "`release_blocked` remains `true`",
        ),
        "Phase 1 portable-core status markers are missing from AGENTS.md",
        errors,
    )
    stale_phase1_markers = (
        "Phase 1 is in progress",
        "the full GitHub ledger arrive",
        "Until the target's issue and PR templates land",
    )
    if agents is not None and any(marker in agents for marker in stale_phase1_markers):
        errors.append("AGENTS.md contains stale Phase 1 status text")
    for label, text in (("AGENTS.md", agents), ("README.md", readme)):
        if text is not None and any(
            marker in text for marker in FORBIDDEN_LIVE_AUTHORITY_MARKERS
        ):
            errors.append(
                f"{label} contains a contradictory hierarchy or completion claim"
            )
    completion_markers = (
        NO_INDIVIDUAL_COMPLETION,
        OVERALL_COMPLETION_CONDITION,
    )
    validate_required_markers(
        agents_markers,
        completion_markers + ("## Repository completion boundary",),
        "repository completion boundary markers are missing from AGENTS.md",
        errors,
    )
    validate_required_markers(
        readme_markers,
        completion_markers,
        "repository completion boundary markers are missing from README.md",
        errors,
    )
    validate_required_markers(
        agreement_text,
        option_b_markers
        + (
            "# ADR-0005: Issue graph authority and optional Project projection",
            "### Option A",
            "### Option B (selected)",
            "### Option C",
            "Selected: Option B.",
            HIERARCHY_AGREEMENT_ISSUE,
            REPOSITORY_COMPLETION_PATH,
            "C-004",
        ),
        "hierarchy agreement ADR is missing reviewed Option B markers",
        errors,
    )
    validate_required_markers(
        completion_text,
        completion_markers
        + (
            "# Repository-level definition of done",
            "eight repository Skills",
            "six custom agents",
            "project hooks and handlers",
            "Epic, Task, and PR ledger schemas",
            "execution envelope and loop-event schemas",
            "Codex execution adapter",
            "installer and upgrade",
            "Task ritual, ownership, and governance",
            "clean-repository installation and end-to-end Task",
            "all 136 conformance scenarios",
            "satisfying each scenario's expected target behavior",
            "K01 through K20",
            "UNKNOWN",
            "UNCHECKABLE",
            "`fail`",
            "`failed`",
        ),
        "repository completion definition is missing reviewed gates",
        errors,
    )


def workflow_job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        jobs_index = lines.index("jobs:")
    except ValueError:
        return {}
    starts: list[tuple[int, str]] = []
    for index in range(jobs_index + 1, len(lines)):
        if lines[index] and not lines[index][0].isspace():
            break
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", lines[index])
        if match:
            starts.append((index, match.group(1)))
    return {
        name: "\n".join(lines[start : starts[position + 1][0] if position + 1 < len(starts) else len(lines)])
        for position, (start, name) in enumerate(starts)
    }


def validate_reserved_check_contexts(
    path: str, text: str, errors: list[str]
) -> None:
    """Keep Ruleset-required job names exclusive to the canonical CI workflow."""

    if path == CI_WORKFLOW:
        return
    lines = text.splitlines()
    jobs_indexes = [index for index, line in enumerate(lines) if line == "jobs:"]
    if len(jobs_indexes) != 1:
        errors.append(
            f"{path} must contain exactly one literal jobs mapping for context reservation"
        )
        return

    job_ids: list[str] = []
    workflow_lines = lines[jobs_indexes[0] + 1 :]
    for line_number, line in enumerate(
        workflow_lines, start=jobs_indexes[0] + 2
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace():
            break
        indent = len(line) - len(line.lstrip(" "))
        if "\t" in line or indent % 2:
            errors.append(
                f"{path}:{line_number} has unsupported job-mapping indentation"
            )
            continue
        if indent == 2:
            match = re.fullmatch(r"  ([A-Za-z_][A-Za-z0-9_-]*):\s*", line)
            if match is None:
                errors.append(
                    f"{path}:{line_number} has a dynamic or non-literal job ID"
                )
            else:
                job_ids.append(match.group(1))
        elif indent == 4:
            match = re.fullmatch(
                r"    ([A-Za-z_][A-Za-z0-9_-]*):(?:\s.*)?", line
            )
            if match is None:
                errors.append(
                    f"{path}:{line_number} has dynamic or merged job metadata"
                )
            elif match.group(1) == "name":
                errors.append(
                    f"{path}:{line_number} job-level name is forbidden because "
                    "Ruleset check contexts are globally reserved"
                )

    duplicates = sorted(
        job_id for job_id in set(job_ids) if job_ids.count(job_id) > 1
    )
    if duplicates:
        errors.append(f"{path} has duplicate job ID(s): {', '.join(duplicates)}")
    reserved = sorted({"quality", "conformance"} & set(job_ids))
    if reserved:
        errors.append(
            f"{path} reuses reserved Ruleset job ID(s): {', '.join(reserved)}"
        )


def simple_mapping(block: str, header: str) -> list[tuple[str, str]] | None:
    lines = block.splitlines()
    indexes = [index for index, line in enumerate(lines) if line == header]
    if len(indexes) != 1:
        return None
    header_indent = len(header) - len(header.lstrip(" "))
    child_indent = header_indent + 2
    entries: list[tuple[str, str]] = []
    for line in lines[indexes[0] + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= header_indent:
            break
        if indent != child_indent:
            return None
        content = re.sub(r"\s+#.*$", "", stripped)
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):\s*(\S.*)", content)
        if not match:
            return None
        entries.append((match.group(1), match.group(2)))
    return entries


def workflow_step_blocks(job_block: str) -> list[str]:
    lines = job_block.splitlines()
    starts = [
        index for index, line in enumerate(lines) if re.match(r"^      -\s+", line)
    ]
    return [
        "\n".join(
            lines[
                start : starts[position + 1]
                if position + 1 < len(starts)
                else len(lines)
            ]
        ).rstrip()
        for position, start in enumerate(starts)
    ]


def canonical_job_header(name: str) -> str:
    return (
        f"  {name}:\n"
        "    runs-on: ubuntu-latest\n"
        "    permissions:\n"
        "      contents: read\n"
        "    steps:"
    )


def validate_ci_job(
    name: str, block: str, commands: list[str], errors: list[str]
) -> None:
    lines = block.splitlines()
    try:
        steps_index = lines.index("    steps:")
    except ValueError:
        steps_index = -1
    header = "\n".join(lines[: steps_index + 1]) if steps_index >= 0 else ""
    if header != canonical_job_header(name):
        errors.append(
            f"ci job {name!r} has unsupported job metadata or execution modifiers"
        )

    steps = workflow_step_blocks(block)
    if len(steps) != len(commands) + 1:
        errors.append(f"ci job {name!r} must contain exactly its reviewed steps")
        return

    checkout_lines = steps[0].splitlines()
    checkout_match = ACTION_USE.fullmatch(checkout_lines[0]) if checkout_lines else None
    if (
        len(checkout_lines) != 4
        or checkout_match is None
        or not checkout_match.group(1).startswith("actions/checkout@")
        or checkout_lines[1:] != [
            "        with:",
            "          fetch-depth: 0",
            "          persist-credentials: false",
        ]
    ):
        errors.append(
            f"ci job {name!r} checkout step has unsupported fields or execution modifiers"
        )

    observed_commands: list[str] = []
    for index, step in enumerate(steps[1:], start=1):
        step_lines = step.splitlines()
        if (
            len(step_lines) != 2
            or not re.fullmatch(
                r"      - name: [A-Za-z0-9][A-Za-z0-9 ._:/()'&-]*",
                step_lines[0],
            )
            or not step_lines[1].startswith("        run: ")
        ):
            errors.append(
                f"ci job {name!r} step {index} has unsupported fields or execution modifiers"
            )
            continue
        observed_commands.append(step_lines[1].removeprefix("        run: "))
    if observed_commands != commands:
        errors.append(f"ci job {name!r} commands differ from the reviewed policy order")


def validate_action_uses(path: str, text: str, errors: list[str]) -> None:
    uses = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if QUOTED_MAPPING_KEY.search(line):
            errors.append(f"{path}:{line_number} quoted or escaped mapping key is unsupported")
            continue
        match = ACTION_USE.match(line)
        if USES_TOKEN.search(line) and not match:
            errors.append(f"{path}:{line_number} uses syntax is unsupported")
            continue
        if not match:
            continue
        uses += 1
        reference, comment = match.groups()
        if reference.startswith("./"):
            errors.append(
                f"{path}:{line_number} local Actions are unsupported until "
                "recursive composite validation is reviewed"
            )
            continue
        if not FULL_ACTION_REF.fullmatch(reference):
            errors.append(f"{path}:{line_number} Action reference must use a full commit SHA")
        if not comment or not re.fullmatch(r"v\d+\.\d+\.\d+", comment):
            errors.append(f"{path}:{line_number} pinned Action needs a version comment")
    if path == CI_WORKFLOW and uses < 2:
        errors.append("ci workflow must retain checkout in both required jobs")


def validate_workflows(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    workflow_root = root / ".github/workflows"
    workflows = sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml"))
    if not workflows:
        errors.append("live repository must contain at least one workflow")
        return
    for path in workflows:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read workflow {relative}: {exc}")
            continue
        if "\t" in text:
            errors.append(f"{relative} contains tab indentation")
        if "continue-on-error:" in text:
            errors.append(f"{relative} contains forbidden continue-on-error")
        if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
            errors.append(f"{relative} uses unsupported pull_request_target")
        validate_action_uses(relative, text, errors)
        validate_reserved_check_contexts(relative, text, errors)
        if text.splitlines().count("permissions: {}") != 1:
            errors.append(
                f"{relative} workflow-level permissions must be exactly one empty mapping"
            )
        workflow_blocks = workflow_job_blocks(text)
        if not workflow_blocks:
            errors.append(f"{relative} has no classifiable block-style jobs")
        for job_name, job_block in workflow_blocks.items():
            if simple_mapping(job_block, "    permissions:") != [("contents", "read")]:
                errors.append(
                    f"{relative} job {job_name!r} permissions must contain only contents: read"
                )

    path = root / CI_WORKFLOW
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read live CI workflow: {exc}")
        return
    if "Run Phase 0 conformance tests" in text:
        errors.append("ci workflow contains stale Phase 0 conformance step label")
    forbidden_runtime_ci_markers = (
        ".github/scripts/codex-exec-adapter.py",
        ".github/scripts/post-runtime-receipt.py",
        "run-live",
        "--apply",
        "codex exec",
    )
    for marker in forbidden_runtime_ci_markers:
        if marker in text:
            errors.append(
                "required CI must not invoke real Codex, live adapter mode, or "
                f"the receipt actuator: {marker}"
            )
    if not text.startswith(CI_PREAMBLE):
        errors.append(
            "ci trigger/preamble must enable pull_request and push to main with empty permissions"
        )
    blocks = workflow_job_blocks(text)
    job_names = re.findall(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", text, re.MULTILINE)
    duplicates = sorted(name for name in set(job_names) if job_names.count(name) > 1)
    if duplicates:
        errors.append(f"ci workflow contains duplicate job ID(s): {', '.join(duplicates)}")
    required_jobs = policy.get("required_jobs")
    if not isinstance(required_jobs, list):
        return
    if set(blocks) != {"quality", "conformance"}:
        errors.append("ci required job drift: jobs must be exactly quality and conformance")
    command_fields = {
        "quality": "required_quality_commands",
        "conformance": "required_conformance_commands",
    }
    for job_name, field in command_fields.items():
        block = blocks.get(job_name, "")
        commands = policy.get(field)
        if not isinstance(commands, list):
            continue
        validate_ci_job(job_name, block, commands, errors)


def validate_text_policy(root: Path, paths: set[str], errors: list[str]) -> None:
    floating_surfaces = {"README.md", "AGENTS.md", ROOT_MANIFEST, CONFORMANCE_MANIFEST}
    floating_surfaces.update(path for path in paths if path.startswith(".github/workflows/"))
    for relative in sorted(paths & floating_surfaces):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read policy surface {relative}: {exc}")
            continue
        if "@latest" in text:
            errors.append(f"{relative} contains forbidden floating dependency '@latest'")
        if relative in {"AGENTS.md", ROOT_MANIFEST, CONFORMANCE_MANIFEST}:
            match = MODEL_SLUG.search(text)
            if match:
                errors.append(f"{relative} hardcodes model slug {match.group(0)!r}")


def validate_repository(
    root: Path,
    *,
    verify_git: bool = True,
    observed_paths: set[str] | None = None,
    observed_modes: dict[str, str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    payload = read_json(root / ROOT_MANIFEST, errors, "ownership manifest")
    expected_modes, policy = validate_manifest(payload, errors)
    validate_phase2_frontier(payload, errors)

    index_entries = git_index_entries(root) if verify_git else None
    tree_entries = git_tree_entries(root) if verify_git else None
    if verify_git and index_entries is None:
        errors.append("cannot classify the live Git index")
    if verify_git and tree_entries is None:
        errors.append("cannot enumerate the live HEAD tree")
    paths = discover_paths(root, index_entries) if observed_paths is None else set(observed_paths)
    if tree_entries is not None:
        paths.update(tree_entries)
    validate_path_collisions(paths, "live repository", errors)
    modes = dict(observed_modes or {})
    if observed_modes is None:
        for relative in paths:
            modes[relative] = (
                index_entries[relative]
                if index_entries is not None and relative in index_entries
                else filesystem_mode(root / relative)
            )

    for relative in sorted(paths - set(expected_modes)):
        errors.append(f"undeclared live path outside Task ownership: {relative}")
    for relative in sorted(set(expected_modes) - paths):
        errors.append(f"declared live path is missing: {relative}")
    for relative in sorted(paths & set(expected_modes)):
        path = root / relative
        if verify_git and not path.exists() and not path.is_symlink() and (
            index_entries is None or relative not in index_entries
        ):
            errors.append(f"live path is absent from the worktree and index: {relative}")
        linked = symlink_component(root, relative)
        if linked is not None or modes.get(relative) == "120000":
            errors.append(
                f"live path must not contain a symlink component: {relative}"
                + (f" (at {linked})" if linked is not None else "")
            )
        if modes.get(relative) != expected_modes[relative]:
            errors.append(
                f"live path mode mismatch for {relative}: expected {expected_modes[relative]}, "
                f"found {modes.get(relative)!r}"
            )

    if tree_entries is not None:
        for relative, (mode, object_type) in sorted(tree_entries.items()):
            if object_type != "blob" or mode not in ALLOWED_MODES:
                errors.append(
                    f"live HEAD tree contains unsupported {object_type} mode {mode}: {relative}"
                )

    if verify_git:
        validate_git_evidence(root, payload, errors)
        validate_accepted_transition_evidence(root, payload, errors)
        validate_execution_authorization(
            root, payload, os.environ if environment is None else environment, errors
        )
    validate_invariants(root, policy, errors)
    validate_hierarchy_and_completion(root, errors)
    validate_workflows(root, policy, errors)
    validate_historical_phase1_checker_boundary(root, payload, policy, errors)
    validate_offline_runtime_checker_boundary(root, errors)
    validate_execution_root_surfaces(paths, errors)
    validate_registry_reachability(paths, policy, errors)
    validate_text_policy(root, paths, errors)
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        print(f"repository-policy: FAIL — {len(errors)} finding(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "repository-policy: OK — versioned Task ownership covers every live path; "
        "frozen Phase 1 evidence, Phase 2 live policy, I01-I13, release blocker, "
        "Actions, permissions, "
        "and required CI jobs are consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
