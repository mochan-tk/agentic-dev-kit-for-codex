#!/usr/bin/env python3
"""Import, render, and validate the durable conformance catalog.

Only the ``import`` and ``render`` commands without ``--check`` write files.
The ``check`` command and both ``--check`` modes are read-only and fail closed.
The implementation intentionally uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = "tests/conformance/source/05_CONFORMANCE_SCENARIOS.md"
SOURCE_MANIFEST_PATH = "tests/conformance/source/manifest.json"
CATALOG_PATH = "tests/conformance/catalog.json"
CATALOG_SCHEMA_PATH = "tests/conformance/catalog.schema.json"
COVERAGE_PATH = "tests/conformance/coverage.json"
COVERAGE_SCHEMA_PATH = "tests/conformance/coverage.schema.json"
RESULTS_PATH = "tests/conformance/results.json"
RESULTS_SCHEMA_PATH = "tests/conformance/results.schema.json"
HUMAN_CATALOG_PATH = "docs/conformance/catalog.md"
PROVENANCE_ADR_PATH = (
    "docs/agreements/adr/ADR-0006-conformance-catalog-provenance.md"
)
PHASE_MANIFEST_PATH = "tests/conformance/manifest.json"
TOOL_PATH = ".github/scripts/conformance-catalog.py"
MANAGED_OUTPUT_PATHS = {
    SOURCE_MANIFEST_PATH,
    CATALOG_PATH,
    CATALOG_SCHEMA_PATH,
    HUMAN_CATALOG_PATH,
}

FIXED_ASSET_POLICY_VERSION = 1
MIB = 1024 * 1024
FIXED_ASSET_CLASS_LIMITS = {
    "frozen-source/v1": 1 * MIB,
    "catalog-json/v1": 4 * MIB,
    "independent-json/v1": 4 * MIB,
    "contract-json/v1": 1 * MIB,
    "repository-text/v1": 4 * MIB,
    "policy-text/v1": 1 * MIB,
}
FIXED_ASSET_SPECS = {
    SOURCE_PATH: {
        "label": "scenario source",
        "class": "frozen-source/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["frozen-source/v1"],
    },
    SOURCE_MANIFEST_PATH: {
        "label": "source provenance",
        "class": "contract-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["contract-json/v1"],
    },
    CATALOG_PATH: {
        "label": "canonical catalog",
        "class": "catalog-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["catalog-json/v1"],
    },
    CATALOG_SCHEMA_PATH: {
        "label": "catalog schema",
        "class": "contract-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["contract-json/v1"],
    },
    COVERAGE_PATH: {
        "label": "target coverage",
        "class": "independent-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["independent-json/v1"],
    },
    COVERAGE_SCHEMA_PATH: {
        "label": "coverage schema",
        "class": "contract-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["contract-json/v1"],
    },
    RESULTS_PATH: {
        "label": "conformance results",
        "class": "independent-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["independent-json/v1"],
    },
    RESULTS_SCHEMA_PATH: {
        "label": "results schema",
        "class": "contract-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["contract-json/v1"],
    },
    HUMAN_CATALOG_PATH: {
        "label": "rendered catalog",
        "class": "repository-text/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["repository-text/v1"],
    },
    PROVENANCE_ADR_PATH: {
        "label": "catalog provenance ADR",
        "class": "policy-text/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["policy-text/v1"],
    },
    PHASE_MANIFEST_PATH: {
        "label": "Phase conformance manifest",
        "class": "contract-json/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["contract-json/v1"],
    },
    TOOL_PATH: {
        "label": "catalog tool",
        "class": "policy-text/v1",
        "max_bytes": FIXED_ASSET_CLASS_LIMITS["policy-text/v1"],
    },
}
AGREEMENT_ADR_MAX_BYTES = FIXED_ASSET_CLASS_LIMITS["policy-text/v1"]
READ_CHUNK_BYTES = 64 * 1024

RESEARCH_ARCHIVE_NAME = "agentic-dev-kit-codex-research-pack.zip"
RESEARCH_ARCHIVE_MEMBER = (
    "agentic-dev-kit-codex-research-pack/05_CONFORMANCE_SCENARIOS.md"
)
RESEARCH_ARCHIVE_SHA256 = (
    "55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7"
)
SOURCE_SHA256 = (
    "21d12a287f536188355e75a9d563d4da329eb934f3ce7836db48b62bfd10faa0"
)
SOURCE_BYTES = 26387
SOURCE_LINES = 876
TOTAL_SCENARIOS = 136
SOURCE_BASELINE_REPOSITORY = "mochan-tk/agentic-dev-kit-for-copilot"
SOURCE_BASELINE_COMMIT = "fd265ddef150fab86cd54d0e383c2c25fe297ffb"
SOURCE_BASELINE_TREE = "88f96493ec167602750c8dfec044629bd494a586"

SOURCE_FAMILY_ORDER = [
    "C",
    "A",
    "S",
    "R",
    "E",
    "H",
    "W",
    "T",
    "O",
    "I",
    "G",
    "P",
    "D",
    "X",
]
EXPECTED_FAMILY_COUNTS = {
    "A": 6,
    "C": 5,
    "D": 4,
    "E": 10,
    "G": 13,
    "H": 10,
    "I": 15,
    "O": 7,
    "P": 12,
    "R": 10,
    "S": 8,
    "T": 16,
    "W": 12,
    "X": 8,
}

SCENARIO_HEADING = re.compile(
    r"^### (?P<id>[A-Z]-[0-9]{3}) — (?P<title>[^\n]+)\n", re.MULTILINE
)
SECTION_HEADING = re.compile(
    r"^## (?P<number>[0-9]+)\. (?P<title>[^\n]+)\n", re.MULTILINE
)
CLAUSE = re.compile(
    r"^\*\*(?P<label>Precondition|Action|Expected|Expected target behavior):\*\* "
    r"(?P<text>[^\n]+)$",
    re.MULTILINE,
)
FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCENARIO_ID = re.compile(r"^[A-Z]-[0-9]{3}$")
PRIVATE_PATH = re.compile(
    r"(?:/Users/|/home/|file://|~/|~\\|"
    r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/])"
)
AGREEMENT_ADR = re.compile(
    r"^docs/agreements/adr/ADR-[0-9]{4}-[a-z0-9][a-z0-9-]*\.md$"
)

A002_SPECIALIZATION = (
    "Nested discovery follows the repository root to the session startup working "
    "directory. Editing a `.github` path from a root-started session does not itself "
    "load `.github/AGENTS.md`; the probe must start within that hierarchy or "
    "explicitly read and apply the nested policy."
)
W008_SPECIALIZATION = (
    "Bind event assertions to a named Codex client, version, and observation date. "
    "The `codex exec --json` JSONL stream shape is distinct from `--output-schema`, "
    "which constrains only the final structured output. Preserve or explicitly "
    "handle unknown event types; malformed, interrupted, or unrecognized required "
    "events are non-pass."
)
C004_AGREEMENT_ISSUE = (
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7"
)


class CatalogError(ValueError):
    """A deterministic catalog validation failure."""


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CatalogError("duplicate object key")
        value[key] = item
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError, UnicodeError):
        raise CatalogError("JSON value cannot be canonicalized") from None


def decode_utf8_lf(raw: bytes, label: str) -> tuple[bytes, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CatalogError(f"{label} must not contain a UTF-8 BOM")
    if b"\r" in raw:
        raise CatalogError(f"{label} must use LF line endings")
    if not raw.endswith(b"\n"):
        raise CatalogError(f"{label} must end with one LF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CatalogError(f"{label} is not valid UTF-8") from None
    if unicodedata.normalize("NFC", text) != text:
        raise CatalogError(f"{label} must use NFC-normalized Unicode")
    return raw, text


def parse_json_bytes(
    raw: bytes, label: str, *, canonical: bool = True
) -> dict[str, Any]:
    raw, text = decode_utf8_lf(raw, label)
    try:
        value = json.loads(text, object_pairs_hook=reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise CatalogError(
            f"{label} is not valid JSON "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from None
    except CatalogError:
        raise CatalogError(f"{label} is not valid JSON: duplicate object key") from None
    except (RecursionError, ValueError):
        raise CatalogError(f"{label} is not valid JSON: invalid structure") from None
    if not isinstance(value, dict):
        raise CatalogError(f"{label} must contain a JSON object")
    if canonical and raw != canonical_json_bytes(value):
        raise CatalogError(f"{label} is not in canonical JSON form")
    return value


def valid_managed_relative_path(relative: str) -> bool:
    return relative in MANAGED_OUTPUT_PATHS and valid_repository_relative_path(relative)


def valid_repository_relative_path(relative: str) -> bool:
    pure = PurePosixPath(relative)
    return (
        relative == pure.as_posix()
        and not relative.startswith("/")
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def close_descriptor(descriptor: int) -> None:
    if descriptor < 0:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def safe_descriptor_open_flags(*, directory: bool) -> int:
    if os.name != "posix":
        raise CatalogError("safe descriptor operations are unsupported")
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory_only = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory_only:
        raise CatalogError("safe descriptor operations are unsupported")
    required_dir_fd = (os.open, os.stat)
    if any(function not in os.supports_dir_fd for function in required_dir_fd):
        raise CatalogError("safe descriptor operations are unsupported")
    if os.stat not in os.supports_follow_symlinks:
        raise CatalogError("safe descriptor operations are unsupported")
    flags = os.O_RDONLY | no_follow
    if directory:
        flags |= directory_only
    else:
        non_blocking = getattr(os, "O_NONBLOCK", 0)
        if not non_blocking:
            raise CatalogError("safe descriptor operations are unsupported")
        flags |= non_blocking
    flags |= getattr(os, "O_CLOEXEC", 0)
    return flags


def require_safe_write_support() -> None:
    try:
        safe_descriptor_open_flags(directory=True)
    except CatalogError:
        raise CatalogError("safe managed output writes are unsupported") from None
    required_dir_fd = (os.mkdir, os.unlink, os.rename)
    if any(function not in os.supports_dir_fd for function in required_dir_fd):
        raise CatalogError("safe managed output writes are unsupported")


def describe_unopenable_parent(
    parent_descriptor: int, component: str, relative: str, subject: str
) -> CatalogError:
    try:
        component_stat = os.stat(
            component,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return CatalogError(f"{subject} parent is missing: {relative}")
    except OSError:
        return CatalogError(f"{subject} parent cannot be inspected: {relative}")
    if stat.S_ISLNK(component_stat.st_mode):
        return CatalogError(f"{subject} parent is a symlink: {relative}")
    if not stat.S_ISDIR(component_stat.st_mode):
        return CatalogError(f"{subject} parent is not a directory: {relative}")
    return CatalogError(f"{subject} parent cannot be opened safely: {relative}")


def open_child_directory(
    parent_descriptor: int,
    component: str,
    relative: str,
    *,
    create: bool,
    subject: str = "managed output",
) -> int:
    flags = safe_descriptor_open_flags(directory=True)
    try:
        return os.open(component, flags, dir_fd=parent_descriptor)
    except FileNotFoundError:
        if not create:
            raise CatalogError(f"{subject} parent is missing: {relative}") from None
        try:
            os.mkdir(component, 0o755, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        except OSError:
            raise CatalogError(
                f"{subject} parent cannot be created: {relative}"
            ) from None
        try:
            return os.open(component, flags, dir_fd=parent_descriptor)
        except OSError:
            raise describe_unopenable_parent(
                parent_descriptor, component, relative, subject
            ) from None
    except OSError:
        raise describe_unopenable_parent(
            parent_descriptor, component, relative, subject
        ) from None
    except (TypeError, NotImplementedError):
        raise CatalogError("safe descriptor operations are unsupported") from None


def canonicalize_repository_root(root: Path) -> Path:
    """Resolve benign ancestor links while preserving the final root component."""

    try:
        absolute = root.absolute()
        if absolute == Path(absolute.anchor):
            return absolute
        return absolute.parent.resolve(strict=True) / absolute.name
    except (OSError, RuntimeError):
        raise CatalogError("repository root cannot be canonicalized") from None


def open_canonical_root(canonical_root: Path) -> int:
    """Open an absolute canonical root component-wise from the filesystem root."""

    flags = safe_descriptor_open_flags(directory=True)
    if not canonical_root.is_absolute() or canonical_root.anchor != "/":
        raise CatalogError("repository root cannot be opened safely")
    descriptor = -1
    try:
        descriptor = os.open(canonical_root.anchor, flags)
        for component in canonical_root.parts[1:]:
            child_descriptor = os.open(component, flags, dir_fd=descriptor)
            close_descriptor(descriptor)
            descriptor = child_descriptor
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise CatalogError("repository root cannot be opened safely")
        return descriptor
    except CatalogError:
        close_descriptor(descriptor)
        raise
    except (OSError, TypeError, NotImplementedError):
        close_descriptor(descriptor)
        raise CatalogError("repository root cannot be opened safely") from None


def open_repository_parent(
    root: Path,
    relative: str,
    *,
    create_parents: bool,
    subject: str,
) -> tuple[Path, int, int, tuple[str, ...], str]:
    """Open a validated repository-relative parent with descriptor authority."""

    if not valid_repository_relative_path(relative):
        raise CatalogError(f"{subject} path is unsupported")
    if create_parents:
        require_safe_write_support()
    canonical_root = canonicalize_repository_root(root)
    root_descriptor = -1
    parent_descriptor = -1
    parent_parts = tuple(PurePosixPath(relative).parent.parts)
    try:
        root_descriptor = open_canonical_root(canonical_root)
        parent_descriptor = os.dup(root_descriptor)
        for component in parent_parts:
            child_descriptor = open_child_directory(
                parent_descriptor,
                component,
                relative,
                create=create_parents,
                subject=subject,
            )
            close_descriptor(parent_descriptor)
            parent_descriptor = child_descriptor
        return (
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            PurePosixPath(relative).name,
        )
    except CatalogError:
        close_descriptor(parent_descriptor)
        close_descriptor(root_descriptor)
        raise
    except (OSError, TypeError, NotImplementedError):
        close_descriptor(parent_descriptor)
        close_descriptor(root_descriptor)
        raise CatalogError("repository root cannot be opened safely") from None


def open_managed_parent(
    root: Path, relative: str, *, create_parents: bool
) -> tuple[Path, int, int, tuple[str, ...], str]:
    """Open the fixed output parent without granting authority to path checks."""

    if not valid_managed_relative_path(relative):
        raise CatalogError("managed output path is unsupported")
    return open_repository_parent(
        root,
        relative,
        create_parents=create_parents,
        subject="managed output",
    )


def open_fixed_asset_parent(
    root: Path, relative: str
) -> tuple[Path, int, int, tuple[str, ...], str]:
    if relative not in FIXED_ASSET_SPECS:
        raise CatalogError("fixed asset path is unsupported")
    return open_repository_parent(
        root,
        relative,
        create_parents=False,
        subject="fixed asset",
    )


def read_target_at(
    parent_descriptor: int,
    target_name: str,
    relative: str,
    *,
    max_bytes: int,
) -> tuple[bytes, os.stat_result] | None:
    try:
        target_stat = os.stat(
            target_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise CatalogError(f"managed output cannot be inspected: {relative}") from None
    if stat.S_ISLNK(target_stat.st_mode):
        raise CatalogError(f"managed output target is a symlink: {relative}")
    if not stat.S_ISREG(target_stat.st_mode):
        raise CatalogError(f"managed output target is not a regular file: {relative}")
    if target_stat.st_size > max_bytes:
        raise CatalogError(
            f"managed output exceeds configured byte limit: {relative}"
        )

    descriptor = -1
    try:
        descriptor = os.open(
            target_name,
            safe_descriptor_open_flags(directory=False),
            dir_fd=parent_descriptor,
        )
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise CatalogError(
                f"managed output target is not a regular file: {relative}"
            )
        if _file_binding(target_stat) != _file_binding(opened_stat):
            raise CatalogError(f"managed output changed during read: {relative}")
        chunks = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, max_bytes + 1 - total),
            )
            if not chunk:
                completed_stat = os.fstat(descriptor)
                if _file_binding(opened_stat) != _file_binding(completed_stat):
                    raise CatalogError(
                        f"managed output changed during read: {relative}"
                    )
                value = b"".join(chunks)
                if len(value) != completed_stat.st_size:
                    raise CatalogError(
                        f"managed output changed during read: {relative}"
                    )
                return value, completed_stat
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise CatalogError(
                    f"managed output exceeds configured byte limit: {relative}"
                )
    except CatalogError:
        raise
    except (OSError, TypeError, NotImplementedError):
        raise CatalogError(f"managed output cannot be read: {relative}") from None
    finally:
        close_descriptor(descriptor)


def create_temporary_at(
    parent_descriptor: int, target_name: str, content: bytes, relative: str
) -> str:
    descriptor = -1
    temporary_name: str | None = None
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | safe_descriptor_open_flags(directory=False)
    )
    try:
        for _ in range(128):
            candidate = f".{target_name}.{secrets.token_hex(12)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        if temporary_name is None:
            raise CatalogError(f"managed output cannot be written: {relative}")
        os.fchmod(descriptor, 0o644)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError
            remaining = remaining[written:]
        os.fsync(descriptor)
        close_descriptor(descriptor)
        descriptor = -1
        return temporary_name
    except CatalogError:
        raise
    except (OSError, TypeError, NotImplementedError):
        cleanup_failed = False
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except (OSError, TypeError, NotImplementedError):
                cleanup_failed = True
        if cleanup_failed:
            raise CatalogError(
                "managed output write failed and temporary cleanup could not "
                f"be confirmed: {relative}"
            ) from None
        raise CatalogError(f"managed output cannot be written: {relative}") from None
    finally:
        close_descriptor(descriptor)


def verify_parent_binding(
    canonical_root: Path,
    root_descriptor: int,
    parent_descriptor: int,
    parent_parts: tuple[str, ...],
    relative: str,
) -> None:
    """Re-open the root-relative chain and compare it with the write dirfd."""

    check_root_descriptor = -1
    check_descriptor = -1
    try:
        check_root_descriptor = open_canonical_root(canonical_root)
        expected_root = os.fstat(root_descriptor)
        observed_root = os.fstat(check_root_descriptor)
        if (expected_root.st_dev, expected_root.st_ino) != (
            observed_root.st_dev,
            observed_root.st_ino,
        ):
            raise CatalogError(
                f"managed output parent changed during operation: {relative}"
            )
        check_descriptor = os.dup(check_root_descriptor)
        for component in parent_parts:
            child_descriptor = open_child_directory(
                check_descriptor,
                component,
                relative,
                create=False,
            )
            close_descriptor(check_descriptor)
            check_descriptor = child_descriptor
        expected = os.fstat(parent_descriptor)
        observed = os.fstat(check_descriptor)
        if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
            raise CatalogError(
                f"managed output parent changed during operation: {relative}"
            )
    except CatalogError:
        raise CatalogError(
            f"managed output parent changed during operation: {relative}"
        ) from None
    except (OSError, TypeError, NotImplementedError):
        raise CatalogError(
            f"managed output parent changed during operation: {relative}"
        ) from None
    finally:
        close_descriptor(check_descriptor)
        close_descriptor(check_root_descriptor)


def _file_binding(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _fixed_asset_test_hook(stage: str, relative: str) -> None:
    """Deterministic no-op seam for namespace-race regression tests."""


def verify_fixed_asset_binding(
    canonical_root: Path,
    root_descriptor: int,
    parent_descriptor: int,
    parent_parts: tuple[str, ...],
    target_name: str,
    relative: str,
    expected_target: os.stat_result,
) -> None:
    """Freshly re-walk root, parent, and target name after a bounded read."""

    check_root_descriptor = -1
    check_parent_descriptor = -1
    target_descriptor = -1
    try:
        check_root_descriptor = open_canonical_root(canonical_root)
        if _file_binding(os.fstat(root_descriptor))[:2] != _file_binding(
            os.fstat(check_root_descriptor)
        )[:2]:
            raise CatalogError("fixed asset changed during read")
        check_parent_descriptor = os.dup(check_root_descriptor)
        for component in parent_parts:
            child_descriptor = open_child_directory(
                check_parent_descriptor,
                component,
                relative,
                create=False,
                subject="fixed asset",
            )
            close_descriptor(check_parent_descriptor)
            check_parent_descriptor = child_descriptor
        if _file_binding(os.fstat(parent_descriptor))[:2] != _file_binding(
            os.fstat(check_parent_descriptor)
        )[:2]:
            raise CatalogError("fixed asset changed during read")
        named_stat = os.stat(
            target_name,
            dir_fd=check_parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(named_stat.st_mode) or not stat.S_ISREG(named_stat.st_mode):
            raise CatalogError("fixed asset changed during read")
        target_descriptor = os.open(
            target_name,
            safe_descriptor_open_flags(directory=False),
            dir_fd=check_parent_descriptor,
        )
        fresh_stat = os.fstat(target_descriptor)
        if not stat.S_ISREG(fresh_stat.st_mode):
            raise CatalogError("fixed asset changed during read")
        expected = _file_binding(expected_target)
        if _file_binding(named_stat) != expected or _file_binding(fresh_stat) != expected:
            raise CatalogError("fixed asset changed during read")
    except CatalogError:
        raise CatalogError(f"fixed asset changed during read: {relative}") from None
    except (OSError, TypeError, NotImplementedError):
        raise CatalogError(f"fixed asset changed during read: {relative}") from None
    finally:
        close_descriptor(target_descriptor)
        close_descriptor(check_parent_descriptor)
        close_descriptor(check_root_descriptor)


def _read_fixed_asset_from_parent(
    root: Path,
    relative: str,
    label: str,
    max_bytes: int,
    parent_opener: Any,
) -> bytes:
    canonical_root: Path | None = None
    root_descriptor = -1
    parent_descriptor = -1
    target_descriptor = -1
    try:
        (
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            target_name,
        ) = parent_opener(root, relative)
        _fixed_asset_test_hook("after_parent_open", relative)
        try:
            named_stat = os.stat(
                target_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            raise CatalogError(f"{label} cannot be read") from None
        if stat.S_ISLNK(named_stat.st_mode):
            raise CatalogError(f"{label} is a symlink")
        if not stat.S_ISREG(named_stat.st_mode):
            raise CatalogError(f"{label} is not a regular file")
        if named_stat.st_size > max_bytes:
            raise CatalogError(f"{label} exceeds configured byte limit")
        _fixed_asset_test_hook("after_target_stat", relative)
        try:
            target_descriptor = os.open(
                target_name,
                safe_descriptor_open_flags(directory=False),
                dir_fd=parent_descriptor,
            )
            opened_stat = os.fstat(target_descriptor)
        except OSError:
            raise CatalogError(f"{label} cannot be read") from None
        if not stat.S_ISREG(opened_stat.st_mode):
            raise CatalogError(f"{label} is not a regular file")
        if _file_binding(named_stat) != _file_binding(opened_stat):
            raise CatalogError(f"{label} changed during read")
        if opened_stat.st_size > max_bytes:
            raise CatalogError(f"{label} exceeds configured byte limit")
        _fixed_asset_test_hook("after_target_open", relative)
        value = bytearray()
        while True:
            chunk = os.read(
                target_descriptor,
                min(READ_CHUNK_BYTES, max_bytes + 1 - len(value)),
            )
            if not chunk:
                break
            value.extend(chunk)
            if len(value) > max_bytes:
                raise CatalogError(f"{label} exceeds configured byte limit")
        completed_stat = os.fstat(target_descriptor)
        if _file_binding(opened_stat) != _file_binding(completed_stat):
            raise CatalogError(f"{label} changed during read")
        if len(value) != completed_stat.st_size:
            raise CatalogError(f"{label} changed during read")
        _fixed_asset_test_hook("after_read", relative)
        close_descriptor(target_descriptor)
        target_descriptor = -1
        _fixed_asset_test_hook("before_binding_check", relative)
        verify_fixed_asset_binding(
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            target_name,
            relative,
            completed_stat,
        )
        return bytes(value)
    except CatalogError:
        raise
    except (OSError, TypeError, NotImplementedError):
        raise CatalogError(f"{label} cannot be read") from None
    finally:
        close_descriptor(target_descriptor)
        close_descriptor(parent_descriptor)
        close_descriptor(root_descriptor)


def read_fixed_asset(root: Path, relative: str) -> bytes:
    spec = FIXED_ASSET_SPECS.get(relative)
    if spec is None:
        raise CatalogError("fixed asset path is unsupported")
    return _read_fixed_asset_from_parent(
        root,
        relative,
        spec["label"],
        spec["max_bytes"],
        open_fixed_asset_parent,
    )


def read_fixed_utf8_lf(root: Path, relative: str) -> tuple[bytes, str]:
    spec = FIXED_ASSET_SPECS.get(relative)
    if spec is None:
        raise CatalogError("fixed asset path is unsupported")
    return decode_utf8_lf(read_fixed_asset(root, relative), spec["label"])


def load_fixed_json(
    root: Path, relative: str, *, canonical: bool = True
) -> dict[str, Any]:
    spec = FIXED_ASSET_SPECS.get(relative)
    if spec is None:
        raise CatalogError("fixed asset path is unsupported")
    return parse_json_bytes(
        read_fixed_asset(root, relative), spec["label"], canonical=canonical
    )


def read_agreement_adr(root: Path, relative: str) -> bytes:
    if not AGREEMENT_ADR.fullmatch(relative):
        raise CatalogError("C-004 agreement ADR path is unsupported")

    def open_agreement_parent(
        repository_root: Path, repository_relative: str
    ) -> tuple[Path, int, int, tuple[str, ...], str]:
        return open_repository_parent(
            repository_root,
            repository_relative,
            create_parents=False,
            subject="agreement ADR",
        )

    return _read_fixed_asset_from_parent(
        root,
        relative,
        "C-004 agreement ADR",
        AGREEMENT_ADR_MAX_BYTES,
        open_agreement_parent,
    )


def write_if_changed(root: Path, relative: str, content: bytes) -> None:
    root_descriptor = -1
    parent_descriptor = -1
    temporary_name: str | None = None
    try:
        spec = FIXED_ASSET_SPECS.get(relative)
        if spec is None or relative not in MANAGED_OUTPUT_PATHS:
            raise CatalogError("managed output path is unsupported")
        if len(content) > spec["max_bytes"]:
            raise CatalogError(
                f"managed output exceeds configured byte limit: {relative}"
            )
        require_safe_write_support()
        (
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            target_name,
        ) = open_managed_parent(root, relative, create_parents=True)
        observed_target = read_target_at(
            parent_descriptor,
            target_name,
            relative,
            max_bytes=spec["max_bytes"],
        )
        if observed_target is not None and observed_target[0] == content:
            observed_stat = observed_target[1]
            verify_parent_binding(
                canonical_root,
                root_descriptor,
                parent_descriptor,
                parent_parts,
                relative,
            )
            verify_fixed_asset_binding(
                canonical_root,
                root_descriptor,
                parent_descriptor,
                parent_parts,
                target_name,
                relative,
                observed_stat,
            )
            os.fsync(parent_descriptor)
            verify_parent_binding(
                canonical_root,
                root_descriptor,
                parent_descriptor,
                parent_parts,
                relative,
            )
            verify_fixed_asset_binding(
                canonical_root,
                root_descriptor,
                parent_descriptor,
                parent_parts,
                target_name,
                relative,
                observed_stat,
            )
            return
        temporary_name = create_temporary_at(
            parent_descriptor, target_name, content, relative
        )
        verify_parent_binding(
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            relative,
        )
        # POSIX renameat semantics atomically replace within this one parent dirfd.
        os.rename(
            temporary_name,
            target_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
        verify_parent_binding(
            canonical_root,
            root_descriptor,
            parent_descriptor,
            parent_parts,
            relative,
        )
    except CatalogError:
        raise
    except (OSError, TypeError, NotImplementedError):
        raise CatalogError(f"managed output cannot be written: {relative}") from None
    finally:
        cleanup_failed = False
        if temporary_name is not None and parent_descriptor >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except (OSError, TypeError, NotImplementedError):
                cleanup_failed = True
        close_descriptor(parent_descriptor)
        close_descriptor(root_descriptor)
        if cleanup_failed:
            raise CatalogError(
                "managed output write failed and temporary cleanup could not "
                f"be confirmed: {relative}"
            ) from None


def read_managed_output(root: Path, relative: str) -> bytes:
    """Read through a verified descriptor chain and fail closed otherwise."""

    spec = FIXED_ASSET_SPECS.get(relative)
    if spec is None or relative not in MANAGED_OUTPUT_PATHS:
        raise CatalogError("managed output path is unsupported")

    def open_output_parent(
        repository_root: Path, repository_relative: str
    ) -> tuple[Path, int, int, tuple[str, ...], str]:
        return open_managed_parent(
            repository_root, repository_relative, create_parents=False
        )

    return _read_fixed_asset_from_parent(
        root,
        relative,
        spec["label"],
        spec["max_bytes"],
        open_output_parent,
    )


def exact_keys(
    value: Mapping[str, Any], required: set[str], optional: set[str], label: str
) -> None:
    observed = set(value)
    missing = required - observed
    unsupported = observed - required - optional
    if missing or unsupported:
        raise CatalogError(
            f"{label} has an invalid key set "
            f"(missing={len(missing)}, unsupported={len(unsupported)})"
        )


def source_manifest() -> dict[str, Any]:
    return {
        "schema": "conformance-source-manifest/v1",
        "research_archive": {
            "file_name": RESEARCH_ARCHIVE_NAME,
            "sha256": RESEARCH_ARCHIVE_SHA256,
            "committed": False,
            "supplied_files_verified": 7,
        },
        "scenario_member": {
            "archive_member": RESEARCH_ARCHIVE_MEMBER,
            "repository_path": SOURCE_PATH,
            "sha256": SOURCE_SHA256,
            "bytes": SOURCE_BYTES,
            "lines": SOURCE_LINES,
            "encoding": "UTF-8",
            "line_endings": "LF",
        },
        "source_baseline": {
            "repository": SOURCE_BASELINE_REPOSITORY,
            "commit": SOURCE_BASELINE_COMMIT,
            "tree": SOURCE_BASELINE_TREE,
            "phase_manifest_pointer": f"{PHASE_MANIFEST_PATH}#source",
        },
        "conversion": {
            "tool": TOOL_PATH,
            "import_outputs": [
                SOURCE_MANIFEST_PATH,
                CATALOG_PATH,
                CATALOG_SCHEMA_PATH,
            ],
            "independent_update_authorities": [
                COVERAGE_PATH,
                COVERAGE_SCHEMA_PATH,
                RESULTS_PATH,
                RESULTS_SCHEMA_PATH,
            ],
            "render_output": HUMAN_CATALOG_PATH,
            "import_write": f"python3 {TOOL_PATH} import",
            "render_write": f"python3 {TOOL_PATH} render",
            "import_check": f"python3 {TOOL_PATH} import --check",
            "render_check": f"python3 {TOOL_PATH} render --check",
            "catalog_check": f"python3 {TOOL_PATH} check",
        },
        "independent_full_text_comparison": {
            "classification": "advisory",
            "required_approver": False,
        },
        "private_local_paths_recorded": False,
    }


def parse_clause(body: str, label: str) -> tuple[str, str] | None:
    matches = [
        (match.group("label"), match.group("text"))
        for match in CLAUSE.finditer(body)
        if match.group("label") == label
        or (label == "Expected" and match.group("label") == "Expected target behavior")
    ]
    if len(matches) > 1:
        raise CatalogError(f"scenario entry has duplicate {label} clauses")
    return matches[0] if matches else None


def parse_source(source: str) -> dict[str, Any]:
    scenario_matches = list(SCENARIO_HEADING.finditer(source))
    if not scenario_matches:
        raise CatalogError("scenario source contains no scenario headings")
    section_matches = list(SECTION_HEADING.finditer(source))
    if not section_matches:
        raise CatalogError("scenario source contains no section headings")

    first_scenario = scenario_matches[0]
    family_sections: list[tuple[re.Match[str], int]] = []
    for index, section in enumerate(section_matches):
        end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(source)
        )
        if SCENARIO_HEADING.search(source, section.end(), end):
            family_sections.append((section, end))
    if not family_sections:
        raise CatalogError("scenario source contains no family sections")

    preamble = source[: family_sections[0][0].start()]
    footer = source[family_sections[-1][1] :]
    # The previous expression is empty because the last family boundary is the next
    # section start. Recover the footer from that boundary explicitly.
    last_family_heading, _last_end = family_sections[-1]
    last_heading_index = section_matches.index(last_family_heading)
    if last_heading_index + 1 >= len(section_matches):
        raise CatalogError("scenario source must end with a non-family footer section")
    footer_start = section_matches[last_heading_index + 1].start()
    footer = source[footer_start:]

    families: list[dict[str, Any]] = []
    global_order = 0
    observed_ids: list[str] = []
    for family_order, (section, section_end) in enumerate(family_sections, start=1):
        section_index = section_matches.index(section)
        next_section_start = (
            section_matches[section_index + 1].start()
            if section_index + 1 < len(section_matches)
            else len(source)
        )
        section_end = next_section_start
        matches = list(SCENARIO_HEADING.finditer(source, section.end(), section_end))
        if not matches:
            raise CatalogError(f"family section index {family_order} is empty")
        family_id = matches[0].group("id").split("-", 1)[0]
        if any(match.group("id").split("-", 1)[0] != family_id for match in matches):
            raise CatalogError(
                f"family section index {family_order} mixes scenario families"
            )
        heading_markdown = source[section.start() : matches[0].start()]
        scenarios: list[dict[str, Any]] = []
        for position, match in enumerate(matches):
            global_order += 1
            body_end = matches[position + 1].start() if position + 1 < len(matches) else section_end
            body = source[match.start() : body_end]
            scenario_id = match.group("id")
            observed_ids.append(scenario_id)
            scenario: dict[str, Any] = {
                "id": scenario_id,
                "source_order": global_order,
                "title": match.group("title"),
                "source_body_markdown": body,
            }
            precondition = parse_clause(body, "Precondition")
            action = parse_clause(body, "Action")
            expected = parse_clause(body, "Expected")
            if precondition is not None:
                scenario["precondition"] = precondition[1]
            if action is not None:
                scenario["action"] = action[1]
            if expected is None:
                raise CatalogError(
                    f"scenario entry index {global_order} has no expected clause"
                )
            scenario["expected"] = {
                "label": expected[0],
                "text": expected[1],
            }
            scenarios.append(scenario)
        families.append(
            {
                "id": family_id,
                "source_order": family_order,
                "title": section.group("title"),
                "source_heading_markdown": heading_markdown,
                "scenarios": scenarios,
            }
        )

    reconstructed = preamble + "".join(
        family["source_heading_markdown"]
        + "".join(item["source_body_markdown"] for item in family["scenarios"])
        for family in families
    ) + footer
    if reconstructed != source:
        raise CatalogError("catalog parser cannot reconstruct the source byte-for-byte")

    if [family["id"] for family in families] != SOURCE_FAMILY_ORDER:
        raise CatalogError("scenario family source order differs from the reviewed order")
    counts = {family["id"]: len(family["scenarios"]) for family in families}
    if counts != {family: EXPECTED_FAMILY_COUNTS[family] for family in SOURCE_FAMILY_ORDER}:
        raise CatalogError("scenario family counts differ from the reviewed counts")
    expected_ids = [
        f"{family}-{number:03d}"
        for family in SOURCE_FAMILY_ORDER
        for number in range(1, EXPECTED_FAMILY_COUNTS[family] + 1)
    ]
    if observed_ids != expected_ids:
        raise CatalogError("scenario IDs are not unique, gap-free, and in source order")
    if len(observed_ids) != TOTAL_SCENARIOS:
        raise CatalogError(f"scenario total must be {TOTAL_SCENARIOS}")
    if first_scenario.start() <= family_sections[0][0].start():
        raise CatalogError("first scenario is not nested in its family section")

    return {
        "schema": "conformance-catalog/v1",
        "source": {
            "path": SOURCE_PATH,
            "sha256": SOURCE_SHA256,
            "bytes": SOURCE_BYTES,
            "lines": SOURCE_LINES,
        },
        "title": "Codex Port Conformance Scenarios",
        "scenario_count": TOTAL_SCENARIOS,
        "preamble_markdown": preamble,
        "families": families,
        "footer_markdown": footer,
    }


def reconstruct_source(catalog: Mapping[str, Any]) -> str:
    try:
        return str(catalog["preamble_markdown"]) + "".join(
            str(family["source_heading_markdown"])
            + "".join(
                str(scenario["source_body_markdown"])
                for scenario in family["scenarios"]
            )
            for family in catalog["families"]
        ) + str(catalog["footer_markdown"])
    except (KeyError, TypeError):
        raise CatalogError("catalog cannot reconstruct source: invalid structure") from None


def catalog_schema() -> dict[str, Any]:
    clause = {"type": "string", "minLength": 1}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/tests/conformance/catalog.schema.json",
        "title": "Canonical conformance scenario definitions",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "source",
            "title",
            "scenario_count",
            "preamble_markdown",
            "families",
            "footer_markdown",
        ],
        "properties": {
            "schema": {"const": "conformance-catalog/v1"},
            "source": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "sha256", "bytes", "lines"],
                "properties": {
                    "path": {"const": SOURCE_PATH},
                    "sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                    "bytes": {"type": "integer", "minimum": 1},
                    "lines": {"type": "integer", "minimum": 1},
                },
            },
            "title": {"type": "string", "minLength": 1},
            "scenario_count": {"const": TOTAL_SCENARIOS},
            "preamble_markdown": {"type": "string", "minLength": 1},
            "families": {
                "type": "array",
                "minItems": len(SOURCE_FAMILY_ORDER),
                "maxItems": len(SOURCE_FAMILY_ORDER),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "source_order",
                        "title",
                        "source_heading_markdown",
                        "scenarios",
                    ],
                    "properties": {
                        "id": {"enum": SOURCE_FAMILY_ORDER},
                        "source_order": {"type": "integer", "minimum": 1},
                        "title": {"type": "string", "minLength": 1},
                        "source_heading_markdown": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "scenarios": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "id",
                                    "source_order",
                                    "title",
                                    "source_body_markdown",
                                    "expected",
                                ],
                                "properties": {
                                    "id": {
                                        "type": "string",
                                        "pattern": "^[A-Z]-[0-9]{3}$",
                                    },
                                    "source_order": {
                                        "type": "integer",
                                        "minimum": 1,
                                    },
                                    "title": {"type": "string", "minLength": 1},
                                    "source_body_markdown": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "precondition": clause,
                                    "action": clause,
                                    "expected": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["label", "text"],
                                        "properties": {
                                            "label": {
                                                "enum": [
                                                    "Expected",
                                                    "Expected target behavior",
                                                ]
                                            },
                                            "text": {
                                                "type": "string",
                                                "minLength": 1,
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "footer_markdown": {"type": "string", "minLength": 1},
        },
    }


def iter_scenarios(catalog: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for family in catalog["families"]:
        for scenario in family["scenarios"]:
            yield scenario


def coverage_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/tests/conformance/coverage.schema.json",
        "title": "Target conformance disposition and coverage plan",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "catalog", "scenario_count", "entries"],
        "properties": {
            "schema": {"const": "conformance-coverage/v1"},
            "catalog": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "sha256"],
                "properties": {
                    "path": {"const": CATALOG_PATH},
                    "sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
            },
            "scenario_count": {"const": TOTAL_SCENARIOS},
            "entries": {
                "type": "array",
                "minItems": TOTAL_SCENARIOS,
                "maxItems": TOTAL_SCENARIOS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "scenario",
                        "disposition",
                        "verification_state",
                    ],
                    "properties": {
                        "scenario": {
                            "type": "string",
                            "pattern": "^[A-Z]-[0-9]{3}$",
                        },
                        "disposition": {
                            "enum": [
                                "planned",
                                "target-specialization",
                                "pending-agreement",
                                "agreement-decision",
                            ]
                        },
                        "verification_state": {"const": "not-run"},
                        "specialization": {"type": "string", "minLength": 1},
                        "agreement_issue": {
                            "const": C004_AGREEMENT_ISSUE,
                        },
                        "agreement_adr": {
                            "type": "string",
                            "pattern": "^docs/agreements/adr/ADR-[0-9]{4}-[a-z0-9][a-z0-9-]*\\.md$",
                        },
                    },
                    "allOf": [
                        {
                            "if": {
                                "properties": {
                                    "disposition": {"const": "planned"}
                                }
                            },
                            "then": {
                                "not": {
                                    "anyOf": [
                                        {"required": ["specialization"]},
                                        {"required": ["agreement_issue"]},
                                        {"required": ["agreement_adr"]},
                                    ]
                                }
                            },
                        },
                        {
                            "if": {
                                "properties": {
                                    "disposition": {
                                        "const": "target-specialization"
                                    }
                                }
                            },
                            "then": {
                                "required": ["specialization"],
                                "not": {
                                    "anyOf": [
                                        {"required": ["agreement_issue"]},
                                        {"required": ["agreement_adr"]},
                                    ]
                                },
                            },
                        },
                        {
                            "if": {
                                "properties": {
                                    "disposition": {"const": "pending-agreement"}
                                }
                            },
                            "then": {
                                "required": ["agreement_issue"],
                                "not": {
                                    "anyOf": [
                                        {"required": ["specialization"]},
                                        {"required": ["agreement_adr"]},
                                    ]
                                },
                            },
                        },
                        {
                            "if": {
                                "properties": {
                                    "disposition": {"const": "agreement-decision"}
                                }
                            },
                            "then": {
                                "required": ["agreement_issue", "agreement_adr"],
                                "not": {"required": ["specialization"]},
                            },
                        },
                    ],
                },
            },
        },
    }


def results_schema() -> dict[str, Any]:
    reference = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "sha256"],
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/tests/conformance/results.schema.json",
        "title": "Conformance result evidence store",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "catalog",
            "result_count",
            "results",
            "release_blocked",
        ],
        "properties": {
            "schema": {"const": "conformance-results/v1"},
            "catalog": reference,
            "result_count": {"type": "integer", "minimum": 0},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "scenario",
                        "status",
                        "source_contract",
                        "target_evidence",
                        "target_commit",
                        "client",
                        "observed_at",
                        "notes",
                    ],
                    "properties": {
                        "scenario": {
                            "type": "string",
                            "pattern": "^[A-Z]-[0-9]{3}$",
                        },
                        "status": {
                            "enum": [
                                "pass",
                                "fail",
                                "skipped",
                                "unverified",
                                "approved-deviation",
                            ]
                        },
                        "source_contract": {"type": "string", "minLength": 1},
                        "target_evidence": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "target_commit": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{40}$",
                        },
                        "client": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["surface", "name", "version"],
                            "properties": {
                                "surface": {
                                    "enum": [
                                        "static",
                                        "cli",
                                        "app",
                                        "cloud",
                                        "github",
                                    ]
                                },
                                "name": {"type": "string", "minLength": 1},
                                "version": {"type": "string", "minLength": 1},
                            },
                        },
                        "observed_at": {
                            "type": "string",
                            "format": "date-time",
                        },
                        "notes": {"type": "string"},
                        "deviation_adr": {
                            "type": "string",
                            "pattern": "^(?:docs/agreements/adr/ADR-[0-9]{4}-.+\\.md|https://github\\.com/.+)$",
                        },
                    },
                    "allOf": [
                        {
                            "if": {
                                "properties": {
                                    "status": {"const": "approved-deviation"}
                                }
                            },
                            "then": {"required": ["deviation_adr"]},
                            "else": {"not": {"required": ["deviation_adr"]}},
                        }
                    ],
                },
            },
            "release_blocked": {"type": "boolean"},
        },
    }


def imported_artifacts(source_text: str) -> dict[str, dict[str, Any]]:
    catalog = parse_source(source_text)
    return {
        SOURCE_MANIFEST_PATH: source_manifest(),
        CATALOG_PATH: catalog,
        CATALOG_SCHEMA_PATH: catalog_schema(),
    }


def render_catalog(catalog: Mapping[str, Any]) -> str:
    catalog_hash = sha256_bytes(canonical_json_bytes(catalog))
    lines = [
        "# Canonical conformance catalog",
        "",
        "> Generated by `.github/scripts/conformance-catalog.py`; do not edit by hand.",
        "",
        f"- Source: `{SOURCE_PATH}`",
        f"- Source SHA-256: `{SOURCE_SHA256}`",
        f"- Catalog SHA-256: `{catalog_hash}`",
        f"- Scenario count: {TOTAL_SCENARIOS}",
        "",
        "This generated file projects canonical source definitions only. Target",
        f"dispositions are independently maintained in `{COVERAGE_PATH}`, and result",
        f"evidence is independently maintained in `{RESULTS_PATH}`. Do not infer a",
        "verification or release state from this projection.",
    ]
    lines.extend(
        [
            "",
            "## Verbatim source definitions",
            "",
            reconstruct_source(catalog).rstrip("\n"),
            "",
        ]
    )
    return "\n".join(lines)


def private_path_values(
    value: Any, location: str = "$", depth: int = 0
) -> Iterable[str]:
    if isinstance(value, dict):
        for index, (key, item) in enumerate(value.items()):
            entry_location = f"$[depth={depth}][entry={index}]"
            if isinstance(key, str) and PRIVATE_PATH.search(key):
                yield f"{entry_location}.<key>"
            yield from private_path_values(
                item, f"{entry_location}.<value>", depth + 1
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from private_path_values(
                item, f"$[depth={depth}][item={index}]", depth + 1
            )
    elif isinstance(value, str) and PRIVATE_PATH.search(value):
        yield location


def validate_import_artifacts(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        source_raw, source_text = read_fixed_utf8_lf(root, SOURCE_PATH)
        if sha256_bytes(source_raw) != SOURCE_SHA256:
            errors.append("scenario source SHA-256 differs from the reviewed member")
        if len(source_raw) != SOURCE_BYTES:
            errors.append("scenario source byte count differs from provenance")
        if source_raw.count(b"\n") != SOURCE_LINES:
            errors.append("scenario source line count differs from provenance")
        if errors:
            return errors
        expected = imported_artifacts(source_text)
    except CatalogError as exc:
        errors.append(str(exc))
        return errors

    for relative, expected_value in expected.items():
        try:
            observed = load_fixed_json(root, relative)
        except CatalogError as exc:
            errors.append(str(exc))
            continue
        if observed != expected_value:
            errors.append(f"{relative} differs from deterministic import output")

    try:
        catalog = load_fixed_json(root, CATALOG_PATH)
        reconstructed = reconstruct_source(catalog).encode("utf-8")
        if reconstructed != source_raw:
            errors.append("catalog full-text reconstruction differs from source bytes")
        scenario_list = list(iter_scenarios(catalog))
        ids = [item.get("id") for item in scenario_list]
        if len(ids) != TOTAL_SCENARIOS or len(ids) != len(set(ids)):
            errors.append("catalog scenario IDs are not exactly 136 unique values")
        d002 = next((item for item in scenario_list if item.get("id") == "D-002"), None)
        if not isinstance(d002, dict) or d002.get("expected", {}).get("label") != "Expected target behavior":
            errors.append("D-002 must retain its Expected target behavior label")
    except (CatalogError, TypeError, AttributeError):
        errors.append("catalog semantic validation failed: invalid structure")

    try:
        provenance = load_fixed_json(root, SOURCE_MANIFEST_PATH)
        private_locations = []
        private_locations_omitted = False
        for location in private_path_values(provenance):
            if len(private_locations) == 8:
                private_locations_omitted = True
                break
            private_locations.append(location)
        if private_locations:
            finding = (
                "source provenance contains private local path material at "
                + ", ".join(private_locations)
            )
            if private_locations_omitted:
                finding += "; additional locations omitted"
            errors.append(finding)
        archive = provenance.get("research_archive", {})
        member = provenance.get("scenario_member", {})
        baseline = provenance.get("source_baseline", {})
        if archive.get("sha256") != RESEARCH_ARCHIVE_SHA256:
            errors.append("research archive SHA-256 provenance drifted")
        if archive.get("supplied_files_verified") != 7:
            errors.append("research archive verified-file count provenance drifted")
        if member.get("sha256") != SOURCE_SHA256:
            errors.append("scenario member SHA-256 provenance drifted")
        if member.get("archive_member") != RESEARCH_ARCHIVE_MEMBER:
            errors.append("scenario archive member path provenance drifted")
        if (
            baseline.get("repository") != SOURCE_BASELINE_REPOSITORY
            or baseline.get("commit") != SOURCE_BASELINE_COMMIT
            or baseline.get("tree") != SOURCE_BASELINE_TREE
        ):
            errors.append("frozen source repository/commit provenance drifted")
    except (CatalogError, AttributeError):
        errors.append("source provenance validation failed: invalid structure")

    return errors


def validate_contract_schemas(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, expected in (
        (COVERAGE_SCHEMA_PATH, coverage_schema()),
        (RESULTS_SCHEMA_PATH, results_schema()),
    ):
        try:
            observed = load_fixed_json(root, relative)
        except CatalogError as exc:
            errors.append(str(exc))
            continue
        if observed != expected:
            errors.append(f"{relative} differs from its deterministic contract")
    return errors


def validate_coverage(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_fixed_json(root, CATALOG_PATH)
        coverage = load_fixed_json(root, COVERAGE_PATH)
    except CatalogError as exc:
        return [str(exc)]

    try:
        exact_keys(
            coverage,
            {"schema", "catalog", "scenario_count", "entries"},
            set(),
            "target coverage",
        )
    except CatalogError as exc:
        errors.append(str(exc))
    if coverage.get("schema") != "conformance-coverage/v1":
        errors.append("target coverage schema is unsupported")
    expected_reference = {
        "path": CATALOG_PATH,
        "sha256": sha256_bytes(canonical_json_bytes(catalog)),
    }
    if coverage.get("catalog") != expected_reference:
        errors.append("target coverage catalog binding drifted")
    if coverage.get("scenario_count") != TOTAL_SCENARIOS:
        errors.append(f"target coverage scenario_count must be {TOTAL_SCENARIOS}")

    expected_ids = [scenario["id"] for scenario in iter_scenarios(catalog)]
    entries = coverage.get("entries")
    if not isinstance(entries, list):
        errors.append("target coverage entries must be an array")
        return errors
    observed_ids = [
        entry.get("scenario") if isinstance(entry, dict) else None
        for entry in entries
    ]
    if observed_ids != expected_ids:
        errors.append("coverage scenario IDs/order must exactly match the catalog")
    unique_count = (
        len(set(observed_ids))
        if all(isinstance(identifier, str) for identifier in observed_ids)
        else -1
    )
    if len(entries) != TOTAL_SCENARIOS or unique_count != TOTAL_SCENARIOS:
        errors.append("coverage must contain exactly one entry per scenario")

    common = {"scenario", "disposition", "verification_state"}
    for index, entry in enumerate(entries):
        label = f"target coverage entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        scenario_id = entry.get("scenario")
        if entry.get("verification_state") != "not-run":
            errors.append(f"{label} verification_state must remain not-run")

        if scenario_id in {"A-002", "W-008"}:
            try:
                exact_keys(entry, common | {"specialization"}, set(), label)
            except CatalogError as exc:
                errors.append(str(exc))
            if entry.get("disposition") != "target-specialization":
                errors.append(f"{scenario_id} must remain a target-specialization")
            expected_specialization = (
                A002_SPECIALIZATION if scenario_id == "A-002" else W008_SPECIALIZATION
            )
            if entry.get("specialization") != expected_specialization:
                errors.append(f"{scenario_id} target specialization is missing or drifted")
        elif scenario_id == "C-004":
            disposition = entry.get("disposition")
            if disposition == "pending-agreement":
                required = common | {"agreement_issue"}
            elif disposition == "agreement-decision":
                required = common | {"agreement_issue", "agreement_adr"}
            else:
                errors.append(
                    "C-004 must be pending-agreement or a versioned agreement-decision"
                )
                required = common
            try:
                exact_keys(entry, required, set(), label)
            except CatalogError as exc:
                errors.append(str(exc))
            if entry.get("agreement_issue") != C004_AGREEMENT_ISSUE:
                errors.append("C-004 must remain bound to hierarchy agreement Issue 7")
            if disposition == "agreement-decision":
                agreement_adr = entry.get("agreement_adr")
                if not isinstance(agreement_adr, str) or not AGREEMENT_ADR.fullmatch(
                    agreement_adr
                ):
                    errors.append(
                        "C-004 agreement-decision requires a repository-relative agreement ADR"
                    )
                else:
                    try:
                        read_agreement_adr(root, agreement_adr)
                    except CatalogError:
                        errors.append("C-004 agreement ADR cannot be read safely")
        else:
            try:
                exact_keys(entry, common, set(), label)
            except CatalogError as exc:
                errors.append(str(exc))
            if entry.get("disposition") != "planned":
                errors.append(f"{label} disposition must remain planned")
    return errors


def validate_results(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_fixed_json(root, CATALOG_PATH)
        results = load_fixed_json(root, RESULTS_PATH)
    except CatalogError as exc:
        return [str(exc)]
    try:
        exact_keys(
            results,
            {
                "schema",
                "catalog",
                "result_count",
                "results",
                "release_blocked",
            },
            set(),
            "conformance results",
        )
    except CatalogError as exc:
        errors.append(str(exc))
    if results.get("schema") != "conformance-results/v1":
        errors.append("conformance results schema is unsupported")
    expected_reference = {
        "path": CATALOG_PATH,
        "sha256": sha256_bytes(canonical_json_bytes(catalog)),
    }
    if results.get("catalog") != expected_reference:
        errors.append("conformance results catalog binding drifted")
    result_entries = results.get("results")
    if not isinstance(result_entries, list):
        errors.append("conformance results must contain a results array")
    elif results.get("result_count") != len(result_entries):
        errors.append("conformance result_count must match the results array")
    if result_entries != [] or results.get("result_count") != 0:
        errors.append(
            "conformance results must remain empty until checker ownership transfers"
        )
    if results.get("release_blocked") is not True:
        errors.append("conformance results must keep release_blocked true")
    return errors


def validate_render(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_fixed_json(root, CATALOG_PATH)
        expected = render_catalog(catalog).encode("utf-8")
        observed, _text = read_fixed_utf8_lf(root, HUMAN_CATALOG_PATH)
        if observed != expected:
            errors.append("rendered catalog differs from deterministic output")
    except CatalogError as exc:
        errors.append(str(exc))
    return errors


def asset_reference(root: Path, path: str) -> dict[str, str]:
    try:
        value = read_fixed_asset(root, path)
    except CatalogError:
        raise CatalogError(f"cannot hash repository asset: {path}") from None
    return {"path": path, "sha256": sha256_bytes(value)}


def expected_manifest_catalog_section(root: Path) -> dict[str, Any]:
    return {
        "total": TOTAL_SCENARIOS,
        "families": EXPECTED_FAMILY_COUNTS,
        "source": {
            "archive_file": RESEARCH_ARCHIVE_NAME,
            "archive_member": RESEARCH_ARCHIVE_MEMBER,
            "archive_sha256": RESEARCH_ARCHIVE_SHA256,
            **asset_reference(root, SOURCE_PATH),
            "provenance": asset_reference(root, SOURCE_MANIFEST_PATH),
            "baseline_repository": SOURCE_BASELINE_REPOSITORY,
            "baseline_commit": SOURCE_BASELINE_COMMIT,
        },
        "definitions": {
            **asset_reference(root, CATALOG_PATH),
            "schema": asset_reference(root, CATALOG_SCHEMA_PATH),
        },
        "coverage": {
            **asset_reference(root, COVERAGE_PATH),
            "schema": asset_reference(root, COVERAGE_SCHEMA_PATH),
        },
        "result_store": {
            **asset_reference(root, RESULTS_PATH),
            "schema": asset_reference(root, RESULTS_SCHEMA_PATH),
            "result_count": 0,
        },
        "human_view": asset_reference(root, HUMAN_CATALOG_PATH),
        "provenance_adr": asset_reference(root, PROVENANCE_ADR_PATH),
        "tool": asset_reference(root, TOOL_PATH),
        "verification_state": "not-run",
    }


def validate_phase_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = load_fixed_json(root, PHASE_MANIFEST_PATH, canonical=False)
        expected = expected_manifest_catalog_section(root)
    except CatalogError as exc:
        errors.append(str(exc))
        return errors
    if manifest.get("release_blocked") is not True:
        errors.append("Phase conformance manifest must keep release_blocked true")
    if manifest.get("results") != []:
        errors.append("Phase 0 compatibility results sentinel must remain empty")
    research = manifest.get("research_pack")
    if not isinstance(research, dict):
        errors.append("Phase conformance manifest research_pack must be an object")
    else:
        if research.get("zip_sha256") != RESEARCH_ARCHIVE_SHA256:
            errors.append("Phase conformance manifest research ZIP hash drifted")
        if research.get("conformance_catalog_sha256") != SOURCE_SHA256:
            errors.append("Phase conformance manifest source hash drifted")
    if manifest.get("scenario_catalog") != expected:
        errors.append("Phase conformance manifest catalog asset/hash links drifted")
    return errors


def validate_advisory_boundary(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        _raw, text = read_fixed_utf8_lf(root, PROVENANCE_ADR_PATH)
    except CatalogError as exc:
        return [str(exc)]
    required = [
        RESEARCH_ARCHIVE_SHA256,
        SOURCE_SHA256,
        "advisory",
        "release_blocked",
        "C-004",
        "A-002",
        "W-008",
    ]
    for token in required:
        if token not in text:
            errors.append(f"catalog provenance ADR is missing {token!r}")
    if PRIVATE_PATH.search(text):
        errors.append("catalog provenance ADR contains a private local path")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    validators = (
        ("import artifact validation", validate_import_artifacts),
        ("contract schema validation", validate_contract_schemas),
        ("coverage validation", validate_coverage),
        ("results validation", validate_results),
        ("render validation", validate_render),
        ("advisory boundary validation", validate_advisory_boundary),
        ("Phase manifest validation", validate_phase_manifest),
    )
    for label, validator in validators:
        try:
            errors.extend(validator(root))
        except Exception:
            errors.append(f"{label} failed: invalid structure")
    return errors


def source_for_import(root: Path) -> str:
    raw, text = read_fixed_utf8_lf(root, SOURCE_PATH)
    if sha256_bytes(raw) != SOURCE_SHA256:
        raise CatalogError("scenario source SHA-256 differs from the reviewed member")
    if len(raw) != SOURCE_BYTES or raw.count(b"\n") != SOURCE_LINES:
        raise CatalogError("scenario source size or line count differs from provenance")
    return text


def run_import(root: Path, check_only: bool) -> int:
    try:
        artifacts = imported_artifacts(source_for_import(root))
    except CatalogError as exc:
        print(f"conformance catalog import: FAIL\n- {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "conformance catalog import: FAIL\n- internal failure was suppressed",
            file=sys.stderr,
        )
        return 1
    differences: list[str] = []
    for relative, value in artifacts.items():
        try:
            expected = canonical_json_bytes(value)
        except CatalogError as exc:
            differences.append(str(exc))
            break
        if check_only:
            try:
                observed = read_managed_output(root, relative)
            except CatalogError as exc:
                differences.append(str(exc))
                continue
            except Exception:
                differences.append("managed output read failure was suppressed")
                continue
            if observed != expected:
                differences.append(f"{relative} differs from deterministic import output")
        else:
            try:
                write_if_changed(root, relative, expected)
            except CatalogError as exc:
                differences.append(str(exc))
                break
            except Exception:
                differences.append("managed output write failure was suppressed")
                break
    if differences:
        print("conformance catalog import: FAIL", file=sys.stderr)
        for difference in differences:
            print(f"- {difference}", file=sys.stderr)
        return 1
    mode = "check" if check_only else "write"
    print(f"conformance catalog import: PASS ({mode}, {TOTAL_SCENARIOS} scenarios)")
    return 0


def run_render(root: Path, check_only: bool) -> int:
    try:
        catalog = load_fixed_json(root, CATALOG_PATH)
        expected = render_catalog(catalog).encode("utf-8")
    except CatalogError as exc:
        print(f"conformance catalog render: FAIL\n- {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "conformance catalog render: FAIL\n- internal failure was suppressed",
            file=sys.stderr,
        )
        return 1
    if check_only:
        try:
            observed = read_managed_output(root, HUMAN_CATALOG_PATH)
        except CatalogError as exc:
            print(f"conformance catalog render: FAIL\n- {exc}", file=sys.stderr)
            return 1
        except Exception:
            print(
                "conformance catalog render: FAIL\n"
                "- managed output read failure was suppressed",
                file=sys.stderr,
            )
            return 1
        if observed != expected:
            print(
                "conformance catalog render: FAIL\n"
                "- rendered catalog differs from deterministic output",
                file=sys.stderr,
            )
            return 1
    else:
        try:
            write_if_changed(root, HUMAN_CATALOG_PATH, expected)
        except CatalogError as exc:
            print(f"conformance catalog render: FAIL\n- {exc}", file=sys.stderr)
            return 1
        except Exception:
            print(
                "conformance catalog render: FAIL\n"
                "- managed output write failure was suppressed",
                file=sys.stderr,
            )
            return 1
    mode = "check" if check_only else "write"
    print(f"conformance catalog render: PASS ({mode})")
    return 0


def run_check(root: Path) -> int:
    try:
        errors = validate_repository(root)
    except Exception:
        errors = ["repository validation failure was suppressed"]
    if errors:
        print("conformance catalog: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "conformance catalog: PASS "
        f"({TOTAL_SCENARIOS} definitions, 0 results, release blocked)"
    )
    return 0


def add_common_options(parser: argparse.ArgumentParser, *, check: bool) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    if check:
        parser.add_argument(
            "--check",
            action="store_true",
            help="compare without writing",
        )


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser("import", help="import the frozen source")
    add_common_options(import_parser, check=True)
    render_parser = subparsers.add_parser("render", help="render human Markdown")
    add_common_options(render_parser, check=True)
    check_parser = subparsers.add_parser("check", help="validate all catalog assets")
    add_common_options(check_parser, check=False)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        root = arguments.root.absolute()
    except OSError:
        print(
            "conformance catalog: FAIL\n- repository root cannot be normalized",
            file=sys.stderr,
        )
        return 1
    if arguments.command == "import":
        return run_import(root, arguments.check)
    if arguments.command == "render":
        return run_render(root, arguments.check)
    return run_check(root)


if __name__ == "__main__":
    raise SystemExit(main())
