#!/usr/bin/env python3
"""Deterministic controller for the bounded T11 Codex execution slice.

Live execution is an explicit mode. Required CI uses only ``run --offline``
with the repository fake process. Dynamic envelope and Task bytes are read
from stdin and are never placed in a process argv.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple


REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
TASK_ISSUE = 23
ATTEMPT_RE = re.compile(r"ATTEMPT-[0-9a-f]{16}\Z")
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_PATH_RE = re.compile(
    r"(?i)(?:^|[\s'\"]|file:(?://)?)(?:/users/|/home/|/root/|/tmp/|/private/|/var/folders/|~/|[a-z]:[\\/]|\\\\)"
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s]+"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:x-api-key|api[_-]?key)\s*[:=]\s*[^\s]+"),
)
SECRET_NAME_RE = re.compile(
    r"(?i)(?:token|secret|password|passwd|credential|private[_-]?key|authorization|cookie|proxy)"
)
EXPECTED_INITIAL = b"status=pending\n"
EXPECTED_FINAL = b"status=complete\n"
EXPECTED_PATH = "work-item.txt"
EXPECTED_BRANCH = "t11-representative"
EXPECTED_BASE_COMMIT = "7ee649272da3355a06a4b3a11271a3f0cbe8ed56"
EXPECTED_BASE_TREE = "fde54bf076ca83895acbd8bca2bba3f1b5378205"
STATIC_ROLE_PATH = ".codex/agents/task_worker.toml"
STATIC_ROLE_DIGEST = "813baae383e35eea7195ffc0ad8695c7f562eac57c37ef1bb61ede6914661d23"
PROFILE_PATH = ".github/governance/codex-runtime-profile.v1.json"
FINAL_SCHEMA_PATH = "docs/agreements/runtime/codex-final-response.v1.schema.json"
FAKE_PATH = "tests/runtime/fixtures/fake-codex.py"
MAX_STDIN_BYTES = 1_048_576
DEFAULT_LIMITS = {
    "prompt_bytes": 16_384,
    "stdout_bytes": 4_194_304,
    "stderr_bytes": 262_144,
    "line_bytes": 262_144,
    "event_count": 4_096,
    "json_depth": 32,
    "json_nodes": 8_192,
    "json_string_bytes": 65_536,
    "final_response_bytes": 65_536,
    "worker_timeout_seconds": 600,
}
REQUIRED_OVERRIDES = {
    "sandbox_workspace_write.network_access": False,
    "hide_agent_reasoning": True,
    "show_raw_agent_reasoning": False,
    "history.persistence": "none",
    "features.hooks": False,
    "features.apps": False,
    "agents.enabled": False,
    "tools.web_search": False,
    "feedback.enabled": False,
    "features.memory_tool": False,
    "features.memory_tool_use": False,
}
REQUIRED_ENV_VALUES = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
    "PYTHONHASHSEED": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
REVIEWED_SENSOR_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TERMINAL_TYPES = {"turn.completed", "turn.failed"}
KNOWN_RAW_TYPES = {"thread.started", "turn.started", "item.started", "item.updated", "item.completed", "error"} | TERMINAL_TYPES
VERIFIER_CHECKS = [
    "root-binding", "file-binding", "branch", "head", "tree", "status",
    "diff", "ownership", "mode", "exact-bytes", "git-config", "hooks",
    "git-inventory", "refs", "index", "unreachable-objects",
]
MAX_EXECUTION_ROOT_ENTRIES = 16_384
MAX_EXECUTION_ROOT_DEPTH = 32
MAX_EXECUTION_ROOT_FILE_BYTES = 16_777_216
MAX_EXECUTION_ROOT_TOTAL_BYTES = 134_217_728
MAX_XATTR_NAMES_BYTES = 262_144
MAX_XATTR_VALUE_BYTES = 1_048_576
MAX_XATTR_TOTAL_BYTES = 4_194_304


class ContractError(Exception):
    """A bounded, user-safe contract failure."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def runtime_fs_capability_error() -> Optional[str]:
    required_flags = ("O_NOFOLLOW", "O_DIRECTORY")
    missing = [name for name in required_flags if not isinstance(getattr(os, name, None), int)]
    if os.open not in getattr(os, "supports_dir_fd", set()):
        missing.append("open(dir_fd)")
    if os.stat not in getattr(os, "supports_dir_fd", set()):
        missing.append("stat(dir_fd)")
    if os.stat not in getattr(os, "supports_follow_symlinks", set()):
        missing.append("stat(follow_symlinks)")
    return ", ".join(missing) if missing else None


def _runtime_libc() -> Any:
    if sys.platform == "darwin":
        return ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    if sys.platform == "linux":
        return ctypes.CDLL(None, use_errno=True)
    raise ContractError("runtime metadata capability is unavailable")


def runtime_metadata_capability_error() -> Optional[str]:
    if sys.platform not in ("darwin", "linux"):
        return "descriptor xattr inventory is unsupported on this platform"
    try:
        library = _runtime_libc()
    except (OSError, ContractError):
        return "descriptor xattr inventory library is unavailable"
    missing = [name for name in ("flistxattr", "fgetxattr") if not hasattr(library, name)]
    if sys.platform == "darwin":
        try:
            if not hasattr(os.stat("/", follow_symlinks=False), "st_flags"):
                missing.append("fstat(st_flags)")
        except OSError:
            missing.append("fstat(st_flags)")
    return ", ".join(missing) if missing else None


def runtime_process_identity_capability_error() -> Optional[str]:
    if sys.platform == "linux":
        return None if Path("/proc/self/stat").is_file() else "Linux /proc start-tick sensor is unavailable"
    if sys.platform == "darwin":
        try:
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        except OSError:
            return "Darwin libproc birth-identity sensor is unavailable"
        return None if hasattr(library, "proc_pidinfo") else "Darwin proc_pidinfo birth-identity sensor is unavailable"
    return "immutable process birth-identity sensor is unsupported on this platform"


def require_runtime_fs_capabilities() -> None:
    error = runtime_fs_capability_error()
    if error:
        raise ContractError("required no-follow filesystem capability is unavailable: " + error)
    metadata_error = runtime_metadata_capability_error()
    if metadata_error:
        raise ContractError("required runtime metadata capability is unavailable: " + metadata_error)
    process_error = runtime_process_identity_capability_error()
    if process_error:
        raise ContractError("required immutable process-identity capability is unavailable: " + process_error)


def read_bounded_regular(path: Path, max_bytes: int, expected_mode: Optional[int] = None) -> bytes:
    require_runtime_fs_capabilities()
    try:
        named_before = os.stat(str(path), follow_symlinks=False)
    except OSError:
        raise ContractError("bounded regular input is unavailable")
    if not stat.S_ISREG(named_before.st_mode) or named_before.st_size > max_bytes:
        raise ContractError("bounded input is not a regular file or exceeds its limit")
    if expected_mode is not None and stat.S_IMODE(named_before.st_mode) != expected_mode:
        raise ContractError("bounded input mode drifted")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        raise ContractError("bounded input cannot be opened without following links")
    try:
        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode) or (opened_before.st_dev, opened_before.st_ino) != (named_before.st_dev, named_before.st_ino):
            raise ContractError("bounded input binding changed before read")
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise ContractError("bounded input exceeds its byte limit")
        opened_after = os.fstat(descriptor)
        if (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns) != (opened_before.st_dev, opened_before.st_ino, opened_before.st_size, opened_before.st_mtime_ns):
            raise ContractError("bounded input changed while reading")
    finally:
        os.close(descriptor)
    named_after = os.stat(str(path), follow_symlinks=False)
    if (named_after.st_dev, named_after.st_ino, named_after.st_size, named_after.st_mtime_ns) != (named_before.st_dev, named_before.st_ino, named_before.st_size, named_before.st_mtime_ns):
        raise ContractError("bounded input namespace changed after read")
    return bytes(data)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _strict_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ContractError("JSON contains a duplicate object key")
        value[key] = child
    return value


def _reject_json_constant(_value: str) -> None:
    raise ContractError("JSON contains a non-finite number")


def _strict_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ContractError("JSON contains a non-finite number")
    return parsed


def strict_json_loads(text: str, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_json_constant,
            parse_float=_strict_float,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError, OverflowError, ValueError):
        raise ContractError(label + " is not valid bounded JSON")


def read_stdin_bounded(limit: int = MAX_STDIN_BYTES) -> bytes:
    data = sys.stdin.buffer.read(limit + 1)
    if len(data) > limit:
        raise ContractError("stdin exceeds the bounded input limit")
    return data


def decode_json_object(data: bytes, label: str, limits: Optional[Mapping[str, int]] = None) -> Dict[str, Any]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ContractError(label + " is not valid UTF-8")
    try:
        value = strict_json_loads(text, label)
    except ContractError:
        raise
    if not isinstance(value, dict):
        raise ContractError(label + " must be a JSON object")
    bounds = limits or {"json_depth": 32, "json_nodes": 8192, "json_string_bytes": 65536}
    validate_json_limits(value, bounds, label)
    return value


def validate_json_limits(value: Any, limits: Mapping[str, int], label: str = "JSON") -> None:
    max_depth = int(limits["json_depth"])
    max_nodes = int(limits["json_nodes"])
    max_string = int(limits["json_string_bytes"])
    stack: List[Tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise ContractError(label + " exceeds the JSON node limit")
        if depth > max_depth:
            raise ContractError(label + " exceeds the JSON depth limit")
        if isinstance(current, str):
            if len(current.encode("utf-8")) > max_string:
                raise ContractError(label + " exceeds the JSON string limit")
        elif isinstance(current, list):
            for child in reversed(current):
                stack.append((child, depth + 1))
        elif isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise ContractError(label + " contains a non-string object key")
                if len(key.encode("utf-8")) > max_string:
                    raise ContractError(label + " contains an oversized object key")
                stack.append((child, depth + 1))
        elif isinstance(current, float) and not math.isfinite(current):
            raise ContractError(label + " contains a non-finite number")
        elif current is not None and not isinstance(current, (bool, int, float)):
            raise ContractError(label + " contains an unsupported value")


def exact_keys(value: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    wanted = set(expected)
    actual = set(value)
    if actual != wanted:
        raise ContractError("{} fields differ: missing={} extra={}".format(label, sorted(wanted - actual), sorted(actual - wanted)))


def require_string(value: Any, label: str, pattern: Optional[re.Pattern] = None) -> str:
    if not isinstance(value, str):
        raise ContractError(label + " must be a string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractError(label + " has invalid syntax")
    return value


def require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(label + " must be boolean")
    return value


def validate_shell_free_command(command: Any) -> None:
    if not isinstance(command, dict):
        raise ContractError("verification command must be an object")
    exact_keys(
        command,
        ("schema", "argv", "cwd", "environment_profile", "timeout_seconds", "expected_exit_codes", "stdout_max_bytes", "stderr_max_bytes", "shell", "process_group_termination", "git_state"),
        "shell-free command",
    )
    if command["schema"] != "shell-free-command/v1" or command["shell"] is not False:
        raise ContractError("verification command must be shell-free-command/v1 with shell=false")
    argv = command["argv"]
    if not isinstance(argv, list) or not 1 <= len(argv) <= 64 or any(not isinstance(x, str) or not x or len(x.encode("utf-8")) > 4096 for x in argv):
        raise ContractError("verification command argv is invalid")
    if any("status=pending" in x or "status=complete" in x or "Issue #23" in x for x in argv):
        raise ContractError("dynamic Task/context bytes must not appear in argv")
    cwd = command["cwd"]
    if not isinstance(cwd, dict):
        raise ContractError("verification command cwd must be an object")
    exact_keys(cwd, ("kind", "repository", "commit", "tree", "device_inode_verified"), "command cwd")
    if cwd != {
        "kind": "exact-bound-repository-root",
        "repository": REPOSITORY,
        "commit": cwd.get("commit"),
        "tree": cwd.get("tree"),
        "device_inode_verified": True,
    }:
        raise ContractError("verification command cwd binding is invalid")
    require_string(cwd["commit"], "command cwd commit", OID_RE)
    require_string(cwd["tree"], "command cwd tree", OID_RE)
    env_profile = command["environment_profile"]
    if not isinstance(env_profile, dict):
        raise ContractError("environment profile must be an object")
    exact_keys(env_profile, ("id", "required_values", "private_home_and_tmp", "secret_named_variables_excluded"), "environment profile")
    if not re.fullmatch(r"[a-z0-9-]+-v[0-9]+", str(env_profile["id"])):
        raise ContractError("environment profile id is invalid")
    if env_profile["required_values"] != REQUIRED_ENV_VALUES or env_profile["private_home_and_tmp"] is not True or env_profile["secret_named_variables_excluded"] is not True:
        raise ContractError("environment profile is not the reviewed minimal profile")
    for field, maximum in (("timeout_seconds", 1800), ("stdout_max_bytes", 8_388_608), ("stderr_max_bytes", 1_048_576)):
        if type(command[field]) is not int or not 1 <= command[field] <= maximum:
            raise ContractError(field + " is outside its bound")
    codes = command["expected_exit_codes"]
    if not isinstance(codes, list) or not codes or len(codes) > 8 or len(codes) != len(set(codes)) or any(type(x) is not int or not 0 <= x <= 255 for x in codes):
        raise ContractError("expected exit codes are invalid")
    policy = command["process_group_termination"]
    if not isinstance(policy, dict):
        raise ContractError("process-group policy must be an object")
    exact_keys(policy, ("start_new_session", "term_then_kill", "grace_seconds", "wait_and_reap"), "process-group policy")
    if policy["start_new_session"] is not True or policy["term_then_kill"] is not True or policy["wait_and_reap"] is not True or type(policy["grace_seconds"]) is not int or not 1 <= policy["grace_seconds"] <= 30:
        raise ContractError("process-group policy is not fail-closed")
    expected_checks = ["branch", "head", "tree", "status", "worktree-binding"]
    if command["git_state"] != {"verify_before": expected_checks, "verify_after": expected_checks}:
        raise ContractError("pre/post Git-state verification is incomplete")


def validate_envelope(envelope: Any) -> Dict[str, Any]:
    if not isinstance(envelope, dict):
        raise ContractError("envelope must be an object")
    exact_keys(
        envelope,
        ("schema", "task", "attempt_id", "harness", "target", "representative_task", "worker", "verification_commands", "limits", "privacy"),
        "envelope",
    )
    if envelope["schema"] != "task-execution-envelope/v1":
        raise ContractError("unsupported envelope schema")
    require_string(envelope["attempt_id"], "attempt_id", ATTEMPT_RE)
    if envelope["task"] != {
        "repository": REPOSITORY,
        "issue": TASK_ISSUE,
        "url": "https://github.com/{}/issues/{}".format(REPOSITORY, TASK_ISSUE),
    }:
        raise ContractError("envelope Task binding is invalid")
    harness = envelope["harness"]
    if not isinstance(harness, dict):
        raise ContractError("harness binding must be an object")
    exact_keys(harness, ("commit", "tree"), "harness")
    require_string(harness["commit"], "harness commit", OID_RE)
    require_string(harness["tree"], "harness tree", OID_RE)
    target = envelope["target"]
    if not isinstance(target, dict):
        raise ContractError("target binding must be an object")
    exact_keys(target, ("kind", "base_commit", "base_tree", "branch", "owned_paths"), "target")
    if target != {
        "kind": "private-synthetic-git-repository",
        "base_commit": EXPECTED_BASE_COMMIT,
        "base_tree": EXPECTED_BASE_TREE,
        "branch": EXPECTED_BRANCH,
        "owned_paths": [EXPECTED_PATH],
    }:
        raise ContractError("target must be the exact reviewed synthetic repository")
    task = envelope["representative_task"]
    if not isinstance(task, dict):
        raise ContractError("representative task must be an object")
    exact_keys(task, ("path", "mode", "initial_utf8", "initial_hex", "initial_sha256", "expected_utf8", "expected_hex", "expected_sha256"), "representative task")
    expected_task = {
        "path": EXPECTED_PATH,
        "mode": "100644",
        "initial_utf8": EXPECTED_INITIAL.decode("utf-8"),
        "initial_hex": EXPECTED_INITIAL.hex(),
        "initial_sha256": sha256_bytes(EXPECTED_INITIAL),
        "expected_utf8": EXPECTED_FINAL.decode("utf-8"),
        "expected_hex": EXPECTED_FINAL.hex(),
        "expected_sha256": sha256_bytes(EXPECTED_FINAL),
    }
    if task != expected_task:
        raise ContractError("representative Task bytes or ownership drifted")
    worker = envelope["worker"]
    if not isinstance(worker, dict):
        raise ContractError("worker contract must be an object")
    exact_keys(worker, ("model", "reasoning_effort", "sandbox", "approval_policy", "invocation_count", "prompt_transport", "static_role", "overrides"), "worker")
    if worker["model"] != "gpt-5.6-sol" or worker["reasoning_effort"] != "high":
        raise ContractError("worker model/reasoning profile drifted")
    if worker["sandbox"] != "workspace-write" or worker["approval_policy"] != "never" or worker["invocation_count"] != 1 or worker["prompt_transport"] != "stdin-only":
        raise ContractError("worker execution boundary drifted")
    if worker["static_role"] != {"path": STATIC_ROLE_PATH, "developer_instructions_sha256": STATIC_ROLE_DIGEST}:
        raise ContractError("static worker role binding drifted")
    if worker["overrides"] != REQUIRED_OVERRIDES:
        raise ContractError("live runtime overrides drifted")
    commands = envelope["verification_commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 32:
        raise ContractError("verification commands must be a bounded non-empty list")
    for command in commands:
        validate_shell_free_command(command)
        if command["cwd"]["commit"] != harness["commit"] or command["cwd"]["tree"] != harness["tree"]:
            raise ContractError("verification command cwd must equal the envelope harness commit/tree")
    expected_verification_argv = [
        ["python3", "-I", ".github/scripts/check-phase0-contracts.py"],
        ["python3", "-I", ".github/scripts/check-phase1-accepted-snapshot.py"],
        ["python3", "-I", ".github/scripts/check-repository-policy.py"],
        ["python3", "-I", ".github/scripts/check-portable-contracts.py"],
        ["python3", "-I", ".github/scripts/check-ledger-templates.py"],
        ["python3", "-I", ".github/scripts/check-skills.py"],
        ["python3", "-I", ".github/scripts/check-runtime-contracts.py"],
        ["python3", "-I", ".github/scripts/conformance-catalog.py", "check"],
        ["python3", "-I", "-m", "unittest", "discover", "-s", "tests/conformance", "-p", "test_*.py"],
        ["git", "diff", "--check"],
    ]
    if [command["argv"] for command in commands] != expected_verification_argv:
        raise ContractError("required verification command registry drifted")
    limits = envelope["limits"]
    if limits != DEFAULT_LIMITS:
        raise ContractError("execution limits drifted from the reviewed profile")
    privacy = envelope["privacy"]
    if privacy != {
        "durable_allowlist_only": True,
        "raw_jsonl_retained": False,
        "raw_reasoning_retained": False,
        "raw_stderr_retained": False,
        "private_paths_retained": False,
    }:
        raise ContractError("envelope privacy boundary drifted")
    validate_json_limits(envelope, limits, "envelope")
    return envelope


def validate_runtime_profile(profile: Any, allow_fixture: bool = False) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        raise ContractError("runtime profile must be an object")
    exact_keys(profile, ("schema", "repository", "observed_at", "scope", "status", "reason", "platform", "client", "capabilities", "auth", "request", "shell_environment", "live_run_allowed"), "runtime profile")
    if profile["schema"] != "runtime-profile/v1" or profile["repository"] != REPOSITORY:
        raise ContractError("runtime profile identity is invalid")
    if not isinstance(profile["observed_at"], str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", profile["observed_at"]) is None:
        raise ContractError("runtime observation time is invalid")
    if profile["scope"] not in ("task-start-sensor", "exact-head-live-sensor", "fixture"):
        raise ContractError("runtime profile scope is invalid")
    if profile["scope"] == "fixture" and not allow_fixture:
        raise ContractError("fixture runtime profile cannot authorize live execution")
    status_value = profile["status"]
    if status_value not in ("match", "profile-drift", "unsupported-client", "UNKNOWN", "UNCHECKABLE"):
        raise ContractError("runtime profile status is invalid")
    if not isinstance(profile["reason"], str) or not 1 <= len(profile["reason"]) <= 256:
        raise ContractError("runtime profile reason is invalid")
    client = profile["client"]
    if not isinstance(client, dict):
        raise ContractError("runtime client record must be an object")
    exact_keys(client, ("version_output", "release_class", "binary_sha256", "exec_help_sha256", "resolved_path_recorded"), "runtime client")
    require_string(client["binary_sha256"], "runtime binary digest", SHA256_RE)
    require_string(client["exec_help_sha256"], "runtime help digest", SHA256_RE)
    if client["resolved_path_recorded"] is not False:
        raise ContractError("private resolved binary paths must not be recorded")
    if not isinstance(client["version_output"], str) or not 1 <= len(client["version_output"]) <= 128:
        raise ContractError("runtime version output is invalid")
    release_class = client["release_class"]
    if release_class not in ("stable", "prerelease-alpha", "prerelease-beta", "prerelease-rc", "unknown"):
        raise ContractError("runtime release class is invalid")
    derived_release_class = classify_release(client["version_output"])
    if release_class != derived_release_class:
        raise ContractError("runtime release class disagrees with exact version output")
    caps = profile["capabilities"]
    required_caps = ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "config_recognition_probe", "shell_environment_probe", "process_containment_probe", "model", "reasoning", "sandbox", "approval", "overrides")
    exact_keys(caps, required_caps, "runtime capabilities")
    for field in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"):
        require_bool(caps[field], "runtime capability " + field)
    if caps["config_recognition_probe"] not in ("pass", "fail", "not-proven", "UNCHECKABLE") or caps["shell_environment_probe"] not in ("pass", "fail", "not-run", "UNCHECKABLE") or caps["process_containment_probe"] not in ("pass", "fail", "not-run", "UNCHECKABLE"):
        raise ContractError("runtime probe status is invalid")
    platform = profile["platform"]
    if not isinstance(platform, dict):
        raise ContractError("runtime platform must be an object")
    exact_keys(platform, ("os", "architecture"), "runtime platform")
    if any(not isinstance(platform[field], str) or not platform[field] for field in ("os", "architecture")):
        raise ContractError("runtime platform values are invalid")
    auth = profile["auth"]
    if not isinstance(auth, dict):
        raise ContractError("runtime auth record must be an object")
    exact_keys(auth, ("class", "credential_values_recorded"), "runtime auth")
    if auth["class"] not in ("signed-in-client", "api-key", "unavailable", "unknown") or auth["credential_values_recorded"] is not False:
        raise ContractError("runtime profile must not record credential values")
    request = profile["request"]
    if request != {"model": "gpt-5.6-sol", "reasoning_effort": "high", "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"}:
        raise ContractError("runtime model/reasoning/sandbox/approval request drifted")
    shell_env = profile["shell_environment"]
    exact_names = ["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS"]
    fixed_values = {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}
    expected_shell = {
        "inherit": "none", "required_names": exact_names,
        "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated",
        "fixed_values": fixed_values, "private_home": True, "private_tmpdir": True,
        "secret_named_variables_excluded": True, "probe_required": True,
    }
    if shell_env != expected_shell:
        raise ContractError("runtime shell environment profile drifted")
    match_ready = (
        status_value == "match"
        and release_class == "stable"
        and caps["config_recognition_probe"] == "pass"
        and caps["shell_environment_probe"] == "pass"
        and caps["process_containment_probe"] == "pass"
        and all(caps[field] for field in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"))
    )
    if profile["live_run_allowed"] is not match_ready:
        raise ContractError("live_run_allowed disagrees with fail-closed profile evidence")
    if release_class.startswith("prerelease") and status_value != "unsupported-client":
        raise ContractError("unapproved prerelease must be unsupported-client")
    if status_value == "match" and auth["class"] not in ("signed-in-client", "api-key"):
        raise ContractError("match profile requires an available auth class")
    return profile


def validate_verifier_record(value: Any, attempt_id: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("verifier artifact must be an object")
    exact_keys(value, ("schema", "attempt_id", "status", "fresh_process", "read_only", "checks"), "verifier artifact")
    expected = {
        "schema": "t11-verifier-result/v1", "attempt_id": attempt_id,
        "status": "pass", "fresh_process": True, "read_only": True,
        "checks": VERIFIER_CHECKS,
    }
    if value != expected:
        raise ContractError("verifier artifact is not the exact fresh read-only success record")
    return value


def validate_execution_result(
    value: Any,
    envelope: Mapping[str, Any],
    profile: Mapping[str, Any],
    verifier: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("execution result artifact must be an object")
    exact_keys(value, ("schema", "attempt_id", "status", "authority", "worker", "events", "final_response", "git", "verifier", "digests", "privacy"), "execution result artifact")
    attempt = envelope["attempt_id"]
    validate_verifier_record(verifier, attempt)
    if value.get("schema") != "execution-result/v1" or value.get("attempt_id") != attempt or value.get("status") != "pass" or value.get("authority") != "adapter-authored":
        raise ContractError("execution result identity/status/authority is invalid")
    worker = value.get("worker")
    if not isinstance(worker, dict):
        raise ContractError("execution result worker evidence is invalid")
    exact_keys(worker, ("logical_invocations", "exit_code", "timed_out", "signal", "stdout_bytes", "stderr_bytes"), "execution result worker")
    if worker["logical_invocations"] != 1 or worker["exit_code"] != 0 or worker["timed_out"] is not False or worker["signal"] is not None or type(worker["stdout_bytes"]) is not int or not 0 <= worker["stdout_bytes"] <= DEFAULT_LIMITS["stdout_bytes"] or type(worker["stderr_bytes"]) is not int or not 0 <= worker["stderr_bytes"] <= DEFAULT_LIMITS["stderr_bytes"]:
        raise ContractError("execution result worker is not one bounded successful invocation")
    events = value.get("events")
    if not isinstance(events, dict) or set(events) != {"count", "terminal_count", "terminal_state", "canonical_sha256"} or type(events["count"]) is not int or not 1 <= events["count"] <= DEFAULT_LIMITS["event_count"] or events["terminal_count"] != 1 or events["terminal_state"] != "completed" or SHA256_RE.fullmatch(str(events["canonical_sha256"])) is None:
        raise ContractError("execution result terminal event evidence is invalid")
    final = value.get("final_response")
    if not isinstance(final, dict) or set(final) != {"present", "valid", "sha256", "outcome"} or final["present"] is not True or final["valid"] is not True or final["outcome"] != "completed" or SHA256_RE.fullmatch(str(final["sha256"])) is None:
        raise ContractError("execution result final response evidence is invalid")
    target = envelope["target"]
    expected_git = {
        "pre_head": target["base_commit"], "post_head": target["base_commit"],
        "pre_tree": target["base_tree"], "post_tree": target["base_tree"],
        "worktree_tree": expected_worktree_tree_oid(),
        "changed_paths": [EXPECTED_PATH], "owned_paths_only": True,
        "expected_bytes": True, "other_changes": False,
    }
    if value.get("git") != expected_git:
        raise ContractError("execution result exact target evidence drifted")
    expected_verifier = {
        "fresh_process": True, "read_only": True, "status": "pass",
        "record_sha256": sha256_bytes(canonical_bytes(verifier)),
    }
    if value.get("verifier") != expected_verifier:
        raise ContractError("execution result verifier digest binding drifted")
    if value.get("digests") != {
        "envelope_sha256": sha256_bytes(canonical_bytes(envelope)),
        "runtime_profile_sha256": sha256_bytes(canonical_bytes(profile)),
    }:
        raise ContractError("execution result envelope/profile digest binding drifted")
    if value.get("privacy") != {
        "raw_jsonl_retained": False, "raw_reasoning_retained": False,
        "raw_stderr_retained": False, "private_paths_retained": False,
    }:
        raise ContractError("execution result privacy boundary drifted")
    return value


def extract_static_role(repository_root: Path) -> str:
    role_path = repository_root / STATIC_ROLE_PATH
    data = read_bounded_regular(role_path, 65_536, 0o644)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ContractError("static worker role is not valid UTF-8")
    marker = 'developer_instructions = """\n'
    start = text.find(marker)
    if start < 0 or not text.endswith('"""\n'):
        raise ContractError("static worker role instructions are malformed")
    instructions = text[start + len(marker):-4]
    if sha256_bytes(instructions.encode("utf-8")) != STATIC_ROLE_DIGEST:
        raise ContractError("static worker role digest drifted")
    return instructions


class ProcessResult(NamedTuple):
    exit_code: Optional[int]
    signal_number: Optional[int]
    timed_out: bool
    stdout_overflow: bool
    stderr_overflow: bool
    stdout: bytes
    stderr_size: int
    reaped: bool


def _linux_process_table_snapshot() -> Dict[int, Tuple[int, int, str]]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        proc_descriptor = os.open("/proc", flags)
    except OSError:
        raise ContractError("Linux process birth-identity sensor is unavailable")
    table: Dict[int, Tuple[int, int, str]] = {}
    try:
        with os.scandir(proc_descriptor) as entries:
            names = [entry.name for entry in entries if entry.name.isascii() and entry.name.isdigit()]
        if len(names) > 131_072:
            raise ContractError("descendant process sensor exceeds its bound")
        for name in names:
            try:
                process_descriptor = os.open(name, flags, dir_fd=proc_descriptor)
                try:
                    stat_descriptor = os.open("stat", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=process_descriptor)
                    try:
                        data = bytearray()
                        while len(data) <= 8192:
                            chunk = os.read(stat_descriptor, min(4096, 8193 - len(data)))
                            if not chunk:
                                break
                            data.extend(chunk)
                    finally:
                        os.close(stat_descriptor)
                finally:
                    os.close(process_descriptor)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            except OSError:
                continue
            if not data or len(data) > 8192:
                continue
            try:
                text = bytes(data).decode("ascii", errors="strict")
                closing = text.rfind(")")
                if closing < 2 or text[0:closing].find("(") < 1:
                    raise ValueError
                pid = int(text[:text.find(" ")])
                fields = text[closing + 2:].split()
                if len(fields) < 20:
                    raise ValueError
                state = fields[0]
                ppid = int(fields[1])
                pgid = int(fields[2])
                start_ticks = int(fields[19])
            except (UnicodeDecodeError, ValueError):
                raise ContractError("Linux process birth-identity sensor returned malformed data")
            if pid <= 0 or ppid < 0 or pgid <= 0 or start_ticks <= 0:
                raise ContractError("Linux process birth-identity sensor returned invalid data")
            if state != "Z":
                table[pid] = (ppid, pgid, "linux:" + str(start_ticks))
    finally:
        os.close(proc_descriptor)
    return table


class _DarwinProcBSDInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32), ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32), ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32), ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32), ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32), ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32), ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32), ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


def _darwin_process_info(pid: int) -> Optional[Tuple[int, int, str]]:
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pidinfo
    except (OSError, AttributeError):
        raise ContractError("Darwin process birth-identity sensor is unavailable")
    function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    function.restype = ctypes.c_int
    info = _DarwinProcBSDInfo()
    received = function(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if received == 0:
        return None
    if received != ctypes.sizeof(info) or info.pbi_pid != pid:
        raise ContractError("Darwin process birth-identity sensor returned malformed data")
    if info.pbi_ppid < 0 or info.pbi_pgid <= 0 or info.pbi_start_tvsec <= 0 or info.pbi_start_tvusec >= 1_000_000:
        raise ContractError("Darwin process birth-identity sensor returned invalid data")
    if info.pbi_status == 5:  # SZOMB: no executable process remains to signal.
        return None
    return (
        int(info.pbi_ppid), int(info.pbi_pgid),
        "darwin:{}:{}".format(info.pbi_start_tvsec, info.pbi_start_tvusec),
    )


def _darwin_process_table_snapshot(env: Mapping[str, str]) -> Dict[int, Tuple[int, int, str]]:
    ps_path = Path("/bin/ps") if Path("/bin/ps").exists() else Path("/usr/bin/ps")
    info = os.stat(str(ps_path), follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not (stat.S_IMODE(info.st_mode) & 0o111):
        raise ContractError("Darwin PID enumeration sensor is unavailable")
    try:
        completed = subprocess.run(
            [str(ps_path), "-axo", "pid="], cwd="/", env=dict(env),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, timeout=2, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise ContractError("Darwin PID enumeration sensor is uncheckable")
    if completed.returncode != 0 or len(completed.stdout) > 2_097_152:
        raise ContractError("Darwin PID enumeration sensor is uncheckable")
    table: Dict[int, Tuple[int, int, str]] = {}
    for raw_line in completed.stdout.splitlines():
        try:
            pid = int(raw_line.decode("ascii", errors="strict").strip())
        except (UnicodeDecodeError, ValueError):
            raise ContractError("Darwin PID enumeration sensor returned malformed data")
        if pid <= 0:
            raise ContractError("Darwin PID enumeration sensor returned invalid data")
        identity = _darwin_process_info(pid)
        if identity is not None:
            table[pid] = identity
        if len(table) > 131_072:
            raise ContractError("descendant process sensor exceeds its bound")
    return table


def process_table_snapshot(env: Mapping[str, str]) -> Dict[int, Tuple[int, int, str]]:
    """Return PID -> (PPID, PGID, immutable birth token) on Darwin/Linux."""
    if sys.platform == "linux":
        return _linux_process_table_snapshot()
    if sys.platform == "darwin":
        return _darwin_process_table_snapshot(env)
    raise ContractError("descendant process birth-identity tracking is unavailable")


class DescendantTracker:
    """Best-effort process-tree tracker used to close observed escape repros.

    It stores an OS birth token with each PID so cleanup never signals a
    numeric PID after that identity has changed. PPID/PGID are discovery
    topology only: a captured child remains the same child after reparenting or
    setsid. This is useful for bounded offline execution, but is not
    kernel-enforced containment; live profiles remain fail-closed unless a
    separately proven containment primitive is introduced.
    """

    def __init__(self, leader_pid: int, env: Mapping[str, str]):
        self.leader_pid = leader_pid
        self.env = dict(env)
        self.known: Dict[int, Tuple[int, int, str]] = {}
        self.failure: Optional[str] = None
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="t11-descendant-tracker", daemon=True)

    def _observe(self) -> None:
        table = process_table_snapshot(self.env)
        leader = table.get(self.leader_pid)
        if leader is not None and self.leader_pid not in self.known:
            self.known[self.leader_pid] = leader
        leader_known = self.known.get(self.leader_pid)
        leader_alive = leader is not None and leader_known is not None and leader[2] == leader_known[2]
        # start_new_session makes the leader PID the initial PGID. Capture any
        # same-group descendant only while that exact leader birth identity is
        # alive; otherwise a reused numeric PGID could capture an unrelated
        # process.
        if leader_alive:
            for pid, identity in table.items():
                if identity[1] == self.leader_pid and pid not in self.known:
                    self.known[pid] = identity
        changed = True
        while changed:
            changed = False
            known_pids = set(self.known)
            for pid, identity in table.items():
                if pid not in self.known and identity[0] in known_pids:
                    self.known[pid] = identity
                    changed = True

    def _run(self) -> None:
        try:
            while not self.stop_event.is_set():
                self._observe()
                self.ready.set()
                self.stop_event.wait(0.005)
            self._observe()
        except ContractError:
            self.failure = "descendant process tracking became uncheckable"
            self.ready.set()

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(2) or self.failure:
            self.stop_event.set()
            self.thread.join(timeout=2)
            raise ContractError("descendant process tracking is uncheckable")

    def _alive_identities(self) -> Dict[int, Tuple[int, int, str]]:
        table = process_table_snapshot(self.env)
        return {
            pid: identity for pid, identity in self.known.items()
            if pid in table and table[pid][2] == identity[2]
        }

    def _signal_if_same_birth(self, pid: int, identity: Tuple[int, int, str], signum: int) -> bool:
        # Refresh immediately before every signal. Topology may legitimately
        # change; the immutable OS birth token may not.
        current = process_table_snapshot(self.env).get(pid)
        if current is None or current[2] != identity[2]:
            return False
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            return False
        return True

    def _terminate(self, grace_seconds: float, include_leader: bool) -> bool:
        try:
            self._observe()
            for signum in (signal.SIGTERM, signal.SIGKILL):
                deadline = time.monotonic() + max(grace_seconds, 0.1)
                while True:
                    alive = {
                        pid: identity for pid, identity in self._alive_identities().items()
                        if include_leader or pid != self.leader_pid
                    }
                    if not alive:
                        break
                    for pid in sorted(alive, reverse=True):
                        self._signal_if_same_birth(pid, alive[pid], signum)
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.01)
            clean = not {
                pid for pid in self._alive_identities()
                if include_leader or pid != self.leader_pid
            }
        except ContractError:
            clean = False
        self.stop_event.set()
        self.thread.join(timeout=max(grace_seconds, 1.0))
        return clean and not self.thread.is_alive() and self.failure is None

    def terminate_descendants(self, grace_seconds: float) -> bool:
        return self._terminate(grace_seconds, include_leader=False)

    def terminate_all(self, grace_seconds: float) -> bool:
        return self._terminate(grace_seconds, include_leader=True)


def live_containment_proven() -> bool:
    """No kernel-enforced escaped-descendant boundary is yet implemented."""
    return False


def run_bounded_process(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin_bytes: bytes,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    grace_seconds: float = 2.0,
) -> ProcessResult:
    require_runtime_fs_capabilities()
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise ContractError("process argv is invalid")
    if len(stdin_bytes) > MAX_STDIN_BYTES:
        raise ContractError("process stdin exceeds its limit")
    if any(SECRET_NAME_RE.search(name) for name in env):
        raise ContractError("minimal environment contains a forbidden secret-like name")
    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )
    tracker = DescendantTracker(process.pid, env)
    try:
        tracker.start()
    except Exception:
        # Without a captured immutable birth identity, signaling this numeric
        # PID/PGID would be unsafe. A process that has not already exited makes
        # the operation uncheckable rather than broadening the actuator.
        try:
            process.wait(timeout=max(grace_seconds, 1.0))
        except subprocess.TimeoutExpired:
            raise ContractError("process identity became uncheckable before safe cleanup")
        raise ContractError("process identity became uncheckable before execution")
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    sizes = {"stdout": 0, "stderr": 0}
    overflows = {"stdout": False, "stderr": False}
    stop_event = threading.Event()

    def drain(stream, name: str, limit: int) -> None:
        while True:
            chunk = stream.read(65_536)
            if not chunk:
                return
            sizes[name] += len(chunk)
            remaining = max(0, limit + 1 - len(buffers[name]))
            if remaining:
                buffers[name].extend(chunk[:remaining])
            if sizes[name] > limit:
                overflows[name] = True
                stop_event.set()

    stdout_thread = threading.Thread(target=drain, args=(process.stdout, "stdout", stdout_limit), daemon=True)
    stderr_thread = threading.Thread(target=drain, args=(process.stderr, "stderr", stderr_limit), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        process.stdin.write(stdin_bytes)
        process.stdin.close()
    except BrokenPipeError:
        pass

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    forced_cleanup = False
    tracked_cleanup = True
    while process.poll() is None:
        if stop_event.wait(0.02):
            forced_cleanup = True
            tracked_cleanup = tracker.terminate_all(grace_seconds)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            forced_cleanup = True
            tracked_cleanup = tracker.terminate_all(grace_seconds)
            break
    if process.poll() is None:
        if not forced_cleanup:
            forced_cleanup = True
            tracked_cleanup = tracker.terminate_all(grace_seconds)
        try:
            process.wait(timeout=max(grace_seconds, 1.0))
        except subprocess.TimeoutExpired:
            raise ContractError("identity-bound process cleanup could not reap the leader")
    return_code = process.wait(timeout=max(grace_seconds, 1.0))
    descendants_gone = tracked_cleanup if forced_cleanup else tracker.terminate_descendants(grace_seconds)
    stdout_thread.join(timeout=max(grace_seconds, 1.0))
    stderr_thread.join(timeout=max(grace_seconds, 1.0))
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        # Never signal a numeric PGID after its leader has been reaped: the
        # number may have been reused. Identity-bound descendant cleanup above
        # is the only post-leader actuator; retained pipes therefore fail the
        # result closed instead of broadening the signal target.
        stdout_thread.join(timeout=max(grace_seconds, 0.1))
        stderr_thread.join(timeout=max(grace_seconds, 0.1))
    reaped = process.poll() is not None and descendants_gone and not stdout_thread.is_alive() and not stderr_thread.is_alive()
    process.stdout.close()
    process.stderr.close()
    signum = -return_code if return_code < 0 else None
    exit_code = return_code if return_code >= 0 else None
    return ProcessResult(
        exit_code=exit_code,
        signal_number=signum,
        timed_out=timed_out,
        stdout_overflow=overflows["stdout"],
        stderr_overflow=overflows["stderr"],
        stdout=bytes(buffers["stdout"][:stdout_limit]),
        stderr_size=sizes["stderr"],
        reaped=reaped,
    )


def minimal_environment(executable: Path, private_home: Path, private_tmp: Path, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    path_parts: List[str] = []
    for candidate in (str(executable.parent), str(Path(sys.executable).resolve().parent), "/usr/bin", "/bin"):
        if candidate not in path_parts:
            path_parts.append(candidate)
    environment = {
        "PATH": os.pathsep.join(path_parts),
        "HOME": str(private_home),
        "TMPDIR": str(private_tmp),
        **REQUIRED_ENV_VALUES,
        "GIT_OPTIONAL_LOCKS": "0",
    }
    if extra:
        for name, value in extra.items():
            if not isinstance(name, str) or not isinstance(value, str) or SECRET_NAME_RE.search(name) or "\x00" in name or "\x00" in value:
                raise ContractError("offline environment extension is unsafe")
            environment[name] = value
    return environment


def resolve_executable_from_path(name: str, env: Mapping[str, str]) -> Optional[Path]:
    """Resolve an executable only through the caller's reviewed PATH value."""
    require_runtime_fs_capabilities()
    path_value = env.get("PATH")
    if not isinstance(path_value, str) or not path_value:
        raise ContractError("explicit executable PATH is unavailable")
    for directory in path_value.split(os.pathsep):
        if not directory or not os.path.isabs(directory):
            raise ContractError("explicit executable PATH contains an unsafe entry")
        candidate = Path(directory) / name
        try:
            named = os.stat(str(candidate), follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError:
            raise ContractError("reviewed executable candidate is uncheckable")
        if not stat.S_ISREG(named.st_mode) or named.st_nlink < 1 or not (stat.S_IMODE(named.st_mode) & 0o111):
            raise ContractError("reviewed executable candidate is not a direct executable regular file")
        # Hashing performs descriptor/name rebinding checks.  The digest is
        # recorded by the profile sensor and rechecked immediately pre-live.
        hash_regular_file(candidate)
        return candidate
    return None


def git_argv(root: Path, env: Mapping[str, str], *arguments: str) -> List[str]:
    git = resolve_executable_from_path("git", env)
    if git is None:
        raise ContractError("Git executable is unavailable from the explicit PATH")
    return [str(git), "--no-replace-objects", "-c", "core.hooksPath=/dev/null", "-C", str(root)] + list(arguments)


def run_git(root: Path, arguments: Sequence[str], env: Mapping[str, str], expected: Sequence[int] = (0,), max_bytes: int = 262_144) -> bytes:
    result = run_bounded_process(
        git_argv(root, env, *arguments), root, env, b"", 30, max_bytes, max_bytes, 2,
    )
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped or result.exit_code not in expected:
        raise ContractError("bounded Git operation failed")
    return result.stdout


def git_executable_evidence(root: Path, env: Mapping[str, str]) -> Tuple[str, str]:
    git = resolve_executable_from_path("git", env)
    if git is None:
        raise ContractError("Git executable is unavailable from the explicit PATH")
    digest = hash_regular_file(git)
    result = run_bounded_process([str(git), "--version"], root, env, b"", 15, 4096, 4096, 2)
    if result.exit_code != 0 or result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped or result.stderr_size:
        raise ContractError("Git version sensor is uncheckable")
    try:
        version = result.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        raise ContractError("Git version sensor is malformed")
    if re.fullmatch(r"git version [0-9]+\.[0-9]+\.[0-9]+(?:\.[A-Za-z0-9.-]+)?(?: \([A-Za-z0-9 ._-]+\))?", version) is None:
        raise ContractError("Git version sensor is malformed")
    return version, digest


def create_synthetic_repository(container: Path, env: Mapping[str, str]) -> Path:
    root = container / "target"
    root.mkdir(mode=0o700)
    git = resolve_executable_from_path("git", env)
    if git is None:
        raise ContractError("Git executable is unavailable from the explicit PATH")
    init = run_bounded_process(
        [str(git), "--no-replace-objects", "-c", "init.defaultBranch=" + EXPECTED_BRANCH, "init", "-q", "-b", EXPECTED_BRANCH, str(root)],
        container, env, b"", 30, 262_144, 262_144,
    )
    if init.exit_code != 0 or init.timed_out or init.stdout_overflow or init.stderr_overflow:
        raise ContractError("synthetic Git initialization failed")
    target = root / EXPECTED_PATH
    target.write_bytes(EXPECTED_INITIAL)
    os.chmod(target, 0o644)
    run_git(root, ["add", "--", EXPECTED_PATH], env)
    commit_env = dict(env)
    commit_env.update({
        "GIT_AUTHOR_NAME": "T11 Fixture", "GIT_AUTHOR_EMAIL": "t11@example.invalid",
        "GIT_COMMITTER_NAME": "T11 Fixture", "GIT_COMMITTER_EMAIL": "t11@example.invalid",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    })
    run_git(root, ["commit", "-q", "-m", "T11 synthetic base"], commit_env)
    commit = run_git(root, ["rev-parse", "HEAD"], env).decode("ascii").strip()
    tree = run_git(root, ["rev-parse", "HEAD^{tree}"], env).decode("ascii").strip()
    if commit != EXPECTED_BASE_COMMIT or tree != EXPECTED_BASE_TREE:
        raise ContractError("synthetic base commit/tree do not match the reviewed binding")
    return root


def bound_directory(root: Path) -> Tuple[int, Tuple[int, int]]:
    require_runtime_fs_capabilities()
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(root), flags)
    except OSError:
        raise ContractError("worktree root cannot be opened without following links")
    current = os.fstat(descriptor)
    named = os.stat(str(root), follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (named.st_dev, named.st_ino):
        os.close(descriptor)
        raise ContractError("worktree root binding changed")
    return descriptor, (current.st_dev, current.st_ino)


def descriptor_stat_flags(info: os.stat_result) -> int:
    if sys.platform == "darwin":
        flags = getattr(info, "st_flags", None)
        if not isinstance(flags, int):
            raise ContractError("runtime stat-flags metadata is uncheckable")
        return flags
    # Linux ``stat(2)`` has no st_flags field. ACLs and other security
    # metadata exposed through xattrs are captured below; filesystem ioctl
    # flags are not claimed by this portable slice.
    return 0


def _xattr_name_blob(descriptor: int) -> bytes:
    library = _runtime_libc()
    function = library.flistxattr
    if sys.platform == "darwin":
        function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        function.restype = ctypes.c_ssize_t
        size = function(descriptor, None, 0, 0)
    else:
        function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
        function.restype = ctypes.c_ssize_t
        size = function(descriptor, None, 0)
    if size < 0 or size > MAX_XATTR_NAMES_BYTES:
        raise ContractError("execution-root xattr-name inventory is unavailable or oversized")
    if size == 0:
        return b""
    buffer = ctypes.create_string_buffer(size)
    if sys.platform == "darwin":
        received = function(descriptor, buffer, size, 0)
    else:
        received = function(descriptor, buffer, size)
    if received < 0 or received > size:
        raise ContractError("execution-root xattr-name inventory changed while reading")
    return bytes(buffer.raw[:received])


def _xattr_value(descriptor: int, name: bytes) -> bytes:
    if not name or b"\0" in name or len(name) > 1024:
        raise ContractError("execution-root xattr name is invalid")
    library = _runtime_libc()
    function = library.fgetxattr
    if sys.platform == "darwin":
        function.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_uint32, ctypes.c_int,
        ]
        function.restype = ctypes.c_ssize_t
        size = function(descriptor, name, None, 0, 0, 0)
    else:
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
        function.restype = ctypes.c_ssize_t
        size = function(descriptor, name, None, 0)
    if size < 0 or size > MAX_XATTR_VALUE_BYTES:
        raise ContractError("execution-root xattr value is unavailable or oversized")
    if size == 0:
        return b""
    buffer = ctypes.create_string_buffer(size)
    if sys.platform == "darwin":
        received = function(descriptor, name, buffer, size, 0, 0)
    else:
        received = function(descriptor, name, buffer, size)
    if received < 0 or received > size:
        raise ContractError("execution-root xattr value changed while reading")
    return bytes(buffer.raw[:received])


def descriptor_xattr_inventory(descriptor: int) -> Tuple[Tuple[str, int, str], ...]:
    def read_once() -> Tuple[Tuple[str, int, str], ...]:
        blob = _xattr_name_blob(descriptor)
        names = [name for name in blob.split(b"\0") if name]
        if len(names) > 4096 or names != sorted(names) or len(names) != len(set(names)):
            # Normalize ordering once, but reject duplicate kernel names.
            if len(names) > 4096 or len(names) != len(set(names)):
                raise ContractError("execution-root xattr inventory is invalid")
            names.sort()
        total = len(blob)
        rows: List[Tuple[str, int, str]] = []
        for name in names:
            value = _xattr_value(descriptor, name)
            total += len(value)
            if total > MAX_XATTR_TOTAL_BYTES:
                raise ContractError("execution-root xattr inventory exceeds its total bound")
            rows.append((name.hex(), len(value), sha256_bytes(value)))
        return tuple(rows)

    first = read_once()
    second = read_once()
    if first != second:
        raise ContractError("execution-root xattr inventory changed while reading")
    return first


def execution_root_inventory(root: Path) -> Dict[str, List[Tuple[Any, ...]]]:
    """Inventory the private execution root without following any link.

    This bounds the adapter-owned target, HOME, and TMPDIR namespace. It is a
    pre/post persistence sensor, not a host-global filesystem monitor or a
    kernel write-confinement primitive.
    """
    require_runtime_fs_capabilities()
    descriptor, root_binding = bound_directory(root)
    content_rows: List[Tuple[Any, ...]] = []
    binding_rows: List[Tuple[Any, ...]] = []
    counters = {"entries": 0, "bytes": 0}

    def walk(directory_descriptor: int, relative: str, depth: int) -> None:
        if depth > MAX_EXECUTION_ROOT_DEPTH:
            raise ContractError("execution root exceeds its depth bound")
        directory_before = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_before.st_mode):
            raise ContractError("execution root contains a non-directory binding")
        xattrs = descriptor_xattr_inventory(directory_descriptor)
        names: List[str] = []
        with os.scandir(directory_descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                counters["entries"] += 1
                if counters["entries"] > MAX_EXECUTION_ROOT_ENTRIES:
                    raise ContractError("execution root exceeds its entry bound")
        if len(names) != len(set(names)) or any(
            not name or name in (".", "..") or "/" in name or "\0" in name
            for name in names
        ):
            raise ContractError("execution root contains unsafe or colliding names")
        names.sort()
        for name in names:
            child_relative = name if relative == "." else relative + "/" + name
            info = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            kind = stat.S_IFMT(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                child_descriptor = os.open(name, flags, dir_fd=directory_descriptor)
                try:
                    opened = os.fstat(child_descriptor)
                    if (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode)) != (info.st_dev, info.st_ino, kind):
                        raise ContractError("execution-root directory binding changed before enumeration")
                    walk(child_descriptor, child_relative, depth + 1)
                    after = os.fstat(child_descriptor)
                    named_after = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
                    if (
                        after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns,
                        named_after.st_dev, named_after.st_ino,
                    ) != (
                        opened.st_dev, opened.st_ino, opened.st_mtime_ns, opened.st_ctime_ns,
                        opened.st_dev, opened.st_ino,
                    ):
                        raise ContractError("execution-root directory namespace changed during enumeration")
                finally:
                    os.close(child_descriptor)
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1 or info.st_size > MAX_EXECUTION_ROOT_FILE_BYTES:
                    raise ContractError("execution root contains an unsafe or oversized regular file")
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if hasattr(os, "O_NONBLOCK"):
                    flags |= os.O_NONBLOCK
                child_descriptor = os.open(name, flags, dir_fd=directory_descriptor)
                try:
                    opened = os.fstat(child_descriptor)
                    if (
                        opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size
                    ) != (info.st_dev, info.st_ino, kind, info.st_size):
                        raise ContractError("execution-root file binding changed before read")
                    digest = hashlib.sha256()
                    read_size = 0
                    while True:
                        chunk = os.read(child_descriptor, 65_536)
                        if not chunk:
                            break
                        read_size += len(chunk)
                        counters["bytes"] += len(chunk)
                        if read_size > MAX_EXECUTION_ROOT_FILE_BYTES or counters["bytes"] > MAX_EXECUTION_ROOT_TOTAL_BYTES:
                            raise ContractError("execution root exceeds its content bound")
                        digest.update(chunk)
                    child_xattrs = descriptor_xattr_inventory(child_descriptor)
                    after = os.fstat(child_descriptor)
                    named_after = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
                    before_state = (
                        opened.st_dev, opened.st_ino, opened.st_size,
                        opened.st_mtime_ns, opened.st_ctime_ns,
                    )
                    if (
                        after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns,
                    ) != before_state or (
                        named_after.st_dev, named_after.st_ino, named_after.st_size,
                        named_after.st_mtime_ns, named_after.st_ctime_ns,
                    ) != before_state:
                        raise ContractError("execution-root file namespace changed during read")
                    content_rows.append((
                        "file", child_relative, stat.S_IMODE(opened.st_mode),
                        descriptor_stat_flags(opened), opened.st_size,
                        opened.st_mtime_ns, opened.st_ctime_ns,
                        digest.hexdigest(), child_xattrs,
                    ))
                    binding_rows.append((
                        "file", child_relative, opened.st_dev, opened.st_ino,
                        stat.S_IFMT(opened.st_mode), stat.S_IMODE(opened.st_mode),
                        opened.st_nlink,
                    ))
                finally:
                    os.close(child_descriptor)
            else:
                raise ContractError("execution root contains a symlink or special file")
        directory_after = os.fstat(directory_descriptor)
        if (
            directory_after.st_dev, directory_after.st_ino,
            directory_after.st_mtime_ns, directory_after.st_ctime_ns,
        ) != (
            directory_before.st_dev, directory_before.st_ino,
            directory_before.st_mtime_ns, directory_before.st_ctime_ns,
        ):
            raise ContractError("execution-root directory changed during enumeration")
        content_rows.append((
            "dir", relative, stat.S_IMODE(directory_after.st_mode),
            descriptor_stat_flags(directory_after), directory_after.st_mtime_ns,
            directory_after.st_ctime_ns, xattrs,
        ))
        binding_rows.append((
            "dir", relative, directory_after.st_dev, directory_after.st_ino,
            stat.S_IFMT(directory_after.st_mode), stat.S_IMODE(directory_after.st_mode),
            directory_after.st_nlink,
        ))

    try:
        walk(descriptor, ".", 1)
        named_after = os.stat(str(root), follow_symlinks=False)
        if (named_after.st_dev, named_after.st_ino) != root_binding:
            raise ContractError("execution-root namespace changed during inventory")
    finally:
        os.close(descriptor)
    return {"content": sorted(content_rows, key=lambda row: row[1]), "binding": sorted(binding_rows, key=lambda row: row[1])}


def validate_execution_root_transition(
    before: Mapping[str, Sequence[Sequence[Any]]],
    after: Mapping[str, Sequence[Sequence[Any]]],
) -> None:
    if set(before) != {"content", "binding"} or set(after) != {"content", "binding"}:
        raise ContractError("execution root inventory is malformed")
    before_content = {row[1]: tuple(row) for row in before["content"]}
    after_content = {row[1]: tuple(row) for row in after["content"]}
    before_binding = {row[1]: tuple(row) for row in before["binding"]}
    after_binding = {row[1]: tuple(row) for row in after["binding"]}
    if (
        len(before_content) != len(before["content"])
        or len(after_content) != len(after["content"])
        or len(before_binding) != len(before["binding"])
        or len(after_binding) != len(after["binding"])
        or set(before_content) != set(after_content)
        or set(before_binding) != set(after_binding)
        or set(before_content) != set(before_binding)
    ):
        raise ContractError("execution root membership changed")
    allowed = "target/" + EXPECTED_PATH
    for path in before_content:
        if path != allowed and before_content[path] != after_content[path]:
            raise ContractError("execution root contains an unowned content or metadata change")
        if before_binding[path] != after_binding[path]:
            raise ContractError("execution root contains an unowned binding change")
    initial = before_content.get(allowed)
    final = after_content.get(allowed)
    if initial is None or final is None or initial[0] != "file" or final[0] != "file":
        raise ContractError("execution root is missing the exact owned leaf")
    # Mode, platform flags, and xattrs must remain exact. Only content bytes
    # and their resulting mtime/ctime may change at the sole owned leaf.
    if initial[2:4] != final[2:4] or initial[8] != final[8]:
        raise ContractError("execution root owned-leaf metadata changed")
    if (
        initial[2] != 0o644
        or initial[4] != len(EXPECTED_INITIAL)
        or initial[7] != sha256_bytes(EXPECTED_INITIAL)
        or final[4] != len(EXPECTED_FINAL)
        or final[7] != sha256_bytes(EXPECTED_FINAL)
    ):
        raise ContractError("execution root owned-leaf transition is not exact")


def list_worktree_entries(root: Path) -> Tuple[List[str], Tuple[int, int], Tuple[int, int]]:
    descriptor, root_binding = bound_directory(root)
    try:
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > 2:
                    raise ContractError("synthetic worktree contains extra entries")
        if sorted(names) != [".git", EXPECTED_PATH]:
            raise ContractError("synthetic worktree does not contain exactly .git and the sole reviewed file")
        git_stat = os.stat(".git", dir_fd=descriptor, follow_symlinks=False)
        file_stat = os.stat(EXPECTED_PATH, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISDIR(git_stat.st_mode):
            raise ContractError(".git is not a directly bound directory")
        if not stat.S_ISREG(file_stat.st_mode) or stat.S_IMODE(file_stat.st_mode) != 0o644 or file_stat.st_nlink != 1:
            raise ContractError("owned path is not a single-link regular mode-100644 file")
        named = os.stat(str(root), follow_symlinks=False)
        if (named.st_dev, named.st_ino) != root_binding:
            raise ContractError("parent namespace swapped during enumeration")
        rebound = os.stat(EXPECTED_PATH, dir_fd=descriptor, follow_symlinks=False)
        if (rebound.st_dev, rebound.st_ino) != (file_stat.st_dev, file_stat.st_ino):
            raise ContractError("owned file namespace swapped during enumeration")
        return names, root_binding, (file_stat.st_dev, file_stat.st_ino)
    finally:
        os.close(descriptor)


def read_owned_file(root: Path, expected_binding: Tuple[int, int], max_bytes: int = 1024) -> bytes:
    descriptor, root_binding = bound_directory(root)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        file_descriptor = os.open(EXPECTED_PATH, flags, dir_fd=descriptor)
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != expected_binding:
                raise ContractError("owned file binding changed")
            chunks = bytearray()
            while len(chunks) <= max_bytes:
                chunk = os.read(file_descriptor, min(4096, max_bytes + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) > max_bytes:
                raise ContractError("owned file exceeds its byte limit")
            after = os.fstat(file_descriptor)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                raise ContractError("owned file changed while it was read")
            named_after = os.stat(EXPECTED_PATH, dir_fd=descriptor, follow_symlinks=False)
            before_binding = (
                before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode),
                stat.S_IMODE(before.st_mode), before.st_nlink, before.st_size,
                before.st_mtime_ns,
            )
            named_binding = (
                named_after.st_dev, named_after.st_ino, stat.S_IFMT(named_after.st_mode),
                stat.S_IMODE(named_after.st_mode), named_after.st_nlink,
                named_after.st_size, named_after.st_mtime_ns,
            )
            if named_binding != before_binding:
                raise ContractError("owned file namespace changed after descriptor read")
        finally:
            os.close(file_descriptor)
        named_root = os.stat(str(root), follow_symlinks=False)
        if (named_root.st_dev, named_root.st_ino) != root_binding:
            raise ContractError("worktree root binding changed after file read")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def local_config_digest(root: Path) -> str:
    path = root / ".git/config"
    data = read_bounded_regular(path, 65_536)
    text = data.decode("utf-8", errors="strict")
    for forbidden in ("hooksPath", "include", "credential", "remote "):
        if forbidden.lower() in text.lower():
            raise ContractError("synthetic repository contains unreviewed Git configuration")
    return sha256_bytes(data)


def hooks_inventory(root: Path) -> List[Tuple[str, int, str]]:
    require_runtime_fs_capabilities()
    hooks = root / ".git/hooks"
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(hooks), flags)
    except OSError:
        raise ContractError("Git hooks directory binding is invalid")
    try:
        binding = os.fstat(descriptor)
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > 64:
                    raise ContractError("Git hooks inventory exceeds its entry limit")
        names.sort()
        inventory = []
        for name in names:
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or not name.endswith(".sample") or info.st_size > 65_536:
                raise ContractError("synthetic repository contains an active, unexpected, or oversized hook")
            file_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW
            if hasattr(os, "O_NONBLOCK"):
                file_flags |= os.O_NONBLOCK
            file_descriptor = os.open(name, file_flags, dir_fd=descriptor)
            try:
                opened = os.fstat(file_descriptor)
                if (opened.st_dev, opened.st_ino, opened.st_size) != (info.st_dev, info.st_ino, info.st_size):
                    raise ContractError("Git hook sample binding changed")
                data = bytearray()
                while len(data) <= 65_536:
                    chunk = os.read(file_descriptor, min(4096, 65_537 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                if len(data) > 65_536:
                    raise ContractError("Git hook sample exceeds its byte bound")
            finally:
                os.close(file_descriptor)
            inventory.append((name, stat.S_IMODE(info.st_mode), sha256_bytes(bytes(data))))
        named = os.stat(str(hooks), follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (binding.st_dev, binding.st_ino):
            raise ContractError("Git hooks namespace changed during enumeration")
        return inventory
    finally:
        os.close(descriptor)


def git_blob_oid(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def git_directory_inventory(root: Path) -> Tuple[List[Tuple[Any, ...]], List[Tuple[Any, ...]]]:
    """Return separate content and same-namespace binding inventories of .git.

    The content inventory is portable across a freshly constructed baseline.
    The binding inventory is deliberately host-local and is compared only
    before/after in the same target.  Keeping these evidence classes separate
    detects byte-identical namespace replacement without treating fresh
    baseline inode numbers as semantic content.
    """
    require_runtime_fs_capabilities()
    root_descriptor, root_binding = bound_directory(root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        git_named = os.stat(".git", dir_fd=root_descriptor, follow_symlinks=False)
        if not stat.S_ISDIR(git_named.st_mode):
            raise ContractError(".git must be a directly bound directory")
        git_descriptor = os.open(".git", flags, dir_fd=root_descriptor)
        try:
            git_opened = os.fstat(git_descriptor)
            if (git_opened.st_dev, git_opened.st_ino) != (git_named.st_dev, git_named.st_ino):
                raise ContractError(".git binding changed before inventory")
            content_rows: List[Tuple[Any, ...]] = []
            binding_rows: List[Tuple[Any, ...]] = [
                (
                    "directory", ".", git_opened.st_dev, git_opened.st_ino,
                    stat.S_IFMT(git_opened.st_mode), stat.S_IMODE(git_opened.st_mode),
                    git_opened.st_nlink,
                )
            ]
            counters = {"entries": 0, "bytes": 0}

            def walk(descriptor: int, prefix: str, depth: int) -> None:
                if depth > 16:
                    raise ContractError(".git inventory exceeds its depth limit")
                names: List[str] = []
                with os.scandir(descriptor) as entries:
                    for entry in entries:
                        names.append(entry.name)
                        counters["entries"] += 1
                        if counters["entries"] > 4096:
                            raise ContractError(".git inventory exceeds its entry limit")
                if len(names) != len(set(names)) or len({unicodedata.normalize("NFC", name).casefold() for name in names}) != len(names):
                    raise ContractError(".git inventory contains colliding names")
                for name in sorted(names):
                    if not name or name in (".", "..") or "/" in name or "\x00" in name or unicodedata.normalize("NFC", name) != name:
                        raise ContractError(".git inventory contains an unsafe name")
                    relative = prefix + "/" + name if prefix else name
                    named = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISDIR(named.st_mode):
                        child = os.open(name, flags, dir_fd=descriptor)
                        try:
                            opened = os.fstat(child)
                            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                                raise ContractError(".git directory binding changed")
                            content_rows.append(("directory", relative, stat.S_IMODE(opened.st_mode)))
                            binding_rows.append((
                                "directory", relative, opened.st_dev, opened.st_ino,
                                stat.S_IFMT(opened.st_mode), stat.S_IMODE(opened.st_mode),
                                opened.st_nlink,
                            ))
                            walk(child, relative, depth + 1)
                            rebound = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                            if (rebound.st_dev, rebound.st_ino) != (opened.st_dev, opened.st_ino):
                                raise ContractError(".git directory namespace changed")
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(named.st_mode) and named.st_nlink == 1:
                        if named.st_size > 8_388_608:
                            raise ContractError(".git file exceeds its byte limit")
                        counters["bytes"] += named.st_size
                        if counters["bytes"] > 33_554_432:
                            raise ContractError(".git inventory exceeds its total byte limit")
                        file_flags = os.O_RDONLY | os.O_NOFOLLOW
                        if hasattr(os, "O_NONBLOCK"):
                            file_flags |= os.O_NONBLOCK
                        opened_descriptor = os.open(name, file_flags, dir_fd=descriptor)
                        try:
                            opened = os.fstat(opened_descriptor)
                            if (opened.st_dev, opened.st_ino, opened.st_size) != (named.st_dev, named.st_ino, named.st_size):
                                raise ContractError(".git file binding changed")
                            digest = hashlib.sha256()
                            remaining = named.st_size
                            while remaining:
                                chunk = os.read(opened_descriptor, min(65_536, remaining))
                                if not chunk:
                                    raise ContractError(".git file changed while reading")
                                digest.update(chunk)
                                remaining -= len(chunk)
                            if os.read(opened_descriptor, 1):
                                raise ContractError(".git file exceeds its observed size")
                            opened_after = os.fstat(opened_descriptor)
                            if (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
                                raise ContractError(".git file changed while reading")
                        finally:
                            os.close(opened_descriptor)
                        rebound = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                        if (rebound.st_dev, rebound.st_ino, rebound.st_size, rebound.st_mtime_ns) != (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns):
                            raise ContractError(".git file namespace changed")
                        content_rows.append(("file", relative, stat.S_IMODE(named.st_mode), named.st_size, digest.hexdigest()))
                        binding_rows.append((
                            "file", relative, named.st_dev, named.st_ino,
                            stat.S_IFMT(named.st_mode), stat.S_IMODE(named.st_mode),
                            named.st_nlink, named.st_size,
                        ))
                    else:
                        raise ContractError(".git inventory contains a symlink, hardlink, or special file")

            walk(git_descriptor, "", 1)
            git_rebound = os.stat(".git", dir_fd=root_descriptor, follow_symlinks=False)
            root_rebound = os.stat(str(root), follow_symlinks=False)
            if (git_rebound.st_dev, git_rebound.st_ino) != (git_opened.st_dev, git_opened.st_ino) or (root_rebound.st_dev, root_rebound.st_ino) != root_binding:
                raise ContractError(".git or worktree namespace changed during inventory")
            return content_rows, binding_rows
        finally:
            os.close(git_descriptor)
    finally:
        os.close(root_descriptor)


def local_config_entries(root: Path, env: Mapping[str, str]) -> List[Tuple[str, str]]:
    raw = run_git(root, ["config", "--local", "--null", "--list"], env)
    values: List[Tuple[str, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            key, value = item.decode("utf-8", errors="strict").split("\n", 1)
        except (UnicodeDecodeError, ValueError):
            raise ContractError("local Git config is malformed")
        values.append((key, value))
    values.sort()
    mandatory = {
        ("core.repositoryformatversion", "0"),
        ("core.filemode", "true"),
        ("core.bare", "false"),
        ("core.logallrefupdates", "true"),
    }
    allowed_optional = {
        ("core.ignorecase", "true"), ("core.ignorecase", "false"),
        ("core.precomposeunicode", "true"), ("core.precomposeunicode", "false"),
    }
    actual = set(values)
    if not mandatory.issubset(actual) or actual - mandatory - allowed_optional:
        raise ContractError("synthetic repository contains unreviewed Git configuration")
    return values


def exact_refs(root: Path, env: Mapping[str, str]) -> List[Tuple[str, str]]:
    raw = run_git(root, ["for-each-ref", "--format=%(refname)%00%(objectname)"], env)
    refs: List[Tuple[str, str]] = []
    for line in raw.splitlines():
        parts = line.split(b"\0")
        if len(parts) != 2:
            raise ContractError("Git ref enumeration is malformed")
        refs.append((parts[0].decode("utf-8", errors="strict"), parts[1].decode("ascii", errors="strict")))
    return sorted(refs)


def normalized_git_inventory(rows: Sequence[Sequence[Any]]) -> List[Tuple[Any, ...]]:
    normalized = []
    for row in rows:
        current = tuple(row)
        if len(current) == 5 and current[0] == "file" and current[1] == "index":
            current = (current[0], current[1], current[2], current[3], "semantic-index")
        normalized.append(current)
    return normalized


def git_snapshot(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    names, root_binding, file_binding = list_worktree_entries(root)
    git_content_inventory, git_binding_inventory = git_directory_inventory(root)
    git_version, git_executable_sha256 = git_executable_evidence(root, env)
    branch = run_git(root, ["symbolic-ref", "--short", "HEAD"], env).decode("utf-8").strip()
    head = run_git(root, ["rev-parse", "HEAD"], env).decode("ascii").strip()
    tree = run_git(root, ["rev-parse", "HEAD^{tree}"], env).decode("ascii").strip()
    status_bytes = run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], env)
    staged = run_git(root, ["diff", "--cached", "--name-status", "-z", "--no-renames"], env)
    unstaged = run_git(root, ["diff", "--name-status", "-z", "--no-renames"], env)
    summary = run_git(root, ["diff", "--summary", "--no-renames"], env)
    refs = exact_refs(root, env)
    index = run_git(root, ["ls-files", "--stage", "-z"], env)
    unreachable = run_git(root, ["fsck", "--unreachable", "--no-reflogs", "--no-progress"], env)
    git_dir = run_git(root, ["rev-parse", "--git-dir"], env).decode("utf-8", errors="strict").strip()
    common_dir = run_git(root, ["rev-parse", "--git-common-dir"], env).decode("utf-8", errors="strict").strip()
    return {
        "names": names,
        "root_binding": root_binding,
        "file_binding": file_binding,
        "git_version": git_version,
        "git_executable_sha256": git_executable_sha256,
        "branch": branch,
        "head": head,
        "tree": tree,
        "status": status_bytes,
        "staged": staged,
        "unstaged": unstaged,
        "summary": summary,
        "config_digest": local_config_digest(root),
        "config_entries": local_config_entries(root, env),
        "hooks": hooks_inventory(root),
        "git_content_inventory": git_content_inventory,
        "git_binding_inventory": git_binding_inventory,
        "refs": refs,
        "index": index,
        "unreachable": unreachable,
        "git_dir": git_dir,
        "common_dir": common_dir,
        "file_bytes": read_owned_file(root, file_binding),
    }


def validate_exact_git_semantics(snapshot: Mapping[str, Any], expected_file_bytes: bytes) -> None:
    if re.fullmatch(r"git version [0-9]+\.[0-9]+\.[0-9]+(?:\.[A-Za-z0-9.-]+)?(?: \([A-Za-z0-9 ._-]+\))?", str(snapshot["git_version"])) is None or SHA256_RE.fullmatch(str(snapshot["git_executable_sha256"])) is None:
        raise ContractError("Git executable version/digest evidence is invalid")
    if snapshot["branch"] != EXPECTED_BRANCH or snapshot["head"] != EXPECTED_BASE_COMMIT or snapshot["tree"] != EXPECTED_BASE_TREE:
        raise ContractError("synthetic repository branch/base commit/tree drifted")
    if snapshot["refs"] != [("refs/heads/" + EXPECTED_BRANCH, EXPECTED_BASE_COMMIT)]:
        raise ContractError("synthetic repository ref set drifted")
    expected_index = "100644 {} 0\t{}\0".format(git_blob_oid(EXPECTED_INITIAL), EXPECTED_PATH).encode("ascii")
    if snapshot["index"] != expected_index or snapshot["staged"]:
        raise ContractError("synthetic repository index or stage set drifted")
    if snapshot["unreachable"]:
        raise ContractError("synthetic repository contains unreachable Git objects")
    if snapshot["git_dir"] != ".git" or snapshot["common_dir"] != ".git":
        raise ContractError("synthetic repository uses split or shared Git state")
    if snapshot["file_bytes"] != expected_file_bytes:
        raise ContractError("representative file does not have the exact expected bytes")
    if expected_file_bytes == EXPECTED_INITIAL:
        if snapshot["status"] or snapshot["unstaged"] or snapshot["summary"]:
            raise ContractError("synthetic repository is not clean before execution")
    else:
        if snapshot["unstaged"] != b"M\x00work-item.txt\x00" or snapshot["status"] != b" M work-item.txt\x00" or snapshot["summary"]:
            raise ContractError("worker diff is not the sole exact reviewed modification")


def validate_pre_snapshot(snapshot: Mapping[str, Any]) -> None:
    validate_exact_git_semantics(snapshot, EXPECTED_INITIAL)


def verify_harness_state(repository_root: Path, envelope: Mapping[str, Any], env: Mapping[str, str], expected_binding: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
    descriptor, binding = bound_directory(repository_root)
    os.close(descriptor)
    if expected_binding is not None and binding != expected_binding:
        raise ContractError("harness repository root binding drifted")
    head = run_git(repository_root, ["rev-parse", "HEAD"], env).decode("ascii").strip()
    tree = run_git(repository_root, ["rev-parse", "HEAD^{tree}"], env).decode("ascii").strip()
    status_bytes = run_git(repository_root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], env)
    if head != envelope["harness"]["commit"] or tree != envelope["harness"]["tree"]:
        raise ContractError("harness commit/tree differs from the envelope")
    if status_bytes:
        raise ContractError("harness repository is not clean at the exact bound head")
    return binding


def validate_post_snapshot(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    validate_exact_git_semantics(after, EXPECTED_FINAL)
    for key in ("root_binding", "file_binding", "git_version", "git_executable_sha256", "branch", "head", "tree", "config_digest", "config_entries", "hooks", "git_content_inventory", "git_binding_inventory", "refs", "index", "unreachable", "git_dir", "common_dir", "names"):
        if after[key] != before[key]:
            raise ContractError("post-execution {} drifted".format(key))


def static_prompt(envelope: Mapping[str, Any]) -> bytes:
    prompt = {
        "schema": "t11-worker-prompt/v1",
        "attempt_id": envelope["attempt_id"],
        "instruction": "Apply the exact reviewed representative Task and return codex-final-response/v1 only.",
        "owned_path": EXPECTED_PATH,
        "initial_hex": EXPECTED_INITIAL.hex(),
        "expected_hex": EXPECTED_FINAL.hex(),
    }
    encoded = canonical_bytes(prompt)
    if len(encoded) > envelope["limits"]["prompt_bytes"]:
        raise ContractError("worker prompt exceeds its byte limit")
    return encoded


def toml_literal(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ContractError("unsupported runtime override type")


def shell_environment_set_toml(environment: Mapping[str, str]) -> str:
    required = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS")
    if any(name not in environment or not isinstance(environment[name], str) for name in required):
        raise ContractError("live shell environment is missing an explicit required value")
    return "{" + ",".join(
        "{}={}".format(name, json.dumps(environment[name])) for name in sorted(required)
    ) + "}"


def build_live_argv(binary: Path, target_root: Path, repository_root: Path, envelope: Mapping[str, Any], environment: Optional[Mapping[str, str]] = None) -> List[str]:
    role = extract_static_role(repository_root)
    worker = envelope["worker"]
    if environment is None:
        environment = {
            "PATH": "/verified/bin:/usr/bin:/bin", "HOME": "/private-home", "TMPDIR": "/private-tmp",
            **REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0",
        }
    argv = [
        str(binary), "exec", "--json", "--ephemeral", "--strict-config", "--ignore-user-config", "--ignore-rules",
        "--model", worker["model"], "--sandbox", "workspace-write", "-C", str(target_root),
        "--output-schema", str((repository_root / FINAL_SCHEMA_PATH).resolve()),
        "-c", 'approval_policy="never"',
        "-c", 'model_reasoning_effort={}'.format(toml_literal(worker["reasoning_effort"])),
        "-c", 'developer_instructions={}'.format(toml_literal(role)),
        "-c", 'shell_environment_policy.inherit="none"',
        "-c", "shell_environment_policy.set=" + shell_environment_set_toml(environment),
    ]
    for key in sorted(REQUIRED_OVERRIDES):
        argv.extend(["-c", "{}={}".format(key, toml_literal(REQUIRED_OVERRIDES[key]))])
    argv.append("-")
    dynamic_markers = (envelope["attempt_id"], "Issue #23")
    if any(any(marker in argument for marker in dynamic_markers) for argument in argv):
        raise ContractError("dynamic Task/context data leaked into worker argv")
    return argv


def validate_final_response(value: Any, attempt_id: str, limits: Mapping[str, int]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("model final response must be an object")
    validate_json_limits(value, limits, "model final response")
    if len(canonical_bytes(value)) > limits["final_response_bytes"]:
        raise ContractError("model final response exceeds its byte limit")
    exact_keys(value, ("schema", "attempt_id", "outcome", "summary", "changed_paths"), "model final response")
    if value["schema"] != "codex-final-response/v1" or value["attempt_id"] != attempt_id:
        raise ContractError("model final response identity or attempt drifted")
    if value["outcome"] not in ("completed", "blocked", "failed"):
        raise ContractError("model final response outcome is invalid")
    if not isinstance(value["summary"], str) or not 1 <= len(value["summary"].encode("utf-8")) <= 1024:
        raise ContractError("model final response summary is invalid")
    paths = value["changed_paths"]
    if not isinstance(paths, list) or len(paths) > 1 or len(paths) != len(set(paths)) or any(path != EXPECTED_PATH for path in paths):
        raise ContractError("model final response changed_paths is invalid")
    if value["outcome"] == "completed" and paths != [EXPECTED_PATH]:
        raise ContractError("completed model final response must claim the sole owned path")
    if value["outcome"] != "completed" and paths:
        raise ContractError("non-completed model final response must not claim a changed path")
    return value


def raw_event_identity(event: Mapping[str, Any]) -> str:
    if isinstance(event.get("id"), str) and event["id"]:
        return "id:" + event["id"]
    item = event.get("item")
    if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
        return "item:" + item["id"]
    event_type = event.get("type")
    return "type:" + str(event_type)


def parse_jsonl(data: bytes, attempt_id: str, limits: Mapping[str, int]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    if len(data) > limits["stdout_bytes"]:
        raise ContractError("worker stdout exceeds its total byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ContractError("worker JSONL is not valid UTF-8")
    if not text or not text.endswith("\n"):
        raise ContractError("worker JSONL is empty or partial")
    raw_lines = text.splitlines()
    if len(raw_lines) > limits["event_count"]:
        raise ContractError("worker JSONL exceeds its event-count limit")
    seen: Dict[str, bytes] = {}
    raw_events: List[Dict[str, Any]] = []
    raw_terminal_count = 0
    for index, line in enumerate(raw_lines, 1):
        encoded = line.encode("utf-8")
        if not encoded or len(encoded) > limits["line_bytes"]:
            raise ContractError("worker JSONL line is empty or oversized")
        event = strict_json_loads(line, "worker JSONL event")
        if not isinstance(event, dict):
            raise ContractError("worker JSONL event must be an object")
        validate_json_limits(event, limits, "worker JSONL event")
        event_type = event.get("type")
        if event_type not in KNOWN_RAW_TYPES:
            raise ContractError("worker JSONL contains unknown event or terminal semantics")
        if event_type in TERMINAL_TYPES:
            raw_terminal_count += 1
        identity = raw_event_identity(event)
        canonical = canonical_bytes(event)
        if identity in seen:
            if seen[identity] != canonical:
                raise ContractError("worker JSONL contains a conflicting duplicate identity")
            continue
        seen[identity] = canonical
        raw_events.append(event)
    if not raw_events:
        raise ContractError("worker JSONL has no events")
    if raw_terminal_count != 1:
        raise ContractError("worker JSONL must contain exactly one raw terminal occurrence")

    normalized: List[Dict[str, Any]] = []
    final_response: Optional[Dict[str, Any]] = None
    terminal_states: List[str] = []
    for raw in raw_events:
        event_type = raw["type"]
        kind = "worker-message"
        state_value = "running"
        if event_type in ("thread.started", "turn.started"):
            kind = "worker-started"
        elif event_type == "error":
            kind = "worker-error"
        elif event_type == "turn.completed":
            kind = "worker-terminal"
            state_value = "completed"
            terminal_states.append(state_value)
        elif event_type == "turn.failed":
            kind = "worker-terminal"
            error = raw.get("error")
            rendered = json.dumps(error, ensure_ascii=False, sort_keys=True) if error is not None else ""
            state_value = "interrupted" if "interrupt" in rendered.lower() else "failed"
            terminal_states.append(state_value)
        elif event_type == "item.completed":
            item = raw.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text_value = item.get("text")
                if not isinstance(text_value, str):
                    raise ContractError("agent message final response text is missing")
                if final_response is not None:
                    raise ContractError("worker emitted multiple model final responses")
                try:
                    parsed_final = strict_json_loads(text_value, "model final response")
                except ContractError:
                    raise ContractError("model final response is malformed JSON")
                final_response = validate_final_response(parsed_final, attempt_id, limits)
        normalized.append({
            "schema": "loop-event/v1",
            "attempt_id": attempt_id,
            "sequence": len(normalized) + 1,
            "kind": kind,
            "source": "codex-exec-adapter",
            "state": state_value,
            "payload_digest": sha256_bytes(canonical_bytes(raw)),
        })
    if len(terminal_states) != 1:
        raise ContractError("worker JSONL must contain exactly one terminal event")
    if final_response is None:
        raise ContractError("worker JSONL has no bounded model final response")
    return normalized, final_response, terminal_states[0]


def event_digest(events: Sequence[Mapping[str, Any]]) -> str:
    return sha256_bytes(b"".join(canonical_bytes(event) for event in events))


def expected_worktree_tree_oid() -> str:
    blob_header = b"blob " + str(len(EXPECTED_FINAL)).encode("ascii") + b"\0"
    blob_oid = hashlib.sha1(blob_header + EXPECTED_FINAL).digest()
    tree_body = b"100644 work-item.txt\0" + blob_oid
    tree_header = b"tree " + str(len(tree_body)).encode("ascii") + b"\0"
    return hashlib.sha1(tree_header + tree_body).hexdigest()


def validate_verification_bundle(bundle: Any, env: Mapping[str, str]) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ContractError("verification bundle must be an object")
    exact_keys(bundle, ("schema", "attempt_id", "target_root", "before", "expected"), "verification bundle")
    if bundle["schema"] != "t11-verification-bundle/v1":
        raise ContractError("verification bundle schema is invalid")
    require_string(bundle["attempt_id"], "verification attempt", ATTEMPT_RE)
    target_root = bundle["target_root"]
    if not isinstance(target_root, str) or "\x00" in target_root:
        raise ContractError("verification target root is invalid")
    root = Path(target_root)
    before = bundle["before"]
    if not isinstance(before, dict):
        raise ContractError("verification pre-state is invalid")
    expected_before_keys = (
        "root_binding", "file_binding", "git_version", "git_executable_sha256", "branch", "head", "tree", "config_digest",
        "config_entries", "hooks", "git_content_inventory", "git_binding_inventory", "refs", "index_hex",
        "unreachable_hex", "git_dir", "common_dir", "names",
    )
    exact_keys(before, expected_before_keys, "verification pre-state")
    before_normalized = {
        "root_binding": tuple(before["root_binding"]),
        "file_binding": tuple(before["file_binding"]),
        "git_version": before["git_version"],
        "git_executable_sha256": before["git_executable_sha256"],
        "branch": before["branch"], "head": before["head"], "tree": before["tree"],
        "config_digest": before["config_digest"],
        "config_entries": [tuple(row) for row in before["config_entries"]],
        "hooks": [tuple(row) for row in before["hooks"]],
        "git_content_inventory": [tuple(row) for row in before["git_content_inventory"]],
        "git_binding_inventory": [tuple(row) for row in before["git_binding_inventory"]],
        "refs": [tuple(row) for row in before["refs"]],
        "index": bytes.fromhex(before["index_hex"]),
        "unreachable": bytes.fromhex(before["unreachable_hex"]),
        "git_dir": before["git_dir"], "common_dir": before["common_dir"],
        "names": before["names"],
    }
    after = git_snapshot(root, env)
    # Reassert the canonical target directly. The verifier does not use a
    # caller-provided branch, head, tree, index, ref, or object set as truth.
    validate_exact_git_semantics(after, EXPECTED_FINAL)
    with tempfile.TemporaryDirectory(prefix="t11-verifier-baseline-") as temporary:
        baseline_container = Path(temporary)
        os.chmod(baseline_container, 0o700)
        baseline_root = create_synthetic_repository(baseline_container, env)
        baseline = git_snapshot(baseline_root, env)
        validate_pre_snapshot(baseline)
    if normalized_git_inventory(after["git_content_inventory"]) != normalized_git_inventory(baseline["git_content_inventory"]):
        raise ContractError("fresh verifier found extra or altered Git-internal state")
    validate_post_snapshot(before_normalized, after)
    if bundle["expected"] != {"path": EXPECTED_PATH, "mode": "100644", "sha256": sha256_bytes(EXPECTED_FINAL)}:
        raise ContractError("verification expected binding is invalid")
    record = {
        "schema": "t11-verifier-result/v1",
        "attempt_id": bundle["attempt_id"],
        "status": "pass",
        "fresh_process": True,
        "read_only": True,
        "checks": VERIFIER_CHECKS,
    }
    return record


def serializable_pre_state(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "root_binding": list(snapshot["root_binding"]),
        "file_binding": list(snapshot["file_binding"]),
        "git_version": snapshot["git_version"],
        "git_executable_sha256": snapshot["git_executable_sha256"],
        "branch": snapshot["branch"],
        "head": snapshot["head"],
        "tree": snapshot["tree"],
        "config_digest": snapshot["config_digest"],
        "config_entries": [list(row) for row in snapshot["config_entries"]],
        "hooks": [list(row) for row in snapshot["hooks"]],
        "git_content_inventory": [list(row) for row in snapshot["git_content_inventory"]],
        "git_binding_inventory": [list(row) for row in snapshot["git_binding_inventory"]],
        "refs": [list(row) for row in snapshot["refs"]],
        "index_hex": snapshot["index"].hex(),
        "unreachable_hex": snapshot["unreachable"].hex(),
        "git_dir": snapshot["git_dir"],
        "common_dir": snapshot["common_dir"],
        "names": list(snapshot["names"]),
    }


def run_fresh_verifier(repository_root: Path, target_root: Path, before: Mapping[str, Any], attempt_id: str, env: Mapping[str, str]) -> Dict[str, Any]:
    bundle = {
        "schema": "t11-verification-bundle/v1",
        "attempt_id": attempt_id,
        "target_root": str(target_root),
        "before": serializable_pre_state(before),
        "expected": {"path": EXPECTED_PATH, "mode": "100644", "sha256": sha256_bytes(EXPECTED_FINAL)},
    }
    result = run_bounded_process(
        [sys.executable, "-I", str((repository_root / ".github/scripts/codex-exec-adapter.py").resolve()), "verify"],
        repository_root,
        env,
        canonical_bytes(bundle),
        30,
        65_536,
        65_536,
        2,
    )
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped or result.exit_code != 0 or result.stderr_size:
        raise ContractError("fresh verifier process failed")
    record = decode_json_object(result.stdout, "fresh verifier result")
    return validate_verifier_record(record, attempt_id)


def worker_process_record(process: ProcessResult) -> Dict[str, Any]:
    return {
        "logical_invocations": 1,
        "exit_code": process.exit_code,
        "timed_out": process.timed_out,
        "signal": process.signal_number,
        "stdout_bytes": len(process.stdout),
        "stderr_bytes": process.stderr_size,
    }


def execute_slice(repository_root: Path, envelope: Dict[str, Any], profile: Dict[str, Any], mode: str, fake_behavior: str = "valid", include_artifacts: bool = False) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    validate_envelope(envelope)
    validate_runtime_profile(profile, allow_fixture=(mode == "offline"))
    if envelope["worker"]["model"] != profile["request"]["model"] or envelope["worker"]["reasoning_effort"] != profile["request"]["reasoning_effort"]:
        raise ContractError("envelope and runtime profile request differ")
    if mode == "live" and (profile["status"] != "match" or profile["live_run_allowed"] is not True):
        raise ContractError("live execution blocked by runtime profile status: " + profile["status"])
    if mode == "live":
        if profile["scope"] != "exact-head-live-sensor":
            raise ContractError("live execution requires an exact-head-live-sensor profile")
        observed = datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - observed).total_seconds()
        if age < -300 or age > 900:
            raise ContractError("live runtime profile is stale or future-dated")
        fresh_profile = observe_runtime_profile(
            repository_root,
            envelope["worker"]["model"],
            envelope["worker"]["reasoning_effort"],
        )
        validate_runtime_profile(fresh_profile)
        supplied_semantics = {key: value for key, value in profile.items() if key != "observed_at"}
        fresh_semantics = {key: value for key, value in fresh_profile.items() if key != "observed_at"}
        if fresh_profile["status"] != "match" or fresh_profile["live_run_allowed"] is not True or fresh_semantics != supplied_semantics:
            raise ContractError("fresh semantic runtime sensor does not match the approved profile")
    if mode not in ("offline", "live"):
        raise ContractError("unsupported execution mode")

    with tempfile.TemporaryDirectory(prefix="t11-runtime-") as temporary:
        container = Path(temporary)
        os.chmod(container, 0o700)
        private_home = container / "home"
        private_tmp = container / "tmp"
        private_home.mkdir(mode=0o700)
        private_tmp.mkdir(mode=0o700)
        executable = Path(sys.executable).resolve() if mode == "offline" else resolve_executable_from_path("codex", {"PATH": REVIEWED_SENSOR_PATH})
        if mode == "live" and executable is None:
            raise ContractError("approved Codex executable is unavailable")
        assert executable is not None
        extra = {"T11_FAKE_BEHAVIOR": fake_behavior} if mode == "offline" else None
        environment = minimal_environment(executable, private_home, private_tmp, extra)
        harness_binding = None
        if mode == "live":
            if hash_regular_file(executable) != profile["client"]["binary_sha256"]:
                raise ContractError("Codex binary digest drifted after the runtime sensor")
            version_result = bounded_capture([str(executable), "--version"], container, environment)
            help_result = bounded_capture([str(executable), "exec", "--help"], container, environment)
            if version_result.exit_code != 0 or help_result.exit_code != 0 or version_result.timed_out or help_result.timed_out or version_result.stdout_overflow or help_result.stdout_overflow:
                raise ContractError("Codex version/help evidence became uncheckable before execution")
            if version_result.stdout.decode("utf-8", errors="strict").strip() != profile["client"]["version_output"] or sha256_bytes(help_result.stdout) != profile["client"]["exec_help_sha256"]:
                raise ContractError("Codex version/help evidence drifted after the runtime sensor")
            harness_binding = verify_harness_state(repository_root, envelope, environment)
        target_root = create_synthetic_repository(container, environment)
        before = git_snapshot(target_root, environment)
        validate_pre_snapshot(before)
        execution_root_before = execution_root_inventory(container)

        if mode == "offline":
            worker_argv = [sys.executable, "-I", str((repository_root / FAKE_PATH).resolve())]
        else:
            worker_argv = build_live_argv(executable, target_root, repository_root, envelope, environment)
        prompt = static_prompt(envelope)
        process = run_bounded_process(
            worker_argv,
            target_root,
            environment,
            prompt,
            envelope["limits"]["worker_timeout_seconds"],
            envelope["limits"]["stdout_bytes"],
            envelope["limits"]["stderr_bytes"],
            2,
        )
        execution_root_after = execution_root_inventory(container)
        validate_execution_root_transition(execution_root_before, execution_root_after)
        if process.timed_out:
            raise ContractError("worker timed out and was terminated and reaped")
        if process.stdout_overflow:
            raise ContractError("worker stdout exceeded its bound")
        if process.stderr_overflow:
            raise ContractError("worker stderr exceeded its bound")
        if not process.reaped:
            raise ContractError("worker process group was not fully reaped")
        events, final_response, terminal_state = parse_jsonl(process.stdout, envelope["attempt_id"], envelope["limits"])
        if process.exit_code != 0 or process.signal_number is not None or terminal_state != "completed" or final_response["outcome"] != "completed":
            raise ContractError("worker exit, terminal event, and final response are not a consistent success")
        after = git_snapshot(target_root, environment)
        validate_post_snapshot(before, after)
        verifier = run_fresh_verifier(repository_root, target_root, before, envelope["attempt_id"], environment)
        if mode == "live":
            assert harness_binding is not None
            verify_harness_state(repository_root, envelope, environment, harness_binding)
        verifier_digest = sha256_bytes(canonical_bytes(verifier))
        result = {
            "schema": "execution-result/v1",
            "attempt_id": envelope["attempt_id"],
            "status": "pass",
            "authority": "adapter-authored",
            "worker": worker_process_record(process),
            "events": {
                "count": len(events),
                "terminal_count": 1,
                "terminal_state": terminal_state,
                "canonical_sha256": event_digest(events),
            },
            "final_response": {
                "present": True,
                "valid": True,
                "sha256": sha256_bytes(canonical_bytes(final_response)),
                "outcome": final_response["outcome"],
            },
            "git": {
                "pre_head": before["head"], "post_head": after["head"],
                "pre_tree": before["tree"], "post_tree": after["tree"],
                "worktree_tree": expected_worktree_tree_oid(),
                "changed_paths": [EXPECTED_PATH], "owned_paths_only": True,
                "expected_bytes": True, "other_changes": False,
            },
            "verifier": {
                "fresh_process": True, "read_only": True, "status": "pass", "record_sha256": verifier_digest,
            },
            "digests": {
                "envelope_sha256": sha256_bytes(canonical_bytes(envelope)),
                "runtime_profile_sha256": sha256_bytes(canonical_bytes(profile)),
            },
            "privacy": {
                "raw_jsonl_retained": False, "raw_reasoning_retained": False,
                "raw_stderr_retained": False, "private_paths_retained": False,
            },
        }
        validate_execution_result(result, envelope, profile, verifier)
        if include_artifacts:
            return {
                "schema": "t11-runtime-artifact-bundle/v1",
                "runtime_profile": profile,
                "envelope": envelope,
                "execution_result": result,
                "verifier": verifier,
            }
        return result


def safe_error(reason: str) -> Dict[str, Any]:
    del reason
    return {"schema": "codex-exec-adapter-error/v1", "status": "fail", "reason": "bounded runtime contract failure"}


def hash_regular_file(path: Path, max_bytes: int = 536_870_912) -> str:
    require_runtime_fs_capabilities()
    info = os.stat(str(path), follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise ContractError("runtime executable is not a bounded regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise ContractError("runtime executable binding changed before hashing")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            digest.update(chunk)
        after_open = os.fstat(descriptor)
        if (after_open.st_dev, after_open.st_ino, after_open.st_size, after_open.st_mtime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ContractError("runtime executable changed while hashing")
    finally:
        os.close(descriptor)
    after = os.stat(str(path), follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
        raise ContractError("runtime executable namespace changed while hashing")
    return digest.hexdigest()


def classify_release(version_output: str) -> str:
    lowered = version_output.lower()
    if "alpha" in lowered:
        return "prerelease-alpha"
    if "beta" in lowered:
        return "prerelease-beta"
    if re.search(r"(?:^|[.\-])rc(?:[.\-]|[0-9])", lowered):
        return "prerelease-rc"
    if re.fullmatch(r"codex-cli [0-9]+\.[0-9]+\.[0-9]+", version_output.strip()):
        return "stable"
    return "unknown"


def sanitize_version_output(data: bytes) -> str:
    try:
        value = data.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return "unrecognized-version-output"
    allowed = re.fullmatch(
        r"codex-cli [0-9]+\.[0-9]+\.[0-9]+(?:-(?:alpha|beta|rc)(?:\.[0-9A-Za-z-]+)?)?",
        value,
    )
    if allowed is None or PRIVATE_PATH_RE.search(value) or any(pattern.search(value) for pattern in SENSITIVE_VALUE_PATTERNS):
        return "unrecognized-version-output"
    return value


def bounded_capture(argv: Sequence[str], cwd: Path, env: Mapping[str, str], stdin_bytes: bytes = b"", timeout: float = 15) -> ProcessResult:
    return run_bounded_process(argv, cwd, env, stdin_bytes, timeout, 1_048_576, 1_048_576, 2)


def auth_class(binary: Path, cwd: Path, env: Mapping[str, str]) -> str:
    result = bounded_capture([str(binary), "login", "status"], cwd, env)
    if result.exit_code != 0 or result.timed_out or result.stdout_overflow or result.stderr_overflow:
        return "unavailable"
    text = result.stdout.decode("utf-8", errors="replace").lower()
    if "api key" in text:
        return "api-key"
    if "logged in" in text or "chatgpt" in text:
        return "signed-in-client"
    return "unknown"


def reviewed_runtime_configuration(env: Mapping[str, str]) -> Dict[str, Any]:
    return {
        "approval_policy": "never",
        "model_reasoning_effort": "high",
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {
            name: env[name] for name in (
                "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
                "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM",
                "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS",
            )
        },
        **REQUIRED_OVERRIDES,
    }


def runtime_configuration_argv(binary: Path, env: Mapping[str, str]) -> List[str]:
    values = reviewed_runtime_configuration(env)
    argv = [str(binary), "--strict-config", "--ignore-user-config"]
    for key in ("approval_policy", "model_reasoning_effort"):
        argv.extend(["-c", "{}={}".format(key, toml_literal(values[key]))])
    argv.extend(["-c", 'shell_environment_policy.inherit="none"'])
    argv.extend(["-c", "shell_environment_policy.set=" + shell_environment_set_toml(env)])
    for key in sorted(REQUIRED_OVERRIDES):
        argv.extend(["-c", "{}={}".format(key, toml_literal(REQUIRED_OVERRIDES[key]))])
    return argv


def probe_runtime_configuration(binary: Path, root: Path, env: Mapping[str, str]) -> Tuple[str, str]:
    """Run no-model semantic probes for every reviewed live setting.

    Help text is insufficient because the current alpha accepts unknown
    ``-c`` keys under strict-config.  A conforming stable client must emit the
    bounded effective-configuration attestation below and must independently
    demonstrate the exact inherited environment in the sandbox probe.
    """
    required = reviewed_runtime_configuration(env)
    attestation_argv = runtime_configuration_argv(binary, env) + ["doctor", "--json"]
    attested = bounded_capture(attestation_argv, root, env)
    if attested.timed_out or attested.stdout_overflow or attested.stderr_overflow or not attested.reaped:
        return "UNCHECKABLE", "UNCHECKABLE"
    if attested.exit_code != 0:
        return "fail", "not-run"
    try:
        attestation = decode_json_object(attested.stdout, "runtime configuration attestation")
        exact_keys(
            attestation,
            ("schema", "effective_configuration_sha256", "model_invoked"),
            "runtime configuration attestation",
        )
    except ContractError:
        return "not-proven", "not-run"
    expected_digest = sha256_bytes(canonical_bytes(required))
    if attestation != {
        "schema": "t11-runtime-configuration-probe/v1",
        "effective_configuration_sha256": expected_digest,
        "model_invoked": False,
    }:
        return "not-proven", "not-run"

    # This second probe invokes no model. A forbidden parent sentinel must be
    # filtered while the exact reviewed set reaches the direct sandbox command.
    probe_env = dict(env)
    probe_env["T11_FORBIDDEN_SENTINEL"] = "must-not-survive"
    set_values = dict(required["shell_environment_policy.set"])
    env_program = Path("/usr/bin/env")
    if not env_program.is_file():
        return "UNCHECKABLE", "UNCHECKABLE"
    argv = runtime_configuration_argv(binary, env) + [
        "sandbox", "--sandbox-state-disable-network", "-C", str(root),
        str(env_program), "-0",
    ]
    result = bounded_capture(argv, root, probe_env)
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
        return "UNCHECKABLE", "UNCHECKABLE"
    if result.exit_code != 0:
        return "fail", "fail"
    entries = result.stdout.split(b"\0")
    parsed: Dict[str, bytes] = {}
    for entry in entries:
        if not entry:
            continue
        if b"=" not in entry:
            return "fail", "fail"
        name, value = entry.split(b"=", 1)
        try:
            key = name.decode("ascii")
        except UnicodeDecodeError:
            return "fail", "fail"
        parsed[key] = value
    if any(parsed.get(name) != value.encode("utf-8") for name, value in set_values.items()) or "T11_FORBIDDEN_SENTINEL" in parsed:
        return "pass", "fail"
    permitted_automatic = {"PWD", "SHLVL", "_", "__CF_USER_TEXT_ENCODING"}
    if set(parsed) - set(set_values) - permitted_automatic or any(SECRET_NAME_RE.search(name) for name in parsed):
        return "pass", "fail"
    return "pass", "pass"


def observe_runtime_profile(repository_root: Path, model: str, reasoning: str) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    resolved = resolve_executable_from_path("codex", {"PATH": REVIEWED_SENSOR_PATH})
    if resolved is None:
        return {
            "schema": "runtime-profile/v1", "repository": REPOSITORY,
            "observed_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "scope": "exact-head-live-sensor", "status": "UNKNOWN", "reason": "Codex executable is unavailable",
            "platform": {"os": os.uname().sysname, "architecture": os.uname().machine},
            "client": {"version_output": "unavailable", "release_class": "unknown", "binary_sha256": "0" * 64, "exec_help_sha256": "0" * 64, "resolved_path_recorded": False},
            "capabilities": {"exec_json": False, "ephemeral": False, "strict_config": False, "ignore_user_config": False, "workspace_write": False, "approval_never": False, "config_recognition_probe": "UNCHECKABLE", "shell_environment_probe": "UNCHECKABLE", "process_containment_probe": "UNCHECKABLE", "model": False, "reasoning": False, "sandbox": False, "approval": False, "overrides": False},
            "auth": {"class": "unavailable", "credential_values_recorded": False},
            "request": {"model": model, "reasoning_effort": reasoning, "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"},
            "shell_environment": {"inherit": "none", "required_names": ["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS"], "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated", "fixed_values": {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}, "private_home": True, "private_tmpdir": True, "secret_named_variables_excluded": True, "probe_required": True},
            "live_run_allowed": False,
        }
    binary = Path(resolved).resolve()
    with tempfile.TemporaryDirectory(prefix="t11-profile-") as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        home = root / "home"
        tmpdir = root / "tmp"
        work = root / "work"
        home.mkdir(mode=0o700)
        tmpdir.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        env = minimal_environment(binary, home, tmpdir)
        version_result = bounded_capture([str(binary), "--version"], work, env)
        help_result = bounded_capture([str(binary), "exec", "--help"], work, env)
        if version_result.exit_code != 0 or help_result.exit_code != 0 or version_result.timed_out or help_result.timed_out or version_result.stdout_overflow or help_result.stdout_overflow:
            raise ContractError("runtime version/help sensor is UNCHECKABLE")
        version_output = sanitize_version_output(version_result.stdout)
        help_bytes = help_result.stdout
        help_text = help_bytes.decode("utf-8", errors="strict")
        release_class = classify_release(version_output)
        flags = {
            "exec_json": "--json" in help_text,
            "ephemeral": "--ephemeral" in help_text,
            "strict_config": "--strict-config" in help_text,
            "ignore_user_config": "--ignore-user-config" in help_text,
            "workspace_write": "workspace-write" in help_text,
            "model": "--model" in help_text,
            "sandbox": "--sandbox" in help_text,
        }
        if release_class == "stable":
            config_probe, shell_probe = probe_runtime_configuration(binary, work, env)
            containment_probe = "pass" if live_containment_proven() else "UNCHECKABLE"
        else:
            config_probe, shell_probe = "not-proven", "not-run"
            containment_probe = "not-run"
        config_ok = config_probe == "pass" and shell_probe == "pass" and containment_probe == "pass"
        caps = {
            **flags,
            "approval_never": config_ok,
            "config_recognition_probe": config_probe,
            "shell_environment_probe": shell_probe,
            "process_containment_probe": containment_probe,
            "reasoning": config_ok,
            "approval": config_ok,
            "overrides": config_ok,
        }
        all_required = all(caps[name] for name in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"))
        if release_class.startswith("prerelease"):
            profile_status, reason = "unsupported-client", "unapproved-prerelease: {} client".format(release_class.split("-", 1)[1])
        elif release_class != "stable":
            profile_status, reason = "UNKNOWN", "client release class is unverifiable"
        elif config_probe == "UNCHECKABLE" or shell_probe == "UNCHECKABLE" or containment_probe == "UNCHECKABLE":
            profile_status, reason = "UNCHECKABLE", "required config, shell-environment, or process-containment capability is uncheckable"
        elif config_probe == "fail" or shell_probe == "fail" or containment_probe == "fail" or not all_required:
            profile_status, reason = "unsupported-client", "required config, shell-environment, or process-containment capability is unsupported"
        else:
            profile_status, reason = "match", "stable client and all reviewed semantic capability probes match"
        profile = {
            "schema": "runtime-profile/v1", "repository": REPOSITORY,
            "observed_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "scope": "exact-head-live-sensor", "status": profile_status, "reason": reason,
            "platform": {"os": os.uname().sysname, "architecture": os.uname().machine},
            "client": {"version_output": version_output, "release_class": release_class, "binary_sha256": hash_regular_file(binary), "exec_help_sha256": sha256_bytes(help_bytes), "resolved_path_recorded": False},
            "capabilities": caps,
            "auth": {"class": auth_class(binary, work, env), "credential_values_recorded": False},
            "request": {"model": model, "reasoning_effort": reasoning, "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"},
            "shell_environment": {"inherit": "none", "required_names": ["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS"], "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated", "fixed_values": {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}, "private_home": True, "private_tmpdir": True, "secret_named_variables_excluded": True, "probe_required": True},
            "live_run_allowed": profile_status == "match",
        }
        validate_runtime_profile(profile)
        return profile


def load_repository_json(repository_root: Path, relative: str, max_bytes: int = MAX_STDIN_BYTES) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    path = repository_root / relative
    info = os.stat(str(path), follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o022 or info.st_size > max_bytes:
        raise ContractError(relative + " is not a bounded non-writable regular file")
    return decode_json_object(read_bounded_regular(path, max_bytes), relative)


def cli_run(args: argparse.Namespace, repository_root: Path) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    data = read_stdin_bounded()
    if args.mode == "offline":
        envelope = decode_json_object(data, "offline envelope")
        profile = load_repository_json(repository_root, "tests/runtime/fixtures/runtime-profile-valid.v1.json")
    else:
        live_input = decode_json_object(data, "live run input")
        exact_keys(live_input, ("schema", "envelope", "runtime_profile"), "live run input")
        if live_input["schema"] != "t11-live-run-input/v1":
            raise ContractError("live run input schema is invalid")
        envelope = live_input["envelope"]
        profile = live_input["runtime_profile"]
    return execute_slice(
        repository_root, envelope, profile, args.mode, args.fake_behavior,
        include_artifacts=True,
    )


def cli_verify(repository_root: Path) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    bundle = decode_json_object(read_stdin_bounded(), "verification bundle")
    # The parent passes a minimal environment. Reconstruct only the explicit
    # values needed by bounded Git reads and never copy arbitrary host values.
    env = {name: os.environ[name] for name in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS") if name in os.environ}
    return validate_verification_bundle(bundle, env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="T11 deterministic Codex execution controller")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="execute one bounded representative slice")
    run_parser.add_argument("--mode", choices=("offline", "live"), required=True)
    run_parser.add_argument(
        "--fake-behavior",
        choices=("valid", "no-edit", "final-failed", "extra-file", "mode-change", "rename", "symlink", "stage", "git-config", "git-hook", "git-object", "git-ref", "git-split-index", "git-head-replace", "git-namespace-replace", "branch-drift", "replace-file", "tmpdir-write", "execution-root-sibling-write", "invalid-utf8", "partial-jsonl", "scalar-event", "stdout-flood", "stderr-flood", "attempt-drift", "zero-terminal", "multiple-terminal", "unknown-terminal", "interrupted", "identical-duplicate", "conflicting-duplicate", "nested-json", "long-string", "sleep", "ignore-term", "child-held-pipe", "child-exit-holds-pipe", "child-exit-closed-pipes", "child-escaped-session", "signal"),
        default="valid",
        help=argparse.SUPPRESS,
    )
    subparsers.add_parser("verify", help=argparse.SUPPRESS)
    profile_parser = subparsers.add_parser("profile", help="observe a bounded live runtime profile without running the Task")
    profile_parser.add_argument("--model", default="gpt-5.6-sol")
    profile_parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"), default="high")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    repository_root = Path(__file__).resolve().parents[2]
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = cli_run(args, repository_root)
        elif args.command == "verify":
            result = cli_verify(repository_root)
        elif args.command == "profile":
            result = observe_runtime_profile(repository_root, args.model, args.reasoning_effort)
        else:
            raise ContractError("unsupported adapter command")
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (ContractError, OSError, subprocess.SubprocessError, UnicodeError, ValueError, KeyError, TypeError, RecursionError) as error:
        sys.stdout.buffer.write(canonical_bytes(safe_error(str(error))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
