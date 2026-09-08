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
import shutil
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
T11_ACCEPTED_PUBLIC_BRANCH = "codex/phase-2-minimal-execution-slice"
T12_PUBLIC_BRANCH = "codex/phase-2-live-codex-runtime"
TASK_ISSUE = 25
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
OFFICIAL_CODEX_0150_SOURCE_COMMIT = "90854393966b21e9ebfd21b122334eb09a20c93d"
OFFICIAL_CODEX_0150_SOURCE_BLOBS = {
    "debug_sandbox": "06c133394b408d4700a82bd88ddd6b8cf01ffd79",
    "spawn": "bbae9308d7e8483476887cb1a1e82555001be06c",
    "shell_environment": "e8bdaa40ca63c29ee23111252a04165e0f1f528e",
}
REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS = (SANDBOX_NETWORK_MARKER,)
SHELL_ENVIRONMENT_REASON_CODES = (
    "none", "not-run", "process-nonzero", "process-timeout",
    "output-overflow", "process-not-reaped", "malformed-env-output",
    "duplicate-env-key", "required-value-missing", "required-value-mismatch",
    "forbidden-sentinel-survived", "network-marker-missing",
    "network-marker-mismatch", "unexpected-key-set", "secret-shaped-key",
    "observation-uncheckable",
)
SHELL_ENVIRONMENT_UNCHECKABLE_REASONS = (
    "process-timeout", "output-overflow", "process-not-reaped",
    "observation-uncheckable",
)
MAX_SHELL_ENVIRONMENT_ENTRIES = 64
MAX_SHELL_ENVIRONMENT_NAME_BYTES = 128
MAX_SHELL_ENVIRONMENT_VALUE_BYTES = 8_192
NETWORK_SANDBOX_REASON_CODES = (
    "none", "not-run", "control-unavailable", "control-not-accepted",
    "control-peer-mismatch", "control-not-closed", "parent-netns-unavailable",
    "sandbox-netns-unavailable", "netns-not-separated",
    "network-marker-missing", "network-marker-mismatch",
    "sandbox-connection-succeeded", "socket-creation-unavailable",
    "unapproved-denial-errno", "process-nonzero", "process-timeout",
    "output-overflow", "process-not-reaped", "malformed-probe-output",
    "observation-uncheckable",
)
NETWORK_SANDBOX_FAIL_REASONS = (
    "netns-not-separated", "network-marker-missing",
    "network-marker-mismatch", "sandbox-connection-succeeded",
)
NETWORK_SANDBOX_UNCHECKABLE_REASONS = (
    "control-unavailable", "control-not-accepted", "control-peer-mismatch",
    "control-not-closed", "parent-netns-unavailable",
    "sandbox-netns-unavailable", "socket-creation-unavailable",
    "unapproved-denial-errno", "process-nonzero", "process-timeout",
    "output-overflow", "process-not-reaped", "malformed-probe-output",
    "observation-uncheckable",
)
APPROVED_NETWORK_DENIAL_ERRNOS = (
    "EPERM", "EACCES", "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED",
)
# The child emits only normalized classifications and a digest of its network
# namespace identity. Socket-creation failure is not accepted as a connection
# result; only an actual connect(2) denial can satisfy the Stage A.2 contract.
NETWORK_SANDBOX_PROBE_SCRIPT = (
    "import errno,hashlib,json,os,re,socket,sys\n"
    "identity='0'*64\n"
    "try:\n"
    " raw_identity=os.readlink('/proc/self/ns/net')\n"
    " if re.fullmatch(r'net:\\[[0-9]+\\]',raw_identity):\n"
    "  identity=hashlib.sha256(raw_identity.encode('ascii')).hexdigest()\n"
    "except (OSError,UnicodeError):\n"
    " pass\n"
    "marker=os.environ.get('CODEX_SANDBOX_NETWORK_DISABLED')\n"
    "marker_status='exact-1' if marker=='1' else ('missing' if marker is None else 'mismatch')\n"
    "connection='UNCHECKABLE'\n"
    "denial='unapproved'\n"
    "try:\n"
    " sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
    "except OSError:\n"
    " pass\n"
    "else:\n"
    " try:\n"
    "  sock.settimeout(2)\n"
    "  sock.connect(('127.0.0.1',int(sys.argv[1])))\n"
    " except OSError as error:\n"
    "  connection='denied'\n"
    "  denial=errno.errorcode.get(error.errno,'unapproved')\n"
    " else:\n"
    "  connection='succeeded'\n"
    "  denial='none'\n"
    " finally:\n"
    "  sock.close()\n"
    "payload={'sandbox_network_namespace_sha256':identity,'network_marker_status':marker_status,'sandbox_connection_status':connection,'denial_errno':denial}\n"
    "sys.stdout.write(json.dumps(payload,sort_keys=True,separators=(',',':'))+'\\n')\n"
)
REVIEWED_RULES_RELATIVE_PATH = "rules/t11-reviewed.rules"
REVIEWED_RULES_BYTES = (
    b"# T11 reviewed empty execpolicy profile. Platform policy remains authoritative.\n"
)
COLIMA_PROVIDER_INPUT_SCHEMA = "t11-colima-provider-input/v1"
CONTAINMENT_PROVIDER_EVIDENCE_SCHEMA = "t11-containment-provider-evidence/v1"
GIT_BOOTSTRAP_EVIDENCE_SCHEMA = "t11-git-bootstrap-evidence/v1"
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
APPROVED_GIT_PACKAGE_VERSION = "1:2.43.0-1ubuntu7.3"
APPROVED_GIT_VERSION_OUTPUT = "git version 2.43.0"
APPROVED_GIT_BINARY_SHA256 = "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942"
APPROVED_APPARMOR_PACKAGE_VERSION = "4.0.1really4.0.1-0ubuntu0.24.04.7"
APPROVED_BWRAP_PROFILE_SHA256 = "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9"
STAGE_A1_BWRAP_BINARY = "/usr/bin/bwrap"
STAGE_A1_GIT_BINARY = "/usr/bin/git"
STAGE_A1_GIT_FIXED_ENVIRONMENT = {
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT = (
    "import os,stat,sys\n"
    "def fail(): os._exit(64)\n"
    "def empty(fd):\n"
    " with os.scandir(fd) as entries: return next(entries,None) is None\n"
    "fixed={'GIT_ATTR_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',"
    "'GIT_CONFIG_NOSYSTEM':'1','GIT_OPTIONAL_LOCKS':'0',"
    "'GIT_TERMINAL_PROMPT':'0','LANG':'C.UTF-8','LC_ALL':'C.UTF-8',"
    "'PATH':'/usr/bin:/bin','TZ':'UTC'}\n"
    "allowed=set(fixed)|{'HOME'}\n"
    "extra=set(os.environ)-allowed\n"
    "home=os.environ.get('HOME','')\n"
    "if not (len(sys.argv)>1 and sys.argv[1]=='/usr/bin/git' "
    "and (not extra or (sys.platform=='darwin' and extra=={'__CF_USER_TEXT_ENCODING'})) "
    "and all(os.environ.get(k)==v for k,v in fixed.items()) "
    "and os.path.isabs(home) and '\\x00' not in home): fail()\n"
    "try:\n"
    " flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW\n"
    " home_fd=os.open(home,flags)\n"
    " info=os.fstat(home_fd)\n"
    " if not (stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700 "
    "and info.st_uid==os.getuid() and empty(home_fd)): fail()\n"
    " after=os.fstat(home_fd)\n"
    " if (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns)!="
    "(info.st_dev,info.st_ino,info.st_mtime_ns,info.st_ctime_ns): fail()\n"
    " rebound=os.stat(home,follow_symlinks=False)\n"
    " if (rebound.st_dev,rebound.st_ino)!=(info.st_dev,info.st_ino): fail()\n"
    " os.set_inheritable(home_fd,True)\n"
    " projection=('/proc/self/fd/' if sys.platform.startswith('linux') "
    "else '/dev/fd/')+str(home_fd)\n"
    " child=dict(fixed); child['HOME']=projection\n"
    " os.umask(0o077)\n"
    " os.execve(sys.argv[1],sys.argv[1:],child)\n"
    "except (OSError,ValueError,TypeError,AttributeError): fail()\n"
)
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
STAGE_A1_GIT_PACKAGE_QUERY_ARGV = (
    "/usr/bin/dpkg-query", "--show",
    "--showformat=${db:Status-Status}\\t${Version}\\t${Architecture}\\n",
    "git",
)
STAGE_A1_GIT_HASH_ARGV = (
    "/usr/bin/sha256sum", "--", STAGE_A1_GIT_BINARY,
)
STAGE_A1_GIT_VERSION_ARGV = (STAGE_A1_GIT_BINARY, "--version")
STAGE_A1_LOADED_PROFILES_ARGV = (
    "/usr/bin/sudo", "-n", "/usr/bin/cat",
    "/sys/kernel/security/apparmor/profiles",
)
STAGE_A1_PRECLONE_CONTROLLER_ARGV = (
    ("/usr/bin/sudo", "-n", "/usr/bin/apt-get", "update"),
    (
        "/usr/bin/sudo", "-n", "/usr/bin/apt-get", "install",
        "--yes", "--no-install-recommends",
        "apparmor=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "apparmor-profiles=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "bubblewrap=" + APPROVED_BWRAP_PACKAGE_VERSION,
        "git=" + APPROVED_GIT_PACKAGE_VERSION,
    ),
    STAGE_A1_GIT_PACKAGE_QUERY_ARGV,
    STAGE_A1_GIT_HASH_ARGV,
    STAGE_A1_GIT_VERSION_ARGV,
)
STAGE_A1_POSTCLONE_CONTROLLER_ARGV = (
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
STAGE_A1_CONTROLLER_ARGV = (
    STAGE_A1_PRECLONE_CONTROLLER_ARGV + STAGE_A1_POSTCLONE_CONTROLLER_ARGV
)
STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256 = (
    "a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc"
)
STAGE_A1_CONTROLLER_ARGV_SHA256 = (
    "3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff"
)
STAGE_A1_REASON_CODES = (
    "none", "not-run", "unsupported-platform", "apparmor-not-enforcing",
    "package-drift", "profile-drift", "binary-drift", "git-package-drift",
    "git-binary-drift",
    "observation-uncheckable", "nonzero-exit", "signal", "timeout",
    "output-overflow", "unexpected-output", "process-not-reaped",
)
STAGE_A1_PRECONDITION_FAILURE_CODES = (
    "unsupported-platform", "apparmor-not-enforcing", "package-drift",
    "profile-drift", "binary-drift", "git-package-drift", "git-binary-drift",
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


def compatibility_contract() -> Dict[str, Any]:
    """Reviewed source/policy facts, never observations of the executing client."""
    return {
        "schema": "t12-compatibility-contract/v1",
        "codex_source_commit": OFFICIAL_CODEX_0150_SOURCE_COMMIT,
        "network_source_sha256": "eb59313c7cfdb7d003df3c1e3d766ad66e414061ef5065d89546a74c1dd658ed",
        "launcher_source_sha256": "bf1d23f8020d4e73f7a3e235165f0953154170256a92cf0c8254e5ab32578f91",
        "sandbox_source_sha256": "3be631c566fbd4cbd08eea042cf425164d01002951b0dcad927c674beb571134",
        "ubuntu_source_orig_sha256": "c6347eaced49ac0141996f46bba3b089e5e6ea4408bc1c43bab9f2d05dd094e1",
        "ubuntu_source_debian_sha256": "d253eccba8f6a8d636dd3df241c2d4d722785341c665c7817040aafa7ed3495e",
        "launcher_binary_sha256": APPROVED_BWRAP_BINARY_SHA256,
        "launcher_help_sha256": "2e2d9c7637f0e032a23cb86705bf9a82946451916e8583aa50ccc8e943c4b15d",
        "launcher_package": APPROVED_BWRAP_PACKAGE_VERSION,
        "launcher_key": "PWD", "launcher_value": "exact-bound-cwd-in-memory",
        "executed_image_required": True, "sandbox_policy": ":read-only-restricted-no-proxy",
        "socket_create_denials": ["EPERM", "EACCES"],
        "connect_denials": list(APPROVED_NETWORK_DENIAL_ERRNOS),
        "observation_max_age_ms": 300000, "capture_max_ms": 15000,
        "housekeeping": "quiescent-private-root-registry-empty-lock-only",
        "housekeeping_max_entries": 2, "housekeeping_file_bytes": 0,
        "worker_boundary": "same-private-tmp-observed-worker-linux-helper-quiescent-only",
    }


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
            "reviewed_codex_injected_keys": list(
                REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS
            ),
        },
        "overrides": dict(REQUIRED_OVERRIDES),
        "execpolicy": {
            "rules_path_relative_to_codex_home": REVIEWED_RULES_RELATIVE_PATH,
            "rules_profile_sha256": sha256_bytes(REVIEWED_RULES_BYTES),
        },
        "compatibility_contract": compatibility_contract(),
    }
    return {
        "schema": "t11-runtime-configuration-intent/v1",
        "authority": "adapter-authored",
        "effective_configuration_proven": False,
        "configuration_sha256": sha256_bytes(canonical_bytes(static_configuration)),
        "rules_profile_sha256": sha256_bytes(REVIEWED_RULES_BYTES),
        "dynamic_environment_values_excluded": list(DYNAMIC_ENVIRONMENT_NAMES),
        "reviewed_codex_source_commit": OFFICIAL_CODEX_0150_SOURCE_COMMIT,
        "reviewed_codex_source_blobs": dict(OFFICIAL_CODEX_0150_SOURCE_BLOBS),
        "compatibility_contract_sha256": sha256_bytes(canonical_bytes(compatibility_contract())),
        "reviewed_codex_injected_keys_sha256": sha256_bytes(canonical_bytes(
            list(REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS)
        )),
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


def read_bounded_regular(
    path: Path,
    max_bytes: int,
    expected_mode: Optional[int] = None,
    max_advertised_bytes: Optional[int] = None,
    allowed_modes: Optional[Sequence[int]] = None,
    require_single_link: bool = False,
) -> bytes:
    require_runtime_fs_capabilities()
    if (
        type(max_bytes) is not int or max_bytes < 0
        or (
            max_advertised_bytes is not None
            and (
                type(max_advertised_bytes) is not int
                or max_advertised_bytes < max_bytes
            )
        )
    ):
        raise ContractError("bounded input size policy is invalid")
    if type(require_single_link) is not bool:
        raise ContractError("bounded input link policy is invalid")
    if (
        allowed_modes is not None
        and (
            expected_mode is not None
            or not isinstance(allowed_modes, tuple)
            or not allowed_modes
            or any(type(mode) is not int for mode in allowed_modes)
            or len(set(allowed_modes)) != len(allowed_modes)
        )
    ):
        raise ContractError("bounded input mode policy is invalid")
    reviewed_modes = (
        (expected_mode,) if expected_mode is not None else allowed_modes
    )
    advertised_limit = (
        max_bytes if max_advertised_bytes is None else max_advertised_bytes
    )
    try:
        named_before = os.stat(str(path), follow_symlinks=False)
    except OSError:
        raise ContractError("bounded regular input is unavailable")
    if (
        not stat.S_ISREG(named_before.st_mode)
        or named_before.st_size > advertised_limit
    ):
        raise ContractError("bounded input is not a regular file or exceeds its limit")
    if require_single_link and named_before.st_nlink != 1:
        raise ContractError("bounded input is not single-link")
    if (
        reviewed_modes is not None
        and stat.S_IMODE(named_before.st_mode) not in reviewed_modes
    ):
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
        if require_single_link and opened_before.st_nlink != 1:
            raise ContractError("bounded input link count drifted before read")
        if (
            reviewed_modes is not None
            and stat.S_IMODE(opened_before.st_mode) not in reviewed_modes
        ):
            raise ContractError("bounded input mode drifted before read")
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise ContractError("bounded input exceeds its byte limit")
        opened_after = os.fstat(descriptor)
        if (
            (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns)
            != (opened_before.st_dev, opened_before.st_ino, opened_before.st_size, opened_before.st_mtime_ns)
            or stat.S_IMODE(opened_after.st_mode)
            != stat.S_IMODE(opened_before.st_mode)
            or (
                require_single_link
                and opened_after.st_nlink != opened_before.st_nlink
            )
        ):
            raise ContractError("bounded input changed while reading")
        if (
            reviewed_modes is not None
            and stat.S_IMODE(opened_after.st_mode) not in reviewed_modes
        ):
            raise ContractError("bounded input mode drifted while reading")
    finally:
        os.close(descriptor)
    named_after = os.stat(str(path), follow_symlinks=False)
    if (
        (named_after.st_dev, named_after.st_ino, named_after.st_size, named_after.st_mtime_ns)
        != (named_before.st_dev, named_before.st_ino, named_before.st_size, named_before.st_mtime_ns)
        or stat.S_IMODE(named_after.st_mode) != stat.S_IMODE(named_before.st_mode)
        or (
            require_single_link
            and named_after.st_nlink != named_before.st_nlink
        )
    ):
        raise ContractError("bounded input namespace changed after read")
    if (
        reviewed_modes is not None
        and stat.S_IMODE(named_after.st_mode) not in reviewed_modes
    ):
        raise ContractError("bounded input mode drifted after read")
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


def stage_a1_git_clone_contract(
    head: str,
    tree: str,
    public_branch: str = T12_PUBLIC_BRANCH,
) -> Dict[str, Any]:
    """Return the reviewed shell-free public-clone contract for one exact head."""
    require_string(head, "Git clone contract head", OID_RE)
    require_string(tree, "Git clone contract tree", OID_RE)
    if public_branch not in (T11_ACCEPTED_PUBLIC_BRANCH, T12_PUBLIC_BRANCH):
        raise ContractError("Git clone contract branch is not reviewed")
    repository_url = "https://github.com/{}.git".format(REPOSITORY)
    target = "<private-vm-repository>"
    prefix = [
        STAGE_A1_GIT_BINARY, "--no-replace-objects",
        "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
    ]
    umask_wrapper = [
        "/usr/bin/python3", "-I", "-c",
        STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT,
    ]
    return {
        "schema": "t11-git-clone-contract/v1",
        "authority": "reviewed-static-contract",
        "repository_url": repository_url,
        "branch": public_branch,
        "head": head,
        "tree": tree,
        "git_binary": STAGE_A1_GIT_BINARY,
        "git_binary_sha256": APPROVED_GIT_BINARY_SHA256,
        "shell": False,
        "process_umask": "0077",
        "umask_wrapper_argv": umask_wrapper,
        "environment": {
            "policy": "replace",
            "fixed": dict(STAGE_A1_GIT_FIXED_ENVIRONMENT),
            "dynamic": {
                "wrapper_input_HOME": (
                    "private-vm-absolute-empty-current-uid-mode-0700-no-follow"
                ),
                "git_child_HOME": "inherited-private-home-directory-descriptor",
            },
            "inherited_keys": [],
            "credential_helper": "disabled-by-argv",
            "ssh_agent": "absent",
        },
        "destination": "private-vm-disk",
        "host_repository_mounted": False,
        "argv_templates": [
            umask_wrapper + prefix + [
                "clone", "--no-checkout", "--single-branch", "--branch",
                public_branch, repository_url, target,
            ],
            umask_wrapper + prefix + [
                "-C", target, "checkout", "--detach", head,
            ],
            umask_wrapper + prefix + [
                "-C", target, "rev-parse", "--verify", "HEAD",
            ],
            umask_wrapper + prefix + [
                "-C", target, "rev-parse", "--verify", "HEAD^{tree}",
            ],
            umask_wrapper + prefix + [
                "-C", target, "status", "--porcelain=v1", "-z",
                "--untracked-files=all",
            ],
        ],
        "expected_outputs": {
            "head": head,
            "tree": tree,
            "status_porcelain_v1_z": "empty",
        },
    }


def stage_a1_git_clone_contract_sha256(
    head: str,
    tree: str,
    public_branch: str = T12_PUBLIC_BRANCH,
) -> str:
    return sha256_bytes(
        canonical_bytes(stage_a1_git_clone_contract(head, tree, public_branch))
    )


def expected_git_bootstrap_evidence() -> Dict[str, Any]:
    """Return the exact owner/controller-authored pre-clone Git trust anchor."""
    return {
        "schema": GIT_BOOTSTRAP_EVIDENCE_SCHEMA,
        "authority": "owner/controller-authored",
        "package_name": "git",
        "package_version": APPROVED_GIT_PACKAGE_VERSION,
        "package_architecture": "arm64",
        "install_status": "installed",
        "binary_sha256": APPROVED_GIT_BINARY_SHA256,
        "version_output": APPROVED_GIT_VERSION_OUTPUT,
        "controller_argv_sha256": STAGE_A1_CONTROLLER_ARGV_SHA256,
        "preclone_qualification_argv_sha256": (
            STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
        ),
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def not_run_git_bootstrap_evidence() -> Dict[str, Any]:
    """Return an exact sentinel that cannot be mistaken for qualification."""
    return {
        "schema": GIT_BOOTSTRAP_EVIDENCE_SCHEMA,
        "authority": "owner/controller-authored",
        "package_name": "not-run",
        "package_version": "not-run",
        "package_architecture": "not-run",
        "install_status": "not-run",
        "binary_sha256": "0" * 64,
        "version_output": "not-run",
        "controller_argv_sha256": STAGE_A1_CONTROLLER_ARGV_SHA256,
        "preclone_qualification_argv_sha256": (
            STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
        ),
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def validate_git_bootstrap_evidence(
    value: Any, *, allow_not_run: bool = False,
) -> Dict[str, Any]:
    """Accept only the exact pinned bootstrap or its explicit not-run sentinel."""
    if not isinstance(value, dict):
        raise ContractError("Git bootstrap evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "package_name", "package_version",
            "package_architecture", "install_status", "binary_sha256",
            "version_output", "controller_argv_sha256",
            "preclone_qualification_argv_sha256",
            "raw_stdout_recorded", "raw_stderr_recorded",
        ),
        "Git bootstrap evidence",
    )
    if value == expected_git_bootstrap_evidence():
        return value
    if allow_not_run and value == not_run_git_bootstrap_evidence():
        return value
    raise ContractError("Git bootstrap evidence is not the exact reviewed trust anchor")


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
    exact_keys(
        repository,
        ("head", "tree", "git_bootstrap", "git_clone_contract_sha256"),
        "Colima provider repository binding",
    )
    head = require_string(repository["head"], "Colima public head", OID_RE)
    tree = require_string(repository["tree"], "Colima public tree", OID_RE)
    if head == "0" * 40 or tree == "0" * 40:
        raise ContractError("Colima public repository binding cannot be a sentinel")
    validate_git_bootstrap_evidence(repository["git_bootstrap"])
    clone_contract_sha256 = require_string(
        repository["git_clone_contract_sha256"],
        "Colima Git clone contract digest", SHA256_RE,
    )
    if clone_contract_sha256 != stage_a1_git_clone_contract_sha256(head, tree):
        raise ContractError("Colima Git clone contract does not bind the exact head/tree")
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
        "repository_git_bootstrap": not_run_git_bootstrap_evidence(),
        "repository_git_bootstrap_runtime_match": False,
        "repository_git_clone_contract_sha256": "0" * 64,
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
        "git": {
            "package_name": "not-run",
            "package_version": "not-run",
            "package_architecture": "not-run",
            "install_status": "not-run",
            "binary_sha256": "0" * 64,
            "version_output": "not-run",
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
            "apparmor", "bubblewrap", "git", "controller", "smoke",
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
    allowed_bubblewrap_values = {
        "package_name": ("bubblewrap", "not-run"),
        "package_version": (
            APPROVED_BWRAP_PACKAGE_VERSION, "not-run", "unrecognized",
        ),
        "package_architecture": ("arm64", "not-run", "unrecognized"),
        "install_status": ("installed", "not-run"),
        "version_output": (
            APPROVED_BWRAP_VERSION_OUTPUT, "not-run", "unrecognized",
        ),
    }
    for field, allowed in allowed_bubblewrap_values.items():
        if bubblewrap[field] not in allowed:
            raise ContractError("Stage A.1 bubblewrap field is invalid")
    for field in ("binary_sha256", "help_sha256"):
        require_string(bubblewrap[field], "Stage A.1 bubblewrap digest", SHA256_RE)
    git = value["git"]
    if not isinstance(git, dict):
        raise ContractError("Stage A.1 Git evidence must be an object")
    exact_keys(
        git,
        (
            "package_name", "package_version", "package_architecture",
            "install_status", "binary_sha256", "version_output",
        ),
        "Stage A.1 Git evidence",
    )
    allowed_git_values = {
        "package_name": ("git", "not-run"),
        "package_version": (
            APPROVED_GIT_PACKAGE_VERSION, "not-run", "unrecognized",
        ),
        "package_architecture": ("arm64", "not-run", "unrecognized"),
        "install_status": ("installed", "not-run"),
        "version_output": (
            APPROVED_GIT_VERSION_OUTPUT, "not-run", "unrecognized",
        ),
    }
    for field, allowed in allowed_git_values.items():
        if git[field] not in allowed:
            raise ContractError("Stage A.1 Git field is invalid")
    require_string(git["binary_sha256"], "Stage A.1 Git digest", SHA256_RE)
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
        if git != {
            "package_name": "git",
            "package_version": APPROVED_GIT_PACKAGE_VERSION,
            "package_architecture": "arm64",
            "install_status": "installed",
            "binary_sha256": APPROVED_GIT_BINARY_SHA256,
            "version_output": APPROVED_GIT_VERSION_OUTPUT,
        }:
            raise ContractError("passing Stage A.1 Git boundary drifted")
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
        {"json_depth": 8, "json_nodes": 112, "json_string_bytes": 256},
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
        or result.stderr_overflow or result.stderr_size or not result.reaped
    ):
        return "UNCHECKABLE"
    try:
        lines = set(result.stdout.decode("utf-8", errors="strict").splitlines())
    except UnicodeDecodeError:
        return "UNCHECKABLE"
    required = {"bwrap (enforce)", "unpriv_bwrap (enforce)"}
    return "enforce" if required.issubset(lines) else "not-loaded"


def observe_stage_a1_git(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """Observe a bounded safe projection of the exact guest Git prerequisite."""
    package_result = bounded_capture(
        STAGE_A1_GIT_PACKAGE_QUERY_ARGV, root, env,
        timeout=15, stdout_limit=1024, stderr_limit=1024,
    )
    if (
        package_result.exit_code != 0 or package_result.timed_out
        or package_result.stdout_overflow or package_result.stderr_overflow
        or package_result.stderr_size or not package_result.reaped
    ):
        raise ContractError("Stage A.1 Git package observation is uncheckable")
    package_match = re.fullmatch(
        rb"installed\t([0-9A-Za-z.:+~_-]{1,128})\t"
        rb"([0-9A-Za-z][0-9A-Za-z-]{0,31})\n",
        package_result.stdout,
    )
    if package_match is None:
        raise ContractError("Stage A.1 Git package observation is malformed")
    observed_version = package_match.group(1).decode("ascii", errors="strict")
    observed_architecture = package_match.group(2).decode("ascii", errors="strict")
    _git_path, binary_sha256 = approved_provider_git_binding(
        require_digest=False,
    )
    if binary_sha256 != APPROVED_GIT_BINARY_SHA256:
        return {
            "package_name": "git",
            "package_version": (
                APPROVED_GIT_PACKAGE_VERSION
                if observed_version == APPROVED_GIT_PACKAGE_VERSION
                else "unrecognized"
            ),
            "package_architecture": (
                "arm64" if observed_architecture == "arm64" else "unrecognized"
            ),
            "install_status": "installed",
            "binary_sha256": binary_sha256,
            "version_output": "not-run",
        }
    version_result = bounded_capture(
        (STAGE_A1_GIT_BINARY, "--version"), root, env,
        timeout=15, stdout_limit=256, stderr_limit=1024,
    )
    if (
        version_result.exit_code != 0 or version_result.timed_out
        or version_result.stdout_overflow or version_result.stderr_overflow
        or not version_result.reaped
    ):
        raise ContractError("Stage A.1 Git binary observation is uncheckable")
    observed_output = version_result.stdout.decode("utf-8", errors="strict").strip()
    return {
        "package_name": "git",
        "package_version": (
            APPROVED_GIT_PACKAGE_VERSION
            if observed_version == APPROVED_GIT_PACKAGE_VERSION
            else "unrecognized"
        ),
        "package_architecture": (
            "arm64" if observed_architecture == "arm64" else "unrecognized"
        ),
        "install_status": "installed",
        "binary_sha256": binary_sha256,
        "version_output": (
            APPROVED_GIT_VERSION_OUTPUT
            if observed_output == APPROVED_GIT_VERSION_OUTPUT
            else "unrecognized"
        ),
    }


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
        apparmor_enabled_bytes = read_bounded_regular(
            STAGE_A1_APPARMOR_ENABLED, 16, max_advertised_bytes=65_536
        ).strip()
        if apparmor_enabled_bytes not in (b"Y", b"N"):
            return fallback
        apparmor_enabled = apparmor_enabled_bytes == b"Y"
        restriction_bytes = read_bounded_regular(
            STAGE_A1_APPARMOR_USERNS_RESTRICTION, 16,
            max_advertised_bytes=65_536,
        ).strip()
        if restriction_bytes not in (b"0", b"1"):
            return fallback
        restriction_status = "active" if restriction_bytes == b"1" else "inactive"
        source_sha = hash_regular_file(STAGE_A1_PROFILE_SOURCE, 1_048_576)
        installed_sha = hash_regular_file(STAGE_A1_PROFILE_INSTALLED, 1_048_576)
        package_result = bounded_capture(
            STAGE_A1_PACKAGE_QUERY_ARGV, root, env,
            timeout=15, stdout_limit=1024, stderr_limit=1024,
        )
        if (
            package_result.exit_code != 0 or package_result.timed_out
            or package_result.stdout_overflow or package_result.stderr_overflow
            or package_result.stderr_size or not package_result.reaped
        ):
            return fallback
        package_match = re.fullmatch(
            rb"installed\t([0-9A-Za-z.:+~_-]{1,128})\t"
            rb"([0-9A-Za-z][0-9A-Za-z-]{0,31})\n",
            package_result.stdout,
        )
        if package_match is None:
            return fallback
        observed_package_version = package_match.group(1).decode(
            "ascii", errors="strict"
        )
        observed_package_architecture = package_match.group(2).decode(
            "ascii", errors="strict"
        )
        package_version = (
            APPROVED_BWRAP_PACKAGE_VERSION
            if observed_package_version == APPROVED_BWRAP_PACKAGE_VERSION
            else "unrecognized"
        )
        package_architecture = (
            "arm64" if observed_package_architecture == "arm64"
            else "unrecognized"
        )
        git = observe_stage_a1_git(root, env)
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
            observed_version_output = version_result.stdout.decode(
                "utf-8", errors="strict"
            ).strip()
        except UnicodeDecodeError:
            return fallback
        version_output = (
            APPROVED_BWRAP_VERSION_OUTPUT
            if observed_version_output == APPROVED_BWRAP_VERSION_OUTPUT
            else "unrecognized"
        )
        load_status = _stage_a1_profile_load_status(
            bounded_capture(
                STAGE_A1_LOADED_PROFILES_ARGV, root, env,
                timeout=15, stdout_limit=262_144, stderr_limit=1024,
            )
        )
        if load_status == "UNCHECKABLE":
            return fallback
    except (ContractError, OSError, subprocess.SubprocessError, UnicodeError):
        return fallback
    if re.fullmatch(r"[0-9][0-9A-Za-z._+~-]{0,127}", uname.release) is None:
        return fallback
    guest = {
        "distribution_id": release["ID"],
        "distribution_version": release["VERSION_ID"],
        "distribution_codename": release["VERSION_CODENAME"],
        "kernel": uname.release,
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
        and git["package_version"] == APPROVED_GIT_PACKAGE_VERSION
        and git["package_architecture"] == "arm64"
        and git["binary_sha256"] == APPROVED_GIT_BINARY_SHA256
        and git["version_output"] == APPROVED_GIT_VERSION_OUTPUT
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
    elif (
        git["package_version"] != APPROVED_GIT_PACKAGE_VERSION
        or git["package_architecture"] != "arm64"
    ):
        status, reason = "fail", "git-package-drift"
    elif (
        git["binary_sha256"] != APPROVED_GIT_BINARY_SHA256
        or git["version_output"] != APPROVED_GIT_VERSION_OUTPUT
    ):
        status, reason = "fail", "git-binary-drift"
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
        "git": git,
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
    *, launcher_observer=None,
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
        **({"launcher_observer": launcher_observer} if launcher_observer is not None else {}),
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
    if any("status=pending" in x or "status=complete" in x or "Issue #25" in x for x in argv):
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
            "public_head", "public_tree", "repository_clean",
            "repository_git_bootstrap", "repository_git_bootstrap_runtime_match",
            "repository_git_clone_contract_sha256",
            "codex_version_output",
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
        "repository_git_clone_contract_sha256",
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
        "repository_git_bootstrap_runtime_match",
    ):
        require_bool(value[field], "containment provider " + field)
    validate_git_bootstrap_evidence(
        value["repository_git_bootstrap"], allow_not_run=True,
    )
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
        if (
            not value["native_architecture"]
            or not value["repository_clean"]
            or not value["repository_git_bootstrap_runtime_match"]
            or value["repository_git_bootstrap"] != expected_git_bootstrap_evidence()
        ):
            raise ContractError("passing containment provider evidence lacks provider-isolation facts")
        if value["guest_os"] != "Linux" or not isinstance(value["guest_kernel"], str) or re.fullmatch(r"[0-9A-Za-z._+~-]{1,128}", value["guest_kernel"]) is None:
            raise ContractError("passing containment provider guest platform is invalid")
        if value["profile_name"] != "t11-e2e-{}-01".format(value["public_head"][:12]):
            raise ContractError("containment provider profile/public-head binding drifted")
        clone_branches = (
            (T11_ACCEPTED_PUBLIC_BRANCH, T12_PUBLIC_BRANCH)
            if allow_fixture
            else (T12_PUBLIC_BRANCH,)
        )
        expected_clone_digests = {
            stage_a1_git_clone_contract_sha256(
                value["public_head"], value["public_tree"], clone_branch,
            )
            for clone_branch in clone_branches
        }
        if value["repository_git_clone_contract_sha256"] not in expected_clone_digests:
            raise ContractError("containment provider clone contract binding drifted")
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
        "repository": {
            "head": evidence["public_head"],
            "tree": evidence["public_tree"],
            "git_bootstrap": dict(evidence["repository_git_bootstrap"]),
            "git_clone_contract_sha256": evidence[
                "repository_git_clone_contract_sha256"
            ],
        },
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


def validate_shell_environment_evidence(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("shell environment evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "status", "reason_code",
            "unexpected_key_count", "unexpected_key_names_sha256",
            "secret_shaped_key_count",
        ),
        "shell environment evidence",
    )
    if (
        value["schema"] != "t11-shell-environment-evidence/v1"
        or value["authority"] != "adapter-authored"
        or value["reason_code"] not in SHELL_ENVIRONMENT_REASON_CODES
    ):
        raise ContractError("shell environment evidence identity is invalid")
    expected_status = (
        "pass" if value["reason_code"] == "none" else
        "not-run" if value["reason_code"] == "not-run" else
        "UNCHECKABLE" if value["reason_code"] in SHELL_ENVIRONMENT_UNCHECKABLE_REASONS else
        "fail"
    )
    if value["status"] != expected_status:
        raise ContractError("shell environment evidence status/reason drifted")
    count = value["unexpected_key_count"]
    secret_count = value["secret_shaped_key_count"]
    digest = value["unexpected_key_names_sha256"]
    if (
        not isinstance(count, int) or isinstance(count, bool)
        or not 0 <= count <= MAX_SHELL_ENVIRONMENT_ENTRIES
        or not isinstance(secret_count, int) or isinstance(secret_count, bool)
        or not 0 <= secret_count <= count
        or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
    ):
        raise ContractError("shell environment evidence summary is invalid")
    empty_digest = sha256_bytes(canonical_bytes([]))
    if value["status"] in ("not-run", "UNCHECKABLE"):
        if (count, secret_count, digest) != (0, 0, "0" * 64):
            raise ContractError("unobserved shell environment contains claims")
    elif count == 0 and digest != empty_digest:
        raise ContractError("empty shell environment summary digest drifted")
    elif count > 0 and digest in ("0" * 64, empty_digest):
        raise ContractError("non-empty shell environment summary digest is invalid")
    if value["reason_code"] == "unexpected-key-set" and (count < 1 or secret_count != 0):
        raise ContractError("unexpected shell key classification is invalid")
    if value["reason_code"] == "secret-shaped-key" and secret_count < 1:
        raise ContractError("secret-shaped shell key classification is invalid")
    if value["status"] == "pass" and (count != 0 or secret_count != 0):
        raise ContractError("passing shell environment contains unexpected keys")
    return value


def validate_network_sandbox_evidence(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("network sandbox evidence must be an object")
    exact_keys(
        value,
        (
            "schema", "authority", "status", "reason_code",
            "unsandboxed_control_accepted", "unsandboxed_control_closed",
            "parent_netns_sha256", "sandbox_netns_sha256", "netns_different",
            "network_marker_status", "sandbox_connect_status",
            "sandbox_connect_errno", "process_cleanup_status", "process_reaped",
            "raw_stdout_recorded", "raw_stderr_recorded",
        ),
        "network sandbox evidence",
    )
    if (
        value["schema"] != "t11-network-sandbox-evidence/v1"
        or value["authority"] != "adapter-authored"
        or value["reason_code"] not in NETWORK_SANDBOX_REASON_CODES
        or value["status"] not in RUNTIME_LANE_STATES
    ):
        raise ContractError("network sandbox evidence identity is invalid")
    expected_status = (
        "pass" if value["reason_code"] == "none" else
        "not-run" if value["reason_code"] == "not-run" else
        "fail" if value["reason_code"] in NETWORK_SANDBOX_FAIL_REASONS else
        "UNCHECKABLE"
    )
    if value["status"] != expected_status:
        raise ContractError("network sandbox evidence status/reason drifted")
    for field in (
        "unsandboxed_control_accepted", "unsandboxed_control_closed",
        "netns_different", "process_reaped", "raw_stdout_recorded",
        "raw_stderr_recorded",
    ):
        require_bool(value[field], "network sandbox " + field)
    if value["raw_stdout_recorded"] is not False or value["raw_stderr_recorded"] is not False:
        raise ContractError("raw network probe output must not be recorded")
    for field in ("parent_netns_sha256", "sandbox_netns_sha256"):
        require_string(value[field], "network namespace digest", SHA256_RE)
    derived_different = (
        value["parent_netns_sha256"] != "0" * 64
        and value["sandbox_netns_sha256"] != "0" * 64
        and value["parent_netns_sha256"] != value["sandbox_netns_sha256"]
    )
    if value["netns_different"] is not derived_different:
        raise ContractError("network namespace comparison drifted")
    if value["network_marker_status"] not in ("exact-1", "missing", "mismatch", "not-run", "UNCHECKABLE"):
        raise ContractError("network marker classification is invalid")
    if value["sandbox_connect_status"] not in ("denied", "succeeded", "not-run", "UNCHECKABLE"):
        raise ContractError("sandbox connection classification is invalid")
    if value["sandbox_connect_errno"] not in (*APPROVED_NETWORK_DENIAL_ERRNOS, "none", "not-run", "unapproved"):
        raise ContractError("sandbox denial classification is invalid")
    if value["process_cleanup_status"] not in RUNTIME_LANE_STATES:
        raise ContractError("network probe cleanup classification is invalid")
    cleanup_pair = (value["process_cleanup_status"], value["process_reaped"])
    if cleanup_pair not in {
        ("pass", True), ("UNCHECKABLE", False), ("not-run", False),
    }:
        raise ContractError("network cleanup/reap facts are contradictory")
    if value["unsandboxed_control_closed"] and not value["unsandboxed_control_accepted"]:
        raise ContractError("network control close claim lacks acceptance")
    marker = value["network_marker_status"]
    connection = value["sandbox_connect_status"]
    denial = value["sandbox_connect_errno"]
    if (
        (connection == "succeeded" and denial != "none")
        or (
            connection == "denied"
            and denial not in (*APPROVED_NETWORK_DENIAL_ERRNOS, "unapproved")
        )
        or (connection == "UNCHECKABLE" and denial != "unapproved")
        or (connection == "not-run" and denial != "not-run")
    ):
        raise ContractError("network connection/errno facts are contradictory")

    zero = "0" * 64
    parent_known = value["parent_netns_sha256"] != zero
    sandbox_known = value["sandbox_netns_sha256"] != zero
    control = (
        value["unsandboxed_control_accepted"],
        value["unsandboxed_control_closed"],
    )
    unobserved_child = (
        not sandbox_known
        and not value["netns_different"]
        and marker == "UNCHECKABLE"
        and connection == "UNCHECKABLE"
        and denial == "unapproved"
    )
    reason = value["reason_code"]
    if cleanup_pair == ("not-run", False) and reason != "not-run":
        raise ContractError("network cleanup not-run is reserved for not-run evidence")
    if reason == "not-run":
        expected = {
            "unsandboxed_control_accepted": False,
            "unsandboxed_control_closed": False,
            "parent_netns_sha256": zero,
            "sandbox_netns_sha256": zero,
            "netns_different": False,
            "network_marker_status": "not-run",
            "sandbox_connect_status": "not-run",
            "sandbox_connect_errno": "not-run",
            "process_cleanup_status": "not-run",
            "process_reaped": False,
        }
        if any(value[key] != expected_value for key, expected_value in expected.items()):
            raise ContractError("not-run network sandbox evidence contains claims")
    elif reason == "parent-netns-unavailable":
        if control != (False, False) or parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            raise ContractError("parent namespace failure facts are contradictory")
    elif reason in {
        "control-unavailable", "control-not-accepted", "control-peer-mismatch",
    }:
        if control != (False, False) or not parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            raise ContractError("control failure facts are contradictory")
    elif reason == "control-not-closed":
        if control != (True, False) or not parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            raise ContractError("control close failure facts are contradictory")
    elif reason == "observation-uncheckable":
        pre_observation = (
            control == (False, False) and not parent_known
            and cleanup_pair == ("UNCHECKABLE", False)
        )
        post_control = (
            control == (True, True) and parent_known
            and cleanup_pair in {("UNCHECKABLE", False), ("pass", True)}
        )
        if not unobserved_child or not (pre_observation or post_control):
            raise ContractError("uncheckable observation facts are contradictory")
    elif reason in {
        "sandbox-netns-unavailable", "process-nonzero", "process-timeout",
        "output-overflow", "process-not-reaped", "malformed-probe-output",
    }:
        if control != (True, True) or not parent_known or not unobserved_child:
            raise ContractError("post-spawn network failure facts are contradictory")
        if reason in {
            "sandbox-netns-unavailable", "process-nonzero",
            "malformed-probe-output",
        } and cleanup_pair != ("pass", True):
            raise ContractError("reaped network failure lost cleanup evidence")
        if reason == "process-not-reaped" and cleanup_pair != ("UNCHECKABLE", False):
            raise ContractError("unreaped network failure claims cleanup")
        if reason in {"process-timeout", "output-overflow"} and cleanup_pair not in {
            ("pass", True), ("UNCHECKABLE", False),
        }:
            raise ContractError("bounded network failure cleanup facts are invalid")
    else:
        if control != (True, True) or not parent_known or not sandbox_known or cleanup_pair != ("pass", True):
            raise ContractError("observed network result facts are incomplete")
        if (
            marker not in ("exact-1", "missing", "mismatch")
            or connection not in ("denied", "succeeded", "UNCHECKABLE")
        ):
            raise ContractError("observed network classifications are invalid")
        if reason == "none" and not (
            value["netns_different"] and marker == "exact-1"
            and connection == "denied"
            and denial in APPROVED_NETWORK_DENIAL_ERRNOS
        ):
            raise ContractError("passing network sandbox evidence is incomplete")
        if reason == "netns-not-separated" and value["netns_different"]:
            raise ContractError("network namespace equality reason drifted")
        if reason in {
            "network-marker-missing", "network-marker-mismatch",
            "sandbox-connection-succeeded", "socket-creation-unavailable",
            "unapproved-denial-errno",
        } and not value["netns_different"]:
            raise ContractError("network failure lacks namespace separation")
        expected_marker = {
            "network-marker-missing": "missing",
            "network-marker-mismatch": "mismatch",
        }.get(reason)
        if expected_marker is not None and marker != expected_marker:
            raise ContractError("network marker reason/fact drifted")
        if reason in {
            "sandbox-connection-succeeded", "socket-creation-unavailable",
            "unapproved-denial-errno",
        } and marker != "exact-1":
            raise ContractError("network connection reason lacks exact marker")
        expected_connection = {
            "sandbox-connection-succeeded": ("succeeded", "none"),
            "socket-creation-unavailable": ("UNCHECKABLE", "unapproved"),
            "unapproved-denial-errno": ("denied", "unapproved"),
        }.get(reason)
        if expected_connection is not None and (connection, denial) != expected_connection:
            raise ContractError("network connection reason/fact drifted")
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
            "shell_environment_behavior", "network_sandbox_behavior",
            "bubblewrap_prerequisite", "sandbox_housekeeping",
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
    shell_evidence = validate_compatibility_shell(
        evidence["shell_environment_behavior"]
    )
    network_evidence = validate_compatibility_network(
        evidence["network_sandbox_behavior"]
    )
    prerequisite_evidence = validate_stage_a1_prerequisite_evidence(
        evidence["bubblewrap_prerequisite"]
    )
    containment_evidence = validate_containment_provider_evidence(
        evidence["containment_provider"], allow_fixture=allow_fixture,
    )
    housekeeping = validate_compatibility_housekeeping(evidence["sandbox_housekeeping"])
    observed_bindings = []
    for record in (shell_evidence, housekeeping):
        if record["observation_binding"] is not None:
            observed_bindings.append(record["observation_binding"])
    if network_evidence["observation"] is not None:
        observed_bindings.append(network_evidence["observation"]["binding"])
    if observed_bindings:
        if containment_evidence["status"] != "pass":
            raise ContractError("compatibility observations lack a validated provider")
        expected_provider_digest = compatibility_provider_digest(containment_evidence, allow_fixture=allow_fixture)
        for binding in observed_bindings:
            if (binding["head"] != containment_evidence["public_head"]
                    or binding["tree"] != containment_evidence["public_tree"]
                    or binding["provider_attempt_sha256"] != expected_provider_digest
                    or binding != observed_bindings[0]):
                raise ContractError("compatibility same-attempt/head/tree binding drifted")
        observed_ms = int(datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
        for started, finished in compatibility_observation_windows(profile):
            # Native timestamps have whole-second precision; observations
            # may finish inside that final second, never after it.
            if not observed_ms - COMPATIBILITY_MAX_AGE_MS <= started <= finished <= observed_ms + 999:
                raise ContractError("nested compatibility evidence is outside the native observation window")
    if shell_evidence["status"] == "pass":
        qualified_bwrap = prerequisite_evidence["bubblewrap"]
        if (prerequisite_evidence["status"] != "pass"
                or qualified_bwrap["binary_sha256"] != shell_evidence["launcher"]["binary_sha256"]
                or qualified_bwrap["help_sha256"] != shell_evidence["launcher"]["help_sha256"]):
            raise ContractError("executed launcher and prerequisite bindings disagree")
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
    if (
        lanes["shell_environment_status"] != caps["shell_environment_probe"]
        or lanes["shell_environment_status"] != shell_evidence["status"]
    ):
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
        and housekeeping["status"] == "pass"
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


PROFILE_STABLE_ROOTS = (
    "schema", "repository", "scope", "status", "reason", "platform", "client",
    "capabilities", "auth", "request", "shell_environment", "live_run_allowed",
)
PROFILE_STABLE_EVIDENCE = (
    "configuration_intent", "exact_worker_argv",
    "bubblewrap_prerequisite", "lane_statuses",
)
PROFILE_FRESH_EVIDENCE = ("diagnostic_health", "network_sandbox_behavior", "shell_environment_behavior", "sandbox_housekeeping")
PROFILE_PROVIDER_STABLE = (
    "schema", "authority", "codex_authenticated_attestation", "status",
    "provider_kind", "vm_backend", "architecture", "native_architecture",
    "guest_os", "guest_kernel", "host_mount_count", "host_mount_classifications",
    "all_host_mounts_read_only", "provider_cache_only", "host_sensitive_mounts_absent",
    "unapproved_mounts_absent", "ssh_agent_forwarding", "dot_ssh_public_key_loading",
    "user_ssh_config_modified", "public_head", "public_tree", "repository_clean",
    "repository_git_bootstrap", "repository_git_bootstrap_runtime_match",
    "repository_git_clone_contract_sha256", "codex_version_output",
    "approved_archive_sha256", "observed_archive_sha256", "extracted_binary_sha256",
)
PROFILE_PROVIDER_ATTEMPT = (
    "profile_name", "created_at", "provider_configuration_sha256",
    "effective_mount_inventory_sha256", "provider_cache_mount_sha256",
    "provider_cache_guest_mountpoint_sha256", "vm_instance_identity_sha256",
    "runtime_root_binding_sha256", "dedicated_codex_home_binding_sha256",
    "control_plane", "lifecycle",
)


def compatibility_observation_windows(profile):
    evidence = profile["evidence"]
    windows = []
    shell = evidence["shell_environment_behavior"]
    if shell["window"] is not None:
        windows.append((shell["window"]["started_ms"], shell["window"]["classified_ms"]))
    network = evidence["network_sandbox_behavior"]
    if network["context"] is not None:
        windows.append((network["context"]["observation_started_ms"], network["classified_at_ms"]))
    housekeeping = evidence["sandbox_housekeeping"]
    if housekeeping["window"] is not None:
        windows.append((housekeeping["window"]["started_ms"], housekeeping["window"]["finished_ms"]))
    return windows


def compare_runtime_profiles(
    supplied: Dict[str, Any], fresh: Dict[str, Any],
    observation_started_at: datetime.datetime,
    observation_finished_at: datetime.datetime,
    *, allow_fixture: bool = False, now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Compare complete native profiles without normalizing away fresh proof.

    The caller must own the actual new sensor invocation. Timestamps or a
    changed namespace alone cannot authenticate an arbitrary caller artifact.
    """
    for profile in (supplied, fresh):
        validate_runtime_profile(profile, allow_fixture=allow_fixture)
        exact_keys(profile, (*PROFILE_STABLE_ROOTS, "observed_at", "evidence"), "classified profile")
        exact_keys(profile["evidence"], (*PROFILE_STABLE_EVIDENCE, *PROFILE_FRESH_EVIDENCE, "containment_provider"), "classified profile evidence")
        exact_keys(profile["evidence"]["containment_provider"], (*PROFILE_PROVIDER_STABLE, *PROFILE_PROVIDER_ATTEMPT), "classified provider")
        if profile["status"] != "match" or profile["live_run_allowed"] is not True:
            raise ContractError("profile comparison requires independently passing live profiles")
        if not allow_fixture and profile["scope"] != "exact-head-live-sensor":
            raise ContractError("profile comparison requires the exact live sensor")
    for key in PROFILE_STABLE_ROOTS:
        if supplied[key] != fresh[key]:
            raise ContractError("stable runtime profile binding drifted")
    for key in PROFILE_STABLE_EVIDENCE:
        if supplied["evidence"][key] != fresh["evidence"][key]:
            raise ContractError("stable runtime evidence binding drifted")
    for key in ("source_contract_sha256",):
        if supplied["evidence"]["shell_environment_behavior"][key] != fresh["evidence"]["shell_environment_behavior"][key]:
            raise ContractError("stable shell source binding drifted")
    for key in ("binary_sha256", "help_sha256"):
        if supplied["evidence"]["shell_environment_behavior"]["launcher"][key] != fresh["evidence"]["shell_environment_behavior"]["launcher"][key]:
            raise ContractError("stable executed launcher binding drifted")
    for key in (*PROFILE_PROVIDER_STABLE, *PROFILE_PROVIDER_ATTEMPT):
        if supplied["evidence"]["containment_provider"][key] != fresh["evidence"]["containment_provider"][key]:
            raise ContractError("stable or same-attempt provider binding drifted")
    # Every fresh network/doctor predicate was checked above by the complete
    # native validator. Do not require cross-observation namespace novelty.
    def timestamp(value: str) -> datetime.datetime:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

    current = now or datetime.datetime.now(datetime.timezone.utc)
    dates = (observation_started_at, observation_finished_at, current)
    if any(not isinstance(value, datetime.datetime) or value.utcoffset() != datetime.timedelta(0) for value in dates):
        raise ContractError("profile sensor invocation window is invalid")
    start = observation_started_at.replace(microsecond=0)
    finish = observation_finished_at.replace(microsecond=0)
    old_time, new_time = timestamp(supplied["observed_at"]), timestamp(fresh["observed_at"])
    if (
        not old_time < new_time
        or not start <= new_time <= finish <= current
        or (current - old_time).total_seconds() > 900
        or (current - finish).total_seconds() > 300
    ):
        raise ContractError("fresh semantic runtime sensor observation is stale, replayed, or outside its invocation")
    old_binding = supplied["evidence"]["sandbox_housekeeping"]["observation_binding"]
    fresh_binding = fresh["evidence"]["sandbox_housekeeping"]["observation_binding"]
    if old_binding["observation_id_sha256"] == fresh_binding["observation_id_sha256"]:
        raise ContractError("fresh compatibility observation identity was replayed")
    start_ms, finish_ms = int(start.timestamp() * 1000), int(finish.timestamp() * 1000) + 999
    if any(not start_ms <= left <= right <= finish_ms for left, right in compatibility_observation_windows(fresh)):
        raise ContractError("fresh nested compatibility evidence is outside its actual sensor invocation")
    return runtime_profile_comparison_record(supplied, fresh, observation_started_at, observation_finished_at, "pass")


def runtime_profile_comparison_record(
    supplied: Dict[str, Any], fresh: Dict[str, Any],
    observation_started_at: datetime.datetime,
    observation_finished_at: datetime.datetime, status_value: str,
) -> Dict[str, Any]:
    # Native shape validation alone does not make arbitrary bounded prose safe
    # to export. Refuse known private-path/credential forms in either original.
    pending: List[Any] = [supplied, fresh]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and (
            PRIVATE_PATH_RE.search(item)
            or any(pattern.search(item) for pattern in SENSITIVE_VALUE_PATTERNS)
        ):
            raise ContractError("runtime profile observation cannot be safely exported")
    # A canonical roundtrip prevents caller mutation after validation. Native
    # artifacts stay unchanged; this supplemental record retains both originals.
    return {
        "schema": "t12-runtime-profile-comparison/v1",
        "authority": "adapter-authored",
        "status": status_value,
        "stable_bindings": "exact" if status_value == "pass" else "not-established",
        "same_attempt_bindings": "exact" if status_value == "pass" else "not-established",
        "fresh_lanes": "independently-validated" if status_value == "pass" else "comparison-non-success",
        "supplied_profile": json.loads(canonical_bytes(supplied)),
        "fresh_profile": json.loads(canonical_bytes(fresh)),
        "supplied_profile_sha256": sha256_bytes(canonical_bytes(supplied)),
        "fresh_profile_sha256": sha256_bytes(canonical_bytes(fresh)),
        "sensor_started_at": observation_started_at.isoformat(),
        "sensor_finished_at": observation_finished_at.isoformat(),
    }


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
        raise ContractError(
            "execution result worker is not exactly one logical invocation "
            "with a bounded successful process result"
        )
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


def extract_static_role(
    repository_root: Path,
    require_private_projection: bool = False,
) -> str:
    if type(require_private_projection) is not bool:
        raise ContractError("static role projection policy is invalid")
    role_path = repository_root / STATIC_ROLE_PATH
    data = read_bounded_regular(
        role_path, 65_536,
        allowed_modes=(0o600,) if require_private_projection else (0o600, 0o644),
        require_single_link=True,
    )
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


class ProcessSpawnError(ContractError):
    """A fixed safe failure raised only at the direct Popen boundary."""


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

    def __init__(self, leader_pid: int, env: Mapping[str, str], launcher_observer=None):
        self.leader_pid = leader_pid
        self.env = dict(env)
        self.known: Dict[int, Tuple[int, int, str]] = {}
        self.failure: Optional[str] = None
        self.launcher_observer = launcher_observer
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
        if self.launcher_observer is not None:
            # Read-only optional corroboration. Its failures never interrupt
            # this tracker's established identity-bound cleanup path.
            try:
                self.launcher_observer.observe(self.leader_pid, leader_known, table)
            except Exception:
                self.launcher_observer.uncheckable = True

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


_PROFILE_REAP_OBSERVATION = threading.local()


def run_bounded_process(*args, **kwargs) -> ProcessResult:
    """Observe existing profile calls without altering subprocess ownership."""
    sample = getattr(_PROFILE_REAP_OBSERVATION, "sample", None)
    if sample is not None:
        sample["requested"] += 1
    try:
        result = _run_bounded_process(*args, **kwargs)
    except BaseException:
        if sample is not None:
            sample["unconfirmed"] += 1
        raise
    if sample is not None:
        if type(result.reaped) is bool and result.reaped:
            sample["reaped"] += 1
        else:
            sample["unconfirmed"] += 1
    return result


def _run_bounded_process(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin_bytes: bytes,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    grace_seconds: float = 2.0,
    capture_stderr: bool = False,
    launcher_observer=None,
) -> ProcessResult:
    require_runtime_fs_capabilities()
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise ContractError("process argv is invalid")
    if len(stdin_bytes) > MAX_STDIN_BYTES:
        raise ContractError("process stdin exceeds its limit")
    if any(SECRET_NAME_RE.search(name) for name in env):
        raise ContractError("minimal environment contains a forbidden secret-like name")
    try:
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
    except OSError:
        raise ProcessSpawnError("bounded process could not start") from None
    tracker = DescendantTracker(process.pid, env, launcher_observer) if launcher_observer is not None else DescendantTracker(process.pid, env)
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
            chunk = stream.read(min(65_536, max(limit, 1)))
            if not chunk:
                return
            sizes[name] += len(chunk)
            remaining = max(0, limit - len(buffers[name]))
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


def approved_provider_git_binding(
    *, require_digest: bool = True,
) -> Tuple[Path, str]:
    """Bind the provider Git to a root-owned immutable-by-guest namespace."""
    for raw in ("/usr", "/usr/bin"):
        info = os.stat(raw, follow_symlinks=False)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise ContractError("approved provider Git parent binding is unsafe")
    path = Path(STAGE_A1_GIT_BINARY)
    info = os.stat(str(path), follow_symlinks=False)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
        or not stat.S_IMODE(info.st_mode) & 0o111
        or info.st_nlink < 1
    ):
        raise ContractError("approved provider Git executable binding is unsafe")
    digest = hash_regular_file(path)
    if require_digest and digest != APPROVED_GIT_BINARY_SHA256:
        raise ContractError("approved provider Git executable digest drifted")
    return path, digest


def run_approved_provider_git(
    root: Path,
    arguments: Sequence[str],
    env: Mapping[str, str],
    expected: Sequence[int] = (0,),
    max_bytes: int = 262_144,
) -> bytes:
    """Run only the fixed root-owned Git, revalidating it before every use."""
    git, _digest = approved_provider_git_binding()
    result = run_bounded_process(
        [
            str(git), "--no-replace-objects", "-c",
            "core.hooksPath=/dev/null", "-C", str(root),
        ] + list(arguments),
        root, env, b"", 30, max_bytes, max_bytes, 2,
    )
    if (
        result.timed_out or result.stdout_overflow or result.stderr_overflow
        or not result.reaped or result.exit_code not in expected
    ):
        raise ContractError("bounded approved provider Git operation failed")
    return result.stdout


def git_executable_evidence(
    root: Path, env: Mapping[str, str], *, require_approved: bool = False,
) -> Tuple[str, str]:
    git = resolve_executable_from_path("git", env)
    if git is None:
        raise ContractError("Git executable is unavailable from the explicit PATH")
    if require_approved:
        if str(git) != STAGE_A1_GIT_BINARY:
            raise ContractError("PATH-resolved Git is outside the approved namespace")
        git, digest = approved_provider_git_binding()
    else:
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
    if require_approved and version != APPROVED_GIT_VERSION_OUTPUT:
        raise ContractError("Git executable version is outside the approved trust anchor")
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
    if init.exit_code != 0 or init.signal_number is not None or init.timed_out or init.stdout_overflow or init.stderr_overflow or init.reaped is not True:
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


NATIVE_BUILTIN_ROOT = ".codex/skills/.system"
NATIVE_BUILTIN_MARKER = NATIVE_BUILTIN_ROOT + "/.codex-system-skills.marker"
# Exact untransformed embedded samples tree dd83abff11d7be56fc9fc10330fc686d1a48ab01.
NATIVE_BUILTIN_ASSETS = {
    "imagegen/LICENSE.txt": (10776, "4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9"),
    "imagegen/SKILL.md": (19201, "681ddb4ad6d06a2acc78a3535b583f8d0c1ea800ecda3d56370d3310fd2cd4ba"),
    "imagegen/agents/openai.yaml": (275, "9ca574af14580dc7a2a3dc37a1796d17f93cb8850be66501f0799ef8603e9dc0"),
    "imagegen/assets/imagegen-small.svg": (2889, "cff5f34f57ff60b3ee92eaedd17b15e96dd4b9e776df3e78936c9e00d42be294"),
    "imagegen/assets/imagegen.png": (1711, "95952f644064eb9e890f98d8db07216347186526e4c41ad66d3420629eb86e20"),
    "imagegen/references/cli.md": (9655, "ecfc2e09261a0feb3482517a5fa0ff410cb7d1958e3cbd2ac6b61586f5b81405"),
    "imagegen/references/codex-network.md": (1779, "c88298ca4481f6116a16fa7987434fc977f8b311c1bbc0c3d862ffd0c5981148"),
    "imagegen/references/image-api.md": (6072, "dc975d7af8a4888967251a0276014b4a71ea30455294944b762256373ce3e569"),
    "imagegen/references/prompting.md": (8282, "b210b051c775860267080941eba968212bf0ac7fce581d75c5dcc217d8293f8b"),
    "imagegen/references/sample-prompts.md": (17617, "70474177d151855b175c6133de2aae1d90b7f146b0dab50ec830972c47d72183"),
    "imagegen/scripts/image_gen.py": (34271, "35e8f9fa47deca111e46c63c4ac2008e09198ef664c0926a9dfdcd6745aa37ed"),
    "imagegen/scripts/remove_chroma_key.py": (13836, "3f7b9b14ad5c90f37618bc1c16a039a2076abca12ddc41b3ae470e2b1cad6c0e"),
    "openai-docs/LICENSE.txt": (10776, "4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9"),
    "openai-docs/SKILL.md": (5446, "7cb8fa1b2a0c635b5c61ffe1da7b8594a7ea0fce5b71e8d523e2025d88b2a05e"),
    "openai-docs/agents/openai.yaml": (370, "44b9efac6be1bae32d869aa2942fecbe4dcae82682ee03e4120f2f9b7d4658ec"),
    "openai-docs/assets/openai-small.svg": (1091, "45be1f0757eb18889eefb1e7db79668ef46a275dc4e0e78e8df5ebd7f6cdeadc"),
    "openai-docs/assets/openai.png": (1429, "156cc84d7332bfe95b310350bd470b690d22aa33d65340cc6c2e06022946194c"),
    "openai-docs/references/codex-self-knowledge.md": (7417, "8c8fb00e6e5cb1977924f5164684a6095427fa828bbc765225f17d9aeb79a912"),
    "openai-docs/references/latest-model.md": (2094, "f25e351e522dd6e30e82d482f31f44c992e794b11031cdcb6ac7c0e6b20c9d5d"),
    "openai-docs/references/mcp-diagnostics.md": (2318, "49bbd2f73df7bbd7f86c80425dea4da2d301c22046080399a36bfc0ca49509e9"),
    "openai-docs/references/model-migration.md": (5054, "5f20c38fbbb10319767b216d91ba74bae49c68fc1bfd6d1abd7c9b4cc9cb9ab0"),
    "openai-docs/references/model-selection.md": (1344, "ba2d164abbca30435a460a0bc3a7d82398dce2bdf092705c98ba55b3f3af38a8"),
    "openai-docs/references/official-docs.md": (3337, "7962f2dce55089b93bde4115bb89fd42f20993c1597a2b13edd4956f463875b9"),
    "openai-docs/references/prompting-guide.md": (15747, "db913884cfe0fabf29bee1a139918f56e299decfa0a14d61c48596f23f76621d"),
    "openai-docs/references/upgrade-guide.md": (1050, "ed1b75a89b8ec4d67787774ef6c4e8b98eace16c63348f42e969e6ffa67cb656"),
    "openai-docs/references/upgrading-to-gpt-5p6-sol.md": (23093, "9a918a0c8dd051d574f2fd0309201afa8a9b9c08241c11ca1fb0ac2f4724e7ac"),
    "openai-docs/scripts/fetch-codex-manual.mjs": (16085, "f53eb6d2f286e9efcc397e8bee93a938e37296c90953e4e06e94899ef1b6c363"),
    "openai-docs/scripts/resolve-latest-model-info": (1038, "7354dbb030ca0736dd633a7ca1b930cf640abd40370725dea3a458cb51d49523"),
    "openai-docs/scripts/resolve-latest-model-info.cjs": (3937, "eeb1bb486018e16b37edfc06b1a37179dbc672982d501040d4f7142f29dd2e64"),
    "plugin-creator/SKILL.md": (11467, "71b95b8219644f95d633721e7f7cd3c469edfc8fe50f8415d400dfb2d74bc7b9"),
    "plugin-creator/agents/openai.yaml": (339, "fecaf35d692bd3d33d1a065648258d12e393afa9055d78adf6e57b42f4142f6d"),
    "plugin-creator/assets/plugin-creator-small.svg": (1319, "6591bf8ea9bb9435890dbdea299e0d2bd05f3aa893a335d26e4c535e93c8e7fb"),
    "plugin-creator/assets/plugin-creator.png": (1563, "a4024b0306ddb05847e1012879d37aaf1e658205199da596f5145ed7a88d9162"),
    "plugin-creator/references/installing-and-updating.md": (6000, "91c4781d48568fcc708b45566b08fb610ad1c88672720ae512f9525a1cf9cb20"),
    "plugin-creator/references/plugin-json-spec.md": (9179, "eeb640130f69636affaa299d4170d5a7ae6a0ff978296ddf75c409ce6dd87b91"),
    "plugin-creator/scripts/create_basic_plugin.py": (11495, "46f532721079f6de6443f30f9362d77f1d879f57c0559250ef9433867414eb93"),
    "plugin-creator/scripts/identifier_validation.py": (784, "a6d51ce4a9a7e8f85626ff5808a467a67574e7f8cdf1167ffb467c5f67e57223"),
    "plugin-creator/scripts/read_marketplace_name.py": (1644, "ba24e6d91eed6f778bde022a967be335c6253983b5ecd1c5e30c8483385887fd"),
    "plugin-creator/scripts/update_plugin_cachebuster.py": (3043, "97c5ecab5ad85d871f0ebfc9bdf25d4b9e1a1680128fd3deb18a8c64f15f85c5"),
    "plugin-creator/scripts/validate_plugin.py": (21533, "6ff4bc1cc8ca94827c30c8299951efdac900ff38a5069c03e9a6554fc194a723"),
    "review-agent/SKILL.md": (2661, "07079efd0dc76f05fade424e5dfb048dce1de2df7626e1a4f56292a4f3f92228"),
    "review-agent/agents/openai.yaml": (252, "4d867a46d15e36ac880176484aae160f59855340c6059b2ea6ab9fbc9af084de"),
    "skill-creator/SKILL.md": (15311, "6656e54755638e8efcf275a472b9672eaa8a9a1b9e59dc210e275b03b59e1e66"),
    "skill-creator/agents/openai.yaml": (183, "d07d21b93fcf3d4dc8d9a3399c05fc226a49a333a96d3e1c68b451b8dd9eade6"),
    "skill-creator/assets/skill-creator-small.svg": (1319, "6591bf8ea9bb9435890dbdea299e0d2bd05f3aa893a335d26e4c535e93c8e7fb"),
    "skill-creator/assets/skill-creator.png": (1563, "a4024b0306ddb05847e1012879d37aaf1e658205199da596f5145ed7a88d9162"),
    "skill-creator/license.txt": (11358, "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"),
    "skill-creator/references/openai_yaml.md": (2356, "ffac39318e408108141d40f820968e59f70434a891694f9bf1d25be8237b150c"),
    "skill-creator/scripts/generate_openai_yaml.py": (6619, "ddaf9abdfb3e762ed3c82571e9c607ce964188f49f2146281beb2cb8a553a93d"),
    "skill-creator/scripts/init_skill.py": (10160, "bc04fae1e671aa1e5104212674e7f22c9665a791fafa2fc2b3897187a89801b2"),
    "skill-creator/scripts/quick_validate.py": (4227, "1fd66498c219616fd9249eacdf16c458412ea9065a9d887fd716aeef03907762"),
    "skill-installer/LICENSE.txt": (11358, "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"),
    "skill-installer/SKILL.md": (3367, "d68b77e5bbb34dedab89d134da52855f140fc4b4299b80104f534e3b9e98f8ee"),
    "skill-installer/agents/openai.yaml": (221, "5ce223d8b1070b82c42298538f1b8d376f788eb9e7a42a987e8c094070d73f0e"),
    "skill-installer/assets/skill-installer-small.svg": (923, "3928703ff00dc1a681e7a22401843b7edcbd4b2051651ce4c43b75f7e140504e"),
    "skill-installer/assets/skill-installer.png": (1086, "d0a230b1a79b71b858b7c215a0fbb0768d6459c14ea4ef80c61592629bf0e605"),
    "skill-installer/scripts/github_utils.py": (659, "61c1bbe2ae217433b4b6f9f09f21aca4df52c12598068343ade719f706e4859b"),
    "skill-installer/scripts/install-skill-from-github.py": (11790, "3569ac8c0b3a525515c2e0e27c4f48e6aef9f2ff04029dcb3f622b280fa8c25e"),
    "skill-installer/scripts/list-skills.py": (2967, "e4e1f78ca3d045827f2a05cfd99fae57cc7c1a1bfeba8704029108834debff35"),
}

NATIVE_DATABASES = (
    "state_5.sqlite", "logs_2.sqlite", "goals_1.sqlite",
    "memories_1.sqlite", "queue_1.sqlite",
)
NATIVE_ARG0_DIRECTORY_RE = re.compile(r"\.codex/tmp/arg0/codex-arg0[A-Za-z0-9]{6}\Z")
NATIVE_SNAPSHOT_RE = re.compile(
    r"\.codex/shell_snapshots/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
    r"(?:\.[0-9]{1,39}\.sh|\.tmp-[0-9]{1,39})\Z"
)
NATIVE_HELPER_NAMES = ("apply_patch", "applypatch", "codex-linux-sandbox", "codex-execve-wrapper")
NATIVE_MUTABLE_DIRECTORIES = (".codex", ".codex/tmp", ".codex/tmp/arg0", ".codex/shell_snapshots")
MAX_NATIVE_STATE_ENTRIES = 128
MAX_NATIVE_STATE_BYTES = 67_108_864


def native_builtin_cache_directories() -> List[str]:
    directories = {".codex/skills", NATIVE_BUILTIN_ROOT}
    for relative in NATIVE_BUILTIN_ASSETS:
        pieces = relative.split("/")
        for count in range(1, len(pieces)):
            directories.add(NATIVE_BUILTIN_ROOT + "/" + "/".join(pieces[:count]))
    return sorted(directories)


def validate_native_builtin_cache(inventory: Mapping[str, Any]) -> None:
    content = {row[1]: row for row in inventory["content"]}
    observed = {path for path in content if path == ".codex/skills" or path.startswith(".codex/skills/")}
    if not observed:
        return
    directories = set(native_builtin_cache_directories())
    files = {NATIVE_BUILTIN_ROOT + "/" + path for path in NATIVE_BUILTIN_ASSETS}
    if observed != directories | files | {NATIVE_BUILTIN_MARKER}:
        raise ContractError("native builtin cache is not the complete exact pinned set")
    for path in directories:
        row = content[path]
        if row[0] != "dir" or row[2:4] != (0o700, 0) or row[-1] != ():
            raise ContractError("native builtin directory metadata drifted")
    for path, (size, digest) in NATIVE_BUILTIN_ASSETS.items():
        row = content[NATIVE_BUILTIN_ROOT + "/" + path]
        if row[0] != "file" or row[2:5] != (0o600, 0, size) or row[7] != digest or row[-1] != ():
            raise ContractError("native builtin asset bytes or metadata drifted")
    marker = content[NATIVE_BUILTIN_MARKER]
    if marker[0] != "file" or marker[2:4] != (0o600, 0) or not 2 <= marker[4] <= 17 or marker[-1] != ():
        raise ContractError("native builtin marker metadata is invalid")


def native_state_class(relative: str) -> Tuple[str, int, int, str]:
    """Finite source-grounded type/mode/byte cap/lifecycle; no default allow."""
    if relative in (".", ".codex/rules"):
        return "dir", 0o700, 0, "protected"
    if relative in NATIVE_MUTABLE_DIRECTORIES:
        return "dir", 0o700, 0, "directory"
    if relative == ".codex/" + REVIEWED_RULES_RELATIVE_PATH:
        return "file", 0o600, len(REVIEWED_RULES_BYTES), "protected"
    if relative == ".codex/auth.json":
        return "file", 0o600, 1_048_576, "protected"
    if relative == ".codex/installation_id":
        return "file", 0o644, 36, "create-once"
    if relative in native_builtin_cache_directories():
        return "dir", 0o700, 0, "immutable-directory"
    if relative == NATIVE_BUILTIN_MARKER:
        return "file", 0o600, 17, "create-once"
    if relative.startswith(NATIVE_BUILTIN_ROOT + "/"):
        source_relative = relative[len(NATIVE_BUILTIN_ROOT) + 1:]
        if source_relative in NATIVE_BUILTIN_ASSETS:
            return "file", 0o600, NATIVE_BUILTIN_ASSETS[source_relative][0], "create-once"
    if relative == ".codex/models_cache.json":
        return "file", 0o600, 4_194_304, "update"
    for database in NATIVE_DATABASES:
        if relative == ".codex/" + database:
            return "file", 0o600, 16_777_216, "update"
        if relative == ".codex/" + database + "-wal":
            return "file", 0o600, 16_777_216, "ephemeral"
        if relative == ".codex/" + database + "-shm":
            return "file", 0o600, 1_048_576, "ephemeral"
    if NATIVE_ARG0_DIRECTORY_RE.fullmatch(relative):
        return "dir", 0o700, 0, "ephemeral-directory"
    parent, _, name = relative.rpartition("/")
    if NATIVE_ARG0_DIRECTORY_RE.fullmatch(parent):
        if name == ".lock":
            return "file", 0o600, 0, "ephemeral"
        if name in NATIVE_HELPER_NAMES:
            return "link", 0o777, 0, "ephemeral"
    if NATIVE_SNAPSHOT_RE.fullmatch(relative):
        nanos = relative.rsplit("/", 1)[1].split(".", 1)[1]
        nanos = nanos[4:] if nanos.startswith("tmp-") else nanos[:-3]
        if int(nanos) > 2 ** 128 - 1:
            raise ContractError("native shell snapshot timestamp exceeds unsigned 128-bit bound")
        return "file", 0o600, 1_048_576, "ephemeral"
    raise ContractError("unclassified native runtime state")


def native_helper_link_xattr_size(path: Path) -> int:
    """No-follow link-metadata observation; retain neither names nor values."""
    try:
        library = _runtime_libc()
        if sys.platform == "darwin":
            function = library.listxattr
            function.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
            function.restype = ctypes.c_ssize_t
            return function(os.fsencode(path), None, 0, 1)  # XATTR_NOFOLLOW
        if sys.platform.startswith("linux"):
            function = library.llistxattr
            function.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
            function.restype = ctypes.c_ssize_t
            return function(os.fsencode(path), None, 0)
    except (OSError, TypeError, NotImplementedError, AttributeError):
        pass
    raise ContractError("native helper link metadata is uncheckable")


def execution_root_inventory(root: Path, *, native_binary: Optional[Path] = None) -> Dict[str, List[Tuple[Any, ...]]]:
    """Inventory the private execution root without following any link.

    This bounds the adapter-owned target, HOME, and TMPDIR namespace. It is a
    pre/post persistence sensor, not a host-global filesystem monitor or a
    kernel write-confinement primitive.
    """
    require_runtime_fs_capabilities()
    if native_binary is None:
        descriptor, root_binding = bound_directory(root)
    else:
        descriptor, root_info = _open_absolute_directory_nofollow(root)
        root_binding = (root_info.st_dev, root_info.st_ino)
    content_rows: List[Tuple[Any, ...]] = []
    binding_rows: List[Tuple[Any, ...]] = []
    counters = {"entries": 0, "bytes": 0}

    def walk(directory_descriptor: int, relative: str, depth: int) -> None:
        if depth > MAX_EXECUTION_ROOT_DEPTH:
            raise ContractError("execution root exceeds its depth bound")
        directory_before = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_before.st_mode):
            raise ContractError("execution root contains a non-directory binding")
        if native_binary is not None:
            expected_kind, expected_mode, _cap, _lifecycle = native_state_class(relative)
            if expected_kind != "dir" or directory_before.st_uid != os.getuid() or directory_before.st_gid != os.getgid() or stat.S_IMODE(directory_before.st_mode) != expected_mode:
                raise ContractError("native directory type, owner or mode drifted")
        xattrs = descriptor_xattr_inventory(directory_descriptor)
        names: List[str] = []
        with os.scandir(directory_descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                counters["entries"] += 1
                if counters["entries"] > (MAX_NATIVE_STATE_ENTRIES if native_binary is not None else MAX_EXECUTION_ROOT_ENTRIES):
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
            native = native_state_class(child_relative) if native_binary is not None else None
            if native is not None:
                actual_kind = "dir" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "link" if stat.S_ISLNK(info.st_mode) else "special"
                if actual_kind != native[0] or stat.S_IMODE(info.st_mode) != native[1] or info.st_uid != os.getuid() or info.st_gid != os.getgid():
                    raise ContractError("native state type, owner or mode drifted")
                if actual_kind == "file" and info.st_size > native[2]:
                    raise ContractError("native state exceeds its class byte limit")
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
                    if native is not None and (
                        opened.st_mode, opened.st_uid, opened.st_gid, opened.st_nlink,
                        opened.st_mtime_ns, opened.st_ctime_ns,
                    ) != (
                        info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
                        info.st_mtime_ns, info.st_ctime_ns,
                    ):
                        raise ContractError("native file metadata changed before descriptor binding")
                    digest = hashlib.sha256()
                    read_size = 0
                    native_scalar_bytes = bytearray()
                    while True:
                        chunk = os.read(child_descriptor, 65_536)
                        if not chunk:
                            break
                        read_size += len(chunk)
                        counters["bytes"] += len(chunk)
                        if read_size > MAX_EXECUTION_ROOT_FILE_BYTES or counters["bytes"] > (MAX_NATIVE_STATE_BYTES if native is not None else MAX_EXECUTION_ROOT_TOTAL_BYTES):
                            raise ContractError("execution root exceeds its content bound")
                        if native is not None and read_size > native[2]:
                            raise ContractError("native state grew beyond its class byte limit")
                        if native is not None and child_relative in (".codex/installation_id", NATIVE_BUILTIN_MARKER):
                            native_scalar_bytes.extend(chunk)
                        digest.update(chunk)
                    if native is not None and child_relative == ".codex/installation_id" and re.fullmatch(rb"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", bytes(native_scalar_bytes)) is None:
                        raise ContractError("native installation identity is malformed")
                    if native is not None and child_relative == NATIVE_BUILTIN_MARKER and re.fullmatch(rb"[0-9a-f]{1,16}\n", bytes(native_scalar_bytes)) is None:
                        raise ContractError("native builtin marker is malformed")
                    child_xattrs = descriptor_xattr_inventory(child_descriptor)
                    after = os.fstat(child_descriptor)
                    named_after = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
                    before_state = (
                        opened.st_dev, opened.st_ino, opened.st_size,
                        opened.st_mtime_ns, opened.st_ctime_ns,
                        opened.st_mode, opened.st_uid, opened.st_gid, opened.st_nlink,
                    )
                    if (
                        after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns,
                        after.st_mode, after.st_uid, after.st_gid, after.st_nlink,
                    ) != before_state or (
                        named_after.st_dev, named_after.st_ino, named_after.st_size,
                        named_after.st_mtime_ns, named_after.st_ctime_ns,
                        named_after.st_mode, named_after.st_uid, named_after.st_gid, named_after.st_nlink,
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
                    ) + ((opened.st_gid,) if native is not None else ()))
                finally:
                    os.close(child_descriptor)
            elif native is not None and native[0] == "link":
                # Read link text without traversing it. Only four source-defined
                # arg0 aliases may name the exact already pinned executable.
                if info.st_nlink != 1 or native_binary is None or not native_binary.is_absolute():
                    raise ContractError("native helper link binding is invalid")
                target = os.readlink(name, dir_fd=directory_descriptor)
                if target != str(native_binary):
                    raise ContractError("native helper target escapes the pinned executable")
                link_xattrs = native_helper_link_xattr_size(root / child_relative)
                if link_xattrs < 0:
                    raise ContractError("native helper link metadata is uncheckable")
                if link_xattrs != 0 or descriptor_stat_flags(info):
                    raise ContractError("native helper link metadata is unapproved")
                named_after = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
                if (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_uid, info.st_gid, info.st_nlink, info.st_mode) != (named_after.st_dev, named_after.st_ino, named_after.st_mtime_ns, named_after.st_ctime_ns, named_after.st_uid, named_after.st_gid, named_after.st_nlink, named_after.st_mode):
                    raise ContractError("native helper link namespace changed")
                content_rows.append(("link", child_relative, 0o777, descriptor_stat_flags(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns, sha256_bytes(target.encode("utf-8")), ()))
                binding_rows.append(("link", child_relative, info.st_dev, info.st_ino, kind, 0o777, 1, info.st_gid))
            else:
                raise ContractError("execution root contains a symlink or special file")
        directory_after = os.fstat(directory_descriptor)
        if native_binary is not None and (
            directory_after.st_uid != directory_before.st_uid
            or directory_after.st_gid != directory_before.st_gid
            or directory_after.st_mode != directory_before.st_mode
            or descriptor_stat_flags(directory_after) != descriptor_stat_flags(directory_before)
            or descriptor_xattr_inventory(directory_descriptor) != xattrs
        ):
            raise ContractError("native directory metadata changed during inventory")
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
        ) + ((directory_after.st_gid,) if native_binary is not None else ()))

    try:
        walk(descriptor, ".", 1)
        named_after = os.stat(str(root), follow_symlinks=False)
        if (named_after.st_dev, named_after.st_ino) != root_binding:
            raise ContractError("execution-root namespace changed during inventory")
    finally:
        os.close(descriptor)
    return {"content": sorted(content_rows, key=lambda row: row[1]), "binding": sorted(binding_rows, key=lambda row: row[1])}


def sandbox_tmp_owner_metadata(root, inventory):
    """Supplement missing uid/gid, VM-local only; no new inventory semantics."""
    rows = {row[1]: row for row in inventory['binding']}
    contents = {row[1]: row for row in inventory['content']}
    if len(rows) > MAX_EXECUTION_ROOT_ENTRIES or set(rows) != set(contents):
        raise ContractError('tmp-supplement-invalid')
    descriptor, _ = _open_absolute_directory_nofollow(root)
    owners = {}
    try:
        for path, row in rows.items():
            parts = [] if path == '.' else path.split('/')
            if any(part in ('', '.', '..') for part in parts) or len(parts) > 32:
                raise ContractError('tmp-supplement-invalid')
            fd = os.dup(descriptor)
            try:
                for index, part in enumerate(parts):
                    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                    if index < len(parts) - 1 or row[0] == 'dir': flags |= os.O_DIRECTORY
                    next_fd = os.open(part, flags, dir_fd=fd)
                    os.close(fd); fd = next_fd
                info = os.fstat(fd); content = contents[path]
                observed_binding = ('dir' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode)
                                    else 'unsupported', path, info.st_dev, info.st_ino,
                                    stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_nlink)
                times = content[4:6] if row[0] == 'dir' else content[5:7]
                if (tuple(row) != observed_binding or (info.st_mtime_ns, info.st_ctime_ns) != tuple(times)
                        or (row[0] == 'file' and info.st_size != content[4])):
                    raise ContractError('tmp-supplement-binding-drift')
                owners[path] = (info.st_uid, info.st_gid)
                after = os.fstat(fd)
                fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
                if any(getattr(info, field) != getattr(after, field) for field in fields):
                    raise ContractError('tmp-supplement-binding-drift')
            finally: os.close(fd)
        if inventory != execution_root_inventory(root):
            raise ContractError('tmp-supplement-binding-drift')
        named = os.stat(root, follow_symlinks=False); opened = os.fstat(descriptor)
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise ContractError('tmp-supplement-binding-drift')
    finally: os.close(descriptor)
    return owners


SANDBOX_HOUSEKEEPING_SOURCE_COMMIT = '90854393966b21e9ebfd21b122334eb09a20c93d'
SANDBOX_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SANDBOX_MAX_NON_ROOT_ENTRIES = 2
SANDBOX_REGISTRY_PREFIX = 'codex-bwrap-synthetic-mount-targets-'


def observe_sandbox_housekeeping(root, *, expected_uid, expected_gid):
    """Reuse frozen bounded/no-follow inventory and bound uid/gid supplement.

The expected identity is an owner-controlled private-VM input, not a pathname
extracted from untrusted content. Existing shared TMP roots are not eligible.
"""
    result = {'status': 'UNCHECKABLE', 'reason_code': 'observation-uncheckable',
              'state': 'unclassified', 'inventory': None, 'owners': None,
              'expected_uid': expected_uid, 'expected_gid': expected_gid}
    if (type(expected_uid) is not int or not 0 < expected_uid <= 4294967295
            or type(expected_gid) is not int or not 0 <= expected_gid <= 4294967295):
        result['reason_code'] = 'identity-input-invalid'; return result
    try:
        inventory = execution_root_inventory(root)
        result['inventory'] = inventory
        # Reuse the existing read cap, then stop before additional per-node
        # owner observation when even the finite entry count cannot qualify.
        if len(inventory['content']) > SANDBOX_MAX_NON_ROOT_ENTRIES + 1 or len(inventory['binding']) > SANDBOX_MAX_NON_ROOT_ENTRIES + 1:
            result.update(status='fail', reason_code='unclassified-or-incomplete-state'); return result
        owners = sandbox_tmp_owner_metadata(root, inventory)
        result.update(inventory=inventory, owners=owners)
    except Exception: return result
    registry = SANDBOX_REGISTRY_PREFIX + str(expected_uid)
    content = {row[1]: row for row in inventory['content']}
    bindings = {row[1]: row for row in inventory['binding']}
    permitted_sets = ({'.'}, {'.', registry, registry + '/lock'})
    if (set(content) not in permitted_sets or len(content) != len(inventory['content'])
            or set(bindings) != set(content) or len(bindings) != len(inventory['binding'])
            or set(owners) != set(content)):
        result.update(status='non-success', reason_code='unclassified-or-incomplete-state'); return result
    for path, row in content.items():
        is_lock = path == registry + '/lock'
        kind, mode = ('file', 0o600) if is_lock else ('dir', 0o700)
        if (row[0] != kind or row[2] != mode or row[3] != 0 or row[-1] != ()
                or owners[path] != (expected_uid, expected_gid)):
            result.update(status='non-success', reason_code='metadata-policy-mismatch'); return result
        binding = bindings[path]
        if binding[0] != kind or binding[5] != mode or binding[2] != bindings['.'][2] or (is_lock and binding[6] != 1):
            result.update(status='non-success', reason_code='binding-policy-mismatch'); return result
        if path == registry and binding[6] != 2:
            result.update(status='non-success', reason_code='registry-link-count-mismatch'); return result
        if path == '.' and binding[6] != (2 if len(content) == 1 else 3):
            result.update(status='non-success', reason_code='root-link-count-mismatch'); return result
        if is_lock and (row[4] != 0 or row[7] != SANDBOX_EMPTY_SHA256):
            result.update(status='non-success', reason_code='lock-content-mismatch'); return result
    result.update(status='pass', reason_code='none', state='empty' if len(content) == 1 else 'registry-only')
    return result


def validate_sandbox_housekeeping_transition(before, after, *, process_reaped):
    """Owner-adopted probe-only finite transition; worker equality is separate.

Only the first complete registry+empty-lock appearance can change the TMP
root's nlink/mtime/ctime. Existing registry-directory times may reflect fully
cleaned transient markers. The lock remains byte/metadata/inode immutable.
    """
    output = {'schema': 't12-sandbox-housekeeping-evidence/v1', 'authority': 'adapter-authored', 'status': 'UNCHECKABLE', 'reason_code': 'observation-uncheckable',
        'current_exact_predicate_equal': None, 'transition': 'unclassified',
        'unknown_entries_accepted': False, 'historical_a2_identified': False,
        'cleanup_required': 'existing-full-disposable-provider-destruction'}
    if type(process_reaped) is not bool or process_reaped is not True:
        output['reason_code'] = 'quiescence-not-proven'; return output
    if before.get('inventory') is not None and after.get('inventory') is not None:
        output['current_exact_predicate_equal'] = before['inventory'] == after['inventory']
    if before.get('status') != 'pass' or after.get('status') != 'pass': return output
    if (before['expected_uid'], before['expected_gid']) != (after['expected_uid'], after['expected_gid']):
        output['reason_code'] = 'expected-identity-drift'; return output
    old = {row[1]: row for row in before['inventory']['content']}
    new = {row[1]: row for row in after['inventory']['content']}
    old_bind = {row[1]: row for row in before['inventory']['binding']}
    new_bind = {row[1]: row for row in after['inventory']['binding']}
    if before['state'] == 'registry-only' and after['state'] == 'empty':
        output['reason_code'] = 'unexpected-registry-removal'; return output
    created = before['state'] == 'empty' and after['state'] == 'registry-only'
    if (old_bind['.'][:6] != new_bind['.'][:6] or old['.'][:4] != new['.'][:4]
            or old['.'][-1] != new['.'][-1] or before['owners']['.'] != after['owners']['.']):
        output['reason_code'] = 'protected-root-drift'; return output
    if created:
        if new_bind['.'][6] != old_bind['.'][6] + 1:
            output['reason_code'] = 'root-link-count-mismatch'; return output
    elif old_bind['.'] != new_bind['.'] or old['.'] != new['.']:
        output['reason_code'] = 'unexplained-root-metadata-drift'; return output
    registry = SANDBOX_REGISTRY_PREFIX + str(before['expected_uid'])
    if before['state'] == 'registry-only':
        lock = registry + '/lock'
        if (old[lock] != new[lock] or old_bind[lock] != new_bind[lock]
                or before['owners'][lock] != after['owners'][lock]):
            output['reason_code'] = 'existing-lock-drift'; return output
        if (old_bind[registry] != new_bind[registry] or old[registry][:4] != new[registry][:4]
                or old[registry][-1] != new[registry][-1]
                or before['owners'][registry] != after['owners'][registry]):
            output['reason_code'] = 'existing-registry-binding-drift'; return output
    output.update(status='pass', reason_code='none', transition='registry-created' if created else 'quiescent-preserved')
    return output


HOUSEKEEPING_REASONS = (
    "none", "not-run", "observation-uncheckable", "quiescence-not-proven",
    "expected-identity-drift", "unexpected-registry-removal", "protected-root-drift",
    "root-link-count-mismatch", "unexplained-root-metadata-drift", "existing-lock-drift",
    "existing-registry-binding-drift",
)


def not_run_compatibility_housekeeping(status="not-run"):
    return {"schema": "t12-sandbox-housekeeping-observation/v1", "authority": "adapter-authored",
        "status": status, "reason_code": "not-run" if status == "not-run" else "observation-uncheckable",
        "source_contract_sha256": sha256_bytes(canonical_bytes(compatibility_contract())),
        "transition": None, "observation_binding": None, "window": None,
        "process_calls": {"requested": 0, "reaped": 0, "unconfirmed": 0}}


def compatibility_housekeeping_record(before, after, sample, context, finished_ms):
    if context is None:
        return not_run_compatibility_housekeeping("UNCHECKABLE")
    proven = (0 < sample["requested"] <= 128 and sample["requested"] == sample["reaped"]
        and sample["unconfirmed"] == 0)
    transition = validate_sandbox_housekeeping_transition(before, after, process_reaped=proven)
    value = {"schema": "t12-sandbox-housekeeping-observation/v1", "authority": "adapter-authored",
        "status": transition["status"], "reason_code": transition["reason_code"],
        "source_contract_sha256": sha256_bytes(canonical_bytes(compatibility_contract())),
        "transition": transition, "observation_binding": dict(context["binding"]),
        "window": {"started_ms": context["started_ms"], "finished_ms": finished_ms},
        "process_calls": dict(sample)}
    return validate_compatibility_housekeeping(value)


def validate_compatibility_housekeeping(value):
    exact_keys(value, tuple(not_run_compatibility_housekeeping()), "housekeeping observation")
    if (value["schema"] != "t12-sandbox-housekeeping-observation/v1" or value["authority"] != "adapter-authored"
            or value["source_contract_sha256"] != sha256_bytes(canonical_bytes(compatibility_contract()))):
        raise ContractError("housekeeping version/source drift")
    if value["transition"] is None:
        if value not in (not_run_compatibility_housekeeping(), not_run_compatibility_housekeeping("UNCHECKABLE")):
            raise ContractError("unobserved housekeeping contains claims")
        return value
    sample = value["process_calls"]
    exact_keys(sample, ("requested", "reaped", "unconfirmed"), "housekeeping process observation")
    if (any(type(number) is not int or not 0 <= number <= 128 for number in sample.values())
            or sample["requested"] != sample["reaped"] + sample["unconfirmed"]):
        raise ContractError("housekeeping process counts are invalid")
    if not _compatibility_binding(value["observation_binding"]):
        raise ContractError("housekeeping attempt binding is invalid")
    window = value["window"]
    exact_keys(window, ("started_ms", "finished_ms"), "housekeeping window")
    if (any(not _compatibility_milliseconds(number) for number in window.values())
            or not 0 <= window["finished_ms"] - window["started_ms"] <= COMPATIBILITY_MAX_AGE_MS):
        raise ContractError("housekeeping window is invalid")
    transition = value["transition"]
    expected_keys = ("schema", "authority", "status", "reason_code", "current_exact_predicate_equal",
        "transition", "unknown_entries_accepted", "historical_a2_identified", "cleanup_required")
    exact_keys(transition, expected_keys, "finite housekeeping transition")
    if (transition["schema"] != "t12-sandbox-housekeeping-evidence/v1" or transition["authority"] != "adapter-authored"
            or transition["status"] not in ("pass", "UNCHECKABLE")
            or transition["reason_code"] not in HOUSEKEEPING_REASONS
            or transition["transition"] not in ("unclassified", "registry-created", "quiescent-preserved")
            or transition["unknown_entries_accepted"] is not False
            or transition["historical_a2_identified"] is not False
            or transition["cleanup_required"] != "existing-full-disposable-provider-destruction"
            or (transition["current_exact_predicate_equal"] is not None and type(transition["current_exact_predicate_equal"]) is not bool)):
        raise ContractError("finite housekeeping transition is invalid")
    if (value["status"], value["reason_code"]) != (transition["status"], transition["reason_code"]):
        raise ContractError("housekeeping summary disagrees")
    if transition["status"] == "pass" and not (
            transition["reason_code"] == "none" and transition["transition"] != "unclassified"
            and type(transition["current_exact_predicate_equal"]) is bool
            and sample["requested"] > 0 and sample["unconfirmed"] == 0):
        raise ContractError("passing housekeeping lacks quiescence")
    if transition["status"] != "pass" and transition["reason_code"] == "none":
        raise ContractError("non-success housekeeping lost its reason")
    if transition["transition"] == "registry-created" and transition["current_exact_predicate_equal"] is not False:
        raise ContractError("registry creation cannot be exact equality")
    return value


def native_codex_home_inventory(home: Path, binary: Path) -> Dict[str, List[Tuple[Any, ...]]]:
    """VM-local only: never export this potentially sensitive path inventory."""
    binary_digest = hash_regular_file(binary)
    inventory = execution_root_inventory(home, native_binary=binary)
    for row in inventory["content"]:
        if native_state_class(row[1])[3] != "protected" and (row[3] != 0 or row[-1] != ()):
            raise ContractError("native state contains unapproved flags or xattrs")
    validate_native_builtin_cache(inventory)
    paths = [row[1] for row in inventory["content"]]
    if sum(bool(NATIVE_ARG0_DIRECTORY_RE.fullmatch(path)) for path in paths) > 4:
        raise ContractError("native arg0 directory count exceeds its bound")
    if sum(bool(NATIVE_SNAPSHOT_RE.fullmatch(path)) for path in paths) > 8:
        raise ContractError("native shell snapshot count exceeds its bound")
    if hash_regular_file(binary) != binary_digest:
        raise ContractError("native helper executable binding drifted")
    return inventory


def validate_native_codex_home_transition(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    """Protect credentials/rules and stable identities; permit finite native data."""
    maps = []
    for inventory in (before, after):
        exact_keys(inventory, ("content", "binding"), "native inventory")
        content = {row[1]: tuple(row) for row in inventory["content"]}
        bindings = {row[1]: tuple(row) for row in inventory["binding"]}
        if len(content) != len(inventory["content"]) or len(bindings) != len(inventory["binding"]) or set(content) != set(bindings):
            raise ContractError("native inventory membership is malformed")
        for path in content:
            native_state_class(path)
        maps.append((content, bindings))
    (old, old_binding), (new, new_binding) = maps
    for path in set(old) | set(new):
        _kind, _mode, _cap, lifecycle = native_state_class(path)
        if lifecycle == "protected":
            if old.get(path) != new.get(path) or old_binding.get(path) != new_binding.get(path):
                raise ContractError("protected native configuration or credential lifecycle changed")
            continue
        if path not in old or path not in new:
            if path in old and lifecycle not in ("ephemeral", "ephemeral-directory"):
                raise ContractError("persistent native state disappeared")
            continue
        left, right = old[path], new[path]
        if left[0] != right[0] or left[2:4] != right[2:4] or left[-1] != right[-1]:
            raise ContractError("native state metadata drifted")
        if left[0] == "dir":
            # Child directory creation/removal may alter nlink and timestamps,
            # never the original directory identity/type/mode/owner.
            if old_binding[path][:6] != new_binding[path][:6] or old_binding[path][7:] != new_binding[path][7:]:
                raise ContractError("native directory binding drifted")
            if lifecycle == "immutable-directory" and (left != right or old_binding[path] != new_binding[path]):
                raise ContractError("immutable native builtin directory changed")
        elif lifecycle not in ("ephemeral",):
            if old_binding[path] != new_binding[path]:
                raise ContractError("persistent native file binding drifted")
            if lifecycle == "create-once" and left != right:
                raise ContractError("native installation identity changed")


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


def build_live_argv(
    binary: Path,
    target_root: Path,
    repository_root: Path,
    envelope: Mapping[str, Any],
    environment: Optional[Mapping[str, str]] = None,
    require_private_projection: bool = False,
) -> List[str]:
    role = extract_static_role(
        repository_root,
        require_private_projection=require_private_projection,
    )
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
    dynamic_markers = (envelope["attempt_id"], "Issue #25")
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


WORKER_BOUNDARY_OWNER_URL = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25#issuecomment-5583709437"
WORKER_BOUNDARY_OWNER_SHA256 = "764f0a2d0acc07d80fc88c3f3710ce5224ca3da5ef8d4bdbcbb13562a4eed3d1"
WORKER_BOUNDARY_REASONS = (
    "none", "worker-observation-uncheckable", "worker-process-not-started",
    "worker-process-unknown", "worker-reap-unconfirmed", "worker-process-non-success",
    "worker-backend-unobserved", "worker-launcher-binding-drift", "worker-tmp-non-success",
    "worker-window-exceeded",
)


def require_worker_housekeeping_agreement():
    """Static adopted agreement is necessary, never evidence or an attempt grant."""
    if compatibility_contract()["worker_boundary"] != "same-private-tmp-observed-worker-linux-helper-quiescent-only":
        raise ContractError("worker-housekeeping-agreement-unavailable")


def worker_boundary_binding(envelope, profile):
    return {"attempt_id": envelope["attempt_id"], "head": envelope["harness"]["commit"],
        "tree": envelope["harness"]["tree"],
        "provider_attempt_sha256": compatibility_provider_digest(profile["evidence"]["containment_provider"], allow_fixture=profile["scope"] == "fixture"),
        "runtime_profile_sha256": sha256_bytes(canonical_bytes(profile)),
        "envelope_sha256": sha256_bytes(canonical_bytes(envelope))}


def validate_worker_boundary(value, envelope, profile, result=None, *, require_success=True):
    """Closed supplemental native proof; no event/result/profile field is rewritten."""
    exact_keys(value, ("schema", "authority", "status", "reason_code", "agreement", "binding",
        "window", "process", "launcher", "housekeeping", "tmp_observations", "execution_result_sha256"), "worker boundary")
    if (value["schema"] != "t12-worker-boundary/v1" or value["authority"] != "adapter-authored"
            or value["agreement"] != {"url": WORKER_BOUNDARY_OWNER_URL, "body_sha256": WORKER_BOUNDARY_OWNER_SHA256}
            or value["binding"] != worker_boundary_binding(envelope, profile)
            or value["status"] not in ("pass", "UNCHECKABLE") or value["reason_code"] not in WORKER_BOUNDARY_REASONS):
        raise ContractError("worker boundary authority/binding is invalid")
    window = value["window"]
    exact_keys(window, ("started_ms", "finished_ms"), "worker window")
    if any(not _compatibility_milliseconds(number) for number in window.values()) or window["finished_ms"] < window["started_ms"]:
        raise ContractError("worker boundary window is invalid")
    bounded_window = window["finished_ms"] - window["started_ms"] <= (envelope["limits"]["worker_timeout_seconds"] + 30) * 1000
    observed_ms = int(datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    fresh_start = observed_ms <= window["started_ms"] <= observed_ms + 900000
    tmp = value["tmp_observations"]
    exact_keys(tmp, ("before_sha256", "after_sha256", "before_status", "after_status"), "worker TMP observations")
    for key in ("before_sha256", "after_sha256"):
        if tmp[key] is not None: require_string(tmp[key], key, SHA256_RE)
    for key in ("before_status", "after_status"):
        if tmp[key] not in ("pass", "non-success", "UNCHECKABLE"): raise ContractError("worker TMP observation status is invalid")
    tmp_complete = all(tmp[key] is not None for key in ("before_sha256", "after_sha256")) and tmp["before_status"] == tmp["after_status"] == "pass"
    process = value["process"]
    if process is not None:
        exact_keys(process, ("logical_invocations", "exit_code", "signal", "timed_out", "stdout_overflow", "stderr_overflow", "reaped"), "worker observed process")
        if type(process["logical_invocations"]) is not int or process["logical_invocations"] != 1:
            raise ContractError("worker process invocation count is invalid")
        for key in ("timed_out", "stdout_overflow", "stderr_overflow", "reaped"):
            require_bool(process[key], "worker " + key)
        if (process["exit_code"] is not None and (type(process["exit_code"]) is not int or not 0 <= process["exit_code"] <= 255)
                or process["signal"] is not None and (type(process["signal"]) is not int or not 1 <= process["signal"] <= 64)
                or process["exit_code"] is not None and process["signal"] is not None):
            raise ContractError("worker process exit status is invalid")
    launcher = value["launcher"]
    exact_keys(launcher, ("role", "actual_image_observed", "binding_stable", "image_samples", "image_error_count", "budget_exhausted", "binary_sha256", "source_commit"), "worker launcher")
    if (launcher["role"] != "same-tmp-worker-linux-sandbox" or launcher["source_commit"] != OFFICIAL_CODEX_0150_SOURCE_COMMIT
            or launcher["binary_sha256"] != APPROVED_BWRAP_BINARY_SHA256):
        raise ContractError("worker launcher source/binary is invalid")
    for key in ("actual_image_observed", "binding_stable", "budget_exhausted"):
        require_bool(launcher[key], "worker launcher " + key)
    for key in ("image_samples", "image_error_count"):
        if type(launcher[key]) is not int or not 0 <= launcher[key] <= 4096:
            raise ContractError("worker launcher count is invalid")
    # Reuse the native transition validator only for its closed finite record.
    # The worker's longer time window above is independent of the probe window.
    transition = value["housekeeping"]
    observation = not_run_compatibility_housekeeping("UNCHECKABLE")
    observation.update(status=transition.get("status"), reason_code=transition.get("reason_code"), transition=transition,
        observation_binding={"head": envelope["harness"]["commit"], "tree": envelope["harness"]["tree"],
            "provider_attempt_sha256": value["binding"]["provider_attempt_sha256"], "observation_id_sha256": "1" * 64},
        window={"started_ms": window["started_ms"], "finished_ms": window["started_ms"]},
        process_calls={"requested": 1, "reaped": int(process is not None and process["reaped"]), "unconfirmed": int(process is None or not process["reaped"])})
    validate_compatibility_housekeeping(observation)
    passing = (bounded_window and fresh_start and tmp_complete and process is not None and process["exit_code"] == 0 and process["signal"] is None
        and process["reaped"] and not any(process[key] for key in ("timed_out", "stdout_overflow", "stderr_overflow"))
        and launcher["actual_image_observed"] and launcher["binding_stable"] and launcher["image_samples"] > 0
        and not launcher["budget_exhausted"] and transition["status"] == "pass")
    if (value["status"] == "pass") != passing or (value["reason_code"] == "none") != passing:
        raise ContractError("worker boundary success disagrees with actual evidence")
    if value["execution_result_sha256"] is not None:
        require_string(value["execution_result_sha256"], "worker result digest", SHA256_RE)
    if result is not None and (value["execution_result_sha256"] != sha256_bytes(canonical_bytes(result))
            or process is None or result["worker"]["logical_invocations"] != process["logical_invocations"]
            or result["worker"]["exit_code"] != process["exit_code"] or result["worker"]["signal"] != process["signal"]
            or result["worker"]["timed_out"] != process["timed_out"]):
        raise ContractError("worker boundary result binding is invalid")
    if require_success and (not passing or result is not None and value["execution_result_sha256"] is None):
        raise ContractError("worker boundary evidence is non-success")
    return value


def observe_worker_boundary(private_tmp, target_root, binary, environment, envelope, profile, invoke, sink, *, expected_before=None):
    """One actual worker call; retain safe facts before later parsing/verification.

    No cleanup ownership is added. The existing bounded runner supplies the
    original process result; exceptions are unknown, never a zero-call claim.
    """
    if not callable(sink):
        raise ContractError("live execution requires a retained worker observation sink")
    before = observe_sandbox_housekeeping(private_tmp, expected_uid=os.geteuid(), expected_gid=os.getegid())
    if before["status"] != "pass":
        raise ContractError("worker TMP preflight is non-success")
    if expected_before is not None and before["inventory"] != expected_before:
        raise ContractError("dedicated private TMPDIR changed before the worker boundary")
    binding = _launcher_file_snapshot(target_root, environment)
    observer = worker_launcher_observer(binding, binary, target_root, private_tmp, environment)
    started = _compatibility_clock_ms()
    observed_ms = int(datetime.datetime.strptime(profile["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    if not observed_ms <= started <= observed_ms + 900000:
        raise ContractError("worker pre-launch runtime profile is stale")
    process = None
    reason = "worker-process-unknown"
    try:
        process = invoke(observer)
        reason = "none"
    except ProcessSpawnError:
        reason = "worker-process-not-started"
        raise
    finally:
        after = observe_sandbox_housekeeping(private_tmp, expected_uid=os.geteuid(), expected_gid=os.getegid())
        transition = validate_sandbox_housekeeping_transition(before, after, process_reaped=process is not None and process.reaped is True)
        stable = False
        try:
            stable = _launcher_file_snapshot(target_root, environment) == binding
        except (ContractError, OSError, ValueError, TypeError):
            pass
        if process is not None:
            if not process.reaped: reason = "worker-reap-unconfirmed"
            elif process.exit_code != 0 or process.signal_number is not None or process.timed_out or process.stdout_overflow or process.stderr_overflow: reason = "worker-process-non-success"
            elif not observer.observed or observer.exhausted: reason = "worker-backend-unobserved"
            elif not stable: reason = "worker-launcher-binding-drift"
            elif transition["status"] != "pass": reason = "worker-tmp-non-success"
        finished = _compatibility_clock_ms()
        if finished - started > (envelope["limits"]["worker_timeout_seconds"] + 30) * 1000:
            reason = "worker-window-exceeded"
        record = {"schema": "t12-worker-boundary/v1", "authority": "adapter-authored",
            "status": "pass" if reason == "none" else "UNCHECKABLE", "reason_code": reason,
            "agreement": {"url": WORKER_BOUNDARY_OWNER_URL, "body_sha256": WORKER_BOUNDARY_OWNER_SHA256},
            "binding": worker_boundary_binding(envelope, profile),
            "window": {"started_ms": started, "finished_ms": finished},
            "process": None if process is None else {"logical_invocations": 1, "exit_code": process.exit_code,
                "signal": process.signal_number, "timed_out": process.timed_out, "stdout_overflow": process.stdout_overflow,
                "stderr_overflow": process.stderr_overflow, "reaped": process.reaped},
            "launcher": {"role": "same-tmp-worker-linux-sandbox", "actual_image_observed": observer.observed,
                "binding_stable": stable, "image_samples": observer.samples, "image_error_count": observer.errors,
                "budget_exhausted": observer.exhausted, "binary_sha256": APPROVED_BWRAP_BINARY_SHA256,
                "source_commit": OFFICIAL_CODEX_0150_SOURCE_COMMIT},
            "housekeeping": transition,
            "tmp_observations": {"before_sha256": sha256_bytes(canonical_bytes(before)) if before.get("inventory") is not None else None,
                "after_sha256": sha256_bytes(canonical_bytes(after)) if after.get("inventory") is not None else None,
                "before_status": before["status"], "after_status": after["status"]},
            "execution_result_sha256": None}
        validate_worker_boundary(record, envelope, profile, require_success=False)
        sink(record)
    return process, record, after.get("inventory")


def execute_slice(repository_root: Path, envelope: Dict[str, Any], profile: Dict[str, Any], mode: str, fake_behavior: str = "valid", include_artifacts: bool = False, *, profile_observation_sink: Optional[Any] = None, worker_observation_sink: Optional[Any] = None) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    validate_envelope(envelope)
    validate_runtime_profile(profile, allow_fixture=(mode == "offline"))
    if mode == "live":
        require_worker_housekeeping_agreement()
        if not callable(worker_observation_sink):
            raise ContractError("live execution requires a retained worker observation sink")
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
        if not callable(profile_observation_sink):
            raise ContractError("live execution requires a retained profile observation sink")
        sensor_started = datetime.datetime.now(datetime.timezone.utc)
        fresh_profile = observe_runtime_profile(
            repository_root,
            envelope["worker"]["model"],
            envelope["worker"]["reasoning_effort"],
            provider_input,
        )
        sensor_finished = datetime.datetime.now(datetime.timezone.utc)
        validate_runtime_profile(fresh_profile)
        try:
            comparison = compare_runtime_profiles(profile, fresh_profile, sensor_started, sensor_finished)
        except ContractError:
            # Retain both valid, sanitized native records even when their
            # comparison rejects. Invalid native records are not exported.
            profile_observation_sink(runtime_profile_comparison_record(
                profile, fresh_profile, sensor_started, sensor_finished, "fail",
            ))
            raise
        profile_observation_sink(comparison)
        # Native result/receipt binding follows the actual immediate pre-worker
        # observation. The separately retained comparison preserves both inputs.
        profile = fresh_profile
    if mode not in ("offline", "live"):
        raise ContractError("unsupported execution mode")

    with contextlib.ExitStack() as stack:
        layout: Optional[ColimaRuntimeLayout] = None
        if mode == "live":
            layout = prepare_colima_runtime_layout()
            names_before = sorted(entry.name for entry in os.scandir(layout.work))
            if names_before:
                raise ContractError("private Colima work root is not empty before execution")
            # No TemporaryDirectory finalizer may delete a tree while worker
            # absence is unconfirmed. The outer provider retains responsibility
            # for a retained tree; a failed observation is never absence.
            temporary = tempfile.mkdtemp(prefix="execution-", dir=str(layout.work))
            live_cleanup = {"absence_confirmed": False}
            def cleanup_live_container():
                if live_cleanup["absence_confirmed"]:
                    shutil.rmtree(temporary)
            stack.callback(cleanup_live_container)
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
            setup_results = []
            for setup_argv in ([str(executable), "--version"], [str(executable), "exec", "--help"]):
                setup_result = bounded_capture(setup_argv, container, environment)
                if (setup_result.exit_code != 0 or setup_result.signal_number is not None
                        or setup_result.timed_out or setup_result.stdout_overflow
                        or setup_result.stderr_overflow or setup_result.reaped is not True):
                    raise ContractError("Codex version/help evidence became uncheckable before execution")
                setup_results.append(setup_result)
            version_result, help_result = setup_results
            if version_result.stdout.decode("utf-8", errors="strict").strip() != profile["client"]["version_output"] or sha256_bytes(help_result.stdout) != profile["client"]["exec_help_sha256"]:
                raise ContractError("Codex version/help evidence drifted after the runtime sensor")
            harness_binding = verify_harness_state(repository_root, envelope, environment)
            persistent_home_before = native_codex_home_inventory(private_home, executable)
            persistent_tmp_before = execution_root_inventory(private_tmp)
        target_root = create_synthetic_repository(container, environment)
        before = git_snapshot(target_root, environment)
        validate_pre_snapshot(before)
        execution_root_before = execution_root_inventory(container)

        if mode == "offline":
            worker_argv = [sys.executable, "-I", str((repository_root / FAKE_PATH).resolve())]
        else:
            worker_argv = build_live_argv(
                executable, target_root, repository_root, envelope,
                environment, require_private_projection=True,
            )
        prompt = static_prompt(envelope)
        worker_boundary = None
        post_worker_tmp = None
        if mode == "live":
            assert layout is not None
            live_cleanup["absence_confirmed"] = False
            process, worker_boundary, post_worker_tmp = observe_worker_boundary(
                private_tmp, target_root, executable, environment, envelope, profile,
                lambda observer: run_claimed_live_worker(
                    layout, envelope, profile, worker_argv, target_root, environment, prompt,
                    launcher_observer=observer,
                ), worker_observation_sink, expected_before=persistent_tmp_before,
            )
            validate_worker_boundary(worker_boundary, envelope, profile)
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
            validate_native_codex_home_transition(
                persistent_home_before, native_codex_home_inventory(private_home, executable),
            )
            if execution_root_inventory(private_tmp) != post_worker_tmp:
                raise ContractError("dedicated private TMPDIR changed after the observed worker boundary")
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
        if mode == "live":
            worker_boundary = {**worker_boundary, "execution_result_sha256": sha256_bytes(canonical_bytes(result))}
            validate_worker_boundary(worker_boundary, envelope, profile, result)
            # Worker reap alone does not prove the later verifier/Git calls
            # finished safely. Every non-success retains this one live tree.
            live_cleanup["absence_confirmed"] = True
        if include_artifacts:
            return {
                "schema": "t11-runtime-artifact-bundle/v1",
                "runtime_profile": profile,
                "envelope": envelope,
                "execution_result": result,
                "verifier": verifier,
                **({"worker_boundary": worker_boundary} if mode == "live" else {}),
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
    launcher_observer=None,
) -> ProcessResult:
    return run_bounded_process(
        argv, cwd, env, stdin_bytes, timeout, stdout_limit, stderr_limit, 2,
        capture_stderr=capture_stderr,
        **({"launcher_observer": launcher_observer} if launcher_observer is not None else {}),
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


LAUNCH_DIAGNOSTIC_STDERR_LIMIT = 4096
LAUNCH_DIAGNOSTIC_SCHEMA = "t12-sandbox-launch-diagnostics/v1"
# Closed, adapter-authored classifications, never exception/stderr text.
LAUNCH_DIAGNOSTIC_CLASSES = {
    "not-run": ("not-run", "not-run"),
    "none": ("pass", "process-execution"),
    "unsupported-strict-config": ("fail", "cli-dispatch"),
    "process-nonzero": ("fail", "unclassified"),
    "unrecognized-stderr": ("fail", "unclassified"),
    "process-signal": ("fail", "process-execution"),
    "process-timeout": ("UNCHECKABLE", "process-execution"),
    "output-overflow": ("UNCHECKABLE", "process-execution"),
    "process-not-reaped": ("UNCHECKABLE", "process-cleanup"),
    "process-spawn-failed": ("UNCHECKABLE", "process-spawn"),
    "argv-policy-failed": ("UNCHECKABLE", "argv-policy"),
    "probe-preflight-uncheckable": ("UNCHECKABLE", "probe-preflight"),
    "process-observation-uncheckable": ("UNCHECKABLE", "unclassified"),
}
# Exact pinned-source diagnostic, not captured historical runtime output.
STRICT_SANDBOX_REJECTION = b"Error: `--strict-config` is not supported for `codex sandbox`\n"


def launch_diagnostic_record(
    reason_code: str = "not-run", *, exit_code: Optional[int] = None,
    signal_number: Optional[int] = None,
) -> Dict[str, Any]:
    if reason_code not in LAUNCH_DIAGNOSTIC_CLASSES:
        raise ContractError("sandbox launch diagnostic reason is invalid")
    for value, low, high in ((exit_code, 0, 255), (signal_number, 1, 64)):
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise ContractError("sandbox launch diagnostic number is invalid")
    if exit_code is not None and signal_number is not None:
        raise ContractError("sandbox launch diagnostic exit/signal conflict")
    status_value, stage = LAUNCH_DIAGNOSTIC_CLASSES[reason_code]
    return {
        "status": status_value, "stage": stage, "reason_code": reason_code,
        "exit_code": exit_code, "signal": signal_number,
    }


def classify_sandbox_launch(result: ProcessResult) -> Dict[str, Any]:
    """Examine at most 4096 transient bytes; export only enums/numbers."""
    exit_code, signum = result.exit_code, result.signal_number
    if (
        (exit_code is not None and (type(exit_code) is not int or not 0 <= exit_code <= 255))
        or (signum is not None and (type(signum) is not int or not 1 <= signum <= 64))
        or (exit_code is not None and signum is not None)
    ):
        return launch_diagnostic_record("process-observation-uncheckable")
    numbers = {"exit_code": exit_code, "signal_number": signum}
    if not result.reaped:
        reason = "process-not-reaped"
    elif result.timed_out:
        reason = "process-timeout"
    elif (
        result.stdout_overflow or result.stderr_overflow
        or result.stderr_size > LAUNCH_DIAGNOSTIC_STDERR_LIMIT
        or len(result.stderr) > LAUNCH_DIAGNOSTIC_STDERR_LIMIT
    ):
        reason = "output-overflow"
    elif signum is not None:
        reason = "process-signal"
    elif exit_code is None or len(result.stderr) != result.stderr_size:
        reason = "process-observation-uncheckable"
    elif exit_code != 0 and result.stderr == STRICT_SANDBOX_REJECTION:
        reason = "unsupported-strict-config"
    elif result.stderr:
        reason = "unrecognized-stderr"
    elif exit_code != 0:
        reason = "process-nonzero"
    else:
        reason = "none"
    return launch_diagnostic_record(reason, **numbers)


def validate_launch_diagnostics_wrapper(value: Any) -> Dict[str, Any]:
    """Separate transport: never broaden runtime-profile/v1's closed shape."""
    exact_keys(value, ("schema", "authority", "runtime_profile", "launch_diagnostics"), "launch diagnostics wrapper")
    if value["schema"] != LAUNCH_DIAGNOSTIC_SCHEMA or value["authority"] != "adapter-authored":
        raise ContractError("launch diagnostics wrapper identity is invalid")
    profile = validate_runtime_profile(value["runtime_profile"])
    if (
        profile["scope"] != "exact-head-probe-only-sensor"
        or profile["auth"]["class"] != "unavailable"
        or profile["live_run_allowed"] is not False
    ):
        raise ContractError("launch diagnostics requires unauthenticated probe-only evidence")
    lanes = value["launch_diagnostics"]
    exact_keys(lanes, ("shell", "network"), "launch diagnostic lanes")
    for lane in lanes.values():
        exact_keys(lane, ("status", "stage", "reason_code", "exit_code", "signal"), "launch diagnostic lane")
        if lane != launch_diagnostic_record(
            lane["reason_code"], exit_code=lane["exit_code"], signal_number=lane["signal"],
        ):
            raise ContractError("launch diagnostic classification is inconsistent")
        reason = lane["reason_code"]
        if (
            (reason == "none" and (lane["exit_code"] != 0 or lane["signal"] is not None))
            or (reason in ("unsupported-strict-config", "process-nonzero") and (lane["exit_code"] in (None, 0) or lane["signal"] is not None))
            or (reason == "process-signal" and lane["signal"] is None)
            or (reason in ("not-run", "process-spawn-failed", "argv-policy-failed", "probe-preflight-uncheckable") and (lane["exit_code"] is not None or lane["signal"] is not None))
        ):
            raise ContractError("launch diagnostic numeric facts conflict with classification")
    return value


def _capture_sandbox_probe(
    argv: Sequence[str], root: Path, env: Mapping[str, str], stdout_limit: int,
    diagnostics: Optional[Dict[str, Any]], lane: str, launcher_observer=None,
) -> ProcessResult:
    """No extra invocation; scrub transient stderr before existing classifiers."""
    options = {"capture_stderr": True} if diagnostics is not None else {}
    if launcher_observer is not None:
        if lane != "shell":
            raise ContractError("executed launcher observation is shell-probe-only")
        options["launcher_observer"] = launcher_observer
    try:
        result = bounded_capture(
            argv, root, env, timeout=15, stdout_limit=stdout_limit,
            stderr_limit=LAUNCH_DIAGNOSTIC_STDERR_LIMIT, **options,
        )
    except ProcessSpawnError:
        if diagnostics is not None:
            diagnostics[lane] = launch_diagnostic_record("process-spawn-failed")
        raise
    except (ContractError, OSError, subprocess.SubprocessError):
        if diagnostics is not None:
            diagnostics[lane] = launch_diagnostic_record("process-observation-uncheckable")
        raise
    if diagnostics is not None:
        diagnostics[lane] = classify_sandbox_launch(result)
    # No retained stderr reaches the existing lane or runtime-profile record.
    result = result._replace(stderr=b"")
    return result


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
    argv = runtime_configuration_argv(binary, env, surface="sandbox") + [
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
    if "--strict-config" in argv[:index]:
        raise ContractError("sandbox probe argv has unsupported strict configuration")
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


def runtime_configuration_argv(
    binary: Path, env: Mapping[str, str], *, surface: str = "doctor",
) -> List[str]:
    values = reviewed_runtime_configuration(env)
    if surface not in ("doctor", "sandbox"):
        raise ContractError("runtime configuration surface is unsupported")
    # Official 0.150.1 cli/src/main.rs rejects strict_config + Sandbox before
    # dispatch; debug_sandbox intentionally builds strict_config=false. Doctor
    # and the separately built live exec argv retain strict configuration.
    # Every reviewed -c value and the configuration-intent digest is unchanged.
    argv = [str(binary)] + (["--strict-config"] if surface == "doctor" else [])
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
    require_private_projection: bool = False,
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
            require_private_projection=require_private_projection,
        )
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return failed("load-envelope", "envelope-invalid")
    try:
        validate_envelope(envelope)
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return failed("schema-binding", "schema-binding-invalid")
    try:
        extract_static_role(
            repository_root,
            require_private_projection=require_private_projection,
        )
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
        argv = build_live_argv(
            binary, root, repository_root, envelope, env,
            require_private_projection=require_private_projection,
        )
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


def shell_environment_evidence(
    status: str,
    reason_code: str,
    unexpected_names: Sequence[str] = (),
    secret_shaped_key_count: int = 0,
) -> Dict[str, Any]:
    """Build the bounded shell observation record without names or values."""
    if reason_code not in SHELL_ENVIRONMENT_REASON_CODES:
        raise ContractError("shell environment reason code is invalid")
    expected_status = (
        "pass" if reason_code == "none" else
        "not-run" if reason_code == "not-run" else
        "UNCHECKABLE" if reason_code in SHELL_ENVIRONMENT_UNCHECKABLE_REASONS else
        "fail"
    )
    if status != expected_status:
        raise ContractError("shell environment status/reason pair is invalid")
    names = sorted(unexpected_names)
    if (
        len(names) > MAX_SHELL_ENVIRONMENT_ENTRIES
        or len(names) != len(set(names))
        or not isinstance(secret_shaped_key_count, int)
        or isinstance(secret_shaped_key_count, bool)
        or not 0 <= secret_shaped_key_count <= len(names)
    ):
        raise ContractError("shell environment summary is invalid")
    digest = (
        sha256_bytes(canonical_bytes(names))
        if status in ("pass", "fail") else "0" * 64
    )
    return {
        "schema": "t11-shell-environment-evidence/v1",
        "authority": "adapter-authored",
        "status": status,
        "reason_code": reason_code,
        "unexpected_key_count": len(names) if status in ("pass", "fail") else 0,
        "unexpected_key_names_sha256": digest,
        "secret_shaped_key_count": (
            secret_shaped_key_count if status in ("pass", "fail") else 0
        ),
    }


def classify_shell_environment_result(
    result: ProcessResult,
    set_values: Mapping[str, Any],
) -> Dict[str, Any]:
    """Classify one bounded ``env -0`` result without retaining its bytes."""
    empty_uncheckable = lambda reason: shell_environment_evidence(
        "UNCHECKABLE", reason
    )
    if result.timed_out:
        return empty_uncheckable("process-timeout")
    if result.stdout_overflow or result.stderr_overflow:
        return empty_uncheckable("output-overflow")
    if not result.reaped:
        return empty_uncheckable("process-not-reaped")
    if result.exit_code != 0 or result.signal_number is not None:
        return shell_environment_evidence("fail", "process-nonzero")
    if result.stderr_size:
        return empty_uncheckable("observation-uncheckable")
    if not result.stdout.endswith(b"\0"):
        return shell_environment_evidence("fail", "malformed-env-output")
    entries = result.stdout.split(b"\0")
    if entries[-1] != b"" or any(entry == b"" for entry in entries[:-1]):
        return shell_environment_evidence("fail", "malformed-env-output")
    entries = entries[:-1]
    if len(entries) > MAX_SHELL_ENVIRONMENT_ENTRIES:
        return shell_environment_evidence("fail", "malformed-env-output")
    parsed: Dict[str, bytes] = {}
    for entry in entries:
        if b"=" not in entry:
            return shell_environment_evidence("fail", "malformed-env-output")
        name, value = entry.split(b"=", 1)
        if (
            not 1 <= len(name) <= MAX_SHELL_ENVIRONMENT_NAME_BYTES
            or len(value) > MAX_SHELL_ENVIRONMENT_VALUE_BYTES
        ):
            return shell_environment_evidence("fail", "malformed-env-output")
        try:
            key = name.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            return shell_environment_evidence("fail", "malformed-env-output")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
            return shell_environment_evidence("fail", "malformed-env-output")
        if key in parsed:
            return shell_environment_evidence("fail", "duplicate-env-key")
        parsed[key] = value
    required_bytes: Dict[str, bytes] = {}
    for key, value in set_values.items():
        if (
            not isinstance(key, str) or not isinstance(value, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None
        ):
            return empty_uncheckable("observation-uncheckable")
        required_bytes[key] = value.encode("utf-8")
    reviewed = set(REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS)
    unexpected = sorted(set(parsed) - set(required_bytes) - reviewed)
    secret_count = sum(1 for name in unexpected if SECRET_NAME_RE.search(name))
    def failed(reason: str) -> Dict[str, Any]:
        return shell_environment_evidence("fail", reason, unexpected, secret_count)
    if "T11_FORBIDDEN_SENTINEL" in parsed:
        return failed("forbidden-sentinel-survived")
    if secret_count:
        return failed("secret-shaped-key")
    if any(key not in parsed for key in required_bytes):
        return failed("required-value-missing")
    if any(parsed[key] != value for key, value in required_bytes.items()):
        return failed("required-value-mismatch")
    if SANDBOX_NETWORK_MARKER not in parsed:
        return failed("network-marker-missing")
    if parsed[SANDBOX_NETWORK_MARKER] != SANDBOX_NETWORK_MARKER_VALUE:
        return failed("network-marker-mismatch")
    if unexpected:
        return failed("unexpected-key-set")
    return shell_environment_evidence("pass", "none", unexpected, secret_count)


def shell_environment_probe(
    binary: Path,
    root: Path,
    env: Mapping[str, str],
    required: Mapping[str, Any],
    launch_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if launch_diagnostics is not None:
        launch_diagnostics["shell"] = launch_diagnostic_record("probe-preflight-uncheckable")
    try:
        probe_env = dict(env)
        probe_env["T11_FORBIDDEN_SENTINEL"] = "must-not-survive"
        probe_env[SANDBOX_NETWORK_MARKER] = "must-be-overridden"
        set_values = dict(required["shell_environment_policy.set"])
        env_program = Path("/usr/bin/env")
        info = os.stat(str(env_program), follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise ContractError("environment probe executable is invalid")
        if launch_diagnostics is not None:
            launch_diagnostics["shell"] = launch_diagnostic_record("argv-policy-failed")
        argv = sandbox_probe_argv(binary, env, [str(env_program), "-0"], root)
        result = _capture_sandbox_probe(
            argv, root, probe_env, 65_536, launch_diagnostics, "shell",
        )
        return classify_shell_environment_result(result, set_values)
    except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
        return shell_environment_evidence(
            "UNCHECKABLE", "observation-uncheckable"
        )


def network_sandbox_evidence(
    status: str,
    reason_code: str,
    *,
    control_accepted: bool = False,
    control_closed: bool = False,
    parent_namespace_sha256: str = "0" * 64,
    sandbox_namespace_sha256: str = "0" * 64,
    marker_status: str = "UNCHECKABLE",
    connect_status: str = "UNCHECKABLE",
    connect_errno: str = "unapproved",
    process_cleanup_status: str = "UNCHECKABLE",
    process_reaped: bool = False,
) -> Dict[str, Any]:
    if reason_code not in NETWORK_SANDBOX_REASON_CODES:
        raise ContractError("network sandbox reason code is invalid")
    expected_status = (
        "pass" if reason_code == "none" else
        "not-run" if reason_code == "not-run" else
        "fail" if reason_code in NETWORK_SANDBOX_FAIL_REASONS else
        "UNCHECKABLE"
    )
    if status != expected_status:
        raise ContractError("network sandbox status/reason pair is invalid")
    for digest in (parent_namespace_sha256, sandbox_namespace_sha256):
        if SHA256_RE.fullmatch(digest) is None:
            raise ContractError("network namespace digest is invalid")
    return {
        "schema": "t11-network-sandbox-evidence/v1",
        "authority": "adapter-authored",
        "status": status,
        "reason_code": reason_code,
        "unsandboxed_control_accepted": control_accepted,
        "unsandboxed_control_closed": control_closed,
        "parent_netns_sha256": parent_namespace_sha256,
        "sandbox_netns_sha256": sandbox_namespace_sha256,
        "netns_different": (
            parent_namespace_sha256 != "0" * 64
            and sandbox_namespace_sha256 != "0" * 64
            and parent_namespace_sha256 != sandbox_namespace_sha256
        ),
        "network_marker_status": marker_status,
        "sandbox_connect_status": connect_status,
        "sandbox_connect_errno": connect_errno,
        "process_cleanup_status": process_cleanup_status,
        "process_reaped": process_reaped,
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def classify_network_sandbox_result(
    control_status: str,
    parent_namespace_sha256: str,
    result: ProcessResult,
) -> Dict[str, Any]:
    common = {
        "control_accepted": control_status == "accepted-and-closed",
        "control_closed": control_status == "accepted-and-closed",
        "parent_namespace_sha256": parent_namespace_sha256,
    }
    def uncheckable(reason: str, **extra: Any) -> Dict[str, Any]:
        return network_sandbox_evidence(
            "UNCHECKABLE", reason, **common, **extra
        )
    if control_status != "accepted-and-closed":
        return uncheckable(
            "control-not-closed" if control_status == "accepted" else
            "control-not-accepted" if control_status == "connected" else
            "control-unavailable"
        )
    if parent_namespace_sha256 == "0" * 64:
        return uncheckable("parent-netns-unavailable")
    cleanup = {
        "process_cleanup_status": "pass" if result.reaped else "UNCHECKABLE",
        "process_reaped": result.reaped,
    }
    if result.timed_out:
        return uncheckable("process-timeout", **cleanup)
    if result.stdout_overflow or result.stderr_overflow:
        return uncheckable("output-overflow", **cleanup)
    if not result.reaped:
        return uncheckable("process-not-reaped", **cleanup)
    if result.exit_code != 0 or result.signal_number is not None:
        return uncheckable("process-nonzero", **cleanup)
    if result.stderr_size:
        return uncheckable("observation-uncheckable", **cleanup)
    try:
        child = decode_json_object(
            result.stdout, "network sandbox observation",
            {"json_depth": 3, "json_nodes": 16, "json_string_bytes": 128},
        )
        exact_keys(
            child,
            (
                "sandbox_network_namespace_sha256", "network_marker_status",
                "sandbox_connection_status", "denial_errno",
            ),
            "network sandbox observation",
        )
    except (ContractError, UnicodeError, ValueError, TypeError):
        return uncheckable("malformed-probe-output", **cleanup)
    sandbox_namespace = child["sandbox_network_namespace_sha256"]
    marker = child["network_marker_status"]
    connection = child["sandbox_connection_status"]
    denial = child["denial_errno"]
    if not isinstance(sandbox_namespace, str) or SHA256_RE.fullmatch(sandbox_namespace) is None or sandbox_namespace == "0" * 64:
        return uncheckable("sandbox-netns-unavailable", **cleanup)
    if (
        marker not in ("exact-1", "missing", "mismatch")
        or connection not in ("denied", "succeeded", "UNCHECKABLE")
        or denial not in (*APPROVED_NETWORK_DENIAL_ERRNOS, "none", "unapproved")
        or (connection == "succeeded" and denial != "none")
        or (
            connection == "denied"
            and denial not in (*APPROVED_NETWORK_DENIAL_ERRNOS, "unapproved")
        )
        or (connection == "UNCHECKABLE" and denial != "unapproved")
    ):
        return uncheckable("malformed-probe-output", **cleanup)
    observed = {
        **common,
        "sandbox_namespace_sha256": sandbox_namespace,
        "marker_status": marker if marker in ("exact-1", "missing", "mismatch") else "UNCHECKABLE",
        "connect_status": connection if connection in ("denied", "succeeded", "UNCHECKABLE") else "UNCHECKABLE",
        "connect_errno": denial if denial in (*APPROVED_NETWORK_DENIAL_ERRNOS, "none", "unapproved") else "unapproved",
        **cleanup,
    }
    if sandbox_namespace == parent_namespace_sha256:
        return network_sandbox_evidence("fail", "netns-not-separated", **observed)
    if marker == "missing":
        return network_sandbox_evidence("fail", "network-marker-missing", **observed)
    if marker != "exact-1":
        return network_sandbox_evidence("fail", "network-marker-mismatch", **observed)
    if connection == "succeeded":
        return network_sandbox_evidence("fail", "sandbox-connection-succeeded", **observed)
    if connection == "UNCHECKABLE":
        return uncheckable(
            "socket-creation-unavailable",
            sandbox_namespace_sha256=sandbox_namespace,
            marker_status=observed["marker_status"],
            connect_status=observed["connect_status"],
            connect_errno=observed["connect_errno"],
            **cleanup,
        )
    if connection != "denied" or denial not in APPROVED_NETWORK_DENIAL_ERRNOS:
        return uncheckable(
            "unapproved-denial-errno",
            sandbox_namespace_sha256=sandbox_namespace,
            marker_status=observed["marker_status"],
            connect_status=observed["connect_status"],
            connect_errno=observed["connect_errno"],
            **cleanup,
        )
    return network_sandbox_evidence("pass", "none", **observed)


NETWORK_SOCKET_DENIALS_V2 = ("EPERM", "EACCES")
NETWORK_CONNECT_DENIALS_V2 = ("EPERM", "EACCES", "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED")
NETWORK_MAX_CAPTURE_MS_V2 = 15_000
COMPATIBILITY_MAX_AGE_MS = 300_000
COMPATIBILITY_BINDING_KEYS = {"head", "tree", "provider_attempt_sha256", "observation_id_sha256"}
NETWORK_CONTEXT_KEYS_V2 = {"expected_binding", "control_binding", "capture_binding",
                "observation_started_ms", "observation_finished_ms"}
NETWORK_OBSERVATION_KEYS_V2 = {
    "binding", "control_connected", "control_accepted", "control_peer_matches", "control_closed",
    "parent_netns_sha256", "sandbox_netns_sha256", "network_marker_status",
    "socket_create_status", "socket_create_errno", "connect_status", "connect_errno",
    "socket_close_status", "exit_code", "signal", "timed_out", "stdout_overflow",
    "stderr_overflow", "stderr_size", "reaped", "control_closed_ms",
    "probe_started_ms", "probe_finished_ms",
}


def _compatibility_exact_keys(value, keys):
    return isinstance(value, dict) and set(value) == keys


def _compatibility_digest(value, length=64):
    return (isinstance(value, str) and re.fullmatch("[0-9a-f]{%d}" % length, value)
            is not None and value != "0" * length)


def _compatibility_binding(value):
    return (_compatibility_exact_keys(value, COMPATIBILITY_BINDING_KEYS) and all(_compatibility_digest(value[key], 40 if key in
            ("head", "tree") else 64) for key in COMPATIBILITY_BINDING_KEYS))


def _compatibility_milliseconds(value):
    return type(value) is int and 0 <= value <= 2 ** 53 - 1


def _network_errno_name_v2(error, allowed):
    value = getattr(error, "errno", None)
    name = errno.errorcode.get(value) if type(value) is int else None
    return name if name in allowed else "unapproved"


def observe_network_socket_calls_v2(create_socket, configure_socket, connect_socket, close_socket):
    """Closed socket stages; the collector owns fixed AF_INET/target/timeout.

    Offline tests supply fakes only. No error text, private address, or arbitrary
    errno name leaves this function. Configure failure is never connect denial.
    """
    result = {"socket_create_status": "UNCHECKABLE", "socket_create_errno": "unapproved",
              "connect_status": "not-attempted", "connect_errno": "none",
              "socket_close_status": "not-needed"}
    try:
        sock = create_socket()
    except OSError as error:
        result["socket_create_errno"] = _network_errno_name_v2(error, NETWORK_SOCKET_DENIALS_V2)
        if result["socket_create_errno"] in NETWORK_SOCKET_DENIALS_V2:
            result["socket_create_status"] = "denied"
        return result
    except Exception:
        return result
    result.update(socket_create_status="created", socket_create_errno="none")
    try:
        try:
            configure_socket(sock)
        except Exception:
            result.update(connect_status="UNCHECKABLE", connect_errno="unapproved")
            return result
        try:
            connect_socket(sock)
        except OSError as error:
            result.update(connect_status="denied", connect_errno=_network_errno_name_v2(error, NETWORK_CONNECT_DENIALS_V2))
        except Exception:
            result.update(connect_status="UNCHECKABLE", connect_errno="unapproved")
        else:
            result.update(connect_status="succeeded", connect_errno="none")
    finally:
        try:
            close_socket(sock)
        except Exception:
            result["socket_close_status"] = "UNCHECKABLE"
        else:
            result["socket_close_status"] = "pass"
    return result


def classify_network_observation_v2(observation, context, now_ms):
    """Classify only a complete closed observation; no runtime action.

    The controller must independently establish the context; matching submitted
    strings alone are not authenticity. Existing full-profile, containment,
    exact-head and receipt checks remain mandatory in the production route.
    """
    safe = {"schema": "t12-network-predicate/v2", "authority": "adapter-authored",
            "status": "UNCHECKABLE", "reason_code": "malformed-observation",
            "proof_path": "none", "socket_create_status": "UNCHECKABLE",
            "socket_create_errno": "unapproved", "connect_status": "UNCHECKABLE",
            "connect_errno": "unapproved", "socket_close_status": "UNCHECKABLE"}

    def done(reason, status="UNCHECKABLE", proof="none"):
        return dict(safe, reason_code=reason, status=status, proof_path=proof)

    if not _compatibility_exact_keys(observation, NETWORK_OBSERVATION_KEYS_V2) or not _compatibility_exact_keys(context, NETWORK_CONTEXT_KEYS_V2):
        return done("malformed-observation")
    if any(not _compatibility_binding(record) for record in (observation["binding"], context["expected_binding"],
            context["control_binding"], context["capture_binding"])):
        return done("binding-uncheckable")
    if any(record != context["expected_binding"] for record in
            (observation["binding"], context["control_binding"], context["capture_binding"])):
        return done("attempt-binding-mismatch")
    times = [context["observation_started_ms"], observation["control_closed_ms"],
             observation["probe_started_ms"], observation["probe_finished_ms"],
             context["observation_finished_ms"], now_ms]
    if any(not _compatibility_milliseconds(value) for value in times) or times != sorted(times):
        return done("freshness-uncheckable")
    if (times[3] - times[2] > NETWORK_MAX_CAPTURE_MS_V2 or
            times[5] - times[4] > COMPATIBILITY_MAX_AGE_MS or
            times[5] - times[0] > COMPATIBILITY_MAX_AGE_MS):
        return done("stale-observation")
    boolean_keys = ("control_connected", "control_accepted", "control_peer_matches", "control_closed",
                    "timed_out", "stdout_overflow", "stderr_overflow", "reaped")
    if any(type(observation[key]) is not bool for key in boolean_keys):
        return done("malformed-observation")
    if not all(observation[key] for key in boolean_keys[:4]):
        return done("control-unavailable")
    if observation["timed_out"]:
        return done("process-timeout")
    if observation["stdout_overflow"] or observation["stderr_overflow"]:
        return done("output-overflow")
    if not observation["reaped"]:
        return done("process-not-reaped")
    if type(observation["exit_code"]) is not int or observation["exit_code"] != 0 or observation["signal"] is not None:
        return done("process-nonzero-or-status-unavailable")
    if type(observation["stderr_size"]) is not int or observation["stderr_size"] != 0:
        return done("observation-uncheckable")
    if not _compatibility_digest(observation["parent_netns_sha256"]) or not _compatibility_digest(observation["sandbox_netns_sha256"]):
        return done("namespace-uncheckable")
    if observation["parent_netns_sha256"] == observation["sandbox_netns_sha256"]:
        return done("netns-not-separated", "fail")
    marker = observation["network_marker_status"]
    if marker in ("missing", "mismatch"):
        return done("network-marker-" + marker, "fail")
    if marker != "exact-1":
        return done("network-marker-uncheckable")
    socket_status, socket_errno = observation["socket_create_status"], observation["socket_create_errno"]
    connection, connect_errno = observation["connect_status"], observation["connect_errno"]
    closed = observation["socket_close_status"]
    if (socket_status not in ("created", "denied", "UNCHECKABLE") or
            socket_errno not in (*NETWORK_SOCKET_DENIALS_V2, "none", "unapproved") or
            connection not in ("denied", "succeeded", "not-attempted", "UNCHECKABLE") or
            connect_errno not in (*NETWORK_CONNECT_DENIALS_V2, "none", "unapproved") or
            closed not in ("pass", "not-needed", "UNCHECKABLE")):
        return done("malformed-observation")
    if socket_status in ("denied", "UNCHECKABLE"):
        if connection != "not-attempted" or connect_errno != "none" or closed != "not-needed":
            return done("contradictory-operation-stages")
        if ((socket_status == "denied" and socket_errno not in NETWORK_SOCKET_DENIALS_V2) or
                (socket_status == "UNCHECKABLE" and socket_errno != "unapproved")):
            return done("contradictory-operation-stages")
    elif socket_errno != "none" or closed == "not-needed" or connection == "not-attempted":
        return done("contradictory-operation-stages")
    if ((connection == "succeeded" and connect_errno != "none") or
            (connection == "denied" and connect_errno not in (*NETWORK_CONNECT_DENIALS_V2, "unapproved")) or
            (connection == "UNCHECKABLE" and connect_errno != "unapproved")):
        return done("contradictory-operation-stages")
    for key in ("socket_create_status", "socket_create_errno", "connect_status", "connect_errno", "socket_close_status"):
        safe[key] = observation[key]
    if socket_status == "UNCHECKABLE":
        return done("socket-creation-uncheckable")
    if socket_status == "denied":
        return done("none", "pass", "socket-create-denial")
    if closed != "pass":
        return done("socket-close-uncheckable")
    if connection == "succeeded":
        return done("sandbox-connection-succeeded", "fail")
    if connection != "denied" or connect_errno not in NETWORK_CONNECT_DENIALS_V2:
        return done("connect-denial-uncheckable")
    return done("none", "pass", "connect-denial")


def compatibility_provider_digest(provider: Mapping[str, Any], *, allow_fixture=False) -> str:
    validate_containment_provider_evidence(dict(provider), allow_fixture=allow_fixture)
    return sha256_bytes(canonical_bytes({
        "configuration_intent": runtime_configuration_intent(),
        "provider": {key: provider[key] for key in (*PROFILE_PROVIDER_STABLE, *PROFILE_PROVIDER_ATTEMPT)},
    }))


def _compatibility_clock_ms() -> int:
    return time.time_ns() // 1000000


def make_compatibility_context(provider, repository_root, work, env):
    """Observe the actual provider/current checkout before collecting any lane.

    Private paths/environment never enter the exported record. The context is
    local call state, not an input envelope or caller-authenticated assertion.
    """
    if provider.get("status") != "pass":
        raise ContractError("compatibility provider is not independently passing")
    descriptor, info = _open_absolute_directory_nofollow(work)
    os.close(descriptor)
    if str(work.resolve()) != str(work) or not stat.S_ISDIR(info.st_mode):
        raise ContractError("compatibility cwd is not an exact canonical binding")
    result = {
        "binding": {
            "head": provider["public_head"], "tree": provider["public_tree"],
            "provider_attempt_sha256": compatibility_provider_digest(provider),
            "observation_id_sha256": sha256_bytes(os.urandom(32)),
        },
        "repository_root": repository_root, "work": work,
        "work_binding": (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid),
        "environment": dict(env),
        "configuration": reviewed_runtime_configuration(env),
        "started_ms": _compatibility_clock_ms(),
    }
    recheck_compatibility_context(result, work, env)
    return result


def recheck_compatibility_context(context, work, env):
    if (not isinstance(context, dict) or not _compatibility_binding(context.get("binding"))
            or context.get("work") != work or context.get("environment") != dict(env)
            or context.get("configuration") != reviewed_runtime_configuration(env)):
        raise ContractError("compatibility execution context is unavailable or changed")
    descriptor, info = _open_absolute_directory_nofollow(work)
    os.close(descriptor)
    if (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid) != context["work_binding"]:
        raise ContractError("compatibility cwd binding changed")
    for field, ref in (("head", "HEAD"), ("tree", "HEAD^{tree}")):
        observed = run_approved_provider_git(context["repository_root"],
            ("rev-parse", "--verify", ref), env, max_bytes=128).decode("ascii").strip()
        if observed != context["binding"][field]:
            raise ContractError("compatibility exact current Git binding changed")
    if run_approved_provider_git(context["repository_root"],
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"), env):
        raise ContractError("compatibility current repository is not clean")
    if not 0 <= _compatibility_clock_ms() - context["started_ms"] <= COMPATIBILITY_MAX_AGE_MS:
        raise ContractError("compatibility observation window is stale")


def _launcher_file_snapshot(root, env):
    """Exact PATH order, no-follow directory/file binding, no source inference."""
    snapshots = []
    selected = None
    for raw in env["PATH"].split(os.pathsep):
        if not raw or not os.path.isabs(raw):
            raise ContractError("launcher PATH entry is invalid")
        path = Path(raw)
        descriptor, info = _open_absolute_directory_nofollow(path)
        try:
            snapshots.append((raw, info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_mtime_ns, info.st_ctime_ns))
            try:
                child = os.stat("bwrap", dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(child.st_mode) or not child.st_mode & 0o111 or child.st_mode & 0o022:
                raise ContractError("launcher candidate is not a direct protected executable")
            candidate = path / "bwrap"
            if str(candidate.resolve()) != str(candidate):
                raise ContractError("launcher candidate is not canonical")
            if root != Path("/") and (candidate == root or root in candidate.parents):
                continue
            selected = candidate
            if selected != Path("/usr/bin/bwrap"):
                raise ContractError("launcher PATH is shadowed")
            digest = hash_regular_file(selected, 16 * 1024 * 1024)
            after = os.stat("bwrap", dir_fd=descriptor, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if tuple(getattr(child, key) for key in fields) != tuple(getattr(after, key) for key in fields):
                raise ContractError("launcher binding changed while inspecting")
            if digest != compatibility_contract()["launcher_binary_sha256"]:
                raise ContractError("launcher binary digest differs from reviewed baseline")
            return {"directories": snapshots, "file": tuple(getattr(child, key) for key in fields), "digest": digest}
        finally:
            os.close(descriptor)
    raise ContractError("reviewed launcher was not selected by PATH")


def _read_owned_linux_image(pid, birth, expected):
    """Only an already witnessed owned PID/birth; never signal or scan here.

    The exe open deliberately follows one anchored kernel procfs magic link.
    This does not relax no-follow rules for filesystem inputs/resources.
    """
    if sys.platform != "linux" or type(pid) is not int or pid <= 0 or not str(birth).startswith("linux:"):
        raise ContractError("executed-image observation is unavailable")
    proc_fd, _ = _open_absolute_directory_nofollow(Path("/proc"))
    process_fd = image_fd = None
    try:
        process_fd = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=proc_fd)
        process_info = os.fstat(process_fd)
        def identity():
            fd = os.open("stat", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=process_fd)
            try:
                data = os.read(fd, 8193)
                if not data or len(data) > 8192:
                    raise ContractError("owned process identity is incomplete")
            finally: os.close(fd)
            value = parse_linux_process_stat(data)
            if value is None or value[0] != pid or value[3] != birth:
                raise ContractError("owned process birth changed")
        identity()
        def command_role():
            descriptor = os.open("cmdline", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=process_fd)
            try:
                data = os.read(descriptor, 65537)
            finally:
                os.close(descriptor)
            if len(data) > 65536 or not data.endswith(b"\0"):
                raise ContractError("owned launcher command role is uncheckable")
            return data, expected.get("role_validator", sandbox_launcher_role)(data)
        def environment_role():
            validator = expected.get("environment_validator")
            if validator is None:
                return None
            descriptor = os.open("environ", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=process_fd)
            try:
                data = os.read(descriptor, 65537)
            finally:
                os.close(descriptor)
            if len(data) > 65536 or not data.endswith(b"\0") or not validator(data):
                raise ContractError("worker launcher private environment binding is uncheckable")
            return data
        command_before, role = command_role()
        if not role:
            return False
        environment_before = environment_role()
        image_fd = os.open("exe", os.O_RDONLY | os.O_NONBLOCK, dir_fd=process_fd)
        image = os.fstat(image_fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(image, key) for key in fields) != expected["file"]:
            return False
        if not stat.S_ISREG(image.st_mode) or image.st_size > 16 * 1024 * 1024:
            raise ContractError("owned image is not bounded regular data")
        digest = hashlib.sha256(); remaining = image.st_size
        while remaining:
            data = os.read(image_fd, min(65536, remaining))
            if not data:
                raise ContractError("owned image read was incomplete")
            digest.update(data); remaining -= len(data)
        if os.read(image_fd, 1):
            raise ContractError("owned image size changed")
        identity()
        command_after, role_after = command_role()
        if not role_after or command_before != command_after or environment_before != environment_role():
            raise ContractError("owned launcher role changed")
        current = os.open("exe", os.O_RDONLY | os.O_NONBLOCK, dir_fd=process_fd)
        try:
            if tuple(getattr(os.fstat(current), key) for key in fields) != expected["file"]:
                raise ContractError("owned executed image changed")
        finally: os.close(current)
        named_process = os.stat(str(pid), dir_fd=proc_fd, follow_symlinks=False)
        if (named_process.st_dev, named_process.st_ino) != (process_info.st_dev, process_info.st_ino):
            raise ContractError("owned proc namespace changed")
        return digest.hexdigest() == expected["digest"]
    finally:
        if image_fd is not None: os.close(image_fd)
        if process_fd is not None: os.close(process_fd)
        os.close(proc_fd)


def sandbox_launcher_role(data):
    """Pinned launcher exec role, excluding its --help and /bin/true probes.

    Raw arguments remain local memory. Source inserts --as-pid-1 at argv[1]
    and the inner seccomp command ends with the exact shell probe command.
    """
    if not isinstance(data, bytes) or len(data) > 65536 or not data.endswith(b"\0"):
        return False
    fields = data[:-1].split(b"\0")
    separators = [index for index, value in enumerate(fields) if value == b"--"]
    if len(separators) != 2:
        return False
    outer, inner = separators
    return (6 <= len(fields) <= 2048 and fields[:2] == [b"bwrap", b"--as-pid-1"]
        and all(flag in fields[2:outer] for flag in (b"--new-session", b"--unshare-user", b"--unshare-pid", b"--unshare-ipc", b"--unshare-net"))
        and b"--apply-seccomp-then-exec" in fields[outer + 1:inner]
        and fields[-3:] == [b"--", b"/usr/bin/env", b"-0"]
        and b"--help" not in fields and b"--allow-network-for-proxy" not in fields)


def _read_owned_linux_identity(pid):
    if sys.platform != "linux" or type(pid) is not int or pid <= 0:
        raise ContractError("owned identity is unavailable")
    proc_fd, _ = _open_absolute_directory_nofollow(Path("/proc"))
    pid_fd = data_fd = None
    try:
        pid_fd = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=proc_fd)
        bound = os.fstat(pid_fd)
        data_fd = os.open("stat", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=pid_fd)
        data = os.read(data_fd, 8193)
        value = parse_linux_process_stat(data) if 0 < len(data) <= 8192 else None
        after = os.stat(str(pid), dir_fd=proc_fd, follow_symlinks=False)
        if (value is None or value[0] != pid or
                (bound.st_dev, bound.st_ino) != (after.st_dev, after.st_ino)):
            raise ContractError("owned identity is incomplete or changed")
        return value
    finally:
        if data_fd is not None: os.close(data_fd)
        if pid_fd is not None: os.close(pid_fd)
        os.close(proc_fd)


class OwnedLauncherImageObserver:
    """Bounded read-only sampler on the existing tracker, never cleanup owner."""
    def __init__(self, expected):
        self.expected = expected
        self.witnessed = {}
        self.observed = False
        self.uncheckable = False
        self.samples = 0
        self.errors = 0
        self.sample_limit = 256
        self.exhausted = False

    def candidate(self, pid, birth):
        return True

    def observe(self, leader_pid, original_leader, table):
        if self.observed or self.samples >= self.sample_limit:
            self.exhausted = not self.observed
            return
        current = table.get(leader_pid)
        if original_leader is not None and current is not None and current[2] == original_leader[2]:
            try:
                fresh = _read_owned_linux_identity(leader_pid)
                if fresh[3] != original_leader[2]:
                    raise ContractError("original leader birth changed")
                self.witnessed.setdefault(leader_pid, fresh[3])
            except (ContractError, OSError, ValueError, TypeError):
                self.uncheckable = True; self.errors = min(self.sample_limit, self.errors + 1)
        changed = True
        while changed and len(self.witnessed) <= 1024:
            changed = False
            for pid, value in table.items():
                parent = value[0]
                parent_now = table.get(parent)
                if (pid not in self.witnessed and parent in self.witnessed and parent_now is not None
                        and parent_now[2] == self.witnessed[parent]):
                    try:
                        parent_before = _read_owned_linux_identity(parent)
                        child = _read_owned_linux_identity(pid)
                        parent_after = _read_owned_linux_identity(parent)
                        if (parent_before[3] != self.witnessed[parent]
                                or parent_after[3] != self.witnessed[parent]
                                or child[1] != parent or child[3] != value[2]):
                            raise ContractError("owned parent-child birth chain changed")
                        self.witnessed[pid] = child[3]; changed = True
                    except (ContractError, OSError, ValueError, TypeError):
                        self.uncheckable = True; self.errors = min(self.sample_limit, self.errors + 1)
        if len(self.witnessed) > 1024:
            self.uncheckable = True; return
        for pid, birth in tuple(self.witnessed.items()):
            if self.samples >= self.sample_limit or self.observed:
                break
            current = table.get(pid)
            if current is None or current[2] != birth:
                continue
            try:
                if not self.candidate(pid, birth):
                    continue
                self.samples += 1
                self.observed = _read_owned_linux_image(pid, birth, self.expected)
            except (ContractError, OSError, ValueError, TypeError):
                self.uncheckable = True; self.errors = min(self.sample_limit, self.errors + 1)
        self.exhausted = not self.observed and self.samples >= self.sample_limit


def worker_permission_profile_matches(value, target_root):
    """Only the pinned workspace-write default, symbolic or exact materialized cwd."""
    if not isinstance(value, dict) or set(value) != {"type", "file_system", "network"} or value["type"] != "managed" or value["network"] != "restricted":
        return False
    filesystem = value["file_system"]
    if not isinstance(filesystem, dict) or set(filesystem) != {"type", "entries"} or filesystem["type"] != "restricted":
        return False
    entries = filesystem["entries"]
    if not isinstance(entries, list) or len(entries) != 7:
        return False
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in ({"path", "access"}, {"path", "access", "missing_path_behavior"}):
            return False
        path = entry["path"]
        if not isinstance(path, dict): return False
        if set(path) == {"type", "path"} and path["type"] == "path":
            mapping = {str(target_root): "project_roots", **{str(target_root / name): "project_roots/" + name for name in (".git", ".agents", ".codex")}}
            label = mapping.get(path["path"])
        elif set(path) == {"type", "value"} and path["type"] == "special" and isinstance(path["value"], dict):
            special = path["value"]
            if set(special) not in ({"kind"}, {"kind", "subpath"}): return False
            label = special["kind"] + ("/" + special["subpath"] if "subpath" in special else "")
        else: return False
        normalized.append((label, entry["access"], entry.get("missing_path_behavior")))
    return set(normalized) == {("root", "read", None), ("project_roots", "write", None), ("slash_tmp", "write", None),
        ("tmpdir", "write", None), *(("project_roots/" + name, "read", "skip") for name in (".git", ".agents", ".codex"))}


def worker_native_helper_binding(program, binary, codex_home):
    """Exact protected arg0 alias, descriptor-bound; no general link allowance."""
    try:
        relative = Path(program).relative_to(codex_home)
        if re.fullmatch(r"tmp/arg0/codex-arg0[A-Za-z0-9]{6}/codex-linux-sandbox", str(relative)) is None:
            return False
        root, root_info = _open_absolute_directory_nofollow(codex_home)
        stack = [(root, None, root_info)]
        fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        try:
            for part in relative.parts[:-1]:
                parent = stack[-1][0]
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                stack.append((child, part, os.fstat(child)))
            for descriptor, _name, info in stack:
                if (info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o700
                        or descriptor_stat_flags(info) or descriptor_xattr_inventory(descriptor)):
                    return False
            parent = stack[-1][0]; leaf = relative.name
            before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISLNK(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o777
                    or before.st_uid != os.geteuid() or before.st_gid != os.getegid() or before.st_nlink != 1
                    or descriptor_stat_flags(before) or native_helper_link_xattr_size(Path(program)) != 0): return False
            if os.readlink(leaf, dir_fd=parent) != str(binary): return False
            after = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            if any(getattr(before, key) != getattr(after, key) for key in fields): return False
            for index, (descriptor, name, info) in enumerate(stack):
                current = os.fstat(descriptor)
                named = os.stat(codex_home, follow_symlinks=False) if index == 0 else os.stat(name, dir_fd=stack[index-1][0], follow_symlinks=False)
                if any(getattr(current, key) != getattr(info, key) or getattr(named, key) != getattr(info, key) for key in fields): return False
            return True
        finally:
            for descriptor, _name, _info in reversed(stack): os.close(descriptor)
    except (ContractError, OSError, ValueError, TypeError):
        return False


def worker_sandbox_launcher_role(data, binary, target_root, private_tmp, environment):
    """Pinned inner seccomp worker role, not shell/help/proc-mount evidence.

    Parse only source-defined prefixes; the arbitrary command after the inner
    delimiter is neither inspected nor exported as evidence of authorship.
    """
    try:
        if not isinstance(data, bytes) or len(data) > 65536 or not data.endswith(b"\0"): return False
        args = [part.decode("utf-8", errors="strict") for part in data[:-1].split(b"\0")]
        if not 12 <= len(args) <= 2048 or args[:2] != ["bwrap", "--as-pid-1"]: return False
        split = args.index("--")
        outer, inner = args[2:split], args[split + 1:]
        inner_split = inner.index("--")
        prefix = inner[:inner_split]
        if not inner[inner_split + 1:]: return False
        program = prefix.pop(0)
        if program != str(binary) and not worker_native_helper_binding(program, binary, Path(environment["CODEX_HOME"])):
            return False
        while prefix[:1] == ["--verify-fd-mount"]:
            if len(prefix) < 2 or re.fullmatch(r"[0-9]{1,9}:/[^\0]*", prefix[1]) is None: return False
            del prefix[:2]
        if prefix[:2] != ["--sandbox-policy-cwd", str(target_root)]: return False
        del prefix[:2]
        if prefix[:1] == ["--command-cwd"]:
            if prefix[:2] != ["--command-cwd", str(target_root)]: return False
            del prefix[:2]
        if len(prefix) != 3 or prefix[0] != "--permission-profile" or prefix[-1] != "--apply-seccomp-then-exec": return False
        if not worker_permission_profile_matches(decode_json_object(prefix[1].encode(), "worker private permission profile"), target_root): return False
        zero = {"--new-session", "--die-with-parent", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-net"}
        one = {"--cap-drop", "--chdir", "--dev", "--dir", "--perms", "--proc", "--remount-ro", "--tmpfs", "--argv0"}
        two = {"--bind", "--bind-try", "--ro-bind", "--ro-bind-data", "--ro-bind-fd"}
        seen = set(); mounts = []; index = 0
        while index < len(outer):
            option = outer[index]; count = 0 if option in zero else 1 if option in one else 2 if option in two else -1
            if count < 0 or index + count >= len(outer): return False
            values = outer[index + 1:index + 1 + count]; seen.add(option)
            if option == "--cap-drop" and values != ["ALL"]: return False
            if option == "--chdir" and values != [str(target_root)]: return False
            if option == "--argv0" and values != ["codex-linux-sandbox"]: return False
            if option in two: mounts.append((option, values[0], values[1]))
            elif option in {"--dev", "--dir", "--proc", "--remount-ro", "--tmpfs"}:
                mounts.append((option, None, values[0]))
            index += count + 1
        if not zero.issubset(seen) or "--cap-drop" not in seen or (program == str(binary) and "--argv0" not in seen): return False
        registry = private_tmp / (SANDBOX_REGISTRY_PREFIX + str(os.geteuid()))
        overlaps = lambda path: path == registry or path in registry.parents or registry in path.parents
        exposure = "unqualified"
        for index, (option, source, destination) in enumerate(mounts):
            if not Path(destination).is_absolute() or os.path.normpath(destination) != destination or destination.startswith("//"): return False
            if not overlaps(Path(destination)): continue
            if option == "--ro-bind" and source == str(registry) and destination == str(registry) and exposure == "writable-host":
                exposure = "exact-read-only"
            elif option in ("--bind", "--bind-try") and source == destination and destination in (str(private_tmp), "/tmp"):
                exposure = "writable-host"
            elif exposure == "exact-read-only":
                # A later covering mount/mask cannot inherit the earlier proof.
                return False
            else:
                exposure = "unqualified"
        return exposure == "exact-read-only"
    except (ContractError, OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError):
        return False


def _owned_linux_image_candidate(pid, birth, expected):
    """Cheap same-birth inode filter; does not consume the expensive image cap."""
    if _read_owned_linux_identity(pid)[3] != birth: raise ContractError("worker image candidate birth drift")
    proc, _ = _open_absolute_directory_nofollow(Path("/proc"))
    directory = image = None
    try:
        directory = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=proc)
        image = os.open("exe", os.O_RDONLY | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(image)
        if _read_owned_linux_identity(pid)[3] != birth: raise ContractError("worker image candidate birth drift")
        return (info.st_dev, info.st_ino) == tuple(expected["file"][:2])
    finally:
        if image is not None: os.close(image)
        if directory is not None: os.close(directory)
        os.close(proc)


class WorkerLauncherImageObserver(OwnedLauncherImageObserver):
    def __init__(self, expected):
        super().__init__(expected)
        self.sample_limit = 4096

    def candidate(self, pid, birth):
        return _owned_linux_image_candidate(pid, birth, self.expected)


def worker_launcher_observer(binding, binary, target_root, private_tmp, environment):
    expected = dict(binding)
    expected["role_validator"] = lambda data: worker_sandbox_launcher_role(data, binary, target_root, private_tmp, environment)
    def environment_matches(data):
        pairs = data[:-1].split(b"\0"); found = []
        for pair in pairs:
            if pair.startswith(b"TMPDIR="): found.append(pair[7:])
        return found == [os.fsencode(private_tmp)]
    expected["environment_validator"] = environment_matches
    return WorkerLauncherImageObserver(expected)


def not_run_compatibility_shell(status="not-run"):
    legacy = shell_environment_evidence(status, "not-run" if status == "not-run" else "observation-uncheckable")
    return {"schema": "t11-shell-environment-evidence/v2", "authority": "adapter-authored",
        "status": status, "reason_code": legacy["reason_code"], "environment_predicate": legacy,
        "source_contract_sha256": sha256_bytes(canonical_bytes(compatibility_contract())),
        "launcher": {"status": "not-run" if status == "not-run" else "UNCHECKABLE",
            "path_binding_stable": False, "binary_sha256": "0" * 64, "help_sha256": "0" * 64,
            "help_required_flags": False, "actual_image_observed": False, "image_samples": 0,
            "image_error_count": 0},
        "observation_binding": None, "window": None,
        "pwd_present": None, "pwd_matches_exact_cwd": None}


def validate_compatibility_shell(value):
    exact_keys(value, tuple(not_run_compatibility_shell()), "shell v2")
    if value["schema"] != "t11-shell-environment-evidence/v2" or value["authority"] != "adapter-authored" or value["source_contract_sha256"] != sha256_bytes(canonical_bytes(compatibility_contract())):
        raise ContractError("shell v2 source/version/authority binding is invalid")
    legacy = validate_shell_environment_evidence(value["environment_predicate"])
    launcher = value["launcher"]
    exact_keys(launcher, tuple(not_run_compatibility_shell()["launcher"]), "launcher evidence")
    for key in ("path_binding_stable", "help_required_flags", "actual_image_observed"):
        require_bool(launcher[key], "launcher " + key)
    for key in ("binary_sha256", "help_sha256"):
        require_string(launcher[key], key, SHA256_RE)
    for key in ("image_samples", "image_error_count"):
        if type(launcher[key]) is not int or not 0 <= launcher[key] <= 256:
            raise ContractError("launcher sample count is invalid")
    if value["observation_binding"] is None:
        if value not in (not_run_compatibility_shell(), not_run_compatibility_shell("UNCHECKABLE")):
            raise ContractError("unobserved shell v2 contains claims")
        return value
    if not _compatibility_binding(value["observation_binding"]):
        raise ContractError("shell observation binding is invalid")
    window = value["window"]
    exact_keys(window, ("started_ms", "capture_started_ms", "capture_finished_ms", "classified_ms"), "shell window")
    values = [window[key] for key in ("started_ms", "capture_started_ms", "capture_finished_ms", "classified_ms")]
    if (any(not _compatibility_milliseconds(item) for item in values) or values != sorted(values)
            or values[-1] - values[0] > COMPATIBILITY_MAX_AGE_MS or values[2] - values[1] > NETWORK_MAX_CAPTURE_MS_V2):
        raise ContractError("shell observation window is stale or invalid")
    for key in ("pwd_present", "pwd_matches_exact_cwd"):
        if value[key] is not None and type(value[key]) is not bool:
            raise ContractError("shell PWD predicate is invalid")
    qualified = (launcher["path_binding_stable"] and launcher["help_required_flags"]
        and launcher["actual_image_observed"] and launcher["image_samples"] > 0
        and launcher["binary_sha256"] == compatibility_contract()["launcher_binary_sha256"]
        and launcher["help_sha256"] == compatibility_contract()["launcher_help_sha256"])
    if launcher["status"] != ("pass" if qualified else "UNCHECKABLE"):
        raise ContractError("launcher qualification disagrees with observations")
    if value["pwd_present"] is False and value["pwd_matches_exact_cwd"] is not None:
        raise ContractError("absent PWD has a fabricated value comparison")
    expected = legacy["status"] if qualified else "UNCHECKABLE"
    expected_reason = legacy["reason_code"] if qualified else "observation-uncheckable"
    if (value["status"], value["reason_code"]) != (expected, expected_reason):
        raise ContractError("shell v2 gate disagrees with observed launcher/environment")
    if value["status"] == "pass" and (type(value["pwd_present"]) is not bool or (value["pwd_present"] is True and value["pwd_matches_exact_cwd"] is not True)):
        raise ContractError("passing PWD does not match the bound cwd")
    return value


def collect_compatibility_shell(binary, root, env, required, context, launch_diagnostics=None):
    if context is None:
        return not_run_compatibility_shell("UNCHECKABLE")
    try:
        recheck_compatibility_context(context, root, env)
        before = _launcher_file_snapshot(root, env)
        help_result = bounded_capture(["/usr/bin/bwrap", "--help"], root, env, stdout_limit=65536, stderr_limit=4096)
        if (help_result.exit_code != 0 or help_result.signal_number is not None or help_result.timed_out
                or help_result.stdout_overflow or help_result.stderr_overflow or help_result.stderr_size or not help_result.reaped):
            raise ContractError("launcher help observation is unavailable")
        help_digest = sha256_bytes(help_result.stdout)
        flags = all(flag in help_result.stdout for flag in (b"--as-pid-1", b"--perms"))
        if help_digest != compatibility_contract()["launcher_help_sha256"] or not flags:
            raise ContractError("launcher help differs from the reviewed selection contract")
        observer = OwnedLauncherImageObserver(before)
        probe_env = dict(env)
        probe_env["T11_FORBIDDEN_SENTINEL"] = "must-not-survive"
        probe_env[SANDBOX_NETWORK_MARKER] = "must-be-overridden"
        env_info = os.stat("/usr/bin/env", follow_symlinks=False)
        if not stat.S_ISREG(env_info.st_mode):
            raise ContractError("environment probe executable is invalid")
        argv = sandbox_probe_argv(binary, env, ["/usr/bin/env", "-0"], root)
        start = _compatibility_clock_ms()
        result = _capture_sandbox_probe(argv, root, probe_env, 65536, launch_diagnostics, "shell", observer)
        finish = _compatibility_clock_ms()
        after = _launcher_file_snapshot(root, env)
        recheck_compatibility_context(context, root, env)
        original = classify_shell_environment_result(result, required["shell_environment_policy.set"])
        present = matches = None
        if original["status"] == "pass":
            present = False
        if original["reason_code"] == "unexpected-key-set":
            pwd = next((entry[4:] for entry in result.stdout.split(b"\0") if entry.startswith(b"PWD=")), None)
            present = pwd is not None
            if present:
                matches = pwd == str(root).encode("utf-8")
                compared = dict(required["shell_environment_policy.set"]); compared["PWD"] = str(root)
                original = classify_shell_environment_result(result, compared)
        qualified = before == after and observer.observed and observer.samples > 0
        value = {"schema": "t11-shell-environment-evidence/v2", "authority": "adapter-authored",
            "status": original["status"] if qualified else "UNCHECKABLE",
            "reason_code": original["reason_code"] if qualified else "observation-uncheckable",
            "environment_predicate": original, "source_contract_sha256": sha256_bytes(canonical_bytes(compatibility_contract())),
            "launcher": {"status": "pass" if qualified else "UNCHECKABLE", "path_binding_stable": before == after,
                "binary_sha256": before["digest"], "help_sha256": help_digest, "help_required_flags": flags,
                "actual_image_observed": observer.observed, "image_samples": observer.samples,
                "image_error_count": observer.errors},
            "observation_binding": dict(context["binding"]),
            "window": {"started_ms": context["started_ms"], "capture_started_ms": start,
                "capture_finished_ms": finish, "classified_ms": _compatibility_clock_ms()},
            "pwd_present": present, "pwd_matches_exact_cwd": matches}
        return validate_compatibility_shell(value)
    except (ContractError, OSError, KeyError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
        return not_run_compatibility_shell("UNCHECKABLE")


def not_run_compatibility_network(status="not-run"):
    return {"schema": "t11-network-sandbox-evidence/v2", "authority": "adapter-authored",
        "status": status, "reason_code": "not-run" if status == "not-run" else "observation-uncheckable",
        "proof_path": "none", "observation": None, "context": None, "classified_at_ms": None}


def compatibility_network_record(observation, context, now_ms):
    result = classify_network_observation_v2(observation, context, now_ms)
    return {"schema": "t11-network-sandbox-evidence/v2", "authority": "adapter-authored",
        "status": result["status"], "reason_code": result["reason_code"], "proof_path": result["proof_path"],
        "observation": observation, "context": context, "classified_at_ms": now_ms}


def validate_compatibility_network(value):
    exact_keys(value, tuple(not_run_compatibility_network()), "network v2")
    if value["schema"] != "t11-network-sandbox-evidence/v2" or value["authority"] != "adapter-authored":
        raise ContractError("network v2 authority/version is invalid")
    if value["observation"] is None:
        if value not in (not_run_compatibility_network(), not_run_compatibility_network("UNCHECKABLE")):
            raise ContractError("unobserved network v2 contains claims")
        return value
    observation, context = value["observation"], value["context"]
    if not _compatibility_exact_keys(observation, NETWORK_OBSERVATION_KEYS_V2) or not _compatibility_exact_keys(context, NETWORK_CONTEXT_KEYS_V2):
        raise ContractError("network v2 closed observation shape is invalid")
    # This complete structural guard also protects non-success export. The
    # classifier alone is not a sanitizer for malformed raw caller values.
    for key in ("binding",):
        if not _compatibility_binding(observation[key]):
            raise ContractError("network observation binding is invalid")
    for key in ("expected_binding", "control_binding", "capture_binding"):
        if not _compatibility_binding(context[key]):
            raise ContractError("network context binding is invalid")
    for key in ("control_closed_ms", "probe_started_ms", "probe_finished_ms"):
        if not _compatibility_milliseconds(observation[key]):
            raise ContractError("network observation time is invalid")
    for key in ("observation_started_ms", "observation_finished_ms"):
        if not _compatibility_milliseconds(context[key]):
            raise ContractError("network context time is invalid")
    if not _compatibility_milliseconds(value["classified_at_ms"]):
        raise ContractError("network classification time is invalid")
    for key in ("control_connected", "control_accepted", "control_peer_matches", "control_closed", "timed_out", "stdout_overflow", "stderr_overflow", "reaped"):
        require_bool(observation[key], "network " + key)
    for key in ("parent_netns_sha256", "sandbox_netns_sha256"):
        require_string(observation[key], key, SHA256_RE)
    enums = {"network_marker_status": ("exact-1", "missing", "mismatch", "UNCHECKABLE"),
        "socket_create_status": ("created", "denied", "UNCHECKABLE"),
        "socket_create_errno": (*NETWORK_SOCKET_DENIALS_V2, "none", "unapproved"),
        "connect_status": ("denied", "succeeded", "not-attempted", "UNCHECKABLE"),
        "connect_errno": (*NETWORK_CONNECT_DENIALS_V2, "none", "unapproved"),
        "socket_close_status": ("pass", "not-needed", "UNCHECKABLE")}
    for key, allowed in enums.items():
        if not isinstance(observation[key], str) or observation[key] not in allowed:
            raise ContractError("network enum is invalid")
    for key, maximum in (("exit_code", 255), ("signal", 64)):
        value_number = observation[key]
        if value_number is not None and (type(value_number) is not int or not 0 <= value_number <= maximum):
            raise ContractError("network process number is invalid")
    if type(observation["stderr_size"]) is not int or not 0 <= observation["stderr_size"] <= 4097:
        raise ContractError("network bounded stderr count is invalid")
    derived = compatibility_network_record(observation, context, value["classified_at_ms"])
    if value != derived:
        raise ContractError("network v2 derived acceptance disagrees")
    return value


NETWORK_SANDBOX_PROBE_SCRIPT_V2 = (
    "import errno,hashlib,json,os,re,socket,sys\n"
    "ns='0'*64\n"
    "try:\n"
    " value=os.readlink('/proc/self/ns/net')\n"
    " if re.fullmatch(r'net:\\[[0-9]+\\]',value): ns=hashlib.sha256(value.encode('ascii')).hexdigest()\n"
    "except (OSError,UnicodeError): pass\n"
    "marker=os.environ.get('CODEX_SANDBOX_NETWORK_DISABLED')\n"
    "r={'sandbox_netns_sha256':ns,'network_marker_status':'exact-1' if marker=='1' else ('missing' if marker is None else 'mismatch'),'socket_create_status':'UNCHECKABLE','socket_create_errno':'unapproved','connect_status':'not-attempted','connect_errno':'none','socket_close_status':'not-needed'}\n"
    "try: sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
    "except OSError as e:\n"
    " name=errno.errorcode.get(e.errno,'unapproved')\n"
    " if name in ('EPERM','EACCES'): r.update(socket_create_status='denied',socket_create_errno=name)\n"
    "else:\n"
    " r.update(socket_create_status='created',socket_create_errno='none')\n"
    " try:\n"
    "  try: sock.settimeout(2)\n"
    "  except OSError: r.update(connect_status='UNCHECKABLE',connect_errno='unapproved')\n"
    "  else:\n"
    "   try: sock.connect(('127.0.0.1',int(sys.argv[1])))\n"
    "   except OSError as e:\n"
    "    name=errno.errorcode.get(e.errno,'unapproved')\n"
    "    r.update(connect_status='denied',connect_errno=name if name in ('EPERM','EACCES','ENETUNREACH','EHOSTUNREACH','ECONNREFUSED') else 'unapproved')\n"
    "   else: r.update(connect_status='succeeded',connect_errno='none')\n"
    " finally:\n"
    "  try: sock.close()\n"
    "  except OSError: r['socket_close_status']='UNCHECKABLE'\n"
    "  else: r['socket_close_status']='pass'\n"
    "sys.stdout.write(json.dumps(r,sort_keys=True,separators=(',',':'))+'\\n')\n"
)


def collect_compatibility_network(binary, root, env, context, launch_diagnostics=None):
    if context is None:
        return not_run_compatibility_network("UNCHECKABLE")
    listener = control = accepted = None
    try:
        recheck_compatibility_context(context, root, env)
        binding = dict(context["binding"])
        parent_ns = _network_namespace_sha256()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0)); listener.listen(2)
        port = listener.getsockname()[1]
        control = socket.create_connection(("127.0.0.1", port), timeout=2)
        peer = control.getsockname()
        accepted, observed_peer = listener.accept()
        if observed_peer != peer:
            raise ContractError("network control peer mismatch")
        accepted.close(); accepted = None
        control.close(); control = None
        control_closed = _compatibility_clock_ms()
        control_binding = dict(context["binding"])
        recheck_compatibility_context(context, root, env)
        capture_binding = dict(context["binding"])
        probe_env = dict(env); probe_env[SANDBOX_NETWORK_MARKER] = "must-be-overridden"
        argv = sandbox_probe_argv(binary, env,
            [str(Path(sys.executable).resolve()), "-I", "-c", NETWORK_SANDBOX_PROBE_SCRIPT_V2, str(port)], root)
        start = _compatibility_clock_ms()
        captured = _capture_sandbox_probe(argv, root, probe_env, 4096, launch_diagnostics, "network")
        finish = _compatibility_clock_ms()
        child = {"sandbox_netns_sha256": "0" * 64, "network_marker_status": "UNCHECKABLE",
            "socket_create_status": "UNCHECKABLE", "socket_create_errno": "unapproved",
            "connect_status": "UNCHECKABLE", "connect_errno": "unapproved", "socket_close_status": "UNCHECKABLE"}
        try:
            decoded_child = decode_json_object(captured.stdout, "network v2 child", {"json_depth": 3, "json_nodes": 24, "json_string_bytes": 128})
            exact_keys(decoded_child, tuple(child), "network child v2")
            # Validate the closed vocabulary before retaining any child strings.
            vocabulary = {"network_marker_status": ("exact-1", "missing", "mismatch", "UNCHECKABLE"),
                "socket_create_status": ("created", "denied", "UNCHECKABLE"),
                "socket_create_errno": (*NETWORK_SOCKET_DENIALS_V2, "none", "unapproved"),
                "connect_status": ("denied", "succeeded", "not-attempted", "UNCHECKABLE"),
                "connect_errno": (*NETWORK_CONNECT_DENIALS_V2, "none", "unapproved"),
                "socket_close_status": ("pass", "not-needed", "UNCHECKABLE")}
            if (all(type(decoded_child[key]) is str and decoded_child[key] in choices for key, choices in vocabulary.items())
                    and isinstance(decoded_child["sandbox_netns_sha256"], str)
                    and SHA256_RE.fullmatch(decoded_child["sandbox_netns_sha256"]) is not None):
                child = decoded_child
        except (ContractError, UnicodeError, ValueError, TypeError):
            pass
        recheck_compatibility_context(context, root, env)
        observation = {**child, "binding": binding,
            "control_connected": True, "control_accepted": True,
            "control_peer_matches": observed_peer == peer, "control_closed": control is None and accepted is None,
            "parent_netns_sha256": parent_ns, "exit_code": captured.exit_code,
            "signal": captured.signal_number, "timed_out": captured.timed_out,
            "stdout_overflow": captured.stdout_overflow, "stderr_overflow": captured.stderr_overflow,
            "stderr_size": min(captured.stderr_size, 4097), "reaped": captured.reaped,
            "control_closed_ms": control_closed, "probe_started_ms": start, "probe_finished_ms": finish}
        public_context = {"expected_binding": binding, "control_binding": control_binding,
            "capture_binding": capture_binding, "observation_started_ms": context["started_ms"],
            "observation_finished_ms": _compatibility_clock_ms()}
        return validate_compatibility_network(compatibility_network_record(observation, public_context, _compatibility_clock_ms()))
    except (ContractError, OSError, subprocess.SubprocessError, UnicodeError, ValueError, TypeError, KeyError):
        return not_run_compatibility_network("UNCHECKABLE")
    finally:
        for owned_socket in (accepted, control, listener):
            if owned_socket is not None:
                try: owned_socket.close()
                except OSError: pass


def _network_namespace_sha256() -> str:
    identity = os.readlink("/proc/self/ns/net")
    if re.fullmatch(r"net:\[[0-9]+\]", identity) is None:
        raise ContractError("network namespace identity is malformed")
    return sha256_bytes(identity.encode("ascii"))


def network_sandbox_behavior_probe(
    binary: Path, root: Path, env: Mapping[str, str],
    launch_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bind control acceptance, namespace separation, marker, and denial."""
    if launch_diagnostics is not None:
        launch_diagnostics["network"] = launch_diagnostic_record("probe-preflight-uncheckable")
    try:
        parent_namespace_sha256 = _network_namespace_sha256()
    except (ContractError, OSError, UnicodeError):
        return network_sandbox_evidence(
            "UNCHECKABLE", "parent-netns-unavailable"
        )
    listener: Optional[socket.socket] = None
    client: Optional[socket.socket] = None
    accepted: Optional[socket.socket] = None
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        port = listener.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        controller_peer = client.getsockname()
    except OSError:
        for item in (client, listener):
            if item is not None:
                with contextlib.suppress(OSError):
                    item.close()
        return network_sandbox_evidence(
            "UNCHECKABLE", "control-unavailable",
            parent_namespace_sha256=parent_namespace_sha256,
        )
    try:
        accepted, accepted_peer = listener.accept()
    except OSError:
        for item in (client, listener):
            if item is not None:
                with contextlib.suppress(OSError):
                    item.close()
        return network_sandbox_evidence(
            "UNCHECKABLE", "control-not-accepted",
            parent_namespace_sha256=parent_namespace_sha256,
        )
    if accepted_peer != controller_peer:
        for item in (accepted, client, listener):
            with contextlib.suppress(OSError):
                item.close()
        return network_sandbox_evidence(
            "UNCHECKABLE", "control-peer-mismatch",
            parent_namespace_sha256=parent_namespace_sha256,
        )
    close_ok = True
    for item in (accepted, client):
        try:
            item.close()
        except OSError:
            close_ok = False
    if not close_ok:
        with contextlib.suppress(OSError):
            listener.close()
        return network_sandbox_evidence(
            "UNCHECKABLE", "control-not-closed",
            control_accepted=True,
            parent_namespace_sha256=parent_namespace_sha256,
        )
    try:
        probe_env = dict(env)
        probe_env[SANDBOX_NETWORK_MARKER] = "must-be-overridden"
        if launch_diagnostics is not None:
            launch_diagnostics["network"] = launch_diagnostic_record("argv-policy-failed")
        argv = sandbox_probe_argv(
            binary, env,
            [
                str(Path(sys.executable).resolve()), "-I", "-c",
                NETWORK_SANDBOX_PROBE_SCRIPT, str(port),
            ],
            root,
        )
        result = _capture_sandbox_probe(
            argv, root, probe_env, 4_096, launch_diagnostics, "network",
        )
    except (ContractError, OSError, subprocess.SubprocessError, ValueError):
        return network_sandbox_evidence(
            "UNCHECKABLE", "observation-uncheckable",
            control_accepted=True, control_closed=True,
            parent_namespace_sha256=parent_namespace_sha256,
        )
    finally:
        with contextlib.suppress(OSError):
            listener.close()
    return classify_network_sandbox_result(
        "accepted-and-closed", parent_namespace_sha256, result,
    )


def probe_runtime_evidence(
    binary: Path,
    root: Path,
    env: Mapping[str, str],
    repository_root: Path,
    auth_required: bool = True,
    prerequisite_evidence: Optional[Mapping[str, Any]] = None,
    require_private_projection: bool = False,
    launch_diagnostics: Optional[Dict[str, Any]] = None,
    compatibility_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Collect bounded independent lanes; no lane claims effective config."""
    if launch_diagnostics is not None and auth_required:
        raise ContractError("launch diagnostics is unavailable to authenticated probes")
    diagnostic_options = {"launch_diagnostics": launch_diagnostics} if launch_diagnostics is not None else {}
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

    worker_evidence = exact_worker_argv_evidence(
        binary, root, repository_root, env,
        require_private_projection=require_private_projection,
    )
    prerequisite_pass = prerequisite["status"] == "pass"
    if not prerequisite_pass:
        shell_evidence = not_run_compatibility_shell()
    elif required is None:
        shell_evidence = not_run_compatibility_shell("UNCHECKABLE")
    else:
        try:
            shell_evidence = collect_compatibility_shell(binary, root, env, required, compatibility_context, **diagnostic_options)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            shell_evidence = not_run_compatibility_shell("UNCHECKABLE")
    if not prerequisite_pass:
        network_evidence = not_run_compatibility_network()
    else:
        try:
            network_evidence = collect_compatibility_network(binary, root, env, compatibility_context, **diagnostic_options)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            network_evidence = not_run_compatibility_network("UNCHECKABLE")
    shell_status = shell_evidence["status"]
    network_status = network_evidence["status"]
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
            "shell_environment_behavior": shell_evidence,
            "network_sandbox_behavior": network_evidence,
            "bubblewrap_prerequisite": prerequisite,
            "sandbox_housekeeping": not_run_compatibility_housekeeping(),
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
        "shell_environment_behavior": not_run_compatibility_shell(),
        "network_sandbox_behavior": not_run_compatibility_network(),
        "sandbox_housekeeping": not_run_compatibility_housekeeping(),
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
    git_bootstrap = provider_input["repository"]["git_bootstrap"]
    observed_git = observe_stage_a1_git(repository_root, environment)
    expected_observed_git = {
        "package_name": git_bootstrap["package_name"],
        "package_version": git_bootstrap["package_version"],
        "package_architecture": git_bootstrap["package_architecture"],
        "install_status": git_bootstrap["install_status"],
        "binary_sha256": git_bootstrap["binary_sha256"],
        "version_output": git_bootstrap["version_output"],
    }
    if observed_git != expected_observed_git:
        raise ContractError("post-clone Git prerequisite differs from its pre-clone trust anchor")
    resolved_git_version, resolved_git_sha256 = git_executable_evidence(
        repository_root, environment, require_approved=True,
    )
    if (
        resolved_git_version != git_bootstrap["version_output"]
        or resolved_git_sha256 != git_bootstrap["binary_sha256"]
    ):
        raise ContractError("runtime Git differs from its pre-clone trust anchor")
    head_bytes = run_approved_provider_git(
        repository_root, ("rev-parse", "--verify", "HEAD"),
        environment, max_bytes=128,
    )
    tree_bytes = run_approved_provider_git(
        repository_root, ("rev-parse", "--verify", "HEAD^{tree}"),
        environment, max_bytes=128,
    )
    status_bytes = run_approved_provider_git(
        repository_root,
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        environment, max_bytes=262_144,
    )
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
        "repository_git_bootstrap": dict(git_bootstrap),
        "repository_git_bootstrap_runtime_match": True,
        "repository_git_clone_contract_sha256": provider_input[
            "repository"
        ]["git_clone_contract_sha256"],
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
    evidence["shell_environment_behavior"] = not_run_compatibility_shell("UNCHECKABLE")
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
    launch_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return _observe_runtime_profile_bound_inner(
            repository_root, model, reasoning, binary, work, env,
            provider_input, layout, probe_only, launch_diagnostics,
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
    launch_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if getattr(_PROFILE_REAP_OBSERVATION, "sample", None) is not None:
        raise ContractError("nested profile reap observation is unsupported")
    sample = {"requested": 0, "reaped": 0, "unconfirmed": 0}
    started_ms = _compatibility_clock_ms()
    before = (observe_sandbox_housekeeping(Path(env["TMPDIR"]), expected_uid=os.getuid(), expected_gid=os.getgid())
        if isinstance(env.get("TMPDIR"), str) else {"status": "UNCHECKABLE", "inventory": None})
    _PROFILE_REAP_OBSERVATION.sample = sample
    try:
        return _observe_runtime_profile_measured(
            repository_root, model, reasoning, binary, work, env,
            provider_input, layout, probe_only, launch_diagnostics,
            before, sample, started_ms,
        )
    finally:
        del _PROFILE_REAP_OBSERVATION.sample


def _observe_runtime_profile_measured(
    repository_root, model, reasoning, binary, work, env, provider_input, layout,
    probe_only, launch_diagnostics, housekeeping_before, process_sample, observation_started_ms,
):
    # Diagnostics is strictly supplemental unauthenticated Stage A transport.
    # Authenticate nothing: the existing bounded status sensor is read-only.
    # Establish absence before capturing any sandbox stderr, and reuse that
    # one auth observation below rather than invoking another auth process.
    diagnostic_auth = None
    if launch_diagnostics is not None:
        if not probe_only or provider_input is None or layout is None:
            raise ContractError("launch diagnostics requires the approved probe-only provider")
        diagnostic_auth = auth_class(binary, work, env)
        if diagnostic_auth != "unavailable":
            raise ContractError("launch diagnostics requires unavailable authentication")
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
    compatibility_context = None
    containment = not_run_containment_provider_evidence()
    if release_class == "stable" and provider_input is not None and layout is not None:
        try:
            containment = observe_colima_provider_evidence(
                repository_root, provider_input, layout, binary_sha256, version_output, env)
            compatibility_context = make_compatibility_context(containment, repository_root, work, env)
            compatibility_context["started_ms"] = observation_started_ms
            recheck_compatibility_context(compatibility_context, work, env)
        except PROFILE_BOUNDARY_EXCEPTIONS:
            # Preserve independently collected provider facts even when an
            # execution-binding predicate cannot be established.
            compatibility_context = None
    if release_class == "stable":
        try:
            prerequisite = observe_stage_a1_prerequisite(work, env)
            diagnostic_options = {"launch_diagnostics": launch_diagnostics} if launch_diagnostics is not None else {}
            probe = probe_runtime_evidence(
                binary, work, env, repository_root, auth_required=not probe_only,
                prerequisite_evidence=prerequisite,
                require_private_projection=provider_input is not None,
                compatibility_context=compatibility_context,
                **diagnostic_options,
            )
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            uncheckable = not_run_runtime_evidence()
            for lane in (
                "process_cleanup_status", "codex_sandbox_network_status",
                "shell_environment_status", "config_status",
            ):
                uncheckable["lane_statuses"][lane] = "UNCHECKABLE"
            uncheckable["diagnostic_health"]["status"] = "UNCHECKABLE"
            uncheckable["shell_environment_behavior"] = not_run_compatibility_shell("UNCHECKABLE")
            uncheckable["network_sandbox_behavior"] = not_run_compatibility_network("UNCHECKABLE")
            probe = {
                "documented_config_keys_probe": "UNCHECKABLE",
                "shell_environment_probe": "UNCHECKABLE",
                "evidence": uncheckable,
            }
        config_probe = probe["documented_config_keys_probe"]
        shell_probe = probe["shell_environment_probe"]
        evidence = probe["evidence"]
        if compatibility_context is None:
            evidence["shell_environment_behavior"] = not_run_compatibility_shell("UNCHECKABLE")
            evidence["network_sandbox_behavior"] = not_run_compatibility_network("UNCHECKABLE")
            shell_probe = "UNCHECKABLE"
            evidence["lane_statuses"]["shell_environment_status"] = "UNCHECKABLE"
            evidence["lane_statuses"]["codex_sandbox_network_status"] = "UNCHECKABLE"
        evidence["containment_provider"] = containment
        evidence["lane_statuses"]["provider_isolation_status"] = containment["status"]
        evidence["lane_statuses"]["mount_boundary_status"] = mount_boundary_status_from_provider(containment)
    else:
        config_probe, shell_probe = "not-proven", "not-run"
        evidence = not_run_runtime_evidence()
    if diagnostic_auth is not None:
        observed_auth_class = diagnostic_auth
    elif release_class == "stable":
        try:
            observed_auth_class = auth_class(binary, work, env)
        except (ContractError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            observed_auth_class = "unknown"
    else:
        observed_auth_class = "unavailable"
    evidence["lane_statuses"]["auth_status"] = observed_auth_class
    if compatibility_context is not None:
        try:
            recheck_compatibility_context(compatibility_context, work, env)
            after = (observe_sandbox_housekeeping(Path(env["TMPDIR"]), expected_uid=os.getuid(), expected_gid=os.getgid())
                if isinstance(env.get("TMPDIR"), str) else {"status": "UNCHECKABLE", "inventory": None})
            evidence["sandbox_housekeeping"] = compatibility_housekeeping_record(
                housekeeping_before, after, process_sample, compatibility_context, _compatibility_clock_ms())
        except PROFILE_BOUNDARY_EXCEPTIONS:
            evidence["sandbox_housekeeping"] = not_run_compatibility_housekeeping("UNCHECKABLE")
    elif release_class == "stable":
        evidence["sandbox_housekeeping"] = not_run_compatibility_housekeeping("UNCHECKABLE")
    non_auth_lanes = [evidence["lane_statuses"][name] for name in RUNTIME_LANE_KEYS[:-1]]
    prerequisite_status = evidence["bubblewrap_prerequisite"]["status"]
    config_ok = (
        prerequisite_status == "pass"
        and evidence["sandbox_housekeeping"]["status"] == "pass"
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
    elif evidence["sandbox_housekeeping"]["status"] != "pass":
        profile_status, reason = "UNCHECKABLE", "sandbox TMP housekeeping is not quiescent or not qualified"
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


def observe_runtime_profile(
    repository_root: Path, model: str, reasoning: str,
    provider_input: Optional[Mapping[str, Any]] = None, probe_only: bool = False,
    launch_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if launch_diagnostics is not None and (not probe_only or provider_input is None):
        raise ContractError("launch diagnostics requires the approved probe-only provider")
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
            repository_root, model, reasoning, binary, layout.work, env, provider_input, layout, probe_only, launch_diagnostics,
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


def load_repository_json(
    repository_root: Path,
    relative: str,
    max_bytes: int = MAX_STDIN_BYTES,
    require_private_projection: bool = False,
) -> Dict[str, Any]:
    require_runtime_fs_capabilities()
    if type(require_private_projection) is not bool:
        raise ContractError(relative + " projection policy is invalid")
    path = repository_root / relative
    info = os.stat(str(path), follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o022 or info.st_size > max_bytes:
        raise ContractError(relative + " is not a bounded non-writable regular file")
    return decode_json_object(
        read_bounded_regular(
            path, max_bytes,
            allowed_modes=(0o600,) if require_private_projection else (0o600, 0o644),
            require_single_link=True,
        ),
        relative,
    )


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
    diagnostic_requested = getattr(args, "launch_diagnostics", False)
    if diagnostic_requested and not args.probe_only:
        raise ContractError("launch diagnostics requires probe-only mode")
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
    diagnostics = {name: launch_diagnostic_record() for name in ("shell", "network")} if diagnostic_requested else None
    diagnostic_options = {"launch_diagnostics": diagnostics} if diagnostics is not None else {}
    profile = observe_runtime_profile(
        repository_root, args.model, args.reasoning_effort, provider_input,
        probe_only=args.probe_only,
        **diagnostic_options,
    )
    if diagnostics is None:
        return profile
    return validate_launch_diagnostics_wrapper({
        "schema": LAUNCH_DIAGNOSTIC_SCHEMA, "authority": "adapter-authored",
        "runtime_profile": profile, "launch_diagnostics": diagnostics,
    })


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
    profile_parser.add_argument(
        "--launch-diagnostics", action="store_true",
        help="opt in to safe supplemental launch classifications; requires unauthenticated probe-only",
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
