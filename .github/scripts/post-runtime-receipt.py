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
MAX_INPUT = 262_144
MAX_COMMENT_BYTES = 65_536
MAX_EXISTING_COMMENTS = 256
OID = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ATTEMPT = re.compile(r"ATTEMPT-[0-9a-f]{16}\Z")
PR_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/pull/([0-9]+)\Z")
CHECK_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/[0-9]+/job/[0-9]+\Z")
COMMENT_URL = re.compile(r"https://github\.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-([0-9]+)\Z")
MARKER = re.compile(r"<!-- t11-runtime-receipt attempt=(ATTEMPT-[0-9a-f]{16}) receipt_sha256=([0-9a-f]{64}) -->")
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
    if type(pr["number"]) is not int or not match or int(match.group(1)) != pr["number"] or not OID.fullmatch(str(pr["head"])) or not OID.fullmatch(str(pr["tree"])):
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
        envelope_digest=receipt["envelope"]["sha256"], result_digest=receipt["result"]["sha256"], verifier_digest=receipt["verifier"]["sha256"], quality_url=checks["quality"]["url"], conformance_url=checks["conformance"]["url"],
    )
    if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
        raise ReceiptError("rendered receipt exceeds its byte limit")
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
                continue
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="T11 append-only runtime receipt actuator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            require_runtime_fs_capabilities()
        data = read_stdin_bounded()
        receipt = validate_receipt(decode_json_object(data, "receipt input"))
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
