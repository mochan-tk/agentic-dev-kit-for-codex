#!/usr/bin/env python3
"""Validate live repository semantics against reviewed Phase/Task ownership."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


ROOT_MANIFEST = ".github/governance/phase-task-ownership.v1.json"
CONFORMANCE_MANIFEST = "tests/conformance/manifest.json"
COVERAGE = "tests/conformance/coverage.json"
CI_WORKFLOW = ".github/workflows/ci.yml"
ACCEPTED_PHASE0_COMMIT = "32615344ad4f0310948bc59d234a84718741788a"
ACCEPTED_PHASE0_TREE = "33259721ec9f378fa67392ef8e1c7645db1321f9"
TARGET_REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
REVIEWED_INVARIANT_DIGEST = (
    "a084a123e16d2fd42619b09161efdaf49bda0ea0ca4a1e076254bd1902aa63f6"
)
HIERARCHY_AGREEMENT_PATH = (
    "docs/agreements/adr/ADR-0005-issue-graph-authority.md"
)
REPOSITORY_COMPLETION_PATH = "docs/agreements/repository-completion.md"
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

jobs:
"""


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
    if phase.get("id") != "phase-1":
        errors.append("ownership phase.id must be phase-1")
    if phase.get("epic") != "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2":
        errors.append("ownership phase.epic must reference Epic issue 2")
    if phase.get("base_commit") != ACCEPTED_PHASE0_COMMIT:
        errors.append("ownership phase base_commit is stale or unsupported")
    if phase.get("base_tree") != ACCEPTED_PHASE0_TREE:
        errors.append("ownership phase base_tree is stale or unsupported")
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
    for field in ("required_quality_commands", "required_conformance_commands"):
        commands = policy.get(field)
        if (
            not isinstance(commands, list)
            or not commands
            or any(not isinstance(item, str) or not item for item in commands)
            or len(commands) != len(set(commands))
        ):
            errors.append(f"ownership policy {field} must be a non-empty unique string list")

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("ownership tasks must be a non-empty list")
        tasks = []
    task_ids: list[str] = []
    active_branches: list[str] = []
    ownership: dict[str, str] = {}
    modes: dict[str, str] = {}
    manifest_paths: list[str] = []
    for index, task in enumerate(tasks):
        label = f"ownership tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{label} must be an object")
            continue
        exact_keys(
            task,
            {"id", "record", "state", "branch", "base_commit", "base_tree", "owned_paths"},
            label,
            errors,
        )
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
        branch = task.get("branch")
        if not isinstance(branch, str) or not BRANCH.fullmatch(branch):
            errors.append(f"{label}.branch must use the codex/ prefix")
        elif state_value == "active":
            active_branches.append(branch)
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

    duplicates = sorted(
        identifier for identifier in set(task_ids) if task_ids.count(identifier) > 1
    )
    if duplicates:
        errors.append(f"duplicate ownership task ID(s): {', '.join(duplicates)}")
    if len(active_branches) != len(set(active_branches)):
        errors.append("active ownership tasks must not share a branch")
    if not any(isinstance(task, dict) and task.get("state") == "active" for task in tasks):
        errors.append("ownership manifest must contain at least one active task")
    if ROOT_MANIFEST not in ownership:
        errors.append("ownership manifest must own its own path")
    validate_path_collisions(manifest_paths, "ownership manifest", errors)
    return modes, policy


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
            ([f"{main_sha}...HEAD"], "committed local Task diff"),
            (["--cached", "HEAD"], "staged local Task diff"),
            ([], "unstaged local Task diff"),
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
    authorize_changed_entries(task, changed_entries, errors)


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

    option_b_markers = (CANONICAL_HIERARCHY, PROJECTS_PROJECTION)
    validate_required_markers(
        agents,
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
        readme,
        option_b_markers
        + (
            f"]({HIERARCHY_AGREEMENT_PATH})",
            f"]({REPOSITORY_COMPLETION_PATH})",
            "Phase 0 is complete",
            "Phase 1 is in progress",
            "not installable",
            "not a parity release",
            "`release_blocked` remains `true`",
        ),
        "Option B hierarchy or current-status markers are missing from README.md",
        errors,
    )
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
        agents,
        completion_markers + ("## Repository completion boundary",),
        "repository completion boundary markers are missing from AGENTS.md",
        errors,
    )
    validate_required_markers(
        readme,
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
        validate_execution_authorization(
            root, payload, os.environ if environment is None else environment, errors
        )
    validate_invariants(root, policy, errors)
    validate_hierarchy_and_completion(root, errors)
    validate_workflows(root, policy, errors)
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
        "Phase 1 base evidence, I01-I13, release blocker, Actions, permissions, "
        "and required CI jobs are consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
