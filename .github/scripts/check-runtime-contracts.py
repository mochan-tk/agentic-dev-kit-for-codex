#!/usr/bin/env python3
"""Fail-closed deterministic validation for the T11 runtime vertical slice."""

from __future__ import annotations

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
EXPECTED_ROLE_DIGEST = "813baae383e35eea7195ffc0ad8695c7f562eac57c37ef1bb61ede6914661d23"
EXPECTED_INITIAL = b"status=pending\n"
EXPECTED_FINAL = b"status=complete\n"
OID = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_PATH = re.compile(r"(?i)(?:^|[\s'\"])(?:/users/|/home/|/root/|/tmp/|/private/|/var/folders/|~/|[a-z]:[\\/]|\\\\)")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


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
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o644 or info.st_nlink != 1:
        errors.append(relative + ": must be a single-link regular mode-100644 file")
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
        if (opened.st_dev, opened.st_ino, opened.st_size) != (info.st_dev, info.st_ino, info.st_size):
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
        if (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            errors.append(relative + ": changed while reading")
            return b""
    finally:
        os.close(descriptor)
    after = os.stat(str(path), follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
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
    conditions = schema["allOf"]
    nonmatch = {
        "if": {"properties": {"status": {"enum": ["profile-drift", "unsupported-client", "UNKNOWN", "UNCHECKABLE"]}}, "required": ["status"]},
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
        "config_recognition_probe", "shell_environment_probe",
        "process_containment_probe",
    ):
        if cap_properties.get(key) != {"const": "pass"}:
            errors.append(label + ": match does not require passing " + key)
    if then_properties.get("live_run_allowed") != {"const": True}:
        errors.append(label + ": match does not require live_run_allowed=true")


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
    if not isinstance(caps, dict) or caps.get("config_recognition_probe") != "not-proven" or caps.get("shell_environment_probe") != "not-run" or caps.get("process_containment_probe") != "not-run":
        errors.append(PROFILE_PATH + ": help output was overclaimed as a capability probe")
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
        errors.append(label + ": worker process evidence drifted")
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


def validate_repository(root: Path) -> List[str]:
    errors: List[str] = []
    for relative in SCHEMAS + JSON_FIXTURES + OTHER_FILES:
        read_regular(root, relative, errors)
    schemas = {relative: load_json(root, relative, errors) for relative in SCHEMAS}
    fixtures = {relative: load_json(root, relative, errors) for relative in JSON_FIXTURES}
    profile = load_json(root, PROFILE_PATH, errors)
    for relative, schema in schemas.items():
        validate_schema(relative, schema, errors)
    validate_runtime_profile_schema(
        schemas.get("docs/agreements/runtime/runtime-profile.v1.schema.json"),
        errors,
    )
    validate_runtime_receipt_schema(
        schemas.get("docs/agreements/runtime/runtime-receipt.v1.schema.json"),
        errors,
    )
    validate_profile(profile, errors)

    role_instructions = {}
    for name, sandbox in (("task_supervisor", "read-only"), ("task_worker", "workspace-write"), ("task_verifier", "read-only")):
        relative = ".codex/agents/{}.toml".format(name)
        role_instructions[name] = parse_role(read_regular(root, relative, errors), relative, name, sandbox, errors)
    if sha256(role_instructions.get("task_worker", "").encode("utf-8")) != EXPECTED_ROLE_DIGEST:
        errors.append(".codex/agents/task_worker.toml: static developer-instruction digest drifted")

    adapter = import_script(root, ".github/scripts/codex-exec-adapter.py", "t11_runtime_adapter", errors)
    if adapter is not None:
        try:
            envelope = fixtures["tests/runtime/fixtures/envelope-valid.v1.json"]
            fixture_profile = fixtures["tests/runtime/fixtures/runtime-profile-valid.v1.json"]
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
                adapter.validate_runtime_profile(receipt_profile)
                adapter.validate_envelope(receipt_envelope)
                adapter.validate_verifier_record(receipt_verifier, receipt_envelope["attempt_id"])
                adapter.validate_execution_result(receipt_result, receipt_envelope, receipt_profile, receipt_verifier)
            live_argv = adapter.build_live_argv(Path("/reviewed/codex"), Path("/private-target"), root, envelope)
            joined = "\n".join(live_argv)
            for marker in (envelope["attempt_id"], "Issue #23"):
                if marker in joined:
                    errors.append(".github/scripts/codex-exec-adapter.py: dynamic Task data appears in live argv")
            for override_key, override_value in sorted(adapter.REQUIRED_OVERRIDES.items()):
                rendered = "{}={}".format(override_key, adapter.toml_literal(override_value))
                if rendered not in live_argv:
                    errors.append(".github/scripts/codex-exec-adapter.py: live argv omits " + override_key)
        except Exception as error:
            errors.append("runtime adapter/fixture validation failed: {}".format(str(error)[:300]))
    representative = fixtures.get("tests/runtime/fixtures/representative-task.v1.json")
    if not isinstance(representative, dict) or representative.get("initial_utf8") != EXPECTED_INITIAL.decode() or representative.get("initial_hex") != EXPECTED_INITIAL.hex() or representative.get("initial_sha256") != sha256(EXPECTED_INITIAL) or representative.get("expected_utf8") != EXPECTED_FINAL.decode() or representative.get("expected_hex") != EXPECTED_FINAL.hex() or representative.get("expected_sha256") != sha256(EXPECTED_FINAL) or representative.get("owned_paths") != ["work-item.txt"] or representative.get("allowed_worktree_entries") != ["work-item.txt"]:
        errors.append("tests/runtime/fixtures/representative-task.v1.json: exact representative Task drifted")

    adapter_text = read_regular(root, ".github/scripts/codex-exec-adapter.py", errors).decode("utf-8", errors="replace")
    receipt_text = read_regular(root, ".github/scripts/post-runtime-receipt.py", errors).decode("utf-8", errors="replace")
    for forbidden in ("shell=True", "os.system(", "subprocess.call(", "os.killpg("):
        if forbidden in adapter_text or forbidden in receipt_text:
            errors.append("runtime scripts contain forbidden shell or unbounded process construction: " + forbidden)
    for required in ("start_new_session=True", "_signal_if_same_birth", "SIGTERM", "SIGKILL", "shell=False", "stdin", "unsupported-client", "profile-drift", "UNCHECKABLE", "strict_json_loads", "git_directory_inventory", "process_table_snapshot", "runtime_process_identity_capability_error", "execution_root_inventory", "descriptor_xattr_inventory", "fresh semantic runtime sensor", "raw terminal occurrence", "release class disagrees"):
        if required not in adapter_text:
            errors.append(".github/scripts/codex-exec-adapter.py: missing deterministic boundary " + required)
    for required in ("--dry-run", "--apply", "--body-file", "read-back differs", "run_bounded_process", "receipt_marker", "native runtime artifact", "artifact_bundle_sha256", "existing_comments", "uncertain", "--paginate", "duplicate object key", "non-finite"):
        if required not in receipt_text:
            errors.append(".github/scripts/post-runtime-receipt.py: missing receipt boundary " + required)
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
