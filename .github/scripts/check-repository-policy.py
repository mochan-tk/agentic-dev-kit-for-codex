#!/usr/bin/env python3
"""Validate live repository semantics against reviewed Phase/Task ownership."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT_MANIFEST = ".github/governance/phase-task-ownership.v1.json"
CONFORMANCE_MANIFEST = "tests/conformance/manifest.json"
CI_WORKFLOW = ".github/workflows/ci.yml"
ACCEPTED_PHASE0_COMMIT = "32615344ad4f0310948bc59d234a84718741788a"
ACCEPTED_PHASE0_TREE = "33259721ec9f378fa67392ef8e1c7645db1321f9"
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


def read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
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
    pure = PurePosixPath(value)
    if value != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        return False
    return True


def exact_keys(
    payload: dict[str, Any], expected: set[str], label: str, errors: list[str]
) -> None:
    if set(payload) != expected:
        errors.append(f"{label} has unsupported or missing fields")


def validate_manifest(
    payload: dict[str, Any], errors: list[str]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate the manifest and return path->mode plus policy."""

    exact_keys(payload, {"schema", "repository", "phase", "policy", "tasks"}, "ownership manifest", errors)
    if payload.get("schema") != "phase-task-ownership/v1":
        errors.append("ownership manifest schema must be phase-task-ownership/v1")
    if payload.get("repository") != "mochan-tk/agentic-dev-kit-for-codex":
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
    required_jobs = policy.get("required_jobs")
    if (
        not isinstance(required_jobs, list)
        or any(not isinstance(item, str) or not item for item in required_jobs)
        or len(required_jobs) != len(set(required_jobs))
        or not {"quality", "conformance"}.issubset(set(required_jobs))
    ):
        errors.append("ownership policy required_jobs must uniquely include quality and conformance")
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
        if state_value not in ALLOWED_TASK_STATES:
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
            if mode not in ALLOWED_MODES:
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

    duplicates = sorted(identifier for identifier in set(task_ids) if task_ids.count(identifier) > 1)
    if duplicates:
        errors.append(f"duplicate ownership task ID(s): {', '.join(duplicates)}")
    if len(active_branches) != len(set(active_branches)):
        errors.append("active ownership tasks must not share a branch")
    if not any(isinstance(task, dict) and task.get("state") == "active" for task in tasks):
        errors.append("ownership manifest must contain at least one active task")
    if ROOT_MANIFEST not in ownership:
        errors.append("ownership manifest must own its own path")
    return modes, policy


def validate_git_anchor(root: Path, commit: str, tree: str, label: str, errors: list[str]) -> None:
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
    digest = invariant_digest(invariants)
    if digest != policy.get("invariant_digest"):
        errors.append("live invariant meanings do not match the reviewed policy digest")

    manifest = read_json(root / CONFORMANCE_MANIFEST, errors, "conformance manifest")
    if manifest.get("release_blocked") is not True:
        errors.append("conformance manifest release_blocked must remain true")
    manifest_invariants = manifest.get("invariants")
    if not isinstance(manifest_invariants, dict) or manifest_invariants.get("digest") != digest:
        errors.append("conformance manifest invariant digest does not match AGENTS.md")


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
    blocks = workflow_job_blocks(text)
    job_names = re.findall(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", text, re.MULTILINE)
    duplicates = sorted(name for name in set(job_names) if job_names.count(name) > 1)
    if duplicates:
        errors.append(f"ci workflow contains duplicate job ID(s): {', '.join(duplicates)}")
    required_jobs = policy.get("required_jobs")
    if not isinstance(required_jobs, list):
        return
    missing = sorted(set(required_jobs) - set(blocks))
    if missing:
        errors.append(f"ci required job drift: missing {', '.join(missing)}")
    command_fields = {
        "quality": "required_quality_commands",
        "conformance": "required_conformance_commands",
    }
    for job_name, field in command_fields.items():
        block = blocks.get(job_name, "")
        commands = policy.get(field)
        if not isinstance(commands, list):
            continue
        for command in commands:
            if f"        run: {command}" not in block:
                errors.append(f"ci job {job_name!r} is missing required command: {command}")
        checkout_lines = [line for line in block.splitlines() if "actions/checkout@" in line]
        if len(checkout_lines) != 1:
            errors.append(f"ci job {job_name!r} must contain exactly one checkout")
        if "          fetch-depth: 0" not in block or "          persist-credentials: false" not in block:
            errors.append(
                f"ci job {job_name!r} checkout must disable persisted credentials and fetch history"
            )


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
    validate_invariants(root, policy, errors)
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
