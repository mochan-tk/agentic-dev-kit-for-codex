#!/usr/bin/env python3
"""Replay the accepted Phase 1 checker from its exact immutable Git tree."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = "tests/conformance/phase1-accepted-snapshot.v1.json"
ACCEPTED_COMMIT = "36c7eabecf7a56eb2a1c2c8f2c4d8fcb371c31c2"
ACCEPTED_TREE = "1c1f46ad20dd289a713663c84eaf1dbb62840deb"
ACCEPTED_PARENTS = [
    "509362e6e12cf0160e58853b0d6c0b6871aa895c",
    "68107c68383dbd2fd046f4c643c2e362e9a176ea",
]
HISTORICAL_CHECKER_PATH = ".github/scripts/check-phase1-acceptance.py"
HISTORICAL_CHECKER_BLOB = "9e8cccbc824efbb11756ac72c5e1e5ec8726ef4d"
HISTORICAL_CHECKER_SHA256 = (
    "fd0bee66f857601b352cee62eb0f71f2a7f33b507bdb31c5f84e80cbfd64a9de"
)
HISTORICAL_CHECKER_SIZE = 67_121
HISTORICAL_SUCCESS_STDOUT = (
    "phase1-acceptance: PASS — T01-T09 evidence, K01-K20 disposition, "
    "136 not-run scenario records, and the release blocker are exact\n"
).encode("utf-8")
EXPECTED_PATH_COUNT = 92
EXPECTED_TOTAL_BYTES = 1_561_147

MAX_SNAPSHOT_BYTES = 131_072
MAX_PATH_BYTES = 512
MAX_TREE_OUTPUT_BYTES = 262_144
MAX_COMMIT_OUTPUT_BYTES = 262_144
MAX_PATHS = 256
MAX_FILE_BYTES = 262_144
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 2_048
MAX_JSON_STRING_BYTES = 1_024
MAX_JSON_INTEGER = (1 << 63) - 1
MAX_FINDINGS = 128
MAX_FINDING_BYTES = 1_024
MAX_CLI_FINDINGS_BYTES = 262_144
GIT_TIMEOUT_SECONDS = 15.0
CHECKER_TIMEOUT_SECONDS = 60.0
MAX_CHECKER_STDOUT_BYTES = 32_768
MAX_CHECKER_STDERR_BYTES = 32_768
TERMINATION_GRACE_SECONDS = 0.5

SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CommandResult(NamedTuple):
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_overflow: bool = False
    launch_error: str | None = None
    process_group_leak: bool = False


def _bounded_findings(errors: list[str]) -> list[str]:
    bounded: list[str] = []
    total = 0
    for raw in errors[: MAX_FINDINGS + 1]:
        encoded = str(raw).encode("utf-8", errors="replace")[:MAX_FINDING_BYTES]
        finding = encoded.decode("utf-8", errors="replace")
        projected = total + len(finding.encode("utf-8")) + 3
        if projected > MAX_CLI_FINDINGS_BYTES or len(bounded) >= MAX_FINDINGS:
            break
        bounded.append(finding)
        total = projected
    if len(errors) > len(bounded) and len(bounded) < MAX_FINDINGS:
        bounded.append("additional findings were suppressed by the bounded reporter")
    return bounded


def filesystem_capability_errors() -> list[str]:
    errors: list[str] = []
    if not isinstance(getattr(os, "O_NOFOLLOW", None), int) or os.O_NOFOLLOW == 0:
        errors.append("required O_NOFOLLOW capability is unavailable")
    if not isinstance(getattr(os, "O_DIRECTORY", None), int) or os.O_DIRECTORY == 0:
        errors.append("required O_DIRECTORY capability is unavailable")
    supports_dir_fd = getattr(os, "supports_dir_fd", frozenset())
    for function in (os.open, os.mkdir, os.stat, os.unlink):
        if function not in supports_dir_fd:
            errors.append(f"required dir_fd capability is unavailable for {function.__name__}")
    supports_follow = getattr(os, "supports_follow_symlinks", frozenset())
    if os.stat not in supports_follow:
        errors.append("required follow_symlinks=False capability is unavailable for stat")
    return _bounded_findings(errors)


def require_filesystem_capabilities() -> None:
    errors = filesystem_capability_errors()
    if errors:
        raise RuntimeError("; ".join(errors))


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_snapshot_digest(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _private_environment(*, home: Path | None = None, temp: Path | None = None) -> dict[str, str]:
    environment = {
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
        "no_proxy": "",
    }
    if home is not None:
        environment["HOME"] = os.fspath(home)
    if temp is not None:
        environment["TMPDIR"] = os.fspath(temp)
    return environment


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _wait_for_process_group_exit(
    group_id: int,
    deadline: float,
    process: subprocess.Popen[bytes],
) -> bool:
    while time.monotonic() < deadline:
        process.poll()
        if not _process_group_exists(group_id):
            return True
        time.sleep(0.01)
    process.poll()
    return not _process_group_exists(group_id)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    group_id = process.pid
    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if not _wait_for_process_group_exit(
        group_id, time.monotonic() + TERMINATION_GRACE_SECONDS, process
    ):
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _wait_for_process_group_exit(
            group_id, time.monotonic() + TERMINATION_GRACE_SECONDS, process
        )
    if process.poll() is None:
        try:
            process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass


def run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    environment: dict[str, str],
    stdin_fd: int | None = None,
) -> CommandResult:
    """Run one shell-free process with bounded pipes and group termination."""

    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL if stdin_fd is None else stdin_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(127, b"", b"", launch_error=type(exc).__name__)

    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout_limit))
    selector.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr_limit))
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    overflow = False
    try:
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _terminate_process_group(process)
                break
            events = selector.select(min(remaining, 0.1))
            if not selector.get_map() and process.poll() is None:
                time.sleep(min(remaining, 0.01))
            for key, _ in events:
                label, limit = key.data
                try:
                    chunk = os.read(key.fileobj.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                sink = captured[label]
                remaining_bytes = max(0, limit - len(sink))
                sink.extend(chunk[:remaining_bytes])
                if len(chunk) > remaining_bytes:
                    overflow = True
                    _terminate_process_group(process)
                    break
            if overflow:
                break
    finally:
        selector.close()
        for pipe in (process.stdout, process.stderr):
            try:
                pipe.close()
            except OSError:
                pass

    process_group_leak = False
    if timed_out or overflow:
        _terminate_process_group(process)
    elif process.poll() is not None and _process_group_exists(process.pid):
        process_group_leak = True
        _terminate_process_group(process)
    try:
        returncode = process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        returncode = process.poll() if process.poll() is not None else 124
    return CommandResult(
        returncode,
        bytes(captured["stdout"]),
        bytes(captured["stderr"]),
        timed_out=timed_out,
        output_overflow=overflow,
        process_group_leak=process_group_leak,
    )


def git_command(
    root: Path,
    *arguments: str,
    stdout_limit: int = MAX_COMMIT_OUTPUT_BYTES,
) -> CommandResult:
    """Run bounded read-only Git with replacement objects disabled."""

    return run_bounded(
        ["git", "--no-replace-objects", "-C", os.fspath(root), *arguments],
        cwd=root,
        timeout_seconds=GIT_TIMEOUT_SECONDS,
        stdout_limit=stdout_limit,
        stderr_limit=16_384,
        environment=_private_environment(),
    )


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    try:
        if len(value.encode("utf-8")) > MAX_PATH_BYTES:
            return None
    except UnicodeEncodeError:
        return None
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.as_posix() != value:
        return None
    if any(part in {"", ".", "..", ".git"} for part in candidate.parts):
        return None
    if unicodedata.normalize("NFC", value) != value:
        return None
    return value


def _open_bound_regular(
    root: Path,
    relative: str,
    maximum: int,
    *,
    expected_mode: int | None = None,
    expected_parent_mode: int | None = None,
) -> tuple[int, bytes]:
    """Open, read, rebind, and return one pinned regular-file descriptor."""

    require_filesystem_capabilities()
    safe = _safe_relative_path(relative)
    if safe is None:
        raise ValueError("unsafe input path")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    descriptors = [root_fd]
    bindings: list[tuple[int, str, int]] = []
    file_descriptor: int | None = None
    keep_file = False
    try:
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("repository root is not a directory")
        if (
            expected_parent_mode is not None
            and stat.S_IMODE(root_stat.st_mode) != expected_parent_mode
        ):
            raise ValueError("repository root has an unsafe mode")
        current = root_fd
        parts = PurePosixPath(safe).parts
        for component in parts[:-1]:
            parent_fd = current
            current = os.open(component, directory_flags, dir_fd=parent_fd)
            bindings.append((parent_fd, component, current))
            descriptors.append(current)
            parent_details = os.fstat(current)
            if not stat.S_ISDIR(parent_details.st_mode):
                raise ValueError("input parent is not a directory")
            if (
                expected_parent_mode is not None
                and stat.S_IMODE(parent_details.st_mode) != expected_parent_mode
            ):
                raise ValueError("input parent has an unsafe mode")
        file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        file_descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("input is not a regular file")
        if expected_mode is not None and stat.S_IMODE(before.st_mode) != expected_mode:
            raise ValueError("input has an unsafe mode")
        if before.st_size > maximum:
            raise ValueError("input exceeds the byte limit")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(file_descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > maximum:
            raise ValueError("input exceeds the byte limit")
        after = os.fstat(file_descriptor)
        rebound = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mode) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mode,
        ) or (after.st_dev, after.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise ValueError("input binding changed during read")
        for parent_fd, component, child_fd in bindings:
            opened = os.fstat(child_fd)
            rebound_parent = os.stat(
                component,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if (opened.st_dev, opened.st_ino, opened.st_mode) != (
                rebound_parent.st_dev,
                rebound_parent.st_ino,
                rebound_parent.st_mode,
            ):
                raise ValueError("input parent binding changed during read")
        root_rebound = os.stat(root, follow_symlinks=False)
        if (root_stat.st_dev, root_stat.st_ino, root_stat.st_mode) != (
            root_rebound.st_dev,
            root_rebound.st_ino,
            root_rebound.st_mode,
        ):
            raise ValueError("repository root binding changed during read")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        keep_file = True
        return file_descriptor, payload
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        if file_descriptor is not None and not keep_file:
            try:
                os.close(file_descriptor)
            except OSError:
                pass


def read_regular_bytes(root: Path, relative: str, maximum: int) -> bytes:
    """Read a fixed repository input through descriptor-relative no-follow opens."""

    descriptor, payload = _open_bound_regular(root, relative, maximum)
    try:
        return payload
    finally:
        os.close(descriptor)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def _reject_float(value: str) -> None:
    raise ValueError(f"floating-point JSON number is not allowed: {value[:32]!r}")


def _bounded_int(value: str) -> int:
    if len(value) > 20:
        raise ValueError("JSON integer exceeds the lexical bound")
    parsed = int(value)
    if abs(parsed) > MAX_JSON_INTEGER:
        raise ValueError("JSON integer exceeds the numeric bound")
    return parsed


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def validate_json_limits(value: Any) -> list[str]:
    errors: list[str] = []
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            errors.append("accepted snapshot JSON exceeds the node limit")
            break
        if depth > MAX_JSON_DEPTH:
            errors.append("accepted snapshot JSON exceeds the depth limit")
            break
        if isinstance(current, dict):
            if len(current) > MAX_JSON_NODES:
                errors.append("accepted snapshot JSON object exceeds the node limit")
                break
            for index, (key, child) in enumerate(current.items()):
                if index >= MAX_JSON_NODES:
                    errors.append("accepted snapshot JSON object exceeds the node limit")
                    break
                if not isinstance(key, str):
                    errors.append("accepted snapshot JSON has a non-string object key")
                    continue
                try:
                    key_size = len(key.encode("utf-8"))
                except UnicodeEncodeError:
                    errors.append("accepted snapshot JSON key is not valid Unicode")
                    continue
                if key_size > MAX_JSON_STRING_BYTES:
                    errors.append("accepted snapshot JSON key exceeds the string limit")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > MAX_JSON_NODES:
                errors.append("accepted snapshot JSON list exceeds the node limit")
                break
            stack.extend((child, depth + 1) for child in reversed(current))
        elif isinstance(current, str):
            try:
                string_size = len(current.encode("utf-8"))
            except UnicodeEncodeError:
                errors.append("accepted snapshot JSON string is not valid Unicode")
                continue
            if string_size > MAX_JSON_STRING_BYTES:
                errors.append("accepted snapshot JSON string exceeds the string limit")
        elif isinstance(current, bool) or current is None:
            continue
        elif isinstance(current, int):
            if abs(current) > MAX_JSON_INTEGER:
                errors.append("accepted snapshot JSON integer exceeds the numeric bound")
        elif isinstance(current, float):
            errors.append("accepted snapshot JSON floating-point values are not allowed")
        else:
            errors.append("accepted snapshot JSON contains an unsupported value type")
    return _bounded_findings(errors)


def load_snapshot(root: Path) -> dict[str, Any]:
    require_filesystem_capabilities()
    raw = read_regular_bytes(root, SNAPSHOT_PATH, MAX_SNAPSHOT_BYTES)
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_bounded_int,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"invalid accepted-snapshot JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError("accepted-snapshot JSON must be an object")
    return payload


def snapshot_files(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files")
    if not isinstance(files, list):
        return []
    return [item for item in files[: MAX_PATHS + 1] if isinstance(item, dict)]


def validate_snapshot_payload(payload: dict[str, Any]) -> list[str]:
    errors = validate_json_limits(payload)
    if errors:
        return errors
    if not isinstance(payload, dict):
        return ["accepted snapshot JSON must be an object"]
    required = {
        "schema",
        "accepted_commit",
        "accepted_tree",
        "accepted_parents",
        "path_count",
        "total_bytes",
        "historical_checker",
        "files",
        "manifest_sha256",
    }
    if set(payload) != required:
        errors.append("accepted snapshot has unsupported or missing top-level fields")
    if payload.get("schema") != "phase1-accepted-snapshot/v1":
        errors.append("accepted snapshot schema drifted")
    if payload.get("accepted_commit") != ACCEPTED_COMMIT:
        errors.append("accepted Phase 1 commit binding drifted")
    if payload.get("accepted_tree") != ACCEPTED_TREE:
        errors.append("accepted Phase 1 tree binding drifted")
    if payload.get("accepted_parents") != ACCEPTED_PARENTS:
        errors.append("accepted Phase 1 ordered parent binding drifted")
    if payload.get("path_count") != EXPECTED_PATH_COUNT:
        errors.append("accepted Phase 1 path count binding drifted")
    if payload.get("total_bytes") != EXPECTED_TOTAL_BYTES:
        errors.append("accepted Phase 1 total byte binding drifted")
    files = payload.get("files")
    if not isinstance(files, list):
        errors.append("accepted snapshot files must be a list")
        files = []
    if len(files) > MAX_PATHS:
        errors.append("accepted snapshot exceeds the path-count safety limit")
    if len(files) != EXPECTED_PATH_COUNT:
        errors.append("accepted snapshot does not contain the complete accepted tree")

    recorded_manifest = payload.get("manifest_sha256")
    if not isinstance(recorded_manifest, str) or not SHA256.fullmatch(recorded_manifest):
        errors.append("accepted snapshot manifest digest is invalid")
    elif len(files) > MAX_PATHS:
        errors.append(
            "accepted snapshot manifest digest was not evaluated past the path-count limit"
        )
    else:
        try:
            actual_manifest = canonical_snapshot_digest(payload)
        except (TypeError, ValueError, RecursionError, UnicodeError):
            errors.append("accepted snapshot manifest cannot be canonically encoded")
        else:
            if recorded_manifest != actual_manifest:
                errors.append("accepted snapshot manifest digest mismatch")

    paths: list[str] = []
    collision_keys: list[str] = []
    total = 0
    for index, item in enumerate(files[: MAX_PATHS + 1]):
        if not isinstance(item, dict):
            errors.append(f"accepted snapshot files[{index}] must be an object")
            continue
        if set(item) != {"path", "mode", "blob", "sha256", "size"}:
            errors.append(f"accepted snapshot files[{index}] fields drifted")
        path = _safe_relative_path(item.get("path"))
        if path is None:
            errors.append(f"accepted snapshot files[{index}] path is unsafe")
            continue
        paths.append(path)
        collision_keys.append(unicodedata.normalize("NFC", path).casefold())
        if item.get("mode") != "100644":
            errors.append(f"accepted snapshot path has an unsafe mode: {path}")
        blob = item.get("blob")
        if not isinstance(blob, str) or not SHA1.fullmatch(blob):
            errors.append(f"accepted snapshot path has an invalid blob: {path}")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            errors.append(f"accepted snapshot path has an invalid SHA-256: {path}")
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"accepted snapshot path has an invalid size: {path}")
        else:
            total += size
            if size > MAX_FILE_BYTES:
                errors.append(f"accepted snapshot path exceeds the file-size limit: {path}")
    if paths != sorted(paths):
        errors.append("accepted snapshot paths must be UTF-8 sorted")
    if len(paths) != len(set(paths)):
        errors.append("accepted snapshot paths must be unique")
    if len(collision_keys) != len(set(collision_keys)):
        errors.append("accepted snapshot paths have a case or Unicode collision")
    if total > MAX_TOTAL_BYTES:
        errors.append("accepted snapshot exceeds the total-byte safety limit")
    if total != EXPECTED_TOTAL_BYTES:
        errors.append("accepted snapshot file sizes do not match the accepted total")

    checker = payload.get("historical_checker")
    expected_checker = {
        "path": HISTORICAL_CHECKER_PATH,
        "mode": "100644",
        "blob": HISTORICAL_CHECKER_BLOB,
        "sha256": HISTORICAL_CHECKER_SHA256,
        "size": HISTORICAL_CHECKER_SIZE,
    }
    if checker != expected_checker:
        errors.append("historical Phase 1 checker binding drifted")
    matching = [item for item in snapshot_files(payload) if item.get("path") == HISTORICAL_CHECKER_PATH]
    if matching != [expected_checker]:
        errors.append("historical Phase 1 checker is not exactly bound in the tree manifest")
    return _bounded_findings(errors)


def _git_failure(result: CommandResult) -> bool:
    return (
        result.returncode != 0
        or result.timed_out
        or result.output_overflow
        or result.launch_error is not None
        or result.process_group_leak
    )


def _parse_commit_binding(raw: bytes) -> tuple[str | None, list[str]]:
    tree: str | None = None
    parents: list[str] = []
    for line in raw.splitlines():
        if not line:
            break
        if line.startswith(b"tree "):
            try:
                tree = line[5:].decode("ascii")
            except UnicodeError:
                tree = None
        elif line.startswith(b"parent "):
            try:
                parents.append(line[7:].decode("ascii"))
            except UnicodeError:
                parents.append("invalid")
    return tree, parents


def _parse_tree(raw: bytes, errors: list[str]) -> dict[str, tuple[str, str]]:
    observed: dict[str, tuple[str, str]] = {}
    records = [record for record in raw.split(b"\0") if record]
    if len(records) > MAX_PATHS:
        errors.append("accepted Git tree exceeds the path-count safety limit")
        return observed
    collision_keys: set[str] = set()
    for record in records:
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, blob = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            errors.append("accepted Git tree contains an unclassifiable entry")
            continue
        safe = _safe_relative_path(path)
        if safe is None:
            errors.append("accepted Git tree contains an unsafe path")
            continue
        collision = unicodedata.normalize("NFC", safe).casefold()
        if safe in observed or collision in collision_keys:
            errors.append("accepted Git tree contains a duplicate, case, or Unicode collision")
            continue
        collision_keys.add(collision)
        if object_type != "blob" or mode != "100644" or not SHA1.fullmatch(blob):
            errors.append(f"accepted Git tree contains an unsafe entry: {safe}")
            continue
        observed[safe] = (mode, blob)
    return observed


def verify_git_snapshot(
    root: Path, payload: dict[str, Any]
) -> tuple[list[str], dict[str, bytes]]:
    """Verify exact immutable objects and return only fully bounded blob bytes."""

    errors: list[str] = []
    commit = git_command(root, "cat-file", "commit", ACCEPTED_COMMIT)
    if _git_failure(commit):
        return ["accepted Phase 1 commit object is missing or unreadable"], {}
    tree, parents = _parse_commit_binding(commit.stdout)
    if tree != ACCEPTED_TREE:
        errors.append("accepted Phase 1 commit resolves to the wrong tree")
    if parents != ACCEPTED_PARENTS:
        errors.append("accepted Phase 1 commit has the wrong ordered parents")

    tree_result = git_command(
        root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        ACCEPTED_TREE,
        stdout_limit=MAX_TREE_OUTPUT_BYTES,
    )
    if _git_failure(tree_result):
        errors.append("accepted Phase 1 tree is missing, unbounded, or unreadable")
        return errors, {}
    observed = _parse_tree(tree_result.stdout, errors)
    expected = {
        item["path"]: (item["mode"], item["blob"])
        for item in snapshot_files(payload)
        if isinstance(item.get("path"), str)
    }
    if observed != expected:
        errors.append("accepted Git tree entries differ from the complete snapshot manifest")
    if errors:
        return _bounded_findings(errors), {}

    contents: dict[str, bytes] = {}
    total = 0
    for item in snapshot_files(payload):
        path = item["path"]
        expected_size = item["size"]
        size_result = git_command(root, "cat-file", "-s", item["blob"], stdout_limit=64)
        if _git_failure(size_result):
            errors.append(f"accepted Git blob size is unreadable: {path}")
            continue
        try:
            actual_size = int(size_result.stdout.strip())
        except ValueError:
            errors.append(f"accepted Git blob size is invalid: {path}")
            continue
        if actual_size != expected_size or actual_size > MAX_FILE_BYTES:
            errors.append(f"accepted Git blob size mismatch or excess: {path}")
            continue
        total += actual_size
        if total > MAX_TOTAL_BYTES:
            errors.append("accepted Git blobs exceed the total-byte safety limit")
            break
        blob_result = git_command(
            root,
            "cat-file",
            "blob",
            item["blob"],
            stdout_limit=expected_size + 1,
        )
        if _git_failure(blob_result) or len(blob_result.stdout) != expected_size:
            errors.append(f"accepted Git blob is missing, unbounded, or truncated: {path}")
            continue
        digest = hashlib.sha256(blob_result.stdout).hexdigest()
        if digest != item["sha256"]:
            errors.append(f"accepted Git blob digest mismatch: {path}")
            continue
        contents[path] = blob_result.stdout
    if total != EXPECTED_TOTAL_BYTES:
        errors.append("accepted Git blob bytes do not match the complete tree total")
    if len(contents) != EXPECTED_PATH_COUNT:
        errors.append("accepted Git blob extraction is incomplete")
    return _bounded_findings(errors), contents


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    require_filesystem_capabilities()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    details = os.fstat(descriptor)
    if not stat.S_ISDIR(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o700:
        os.close(descriptor)
        raise ValueError("snapshot extraction parent is not a private regular directory")
    return descriptor


def materialize_snapshot(
    destination: Path,
    payload: dict[str, Any],
    contents: dict[str, bytes],
) -> None:
    """Extract verified blobs through mkdirat/openat without following links."""

    require_filesystem_capabilities()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(destination, flags)
    try:
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o700:
            raise ValueError("snapshot extraction root must be a private 0700 directory")
        for item in snapshot_files(payload):
            path = item["path"]
            if path not in contents:
                raise ValueError(f"missing verified blob for extraction: {path}")
            descriptors = [os.dup(root_fd)]
            bindings: list[tuple[int, str, int]] = []
            try:
                parts = PurePosixPath(path).parts
                for component in parts[:-1]:
                    parent_fd = descriptors[-1]
                    next_fd = _open_or_create_directory(parent_fd, component)
                    bindings.append((parent_fd, component, next_fd))
                    descriptors.append(next_fd)
                current = descriptors[-1]
                file_flags = (
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW
                )
                descriptor = os.open(parts[-1], file_flags, 0o600, dir_fd=current)
                try:
                    os.fchmod(descriptor, 0o600)
                    view = memoryview(contents[path])
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise OSError("short write")
                        view = view[written:]
                    os.fsync(descriptor)
                    details = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(details.st_mode)
                        or stat.S_IMODE(details.st_mode) != 0o600
                        or details.st_size != item["size"]
                    ):
                        raise ValueError(f"unsafe extracted file state: {path}")
                    rebound = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
                    if (details.st_dev, details.st_ino) != (rebound.st_dev, rebound.st_ino):
                        raise ValueError(f"snapshot extraction binding changed: {path}")
                finally:
                    os.close(descriptor)
                for parent_fd, component, child_fd in bindings:
                    opened = os.fstat(child_fd)
                    rebound = os.stat(
                        component,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                    if (opened.st_dev, opened.st_ino) != (
                        rebound.st_dev,
                        rebound.st_ino,
                    ):
                        raise ValueError(
                            f"snapshot extraction parent binding changed: {path}"
                        )
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)
        rebound_root = os.stat(destination, follow_symlinks=False)
        if (root_stat.st_dev, root_stat.st_ino) != (
            rebound_root.st_dev,
            rebound_root.st_ino,
        ):
            raise ValueError("snapshot extraction root binding changed")
    finally:
        os.close(root_fd)


def validate_materialized_snapshot(
    repository: Path,
    payload: dict[str, Any],
) -> list[str]:
    """Re-read every extracted file through no-follow descriptors after extraction."""

    errors: list[str] = []
    for item in snapshot_files(payload):
        descriptor: int | None = None
        try:
            descriptor, contents = _open_bound_regular(
                repository,
                item["path"],
                item["size"],
                expected_mode=0o600,
                expected_parent_mode=0o700,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(
                f"cannot revalidate extracted Phase 1 path {item['path']}: {exc}"
            )
            continue
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if len(contents) != item["size"]:
            errors.append(f"extracted Phase 1 path size drifted: {item['path']}")
        elif hashlib.sha256(contents).hexdigest() != item["sha256"]:
            errors.append(f"extracted Phase 1 path digest drifted: {item['path']}")
        if len(errors) >= MAX_FINDINGS:
            break
    return _bounded_findings(errors)


PINNED_CHECKER_BOOTSTRAP = (
    "import os,sys\n"
    "path=os.path.abspath('.github/scripts/check-phase1-acceptance.py')\n"
    "source=sys.stdin.buffer.read(67122)\n"
    "if len(source)!=67121: raise SystemExit(97)\n"
    "scope={'__name__':'__main__','__file__':path,'__package__':None,"
    "'__cached__':None}\n"
    "exec(compile(source,path,'exec'),scope,scope)\n"
)


def _anonymous_pinned_bytes(directory: Path, contents: bytes) -> int:
    """Copy verified bytes to one unlinked, read-only descriptor."""

    require_filesystem_capabilities()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(directory, directory_flags)
    writer: int | None = None
    reader: int | None = None
    name = ".phase1-checker-pinned-input"
    try:
        directory_details = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(directory_details.st_mode)
            or stat.S_IMODE(directory_details.st_mode) != 0o700
        ):
            raise ValueError("checker pin directory must be private 0700")
        writer = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        view = memoryview(contents)
        while view:
            written = os.write(writer, view)
            if written <= 0:
                raise OSError("short checker pin write")
            view = view[written:]
        os.fsync(writer)
        os.fchmod(writer, 0o400)
        writer_details = os.fstat(writer)
        reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        reader_details = os.fstat(reader)
        rebound = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(reader_details.st_mode)
            or stat.S_IMODE(reader_details.st_mode) != 0o400
            or reader_details.st_size != len(contents)
            or (writer_details.st_dev, writer_details.st_ino)
            != (reader_details.st_dev, reader_details.st_ino)
            or (reader_details.st_dev, reader_details.st_ino)
            != (rebound.st_dev, rebound.st_ino)
        ):
            raise ValueError("checker pin binding or size drifted")
        pinned_chunks: list[bytes] = []
        remaining = len(contents) + 1
        while remaining:
            chunk = os.read(reader, min(65_536, remaining))
            if not chunk:
                break
            pinned_chunks.append(chunk)
            remaining -= len(chunk)
        if b"".join(pinned_chunks) != contents:
            raise ValueError("checker pin content drifted")
        os.unlink(name, dir_fd=directory_fd)
        os.close(writer)
        writer = None
        os.lseek(reader, 0, os.SEEK_SET)
        result = reader
        reader = None
        return result
    finally:
        if writer is not None:
            os.close(writer)
        if reader is not None:
            os.close(reader)
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def run_historical_checker(repository: Path, home: Path, temp: Path) -> list[str]:
    source_descriptor: int | None = None
    pinned_descriptor: int | None = None
    try:
        source_descriptor, checker_bytes = _open_bound_regular(
            repository,
            HISTORICAL_CHECKER_PATH,
            HISTORICAL_CHECKER_SIZE,
            expected_mode=0o600,
            expected_parent_mode=0o700,
        )
        if (
            len(checker_bytes) != HISTORICAL_CHECKER_SIZE
            or hashlib.sha256(checker_bytes).hexdigest()
            != HISTORICAL_CHECKER_SHA256
        ):
            return ["historical Phase 1 checker pin digest or size drifted"]
        pinned_descriptor = _anonymous_pinned_bytes(temp, checker_bytes)
        os.close(source_descriptor)
        source_descriptor = None
        result = run_bounded(
            ["python3", "-I", "-c", PINNED_CHECKER_BOOTSTRAP],
            cwd=repository,
            timeout_seconds=CHECKER_TIMEOUT_SECONDS,
            stdout_limit=MAX_CHECKER_STDOUT_BYTES,
            stderr_limit=MAX_CHECKER_STDERR_BYTES,
            environment=_private_environment(home=home, temp=temp),
            stdin_fd=pinned_descriptor,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return [f"historical Phase 1 checker pin validation failed: {exc}"]
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        if pinned_descriptor is not None:
            os.close(pinned_descriptor)
    if result.launch_error is not None:
        return ["historical Phase 1 checker could not be launched"]
    if result.timed_out:
        return ["historical Phase 1 checker exceeded its timeout"]
    if result.output_overflow:
        return ["historical Phase 1 checker exceeded its output limits"]
    if result.process_group_leak:
        return ["historical Phase 1 checker left a descendant process group"]
    if result.returncode != 0:
        return [f"historical Phase 1 checker failed with exit code {result.returncode}"]
    if result.stdout != HISTORICAL_SUCCESS_STDOUT or result.stderr:
        return ["historical Phase 1 checker did not emit its exact bounded success output"]
    return []


def verified_snapshot_contents(
    root: Path, payload: dict[str, Any] | None = None
) -> tuple[dict[str, Any] | None, dict[str, bytes], list[str]]:
    errors = filesystem_capability_errors()
    if errors:
        return payload, {}, errors
    if payload is None:
        try:
            payload = load_snapshot(root)
        except (OSError, RuntimeError, ValueError) as exc:
            return None, {}, [f"cannot read accepted Phase 1 snapshot: {exc}"]
    errors.extend(validate_snapshot_payload(payload))
    if errors:
        return payload, {}, _bounded_findings(errors)
    object_errors, contents = verify_git_snapshot(root, payload)
    errors.extend(object_errors)
    return payload, contents, _bounded_findings(errors)


def validate_historical_repository(
    root: Path = ROOT, payload: dict[str, Any] | None = None
) -> list[str]:
    """Validate, safely reconstruct, and replay the accepted Phase 1 tree."""

    capability_errors = filesystem_capability_errors()
    if capability_errors:
        return capability_errors
    payload, contents, errors = verified_snapshot_contents(root, payload)
    if errors or payload is None:
        return errors
    private = Path(tempfile.mkdtemp(prefix="phase1-accepted-replay-"))
    try:
        os.chmod(private, 0o700)
        repository = private / "repository"
        home = private / "home"
        temp = private / "tmp"
        for directory in (repository, home, temp):
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
        try:
            materialize_snapshot(repository, payload, contents)
        except (OSError, ValueError) as exc:
            return [f"cannot safely extract accepted Phase 1 snapshot: {exc}"]
        extracted_errors = validate_materialized_snapshot(repository, payload)
        if extracted_errors:
            return extracted_errors
        checker_errors = run_historical_checker(repository, home, temp)
        post_checker_errors = validate_materialized_snapshot(repository, payload)
        return _bounded_findings(checker_errors + post_checker_errors)
    finally:
        shutil.rmtree(private, ignore_errors=True)


def main() -> int:
    errors = _bounded_findings(validate_historical_repository(ROOT))
    if errors:
        print(
            f"phase1-accepted-snapshot: FAIL — {len(errors)} finding(s)",
            file=sys.stderr,
        )
        emitted = 0
        for error in errors:
            line = f"- {error}"
            encoded = line.encode("utf-8", errors="replace")
            if emitted + len(encoded) + 1 > MAX_CLI_FINDINGS_BYTES:
                break
            print(line, file=sys.stderr)
            emitted += len(encoded) + 1
        return 1
    print(
        "phase1-accepted-snapshot: PASS — exact merge/tree/parents, complete "
        "92-path object manifest, safe private replay, and historical checker"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
