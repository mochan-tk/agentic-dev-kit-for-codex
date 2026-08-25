#!/usr/bin/env python3
"""Install and run the repository's hash-pinned CI tools without PATH fallback."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import io
import json
import os
import platform
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


_MAX_LOCK_BYTES = 64 * 1024
_MAX_REDIRECTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 30
_MAX_ARCHIVE_MEMBERS = 128
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_VERSION_TIMEOUT_SECONDS = 10
_MAX_VERSION_OUTPUT_BYTES = 16 * 1024
_CHECK_TIMEOUT_SECONDS = 120
_MAX_CHECK_OUTPUT_BYTES = 64 * 1024
_GIT_ENUMERATION_TIMEOUT_SECONDS = 10
_MAX_GIT_ENUMERATION_BYTES = 8 * 1024 * 1024
_MAX_LINT_INPUT_BYTES = 4 * 1024 * 1024
_MAX_LINT_INPUT_AGGREGATE_BYTES = 32 * 1024 * 1024

_REVIEWED_LOCK: dict[str, Any] = {
    "schema": "ci-tools-lock/v1",
    "platform": {"os": "linux", "architecture": "x86_64"},
    "tools": [
        {
            "name": "actionlint",
            "version": "1.7.12",
            "source": {
                "repository": "https://github.com/rhysd/actionlint",
                "commit": "914e7df21a07ef503a81201c76d2b11c789d3fca",
            },
            "archive": {
                "url": "https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz",
                "format": "tar.gz",
                "size": 2353908,
                "sha256": "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
                "member": "actionlint",
            },
            "binary": {
                "size": 6074530,
                "sha256": "c872d6db8c6bf83a8eaa704fc93999f027d55dffbc63b8a6abdccb47df5f4cd4",
                "version_arguments": ["-version"],
                "version_output_line": "1.7.12",
                "platform_output_pattern": "^built with go[0-9.]+ compiler for linux/amd64$",
            },
        },
        {
            "name": "shellcheck",
            "version": "0.11.0",
            "source": {
                "repository": "https://github.com/koalaman/shellcheck",
                "commit": "aac0823e6b58f8a499e856e93738082691cbf212",
            },
            "archive": {
                "url": "https://github.com/koalaman/shellcheck/releases/download/v0.11.0/shellcheck-v0.11.0.linux.x86_64.tar.xz",
                "format": "tar.xz",
                "size": 2559196,
                "sha256": "8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198",
                "member": "shellcheck-v0.11.0/shellcheck",
            },
            "binary": {
                "size": 16213136,
                "sha256": "4da528ddb3a4d1b7b24a59d4e16eb2f5fd960f4bd9a3708a15baddbdf1d5a55b",
                "version_arguments": ["--version"],
                "version_output_line": "version: 0.11.0",
            },
        },
    ],
}

_INITIAL_URLS = {
    tool["archive"]["url"] for tool in _REVIEWED_LOCK["tools"]
}


class ToolchainError(RuntimeError):
    """A bounded, user-safe CI toolchain validation failure."""


class _TransferDeadlineExpired(TimeoutError):
    """Internal interrupt used to enforce one whole-transfer deadline."""


@contextlib.contextmanager
def _total_transfer_deadline(seconds: float):
    """Interrupt all open/redirect/read work after one monotonic deadline."""

    if (
        seconds <= 0
        or not hasattr(signal, "setitimer")
        or not hasattr(signal, "getitimer")
        or not hasattr(signal, "ITIMER_REAL")
        or not hasattr(signal, "pthread_sigmask")
        or not hasattr(signal, "SIG_BLOCK")
        or not hasattr(signal, "SIG_SETMASK")
    ):
        raise ToolchainError("whole-transfer deadline support is unavailable")
    try:
        prior_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        prior_timer = signal.getitimer(signal.ITIMER_REAL)
        prior_handler = signal.getsignal(signal.SIGALRM)
    except (AttributeError, OSError, ValueError) as exc:
        raise ToolchainError("whole-transfer deadline support is unavailable") from exc
    if signal.SIGALRM in prior_mask:
        raise ToolchainError("SIGALRM is blocked; download deadline cannot be enforced")
    if prior_timer != (0.0, 0.0):
        raise ToolchainError("cannot replace an active process alarm for a download")

    deadline = time.monotonic() + seconds

    def expire(_signum, _frame):
        raise _TransferDeadlineExpired("artifact download deadline expired")

    handler_installed = False
    try:
        signal.signal(signal.SIGALRM, expire)
        handler_installed = True
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except (AttributeError, OSError, ValueError) as exc:
        if handler_installed:
            signal.signal(signal.SIGALRM, prior_handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask)
        raise ToolchainError("cannot establish the whole-transfer deadline") from exc
    try:
        yield deadline
        if time.monotonic() >= deadline:
            raise _TransferDeadlineExpired("artifact download deadline expired")
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        finally:
            try:
                signal.signal(signal.SIGALRM, prior_handler)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_regular_file(path: Path, maximum: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ToolchainError(f"cannot open reviewed lock: {exc.strerror or exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise ToolchainError("reviewed lock must be a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(16384, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ToolchainError("reviewed lock exceeds its size bound")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def load_reviewed_lock(path: Path | str) -> dict[str, Any]:
    """Load the one reviewed lock; any structural or pin drift fails closed."""

    raw = _read_regular_file(Path(path), _MAX_LOCK_BYTES)
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ToolchainError(f"reviewed lock is not exact UTF-8 JSON: {exc}") from exc
    if payload != _REVIEWED_LOCK:
        raise ToolchainError("CI tool lock differs from the reviewed exact pins")
    return payload


def _validate_artifact_url(url: str, *, redirect: bool) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise ToolchainError("artifact URL is malformed") from exc
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.fragment
    ):
        raise ToolchainError("artifact URL must be unambiguous HTTPS")
    if not redirect:
        if url not in _INITIAL_URLS:
            raise ToolchainError("artifact URL is not an exact reviewed GitHub release URL")
        return
    if parsed.hostname != "release-assets.githubusercontent.com":
        raise ToolchainError("artifact redirect host is not approved")
    if not re.fullmatch(
        r"/github-production-release-asset/[1-9][0-9]*/[0-9a-fA-F-]{36}",
        parsed.path,
    ):
        raise ToolchainError("artifact redirect path is not an approved release asset")
    if not parsed.query:
        raise ToolchainError("artifact redirect is missing its signed query")


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        self.count += 1
        if self.count > _MAX_REDIRECTS:
            raise ToolchainError("artifact redirect limit exceeded")
        _validate_artifact_url(new_url, redirect=True)
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def _open_url(url: str):
    handler = _RestrictedRedirectHandler()
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": "agentic-dev-kit-ci"},
        method="GET",
    )
    response = opener.open(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    try:
        setattr(response, "redirect_count", handler.count)
    except (AttributeError, TypeError):
        pass
    return response


def _download_artifact(
    artifact: Mapping[str, Any], *, opener: Callable[[str], Any] | None = None
) -> bytes:
    url = artifact["url"]
    expected_size = artifact["size"]
    expected_hash = artifact["sha256"]
    _validate_artifact_url(url, redirect=False)
    opener = _open_url if opener is None else opener
    try:
        with _total_transfer_deadline(_DOWNLOAD_TIMEOUT_SECONDS):
            response = opener(url)
            with response:
                if getattr(response, "status", 200) != 200:
                    raise ToolchainError("artifact download did not return HTTP 200")
                final_url = response.geturl()
                if final_url == url:
                    _validate_artifact_url(final_url, redirect=False)
                else:
                    _validate_artifact_url(final_url, redirect=True)
                if getattr(response, "redirect_count", 0) > _MAX_REDIRECTS:
                    raise ToolchainError("artifact redirect limit exceeded")
                content_length = response.headers.get("Content-Length")
                if (
                    content_length is None
                    or not content_length.isascii()
                    or not content_length.isdigit()
                    or int(content_length) != expected_size
                ):
                    raise ToolchainError(
                        "artifact Content-Length differs from the reviewed size"
                    )
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(65536, expected_size + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > expected_size:
                        raise ToolchainError("artifact stream exceeds the reviewed size")
                    chunks.append(chunk)
    except _TransferDeadlineExpired as exc:
        raise ToolchainError("artifact download exceeded its total deadline") from exc
    except ToolchainError:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise ToolchainError(f"artifact download failed: {exc}") from exc
    payload = b"".join(chunks)
    if len(payload) != expected_size:
        raise ToolchainError("artifact stream is shorter than the reviewed size")
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ToolchainError("artifact SHA-256 differs from the reviewed digest")
    return payload


def _safe_member_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/"):
        return False
    pure = PurePosixPath(name)
    if name != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        return False
    return not any(ord(character) < 32 or ord(character) == 127 for character in name)


def _extract_member(
    archive_payload: bytes,
    *,
    archive_format: str,
    member: str,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    mode = {"tar.gz": "r:gz", "tar.xz": "r:xz"}.get(archive_format)
    if mode is None:
        raise ToolchainError("archive format is not supported")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_payload), mode=mode) as archive:
            members = archive.getmembers()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ToolchainError("archive member count exceeds its bound")
            names: set[str] = set()
            total_size = 0
            target = None
            for entry in members:
                if not _safe_member_name(entry.name):
                    raise ToolchainError("archive contains an unsafe member path")
                if entry.name in names:
                    raise ToolchainError("archive contains a duplicate member")
                names.add(entry.name)
                if entry.isdir():
                    continue
                if not entry.isreg():
                    raise ToolchainError("archive contains a link, device, or special member")
                total_size += entry.size
                if total_size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise ToolchainError("archive uncompressed content exceeds its bound")
                if entry.name == member:
                    target = entry
            if target is None:
                raise ToolchainError("reviewed binary member is missing from archive")
            if target.size != expected_size:
                raise ToolchainError("binary member size differs from the reviewed size")
            stream = archive.extractfile(target)
            if stream is None:
                raise ToolchainError("binary member cannot be read")
            binary = stream.read(expected_size + 1)
    except ToolchainError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError) as exc:
        raise ToolchainError("artifact is not a valid bounded archive") from exc
    if len(binary) != expected_size:
        raise ToolchainError("extracted binary size differs from the reviewed size")
    if hashlib.sha256(binary).hexdigest() != expected_sha256:
        raise ToolchainError("extracted binary SHA-256 differs from the reviewed digest")
    return binary


def _decode_completed_output(
    result: subprocess.CompletedProcess[Any], label: str, maximum: int
) -> tuple[str, str]:
    stdout = (
        result.stdout
        if isinstance(result.stdout, str)
        else (result.stdout or b"").decode("utf-8", "replace")
    )
    stderr = (
        result.stderr
        if isinstance(result.stderr, str)
        else (result.stderr or b"").decode("utf-8", "replace")
    )
    if len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")) > maximum:
        raise ToolchainError(f"{label} output exceeds its bound")
    return stdout, stderr


def _fd_path(descriptor: int) -> str:
    proc_path = f"/proc/self/fd/{descriptor}"
    return proc_path if os.path.exists(proc_path) else f"/dev/fd/{descriptor}"


def _kill_and_reap(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_bounded_process(
    arguments: Sequence[str],
    *,
    label: str,
    timeout: float,
    maximum: int,
    cwd: Path | None = None,
    cwd_fd: int | None = None,
    executable_fd: int | None = None,
    inherited_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[bytes]:
    """Run one real process with streaming output caps and process-group cleanup."""

    pass_fds = set(inherited_fds)
    executable = None
    if executable_fd is not None:
        pass_fds.add(executable_fd)
        executable = _fd_path(executable_fd)
    effective_cwd: str | Path | None = cwd
    if cwd_fd is not None:
        pass_fds.add(cwd_fd)
        if sys.platform.startswith("linux"):
            effective_cwd = _fd_path(cwd_fd)
        elif cwd is None:
            raise ToolchainError(
                f"{label} requires a lexical cwd fallback on this test host"
            )
    try:
        process = subprocess.Popen(
            list(arguments),
            executable=executable,
            cwd=effective_cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=tuple(sorted(pass_fds)),
            start_new_session=True,
        )
    except OSError as exc:
        raise ToolchainError(f"{label} could not start") from exc
    assert process.stdout is not None and process.stderr is not None
    selector: selectors.BaseSelector | None = None
    buffers: dict[str, bytearray] = {}
    total = 0
    deadline = 0.0
    try:
        selector = selectors.DefaultSelector()
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + timeout
        for stream, name in (
            (process.stdout, "stdout"),
            (process.stderr, "stderr"),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ToolchainError(f"{label} timed out")
            events = selector.select(remaining)
            if not events:
                raise ToolchainError(f"{label} timed out")
            for key, _mask in events:
                try:
                    chunk = os.read(
                        key.fileobj.fileno(), min(65536, maximum + 1 - total)
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(chunk)
                total += len(chunk)
                if total > maximum:
                    raise ToolchainError(f"{label} output exceeds its bound")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ToolchainError(f"{label} timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise ToolchainError(f"{label} timed out") from exc
    except BaseException as exc:
        _kill_and_reap(process)
        if isinstance(exc, (ToolchainError, KeyboardInterrupt, SystemExit)):
            raise
        raise ToolchainError(f"{label} process monitoring failed") from exc
    finally:
        if selector is not None:
            selector.close()
        process.stdout.close()
        process.stderr.close()
    return subprocess.CompletedProcess(
        list(arguments), returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"])
    )


def _run_process(
    arguments: Sequence[str],
    *,
    label: str,
    timeout: float,
    maximum: int,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
    cwd: Path | None = None,
    cwd_fd: int | None = None,
    executable_fd: int | None = None,
    inherited_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[Any]:
    if runner is None:
        return _run_bounded_process(
            arguments,
            label=label,
            timeout=timeout,
            maximum=maximum,
            cwd=cwd,
            cwd_fd=cwd_fd,
            executable_fd=executable_fd,
            inherited_fds=inherited_fds,
        )
    pass_fds = set(inherited_fds)
    executable = None
    if executable_fd is not None:
        pass_fds.add(executable_fd)
        executable = _fd_path(executable_fd)
    try:
        result = runner(
            list(arguments),
            executable=executable,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            pass_fds=tuple(sorted(pass_fds)),
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"{label} did not complete") from exc
    _decode_completed_output(result, label, maximum)
    return result


def _probe_version(
    path: Path,
    binary_policy: Mapping[str, Any],
    *,
    executable_fd: int,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> str:
    arguments = [str(path), *binary_policy["version_arguments"]]
    result = _run_process(
        arguments,
        label=f"{path.name} version probe",
        timeout=_VERSION_TIMEOUT_SECONDS,
        maximum=_MAX_VERSION_OUTPUT_BYTES,
        runner=runner,
        executable_fd=executable_fd,
    )
    stdout, _stderr = _decode_completed_output(
        result, f"{path.name} version probe", _MAX_VERSION_OUTPUT_BYTES
    )
    if result.returncode != 0:
        raise ToolchainError(f"version probe failed for {path.name}")
    lines = stdout.splitlines()
    required_line = binary_policy["version_output_line"]
    if lines.count(required_line) != 1:
        raise ToolchainError(f"{path.name} did not emit its exact reviewed version line")
    platform_pattern = binary_policy.get("platform_output_pattern")
    if platform_pattern is not None and not any(
        re.fullmatch(platform_pattern, line) for line in lines
    ):
        raise ToolchainError(f"{path.name} did not identify the reviewed Linux platform")
    return stdout


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_trusted_parent(destination: Path) -> int:
    if not destination.is_absolute() or destination == Path("/"):
        raise ToolchainError("tool destination must be an absolute child path")
    if (
        destination.name in {"", ".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9._-]+", destination.name)
    ):
        raise ToolchainError("tool destination name is unsupported")
    parts = destination.parent.parts
    if not parts or parts[0] != "/" or any(part in {"", ".", ".."} for part in parts[1:]):
        raise ToolchainError("tool destination parent is not canonical")
    try:
        descriptor = os.open("/", _directory_flags())
        for part in parts[1:]:
            next_descriptor = os.open(
                part, _directory_flags(), dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as exc:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise ToolchainError("tool destination has an unsafe or missing parent") from exc
    metadata = os.fstat(descriptor)
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        os.close(descriptor)
        raise ToolchainError(
            "tool destination parent must be current-user owned and not group/world writable"
        )
    try:
        os.stat(destination.name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise ToolchainError("cannot inspect fresh tool destination") from exc
    os.close(descriptor)
    raise ToolchainError("tool destination must not already exist")


def _hash_descriptor(descriptor: int, maximum: int) -> tuple[int, str]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = os.read(descriptor, min(65536, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise ToolchainError("regular file exceeds its reviewed size bound")
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return total, digest.hexdigest()


def _rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            result = renameat2(
                parent_fd,
                os.fsencode(source),
                parent_fd,
                os.fsencode(destination),
                1,
            )
        else:
            result = libc.syscall(
                316,
                parent_fd,
                os.fsencode(source),
                parent_fd,
                os.fsencode(destination),
                1,
            )
        if result != 0:
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                raise ToolchainError("tool destination appeared before publication")
            raise ToolchainError(f"atomic tool publication failed with errno {code}")
        return
    try:
        os.stat(destination, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        os.rename(
            source,
            destination,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        return
    raise ToolchainError("tool destination appeared before publication")


def _move_to_fresh_quarantine(
    parent_fd: int, source: str, *, label: str
) -> str | None:
    """Atomically isolate one cleanup candidate without overwriting any entry."""

    for _attempt in range(8):
        quarantine = f".ci-tools-abort-{label}-{secrets.token_hex(12)}"
        try:
            _rename_noreplace(parent_fd, source, quarantine)
        except (OSError, ToolchainError):
            continue
        return quarantine
    return None


def _restore_quarantined_entry(
    parent_fd: int, quarantine: str, original: str
) -> None:
    """Best-effort no-replace restore; otherwise leave the entry preserved."""

    try:
        _rename_noreplace(parent_fd, quarantine, original)
    except (OSError, ToolchainError):
        pass


class _StagingArea:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.parent_fd = _open_trusted_parent(destination)
        self.final_name = destination.name
        self.staging_name = ""
        self.directory_fd = -1
        self.directory_identity: tuple[int, int] | None = None
        self.records: dict[str, dict[str, Any]] = {}
        self.known_names: set[str] = set()
        self.created_identities: dict[str, tuple[int, int]] = {}
        self.published = False
        try:
            for _attempt in range(8):
                candidate = f".ci-tools-staging-{secrets.token_hex(12)}"
                try:
                    os.mkdir(candidate, 0o700, dir_fd=self.parent_fd)
                except FileExistsError:
                    continue
                self.staging_name = candidate
                created = os.stat(
                    candidate, dir_fd=self.parent_fd, follow_symlinks=False
                )
                self.directory_identity = (created.st_dev, created.st_ino)
                break
            if not self.staging_name:
                raise ToolchainError("cannot allocate a fresh private staging directory")
            self.directory_fd = os.open(
                self.staging_name, _directory_flags(), dir_fd=self.parent_fd
            )
            opened = os.fstat(self.directory_fd)
            if self.directory_identity != (opened.st_dev, opened.st_ino):
                raise ToolchainError("fresh staging directory binding changed")
            os.fsync(self.parent_fd)
        except Exception:
            self.abort()
            raise

    def install(self, name: str, payload: bytes, policy: Mapping[str, Any]) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in self.known_names:
            raise ToolchainError("tool binary name is unsupported or duplicated")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(name, flags, 0o500, dir_fd=self.directory_fd)
            self.known_names.add(name)
            try:
                created = os.fstat(descriptor)
                self.created_identities[name] = (created.st_dev, created.st_ino)
                view = memoryview(payload)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise ToolchainError(f"cannot write pinned binary {name}")
                    view = view[written:]
                os.fchmod(descriptor, 0o555)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            read_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                read_flags |= os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                read_flags |= os.O_CLOEXEC
            if hasattr(os, "O_NONBLOCK"):
                read_flags |= os.O_NONBLOCK
            read_descriptor = os.open(name, read_flags, dir_fd=self.directory_fd)
            try:
                metadata = os.fstat(read_descriptor)
                size, digest = _hash_descriptor(read_descriptor, int(policy["size"]))
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o555
                    or (metadata.st_dev, metadata.st_ino)
                    != self.created_identities[name]
                    or size != policy["size"]
                    or digest != policy["sha256"]
                ):
                    raise ToolchainError(
                        f"installed binary verification failed for {name}"
                    )
            except Exception:
                os.close(read_descriptor)
                raise
        except ToolchainError:
            raise
        except OSError as exc:
            raise ToolchainError(f"cannot stage pinned binary {name}") from exc
        self.records[name] = {
            "fd": read_descriptor,
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "size": size,
            "sha256": digest,
        }
        return self.destination / name

    def verify(self) -> None:
        try:
            directory = os.fstat(self.directory_fd)
            entry_name = self.final_name if self.published else self.staging_name
            entry = os.stat(entry_name, dir_fd=self.parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(directory.st_mode)
                or self.directory_identity
                != (directory.st_dev, directory.st_ino)
                or (directory.st_dev, directory.st_ino)
                != (entry.st_dev, entry.st_ino)
            ):
                raise ToolchainError("tool directory binding changed")
            entries = os.listdir(self.directory_fd)
            if len(entries) != len(set(entries)) or set(entries) != self.known_names:
                raise ToolchainError("tool staging directory contains unknown entries")
            if self.published:
                lexical = self.destination.lstat()
                if (lexical.st_dev, lexical.st_ino) != (
                    directory.st_dev,
                    directory.st_ino,
                ):
                    raise ToolchainError("published tool directory namespace changed")
            for name, record in self.records.items():
                metadata = os.fstat(record["fd"])
                bound = os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False)
                size, digest = _hash_descriptor(record["fd"], int(record["size"]))
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o555
                    or (metadata.st_dev, metadata.st_ino)
                    != (record["device"], record["inode"])
                    or (bound.st_dev, bound.st_ino)
                    != (record["device"], record["inode"])
                    or size != record["size"]
                    or digest != record["sha256"]
                ):
                    raise ToolchainError(f"pinned binary binding changed for {name}")
                if self.published:
                    lexical = (self.destination / name).lstat()
                    if (lexical.st_dev, lexical.st_ino) != (
                        record["device"],
                        record["inode"],
                    ):
                        raise ToolchainError(
                            f"published binary namespace changed for {name}"
                        )
        except ToolchainError:
            raise
        except OSError as exc:
            raise ToolchainError("tool namespace or descriptor became unavailable") from exc

    def publish(self) -> None:
        self.verify()
        os.fsync(self.directory_fd)
        _rename_noreplace(self.parent_fd, self.staging_name, self.final_name)
        self.published = True
        os.fsync(self.parent_fd)
        self.verify()

    def execution_fd(self, name: str) -> int:
        return int(self.records[name]["fd"])

    def _close_descriptors(self) -> None:
        for record in self.records.values():
            descriptor = record.get("fd", -1)
            if isinstance(descriptor, int) and descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                record["fd"] = -1
        if self.directory_fd >= 0:
            try:
                os.close(self.directory_fd)
            except OSError:
                pass
            self.directory_fd = -1
        if self.parent_fd >= 0:
            try:
                os.close(self.parent_fd)
            except OSError:
                pass
            self.parent_fd = -1

    def abort(self) -> None:
        if self.parent_fd < 0:
            return
        held_identity: tuple[int, int] | None = None
        if self.directory_fd >= 0:
            try:
                directory = os.fstat(self.directory_fd)
                held_identity = (directory.st_dev, directory.st_ino)
            except OSError:
                pass
        held_is_original = (
            held_identity is not None
            and held_identity == self.directory_identity
        )
        for record in self.records.values():
            descriptor = record.get("fd", -1)
            if isinstance(descriptor, int) and descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                record["fd"] = -1
        if self.directory_fd >= 0:
            if held_is_original:
                for name in self.known_names:
                    expected_identity = self.created_identities.get(name)
                    quarantine = _move_to_fresh_quarantine(
                        self.directory_fd, name, label="entry"
                    )
                    if quarantine is None:
                        continue
                    try:
                        current = os.stat(
                            quarantine,
                            dir_fd=self.directory_fd,
                            follow_symlinks=False,
                        )
                        if expected_identity is not None and (
                            current.st_dev,
                            current.st_ino,
                        ) == expected_identity:
                            # POSIX has no inode-conditional unlink. Keep the
                            # verified entry quarantined so a post-stat swap
                            # can never make abort delete unreviewed bytes.
                            pass
                        else:
                            _restore_quarantined_entry(
                                self.directory_fd, quarantine, name
                            )
                    except OSError:
                        _restore_quarantined_entry(
                            self.directory_fd, quarantine, name
                        )
                try:
                    os.fsync(self.directory_fd)
                except OSError:
                    pass
            try:
                os.close(self.directory_fd)
            except OSError:
                pass
            self.directory_fd = -1
        entry_name = self.final_name if self.published else self.staging_name
        if entry_name:
            quarantine = _move_to_fresh_quarantine(
                self.parent_fd, entry_name, label="directory"
            )
        else:
            quarantine = None
        if quarantine is not None:
            try:
                entry = os.stat(
                    quarantine,
                    dir_fd=self.parent_fd,
                    follow_symlinks=False,
                )
                if self.directory_identity is not None and (
                    entry.st_dev,
                    entry.st_ino,
                ) == self.directory_identity:
                    # Preserve the isolated directory for the same reason as
                    # its entries: rmdir is pathname-based, not inode-bound.
                    os.fsync(self.parent_fd)
                else:
                    _restore_quarantined_entry(
                        self.parent_fd, quarantine, entry_name
                    )
            except OSError:
                _restore_quarantined_entry(
                    self.parent_fd, quarantine, entry_name
                )
        try:
            os.close(self.parent_fd)
        except OSError:
            pass
        self.parent_fd = -1


class _InstalledTools(dict[str, Path]):
    def __init__(self, paths: dict[str, Path], area: _StagingArea) -> None:
        super().__init__(paths)
        self._area = area

    def execution_fd(self, name: str) -> int:
        return self._area.execution_fd(name)

    def verify(self) -> None:
        self._area.verify()

    def close(self) -> None:
        self._area._close_descriptors()


def _install_validated_tools(
    payload: Mapping[str, Any],
    destination: Path,
    *,
    opener: Callable[[str], Any] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
    system: str | None = None,
    machine: str | None = None,
) -> _InstalledTools:
    system = platform.system() if system is None else system
    machine = platform.machine() if machine is None else machine
    if system != "Linux" or machine != "x86_64":
        raise ToolchainError("pinned CI tools support only Linux/x86_64")
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ToolchainError("validated tool payload is empty")
    area = _StagingArea(destination)
    paths: dict[str, Path] = {}
    evidence: list[tuple[str, str, Path, str]] = []
    try:
        for tool in tools:
            archive = tool["archive"]
            archive_payload = _download_artifact(archive, opener=opener)
            binary_policy = tool["binary"]
            binary_payload = _extract_member(
                archive_payload,
                archive_format=archive["format"],
                member=archive["member"],
                expected_size=binary_policy["size"],
                expected_sha256=binary_policy["sha256"],
            )
            path = area.install(tool["name"], binary_payload, binary_policy)
            output = _probe_version(
                path,
                binary_policy,
                executable_fd=area.execution_fd(tool["name"]),
                runner=runner,
            )
            area.verify()
            evidence.append((tool["name"], tool["version"], path, output))
            paths[tool["name"]] = path
        area.publish()
        for name, version, path, output in evidence:
            print(f"verified {name} {version} at {path}")
            print(output, end="" if output.endswith("\n") else "\n")
        return _InstalledTools(paths, area)
    except Exception:
        area.abort()
        raise


def _valid_repository_path(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value:
        return False
    if unicodedata.normalize("NFC", value) != value:
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    pure = PurePosixPath(value)
    return value == pure.as_posix() and all(
        part not in {"", ".", ".."} for part in pure.parts
    )


def _open_relative_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = PurePosixPath(relative).parts
    descriptor = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part, _directory_flags(), dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except Exception:
        os.close(descriptor)
        raise


class _RepositoryScan:
    def __init__(
        self,
        root: Path,
        root_fd: int,
        paths: list[str],
        records: dict[str, dict[str, Any]],
    ) -> None:
        self.root = root
        self.root_fd = root_fd
        self.paths = paths
        self.records = records

    def descriptor_paths(self, paths: Sequence[str]) -> list[str]:
        try:
            return [_fd_path(int(self.records[path]["fd"])) for path in paths]
        except KeyError as exc:
            raise ToolchainError("repository scan descriptor set is incomplete") from exc

    def descriptors(self, paths: Sequence[str]) -> tuple[int, ...]:
        try:
            return tuple(int(self.records[path]["fd"]) for path in paths)
        except KeyError as exc:
            raise ToolchainError("repository scan descriptor set is incomplete") from exc

    def verify(self) -> None:
        try:
            root_metadata = os.fstat(self.root_fd)
            lexical_root = self.root.lstat()
            if (root_metadata.st_dev, root_metadata.st_ino) != (
                lexical_root.st_dev,
                lexical_root.st_ino,
            ):
                raise ToolchainError(
                    "repository root namespace changed during tool scan"
                )
            for path, record in self.records.items():
                parent_fd, name = _open_relative_parent(self.root_fd, path)
                try:
                    current = os.stat(
                        name, dir_fd=parent_fd, follow_symlinks=False
                    )
                finally:
                    os.close(parent_fd)
                metadata = os.fstat(record["fd"])
                size, digest = _hash_descriptor(record["fd"], int(record["size"]))
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != record["mode"]
                    or stat.S_IMODE(current.st_mode) != record["mode"]
                    or (metadata.st_dev, metadata.st_ino)
                    != (record["device"], record["inode"])
                    or (current.st_dev, current.st_ino)
                    != (record["device"], record["inode"])
                    or size != record["size"]
                    or digest != record["sha256"]
                ):
                    raise ToolchainError(f"repository scan input changed: {path}")
        except ToolchainError:
            raise
        except OSError as exc:
            raise ToolchainError(
                "repository scan input namespace became unavailable"
            ) from exc

    def close(self) -> None:
        for record in self.records.values():
            try:
                os.close(record["fd"])
            except OSError:
                pass
        self.records.clear()
        if self.root_fd >= 0:
            try:
                os.close(self.root_fd)
            except OSError:
                pass
            self.root_fd = -1


def _prepare_repository_scan(root: Path) -> _RepositoryScan:
    root = root.resolve()
    try:
        root_fd = os.open(root, _directory_flags())
    except OSError as exc:
        raise ToolchainError("repository root is not a safe directory") from exc
    records: dict[str, dict[str, Any]] = {}
    try:
        result = _run_bounded_process(
            ["git", "--no-replace-objects", "ls-files", "--stage", "-z"],
            label="tracked repository enumeration",
            timeout=_GIT_ENUMERATION_TIMEOUT_SECONDS,
            maximum=_MAX_GIT_ENUMERATION_BYTES,
            cwd=root,
            cwd_fd=root_fd,
        )
        if result.returncode != 0:
            raise ToolchainError("cannot enumerate tracked repository files")
        paths: list[str] = []
        modes: dict[str, str] = {}
        for field in result.stdout.split(b"\0"):
            if not field:
                continue
            try:
                metadata, raw_path = field.split(b"\t", 1)
                mode, object_id, stage = metadata.decode("ascii").split()
                path = raw_path.decode("utf-8")
            except (ValueError, UnicodeError) as exc:
                raise ToolchainError("tracked repository index entry is malformed") from exc
            if (
                stage != "0"
                or mode not in {"100644", "100755"}
                or re.fullmatch(r"[0-9a-f]{40}", object_id) is None
                or not _valid_repository_path(path)
                or path in modes
            ):
                raise ToolchainError("tracked repository index is ambiguous or unsafe")
            paths.append(path)
            modes[path] = mode
        if paths != sorted(paths):
            raise ToolchainError("tracked repository paths are not deterministic")
        selected = [
            path
            for path in paths
            if path.endswith(".sh")
            or (
                path.startswith(".github/workflows/")
                and path.endswith((".yml", ".yaml"))
            )
        ]
        aggregate = 0
        for path in selected:
            try:
                parent_fd, name = _open_relative_parent(root_fd, path)
            except OSError as exc:
                raise ToolchainError(
                    f"repository scan input cannot be opened safely: {path}"
                ) from exc
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_NONBLOCK"):
                flags |= os.O_NONBLOCK
            try:
                descriptor = os.open(name, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise ToolchainError(
                    f"repository scan input cannot be opened safely: {path}"
                ) from exc
            finally:
                os.close(parent_fd)
            try:
                metadata = os.fstat(descriptor)
                expected_mode = 0o755 if modes[path] == "100755" else 0o644
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != expected_mode
                    or metadata.st_size > _MAX_LINT_INPUT_BYTES
                ):
                    raise ToolchainError(f"repository scan input is unsafe: {path}")
                size, digest = _hash_descriptor(
                    descriptor, _MAX_LINT_INPUT_BYTES
                )
            except Exception:
                os.close(descriptor)
                raise
            aggregate += size
            if aggregate > _MAX_LINT_INPUT_AGGREGATE_BYTES:
                os.close(descriptor)
                raise ToolchainError("repository scan inputs exceed their aggregate bound")
            records[path] = {
                "fd": descriptor,
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "mode": expected_mode,
                "size": size,
                "sha256": digest,
            }
        return _RepositoryScan(root, root_fd, paths, records)
    except Exception:
        for record in records.values():
            try:
                os.close(record["fd"])
            except OSError:
                pass
        os.close(root_fd)
        raise


def _run_repository_check(
    arguments: list[str],
    *,
    root: Path,
    root_fd: int,
    executable_fd: int,
    inherited_fds: Sequence[int] = (),
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None,
    label: str,
) -> None:
    result = _run_process(
        arguments,
        label=label,
        timeout=_CHECK_TIMEOUT_SECONDS,
        maximum=_MAX_CHECK_OUTPUT_BYTES,
        runner=runner,
        cwd=root,
        cwd_fd=root_fd,
        executable_fd=executable_fd,
        inherited_fds=inherited_fds,
    )
    if result.returncode != 0:
        raise ToolchainError(f"{label} failed with exit status {result.returncode}")


def _check_repository(
    installed: Mapping[str, Path],
    *,
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> None:
    if not isinstance(installed, _InstalledTools):
        raise ToolchainError("repository checks require descriptor-bound pinned tools")
    shellcheck = installed.get("shellcheck")
    actionlint = installed.get("actionlint")
    if shellcheck is None or actionlint is None:
        raise ToolchainError("both pinned repository tools are required")
    if not shellcheck.is_absolute() or not actionlint.is_absolute():
        raise ToolchainError("repository checks require absolute pinned tool paths")
    installed.verify()
    scan = _prepare_repository_scan(root)
    try:
        shell_paths = [path for path in scan.paths if path.endswith(".sh")]
        workflow_paths = [
            path
            for path in scan.paths
            if path.startswith(".github/workflows/")
            and path.endswith((".yml", ".yaml"))
        ]
        if not shell_paths or not workflow_paths:
            raise ToolchainError("repository tool inputs are empty or uncheckable")
        scan.verify()
        _run_repository_check(
            [
                str(shellcheck),
                "--norc",
                "--",
                *scan.descriptor_paths(shell_paths),
            ],
            root=root,
            root_fd=scan.root_fd,
            executable_fd=installed.execution_fd("shellcheck"),
            inherited_fds=scan.descriptors(shell_paths),
            runner=runner,
            label="pinned ShellCheck repository scan",
        )
        installed.verify()
        scan.verify()
        _run_repository_check(
            [
                str(actionlint),
                "-config-file=/dev/null",
                f"-shellcheck={_fd_path(installed.execution_fd('shellcheck'))}",
                "-pyflakes=",
                "--",
                *scan.descriptor_paths(workflow_paths),
            ],
            root=root,
            root_fd=scan.root_fd,
            executable_fd=installed.execution_fd("actionlint"),
            inherited_fds=(
                installed.execution_fd("shellcheck"),
                *scan.descriptors(workflow_paths),
            ),
            runner=runner,
            label="pinned actionlint repository scan",
        )
        installed.verify()
        scan.verify()
    finally:
        scan.close()
    print("repository tool checks: OK — pinned ShellCheck and actionlint completed")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--check-repository", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    installed: _InstalledTools | None = None
    try:
        payload = load_reviewed_lock(arguments.lock)
        installed = _install_validated_tools(payload, arguments.destination)
        if arguments.check_repository:
            _check_repository(
                installed, root=Path(__file__).resolve().parents[2]
            )
    except ToolchainError as exc:
        print(f"ci-tools: FAIL — {exc}", file=sys.stderr)
        return 1
    finally:
        if installed is not None:
            installed.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
