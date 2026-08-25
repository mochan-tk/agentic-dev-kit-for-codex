#!/usr/bin/env python3
"""Fail-closed validation for the connector-neutral portable context contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


REPOSITORY = "mochan-tk/agentic-dev-kit-for-codex"
CONTRACT_PATH = "docs/agreements/portable-context-contract.v1.json"
HUMAN_PATH = "docs/agreements/portable-context-contract.md"
ADR_PATH = "docs/agreements/adr/ADR-0007-connector-neutral-context-contract.md"
REQUIREMENT_DIRECTORY = "docs/agreements/requirements"
DECISION_DIRECTORY = "docs/agreements/decisions"
PIN_DIRECTORY = "docs/context/pins"
CONTEXT_README = "docs/context/README.md"
CONNECTOR_PATH = ".github/connectors/connector-contract.v1.json"
CONNECTOR_README = ".github/connectors/README.md"
OWNERSHIP_PATH = ".github/governance/phase-task-ownership.v1.json"
RESULTS_PATH = "tests/conformance/results.json"
REQ_FIXTURE = "tests/contracts/fixtures/requirements-valid.v1.json"
DEC_FIXTURE = "tests/contracts/fixtures/decisions-valid.v1.json"
PIN_FIXTURE = "tests/contracts/fixtures/context-pin-valid.v1.json"
CONNECTOR_FIXTURE = "tests/contracts/fixtures/connector-valid.v1.json"
MAX_FILE_BYTES = 1_048_576
MAX_BLOB_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 20_000
MAX_STRING_LENGTH = 32_768
MAX_RECORDS_PER_KIND = 256
EXPECTED_REQ0001_SOURCES = [
    "https://github.com/mochan-tk/agentic-dev-kit-for-copilot/blob/fd265ddef150fab86cd54d0e383c2c25fe297ffb/.github/connectors/README.md",
    "https://github.com/mochan-tk/agentic-dev-kit-for-copilot/blob/fd265ddef150fab86cd54d0e383c2c25fe297ffb/.github/docs/agreements/requirements.md",
]
FULL_OID = re.compile(r"[0-9a-f]{40}\Z")
FULL_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REQ_ID = re.compile(r"REQ-([0-9]{4})\Z")
DEC_ID = re.compile(r"DEC-([0-9]{4})\Z")
PIN_ID = re.compile(r"PIN-([0-9]{4})\Z")
PRIVATE_PATH = re.compile(
    r"(?i)(?:^|[\s'\"])(?:/users/|/home/|/root/|/tmp/|/private/tmp/|/var/folders/|~/|[a-z]:[\\/]|\\\\)"
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s]+"),
    re.compile(r"(?im)^\s*raw[ _-]+(?:transcript|log)\s*:\s*\S+"),
)
FORBIDDEN_RECORD_KEYS = {
    "secret",
    "secrets",
    "credential",
    "credentials",
    "credentialvalue",
    "credentialvalues",
    "accesstoken",
    "accesstokens",
    "privatekey",
    "privatekeys",
    "environmentdump",
    "environmentdumps",
    "rawtranscript",
    "rawtranscripts",
    "rawlog",
    "rawlogs",
}

EXPECTED_CONTRACT = {
    "schema": "portable-context-contract/v1",
    "repository": REPOSITORY,
    "document_bindings": [
        {"path": CONNECTOR_README, "sha256": "24430131bc2d21376a28bbc41da533e9712d0b47274e317789e63a161c414461"},
        {"path": ADR_PATH, "sha256": "39a1c86f027534e600b630a4073e7d6f0a0293cfbbb852317cdcbf593705c160"},
        {"path": HUMAN_PATH, "sha256": "8cae4b44afd8d2cf05874f73d2e8f19b211cd4891630e9474321442dcf4a069f"},
        {"path": CONTEXT_README, "sha256": "aea59dc90f55cec1b6e3250600af52deab7f860287d72c6634829740ecc53b7c"},
    ],
    "record_locations": {
        "requirements": REQUIREMENT_DIRECTORY,
        "decisions": DECISION_DIRECTORY,
        "pins": PIN_DIRECTORY,
    },
    "identifiers": {
        "requirement": {
            "schema": "portable-requirement/v1",
            "pattern": "^REQ-[0-9]{4}$",
            "filename_pattern": "^REQ-[0-9]{4}\\.json$",
            "reuse": "forbidden",
            "immutable_after_task_base": True,
        },
        "decision": {
            "schema": "portable-decision/v1",
            "pattern": "^DEC-[0-9]{4}$",
            "filename_pattern": "^DEC-[0-9]{4}\\.json$",
            "reuse": "forbidden",
            "immutable_after_task_base": True,
        },
        "pin": {
            "schema": "context-pin/v1",
            "pattern": "^PIN-[0-9]{4}$",
            "filename_pattern": "^PIN-[0-9]{4}\\.context-pin\\.v1\\.json$",
            "reuse": "forbidden",
        },
    },
    "history": {
        "semantic_change": "new-record-only",
        "supersedes": "explicit-earlier-only-same-kind",
        "acyclic": True,
        "non_forking": True,
        "historical_records": "retained-byte-identical",
    },
    "context_conditions": {
        "required": [
            "verifiable-stable-requirements",
            "immutable-append-only-decisions",
            "reachable-from-every-declared-execution-surface",
            "stable-exact-task-reference",
        ],
        "t08_evidence": "stable-id-closed-shape-nonempty-verification-and-immutable-history-only",
        "semantic_verifiability": "requires-human-review-and-sufficiency-test",
        "cross_surface_reachability": "not-proven",
    },
    "sufficiency": {
        "test": "epic-decomposition",
        "criterion": "next-epic-tasks-have-verifiable-acceptance-without-missing-fundamentals",
        "canonical_state": "not-run",
        "proven": False,
    },
    "pin_verification": {
        "revision": "full-git-commit-id",
        "tree": "exact-git-tree-id",
        "source_kind": "regular-git-blob",
        "path_form": "normalized-nfc-repository-relative",
        "per_source_digest": "sha256",
        "aggregate_canonicalization": "context-pin-v1-lines",
        "aggregate_lines": [
            "context-pin/v1",
            "repository<TAB>{repository}",
            "revision<TAB>{revision}",
            "tree<TAB>{tree}",
            "{path}<TAB>{mode}<TAB>{blob}<TAB>{sha256} sorted by path",
        ],
        "aggregate_encoding": "utf-8-lf-with-trailing-lf",
        "git_object_resolution": "required-no-worktree-fallback",
        "self_pin": "forbidden",
        "validity": "exact-historical-object-and-digest-match",
        "freshness": "selected-pin-sources-match-head-index-live-worktree",
        "historic_staleness": "allowed-when-not-selected",
        "selected_pin_count": 1,
        "selection": "highest-pin-id",
        "required_before": ["decomposition", "execution"],
        "success_states": ["pass"],
        "non_success_states": ["drift", "UNKNOWN", "UNCHECKABLE", "fail"],
    },
    "connector_interface": {
        "contract": CONNECTOR_PATH,
        "operations": ["discover", "retrieve", "pin", "verify"],
        "mandatory_external_service": False,
        "mandatory_credential": False,
        "connector_specific_core_fields": [],
    },
    "task_reference": {
        "ledger_field": "References",
        "semantics": "durable-linkage-only",
        "proves_pin_validity": False,
        "proves_pin_freshness": False,
    },
    "privacy": {
        "record_shape": "closed-field-allowlists",
        "forbidden_categories": [
            "secrets",
            "credential-values",
            "access-tokens",
            "private-keys",
            "environment-dumps",
            "raw-transcripts",
            "raw-logs",
            "private-absolute-local-paths",
        ],
        "high_confidence_value_signatures": "rejected",
        "arbitrary_secret_absence": "requires-human-review",
    },
    "implementation": {
        "K01": "static-contract-advanced",
        "K02": "static-contract-advanced",
        "K05": "static-contract-advanced",
        "K06": "static-contract-only-runtime-unproven",
        "K10": "planned-unimplemented",
        "K11": "planned-unimplemented",
        "K16": "boundary-only-feedback-transport-unimplemented",
        "K18": "static-contract-advanced",
        "K19": "static-contract-advanced",
        "live_task_ritual": "not-implemented",
        "runtime_adapter": "not-implemented",
    },
    "scenario_families": {
        family: {"canonical_state": "not-run", "t08_effect": "static-contract-fixtures-only"}
        for family in ("C", "D", "I", "P", "S", "X")
    },
    "completion": {
        "results_empty": True,
        "release_blocked": True,
        "repository_complete": False,
    },
}

EXPECTED_CONNECTOR = {
    "schema": "connector-neutral-interface/v1",
    "repository": REPOSITORY,
    "scope": {
        "metadata_validation": "deferred",
        "concrete_connector_definitions": "not-shipped",
        "external_services": "not-required",
    },
    "operations": [
        {"name": "discover", "mutation": "read-only", "output": "bounded-source-inventory"},
        {
            "name": "retrieve",
            "mutation": "read-only",
            "output": "bounded-in-memory-provenance-records",
        },
        {
            "name": "pin",
            "mutation": "explicit-proposal-actuator",
            "output": "context-pin/v1",
        },
        {
            "name": "verify",
            "mutation": "read-only",
            "output": "validity-and-selected-freshness",
        },
    ],
    "evidence": {
        "states": ["pass", "fail", "drift", "UNKNOWN", "UNCHECKABLE"],
        "success_states": ["pass"],
        "unknown_is_success": False,
        "uncheckable_is_success": False,
    },
    "dependencies": {
        "mandatory_external_service": False,
        "mandatory_network": False,
        "mandatory_credential": False,
        "mandatory_connector": False,
    },
    "core_record": {
        "connector_specific_fields": [],
        "raw_payload_storage": "forbidden",
        "silent_repin": "forbidden",
        "repository_landing": "separate-explicit-proposal-actuator",
    },
}

REQUIRED_HUMAN_MARKERS = (
    "accepted-on-owner-merge",
    "context-pin-v1-lines",
    "repository<TAB>{repository}",
    "{path}<TAB>{mode}<TAB>{blob}<TAB>{sha256}",
    "numerically highest `PIN-####`",
    "linkage only",
    "does not prove pin validity or freshness",
    "`UNKNOWN`",
    "`UNCHECKABLE`",
    "K10 and K11 remain unimplemented",
    "feedback transport is not implemented",
    "does not implement the live Task ritual",
    "separate explicit proposal actuator",
    "`release_blocked` remains `true`",
)


class DuplicateKeyError(ValueError):
    pass


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def valid_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if value.startswith(("/", "//")) or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return False
    if unicodedata.normalize("NFC", value) != value:
        return False
    if any(unicodedata.category(char).startswith("C") for char in value):
        return False
    path = PurePosixPath(value)
    return value == path.as_posix() and all(part not in {"", ".", ".."} for part in path.parts)


def read_regular_snapshot(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> tuple[bytes, str]:
    """Read a bounded regular file through descriptor-relative no-follow opens."""
    if not valid_repo_path(relative):
        raise ValueError(f"unsafe repository path: {relative!r}")
    required: dict[str, int] = {}
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise ValueError(f"required platform flag {name} is unavailable")
        required[name] = value
    parts = relative.split("/")
    descriptors: list[int] = []
    bindings: list[tuple[int, str, tuple[int, int]]] = []
    try:
        current = os.open(os.fspath(root), os.O_RDONLY | required["O_DIRECTORY"] | required["O_NOFOLLOW"])
        descriptors.append(current)
        root_stat = os.fstat(current)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("repository root is not a directory")
        root_binding = (root_stat.st_dev, root_stat.st_ino)
        for part in parts[:-1]:
            parent = current
            current = os.open(
                part,
                os.O_RDONLY | required["O_DIRECTORY"] | required["O_NOFOLLOW"],
                dir_fd=parent,
            )
            descriptors.append(current)
            current_stat = os.fstat(current)
            if not stat.S_ISDIR(current_stat.st_mode):
                raise ValueError(f"repository path parent is not a directory: {relative}")
            bindings.append((parent, part, (current_stat.st_dev, current_stat.st_ino)))
        parent = current
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | required["O_NOFOLLOW"] | required["O_NONBLOCK"],
            dir_fd=parent,
        )
        descriptors.append(file_fd)

        def verify_bindings() -> None:
            live_root = os.stat(os.fspath(root), follow_symlinks=False)
            if not stat.S_ISDIR(live_root.st_mode) or (live_root.st_dev, live_root.st_ino) != root_binding:
                raise ValueError("repository root binding changed while reading governed input")
            for parent_fd, name, expected in bindings:
                live = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISDIR(live.st_mode) or (live.st_dev, live.st_ino) != expected:
                    raise ValueError(f"repository directory binding changed while reading {relative}")

        verify_bindings()
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"repository input is not a regular file: {relative}")
        if before.st_size > limit:
            raise ValueError(f"repository input exceeds size limit: {relative}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(65_536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise ValueError(f"repository input exceeds size limit: {relative}")
        after = os.fstat(file_fd)
        verify_bindings()
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        signature = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if signature(before) != signature(after):
            raise ValueError(f"repository input changed while read: {relative}")
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError(f"repository input binding changed while read: {relative}")
        git_mode = "100755" if before.st_mode & 0o111 else "100644"
        return b"".join(chunks), git_mode
    except OSError as exc:
        raise ValueError(f"cannot safely read {relative}: {exc}") from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def read_regular_bytes(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> bytes:
    return read_regular_snapshot(root, relative, limit)[0]


def read_text(root: Path, relative: str) -> str:
    data = read_regular_bytes(root, relative)
    if b"\0" in data:
        raise ValueError(f"repository input contains NUL: {relative}")
    try:
        return data.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"repository input is not UTF-8: {relative}") from exc


def load_json(root: Path, relative: str) -> Any:
    text = read_text(root, relative)
    try:
        value = json.loads(text, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, DuplicateKeyError, RecursionError) as exc:
        raise ValueError(f"invalid JSON in {relative}: {exc}") from exc
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError(f"invalid JSON in {relative}: structure exceeds safe limit")
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > MAX_STRING_LENGTH:
            raise ValueError(f"invalid JSON in {relative}: string exceeds safe limit")
    return value


def strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(strict_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(strict_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected


def exact_keys(value: Any, keys: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    if set(value) != keys:
        errors.append(f"{label} has unsupported or missing fields")
        return False
    return True


def safe_string(value: Any, label: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > MAX_STRING_LENGTH:
        errors.append(f"{label} must be a bounded non-empty canonical string")
        return False
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"} and char not in "\n\t" for char in value):
        errors.append(f"{label} contains an unsafe Unicode character")
        return False
    if PRIVATE_PATH.search(value):
        errors.append(f"{label} contains a private absolute local path")
        return False
    return True


def scan_privacy(value: Any, label: str, errors: list[str]) -> None:
    stack: list[tuple[Any, str]] = [(value, label)]
    while stack:
        item, current = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
                if normalized in FORBIDDEN_RECORD_KEYS:
                    errors.append(f"{current} contains forbidden durable field {key!r}")
                stack.append((child, f"{current}.{key}"))
        elif isinstance(item, list):
            stack.extend((child, f"{current}[{index}]") for index, child in enumerate(item))
        elif isinstance(item, str):
            if PRIVATE_PATH.search(item):
                errors.append(f"{current} contains a private absolute local path")
            if any(pattern.search(item) for pattern in SENSITIVE_VALUE_PATTERNS):
                errors.append(f"{current} contains a prohibited high-confidence sensitive value")


def record_number(identifier: Any, pattern: re.Pattern[str], label: str, errors: list[str]) -> int | None:
    if not isinstance(identifier, str):
        errors.append(f"{label} must be a string")
        return None
    match = pattern.fullmatch(identifier)
    if match is None or int(match.group(1)) == 0:
        errors.append(f"{label} has an invalid stable ID")
        return None
    return int(match.group(1))


def string_list(value: Any, label: str, errors: list[str], *, allow_empty: bool = False) -> list[str] | None:
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > 256:
        errors.append(f"{label} must be a bounded string list")
        return None
    for index, item in enumerate(value):
        safe_string(item, f"{label}[{index}]", errors)
    if any(not isinstance(item, str) for item in value) or len(value) != len(set(value)):
        errors.append(f"{label} must contain unique strings")
        return None
    return value


def validate_record_set(records: Any, kind: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    pattern = REQ_ID if kind == "requirement" else DEC_ID
    required = (
        {"schema", "id", "title", "statement", "status", "supersedes", "source_references", "verification"}
        if kind == "requirement"
        else {"schema", "id", "title", "status", "decision", "rationale", "supersedes", "references"}
    )
    schema = f"portable-{kind}/v1"
    if not isinstance(records, list) or not records or len(records) > MAX_RECORDS_PER_KIND:
        errors.append(f"{label} must be a bounded non-empty record list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    observed_numbers: list[int] = []
    superseded_by: Counter[str] = Counter()
    for index, record in enumerate(records):
        item_label = f"{label}[{index}]"
        scan_privacy(record, item_label, errors)
        if not exact_keys(record, required, item_label, errors):
            continue
        identifier = record.get("id")
        number = record_number(identifier, pattern, f"{item_label}.id", errors)
        if number is not None:
            observed_numbers.append(number)
        if isinstance(identifier, str):
            if identifier in result:
                errors.append(f"{label} reuses stable ID {identifier}")
            else:
                result[identifier] = record
        if record.get("schema") != schema:
            errors.append(f"{item_label}.schema must be {schema}")
        for field in required - {"schema", "id", "supersedes", "source_references", "verification", "references"}:
            safe_string(record.get(field), f"{item_label}.{field}", errors)
        if record.get("status") != "accepted-on-owner-merge":
            errors.append(f"{item_label}.status must be accepted-on-owner-merge")
        supersedes = string_list(record.get("supersedes"), f"{item_label}.supersedes", errors, allow_empty=True)
        if supersedes is not None:
            for prior in supersedes:
                superseded_by[prior] += 1
                prior_number = record_number(prior, pattern, f"{item_label}.supersedes", errors)
                if number is not None and prior_number is not None and prior_number >= number:
                    errors.append(f"{item_label}.supersedes must name earlier same-kind IDs")
        if kind == "requirement":
            string_list(record.get("source_references"), f"{item_label}.source_references", errors)
            string_list(record.get("verification"), f"{item_label}.verification", errors)
        else:
            string_list(record.get("references"), f"{item_label}.references", errors)
    if observed_numbers != sorted(observed_numbers):
        errors.append(f"{label} must be sorted by stable ID")
    for identifier, record in result.items():
        for prior in record.get("supersedes", []) if isinstance(record.get("supersedes"), list) else []:
            if prior not in result:
                errors.append(f"{identifier} supersedes missing historical record {prior}")
    forks = sorted(identifier for identifier, count in superseded_by.items() if count > 1)
    if forks:
        errors.append(f"{label} has non-forking supersedes violations: {', '.join(forks)}")
    return result


def list_record_paths(root: Path, directory: str, filename: re.Pattern[str], errors: list[str]) -> list[str]:
    target = root / directory
    try:
        entries = list(target.iterdir())
    except OSError as exc:
        errors.append(f"cannot enumerate {directory}: {exc}")
        return []
    if len(entries) > MAX_RECORDS_PER_KIND:
        errors.append(f"{directory} exceeds record count limit")
        return []
    paths: list[str] = []
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        try:
            mode = entry.lstat().st_mode
        except OSError as exc:
            errors.append(f"cannot inspect {relative}: {exc}")
            continue
        if not stat.S_ISREG(mode):
            errors.append(f"record input is not a regular file: {relative}")
            continue
        if filename.fullmatch(entry.name) is None:
            errors.append(f"unsupported record filename: {relative}")
            continue
        paths.append(relative)
    collision = Counter(unicodedata.normalize("NFC", item).casefold() for item in paths)
    if any(count > 1 for count in collision.values()):
        errors.append(f"{directory} has a Unicode/case path collision")
    return sorted(paths)


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_text(root: Path, arguments: tuple[str, ...], label: str, errors: list[str]) -> str | None:
    result = run_git(root, *arguments)
    if result is None:
        errors.append(f"UNCHECKABLE: cannot execute Git while resolving {label}")
        return None
    if result.returncode != 0:
        errors.append(f"UNKNOWN: Git object unavailable for {label}")
        return None
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeError:
        errors.append(f"UNCHECKABLE: non-ASCII Git result for {label}")
        return None


def tree_entry(
    root: Path,
    tree: str,
    path: str,
    label: str,
    errors: list[str],
    *,
    invalid_state: str = "fail",
) -> tuple[str, str] | None:
    result = run_git(root, "ls-tree", "-z", tree, "--", path)
    if result is None:
        errors.append(f"UNCHECKABLE: cannot execute Git while resolving {label}")
        return None
    if result.returncode != 0:
        errors.append(f"UNKNOWN: Git tree unavailable for {label}")
        return None
    records = [item for item in result.stdout.split(b"\0") if item]
    if len(records) != 1:
        errors.append(f"{invalid_state}: exact Git path is absent or ambiguous for {label}")
        return None
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, object_type, oid = metadata.decode("ascii").split()
        decoded = raw_path.decode("utf-8")
    except (ValueError, UnicodeError):
        errors.append(f"UNCHECKABLE: malformed Git tree entry for {label}")
        return None
    if decoded != path or object_type != "blob" or mode not in {"100644", "100755"} or FULL_OID.fullmatch(oid) is None:
        errors.append(f"{invalid_state}: {label} is not the exact regular Git blob")
        return None
    return mode, oid


def index_entry(root: Path, path: str, label: str, errors: list[str]) -> tuple[str, str] | None:
    result = run_git(root, "ls-files", "--stage", "-z", "--", path)
    if result is None:
        errors.append(f"UNCHECKABLE: cannot inspect Git index for {label}")
        return None
    if result.returncode != 0:
        errors.append(f"UNCHECKABLE: Git index observation failed for {label}")
        return None
    records = [item for item in result.stdout.split(b"\0") if item]
    if len(records) != 1:
        errors.append(f"drift: selected pin index path is absent or conflicted for {label}")
        return None
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        decoded = raw_path.decode("utf-8")
    except (ValueError, UnicodeError):
        errors.append(f"UNCHECKABLE: malformed Git index entry for {label}")
        return None
    if decoded != path or stage != "0" or mode not in {"100644", "100755"} or FULL_OID.fullmatch(oid) is None:
        errors.append(f"drift: selected pin index entry is not one exact regular file for {label}")
        return None
    return mode, oid


def git_blob(root: Path, oid: str, label: str, errors: list[str]) -> bytes | None:
    size = git_text(root, ("cat-file", "-s", oid), f"{label} size", errors)
    if size is None:
        return None
    try:
        parsed_size = int(size)
    except ValueError:
        errors.append(f"UNCHECKABLE: invalid Git blob size for {label}")
        return None
    if parsed_size < 0 or parsed_size > MAX_BLOB_BYTES:
        errors.append(f"UNCHECKABLE: Git blob exceeds size limit for {label}")
        return None
    result = run_git(root, "cat-file", "blob", oid)
    if result is None:
        errors.append(f"UNCHECKABLE: cannot read Git blob for {label}")
        return None
    if result.returncode != 0:
        errors.append(f"UNKNOWN: Git blob unavailable for {label}")
        return None
    if len(result.stdout) != parsed_size:
        errors.append(f"UNCHECKABLE: Git blob size changed for {label}")
        return None
    return result.stdout


def canonical_pin_bytes(pin: dict[str, Any]) -> bytes:
    lines = [
        "context-pin/v1",
        f"repository\t{pin['repository']}",
        f"revision\t{pin['revision']}",
        f"tree\t{pin['tree']}",
    ]
    lines.extend(
        f"{source['path']}\t{source['mode']}\t{source['blob']}\t{source['sha256']}"
        for source in pin["sources"]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_pin_shape(pin: Any, pin_path: str, label: str, errors: list[str]) -> int | None:
    if not exact_keys(
        pin,
        {"schema", "id", "purpose", "repository", "revision", "tree", "sources", "aggregate", "claim_boundary", "verification"},
        label,
        errors,
    ):
        return None
    if pin.get("schema") != "context-pin/v1" or pin.get("repository") != REPOSITORY:
        errors.append(f"{label} has unsupported schema or repository")
    if pin.get("purpose") != "bootstrap-governance-inputs":
        errors.append(f"{label}.purpose must be bootstrap-governance-inputs")
    number = record_number(pin.get("id"), PIN_ID, f"{label}.id", errors)
    expected_name = f"{pin.get('id')}.context-pin.v1.json"
    if PurePosixPath(pin_path).name != expected_name:
        errors.append(f"{label} filename must match its stable ID")
    for field in ("revision", "tree"):
        value = pin.get(field)
        if not isinstance(value, str) or FULL_OID.fullmatch(value) is None:
            errors.append(f"{label}.{field} must be a full lowercase Git object ID")
    sources = pin.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 64:
        errors.append(f"{label}.sources must be a bounded non-empty list")
        sources = []
    observed: list[str] = []
    for index, source in enumerate(sources):
        source_label = f"{label}.sources[{index}]"
        if not exact_keys(source, {"path", "mode", "blob", "sha256"}, source_label, errors):
            continue
        path = source.get("path")
        if not valid_repo_path(path):
            errors.append(f"{source_label}.path is not a normalized repository-relative path")
        elif path == pin_path:
            errors.append(f"{source_label}.path creates a forbidden self-pin")
        else:
            observed.append(path)
        if source.get("mode") not in {"100644", "100755"}:
            errors.append(f"{source_label}.mode is not a regular-file Git mode")
        if not isinstance(source.get("blob"), str) or FULL_OID.fullmatch(source["blob"]) is None:
            errors.append(f"{source_label}.blob must be a full Git blob ID")
        if not isinstance(source.get("sha256"), str) or FULL_SHA256.fullmatch(source["sha256"]) is None:
            errors.append(f"{source_label}.sha256 must be a lowercase SHA-256")
    if observed != sorted(observed) or len(observed) != len(set(observed)):
        errors.append(f"{label}.sources must be sorted and unique")
    collisions = Counter(unicodedata.normalize("NFC", path).casefold() for path in observed)
    if any(count > 1 for count in collisions.values()):
        errors.append(f"{label}.sources has a Unicode/case path collision")
    aggregate = pin.get("aggregate")
    if not exact_keys(aggregate, {"algorithm", "canonicalization", "sha256"}, f"{label}.aggregate", errors):
        aggregate = {}
    if aggregate.get("algorithm") != "sha256" or aggregate.get("canonicalization") != "context-pin-v1-lines":
        errors.append(f"{label}.aggregate has unsupported semantics")
    if not isinstance(aggregate.get("sha256"), str) or FULL_SHA256.fullmatch(aggregate["sha256"]) is None:
        errors.append(f"{label}.aggregate.sha256 must be a lowercase SHA-256")
    expected_claim_boundary = {
        "proves_listed_sources_only": True,
        "proves_context_completeness": False,
        "proves_sufficiency": False,
        "binds_t08_new_records": False,
    }
    if not strict_equal(pin.get("claim_boundary"), expected_claim_boundary):
        errors.append(f"{label}.claim_boundary must limit proof to listed bootstrap sources")
    verification = pin.get("verification")
    expected_verification = {
        "required_before": ["decomposition", "execution"],
        "success_state": "pass",
        "non_success_states": ["drift", "UNKNOWN", "UNCHECKABLE", "fail"],
        "references_semantics": "durable-linkage-only-not-validity-or-freshness-evidence",
    }
    if not strict_equal(verification, expected_verification):
        errors.append(f"{label}.verification must keep both fail-closed gates and linkage-only references")
    scan_privacy(pin, label, errors)
    return number


def verify_pin_git(root: Path, pin: dict[str, Any], pin_path: str, selected: bool, errors: list[str]) -> None:
    label = f"pin {pin.get('id', pin_path)}"
    revision = pin.get("revision")
    tree = pin.get("tree")
    if not isinstance(revision, str) or FULL_OID.fullmatch(revision) is None or not isinstance(tree, str) or FULL_OID.fullmatch(tree) is None:
        return
    object_type = git_text(root, ("cat-file", "-t", revision), f"{label} revision", errors)
    if object_type is not None:
        if object_type not in {"blob", "commit", "tag", "tree"}:
            errors.append(f"UNCHECKABLE: malformed Git object type for {label} revision")
            return
        if object_type != "commit":
            errors.append(f"fail: {label} revision is not a commit")
            return
    ancestry = run_git(root, "merge-base", "--is-ancestor", revision, "HEAD")
    if ancestry is None:
        errors.append(f"UNCHECKABLE: cannot establish governed ancestry for {label}")
    elif ancestry.returncode == 1:
        errors.append(f"fail: {label} revision is not an ancestor of governed HEAD")
    elif ancestry.returncode != 0:
        errors.append(f"UNKNOWN: governed ancestry is unavailable for {label}")
    resolved_tree = git_text(root, ("rev-parse", f"{revision}^{{tree}}"), f"{label} tree", errors)
    if resolved_tree is not None:
        if FULL_OID.fullmatch(resolved_tree) is None:
            errors.append(f"UNCHECKABLE: malformed resolved Git tree for {label}")
        elif resolved_tree != tree:
            errors.append(f"fail: {label} tree does not match its exact revision")
    sources = pin.get("sources") if isinstance(pin.get("sources"), list) else []
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not valid_repo_path(source.get("path")):
            continue
        path = source["path"]
        entry = tree_entry(root, tree, path, f"{label} source {path}", errors)
        if entry is None:
            continue
        mode, oid = entry
        if mode != source.get("mode") or oid != source.get("blob"):
            errors.append(f"fail: {label} source binding mismatch for {path}")
        data = git_blob(root, oid, f"{label} source {path}", errors)
        if data is not None and hashlib.sha256(data).hexdigest() != source.get("sha256"):
            errors.append(f"fail: {label} source digest mismatch for {path}")
    try:
        canonical = canonical_pin_bytes(pin)
    except (KeyError, TypeError):
        canonical = b""
    aggregate = pin.get("aggregate") if isinstance(pin.get("aggregate"), dict) else {}
    if canonical and hashlib.sha256(canonical).hexdigest() != aggregate.get("sha256"):
        errors.append(f"fail: {label} canonical aggregate digest mismatch")
    if not selected:
        return
    current_tree = git_text(root, ("rev-parse", "HEAD^{tree}"), "current selected-pin freshness tree", errors)
    if current_tree is None:
        errors.append("UNCHECKABLE: selected pin blocks decomposition and execution")
        return
    drifted: list[str] = []
    for source in sources:
        if not isinstance(source, dict) or not valid_repo_path(source.get("path")):
            continue
        path = source["path"]
        entry_errors: list[str] = []
        entry = tree_entry(
            root,
            current_tree,
            path,
            f"selected HEAD freshness source {path}",
            entry_errors,
            invalid_state="drift",
        )
        if entry is None:
            errors.extend(entry_errors)
            drifted.append(path)
            continue
        mode, oid = entry
        data = git_blob(root, oid, f"selected HEAD freshness source {path}", entry_errors)
        errors.extend(entry_errors)
        if mode != source.get("mode") or data is None or hashlib.sha256(data).hexdigest() != source.get("sha256"):
            drifted.append(path)
            continue
        index_errors: list[str] = []
        indexed = index_entry(root, path, f"selected freshness source {path}", index_errors)
        errors.extend(index_errors)
        if indexed is None:
            drifted.append(path)
            continue
        index_errors = []
        index_mode, index_oid = indexed
        index_data = git_blob(root, index_oid, f"selected index freshness source {path}", index_errors)
        errors.extend(index_errors)
        if index_mode != source.get("mode") or index_data is None or hashlib.sha256(index_data).hexdigest() != source.get("sha256"):
            drifted.append(path)
            continue
        try:
            live_data, live_mode = read_regular_snapshot(root, path)
        except ValueError as exc:
            errors.append(f"drift: selected pin live source is not safely readable for {path}: {exc}")
            drifted.append(path)
            continue
        if live_mode != source.get("mode") or hashlib.sha256(live_data).hexdigest() != source.get("sha256"):
            drifted.append(path)
    if drifted:
        errors.append("drift: selected pin blocks decomposition and execution: " + ", ".join(sorted(drifted)))


def git_base_records(root: Path, base_tree: str, directory: str, errors: list[str]) -> dict[str, str]:
    result = run_git(root, "ls-tree", "-r", "-z", base_tree, "--", directory)
    if result is None:
        errors.append(f"UNCHECKABLE: cannot inspect immutable base records under {directory}")
        return {}
    if result.returncode != 0:
        errors.append(f"UNKNOWN: immutable Task base tree is unavailable for {directory}")
        return {}
    records: dict[str, str] = {}
    for raw in [item for item in result.stdout.split(b"\0") if item]:
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode, object_type, oid = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            errors.append(f"UNCHECKABLE: malformed immutable base listing under {directory}")
            return {}
        if object_type != "blob" or mode not in {"100644", "100755"} or not valid_repo_path(path):
            errors.append(f"UNKNOWN: immutable base record is not a regular blob: {path}")
            continue
        records[path] = oid
    return records


def validate_immutable_history(root: Path, ownership: Any, current_paths: set[str], errors: list[str]) -> None:
    if not isinstance(ownership, dict) or not isinstance(ownership.get("tasks"), list):
        return
    active = [task for task in ownership["tasks"] if isinstance(task, dict) and task.get("state") == "active"]
    if len(active) != 1:
        errors.append("portable history requires exactly one active Task")
        return
    base_commit = active[0].get("base_commit")
    base_tree = active[0].get("base_tree")
    if not isinstance(base_commit, str) or FULL_OID.fullmatch(base_commit) is None or not isinstance(base_tree, str) or FULL_OID.fullmatch(base_tree) is None:
        errors.append("portable history active Task base binding is invalid")
        return
    resolved = git_text(root, ("rev-parse", f"{base_commit}^{{tree}}"), "active Task base tree", errors)
    if resolved is not None and resolved != base_tree:
        errors.append("fail: active Task base tree binding is invalid")
    patterns = {
        REQUIREMENT_DIRECTORY: re.compile(r"REQ-([0-9]{4})\.json\Z"),
        DECISION_DIRECTORY: re.compile(r"DEC-([0-9]{4})\.json\Z"),
        PIN_DIRECTORY: re.compile(r"PIN-([0-9]{4})\.context-pin\.v1\.json\Z"),
    }
    for directory, pattern in patterns.items():
        base_records = git_base_records(root, base_tree, directory, errors)
        for path, oid in base_records.items():
            if path not in current_paths:
                errors.append(f"immutable historical record was deleted: {path}")
                continue
            base_data = git_blob(root, oid, f"immutable base record {path}", errors)
            if base_data is None:
                continue
            try:
                current_data = read_regular_bytes(root, path)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if current_data != base_data:
                errors.append(f"immutable historical record changed after Task base: {path}")
        base_numbers = [
            int(match.group(1))
            for path in base_records
            if (match := pattern.fullmatch(PurePosixPath(path).name)) is not None
        ]
        if base_numbers:
            highest = max(base_numbers)
            for path in sorted(current_paths - set(base_records)):
                if PurePosixPath(path).parent.as_posix() != directory:
                    continue
                match = pattern.fullmatch(PurePosixPath(path).name)
                if match is not None and int(match.group(1)) <= highest:
                    errors.append(
                        f"new append-only record ID must exceed active Task base maximum {highest:04d}: {path}"
                    )


def validate_accepted_main_history(root: Path, current_paths: set[str], errors: list[str]) -> None:
    """Keep records already present on a resolvable main ref byte-immutable."""
    observed_trees: set[str] = set()
    for reference in ("refs/remotes/origin/main", "refs/heads/main"):
        result = run_git(root, "show-ref", "--verify", "--hash", reference)
        if result is None:
            errors.append(f"UNCHECKABLE: cannot inspect accepted main reference {reference}")
            continue
        if result.returncode != 0:
            continue
        try:
            commit = result.stdout.decode("ascii").strip()
        except UnicodeError:
            errors.append(f"UNCHECKABLE: malformed accepted main reference {reference}")
            continue
        if FULL_OID.fullmatch(commit) is None:
            errors.append(f"UNCHECKABLE: malformed accepted main object for {reference}")
            continue
        tree = git_text(root, ("rev-parse", f"{commit}^{{tree}}"), f"accepted main tree {reference}", errors)
        if tree is None or tree in observed_trees:
            continue
        observed_trees.add(tree)
        accepted_paths: set[str] = set()
        for directory in (REQUIREMENT_DIRECTORY, DECISION_DIRECTORY, PIN_DIRECTORY):
            for path, oid in git_base_records(root, tree, directory, errors).items():
                accepted_paths.add(path)
                if path not in current_paths:
                    errors.append(f"accepted main historical record was deleted: {path}")
                    continue
                accepted = git_blob(root, oid, f"accepted main record {path}", errors)
                if accepted is None:
                    continue
                try:
                    current = read_regular_bytes(root, path)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if current != accepted:
                    errors.append(f"accepted main historical record changed: {path}")
        if accepted_paths:
            history = run_git(
                root,
                "log",
                "--format=",
                "--name-only",
                "-z",
                "--diff-filter=DR",
                f"{commit}..HEAD",
                "--",
                REQUIREMENT_DIRECTORY,
                DECISION_DIRECTORY,
                PIN_DIRECTORY,
            )
            if history is None:
                errors.append(f"UNCHECKABLE: cannot inspect append-only history from {reference}")
            elif history.returncode != 0:
                errors.append(f"UNKNOWN: append-only history is unavailable from {reference}")
            else:
                try:
                    removed = {
                        item.strip(b"\n").decode("utf-8")
                        for item in history.stdout.split(b"\0")
                        if item.strip(b"\n")
                    }
                except UnicodeError:
                    errors.append(f"UNCHECKABLE: malformed append-only history from {reference}")
                else:
                    violations = sorted(accepted_paths & removed)
                    if violations:
                        errors.append(
                            "accepted main historical record was deleted or renamed in intervening history: "
                            + ", ".join(violations)
                        )


def validate_documents(root: Path, errors: list[str]) -> None:
    try:
        human = read_text(root, HUMAN_PATH)
        adr = read_text(root, ADR_PATH)
        context = read_text(root, CONTEXT_README)
        connector = read_text(root, CONNECTOR_README)
    except ValueError as exc:
        errors.append(str(exc))
        return
    for marker in REQUIRED_HUMAN_MARKERS:
        if marker not in human:
            errors.append(f"human portable contract is missing synchronized marker: {marker}")
    for marker in (
        "fd265ddef150fab86cd54d0e383c2c25fe297ffb",
        "88f96493ec167602750c8dfec044629bd494a586",
        "55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7",
        "accepted-on-owner-merge",
        "K10, K11",
    ):
        if marker not in adr:
            errors.append(f"ADR-0007 is missing provenance or boundary marker: {marker}")
    for marker in ("numerically highest immutable `PIN-####`", "linkage only", "does not prove"):
        if marker not in context:
            errors.append(f"context README is missing validity/reference boundary: {marker}")
    for marker in ("exactly four operations", "separate explicit proposal actuator", "No account, network service, credential"):
        if marker not in connector:
            errors.append(f"connector README is missing neutral interface boundary: {marker}")


def validate_document_bindings(root: Path, contract: Any, errors: list[str]) -> None:
    bindings = contract.get("document_bindings") if isinstance(contract, dict) else None
    if not isinstance(bindings, list):
        errors.append("machine portable contract is missing document SHA-256 bindings")
        return
    observed: list[str] = []
    for index, binding in enumerate(bindings):
        label = f"document_bindings[{index}]"
        if not exact_keys(binding, {"path", "sha256"}, label, errors):
            continue
        path = binding.get("path")
        digest = binding.get("sha256")
        if not valid_repo_path(path) or not isinstance(digest, str) or FULL_SHA256.fullmatch(digest) is None:
            errors.append(f"{label} must bind one normalized path to SHA-256")
            continue
        observed.append(path)
        try:
            actual = hashlib.sha256(read_regular_bytes(root, path)).hexdigest()
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if actual != digest:
            errors.append(f"reviewed human document SHA-256 drift: {path}")
    if observed != sorted(observed) or len(observed) != len(set(observed)):
        errors.append("document SHA-256 bindings must be sorted and unique")


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        contract = load_json(root, CONTRACT_PATH)
        connector = load_json(root, CONNECTOR_PATH)
        ownership = load_json(root, OWNERSHIP_PATH)
        results = load_json(root, RESULTS_PATH)
        req_fixture = load_json(root, REQ_FIXTURE)
        dec_fixture = load_json(root, DEC_FIXTURE)
        pin_fixture = load_json(root, PIN_FIXTURE)
        connector_fixture = load_json(root, CONNECTOR_FIXTURE)
    except ValueError as exc:
        return [str(exc)]
    if not strict_equal(contract, EXPECTED_CONTRACT):
        errors.append("machine portable contract drifted from the reviewed v1 contract")
    validate_document_bindings(root, contract, errors)
    if not strict_equal(connector, EXPECTED_CONNECTOR):
        errors.append("machine connector contract drifted from the neutral v1 interface")
    if not strict_equal(connector_fixture, connector):
        errors.append("connector fixture is not synchronized with the machine contract")
    if not isinstance(results, dict) or results.get("results") != []:
        errors.append("conformance results must remain empty")
    if not isinstance(ownership, dict) or not isinstance(ownership.get("phase"), dict) or ownership["phase"].get("release_blocked") is not True:
        errors.append("release_blocked must remain true")

    req_paths = list_record_paths(root, REQUIREMENT_DIRECTORY, re.compile(r"REQ-[0-9]{4}\.json\Z"), errors)
    dec_paths = list_record_paths(root, DECISION_DIRECTORY, re.compile(r"DEC-[0-9]{4}\.json\Z"), errors)
    pin_paths = list_record_paths(root, PIN_DIRECTORY, re.compile(r"PIN-[0-9]{4}\.context-pin\.v1\.json\Z"), errors)
    requirements: list[Any] = []
    decisions: list[Any] = []
    pins: list[tuple[int, str, dict[str, Any]]] = []
    for path in req_paths:
        try:
            record = load_json(root, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        identifier = record.get("id") if isinstance(record, dict) else None
        if PurePosixPath(path).name != f"{identifier}.json":
            errors.append(f"requirement filename does not match stable ID: {path}")
        requirements.append(record)
    for path in dec_paths:
        try:
            record = load_json(root, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        identifier = record.get("id") if isinstance(record, dict) else None
        if PurePosixPath(path).name != f"{identifier}.json":
            errors.append(f"decision filename does not match stable ID: {path}")
        decisions.append(record)
    validate_record_set(requirements, "requirement", "requirements", errors)
    validate_record_set(decisions, "decision", "decisions", errors)

    if not exact_keys(req_fixture, {"schema", "records"}, "requirement fixture", errors) or req_fixture.get("schema") != "portable-requirement-fixture/v1":
        errors.append("requirement fixture envelope is invalid")
    fixture_requirements = req_fixture.get("records", []) if isinstance(req_fixture, dict) else []
    validate_record_set(fixture_requirements, "requirement", "requirement fixture records", errors)
    if requirements and (not fixture_requirements or not strict_equal(requirements[0], fixture_requirements[0])):
        errors.append("requirement fixture is not synchronized with REQ-0001")
    if requirements and requirements[0].get("id") == "REQ-0001" and requirements[0].get("source_references") != EXPECTED_REQ0001_SOURCES:
        errors.append("REQ-0001 source references drifted from the frozen source mapping")
    if not exact_keys(dec_fixture, {"schema", "records"}, "decision fixture", errors) or dec_fixture.get("schema") != "portable-decision-fixture/v1":
        errors.append("decision fixture envelope is invalid")
    fixture_decisions = dec_fixture.get("records", []) if isinstance(dec_fixture, dict) else []
    validate_record_set(fixture_decisions, "decision", "decision fixture records", errors)
    if decisions and (not fixture_decisions or not strict_equal(decisions[0], fixture_decisions[0])):
        errors.append("decision fixture is not synchronized with DEC-0001")

    for path in pin_paths:
        try:
            pin = load_json(root, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        number = validate_pin_shape(pin, path, f"pin record {path}", errors)
        if number is not None and isinstance(pin, dict):
            pins.append((number, path, pin))
    if not pins:
        errors.append("at least one context pin is required")
    else:
        numbers = [number for number, _path, _pin in pins]
        if numbers != sorted(numbers) or len(numbers) != len(set(numbers)):
            errors.append("context pins must have unique sorted stable IDs")
        selected_number = max(numbers)
        for number, path, pin in pins:
            verify_pin_git(root, pin, path, number == selected_number, errors)
        if not strict_equal(pin_fixture, next(pin for number, _path, pin in pins if number == selected_number)):
            errors.append("context-pin fixture is not synchronized with the selected pin")

    current_paths = set(req_paths + dec_paths + pin_paths)
    validate_immutable_history(root, ownership, current_paths, errors)
    validate_accepted_main_history(root, current_paths, errors)
    validate_documents(root, errors)
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(f"portable-contract error: {error}", file=sys.stderr)
        return 1
    print("portable contracts: pass (selected pin valid and fresh for decomposition and execution)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
