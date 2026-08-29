#!/usr/bin/env python3
"""Validate, render, and explicitly append the allowlisted T11 receipt."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
TASK = 23
PULL_REQUEST = 24
MAX_INPUT = 262_144
MAX_COMMENT_BYTES = 65_536
MAX_EXISTING_COMMENTS = 256
MAX_FUTURE_SKEW_SECONDS = 300
MAX_LIFECYCLE_ABSENCE_AGE_SECONDS = 3600
OID = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ATTEMPT = re.compile(r"ATTEMPT-[0-9a-f]{16}\Z")
PR_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/pull/([0-9]+)\Z")
CHECK_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/[0-9]+/job/[0-9]+\Z")
COMMENT_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-([0-9]+)\Z")
PR_COMMENT_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-([0-9]+)\Z")
MARKER = re.compile(r"<!-- t11-runtime-receipt attempt=(ATTEMPT-[0-9a-f]{16}) receipt_sha256=([0-9a-f]{64}) -->")
LIFECYCLE_MARKER = re.compile(r"<!-- t11-colima-lifecycle-receipt target=(issue|pr) attempt=(ATTEMPT-[0-9a-f]{16}) lifecycle_sha256=([0-9a-f]{64}) -->")
PRIVATE_PATH = re.compile(r"(?i)(?:^|[\s'\"]|file:(?://)?)(?:/users/|/home/|/root/|/tmp/|/private/|/var/folders/|~/|[a-z]:[\\/]|\\\\)")
SENSITIVE = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s]+"),
    re.compile(r"(?i)\b(?:x-api-key|api[_-]?key)\s*[:=]\s*[^\s]+"),
)
FORBIDDEN_KEYS = {
    "secret", "secrets", "credential", "credentials", "token", "tokens",
    "rawtranscript", "transcriptbody", "rawlog", "rawlogs", "stderrdump",
    "stdoutdump", "reasoningbody", "environment", "environmentdump",
    "localpath", "binarypath",
}
LIMITATIONS = {
    "named_custom_agent_runtime_selection": "unverified",
    "authenticated_role_identity": "unverified",
    "artifact_provenance": "unsigned-unverified",
    "phase2_complete": False,
    "repository_complete": False,
    "release_ready": False,
}
PRIVACY = {
    "allowlisted_projection": True,
    "raw_jsonl": False,
    "raw_reasoning": False,
    "raw_stderr": False,
    "transcript": False,
    "private_paths": False,
    "credential_values": False,
}
LIFECYCLE_PRIVACY = {
    "allowlisted_projection": True,
    "raw_mount_inventory": False,
    "raw_provider_configuration": False,
    "raw_paths": False,
    "credential_values": False,
    "auth_files": False,
    "device_codes": False,
    "raw_jsonl": False,
    "raw_reasoning": False,
    "raw_stderr": False,
    "transcript": False,
    "environment_values": False,
}


class ReceiptError(Exception):
    """A bounded, privacy-safe receipt failure."""


def runtime_fs_capability_error() -> Optional[str]:
    missing = [name for name in ("O_NOFOLLOW", "O_DIRECTORY") if not isinstance(getattr(os, name, None), int)]
    if os.open not in getattr(os, "supports_dir_fd", set()):
        missing.append("open(dir_fd)")
    if os.stat not in getattr(os, "supports_dir_fd", set()):
        missing.append("stat(dir_fd)")
    if os.stat not in getattr(os, "supports_follow_symlinks", set()):
        missing.append("stat(follow_symlinks)")
    return ", ".join(missing) if missing else None


def require_runtime_fs_capabilities() -> None:
    if runtime_fs_capability_error():
        raise ReceiptError("required no-follow filesystem capability is unavailable")


def read_stdin_bounded() -> bytes:
    data = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ReceiptError("receipt input exceeds its byte limit")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise ReceiptError("value is not canonical finite JSON")
    return (text + "\n").encode("utf-8")


def _strict_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("JSON contains a duplicate object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ReceiptError("JSON contains a non-finite number")


def _strict_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReceiptError("JSON contains a non-finite number")
    return parsed


def strict_json_loads(text: str, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_strict_pairs, parse_constant=_reject_constant, parse_float=_strict_float)
    except ReceiptError:
        raise
    except (json.JSONDecodeError, RecursionError, OverflowError, ValueError):
        raise ReceiptError(label + " is not valid bounded JSON")


def decode_json_object(data: bytes, label: str) -> Dict[str, Any]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ReceiptError(label + " is not valid UTF-8")
    value = strict_json_loads(text, label)
    if not isinstance(value, dict):
        raise ReceiptError(label + " must be an object")
    validate_tree_limits(value)
    return value


def exact_keys(value: Mapping[str, Any], expected: Sequence[str], label: str) -> None:
    if set(value) != set(expected):
        raise ReceiptError(label + " has unsupported or missing fields")


def validate_tree_limits(value: Any, privacy: bool = True) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 4096 or depth > 24:
            raise ReceiptError("receipt JSON exceeds structural limits")
        if isinstance(current, str):
            if len(current.encode("utf-8")) > 4096:
                raise ReceiptError("receipt string exceeds its limit")
            if privacy and (PRIVATE_PATH.search(current) or any(pattern.search(current) for pattern in SENSITIVE)):
                raise ReceiptError("receipt contains private or sensitive data")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ReceiptError("receipt contains a non-finite number")
        elif isinstance(current, list):
            if len(current) > 256:
                raise ReceiptError("receipt list exceeds its limit")
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise ReceiptError("receipt object key must be a string")
                normalized = re.sub(r"[^a-z0-9]", "", key.lower())
                if normalized in FORBIDDEN_KEYS:
                    raise ReceiptError("receipt contains a forbidden raw/private field")
                stack.append((child, depth + 1))


def load_adapter():
    adapter_path = Path(__file__).with_name("codex-exec-adapter.py")
    spec = importlib.util.spec_from_file_location("t11_receipt_runtime_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise ReceiptError("runtime artifact validator is unavailable")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def parse_observed_at(value: str) -> datetime.datetime:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise ReceiptError("runtime_profile observation time is invalid")
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        raise ReceiptError("runtime_profile observation time is invalid")


def validate_receipt(value: Any, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Validate native runtime artifacts and derive a safe receipt projection."""
    if not isinstance(value, dict):
        raise ReceiptError("receipt request must be an object")
    validate_tree_limits(value)
    exact_keys(value, ("schema", "repository", "task", "pull_request", "artifacts", "checks", "limitations", "privacy"), "receipt request")
    if value["schema"] != "runtime-receipt-request/v1" or value["repository"] != REPOSITORY:
        raise ReceiptError("receipt request identity is invalid")
    if value["task"] != {"issue": TASK, "url": "https://github.com/{}/issues/{}".format(REPOSITORY, TASK)}:
        raise ReceiptError("receipt request Task binding is invalid")
    pr = value["pull_request"]
    if not isinstance(pr, dict):
        raise ReceiptError("pull request must be an object")
    exact_keys(pr, ("number", "url", "head", "tree"), "pull request")
    match = PR_URL.fullmatch(str(pr["url"]))
    if type(pr["number"]) is not int or pr["number"] != PULL_REQUEST or not match or int(match.group(1)) != PULL_REQUEST or not OID.fullmatch(str(pr["head"])) or not OID.fullmatch(str(pr["tree"])):
        raise ReceiptError("pull-request binding is invalid")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, dict):
        raise ReceiptError("native runtime artifacts must be an object")
    exact_keys(artifacts, ("runtime_profile", "envelope", "execution_result", "verifier"), "native runtime artifacts")
    adapter = load_adapter()
    profile = artifacts["runtime_profile"]
    envelope = artifacts["envelope"]
    result = artifacts["execution_result"]
    verifier = artifacts["verifier"]
    try:
        adapter.validate_runtime_profile(profile)
        adapter.validate_envelope(envelope)
        adapter.validate_verifier_record(verifier, envelope.get("attempt_id") if isinstance(envelope, dict) else "")
        adapter.validate_execution_result(result, envelope, profile, verifier)
    except Exception as error:
        if error.__class__.__name__ == "ContractError":
            raise ReceiptError("native runtime artifact validation failed")
        raise
    attempt = envelope["attempt_id"]
    if not ATTEMPT.fullmatch(attempt):
        raise ReceiptError("native artifact attempt ID is invalid")
    if envelope["harness"] != {"commit": pr["head"], "tree": pr["tree"]}:
        raise ReceiptError("native envelope harness must equal the exact PR head/tree")
    if envelope["worker"]["model"] != profile["request"]["model"] or envelope["worker"]["reasoning_effort"] != profile["request"]["reasoning_effort"]:
        raise ReceiptError("native envelope/profile request binding drifted")
    if profile["scope"] != "exact-head-live-sensor" or profile["status"] != "match" or profile["live_run_allowed"] is not True:
        raise ReceiptError("native runtime profile is not an exact-head live match")
    provider = profile["evidence"]["containment_provider"]
    if provider["public_head"] != pr["head"] or provider["public_tree"] != pr["tree"]:
        raise ReceiptError("containment provider is not bound to the exact public PR head/tree")
    if (
        provider["codex_version_output"] != profile["client"]["version_output"]
        or provider["extracted_binary_sha256"] != profile["client"]["binary_sha256"]
        or profile["platform"] != {"os": provider["guest_os"], "architecture": provider["architecture"]}
    ):
        raise ReceiptError("containment provider client/platform binding drifted")
    observed = parse_observed_at(profile["observed_at"])
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    age = (current.astimezone(datetime.timezone.utc) - observed).total_seconds()
    if age < -300 or age > 900:
        raise ReceiptError("runtime_profile observation is stale or future-dated")

    checks = value["checks"]
    if not isinstance(checks, list) or len(checks) != 2:
        raise ReceiptError("receipt must bind exactly quality and conformance")
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ReceiptError("check must be an object")
        exact_keys(check, ("context", "url", "head", "result"), "check")
        if check["context"] not in ("quality", "conformance") or check["context"] in seen or check["head"] != pr["head"] or check["result"] != "success" or not CHECK_URL.fullmatch(str(check["url"])):
            raise ReceiptError("check binding is invalid or stale")
        seen.add(check["context"])
    if seen != {"quality", "conformance"}:
        raise ReceiptError("required check contexts are incomplete")
    if value["limitations"] != LIMITATIONS:
        raise ReceiptError("limitations must equal the tight allowlisted completion boundary")
    if value["privacy"] != PRIVACY:
        raise ReceiptError("receipt privacy boundary is invalid")
    profile_digest = sha256(canonical_bytes(profile))
    envelope_digest = sha256(canonical_bytes(envelope))
    result_digest = sha256(canonical_bytes(result))
    verifier_digest = sha256(canonical_bytes(verifier))
    target = {
        "base_commit": envelope["target"]["base_commit"],
        "base_tree": envelope["target"]["base_tree"],
        "changed_paths": result["git"]["changed_paths"],
        "post_tree": result["git"]["worktree_tree"],
    }
    receipt = {
        "schema": "runtime-receipt/v1", "repository": REPOSITORY,
        "task": value["task"], "pull_request": pr, "attempt_id": attempt,
        "harness": dict(envelope["harness"]), "target": target,
        "artifact_bundle_sha256": sha256(canonical_bytes(artifacts)),
        "runtime_profile": {
            "schema": "runtime-profile-evidence/v1", "sha256": profile_digest,
            "status": "pass", "observed_status": profile["status"],
            "observed_at": profile["observed_at"],
            "client_version": profile["client"]["version_output"],
            "release_class": profile["client"]["release_class"],
            "binary_sha256": profile["client"]["binary_sha256"],
            "exec_help_sha256": profile["client"]["exec_help_sha256"],
            "auth_class": profile["auth"]["class"],
            "model": profile["request"]["model"],
            "reasoning_effort": profile["request"]["reasoning_effort"],
        },
        "containment_provider": {
            "schema": "containment-provider-receipt-evidence/v1",
            "authority": provider["authority"],
            "codex_authenticated_attestation": provider["codex_authenticated_attestation"],
            "status": provider["status"],
            "provider_kind": provider["provider_kind"],
            "profile_name": provider["profile_name"],
            "vm_backend": provider["vm_backend"],
            "architecture": provider["architecture"],
            "native_architecture": provider["native_architecture"],
            "guest_os_kernel_sha256": sha256(canonical_bytes({
                "guest_os": provider["guest_os"],
                "guest_kernel": provider["guest_kernel"],
            })),
            "created_at": provider["created_at"],
            "provider_configuration_sha256": provider["provider_configuration_sha256"],
            "effective_mount_inventory_sha256": provider["effective_mount_inventory_sha256"],
            "provider_cache_mount_sha256": provider["provider_cache_mount_sha256"],
            "provider_cache_guest_mountpoint_sha256": provider["provider_cache_guest_mountpoint_sha256"],
            "host_mount_count": provider["host_mount_count"],
            "host_mount_classifications": provider["host_mount_classifications"],
            "all_host_mounts_read_only": provider["all_host_mounts_read_only"],
            "provider_cache_only": provider["provider_cache_only"],
            "host_sensitive_mounts_absent": provider["host_sensitive_mounts_absent"],
            "unapproved_mounts_absent": provider["unapproved_mounts_absent"],
            "ssh_agent_forwarding": provider["ssh_agent_forwarding"],
            "dot_ssh_public_key_loading": provider["dot_ssh_public_key_loading"],
            "user_ssh_config_modified": provider["user_ssh_config_modified"],
            "vm_instance_identity_sha256": provider["vm_instance_identity_sha256"],
            "public_head": provider["public_head"],
            "public_tree": provider["public_tree"],
            "repository_clean": provider["repository_clean"],
            "codex_version_output": provider["codex_version_output"],
            "approved_archive_sha256": provider["approved_archive_sha256"],
            "observed_archive_sha256": provider["observed_archive_sha256"],
            "extracted_binary_sha256": provider["extracted_binary_sha256"],
            "runtime_root_binding_sha256": provider["runtime_root_binding_sha256"],
            "dedicated_codex_home_binding_sha256": provider["dedicated_codex_home_binding_sha256"],
            "sandbox_configuration_probe": provider["sandbox_configuration_probe"],
            "network_boundary_probe": provider["network_boundary_probe"],
            "process_containment_probe": provider["process_containment_probe"],
            "control_plane": {
                "schema": "colima-control-plane-receipt-evidence/v1",
                **{
                    key: provider["control_plane"][key]
                    for key in (
                        "authority", "codex_authenticated_attestation", "status",
                        "pre_create_observed_at", "post_create_observed_at", "profile_name",
                        "colima_version", "vm_backend", "architecture",
                        "pre_create_profile_absent", "pre_create_runtime_data_absent",
                        "fresh_instance", "existing_instance_reused", "existing_container_reused",
                        "existing_volume_reused", "default_profile_reused",
                        "activation_context_unchanged", "private_vm_disk",
                        "repository_on_private_vm_disk", "runtime_root_on_private_vm_disk",
                        "additional_disks", "instance_identity_sha256",
                        "provider_configuration_sha256", "normalized_control_plane_sha256",
                        "raw_paths_recorded",
                    )
                },
            },
            "lifecycle": dict(provider["lifecycle"]),
        },
        "envelope": {
            "schema": "envelope-evidence/v1", "sha256": envelope_digest,
            "status": "pass", "attempt_id": attempt,
            "harness_commit": envelope["harness"]["commit"],
            "harness_tree": envelope["harness"]["tree"],
            "target_base_commit": envelope["target"]["base_commit"],
            "target_base_tree": envelope["target"]["base_tree"],
            "owned_paths": envelope["target"]["owned_paths"],
        },
        "result": {
            "schema": "execution-result-evidence/v1", "sha256": result_digest,
            "status": "pass", "attempt_id": attempt,
            "envelope_sha256": result["digests"]["envelope_sha256"],
            "runtime_profile_sha256": result["digests"]["runtime_profile_sha256"],
            "verifier_sha256": result["verifier"]["record_sha256"],
            "target_post_tree": result["git"]["worktree_tree"],
            "changed_paths": result["git"]["changed_paths"],
            "worker_invocations": result["worker"]["logical_invocations"],
            "terminal_state": result["events"]["terminal_state"],
        },
        "verifier": {
            "schema": "verifier-evidence/v1", "sha256": verifier_digest,
            "status": "pass", "attempt_id": attempt,
            "fresh_process": verifier["fresh_process"],
            "read_only": verifier["read_only"],
        },
        "checks": checks, "limitations": value["limitations"],
        "privacy": value["privacy"],
    }
    validate_tree_limits(receipt)
    return receipt


def validate_lifecycle_receipt(value: Any, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Validate the closed final-destroy evidence, separate from runtime receipt apply."""
    if not isinstance(value, dict):
        raise ReceiptError("lifecycle receipt request must be an object")
    validate_tree_limits(value)
    exact_keys(
        value,
        (
            "schema", "repository", "authority", "codex_authenticated_attestation",
            "task", "pull_request", "attempt_id", "provider", "runtime_receipt",
            "checks", "destroy", "privacy",
        ),
        "lifecycle receipt request",
    )
    if (
        value["schema"] != "t11-colima-lifecycle-receipt-request/v1"
        or value["repository"] != REPOSITORY
        or value["authority"] != "owner-authored"
        or value["codex_authenticated_attestation"] is not False
    ):
        raise ReceiptError("lifecycle receipt identity/authority is invalid")
    task = value["task"]
    if task != {"issue": TASK, "url": "https://github.com/{}/issues/{}".format(REPOSITORY, TASK)}:
        raise ReceiptError("lifecycle receipt Task binding is invalid")
    pr = value["pull_request"]
    expected_pr_url = "https://github.com/{}/pull/{}".format(REPOSITORY, PULL_REQUEST)
    if not isinstance(pr, dict):
        raise ReceiptError("lifecycle pull request must be an object")
    exact_keys(pr, ("number", "url", "head", "tree"), "lifecycle pull request")
    if (
        pr.get("number") != PULL_REQUEST or pr.get("url") != expected_pr_url
        or not OID.fullmatch(str(pr.get("head"))) or not OID.fullmatch(str(pr.get("tree")))
    ):
        raise ReceiptError("lifecycle receipt must bind exact PR #24 head/tree")
    attempt = value["attempt_id"]
    if not isinstance(attempt, str) or ATTEMPT.fullmatch(attempt) is None:
        raise ReceiptError("lifecycle attempt ID is invalid")
    provider = value["provider"]
    if not isinstance(provider, dict):
        raise ReceiptError("lifecycle provider binding must be an object")
    exact_keys(
        provider,
        ("profile_name", "vm_instance_identity_sha256", "normalized_control_plane_sha256"),
        "lifecycle provider binding",
    )
    if (
        provider.get("profile_name") != "t11-e2e-{}-01".format(pr["head"][:12])
        or not SHA.fullmatch(str(provider.get("vm_instance_identity_sha256")))
        or not SHA.fullmatch(str(provider.get("normalized_control_plane_sha256")))
        or provider.get("vm_instance_identity_sha256") == "0" * 64
        or provider.get("normalized_control_plane_sha256") == "0" * 64
    ):
        raise ReceiptError("lifecycle provider binding is invalid")
    linked = value["runtime_receipt"]
    if not isinstance(linked, dict):
        raise ReceiptError("linked runtime receipt must be an object")
    exact_keys(
        linked,
        ("comment_url", "body_sha256", "receipt_sha256", "posted_at", "request"),
        "linked runtime receipt",
    )
    if (
        not isinstance(linked.get("comment_url"), str)
        or COMMENT_URL.fullmatch(linked["comment_url"]) is None
        or not SHA.fullmatch(str(linked.get("body_sha256")))
        or not SHA.fullmatch(str(linked.get("receipt_sha256")))
    ):
        raise ReceiptError("linked runtime receipt binding is invalid")
    runtime_receipt_posted_at = parse_observed_at(linked.get("posted_at"))
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    current = current.astimezone(datetime.timezone.utc)
    if (runtime_receipt_posted_at - current).total_seconds() > MAX_FUTURE_SKEW_SECONDS:
        raise ReceiptError("lifecycle receipt timestamp is future-dated")
    canonical_runtime_receipt = validate_receipt(
        linked.get("request"), now=runtime_receipt_posted_at
    )
    canonical_runtime_body = render_comment(canonical_runtime_receipt)
    canonical_runtime_receipt_sha256 = sha256(canonical_bytes(canonical_runtime_receipt))
    canonical_runtime_body_sha256 = sha256(canonical_runtime_body.encode("utf-8"))
    if (
        linked["receipt_sha256"] != canonical_runtime_receipt_sha256
        or linked["body_sha256"] != canonical_runtime_body_sha256
        or canonical_runtime_receipt["attempt_id"] != attempt
        or canonical_runtime_receipt["task"] != task
        or canonical_runtime_receipt["pull_request"] != pr
    ):
        raise ReceiptError("linked runtime receipt is not the exact validated canonical receipt")
    runtime_profile_observed_at = parse_observed_at(
        canonical_runtime_receipt["runtime_profile"]["observed_at"]
    )
    if runtime_profile_observed_at > runtime_receipt_posted_at:
        raise ReceiptError("linked runtime receipt predates its runtime observation")
    canonical_provider = canonical_runtime_receipt["containment_provider"]
    if (
        canonical_provider["profile_name"] != provider["profile_name"]
        or canonical_provider["vm_instance_identity_sha256"]
        != provider["vm_instance_identity_sha256"]
        or canonical_provider["control_plane"]["normalized_control_plane_sha256"]
        != provider["normalized_control_plane_sha256"]
    ):
        raise ReceiptError("linked runtime receipt provider binding drifted")
    checks = value["checks"]
    if not isinstance(checks, list) or len(checks) != 2:
        raise ReceiptError("lifecycle receipt must bind exactly quality and conformance")
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ReceiptError("lifecycle check must be an object")
        exact_keys(check, ("context", "url", "head", "result"), "lifecycle check")
        if (
            check["context"] not in ("quality", "conformance") or check["context"] in seen
            or check["head"] != pr["head"] or check["result"] != "success"
            or not CHECK_URL.fullmatch(str(check["url"]))
        ):
            raise ReceiptError("lifecycle check binding is invalid or stale")
        seen.add(check["context"])
    if seen != {"quality", "conformance"}:
        raise ReceiptError("lifecycle required checks are incomplete")
    if canonical_runtime_receipt["checks"] != checks:
        raise ReceiptError("linked runtime receipt check binding drifted")
    destroy = value["destroy"]
    if not isinstance(destroy, dict):
        raise ReceiptError("lifecycle destroy evidence must be an object")
    exact_keys(
        destroy,
        (
            "destroy_requested", "destroy_requested_at", "destroy_completed",
            "destroy_completed_at", "profile_absence_readback",
            "profile_absence_observed_at", "runtime_data_absence_readback",
            "runtime_data_absence_observed_at",
        ),
        "lifecycle destroy evidence",
    )
    if (
        destroy.get("destroy_requested") is not True
        or destroy.get("destroy_completed") is not True
        or destroy.get("profile_absence_readback") != "absent"
        or destroy.get("runtime_data_absence_readback") != "absent"
    ):
        raise ReceiptError("lifecycle destroy/absence evidence is incomplete")
    times = {}
    for key in (
        "destroy_requested_at", "destroy_completed_at",
        "profile_absence_observed_at", "runtime_data_absence_observed_at",
    ):
        times[key] = parse_observed_at(destroy.get(key))
    if any(
        (timestamp - current).total_seconds() > MAX_FUTURE_SKEW_SECONDS
        for timestamp in (runtime_receipt_posted_at, *times.values())
    ):
        raise ReceiptError("lifecycle receipt timestamp is future-dated")
    if not (
        runtime_receipt_posted_at <= times["destroy_requested_at"]
        <= times["destroy_completed_at"]
        <= times["profile_absence_observed_at"]
        and times["destroy_completed_at"] <= times["runtime_data_absence_observed_at"]
    ):
        raise ReceiptError("lifecycle destroy/read-back chronology is invalid")
    latest_absence = max(
        times["profile_absence_observed_at"],
        times["runtime_data_absence_observed_at"],
    )
    if (current - latest_absence).total_seconds() > MAX_LIFECYCLE_ABSENCE_AGE_SECONDS:
        raise ReceiptError("lifecycle absence read-back is stale")
    if value["privacy"] != LIFECYCLE_PRIVACY:
        raise ReceiptError("lifecycle receipt privacy boundary is invalid")
    receipt = {
        "schema": "t11-colima-lifecycle-receipt/v1",
        "repository": REPOSITORY,
        "authority": value["authority"],
        "codex_authenticated_attestation": value["codex_authenticated_attestation"],
        "task": dict(task),
        "pull_request": dict(pr),
        "attempt_id": attempt,
        "provider": dict(provider),
        "runtime_receipt": {
            "comment_url": linked["comment_url"],
            "body_sha256": canonical_runtime_body_sha256,
            "receipt_sha256": canonical_runtime_receipt_sha256,
            "posted_at": linked["posted_at"],
            "request_sha256": sha256(canonical_bytes(linked["request"])),
            "record": canonical_runtime_receipt,
        },
        "checks": list(checks),
        "destroy": dict(destroy),
        "privacy": dict(value["privacy"]),
    }
    validate_tree_limits(receipt)
    return receipt


def receipt_marker(receipt: Mapping[str, Any]) -> str:
    return "<!-- t11-runtime-receipt attempt={} receipt_sha256={} -->".format(receipt["attempt_id"], sha256(canonical_bytes(receipt)))


def render_comment(receipt: Mapping[str, Any]) -> str:
    checks = {check["context"]: check for check in receipt["checks"]}
    body = """{marker}
## T11 exact-head runtime receipt

- Schema: `runtime-receipt/v1`
- Attempt: `{attempt}`
- Pull request: {pr_url}
- Harness commit/tree: `{head}` / `{tree}`
- Target base commit/tree: `{base}` / `{base_tree}`
- Target post-state tree: `{post_tree}`
- Changed paths: `work-item.txt` only
- Runtime profile projection: `pass` / `{profile_digest}`
- Containment provider: `{provider_kind}` / `{profile_name}` / `{provider_status}`
- Provider mount inventory: `{mount_digest}` (one read-only provider-internal cache mount; no other shared mount)
- Provider instance/control plane: `{instance_digest}` / `{control_plane_digest}` (fresh exact-head instance; safe normalized fields only)
- Provider lifecycle at receipt: destruction required; destruction not yet claimed
- Envelope projection: `pass` / `{envelope_digest}`
- Result projection: `pass` / `{result_digest}`
- Fresh verifier projection: `pass` / `{verifier_digest}`
- quality: [success]({quality_url})
- conformance: [success]({conformance_url})

### Structured limitations

- Named custom-agent runtime selection: unverified
- Authenticated role identity: unverified
- Artifact provenance/authentication: unsigned and unverified
- Phase 2 complete: false
- Repository complete: false
- Release ready: false

Privacy projection: allowlisted fields only; no credential value, private path,
raw JSONL, raw reasoning, raw stderr, transcript, raw log, or environment dump
is stored. This receipt does not complete Phase 2, the repository, or a release.""".format(
        marker=receipt_marker(receipt), attempt=receipt["attempt_id"], pr_url=receipt["pull_request"]["url"], head=receipt["pull_request"]["head"], tree=receipt["pull_request"]["tree"],
        base=receipt["target"]["base_commit"], base_tree=receipt["target"]["base_tree"], post_tree=receipt["target"]["post_tree"], profile_digest=receipt["runtime_profile"]["sha256"],
        provider_kind=receipt["containment_provider"]["provider_kind"], profile_name=receipt["containment_provider"]["profile_name"], provider_status=receipt["containment_provider"]["status"], mount_digest=receipt["containment_provider"]["effective_mount_inventory_sha256"], instance_digest=receipt["containment_provider"]["vm_instance_identity_sha256"], control_plane_digest=receipt["containment_provider"]["control_plane"]["normalized_control_plane_sha256"],
        envelope_digest=receipt["envelope"]["sha256"], result_digest=receipt["result"]["sha256"], verifier_digest=receipt["verifier"]["sha256"], quality_url=checks["quality"]["url"], conformance_url=checks["conformance"]["url"],
    )
    if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
        raise ReceiptError("rendered receipt exceeds its byte limit")
    validate_tree_limits(body)
    return body


def lifecycle_marker(receipt: Mapping[str, Any], target: str) -> str:
    if target not in ("issue", "pr"):
        raise ReceiptError("lifecycle receipt target is invalid")
    return "<!-- t11-colima-lifecycle-receipt target={} attempt={} lifecycle_sha256={} -->".format(
        target, receipt["attempt_id"], sha256(canonical_bytes(receipt))
    )


def render_lifecycle_comment(receipt: Mapping[str, Any], target: str) -> str:
    checks = {check["context"]: check for check in receipt["checks"]}
    body = """{marker}
## T11 Colima final-destroy evidence

- Target copy: `{target}`
- Schema: `t11-colima-lifecycle-receipt/v1`
- Authority: `owner-authored`; Codex-authenticated attestation: `false`
- Attempt: `{attempt}`
- Pull request/head/tree: {pr_url} / `{head}` / `{tree}`
- Runtime receipt: {runtime_url} / posted `{runtime_posted_at}`
- Runtime receipt body/record digests: `{runtime_body}` / `{runtime_record}`
- Provider profile: `{profile}`
- Provider instance/control-plane digests: `{instance}` / `{control}`
- Destroy requested/completed: `{requested_at}` / `{completed_at}`
- Profile absence read-back: `absent` / `{profile_absence_at}`
- Runtime-data absence read-back: `absent` / `{runtime_absence_at}`
- quality: [success]({quality_url})
- conformance: [success]({conformance_url})

Privacy projection is closed and allowlisted. It contains no raw mount or
provider configuration, private path, credential, auth file, device code,
environment dump, JSONL, reasoning, stderr, or transcript. This final-destroy
record does not complete Phase 2, the repository, or a release.""".format(
        marker=lifecycle_marker(receipt, target), target=target,
        attempt=receipt["attempt_id"], pr_url=receipt["pull_request"]["url"],
        head=receipt["pull_request"]["head"], tree=receipt["pull_request"]["tree"],
        runtime_url=receipt["runtime_receipt"]["comment_url"],
        runtime_posted_at=receipt["runtime_receipt"]["posted_at"],
        runtime_body=receipt["runtime_receipt"]["body_sha256"],
        runtime_record=receipt["runtime_receipt"]["receipt_sha256"],
        profile=receipt["provider"]["profile_name"],
        instance=receipt["provider"]["vm_instance_identity_sha256"],
        control=receipt["provider"]["normalized_control_plane_sha256"],
        requested_at=receipt["destroy"]["destroy_requested_at"],
        completed_at=receipt["destroy"]["destroy_completed_at"],
        profile_absence_at=receipt["destroy"]["profile_absence_observed_at"],
        runtime_absence_at=receipt["destroy"]["runtime_data_absence_observed_at"],
        quality_url=checks["quality"]["url"], conformance_url=checks["conformance"]["url"],
    )
    if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
        raise ReceiptError("rendered lifecycle receipt exceeds its byte limit")
    validate_tree_limits(body)
    return body


def gh_environment() -> Dict[str, str]:
    environment = {name: os.environ[name] for name in ("PATH", "HOME", "XDG_CONFIG_HOME", "LANG", "LC_ALL", "TZ") if name in os.environ}
    environment.setdefault("PATH", "/usr/bin:/bin")
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("LC_ALL", "C.UTF-8")
    environment.setdefault("TZ", "UTC")
    return environment


def run_gh(argv: Sequence[str], stdin_bytes: bytes = b"") -> bytes:
    environment = gh_environment()
    adapter = load_adapter()
    gh = adapter.resolve_executable_from_path("gh", environment)
    if gh is None:
        raise ReceiptError("GitHub CLI is unavailable from the explicit PATH")
    result = adapter.run_bounded_process([str(gh)] + list(argv), Path(__file__).resolve().parents[2], environment, stdin_bytes, 30, 1_048_576, 1_048_576, 2)
    if result.exit_code != 0 or result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
        raise ReceiptError("bounded GitHub operation failed")
    return result.stdout


def verify_local_head(receipt: Mapping[str, Any]) -> None:
    root = Path(__file__).resolve().parents[2]
    before = os.stat(str(root), follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ReceiptError("local harness root is not a directory")
    adapter = load_adapter()
    adapter.require_runtime_fs_capabilities()
    env = gh_environment()
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "PYTHONHASHSEED": "0"})
    git = adapter.resolve_executable_from_path("git", env)
    if git is None:
        raise ReceiptError("Git executable is unavailable from the explicit PATH")
    outputs = []
    for arguments in (("rev-parse", "HEAD"), ("rev-parse", "HEAD^{tree}"), ("status", "--porcelain=v1", "-z", "--untracked-files=all")):
        result = adapter.run_bounded_process([str(git), "--no-replace-objects", "-c", "core.hooksPath=/dev/null", "-C", str(root)] + list(arguments), root, env, b"", 30, 262_144, 262_144, 2)
        if result.exit_code != 0 or result.timed_out or result.stdout_overflow or result.stderr_overflow or not result.reaped:
            raise ReceiptError("bounded local Git verification failed")
        outputs.append(result.stdout)
    if outputs[0].decode("ascii").strip() != receipt["pull_request"]["head"] or outputs[1].decode("ascii").strip() != receipt["pull_request"]["tree"] or outputs[2]:
        raise ReceiptError("local harness head/tree/status drifted before receipt application")
    after = os.stat(str(root), follow_symlinks=False)
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        raise ReceiptError("local harness root binding drifted")


def gh_json(argv: Sequence[str], label: str, privacy: bool = True) -> Any:
    data = run_gh(argv)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ReceiptError(label + " is not valid UTF-8")
    value = strict_json_loads(text, label)
    validate_tree_limits(value, privacy=privacy)
    return value


def verify_external_head(receipt: Mapping[str, Any]) -> None:
    pr = receipt["pull_request"]
    issue = gh_json(["issue", "view", str(TASK), "--repo", REPOSITORY, "--json", "state,url"], "Task read-back")
    if issue != {"state": "OPEN", "url": "https://github.com/{}/issues/{}".format(REPOSITORY, TASK)}:
        raise ReceiptError("Task Issue is not the exact open receipt target")
    payload = gh_json(["pr", "view", str(pr["number"]), "--repo", REPOSITORY, "--json", "headRefOid,state,statusCheckRollup,url"], "PR read-back")
    if not isinstance(payload, dict) or payload.get("headRefOid") != pr["head"] or payload.get("state") != "OPEN" or payload.get("url") != pr["url"]:
        raise ReceiptError("pull-request head drifted before receipt application")
    expected_checks = {check["context"]: check["url"] for check in receipt["checks"]}
    observed_checks: Dict[str, Tuple[str, Any]] = {}
    rollup = payload.get("statusCheckRollup")
    if not isinstance(rollup, list):
        raise ReceiptError("pull-request required checks are uncheckable")
    for item in rollup:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("context")
        if name in expected_checks:
            if name in observed_checks:
                raise ReceiptError("required check context is duplicated")
            observed_checks[name] = (str(item.get("conclusion", "")).upper(), item.get("detailsUrl"))
    if set(observed_checks) != {"quality", "conformance"} or any(observed_checks[name] != ("SUCCESS", expected_checks[name]) for name in observed_checks):
        raise ReceiptError("required check results or URLs are missing, stale, or non-success")
    commit = gh_json(["api", "repos/{}/git/commits/{}".format(REPOSITORY, pr["head"])], "commit read-back")
    if not isinstance(commit, dict) or not isinstance(commit.get("tree"), dict) or commit["tree"].get("sha") != pr["tree"]:
        raise ReceiptError("pull-request tree drifted before receipt application")


def verify_linked_runtime_receipt(receipt: Mapping[str, Any]) -> None:
    linked = receipt["runtime_receipt"]
    exact_keys(
        linked,
        (
            "comment_url", "body_sha256", "receipt_sha256", "posted_at",
            "request_sha256", "record",
        ),
        "validated linked runtime receipt",
    )
    record = linked["record"]
    if not isinstance(record, dict):
        raise ReceiptError("validated linked runtime receipt record is invalid")
    canonical_receipt_sha256 = sha256(canonical_bytes(record))
    canonical_body = render_comment(record)
    canonical_body_sha256 = sha256(canonical_body.encode("utf-8"))
    if (
        canonical_receipt_sha256 != linked["receipt_sha256"]
        or canonical_body_sha256 != linked["body_sha256"]
        or record.get("attempt_id") != receipt["attempt_id"]
        or record.get("task") != receipt["task"]
        or record.get("pull_request") != receipt["pull_request"]
        or record.get("checks") != receipt["checks"]
    ):
        raise ReceiptError("linked runtime receipt canonical record binding drifted")
    record_provider = record.get("containment_provider")
    provider = receipt["provider"]
    if (
        not isinstance(record_provider, dict)
        or record_provider.get("profile_name") != provider["profile_name"]
        or record_provider.get("vm_instance_identity_sha256")
        != provider["vm_instance_identity_sha256"]
        or not isinstance(record_provider.get("control_plane"), dict)
        or record_provider["control_plane"].get("normalized_control_plane_sha256")
        != provider["normalized_control_plane_sha256"]
    ):
        raise ReceiptError("linked runtime receipt canonical provider binding drifted")
    match = COMMENT_URL.fullmatch(linked["comment_url"])
    if match is None:
        raise ReceiptError("linked runtime receipt URL is invalid")
    comment = gh_json(
        ["api", "repos/{}/issues/comments/{}".format(REPOSITORY, match.group(1))],
        "linked runtime receipt read-back",
    )
    if (
        not isinstance(comment, dict)
        or comment.get("html_url") != linked["comment_url"]
        or comment.get("created_at") != linked["posted_at"]
    ):
        raise ReceiptError("linked runtime receipt URL read-back drifted")
    body = comment.get("body")
    if not isinstance(body, str) or body != canonical_body:
        raise ReceiptError("linked runtime receipt is not the exact canonical render")
    if sha256(body.encode("utf-8")) != linked["body_sha256"]:
        raise ReceiptError("linked runtime receipt body digest drifted")
    markers = list(MARKER.finditer(body))
    if (
        len(markers) != 1
        or markers[0].group(1) != receipt["attempt_id"]
        or markers[0].group(2) != linked["receipt_sha256"]
    ):
        raise ReceiptError("linked runtime receipt marker binding drifted")
    for exact in (
        provider["profile_name"], provider["vm_instance_identity_sha256"],
        provider["normalized_control_plane_sha256"],
    ):
        if "`{}`".format(exact) not in body:
            raise ReceiptError("linked runtime receipt provider binding is incomplete")


def existing_comments() -> List[Mapping[str, Any]]:
    data = run_gh(["api", "repos/{}/issues/{}/comments?per_page=100".format(REPOSITORY, TASK), "--paginate", "--slurp"])
    try:
        value = strict_json_loads(data.decode("utf-8", errors="strict"), "existing receipt comments")
    except UnicodeDecodeError:
        raise ReceiptError("existing receipt comments are not valid UTF-8")
    pages = value if isinstance(value, list) else []
    comments: List[Mapping[str, Any]] = []
    for page in pages:
        candidates = page if isinstance(page, list) else ([page] if isinstance(page, dict) else [])
        for comment in candidates:
            if not isinstance(comment, dict):
                raise ReceiptError("existing receipt comment record is malformed")
            comments.append(comment)
            if len(comments) > MAX_EXISTING_COMMENTS:
                raise ReceiptError("existing receipt comments exceed the bounded preflight limit")
    return comments


def preflight_existing_receipt(receipt: Mapping[str, Any], body: str) -> Optional[str]:
    expected_marker = receipt_marker(receipt)
    attempt = receipt["attempt_id"]
    exact_url: Optional[str] = None
    for comment in existing_comments():
        text = comment.get("body")
        if not isinstance(text, str):
            continue
        bounded_text = text[:MAX_COMMENT_BYTES + 1]
        for marker in MARKER.finditer(bounded_text):
            if marker.group(1) != attempt:
                raise ReceiptError("a T11 runtime receipt already exists for a different attempt")
            if len(text.encode("utf-8")) > MAX_COMMENT_BYTES:
                raise ReceiptError("existing same-attempt receipt exceeds the bounded comment limit")
            if marker.group(0) != expected_marker or text != body:
                raise ReceiptError("existing receipt conflicts with the same attempt ID")
            url = comment.get("html_url")
            if not isinstance(url, str) or COMMENT_URL.fullmatch(url) is None:
                raise ReceiptError("idempotent receipt read-back URL is invalid")
            if exact_url is not None and exact_url != url:
                raise ReceiptError("same-attempt receipt is duplicated")
            exact_url = url
    return exact_url


def application_record(receipt: Mapping[str, Any], body: str, url: str, idempotent: bool, reconciled: bool) -> Dict[str, Any]:
    digest = sha256(body.encode("utf-8"))
    return {"schema": "runtime-receipt-application/v1", "status": "pass", "comment_url": url, "body_sha256": digest, "readback_sha256": digest, "receipt_sha256": sha256(canonical_bytes(receipt)), "idempotent": idempotent, "reconciled_after_uncertain_post": reconciled}


def apply_comment(receipt: Mapping[str, Any], body: str) -> Dict[str, Any]:
    verify_external_head(receipt)
    existing = preflight_existing_receipt(receipt, body)
    if existing is not None:
        verify_external_head(receipt)
        return application_record(receipt, body, existing, True, False)
    try:
        output = run_gh(["issue", "comment", str(TASK), "--repo", REPOSITORY, "--body-file", "-"], body.encode("utf-8"))
    except ReceiptError:
        reconciled = preflight_existing_receipt(receipt, body)
        if reconciled is not None:
            verify_external_head(receipt)
            return application_record(receipt, body, reconciled, True, True)
        raise ReceiptError("receipt POST outcome is uncertain; read-back found no matching receipt before retry")
    url = output.decode("utf-8", errors="strict").strip()
    match = COMMENT_URL.fullmatch(url)
    if not match:
        raise ReceiptError("GitHub did not return the expected Task comment URL")
    comment = gh_json(["api", "repos/{}/issues/comments/{}".format(REPOSITORY, match.group(1))], "posted receipt read-back")
    readback = comment.get("body") if isinstance(comment, dict) else None
    if readback != body:
        raise ReceiptError("posted receipt read-back differs from the exact rendered body")
    # A successful POST is not a success receipt if the governed head, tree,
    # or required checks drifted during the actuator/read-back interval.
    verify_external_head(receipt)
    return application_record(receipt, body, url, False, False)


def lifecycle_existing_comments(number: int) -> List[Mapping[str, Any]]:
    if number not in (TASK, PULL_REQUEST):
        raise ReceiptError("lifecycle comment target number is invalid")
    data = run_gh([
        "api", "repos/{}/issues/{}/comments?per_page=100".format(REPOSITORY, number),
        "--paginate", "--slurp",
    ])
    try:
        value = strict_json_loads(data.decode("utf-8", errors="strict"), "existing lifecycle comments")
    except UnicodeDecodeError:
        raise ReceiptError("existing lifecycle comments are not valid UTF-8")
    pages = value if isinstance(value, list) else []
    comments: List[Mapping[str, Any]] = []
    for page in pages:
        candidates = page if isinstance(page, list) else ([page] if isinstance(page, dict) else [])
        for comment in candidates:
            if not isinstance(comment, dict):
                raise ReceiptError("existing lifecycle comment record is malformed")
            comments.append(comment)
            if len(comments) > MAX_EXISTING_COMMENTS:
                raise ReceiptError("existing lifecycle comments exceed the bounded preflight limit")
    return comments


def lifecycle_url_pattern(target: str):
    if target == "issue":
        return COMMENT_URL
    if target == "pr":
        return PR_COMMENT_URL
    raise ReceiptError("lifecycle receipt target is invalid")


def preflight_existing_lifecycle_receipt(receipt: Mapping[str, Any], target: str, body: str) -> Optional[str]:
    expected_marker = lifecycle_marker(receipt, target)
    exact_url: Optional[str] = None
    number = TASK if target == "issue" else PULL_REQUEST
    for comment in lifecycle_existing_comments(number):
        text = comment.get("body")
        if not isinstance(text, str):
            continue
        bounded = text[:MAX_COMMENT_BYTES + 1]
        for marker in LIFECYCLE_MARKER.finditer(bounded):
            if marker.group(1) != target or marker.group(2) != receipt["attempt_id"]:
                continue
            if len(text.encode("utf-8")) > MAX_COMMENT_BYTES:
                raise ReceiptError("existing lifecycle receipt exceeds the bounded comment limit")
            if marker.group(0) != expected_marker or text != body:
                raise ReceiptError("existing lifecycle receipt conflicts with the same attempt and target")
            url = comment.get("html_url")
            if not isinstance(url, str) or lifecycle_url_pattern(target).fullmatch(url) is None:
                raise ReceiptError("idempotent lifecycle receipt URL is invalid")
            if exact_url is not None and exact_url != url:
                raise ReceiptError("same-target lifecycle receipt is duplicated")
            exact_url = url
    return exact_url


def apply_one_lifecycle_comment(receipt: Mapping[str, Any], target: str, body: str) -> Tuple[str, bool, bool]:
    existing = preflight_existing_lifecycle_receipt(receipt, target, body)
    if existing is not None:
        return existing, True, False
    number = TASK if target == "issue" else PULL_REQUEST
    argv = ["issue" if target == "issue" else "pr", "comment", str(number), "--repo", REPOSITORY, "--body-file", "-"]
    try:
        output = run_gh(argv, body.encode("utf-8"))
    except ReceiptError:
        reconciled = preflight_existing_lifecycle_receipt(receipt, target, body)
        if reconciled is not None:
            return reconciled, True, True
        raise ReceiptError("lifecycle receipt POST outcome is uncertain; read-back found no matching target copy")
    url = output.decode("utf-8", errors="strict").strip()
    match = lifecycle_url_pattern(target).fullmatch(url)
    if match is None:
        raise ReceiptError("GitHub did not return the expected lifecycle comment URL")
    comment = gh_json(
        ["api", "repos/{}/issues/comments/{}".format(REPOSITORY, match.group(1))],
        "posted lifecycle receipt read-back",
    )
    if not isinstance(comment, dict) or comment.get("html_url") != url or comment.get("body") != body:
        raise ReceiptError("posted lifecycle receipt read-back differs from the exact target body")
    return url, False, False


def apply_lifecycle_comments(
    receipt: Mapping[str, Any], issue_body: str, pr_body: str
) -> Dict[str, Any]:
    verify_external_head(receipt)
    verify_linked_runtime_receipt(receipt)
    issue_url, issue_idempotent, issue_reconciled = apply_one_lifecycle_comment(
        receipt, "issue", issue_body
    )
    verify_external_head(receipt)
    verify_linked_runtime_receipt(receipt)
    pr_url, pr_idempotent, pr_reconciled = apply_one_lifecycle_comment(
        receipt, "pr", pr_body
    )
    verify_external_head(receipt)
    verify_linked_runtime_receipt(receipt)
    return {
        "schema": "t11-colima-lifecycle-receipt-application/v1",
        "status": "pass",
        "issue_comment_url": issue_url,
        "issue_body_sha256": sha256(issue_body.encode("utf-8")),
        "pr_comment_url": pr_url,
        "pr_body_sha256": sha256(pr_body.encode("utf-8")),
        "lifecycle_sha256": sha256(canonical_bytes(receipt)),
        "idempotent_targets": {
            "issue": issue_idempotent,
            "pr": pr_idempotent,
        },
        "reconciled_after_uncertain_post": {
            "issue": issue_reconciled,
            "pr": pr_reconciled,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="T11 append-only runtime receipt actuator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--lifecycle-dry-run", action="store_true")
    mode.add_argument("--lifecycle-apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.apply or args.lifecycle_apply:
            require_runtime_fs_capabilities()
        data = read_stdin_bounded()
        decoded = decode_json_object(data, "receipt input")
        if args.lifecycle_dry_run or args.lifecycle_apply:
            receipt = validate_lifecycle_receipt(decoded)
            issue_body = render_lifecycle_comment(receipt, "issue")
            pr_body = render_lifecycle_comment(receipt, "pr")
            if args.lifecycle_dry_run:
                result = {
                    "schema": "t11-colima-lifecycle-receipt-dry-run/v1",
                    "status": "pass",
                    "target_issue": TASK,
                    "target_pull_request": PULL_REQUEST,
                    "issue_body_sha256": sha256(issue_body.encode("utf-8")),
                    "pr_body_sha256": sha256(pr_body.encode("utf-8")),
                    "lifecycle_sha256": sha256(canonical_bytes(receipt)),
                    "issue_body": issue_body,
                    "pr_body": pr_body,
                }
            else:
                verify_local_head(receipt)
                result = apply_lifecycle_comments(receipt, issue_body, pr_body)
        else:
            receipt = validate_receipt(decoded)
            body = render_comment(receipt)
            if args.dry_run:
                result = {"schema": "runtime-receipt-dry-run/v1", "status": "pass", "target_issue": TASK, "body_sha256": sha256(body.encode("utf-8")), "receipt_sha256": sha256(canonical_bytes(receipt)), "body": body}
            else:
                verify_local_head(receipt)
                result = apply_comment(receipt, body)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (ReceiptError, OSError, subprocess.SubprocessError, UnicodeError, ValueError, KeyError, TypeError, RecursionError) as error:
        # Never persist or echo attacker-controlled keys or values. Detailed
        # diagnostics remain local transport; the machine error is constant.
        del error
        sys.stdout.buffer.write(canonical_bytes({"schema": "runtime-receipt-error/v1", "status": "fail", "reason": "bounded receipt validation or actuation failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
