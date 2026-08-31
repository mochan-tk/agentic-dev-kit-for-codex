#!/usr/bin/env python3
"""Fail-closed deterministic validation for the T11 runtime vertical slice."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 5_242_880
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 20_000
MAX_STRING_BYTES = 131_072
SCHEMAS = (
    "docs/agreements/runtime/codex-final-response.v1.schema.json",
    "docs/agreements/runtime/execution-result.v1.schema.json",
    "docs/agreements/runtime/loop-event.v1.schema.json",
    "docs/agreements/runtime/runtime-profile.v1.schema.json",
    "docs/agreements/runtime/runtime-receipt.v1.schema.json",
    "docs/agreements/runtime/task-execution-envelope.v1.schema.json",
)
JSON_FIXTURES = (
    "tests/runtime/fixtures/codex-final-response-valid.v1.json",
    "tests/runtime/fixtures/envelope-valid.v1.json",
    "tests/runtime/fixtures/execution-result-valid.v1.json",
    "tests/runtime/fixtures/representative-task.v1.json",
    "tests/runtime/fixtures/runtime-profile-valid.v1.json",
    "tests/runtime/fixtures/runtime-receipt-valid.v1.json",
)
OTHER_FILES = (
    ".codex/agents/task_supervisor.toml",
    ".codex/agents/task_verifier.toml",
    ".codex/agents/task_worker.toml",
    ".github/governance/codex-runtime-profile.v1.json",
    ".github/scripts/codex-exec-adapter.py",
    ".github/scripts/post-runtime-receipt.py",
    "docs/agreements/adr/ADR-0008-minimal-codex-execution-loop.md",
    "docs/agreements/runtime/minimal-codex-execution-loop.md",
    "tests/runtime/fixtures/codex-jsonl-interrupted.jsonl",
    "tests/runtime/fixtures/codex-jsonl-valid.jsonl",
    "tests/runtime/fixtures/fake-codex.py",
    "tests/runtime/fixtures/loop-events-valid.v1.jsonl",
)
LEDGER_CONTRACT_PATH = ".github/governance/ledger-contracts.v1.json"
CONFORMANCE_COVERAGE_PATH = "tests/conformance/coverage.json"
CONFORMANCE_MANIFEST_PATH = "tests/conformance/manifest.json"
CONFORMANCE_RESULTS_PATH = "tests/conformance/results.json"
EXPECTED_ROLE_DIGEST = "813baae383e35eea7195ffc0ad8695c7f562eac57c37ef1bb61ede6914661d23"
EXPECTED_INITIAL = b"status=pending\n"
EXPECTED_FINAL = b"status=complete\n"
OID = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_PATH = re.compile(r"(?i)(?:^|[\s'\"])(?:/users/|/home/|/root/|/tmp/|/private/|/var/folders/|~/|[a-z]:[\\/]|\\\\)")
DOCUMENTED_MEMORY_OVERRIDES = {
    "memories.generate_memories": False,
    "memories.use_memories": False,
}
LEGACY_MEMORY_OVERRIDES = {
    "features.memory_tool",
    "features.memory_tool_use",
}
EXPECTED_RUNTIME_OVERRIDES = {
    "sandbox_workspace_write.network_access": False,
    "hide_agent_reasoning": True,
    "show_raw_agent_reasoning": False,
    "history.persistence": "none",
    "features.hooks": False,
    "features.apps": False,
    "agents.enabled": False,
    "tools.web_search": False,
    "feedback.enabled": False,
    **DOCUMENTED_MEMORY_OVERRIDES,
}
EXPECTED_SHELL_ENVIRONMENT_NAMES = [
    "PATH", "HOME", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
    "PYTHONHASHSEED", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT",
    "GIT_OPTIONAL_LOCKS",
]
EXPECTED_FIXED_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
    "PYTHONHASHSEED": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
}
OFFICIAL_CODEX_0150_SOURCE_COMMIT = "90854393966b21e9ebfd21b122334eb09a20c93d"
OFFICIAL_CODEX_0150_SOURCE_BLOBS = {
    "debug_sandbox": "06c133394b408d4700a82bd88ddd6b8cf01ffd79",
    "spawn": "bbae9308d7e8483476887cb1a1e82555001be06c",
    "shell_environment": "e8bdaa40ca63c29ee23111252a04165e0f1f528e",
}
REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS = ["CODEX_SANDBOX_NETWORK_DISABLED"]
SHELL_ENVIRONMENT_REASON_CODES = (
    "none", "not-run", "process-nonzero", "process-timeout",
    "output-overflow", "process-not-reaped", "malformed-env-output",
    "duplicate-env-key", "required-value-missing", "required-value-mismatch",
    "forbidden-sentinel-survived", "network-marker-missing",
    "network-marker-mismatch", "unexpected-key-set", "secret-shaped-key",
    "observation-uncheckable",
)
SHELL_ENVIRONMENT_UNCHECKABLE_REASONS = {
    "process-timeout", "output-overflow", "process-not-reaped",
    "observation-uncheckable",
}
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
NETWORK_SANDBOX_FAIL_REASONS = {
    "netns-not-separated", "network-marker-missing",
    "network-marker-mismatch", "sandbox-connection-succeeded",
}
APPROVED_NETWORK_DENIAL_ERRNOS = (
    "EPERM", "EACCES", "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED",
)
REVIEWED_RULES_RELATIVE_PATH = "rules/t11-reviewed.rules"
REVIEWED_RULES_BYTES = (
    b"# T11 reviewed empty execpolicy profile. Platform policy remains authoritative.\n"
)
APPROVED_CODEX_VERSION = "codex-cli 0.150.1"
APPROVED_ARCHIVE_SHA256 = "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264"
APPROVED_BWRAP_PACKAGE_VERSION = "0.9.0-1ubuntu0.1"
APPROVED_BWRAP_VERSION_OUTPUT = "bubblewrap 0.9.0"
APPROVED_BWRAP_BINARY_SHA256 = "ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8"
APPROVED_APPARMOR_PACKAGE_VERSION = "4.0.1really4.0.1-0ubuntu0.24.04.7"
APPROVED_BWRAP_PROFILE_SHA256 = "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9"
APPROVED_GIT_PACKAGE_VERSION = "1:2.43.0-1ubuntu7.3"
APPROVED_GIT_VERSION_OUTPUT = "git version 2.43.0"
APPROVED_GIT_BINARY_SHA256 = "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942"
EXPECTED_REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH = "codex/phase-2-minimal-execution-slice"
EXPECTED_T12_PUBLIC_BRANCH = "codex/phase-2-live-codex-runtime"
EXPECTED_STAGE_A1_GIT_FIXED_ENVIRONMENT = {
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
EXPECTED_STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT = (
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
EXPECTED_REPRESENTATIVE_GIT_CLONE_CONTRACT_SHA256 = (
    "af134538a459119e618854b6455199ac92ee0b7abd4546fabc1c7330d4eb51d8"
)
STAGE_A1_REASON_CODES = [
    "none", "not-run", "unsupported-platform", "apparmor-not-enforcing",
    "package-drift", "profile-drift", "binary-drift", "git-package-drift",
    "git-binary-drift",
    "observation-uncheckable", "nonzero-exit", "signal", "timeout",
    "output-overflow", "unexpected-output", "process-not-reaped",
]
STAGE_A1_PRECONDITION_FAILURE_CODES = {
    "unsupported-platform", "apparmor-not-enforcing", "package-drift",
    "profile-drift", "binary-drift", "git-package-drift",
    "git-binary-drift",
}
STAGE_A1_SMOKE_FAILURE_CODES = {
    "nonzero-exit", "signal", "unexpected-output",
}
STAGE_A1_UNCHECKABLE_CODES = {
    "observation-uncheckable", "timeout", "output-overflow",
    "process-not-reaped",
}
EXPECTED_STAGE_A1_SMOKE_ARGV = [
    "/usr/bin/bwrap", "--unshare-user", "--unshare-net",
    "--ro-bind", "/", "/", "/bin/true",
]
EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV = [
    ["/usr/bin/sudo", "-n", "/usr/bin/apt-get", "update"],
    [
        "/usr/bin/sudo", "-n", "/usr/bin/apt-get", "install",
        "--yes", "--no-install-recommends",
        "apparmor=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "apparmor-profiles=" + APPROVED_APPARMOR_PACKAGE_VERSION,
        "bubblewrap=" + APPROVED_BWRAP_PACKAGE_VERSION,
        "git=" + APPROVED_GIT_PACKAGE_VERSION,
    ],
    [
        "/usr/bin/dpkg-query", "--show",
        "--showformat=${db:Status-Status}\\t${Version}\\t${Architecture}\\n",
        "git",
    ],
    ["/usr/bin/sha256sum", "--", "/usr/bin/git"],
    ["/usr/bin/git", "--version"],
]
EXPECTED_STAGE_A1_POSTCLONE_CONTROLLER_ARGV = [
    [
        "/usr/bin/sudo", "-n", "/usr/bin/install", "--owner=root",
        "--group=root", "--mode=0644",
        "/usr/share/apparmor/extra-profiles/bwrap-userns-restrict",
        "/etc/apparmor.d/bwrap-userns-restrict",
    ],
    [
        "/usr/bin/sudo", "-n", "/usr/sbin/apparmor_parser", "--replace",
        "/etc/apparmor.d/bwrap-userns-restrict",
    ],
    EXPECTED_STAGE_A1_SMOKE_ARGV,
]
EXPECTED_STAGE_A1_CONTROLLER_ARGV = (
    EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV
    + EXPECTED_STAGE_A1_POSTCLONE_CONTROLLER_ARGV
)
EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256 = (
    "a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc"
)
EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256 = (
    "3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff"
)
ZERO_OID = "0" * 40
ZERO_SHA256 = "0" * 64


def expected_runtime_frontier() -> Dict[str, Any]:
    """Return the exact accepted-T11 / active-T12 runtime frontier."""

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
            "branch": EXPECTED_T12_PUBLIC_BRANCH,
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
                    "exactly-one-owner-triggered-logical-codex-exec-worker-"
                    "process-invocation"
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
                    "K09", "K10", "K11", "K12", "full-runtime-parity",
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
CONTAINMENT_PROVIDER_KEYS = (
    "schema", "authority", "codex_authenticated_attestation", "status",
    "provider_kind", "profile_name", "vm_backend", "architecture",
    "native_architecture", "guest_os", "guest_kernel", "created_at",
    "provider_configuration_sha256", "effective_mount_inventory_sha256",
    "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
    "host_mount_count", "host_mount_classifications", "all_host_mounts_read_only",
    "provider_cache_only", "host_sensitive_mounts_absent", "unapproved_mounts_absent",
    "ssh_agent_forwarding", "dot_ssh_public_key_loading", "user_ssh_config_modified",
    "vm_instance_identity_sha256", "public_head", "public_tree", "repository_clean",
    "repository_git_bootstrap", "repository_git_bootstrap_runtime_match",
    "repository_git_clone_contract_sha256",
    "codex_version_output", "approved_archive_sha256", "observed_archive_sha256",
    "extracted_binary_sha256", "runtime_root_binding_sha256",
    "dedicated_codex_home_binding_sha256", "control_plane", "lifecycle",
)
GIT_BOOTSTRAP_KEYS = (
    "schema", "authority", "package_name", "package_version",
    "package_architecture", "install_status", "binary_sha256",
    "version_output", "controller_argv_sha256",
    "preclone_qualification_argv_sha256", "raw_stdout_recorded",
    "raw_stderr_recorded",
)
LANE_STATUS_KEYS = (
    "provider_isolation_status", "mount_boundary_status", "process_cleanup_status",
    "codex_sandbox_network_status", "shell_environment_status", "config_status",
    "auth_status",
)
WORKER_ARGV_STAGES = (
    "load-envelope", "load-static-role", "environment-contract", "build-argv",
    "argv-policy", "schema-binding", "filesystem-binding",
)
WORKER_ARGV_REASON_CODES = (
    "none", "not-run", "envelope-invalid", "static-role-invalid",
    "environment-invalid", "argv-build-failed", "argv-policy-rejected",
    "schema-binding-invalid", "filesystem-binding-invalid",
)
CONTROL_PLANE_KEYS = (
    "schema", "authority", "codex_authenticated_attestation", "status",
    "pre_create_observed_at", "post_create_observed_at", "profile_name",
    "colima_version", "vm_backend", "architecture", "pre_create_profile_absent",
    "pre_create_runtime_data_absent", "fresh_instance", "existing_instance_reused",
    "existing_container_reused", "existing_volume_reused", "default_profile_reused",
    "activation_context_unchanged", "private_vm_disk",
    "repository_on_private_vm_disk", "runtime_root_on_private_vm_disk",
    "additional_disks", "instance_identity_sha256", "provider_configuration_sha256",
    "normalized_control_plane_sha256", "raw_paths_recorded",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def expected_runtime_configuration_intent() -> Dict[str, Any]:
    """Return the checker-owned T11 intent anchor, independent of the adapter."""
    rules_digest = sha256(REVIEWED_RULES_BYTES)
    static_configuration = {
        "approval_policy": "never",
        "model_reasoning_effort": "high",
        "shell_environment_policy": {
            "inherit": "none",
            "required_names": EXPECTED_SHELL_ENVIRONMENT_NAMES,
            "fixed_values": EXPECTED_FIXED_ENVIRONMENT,
            "reviewed_codex_injected_keys": REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS,
        },
        "overrides": EXPECTED_RUNTIME_OVERRIDES,
        "execpolicy": {
            "rules_path_relative_to_codex_home": REVIEWED_RULES_RELATIVE_PATH,
            "rules_profile_sha256": rules_digest,
        },
    }
    return {
        "schema": "t11-runtime-configuration-intent/v1",
        "authority": "adapter-authored",
        "effective_configuration_proven": False,
        "configuration_sha256": sha256(canonical_bytes(static_configuration)),
        "rules_profile_sha256": rules_digest,
        "dynamic_environment_values_excluded": ["CODEX_HOME", "HOME", "PATH", "TMPDIR"],
        "reviewed_codex_source_commit": OFFICIAL_CODEX_0150_SOURCE_COMMIT,
        "reviewed_codex_source_blobs": OFFICIAL_CODEX_0150_SOURCE_BLOBS,
        "reviewed_codex_injected_keys_sha256": sha256(canonical_bytes(
            REVIEWED_CODEX_INJECTED_ENVIRONMENT_KEYS
        )),
    }


def validate_memory_overrides(value: Any, label: str, errors: List[str]) -> None:
    """Pin the documented memory keys even if every producer drifts together."""
    if not isinstance(value, dict):
        errors.append(label + ": runtime override mapping must be an object")
        return
    observed_memory = {
        key for key in value
        if isinstance(key, str)
        and (key.startswith("memories.") or key.startswith("features.memory"))
    }
    if observed_memory != set(DOCUMENTED_MEMORY_OVERRIDES):
        errors.append(label + ": documented memory override key set drifted")
    for key, expected in DOCUMENTED_MEMORY_OVERRIDES.items():
        if value.get(key) is not expected:
            errors.append(label + ": documented memory override must be present and false: " + key)
    if LEGACY_MEMORY_OVERRIDES & set(value):
        errors.append(label + ": legacy undocumented memory override is forbidden")


def validate_runtime_override_mapping(value: Any, label: str, errors: List[str]) -> None:
    validate_memory_overrides(value, label, errors)
    if isinstance(value, dict) and value != EXPECTED_RUNTIME_OVERRIDES:
        errors.append(label + ": exact reviewed runtime override mapping drifted")


def validate_runtime_override_schema(schema: Any, errors: List[str]) -> None:
    label = "docs/agreements/runtime/task-execution-envelope.v1.schema.json"
    try:
        overrides = schema["properties"]["worker"]["properties"]["overrides"]
    except (KeyError, TypeError):
        errors.append(label + ": worker override schema is missing")
        return
    expected_properties = {
        key: {"const": value} for key, value in EXPECTED_RUNTIME_OVERRIDES.items()
    }
    if (
        not isinstance(overrides, dict)
        or overrides.get("type") != "object"
        or overrides.get("additionalProperties") is not False
        or overrides.get("required") != list(EXPECTED_RUNTIME_OVERRIDES)
        or overrides.get("properties") != expected_properties
    ):
        errors.append(label + ": exact reviewed runtime override schema drifted")
    validate_memory_overrides(
        {
            key: definition.get("const")
            for key, definition in overrides.get("properties", {}).items()
            if isinstance(definition, dict)
        } if isinstance(overrides, dict) else None,
        label,
        errors,
    )


def expected_control_plane_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(CONTROL_PLANE_KEYS),
        "properties": {
            "schema": {"const": "t11-colima-control-plane-evidence/v1"},
            "authority": {"const": "owner-authored"},
            "codex_authenticated_attestation": {"const": False},
            "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
            "pre_create_observed_at": {"type": ["string", "null"], "format": "date-time"},
            "post_create_observed_at": {"type": ["string", "null"], "format": "date-time"},
            "profile_name": {"anyOf": [{"const": "not-run"}, {"type": "string", "pattern": "^t11-e2e-[0-9a-f]{12}-01$"}]},
            "colima_version": {"enum": ["not-run", "0.10.1"]},
            "vm_backend": {"enum": ["not-run", "vz"]},
            "architecture": {"enum": ["not-run", "aarch64"]},
            "pre_create_profile_absent": {"type": "boolean"},
            "pre_create_runtime_data_absent": {"type": "boolean"},
            "fresh_instance": {"type": "boolean"},
            "existing_instance_reused": {"type": "boolean"},
            "existing_container_reused": {"type": "boolean"},
            "existing_volume_reused": {"type": "boolean"},
            "default_profile_reused": {"type": "boolean"},
            "activation_context_unchanged": {"type": "boolean"},
            "private_vm_disk": {"type": "boolean"},
            "repository_on_private_vm_disk": {"type": "boolean"},
            "runtime_root_on_private_vm_disk": {"type": "boolean"},
            "additional_disks": {"type": "integer", "minimum": 0, "maximum": 32},
            "instance_identity_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "provider_configuration_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "normalized_control_plane_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "raw_paths_recorded": {"const": False},
        },
        "allOf": [{
            "if": {"properties": {"status": {"const": "pass"}}, "required": ["status"]},
            "then": {"properties": {
                "colima_version": {"const": "0.10.1"},
                "vm_backend": {"const": "vz"},
                "architecture": {"const": "aarch64"},
                "pre_create_profile_absent": {"const": True},
                "pre_create_runtime_data_absent": {"const": True},
                "fresh_instance": {"const": True},
                "existing_instance_reused": {"const": False},
                "existing_container_reused": {"const": False},
                "existing_volume_reused": {"const": False},
                "default_profile_reused": {"const": False},
                "activation_context_unchanged": {"const": True},
                "private_vm_disk": {"const": True},
                "repository_on_private_vm_disk": {"const": True},
                "runtime_root_on_private_vm_disk": {"const": True},
                "additional_disks": {"const": 0},
            }},
        }],
    }


def expected_git_clone_contract(
    head: str,
    tree: str,
    public_branch: str = EXPECTED_T12_PUBLIC_BRANCH,
) -> Dict[str, Any]:
    if public_branch not in (
        EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH,
        EXPECTED_T12_PUBLIC_BRANCH,
    ):
        raise ValueError("Git clone contract branch is not reviewed")
    repository_url = "https://github.com/{}.git".format(EXPECTED_REPOSITORY)
    target = "<private-vm-repository>"
    prefix = [
        "/usr/bin/git", "--no-replace-objects",
        "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
    ]
    umask_wrapper = [
        "/usr/bin/python3", "-I", "-c",
        EXPECTED_STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT,
    ]
    return {
        "schema": "t11-git-clone-contract/v1",
        "authority": "reviewed-static-contract",
        "repository_url": repository_url,
        "branch": public_branch,
        "head": head,
        "tree": tree,
        "git_binary": "/usr/bin/git",
        "git_binary_sha256": APPROVED_GIT_BINARY_SHA256,
        "shell": False,
        "process_umask": "0077",
        "umask_wrapper_argv": umask_wrapper,
        "environment": {
            "policy": "replace",
            "fixed": dict(EXPECTED_STAGE_A1_GIT_FIXED_ENVIRONMENT),
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


def expected_git_clone_contract_sha256(
    head: str,
    tree: str,
    public_branch: str = EXPECTED_T12_PUBLIC_BRANCH,
) -> str:
    return sha256(canonical_bytes(expected_git_clone_contract(
        head, tree, public_branch,
    )))


def expected_git_bootstrap_evidence() -> Dict[str, Any]:
    return {
        "schema": "t11-git-bootstrap-evidence/v1",
        "authority": "owner/controller-authored",
        "package_name": "git",
        "package_version": APPROVED_GIT_PACKAGE_VERSION,
        "package_architecture": "arm64",
        "install_status": "installed",
        "binary_sha256": APPROVED_GIT_BINARY_SHA256,
        "version_output": APPROVED_GIT_VERSION_OUTPUT,
        "preclone_qualification_argv_sha256": (
            EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
        ),
        "controller_argv_sha256": EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256,
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def expected_not_run_git_bootstrap_evidence() -> Dict[str, Any]:
    return {
        "schema": "t11-git-bootstrap-evidence/v1",
        "authority": "owner/controller-authored",
        "package_name": "not-run",
        "package_version": "not-run",
        "package_architecture": "not-run",
        "install_status": "not-run",
        "binary_sha256": ZERO_SHA256,
        "version_output": "not-run",
        "preclone_qualification_argv_sha256": (
            EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
        ),
        "controller_argv_sha256": EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256,
        "raw_stdout_recorded": False,
        "raw_stderr_recorded": False,
    }


def expected_git_bootstrap_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(GIT_BOOTSTRAP_KEYS),
        "properties": {
            "schema": {"const": "t11-git-bootstrap-evidence/v1"},
            "authority": {"const": "owner/controller-authored"},
            "package_name": {"enum": ["git", "not-run"]},
            "package_version": {
                "enum": [APPROVED_GIT_PACKAGE_VERSION, "not-run"]
            },
            "package_architecture": {"enum": ["arm64", "not-run"]},
            "install_status": {"enum": ["installed", "not-run"]},
            "binary_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "version_output": {
                "enum": [APPROVED_GIT_VERSION_OUTPUT, "not-run"]
            },
            "preclone_qualification_argv_sha256": {
                "const": EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
            },
            "controller_argv_sha256": {
                "const": EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256
            },
            "raw_stdout_recorded": {"const": False},
            "raw_stderr_recorded": {"const": False},
        },
        "oneOf": [
            {"const": expected_git_bootstrap_evidence()},
            {"const": expected_not_run_git_bootstrap_evidence()},
        ],
    }


def expected_containment_provider_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(CONTAINMENT_PROVIDER_KEYS),
        "properties": {
            "schema": {"const": "t11-containment-provider-evidence/v1"},
            "authority": {"const": "adapter/owner-authored"},
            "codex_authenticated_attestation": {"const": False},
            "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
            "provider_kind": {"enum": ["not-run", "colima-vm"]},
            "profile_name": {"anyOf": [{"const": "not-run"}, {"type": "string", "pattern": "^t11-e2e-[0-9a-f]{12}-01$"}]},
            "vm_backend": {"enum": ["not-run", "vz"]},
            "architecture": {"enum": ["not-run", "aarch64"]},
            "native_architecture": {"type": "boolean"},
            "guest_os": {"type": "string", "minLength": 1, "maxLength": 128},
            "guest_kernel": {"type": "string", "minLength": 1, "maxLength": 256},
            "created_at": {"type": ["string", "null"], "format": "date-time"},
            "provider_configuration_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "effective_mount_inventory_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "provider_cache_mount_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "provider_cache_guest_mountpoint_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "host_mount_count": {"type": "integer", "minimum": 0, "maximum": 32},
            "host_mount_classifications": {
                "type": "array", "maxItems": 1, "uniqueItems": True,
                "items": {"const": "provider-internal-cache"},
            },
            "all_host_mounts_read_only": {"type": "boolean"},
            "provider_cache_only": {"type": "boolean"},
            "host_sensitive_mounts_absent": {"type": "boolean"},
            "unapproved_mounts_absent": {"type": "boolean"},
            "ssh_agent_forwarding": {"type": "boolean"},
            "dot_ssh_public_key_loading": {"type": "boolean"},
            "user_ssh_config_modified": {"type": "boolean"},
            "vm_instance_identity_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "public_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "public_tree": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "repository_clean": {"type": "boolean"},
            "repository_git_bootstrap": expected_git_bootstrap_schema(),
            "repository_git_bootstrap_runtime_match": {"type": "boolean"},
            "repository_git_clone_contract_sha256": {
                "type": "string", "pattern": "^[0-9a-f]{64}$"
            },
            "codex_version_output": {"type": "string", "minLength": 1, "maxLength": 128},
            "approved_archive_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "observed_archive_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "extracted_binary_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "runtime_root_binding_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "dedicated_codex_home_binding_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "control_plane": expected_control_plane_schema(),
            "lifecycle": {
                "type": "object", "additionalProperties": False,
                "required": ["destroy_required", "destroy_requested", "destroy_completed", "profile_absence_readback"],
                "properties": {
                    "destroy_required": {"type": "boolean"},
                    "destroy_requested": {"const": False},
                    "destroy_completed": {"const": False},
                    "profile_absence_readback": {"const": "not-run"},
                },
            },
        },
        "allOf": [{
            "if": {"properties": {"status": {"const": "pass"}}, "required": ["status"]},
            "then": {"properties": {
                "native_architecture": {"const": True},
                "provider_kind": {"const": "colima-vm"},
                "vm_backend": {"const": "vz"},
                "architecture": {"const": "aarch64"},
                "repository_clean": {"const": True},
                "repository_git_bootstrap": {
                    "const": expected_git_bootstrap_evidence()
                },
                "repository_git_bootstrap_runtime_match": {"const": True},
                "repository_git_clone_contract_sha256": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$",
                    "not": {"const": ZERO_SHA256},
                },
                "codex_version_output": {"const": APPROVED_CODEX_VERSION},
                "approved_archive_sha256": {"const": APPROVED_ARCHIVE_SHA256},
                "observed_archive_sha256": {"const": APPROVED_ARCHIVE_SHA256},
                "control_plane": {"properties": {"status": {"const": "pass"}}},
                "lifecycle": {"properties": {
                    "destroy_required": {"const": True},
                    "destroy_requested": {"const": False},
                    "destroy_completed": {"const": False},
                    "profile_absence_readback": {"const": "not-run"},
                }},
            }},
        }, {
            "if": {"properties": {"status": {"const": "not-run"}}, "required": ["status"]},
            "then": {"properties": {
                "repository_git_bootstrap": {
                    "const": expected_not_run_git_bootstrap_evidence()
                },
                "repository_git_bootstrap_runtime_match": {"const": False},
                "repository_git_clone_contract_sha256": {"const": ZERO_SHA256},
                "lifecycle": {"properties": {"destroy_required": {"const": False}}},
            }},
            "else": {"properties": {"lifecycle": {"properties": {"destroy_required": {"const": True}}}}},
        }],
    }


def expected_stage_a1_prerequisite_schema() -> Dict[str, Any]:
    string_field = {"type": "string", "minLength": 1, "maxLength": 128}
    digest_field = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema", "authority", "status", "reason_code", "guest",
            "apparmor", "bubblewrap", "git", "controller", "smoke",
        ],
        "properties": {
            "schema": {"const": "t11-bubblewrap-prerequisite-evidence/v1"},
            "authority": {"const": "adapter/owner-authored"},
            "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
            "reason_code": {"enum": STAGE_A1_REASON_CODES},
            "guest": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "distribution_id", "distribution_version",
                    "distribution_codename", "kernel", "architecture",
                ],
                "properties": {
                    "distribution_id": dict(string_field),
                    "distribution_version": dict(string_field),
                    "distribution_codename": dict(string_field),
                    "kernel": dict(string_field),
                    "architecture": dict(string_field),
                },
            },
            "apparmor": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "enabled", "unprivileged_userns_restriction",
                    "profile_required", "profile_source", "source_sha256",
                    "installed_sha256", "load_status",
                ],
                "properties": {
                    "enabled": {"type": "boolean"},
                    "unprivileged_userns_restriction": {
                        "enum": ["active", "inactive", "not-run", "UNCHECKABLE"]
                    },
                    "profile_required": {"type": "boolean"},
                    "profile_source": {
                        "enum": ["ubuntu-noble-apparmor-profiles", "not-run"]
                    },
                    "source_sha256": dict(digest_field),
                    "installed_sha256": dict(digest_field),
                    "load_status": {
                        "enum": ["enforce", "not-loaded", "not-run", "UNCHECKABLE"]
                    },
                },
            },
            "bubblewrap": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "package_name", "package_version", "package_architecture",
                    "install_status", "binary_sha256", "version_output",
                    "help_sha256",
                ],
                "properties": {
                    "package_name": {"enum": ["bubblewrap", "not-run"]},
                    "package_version": {"enum": [
                        APPROVED_BWRAP_PACKAGE_VERSION,
                        "not-run", "unrecognized",
                    ]},
                    "package_architecture": {
                        "enum": ["arm64", "not-run", "unrecognized"]
                    },
                    "install_status": {"enum": ["installed", "not-run"]},
                    "binary_sha256": dict(digest_field),
                    "version_output": {"enum": [
                        APPROVED_BWRAP_VERSION_OUTPUT,
                        "not-run", "unrecognized",
                    ]},
                    "help_sha256": dict(digest_field),
                },
            },
            "git": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "package_name", "package_version", "package_architecture",
                    "install_status", "binary_sha256", "version_output",
                ],
                "properties": {
                    "package_name": {"enum": ["git", "not-run"]},
                    "package_version": {"enum": [
                        APPROVED_GIT_PACKAGE_VERSION,
                        "not-run", "unrecognized",
                    ]},
                    "package_architecture": {
                        "enum": ["arm64", "not-run", "unrecognized"]
                    },
                    "install_status": {"enum": ["installed", "not-run"]},
                    "binary_sha256": dict(digest_field),
                    "version_output": {"enum": [
                        APPROVED_GIT_VERSION_OUTPUT,
                        "not-run", "unrecognized",
                    ]},
                },
            },
            "controller": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "argv_sha256", "shell", "model_invoked",
                    "device_auth_performed", "legacy_landlock_enabled",
                    "global_apparmor_userns_disabled",
                ],
                "properties": {
                    "argv_sha256": {
                        "const": EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256
                    },
                    "shell": {"const": False},
                    "model_invoked": {"const": False},
                    "device_auth_performed": {"const": False},
                    "legacy_landlock_enabled": {"const": False},
                    "global_apparmor_userns_disabled": {"const": False},
                },
            },
            "smoke": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "argv_sha256", "status", "reason_code", "exit_code",
                    "raw_stdout_recorded", "raw_stderr_recorded",
                ],
                "properties": {
                    "argv_sha256": {
                        "const": sha256(canonical_bytes(EXPECTED_STAGE_A1_SMOKE_ARGV))
                    },
                    "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "reason_code": {"enum": STAGE_A1_REASON_CODES},
                    "exit_code": {"type": ["integer", "null"], "minimum": 0, "maximum": 255},
                    "raw_stdout_recorded": {"const": False},
                    "raw_stderr_recorded": {"const": False},
                },
                "allOf": [{
                    "if": {"properties": {"status": {"const": "pass"}}, "required": ["status"]},
                    "then": {"properties": {
                        "reason_code": {"const": "none"},
                        "exit_code": {"const": 0},
                    }},
                }, {
                    "if": {"properties": {"status": {"const": "not-run"}}, "required": ["status"]},
                    "then": {"properties": {
                        "reason_code": {"const": "not-run"},
                        "exit_code": {"type": "null"},
                    }},
                }, {
                    "if": {"properties": {"status": {"const": "fail"}}, "required": ["status"]},
                    "then": {"properties": {
                        "reason_code": {"enum": sorted(STAGE_A1_SMOKE_FAILURE_CODES)},
                    }},
                }, {
                    "if": {"properties": {"reason_code": {"const": "nonzero-exit"}}, "required": ["reason_code"]},
                    "then": {"properties": {
                        "status": {"const": "fail"},
                        "exit_code": {"type": "integer", "minimum": 1, "maximum": 255},
                    }},
                }, {
                    "if": {"properties": {"reason_code": {"const": "signal"}}, "required": ["reason_code"]},
                    "then": {"properties": {
                        "status": {"const": "fail"},
                        "exit_code": {"type": "null"},
                    }},
                }, {
                    "if": {"properties": {"reason_code": {"const": "unexpected-output"}}, "required": ["reason_code"]},
                    "then": {"properties": {
                        "status": {"const": "fail"},
                        "exit_code": {"const": 0},
                    }},
                }, {
                    "if": {"properties": {"status": {"const": "UNCHECKABLE"}}, "required": ["status"]},
                    "then": {"properties": {
                        "reason_code": {"enum": sorted(STAGE_A1_UNCHECKABLE_CODES)},
                        "exit_code": {"type": "null"},
                    }},
                }],
            },
        },
        "allOf": [{
            "if": {"properties": {"status": {"const": "pass"}}, "required": ["status"]},
            "then": {"properties": {
                "reason_code": {"const": "none"},
                "guest": {"properties": {
                    "distribution_id": {"const": "ubuntu"},
                    "distribution_version": {"const": "24.04"},
                    "distribution_codename": {"const": "noble"},
                    "kernel": {
                        "type": "string",
                        "pattern": "^[0-9][0-9A-Za-z._+~-]{0,127}$",
                    },
                    "architecture": {"const": "aarch64"},
                }},
                "apparmor": {"properties": {
                    "enabled": {"const": True},
                    "unprivileged_userns_restriction": {"const": "active"},
                    "profile_required": {"const": True},
                    "profile_source": {"const": "ubuntu-noble-apparmor-profiles"},
                    "source_sha256": {"const": APPROVED_BWRAP_PROFILE_SHA256},
                    "installed_sha256": {"const": APPROVED_BWRAP_PROFILE_SHA256},
                    "load_status": {"const": "enforce"},
                }},
                "bubblewrap": {"properties": {
                    "package_name": {"const": "bubblewrap"},
                    "package_version": {"const": APPROVED_BWRAP_PACKAGE_VERSION},
                    "package_architecture": {"const": "arm64"},
                    "install_status": {"const": "installed"},
                    "binary_sha256": {"const": APPROVED_BWRAP_BINARY_SHA256},
                    "version_output": {"const": APPROVED_BWRAP_VERSION_OUTPUT},
                    "help_sha256": {
                        "type": "string", "pattern": "^[0-9a-f]{64}$",
                        "not": {"const": ZERO_SHA256},
                    },
                }},
                "git": {"properties": {
                    "package_name": {"const": "git"},
                    "package_version": {"const": APPROVED_GIT_PACKAGE_VERSION},
                    "package_architecture": {"const": "arm64"},
                    "install_status": {"const": "installed"},
                    "binary_sha256": {"const": APPROVED_GIT_BINARY_SHA256},
                    "version_output": {"const": APPROVED_GIT_VERSION_OUTPUT},
                }},
                "smoke": {"properties": {
                    "status": {"const": "pass"},
                    "reason_code": {"const": "none"},
                    "exit_code": {"const": 0},
                }},
            }},
        }, {
            "if": {"properties": {"status": {"const": "not-run"}}, "required": ["status"]},
            "then": {"properties": {
                "reason_code": {"const": "not-run"},
                "guest": {"const": expected_not_run_stage_a1_prerequisite()["guest"]},
                "apparmor": {"const": expected_not_run_stage_a1_prerequisite()["apparmor"]},
                "bubblewrap": {"const": expected_not_run_stage_a1_prerequisite()["bubblewrap"]},
                "git": {"const": expected_not_run_stage_a1_prerequisite()["git"]},
                "smoke": {"properties": {"status": {"const": "not-run"}}},
            }},
        }, {
            "if": {"properties": {"status": {"const": "fail"}}, "required": ["status"]},
            "then": {"properties": {
                "reason_code": {"enum": sorted(
                    STAGE_A1_PRECONDITION_FAILURE_CODES
                    | STAGE_A1_SMOKE_FAILURE_CODES
                )},
                "smoke": {"properties": {
                    "status": {"enum": ["fail", "not-run"]},
                }},
            }},
        }, {
            "if": {"properties": {
                "reason_code": {"enum": sorted(STAGE_A1_PRECONDITION_FAILURE_CODES)},
            }, "required": ["reason_code"]},
            "then": {"properties": {
                "status": {"const": "fail"},
                "smoke": {"properties": {
                    "status": {"const": "not-run"},
                    "reason_code": {"const": "not-run"},
                }},
            }},
        }, *[{
            "if": {"properties": {
                "reason_code": {"const": reason},
            }, "required": ["reason_code"]},
            "then": {"properties": {
                "status": {"const": "fail"},
                "smoke": {"properties": {
                    "status": {"const": "fail"},
                    "reason_code": {"const": reason},
                }},
            }},
        } for reason in sorted(STAGE_A1_SMOKE_FAILURE_CODES)],
        *[{
            "if": {"properties": {
                "reason_code": {"const": reason},
                "status": {"const": "UNCHECKABLE"},
            }, "required": ["reason_code", "status"]},
            "then": {"properties": {
                "smoke": {"properties": {
                    "status": {"const": "UNCHECKABLE"},
                    "reason_code": {"const": reason},
                }},
            }},
        } for reason in sorted(STAGE_A1_UNCHECKABLE_CODES)],
        {
            "if": {"properties": {"status": {"const": "UNCHECKABLE"}}, "required": ["status"]},
            "then": {"properties": {
                "reason_code": {"enum": sorted(STAGE_A1_UNCHECKABLE_CODES)},
                "smoke": {"properties": {"status": {"const": "UNCHECKABLE"}}},
            }},
        }],
    }


def expected_profile_evidence_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "configuration_intent", "diagnostic_health", "exact_worker_argv",
            "shell_environment_behavior", "network_sandbox_behavior",
            "bubblewrap_prerequisite",
            "containment_provider", "lane_statuses",
        ],
        "properties": {
            "configuration_intent": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema", "authority", "effective_configuration_proven",
                    "configuration_sha256", "rules_profile_sha256",
                    "dynamic_environment_values_excluded",
                    "reviewed_codex_source_commit", "reviewed_codex_source_blobs",
                    "reviewed_codex_injected_keys_sha256",
                ],
                "properties": {
                    "schema": {"const": "t11-runtime-configuration-intent/v1"},
                    "authority": {"const": "adapter-authored"},
                    "effective_configuration_proven": {"const": False},
                    "configuration_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "rules_profile_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "dynamic_environment_values_excluded": {
                        "const": ["CODEX_HOME", "HOME", "PATH", "TMPDIR"]
                    },
                    "reviewed_codex_source_commit": {
                        "const": OFFICIAL_CODEX_0150_SOURCE_COMMIT
                    },
                    "reviewed_codex_source_blobs": {
                        "const": OFFICIAL_CODEX_0150_SOURCE_BLOBS
                    },
                    "reviewed_codex_injected_keys_sha256": {
                        "type": "string", "pattern": "^[0-9a-f]{64}$"
                    },
                },
            },
            "diagnostic_health": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "classification", "status", "checks",
                    "codex_issued_effective_configuration_proof",
                ],
                "properties": {
                    "classification": {"const": "diagnostic-only"},
                    "status": {"enum": ["pass", "pass-with-advisory-warning", "fail", "not-run", "UNCHECKABLE"]},
                    "checks": {
                        "type": "array", "maxItems": 64,
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["id", "category", "status"],
                            "properties": {
                                "id": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[a-z0-9][a-z0-9._-]*$"},
                                "category": {"type": "string", "minLength": 1, "maxLength": 64, "pattern": "^[a-z0-9][a-z0-9._-]*$"},
                                "status": {"enum": ["ok", "warning", "fail"]},
                            },
                        },
                    },
                    "codex_issued_effective_configuration_proof": {"const": False},
                },
            },
            "exact_worker_argv": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "status", "stage", "reason_code", "rules_bypass_absent",
                    "dynamic_task_data_stdin_only",
                ],
                "properties": {
                    "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "stage": {"enum": list(WORKER_ARGV_STAGES)},
                    "reason_code": {"enum": list(WORKER_ARGV_REASON_CODES)},
                    "rules_bypass_absent": {"type": "boolean"},
                    "dynamic_task_data_stdin_only": {"type": "boolean"},
                },
                "allOf": [{
                    "if": {
                        "properties": {"status": {"const": "pass"}},
                        "required": ["status"],
                    },
                    "then": {"properties": {
                        "reason_code": {"const": "none"},
                        "rules_bypass_absent": {"const": True},
                        "dynamic_task_data_stdin_only": {"const": True},
                    }},
                }],
            },
            "shell_environment_behavior": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema", "authority", "status", "reason_code",
                    "unexpected_key_count", "unexpected_key_names_sha256",
                    "secret_shaped_key_count",
                ],
                "properties": {
                    "schema": {"const": "t11-shell-environment-evidence/v1"},
                    "authority": {"const": "adapter-authored"},
                    "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "reason_code": {"enum": list(SHELL_ENVIRONMENT_REASON_CODES)},
                    "unexpected_key_count": {"type": "integer", "minimum": 0, "maximum": 64},
                    "unexpected_key_names_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "secret_shaped_key_count": {"type": "integer", "minimum": 0, "maximum": 64},
                },
                "allOf": [
                    {
                        "if": {"properties": {"reason_code": {"const": "none"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "status": {"const": "pass"},
                            "unexpected_key_count": {"const": 0},
                            "unexpected_key_names_sha256": {"const": sha256(canonical_bytes([]))},
                            "secret_shaped_key_count": {"const": 0},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "not-run"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "status": {"const": "not-run"},
                            "unexpected_key_count": {"const": 0},
                            "unexpected_key_names_sha256": {"const": ZERO_SHA256},
                            "secret_shaped_key_count": {"const": 0},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": sorted(SHELL_ENVIRONMENT_UNCHECKABLE_REASONS)}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "status": {"const": "UNCHECKABLE"},
                            "unexpected_key_count": {"const": 0},
                            "unexpected_key_names_sha256": {"const": ZERO_SHA256},
                            "secret_shaped_key_count": {"const": 0},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            reason for reason in SHELL_ENVIRONMENT_REASON_CODES
                            if reason not in {"none", "not-run", *SHELL_ENVIRONMENT_UNCHECKABLE_REASONS}
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {"status": {"const": "fail"}}},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "unexpected-key-set"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unexpected_key_count": {"minimum": 1},
                            "unexpected_key_names_sha256": {"not": {"enum": [
                                ZERO_SHA256, sha256(canonical_bytes([])),
                            ]}},
                            "secret_shaped_key_count": {"const": 0},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "secret-shaped-key"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unexpected_key_count": {"minimum": 1},
                            "unexpected_key_names_sha256": {"not": {"enum": [
                                ZERO_SHA256, sha256(canonical_bytes([])),
                            ]}},
                            "secret_shaped_key_count": {"minimum": 1},
                        }},
                    },
                ],
            },
            "network_sandbox_behavior": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema", "authority", "status", "reason_code",
                    "unsandboxed_control_accepted", "unsandboxed_control_closed",
                    "parent_netns_sha256", "sandbox_netns_sha256", "netns_different",
                    "network_marker_status", "sandbox_connect_status",
                    "sandbox_connect_errno", "process_cleanup_status", "process_reaped",
                    "raw_stdout_recorded", "raw_stderr_recorded",
                ],
                "properties": {
                    "schema": {"const": "t11-network-sandbox-evidence/v1"},
                    "authority": {"const": "adapter-authored"},
                    "status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "reason_code": {"enum": list(NETWORK_SANDBOX_REASON_CODES)},
                    "unsandboxed_control_accepted": {"type": "boolean"},
                    "unsandboxed_control_closed": {"type": "boolean"},
                    "parent_netns_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "sandbox_netns_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "netns_different": {"type": "boolean"},
                    "network_marker_status": {"enum": ["exact-1", "missing", "mismatch", "not-run", "UNCHECKABLE"]},
                    "sandbox_connect_status": {"enum": ["denied", "succeeded", "not-run", "UNCHECKABLE"]},
                    "sandbox_connect_errno": {"enum": [*APPROVED_NETWORK_DENIAL_ERRNOS, "none", "not-run", "unapproved"]},
                    "process_cleanup_status": {"enum": ["pass", "not-run", "UNCHECKABLE"]},
                    "process_reaped": {"type": "boolean"},
                    "raw_stdout_recorded": {"const": False},
                    "raw_stderr_recorded": {"const": False},
                },
                "allOf": [
                    {
                        "if": {"properties": {"reason_code": {"const": "none"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "status": {"const": "pass"},
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "netns_different": {"const": True},
                            "network_marker_status": {"const": "exact-1"},
                            "sandbox_connect_status": {"const": "denied"},
                            "sandbox_connect_errno": {"enum": list(APPROVED_NETWORK_DENIAL_ERRNOS)},
                            "process_cleanup_status": {"const": "pass"},
                            "process_reaped": {"const": True},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "not-run"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "status": {"const": "not-run"},
                            "unsandboxed_control_accepted": {"const": False},
                            "unsandboxed_control_closed": {"const": False},
                            "parent_netns_sha256": {"const": ZERO_SHA256},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "not-run"},
                            "sandbox_connect_status": {"const": "not-run"},
                            "sandbox_connect_errno": {"const": "not-run"},
                            "process_cleanup_status": {"const": "not-run"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": sorted(NETWORK_SANDBOX_FAIL_REASONS)}}, "required": ["reason_code"]},
                        "then": {"properties": {"status": {"const": "fail"}}},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            reason for reason in NETWORK_SANDBOX_REASON_CODES
                            if reason not in {"none", "not-run", *NETWORK_SANDBOX_FAIL_REASONS}
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {"status": {"const": "UNCHECKABLE"}}},
                    },
                    {
                        "if": {"properties": {"process_cleanup_status": {"const": "not-run"}}, "required": ["process_cleanup_status"]},
                        "then": {"properties": {
                            "reason_code": {"const": "not-run"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"sandbox_connect_status": {"const": "succeeded"}}, "required": ["sandbox_connect_status"]},
                        "then": {"properties": {"sandbox_connect_errno": {"const": "none"}}},
                    },
                    {
                        "if": {"properties": {"sandbox_connect_status": {"const": "denied"}}, "required": ["sandbox_connect_status"]},
                        "then": {"properties": {"sandbox_connect_errno": {"enum": [
                            *APPROVED_NETWORK_DENIAL_ERRNOS, "unapproved",
                        ]}}},
                    },
                    {
                        "if": {"properties": {"sandbox_connect_status": {"const": "UNCHECKABLE"}}, "required": ["sandbox_connect_status"]},
                        "then": {"properties": {"sandbox_connect_errno": {"const": "unapproved"}}},
                    },
                    {
                        "if": {"properties": {"sandbox_connect_status": {"const": "not-run"}}, "required": ["sandbox_connect_status"]},
                        "then": {"properties": {"sandbox_connect_errno": {"const": "not-run"}}},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            "control-unavailable", "control-not-accepted",
                            "control-peer-mismatch",
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": False},
                            "unsandboxed_control_closed": {"const": False},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                            "process_cleanup_status": {"const": "UNCHECKABLE"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "control-not-closed"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": False},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                            "process_cleanup_status": {"const": "UNCHECKABLE"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "parent-netns-unavailable"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": False},
                            "unsandboxed_control_closed": {"const": False},
                            "parent_netns_sha256": {"const": ZERO_SHA256},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                            "process_cleanup_status": {"const": "UNCHECKABLE"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            "sandbox-netns-unavailable", "process-nonzero",
                            "malformed-probe-output",
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                            "process_cleanup_status": {"const": "pass"},
                            "process_reaped": {"const": True},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            "process-timeout", "output-overflow",
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                        }, "oneOf": [
                            {"properties": {"process_cleanup_status": {"const": "pass"}, "process_reaped": {"const": True}}},
                            {"properties": {"process_cleanup_status": {"const": "UNCHECKABLE"}, "process_reaped": {"const": False}}},
                        ]},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "process-not-reaped"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"const": ZERO_SHA256},
                            "netns_different": {"const": False},
                            "network_marker_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                            "process_cleanup_status": {"const": "UNCHECKABLE"},
                            "process_reaped": {"const": False},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "netns-not-separated"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "netns_different": {"const": False},
                            "network_marker_status": {"enum": ["exact-1", "missing", "mismatch"]},
                            "sandbox_connect_status": {"enum": ["denied", "succeeded", "UNCHECKABLE"]},
                            "process_cleanup_status": {"const": "pass"},
                            "process_reaped": {"const": True},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"enum": [
                            "network-marker-missing", "network-marker-mismatch",
                            "sandbox-connection-succeeded", "socket-creation-unavailable",
                            "unapproved-denial-errno",
                        ]}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "unsandboxed_control_accepted": {"const": True},
                            "unsandboxed_control_closed": {"const": True},
                            "parent_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "sandbox_netns_sha256": {"not": {"const": ZERO_SHA256}},
                            "netns_different": {"const": True},
                            "process_cleanup_status": {"const": "pass"},
                            "process_reaped": {"const": True},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "network-marker-missing"}}, "required": ["reason_code"]},
                        "then": {"properties": {"network_marker_status": {"const": "missing"}}},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "network-marker-mismatch"}}, "required": ["reason_code"]},
                        "then": {"properties": {"network_marker_status": {"const": "mismatch"}}},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "sandbox-connection-succeeded"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "network_marker_status": {"const": "exact-1"},
                            "sandbox_connect_status": {"const": "succeeded"},
                            "sandbox_connect_errno": {"const": "none"},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "socket-creation-unavailable"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "network_marker_status": {"const": "exact-1"},
                            "sandbox_connect_status": {"const": "UNCHECKABLE"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                        }},
                    },
                    {
                        "if": {"properties": {"reason_code": {"const": "unapproved-denial-errno"}}, "required": ["reason_code"]},
                        "then": {"properties": {
                            "network_marker_status": {"const": "exact-1"},
                            "sandbox_connect_status": {"const": "denied"},
                            "sandbox_connect_errno": {"const": "unapproved"},
                        }},
                    },
                ],
            },
            "bubblewrap_prerequisite": expected_stage_a1_prerequisite_schema(),
            "containment_provider": expected_containment_provider_schema(),
            "lane_statuses": {
                "type": "object",
                "additionalProperties": False,
                "required": list(LANE_STATUS_KEYS),
                "properties": {
                    "provider_isolation_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "mount_boundary_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "process_cleanup_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "codex_sandbox_network_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "shell_environment_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "config_status": {"enum": ["pass", "fail", "not-run", "UNCHECKABLE"]},
                    "auth_status": {"enum": ["signed-in-client", "api-key", "unavailable", "unknown"]},
                },
            },
        },
    }


def expected_not_run_control_plane() -> Dict[str, Any]:
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
        "instance_identity_sha256": ZERO_SHA256,
        "provider_configuration_sha256": ZERO_SHA256,
        "normalized_control_plane_sha256": ZERO_SHA256,
        "raw_paths_recorded": False,
    }


def normalized_control_plane_sha256(value: Mapping[str, Any]) -> str:
    return sha256(canonical_bytes({
        key: value[key] for key in CONTROL_PLANE_KEYS
        if key != "normalized_control_plane_sha256"
    }))


def validate_control_plane(value: Any, provider: Mapping[str, Any], label: str, errors: List[str]) -> None:
    if not isinstance(value, dict) or set(value) != set(CONTROL_PLANE_KEYS):
        errors.append(label + ": closed control-plane evidence shape drifted")
        return
    if (
        value.get("schema") != "t11-colima-control-plane-evidence/v1"
        or value.get("authority") != "owner-authored"
        or value.get("codex_authenticated_attestation") is not False
        or value.get("status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}
        or value.get("raw_paths_recorded") is not False
    ):
        errors.append(label + ": control-plane identity/authority/status is invalid")
    for key in ("instance_identity_sha256", "provider_configuration_sha256", "normalized_control_plane_sha256"):
        if not isinstance(value.get(key), str) or SHA.fullmatch(value[key]) is None:
            errors.append(label + ": invalid control-plane digest field " + key)
    for key in (
        "pre_create_profile_absent", "pre_create_runtime_data_absent", "fresh_instance",
        "existing_instance_reused", "existing_container_reused", "existing_volume_reused",
        "default_profile_reused", "activation_context_unchanged",
        "private_vm_disk", "repository_on_private_vm_disk", "runtime_root_on_private_vm_disk",
    ):
        if type(value.get(key)) is not bool:
            errors.append(label + ": invalid control-plane boolean " + key)
    if type(value.get("additional_disks")) is not int or not 0 <= value["additional_disks"] <= 32:
        errors.append(label + ": invalid control-plane additional disk count")
    if value.get("status") == "not-run":
        if value != expected_not_run_control_plane():
            errors.append(label + ": not-run control-plane evidence must use the exact non-claiming sentinel")
        return
    for key in ("pre_create_observed_at", "post_create_observed_at"):
        if not isinstance(value.get(key), str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value[key]) is None:
            errors.append(label + ": invalid control-plane timestamp " + key)
    if value.get("status") == "pass":
        claims = {
            "colima_version": "0.10.1", "vm_backend": "vz", "architecture": "aarch64",
            "pre_create_profile_absent": True, "pre_create_runtime_data_absent": True,
            "fresh_instance": True, "existing_instance_reused": False,
            "existing_container_reused": False, "existing_volume_reused": False,
            "default_profile_reused": False, "activation_context_unchanged": True,
            "private_vm_disk": True, "repository_on_private_vm_disk": True,
            "runtime_root_on_private_vm_disk": True, "additional_disks": 0,
        }
        for key, expected in claims.items():
            if value.get(key) != expected:
                errors.append(label + ": passing control-plane evidence drifted: " + key)
        for key in ("instance_identity_sha256", "provider_configuration_sha256"):
            if value.get(key) == ZERO_SHA256:
                errors.append(label + ": passing control-plane evidence uses a placeholder digest")
        if value.get("normalized_control_plane_sha256") != normalized_control_plane_sha256(value):
            errors.append(label + ": normalized control-plane digest is not independently reproducible")
        for key in ("profile_name", "vm_backend", "architecture", "instance_identity_sha256", "provider_configuration_sha256"):
            provider_key = {
                "instance_identity_sha256": "vm_instance_identity_sha256"
            }.get(key, key)
            if value.get(key) != provider.get(provider_key):
                errors.append(label + ": control-plane/provider cross-binding drifted: " + key)
        if value.get("pre_create_observed_at", "") > str(provider.get("created_at", "")) or str(provider.get("created_at", "")) > value.get("post_create_observed_at", ""):
            errors.append(label + ": control-plane create chronology is invalid")


def expected_not_run_containment_provider() -> Dict[str, Any]:
    return {
        "schema": "t11-containment-provider-evidence/v1",
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
        "provider_configuration_sha256": ZERO_SHA256,
        "effective_mount_inventory_sha256": ZERO_SHA256,
        "provider_cache_mount_sha256": ZERO_SHA256,
        "provider_cache_guest_mountpoint_sha256": ZERO_SHA256,
        "host_mount_count": 0,
        "host_mount_classifications": [],
        "all_host_mounts_read_only": False,
        "provider_cache_only": False,
        "host_sensitive_mounts_absent": False,
        "unapproved_mounts_absent": False,
        "ssh_agent_forwarding": False,
        "dot_ssh_public_key_loading": False,
        "user_ssh_config_modified": False,
        "vm_instance_identity_sha256": ZERO_SHA256,
        "public_head": ZERO_OID,
        "public_tree": ZERO_OID,
        "repository_clean": False,
        "repository_git_bootstrap": expected_not_run_git_bootstrap_evidence(),
        "repository_git_bootstrap_runtime_match": False,
        "repository_git_clone_contract_sha256": ZERO_SHA256,
        "codex_version_output": "unavailable",
        "approved_archive_sha256": ZERO_SHA256,
        "observed_archive_sha256": ZERO_SHA256,
        "extracted_binary_sha256": ZERO_SHA256,
        "runtime_root_binding_sha256": ZERO_SHA256,
        "dedicated_codex_home_binding_sha256": ZERO_SHA256,
        "control_plane": expected_not_run_control_plane(),
        "lifecycle": {
            "destroy_required": False,
            "destroy_requested": False,
            "destroy_completed": False,
            "profile_absence_readback": "not-run",
        },
    }


def validate_containment_provider(
    value: Any,
    profile_status: Any,
    label: str,
    errors: List[str],
    clone_public_branch: str = EXPECTED_T12_PUBLIC_BRANCH,
) -> None:
    if not isinstance(value, dict) or set(value) != set(CONTAINMENT_PROVIDER_KEYS):
        errors.append(label + ": closed containment-provider evidence shape drifted")
        return
    if (
        value.get("schema") != "t11-containment-provider-evidence/v1"
        or value.get("authority") != "adapter/owner-authored"
        or value.get("codex_authenticated_attestation") is not False
    ):
        errors.append(label + ": provider evidence authority drifted")
    if value.get("status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}:
        errors.append(label + ": containment-provider status is invalid")
    if not isinstance(value.get("profile_name"), str) or (
        value["profile_name"] != "not-run"
        and re.fullmatch(r"t11-e2e-[0-9a-f]{12}-01", value["profile_name"]) is None
    ):
        errors.append(label + ": containment profile name is invalid")
    for key in (
        "provider_configuration_sha256", "effective_mount_inventory_sha256",
        "provider_cache_mount_sha256", "provider_cache_guest_mountpoint_sha256",
        "vm_instance_identity_sha256", "observed_archive_sha256",
        "extracted_binary_sha256", "runtime_root_binding_sha256",
        "dedicated_codex_home_binding_sha256", "approved_archive_sha256",
        "repository_git_clone_contract_sha256",
    ):
        if not isinstance(value.get(key), str) or SHA.fullmatch(value[key]) is None:
            errors.append(label + ": invalid provider digest field " + key)
    for key in ("public_head", "public_tree"):
        if not isinstance(value.get(key), str) or OID.fullmatch(value[key]) is None:
            errors.append(label + ": invalid provider Git field " + key)
    for key in (
        "native_architecture", "all_host_mounts_read_only", "provider_cache_only",
        "host_sensitive_mounts_absent", "unapproved_mounts_absent",
        "ssh_agent_forwarding", "dot_ssh_public_key_loading",
        "user_ssh_config_modified", "repository_clean",
        "repository_git_bootstrap_runtime_match",
    ):
        if type(value.get(key)) is not bool:
            errors.append(label + ": provider boolean field is invalid: " + key)
    if type(value.get("host_mount_count")) is not int or not 0 <= value["host_mount_count"] <= 32:
        errors.append(label + ": provider host mount count is invalid")
    classifications = value.get("host_mount_classifications")
    if not isinstance(classifications, list) or classifications not in ([], ["provider-internal-cache"]):
        errors.append(label + ": provider host mount classification is invalid")
    for key in ("guest_os", "guest_kernel", "codex_version_output"):
        if not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 256:
            errors.append(label + ": provider string field is invalid: " + key)
    if value.get("created_at") is not None and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", str(value.get("created_at"))) is None:
        errors.append(label + ": provider creation timestamp is invalid")
    lifecycle = value.get("lifecycle")
    expected_lifecycle = {
        "destroy_required": value.get("status") != "not-run",
        "destroy_requested": False,
        "destroy_completed": False,
        "profile_absence_readback": "not-run",
    }
    if lifecycle != expected_lifecycle:
        errors.append(label + ": pre-live lifecycle must require later destruction without claiming it occurred")
    validate_control_plane(value.get("control_plane"), value, label, errors)
    git_bootstrap = value.get("repository_git_bootstrap")
    if git_bootstrap not in (
        expected_git_bootstrap_evidence(),
        expected_not_run_git_bootstrap_evidence(),
    ):
        errors.append(label + ": repository Git bootstrap evidence drifted")

    provider_status = value.get("status")
    if provider_status == "not-run" and value != expected_not_run_containment_provider():
        errors.append(label + ": not-run containment evidence must use the exact non-claiming placeholder")
    if provider_status == "pass":
        pass_claims = {
            "native_architecture": True,
            "provider_kind": "colima-vm",
            "vm_backend": "vz",
            "architecture": "aarch64",
            "repository_clean": True,
            "repository_git_bootstrap": expected_git_bootstrap_evidence(),
            "repository_git_bootstrap_runtime_match": True,
            "codex_version_output": APPROVED_CODEX_VERSION,
            "approved_archive_sha256": APPROVED_ARCHIVE_SHA256,
            "observed_archive_sha256": APPROVED_ARCHIVE_SHA256,
        }
        for key, expected in pass_claims.items():
            if value.get(key) != expected:
                errors.append(label + ": passing provider evidence drifted: " + key)
        for key in (
            "provider_configuration_sha256", "vm_instance_identity_sha256",
            "extracted_binary_sha256",
            "runtime_root_binding_sha256", "dedicated_codex_home_binding_sha256",
        ):
            if value.get(key) == ZERO_SHA256:
                errors.append(label + ": passing provider evidence uses placeholder digest: " + key)
        if value.get("public_head") == ZERO_OID or value.get("public_tree") == ZERO_OID:
            errors.append(label + ": passing provider evidence uses placeholder Git binding")
        elif value.get("profile_name") != "t11-e2e-{}-01".format(value["public_head"][:12]):
            errors.append(label + ": provider profile name is not bound to the public head")
        if value.get("repository_git_clone_contract_sha256") != (
            expected_git_clone_contract_sha256(
                str(value.get("public_head")), str(value.get("public_tree")),
                clone_public_branch,
            )
        ):
            errors.append(label + ": provider Git clone contract does not bind the exact head/tree")
        if value.get("guest_os") == "not-run" or value.get("guest_kernel") == "not-run":
            errors.append(label + ": passing provider evidence omits guest OS/kernel")
        if value.get("created_at") is None:
            errors.append(label + ": passing provider evidence omits creation time")
        if value.get("control_plane", {}).get("status") != "pass":
            errors.append(label + ": passing provider evidence lacks passing control-plane evidence")
    if profile_status in {"match", "probe-only-match"} and provider_status != "pass":
        errors.append(label + ": matching profile requires passing containment-provider evidence")


def expected_not_run_stage_a1_prerequisite() -> Dict[str, Any]:
    return {
        "schema": "t11-bubblewrap-prerequisite-evidence/v1",
        "authority": "adapter/owner-authored",
        "status": "not-run",
        "reason_code": "not-run",
        "guest": {
            "distribution_id": "not-run", "distribution_version": "not-run",
            "distribution_codename": "not-run", "kernel": "not-run",
            "architecture": "not-run",
        },
        "apparmor": {
            "enabled": False, "unprivileged_userns_restriction": "not-run",
            "profile_required": False, "profile_source": "not-run",
            "source_sha256": ZERO_SHA256, "installed_sha256": ZERO_SHA256,
            "load_status": "not-run",
        },
        "bubblewrap": {
            "package_name": "not-run", "package_version": "not-run",
            "package_architecture": "not-run", "install_status": "not-run",
            "binary_sha256": ZERO_SHA256, "version_output": "not-run",
            "help_sha256": ZERO_SHA256,
        },
        "git": {
            "package_name": "not-run", "package_version": "not-run",
            "package_architecture": "not-run", "install_status": "not-run",
            "binary_sha256": ZERO_SHA256, "version_output": "not-run",
        },
        "controller": {
            "argv_sha256": EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256,
            "shell": False, "model_invoked": False,
            "device_auth_performed": False, "legacy_landlock_enabled": False,
            "global_apparmor_userns_disabled": False,
        },
        "smoke": {
            "argv_sha256": sha256(canonical_bytes(EXPECTED_STAGE_A1_SMOKE_ARGV)),
            "status": "not-run", "reason_code": "not-run", "exit_code": None,
            "raw_stdout_recorded": False, "raw_stderr_recorded": False,
        },
    }


def validate_stage_a1_prerequisite(value: Any, profile_status: Any, label: str, errors: List[str]) -> None:
    expected_keys = set(expected_not_run_stage_a1_prerequisite())
    if not isinstance(value, dict) or set(value) != expected_keys:
        errors.append(label + ": closed Stage A.1 prerequisite evidence shape drifted")
        return
    if (
        value.get("schema") != "t11-bubblewrap-prerequisite-evidence/v1"
        or value.get("authority") != "adapter/owner-authored"
        or value.get("status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}
        or value.get("reason_code") not in set(STAGE_A1_REASON_CODES)
    ):
        errors.append(label + ": Stage A.1 prerequisite identity/status drifted")
        return
    if value.get("status") == "not-run" and value != expected_not_run_stage_a1_prerequisite():
        errors.append(label + ": Stage A.1 not-run sentinel drifted")
    controller = value.get("controller")
    if controller != expected_not_run_stage_a1_prerequisite()["controller"]:
        errors.append(label + ": Stage A.1 controller shell/model/auth boundary drifted")
    smoke = value.get("smoke")
    if not isinstance(smoke, dict) or set(smoke) != {
        "argv_sha256", "status", "reason_code", "exit_code",
        "raw_stdout_recorded", "raw_stderr_recorded",
    }:
        errors.append(label + ": Stage A.1 smoke shape drifted")
        return
    if (
        smoke.get("argv_sha256") != sha256(canonical_bytes(EXPECTED_STAGE_A1_SMOKE_ARGV))
        or smoke.get("raw_stdout_recorded") is not False
        or smoke.get("raw_stderr_recorded") is not False
        or smoke.get("status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}
        or smoke.get("reason_code") not in set(STAGE_A1_REASON_CODES)
    ):
        errors.append(label + ": Stage A.1 smoke privacy/status boundary drifted")
    smoke_status = smoke.get("status")
    smoke_reason = smoke.get("reason_code")
    smoke_exit = smoke.get("exit_code")
    if smoke_status == "pass" and (smoke_reason != "none" or smoke_exit != 0):
        errors.append(label + ": passing Stage A.1 smoke evidence is inconsistent")
    elif smoke_status == "not-run" and (
        smoke_reason != "not-run" or smoke_exit is not None
    ):
        errors.append(label + ": not-run Stage A.1 smoke evidence is inconsistent")
    elif smoke_status == "fail":
        invalid_exit = (
            smoke_reason not in STAGE_A1_SMOKE_FAILURE_CODES
            or (
                smoke_reason == "nonzero-exit"
                and (
                    type(smoke_exit) is not int
                    or not 1 <= smoke_exit <= 255
                )
            )
            or (smoke_reason == "signal" and smoke_exit is not None)
            or (smoke_reason == "unexpected-output" and smoke_exit != 0)
        )
        if invalid_exit:
            errors.append(label + ": failed Stage A.1 smoke classification drifted")
    elif smoke_status == "UNCHECKABLE" and (
        smoke_reason not in STAGE_A1_UNCHECKABLE_CODES or smoke_exit is not None
    ):
        errors.append(label + ": uncheckable Stage A.1 smoke classification drifted")
    if value.get("status") == "pass":
        guest = value.get("guest")
        apparmor = value.get("apparmor")
        bubblewrap = value.get("bubblewrap")
        git = value.get("git")
        if not isinstance(guest, dict) or any(guest.get(key) != expected for key, expected in {
            "distribution_id": "ubuntu", "distribution_version": "24.04",
            "distribution_codename": "noble", "architecture": "aarch64",
        }.items()):
            errors.append(label + ": passing Stage A.1 guest boundary drifted")
        elif re.fullmatch(
            r"[0-9][0-9A-Za-z._+~-]{0,127}", str(guest.get("kernel", ""))
        ) is None:
            errors.append(label + ": passing Stage A.1 kernel evidence is missing or invalid")
        if apparmor != {
            "enabled": True, "unprivileged_userns_restriction": "active",
            "profile_required": True,
            "profile_source": "ubuntu-noble-apparmor-profiles",
            "source_sha256": APPROVED_BWRAP_PROFILE_SHA256,
            "installed_sha256": APPROVED_BWRAP_PROFILE_SHA256,
            "load_status": "enforce",
        }:
            errors.append(label + ": passing Stage A.1 AppArmor/profile boundary drifted")
        if not isinstance(bubblewrap, dict) or any(
            bubblewrap.get(key) != expected for key, expected in {
                "package_name": "bubblewrap",
                "package_version": APPROVED_BWRAP_PACKAGE_VERSION,
                "package_architecture": "arm64", "install_status": "installed",
                "binary_sha256": APPROVED_BWRAP_BINARY_SHA256,
                "version_output": APPROVED_BWRAP_VERSION_OUTPUT,
            }.items()
        ) or not isinstance(bubblewrap.get("help_sha256"), str) or SHA.fullmatch(
            bubblewrap.get("help_sha256", "")
        ) is None or bubblewrap.get("help_sha256") == ZERO_SHA256:
            errors.append(label + ": passing Stage A.1 bubblewrap boundary drifted")
        if not isinstance(git, dict) or any(
            git.get(key) != expected for key, expected in {
                "package_name": "git",
                "package_version": APPROVED_GIT_PACKAGE_VERSION,
                "package_architecture": "arm64", "install_status": "installed",
                "binary_sha256": APPROVED_GIT_BINARY_SHA256,
                "version_output": APPROVED_GIT_VERSION_OUTPUT,
            }.items()
        ):
            errors.append(label + ": passing Stage A.1 Git boundary drifted")
        if (
            value.get("reason_code") != "none" or smoke.get("status") != "pass"
            or smoke.get("reason_code") != "none" or smoke.get("exit_code") != 0
        ):
            errors.append(label + ": passing Stage A.1 smoke outcome drifted")
    elif value.get("status") == "fail":
        if value.get("reason_code") in STAGE_A1_PRECONDITION_FAILURE_CODES:
            if smoke_status != "not-run":
                errors.append(label + ": failed Stage A.1 precondition contains a smoke claim")
        elif value.get("reason_code") in STAGE_A1_SMOKE_FAILURE_CODES:
            if smoke_status != "fail" or smoke_reason != value.get("reason_code"):
                errors.append(label + ": failed Stage A.1 outcome disagrees with smoke evidence")
        else:
            errors.append(label + ": failed Stage A.1 reason is invalid")
    elif value.get("status") == "UNCHECKABLE" and (
        value.get("reason_code") not in STAGE_A1_UNCHECKABLE_CODES
        or smoke_status != "UNCHECKABLE"
        or smoke_reason != value.get("reason_code")
    ):
        errors.append(label + ": uncheckable Stage A.1 outcome is inconsistent")
    if profile_status in {"match", "probe-only-match"} and value.get("status") != "pass":
        errors.append(label + ": matching profile requires passing Stage A.1 prerequisite")


def validate_shell_environment_evidence(
    value: Any, label: str, errors: List[str]
) -> Any:
    expected_keys = {
        "schema", "authority", "status", "reason_code",
        "unexpected_key_count", "unexpected_key_names_sha256",
        "secret_shaped_key_count",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        errors.append(label + ": shell environment evidence shape drifted")
        return None
    reason = value.get("reason_code")
    expected_status = (
        "pass" if reason == "none" else
        "not-run" if reason == "not-run" else
        "UNCHECKABLE" if reason in SHELL_ENVIRONMENT_UNCHECKABLE_REASONS else
        "fail" if reason in SHELL_ENVIRONMENT_REASON_CODES else None
    )
    count = value.get("unexpected_key_count")
    secret_count = value.get("secret_shaped_key_count")
    digest = value.get("unexpected_key_names_sha256")
    if (
        value.get("schema") != "t11-shell-environment-evidence/v1"
        or value.get("authority") != "adapter-authored"
        or value.get("status") != expected_status
        or not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 64
        or not isinstance(secret_count, int) or isinstance(secret_count, bool)
        or not 0 <= secret_count <= count
        or not isinstance(digest, str) or SHA.fullmatch(digest) is None
    ):
        errors.append(label + ": shell environment evidence is invalid")
        return value.get("status")
    empty_digest = sha256(canonical_bytes([]))
    if value.get("status") in {"not-run", "UNCHECKABLE"} and (
        count != 0 or secret_count != 0 or digest != ZERO_SHA256
    ):
        errors.append(label + ": unobserved shell environment contains claims")
    if value.get("status") in {"pass", "fail"} and count == 0 and digest != empty_digest:
        errors.append(label + ": empty shell environment key digest drifted")
    if count > 0 and digest in {ZERO_SHA256, empty_digest}:
        errors.append(label + ": non-empty shell environment key digest is invalid")
    if reason == "unexpected-key-set" and (count < 1 or secret_count != 0):
        errors.append(label + ": unexpected shell key classification is invalid")
    if reason == "secret-shaped-key" and secret_count < 1:
        errors.append(label + ": secret-shaped shell key classification is invalid")
    if value.get("status") == "pass" and (count != 0 or secret_count != 0):
        errors.append(label + ": passing shell environment contains unexpected keys")
    return value.get("status")


def validate_network_sandbox_evidence(
    value: Any, label: str, errors: List[str]
) -> Any:
    expected_keys = {
        "schema", "authority", "status", "reason_code",
        "unsandboxed_control_accepted", "unsandboxed_control_closed",
        "parent_netns_sha256", "sandbox_netns_sha256", "netns_different",
        "network_marker_status", "sandbox_connect_status",
        "sandbox_connect_errno", "process_cleanup_status", "process_reaped",
        "raw_stdout_recorded", "raw_stderr_recorded",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        errors.append(label + ": network/sandbox behavior evidence shape drifted")
        return None
    reason = value.get("reason_code")
    expected_status = (
        "pass" if reason == "none" else
        "not-run" if reason == "not-run" else
        "fail" if reason in NETWORK_SANDBOX_FAIL_REASONS else
        "UNCHECKABLE" if reason in NETWORK_SANDBOX_REASON_CODES else None
    )
    parent = value.get("parent_netns_sha256")
    sandbox = value.get("sandbox_netns_sha256")
    derived_different = (
        isinstance(parent, str) and isinstance(sandbox, str)
        and parent != ZERO_SHA256 and sandbox != ZERO_SHA256 and parent != sandbox
    )
    if (
        value.get("schema") != "t11-network-sandbox-evidence/v1"
        or value.get("authority") != "adapter-authored"
        or value.get("status") != expected_status
        or not isinstance(parent, str) or SHA.fullmatch(parent) is None
        or not isinstance(sandbox, str) or SHA.fullmatch(sandbox) is None
        or value.get("netns_different") is not derived_different
        or value.get("network_marker_status") not in {"exact-1", "missing", "mismatch", "not-run", "UNCHECKABLE"}
        or value.get("sandbox_connect_status") not in {"denied", "succeeded", "not-run", "UNCHECKABLE"}
        or value.get("sandbox_connect_errno") not in {*APPROVED_NETWORK_DENIAL_ERRNOS, "none", "not-run", "unapproved"}
        or value.get("process_cleanup_status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}
        or any(type(value.get(field)) is not bool for field in (
            "unsandboxed_control_accepted", "unsandboxed_control_closed",
            "netns_different", "process_reaped", "raw_stdout_recorded",
            "raw_stderr_recorded",
        ))
        or value.get("raw_stdout_recorded") is not False
        or value.get("raw_stderr_recorded") is not False
    ):
        errors.append(label + ": network/sandbox behavior evidence is invalid")
        return value.get("status")
    if value.get("unsandboxed_control_closed") and not value.get("unsandboxed_control_accepted"):
        errors.append(label + ": network control close lacks acceptance")
    cleanup_pair = (
        value.get("process_cleanup_status"), value.get("process_reaped"),
    )
    if cleanup_pair not in {
        ("pass", True), ("UNCHECKABLE", False), ("not-run", False),
    }:
        errors.append(label + ": network cleanup/reap facts are contradictory")
    if cleanup_pair == ("not-run", False) and reason != "not-run":
        errors.append(label + ": network cleanup not-run is reserved for not-run evidence")
    marker = value.get("network_marker_status")
    connection = value.get("sandbox_connect_status")
    denial = value.get("sandbox_connect_errno")
    if (
        (connection == "succeeded" and denial != "none")
        or (
            connection == "denied"
            and denial not in {*APPROVED_NETWORK_DENIAL_ERRNOS, "unapproved"}
        )
        or (connection == "UNCHECKABLE" and denial != "unapproved")
        or (connection == "not-run" and denial != "not-run")
    ):
        errors.append(label + ": network connection/errno facts are contradictory")

    parent_known = parent != ZERO_SHA256
    sandbox_known = sandbox != ZERO_SHA256
    control = (
        value.get("unsandboxed_control_accepted"),
        value.get("unsandboxed_control_closed"),
    )
    unobserved_child = (
        not sandbox_known
        and value.get("netns_different") is False
        and marker == "UNCHECKABLE"
        and connection == "UNCHECKABLE"
        and denial == "unapproved"
    )
    if reason == "not-run":
        expected = {
            "unsandboxed_control_accepted": False,
            "unsandboxed_control_closed": False,
            "parent_netns_sha256": ZERO_SHA256,
            "sandbox_netns_sha256": ZERO_SHA256,
            "netns_different": False,
            "network_marker_status": "not-run",
            "sandbox_connect_status": "not-run",
            "sandbox_connect_errno": "not-run",
            "process_cleanup_status": "not-run",
            "process_reaped": False,
        }
        if any(value.get(key) != expected_value for key, expected_value in expected.items()):
            errors.append(label + ": not-run network/sandbox evidence contains claims")
    elif reason == "parent-netns-unavailable":
        if control != (False, False) or parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            errors.append(label + ": parent namespace failure facts are contradictory")
    elif reason in {
        "control-unavailable", "control-not-accepted", "control-peer-mismatch",
    }:
        if control != (False, False) or not parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            errors.append(label + ": control failure facts are contradictory")
    elif reason == "control-not-closed":
        if control != (True, False) or not parent_known or not unobserved_child or cleanup_pair != ("UNCHECKABLE", False):
            errors.append(label + ": control close failure facts are contradictory")
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
            errors.append(label + ": uncheckable observation facts are contradictory")
    elif reason in {
        "sandbox-netns-unavailable", "process-nonzero", "process-timeout",
        "output-overflow", "process-not-reaped", "malformed-probe-output",
    }:
        if control != (True, True) or not parent_known or not unobserved_child:
            errors.append(label + ": post-spawn network failure facts are contradictory")
        if reason in {
            "sandbox-netns-unavailable", "process-nonzero",
            "malformed-probe-output",
        } and cleanup_pair != ("pass", True):
            errors.append(label + ": reaped network failure lost cleanup evidence")
        if reason == "process-not-reaped" and cleanup_pair != ("UNCHECKABLE", False):
            errors.append(label + ": unreaped network failure claims cleanup")
        if reason in {"process-timeout", "output-overflow"} and cleanup_pair not in {
            ("pass", True), ("UNCHECKABLE", False),
        }:
            errors.append(label + ": bounded network failure cleanup facts are invalid")
    elif reason in NETWORK_SANDBOX_REASON_CODES:
        if control != (True, True) or not parent_known or not sandbox_known or cleanup_pair != ("pass", True):
            errors.append(label + ": observed network result facts are incomplete")
        if (
            marker not in {"exact-1", "missing", "mismatch"}
            or connection not in {"denied", "succeeded", "UNCHECKABLE"}
        ):
            errors.append(label + ": observed network classifications are invalid")
        if reason == "none" and not (
            value.get("netns_different")
            and marker == "exact-1"
            and connection == "denied"
            and denial in APPROVED_NETWORK_DENIAL_ERRNOS
        ):
            errors.append(label + ": passing network/sandbox proof is incomplete")
        if reason == "netns-not-separated" and value.get("netns_different"):
            errors.append(label + ": network namespace equality reason drifted")
        if reason in {
            "network-marker-missing", "network-marker-mismatch",
            "sandbox-connection-succeeded", "socket-creation-unavailable",
            "unapproved-denial-errno",
        } and not value.get("netns_different"):
            errors.append(label + ": network failure lacks namespace separation")
        expected_marker = {
            "network-marker-missing": "missing",
            "network-marker-mismatch": "mismatch",
        }.get(reason)
        if expected_marker is not None and marker != expected_marker:
            errors.append(label + ": network marker reason/fact drifted")
        if reason in {
            "sandbox-connection-succeeded", "socket-creation-unavailable",
            "unapproved-denial-errno",
        } and marker != "exact-1":
            errors.append(label + ": network connection reason lacks exact marker")
        expected_connection = {
            "sandbox-connection-succeeded": ("succeeded", "none"),
            "socket-creation-unavailable": ("UNCHECKABLE", "unapproved"),
            "unapproved-denial-errno": ("denied", "unapproved"),
        }.get(reason)
        if expected_connection is not None and (connection, denial) != expected_connection:
            errors.append(label + ": network connection reason/fact drifted")
    return value.get("status")


def validate_profile_evidence(
    value: Any,
    status: Any,
    label: str,
    errors: List[str],
    clone_public_branch: str = EXPECTED_T12_PUBLIC_BRANCH,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "configuration_intent", "diagnostic_health", "exact_worker_argv",
        "shell_environment_behavior", "network_sandbox_behavior",
        "bubblewrap_prerequisite",
        "containment_provider", "lane_statuses",
    }:
        errors.append(label + ": separated runtime evidence lanes drifted")
        return
    if value.get("configuration_intent") != expected_runtime_configuration_intent():
        errors.append(label + ": adapter-authored configuration intent/digest drifted")
    diagnostic = value.get("diagnostic_health")
    if (
        not isinstance(diagnostic, dict)
        or set(diagnostic) != {
            "classification", "status", "checks",
            "codex_issued_effective_configuration_proof"
        }
        or diagnostic.get("classification") != "diagnostic-only"
        or diagnostic.get("status") not in {
            "pass", "pass-with-advisory-warning", "fail", "not-run", "UNCHECKABLE"
        }
        or diagnostic.get("codex_issued_effective_configuration_proof") is not False
    ):
        errors.append(label + ": doctor evidence must remain diagnostic-only, never effective-config proof")
    checks = diagnostic.get("checks") if isinstance(diagnostic, dict) else None
    if not isinstance(checks, list) or len(checks) > 64:
        errors.append(label + ": doctor checks must be a bounded allowlisted projection")
    else:
        for check in checks:
            if (
                not isinstance(check, dict)
                or set(check) != {"id", "category", "status"}
                or not isinstance(check.get("id"), str)
                or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", check["id"]) is None
                or not isinstance(check.get("category"), str)
                or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", check["category"]) is None
                or check.get("status") not in {"ok", "warning", "fail"}
            ):
                errors.append(label + ": doctor check projection contains unsafe or unsupported fields")
                break
    worker_argv = value.get("exact_worker_argv")
    if (
        not isinstance(worker_argv, dict)
        or set(worker_argv) != {
            "status", "stage", "reason_code", "rules_bypass_absent",
            "dynamic_task_data_stdin_only"
        }
        or worker_argv.get("status") not in {"pass", "fail", "not-run", "UNCHECKABLE"}
        or worker_argv.get("stage") not in WORKER_ARGV_STAGES
        or worker_argv.get("reason_code") not in WORKER_ARGV_REASON_CODES
        or type(worker_argv.get("rules_bypass_absent")) is not bool
        or type(worker_argv.get("dynamic_task_data_stdin_only")) is not bool
        or ((worker_argv.get("status") == "pass") is not (
            worker_argv.get("rules_bypass_absent") is True
            and worker_argv.get("dynamic_task_data_stdin_only") is True
        ))
        or (worker_argv.get("status") == "pass" and worker_argv.get("reason_code") != "none")
        or (worker_argv.get("status") == "not-run" and worker_argv.get("reason_code") != "not-run")
        or (worker_argv.get("status") in {"fail", "UNCHECKABLE"} and worker_argv.get("reason_code") in {"none", "not-run"})
    ):
        errors.append(label + ": exact worker argv evidence is invalid")
    shell = value.get("shell_environment_behavior")
    shell_status = validate_shell_environment_evidence(shell, label, errors)
    network = value.get("network_sandbox_behavior")
    network_status = validate_network_sandbox_evidence(network, label, errors)
    validate_stage_a1_prerequisite(
        value.get("bubblewrap_prerequisite"), status, label, errors
    )
    validate_containment_provider(
        value.get("containment_provider"), status, label, errors,
        clone_public_branch,
    )
    lanes = value.get("lane_statuses")
    if not isinstance(lanes, dict) or set(lanes) != set(LANE_STATUS_KEYS):
        errors.append(label + ": closed independent runtime lane status shape drifted")
        lanes = {}
    else:
        for key in LANE_STATUS_KEYS[:-1]:
            if lanes.get(key) not in {"pass", "fail", "not-run", "UNCHECKABLE"}:
                errors.append(label + ": invalid independent runtime lane status: " + key)
        if lanes.get("auth_status") not in {"signed-in-client", "api-key", "unavailable", "unknown"}:
            errors.append(label + ": invalid auth lane status")
    provider = value.get("containment_provider", {})
    if lanes.get("provider_isolation_status") != provider.get("status"):
        errors.append(label + ": provider isolation lane does not match provider evidence")
    if lanes.get("codex_sandbox_network_status") != network_status:
        errors.append(label + ": sandbox/network lane does not match network evidence")
    if lanes.get("shell_environment_status") != shell_status:
        errors.append(label + ": shell environment lane does not match shell evidence")
    if lanes.get("mount_boundary_status") == "pass":
        mount_claims = {
            "host_mount_count": 1,
            "host_mount_classifications": ["provider-internal-cache"],
            "all_host_mounts_read_only": True,
            "provider_cache_only": True,
            "host_sensitive_mounts_absent": True,
            "unapproved_mounts_absent": True,
            "ssh_agent_forwarding": False,
            "dot_ssh_public_key_loading": False,
            "user_ssh_config_modified": False,
        }
        for key, expected in mount_claims.items():
            if provider.get(key) != expected:
                errors.append(label + ": passing mount boundary lane drifted: " + key)
        for key in (
            "effective_mount_inventory_sha256", "provider_cache_mount_sha256",
            "provider_cache_guest_mountpoint_sha256",
        ):
            if provider.get(key) == ZERO_SHA256:
                errors.append(label + ": passing mount boundary uses placeholder digest: " + key)
    if status == "match" and (
        not isinstance(diagnostic, dict) or diagnostic.get("status") not in {"pass", "pass-with-advisory-warning"}
        or not isinstance(worker_argv, dict) or worker_argv.get("status") != "pass"
        or not isinstance(network, dict) or network.get("status") != "pass"
        or value.get("bubblewrap_prerequisite", {}).get("status") != "pass"
        or value.get("containment_provider", {}).get("status") != "pass"
        or any(lanes.get(key) != "pass" for key in LANE_STATUS_KEYS[:-1])
        or lanes.get("auth_status") != "signed-in-client"
    ):
        errors.append(label + ": match requires passing diagnostic, argv, and network evidence lanes")
    if status == "probe-only-match" and (
        not isinstance(diagnostic, dict)
        or diagnostic.get("status") not in {"pass", "pass-with-advisory-warning"}
        or not isinstance(worker_argv, dict) or worker_argv.get("status") != "pass"
        or not isinstance(network, dict) or network.get("status") != "pass"
        or value.get("bubblewrap_prerequisite", {}).get("status") != "pass"
        or value.get("containment_provider", {}).get("status") != "pass"
        or any(lanes.get(key) != "pass" for key in LANE_STATUS_KEYS[:-1])
        or lanes.get("auth_status") != "unavailable"
    ):
        errors.append(label + ": probe-only-match requires all non-auth lanes pass and auth unavailable")


def validate_profile_lane_bindings(profile: Any, label: str, errors: List[str]) -> None:
    """Cross-check independent lane outcomes without collapsing their evidence."""
    if not isinstance(profile, dict):
        errors.append(label + ": profile lane bindings require an object")
        return
    evidence = profile.get("evidence")
    lanes = evidence.get("lane_statuses") if isinstance(evidence, dict) else None
    capabilities = profile.get("capabilities")
    auth = profile.get("auth")
    if not isinstance(lanes, dict) or not isinstance(capabilities, dict) or not isinstance(auth, dict):
        errors.append(label + ": profile lane binding inputs are missing")
        return
    expected_bindings = {
        "provider_isolation_status": (
            evidence.get("containment_provider", {}).get("status")
            if isinstance(evidence.get("containment_provider"), dict) else None
        ),
        "process_cleanup_status": capabilities.get("process_cleanup_probe"),
        "codex_sandbox_network_status": (
            evidence.get("network_sandbox_behavior", {}).get("status")
            if isinstance(evidence.get("network_sandbox_behavior"), dict) else None
        ),
        "shell_environment_status": (
            evidence.get("shell_environment_behavior", {}).get("status")
            if isinstance(evidence.get("shell_environment_behavior"), dict) else None
        ),
        "config_status": (
            "not-run" if capabilities.get("documented_config_keys_probe") == "not-proven"
            else capabilities.get("documented_config_keys_probe")
        ),
        "auth_status": auth.get("class"),
    }
    for key, expected in expected_bindings.items():
        if lanes.get(key) != expected:
            errors.append(label + ": independent lane binding drifted: " + key)
    if capabilities.get("shell_environment_probe") != lanes.get("shell_environment_status"):
        errors.append(label + ": shell capability does not match shell evidence lane")
    status = profile.get("status")
    if status == "match" and (
        profile.get("live_run_allowed") is not True
        or lanes.get("auth_status") != "signed-in-client"
        or any(lanes.get(key) != "pass" for key in LANE_STATUS_KEYS[:-1])
    ):
        errors.append(label + ": live match does not have exact passing lane bindings")
    if status == "probe-only-match" and (
        profile.get("scope") != "exact-head-probe-only-sensor"
        or profile.get("live_run_allowed") is not False
        or auth.get("class") != "unavailable"
        or lanes.get("auth_status") != "unavailable"
        or any(lanes.get(key) != "pass" for key in LANE_STATUS_KEYS[:-1])
    ):
        errors.append(label + ": probe-only match does not have exact unauthenticated lane bindings")


def validate_runtime_script_bypass_literals(
    text: str, label: str, errors: List[str], guard_function: str = ""
) -> None:
    """Reject reviewed-script argv bypass literals outside the rejecting guard."""
    try:
        tree = ast.parse(text, filename=label)
    except (SyntaxError, ValueError):
        errors.append(label + ": cannot inspect runtime argv literals")
        return
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name == guard_function:
                continue
            nodes: Iterable[ast.AST] = ast.walk(statement)
        else:
            nodes = ast.walk(statement)
        for node in nodes:
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if (
                node.value == "--ignore-rules"
                or node.value.startswith("--ignore-rules=")
                or node.value.startswith("--dangerously-bypass-")
            ):
                errors.append(label + ": runtime/config argv contains forbidden policy bypass " + node.value)


def validate_provider_git_source(text: str, label: str, errors: List[str]) -> None:
    """Pin the fixed, revalidated provider-Git call graph."""
    try:
        tree = ast.parse(text, filename=label)
    except (SyntaxError, ValueError):
        errors.append(label + ": cannot inspect approved provider Git boundary")
        return
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    required = {
        "approved_provider_git_binding",
        "run_approved_provider_git",
        "observe_colima_provider_evidence",
    }
    if not required.issubset(functions):
        errors.append(label + ": approved provider Git functions are missing")
        return

    def call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            return node.func.value.id + "." + node.func.attr
        return ""

    binding = functions["approved_provider_git_binding"]
    binding_calls = [
        node for node in ast.walk(binding) if isinstance(node, ast.Call)
    ]
    binding_names = [call_name(node) for node in binding_calls]
    binding_constants = {
        node.value for node in ast.walk(binding)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    stat_calls = [
        node for node in binding_calls if call_name(node) == "os.stat"
    ]
    nofollow_stats = all(
        any(
            keyword.arg == "follow_symlinks"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in node.keywords
        )
        for node in stat_calls
    )
    binding_identifiers = {
        node.id for node in ast.walk(binding) if isinstance(node, ast.Name)
    }
    if (
        not {"/usr", "/usr/bin"}.issubset(binding_constants)
        or len(stat_calls) < 2
        or not nofollow_stats
        or "hash_regular_file" not in binding_names
        or "STAGE_A1_GIT_BINARY" not in binding_identifiers
        or "APPROVED_GIT_BINARY_SHA256" not in binding_identifiers
    ):
        errors.append(label + ": root-owned no-follow provider Git binding drifted")

    runner = functions["run_approved_provider_git"]
    runner_calls = [
        node for node in ast.walk(runner) if isinstance(node, ast.Call)
    ]
    runner_names = [call_name(node) for node in runner_calls]
    binding_lines = [
        node.lineno for node in runner_calls
        if call_name(node) == "approved_provider_git_binding"
    ]
    process_lines = [
        node.lineno for node in runner_calls
        if call_name(node) == "run_bounded_process"
    ]
    if (
        len(binding_lines) != 1
        or len(process_lines) != 1
        or binding_lines[0] >= process_lines[0]
        or "resolve_executable_from_path" in runner_names
        or "run_git" in runner_names
    ):
        errors.append(label + ": provider Git is not rebound before every fixed execution")

    observer = functions["observe_colima_provider_evidence"]
    observer_names = [
        call_name(node) for node in ast.walk(observer) if isinstance(node, ast.Call)
    ]
    if (
        observer_names.count("run_approved_provider_git") != 3
        or "run_git" in observer_names
    ):
        errors.append(label + ": provider observation bypasses the fixed Git runner")


def runtime_fs_capability_error() -> str:
    missing = [name for name in ("O_NOFOLLOW", "O_DIRECTORY") if not isinstance(getattr(os, name, None), int)]
    if os.open not in getattr(os, "supports_dir_fd", set()):
        missing.append("open(dir_fd)")
    if os.stat not in getattr(os, "supports_dir_fd", set()):
        missing.append("stat(dir_fd)")
    if os.stat not in getattr(os, "supports_follow_symlinks", set()):
        missing.append("stat(follow_symlinks)")
    return ", ".join(missing)


def strict_json_loads(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("non-finite")

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite")
        return parsed

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def read_regular(root: Path, relative: str, errors: List[str], max_bytes: int = MAX_FILE_BYTES) -> bytes:
    capability_error = runtime_fs_capability_error()
    if capability_error:
        errors.append(relative + ": required no-follow filesystem capability is unavailable: " + capability_error)
        return b""
    path = root / relative
    try:
        info = os.lstat(path)
    except OSError:
        errors.append(relative + ": missing runtime contract path")
        return b""
    reviewed_modes = (0o600, 0o644)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) not in reviewed_modes or info.st_nlink != 1:
        errors.append(relative + ": must be a single-link regular non-writable repository file")
        return b""
    if info.st_size > max_bytes:
        errors.append(relative + ": file exceeds byte limit")
        return b""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        errors.append(relative + ": cannot open runtime contract path without following links")
        return b""
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino, opened.st_size)
            != (info.st_dev, info.st_ino, info.st_size)
            or stat.S_IMODE(opened.st_mode) != stat.S_IMODE(info.st_mode)
            or opened.st_nlink != info.st_nlink
        ):
            errors.append(relative + ": binding changed before read")
            return b""
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            errors.append(relative + ": file exceeds byte limit")
            return b""
        opened_after = os.fstat(descriptor)
        if (
            (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or stat.S_IMODE(opened_after.st_mode) != stat.S_IMODE(opened.st_mode)
            or opened_after.st_nlink != opened.st_nlink
        ):
            errors.append(relative + ": changed while reading")
            return b""
    finally:
        os.close(descriptor)
    after = os.stat(str(path), follow_symlinks=False)
    if (
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        or stat.S_IMODE(after.st_mode) != stat.S_IMODE(info.st_mode)
        or after.st_nlink != info.st_nlink
    ):
        errors.append(relative + ": binding changed while reading")
        return b""
    return bytes(data)


def validate_json_limits(value: Any, label: str, errors: List[str]) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            errors.append(label + ": JSON node limit exceeded")
            return
        if depth > MAX_JSON_DEPTH:
            errors.append(label + ": JSON depth limit exceeded")
            return
        if isinstance(current, str):
            if len(current.encode("utf-8")) > MAX_STRING_BYTES:
                errors.append(label + ": JSON string limit exceeded")
                return
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    errors.append(label + ": JSON key is not a string")
                    return
                stack.append((item, depth + 1))


def load_json(root: Path, relative: str, errors: List[str]) -> Any:
    data = read_regular(root, relative, errors)
    if not data:
        return None
    try:
        text = data.decode("utf-8", errors="strict")
        value = strict_json_loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError, OverflowError):
        errors.append(relative + ": invalid bounded UTF-8 JSON")
        return None
    validate_json_limits(value, relative, errors)
    return value


def import_script(root: Path, relative: str, module_name: str, errors: List[str]):
    path = root / relative
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError("no loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as error:
        errors.append(relative + ": cannot import deterministically ({})".format(type(error).__name__))
        return None


def validate_schema(relative: str, schema: Any, errors: List[str]) -> None:
    if not isinstance(schema, dict):
        errors.append(relative + ": schema must be an object")
        return
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(relative + ": must declare Draft 2020-12")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append(relative + ": top-level schema must be a closed object")
    title = schema.get("title")
    if not isinstance(title, str) or not title.endswith("/v1"):
        errors.append(relative + ": title must be an exact v1 contract name")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not required or len(required) != len(set(required)) or not isinstance(properties, dict) or set(required) - set(properties):
        errors.append(relative + ": required/properties contract is invalid")
    rendered = canonical_bytes(schema).decode("utf-8")
    if PRIVATE_PATH.search(rendered):
        errors.append(relative + ": schema contains a private local path")


def parse_role(data: bytes, relative: str, expected_name: str, expected_sandbox: str, errors: List[str]) -> str:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        errors.append(relative + ": role is not UTF-8")
        return ""
    for line in ('name = "{}"'.format(expected_name), 'sandbox_mode = "{}"'.format(expected_sandbox), "K09-partial"):
        if line not in text:
            errors.append(relative + ": missing role boundary " + line)
    marker = 'developer_instructions = """\n'
    start = text.find(marker)
    if start < 0 or not text.endswith('"""\n'):
        errors.append(relative + ": malformed developer instructions")
        return ""
    instructions = text[start + len(marker):-4]
    for phrase in ("Do not", "Task", "acceptance"):
        if phrase not in instructions:
            errors.append(relative + ": static role instructions omit " + phrase)
    return instructions


def validate_runtime_profile_schema(schema: Any, errors: List[str]) -> None:
    label = "docs/agreements/runtime/runtime-profile.v1.schema.json"
    if not isinstance(schema, dict) or not isinstance(schema.get("allOf"), list):
        errors.append(label + ": fail-closed conditional constraints are missing")
        return
    if schema.get("properties", {}).get("evidence") != expected_profile_evidence_schema():
        errors.append(label + ": separated runtime evidence schema drifted")
    properties = schema.get("properties", {})
    if properties.get("scope") != {"enum": [
        "task-start-sensor", "exact-head-probe-only-sensor",
        "exact-head-live-sensor", "fixture",
    ]}:
        errors.append(label + ": probe-only profile scope is missing or drifted")
    if properties.get("status") != {"enum": [
        "match", "probe-only-match", "profile-drift", "unsupported-client",
        "UNKNOWN", "UNCHECKABLE",
    ]}:
        errors.append(label + ": profile status enum is missing probe-only-match or drifted")
    capabilities = properties.get("capabilities", {})
    capability_required = capabilities.get("required", []) if isinstance(capabilities, dict) else []
    capability_properties = capabilities.get("properties", {}) if isinstance(capabilities, dict) else {}
    if "process_cleanup_probe" not in capability_required or "process_containment_probe" in capability_required:
        errors.append(label + ": process cleanup capability name drifted")
    if "process_cleanup_probe" not in capability_properties or "process_containment_probe" in capability_properties:
        errors.append(label + ": obsolete containment capability remains")
    required = schema.get("required")
    if not isinstance(required, list) or required.count("evidence") != 1:
        errors.append(label + ": separated runtime evidence is not required exactly once")
    conditions = schema["allOf"]
    nonmatch = {
        "if": {"properties": {"status": {"enum": ["probe-only-match", "profile-drift", "unsupported-client", "UNKNOWN", "UNCHECKABLE"]}}, "required": ["status"]},
        "then": {"properties": {"live_run_allowed": {"const": False}}},
    }
    live_true = {
        "if": {"properties": {"live_run_allowed": {"const": True}}, "required": ["live_run_allowed"]},
        "then": {"properties": {"status": {"const": "match"}}},
    }
    if nonmatch not in conditions or live_true not in conditions:
        errors.append(label + ": non-match/live authorization conditionals drifted")
    match_conditions = [
        item for item in conditions if isinstance(item, dict)
        and item.get("if") == {"properties": {"status": {"const": "match"}}, "required": ["status"]}
    ]
    if len(match_conditions) != 1:
        errors.append(label + ": exact match conditional is missing or duplicated")
        return
    then_properties = match_conditions[0].get("then", {}).get("properties", {})
    cap_properties = then_properties.get("capabilities", {}).get("properties", {})
    for key in (
        "documented_config_keys_probe", "shell_environment_probe",
        "process_cleanup_probe",
    ):
        if cap_properties.get(key) != {"const": "pass"}:
            errors.append(label + ": match does not require passing " + key)
    evidence_properties = then_properties.get("evidence", {}).get("properties", {})
    for key in (
        "exact_worker_argv", "shell_environment_behavior",
        "network_sandbox_behavior",
        "bubblewrap_prerequisite", "containment_provider",
    ):
        if evidence_properties.get(key, {}).get("properties", {}).get("status") != {"const": "pass"}:
            errors.append(label + ": match does not require passing evidence lane " + key)
    if evidence_properties.get("diagnostic_health", {}).get("properties", {}).get("status") != {
        "enum": ["pass", "pass-with-advisory-warning"]
    }:
        errors.append(label + ": match does not accept only safe diagnostic outcomes")
    lane_match = evidence_properties.get("lane_statuses", {}).get("properties", {})
    for key in LANE_STATUS_KEYS[:-1]:
        if lane_match.get(key) != {"const": "pass"}:
            errors.append(label + ": match does not require passing independent lane " + key)
    if lane_match.get("auth_status") != {"const": "signed-in-client"}:
        errors.append(label + ": match does not require signed-in auth lane")
    if then_properties.get("client", {}).get("properties", {}).get("version_output") != {"const": APPROVED_CODEX_VERSION}:
        errors.append(label + ": match does not require the exact approved Codex version")
    if then_properties.get("auth", {}).get("properties", {}).get("class") != {"const": "signed-in-client"}:
        errors.append(label + ": match does not require dedicated device-auth client state")
    if then_properties.get("platform", {}).get("properties", {}) != {
        "os": {"const": "Linux"}, "architecture": {"const": "aarch64"}
    }:
        errors.append(label + ": match does not require the approved Linux aarch64 guest")
    if then_properties.get("live_run_allowed") != {"const": True}:
        errors.append(label + ": match does not require live_run_allowed=true")
    probe_conditions = [
        item for item in conditions if isinstance(item, dict)
        and item.get("if") == {
            "properties": {"status": {"const": "probe-only-match"}},
            "required": ["status"],
        }
    ]
    if len(probe_conditions) != 1:
        errors.append(label + ": exact probe-only-match conditional is missing or duplicated")
    else:
        probe_then = probe_conditions[0].get("then", {}).get("properties", {})
        probe_evidence = probe_then.get("evidence", {}).get("properties", {})
        probe_lanes = probe_evidence.get(
            "lane_statuses", {}
        ).get("properties", {})
        probe_caps = probe_then.get("capabilities", {}).get("properties", {})
        if (
            probe_then.get("scope") != {"const": "exact-head-probe-only-sensor"}
            or probe_then.get("client", {}).get("properties", {}).get("version_output") != {"const": APPROVED_CODEX_VERSION}
            or probe_then.get("client", {}).get("properties", {}).get("release_class") != {"const": "stable"}
            or probe_then.get("platform", {}).get("properties", {}) != {
                "os": {"const": "Linux"}, "architecture": {"const": "aarch64"}
            }
            or any(probe_caps.get(key) != {"const": "pass"} for key in (
                "documented_config_keys_probe", "shell_environment_probe",
                "process_cleanup_probe",
            ))
            or any(probe_caps.get(key) != {"const": True} for key in (
                "exec_json", "ephemeral", "strict_config", "ignore_user_config",
                "workspace_write", "approval_never", "model", "reasoning",
                "sandbox", "approval", "overrides",
            ))
            or probe_then.get("auth", {}).get("properties", {}).get("class") != {"const": "unavailable"}
            or probe_then.get("live_run_allowed") != {"const": False}
            or probe_evidence.get("diagnostic_health", {}).get(
                "properties", {}
            ).get("status") != {
                "enum": ["pass", "pass-with-advisory-warning"]
            }
            or probe_evidence.get("bubblewrap_prerequisite", {}).get(
                "properties", {}
            ).get("status") != {"const": "pass"}
            or probe_evidence.get("shell_environment_behavior", {}).get(
                "properties", {}
            ).get("status") != {"const": "pass"}
            or probe_evidence.get("network_sandbox_behavior", {}).get(
                "properties", {}
            ).get("status") != {"const": "pass"}
            or any(probe_lanes.get(key) != {"const": "pass"} for key in LANE_STATUS_KEYS[:-1])
            or probe_lanes.get("auth_status") != {"const": "unavailable"}
        ):
            errors.append(label + ": probe-only-match fail-closed constraints drifted")


def validate_runtime_receipt_schema(schema: Any, errors: List[str]) -> None:
    label = "docs/agreements/runtime/runtime-receipt.v1.schema.json"
    if not isinstance(schema, dict):
        errors.append(label + ": native-artifact request schema is missing")
        return
    if schema.get("title") != "runtime-receipt-request/v1":
        errors.append(label + ": receipt input must be the native-artifact request")
    artifacts = schema.get("properties", {}).get("artifacts", {})
    expected = {
        "runtime_profile": {"$ref": "runtime-profile.v1.schema.json"},
        "envelope": {"$ref": "task-execution-envelope.v1.schema.json"},
        "execution_result": {"$ref": "execution-result.v1.schema.json"},
        "verifier": {"$ref": "#/$defs/verifierArtifact"},
    }
    if artifacts.get("additionalProperties") is not False or artifacts.get("required") != list(expected) or artifacts.get("properties") != expected:
        errors.append(label + ": exact native runtime artifacts are not required")
    limitations = schema.get("properties", {}).get("limitations", {}).get("const", {})
    if limitations.get("artifact_provenance") != "unsigned-unverified":
        errors.append(label + ": unsigned artifact provenance limitation is missing")


def validate_profile(profile: Any, errors: List[str]) -> None:
    if not isinstance(profile, dict):
        errors.append(PROFILE_PATH + ": profile must be an object")
        return
    expected = {
        "schema": "runtime-profile/v1", "repository": "mochan-tk/agentic-dev-kit-for-codex",
        "scope": "task-start-sensor", "status": "unsupported-client", "live_run_allowed": False,
    }
    for key, value in expected.items():
        if profile.get(key) != value:
            errors.append(PROFILE_PATH + ": task-start profile {} drifted".format(key))
    client = profile.get("client")
    if not isinstance(client, dict):
        errors.append(PROFILE_PATH + ": client sensor is missing")
        return
    exact_client = {
        "version_output": "codex-cli 0.150.0-alpha.8",
        "release_class": "prerelease-alpha",
        "binary_sha256": "4ff5e75f028e913cfeb53bd7319f87573cdce6538c1b1ccc44ce62d5ce51ca1d",
        "exec_help_sha256": "e504bac5a6364566fbe408132dec7993639def9258ece34e8352f51f8d43687c",
        "resolved_path_recorded": False,
    }
    if client != exact_client:
        errors.append(PROFILE_PATH + ": observed client evidence drifted")
    caps = profile.get("capabilities")
    if not isinstance(caps, dict) or caps.get("documented_config_keys_probe") != "not-proven" or caps.get("shell_environment_probe") != "not-run" or caps.get("process_cleanup_probe") != "not-run":
        errors.append(PROFILE_PATH + ": help output was overclaimed as a capability probe")
    validate_profile_evidence(
        profile.get("evidence"), profile.get("status"), PROFILE_PATH, errors
    )
    validate_profile_lane_bindings(profile, PROFILE_PATH, errors)
    if "unapproved-prerelease" not in str(profile.get("reason")):
        errors.append(PROFILE_PATH + ": prerelease blocking reason is missing")


def validate_execution_fixture(value: Any, envelope: Mapping[str, Any], profile: Mapping[str, Any], events: List[Mapping[str, Any]], final_value: Mapping[str, Any], errors: List[str]) -> None:
    label = "tests/runtime/fixtures/execution-result-valid.v1.json"
    if not isinstance(value, dict):
        errors.append(label + ": execution result must be an object")
        return
    if set(value) != {"schema", "attempt_id", "status", "authority", "worker", "events", "final_response", "git", "verifier", "digests", "privacy"}:
        errors.append(label + ": execution result fields drifted")
        return
    if value["schema"] != "execution-result/v1" or value["attempt_id"] != envelope["attempt_id"] or value["status"] != "pass" or value["authority"] != "adapter-authored":
        errors.append(label + ": result identity/status/authority drifted")
    worker = value["worker"]
    if worker != {"logical_invocations": 1, "exit_code": 0, "timed_out": False, "signal": None, "stdout_bytes": 467, "stderr_bytes": 0}:
        errors.append(
            label
            + ": worker evidence must record exactly one logical invocation"
        )
    expected_event_digest = sha256(b"".join(canonical_bytes(event) for event in events))
    if value["events"] != {"count": len(events), "terminal_count": 1, "terminal_state": "completed", "canonical_sha256": expected_event_digest}:
        errors.append(label + ": normalized event evidence drifted")
    if value["final_response"] != {"present": True, "valid": True, "sha256": sha256(canonical_bytes(final_value)), "outcome": "completed"}:
        errors.append(label + ": final-response evidence drifted")
    if value["git"] != {
        "pre_head": "7ee649272da3355a06a4b3a11271a3f0cbe8ed56", "post_head": "7ee649272da3355a06a4b3a11271a3f0cbe8ed56",
        "pre_tree": "fde54bf076ca83895acbd8bca2bba3f1b5378205", "post_tree": "fde54bf076ca83895acbd8bca2bba3f1b5378205",
        "worktree_tree": "ceb8f052e9f801dd1a7093dc2e6c408bf998508c",
        "changed_paths": ["work-item.txt"], "owned_paths_only": True, "expected_bytes": True, "other_changes": False,
    }:
        errors.append(label + ": exact Git evidence drifted")
    verifier = value["verifier"]
    if verifier != {"fresh_process": True, "read_only": True, "status": "pass", "record_sha256": "eadf6a4de1854f600255940213aebc966ecfe5185d48a9f34c83db3e2ce0af12"}:
        errors.append(label + ": fresh verifier evidence drifted")
    if value["digests"] != {"envelope_sha256": sha256(canonical_bytes(envelope)), "runtime_profile_sha256": sha256(canonical_bytes(profile))}:
        errors.append(label + ": envelope/profile digest binding drifted")
    if value["privacy"] != {"raw_jsonl_retained": False, "raw_reasoning_retained": False, "raw_stderr_retained": False, "private_paths_retained": False}:
        errors.append(label + ": execution-result privacy boundary drifted")


PROFILE_PATH = ".github/governance/codex-runtime-profile.v1.json"


def validate_runtime_frontier(
    ledger: Any,
    coverage: Any,
    manifest: Any,
    results: Any,
    errors: List[str],
) -> None:
    """Bind accepted T11 and active T12 to canonical release state."""

    if not isinstance(ledger, dict):
        errors.append(LEDGER_CONTRACT_PATH + ": ledger must be an object")
        return
    frontier = ledger.get("runtime_frontier")
    if frontier != expected_runtime_frontier():
        errors.append(
            LEDGER_CONTRACT_PATH
            + ": runtime_frontier must match the exact T11/T12 activation frontier"
        )

    if not isinstance(coverage, dict):
        errors.append(CONFORMANCE_COVERAGE_PATH + ": coverage must be an object")
        coverage = {}
    entries = coverage.get("entries")
    if not isinstance(entries, list):
        errors.append(CONFORMANCE_COVERAGE_PATH + ": entries must be a list")
        entries = []
    scenario_ids = [
        entry.get("scenario") if isinstance(entry, dict) else None
        for entry in entries
    ]
    if (
        coverage.get("scenario_count") != 136
        or len(entries) != 136
        or any(not isinstance(identifier, str) for identifier in scenario_ids)
        or len(set(scenario_ids)) != 136
    ):
        errors.append(
            CONFORMANCE_COVERAGE_PATH
            + ": canonical coverage must contain exactly 136 unique scenarios"
        )
    if any(
        not isinstance(entry, dict) or entry.get("verification_state") != "not-run"
        for entry in entries
    ):
        errors.append(
            CONFORMANCE_COVERAGE_PATH
            + ": every canonical scenario must remain not-run"
        )

    if not isinstance(manifest, dict):
        errors.append(CONFORMANCE_MANIFEST_PATH + ": manifest must be an object")
        manifest = {}
    catalog = manifest.get("scenario_catalog")
    if not isinstance(catalog, dict):
        errors.append(
            CONFORMANCE_MANIFEST_PATH + ": scenario_catalog must be an object"
        )
        catalog = {}
    result_store = catalog.get("result_store")
    if not isinstance(result_store, dict):
        errors.append(
            CONFORMANCE_MANIFEST_PATH
            + ": scenario_catalog.result_store must be an object"
        )
        result_store = {}
    if catalog.get("total") != 136 or catalog.get("verification_state") != "not-run":
        errors.append(
            CONFORMANCE_MANIFEST_PATH
            + ": catalog must preserve 136 scenarios in not-run state"
        )
    if (
        manifest.get("results") != []
        or manifest.get("release_blocked") is not True
        or result_store.get("result_count") != 0
    ):
        errors.append(
            CONFORMANCE_MANIFEST_PATH
            + ": release results must remain empty and release_blocked true"
        )

    if not isinstance(results, dict):
        errors.append(CONFORMANCE_RESULTS_PATH + ": results must be an object")
        results = {}
    if (
        results.get("result_count") != 0
        or results.get("results") != []
        or results.get("release_blocked") is not True
    ):
        errors.append(
            CONFORMANCE_RESULTS_PATH
            + ": release-level results must remain empty and release_blocked true"
        )


def validate_repository(root: Path) -> List[str]:
    errors: List[str] = []
    for relative in SCHEMAS + JSON_FIXTURES + OTHER_FILES + (
        LEDGER_CONTRACT_PATH,
        CONFORMANCE_COVERAGE_PATH,
        CONFORMANCE_MANIFEST_PATH,
        CONFORMANCE_RESULTS_PATH,
    ):
        read_regular(root, relative, errors)
    schemas = {relative: load_json(root, relative, errors) for relative in SCHEMAS}
    fixtures = {relative: load_json(root, relative, errors) for relative in JSON_FIXTURES}
    profile = load_json(root, PROFILE_PATH, errors)
    ledger = load_json(root, LEDGER_CONTRACT_PATH, errors)
    coverage = load_json(root, CONFORMANCE_COVERAGE_PATH, errors)
    manifest = load_json(root, CONFORMANCE_MANIFEST_PATH, errors)
    results = load_json(root, CONFORMANCE_RESULTS_PATH, errors)
    for relative, schema in schemas.items():
        validate_schema(relative, schema, errors)
    validate_runtime_profile_schema(
        schemas.get("docs/agreements/runtime/runtime-profile.v1.schema.json"),
        errors,
    )
    validate_runtime_override_schema(
        schemas.get("docs/agreements/runtime/task-execution-envelope.v1.schema.json"),
        errors,
    )
    validate_runtime_receipt_schema(
        schemas.get("docs/agreements/runtime/runtime-receipt.v1.schema.json"),
        errors,
    )
    validate_profile(profile, errors)
    validate_runtime_frontier(ledger, coverage, manifest, results, errors)

    role_instructions = {}
    for name, sandbox in (("task_supervisor", "read-only"), ("task_worker", "workspace-write"), ("task_verifier", "read-only")):
        relative = ".codex/agents/{}.toml".format(name)
        role_instructions[name] = parse_role(read_regular(root, relative, errors), relative, name, sandbox, errors)
    if sha256(role_instructions.get("task_worker", "").encode("utf-8")) != EXPECTED_ROLE_DIGEST:
        errors.append(".codex/agents/task_worker.toml: static developer-instruction digest drifted")

    adapter = import_script(root, ".github/scripts/codex-exec-adapter.py", "t11_runtime_adapter", errors)
    if adapter is not None:
        try:
            if tuple(adapter.SHELL_ENVIRONMENT_REASON_CODES) != SHELL_ENVIRONMENT_REASON_CODES:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: shell reason-code registry drifted from checker"
                )
            if tuple(adapter.NETWORK_SANDBOX_REASON_CODES) != NETWORK_SANDBOX_REASON_CODES:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: network reason-code registry drifted from checker"
                )
            if tuple(adapter.APPROVED_NETWORK_DENIAL_ERRNOS) != APPROVED_NETWORK_DENIAL_ERRNOS:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: approved network errno registry drifted from checker"
                )
            envelope = fixtures["tests/runtime/fixtures/envelope-valid.v1.json"]
            fixture_profile = fixtures["tests/runtime/fixtures/runtime-profile-valid.v1.json"]
            validate_runtime_override_mapping(
                envelope.get("worker", {}).get("overrides") if isinstance(envelope, dict) else None,
                "tests/runtime/fixtures/envelope-valid.v1.json",
                errors,
            )
            validate_profile_evidence(
                fixture_profile.get("evidence") if isinstance(fixture_profile, dict) else None,
                fixture_profile.get("status") if isinstance(fixture_profile, dict) else None,
                "tests/runtime/fixtures/runtime-profile-valid.v1.json",
                errors,
                EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH,
            )
            validate_profile_lane_bindings(
                fixture_profile,
                "tests/runtime/fixtures/runtime-profile-valid.v1.json",
                errors,
            )
            validate_runtime_override_mapping(
                adapter.REQUIRED_OVERRIDES,
                ".github/scripts/codex-exec-adapter.py",
                errors,
            )
            if adapter.runtime_configuration_intent() != expected_runtime_configuration_intent():
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: adapter-authored configuration intent/digest drifted"
                )
            observed_stage_a1_controller = [
                list(argv) for argv in adapter.STAGE_A1_CONTROLLER_ARGV
            ]
            observed_stage_a1_preclone = [
                list(argv) for argv in adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV
            ]
            if observed_stage_a1_preclone != EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Stage A.1 pre-clone qualification argv drifted"
                )
            if observed_stage_a1_controller != EXPECTED_STAGE_A1_CONTROLLER_ARGV:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Stage A.1 controller argv drifted"
                )
            if list(adapter.STAGE_A1_BWRAP_SMOKE_ARGV) != EXPECTED_STAGE_A1_SMOKE_ARGV:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Stage A.1 direct smoke argv drifted"
                )
            expected_controller_digest = sha256(
                canonical_bytes(EXPECTED_STAGE_A1_CONTROLLER_ARGV)
            )
            expected_preclone_digest = sha256(
                canonical_bytes(EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV)
            )
            if (
                expected_preclone_digest
                != EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
            ):
                errors.append(
                    ".github/scripts/check-runtime-contracts.py: Stage A.1 reviewed pre-clone argv/digest disagree"
                )
            if (
                adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
                != EXPECTED_STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256
            ):
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Stage A.1 pre-clone argv digest drifted"
                )
            if expected_controller_digest != EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256:
                errors.append(
                    ".github/scripts/check-runtime-contracts.py: Stage A.1 reviewed controller argv/digest disagree"
                )
            if adapter.STAGE_A1_CONTROLLER_ARGV_SHA256 != EXPECTED_STAGE_A1_CONTROLLER_ARGV_SHA256:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Stage A.1 controller argv digest drifted"
                )
            if (
                getattr(adapter, "GIT_BOOTSTRAP_EVIDENCE_SCHEMA", None)
                != "t11-git-bootstrap-evidence/v1"
                or adapter.expected_git_bootstrap_evidence()
                != expected_git_bootstrap_evidence()
                or adapter.not_run_git_bootstrap_evidence()
                != expected_not_run_git_bootstrap_evidence()
            ):
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: Git bootstrap trust anchor drifted"
                )
            representative_head = "a" * 40
            representative_tree = "b" * 40
            if (
                getattr(adapter, "REPOSITORY", None) != EXPECTED_REPOSITORY
                or getattr(adapter, "T11_ACCEPTED_PUBLIC_BRANCH", None)
                != EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH
                or getattr(adapter, "T12_PUBLIC_BRANCH", None)
                != EXPECTED_T12_PUBLIC_BRANCH
                or adapter.stage_a1_git_clone_contract(
                    representative_head, representative_tree,
                ) != expected_git_clone_contract(
                    representative_head, representative_tree,
                )
                or adapter.stage_a1_git_clone_contract_sha256(
                    representative_head, representative_tree,
                ) != expected_git_clone_contract_sha256(
                    representative_head, representative_tree,
                )
                or expected_git_clone_contract_sha256(
                    representative_head, representative_tree,
                ) != EXPECTED_REPRESENTATIVE_GIT_CLONE_CONTRACT_SHA256
                or adapter.stage_a1_git_clone_contract_sha256(
                    representative_head, representative_tree,
                    adapter.T11_ACCEPTED_PUBLIC_BRANCH,
                ) != expected_git_clone_contract_sha256(
                    representative_head, representative_tree,
                    EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH,
                )
                or expected_git_clone_contract_sha256(
                    representative_head, representative_tree,
                    EXPECTED_T11_ACCEPTED_PUBLIC_BRANCH,
                ) != "80175bb5a8b09587866e54b425361eaa796213e770e40b3b866d389796da12b7"
            ):
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: reviewed Git clone contract drifted"
                )
            approved_stage_a1_values = (
                ("bubblewrap package", adapter.APPROVED_BWRAP_PACKAGE_VERSION,
                 APPROVED_BWRAP_PACKAGE_VERSION),
                ("bubblewrap version", adapter.APPROVED_BWRAP_VERSION_OUTPUT,
                 APPROVED_BWRAP_VERSION_OUTPUT),
                ("bubblewrap binary", adapter.APPROVED_BWRAP_BINARY_SHA256,
                 APPROVED_BWRAP_BINARY_SHA256),
                ("AppArmor package", adapter.APPROVED_APPARMOR_PACKAGE_VERSION,
                 APPROVED_APPARMOR_PACKAGE_VERSION),
                ("AppArmor profile", adapter.APPROVED_BWRAP_PROFILE_SHA256,
                 APPROVED_BWRAP_PROFILE_SHA256),
                ("Git package", adapter.APPROVED_GIT_PACKAGE_VERSION,
                 APPROVED_GIT_PACKAGE_VERSION),
                ("Git version", adapter.APPROVED_GIT_VERSION_OUTPUT,
                 APPROVED_GIT_VERSION_OUTPUT),
                ("Git binary", adapter.APPROVED_GIT_BINARY_SHA256,
                 APPROVED_GIT_BINARY_SHA256),
            )
            for name, observed, expected in approved_stage_a1_values:
                if observed != expected:
                    errors.append(
                        ".github/scripts/codex-exec-adapter.py: Stage A.1 approved value drifted: "
                        + name
                    )
            adapter.validate_envelope(envelope)
            adapter.validate_runtime_profile(fixture_profile, allow_fixture=True)
            adapter.validate_runtime_profile(profile)
            final_fixture = fixtures["tests/runtime/fixtures/codex-final-response-valid.v1.json"]
            adapter.validate_final_response(final_fixture, envelope["attempt_id"], envelope["limits"])
            events, final_value, terminal = adapter.parse_jsonl(
                read_regular(root, "tests/runtime/fixtures/codex-jsonl-valid.jsonl", errors),
                envelope["attempt_id"], envelope["limits"],
            )
            expected_events = []
            for line in read_regular(root, "tests/runtime/fixtures/loop-events-valid.v1.jsonl", errors).decode("utf-8").splitlines():
                expected_events.append(strict_json_loads(line))
            if events != expected_events or final_value != final_fixture or terminal != "completed":
                errors.append("tests/runtime/fixtures: normalized event/final fixtures drifted")
            validate_execution_fixture(
                fixtures["tests/runtime/fixtures/execution-result-valid.v1.json"],
                envelope, fixture_profile, events, final_value, errors,
            )
            receipt_request = fixtures["tests/runtime/fixtures/runtime-receipt-valid.v1.json"]
            if not isinstance(receipt_request, dict) or set(receipt_request) != {"schema", "repository", "task", "pull_request", "artifacts", "checks", "limitations", "privacy"}:
                errors.append("tests/runtime/fixtures/runtime-receipt-valid.v1.json: native-artifact request fields drifted")
            else:
                artifacts = receipt_request["artifacts"]
                receipt_profile = artifacts["runtime_profile"]
                receipt_envelope = artifacts["envelope"]
                receipt_result = artifacts["execution_result"]
                receipt_verifier = artifacts["verifier"]
                validate_runtime_override_mapping(
                    receipt_envelope.get("worker", {}).get("overrides")
                    if isinstance(receipt_envelope, dict) else None,
                    "tests/runtime/fixtures/runtime-receipt-valid.v1.json envelope",
                    errors,
                )
                validate_profile_evidence(
                    receipt_profile.get("evidence") if isinstance(receipt_profile, dict) else None,
                    receipt_profile.get("status") if isinstance(receipt_profile, dict) else None,
                    "tests/runtime/fixtures/runtime-receipt-valid.v1.json profile",
                    errors,
                )
                validate_profile_lane_bindings(
                    receipt_profile,
                    "tests/runtime/fixtures/runtime-receipt-valid.v1.json profile",
                    errors,
                )
                adapter.validate_runtime_profile(receipt_profile)
                provider = receipt_profile.get("evidence", {}).get("containment_provider", {})
                receipt_pr = receipt_request.get("pull_request", {})
                if (
                    provider.get("public_head") != receipt_pr.get("head")
                    or provider.get("public_tree") != receipt_pr.get("tree")
                    or provider.get("codex_version_output") != receipt_profile.get("client", {}).get("version_output")
                    or provider.get("extracted_binary_sha256") != receipt_profile.get("client", {}).get("binary_sha256")
                ):
                    errors.append("tests/runtime/fixtures/runtime-receipt-valid.v1.json: provider/profile/PR cross-binding drifted")
                adapter.validate_envelope(receipt_envelope)
                adapter.validate_verifier_record(receipt_verifier, receipt_envelope["attempt_id"])
                adapter.validate_execution_result(receipt_result, receipt_envelope, receipt_profile, receipt_verifier)
            live_argv = adapter.build_live_argv(Path("/reviewed/codex"), Path("/private-target"), root, envelope)
            joined = "\n".join(live_argv)
            for marker in (envelope["attempt_id"], "Issue #25"):
                if marker in joined:
                    errors.append(".github/scripts/codex-exec-adapter.py: dynamic Task data appears in live argv")
            for argument in live_argv:
                if (
                    argument == "--ignore-rules"
                    or argument.startswith("--ignore-rules=")
                    or argument.startswith("--dangerously-bypass-")
                ):
                    errors.append(
                        ".github/scripts/codex-exec-adapter.py: live argv contains forbidden policy bypass "
                        + argument
                    )
            adapter.validate_runtime_argv_policy(live_argv, require_memory_overrides=True)
            for override_key, override_value in sorted(EXPECTED_RUNTIME_OVERRIDES.items()):
                rendered = "{}={}".format(override_key, adapter.toml_literal(override_value))
                if rendered not in live_argv:
                    errors.append(".github/scripts/codex-exec-adapter.py: live argv omits " + override_key)
            doctor_report = {
                "schemaVersion": 1,
                "generatedAt": "2026-08-28T00:00:00Z",
                "codexVersion": "0.150.1",
                "overallStatus": "ok",
                "checks": {
                    "auth.credentials": {
                        "id": "auth.credentials", "category": "auth", "status": "ok",
                        "summary": "Authentication available", "details": {},
                        "durationMs": 1, "remediation": None,
                    },
                    "config.load": {
                        "id": "config.load",
                        "category": "config",
                        "status": "ok",
                        "summary": "Configuration loaded",
                        "details": {"sources": ["user"]},
                        "durationMs": 1,
                        "remediation": None,
                        "issues": [],
                        "notes": ["redacted diagnostic note"],
                    },
                    "runtime.provenance": {
                        "id": "runtime.provenance", "category": "runtime", "status": "ok",
                        "summary": "Runtime identified", "details": {},
                        "durationMs": 1, "remediation": None,
                    },
                    "sandbox.helpers": {
                        "id": "sandbox.helpers", "category": "sandbox", "status": "ok",
                        "summary": "Sandbox helpers available", "details": {},
                        "durationMs": 1, "remediation": None,
                    },
                },
            }
            doctor_result = adapter.ProcessResult(
                0, None, False, False, False, canonical_bytes(doctor_report), 0, True
            )
            doctor_evidence = adapter.doctor_diagnostic_health(doctor_result)
            if doctor_evidence != {
                "classification": "diagnostic-only",
                "status": "pass",
                "checks": [
                    {"id": "auth.credentials", "category": "auth", "status": "ok"},
                    {"id": "config.load", "category": "config", "status": "ok"},
                    {"id": "runtime.provenance", "category": "runtime", "status": "ok"},
                    {"id": "sandbox.helpers", "category": "sandbox", "status": "ok"},
                ],
                "codex_issued_effective_configuration_proof": False,
            }:
                errors.append(
                    ".github/scripts/codex-exec-adapter.py: real doctor report shape was misclassified as effective-config proof"
                )
        except Exception as error:
            errors.append("runtime adapter/fixture validation failed: {}".format(str(error)[:300]))
    representative = fixtures.get("tests/runtime/fixtures/representative-task.v1.json")
    if not isinstance(representative, dict) or representative.get("initial_utf8") != EXPECTED_INITIAL.decode() or representative.get("initial_hex") != EXPECTED_INITIAL.hex() or representative.get("initial_sha256") != sha256(EXPECTED_INITIAL) or representative.get("expected_utf8") != EXPECTED_FINAL.decode() or representative.get("expected_hex") != EXPECTED_FINAL.hex() or representative.get("expected_sha256") != sha256(EXPECTED_FINAL) or representative.get("owned_paths") != ["work-item.txt"] or representative.get("allowed_worktree_entries") != ["work-item.txt"]:
        errors.append("tests/runtime/fixtures/representative-task.v1.json: exact representative Task drifted")

    adapter_text = read_regular(root, ".github/scripts/codex-exec-adapter.py", errors).decode("utf-8", errors="replace")
    receipt_text = read_regular(root, ".github/scripts/post-runtime-receipt.py", errors).decode("utf-8", errors="replace")
    validate_runtime_script_bypass_literals(
        adapter_text,
        ".github/scripts/codex-exec-adapter.py",
        errors,
        guard_function="validate_runtime_argv_policy",
    )
    validate_provider_git_source(
        adapter_text, ".github/scripts/codex-exec-adapter.py", errors,
    )
    validate_runtime_script_bypass_literals(
        receipt_text,
        ".github/scripts/post-runtime-receipt.py",
        errors,
    )
    for forbidden in ("shell=True", "os.system(", "subprocess.call(", "os.killpg("):
        if forbidden in adapter_text or forbidden in receipt_text:
            errors.append("runtime scripts contain forbidden shell or unbounded process construction: " + forbidden)
    for required in ("start_new_session=True", "_signal_if_same_birth", "SIGTERM", "SIGKILL", "shell=False", "stdin", "unsupported-client", "profile-drift", "UNCHECKABLE", "strict_json_loads", "git_directory_inventory", "process_table_snapshot", "runtime_process_identity_capability_error", "execution_root_inventory", "descriptor_xattr_inventory", "fresh semantic runtime sensor", "raw terminal occurrence", "release class disagrees"):
        if required not in adapter_text:
            errors.append(".github/scripts/codex-exec-adapter.py: missing deterministic boundary " + required)
    for required in (
        "--dry-run", "--apply", "--dry-run-proof-sha256",
        "--lifecycle-dry-run", "--lifecycle-apply",
        "t12-colima-lifecycle-completion-request/v1", "verify_linked_runtime_receipt",
        "validate_pull_request_binding", "PROBE_PULL_REQUEST = 24",
        "isCrossRepository", "headRepository", "headRefName",
        "codex/phase-2-live-codex-runtime",
        "--body-file", "read-back differs",
        "run_bounded_process", "receipt_marker", "lifecycle_marker",
        "native runtime artifact", "artifact_bundle_sha256", "existing_comments",
        "uncertain", "--paginate", "duplicate object key", "non-finite",
        "canonical_runtime_body", "different attempt",
        "MAX_LIFECYCLE_ABSENCE_AGE_SECONDS",
    ):
        if required not in receipt_text:
            errors.append(".github/scripts/post-runtime-receipt.py: missing receipt boundary " + required)
    if re.search(r"(?m)^PULL_REQUEST\s*=", receipt_text) is not None:
        errors.append(
            ".github/scripts/post-runtime-receipt.py: live receipt must not pin a static PR number"
        )
    for forbidden in ("issue edit", "comment --edit", "comment --delete"):
        if forbidden in receipt_text:
            errors.append(".github/scripts/post-runtime-receipt.py: append-only actuator contains forbidden operation " + forbidden)
    for relative in ("docs/agreements/adr/ADR-0008-minimal-codex-execution-loop.md", "docs/agreements/runtime/minimal-codex-execution-loop.md"):
        text = read_regular(root, relative, errors).decode("utf-8", errors="replace")
        for phrase in ("stdin", "fresh", "unsupported-client", "raw JSONL", "repository", "release"):
            if phrase not in text:
                errors.append(relative + ": missing documented boundary " + phrase)
    return errors


def main() -> int:
    errors = validate_repository(ROOT)
    if errors:
        for error in errors:
            print("ERROR: " + error, file=sys.stderr)
        return 1
    print("runtime contracts: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
