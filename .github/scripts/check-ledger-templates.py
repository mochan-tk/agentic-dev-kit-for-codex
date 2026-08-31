#!/usr/bin/env python3
"""Fail-closed, read-only validation for the static ledger contracts."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ".github/governance/ledger-contracts.v1.json"
FIXTURE_PATH = "tests/ledger/fixtures/ledger-valid.v1.json"
RENDERED_PATHS = {
    "epic": "tests/ledger/fixtures/epic-rendered.md",
    "task": "tests/ledger/fixtures/task-rendered.md",
    "pull_request": "tests/ledger/fixtures/pull-request-rendered.md",
}
MAX_FILE_BYTES = 1_048_576
MAX_STRING_LENGTH = 16_384
MAX_JSON_NESTING_DEPTH = 128
REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
ISSUE_URL = re.compile(
    rf"https://github\.com/{re.escape(REPOSITORY)}/issues/([1-9][0-9]*)\Z"
)
COMMENT_URL = re.compile(
    rf"https://github\.com/{re.escape(REPOSITORY)}/issues/([1-9][0-9]*)"
    r"#issuecomment-([1-9][0-9]*)\Z"
)
PULL_URL = re.compile(
    rf"https://github\.com/{re.escape(REPOSITORY)}/pull/([1-9][0-9]*)\Z"
)
COMMIT_URL = re.compile(
    rf"https://github\.com/{re.escape(REPOSITORY)}/commit/([0-9a-f]{{40}})(?:/checks)?\Z"
)
ACTIONS_URL = re.compile(
    rf"https://github\.com/{re.escape(REPOSITORY)}/actions/runs/([1-9][0-9]*)"
    r"(?:/job/([1-9][0-9]*))?\Z"
)
TASK_RELATIONSHIP = re.compile(
    rf"(Closes|Refs) (https://github\.com/{re.escape(REPOSITORY)}/issues/[1-9][0-9]*)\Z"
)
OPAQUE_RUNTIME_REFERENCE_PATTERNS = {
    "task_execution_envelope_ref": re.compile(
        r"opaque-ref/v1:task-execution-envelope:sha256:[0-9a-f]{64}\Z"
    ),
    "loop_event_ref": re.compile(
        r"opaque-ref/v1:loop-event:sha256:[0-9a-f]{64}\Z"
    ),
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*\Z")
CRITERION_ID = re.compile(r"[A-Z][A-Z0-9]*-[0-9]{2,}\Z")
EVIDENCE_ID = re.compile(r"[A-Z][A-Z0-9]*-[0-9]{2,}\Z")
PLACEHOLDER = re.compile(r"(?i)(?:\b(?:todo|tbd|replace[-_ ]?me)\b|<[^>]+>|example\.com)")
HTML_CHARACTER_REFERENCE = re.compile(
    r"&(?:#[0-9]{1,7}|#x[0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});"
)
UNSAFE_MARKDOWN_LINE = re.compile(
    r"(?m)^[ \t]*(?:#{1,6}(?:[ \t]|$)|`{3,}|~{3,}|-{3,}[ \t]*$|={3,}[ \t]*$|<[!/A-Za-z])"
)
WINDOWS_RESERVED_COMPONENT = re.compile(
    r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z"
)


def expected_runtime_frontier() -> dict[str, Any]:
    """Return the exact immutable T11 history and active T12 tree snapshot."""

    return {
        "tree_snapshot": {
            "t11": "accepted",
            "t12": "sole-active",
            "live_evidence": "external-github-current-outcome-not-embedded-in-tree",
        },
        "t11_history": {
            "agreement": {
                "version": "t11-agreement-v2",
                "task_issue": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
                ),
                "decision_url": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
                    "#issuecomment-5472720734"
                ),
                "decision_body_sha256": (
                    "f177b639139558c6a85d84d88c827e72c22e642ae0197c8a3fc8adf6dc6c0581"
                ),
            },
            "acceptance_mapping": {
                "AC-01-through-AC-12": "applicable-offline-static-boundary",
                "AC-13": "deferred-to-T12-by-approved-agreement-replan",
                "AC-14": "unchanged",
                "AC-15": "owner-merge-gate-offline-harness",
            },
            "status": {
                "task": "accepted",
                "runtime_harness": "minimal-offline-implemented",
                "live_codex_execution": "deferred-to-T12",
                "sandbox_compatibility": "unresolved-non-success",
                "runtime_receipt_apply": "deferred-to-T12",
            },
            "merge": {
                "commit": "4a85a007ed62795b48bcbce04f6b7e5482e71e82",
                "tree": "49afe003de2bbb04249d6f4c36ea6462c271c26f",
                "receipt": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
                    "#issuecomment-5473274452"
                ),
            },
            "stage_a1": {
                "classification": "bounded-non-success",
                "qualified_boundary": "git-and-bubblewrap-prerequisites-only",
                "aggregate_status": "UNCHECKABLE",
                "direct_bwrap_smoke_status": "pass",
                "device_auth_performed": False,
                "logical_codex_exec_worker_process_invocation_count": 0,
                "runtime_receipt_dry_run_count": 0,
                "runtime_receipt_apply_count": 0,
                "evidence_issue_url": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
                    "#issuecomment-5470293000"
                ),
                "evidence_body_sha256": (
                    "5911657f46e4a0f555ac642ed69f38dd31efe771ec5846d5a19d2a4f1a62dbce"
                ),
            },
            "stage_a2": {
                "classification": "bounded-non-success",
                "aggregate_status": "UNCHECKABLE",
                "provider_isolation_status": "pass",
                "mount_boundary_status": "pass",
                "process_cleanup_status": "pass",
                "config_status": "pass",
                "shell_environment_status": "fail",
                "shell_environment_reason_code": "process-nonzero",
                "codex_sandbox_network_status": "UNCHECKABLE",
                "codex_sandbox_network_reason_code": "process-nonzero",
                "auth_status": "unavailable",
                "device_auth_performed": False,
                "logical_codex_exec_worker_process_invocation_count": 0,
                "runtime_receipt_dry_run_count": 0,
                "runtime_receipt_apply_count": 0,
                "evidence_issue_url": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23"
                    "#issuecomment-5472529555"
                ),
                "evidence_pull_request_url": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24"
                    "#issuecomment-5472529704"
                ),
                "evidence_body_sha256": (
                    "ba3f7d65be3a415e3fc36c1e6d20d16de4147cbd28912932b5cfeac759f972df"
                ),
            },
        },
        "t12_activation": {
            "task_issue": (
                "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25"
            ),
            "state": "active-in-this-tree",
            "branch": "codex/phase-2-live-codex-runtime",
            "phase_origin": {
                "commit": "36c7eabecf7a56eb2a1c2c8f2c4d8fcb371c31c2",
                "tree": "1c1f46ad20dd289a713663c84eaf1dbb62840deb",
            },
            "task_base": {
                "commit": "4a85a007ed62795b48bcbce04f6b7e5482e71e82",
                "tree": "49afe003de2bbb04249d6f4c36ea6462c271c26f",
            },
            "owner_amendment": {
                "url": (
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25"
                    "#issuecomment-5480062206"
                ),
                "body_sha256": (
                    "b3f051da26ebba7e0d49b79917cffa81ec6e9c66d409029ffd0020d0211850ee"
                ),
            },
            "ownership": {
                "transferred_path_count": 21,
                "path_transitions": [],
                "expansion_requires_replan": True,
            },
            "runtime_evidence": {
                "authority": "external-github-current-outcome-not-embedded-in-tree",
                "stage_a": "required-before-stage-b",
                "stage_b": "required-before-runtime-receipt",
                "sandbox_compatibility": "must-be-qualified-not-embedded",
                "runtime_receipt_apply": "exactly-once-required-not-embedded",
                "lifecycle_completion": (
                    "separate-append-only-comment-not-runtime-receipt"
                ),
            },
            "compatibility_baseline": {
                "client": "official-stable-codex-cli-0.150.1",
                "scope": "one-exact-receipt-bound-profile-only",
                "current_latest_stable_claimed": False,
                "version_change": "ownership-and-source-review-replan-required",
            },
            "invocation_boundary": {
                "claim": (
                    "exactly-one-owner-triggered-logical-codex-exec-"
                    "worker-process-invocation"
                ),
                "execution_result_logical_invocations": 1,
                "backend_model_request_count_claimed": False,
                "automatic_worker_retry": False,
            },
            "pull_request_binding": (
                "dynamic-github-readback-required-no-static-pr-number"
            ),
            "receipt_chronology": [
                "stage-b-live-worker",
                "deterministic-verification",
                "receipt-dry-run",
                "exact-head-tree-check-readback",
                "exactly-one-runtime-receipt-apply",
                "canonical-receipt-readback",
                "provider-and-runtime-destruction",
                "profile-runtime-data-process-absence-readback",
                "one-append-only-lifecycle-completion-evidence-comment",
                "owner-merge-judgment",
            ],
            "source_parity": {
                "repository": "mochan-tk/agentic-dev-kit-for-copilot",
                "commit": "fd265ddef150fab86cd54d0e383c2c25fe297ffb",
                "tree": "88f96493ec167602750c8dfec044629bd494a586",
                "contributes": [
                    "capability-aware-routing-for-one-exact-profile",
                    "bounded-worker-execution",
                    "durable-attempt-and-receipt-trail",
                    "independent-verification-over-worker-claim",
                    "privacy-by-reference",
                ],
                "does_not_complete": [
                    "K09",
                    "K10",
                    "K11",
                    "K12",
                    "full-runtime-parity",
                ],
            },
        },
        "status": {
            "runtime_harness": "minimal-offline-implemented",
            "live_codex_execution": (
                "active-qualification-external-evidence-not-embedded"
            ),
            "sandbox_compatibility": "required-external-evidence-not-embedded",
            "runtime_receipt_apply": "required-external-evidence-not-embedded",
            "phase_2": "incomplete",
            "repository": "incomplete",
            "release_blocked": True,
        },
        "canonical_release_boundary": {
            "scenario_count": 136,
            "scenario_state": "not-run",
            "release_result_count": 0,
            "release_results": [],
            "release_blocked": True,
        },
    }

EXPECTED_LAYOUT = {
    "epic": [
        ("goal", [("goal", "textarea", True)]),
        (
            "scope_and_non_goals",
            [("scope", "textarea", True), ("non_goals", "textarea", True)],
        ),
        (
            "decomposition_and_dependency_graph",
            [("task_graph", "textarea", True), ("dependency_policy", "textarea", True)],
        ),
        (
            "acceptance_and_evidence",
            [
                ("acceptance_criteria", "textarea", True),
                ("evidence_requirements", "textarea", True),
            ],
        ),
        (
            "planning_and_control",
            [("planning_owner", "input", True), ("control_policy", "textarea", True)],
        ),
    ],
    "task": [
        (
            "objective_and_scope",
            [("objective", "textarea", True), ("scope", "textarea", True)],
        ),
        ("acceptance_criteria", [("acceptance_criteria", "textarea", True)]),
        (
            "dependencies_and_references",
            [
                ("epic_url", "input", True),
                ("dependencies", "textarea", True),
                ("references", "textarea", True),
            ],
        ),
        ("ownership", [("ownership", "textarea", True)]),
        (
            "risk_and_constraints",
            [
                ("risk_tier", "dropdown", True),
                ("risk_rationale", "textarea", True),
                ("risk_constraints", "textarea", True),
            ],
        ),
        (
            "verification_and_evidence",
            [
                ("verification_commands", "textarea", True),
                ("evidence_requirements", "textarea", True),
            ],
        ),
        (
            "routing_and_execution",
            [("routing", "textarea", True), ("execution", "textarea", True)],
        ),
        (
            "completion_and_relationships",
            [
                ("completion_conditions", "textarea", True),
                ("relationships", "textarea", True),
                ("task_execution_envelope_ref", "input", False),
                ("loop_event_ref", "input", False),
            ],
        ),
    ],
    "pull_request": [
        (
            "task_relationship",
            [("task_relationship", "input", True), ("plan_comment_url", "input", True)],
        ),
        (
            "summary_and_scope",
            [("summary", "textarea", True), ("scope", "textarea", True)],
        ),
        (
            "evidence_table",
            [("head_sha", "input", True), ("evidence", "textarea", True)],
        ),
        (
            "risks_and_limitations",
            [("risks", "textarea", True), ("limitations", "textarea", True)],
        ),
        ("deferred_evidence", [("deferred_evidence", "textarea", True)]),
    ],
}
EXPECTED_HEADINGS = {
    "epic": [
        "Goal",
        "Scope and non-goals",
        "Decomposition and dependency graph",
        "Acceptance and evidence",
        "Planning and control",
    ],
    "task": [
        "Objective and scope",
        "Acceptance criteria",
        "Dependencies and references",
        "Ownership",
        "Risk and constraints",
        "Verification and evidence",
        "Routing and execution",
        "Completion and relationships",
    ],
    "pull_request": [
        "Task relationship",
        "Summary and scope",
        "Evidence table",
        "Risks and limitations",
        "Deferred evidence",
    ],
}
EXPECTED_LABELS = {
    "epic": {
        "goal": "Goal",
        "scope": "Scope",
        "non_goals": "Non-goals",
        "task_graph": "Task graph",
        "dependency_policy": "Dependency policy",
        "acceptance_criteria": "Acceptance criteria",
        "evidence_requirements": "Evidence requirements",
        "planning_owner": "Planning owner",
        "control_policy": "Control policy",
    },
    "task": {
        "objective": "Objective",
        "scope": "Scope",
        "acceptance_criteria": "Acceptance criteria",
        "epic_url": "Parent Epic Issue URL",
        "dependencies": "Dependencies",
        "references": "References",
        "ownership": "Owned paths",
        "risk_tier": "Risk tier",
        "risk_rationale": "Risk rationale",
        "risk_constraints": "Risk constraints",
        "verification_commands": "Verification commands",
        "evidence_requirements": "Evidence requirements",
        "routing": "Routing",
        "execution": "Execution",
        "completion_conditions": "Completion conditions",
        "relationships": "Relationships",
        "task_execution_envelope_ref": "Task execution envelope reference (optional and opaque)",
        "loop_event_ref": "Loop event reference (optional and opaque)",
    },
    "pull_request": {
        "task_relationship": "Task relationship",
        "plan_comment_url": "Plan comment URL",
        "summary": "Summary",
        "scope": "Scope",
        "head_sha": "Exact head SHA",
        "evidence": "Evidence",
        "risks": "Risks",
        "limitations": "Limitations",
        "deferred_evidence": "Deferred evidence",
    },
}
EXPECTED_METADATA = {
    "epic": {
        "name": "Epic",
        "description": "Define a durable Epic in the canonical Issue graph.",
        "title": "[Epic] ",
        "labels": [],
        "assignees": [],
    },
    "task": {
        "name": "Task",
        "description": "Define one bounded Task under an Epic Issue.",
        "title": "[Task] ",
        "labels": [],
        "assignees": [],
    },
    "pull_request": {"title": "Pull request ledger record"},
}
EXPECTED_BOOTSTRAP_SNAPSHOTS = {
    "epic": {
        "issue_url": f"https://github.com/{REPOSITORY}/issues/2",
        "body_sha256": "9f6580a584d09f7006675bfd6a63dfc91b3ff632effa4f23ba260f92e621ac52",
        "ordered_headings": [
            "Goal",
            "Scope and non-goals",
            "Task graph and dependencies",
            "Acceptance",
            "Planning and control",
        ],
    },
    "task": {
        "issue_url": f"https://github.com/{REPOSITORY}/issues/9",
        "body_sha256": "dc4b92ad6e4df58d0b9ce4ea0686b53a1d6faf18b5b6bf4767c4e8316c17e403",
        "ordered_headings": [
            "Objective",
            "Rationale",
            "Dependencies / blocked by",
            "Acceptance criteria",
            "Ownership",
            "Out of scope",
            "Risk and human gates",
            "Verification / evidence",
            "Expected pull-request boundary",
            "Contract and conformance coverage",
            "Completion boundary",
        ],
    },
}
EXPECTED_BOOTSTRAP_OBSERVED_AT = "2026-08-25T03:51:32Z"


class DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_regular_text(root: Path, relative: str) -> str:
    """Read a bounded regular file without following repository symlinks."""
    parts = relative.split("/")
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or relative.startswith("/")
        or "\\" in relative
    ):
        raise ValueError(f"unsafe repository path: {relative}")
    platform_flags: dict[str, int] = {}
    for flag_name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        flag_value = getattr(os, flag_name, None)
        if not isinstance(flag_value, int) or flag_value == 0:
            raise ValueError(f"required platform flag {flag_name} is unavailable")
        platform_flags[flag_name] = flag_value
    directory_flags = os.O_RDONLY | platform_flags["O_DIRECTORY"]
    nofollow = platform_flags["O_NOFOLLOW"]
    nonblock = platform_flags["O_NONBLOCK"]
    fds: list[int] = []
    directory_bindings: list[tuple[int, str, tuple[int, int]]] = []
    try:
        current = os.open(os.fspath(root), directory_flags | nofollow)
        fds.append(current)
        root_stat = os.fstat(current)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("repository root is not a directory")
        root_binding = (root_stat.st_dev, root_stat.st_ino)
        for part in parts[:-1]:
            parent_fd = current
            child_fd = os.open(part, directory_flags | nofollow, dir_fd=parent_fd)
            fds.append(child_fd)
            child_stat = os.fstat(child_fd)
            if not stat.S_ISDIR(child_stat.st_mode):
                raise ValueError(f"repository path parent is not a directory: {relative}")
            directory_bindings.append(
                (parent_fd, part, (child_stat.st_dev, child_stat.st_ino))
            )
            current = child_fd
        parent_fd = current
        file_fd = os.open(
            parts[-1], os.O_RDONLY | nofollow | nonblock, dir_fd=parent_fd
        )
        fds.append(file_fd)

        def verify_directory_chain() -> None:
            live_root = os.stat(os.fspath(root), follow_symlinks=False)
            if not stat.S_ISDIR(live_root.st_mode) or (
                live_root.st_dev,
                live_root.st_ino,
            ) != root_binding:
                raise ValueError("repository root binding changed while reading governed input")
            for held_parent, name, expected in directory_bindings:
                live_child = os.stat(name, dir_fd=held_parent, follow_symlinks=False)
                if not stat.S_ISDIR(live_child.st_mode) or (
                    live_child.st_dev,
                    live_child.st_ino,
                ) != expected:
                    raise ValueError(
                        f"repository directory binding changed while reading {relative}"
                    )

        verify_directory_chain()
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"repository input is not a regular file: {relative}")
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError(f"repository input exceeds size limit: {relative}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(65_536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError(f"repository input exceeds size limit: {relative}")
        after = os.fstat(file_fd)
        verify_directory_chain()
        named = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        binding = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if binding != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(f"repository input changed while read: {relative}")
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError(f"repository input binding changed while read: {relative}")
        data = b"".join(chunks)
        if b"\x00" in data:
            raise ValueError(f"repository input contains NUL: {relative}")
        return data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot safely read {relative}: {exc}") from exc
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


def load_json(root: Path, relative: str) -> Any:
    text = read_regular_text(root, relative)
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ValueError(f"invalid JSON in {relative}: {exc}") from exc
    except RecursionError as exc:
        raise ValueError(
            f"invalid JSON in {relative}: nesting depth exceeds the safe limit"
        ) from exc
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_JSON_NESTING_DEPTH:
            raise ValueError(
                f"invalid JSON in {relative}: nesting depth exceeds the safe limit"
            )
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return value


def exact_keys(
    value: Any,
    required: Iterable[str],
    optional: Iterable[str],
    label: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    required_set = set(required)
    allowed = required_set | set(optional)
    actual = set(value)
    missing = sorted(required_set - actual)
    extra = sorted(actual - allowed)
    if missing:
        errors.append(f"{label} missing required fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} has unsupported fields: {', '.join(extra)}")
    return not missing and not extra


def valid_string(value: Any, label: str, errors: list[str]) -> bool:
    if not isinstance(value, str):
        errors.append(f"{label} must be a string")
        return False
    if value != value.strip() or not value or len(value) > MAX_STRING_LENGTH:
        errors.append(f"{label} must be a bounded, non-blank, trimmed string")
        return False
    if any(
        (unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"})
        and char not in "\n\t"
        for char in value
    ):
        errors.append(f"{label} contains an unsafe Unicode control or format character")
        return False
    if "-->" in value or "<!--" in value:
        errors.append(f"{label} contains an HTML comment delimiter")
        return False
    if HTML_CHARACTER_REFERENCE.search(value):
        errors.append(f"{label} contains an HTML character reference")
        return False
    if PLACEHOLDER.search(value):
        errors.append(f"{label} contains a placeholder value")
        return False
    if UNSAFE_MARKDOWN_LINE.search(value):
        errors.append(f"{label} contains a structural Markdown injection")
        return False
    return True


def string_list(
    value: Any,
    label: str,
    errors: list[str],
    *,
    allow_none: bool = False,
) -> list[str] | None:
    if allow_none and value == "None":
        return []
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list" + (" or None" if allow_none else ""))
        return None
    if len(value) > 256:
        errors.append(f"{label} exceeds the item limit")
        return None
    result: list[str] = []
    for index, item in enumerate(value):
        if valid_string(item, f"{label}[{index}]", errors):
            result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicate values")
    return result


def issue_number(value: Any, label: str, errors: list[str]) -> int | None:
    if not valid_string(value, label, errors):
        return None
    match = ISSUE_URL.fullmatch(value)
    if not match:
        errors.append(f"{label} must be a canonical same-repository Issue URL")
        return None
    return int(match.group(1))


def pull_number(value: Any, label: str, errors: list[str]) -> int | None:
    if not valid_string(value, label, errors):
        return None
    match = PULL_URL.fullmatch(value)
    if not match:
        errors.append(f"{label} must be a canonical same-repository pull-request URL")
        return None
    return int(match.group(1))


def reference_url(value: Any, label: str, errors: list[str]) -> bool:
    if not valid_string(value, label, errors):
        return False
    if not any(
        pattern.fullmatch(value)
        for pattern in (ISSUE_URL, COMMENT_URL, PULL_URL, COMMIT_URL, ACTIONS_URL)
    ):
        errors.append(f"{label} must be a supported canonical same-repository URL")
        return False
    return True


def validate_task_relationship(
    value: Any,
    expected_task_url: Any,
    label: str,
    errors: list[str],
) -> None:
    if not valid_string(value, label, errors):
        return
    match = TASK_RELATIONSHIP.fullmatch(value)
    if not match:
        errors.append(
            f"{label} must be exactly Closes or Refs followed by one canonical Task Issue URL"
        )
        return
    if match.group(2) != expected_task_url:
        errors.append(f"{label} Task URL must match task_url")


def validate_opaque_runtime_reference(
    value: Any,
    field: str,
    label: str,
    errors: list[str],
) -> None:
    """Validate only a bounded opaque locator shape; never resolve its target."""
    if not valid_string(value, label, errors):
        return
    pattern = OPAQUE_RUNTIME_REFERENCE_PATTERNS[field]
    if not pattern.fullmatch(value):
        errors.append(
            f"{label} must use the field-specific bounded opaque linkage grammar; "
            "shape validation does not prove target validity or freshness"
        )


def recursive_strings(value: Any, *, skip_keys: frozenset[str] = frozenset()) -> Iterable[str]:
    """Yield nested strings iteratively so adversarial JSON depth cannot recurse."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            yield current
        elif isinstance(current, list):
            pending.extend(reversed(current))
        elif isinstance(current, dict):
            pending.extend(
                item
                for key, item in reversed(list(current.items()))
                if key not in skip_keys
            )


def reject_comment_delimiters(value: Any, label: str, errors: list[str]) -> None:
    for text in recursive_strings(value):
        if "-->" in text or "<!--" in text:
            errors.append(f"{label} contains an HTML comment delimiter")
            return


def normalized_claim_text(value: str) -> str:
    """Create a formatting-insensitive view for protected claim classification."""
    normalized = value
    for _ in range(4):
        decoded = html.unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    normalized = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", normalized)
    normalized = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", normalized)
    normalized = normalized.translate(str.maketrans("", "", "*_~`[]()\\"))
    return " ".join(normalized.casefold().split())


def reject_authority_and_implementation_claims(value: Any, label: str, errors: list[str]) -> None:
    explicit_non_authority = re.compile(
        r"\b(?:(?:is|are|was|were|remains?) )?(?:not|never) (?:the )?"
        r"(?:authoritative|canonical|source of truth|truth|authority)\b|"
        r"\b(?:does not|cannot|must not|never) outrank(?:s)?(?: the issue graph)?\b|"
        r"\bhas no authority\b"
    )
    github_board = r"(?:github project(?:s)?(?: board)?|project(?:s)? board)"
    contextual_board = rf"(?:{github_board}|the board)"
    board_reference = rf"(?:(?:a|an|the)\s+)?{github_board}"
    approved_board_patterns = [
        re.compile(
            rf"\b{board_reference}\b\s+(?:is|are|remains?)\s+(?:an?\s+)?"
            r"optional projection(?:\s+and\s+(?:never|cannot|does not|must not)\s+"
            r"outrank(?:s)?(?:\s+the issue graph)?)?\b"
        ),
        re.compile(
            rf"\b{board_reference}\b\s+(?:(?:is|are|was|were|remains?)\s+)?"
            r"(?:not|never)\s+(?:the\s+)?(?:authoritative|canonical|source of truth|"
            r"truth|authority)\b"
        ),
        re.compile(
            rf"\b{board_reference}\b\s+(?:never|cannot|does not|must not)\s+"
            r"outrank(?:s)?(?:\s+the issue graph)?\b"
        ),
        re.compile(rf"\b{board_reference}\b\s+has no authority\b"),
        re.compile(
            rf"\b(?:the\s+)?(?:canonical source of truth|source of truth|canonical truth)\s+"
            rf"(?:is|are)\s+not\s+{board_reference}\b"
        ),
        re.compile(
            rf"\b(?:do not|must not|never)\s+grant\s+(?:final\s+)?authority\s+to\s+"
            rf"{board_reference}\b"
        ),
        re.compile(
            rf"\b(?:do not|must not|never)\s+make\s+{board_reference}\s+"
            r"(?:authoritative|canonical|the source of truth)\b"
        ),
    ]
    board_authority_patterns = [
        re.compile(
            rf"\b{contextual_board}\b\s+(?:(?:is|are|be|becomes?|remains?)|"
            r"(?:(?:shall|must|will|should)\s+be)|(?:(?:serves|acts)\s+as))\s+"
            r"(?:the\s+)?(?:authoritative|canonical|authority|source of truth|truth)\b"
        ),
        re.compile(
            rf"\b(?:canonical source of truth|canonical truth|source of truth|"
            rf"authoritative source|completion truth)\s+(?:is|are|=)\s+(?:the\s+)?"
            rf"{github_board}\b"
        ),
        re.compile(
            rf"\b(?:use|treat)\s+(?:the\s+)?{github_board}\s+as\s+(?:the\s+)?"
            r"(?:truth|source of truth|canonical|authoritative)(?:\s+for\s+completion)?\b"
        ),
        re.compile(
            rf"\bconsider\s+(?:the\s+)?{github_board}\s+(?:the\s+)?"
            r"(?:canonical|authoritative|source of truth)\b"
        ),
        re.compile(rf"\b{contextual_board}\b.{{0,120}}\boutranks?\b"),
        re.compile(
            rf"\b{contextual_board}\b.{{0,120}}\b"
            r"(?:controls?|decides?|determines?|governs?)\s+(?:the\s+)?completion\b"
        ),
    ]
    non_option_b_chain = re.compile(
        r"\b(?:github project(?:s)?(?: board)?|project record)\s*->\s*"
        r"epic issue\s*->\s*task issue\s*->\s*(?:pull request|pr)\s+"
        r"(?:is\s+)?canonical\b"
    )
    safe_negative_status = re.compile(
        r"\b(?:planned[- /]unimplemented|unimplemented|incomplete|unsupported|inactive|"
        r"unavailable|absent|(?:not|never) (?:been )?(?:fully )?(?:implemented|complete|completed|done|"
        r"available|validated|enforced|supported|active|operational|working|ready|shipped|"
        r"live|existent|present|built|created|deployed|delivered)|(?:isn't|aren't|wasn't|"
        r"weren't|hasn't been|haven't been) "
        r"(?:fully )?(?:implemented|complete|completed|done|available|validated|enforced|"
        r"supported|active|operational|working|ready|shipped|live|present|built|created|"
        r"deployed|delivered)|does not (?:exist|work)|doesn't work|"
        r"no (?:task execution envelope|loop[- ]event(?: contract| support)?|k1[01](?: support)?) "
        r"(?:(?:is|are|was|were) )?(?:implemented|complete|completed|done|available|"
        r"validated|enforced|supported|active|operational|working|ready|shipped|live|"
        r"present|built|created|deployed|delivered))\b"
    )
    k_reference = r"\bk1[01](?:(?:\s+(?:and|or)\s+|/)k1[01])?\b"
    approved_k_patterns = [
        re.compile(
            rf"\b(?:it\s+is\s+not\s+parsed\s+or\s+dereferenced\s+and\s+)?"
            rf"(?:does|do)\s+not\s+prove\s+{k_reference}\s+validity,\s+"
            r"freshness,\s+execution,\s+or\s+acceptance\b"
        ),
        re.compile(
            rf"{k_reference}\s+(?:(?:status\s+)?(?:is|are)|has|have)\s+"
            r"(?:a\s+)?minimal[- /]partial[- /]offline(?:[- /]implemented|\s+"
            r"implementation)?\s+only\b"
        ),
        re.compile(
            rf"{k_reference}\s+(?:(?:is|are|was|were)\s+)?implemented\s+only\s+for\s+"
            r"(?:the\s+)?bounded\s+offline\s+t11\s+slice\b"
        ),
        re.compile(
            rf"{k_reference}\s+(?:(?:is|are|remain|remains)\s+)?(?:planned[- /]"
            r"unimplemented|unimplemented|incomplete|unsupported|inactive|unavailable|absent)\b"
        ),
        re.compile(
            rf"{k_reference}\s+(?:(?:is|are|was|were|has|have|remain|remains)\s+)?"
            r"(?:not|never)\s+(?:been\s+)?(?:fully\s+)?(?:implemented|complete|completed|"
            r"done|available|validated|enforced|supported|active|operational|working|ready|"
            r"shipped|live|present|built|created|deployed|delivered)\b"
        ),
        re.compile(
            rf"\bno\s+{k_reference}(?:\s+(?:implementation|functionality|support))?\s+"
            r"(?:(?:is|are|was|were)\s+)?(?:implemented|available|active|operational|"
            r"working|present|ready|live)\b"
        ),
        re.compile(
            rf"\b(?:do not|must not|never)\s+claim(?:\s+that)?\s+{k_reference}\s+"
            r"(?:implementation|(?:(?:is|are)\s+)?(?:implemented|complete|available|"
            r"active|operational|working|present|ready|live))\b"
        ),
        re.compile(
            rf"\bnot\b.{{0,96}}\baccepted as\s+{k_reference}\s+"
            r"(?:acceptance\s+)?evidence\b"
        ),
        re.compile(
            rf"{k_reference}.{{0,64}}\b(?:is|are|does|do|cannot|must not)\b.{{0,32}}\b"
            r"not\b.{{0,32}}\b(?:acceptance\s+)?evidence\b"
        ),
    ]
    runtime_name = r"(?:task[- ]execution[- ]envelope(?:/v1)?|loop[- ]event(?:/v1)?)"
    runtime_reference = rf"(?:{runtime_name}(?: contract| support)?)"
    approved_runtime_patterns = [
        re.compile(
            rf"\b{runtime_name}\s+reference\s+"
            r"optional and opaque\b"
        ),
        re.compile(
            r"\bleave blank unless a durable record supplies an opaque "
            r"loop[- ]event reference\b"
        ),
        re.compile(
            rf"\b(?:the\s+)?{runtime_reference}\b\s+"
            r"(?:(?:status\s+)?(?:is|are)|has|have)\s+"
            r"(?:a\s+)?minimal[- /]partial[- /]offline(?:\s+t11)?"
            r"(?:[- /](?:slice|contract|support|implementation|implemented))?"
            r"\s+only\b"
        ),
        re.compile(
            rf"\b(?:the\s+)?{runtime_reference}\b\s+"
            r"(?:(?:is|are|was|were)\s+)?implemented\s+"
            r"only\s+for\s+(?:the\s+)?bounded\s+offline\s+t11\s+slice\b"
        ),
        re.compile(
            rf"\b(?:the\s+)?{runtime_reference}\s+reference\s+optional and opaque\b"
        ),
        re.compile(
            rf"\b(?:the\s+)?{runtime_reference}\b\s+"
            r"(?:(?:is|are|was|were|has|have|remain|remains)\s+)?"
            r"(?:not|never)\s+(?:been\s+)?(?:implemented|complete|available|active|"
            r"operational|working|present|ready|live|built|created|deployed|delivered)\b"
        ),
        re.compile(
            rf"\b(?:the\s+)?{runtime_reference}\b\s+"
            r"(?:(?:is|are|remain|remains)\s+)?"
            r"(?:planned[- /]unimplemented|unimplemented|incomplete|unsupported|inactive|"
            r"unavailable|absent)\b"
        ),
        re.compile(
            rf"\bno\s+{runtime_reference}\b\s+(?:(?:is|are|was|were)\s+)?"
            r"(?:implemented|available|active|operational|working|present|ready|live|built|"
            r"created|deployed|delivered)\b"
        ),
        re.compile(
            rf"\b(?:do not|must not|never)\s+claim(?:\s+that)?\s+(?:the\s+)?"
            rf"{runtime_reference}\b.{{0,48}}\b(?:implemented|complete|available|active|"
            r"operational|working|present|ready|live)\b"
        ),
    ]
    historical_status = re.compile(
        r"\b(?:recorded|completed|complete|verified|backfilled|performed|created|added|"
        r"posted|written|synthesized)\b"
    )
    safe_negative_history = re.compile(
        r"\b(?:(?:not|never) (?:been )?(?:recorded|completed|complete|verified|"
        r"backfilled|performed|created|added|posted|written|synthesized)|(?:wasn't|weren't|"
        r"hasn't been|haven't been) (?:recorded|completed|complete|verified|backfilled|"
        r"performed|created|added|posted|written|synthesized)|"
        r"no (?:historical ritual(?: record)?|bootstrap (?:claim|plan|dispatch|release|"
        r"evidence|ritual)(?: (?:comment|record|receipt))?) (?:(?:was|were) )?"
        r"(?:recorded|completed|complete|verified|"
        r"backfilled|performed|created|added|posted|written|synthesized))\b"
    )
    safe_negative_retroactive = re.compile(
        r"\b(?:(?:not|never)\s+(?:created|added|posted|written|synthesized)\s+"
        r"retroactiv(?:e|ely)|no\s+(?:historical ritual(?: record)?|bootstrap\s+"
        r"(?:claim|plan|dispatch|release|evidence|ritual|comment)(?:\s+(?:comment|record))?)\s+"
        r"(?:(?:was|were)\s+)?(?:created|added|posted|written|synthesized)\s+"
        r"retroactiv(?:e|ely))\b"
    )
    for text in recursive_strings(
        value,
        skip_keys=frozenset({"task_execution_envelope_ref", "loop_event_ref", "body"}),
    ):
        normalized = normalized_claim_text(text)
        clauses = [
            clause.strip()
            for clause in re.split(r"[;\n]+|(?<=[.!?])\s+", normalized)
            if clause.strip()
        ]
        rejected = False
        for clause in clauses:
            status_text = safe_negative_status.sub("", clause)
            authority_text = explicit_non_authority.sub("", clause)
            board_is_identified = bool(re.search(rf"\b{github_board}\b", normalized))
            bad_board_claim = non_option_b_chain.search(authority_text) or (
                (board_is_identified or "the board" not in authority_text)
                and any(pattern.search(authority_text) for pattern in board_authority_patterns)
            )
            board_residual = clause
            for pattern in approved_board_patterns:
                board_residual = pattern.sub("", board_residual)
            residual_authority = re.search(
                r"\b(?:(?:has|holds?)\s+(?:the\s+)?(?:final|ultimate|canonical)?\s*"
                r"authority|(?:supersedes?|overrides?|displaces?)\s+(?:the\s+)?"
                r"issue graph)\b",
                board_residual,
            )
            if re.search(rf"\b{github_board}\b", board_residual):
                bad_board_claim = True
            if re.search(rf"\b{github_board}\b", clause) and residual_authority:
                bad_board_claim = True
            if bad_board_claim:
                errors.append(f"{label} must not grant authority to a GitHub Projects board")
                rejected = True
                break

            k_residual = clause
            for pattern in approved_k_patterns:
                k_residual = pattern.sub("", k_residual)
            if re.search(r"\bk1[01]\b", clause) and re.search(
                r"[a-z0-9]", k_residual
            ):
                errors.append(
                    f"{label} must limit K10 or K11 claims to the minimal/partial "
                    "offline T11 slice"
                )
                rejected = True
                break

            runtime_residual = clause
            for pattern in approved_runtime_patterns:
                runtime_residual = pattern.sub("", runtime_residual)
            if re.search(rf"\b{runtime_reference}\b", clause) and re.search(
                r"[a-z0-9]", runtime_residual
            ):
                message = (
                    "must limit the Task execution envelope claim to the minimal/partial offline T11 slice"
                    if re.search(r"task[- ]execution[- ]envelope(?:/v1)?", clause)
                    else "must limit the loop-event claim to the minimal/partial offline T11 slice"
                )
                errors.append(f"{label} {message}")
                rejected = True
                break
        if rejected:
            continue
        history_text = safe_negative_history.sub(
            "", safe_negative_retroactive.sub("", normalized)
        )
        if (
            "bootstrap" in normalized
            and re.search(r"\b(?:claim|plan|dispatch|release|evidence|ritual)\b", normalized)
            and historical_status.search(history_text)
        ):
            errors.append(f"{label} must not fabricate bootstrap ritual records")
            continue
        if (
            "historical ritual" in normalized
            and historical_status.search(history_text)
        ) or (
            re.search(
                r"\b(?:retroactiv(?:e|ely)|backfilled|fabricated historical)\b",
                history_text,
            )
            and re.search(r"\b(?:comment|record|receipt|plan|dispatch)\b", history_text)
        ):
            errors.append(f"{label} must not fabricate historical ritual records")


def validate_contract(contract: Any, errors: list[str]) -> None:
    if not exact_keys(
        contract,
        [
            "schema",
            "repository",
            "authority",
            "implementation",
            "progress",
            "runtime_frontier",
            "validation_boundary",
            "bootstrap_compatibility",
            "rendering_semantics",
            "semantics",
            "records",
        ],
        [],
        "contract",
        errors,
    ):
        return
    if contract["schema"] != "ledger-contracts/v1":
        errors.append("contract schema must be ledger-contracts/v1")
    if contract["repository"] != REPOSITORY:
        errors.append("contract repository must be the canonical repository")
    expected_authority = {
        "durable_truth": "issue-graph",
        "canonical_graph": "repository-initiative-or-epic-set -> epic-issue -> task-issue -> pull-request -> commits-checks-evidence",
        "github_projects_board": "optional-projection-never-authoritative",
    }
    if contract["authority"] != expected_authority:
        errors.append("contract must preserve Option B Issue-graph authority")
    expected_implementation = {
        "K01": "static-contract-advanced",
        "K02": "static-contract-advanced",
        "K03": "static-contract-advanced",
        "K04": "static-contract-advanced",
        "K05": "static-contract-advanced",
        "K07": "static-contract-implemented",
        "K10": "minimal-partial-offline-implemented",
        "K11": "minimal-partial-offline-implemented",
        "K14": "static-validation-only",
    }
    if contract["implementation"] != expected_implementation:
        errors.append(
            "contract implementation states must keep K10/K11 at "
            "minimal/partial offline status"
        )
    expected_progress = {
        "contracts_advanced_static": ["K01", "K02", "K03", "K04", "K05", "K07", "K14"],
        "contracts_advanced_minimal_partial_offline": ["K10", "K11"],
        "scenario_families": {
            "C": "not-run",
            "E": "not-run",
            "O": "not-run",
            "T": "not-run",
            "X": "not-run",
        },
    }
    if contract["progress"] != expected_progress:
        errors.append(
            "contract progress must preserve minimal/partial offline K10/K11 "
            "and scenarios not-run"
        )
    expected_frontier = expected_runtime_frontier()
    frontier = contract["runtime_frontier"]
    if not isinstance(frontier, dict):
        errors.append("contract runtime frontier must be an object")
    else:
        if frontier.get("tree_snapshot") != expected_frontier["tree_snapshot"]:
            errors.append("contract runtime frontier tree snapshot drifted")
        if frontier.get("t11_history") != expected_frontier["t11_history"]:
            errors.append("contract runtime frontier T11 history drifted")
        if frontier.get("t12_activation") != expected_frontier["t12_activation"]:
            errors.append("contract runtime frontier T12 activation drifted")
        if frontier.get("status") != expected_frontier["status"]:
            errors.append("contract runtime frontier status drifted")
        if (
            frontier.get("canonical_release_boundary")
            != expected_frontier["canonical_release_boundary"]
        ):
            errors.append("contract runtime frontier release boundary drifted")
        if frontier != expected_frontier:
            errors.append(
                "contract runtime frontier must contain only the exact reviewed fields"
            )
    expected_boundary = {
        "validated_offline": [
            "canonical same-repository URL shape",
            "frozen bootstrap Issue body hashes and heading-to-section mappings",
            "non-placeholder field values",
            "record shape and internal cross-reference integrity",
            "template and rendered-fixture synchronization",
            "K10 and K11 minimal-partial-offline status vocabulary",
            "opaque runtime-reference non-evidence boundary",
        ],
        "not_validated_offline": [
            "GitHub API object existence or native type",
            "current GitHub Issue body equality after the recorded observation",
            "issue parent or dependency state",
            "plan-comment authorship, edit history, or chronology",
            "Actions run or job URL association with the declared head SHA",
            "live labels or current-attempt ritual enforcement",
            "real Codex execution or runtime-profile match",
            "live runtime receipt existence, freshness, or acceptance",
            "full K10, K11, runtime, or cross-surface parity",
        ],
    }
    if contract["validation_boundary"] != expected_boundary:
        errors.append("contract static validation boundary drifted or overclaims proof")
    expected_bootstrap = {
        "mode": "narrow-static-body",
        "historical_ritual_synthesis": False,
        "template_adoption_is_not_historical_compliance": True,
        "static_heading_aliases": {
            "epic.decomposition_and_dependency_graph": ["Task graph and dependencies"],
            "epic.acceptance_and_evidence": ["Acceptance"],
            "task.objective_and_scope": ["Objective", "Rationale", "Out of scope"],
            "task.dependencies_and_references": ["Dependencies / blocked by"],
            "task.risk_and_constraints": ["Risk and human gates"],
            "task.verification_and_evidence": ["Verification / evidence"],
            "task.routing_and_execution": ["Expected pull-request boundary"],
            "task.completion_and_relationships": [
                "Contract and conformance coverage",
                "Completion boundary",
            ],
        },
    }
    if contract["bootstrap_compatibility"] != expected_bootstrap:
        errors.append("contract bootstrap compatibility must not synthesize history")
    expected_rendering = {
        "issue_form_markdown_elements": "displayed-in-form-not-submitted",
        "submitted_issue_body": "field-label-headings-and-values-only",
        "empty_optional_input_or_textarea": "submitted-as-_No response_",
        "pull_request_template_headings": "persisted-markdown",
    }
    if contract["rendering_semantics"] != expected_rendering:
        errors.append("contract Issue Form persistence semantics drifted")
    expected_semantics = {
        "risk_tiers": ["A", "B", "C", "D"],
        "evidence_results": ["pass", "fail", "blocked", "not-run", "UNKNOWN", "UNCHECKABLE"],
        "evidence_success_results": ["pass"],
        "none_token": "None",
        "ownership_modes": ["100644", "100755"],
        "optional_opaque_fields": ["task_execution_envelope_ref", "loop_event_ref"],
        "runtime_contract_statuses": ["minimal-partial-offline-implemented"],
        "opaque_runtime_reference_format": (
            "opaque-ref/v1:<field-kind>:sha256:<64-lowercase-hex>"
        ),
        "opaque_runtime_reference_evidence": (
            "linkage-only-never-validity-freshness-execution-or-acceptance"
        ),
    }
    if contract["semantics"] != expected_semantics:
        errors.append("contract ledger semantics drifted")
    records = contract["records"]
    if not isinstance(records, dict) or list(records) != ["epic", "task", "pull_request"]:
        errors.append("contract records must be ordered epic, task, pull_request")
        return
    expected_paths = {
        "epic": ".github/ISSUE_TEMPLATE/epic.yml",
        "task": ".github/ISSUE_TEMPLATE/ai-task.yml",
        "pull_request": ".github/PULL_REQUEST_TEMPLATE.md",
    }
    expected_locators = {
        "epic": ["record_type", "issue_url"],
        "task": ["record_type", "issue_url"],
        "pull_request": ["record_type", "pr_url", "task_url"],
    }
    for kind, expected_sections in EXPECTED_LAYOUT.items():
        record = records.get(kind)
        if not exact_keys(
            record,
            ["template_path", "template", "locator_fields", "sections"],
            [],
            f"contract.records.{kind}",
            errors,
        ):
            continue
        if record["template_path"] != expected_paths[kind]:
            errors.append(f"contract.records.{kind}.template_path drifted")
        if record["locator_fields"] != expected_locators[kind]:
            errors.append(f"contract.records.{kind}.locator_fields drifted")
        template = record["template"]
        template_keys = (
            {"title"}
            if kind == "pull_request"
            else {"name", "description", "title", "labels", "assignees"}
        )
        if not isinstance(template, dict) or set(template) != template_keys:
            errors.append(f"contract.records.{kind}.template metadata drifted")
        elif template != EXPECTED_METADATA[kind]:
            errors.append(f"contract.records.{kind}.template metadata values drifted")
        sections = record["sections"]
        if not isinstance(sections, list) or len(sections) != len(expected_sections):
            errors.append(f"contract.records.{kind}.sections count drifted")
            continue
        headings = []
        seen_fields: set[str] = set()
        actual_layout: list[tuple[str, list[tuple[str, str, bool]]]] = []
        for section_index, section in enumerate(sections):
            section_label = f"contract.records.{kind}.sections[{section_index}]"
            if not exact_keys(section, ["id", "heading", "fields"], [], section_label, errors):
                continue
            headings.append(section.get("heading"))
            fields = section.get("fields")
            if not isinstance(fields, list) or not fields:
                errors.append(f"{section_label}.fields must be a non-empty list")
                continue
            actual_fields = []
            for field_index, field in enumerate(fields):
                field_label = f"{section_label}.fields[{field_index}]"
                field_type = field.get("type") if isinstance(field, dict) else None
                keys = ["id", "type", "label", "description", "required"]
                if field_type == "dropdown":
                    keys.append("options")
                else:
                    keys.append("placeholder")
                if not exact_keys(field, keys, [], field_label, errors):
                    continue
                field_id = field["id"]
                if not isinstance(field_id, str) or not IDENTIFIER.fullmatch(field_id):
                    errors.append(f"{field_label}.id is invalid")
                else:
                    if field_id in seen_fields:
                        errors.append(f"contract.records.{kind} has duplicate field id {field_id}")
                    seen_fields.add(field_id)
                for text_key in ("label", "description"):
                    valid_string(field[text_key], f"{field_label}.{text_key}", errors)
                expected_label = (
                    EXPECTED_LABELS[kind].get(field_id)
                    if isinstance(field_id, str)
                    else None
                )
                if field.get("label") != expected_label:
                    errors.append(f"{field_label}.label drifted")
                if field_type != "dropdown":
                    valid_string(field["placeholder"], f"{field_label}.placeholder", errors)
                if not isinstance(field["required"], bool):
                    errors.append(f"{field_label}.required must be boolean")
                if field_type == "dropdown" and field.get("options") != ["A", "B", "C", "D"]:
                    errors.append(f"{field_label}.options must be exactly A-D")
                actual_fields.append((field_id, field_type, field["required"]))
            actual_layout.append((section.get("id"), actual_fields))
        if actual_layout != expected_sections:
            errors.append(f"contract.records.{kind} ordered field layout drifted")
        if headings != EXPECTED_HEADINGS[kind]:
            errors.append(f"contract.records.{kind} ordered headings drifted")
    reject_authority_and_implementation_claims(
        contract["records"], "contract prose", errors
    )


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_issue_form(record: dict[str, Any]) -> str:
    metadata = record["template"]
    lines = [
        f"name: {yaml_scalar(metadata['name'])}",
        f"description: {yaml_scalar(metadata['description'])}",
        f"title: {yaml_scalar(metadata['title'])}",
        "labels: []",
        "assignees: []",
        "body:",
    ]
    for section in record["sections"]:
        lines.extend(
            [
                "  - type: markdown",
                "    attributes:",
                f"      value: {yaml_scalar('## ' + section['heading'])}",
            ]
        )
        for field in section["fields"]:
            lines.extend(
                [
                    f"  - type: {field['type']}",
                    f"    id: {field['id']}",
                    "    attributes:",
                    f"      label: {yaml_scalar(field['label'])}",
                    f"      description: {yaml_scalar(field['description'])}",
                ]
            )
            if field["type"] == "dropdown":
                lines.append("      options:")
                lines.extend(f"        - {yaml_scalar(option)}" for option in field["options"])
            else:
                lines.append(f"      placeholder: {yaml_scalar(field['placeholder'])}")
            lines.extend(
                [
                    "    validations:",
                    f"      required: {'true' if field['required'] else 'false'}",
                ]
            )
    return "\n".join(lines) + "\n"


def render_pr_template(record: dict[str, Any]) -> str:
    lines = [
        "<!-- ledger-contract: pull-request/v1 -->",
        "<!--",
        "This is a static ledger form. Use concrete durable URLs and current-head evidence.",
        "Offline validation checks shape and internal consistency only; it does not prove",
        "GitHub object existence, authorship, edit history, chronology, labels, or live ritual state.",
        "Do not grant authority to a GitHub Projects board, fabricate historical ritual records,",
        "or claim full/runtime parity for K10 or K11. Their current repository status is limited",
        "to the accepted minimal/partial offline T11 slice. T12 live evidence is external GitHub",
        "state and must be exact-head bound; opaque references do not prove validity, freshness,",
        "live execution, or acceptance.",
        "Opaque runtime references are bounded linkage only. Only the locator grammar is parsed.",
        "The referenced target is neither resolved nor dereferenced, and the value proves neither",
        "target validity nor target freshness; it provides no evidence of implementation, execution,",
        "or acceptance.",
        "-->",
    ]
    for section in record["sections"]:
        lines.extend(["", f"## {section['heading']}"])
        for field in section["fields"]:
            lines.extend(
                [
                    "",
                    f"<!-- field:{field['id']} type:{field['type']} required:{str(field['required']).lower()} -->",
                    f"### {field['label']}",
                    "",
                    "<!--",
                    f"Description: {field['description']}",
                    f"Prompt: {field['placeholder']}",
                    "-->",
                ]
            )
    return "\n".join(lines) + "\n"


def format_record_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_record(kind: str, contract_record: dict[str, Any], record: dict[str, Any]) -> str:
    locator = "issue_url" if kind in {"epic", "task"} else "pr_url"
    boundary = (
        "<!-- Submitted Issue body oracle: type:markdown groups are displayed in the form "
        "but not submitted; persisted field-label headings follow. -->"
        if kind in {"epic", "task"}
        else "<!-- Example static record; URL existence and chronology are outside offline validation. -->"
    )
    lines = [
        f"<!-- ledger-rendered-record: {kind}/v1 -->",
        boundary,
        f"Record URL: {record[locator]}",
    ]
    for section in contract_record["sections"]:
        if kind == "pull_request":
            lines.extend(["", f"## {section['heading']}"])
        for field in section["fields"]:
            if field["id"] in record:
                rendered_value = format_record_value(record[field["id"]])
            elif kind in {"epic", "task"} and not field["required"]:
                rendered_value = (
                    "None" if field["type"] == "dropdown" else "_No response_"
                )
            else:
                continue
            lines.extend(
                [
                    "",
                    f"### {field['label']}",
                    "",
                    rendered_value,
                ]
            )
    return "\n".join(lines) + "\n"


def validate_templates(root: Path, contract: dict[str, Any], errors: list[str]) -> None:
    if errors:
        return
    for kind in ("epic", "task"):
        record = contract["records"][kind]
        try:
            actual = read_regular_text(root, record["template_path"])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        expected = render_issue_form(record)
        if actual != expected:
            errors.append(f"{record['template_path']} is not synchronized with the contract")
    record = contract["records"]["pull_request"]
    try:
        actual = read_regular_text(root, record["template_path"])
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if actual != render_pr_template(record):
            errors.append(f"{record['template_path']} is not synchronized with the contract")


def dependency_values(value: Any, label: str, errors: list[str]) -> list[str] | None:
    if value == "None":
        return []
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be None or a non-empty list of Task Issue URLs")
        return None
    dependencies: list[str] = []
    for index, item in enumerate(value):
        if issue_number(item, f"{label}[{index}]", errors) is not None:
            dependencies.append(item)
    if len(dependencies) != len(set(dependencies)):
        errors.append(f"{label} contains duplicate dependency links")
    return dependencies


def validate_task_graph(value: Any, errors: list[str]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    if not isinstance(value, list) or not value:
        errors.append("epic.task_graph must be a non-empty list")
        return graph
    for index, node in enumerate(value):
        label = f"epic.task_graph[{index}]"
        if not exact_keys(node, ["task_url", "dependencies"], [], label, errors):
            continue
        task_url = node.get("task_url")
        if issue_number(task_url, f"{label}.task_url", errors) is None:
            continue
        if task_url in graph:
            errors.append(f"epic.task_graph contains duplicate Task node {task_url}")
            continue
        dependencies = dependency_values(node.get("dependencies"), f"{label}.dependencies", errors)
        graph[task_url] = dependencies or []
    known = set(graph)
    for task_url, dependencies in graph.items():
        for dependency in dependencies:
            if dependency == task_url:
                errors.append(f"epic.task_graph Task {task_url} depends on itself")
            elif dependency not in known:
                errors.append(f"epic.task_graph dependency is an unknown Task node: {dependency}")
    pending = {
        node: {dependency for dependency in dependencies if dependency in graph}
        for node, dependencies in graph.items()
    }
    ready = [node for node, dependencies in pending.items() if not dependencies]
    visited: set[str] = set()
    while ready:
        node = ready.pop()
        if node in visited:
            continue
        visited.add(node)
        for candidate, dependencies in pending.items():
            if node in dependencies:
                dependencies.remove(node)
                if not dependencies and candidate not in visited:
                    ready.append(candidate)
    if len(visited) != len(graph):
        cycle_node = sorted(set(graph) - visited)[0]
        errors.append(f"epic.task_graph contains a dependency cycle at {cycle_node}")
    return graph


def canonical_ownership_pattern(value: Any, label: str, errors: list[str]) -> tuple[str, tuple[str, ...]] | None:
    if not valid_string(value, label, errors):
        return None
    if value != unicodedata.normalize("NFC", value):
        errors.append(f"{label} must use NFC Unicode normalization")
        return None
    if re.match(r"^[A-Za-z]:[/\\]", value) or value.startswith(("//", "\\\\")):
        errors.append(f"{label} must not use Windows drive or UNC syntax")
        return None
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        errors.append(f"{label} must be a relative slash-separated repository pattern")
        return None
    if any(unicodedata.category(char).startswith("C") for char in value):
        errors.append(f"{label} contains a control or format character")
        return None
    recursive = value.endswith("/**")
    literal = value[:-3] if recursive else value
    if any(char in literal for char in "*?[") or ("*" in value and not recursive):
        errors.append(f"{label} supports only exact paths or a terminal /** pattern")
        return None
    parts = literal.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        errors.append(f"{label} is not normalized")
        return None
    if any(part.endswith((".", " ")) for part in parts):
        errors.append(f"{label} has a component ending in a Windows-ambiguous dot or space")
        return None
    if any(any(char in part for char in '<>:"|?*') for part in parts):
        errors.append(f"{label} contains a Windows-reserved path character")
        return None
    if any(WINDOWS_RESERVED_COMPONENT.fullmatch(part) for part in parts):
        errors.append(f"{label} contains a Windows-reserved device component")
        return None
    normalized = "/".join(part.casefold() for part in parts)
    kind = "recursive" if recursive else "exact"
    return kind, tuple(normalized.split("/"))


def ownership_overlaps(first: tuple[str, tuple[str, ...]], second: tuple[str, tuple[str, ...]]) -> bool:
    first_parts = first[1]
    second_parts = second[1]
    shortest = min(len(first_parts), len(second_parts))
    return first_parts[:shortest] == second_parts[:shortest]


def validate_ownership(tasks: list[dict[str, Any]], modes: list[str], errors: list[str]) -> None:
    seen: list[tuple[str, str, tuple[str, tuple[str, ...]]]] = []
    for task_index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        task_url = task.get("issue_url", f"task[{task_index}]")
        ownership = task.get("ownership")
        label = f"tasks[{task_index}].ownership"
        if not isinstance(ownership, list) or not ownership:
            errors.append(f"{label} must be a non-empty list")
            continue
        for entry_index, entry in enumerate(ownership):
            entry_label = f"{label}[{entry_index}]"
            if not exact_keys(entry, ["pattern", "mode"], [], entry_label, errors):
                continue
            if entry.get("mode") not in modes:
                errors.append(f"{entry_label}.mode is invalid")
            normalized = canonical_ownership_pattern(entry.get("pattern"), f"{entry_label}.pattern", errors)
            if normalized is None:
                continue
            for prior_task, prior_pattern, prior_normalized in seen:
                if ownership_overlaps(prior_normalized, normalized):
                    errors.append(
                        f"ownership overlap: {prior_pattern} ({prior_task}) and "
                        f"{entry['pattern']} ({task_url})"
                    )
            seen.append((task_url, entry["pattern"], normalized))


def validate_criteria(value: Any, label: str, errors: list[str], *, evidence: bool) -> set[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return set()
    seen: set[str] = set()
    required = ["id", "criterion"] + (["evidence_required"] if evidence else [])
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if not exact_keys(item, required, [], item_label, errors):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not CRITERION_ID.fullmatch(identifier):
            errors.append(f"{item_label}.id must be a stable criterion identifier")
        else:
            if identifier in seen:
                errors.append(f"{label} contains duplicate criterion ID {identifier}")
            seen.add(identifier)
        valid_string(item.get("criterion"), f"{item_label}.criterion", errors)
        if evidence:
            valid_string(item.get("evidence_required"), f"{item_label}.evidence_required", errors)
    return seen


def validate_iso_timestamp(value: Any, label: str, errors: list[str]) -> None:
    if not valid_string(value, label, errors):
        return
    if not value.endswith("Z"):
        errors.append(f"{label} must be an explicit UTC timestamp ending in Z")
        return
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        errors.append(f"{label} must be an ISO-8601 UTC timestamp")
        return
    if parsed.tzinfo != dt.timezone.utc:
        errors.append(f"{label} must be UTC")


def validate_evidence_url(value: Any, head_sha: Any, label: str, errors: list[str]) -> None:
    if not valid_string(value, label, errors):
        return
    commit_match = COMMIT_URL.fullmatch(value)
    if commit_match:
        if commit_match.group(1) != head_sha:
            errors.append(f"{label} embedded commit SHA must match the pull-request head")
        return
    if ACTIONS_URL.fullmatch(value):
        return
    errors.append(
        f"{label} must be a same-repository commit/check URL or Actions run/job URL"
    )


def validate_evidence(
    value: Any,
    head_sha: Any,
    results: list[str],
    errors: list[str],
) -> tuple[set[str], set[str]]:
    if not isinstance(value, list) or not value:
        errors.append("pull_request.evidence must be a non-empty list")
        return set(), set()
    seen_ids: set[str] = set()
    seen_criteria: set[str] = set()
    for index, item in enumerate(value):
        label = f"pull_request.evidence[{index}]"
        if not exact_keys(
            item,
            [
                "id",
                "criterion_id",
                "check",
                "result",
                "evidence_url",
                "head_sha",
                "observed_at",
            ],
            [],
            label,
            errors,
        ):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not EVIDENCE_ID.fullmatch(identifier):
            errors.append(f"{label}.id must be a stable evidence identifier")
        else:
            if identifier in seen_ids:
                errors.append(f"pull_request.evidence contains duplicate ID {identifier}")
            seen_ids.add(identifier)
        criterion_id = item.get("criterion_id")
        if not isinstance(criterion_id, str) or not CRITERION_ID.fullmatch(criterion_id):
            errors.append(f"{label}.criterion_id must be a stable Task criterion identifier")
        else:
            if criterion_id in seen_criteria:
                errors.append(
                    f"pull_request.evidence contains duplicate criterion ID {criterion_id}"
                )
            seen_criteria.add(criterion_id)
        valid_string(item.get("check"), f"{label}.check", errors)
        if item.get("result") not in results:
            errors.append(f"{label}.result is invalid")
        validate_evidence_url(
            item.get("evidence_url"), head_sha, f"{label}.evidence_url", errors
        )
        if item.get("head_sha") != head_sha:
            errors.append(f"{label}.head_sha must match the exact pull-request head")
        validate_iso_timestamp(item.get("observed_at"), f"{label}.observed_at", errors)
    return seen_criteria, seen_ids


def validate_deferred(value: Any, errors: list[str]) -> tuple[set[str], set[str]]:
    if value == "None":
        return set(), set()
    if not isinstance(value, list) or not value:
        errors.append("pull_request.deferred_evidence must be None or a non-empty list")
        return set(), set()
    seen_ids: set[str] = set()
    seen_criteria: set[str] = set()
    for index, item in enumerate(value):
        label = f"pull_request.deferred_evidence[{index}]"
        if not exact_keys(
            item,
            ["id", "criterion_id", "reason", "owner", "follow_up_url"],
            [],
            label,
            errors,
        ):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not EVIDENCE_ID.fullmatch(identifier):
            errors.append(f"{label}.id must be a stable deferred-evidence identifier")
        else:
            if identifier in seen_ids:
                errors.append(f"pull_request.deferred_evidence contains duplicate ID {identifier}")
            seen_ids.add(identifier)
        criterion_id = item.get("criterion_id")
        if not isinstance(criterion_id, str) or not CRITERION_ID.fullmatch(criterion_id):
            errors.append(f"{label}.criterion_id must be a stable Task criterion identifier")
        else:
            if criterion_id in seen_criteria:
                errors.append(
                    f"pull_request.deferred_evidence contains duplicate criterion ID {criterion_id}"
                )
            seen_criteria.add(criterion_id)
        valid_string(item.get("reason"), f"{label}.reason", errors)
        valid_string(item.get("owner"), f"{label}.owner", errors)
        issue_number(item.get("follow_up_url"), f"{label}.follow_up_url", errors)
    return seen_criteria, seen_ids


def record_field_sets(contract: dict[str, Any], kind: str) -> tuple[list[str], list[str]]:
    spec = contract["records"][kind]
    required = list(spec["locator_fields"])
    optional = []
    for section in spec["sections"]:
        for field in section["fields"]:
            (required if field["required"] else optional).append(field["id"])
    return required, optional


def validate_bootstrap_snapshots(
    contract: dict[str, Any], value: Any, errors: list[str]
) -> None:
    label = "ledger fixture.bootstrap_snapshots"
    if not exact_keys(value, ["source", "observed_at", "issues"], [], label, errors):
        return
    if value["source"] != "read-only GitHub Issue API body snapshot":
        errors.append(f"{label}.source must identify the read-only GitHub Issue API")
    validate_iso_timestamp(value["observed_at"], f"{label}.observed_at", errors)
    if value["observed_at"] != EXPECTED_BOOTSTRAP_OBSERVED_AT:
        errors.append(f"{label}.observed_at drifted from the frozen observation")
    issues = value["issues"]
    if not isinstance(issues, list) or len(issues) != 2:
        errors.append(f"{label}.issues must contain exactly the Epic and Task snapshots")
        return
    seen_kinds: set[str] = set()
    aliases = contract["bootstrap_compatibility"]["static_heading_aliases"]
    for index, snapshot in enumerate(issues):
        snapshot_label = f"{label}.issues[{index}]"
        if not exact_keys(
            snapshot,
            [
                "kind",
                "issue_url",
                "body_sha256",
                "body",
                "ordered_headings",
                "heading_mapping",
            ],
            [],
            snapshot_label,
            errors,
        ):
            continue
        kind = snapshot.get("kind")
        if kind not in EXPECTED_BOOTSTRAP_SNAPSHOTS:
            errors.append(f"{snapshot_label}.kind must be epic or task")
            continue
        if kind in seen_kinds:
            errors.append(f"{label}.issues contains duplicate kind {kind}")
        seen_kinds.add(kind)
        expected = EXPECTED_BOOTSTRAP_SNAPSHOTS[kind]
        if snapshot.get("issue_url") != expected["issue_url"]:
            errors.append(f"{snapshot_label}.issue_url drifted from the frozen Issue")
        body_sha = snapshot.get("body_sha256")
        if not isinstance(body_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", body_sha):
            errors.append(f"{snapshot_label}.body_sha256 must be a lowercase SHA-256")
        elif body_sha != expected["body_sha256"]:
            errors.append(f"{snapshot_label}.body_sha256 drifted from the frozen Issue body")
        body = snapshot.get("body")
        body_is_safe = isinstance(body, str) and 0 < len(body) <= MAX_STRING_LENGTH
        if body_is_safe:
            body_is_safe = not any(
                unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"}
                and char not in "\n\t"
                for char in body
            )
        if (
            not body_is_safe
            or "<!--" in body
            or "-->" in body
            or HTML_CHARACTER_REFERENCE.search(body)
        ):
            errors.append(f"{snapshot_label}.body must be a bounded safe frozen Markdown body")
            extracted_headings: list[str] = []
        else:
            actual_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if actual_sha != body_sha:
                errors.append(f"{snapshot_label}.body does not match body_sha256")
            extracted_headings = re.findall(r"(?m)^## ([^\n]+)$", body)
        headings = snapshot.get("ordered_headings")
        valid_headings = (
            isinstance(headings, list)
            and headings
            and all(isinstance(heading, str) and heading for heading in headings)
        )
        if not valid_headings:
            errors.append(f"{snapshot_label}.ordered_headings must be a non-empty string list")
            headings = []
        else:
            if len(headings) != len(set(headings)):
                errors.append(f"{snapshot_label}.ordered_headings contains duplicates")
            if headings != extracted_headings:
                errors.append(
                    f"{snapshot_label}.ordered_headings must exactly match the frozen body"
                )
            if headings != expected["ordered_headings"]:
                errors.append(f"{snapshot_label}.ordered_headings drifted from the frozen Issue")
        mappings = snapshot.get("heading_mapping")
        if not isinstance(mappings, list) or not mappings:
            errors.append(f"{snapshot_label}.heading_mapping must be a non-empty list")
            continue
        mapped_headings: list[str] = []
        mapped_sections: list[str] = []
        for mapping_index, mapping in enumerate(mappings):
            mapping_label = f"{snapshot_label}.heading_mapping[{mapping_index}]"
            if not exact_keys(mapping, ["heading", "section_id"], [], mapping_label, errors):
                continue
            heading = mapping.get("heading")
            section_id = mapping.get("section_id")
            if not isinstance(heading, str) or not heading:
                errors.append(f"{mapping_label}.heading must be a non-empty string")
                continue
            if not isinstance(section_id, str) or not section_id:
                errors.append(f"{mapping_label}.section_id must be a non-empty string")
                continue
            mapped_headings.append(heading)
            mapped_sections.append(section_id)
            sections = {
                section["id"]: section["heading"]
                for section in contract["records"][kind]["sections"]
            }
            if section_id not in sections:
                errors.append(f"{mapping_label}.section_id is unknown")
                continue
            allowed = {sections[section_id]} | set(
                aliases.get(f"{kind}.{section_id}", [])
            )
            if heading not in allowed:
                errors.append(
                    f"{mapping_label}.heading is not allowed by the canonical heading or alias contract"
                )
        if len(mapped_headings) != len(set(mapped_headings)):
            errors.append(f"{snapshot_label}.heading_mapping contains duplicate headings")
        if mapped_headings != headings:
            if set(mapped_headings) == set(headings) and len(mapped_headings) == len(headings):
                errors.append(f"{snapshot_label}.heading_mapping is out of frozen-body order")
            else:
                errors.append(
                    f"{snapshot_label}.heading_mapping has missing, unknown, or unmapped headings"
                )
        required_sections = {
            section["id"] for section in contract["records"][kind]["sections"]
        }
        mapped_section_set = set(mapped_sections)
        if mapped_section_set != required_sections:
            missing = sorted(required_sections - mapped_section_set)
            unknown = sorted(mapped_section_set - required_sections)
            if missing:
                errors.append(
                    f"{snapshot_label}.heading_mapping leaves required groups unmapped: "
                    + ", ".join(missing)
                )
            if unknown:
                errors.append(
                    f"{snapshot_label}.heading_mapping targets unknown groups: "
                    + ", ".join(unknown)
                )
    if seen_kinds != set(EXPECTED_BOOTSTRAP_SNAPSHOTS):
        errors.append(f"{label}.issues must contain one epic and one task snapshot")
    actual_kind_order = [
        snapshot.get("kind") for snapshot in issues if isinstance(snapshot, dict)
    ]
    if actual_kind_order != ["epic", "task"]:
        errors.append(f"{label}.issues must remain ordered epic, task")


def validate_records(contract: dict[str, Any], payload: Any, errors: list[str]) -> None:
    reject_comment_delimiters(payload, "ledger fixture", errors)
    if not exact_keys(
        payload,
        ["schema", "repository", "bootstrap_snapshots", "records"],
        [],
        "ledger fixture",
        errors,
    ):
        return
    if payload["schema"] != "ledger-records/v1":
        errors.append("ledger fixture schema must be ledger-records/v1")
    if payload["repository"] != REPOSITORY:
        errors.append("ledger fixture repository must be canonical")
    validate_bootstrap_snapshots(contract, payload["bootstrap_snapshots"], errors)
    records = payload["records"]
    if not exact_keys(records, ["epic", "tasks", "pull_requests"], [], "ledger fixture.records", errors):
        return
    epic = records["epic"]
    epic_required, epic_optional = record_field_sets(contract, "epic")
    if not exact_keys(epic, epic_required, epic_optional, "epic", errors):
        return
    if epic.get("record_type") != "epic":
        errors.append("epic.record_type must be epic")
    epic_number = issue_number(epic.get("issue_url"), "epic.issue_url", errors)
    valid_string(epic.get("goal"), "epic.goal", errors)
    string_list(epic.get("scope"), "epic.scope", errors)
    string_list(epic.get("non_goals"), "epic.non_goals", errors, allow_none=True)
    graph = validate_task_graph(epic.get("task_graph"), errors)
    valid_string(epic.get("dependency_policy"), "epic.dependency_policy", errors)
    validate_criteria(epic.get("acceptance_criteria"), "epic.acceptance_criteria", errors, evidence=True)
    string_list(epic.get("evidence_requirements"), "epic.evidence_requirements", errors)
    valid_string(epic.get("planning_owner"), "epic.planning_owner", errors)
    valid_string(epic.get("control_policy"), "epic.control_policy", errors)

    tasks = records["tasks"]
    if not isinstance(tasks, list) or not tasks:
        errors.append("ledger fixture.records.tasks must be a non-empty list")
        tasks = []
    task_urls: set[str] = set()
    task_by_url: dict[str, dict[str, Any]] = {}
    task_criteria_by_url: dict[str, set[str]] = {}
    primary_pr_claims: dict[str, str] = {}
    task_required, task_optional = record_field_sets(contract, "task")
    for index, task in enumerate(tasks):
        label = f"tasks[{index}]"
        if not exact_keys(task, task_required, task_optional, label, errors):
            continue
        if task.get("record_type") != "task":
            errors.append(f"{label}.record_type must be task")
        task_url = task.get("issue_url")
        if issue_number(task_url, f"{label}.issue_url", errors) is None:
            continue
        if task_url in task_urls:
            errors.append(f"ledger fixture contains duplicate Task record {task_url}")
        task_urls.add(task_url)
        task_by_url[task_url] = task
        if task_url not in graph:
            errors.append(f"{label}.issue_url is missing from the Epic Task graph")
        valid_string(task.get("objective"), f"{label}.objective", errors)
        string_list(task.get("scope"), f"{label}.scope", errors)
        task_criteria_by_url[task_url] = validate_criteria(
            task.get("acceptance_criteria"),
            f"{label}.acceptance_criteria",
            errors,
            evidence=False,
        )
        if issue_number(task.get("epic_url"), f"{label}.epic_url", errors) is not None:
            if task["epic_url"] != epic.get("issue_url"):
                errors.append(f"{label}.epic_url must match the ledger Epic")
        dependencies = dependency_values(task.get("dependencies"), f"{label}.dependencies", errors)
        if dependencies is not None and task_url in graph and dependencies != graph[task_url]:
            errors.append(f"{label}.dependencies must exactly match the Epic Task graph")
        references = task.get("references")
        if references != "None":
            values = string_list(references, f"{label}.references", errors)
            if values is not None:
                for reference_index, reference in enumerate(values):
                    reference_url(reference, f"{label}.references[{reference_index}]", errors)
        if task.get("risk_tier") not in contract["semantics"]["risk_tiers"]:
            errors.append(f"{label}.risk_tier must be one of A, B, C, or D")
        valid_string(task.get("risk_rationale"), f"{label}.risk_rationale", errors)
        string_list(task.get("risk_constraints"), f"{label}.risk_constraints", errors)
        string_list(task.get("verification_commands"), f"{label}.verification_commands", errors)
        string_list(task.get("evidence_requirements"), f"{label}.evidence_requirements", errors)
        valid_string(task.get("routing"), f"{label}.routing", errors)
        valid_string(task.get("execution"), f"{label}.execution", errors)
        string_list(task.get("completion_conditions"), f"{label}.completion_conditions", errors)
        relationships = task.get("relationships")
        if exact_keys(relationships, ["epic_url", "primary_pr"], [], f"{label}.relationships", errors):
            if relationships["epic_url"] != epic.get("issue_url"):
                errors.append(f"{label}.relationships.epic_url must match the ledger Epic")
            if relationships["primary_pr"] != "None":
                primary_pr = relationships["primary_pr"]
                if pull_number(
                    primary_pr, f"{label}.relationships.primary_pr", errors
                ) is not None:
                    previous = primary_pr_claims.get(primary_pr)
                    if previous is not None and previous != task_url:
                        errors.append(
                            f"conflicting Tasks claim the same primary PR: {primary_pr}"
                        )
                    else:
                        primary_pr_claims[primary_pr] = task_url
        for opaque in contract["semantics"]["optional_opaque_fields"]:
            if opaque in task:
                validate_opaque_runtime_reference(
                    task[opaque], opaque, f"{label}.{opaque}", errors
                )
    validate_ownership(tasks, contract["semantics"]["ownership_modes"], errors)
    if graph and set(graph) != task_urls:
        missing = sorted(set(graph) - task_urls)
        extra = sorted(task_urls - set(graph))
        if missing:
            errors.append("Epic Task graph has no corresponding Task record: " + ", ".join(missing))
        if extra:
            errors.append("Task record is unknown to the Epic graph: " + ", ".join(extra))

    pull_requests = records["pull_requests"]
    if not isinstance(pull_requests, list) or not pull_requests:
        errors.append("ledger fixture.records.pull_requests must be a non-empty list")
        pull_requests = []
    pr_required, pr_optional = record_field_sets(contract, "pull_request")
    pull_urls: set[str] = set()
    pull_task_by_url: dict[str, str] = {}
    for index, pull_request in enumerate(pull_requests):
        label = f"pull_requests[{index}]"
        if not exact_keys(pull_request, pr_required, pr_optional, label, errors):
            continue
        if pull_request.get("record_type") != "pull_request":
            errors.append(f"{label}.record_type must be pull_request")
        pr_url = pull_request.get("pr_url")
        if pull_number(pr_url, f"{label}.pr_url", errors) is not None:
            if pr_url in pull_urls:
                errors.append(f"ledger fixture contains duplicate pull-request record {pr_url}")
            pull_urls.add(pr_url)
        task_url = pull_request.get("task_url")
        task_number = issue_number(task_url, f"{label}.task_url", errors)
        if not isinstance(task_url, str) or task_url not in task_by_url:
            errors.append(f"{label}.task_url must identify exactly one ledger Task")
        validate_task_relationship(
            pull_request.get("task_relationship"),
            task_url,
            f"{label}.task_relationship",
            errors,
        )
        if (
            isinstance(pr_url, str)
            and pr_url in pull_urls
            and isinstance(task_url, str)
        ):
            pull_task_by_url[pr_url] = task_url
        plan_url = pull_request.get("plan_comment_url")
        if valid_string(plan_url, f"{label}.plan_comment_url", errors):
            match = COMMENT_URL.fullmatch(plan_url)
            if not match:
                errors.append(f"{label}.plan_comment_url must be a concrete same-repository issuecomment URL")
            elif task_number is not None and int(match.group(1)) != task_number:
                errors.append(f"{label}.plan_comment_url must belong to the primary Task")
        valid_string(pull_request.get("summary"), f"{label}.summary", errors)
        string_list(pull_request.get("scope"), f"{label}.scope", errors)
        head_sha = pull_request.get("head_sha")
        if not isinstance(head_sha, str) or not SHA.fullmatch(head_sha):
            errors.append(f"{label}.head_sha must be a 40-character lowercase SHA")
        evidence_criteria, evidence_ids = validate_evidence(
            pull_request.get("evidence"),
            head_sha,
            contract["semantics"]["evidence_results"],
            errors,
        )
        string_list(pull_request.get("risks"), f"{label}.risks", errors, allow_none=True)
        string_list(pull_request.get("limitations"), f"{label}.limitations", errors, allow_none=True)
        deferred_criteria, deferred_ids = validate_deferred(
            pull_request.get("deferred_evidence"), errors
        )
        id_collision = sorted(evidence_ids & deferred_ids)
        if id_collision:
            errors.append(
                "pull_request evidence and deferred evidence IDs collide: "
                + ", ".join(id_collision)
            )
        criterion_collision = sorted(evidence_criteria & deferred_criteria)
        if criterion_collision:
            errors.append(
                "pull_request criteria cannot be both evidenced and deferred: "
                + ", ".join(criterion_collision)
            )
        expected_criteria = (
            task_criteria_by_url.get(task_url) if isinstance(task_url, str) else None
        )
        if expected_criteria is not None:
            observed_criteria = evidence_criteria | deferred_criteria
            if observed_criteria != expected_criteria:
                missing = sorted(expected_criteria - observed_criteria)
                unknown = sorted(observed_criteria - expected_criteria)
                if missing:
                    errors.append(
                        "pull_request evidence is missing Task criteria: "
                        + ", ".join(missing)
                    )
                if unknown:
                    errors.append(
                        "pull_request evidence references unknown Task criteria: "
                        + ", ".join(unknown)
                    )
    for primary_pr, claimed_task in primary_pr_claims.items():
        linked_task = pull_task_by_url.get(primary_pr)
        if linked_task is None:
            errors.append(
                f"Task primary_pr has no ledger pull-request record: {primary_pr}"
            )
        elif linked_task != claimed_task:
            errors.append(
                f"Task primary_pr and PR task_url disagree for {primary_pr}"
            )
    for pr_url, linked_task in pull_task_by_url.items():
        if primary_pr_claims.get(pr_url) != linked_task:
            errors.append(
                f"PR task_url is not reciprocated by Task primary_pr: {pr_url}"
            )
    reject_authority_and_implementation_claims(payload, "ledger records", errors)
    if epic_number is None:
        return


def validate_rendered_fixtures(
    root: Path,
    contract: dict[str, Any],
    payload: dict[str, Any],
    errors: list[str],
) -> None:
    if errors:
        return
    records = payload["records"]
    selected = {
        "epic": records["epic"],
        "task": records["tasks"][0],
        "pull_request": records["pull_requests"][0],
    }
    for kind, path in RENDERED_PATHS.items():
        try:
            actual = read_regular_text(root, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        expected = render_record(kind, contract["records"][kind], selected[kind])
        if actual != expected:
            errors.append(f"{path} is not synchronized with the contract and record fixture")


def validate_repository(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        contract = load_json(root, CONTRACT_PATH)
    except ValueError as exc:
        return [str(exc)]
    validate_contract(contract, errors)
    validate_templates(root, contract, errors)
    try:
        payload = load_json(root, FIXTURE_PATH)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    if not errors:
        validate_records(contract, payload, errors)
    if not errors:
        validate_rendered_fixtures(root, contract, payload, errors)
    return errors


def main() -> int:
    errors = validate_repository(ROOT)
    if errors:
        for error in errors:
            print(f"ledger contract error: {error}", file=sys.stderr)
        return 1
    print("ledger contracts: synchronized; static validation boundary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
