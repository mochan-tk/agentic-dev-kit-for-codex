#!/usr/bin/env python3
"""Deterministic controller for the bounded T11 Codex execution slice.

Live execution is an explicit mode. Required CI uses only ``run --offline``
with the repository fake process. Dynamic envelope and Task bytes are read
from stdin and are never placed in a process argv.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime
import hashlib
import json
import math
import os
import re
import signal
import socket
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
    "memories.generate_memories": False,
    "memories.use_memories": False,
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
SHELL_ENVIRONMENT_NAMES = (
    "PATH", "HOME", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
    "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT",
    "GIT_OPTIONAL_LOCKS",
)
DYNAMIC_ENVIRONMENT_NAMES = ("CODEX_HOME", "HOME", "PATH", "TMPDIR")
SANDBOX_NETWORK_MARKER = "CODEX_SANDBOX_NETWORK_DISABLED"
SANDBOX_NETWORK_MARKER_VALUE = b"1"
# Official 0.150.1 Linux restricted-network seccomp returns EPERM for the
# denied AF_INET socket/connect syscalls.  Other OSError values are not proof
# of sandbox enforcement and remain UNCHECKABLE through exit 43.
NETWORK_SANDBOX_PROBE_SCRIPT = (
    "import errno,socket,sys\n"
    "try:\n"
    " with socket.socket() as sock:\n"
    "  sock.settimeout(2)\n"
    "  sock.connect(('127.0.0.1',int(sys.argv[1])))\n"
    "except OSError as error:\n"
    " raise SystemExit(0 if error.errno == errno.EPERM else 43)\n"
    "raise SystemExit(42)\n"
)
REVIEWED_RULES_RELATIVE_PATH = "rules/t11-reviewed.rules"
REVIEWED_RULES_BYTES = (
    b"# T11 reviewed empty execpolicy profile. Platform policy remains authoritative.\n"
)
COLIMA_PROVIDER_INPUT_SCHEMA = "t11-colima-provider-input/v1"
CONTAINMENT_PROVIDER_EVIDENCE_SCHEMA = "t11-containment-provider-evidence/v1"
COLIMA_PROVIDER_KIND = "colima-vm"
COLIMA_VM_BACKEND = "vz"
COLIMA_ARCHITECTURE = "aarch64"
COLIMA_RUNTIME_ROOT_ENV = "T11_VM_RUNTIME_ROOT"
LIVE_ATTEMPT_CLAIM_NAME = "t11-live-attempt.claim.v1.json"
APPROVED_CODEX_VERSION = "codex-cli 0.150.1"
APPROVED_CODEX_ARCHIVE_SHA256 = "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264"
APPROVED_BWRAP_PACKAGE_VERSION = "0.9.0-1ubuntu0.1"
APPROVED_BWRAP_VERSION_OUTPUT = "bubblewrap 0.9.0"
APPROVED_BWRAP_BINARY_SHA256 = "ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8"
APPROVED_APPARMOR_PACKAGE_VERSION = "4.0.1really4.0.1-0ubuntu0.24.04.7"
APPROVED_BWRAP_PROFILE_SHA256 = "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9"
STAGE_A1_BWRAP_BINARY = "/usr/bin/bwrap"
STAGE_A1_OS_RELEASE = "/usr/lib/os-release"
STAGE_A1_APPARMOR_ENABLED = "/sys/module/apparmor/parameters/enabled"
STAGE_A1_APPARMOR_USERNS_RESTRICTION = (
    "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"
)
STAGE_A1_PROFILE_SOURCE = (
    "/usr/share/apparmor/extra-profiles/bwrap-userns-restrict"
)
STAGE_A1_PROFILE_INSTALLED = "/etc/apparmor.d/bwrap-userns-restrict"
STAGE_A1_BWRAP_SMOKE_ARGV = (
    "/usr/bin/bwrap", "--unshare-user", "--unshare-net",
    "--ro-bind", "/", "/", "/bin/true",
)
STAGE_A1_PACKAGE_QUERY_ARGV = (
    "/usr/bin/dpkg-query", "--show",
    "--showformat=${db:Status-Status}\\t${Version}\\t${Architecture}\\n",
    "bubblewrap",
)
STAGE_A1_LOADED_PROFILES_ARGV = (
    "/usr/bin/sudo", "-n", "/usr/bin/cat",
    "/sys/kernel/security/apparmor/profiles",
)
STAGE_A1_CONTROLLER_ARGV = (
    ("/usr/bin/sudo", "-n", "/usr/bin/apt-get", "update"),
    (
        "/usr/bin/sudo", "-n", "/usr/bin/apt-get", "install",
        "--yes", "--no-install-recommends",
        "apparmor=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "apparmor-profiles=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "bubblewrap=" + APPROVED_BWRAP_PACKAGE_VERSION,
    ),
    (
        "/usr/bin/sudo", "-n", "/usr/bin/install",
        "--owner=root", "--group=root", "--mode=0644",
        STAGE_A1_PROFILE_SOURCE, STAGE_A1_PROFILE_INSTALLED,
    ),
    (
        "/usr/bin/sudo", "-n", "/usr/sbin/apparmor_parser", "--replace",
        STAGE_A1_PROFILE_INSTALLED,
    ),
    STAGE_A1_BWRAP_SMOKE_ARGV,
)
STAGE_A1_CONTROLLER_ARGV_SHA256 = (
    "0ab2466caf998d3e0d2ca8c76e4abc4d2205dff737e6809dff7d919d73b187dd"
)
STAGE_A1_REASON_CODES = (
    "none", "not-run", "unsupported-platform", "apparmor-not-enforcing",
    "package-drift", "profile-drift", "binary-drift",
    "observation-uncheckable", "nonzero-exit", "signal", "timeout",
    "output-overflow", "unexpected-output", "process-not-reaped",
)
STAGE_A1_PRECONDITION_FAILURE_CODES = (
    "unsupported-platform", "apparmor-not-enforcing", "package-drift",
    "profile-drift", "binary-drift",
)
STAGE_A1_SMOKE_FAILURE_CODES = (
    "nonzero-exit", "signal", "unexpected-output",
)
STAGE_A1_UNCHECKABLE_CODES = (
    "observation-uncheckable", "timeout", "output-overflow",
    "process-not-reaped",
)
MAX_MOUNTINFO_BYTES = 1_048_576
MAX_MOUNTINFO_LINES = 8_192
REVIEWED_GUEST_LOCAL_FS_TYPES = (
    "autofs", "binfmt_misc", "bpf", "btrfs", "cgroup", "cgroup2", "configfs",
    "debugfs", "devpts", "devtmpfs", "efivarfs", "erofs", "ext2", "ext3",
    "ext4", "f2fs", "fusectl", "hugetlbfs", "iso9660", "mqueue", "nsfs",
    "overlay", "proc", "pstore", "ramfs", "resctrl", "rootfs", "securityfs",
    "selinuxfs", "smackfs", "squashfs", "sysfs", "tmpfs", "tracefs", "vfat",
    "xfs",
)
PROVIDER_LIFECYCLE_PRE_LIVE = {
    "destroy_required": True,
    "destroy_requested": False,
    "destroy_completed": False,
    "profile_absence_readback": "not-run",
}
RUNTIME_LANE_KEYS = (
    "provider_isolation_status", "mount_boundary_status",
    "process_cleanup_status", "codex_sandbox_network_status",
    "shell_environment_status", "config_status", "auth_status",
)
RUNTIME_LANE_STATES = ("pass", "fail", "not-run", "UNCHECKABLE")
AUTH_STATES = ("signed-in-client", "api-key", "unavailable", "unknown")
WORKER_ARGV_STAGES = (
    "load-envelope", "load-static-role", "environment-contract",
    "build-argv", "argv-policy", "schema-binding", "filesystem-binding",
)
WORKER_ARGV_REASON_CODES = (
    "none", "not-run", "envelope-invalid", "static-role-invalid",
    "environment-invalid", "argv-build-failed", "argv-policy-rejected",
    "schema-binding-invalid", "filesystem-binding-invalid",
)
PROFILE_PROBE_FAILURES = {
    "runtime-capabilities": "capability-unavailable",
    "provider-input": "input-invalid",
    "runtime-layout": "layout-invalid",
    "client-evidence": "version-help-uncheckable",
    "provider-evidence": "observation-invalid",
    "profile-validation": "profile-invalid",
}
DOCTOR_REQUIRED_CATEGORIES = ("auth", "config", "runtime", "sandbox")
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


class ProfileProbeError(Exception):
    """A fixed-enum profile boundary failure with no private diagnostic text."""

    def __init__(self, stage: str, reason_code: str):
        if PROFILE_PROBE_FAILURES.get(stage) != reason_code:
            raise ContractError("runtime profile failure classification is invalid")
        self.stage = stage
        self.reason_code = reason_code
        super().__init__("bounded runtime profile failure")


PROFILE_BOUNDARY_EXCEPTIONS = (
    ProfileProbeError, ContractError, OSError, subprocess.SubprocessError, UnicodeError,
    ValueError, KeyError, TypeError, RecursionError,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_documented_memory_overrides(overrides: Mapping[str, Any]) -> None:
    """Reject legacy or non-disabling memory keys before any Codex process."""
    legacy = ("features.memory_tool", "features.memory_tool_use")
    if any(key in overrides for key in legacy):
        raise ContractError("legacy undocumented memory override is forbidden")
    for key in ("memories.generate_memories", "memories.use_memories"):
        if key not in overrides or overrides[key] is not False:
            raise ContractError("documented memory override must be present and false: " + key)


def runtime_configuration_intent() -> Dict[str, Any]:
    """Return stable adapter-authored intent, never effective-config proof.

    The digest deliberately excludes the private, per-run PATH/HOME/CODEX_HOME/
    TMPDIR values. Their required names and the non-private fixed values remain
    bound, while the exact runtime observation is a separate evidence lane.
    """
    validate_documented_memory_overrides(REQUIRED_OVERRIDES)
    static_configuration = {
        "approval_policy": "never",
        "model_reasoning_effort": "high",
        "shell_environment_policy": {
            "inherit": "none",
            "required_names": list(SHELL_ENVIRONMENT_NAMES),
            "fixed_values": {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"},
        },
        "overrides": dict(REQUIRED_OVERRIDES),
        "execpolicy": {
            "rules_path_relative_to_codex_home": REVIEWED_RULES_RELATIVE_PATH,
            "rules_profile_sha256": sha256_bytes(REVIEWED_RULES_BYTES),
        },
    }
    return {
        "schema": "t11-runtime-configuration-intent/v1",
        "authority": "adapter-authored",
        "effective_configuration_proven": False,
        "configuration_sha256": sha256_bytes(canonical_bytes(static_configuration)),
        "rules_profile_sha256": sha256_bytes(REVIEWED_RULES_BYTES),
        "dynamic_environment_values_excluded": list(DYNAMIC_ENVIRONMENT_NAMES),
    }


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


class ColimaRuntimeLayout(NamedTuple):
    root: Path
    home: Path
    tmp: Path
    work: Path
    binary: Path
    runtime_root_binding_sha256: str
    dedicated_codex_home_binding_sha256: str


def normalized_control_plane_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({
        key: child for key, child in value.items()
        if key != "normalized_control_plane_sha256"
    }))


def not_run_control_plane_evidence() -> Dict[str, Any]:
    return {
        "schema": "t11-colima-control-plane-evidence/v1",
        "authority": "owner-authored",
        "codex_authenticated_attestation": False,
        "status": "not-run",
        "pre_create_observed_at": None,
        "post_create_observed_at": None,
        "profile_name": "not-run",
        "colima_version": "not-run",
        "vm_backend": "not-run",
        "architecture": "not-run",
        "pre_create_profile_absent": False,
        "pre_create_runtime_data_absent": False,
        "fresh_instance": False,
        "existing_instance_reused": False,
        "existing_container_reused": False,
        "existing_volume_reused": False,
        "default_profile_reused": False,
        "activation_context_unchanged": False,
        "private_vm_disk": False,
        "repository_on_private_vm_disk": False,
        "runtime_root_on_private_vm_disk": False,
        "additional_disks": 0,
        "instance_identity_sha256": "0" * 64,
        "provider_configuration_sha256": "0" * 64,
        "normalized_control_plane_sha256": "0" * 64,
        "raw_paths_recorded": False,
    }


def validate_control_plane_evidence(value: Any, allow_not_run: bool = True) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("Colima control-plane evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "codex_authenticated_attestation", "status",
            "pre_create_observed_at", "post_create_observed_at", "profile_name",
            "colima_version", "vm_backend", "architecture", "pre_create_profile_absent",
            "pre_create_runtime_data_absent", "fresh_instance", "existing_instance_reused",
            "existing_container_reused", "existing_volume_reused", "default_profile_reused",
            "activation_context_unchanged", "private_vm_disk",
            "repository_on_private_vm_disk", "runtime_root_on_private_vm_disk",
            "additional_disks", "instance_identity_sha256", "provider_configuration_sha256",
            "normalized_control_plane_sha256", "raw_paths_recorded",
        ),
        "Colima control-plane evidence",
    )
    if value["schema"] != "t11-colima-control-plane-evidence/v1" or value["authority"] != "owner-authored" or value["codex_authenticated_attestation"] is not False:
        raise ContractError("Colima control-plane evidence identity is invalid")
    if value["status"] == "not-run":
        if not allow_not_run or value != not_run_control_plane_evidence():
            raise ContractError("not-run Colima control-plane evidence contains fabricated claims")
        return value
    if value["status"] != "pass":
        raise ContractError("owner-authored Colima control-plane input must be pass or not-run")
    for field in ("pre_create_observed_at", "post_create_observed_at"):
        if not isinstance(value[field], str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value[field]) is None:
            raise ContractError("Colima control-plane chronology is invalid")
    if value["colima_version"] != "0.10.1" or value["vm_backend"] != COLIMA_VM_BACKEND or value["architecture"] != COLIMA_ARCHITECTURE:
        raise ContractError("Colima control-plane version/backend/architecture drifted")
    if re.fullmatch(r"t11-e2e-[0-9a-f]{12}-01", str(value["profile_name"])) is None:
        raise ContractError("Colima control-plane profile name is invalid")
    expected_true = (
        "pre_create_profile_absent", "pre_create_runtime_data_absent", "fresh_instance",
        "activation_context_unchanged", "private_vm_disk", "repository_on_private_vm_disk",
        "runtime_root_on_private_vm_disk",
    )
    expected_false = (
        "existing_instance_reused", "existing_container_reused", "existing_volume_reused",
        "default_profile_reused", "raw_paths_recorded",
    )
    if any(value[field] is not True for field in expected_true) or any(value[field] is not False for field in expected_false) or value["additional_disks"] != 0:
        raise ContractError("Colima control-plane fresh/private/no-reuse boundary drifted")
    for field in ("instance_identity_sha256", "provider_configuration_sha256", "normalized_control_plane_sha256"):
        require_string(value[field], "Colima control-plane " + field, SHA256_RE)
        if value[field] == "0" * 64:
            raise ContractError("Colima control-plane digest cannot be a sentinel")
    if value["normalized_control_plane_sha256"] != normalized_control_plane_sha256(value):
        raise ContractError("Colima control-plane normalized digest drifted")
    pre = datetime.datetime.strptime(value["pre_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ")
    post = datetime.datetime.strptime(value["post_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ")
    if pre > post:
        raise ContractError("Colima control-plane chronology is reversed")
    validate_json_limits(value, {"json_depth": 4, "json_nodes": 64, "json_string_bytes": 256}, "Colima control-plane evidence")
    return value


def validate_colima_provider_input(value: Any) -> Dict[str, Any]:
    """Validate the closed owner-authored Option A input.

    Every dynamic value arrives through stdin.  No path, Task prompt, mount
    record, credential, or provider identity is accepted through argv.
    """
    if not isinstance(value, dict):
        raise ContractError("Colima provider input must be an object")
    exact_keys(value, ("schema", "authority", "provider", "control_plane", "repository", "client", "lifecycle"), "Colima provider input")
    if value["schema"] != COLIMA_PROVIDER_INPUT_SCHEMA or value["authority"] != "owner-authored":
        raise ContractError("Colima provider input identity is invalid")
    repository = value["repository"]
    if not isinstance(repository, dict):
        raise ContractError("Colima provider repository binding must be an object")
    exact_keys(repository, ("head", "tree"), "Colima provider repository binding")
    head = require_string(repository["head"], "Colima public head", OID_RE)
    tree = require_string(repository["tree"], "Colima public tree", OID_RE)
    if head == "0" * 40 or tree == "0" * 40:
        raise ContractError("Colima public repository binding cannot be a sentinel")
    provider = value["provider"]
    if not isinstance(provider, dict):
        raise ContractError("Colima provider record must be an object")
    exact_keys(
        provider,
        (
            "kind", "profile_name", "vm_backend", "architecture", "created_at",
            "provider_configuration_sha256", "effective_mount_inventory_sha256",
            "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
            "host_mount_count", "host_mount_classifications", "all_host_mounts_read_only",
            "ssh_agent_forwarding", "dot_ssh_public_key_loading", "user_ssh_config_modified",
        ),
        "Colima provider record",
    )
    if provider["kind"] != COLIMA_PROVIDER_KIND or provider["vm_backend"] != COLIMA_VM_BACKEND or provider["architecture"] != COLIMA_ARCHITECTURE:
        raise ContractError("Colima provider kind/backend/architecture drifted")
    expected_profile = "t11-e2e-{}-01".format(head[:12])
    if provider["profile_name"] != expected_profile:
        raise ContractError("Colima provider profile does not bind the exact public head")
    if not isinstance(provider["created_at"], str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", provider["created_at"]) is None:
        raise ContractError("Colima provider creation timestamp is invalid")
    for field in (
        "provider_configuration_sha256", "effective_mount_inventory_sha256",
        "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
    ):
        require_string(provider[field], "Colima provider " + field, SHA256_RE)
        if provider[field] == "0" * 64:
            raise ContractError("Colima provider digest cannot be a sentinel")
    if provider["host_mount_count"] != 1 or provider["host_mount_classifications"] != ["provider-internal-cache"] or provider["all_host_mounts_read_only"] is not True:
        raise ContractError("Colima provider host-mount allowlist is not the exact reviewed cache share")
    for field in ("ssh_agent_forwarding", "dot_ssh_public_key_loading", "user_ssh_config_modified"):
        if provider[field] is not False:
            raise ContractError("Colima provider SSH isolation drifted")
    client = value["client"]
    if not isinstance(client, dict):
        raise ContractError("Colima provider client binding must be an object")
    exact_keys(client, ("version_output", "approved_archive_sha256", "observed_archive_sha256", "extracted_binary_sha256"), "Colima provider client binding")
    if client["version_output"] != APPROVED_CODEX_VERSION:
        raise ContractError("Colima provider requires the exact approved stable Codex client")
    if client["approved_archive_sha256"] != APPROVED_CODEX_ARCHIVE_SHA256 or client["observed_archive_sha256"] != APPROVED_CODEX_ARCHIVE_SHA256:
        raise ContractError("Colima provider archive digest is not the approved exact digest")
    require_string(client["extracted_binary_sha256"], "Colima provider extracted binary digest", SHA256_RE)
    if client["extracted_binary_sha256"] == "0" * 64:
        raise ContractError("Colima provider extracted binary digest cannot be a sentinel")
    if value["lifecycle"] != PROVIDER_LIFECYCLE_PRE_LIVE:
        raise ContractError("Colima provider lifecycle is not the honest pre-live state")
    control_plane = validate_control_plane_evidence(value["control_plane"], allow_not_run=False)
    if (
        control_plane["profile_name"] != provider["profile_name"]
        or control_plane["vm_backend"] != provider["vm_backend"]
        or control_plane["architecture"] != provider["architecture"]
        or control_plane["provider_configuration_sha256"] != provider["provider_configuration_sha256"]
    ):
        raise ContractError("Colima provider and control-plane bindings differ")
    created = datetime.datetime.strptime(provider["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    pre = datetime.datetime.strptime(control_plane["pre_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ")
    post = datetime.datetime.strptime(control_plane["post_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ")
    if not pre <= created <= post:
        raise ContractError("Colima provider creation chronology drifted")
    validate_json_limits(value, {"json_depth": 8, "json_nodes": 128, "json_string_bytes": 256}, "Colima provider input")
    return value


def not_run_containment_provider_evidence() -> Dict[str, Any]:
    return {
        "schema": CONTAINMENT_PROVIDER_EVIDENCE_SCHEMA,
        "authority": "adapter/owner-authored",
        "codex_authenticated_attestation": False,
        "status": "not-run",
        "provider_kind": "not-run",
        "profile_name": "not-run",
        "vm_backend": "not-run",
        "architecture": "not-run",
        "native_architecture": False,
        "guest_os": "not-run",
        "guest_kernel": "not-run",
        "created_at": None,
        "provider_configuration_sha256": "0" * 64,
        "effective_mount_inventory_sha256": "0" * 64,
        "provider_cache_mount_sha256": "0" * 64,
        "provider_cache_guest_mountpoint_sha256": "0" * 64,
        "host_mount_count": 0,
        "host_mount_classifications": [],
        "all_host_mounts_read_only": False,
        "provider_cache_only": False,
        "host_sensitive_mounts_absent": False,
        "unapproved_mounts_absent": False,
        "ssh_agent_forwarding": False,
        "dot_ssh_public_key_loading": False,
        "user_ssh_config_modified": False,
        "vm_instance_identity_sha256": "0" * 64,
        "public_head": "0" * 40,
        "public_tree": "0" * 40,
        "repository_clean": False,
        "codex_version_output": "unavailable",
        "approved_archive_sha256": "0" * 64,
        "observed_archive_sha256": "0" * 64,
        "extracted_binary_sha256": "0" * 64,
        "runtime_root_binding_sha256": "0" * 64,
        "dedicated_codex_home_binding_sha256": "0" * 64,
        "control_plane": not_run_control_plane_evidence(),
        "lifecycle": {
            "destroy_required": False,
            "destroy_requested": False,
            "destroy_completed": False,
            "profile_absence_readback": "not-run",
        },
    }


def _stage_a1_smoke_argv_sha256() -> str:
    return sha256_bytes(canonical_bytes(list(STAGE_A1_BWRAP_SMOKE_ARGV)))


def not_run_stage_a1_prerequisite_evidence() -> Dict[str, Any]:
    """Return the exact historical/non-observation sentinel for Stage A.1."""
    return {
        "schema": "t11-bubblewrap-prerequisite-evidence/v1",
        "authority": "adapter/owner-authored",
        "status": "not-run",
        "reason_code": "not-run",
        "guest": {
            "distribution_id": "not-run",
            "distribution_version": "not-run",
            "distribution_codename": "not-run",
            "kernel": "not-run",
            "architecture": "not-run",
        },
        "apparmor": {
            "enabled": False,
            "unprivileged_userns_restriction": "not-run",
            "profile_required": False,
            "profile_source": "not-run",
            "source_sha256": "0" * 64,
            "installed_sha256": "0" * 64,
            "load_status": "not-run",
        },
        "bubblewrap": {
            "package_name": "not-run",
            "package_version": "not-run",
            "package_architecture": "not-run",
            "install_status": "not-run",
            "binary_sha256": "0" * 64,
            "version_output": "not-run",
            "help_sha256": "0" * 64,
        },
        "controller": {
            "argv_sha256": STAGE_A1_CONTROLLER_ARGV_SHA256,
            "shell": False,
            "model_invoked": False,
            "device_auth_performed": False,
            "legacy_landlock_enabled": False,
            "global_apparmor_userns_disabled": False,
        },
        "smoke": {
            "argv_sha256": _stage_a1_smoke_argv_sha256(),
            "status": "not-run",
            "reason_code": "not-run",
            "exit_code": None,
            "raw_stdout_recorded": False,
            "raw_stderr_recorded": False,
        },
    }


def validate_stage_a1_prerequisite_evidence(value: Any) -> Dict[str, Any]:
    """Validate only the closed, allowlisted Stage A.1 projection."""
    if not isinstance(value, dict):
        raise ContractError("Stage A.1 prerequisite evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "status", "reason_code", "guest",
            "apparmor", "bubblewrap", "controller", "smoke",
        ),
        "Stage A.1 prerequisite evidence",
    )
    if (
        value["schema"] != "t11-bubblewrap-prerequisite-evidence/v1"
        or value["authority"] != "adapter/owner-authored"
        or value["status"] not in ("pass", "fail", "not-run", "UNCHECKABLE")
        or value["reason_code"] not in STAGE_A1_REASON_CODES
    ):
        raise ContractError("Stage A.1 prerequisite identity/status is invalid")
    guest = value["guest"]
    if not isinstance(guest, dict):
        raise ContractError("Stage A.1 guest evidence must be an object")
    exact_keys(
        guest,
        (
            "distribution_id", "distribution_version",
            "distribution_codename", "kernel", "architecture",
        ),
        "Stage A.1 guest evidence",
    )
    for field in guest:
        if (
            not isinstance(guest[field], str)
            or not 1 <= len(guest[field]) <= 128
            or re.fullmatch(r"[0-9A-Za-z._+~-]+", guest[field]) is None
        ):
            raise ContractError("Stage A.1 guest field is invalid")
    apparmor = value["apparmor"]
    if not isinstance(apparmor, dict):
        raise ContractError("Stage A.1 AppArmor evidence must be an object")
    exact_keys(
        apparmor,
        (
            "enabled", "unprivileged_userns_restriction", "profile_required",
            "profile_source", "source_sha256", "installed_sha256",
            "load_status",
        ),
        "Stage A.1 AppArmor evidence",
    )
    for field in ("enabled", "profile_required"):
        require_bool(apparmor[field], "Stage A.1 AppArmor " + field)
    if apparmor["unprivileged_userns_restriction"] not in (
        "active", "inactive", "not-run", "UNCHECKABLE",
    ) or apparmor["load_status"] not in (
        "enforce", "not-loaded", "not-run", "UNCHECKABLE",
    ) or apparmor["profile_source"] not in (
        "ubuntu-noble-apparmor-profiles", "not-run",
    ):
        raise ContractError("Stage A.1 AppArmor state is invalid")
    for field in ("source_sha256", "installed_sha256"):
        require_string(apparmor[field], "Stage A.1 AppArmor digest", SHA256_RE)
    bubblewrap = value["bubblewrap"]
    if not isinstance(bubblewrap, dict):
        raise ContractError("Stage A.1 bubblewrap evidence must be an object")
    exact_keys(
        bubblewrap,
        (
            "package_name", "package_version", "package_architecture",
            "install_status", "binary_sha256", "version_output",
            "help_sha256",
        ),
        "Stage A.1 bubblewrap evidence",
    )
    for field in (
        "package_name", "package_version", "package_architecture",
        "install_status", "version_output",
    ):
        if (
            not isinstance(bubblewrap[field], str)
            or not 1 <= len(bubblewrap[field]) <= 128
            or PRIVATE_PATH_RE.search(bubblewrap[field])
        ):
            raise ContractError("Stage A.1 bubblewrap field is invalid")
    for field in ("binary_sha256", "help_sha256"):
        require_string(bubblewrap[field], "Stage A.1 bubblewrap digest", SHA256_RE)
    controller = value["controller"]
    if not isinstance(controller, dict):
        raise ContractError("Stage A.1 controller evidence must be an object")
    expected_controller = {
        "argv_sha256": STAGE_A1_CONTROLLER_ARGV_SHA256,
        "shell": False,
        "model_invoked": False,
        "device_auth_performed": False,
        "legacy_landlock_enabled": False,
        "global_apparmor_userns_disabled": False,
    }
    if controller != expected_controller:
        raise ContractError("Stage A.1 controller boundary drifted")
    smoke = value["smoke"]
    if not isinstance(smoke, dict):
        raise ContractError("Stage A.1 smoke evidence must be an object")
    exact_keys(
        smoke,
        (
            "argv_sha256", "status", "reason_code", "exit_code",
            "raw_stdout_recorded", "raw_stderr_recorded",
        ),
        "Stage A.1 smoke evidence",
    )
    if (
        smoke["argv_sha256"] != _stage_a1_smoke_argv_sha256()
        or smoke["status"] not in ("pass", "fail", "not-run", "UNCHECKABLE")
        or smoke["reason_code"] not in STAGE_A1_REASON_CODES
        or smoke["raw_stdout_recorded"] is not False
        or smoke["raw_stderr_recorded"] is not False
        or (
            smoke["exit_code"] is not None
            and (
                type(smoke["exit_code"]) is not int
                or not 0 <= smoke["exit_code"] <= 255
            )
        )
    ):
        raise ContractError("Stage A.1 smoke evidence is invalid")
    if smoke["status"] == "pass" and (
        smoke["reason_code"] != "none" or smoke["exit_code"] != 0
    ):
        raise ContractError("passing Stage A.1 smoke evidence is inconsistent")
    if smoke["status"] == "not-run" and (
        smoke["reason_code"] != "not-run" or smoke["exit_code"] is not None
    ):
        raise ContractError("not-run Stage A.1 smoke evidence is inconsistent")
    if smoke["status"] == "fail":
        if smoke["reason_code"] not in STAGE_A1_SMOKE_FAILURE_CODES:
            raise ContractError("failed Stage A.1 smoke reason is invalid")
        if (
            smoke["reason_code"] == "nonzero-exit"
            and (
                type(smoke["exit_code"]) is not int
                or not 1 <= smoke["exit_code"] <= 255
            )
        ) or (
            smoke["reason_code"] == "signal" and smoke["exit_code"] is not None
        ) or (
            smoke["reason_code"] == "unexpected-output"
            and smoke["exit_code"] != 0
        ):
            raise ContractError("failed Stage A.1 smoke exit classification is invalid")
    if smoke["status"] == "UNCHECKABLE" and (
        smoke["reason_code"] not in STAGE_A1_UNCHECKABLE_CODES
        or smoke["exit_code"] is not None
    ):
        raise ContractError("uncheckable Stage A.1 smoke evidence is inconsistent")
    if value["status"] == "not-run":
        if value != not_run_stage_a1_prerequisite_evidence():
            raise ContractError("Stage A.1 not-run sentinel drifted")
        return value
    if value["status"] == "pass":
        expected_guest = {
            "distribution_id": "ubuntu", "distribution_version": "24.04",
            "distribution_codename": "noble", "architecture": "aarch64",
        }
        for field, expected in expected_guest.items():
            if guest[field] != expected:
                raise ContractError("passing Stage A.1 guest boundary drifted")
        if re.fullmatch(r"[0-9][0-9A-Za-z._+~-]{0,127}", guest["kernel"]) is None:
            raise ContractError("passing Stage A.1 kernel evidence is missing or invalid")
        expected_apparmor = {
            "enabled": True,
            "unprivileged_userns_restriction": "active",
            "profile_required": True,
            "profile_source": "ubuntu-noble-apparmor-profiles",
            "source_sha256": APPROVED_BWRAP_PROFILE_SHA256,
            "installed_sha256": APPROVED_BWRAP_PROFILE_SHA256,
            "load_status": "enforce",
        }
        if apparmor != expected_apparmor:
            raise ContractError("passing Stage A.1 AppArmor boundary drifted")
        if bubblewrap != {
            "package_name": "bubblewrap",
            "package_version": APPROVED_BWRAP_PACKAGE_VERSION,
            "package_architecture": "arm64",
            "install_status": "installed",
            "binary_sha256": APPROVED_BWRAP_BINARY_SHA256,
            "version_output": APPROVED_BWRAP_VERSION_OUTPUT,
            "help_sha256": bubblewrap["help_sha256"],
        } or bubblewrap["help_sha256"] == "0" * 64:
            raise ContractError("passing Stage A.1 bubblewrap boundary drifted")
        if value["reason_code"] != "none" or smoke["status"] != "pass":
            raise ContractError("passing Stage A.1 evidence has a failure reason")
    elif value["status"] == "fail":
        if value["reason_code"] in STAGE_A1_PRECONDITION_FAILURE_CODES:
            if smoke["status"] != "not-run":
                raise ContractError("failed Stage A.1 precondition contains a smoke claim")
        elif value["reason_code"] in STAGE_A1_SMOKE_FAILURE_CODES:
            if (
                smoke["status"] != "fail"
                or smoke["reason_code"] != value["reason_code"]
            ):
                raise ContractError("failed Stage A.1 outcome disagrees with smoke evidence")
        else:
            raise ContractError("failed Stage A.1 reason is invalid")
    elif value["status"] == "UNCHECKABLE":
        if (
            value["reason_code"] not in STAGE_A1_UNCHECKABLE_CODES
            or smoke["status"] != "UNCHECKABLE"
            or smoke["reason_code"] != value["reason_code"]
        ):
            raise ContractError("uncheckable Stage A.1 outcome is inconsistent")
    validate_json_limits(
        value,
        {"json_depth": 8, "json_nodes": 96, "json_string_bytes": 256},
        "Stage A.1 prerequisite evidence",
    )
    return value


def classify_stage_a1_bwrap_smoke(result: "ProcessResult") -> Dict[str, Any]:
    """Map a direct non-root smoke result to safe fixed codes only."""
    if result.timed_out:
        status, reason = "UNCHECKABLE", "timeout"
    elif result.stdout_overflow or result.stderr_overflow:
        status, reason = "UNCHECKABLE", "output-overflow"
    elif not result.reaped:
        status, reason = "UNCHECKABLE", "process-not-reaped"
    elif result.signal_number is not None:
        status, reason = "fail", "signal"
    elif result.exit_code != 0:
        status, reason = "fail", "nonzero-exit"
    elif result.stdout or result.stderr_size:
        status, reason = "fail", "unexpected-output"
    else:
        status, reason = "pass", "none"
    return {
        "argv_sha256": _stage_a1_smoke_argv_sha256(),
        "status": status,
        "reason_code": reason,
        "exit_code": result.exit_code if status in ("pass", "fail") else None,
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def _parse_stage_a1_os_release(data: bytes) -> Dict[str, str]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ContractError("Stage A.1 distribution data is invalid")
    values: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ContractError("Stage A.1 distribution data is malformed")
        key, raw = line.split("=", 1)
        if key not in ("ID", "VERSION_ID", "VERSION_CODENAME"):
            continue
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        if re.fullmatch(r"[0-9A-Za-z._+~-]+", raw) is None:
            raise ContractError("Stage A.1 distribution value is malformed")
        if key in values:
            raise ContractError("Stage A.1 distribution key is duplicated")
        values[key] = raw
    if set(values) != {"ID", "VERSION_ID", "VERSION_CODENAME"}:
        raise ContractError("Stage A.1 distribution fields are incomplete")
    return values


def _stage_a1_profile_load_status(result: "ProcessResult") -> str:
    if (
        result.exit_code != 0 or result.timed_out or result.stdout_overflow
        or result.stderr_overflow or not result.reaped
    ):
        return "UNCHECKABLE"
    try:
        lines = set(result.stdout.decode("utf-8", errors="strict").splitlines())
    except UnicodeDecodeError:
        return "UNCHECKABLE"
    required = {"bwrap (enforce)", "bwrap//&unpriv_bwrap (enforce)"}
    return "enforce" if required.issubset(lines) else "not-loaded"


def observe_stage_a1_prerequisite(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """Re-observe the installed Noble prerequisite and run one direct smoke."""
    fallback = not_run_stage_a1_prerequisite_evidence()
    fallback["status"] = "UNCHECKABLE"
    fallback["reason_code"] = "observation-uncheckable"
    fallback["smoke"]["status"] = "UNCHECKABLE"
    fallback["smoke"]["reason_code"] = "observation-uncheckable"
    try:
        release = _parse_stage_a1_os_release(
            read_bounded_regular(STAGE_A1_OS_RELEASE, 16_384)
        )
        uname = os.uname()
        apparmor_enabled = read_bounded_regular(
            STAGE_A1_APPARMOR_ENABLED, 16
        ).strip() == b"Y"
        restriction = read_bounded_regular(
            STAGE_A1_APPARMOR_USERNS_RESTRICTION, 16
        ).strip()
        restriction_status = (
            "active" if restriction == b"1"
            else "inactive" if restriction == b"0"
            else "UNCHECKABLE"
        )
        source_sha = hash_regular_file(STAGE_A1_PROFILE_SOURCE, 1_048_576)
        installed_sha = hash_regular_file(STAGE_A1_PROFILE_INSTALLED, 1_048_576)
        package_result = bounded_capture(
            STAGE_A1_PACKAGE_QUERY_ARGV, root, env,
            timeout=15, stdout_limit=1024, stderr_limit=1024,
        )
        if (
            package_result.exit_code != 0 or package_result.timed_out
            or package_result.stdout_overflow or package_result.stderr_overflow
            or not package_result.reaped
        ):
            return fallback
        package_match = re.fullmatch(
            rb"install ok installed\t([^\t\n]{1,128})\t([^\t\n]{1,32})\n",
            package_result.stdout,
        )
        if package_match is None:
            return fallback
        package_version = package_match.group(1).decode("ascii", errors="strict")
        package_architecture = package_match.group(2).decode("ascii", errors="strict")
        binary_sha = hash_regular_file(STAGE_A1_BWRAP_BINARY)
        version_result = bounded_capture(
            (str(STAGE_A1_BWRAP_BINARY), "--version"), root, env,
            timeout=15, stdout_limit=256, stderr_limit=1024,
        )
        help_result = bounded_capture(
            (str(STAGE_A1_BWRAP_BINARY), "--help"), root, env,
            timeout=15, stdout_limit=262_144, stderr_limit=1024,
        )
        if any(
            result.exit_code != 0 or result.timed_out
            or result.stdout_overflow or result.stderr_overflow or not result.reaped
            for result in (version_result, help_result)
        ):
            return fallback
        try:
            version_output = version_result.stdout.decode(
                "utf-8", errors="strict"
            ).strip()
        except UnicodeDecodeError:
            return fallback
        load_status = _stage_a1_profile_load_status(
            bounded_capture(
                STAGE_A1_LOADED_PROFILES_ARGV, root, env,
                timeout=15, stdout_limit=262_144, stderr_limit=1024,
            )
        )
    except (ContractError, OSError, subprocess.SubprocessError, UnicodeError):
        return fallback
    guest = {
        "distribution_id": release["ID"],
        "distribution_version": release["VERSION_ID"],
        "distribution_codename": release["VERSION_CODENAME"],
        "kernel": uname.release if re.fullmatch(
            r"[0-9A-Za-z._+~-]{1,128}", uname.release
        ) else "invalid",
        "architecture": uname.machine,
    }
    apparmor = {
        "enabled": apparmor_enabled,
        "unprivileged_userns_restriction": restriction_status,
        "profile_required": True,
        "profile_source": "ubuntu-noble-apparmor-profiles",
        "source_sha256": source_sha,
        "installed_sha256": installed_sha,
        "load_status": load_status,
    }
    bubblewrap = {
        "package_name": "bubblewrap",
        "package_version": package_version,
        "package_architecture": package_architecture,
        "install_status": "installed",
        "binary_sha256": binary_sha,
        "version_output": version_output,
        "help_sha256": sha256_bytes(help_result.stdout),
    }
    preconditions = (
        guest["distribution_id"] == "ubuntu"
        and guest["distribution_version"] == "24.04"
        and guest["distribution_codename"] == "noble"
        and uname.sysname == "Linux" and guest["architecture"] == "aarch64"
        and apparmor["enabled"]
        and apparmor["unprivileged_userns_restriction"] == "active"
        and source_sha == APPROVED_BWRAP_PROFILE_SHA256
        and installed_sha == APPROVED_BWRAP_PROFILE_SHA256
        and load_status == "enforce"
        and package_version == APPROVED_BWRAP_PACKAGE_VERSION
        and package_architecture == "arm64"
        and binary_sha == APPROVED_BWRAP_BINARY_SHA256
        and version_output == APPROVED_BWRAP_VERSION_OUTPUT
    )
    smoke = not_run_stage_a1_prerequisite_evidence()["smoke"]
    if preconditions:
        try:
            smoke = classify_stage_a1_bwrap_smoke(
                bounded_capture(
                    STAGE_A1_BWRAP_SMOKE_ARGV, root, env,
                    timeout=15, stdout_limit=1024, stderr_limit=1024,
                )
            )
        except (ContractError, OSError, subprocess.SubprocessError):
            smoke = dict(smoke)
            smoke["status"] = "UNCHECKABLE"
            smoke["reason_code"] = "observation-uncheckable"
    if not (
        guest["distribution_id"] == "ubuntu"
        and guest["distribution_version"] == "24.04"
        and guest["distribution_codename"] == "noble"
        and uname.sysname == "Linux" and guest["architecture"] == "aarch64"
    ):
        status, reason = "fail", "unsupported-platform"
    elif not (
        apparmor["enabled"]
        and apparmor["unprivileged_userns_restriction"] == "active"
    ):
        status, reason = "fail", "apparmor-not-enforcing"
    elif package_version != APPROVED_BWRAP_PACKAGE_VERSION or package_architecture != "arm64":
        status, reason = "fail", "package-drift"
    elif (
        source_sha != APPROVED_BWRAP_PROFILE_SHA256
        or installed_sha != APPROVED_BWRAP_PROFILE_SHA256
        or load_status != "enforce"
    ):
        status, reason = "fail", "profile-drift"
    elif binary_sha != APPROVED_BWRAP_BINARY_SHA256 or version_output != APPROVED_BWRAP_VERSION_OUTPUT:
        status, reason = "fail", "binary-drift"
    else:
        status, reason = smoke["status"], smoke["reason_code"]
    evidence = {
        "schema": "t11-bubblewrap-prerequisite-evidence/v1",
        "authority": "adapter/owner-authored",
        "status": status,
        "reason_code": reason,
        "guest": guest,
        "apparmor": apparmor,
        "bubblewrap": bubblewrap,
        "controller": not_run_stage_a1_prerequisite_evidence()["controller"],
        "smoke": smoke,
    }
    return validate_stage_a1_prerequisite_evidence(evidence)


def _decode_mountinfo_field(value: bytes) -> bytes:
    replacements = {b"\\040": b" ", b"\\011": b"\t", b"\\012": b"\n", b"\\134": b"\\"}
    for encoded, decoded in replacements.items():
        value = value.replace(encoded, decoded)
    return value


def inspect_colima_mount_inventory(data: bytes, provider: Mapping[str, Any]) -> Dict[str, Any]:
    """Return only allowlisted digests/booleans, never raw mount paths."""
    if len(data) > MAX_MOUNTINFO_BYTES or b"\0" in data:
        raise ContractError("mount inventory exceeds its bounded representation")
    lines = data.splitlines()
    if not lines or len(lines) > MAX_MOUNTINFO_LINES:
        raise ContractError("mount inventory line count is invalid")
    shared: List[Tuple[bytes, bytes, bool, str]] = []
    malformed = False
    for line in lines:
        fields = line.split(b" ")
        try:
            separator = fields.index(b"-")
        except ValueError:
            malformed = True
            continue
        if separator < 6 or len(fields) < separator + 4:
            malformed = True
            continue
        try:
            fs_type = fields[separator + 1].decode("ascii", errors="strict").lower()
        except UnicodeDecodeError:
            malformed = True
            continue
        mountpoint = _decode_mountinfo_field(fields[4])
        source = _decode_mountinfo_field(fields[separator + 2])
        lowered_mountpoint = mountpoint.lower()
        lowered_source = source.lower()
        path_indicator = any(
            token in lowered_mountpoint or token in lowered_source
            for token in (
                b"/users/", b"/volumes/", b"/private/", b"/var/folders/",
                b"/mnt/host", b"/run/host", b"/.ssh", b"/.codex",
                b"/auth.json", b"docker.sock", b"agentic-dev-kit",
            )
        )
        # Positive policy: every mount is either a reviewed guest-local/kernel
        # filesystem or the one exact provider cache virtiofs record. Unknown
        # types fail closed instead of depending on an incomplete blacklist.
        provider_or_unapproved = (
            fs_type == "virtiofs"
            or fs_type not in REVIEWED_GUEST_LOCAL_FS_TYPES
            or path_indicator
            or source.startswith(b"//")
            or b":/" in source
        )
        if provider_or_unapproved:
            options = set(fields[5].split(b","))
            shared.append((line, mountpoint, b"ro" in options and b"rw" not in options, fs_type))
    inventory_sha256 = sha256_bytes(data)
    one = shared[0] if len(shared) == 1 else None
    cache_line_sha256 = sha256_bytes(one[0] + b"\n") if one else "0" * 64
    cache_mountpoint_sha256 = sha256_bytes(one[1] + b"\n") if one else "0" * 64
    cache_path_ok = False
    if one is not None:
        mountpoint = one[1]
        lowered = mountpoint.lower()
        expected_prefix = (
            "/Users/Shared/t11-colima-{}.".format(provider["profile_name"])
        ).encode("ascii")
        expected_suffix = b"/xdg-cache/colima"
        middle = mountpoint[len(expected_prefix):-len(expected_suffix)] if (
            mountpoint.startswith(expected_prefix) and mountpoint.endswith(expected_suffix)
        ) else b""
        cache_path_ok = (
            len(middle) == 8
            and re.fullmatch(rb"[0-9A-Za-z]{8}", middle) is not None
            and one[3] == "virtiofs"
            and not any(token in lowered for token in (
                b"agentic-dev-kit", b"/.codex", b"/auth.json", b"/.ssh",
                b"docker.sock", b"/private/", b"/var/folders/",
            ))
        )
    cache_only = (
        not malformed
        and len(shared) == 1
        and cache_path_ok
        and cache_line_sha256 == provider["provider_cache_mount_sha256"]
        and cache_mountpoint_sha256 == provider["provider_cache_guest_mountpoint_sha256"]
    )
    read_only = bool(one is not None and one[2])
    inventory_matches = inventory_sha256 == provider["effective_mount_inventory_sha256"]
    status = "pass" if cache_only and read_only and inventory_matches else "fail"
    return {
        "status": status,
        "effective_mount_inventory_sha256": inventory_sha256,
        "provider_cache_mount_sha256": cache_line_sha256,
        "provider_cache_guest_mountpoint_sha256": cache_mountpoint_sha256,
        "host_mount_count": len(shared),
        "host_mount_classifications": ["provider-internal-cache"] if cache_only else [],
        "all_host_mounts_read_only": read_only and len(shared) == 1,
        "provider_cache_only": cache_only,
        "host_sensitive_mounts_absent": cache_path_ok and len(shared) == 1,
        "unapproved_mounts_absent": cache_only and read_only and len(shared) == 1,
    }


def _directory_binding_sha256(info: os.stat_result, label: str) -> str:
    return sha256_bytes(canonical_bytes({
        "label": label,
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": stat.S_IMODE(info.st_mode),
        "owner": info.st_uid,
    }))


def _open_absolute_directory_nofollow(path: Path) -> Tuple[int, os.stat_result]:
    if not path.is_absolute() or "\0" in str(path):
        raise ContractError("private runtime root must be an absolute directory")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            if component in ("", ".", ".."):
                raise ContractError("private runtime root has an unsafe component")
            named = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(named.st_mode):
                raise ContractError("private runtime root component is a link or non-directory")
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                os.close(child)
                raise ContractError("private runtime root namespace changed")
            os.close(descriptor)
            descriptor = child
        return descriptor, os.fstat(descriptor)
    except Exception:
        os.close(descriptor)
        raise


def _ensure_private_child(parent_descriptor: int, parent: Path, name: str) -> Tuple[Path, os.stat_result, int]:
    if os.mkdir not in getattr(os, "supports_dir_fd", set()):
        raise ContractError("private runtime mkdir(dir_fd) capability is unavailable")
    path = parent / name
    try:
        os.mkdir(name, 0o700, dir_fd=parent_descriptor)
    except FileExistsError:
        pass
    info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise ContractError("private runtime child is a link or non-directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ContractError("private runtime child owner or mode drifted")
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_descriptor)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
        os.close(descriptor)
        raise ContractError("private runtime child namespace changed")
    return path, opened, descriptor


def prepare_colima_runtime_layout() -> ColimaRuntimeLayout:
    raw_root = os.environ.get(COLIMA_RUNTIME_ROOT_ENV)
    if not isinstance(raw_root, str) or not raw_root:
        raise ContractError("private Colima runtime root environment binding is unavailable")
    root = Path(raw_root)
    descriptor, root_info = _open_absolute_directory_nofollow(root)
    opened_children: List[int] = []
    try:
        if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
            raise ContractError("private Colima runtime root owner or mode drifted")
        home, _home_info, home_descriptor = _ensure_private_child(descriptor, root, "home")
        opened_children.append(home_descriptor)
        tmp, _tmp_info, tmp_descriptor = _ensure_private_child(descriptor, root, "tmp")
        opened_children.append(tmp_descriptor)
        work, _work_info, work_descriptor = _ensure_private_child(descriptor, root, "work")
        opened_children.append(work_descriptor)
        bin_dir, _bin_info, bin_descriptor = _ensure_private_child(descriptor, root, "bin")
        opened_children.append(bin_descriptor)
        _codex_home, codex_info, codex_descriptor = _ensure_private_child(home_descriptor, home, ".codex")
        opened_children.append(codex_descriptor)
        root_after = os.stat(str(root), follow_symlinks=False)
        opened_root_after = os.fstat(descriptor)
        if (
            root_after.st_dev, root_after.st_ino,
            opened_root_after.st_dev, opened_root_after.st_ino,
        ) != (
            root_info.st_dev, root_info.st_ino,
            root_info.st_dev, root_info.st_ino,
        ):
            raise ContractError("private Colima runtime root namespace changed")
        return ColimaRuntimeLayout(
            root=root,
            home=home,
            tmp=tmp,
            work=work,
            binary=bin_dir / "codex",
            runtime_root_binding_sha256=_directory_binding_sha256(root_info, "runtime-root"),
            dedicated_codex_home_binding_sha256=_directory_binding_sha256(codex_info, "codex-home"),
        )
    finally:
        for child_descriptor in reversed(opened_children):
            os.close(child_descriptor)
        os.close(descriptor)


def create_live_attempt_claim(
    layout: ColimaRuntimeLayout,
    envelope: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> str:
    """Consume the VM-local T11 live actuation exactly once.

    The claim is never removed or rewritten.  A crash or failed worker still
    leaves it present, so the disposable VM must be destroyed before another
    live attempt can be authorized.
    """
    attempt_id = require_string(envelope.get("attempt_id"), "live claim attempt", ATTEMPT_RE)
    harness = envelope.get("harness")
    if not isinstance(harness, dict):
        raise ContractError("live claim harness binding is unavailable")
    exact_keys(harness, ("commit", "tree"), "live claim harness")
    public_head = require_string(harness["commit"], "live claim public head", OID_RE)
    public_tree = require_string(harness["tree"], "live claim public tree", OID_RE)
    try:
        containment = profile["evidence"]["containment_provider"]
    except (KeyError, TypeError):
        raise ContractError("live claim containment binding is unavailable")
    if (
        not isinstance(containment, dict)
        or containment.get("status") != "pass"
        or containment.get("public_head") != public_head
        or containment.get("public_tree") != public_tree
    ):
        raise ContractError("live claim provider/public binding drifted")
    provider_profile_name = require_string(
        containment.get("profile_name"), "live claim provider profile",
    )
    if re.fullmatch(r"t11-e2e-[0-9a-f]{12}-01", provider_profile_name) is None:
        raise ContractError("live claim provider profile is invalid")
    vm_instance_identity_sha256 = require_string(
        containment.get("vm_instance_identity_sha256"),
        "live claim VM identity", SHA256_RE,
    )
    control_plane = containment.get("control_plane")
    if not isinstance(control_plane, dict) or control_plane.get("status") != "pass":
        raise ContractError("live claim control-plane binding is unavailable")
    control_plane_sha256 = require_string(
        control_plane.get("normalized_control_plane_sha256"),
        "live claim control-plane digest", SHA256_RE,
    )
    if (
        vm_instance_identity_sha256 == "0" * 64
        or control_plane_sha256 == "0" * 64
        or control_plane.get("instance_identity_sha256") != vm_instance_identity_sha256
        or control_plane.get("profile_name") != provider_profile_name
    ):
        raise ContractError("live claim provider/control-plane binding drifted")
    payload = {
        "schema": "t11-live-attempt-claim/v1",
        "attempt_id": attempt_id,
        "public_head": public_head,
        "public_tree": public_tree,
        "provider_profile_name": provider_profile_name,
        "vm_instance_identity_sha256": vm_instance_identity_sha256,
        "control_plane_sha256": control_plane_sha256,
    }
    claim_sha256 = sha256_bytes(canonical_bytes(payload))
    record = {**payload, "canonical_sha256": claim_sha256}
    data = canonical_bytes(record)
    root_descriptor, root_info = _open_absolute_directory_nofollow(layout.root)
    claim_descriptor: Optional[int] = None
    claim_created = False
    try:
        if (
            root_info.st_uid != os.getuid()
            or stat.S_IMODE(root_info.st_mode) != 0o700
            or _directory_binding_sha256(root_info, "runtime-root") != layout.runtime_root_binding_sha256
        ):
            raise ContractError("the VM-local live-attempt root binding drifted")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            claim_descriptor = os.open(
                LIVE_ATTEMPT_CLAIM_NAME, flags, 0o600, dir_fd=root_descriptor,
            )
            claim_created = True
        except FileExistsError:
            raise ContractError("the disposable VM live attempt is already consumed")
        except OSError:
            raise ContractError("the VM-local live-attempt claim cannot be created safely")
        os.fchmod(claim_descriptor, 0o600)
        opened = os.fstat(claim_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or opened.st_size != 0
        ):
            raise ContractError("the VM-local live-attempt claim mode/binding is invalid")
        offset = 0
        while offset < len(data):
            written = os.write(claim_descriptor, data[offset:])
            if written <= 0:
                raise ContractError("the VM-local live-attempt claim write did not progress")
            offset += written
        os.fsync(claim_descriptor)
        after_write = os.fstat(claim_descriptor)
        if (
            after_write.st_dev, after_write.st_ino, after_write.st_size,
            stat.S_IMODE(after_write.st_mode), after_write.st_uid, after_write.st_nlink,
        ) != (
            opened.st_dev, opened.st_ino, len(data), 0o600, os.getuid(), 1,
        ):
            raise ContractError("the VM-local live-attempt claim changed while writing")
        os.lseek(claim_descriptor, 0, os.SEEK_SET)
        observed = bytearray()
        while len(observed) <= len(data):
            chunk = os.read(claim_descriptor, min(4096, len(data) + 1 - len(observed)))
            if not chunk:
                break
            observed.extend(chunk)
        if bytes(observed) != data:
            raise ContractError("the VM-local live-attempt claim bytes are not exact")
        named = os.stat(LIVE_ATTEMPT_CLAIM_NAME, dir_fd=root_descriptor, follow_symlinks=False)
        if (
            named.st_dev, named.st_ino, named.st_size, stat.S_IMODE(named.st_mode),
            named.st_uid, named.st_nlink,
        ) != (
            opened.st_dev, opened.st_ino, len(data), 0o600, os.getuid(), 1,
        ):
            raise ContractError("the VM-local live-attempt claim namespace changed")
        os.fsync(root_descriptor)
        named_after_fsync = os.stat(
            LIVE_ATTEMPT_CLAIM_NAME, dir_fd=root_descriptor, follow_symlinks=False,
        )
        root_named = os.stat(str(layout.root), follow_symlinks=False)
        if (
            named_after_fsync.st_dev, named_after_fsync.st_ino,
            named_after_fsync.st_size, stat.S_IMODE(named_after_fsync.st_mode),
            root_named.st_dev, root_named.st_ino,
        ) != (
            opened.st_dev, opened.st_ino, len(data), 0o600,
            root_info.st_dev, root_info.st_ino,
        ):
            raise ContractError("the VM-local live-attempt claim durability binding drifted")
        return claim_sha256
    except ContractError:
        # Never unlink a claim after O_EXCL succeeds: a failed durability or
        # binding proof consumes the live actuation and therefore blocks retry.
        raise
    except OSError:
        if claim_created:
            raise ContractError("the VM-local live-attempt claim durability is uncheckable")
        raise ContractError("the VM-local live-attempt claim is uncheckable")
    finally:
        if claim_descriptor is not None:
            os.close(claim_descriptor)
        os.close(root_descriptor)


def run_claimed_live_worker(
    layout: ColimaRuntimeLayout,
    envelope: Mapping[str, Any],
    profile: Mapping[str, Any],
    worker_argv: Sequence[str],
    target_root: Path,
    environment: Mapping[str, str],
    prompt: bytes,
) -> ProcessResult:
    if not worker_argv or any(not isinstance(item, str) or "\0" in item for item in worker_argv):
        raise ContractError("live worker argv is invalid before claim")
    validate_runtime_argv_policy(worker_argv, require_memory_overrides=True)
    if len(prompt) > MAX_STDIN_BYTES:
        raise ContractError("live worker stdin exceeds its limit before claim")
    if any(SECRET_NAME_RE.search(name) for name in environment):
        raise ContractError("live worker environment is unsafe before claim")
    target_descriptor, _target_binding = bound_directory(target_root)
    os.close(target_descriptor)
    create_live_attempt_claim(layout, envelope, profile)
    return run_bounded_process(
        worker_argv,
        target_root,
        environment,
        prompt,
        envelope["limits"]["worker_timeout_seconds"],
        envelope["limits"]["stdout_bytes"],
        envelope["limits"]["stderr_bytes"],
        2,
    )


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


def validate_containment_provider_evidence(value: Any, allow_fixture: bool = False) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("containment provider evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "codex_authenticated_attestation", "status",
            "provider_kind", "profile_name", "vm_backend", "architecture", "native_architecture",
            "guest_os", "guest_kernel", "created_at", "provider_configuration_sha256",
            "effective_mount_inventory_sha256", "provider_cache_mount_sha256",
            "provider_cache_guest_mountpoint_sha256", "host_mount_count",
            "host_mount_classifications", "all_host_mounts_read_only", "provider_cache_only",
            "host_sensitive_mounts_absent", "unapproved_mounts_absent", "ssh_agent_forwarding",
            "dot_ssh_public_key_loading", "user_ssh_config_modified", "vm_instance_identity_sha256",
            "public_head", "public_tree", "repository_clean", "codex_version_output",
            "approved_archive_sha256", "observed_archive_sha256", "extracted_binary_sha256",
            "runtime_root_binding_sha256", "dedicated_codex_home_binding_sha256",
            "control_plane", "lifecycle",
        ),
        "containment provider evidence",
    )
    if value["schema"] != CONTAINMENT_PROVIDER_EVIDENCE_SCHEMA or value["authority"] != "adapter/owner-authored" or value["codex_authenticated_attestation"] is not False:
        raise ContractError("containment evidence authority is invalid")
    if value["status"] not in ("pass", "fail", "not-run", "UNCHECKABLE"):
        raise ContractError("containment provider status is invalid")
    for field in (
        "provider_configuration_sha256", "effective_mount_inventory_sha256",
        "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
        "vm_instance_identity_sha256", "approved_archive_sha256", "observed_archive_sha256",
        "extracted_binary_sha256", "runtime_root_binding_sha256",
        "dedicated_codex_home_binding_sha256",
    ):
        require_string(value[field], "containment provider " + field, SHA256_RE)
    require_string(value["public_head"], "containment provider public head", OID_RE)
    require_string(value["public_tree"], "containment provider public tree", OID_RE)
    if type(value["host_mount_count"]) is not int or not 0 <= value["host_mount_count"] <= 32:
        raise ContractError("containment provider host mount count is invalid")
    if not isinstance(value["host_mount_classifications"], list) or any(not isinstance(item, str) for item in value["host_mount_classifications"]):
        raise ContractError("containment provider host mount classifications are invalid")
    for field in (
        "native_architecture", "all_host_mounts_read_only", "provider_cache_only",
        "host_sensitive_mounts_absent", "unapproved_mounts_absent", "ssh_agent_forwarding",
        "dot_ssh_public_key_loading", "user_ssh_config_modified", "repository_clean",
    ):
        require_bool(value[field], "containment provider " + field)
    lifecycle = value["lifecycle"]
    if not isinstance(lifecycle, dict):
        raise ContractError("containment lifecycle must be an object")
    exact_keys(lifecycle, ("destroy_required", "destroy_requested", "destroy_completed", "profile_absence_readback"), "containment lifecycle")
    for field in ("destroy_required", "destroy_requested", "destroy_completed"):
        require_bool(lifecycle[field], "containment lifecycle " + field)
    if lifecycle["profile_absence_readback"] not in ("not-run", "absent", "present", "UNKNOWN", "UNCHECKABLE"):
        raise ContractError("containment lifecycle absence state is invalid")
    if value["status"] == "not-run":
        expected = not_run_containment_provider_evidence()
        if value != expected:
            raise ContractError("not-run containment evidence contains fabricated provider facts")
        return value
    control_plane = validate_control_plane_evidence(value["control_plane"], allow_not_run=False)
    if value["provider_kind"] != COLIMA_PROVIDER_KIND or value["vm_backend"] != COLIMA_VM_BACKEND or value["architecture"] != COLIMA_ARCHITECTURE:
        raise ContractError("containment provider identity drifted")
    if not isinstance(value["created_at"], str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value["created_at"]) is None:
        raise ContractError("containment provider creation timestamp is invalid")
    if re.fullmatch(r"t11-e2e-[0-9a-f]{12}-01", str(value["profile_name"])) is None:
        raise ContractError("containment provider profile name is invalid")
    if value["lifecycle"] != PROVIDER_LIFECYCLE_PRE_LIVE:
        raise ContractError("containment provider evidence is not a pre-live lifecycle record")
    created = datetime.datetime.strptime(value["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    control_pre = datetime.datetime.strptime(
        control_plane["pre_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ",
    )
    control_post = datetime.datetime.strptime(
        control_plane["post_create_observed_at"], "%Y-%m-%dT%H:%M:%SZ",
    )
    if not control_pre <= created <= control_post:
        raise ContractError("containment provider/control-plane creation chronology drifted")
    if value["approved_archive_sha256"] != APPROVED_CODEX_ARCHIVE_SHA256 or value["observed_archive_sha256"] != APPROVED_CODEX_ARCHIVE_SHA256:
        raise ContractError("containment provider archive digest drifted")
    if value["codex_version_output"] != APPROVED_CODEX_VERSION:
        raise ContractError("containment provider client version drifted")
    if value["status"] == "pass":
        if not value["native_architecture"] or not value["repository_clean"]:
            raise ContractError("passing containment provider evidence lacks provider-isolation facts")
        if value["guest_os"] != "Linux" or not isinstance(value["guest_kernel"], str) or re.fullmatch(r"[0-9A-Za-z._+~-]{1,128}", value["guest_kernel"]) is None:
            raise ContractError("passing containment provider guest platform is invalid")
        if value["profile_name"] != "t11-e2e-{}-01".format(value["public_head"][:12]):
            raise ContractError("containment provider profile/public-head binding drifted")
        if control_plane["status"] != "pass":
            raise ContractError("passing containment provider evidence lacks passing control-plane evidence")
        if (
            control_plane["profile_name"] != value["profile_name"]
            or control_plane["vm_backend"] != value["vm_backend"]
            or control_plane["architecture"] != value["architecture"]
            or control_plane["provider_configuration_sha256"] != value["provider_configuration_sha256"]
            or control_plane["instance_identity_sha256"] != value["vm_instance_identity_sha256"]
        ):
            raise ContractError("containment provider and control-plane evidence differ")
        if value["public_head"] == "0" * 40 or value["public_tree"] == "0" * 40 or any(
            value[field] == "0" * 64 for field in (
                "provider_configuration_sha256", "effective_mount_inventory_sha256",
                "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
                "vm_instance_identity_sha256", "extracted_binary_sha256",
                "runtime_root_binding_sha256", "dedicated_codex_home_binding_sha256",
            )
        ):
            raise ContractError("passing containment provider evidence contains a sentinel binding")
    validate_json_limits(value, {"json_depth": 8, "json_nodes": 192, "json_string_bytes": 256}, "containment provider evidence")
    return value


def mount_boundary_status_from_provider(value: Mapping[str, Any]) -> str:
    """Project only mount/host-sharing facts, independently of provider status."""
    if value.get("status") == "not-run":
        return "not-run"
    closed = (
        value.get("host_mount_count") == 1
        and value.get("host_mount_classifications") == ["provider-internal-cache"]
        and value.get("all_host_mounts_read_only") is True
        and value.get("provider_cache_only") is True
        and value.get("host_sensitive_mounts_absent") is True
        and value.get("unapproved_mounts_absent") is True
        and value.get("ssh_agent_forwarding") is False
        and value.get("dot_ssh_public_key_loading") is False
        and value.get("user_ssh_config_modified") is False
    )
    return "pass" if closed else "fail"


def colima_provider_input_from_profile(profile: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = profile["evidence"]["containment_provider"]
    validate_containment_provider_evidence(evidence)
    if evidence["status"] != "pass" or mount_boundary_status_from_provider(evidence) != "pass":
        raise ContractError("live execution requires passing Colima provider and mount evidence")
    value = {
        "schema": COLIMA_PROVIDER_INPUT_SCHEMA,
        "authority": "owner-authored",
        "provider": {
            "kind": evidence["provider_kind"],
            "profile_name": evidence["profile_name"],
            "vm_backend": evidence["vm_backend"],
            "architecture": evidence["architecture"],
            "created_at": evidence["created_at"],
            "provider_configuration_sha256": evidence["provider_configuration_sha256"],
            "effective_mount_inventory_sha256": evidence["effective_mount_inventory_sha256"],
            "provider_cache_mount_sha256": evidence["provider_cache_mount_sha256"],
            "provider_cache_guest_mountpoint_sha256": evidence["provider_cache_guest_mountpoint_sha256"],
            "host_mount_count": evidence["host_mount_count"],
            "host_mount_classifications": evidence["host_mount_classifications"],
            "all_host_mounts_read_only": evidence["all_host_mounts_read_only"],
            "ssh_agent_forwarding": evidence["ssh_agent_forwarding"],
            "dot_ssh_public_key_loading": evidence["dot_ssh_public_key_loading"],
            "user_ssh_config_modified": evidence["user_ssh_config_modified"],
        },
        "control_plane": dict(evidence["control_plane"]),
        "repository": {"head": evidence["public_head"], "tree": evidence["public_tree"]},
        "client": {
            "version_output": evidence["codex_version_output"],
            "approved_archive_sha256": evidence["approved_archive_sha256"],
            "observed_archive_sha256": evidence["observed_archive_sha256"],
            "extracted_binary_sha256": evidence["extracted_binary_sha256"],
        },
        "lifecycle": dict(evidence["lifecycle"]),
    }
    validate_colima_provider_input(value)
    return value


def validate_runtime_profile(profile: Any, allow_fixture: bool = False) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        raise ContractError("runtime profile must be an object")
    exact_keys(profile, ("schema", "repository", "observed_at", "scope", "status", "reason", "platform", "client", "capabilities", "evidence", "auth", "request", "shell_environment", "live_run_allowed"), "runtime profile")
    if profile["schema"] != "runtime-profile/v1" or profile["repository"] != REPOSITORY:
        raise ContractError("runtime profile identity is invalid")
    if not isinstance(profile["observed_at"], str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", profile["observed_at"]) is None:
        raise ContractError("runtime observation time is invalid")
    if profile["scope"] not in (
        "task-start-sensor", "exact-head-live-sensor",
        "exact-head-probe-only-sensor", "fixture",
    ):
        raise ContractError("runtime profile scope is invalid")
    if profile["scope"] == "fixture" and not allow_fixture:
        raise ContractError("fixture runtime profile cannot authorize live execution")
    status_value = profile["status"]
    if status_value not in (
        "match", "probe-only-match", "profile-drift",
        "unsupported-client", "UNKNOWN", "UNCHECKABLE",
    ):
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
    required_caps = ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "documented_config_keys_probe", "shell_environment_probe", "process_cleanup_probe", "model", "reasoning", "sandbox", "approval", "overrides")
    exact_keys(caps, required_caps, "runtime capabilities")
    for field in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"):
        require_bool(caps[field], "runtime capability " + field)
    if caps["documented_config_keys_probe"] not in ("pass", "fail", "not-proven", "UNCHECKABLE") or caps["shell_environment_probe"] not in ("pass", "fail", "not-run", "UNCHECKABLE") or caps["process_cleanup_probe"] not in RUNTIME_LANE_STATES:
        raise ContractError("runtime probe status is invalid")
    evidence = profile["evidence"]
    if not isinstance(evidence, dict):
        raise ContractError("runtime evidence must be an object")
    exact_keys(
        evidence,
        (
            "configuration_intent", "diagnostic_health", "exact_worker_argv",
            "network_sandbox_behavior", "bubblewrap_prerequisite",
            "lane_statuses", "containment_provider",
        ),
        "runtime evidence",
    )
    if evidence["configuration_intent"] != runtime_configuration_intent():
        raise ContractError("adapter-authored runtime configuration intent drifted")
    diagnostic = evidence["diagnostic_health"]
    if not isinstance(diagnostic, dict):
        raise ContractError("runtime diagnostic evidence must be an object")
    exact_keys(
        diagnostic,
        ("classification", "status", "checks", "codex_issued_effective_configuration_proof"),
        "runtime diagnostic evidence",
    )
    if diagnostic["classification"] != "diagnostic-only" or diagnostic["status"] not in ("pass", "pass-with-advisory-warning", "fail", "not-run", "UNCHECKABLE") or diagnostic["codex_issued_effective_configuration_proof"] is not False:
        raise ContractError("runtime diagnostic evidence is invalid")
    checks = diagnostic["checks"]
    if not isinstance(checks, list) or len(checks) > 64:
        raise ContractError("runtime diagnostic safe checks are invalid")
    if checks != sorted(checks, key=lambda item: (item.get("id", ""), item.get("category", ""), item.get("status", "")) if isinstance(item, dict) else ("", "", "")):
        raise ContractError("runtime diagnostic safe checks are not canonical")
    for check in checks:
        if not isinstance(check, dict):
            raise ContractError("runtime diagnostic safe check is invalid")
        exact_keys(check, ("id", "category", "status"), "runtime diagnostic safe check")
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", str(check["id"])) is None or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", str(check["category"])) is None or check["status"] not in ("ok", "warning", "fail"):
            raise ContractError("runtime diagnostic safe check is invalid")
    if diagnostic["status"] in ("pass", "pass-with-advisory-warning", "fail"):
        if profile["scope"] == "fixture" and allow_fixture and not checks:
            derived_diagnostic_status = diagnostic["status"]
        else:
            required_doctor_categories = (
                tuple(category for category in DOCTOR_REQUIRED_CATEGORIES if category != "auth")
                if profile["scope"] == "exact-head-probe-only-sensor"
                else DOCTOR_REQUIRED_CATEGORIES
            )
            derived_diagnostic_status = classify_doctor_safe_checks(
                checks, required_doctor_categories,
            )
        if diagnostic["status"] != derived_diagnostic_status:
            raise ContractError("runtime diagnostic status disagrees with safe checks")
    elif checks:
        raise ContractError("non-observed runtime diagnostic contains check claims")
    worker_argv_evidence = evidence["exact_worker_argv"]
    if not isinstance(worker_argv_evidence, dict):
        raise ContractError("runtime worker argv evidence must be an object")
    exact_keys(
        worker_argv_evidence,
        ("status", "stage", "reason_code", "rules_bypass_absent", "dynamic_task_data_stdin_only"),
        "runtime worker argv evidence",
    )
    if worker_argv_evidence["status"] not in ("pass", "fail", "not-run", "UNCHECKABLE"):
        raise ContractError("runtime worker argv status is invalid")
    if worker_argv_evidence["stage"] not in WORKER_ARGV_STAGES or worker_argv_evidence["reason_code"] not in WORKER_ARGV_REASON_CODES:
        raise ContractError("runtime worker argv stage/reason is invalid")
    for field in ("rules_bypass_absent", "dynamic_task_data_stdin_only"):
        require_bool(worker_argv_evidence[field], "runtime worker argv " + field)
    argv_claims = (
        worker_argv_evidence["rules_bypass_absent"],
        worker_argv_evidence["dynamic_task_data_stdin_only"],
    )
    if (worker_argv_evidence["status"] == "pass" and argv_claims != (True, True)) or (
        worker_argv_evidence["status"] != "pass" and argv_claims != (False, False)
    ):
        raise ContractError("runtime worker argv evidence is internally inconsistent")
    if worker_argv_evidence["status"] == "pass" and worker_argv_evidence["reason_code"] != "none":
        raise ContractError("passing runtime worker argv evidence has a failure reason")
    if worker_argv_evidence["status"] == "not-run" and worker_argv_evidence["reason_code"] != "not-run":
        raise ContractError("not-run runtime worker argv evidence has an invalid reason")
    failure_pairs = {
        "envelope-invalid": "load-envelope",
        "static-role-invalid": "load-static-role",
        "environment-invalid": "environment-contract",
        "argv-build-failed": "build-argv",
        "argv-policy-rejected": "argv-policy",
        "schema-binding-invalid": "schema-binding",
        "filesystem-binding-invalid": "filesystem-binding",
    }
    if worker_argv_evidence["status"] in ("fail", "UNCHECKABLE") and failure_pairs.get(worker_argv_evidence["reason_code"]) != worker_argv_evidence["stage"]:
        raise ContractError("runtime worker argv failure stage/reason pair is invalid")
    network_evidence = evidence["network_sandbox_behavior"]
    if not isinstance(network_evidence, dict):
        raise ContractError("runtime network/sandbox evidence must be an object")
    exact_keys(network_evidence, ("status",), "runtime network/sandbox evidence")
    if network_evidence["status"] not in ("pass", "fail", "not-run", "UNCHECKABLE"):
        raise ContractError("runtime network/sandbox status is invalid")
    prerequisite_evidence = validate_stage_a1_prerequisite_evidence(
        evidence["bubblewrap_prerequisite"]
    )
    containment_evidence = validate_containment_provider_evidence(
        evidence["containment_provider"], allow_fixture=allow_fixture,
    )
    lanes = evidence["lane_statuses"]
    if not isinstance(lanes, dict):
        raise ContractError("runtime evidence lanes must be an object")
    exact_keys(lanes, RUNTIME_LANE_KEYS, "runtime evidence lanes")
    for field in RUNTIME_LANE_KEYS[:-1]:
        if lanes[field] not in RUNTIME_LANE_STATES:
            raise ContractError("runtime evidence lane status is invalid")
    if lanes["auth_status"] not in AUTH_STATES:
        raise ContractError("runtime auth evidence lane status is invalid")
    if lanes["provider_isolation_status"] != containment_evidence["status"]:
        raise ContractError("provider-isolation lane and provider evidence disagree")
    if lanes["mount_boundary_status"] != mount_boundary_status_from_provider(containment_evidence):
        raise ContractError("mount-boundary lane and provider facts disagree")
    if lanes["process_cleanup_status"] != caps["process_cleanup_probe"]:
        raise ContractError("process-cleanup lane and capability disagree")
    if lanes["codex_sandbox_network_status"] != network_evidence["status"]:
        raise ContractError("sandbox/network lane and evidence disagree")
    if lanes["shell_environment_status"] != caps["shell_environment_probe"]:
        raise ContractError("shell-environment lane and capability disagree")
    if (
        caps["documented_config_keys_probe"] == "pass"
        and diagnostic["status"] in ("pass", "pass-with-advisory-warning")
        and worker_argv_evidence["status"] == "pass"
    ):
        derived_config_status = "pass"
    elif (
        caps["documented_config_keys_probe"] == "not-proven"
        and diagnostic["status"] == "not-run"
        and worker_argv_evidence["status"] == "not-run"
    ):
        derived_config_status = "not-run"
    elif "UNCHECKABLE" in (
        caps["documented_config_keys_probe"], diagnostic["status"],
        worker_argv_evidence["status"],
    ):
        derived_config_status = "UNCHECKABLE"
    else:
        derived_config_status = "fail"
    if lanes["config_status"] != derived_config_status:
        raise ContractError("config lane and bounded config evidence disagree")
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
    if lanes["auth_status"] != auth["class"]:
        raise ContractError("auth lane and safe auth classification disagree")
    request = profile["request"]
    if request != {"model": "gpt-5.6-sol", "reasoning_effort": "high", "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"}:
        raise ContractError("runtime model/reasoning/sandbox/approval request drifted")
    shell_env = profile["shell_environment"]
    exact_names = list(SHELL_ENVIRONMENT_NAMES)
    fixed_values = {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}
    expected_shell = {
        "inherit": "none", "required_names": exact_names,
        "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated",
        "fixed_values": fixed_values, "private_home": True, "private_tmpdir": True,
        "secret_named_variables_excluded": True, "probe_required": True,
    }
    if shell_env != expected_shell:
        raise ContractError("runtime shell environment profile drifted")
    non_auth_lanes_pass = all(lanes[field] == "pass" for field in RUNTIME_LANE_KEYS[:-1])
    common_ready = (
        release_class == "stable"
        and non_auth_lanes_pass
        and caps["documented_config_keys_probe"] == "pass"
        and caps["shell_environment_probe"] == "pass"
        and caps["process_cleanup_probe"] == "pass"
        and diagnostic["status"] in ("pass", "pass-with-advisory-warning")
        and worker_argv_evidence["status"] == "pass"
        and network_evidence["status"] == "pass"
        and prerequisite_evidence["status"] == "pass"
        and containment_evidence["status"] == "pass"
        and all(caps[field] for field in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"))
    )
    match_ready = (
        status_value == "match"
        and common_ready
        and lanes["auth_status"] == "signed-in-client"
    )
    if profile["live_run_allowed"] is not match_ready:
        raise ContractError("live_run_allowed disagrees with fail-closed profile evidence")
    if release_class.startswith("prerelease") and status_value != "unsupported-client":
        raise ContractError("unapproved prerelease must be unsupported-client")
    if status_value == "match" and auth["class"] != "signed-in-client":
        raise ContractError("match profile requires the approved VM device-auth class")
    if status_value == "probe-only-match":
        if (
            profile["scope"] != "exact-head-probe-only-sensor"
            or not common_ready
            or auth["class"] != "unavailable"
            or profile["live_run_allowed"] is not False
        ):
            raise ContractError("probe-only-match disagrees with Stage A evidence")
    if status_value == "match" and profile["scope"] != "fixture" and client["version_output"] != APPROVED_CODEX_VERSION:
        raise ContractError("live match requires the exact approved Codex client version")
    if containment_evidence["status"] == "pass" and containment_evidence["extracted_binary_sha256"] != client["binary_sha256"]:
        raise ContractError("containment provider and runtime client binary digests disagree")
    if containment_evidence["status"] == "pass" and profile["scope"] != "fixture":
        if platform != {"os": "Linux", "architecture": COLIMA_ARCHITECTURE}:
            raise ContractError("live runtime platform is not the approved Linux/aarch64 guest")
        if containment_evidence["guest_os"] != platform["os"] or containment_evidence["architecture"] != platform["architecture"]:
            raise ContractError("runtime platform and containment provider disagree")
        if containment_evidence["codex_version_output"] != client["version_output"]:
            raise ContractError("runtime client and containment provider version disagree")
        created = datetime.datetime.strptime(containment_evidence["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        observed = datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ")
        control_pre = datetime.datetime.strptime(
            containment_evidence["control_plane"]["pre_create_observed_at"],
            "%Y-%m-%dT%H:%M:%SZ",
        )
        control_post = datetime.datetime.strptime(
            containment_evidence["control_plane"]["post_create_observed_at"],
            "%Y-%m-%dT%H:%M:%SZ",
        )
        if not control_pre <= created <= control_post <= observed:
            raise ContractError("containment provider/control-plane/runtime chronology drifted")
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
    # Raw stderr is retained only for a dedicated bounded in-memory probe.
    # Callers must opt in, classify it immediately, and persist no bytes.
    stderr: bytes = b""


def parse_linux_process_stat(data: bytes) -> Optional[Tuple[int, int, int, str]]:
    """Return PID, PPID, process group, and immutable start-time token."""
    try:
        text = data.decode("ascii", errors="strict")
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
    # A process group outside the reader's PID namespace is represented as
    # zero by procfs. It remains valid discovery topology; the immutable
    # start-time token, not PGID, gates every signal operation.
    # ``starttime`` is an unsigned count of clock ticks since boot.  A
    # process created during the first tick (notably early boot processes in
    # a fresh Colima VM) can therefore have the legitimate value zero.  The
    # PID plus this kernel value remains the signal-time birth binding; only
    # values outside the documented non-negative domain are invalid.
    if pid <= 0 or ppid < 0 or pgid < 0 or start_ticks < 0:
        raise ContractError("Linux process birth-identity sensor returned invalid data")
    if state == "Z":
        return None
    return pid, ppid, pgid, "linux:" + str(start_ticks)


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
            record = parse_linux_process_stat(bytes(data))
            if record is not None:
                pid, ppid, pgid, birth_token = record
                table[pid] = (ppid, pgid, birth_token)
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


def live_containment_proven(evidence: Optional[Mapping[str, Any]] = None) -> bool:
    """Require the approved outer VM and mount boundary, not PID containment."""
    if evidence is None:
        return False
    try:
        validate_containment_provider_evidence(evidence)
    except ContractError:
        return False
    return (
        evidence["status"] == "pass"
        and mount_boundary_status_from_provider(evidence) == "pass"
    )


def run_bounded_process(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin_bytes: bytes,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    grace_seconds: float = 2.0,
    capture_stderr: bool = False,
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
        stderr=bytes(buffers["stderr"][:stderr_limit]) if capture_stderr else b"",
    )


def _materialize_reviewed_rules_profile(environment: Mapping[str, str]) -> str:
    """Create and verify the fixed empty rules profile without following links."""
    require_runtime_fs_capabilities()
    home_value = environment.get("HOME")
    codex_home_value = environment.get("CODEX_HOME")
    if not isinstance(home_value, str) or not isinstance(codex_home_value, str):
        raise ContractError("private runtime home or CODEX_HOME is unavailable")
    home = Path(home_value)
    codex_home = Path(codex_home_value)
    if not home.is_absolute() or codex_home != home / ".codex":
        raise ContractError("CODEX_HOME is not the reviewed private-home layer")
    if os.mkdir not in getattr(os, "supports_dir_fd", set()):
        raise ContractError("rules profile requires mkdir(dir_fd) capability")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    home_descriptor = os.open(str(home), directory_flags)
    try:
        home_binding = os.fstat(home_descriptor)
        if not stat.S_ISDIR(home_binding.st_mode) or stat.S_IMODE(home_binding.st_mode) & 0o077:
            raise ContractError("private runtime home mode is unsafe")
        try:
            os.mkdir(".codex", 0o700, dir_fd=home_descriptor)
        except FileExistsError:
            pass
        codex_descriptor = os.open(".codex", directory_flags, dir_fd=home_descriptor)
        try:
            codex_binding = os.fstat(codex_descriptor)
            named_codex = os.stat(".codex", dir_fd=home_descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(codex_binding.st_mode) or stat.S_IMODE(codex_binding.st_mode) != 0o700 or (codex_binding.st_dev, codex_binding.st_ino) != (named_codex.st_dev, named_codex.st_ino):
                raise ContractError("private CODEX_HOME binding or mode is unsafe")
            try:
                os.mkdir("rules", 0o700, dir_fd=codex_descriptor)
            except FileExistsError:
                pass
            rules_descriptor = os.open("rules", directory_flags, dir_fd=codex_descriptor)
            try:
                rules_binding = os.fstat(rules_descriptor)
                named_rules = os.stat("rules", dir_fd=codex_descriptor, follow_symlinks=False)
                if not stat.S_ISDIR(rules_binding.st_mode) or stat.S_IMODE(rules_binding.st_mode) != 0o700 or (rules_binding.st_dev, rules_binding.st_ino) != (named_rules.st_dev, named_rules.st_ino):
                    raise ContractError("reviewed rules directory binding or mode is unsafe")
                name = Path(REVIEWED_RULES_RELATIVE_PATH).name
                try:
                    file_descriptor = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=rules_descriptor,
                    )
                except FileExistsError:
                    file_descriptor = None
                if file_descriptor is not None:
                    try:
                        written = 0
                        while written < len(REVIEWED_RULES_BYTES):
                            count = os.write(file_descriptor, REVIEWED_RULES_BYTES[written:])
                            if count <= 0:
                                raise ContractError("reviewed rules profile write did not progress")
                            written += count
                        os.fsync(file_descriptor)
                    finally:
                        os.close(file_descriptor)
                read_descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=rules_descriptor)
                try:
                    info = os.fstat(read_descriptor)
                    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != len(REVIEWED_RULES_BYTES):
                        raise ContractError("reviewed rules profile mode or size drifted")
                    data = bytearray()
                    while len(data) <= len(REVIEWED_RULES_BYTES):
                        chunk = os.read(read_descriptor, len(REVIEWED_RULES_BYTES) + 1 - len(data))
                        if not chunk:
                            break
                        data.extend(chunk)
                finally:
                    os.close(read_descriptor)
                named_file = os.stat(name, dir_fd=rules_descriptor, follow_symlinks=False)
                if (named_file.st_dev, named_file.st_ino) != (info.st_dev, info.st_ino) or bytes(data) != REVIEWED_RULES_BYTES:
                    raise ContractError("reviewed rules profile binding or bytes drifted")
                os.fsync(rules_descriptor)
            finally:
                os.close(rules_descriptor)
            os.fsync(codex_descriptor)
        finally:
            os.close(codex_descriptor)
        os.fsync(home_descriptor)
        named_home = os.stat(str(home), follow_symlinks=False)
        if (named_home.st_dev, named_home.st_ino) != (home_binding.st_dev, home_binding.st_ino):
            raise ContractError("private runtime home namespace changed")
    finally:
        os.close(home_descriptor)
    return sha256_bytes(REVIEWED_RULES_BYTES)


def materialize_reviewed_rules_profile(environment: Mapping[str, str]) -> str:
    try:
        return _materialize_reviewed_rules_profile(environment)
    except ContractError:
        raise
    except OSError:
        raise ContractError("reviewed rules profile cannot be materialized safely")


def minimal_environment(executable: Path, private_home: Path, private_tmp: Path, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    path_parts: List[str] = []
    for candidate in (str(executable.parent), str(Path(sys.executable).resolve().parent), "/usr/bin", "/bin"):
        if candidate not in path_parts:
            path_parts.append(candidate)
    environment = {
        "PATH": os.pathsep.join(path_parts),
        "HOME": str(private_home),
        "CODEX_HOME": str(private_home / ".codex"),
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
    required = SHELL_ENVIRONMENT_NAMES
    if any(name not in environment or not isinstance(environment[name], str) for name in required):
        raise ContractError("live shell environment is missing an explicit required value")
    return "{" + ",".join(
        "{}={}".format(name, json.dumps(environment[name])) for name in sorted(required)
    ) + "}"


def validate_runtime_argv_policy(argv: Sequence[str], require_memory_overrides: bool = False) -> None:
    """Reject policy bypasses and legacy/missing memory configuration in argv."""
    if not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        raise ContractError("runtime argv is invalid")
    for item in argv:
        if item == "--ignore-rules" or item.startswith("--ignore-rules="):
            raise ContractError("runtime argv must not bypass execpolicy rules")
        if item.startswith("--dangerously-bypass-"):
            raise ContractError("runtime argv contains a dangerous bypass flag")
    configuration: Dict[str, str] = {}
    for index, item in enumerate(argv):
        if item != "-c":
            continue
        if index + 1 >= len(argv) or "=" not in argv[index + 1]:
            raise ContractError("runtime configuration argv is malformed")
        key, literal = argv[index + 1].split("=", 1)
        if key in configuration:
            raise ContractError("runtime configuration argv contains a duplicate key")
        configuration[key] = literal
    legacy = ("features.memory_tool", "features.memory_tool_use")
    if any(key in configuration for key in legacy):
        raise ContractError("runtime argv contains a legacy undocumented memory key")
    if "features.use_legacy_landlock" in configuration:
        raise ContractError("runtime argv contains the unapproved legacy Landlock fallback")
    if require_memory_overrides:
        for key in ("memories.generate_memories", "memories.use_memories"):
            if configuration.get(key) != "false":
                raise ContractError("runtime argv must set documented memory key false: " + key)


def build_live_argv(binary: Path, target_root: Path, repository_root: Path, envelope: Mapping[str, Any], environment: Optional[Mapping[str, str]] = None) -> List[str]:
    role = extract_static_role(repository_root)
    worker = envelope["worker"]
    if environment is None:
        environment = {
            "PATH": "/verified/bin:/usr/bin:/bin", "HOME": "/private-home",
            "CODEX_HOME": "/private-home/.codex", "TMPDIR": "/private-tmp",
            **REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0",
        }
    argv = [
        str(binary), "exec", "--json", "--ephemeral", "--strict-config", "--ignore-user-config",
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
    validate_runtime_argv_policy(argv, require_memory_overrides=True)
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
        containment = profile["evidence"]["containment_provider"]
        if (
            containment["status"] != "pass"
            or containment["public_head"] != envelope["harness"]["commit"]
            or containment["public_tree"] != envelope["harness"]["tree"]
        ):
            raise ContractError("containment provider and envelope harness binding differ")
        provider_input = colima_provider_input_from_profile(profile)
        observed = datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - observed).total_seconds()
        if age < -300 or age > 900:
            raise ContractError("live runtime profile is stale or future-dated")
        fresh_profile = observe_runtime_profile(
            repository_root,
            envelope["worker"]["model"],
            envelope["worker"]["reasoning_effort"],
            provider_input,
        )
        validate_runtime_profile(fresh_profile)
        supplied_semantics = {key: value for key, value in profile.items() if key != "observed_at"}
        fresh_semantics = {key: value for key, value in fresh_profile.items() if key != "observed_at"}
        if fresh_profile["status"] != "match" or fresh_profile["live_run_allowed"] is not True or fresh_semantics != supplied_semantics:
            raise ContractError("fresh semantic runtime sensor does not match the approved profile")
    if mode not in ("offline", "live"):
        raise ContractError("unsupported execution mode")

    with contextlib.ExitStack() as stack:
        layout: Optional[ColimaRuntimeLayout] = None
        if mode == "live":
            layout = prepare_colima_runtime_layout()
            names_before = sorted(entry.name for entry in os.scandir(layout.work))
            if names_before:
                raise ContractError("private Colima work root is not empty before execution")
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="execution-", dir=str(layout.work)))
            private_home = layout.home
            private_tmp = layout.tmp
            executable = layout.binary
        else:
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="t11-runtime-"))
            private_home = Path(temporary) / "home"
            private_tmp = Path(temporary) / "tmp"
            private_home.mkdir(mode=0o700)
            private_tmp.mkdir(mode=0o700)
            executable = Path(sys.executable).resolve()
        container = Path(temporary)
        os.chmod(container, 0o700)
        extra = {"T11_FAKE_BEHAVIOR": fake_behavior} if mode == "offline" else None
        environment = minimal_environment(executable, private_home, private_tmp, extra)
        harness_binding = None
        persistent_home_before = None
        persistent_tmp_before = None
        binary_before = None
        if mode == "live":
            if materialize_reviewed_rules_profile(environment) != runtime_configuration_intent()["rules_profile_sha256"]:
                raise ContractError("reviewed live execpolicy profile digest drifted")
            if hash_regular_file(executable) != profile["client"]["binary_sha256"]:
                raise ContractError("Codex binary digest drifted after the runtime sensor")
            binary_before = hash_regular_file(executable)
            version_result = bounded_capture([str(executable), "--version"], container, environment)
            help_result = bounded_capture([str(executable), "exec", "--help"], container, environment)
            if version_result.exit_code != 0 or help_result.exit_code != 0 or version_result.timed_out or help_result.timed_out or version_result.stdout_overflow or help_result.stdout_overflow:
                raise ContractError("Codex version/help evidence became uncheckable before execution")
            if version_result.stdout.decode("utf-8", errors="strict").strip() != profile["client"]["version_output"] or sha256_bytes(help_result.stdout) != profile["client"]["exec_help_sha256"]:
                raise ContractError("Codex version/help evidence drifted after the runtime sensor")
            harness_binding = verify_harness_state(repository_root, envelope, environment)
            persistent_home_before = execution_root_inventory(private_home)
            persistent_tmp_before = execution_root_inventory(private_tmp)
        target_root = create_synthetic_repository(container, environment)
        before = git_snapshot(target_root, environment)
        validate_pre_snapshot(before)
        execution_root_before = execution_root_inventory(container)

        if mode == "offline":
            worker_argv = [sys.executable, "-I", str((repository_root / FAKE_PATH).resolve())]
        else:
            worker_argv = build_live_argv(executable, target_root, repository_root, envelope, environment)
        prompt = static_prompt(envelope)
        if mode == "live":
            assert layout is not None
            process = run_claimed_live_worker(
                layout, envelope, profile, worker_argv, target_root, environment, prompt,
            )
        else:
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
            assert persistent_home_before is not None and persistent_tmp_before is not None and binary_before is not None
            if execution_root_inventory(private_home) != persistent_home_before:
                raise ContractError("dedicated Codex HOME changed during the live worker")
            if execution_root_inventory(private_tmp) != persistent_tmp_before:
                raise ContractError("dedicated private TMPDIR changed during the live worker")
            if hash_regular_file(executable) != binary_before:
                raise ContractError("Codex binary changed during the live worker")
            assert layout is not None
            names_during = sorted(entry.name for entry in os.scandir(layout.work))
            if names_during != [container.name]:
                raise ContractError("private Colima work root membership changed")
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


def safe_error(error: BaseException) -> Dict[str, Any]:
    value = {
        "schema": "codex-exec-adapter-error/v1",
        "status": "fail",
        "reason": "bounded runtime contract failure",
    }
    if isinstance(error, ProfileProbeError):
        value["stage"] = error.stage
        value["reason_code"] = error.reason_code
    return value


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


def bounded_capture(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin_bytes: bytes = b"",
    timeout: float = 15,
    *,
    stdout_limit: int = 1_048_576,
    stderr_limit: int = 1_048_576,
    capture_stderr: bool = False,
) -> ProcessResult:
    return run_bounded_process(
        argv, cwd, env, stdin_bytes, timeout, stdout_limit, stderr_limit, 2,
        capture_stderr=capture_stderr,
    )


def auth_class(binary: Path, cwd: Path, env: Mapping[str, str]) -> str:
    argv = [str(binary), "-c", 'cli_auth_credentials_store="file"', "login", "status"]
    try:
        validate_runtime_argv_policy(argv, require_memory_overrides=False)
        result = bounded_capture(
            argv, cwd, env, timeout=15, stdout_limit=64, stderr_limit=256,
            capture_stderr=True,
        )
    except (ContractError, OSError, subprocess.SubprocessError):
        return "unknown"
    if (
        result.exit_code is None or result.exit_code != 0 or result.timed_out
        or not result.reaped
    ):
        return "unavailable"
    if result.stdout_overflow or result.stderr_overflow or result.stdout != b"":
        return "unknown"
    stderr = result.stderr
    if stderr == b"Logged in using ChatGPT\n":
        classification = "signed-in-client"
    elif re.fullmatch(
        rb"Logged in using an API key - (?:\*\*\*|[A-Za-z0-9_-]{8}\*\*\*[A-Za-z0-9_-]{5})\n",
        stderr,
    ) is not None:
        classification = "api-key"
    else:
        classification = "unknown"
    # Do not return, hash, or persist even redacted authentication output.
    del stderr, result
    return classification


def sandbox_probe_argv(
    binary: Path,
    env: Mapping[str, str],
    command_argv: Sequence[str],
    root: Optional[Path] = None,
) -> List[str]:
    """Build the reviewed official 0.150.1 Option B sandbox argv."""
    if root is None:
        home_value = env.get("HOME")
        if not isinstance(home_value, str):
            raise ContractError("sandbox probe root binding is unavailable")
        root = Path(home_value).parent
    if not root.is_absolute() or not command_argv:
        raise ContractError("sandbox probe argv root or command is invalid")
    argv = runtime_configuration_argv(binary, env) + [
        "sandbox", "--permission-profile", ":read-only",
        "-C", str(root), "--", *list(command_argv),
    ]
    validate_sandbox_probe_argv(argv)
    return argv


def validate_sandbox_probe_argv(argv: Sequence[str]) -> None:
    """Reject unsupported or conflicting 0.150.1 sandbox combinations."""
    validate_runtime_argv_policy(argv, require_memory_overrides=True)
    if argv.count("sandbox") != 1:
        raise ContractError("sandbox probe argv must contain one sandbox subcommand")
    index = argv.index("sandbox")
    tail = list(argv[index:])
    if len(tail) < 7 or tail[:4] != [
        "sandbox", "--permission-profile", ":read-only", "-C",
    ]:
        raise ContractError("sandbox probe argv is not the reviewed Option B profile")
    if not Path(tail[4]).is_absolute() or tail[5] != "--" or not tail[6:]:
        raise ContractError("sandbox probe argv lacks its exact root or delimiter")
    if tail.count("--") != 1 or any(
        item in ("--sandbox-state-json", "--sandbox-state-disable-network", "--include-managed-config")
        or item.startswith("--sandbox-state-json=")
        or item.startswith("--permission-profile=")
        for item in tail[6:]
    ):
        raise ContractError("sandbox probe argv contains unsupported or conflicting arguments")
    if any(item in ("--sandbox-state-json", "--sandbox-state-disable-network", "--include-managed-config") for item in tail[:6]):
        raise ContractError("sandbox probe argv contains conflicting state flags")
    if tail.count("--permission-profile") != 1 or tail.count("-C") != 1:
        raise ContractError("sandbox probe argv duplicates its reviewed bindings")


def reviewed_runtime_configuration(env: Mapping[str, str]) -> Dict[str, Any]:
    validate_documented_memory_overrides(REQUIRED_OVERRIDES)
    return {
        "approval_policy": "never",
        "model_reasoning_effort": "high",
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {
            name: env[name] for name in SHELL_ENVIRONMENT_NAMES
        },
        **REQUIRED_OVERRIDES,
    }


def runtime_configuration_argv(binary: Path, env: Mapping[str, str]) -> List[str]:
    values = reviewed_runtime_configuration(env)
    # doctor and sandbox accept the global strict/config flags, but
    # --ignore-user-config is an exec-specific option. The private CODEX_HOME
    # contains no config.toml, so these no-model probes do not need that bypass.
    argv = [str(binary), "--strict-config"]
    for key in ("approval_policy", "model_reasoning_effort"):
        argv.extend(["-c", "{}={}".format(key, toml_literal(values[key]))])
    argv.extend(["-c", 'shell_environment_policy.inherit="none"'])
    argv.extend(["-c", "shell_environment_policy.set=" + shell_environment_set_toml(env)])
    for key in sorted(REQUIRED_OVERRIDES):
        argv.extend(["-c", "{}={}".format(key, toml_literal(REQUIRED_OVERRIDES[key]))])
    validate_runtime_argv_policy(argv, require_memory_overrides=True)
    return argv


def classify_doctor_safe_checks(
    checks: Sequence[Mapping[str, str]],
    required_categories: Sequence[str],
) -> str:
    """Derive the closed diagnostic status from the persisted safe projection."""
    required = tuple(required_categories)
    required_set = set(required)
    if (
        len(required_set) != len(required)
        or not required_set.issubset(DOCTOR_REQUIRED_CATEGORIES)
    ):
        raise ContractError("Codex doctor required categories are invalid")
    observed_categories = {check["category"] for check in checks}
    if not required_set.issubset(observed_categories):
        raise ContractError("Codex doctor required category evidence is missing")
    blocking = any(
        check["category"] in required_set and check["status"] != "ok"
        for check in checks
    )
    if blocking:
        return "fail"
    if any(check["status"] != "ok" for check in checks):
        return "pass-with-advisory-warning"
    return "pass"


def doctor_diagnostic_health(
    result: ProcessResult,
    required_categories: Sequence[str] = DOCTOR_REQUIRED_CATEGORIES,
) -> Dict[str, Any]:
    """Normalize a real doctor report without treating it as config proof."""
    evidence = {
        "classification": "diagnostic-only",
        "status": "UNCHECKABLE",
        "checks": [],
        "codex_issued_effective_configuration_proof": False,
    }
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped or result.exit_code is None:
        return evidence
    try:
        report = decode_json_object(result.stdout, "Codex doctor diagnostic report")
        exact_keys(
            report,
            ("schemaVersion", "generatedAt", "codexVersion", "overallStatus", "checks"),
            "Codex doctor diagnostic report",
        )
        if type(report["schemaVersion"]) is not int or report["schemaVersion"] != 1:
            raise ContractError("Codex doctor schemaVersion is invalid")
        if not isinstance(report["generatedAt"], str) or not report["generatedAt"]:
            raise ContractError("Codex doctor generatedAt is invalid")
        if report["codexVersion"] != "0.150.1":
            raise ContractError("Codex doctor version is invalid")
        overall = report["overallStatus"]
        if overall not in ("ok", "warning", "fail"):
            raise ContractError("Codex doctor overallStatus is invalid")
        checks = report["checks"]
        if not isinstance(checks, dict) or not 1 <= len(checks) <= 64:
            raise ContractError("Codex doctor checks are invalid")
        safe_checks = []
        for check_id, check in checks.items():
            if not isinstance(check_id, str) or not check_id or not isinstance(check, dict):
                raise ContractError("Codex doctor check entry is invalid")
            required = {"id", "category", "status", "summary", "details", "durationMs", "remediation"}
            if not required.issubset(check) or set(check) - required - {"issues", "notes"}:
                raise ContractError("Codex doctor check fields are invalid")
            if check["id"] != check_id or check["status"] not in ("ok", "warning", "fail"):
                raise ContractError("Codex doctor check identity/status is invalid")
            if not isinstance(check["category"], str) or not isinstance(check["summary"], str) or not isinstance(check["details"], dict):
                raise ContractError("Codex doctor check content is invalid")
            if type(check["durationMs"]) is not int or not 0 <= check["durationMs"] <= 18_446_744_073_709_551_615:
                raise ContractError("Codex doctor duration is invalid")
            if check["remediation"] is not None and not isinstance(check["remediation"], str):
                raise ContractError("Codex doctor remediation is invalid")
            if len(check["details"]) > 128:
                raise ContractError("Codex doctor details exceed their bound")
            for detail_key, detail_value in check["details"].items():
                if not isinstance(detail_key, str) or not 1 <= len(detail_key) <= 128:
                    raise ContractError("Codex doctor detail key is invalid")
                if isinstance(detail_value, str):
                    continue
                if (
                    not isinstance(detail_value, list)
                    or len(detail_value) > 128
                    or any(not isinstance(item, str) for item in detail_value)
                ):
                    raise ContractError("Codex doctor detail value is invalid")
            if "issues" in check:
                issues = check["issues"]
                if not isinstance(issues, list) or len(issues) > 128:
                    raise ContractError("Codex doctor issues are invalid")
                for issue in issues:
                    if not isinstance(issue, dict):
                        raise ContractError("Codex doctor issue is invalid")
                    exact_keys(
                        issue,
                        ("severity", "cause", "measured", "expected", "remedy", "fields"),
                        "Codex doctor issue",
                    )
                    if issue["severity"] not in ("ok", "warning", "fail") or not isinstance(issue["cause"], str):
                        raise ContractError("Codex doctor issue status/cause is invalid")
                    if any(issue[field] is not None and not isinstance(issue[field], str) for field in ("measured", "expected", "remedy")):
                        raise ContractError("Codex doctor issue optional value is invalid")
                    if not isinstance(issue["fields"], list) or len(issue["fields"]) > 128 or any(not isinstance(field, str) for field in issue["fields"]):
                        raise ContractError("Codex doctor issue fields are invalid")
            if "notes" in check and (
                not isinstance(check["notes"], list)
                or len(check["notes"]) > 128
                or any(not isinstance(note, str) for note in check["notes"])
            ):
                raise ContractError("Codex doctor notes are invalid")
            if (
                re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", check_id) is None
                or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", check["category"]) is None
            ):
                raise ContractError("Codex doctor safe check projection is invalid")
            safe_checks.append({
                "id": check_id,
                "category": check["category"],
                "status": check["status"],
            })
        derived_overall = (
            "fail" if any(item["status"] == "fail" for item in safe_checks)
            else "warning" if any(item["status"] == "warning" for item in safe_checks)
            else "ok"
        )
        if overall != derived_overall:
            raise ContractError("Codex doctor overall status is inconsistent")
        if (overall == "fail" and result.exit_code != 1) or (
            overall != "fail" and result.exit_code != 0
        ):
            raise ContractError("Codex doctor exit status is inconsistent")
        safe_checks.sort(key=lambda item: (item["id"], item["category"], item["status"]))
        normalized = classify_doctor_safe_checks(safe_checks, required_categories)
    except ContractError:
        return evidence
    evidence["checks"] = safe_checks
    evidence["status"] = normalized
    return evidence


def exact_worker_argv_evidence(
    binary: Path,
    root: Path,
    repository_root: Path,
    env: Mapping[str, str],
) -> Dict[str, Any]:
    def failed(stage: str, reason_code: str) -> Dict[str, Any]:
        return {
            "status": "fail", "stage": stage, "reason_code": reason_code,
            "rules_bypass_absent": False,
            "dynamic_task_data_stdin_only": False,
        }

    try:
        envelope = load_repository_json(
            repository_root, "tests/runtime/fixtures/envelope-valid.v1.json",
        )
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return failed("load-envelope", "envelope-invalid")
    try:
        validate_envelope(envelope)
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return failed("schema-binding", "schema-binding-invalid")
    try:
        extract_static_role(repository_root)
    except (ContractError, OSError, UnicodeError):
        return failed("load-static-role", "static-role-invalid")
    try:
        reviewed_runtime_configuration(env)
    except (ContractError, KeyError, TypeError, ValueError):
        return failed("environment-contract", "environment-invalid")
    try:
        root_info = os.stat(str(root), follow_symlinks=False)
        repository_info = os.stat(str(repository_root), follow_symlinks=False)
        if not stat.S_ISDIR(root_info.st_mode) or not stat.S_ISDIR(repository_info.st_mode):
            raise ContractError("directory binding is invalid")
    except (ContractError, OSError):
        return failed("filesystem-binding", "filesystem-binding-invalid")
    try:
        argv = build_live_argv(binary, root, repository_root, envelope, env)
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return failed("build-argv", "argv-build-failed")
    try:
        validate_runtime_argv_policy(argv, require_memory_overrides=True)
    except (ContractError, KeyError, TypeError, ValueError):
        return failed("argv-policy", "argv-policy-rejected")
    return {
        "status": "pass", "stage": "argv-policy", "reason_code": "none",
        "rules_bypass_absent": True,
        "dynamic_task_data_stdin_only": True,
    }


def process_cleanup_probe(root: Path, env: Mapping[str, str]) -> str:
    """Exercise identity-bound process-group cleanup without invoking a model."""
    program = Path("/usr/bin/true")
    try:
        info = os.stat(str(program), follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            return "UNCHECKABLE"
        result = run_bounded_process(
            [str(program)], root, env, b"", 5, 64, 64, 1,
        )
    except (ContractError, OSError, subprocess.SubprocessError):
        return "UNCHECKABLE"
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
        return "UNCHECKABLE"
    return "pass" if result.exit_code == 0 else "fail"


def shell_environment_probe(
    binary: Path,
    root: Path,
    env: Mapping[str, str],
    required: Mapping[str, Any],
) -> str:
    probe_env = dict(env)
    probe_env["T11_FORBIDDEN_SENTINEL"] = "must-not-survive"
    probe_env[SANDBOX_NETWORK_MARKER] = "must-be-overridden"
    set_values = dict(required["shell_environment_policy.set"])
    env_program = Path("/usr/bin/env")
    if not env_program.is_file():
        return "UNCHECKABLE"
    argv = sandbox_probe_argv(binary, env, [str(env_program), "-0"], root)
    result = bounded_capture(argv, root, probe_env)
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
        return "UNCHECKABLE"
    if result.exit_code != 0:
        return "fail"
    entries = result.stdout.split(b"\0")
    parsed: Dict[str, bytes] = {}
    for entry in entries:
        if not entry:
            continue
        if b"=" not in entry:
            return "fail"
        name, value = entry.split(b"=", 1)
        try:
            key = name.decode("ascii")
        except UnicodeDecodeError:
            return "fail"
        parsed[key] = value
    if any(parsed.get(name) != value.encode("utf-8") for name, value in set_values.items()) or "T11_FORBIDDEN_SENTINEL" in parsed:
        return "fail"
    if parsed.get(SANDBOX_NETWORK_MARKER) != SANDBOX_NETWORK_MARKER_VALUE:
        return "fail"
    permitted_automatic = {
        "PWD", "SHLVL", "_", "__CF_USER_TEXT_ENCODING",
        SANDBOX_NETWORK_MARKER,
    }
    if set(parsed) - set(set_values) - permitted_automatic or any(SECRET_NAME_RE.search(name) for name in parsed):
        return "fail"
    return "pass"


def network_sandbox_behavior_probe(binary: Path, root: Path, env: Mapping[str, str]) -> str:
    """Prove that a sandboxed direct loopback connect is denied."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(2)
            port = listener.getsockname()[1]
            # Establish the control condition: the endpoint is reachable before
            # the sandbox is applied, so a later denial is behavior evidence.
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass
            argv = sandbox_probe_argv(
                binary, env,
                [
                    str(Path(sys.executable).resolve()), "-I", "-c",
                    NETWORK_SANDBOX_PROBE_SCRIPT, str(port),
                ],
                root,
            )
            result = bounded_capture(argv, root, env)
    except OSError:
        return "UNCHECKABLE"
    if result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
        return "UNCHECKABLE"
    if result.exit_code == 0:
        return "pass"
    if result.exit_code == 42:
        return "fail"
    return "UNCHECKABLE"


def probe_runtime_evidence(
    binary: Path,
    root: Path,
    env: Mapping[str, str],
    repository_root: Path,
    auth_required: bool = True,
    prerequisite_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Collect bounded independent lanes; no lane claims effective config."""
    prerequisite = validate_stage_a1_prerequisite_evidence(
        dict(prerequisite_evidence)
        if prerequisite_evidence is not None
        else not_run_stage_a1_prerequisite_evidence()
    )
    intent = runtime_configuration_intent()
    required: Optional[Dict[str, Any]] = None
    config_key_status = "UNCHECKABLE"
    try:
        required = reviewed_runtime_configuration(env)
        rules_digest = materialize_reviewed_rules_profile(env)
        if rules_digest != intent["rules_profile_sha256"]:
            raise ContractError("materialized rules profile digest drifted")
        config_key_status = "pass"
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        pass

    required_doctor_categories = DOCTOR_REQUIRED_CATEGORIES if auth_required else tuple(
        category for category in DOCTOR_REQUIRED_CATEGORIES if category != "auth"
    )
    diagnostic = {
        "classification": "diagnostic-only", "status": "UNCHECKABLE",
        "checks": [], "codex_issued_effective_configuration_proof": False,
    }
    if required is not None:
        try:
            diagnostic_argv = runtime_configuration_argv(binary, env) + ["doctor", "--json"]
            validate_runtime_argv_policy(diagnostic_argv, require_memory_overrides=True)
            diagnostic = doctor_diagnostic_health(
                bounded_capture(diagnostic_argv, root, env), required_doctor_categories,
            )
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            pass

    worker_evidence = exact_worker_argv_evidence(binary, root, repository_root, env)
    prerequisite_pass = prerequisite["status"] == "pass"
    if not prerequisite_pass:
        shell_status = "not-run"
    elif required is None:
        shell_status = "UNCHECKABLE"
    else:
        try:
            shell_status = shell_environment_probe(binary, root, env, required)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            shell_status = "UNCHECKABLE"
    if not prerequisite_pass:
        network_status = "not-run"
    else:
        try:
            network_status = network_sandbox_behavior_probe(binary, root, env)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            network_status = "UNCHECKABLE"
    cleanup_status = process_cleanup_probe(root, env)
    config_status = "pass" if (
        config_key_status == "pass"
        and diagnostic["status"] in ("pass", "pass-with-advisory-warning")
        and worker_evidence["status"] == "pass"
    ) else (
        "UNCHECKABLE" if "UNCHECKABLE" in (
            config_key_status, diagnostic["status"], worker_evidence["status"],
        ) else "fail"
    )
    return {
        "documented_config_keys_probe": config_key_status,
        "shell_environment_probe": shell_status,
        "evidence": {
            "configuration_intent": intent,
            "diagnostic_health": diagnostic,
            "exact_worker_argv": worker_evidence,
            "network_sandbox_behavior": {"status": network_status},
            "bubblewrap_prerequisite": prerequisite,
            "lane_statuses": {
                "provider_isolation_status": "not-run",
                "mount_boundary_status": "not-run",
                "process_cleanup_status": cleanup_status,
                "codex_sandbox_network_status": network_status,
                "shell_environment_status": shell_status,
                "config_status": config_status,
                "auth_status": "unavailable",
            },
        },
    }


def probe_runtime_configuration(binary: Path, root: Path, env: Mapping[str, str], repository_root: Optional[Path] = None) -> Tuple[str, str]:
    """Compatibility projection of the separated runtime evidence lanes."""
    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[2]
    observed = probe_runtime_evidence(binary, root, env, repository_root)
    return observed["documented_config_keys_probe"], observed["shell_environment_probe"]


def not_run_runtime_evidence() -> Dict[str, Any]:
    return {
        "configuration_intent": runtime_configuration_intent(),
        "diagnostic_health": {
            "classification": "diagnostic-only",
            "status": "not-run",
            "checks": [],
            "codex_issued_effective_configuration_proof": False,
        },
        "exact_worker_argv": {
            "status": "not-run",
            "stage": "argv-policy",
            "reason_code": "not-run",
            "rules_bypass_absent": False,
            "dynamic_task_data_stdin_only": False,
        },
        "network_sandbox_behavior": {"status": "not-run"},
        "bubblewrap_prerequisite": not_run_stage_a1_prerequisite_evidence(),
        "lane_statuses": {
            "provider_isolation_status": "not-run",
            "mount_boundary_status": "not-run",
            "process_cleanup_status": "not-run",
            "codex_sandbox_network_status": "not-run",
            "shell_environment_status": "not-run",
            "config_status": "not-run",
            "auth_status": "unavailable",
        },
        "containment_provider": not_run_containment_provider_evidence(),
    }


def _read_identity_value(path: Path, label: str) -> bytes:
    data = read_bounded_regular(path, 4096).strip()
    if re.fullmatch(rb"[0-9A-Fa-f-]{8,128}", data) is None:
        raise ContractError(label + " identity is malformed")
    return data.lower()


def observe_colima_provider_evidence(
    repository_root: Path,
    provider_input: Mapping[str, Any],
    layout: ColimaRuntimeLayout,
    binary_sha256: str,
    version_output: str,
    environment: Mapping[str, str],
) -> Dict[str, Any]:
    validate_colima_provider_input(provider_input)
    provider = provider_input["provider"]
    mount_data = read_bounded_regular(Path("/proc/self/mountinfo"), MAX_MOUNTINFO_BYTES)
    mount_facts = inspect_colima_mount_inventory(mount_data, provider)
    machine = _read_identity_value(Path("/etc/machine-id"), "machine")
    boot = _read_identity_value(Path("/proc/sys/kernel/random/boot_id"), "boot")
    instance_sha256 = sha256_bytes(machine + b"\0" + boot)
    control_plane = provider_input["control_plane"]
    uname = os.uname()
    guest_os = uname.sysname
    guest_architecture = uname.machine
    guest_kernel = uname.release
    platform_ok = (
        guest_os == "Linux"
        and guest_architecture == COLIMA_ARCHITECTURE
        and re.fullmatch(r"[0-9A-Za-z._+~-]{1,128}", guest_kernel) is not None
    )
    head_bytes = run_git(repository_root, ("rev-parse", "--verify", "HEAD"), environment, max_bytes=128)
    tree_bytes = run_git(repository_root, ("rev-parse", "--verify", "HEAD^{tree}"), environment, max_bytes=128)
    status_bytes = run_git(repository_root, ("status", "--porcelain=v1", "-z", "--untracked-files=all"), environment, max_bytes=262_144)
    try:
        public_head = head_bytes.decode("ascii", errors="strict").strip()
        public_tree = tree_bytes.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        raise ContractError("public repository identity is malformed")
    if OID_RE.fullmatch(public_head) is None or OID_RE.fullmatch(public_tree) is None:
        raise ContractError("public repository identity is malformed")
    repository_clean = not status_bytes
    repository_matches = (
        public_head == provider_input["repository"]["head"]
        and public_tree == provider_input["repository"]["tree"]
        and repository_clean
    )
    ssh_agent_absent = "SSH_AUTH_SOCK" not in os.environ and "SSH_AGENT_PID" not in os.environ
    sensitive_mounts_absent = mount_facts["host_sensitive_mounts_absent"] and ssh_agent_absent
    provider_isolation_pass = (
        platform_ok
        and repository_matches
        and version_output == provider_input["client"]["version_output"]
        and binary_sha256 == provider_input["client"]["extracted_binary_sha256"]
        and control_plane["status"] == "pass"
        and control_plane["instance_identity_sha256"] == instance_sha256
        and layout.runtime_root_binding_sha256 != "0" * 64
        and layout.dedicated_codex_home_binding_sha256 != "0" * 64
    )
    return {
        "schema": CONTAINMENT_PROVIDER_EVIDENCE_SCHEMA,
        "authority": "adapter/owner-authored",
        "codex_authenticated_attestation": False,
        "status": "pass" if provider_isolation_pass else "fail",
        "provider_kind": provider["kind"],
        "profile_name": provider["profile_name"],
        "vm_backend": provider["vm_backend"],
        "architecture": provider["architecture"],
        "native_architecture": platform_ok,
        "guest_os": guest_os,
        "guest_kernel": guest_kernel if re.fullmatch(r"[0-9A-Za-z._+~-]{1,128}", guest_kernel) else "invalid",
        "created_at": provider["created_at"],
        "provider_configuration_sha256": provider["provider_configuration_sha256"],
        "effective_mount_inventory_sha256": mount_facts["effective_mount_inventory_sha256"],
        "provider_cache_mount_sha256": mount_facts["provider_cache_mount_sha256"],
        "provider_cache_guest_mountpoint_sha256": mount_facts["provider_cache_guest_mountpoint_sha256"],
        "host_mount_count": mount_facts["host_mount_count"],
        "host_mount_classifications": mount_facts["host_mount_classifications"],
        "all_host_mounts_read_only": mount_facts["all_host_mounts_read_only"],
        "provider_cache_only": mount_facts["provider_cache_only"],
        "host_sensitive_mounts_absent": sensitive_mounts_absent,
        "unapproved_mounts_absent": mount_facts["unapproved_mounts_absent"],
        "ssh_agent_forwarding": not ssh_agent_absent,
        "dot_ssh_public_key_loading": provider["dot_ssh_public_key_loading"],
        "user_ssh_config_modified": provider["user_ssh_config_modified"],
        "vm_instance_identity_sha256": instance_sha256,
        "public_head": public_head,
        "public_tree": public_tree,
        "repository_clean": repository_clean,
        "codex_version_output": version_output,
        "approved_archive_sha256": provider_input["client"]["approved_archive_sha256"],
        "observed_archive_sha256": provider_input["client"]["observed_archive_sha256"],
        "extracted_binary_sha256": binary_sha256,
        "runtime_root_binding_sha256": layout.runtime_root_binding_sha256,
        "dedicated_codex_home_binding_sha256": layout.dedicated_codex_home_binding_sha256,
        "control_plane": dict(control_plane),
        "lifecycle": dict(provider_input["lifecycle"]),
    }


def _unavailable_runtime_profile(model: str, reasoning: str, probe_only: bool = False) -> Dict[str, Any]:
    evidence = not_run_runtime_evidence()
    evidence["lane_statuses"]["shell_environment_status"] = "UNCHECKABLE"
    evidence["lane_statuses"]["config_status"] = "UNCHECKABLE"
    return {
        "schema": "runtime-profile/v1", "repository": REPOSITORY,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": "exact-head-probe-only-sensor" if probe_only else "exact-head-live-sensor", "status": "UNKNOWN", "reason": "Codex executable is unavailable",
        "platform": {"os": os.uname().sysname, "architecture": os.uname().machine},
        "client": {"version_output": "unavailable", "release_class": "unknown", "binary_sha256": "0" * 64, "exec_help_sha256": "0" * 64, "resolved_path_recorded": False},
        "capabilities": {"exec_json": False, "ephemeral": False, "strict_config": False, "ignore_user_config": False, "workspace_write": False, "approval_never": False, "documented_config_keys_probe": "UNCHECKABLE", "shell_environment_probe": "UNCHECKABLE", "process_cleanup_probe": "not-run", "model": False, "reasoning": False, "sandbox": False, "approval": False, "overrides": False},
        "evidence": evidence,
        "auth": {"class": "unavailable", "credential_values_recorded": False},
        "request": {"model": model, "reasoning_effort": reasoning, "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"},
        "shell_environment": {"inherit": "none", "required_names": list(SHELL_ENVIRONMENT_NAMES), "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated", "fixed_values": {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}, "private_home": True, "private_tmpdir": True, "secret_named_variables_excluded": True, "probe_required": True},
        "live_run_allowed": False,
    }


def _observe_runtime_profile_bound(
    repository_root: Path,
    model: str,
    reasoning: str,
    binary: Path,
    work: Path,
    env: Mapping[str, str],
    provider_input: Optional[Mapping[str, Any]],
    layout: Optional[ColimaRuntimeLayout],
    probe_only: bool = False,
) -> Dict[str, Any]:
    try:
        return _observe_runtime_profile_bound_inner(
            repository_root, model, reasoning, binary, work, env,
            provider_input, layout, probe_only,
        )
    except ProfileProbeError:
        raise
    except PROFILE_BOUNDARY_EXCEPTIONS:
        raise ProfileProbeError(
            "profile-validation", "profile-invalid",
        ) from None


def _observe_runtime_profile_bound_inner(
    repository_root: Path,
    model: str,
    reasoning: str,
    binary: Path,
    work: Path,
    env: Mapping[str, str],
    provider_input: Optional[Mapping[str, Any]],
    layout: Optional[ColimaRuntimeLayout],
    probe_only: bool = False,
) -> Dict[str, Any]:
    try:
        version_result = bounded_capture([str(binary), "--version"], work, env)
        help_result = bounded_capture([str(binary), "exec", "--help"], work, env)
        if version_result.exit_code != 0 or help_result.exit_code != 0 or version_result.timed_out or help_result.timed_out or version_result.stdout_overflow or help_result.stdout_overflow:
            raise ContractError("runtime version/help sensor is UNCHECKABLE")
        version_output = sanitize_version_output(version_result.stdout)
        help_bytes = help_result.stdout
        help_text = help_bytes.decode("utf-8", errors="strict")
        release_class = classify_release(version_output)
        binary_sha256 = hash_regular_file(binary)
        flags = {
            "exec_json": "--json" in help_text,
            "ephemeral": "--ephemeral" in help_text,
            "strict_config": "--strict-config" in help_text,
            "ignore_user_config": "--ignore-user-config" in help_text,
            "workspace_write": "workspace-write" in help_text,
            "model": "--model" in help_text,
            "sandbox": "--sandbox" in help_text,
        }
    except PROFILE_BOUNDARY_EXCEPTIONS:
        raise ProfileProbeError(
            "client-evidence", "version-help-uncheckable",
        ) from None
    if release_class == "stable":
        try:
            prerequisite = observe_stage_a1_prerequisite(work, env)
            probe = probe_runtime_evidence(
                binary, work, env, repository_root, auth_required=not probe_only,
                prerequisite_evidence=prerequisite,
            )
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            uncheckable = not_run_runtime_evidence()
            for lane in (
                "process_cleanup_status", "codex_sandbox_network_status",
                "shell_environment_status", "config_status",
            ):
                uncheckable["lane_statuses"][lane] = "UNCHECKABLE"
            uncheckable["diagnostic_health"]["status"] = "UNCHECKABLE"
            uncheckable["network_sandbox_behavior"]["status"] = "UNCHECKABLE"
            probe = {
                "documented_config_keys_probe": "UNCHECKABLE",
                "shell_environment_probe": "UNCHECKABLE",
                "evidence": uncheckable,
            }
        config_probe = probe["documented_config_keys_probe"]
        shell_probe = probe["shell_environment_probe"]
        evidence = probe["evidence"]
        if provider_input is not None and layout is not None:
            try:
                containment = observe_colima_provider_evidence(
                    repository_root, provider_input, layout, binary_sha256,
                    version_output, env,
                )
            except PROFILE_BOUNDARY_EXCEPTIONS:
                raise ProfileProbeError(
                    "provider-evidence", "observation-invalid",
                ) from None
            evidence["containment_provider"] = containment
            evidence["lane_statuses"]["provider_isolation_status"] = containment["status"]
            evidence["lane_statuses"]["mount_boundary_status"] = mount_boundary_status_from_provider(containment)
        else:
            containment = not_run_containment_provider_evidence()
            evidence["containment_provider"] = containment
    else:
        config_probe, shell_probe = "not-proven", "not-run"
        evidence = not_run_runtime_evidence()
    if release_class == "stable":
        try:
            observed_auth_class = auth_class(binary, work, env)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            observed_auth_class = "unknown"
    else:
        observed_auth_class = "unavailable"
    evidence["lane_statuses"]["auth_status"] = observed_auth_class
    non_auth_lanes = [evidence["lane_statuses"][name] for name in RUNTIME_LANE_KEYS[:-1]]
    prerequisite_status = evidence["bubblewrap_prerequisite"]["status"]
    config_ok = (
        prerequisite_status == "pass"
        and all(value == "pass" for value in non_auth_lanes)
    )
    caps = {
        **flags,
        "approval_never": config_ok,
        "documented_config_keys_probe": config_probe,
        "shell_environment_probe": shell_probe,
        "process_cleanup_probe": evidence["lane_statuses"]["process_cleanup_status"],
        "reasoning": config_ok,
        "approval": config_ok,
        "overrides": config_ok,
    }
    all_required = all(caps[name] for name in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"))
    if release_class.startswith("prerelease"):
        profile_status, reason = "unsupported-client", "unapproved-prerelease: {} client".format(release_class.split("-", 1)[1])
    elif release_class != "stable":
        profile_status, reason = "UNKNOWN", "client release class is unverifiable"
    elif version_output != APPROVED_CODEX_VERSION:
        profile_status, reason = "unsupported-client", "stable client version is outside the approved exact release"
    elif provider_input is None:
        profile_status, reason = "UNCHECKABLE", "approved disposable Colima provider input is absent"
    elif prerequisite_status in ("not-run", "UNCHECKABLE"):
        profile_status, reason = "UNCHECKABLE", "bubblewrap prerequisite qualification is uncheckable"
    elif prerequisite_status == "fail":
        profile_status, reason = "profile-drift", "bubblewrap prerequisite qualification failed"
    elif any(value in ("not-run", "UNCHECKABLE") for value in non_auth_lanes):
        profile_status, reason = "UNCHECKABLE", "one or more independent Stage A runtime lanes are uncheckable"
    elif any(value == "fail" for value in non_auth_lanes):
        profile_status, reason = "profile-drift", "one or more independent Stage A runtime lanes failed"
    elif not all_required:
        profile_status, reason = "unsupported-client", "required exact client capabilities are unsupported"
    elif observed_auth_class == "unknown":
        profile_status, reason = "UNKNOWN", "authentication probe result is unknown"
    elif probe_only and observed_auth_class != "unavailable":
        profile_status, reason = "profile-drift", "Stage A requires an unauthenticated dedicated CODEX_HOME"
    elif probe_only:
        profile_status, reason = "probe-only-match", "exact unauthenticated Stage A provider and runtime probes match"
    elif observed_auth_class != "signed-in-client":
        profile_status, reason = "profile-drift", "approved VM device-auth class is unavailable or drifted"
    else:
        profile_status, reason = "match", "exact approved stable client and disposable Colima provider probes match"
    profile = {
        "schema": "runtime-profile/v1", "repository": REPOSITORY,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": "exact-head-probe-only-sensor" if probe_only else "exact-head-live-sensor", "status": profile_status, "reason": reason,
        "platform": {"os": os.uname().sysname, "architecture": os.uname().machine},
        "client": {"version_output": version_output, "release_class": release_class, "binary_sha256": binary_sha256, "exec_help_sha256": sha256_bytes(help_bytes), "resolved_path_recorded": False},
        "capabilities": caps,
        "evidence": evidence,
        "auth": {"class": observed_auth_class, "credential_values_recorded": False},
        "request": {"model": model, "reasoning_effort": reasoning, "sandbox": "workspace-write", "approval_policy": "never", "config_profile": "t11-live-v1"},
        "shell_environment": {"inherit": "none", "required_names": list(SHELL_ENVIRONMENT_NAMES), "path_policy": "verified-executable-parent+verified-python-parent+/usr/bin+/bin-deduplicated", "fixed_values": {**REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}, "private_home": True, "private_tmpdir": True, "secret_named_variables_excluded": True, "probe_required": True},
        "live_run_allowed": profile_status == "match",
    }
    validate_runtime_profile(profile)
    return profile


def observe_runtime_profile(repository_root: Path, model: str, reasoning: str, provider_input: Optional[Mapping[str, Any]] = None, probe_only: bool = False) -> Dict[str, Any]:
    try:
        require_runtime_fs_capabilities()
    except PROFILE_BOUNDARY_EXCEPTIONS:
        raise ProfileProbeError(
            "runtime-capabilities", "capability-unavailable",
        ) from None
    if provider_input is not None:
        try:
            validate_colima_provider_input(provider_input)
        except PROFILE_BOUNDARY_EXCEPTIONS:
            raise ProfileProbeError("provider-input", "input-invalid") from None
        try:
            layout = prepare_colima_runtime_layout()
        except PROFILE_BOUNDARY_EXCEPTIONS:
            raise ProfileProbeError("runtime-layout", "layout-invalid") from None
        binary = layout.binary
        try:
            hash_regular_file(binary)
        except (ContractError, OSError):
            return _unavailable_runtime_profile(model, reasoning, probe_only)
        env = minimal_environment(binary, layout.home, layout.tmp)
        return _observe_runtime_profile_bound(
            repository_root, model, reasoning, binary, layout.work, env, provider_input, layout, probe_only,
        )
    resolved = resolve_executable_from_path("codex", {"PATH": REVIEWED_SENSOR_PATH})
    if resolved is None:
        return _unavailable_runtime_profile(model, reasoning, probe_only)
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
        return _observe_runtime_profile_bound(
            repository_root, model, reasoning, binary, work, env, None, None, probe_only,
        )


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


def cli_profile(args: argparse.Namespace, repository_root: Path) -> Dict[str, Any]:
    try:
        require_runtime_fs_capabilities()
    except PROFILE_BOUNDARY_EXCEPTIONS:
        raise ProfileProbeError(
            "runtime-capabilities", "capability-unavailable",
        ) from None
    try:
        provider_input = decode_json_object(
            read_stdin_bounded(), "Colima provider input",
        )
        validate_colima_provider_input(provider_input)
    except PROFILE_BOUNDARY_EXCEPTIONS:
        raise ProfileProbeError("provider-input", "input-invalid") from None
    return observe_runtime_profile(
        repository_root, args.model, args.reasoning_effort, provider_input,
        probe_only=args.probe_only,
    )


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
    profile_parser.add_argument(
        "--probe-only", action="store_true",
        help="observe unauthenticated Stage A lanes; never authorize live execution",
    )
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
            result = cli_profile(args, repository_root)
        else:
            raise ContractError("unsupported adapter command")
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (ProfileProbeError, ContractError, OSError, subprocess.SubprocessError, UnicodeError, ValueError, KeyError, TypeError, RecursionError) as error:
        sys.stdout.buffer.write(canonical_bytes(safe_error(error)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
