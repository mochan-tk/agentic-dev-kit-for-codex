#!/usr/bin/env python3
"""Fail-closed validation for the eight repository Skills and parity record."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import posixpath
import re
import stat
import sys
import unicodedata
from datetime import date
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ".agents/skills"
PARITY_PATH = "docs/agreements/skill-parity.v1.json"
SOURCE_MANIFEST_PATH = "tests/skills/fixtures/source-manifest.v1.json"
EXPECTED_PARITY_SHA256 = "5afdf968f021d81b370bcdc3955ecf8a4155b670fe903596bd7c71b0727d54df"
MAX_FILE_BYTES = 262_144
MAX_DIRECTORY_ENTRIES = 64
MAX_LIST_ITEMS = 32
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 4096
MAX_JSON_STRING_LENGTH = 4096

REQUIRED_SKILLS = [
    "project-onboarding",
    "context-collection",
    "context-distillation",
    "plan-management",
    "task-routing",
    "session-orchestration",
    "verification",
    "retro",
]

DESCRIPTIONS = {
    "context-collection": (
        "Collect bounded source context with provenance. Use when requirements "
        "must be gathered. Do not use to approve agreements or execute implementation."
    ),
    "context-distillation": (
        "Distill pinned context into reviewable agreements. Use when evidence must "
        "become requirements or decisions. Do not use for raw collection."
    ),
    "plan-management": (
        "Maintain the canonical Issue graph and rolling plan. Use when decomposing "
        "or replanning durable work. Do not use to execute a Task."
    ),
    "project-onboarding": (
        "Assess and propose repository onboarding safely. Use when adopting or "
        "re-tuning this kit. Do not use for ordinary feature implementation."
    ),
    "retro": (
        "Convert failures into stronger controls. Use after recurrence, a material "
        "incident or rejected PR, or scheduled hygiene. Do not use for one-off repair "
        "or feedback transport."
    ),
    "session-orchestration": (
        "Coordinate durable Task attempts and recovery. Use when supervising bounded "
        "execution contexts. Do not use as a runtime identity guarantee."
    ),
    "task-routing": (
        "Recommend a bounded execution route from evidence. Use when a planned Task "
        "needs placement. Do not use to claim runtime support or dispatch."
    ),
    "verification": (
        "Verify acceptance against exact current evidence. Use when defining Verification "
        "sections, triaging CI, or judging a Task or pull request. Do not use to approve "
        "agreements or final completion."
    ),
}

REFERENCE_FILES = {
    "plan-management": "references/issue-graph-procedure.md",
    "project-onboarding": "references/onboarding-procedure.md",
    "session-orchestration": "references/orchestration-protocols.md",
}

ONBOARDING_CONTRACT_PATHS = (
    ".agents/skills/project-onboarding/SKILL.md",
    ".agents/skills/project-onboarding/references/onboarding-procedure.md",
)

ONBOARDING_CONTRACTS = {
    "ONBOARD-REMOTE-DEFAULT-GATE": (
        "Do not perform any GitHub write, including labels, Ruleset changes, "
        "or Epic creation, until the kit baseline is reachable from the remote "
        "default branch."
    ),
    "ONBOARD-COMMAND-EVIDENCE": (
        "For every candidate command, record the exact command, environment "
        "prerequisites, runtime, and result from a clean checkout."
    ),
    "ONBOARD-NO-UNRUN-PROMOTION": "Never promote an unrun command.",
    "ONBOARD-EVIDENCE-PR-BOUNDARY": (
        "Onboarding is not complete until an evidence PR exists or an exact "
        "blocked-PR receipt and creation command are durably recorded."
    ),
    "ONBOARD-DEFERRED-LEDGER": (
        "Write every unfinished or unverified item to a durable "
        "`## Deferred from onboarding` ledger in the first active Epic or "
        "evidence PR."
    ),
    "ONBOARD-CHAT-NOT-CARRIER": "Chat is not a carrier for deferred work.",
    "ONBOARD-DURABLE-HANDOFF": (
        "Replace the source Project-session step with a Codex-native durable "
        "handoff to the first approved Epic/Task frontier."
    ),
}

EXPECTED_FILES = {
    f"{SKILLS_ROOT}/{skill}/SKILL.md" for skill in REQUIRED_SKILLS
} | {
    f"{SKILLS_ROOT}/{skill}/agents/openai.yaml" for skill in REQUIRED_SKILLS
} | {
    f"{SKILLS_ROOT}/{skill}/{relative}"
    for skill, relative in REFERENCE_FILES.items()
}

EXPECTED_IMPLICIT = {skill: skill == "verification" for skill in REQUIRED_SKILLS}

REQUIRED_HEADINGS = [
    "## Inputs",
    "## Outputs and durable records",
    "## Procedure and chronology",
    "## Failure states, escalation, and human gates",
    "## Verification",
    "## Capability boundaries",
]

SOURCE_REPOSITORY = "mochan-tk/agentic-dev-kit-for-copilot"
SOURCE_COMMIT = "fd265ddef150fab86cd54d0e383c2c25fe297ffb"
SOURCE_TREE = "88f96493ec167602750c8dfec044629bd494a586"
RESEARCH_SHA256 = "55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7"

# path: (mode, blob, sha256, size, classification)
EXPECTED_SOURCE_ARTIFACTS = {
    ".github/skills/context-collection/SKILL.md": (
        "100644", "cead6452f8a7015ef2070596bde26da3e2ae2cfd",
        "2a937f40c00d32b49452b0eb08f05817aa86da97073c9d29a50906d6e50ae0eb", 3220,
        "codex-native-adaptation",
    ),
    ".github/skills/context-distillation/SKILL.md": (
        "100644", "4f2e57a7f613cdadb7c7d76306c3a04458ca7b08",
        "98e34a51a92d8a123a6fb6bd2d708751f84fffdf53848565a3d110f92ce9c785", 4748,
        "codex-native-adaptation",
    ),
    ".github/skills/plan-management/SKILL.md": (
        "100644", "4c76ec1a95516358b038f915668e01eac7f126e5",
        "c547dd2dc0e46a5b694ed31beb7db987f74b45efec2053ae8bf6737e670098ca", 13076,
        "codex-native-adaptation",
    ),
    ".github/skills/plan-management/scripts/frontier.sh": (
        "100755", "af0905cb90626001c50c2937d35ba7ea5f9d077c",
        "acb8ad8bbd9a6a15aa490c704b77c336eb06aaff16d0259aab76927beb0f5886", 3817,
        "documented-limitation",
    ),
    ".github/skills/plan-management/scripts/new-task.sh": (
        "100755", "1156b004fd554b12cdccf55bc5b62a98e3a82bda",
        "876095fb0dbd52bcef3529b1a1a67c23d30c113639326521f62f78f3316059bf", 2771,
        "documented-limitation",
    ),
    ".github/skills/plan-management/templates/epic-body.md": (
        "100644", "b01a35256b48f1c1e1c31c4d1e35822767bd5551",
        "28adc386b85e5d9a4861aede3a476606b9b826a74d08308ac69461232aa248b4", 854,
        "codex-native-adaptation",
    ),
    ".github/skills/plan-management/templates/task-body.md": (
        "100644", "2338d2e79db0afad54e498d5582b80ad63fa198f",
        "9104f12f53998e5ff86a4b1be43fae9bfbf954bcee56c53c2f35437a74d9ba12", 2266,
        "codex-native-adaptation",
    ),
    ".github/skills/project-onboarding/SKILL.md": (
        "100644", "20643ee9c8f5c3e0221db41e05b0abe3e1b22943",
        "213670b95758ade2e30ac9fcbb2aa2f114910d2176b44973658a324c26b28d29", 17895,
        "codex-native-adaptation",
    ),
    ".github/skills/retro/SKILL.md": (
        "100644", "e0f059e8b98d9692c4ae47d45c9da49a9ab711f3",
        "db359435b3443e1d5ab085222b1326f1e7d0c500ed2496f4d7b45f7d72b39cdf", 6798,
        "codex-native-adaptation",
    ),
    ".github/skills/session-orchestration/SKILL.md": (
        "100644", "d50002b5a95fef18fb651cd4fe31b459593bedb0",
        "3e4cced1d9a56ad3f1d4c58e7d471f06bd3e42f4df5969f1f0b125db22891d39", 25914,
        "codex-native-adaptation",
    ),
    ".github/skills/task-routing/SKILL.md": (
        "100644", "30a6b0123f82b15f6379a4b1e62f5c6d30c7e984",
        "252f7a12ac45dddaaa55e8b73b06e64047d0ef7196a0c17a711516087bbff100", 8552,
        "codex-native-adaptation",
    ),
    ".github/skills/verification/SKILL.md": (
        "100644", "6d0916437bf490116cefaf71e234a6f1aa3eaf6a",
        "cb310318d776263fa1a506f2f37202aa44bd77b7adb879c0cb120fed897e8fa0", 7329,
        "codex-native-adaptation",
    ),
}

SOURCE_LINE_COUNTS = {
    ".github/skills/context-collection/SKILL.md": 66,
    ".github/skills/context-distillation/SKILL.md": 80,
    ".github/skills/plan-management/SKILL.md": 237,
    ".github/skills/plan-management/scripts/frontier.sh": 102,
    ".github/skills/plan-management/scripts/new-task.sh": 72,
    ".github/skills/plan-management/templates/epic-body.md": 36,
    ".github/skills/plan-management/templates/task-body.md": 73,
    ".github/skills/project-onboarding/SKILL.md": 316,
    ".github/skills/retro/SKILL.md": 123,
    ".github/skills/session-orchestration/SKILL.md": 434,
    ".github/skills/task-routing/SKILL.md": 149,
    ".github/skills/verification/SKILL.md": 135,
}

SKILL_SOURCE_PATHS = {
    "project-onboarding": [".github/skills/project-onboarding/SKILL.md"],
    "context-collection": [".github/skills/context-collection/SKILL.md"],
    "context-distillation": [".github/skills/context-distillation/SKILL.md"],
    "plan-management": [
        ".github/skills/plan-management/SKILL.md",
        ".github/skills/plan-management/scripts/frontier.sh",
        ".github/skills/plan-management/scripts/new-task.sh",
        ".github/skills/plan-management/templates/epic-body.md",
        ".github/skills/plan-management/templates/task-body.md",
    ],
    "task-routing": [".github/skills/task-routing/SKILL.md"],
    "session-orchestration": [".github/skills/session-orchestration/SKILL.md"],
    "verification": [".github/skills/verification/SKILL.md"],
    "retro": [".github/skills/retro/SKILL.md"],
}

LIST_CATEGORIES = [
    "inputs", "outputs", "durable_records", "chronology", "ownership",
    "escalation", "verification", "runtime_dependencies",
]
EVIDENCE_KEYS = {
    "static_contract", "runtime_invocation", "implicit_selection",
    "progressive_disclosure_runtime", "cross_surface_support",
}
ALLOWED_CLASSIFICATIONS = {"codex-native-adaptation", "documented-limitation"}

EXPECTED_SOURCE_DISPOSITIONS = {
    ".github/skills/context-collection/SKILL.md": (
        [".agents/skills/context-collection/SKILL.md"], PARITY_PATH,
    ),
    ".github/skills/context-distillation/SKILL.md": (
        [".agents/skills/context-distillation/SKILL.md"], PARITY_PATH,
    ),
    ".github/skills/plan-management/SKILL.md": (
        [
            ".agents/skills/plan-management/SKILL.md",
            ".agents/skills/plan-management/references/issue-graph-procedure.md",
        ],
        PARITY_PATH,
    ),
    ".github/skills/plan-management/scripts/frontier.sh": (
        [".agents/skills/plan-management/references/issue-graph-procedure.md"],
        ".agents/skills/plan-management/references/issue-graph-procedure.md",
    ),
    ".github/skills/plan-management/scripts/new-task.sh": (
        [".agents/skills/plan-management/references/issue-graph-procedure.md"],
        ".agents/skills/plan-management/references/issue-graph-procedure.md",
    ),
    ".github/skills/plan-management/templates/epic-body.md": (
        [".github/ISSUE_TEMPLATE/epic.yml", ".github/governance/ledger-contracts.v1.json"],
        ".github/governance/ledger-contracts.v1.json",
    ),
    ".github/skills/plan-management/templates/task-body.md": (
        [".github/ISSUE_TEMPLATE/ai-task.yml", ".github/governance/ledger-contracts.v1.json"],
        ".github/governance/ledger-contracts.v1.json",
    ),
    ".github/skills/project-onboarding/SKILL.md": (
        [
            ".agents/skills/project-onboarding/SKILL.md",
            ".agents/skills/project-onboarding/references/onboarding-procedure.md",
        ],
        PARITY_PATH,
    ),
    ".github/skills/retro/SKILL.md": ([".agents/skills/retro/SKILL.md"], PARITY_PATH),
    ".github/skills/session-orchestration/SKILL.md": (
        [
            ".agents/skills/session-orchestration/SKILL.md",
            ".agents/skills/session-orchestration/references/orchestration-protocols.md",
        ],
        PARITY_PATH,
    ),
    ".github/skills/task-routing/SKILL.md": ([".agents/skills/task-routing/SKILL.md"], PARITY_PATH),
    ".github/skills/verification/SKILL.md": ([".agents/skills/verification/SKILL.md"], PARITY_PATH),
}

AFFIRMATIVE_CLAIM_PATTERNS = [
    re.compile(
        r"\b(?:K10|K11|custom[- ]agents?|hooks?|execution envelope|loop events?|"
        r"runtime adapter|installer|live (?:Task )?ritual|live runtime routing|"
        r"cross-surface (?:runtime )?support)\s+(?:is|are)(?:\s+now)?\s+"
        r"(?:implemented|supported|available|enabled|enforced|provided|guaranteed|operational|production[- ]ready)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:this Skill|T09|the repository|we)\s+"
        r"(?:implements|supports|provides|enforces|guarantees|includes)\s+(?:an?\s+)?"
        r"(?:K10|K11|custom[- ]agents?|hooks?|execution envelope|loop events?|"
        r"runtime adapter|installer|live (?:Task )?ritual|live runtime routing|"
        r"cross-surface (?:runtime )?support)\b",
        re.I,
    ),
    re.compile(r"\brepository(?:-level)?(?:\s+implementation)?\s+is\s+complete\b", re.I),
    re.compile(r"\bS-00[1-8]\s+(?:has\s+)?(?:passed|succeeded|is\s+successful)\b", re.I),
]


class DuplicateKeyError(ValueError):
    pass


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON key")
        result[key] = value
    return result


def _identity(value):
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _snapshot(value):
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _valid_relative_path(relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or unicodedata.normalize("NFC", relative) != relative
        or any(unicodedata.category(character).startswith("C") for character in relative)
    ):
        return False
    pure = PurePosixPath(relative)
    return (
        not pure.is_absolute()
        and str(pure) == relative
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def _safe_open_flags(errors):
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC")
    values = {}
    available = True
    for name in required:
        value = getattr(os, name, None)
        if not isinstance(value, int) or isinstance(value, bool) or value == 0:
            errors.append(f"safe filesystem capability is unavailable: {name}")
            available = False
        else:
            values[name] = value
    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    supports_follow = getattr(os, "supports_follow_symlinks", set())
    if os.open not in supports_dir_fd or os.stat not in supports_dir_fd:
        errors.append("safe filesystem capability is unavailable: descriptor-relative open/stat")
        available = False
    if os.stat not in supports_follow:
        errors.append("safe filesystem capability is unavailable: no-follow stat")
        available = False
    if not available:
        return None
    return {
        "directory": os.O_RDONLY | values["O_DIRECTORY"] | values["O_CLOEXEC"] | values["O_NOFOLLOW"],
        "file": os.O_RDONLY | values["O_CLOEXEC"] | values["O_NONBLOCK"] | values["O_NOFOLLOW"],
    }


def _open_directory_chain(root, relative, errors):
    """Return open directory chain, or None. Caller closes every fd."""
    if not _valid_relative_path(relative):
        errors.append(f"unsafe repository path: {relative!r}")
        return None
    safe_flags = _safe_open_flags(errors)
    if safe_flags is None:
        return None
    flags = safe_flags["directory"]
    chain = []
    try:
        root_path = os.fspath(root)
        observed_root = os.lstat(root_path)
        if stat.S_ISLNK(observed_root.st_mode):
            raise OSError(errno.ELOOP, "repository root is a symlink", root_path)
        if not stat.S_ISDIR(observed_root.st_mode):
            raise OSError(errno.ENOTDIR, "repository root is not a directory", root_path)
        root_fd = os.open(root_path, flags)
        actual_root = os.fstat(root_fd)
        if _identity(observed_root) != _identity(actual_root):
            os.close(root_fd)
            raise OSError(errno.ESTALE, "repository root binding changed", root_path)
        chain.append((root_fd, None, root_path, actual_root))
        parent_fd = root_fd
        for part in PurePosixPath(relative).parts:
            observed = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(observed.st_mode):
                raise OSError(errno.ELOOP, "symlink directory component", part)
            if not stat.S_ISDIR(observed.st_mode):
                raise OSError(errno.ENOTDIR, "non-directory component", part)
            child_fd = os.open(part, flags, dir_fd=parent_fd)
            actual = os.fstat(child_fd)
            if _identity(observed) != _identity(actual):
                os.close(child_fd)
                raise OSError(errno.ESTALE, "directory binding changed", part)
            chain.append((child_fd, parent_fd, part, actual))
            parent_fd = child_fd
        return chain
    except (OSError, ValueError, TypeError, NotImplementedError) as exc:
        errors.append(f"cannot open directory {relative}: {exc}")
        for fd, _, _, _ in reversed(chain):
            try:
                os.close(fd)
            except OSError:
                pass
        return None


def _verify_directory_chain(chain, label, errors):
    okay = True
    for index in range(len(chain)):
        fd, parent_fd, name, before = chain[index]
        try:
            held = os.fstat(fd)
            if parent_fd is None:
                rebound = os.lstat(name)
            else:
                rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except (OSError, ValueError, TypeError, NotImplementedError) as exc:
            errors.append(f"directory binding became uncheckable for {label}: {exc}")
            okay = False
            continue
        if _identity(held) != _identity(before) or _identity(rebound) != _identity(before):
            errors.append(f"directory namespace binding changed while reading {label}")
            okay = False
    return okay


def enumerate_directory(root, relative, errors, max_entries=MAX_DIRECTORY_ENTRIES):
    chain = _open_directory_chain(root, relative, errors)
    if chain is None:
        return None
    directory_fd = chain[-1][0]
    entries = []
    try:
        before = os.fstat(directory_fd)
        with os.scandir(directory_fd) as iterator:
            count = 0
            while True:
                try:
                    entry = next(iterator)
                except StopIteration:
                    break
                count += 1
                if count > max_entries:
                    errors.append(f"directory {relative} exceeds {max_entries} entries")
                    break
                try:
                    observed = entry.stat(follow_symlinks=False)
                except (OSError, ValueError, TypeError, NotImplementedError) as exc:
                    errors.append(f"cannot inspect {relative}/{entry.name}: {exc}")
                    continue
                entries.append((entry.name, observed))
        after = os.fstat(directory_fd)
        if _snapshot(before) != _snapshot(after):
            errors.append(f"directory contents changed while enumerating {relative}")
        if not _verify_directory_chain(chain, relative, errors):
            return None
        return entries
    except (OSError, ValueError, TypeError, NotImplementedError) as exc:
        errors.append(f"cannot enumerate {relative}: {exc}")
        return None
    finally:
        for fd, _, _, _ in reversed(chain):
            try:
                os.close(fd)
            except OSError:
                pass


def read_regular_file(root, relative, errors, limit=MAX_FILE_BYTES):
    if not _valid_relative_path(relative):
        errors.append(f"unsafe repository path: {relative!r}")
        return None
    pure = PurePosixPath(relative)
    parent = str(pure.parent)
    if parent == ".":
        errors.append(f"top-level reads are not allowed by Skill checker: {relative}")
        return None
    chain = _open_directory_chain(root, parent, errors)
    if chain is None:
        return None
    parent_fd = chain[-1][0]
    file_fd = None
    try:
        safe_flags = _safe_open_flags(errors)
        if safe_flags is None:
            return None
        observed = os.stat(pure.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(observed.st_mode):
            errors.append(f"governed input is not a regular file: {relative}")
            return None
        if observed.st_size > limit:
            errors.append(f"governed input exceeds {limit} bytes: {relative}")
            return None
        file_fd = os.open(pure.name, safe_flags["file"], dir_fd=parent_fd)
        opened = os.fstat(file_fd)
        if _identity(observed) != _identity(opened):
            errors.append(f"file binding changed before read: {relative}")
            return None
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > limit:
            errors.append(f"governed input exceeds {limit} bytes: {relative}")
            return None
        final = os.fstat(file_fd)
        rebound = os.stat(pure.name, dir_fd=parent_fd, follow_symlinks=False)
        if _snapshot(opened) != _snapshot(final) or _identity(opened) != _identity(rebound):
            errors.append(f"file binding changed during read: {relative}")
            return None
        if not _verify_directory_chain(chain, relative, errors):
            return None
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            errors.append(f"governed input is not UTF-8: {relative}: {exc}")
            return None
        if "\x00" in text:
            errors.append(f"governed input contains NUL: {relative}")
            return None
        return text
    except (OSError, ValueError, TypeError, NotImplementedError) as exc:
        errors.append(f"cannot read governed input {relative}: {exc}")
        return None
    finally:
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                pass
        for fd, _, _, _ in reversed(chain):
            try:
                os.close(fd)
            except OSError:
                pass


def parse_json(root, relative, errors):
    text = read_regular_file(root, relative, errors)
    if text is None:
        return None, None
    try:
        value = json.loads(text, object_pairs_hook=_pairs_without_duplicates)
    except RecursionError:
        errors.append(f"invalid JSON in {relative}: parser recursion limit exceeded")
        return None, text
    except (json.JSONDecodeError, DuplicateKeyError, ValueError) as exc:
        errors.append(f"invalid JSON in {relative}: {exc}")
        return None, text
    if not validate_json_bounds(value, relative, errors):
        return None, text
    return value, text


def validate_json_bounds(value, relative, errors):
    """Validate parsed JSON iteratively with root depth one and bounded work."""
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            errors.append(f"JSON depth exceeds {MAX_JSON_DEPTH} in {relative}")
            return False
        nodes += 1
        if nodes > MAX_JSON_NODES:
            errors.append(f"JSON node count exceeds {MAX_JSON_NODES} in {relative}")
            return False
        if isinstance(current, str) and len(current) > MAX_JSON_STRING_LENGTH:
            errors.append(f"JSON string length exceeds {MAX_JSON_STRING_LENGTH} in {relative}")
            return False

        if isinstance(current, dict):
            child_count = len(current) * 2
        elif isinstance(current, list):
            child_count = len(current)
        else:
            child_count = 0
        if child_count == 0:
            continue

        child_depth = depth + 1
        if child_depth > MAX_JSON_DEPTH:
            errors.append(f"JSON depth exceeds {MAX_JSON_DEPTH} in {relative}")
            return False
        if nodes + len(stack) + child_count > MAX_JSON_NODES:
            errors.append(f"JSON node count exceeds {MAX_JSON_NODES} in {relative}")
            return False
        if isinstance(current, dict):
            for key, child in current.items():
                stack.append((child, child_depth))
                stack.append((key, child_depth))
        else:
            stack.extend((child, child_depth) for child in reversed(current))
    return True


def _check_exact_keys(value, expected, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != set(expected):
        errors.append(f"{label} keys must be exactly {sorted(expected)}; got {sorted(actual)}")
        return False
    return True


def _check_string_list(value, label, errors, *, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > MAX_LIST_ITEMS:
        errors.append(f"{label} must be a bounded {'possibly empty ' if allow_empty else 'non-empty '}array")
        return False
    okay = True
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or len(item) > 500:
            errors.append(f"{label}[{index}] must be a non-empty bounded string")
            okay = False
    return okay


def _collision_errors(paths):
    errors = []
    seen = {}
    for path in paths:
        normalized = unicodedata.normalize("NFC", path)
        key = normalized.casefold()
        previous = seen.get(key)
        if previous is not None and previous != path:
            errors.append(f"case or Unicode-normalization path collision: {previous} <> {path}")
        else:
            seen[key] = path
        if normalized != path:
            errors.append(f"path is not NFC-normalized: {path}")
    return errors


def inventory_skill_files(root, errors):
    discovered = []
    top = enumerate_directory(root, SKILLS_ROOT, errors)
    if top is None:
        return discovered
    top_names = []
    for name, observed in top:
        top_names.append(name)
        if not stat.S_ISDIR(observed.st_mode):
            errors.append(f"Skill root entry is not a directory: {SKILLS_ROOT}/{name}")
    if set(top_names) != set(REQUIRED_SKILLS) or len(top_names) != len(REQUIRED_SKILLS):
        errors.append(f"Skill roots must be exactly {REQUIRED_SKILLS}; got {sorted(top_names)}")

    for skill in REQUIRED_SKILLS:
        skill_dir = f"{SKILLS_ROOT}/{skill}"
        entries = enumerate_directory(root, skill_dir, errors)
        if entries is None:
            continue
        expected_names = {"SKILL.md", "agents"}
        if skill in REFERENCE_FILES:
            expected_names.add("references")
        names = {name for name, _ in entries}
        if names != expected_names or len(entries) != len(expected_names):
            errors.append(f"{skill_dir} entries must be exactly {sorted(expected_names)}; got {sorted(names)}")
        for name, observed in entries:
            relative = f"{skill_dir}/{name}"
            if name == "SKILL.md":
                if not stat.S_ISREG(observed.st_mode):
                    errors.append(f"governed Skill file is not regular: {relative}")
                elif stat.S_IMODE(observed.st_mode) & 0o111:
                    errors.append(f"governed Skill file must not be executable: {relative}")
                discovered.append(relative)
            elif name in {"agents", "references"} and not stat.S_ISDIR(observed.st_mode):
                errors.append(f"governed Skill component is not a directory: {relative}")

        agents_dir = f"{skill_dir}/agents"
        agent_entries = enumerate_directory(root, agents_dir, errors)
        if agent_entries is not None:
            names = {name for name, _ in agent_entries}
            if names != {"openai.yaml"} or len(agent_entries) != 1:
                errors.append(f"{agents_dir} must contain only openai.yaml")
            for name, observed in agent_entries:
                relative = f"{agents_dir}/{name}"
                if not stat.S_ISREG(observed.st_mode):
                    errors.append(f"governed Skill metadata is not regular: {relative}")
                elif stat.S_IMODE(observed.st_mode) & 0o111:
                    errors.append(f"governed Skill metadata must not be executable: {relative}")
                discovered.append(relative)

        if skill in REFERENCE_FILES:
            reference_dir = f"{skill_dir}/references"
            reference_entries = enumerate_directory(root, reference_dir, errors)
            expected_reference = PurePosixPath(REFERENCE_FILES[skill]).name
            if reference_entries is not None:
                names = {name for name, _ in reference_entries}
                if names != {expected_reference} or len(reference_entries) != 1:
                    errors.append(f"{reference_dir} must contain only {expected_reference}")
                for name, observed in reference_entries:
                    relative = f"{reference_dir}/{name}"
                    if not stat.S_ISREG(observed.st_mode):
                        errors.append(f"governed Skill resource is not regular: {relative}")
                    elif stat.S_IMODE(observed.st_mode) & 0o111:
                        errors.append(f"governed Skill resource must not be executable: {relative}")
                    discovered.append(relative)

    errors.extend(_collision_errors(discovered))
    if set(discovered) != EXPECTED_FILES or len(discovered) != len(EXPECTED_FILES):
        errors.append(
            "Skill file inventory mismatch; missing="
            f"{sorted(EXPECTED_FILES - set(discovered))}, extra={sorted(set(discovered) - EXPECTED_FILES)}"
        )
    return discovered


def parse_frontmatter(text, relative, errors):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        errors.append(f"{relative} must begin with YAML frontmatter")
        return None, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        errors.append(f"{relative} has unterminated frontmatter")
        return None, text
    pairs = {}
    for number, line in enumerate(lines[1:end], start=2):
        if ":" not in line:
            errors.append(f"{relative}:{number} malformed frontmatter line")
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key in pairs:
            errors.append(f"{relative} duplicate frontmatter key: {key}")
        else:
            pairs[key] = value
    _check_exact_keys(pairs, {"name", "description"}, f"{relative} frontmatter", errors)
    return pairs, "\n".join(lines[end + 1 :]) + ("\n" if text.endswith("\n") else "")


def parse_openai_yaml(text, skill, relative, errors):
    pattern = re.compile(
        r'\Ainterface:\n'
        r'  display_name: ("(?:[^"\\]|\\.)*")\n'
        r'  short_description: ("(?:[^"\\]|\\.)*")\n'
        r'  default_prompt: ("(?:[^"\\]|\\.)*")\n'
        r'policy:\n'
        r'  allow_implicit_invocation: (true|false)\n\Z'
    )
    match = pattern.fullmatch(text)
    if match is None:
        errors.append(f"{relative} must use the exact closed interface and policy shape with quoted strings")
        return None
    try:
        display_name, short_description, default_prompt = [json.loads(value) for value in match.group(1, 2, 3)]
    except json.JSONDecodeError as exc:
        errors.append(f"{relative} contains invalid quoted metadata: {exc}")
        return None
    implicit = match.group(4) == "true"
    for field, value in (
        ("display_name", display_name),
        ("short_description", short_description),
        ("default_prompt", default_prompt),
    ):
        if (
            unicodedata.normalize("NFC", value) != value
            or any(unicodedata.category(character).startswith("C") for character in value)
        ):
            errors.append(f"{relative} {field} must be NFC-normalized and control-free")
    if display_name != display_name.strip() or not 1 <= len(display_name) <= 64:
        errors.append(f"{relative} display_name must be trimmed and contain 1 through 64 characters")
    if short_description != short_description.strip() or not 25 <= len(short_description) <= 64:
        errors.append(f"{relative} short_description must be trimmed and contain 25 through 64 characters")
    if default_prompt != default_prompt.strip() or len(default_prompt) > 256:
        errors.append(f"{relative} default_prompt must be trimmed and no longer than 256 characters")
    if not default_prompt.startswith(f"Use ${skill} "):
        errors.append(f"{relative} default_prompt must begin 'Use ${skill} '")
    if implicit is not EXPECTED_IMPLICIT[skill]:
        errors.append(f"{relative} allow_implicit_invocation must be {str(EXPECTED_IMPLICIT[skill]).lower()}")
    return {
        "display_name": display_name,
        "short_description": short_description,
        "default_prompt": default_prompt,
        "allow_implicit_invocation": implicit,
    }


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _visible_markdown_lines(text):
    visible_lines = []
    in_comment = False
    block_comment = False
    fence = None
    raw_html_end = None
    html_until_blank = False
    block_tags = (
        "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
        "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
        "footer|form|frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|"
        "iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|"
        "option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|"
        "title|tr|track|ul"
    )
    for raw_line in text.splitlines():
        if fence is not None:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{fence[1]},}}[ \t]*", raw_line):
                fence = None
            continue
        if raw_html_end is not None:
            if re.search(raw_html_end, raw_line, re.I):
                raw_html_end = None
            continue
        if html_until_blank:
            if not raw_line.strip():
                html_until_blank = False
                visible_lines.append("")
            continue
        if block_comment:
            if "-->" in raw_line:
                block_comment = False
            continue
        if re.match(r"^ {0,3}<!--", raw_line):
            if "-->" not in raw_line:
                block_comment = True
            continue
        if in_comment:
            if "-->" in raw_line:
                in_comment = False
            continue
        line = raw_line
        visible = []
        cursor = 0
        while cursor < len(line):
            if in_comment:
                end = line.find("-->", cursor)
                if end < 0:
                    cursor = len(line)
                    break
                in_comment = False
                cursor = end + 3
                continue
            start = line.find("<!--", cursor)
            if start < 0:
                visible.append(line[cursor:])
                break
            visible.append(line[cursor:start])
            cursor = start + 4
            in_comment = True
        line = "".join(visible)
        opening = re.match(r"^ {0,3}(`{3,})[^`]*$", line)
        if opening is None:
            opening = re.match(r"^ {0,3}(~{3,}).*$", line)
        if opening is not None:
            marker = opening.group(1)
            fence = (marker[0], len(marker))
            continue
        container = re.match(r"^ {0,3}<(pre|script|style|textarea)(?:\s|>|$)", line, re.I)
        if container is not None:
            raw_html_end = rf"</{re.escape(container.group(1))}\s*>"
            if re.search(raw_html_end, line, re.I):
                raw_html_end = None
            continue
        if re.match(r"^ {0,3}<\?", line):
            raw_html_end = r"\?>"
            if "?>" in line:
                raw_html_end = None
            continue
        if re.match(r"^ {0,3}<!\[CDATA\[", line, re.I):
            raw_html_end = r"\]\]>"
            if "]]>" in line:
                raw_html_end = None
            continue
        if re.match(r"^ {0,3}<![A-Z]", line):
            raw_html_end = r">"
            if ">" in line:
                raw_html_end = None
            continue
        if re.match(rf"^ {{0,3}}</?(?:{block_tags})(?:\s|/?>|$)", line, re.I):
            html_until_blank = True
            continue
        if re.match(r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>[ \t]*$", line):
            html_until_blank = True
            continue
        visible_lines.append(line)
    return visible_lines


def validate_onboarding_contracts(texts, errors):
    """Require each onboarding contract in both reviewed visible Markdown files."""
    for relative in ONBOARDING_CONTRACT_PATHS:
        text = texts.get(relative)
        if not isinstance(text, str):
            for contract_id in ONBOARDING_CONTRACTS:
                errors.append(f"missing {contract_id} in {relative}")
            continue
        visible = " ".join(
            line.strip()
            for line in _visible_markdown_lines(text)
            if line.strip()
        )
        for contract_id, marker in ONBOARDING_CONTRACTS.items():
            if marker not in visible:
                errors.append(f"missing {contract_id} in {relative}")


def _markdown_anchors(text):
    anchors = set()
    occurrences = {}
    for line in _visible_markdown_lines(text):
        match = re.fullmatch(r"#{1,6}\s+(.+?)\s*#*", line)
        if match is None:
            continue
        title = match.group(1).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug)
        count = occurrences.get(slug, 0)
        occurrences[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def validate_markdown_links(root, skill, relative, text, errors):
    linked = set()
    skill_root = f"{SKILLS_ROOT}/{skill}"
    for target in MARKDOWN_LINK.findall(text):
        target = target.strip()
        if not target:
            continue
        if (
            target.startswith("/")
            or "\\" in target
            or "%" in target
            or target.lower().startswith("file:")
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
        ):
            errors.append(f"unsafe or non-repository Markdown resource in {relative}: {target}")
            continue
        path_part, separator, fragment = target.partition("#")
        if not path_part:
            if not separator or not fragment or fragment not in _markdown_anchors(text):
                errors.append(f"unresolved Markdown fragment in {relative}: {target}")
            continue
        if not _valid_relative_path(path_part):
            errors.append(f"noncanonical Markdown resource in {relative}: {target}")
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), path_part))
        if not _valid_relative_path(resolved) or not resolved.startswith(skill_root + "/"):
            errors.append(f"Markdown resource escapes Skill root in {relative}: {target}")
            continue
        if unicodedata.normalize("NFC", resolved) != resolved:
            errors.append(f"Markdown resource is not NFC-normalized in {relative}: {target}")
        if resolved not in EXPECTED_FILES:
            errors.append(f"dangling or case-mismatched Skill resource in {relative}: {target}")
            continue
        payload = read_regular_file(root, resolved, errors)
        if payload is not None:
            if separator and (not fragment or fragment not in _markdown_anchors(payload)):
                errors.append(f"unresolved Markdown fragment in {relative}: {target}")
            linked.add(resolved)
    return linked


def validate_skills(root, errors):
    inventory_skill_files(root, errors)
    names = []
    descriptions = []
    display_names = []
    short_descriptions = []
    default_prompts = []
    all_text = []
    for skill in REQUIRED_SKILLS:
        skill_path = f"{SKILLS_ROOT}/{skill}/SKILL.md"
        text = read_regular_file(root, skill_path, errors)
        if text is None:
            continue
        all_text.append((skill_path, text))
        frontmatter, body = parse_frontmatter(text, skill_path, errors)
        if isinstance(frontmatter, dict):
            name = frontmatter.get("name")
            description = frontmatter.get("description")
            if name != skill:
                errors.append(f"{skill_path} frontmatter name must equal directory name {skill}")
            if isinstance(name, str):
                names.append(name)
            if description != DESCRIPTIONS[skill]:
                errors.append(f"{skill_path} description must match the reviewed discriminating boundary")
            if isinstance(description, str):
                descriptions.append(description)
        body_lines = _visible_markdown_lines(body)
        positions = []
        for heading in REQUIRED_HEADINGS:
            count = body_lines.count(heading)
            if count != 1:
                errors.append(f"{skill_path} must contain heading exactly once: {heading}")
                positions.append(-1)
            else:
                positions.append(body_lines.index(heading))
        if all(position >= 0 for position in positions) and positions != sorted(positions):
            errors.append(f"{skill_path} required procedural headings are out of order")
        linked = validate_markdown_links(root, skill, skill_path, body, errors)
        expected_reference = REFERENCE_FILES.get(skill)
        if expected_reference:
            expected_path = f"{SKILLS_ROOT}/{skill}/{expected_reference}"
            if expected_path not in linked:
                errors.append(f"{skill_path} must link its progressive-disclosure resource {expected_reference}")
            reference_text = read_regular_file(root, expected_path, errors)
            if reference_text is not None:
                all_text.append((expected_path, reference_text))
                validate_markdown_links(root, skill, expected_path, reference_text, errors)
        elif linked:
            errors.append(f"{skill_path} declares an unexpected local resource")

        openai_path = f"{SKILLS_ROOT}/{skill}/agents/openai.yaml"
        openai_text = read_regular_file(root, openai_path, errors)
        if openai_text is not None:
            all_text.append((openai_path, openai_text))
            metadata = parse_openai_yaml(openai_text, skill, openai_path, errors)
            if metadata is not None:
                display_names.append(metadata["display_name"])
                short_descriptions.append(metadata["short_description"])
                default_prompts.append(metadata["default_prompt"])

    if len(names) != len(REQUIRED_SKILLS) or len(set(names)) != len(REQUIRED_SKILLS):
        errors.append("Skill frontmatter names must be present and unique")
    if len(descriptions) != len(REQUIRED_SKILLS) or len(set(descriptions)) != len(REQUIRED_SKILLS):
        errors.append("Skill descriptions must be present and unique")
    for label, values in (
        ("display names", display_names),
        ("short descriptions", short_descriptions),
        ("default prompts", default_prompts),
    ):
        canonical = [unicodedata.normalize("NFC", value).casefold() for value in values]
        if len(values) != len(REQUIRED_SKILLS) or len(set(canonical)) != len(REQUIRED_SKILLS):
            errors.append(f"Skill UI {label} must be present and unique by NFC casefold")
    validate_onboarding_contracts(dict(all_text), errors)
    return all_text


def validate_source_manifest(root, errors):
    manifest, text = parse_json(root, SOURCE_MANIFEST_PATH, errors)
    if not isinstance(manifest, dict):
        return None, text
    if not _check_exact_keys(manifest, {"schema", "source", "research_pack", "artifacts"}, "source manifest", errors):
        return manifest, text
    if manifest.get("schema") != "skill-source-manifest/v1":
        errors.append("source manifest schema must be skill-source-manifest/v1")
    source = manifest.get("source")
    if _check_exact_keys(source, {"repository", "commit", "tree"}, "source manifest source", errors):
        if source != {"repository": SOURCE_REPOSITORY, "commit": SOURCE_COMMIT, "tree": SOURCE_TREE}:
            errors.append("frozen source repository commit or tree drifted")
    research = manifest.get("research_pack")
    if _check_exact_keys(research, {"archive", "sha256"}, "source manifest research_pack", errors):
        if research.get("archive") != "agentic-dev-kit-codex-research-pack.zip" or research.get("sha256") != RESEARCH_SHA256:
            errors.append("research-pack provenance drifted")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 12:
        errors.append("source manifest must contain exactly 12 artifacts")
        return manifest, text
    paths = []
    for index, artifact in enumerate(artifacts):
        label = f"source artifact[{index}]"
        expected_keys = {"path", "mode", "blob", "sha256", "size", "classification", "target_paths", "evidence_path"}
        if not _check_exact_keys(artifact, expected_keys, label, errors):
            continue
        path = artifact.get("path")
        if not isinstance(path, str):
            errors.append(f"{label} path must be a string")
            continue
        paths.append(path)
        expected = EXPECTED_SOURCE_ARTIFACTS.get(path)
        if expected is None:
            errors.append(f"unexpected frozen source artifact: {path}")
            continue
        actual = (artifact.get("mode"), artifact.get("blob"), artifact.get("sha256"), artifact.get("size"), artifact.get("classification"))
        if actual != expected:
            errors.append(f"frozen source artifact metadata drifted: {path}")
        _check_string_list(artifact.get("target_paths"), f"{label}.target_paths", errors)
        for target in artifact.get("target_paths", []) if isinstance(artifact.get("target_paths"), list) else []:
            if not _valid_relative_path(target):
                errors.append(f"unsafe target path for frozen artifact {path}: {target!r}")
        evidence_path = artifact.get("evidence_path")
        if not _valid_relative_path(evidence_path):
            errors.append(f"unsafe evidence path for frozen artifact {path}")
        expected_targets, expected_evidence = EXPECTED_SOURCE_DISPOSITIONS[path]
        if artifact.get("target_paths") != expected_targets:
            errors.append(f"frozen source artifact target disposition drifted: {path}")
        if evidence_path != expected_evidence:
            errors.append(f"frozen source artifact evidence disposition drifted: {path}")
        for target in expected_targets:
            if read_regular_file(root, target, errors) is None:
                errors.append(f"frozen source artifact target is not readable: {target}")
        if read_regular_file(root, expected_evidence, errors) is None:
            errors.append(f"frozen source artifact evidence is not readable: {expected_evidence}")
    if paths != sorted(EXPECTED_SOURCE_ARTIFACTS) or len(set(paths)) != 12:
        errors.append("frozen source artifacts must be unique, complete, and path-sorted")
    return manifest, text


def validate_invocation_evidence(value, errors):
    if not isinstance(value, list) or len(value) > 32:
        errors.append("explicit_invocation_evidence must be a bounded array")
        return
    required = {
        "skill",
        "codex_client_or_surface",
        "client_version",
        "date",
        "repository_commit",
        "invocation_prompt",
        "observed_result",
        "limitations",
    }
    for index, item in enumerate(value):
        label = f"explicit_invocation_evidence[{index}]"
        if not _check_exact_keys(item, required, label, errors):
            continue
        for key in required:
            field = item.get(key)
            if (
                not isinstance(field, str)
                or not field.strip()
                or field != field.strip()
                or len(field) > 500
                or unicodedata.normalize("NFC", field) != field
                or any(unicodedata.category(character).startswith("C") for character in field)
            ):
                errors.append(f"{label}.{key} must be a non-empty bounded NFC control-free string")
        if item.get("skill") not in REQUIRED_SKILLS:
            errors.append(f"{label}.skill is not a required Skill")
        skill = item.get("skill")
        prompt = item.get("invocation_prompt")
        if (
            isinstance(skill, str)
            and skill in REQUIRED_SKILLS
            and isinstance(prompt, str)
            and re.search(
                rf"(?<![A-Za-z0-9_-])\${re.escape(skill)}(?![A-Za-z0-9_-])",
                prompt,
            )
            is None
        ):
            errors.append(f"{label}.invocation_prompt must contain the exact ${skill} token")
        commit = item.get("repository_commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            errors.append(f"{label}.repository_commit must be an exact commit")
        observed_date = item.get("date")
        if not isinstance(observed_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed_date):
            errors.append(f"{label}.date must be YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(observed_date)
            except ValueError:
                errors.append(f"{label}.date must be a real calendar date")
        result = item.get("observed_result")
        if not isinstance(result, str) or result not in {"observed", "not-observed", "unavailable"}:
            errors.append(f"{label}.observed_result is invalid")


def validate_source_anchor(anchor, allowed_paths, label, errors):
    if not isinstance(anchor, str):
        errors.append(f"{label}.source_anchor must be a string")
        return None
    path, separator, fragment = anchor.partition("#")
    if path not in allowed_paths:
        errors.append(f"{label}.source_anchor is not in this Skill's frozen sources")
        return None
    if not separator:
        if path.endswith("/SKILL.md"):
            errors.append(f"{label}.source_anchor must bind exact frozen source lines")
            return None
        return path
    match = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", fragment)
    if match is None:
        errors.append(f"{label}.source_anchor has an unresolved frozen-source fragment")
        return None
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    if start > end or end > SOURCE_LINE_COUNTS[path]:
        errors.append(f"{label}.source_anchor line range is outside the frozen source")
        return None
    return path


def validate_parity(root, source_manifest_text, errors):
    parity, parity_text = parse_json(root, PARITY_PATH, errors)
    if (
        parity_text is not None
        and hashlib.sha256(parity_text.encode("utf-8")).hexdigest()
        != EXPECTED_PARITY_SHA256
    ):
        errors.append("reviewed skill parity digest drifted")
    if not isinstance(parity, dict):
        return parity_text
    top_keys = {
        "schema", "source_manifest", "target", "skills", "contract_effects",
        "scenario_evidence", "explicit_invocation_evidence", "results",
        "release_blocked", "repository_completion",
    }
    if not _check_exact_keys(parity, top_keys, "skill parity", errors):
        return parity_text
    if parity.get("schema") != "skill-parity/v1":
        errors.append("skill parity schema must be skill-parity/v1")
    binding = parity.get("source_manifest")
    if _check_exact_keys(binding, {"path", "sha256"}, "skill parity source_manifest", errors):
        if binding.get("path") != SOURCE_MANIFEST_PATH:
            errors.append("skill parity source manifest path drifted")
        if source_manifest_text is not None:
            digest = hashlib.sha256(source_manifest_text.encode("utf-8")).hexdigest()
            if binding.get("sha256") != digest:
                errors.append("skill parity source manifest digest drifted")
    target = parity.get("target")
    expected_target = {
        "repository": "mochan-tk/agentic-dev-kit-for-codex",
        "task": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/11",
        "base_commit": "539c01822c005e639438331e70c592891e136430",
        "base_tree": "f006ed8963d600a2a9bbf1b3917dc57e6f6a41d8",
    }
    if _check_exact_keys(target, expected_target, "skill parity target", errors) and target != expected_target:
        errors.append("skill parity target binding drifted")

    rows = parity.get("skills")
    if not isinstance(rows, list) or len(rows) != 8:
        errors.append("skill parity must contain exactly eight rows")
        rows = []
    row_ids = []
    accounted_sources = []
    adaptation_ids = set()
    row_keys = {
        "id", "source_artifacts", "target_files", "trigger", *LIST_CATEGORIES,
        "adaptations", "evidence_status",
    }
    for index, row in enumerate(rows):
        label = f"skill parity row[{index}]"
        if not _check_exact_keys(row, row_keys, label, errors):
            continue
        skill = row.get("id")
        if not isinstance(skill, str) or skill not in REQUIRED_SKILLS:
            errors.append(f"{label}.id is invalid")
            continue
        row_ids.append(skill)
        expected_source_artifacts = [
            {"path": path, "blob": EXPECTED_SOURCE_ARTIFACTS[path][1]}
            for path in SKILL_SOURCE_PATHS[skill]
        ]
        source_artifacts = row.get("source_artifacts")
        if not isinstance(source_artifacts, list):
            errors.append(f"{label}.source_artifacts must be an exact ordered array")
            source_artifacts = []
        for source_index, artifact in enumerate(source_artifacts):
            source_label = f"{label}.source_artifacts[{source_index}]"
            if not _check_exact_keys(artifact, {"path", "blob"}, source_label, errors):
                continue
            path = artifact.get("path")
            blob = artifact.get("blob")
            if not isinstance(path, str) or not _valid_relative_path(path):
                errors.append(f"{source_label}.path must be a safe repository-relative path")
            else:
                accounted_sources.append(path)
            if not isinstance(blob, str) or not re.fullmatch(r"[0-9a-f]{40}", blob):
                errors.append(f"{source_label}.blob must be an exact frozen blob")
        if source_artifacts != expected_source_artifacts:
            errors.append(f"{label}.source_artifacts path/blob bindings drifted omitted duplicated or reordered")

        target_files = row.get("target_files")
        expected_targets = {
            f"{SKILLS_ROOT}/{skill}/SKILL.md",
            f"{SKILLS_ROOT}/{skill}/agents/openai.yaml",
        }
        if skill in REFERENCE_FILES:
            expected_targets.add(f"{SKILLS_ROOT}/{skill}/{REFERENCE_FILES[skill]}")
        observed_targets = []
        if not isinstance(target_files, list) or len(target_files) != len(expected_targets):
            errors.append(f"{label}.target_files must bind the exact reviewed Skill files")
            target_files = []
        for file_index, target_file in enumerate(target_files):
            target_label = f"{label}.target_files[{file_index}]"
            if not _check_exact_keys(target_file, {"path", "sha256"}, target_label, errors):
                continue
            path = target_file.get("path")
            digest = target_file.get("sha256")
            if not isinstance(path, str) or path not in expected_targets:
                errors.append(f"{target_label}.path is unexpected")
                continue
            observed_targets.append(path)
            text = read_regular_file(root, path, errors)
            if text is not None and digest != hashlib.sha256(text.encode("utf-8")).hexdigest():
                errors.append(f"target Skill digest drifted: {path}")
        if observed_targets != sorted(expected_targets):
            errors.append(f"{label}.target_files must be unique and path-sorted")

        trigger = row.get("trigger")
        if _check_exact_keys(trigger, {"use_when", "do_not_use", "allow_implicit_invocation"}, f"{label}.trigger", errors):
            if not isinstance(trigger.get("use_when"), str) or not trigger["use_when"].strip():
                errors.append(f"{label}.trigger.use_when must be non-empty")
            if not isinstance(trigger.get("do_not_use"), str) or not trigger["do_not_use"].strip():
                errors.append(f"{label}.trigger.do_not_use must be non-empty")
            if type(trigger.get("allow_implicit_invocation")) is not bool or trigger["allow_implicit_invocation"] is not EXPECTED_IMPLICIT[skill]:
                errors.append(f"{label}.trigger implicit policy drifted")
        for category in LIST_CATEGORIES:
            _check_string_list(row.get(category), f"{label}.{category}", errors)

        adaptations = row.get("adaptations")
        if not isinstance(adaptations, list) or not adaptations or len(adaptations) > 16:
            errors.append(f"{label}.adaptations must be a bounded non-empty array")
            adaptations = []
        anchored = set()
        for adaptation_index, adaptation in enumerate(adaptations):
            adaptation_label = f"{label}.adaptations[{adaptation_index}]"
            keys = {"id", "classification", "source_anchor", "target_behavior", "rationale", "evidence_path"}
            if not _check_exact_keys(adaptation, keys, adaptation_label, errors):
                continue
            identifier = adaptation.get("id")
            if not isinstance(identifier, str) or not re.fullmatch(r"(?:ADAPT|LIMIT)-[A-Z]+-[0-9]{3}", identifier):
                errors.append(f"{adaptation_label}.id is invalid")
            elif identifier in adaptation_ids:
                errors.append(f"duplicate semantic-change id: {identifier}")
            else:
                adaptation_ids.add(identifier)
            classification = adaptation.get("classification")
            if not isinstance(classification, str) or classification not in ALLOWED_CLASSIFICATIONS:
                errors.append(f"{adaptation_label}.classification is not authorized")
            anchor_path = validate_source_anchor(
                adaptation.get("source_anchor"),
                SKILL_SOURCE_PATHS[skill],
                adaptation_label,
                errors,
            )
            if anchor_path is not None:
                anchored.add(anchor_path)
            for field in ("target_behavior", "rationale"):
                if not isinstance(adaptation.get(field), str) or not adaptation[field].strip():
                    errors.append(f"{adaptation_label}.{field} must be non-empty")
            evidence_path = adaptation.get("evidence_path")
            if not _valid_relative_path(evidence_path):
                errors.append(f"{adaptation_label}.evidence_path is unsafe")
            elif read_regular_file(root, evidence_path, errors) is None:
                errors.append(f"{adaptation_label}.evidence_path is not readable")
        if set(SKILL_SOURCE_PATHS[skill]) - anchored:
            errors.append(f"{label} has unclassified source semantic changes: {sorted(set(SKILL_SOURCE_PATHS[skill]) - anchored)}")

        evidence = row.get("evidence_status")
        if _check_exact_keys(evidence, EVIDENCE_KEYS, f"{label}.evidence_status", errors):
            expected_evidence = {key: "not-run" for key in EVIDENCE_KEYS}
            expected_evidence["static_contract"] = "present"
            if evidence != expected_evidence:
                errors.append(f"{label}.evidence_status overclaims runtime evidence")

    if row_ids != REQUIRED_SKILLS or len(set(row_ids)) != 8:
        errors.append(f"skill parity rows must be unique and ordered as {REQUIRED_SKILLS}")
    if sorted(accounted_sources) != sorted(EXPECTED_SOURCE_ARTIFACTS) or len(set(accounted_sources)) != 12:
        errors.append("skill parity source artifact accounting is incomplete or duplicated")

    effects = parity.get("contract_effects")
    if _check_exact_keys(effects, {"K08", "advanced", "boundaries"}, "skill parity contract_effects", errors):
        if effects.get("K08") != "static-repository-skill-contracts":
            errors.append("K08 effect must remain static repository Skill contracts")
        if effects.get("advanced") != ["K02", "K03", "K04", "K05", "K06", "K14", "K16", "K18", "K19"]:
            errors.append("contract advancement list drifted")
        required_boundaries = [
            "K10-not-implemented", "K11-not-implemented", "K12-not-implemented",
            "K13-not-implemented", "K14-live-ritual-not-implemented",
            "K15-live-actuators-not-implemented", "K16-feedback-transport-not-implemented",
        ]
        boundaries = effects.get("boundaries")
        _check_string_list(boundaries, "contract_effects.boundaries", errors)
        if boundaries != required_boundaries:
            errors.append("contract boundaries must preserve every reviewed not-implemented claim")

    scenarios = parity.get("scenario_evidence")
    if not isinstance(scenarios, list) or len(scenarios) != 8:
        errors.append("scenario_evidence must contain S-001 through S-008")
    else:
        ids = []
        for index, scenario in enumerate(scenarios):
            label = f"scenario_evidence[{index}]"
            if not _check_exact_keys(scenario, {"id", "status", "t09_effect"}, label, errors):
                continue
            ids.append(scenario.get("id"))
            if scenario.get("status") != "not-run":
                errors.append(f"{label}.status must remain not-run")
            effect = scenario.get("t09_effect")
            if not isinstance(effect, str) or not effect.strip() or re.search(r"\b(?:pass|passed|success|successful)\b", effect, re.I):
                errors.append(f"{label}.t09_effect must be honest bounded static evidence")
        if ids != [f"S-{number:03d}" for number in range(1, 9)]:
            errors.append("scenario_evidence IDs must be ordered S-001 through S-008")

    validate_invocation_evidence(parity.get("explicit_invocation_evidence"), errors)
    if parity.get("explicit_invocation_evidence") != []:
        errors.append("T09 records no runtime invocation evidence; array must remain empty")
    if parity.get("results") != []:
        errors.append("skill parity results must remain empty")
    if parity.get("release_blocked") is not True:
        errors.append("skill parity release_blocked must remain true")
    if parity.get("repository_completion") != "incomplete":
        errors.append("repository completion must remain incomplete")
    return parity_text


def validate_false_claims(texts, errors):
    for relative, text in texts:
        for pattern in AFFIRMATIVE_CLAIM_PATTERNS:
            match = pattern.search(text)
            if match:
                errors.append(f"unsupported affirmative capability claim in {relative}: {match.group(0)!r}")


def validate_repository(root=ROOT):
    root = Path(root)
    errors = []
    texts = validate_skills(root, errors)
    _, source_text = validate_source_manifest(root, errors)
    parity_text = validate_parity(root, source_text, errors)
    if source_text is not None:
        texts.append((SOURCE_MANIFEST_PATH, source_text))
    if parity_text is not None:
        texts.append((PARITY_PATH, parity_text))
    validate_false_claims(texts, errors)
    return errors


def main():
    errors = validate_repository(ROOT)
    if errors:
        for error in errors:
            print(f"skill-check: ERROR: {error}", file=sys.stderr)
        return 1
    print("skill-check: PASS (8 Skills, 12 frozen source artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
