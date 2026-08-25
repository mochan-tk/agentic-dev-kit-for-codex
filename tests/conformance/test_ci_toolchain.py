import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / ".github/scripts/install-ci-tools.py"
LOCK = ROOT / ".github/governance/ci-tools.lock.v1.json"

EXPECTED_LOCK = {
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


def load_installer():
    if not INSTALLER.is_file():
        raise AssertionError(f"reviewed installer is missing: {INSTALLER}")
    spec = importlib.util.spec_from_file_location("install_ci_tools", INSTALLER)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load installer: {INSTALLER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse(io.BytesIO):
    def __init__(self, payload, *, final_url, content_length=None, redirect_count=0):
        super().__init__(payload)
        self._final_url = final_url
        self.headers = {
            "Content-Length": str(
                len(payload) if content_length is None else content_length
            )
        }
        self.redirect_count = redirect_count
        self.status = 200

    def geturl(self):
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        self.close()


def tar_payload(members, archive_format="tar.gz"):
    buffer = io.BytesIO()
    mode = "w:gz" if archive_format == "tar.gz" else "w:xz"
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for member in members:
            info = tarfile.TarInfo(member["name"])
            kind = member.get("kind", "file")
            data = member.get("data", b"")
            if kind == "file":
                info.size = len(data)
            elif kind == "directory":
                info.type = tarfile.DIRTYPE
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = member.get("target", "target")
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = member.get("target", "target")
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
            elif kind == "device":
                info.type = tarfile.CHRTYPE
            else:
                raise AssertionError(f"unsupported fixture kind: {kind}")
            archive.addfile(info, io.BytesIO(data) if kind == "file" else None)
    return buffer.getvalue()


def fixture_lock():
    payload = copy.deepcopy(EXPECTED_LOCK)
    archives = {}
    for tool in payload["tools"]:
        output = expected_version_output(tool)
        binary = f"#!/bin/sh\nprintf '%s' '{output}'\n".encode("utf-8")
        archive = tar_payload(
            [
                {"name": "docs", "kind": "directory"},
                {"name": tool["archive"]["member"], "data": binary},
            ],
            tool["archive"]["format"],
        )
        tool["archive"]["size"] = len(archive)
        tool["archive"]["sha256"] = hashlib.sha256(archive).hexdigest()
        tool["binary"]["size"] = len(binary)
        tool["binary"]["sha256"] = hashlib.sha256(binary).hexdigest()
        archives[tool["archive"]["url"]] = archive
    return payload, archives


def expected_version_output(tool):
    if tool["name"] == "actionlint":
        return (
            f"{tool['version']}\n"
            "installed by downloading from release page\n"
            "built with go1.25.0 compiler for linux/amd64\n"
        )
    return f"ShellCheck\nversion: {tool['version']}\n"


class ToolLockContractTest(unittest.TestCase):
    def test_reviewed_lock_is_exact(self):
        self.assertTrue(LOCK.is_file(), "canonical CI tool lock is missing")
        self.assertEqual(EXPECTED_LOCK, json.loads(LOCK.read_text(encoding="utf-8")))

    def test_reviewed_lock_loader_rejects_any_pin_or_shape_tamper(self):
        installer = load_installer()
        mutations = (
            ("schema", lambda value: value.__setitem__("schema", "ci-tools-lock/v2")),
            ("extra", lambda value: value.__setitem__("extra", True)),
            ("platform", lambda value: value["platform"].__setitem__("os", "darwin")),
            ("order", lambda value: value["tools"].reverse()),
            ("version", lambda value: value["tools"][0].__setitem__("version", "latest")),
            ("source", lambda value: value["tools"][0]["source"].__setitem__("commit", "0" * 40)),
            ("url", lambda value: value["tools"][0]["archive"].__setitem__("url", "https://example.invalid/tool")),
            ("archive-size", lambda value: value["tools"][0]["archive"].__setitem__("size", 1)),
            ("archive-hash", lambda value: value["tools"][0]["archive"].__setitem__("sha256", "0" * 64)),
            ("member", lambda value: value["tools"][0]["archive"].__setitem__("member", "../actionlint")),
            ("binary-size", lambda value: value["tools"][1]["binary"].__setitem__("size", 1)),
            ("binary-hash", lambda value: value["tools"][1]["binary"].__setitem__("sha256", "f" * 64)),
            ("version-command", lambda value: value["tools"][1]["binary"].__setitem__("version_arguments", ["--help"])),
            ("version-line", lambda value: value["tools"][1]["binary"].__setitem__("version_output_line", "0.11.0")),
            ("platform-line", lambda value: value["tools"][0]["binary"].__setitem__("platform_output_pattern", ".*")),
        )
        for label, mutation in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                payload = copy.deepcopy(EXPECTED_LOCK)
                mutation(payload)
                path = Path(directory) / "lock.json"
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                with self.assertRaises(installer.ToolchainError):
                    installer.load_reviewed_lock(path)

    def test_lock_loader_rejects_duplicate_json_keys(self):
        installer = load_installer()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text(
                '{"schema":"ci-tools-lock/v1","schema":"ci-tools-lock/v1"}\n',
                encoding="utf-8",
            )
            with self.assertRaises(installer.ToolchainError):
                installer.load_reviewed_lock(path)

    def test_lock_loader_rejects_fifo_without_blocking(self):
        installer = load_installer()
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory).resolve() / "lock.fifo"
            os.mkfifo(fifo)
            started = time.monotonic()
            with self.assertRaisesRegex(
                installer.ToolchainError, "bounded regular file"
            ):
                installer.load_reviewed_lock(fifo)
            self.assertLess(time.monotonic() - started, 1.0)


class InstallerSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = load_installer()

    def test_platform_is_exact_and_unsupported_platforms_fail_closed(self):
        payload, archives = fixture_lock()
        opener = lambda url: FakeResponse(archives[url], final_url=url)
        with tempfile.TemporaryDirectory() as directory:
            for system, machine in (
                ("Darwin", "x86_64"),
                ("Linux", "aarch64"),
                ("Linux", "amd64"),
                ("", ""),
            ):
                with self.subTest(system=system, machine=machine):
                    with self.assertRaises(self.installer.ToolchainError):
                        self.installer._install_validated_tools(
                            payload,
                            Path(directory),
                            opener=opener,
                            runner=subprocess.run,
                            system=system,
                            machine=machine,
                        )

    def test_artifact_url_and_redirect_policy_fail_closed(self):
        valid = EXPECTED_LOCK["tools"][0]["archive"]["url"]
        valid_redirect = (
            "https://release-assets.githubusercontent.com/"
            "github-production-release-asset/370668507/"
            "4937bfe7-85f6-4ede-96c2-1968894594a4?sp=r&sv=2018-11-09"
        )
        self.installer._validate_artifact_url(valid, redirect=False)
        self.installer._validate_artifact_url(valid_redirect, redirect=True)
        invalid = (
            valid.replace("https://", "http://"),
            valid.replace("github.com", "github.example.invalid"),
            valid.replace("/releases/download/", "/archive/"),
            valid + "?mutable=true",
            "https://github.com/rhysd/actionlint/releases/latest/download/actionlint.tar.gz",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(self.installer.ToolchainError):
                self.installer._validate_artifact_url(url, redirect=False)
        for url in (
            "http://release-assets.githubusercontent.com/asset",
            "https://example.invalid/github-production-release-asset-x",
            "https://release-assets.githubusercontent.com/not-a-release-asset",
        ):
            with self.subTest(redirect=url), self.assertRaises(self.installer.ToolchainError):
                self.installer._validate_artifact_url(url, redirect=True)

    def test_download_rejects_bad_final_url_redirect_count_and_length(self):
        artifact = copy.deepcopy(EXPECTED_LOCK["tools"][0]["archive"])
        data = b"verified archive"
        artifact["size"] = len(data)
        artifact["sha256"] = hashlib.sha256(data).hexdigest()
        cases = (
            (
                "redirect-host",
                FakeResponse(data, final_url="https://example.invalid/asset"),
            ),
            (
                "redirect-path",
                FakeResponse(
                    data,
                    final_url="https://release-assets.githubusercontent.com/not-approved",
                ),
            ),
            (
                "too-many-redirects",
                FakeResponse(data, final_url=artifact["url"], redirect_count=4),
            ),
            (
                "declared-oversize",
                FakeResponse(data, final_url=artifact["url"], content_length=len(data) + 1),
            ),
            (
                "stream-oversize",
                FakeResponse(data + b"x", final_url=artifact["url"], content_length=len(data)),
            ),
        )
        for label, response in cases:
            with self.subTest(label=label), self.assertRaises(self.installer.ToolchainError):
                self.installer._download_artifact(artifact, opener=lambda _url, value=response: value)

    def test_download_rejects_corrupt_archive_hash(self):
        artifact = copy.deepcopy(EXPECTED_LOCK["tools"][0]["archive"])
        data = b"not the reviewed archive"
        artifact["size"] = len(data)
        artifact["sha256"] = "0" * 64
        with self.assertRaises(self.installer.ToolchainError):
            self.installer._download_artifact(
                artifact,
                opener=lambda _url: FakeResponse(data, final_url=artifact["url"]),
            )

    @unittest.skipUnless(
        hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL"),
        "whole-transfer interrupt test requires POSIX interval timers",
    )
    def test_download_enforces_one_total_deadline_across_trickle_reads(self):
        artifact = copy.deepcopy(EXPECTED_LOCK["tools"][0]["archive"])
        data = b"slow"
        artifact["size"] = len(data)
        artifact["sha256"] = hashlib.sha256(data).hexdigest()

        class TrickleResponse(FakeResponse):
            def read(self, _maximum=-1):
                time.sleep(0.03)
                return super().read(1)

        response = TrickleResponse(data, final_url=artifact["url"])
        started = time.monotonic()
        with mock.patch.object(
            self.installer, "_DOWNLOAD_TIMEOUT_SECONDS", 0.05
        ), self.assertRaisesRegex(
            self.installer.ToolchainError, "total deadline"
        ):
            self.installer._download_artifact(
                artifact, opener=lambda _url: response
            )
        self.assertLess(time.monotonic() - started, 0.5)

    @unittest.skipUnless(
        hasattr(signal, "pthread_sigmask")
        and hasattr(signal, "setitimer")
        and hasattr(signal, "ITIMER_REAL"),
        "deadline signal-state tests require POSIX signal masks and timers",
    )
    def test_download_deadline_rejects_blocked_alarm_and_restores_signal_state(self):
        artifact = copy.deepcopy(EXPECTED_LOCK["tools"][0]["archive"])
        data = b"bounded"
        artifact["size"] = len(data)
        artifact["sha256"] = hashlib.sha256(data).hexdigest()
        original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        original_handler = signal.getsignal(signal.SIGALRM)
        original_timer = signal.getitimer(signal.ITIMER_REAL)
        self.assertEqual((0.0, 0.0), original_timer)

        def sentinel_handler(_signum, _frame):
            raise AssertionError("restored handler should not run")

        try:
            signal.signal(signal.SIGALRM, sentinel_handler)
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "SIGALRM is blocked"
            ):
                self.installer._download_artifact(
                    artifact,
                    opener=lambda _url: FakeResponse(
                        data, final_url=artifact["url"]
                    ),
                )
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)
            self.assertEqual(sentinel_handler, signal.getsignal(signal.SIGALRM))
            self.assertEqual((0.0, 0.0), signal.getitimer(signal.ITIMER_REAL))

            self.assertEqual(
                data,
                self.installer._download_artifact(
                    artifact,
                    opener=lambda _url: FakeResponse(
                        data, final_url=artifact["url"]
                    ),
                ),
            )
            self.assertEqual(sentinel_handler, signal.getsignal(signal.SIGALRM))
            self.assertEqual((0.0, 0.0), signal.getitimer(signal.ITIMER_REAL))
            self.assertEqual(
                original_mask,
                signal.pthread_sigmask(signal.SIG_BLOCK, set()),
            )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, original_handler)
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)

    def test_archive_rejects_unsafe_duplicate_or_missing_members(self):
        binary = b"#!/bin/sh\nexit 0\n"
        digest = hashlib.sha256(binary).hexdigest()
        cases = (
            ("traversal", [{"name": "../tool", "data": binary}]),
            ("absolute", [{"name": "/tool", "data": binary}]),
            ("symlink", [{"name": "tool", "kind": "symlink"}]),
            ("hardlink", [{"name": "tool", "kind": "hardlink"}]),
            ("fifo", [{"name": "tool", "kind": "fifo"}]),
            ("device", [{"name": "tool", "kind": "device"}]),
            (
                "duplicate",
                [{"name": "tool", "data": binary}, {"name": "tool", "data": binary}],
            ),
            ("missing", [{"name": "other", "data": binary}]),
        )
        for label, members in cases:
            with self.subTest(label=label), self.assertRaises(self.installer.ToolchainError):
                self.installer._extract_member(
                    tar_payload(members),
                    archive_format="tar.gz",
                    member="tool",
                    expected_size=len(binary),
                    expected_sha256=digest,
                )

    def test_archive_rejects_wrong_binary_size_and_hash(self):
        binary = b"reviewed binary"
        archive = tar_payload([{"name": "tool", "data": binary}])
        for size, digest in (
            (len(binary) + 1, hashlib.sha256(binary).hexdigest()),
            (len(binary), "0" * 64),
        ):
            with self.subTest(size=size, digest=digest), self.assertRaises(
                self.installer.ToolchainError
            ):
                self.installer._extract_member(
                    archive,
                    archive_format="tar.gz",
                    member="tool",
                    expected_size=size,
                    expected_sha256=digest,
                )

        with self.assertRaises(self.installer.ToolchainError):
            self.installer._extract_member(
                b"not a tar archive",
                archive_format="tar.gz",
                member="tool",
                expected_size=len(binary),
                expected_sha256=hashlib.sha256(binary).hexdigest(),
            )

    def test_archive_member_count_and_aggregate_uncompressed_size_are_bounded(self):
        binary = b"x"
        digest = hashlib.sha256(binary).hexdigest()
        count_archive = tar_payload(
            [
                {"name": "tool", "data": binary},
                {"name": "one", "data": b"1"},
                {"name": "two", "data": b"2"},
            ]
        )
        with mock.patch.object(self.installer, "_MAX_ARCHIVE_MEMBERS", 2):
            with self.assertRaises(self.installer.ToolchainError):
                self.installer._extract_member(
                    count_archive,
                    archive_format="tar.gz",
                    member="tool",
                    expected_size=1,
                    expected_sha256=digest,
                )

        aggregate_archive = tar_payload(
            [
                {"name": "tool", "data": binary},
                {"name": "metadata", "data": b"12"},
            ]
        )
        with mock.patch.object(
            self.installer, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 2
        ):
            with self.assertRaises(self.installer.ToolchainError):
                self.installer._extract_member(
                    aggregate_archive,
                    archive_format="tar.gz",
                    member="tool",
                    expected_size=1,
                    expected_sha256=digest,
                )

    def test_successful_offline_flow_uses_absolute_pinned_binaries_and_fixed_mode(self):
        payload, archives = fixture_lock()
        calls = []
        executables = []

        def opener(url):
            return FakeResponse(archives[url], final_url=url)

        def runner(arguments, **kwargs):
            calls.append(list(arguments))
            executables.append(kwargs.get("executable"))
            name = Path(arguments[0]).name
            tool = next(item for item in payload["tools"] if item["name"] == name)
            return subprocess.CompletedProcess(
                arguments, 0, stdout=expected_version_output(tool), stderr=""
            )

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            destination = parent / "bin"
            malicious_path = parent / "malicious-path"
            malicious_path.mkdir()
            self.assertFalse(destination.exists())
            for name in ("actionlint", "shellcheck"):
                fake = malicious_path / name
                fake.write_text(
                    "#!/bin/sh\necho malicious PATH fallback\n", encoding="utf-8"
                )
                fake.chmod(0o777)
            previous_path = os.environ.get("PATH")
            os.environ["PATH"] = str(malicious_path)
            installed = None
            try:
                installed = self.installer._install_validated_tools(
                    payload,
                    destination,
                    opener=opener,
                    runner=runner,
                    system="Linux",
                    machine="x86_64",
                )
                installed.verify()
                self.assertEqual({"actionlint", "shellcheck"}, set(installed))
                for name, path in installed.items():
                    self.assertEqual(destination / name, path)
                    self.assertTrue(path.is_absolute())
                    self.assertEqual(0o555, stat.S_IMODE(path.stat().st_mode))
            finally:
                if previous_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = previous_path
                if installed is not None:
                    installed.close()
            self.assertEqual(
                [
                    [str(destination / "actionlint"), "-version"],
                    [str(destination / "shellcheck"), "--version"],
                ],
                calls,
            )
            self.assertEqual(2, len(executables))
            self.assertTrue(
                all(
                    executable is not None
                    and executable.startswith(("/proc/self/fd/", "/dev/fd/"))
                    and executable not in {str(path) for path in installed.values()}
                    for executable in executables
                )
            )

    def test_preexisting_destination_target_or_symlink_fails_closed(self):
        payload, archives = fixture_lock()
        for kind in ("empty", "regular", "symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory).resolve()
                destination = parent / "bin"
                destination.mkdir()
                target = destination / "actionlint"
                if kind == "regular":
                    target.write_text("unreviewed\n", encoding="utf-8")
                elif kind == "symlink":
                    outside = parent / "outside"
                    outside.write_text("unreviewed\n", encoding="utf-8")
                    target.symlink_to(outside)
                with self.assertRaises(self.installer.ToolchainError):
                    self.installer._install_validated_tools(
                        payload,
                        destination,
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=subprocess.run,
                        system="Linux",
                        machine="x86_64",
                    )
                self.assertTrue(destination.is_dir())
                if kind == "empty":
                    self.assertEqual([], list(destination.iterdir()))
                else:
                    self.assertTrue(target.exists())
                    self.assertEqual(
                        "unreviewed\n", target.read_text(encoding="utf-8")
                    )

    def test_symlinked_or_untrusted_destination_parent_fails_closed(self):
        payload, archives = fixture_lock()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            real_parent = parent / "real-parent"
            real_parent.mkdir()
            symlink_parent = parent / "linked-parent"
            symlink_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "unsafe or missing parent"
            ):
                self.installer._install_validated_tools(
                    payload,
                    symlink_parent / "bin",
                    opener=lambda url: FakeResponse(archives[url], final_url=url),
                    runner=subprocess.run,
                    system="Linux",
                    machine="x86_64",
                )
            self.assertFalse((real_parent / "bin").exists())

            writable_parent = parent / "writable-parent"
            writable_parent.mkdir(mode=0o770)
            writable_parent.chmod(0o770)
            try:
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "current-user owned"
                ):
                    self.installer._install_validated_tools(
                        payload,
                        writable_parent / "bin",
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=subprocess.run,
                        system="Linux",
                        machine="x86_64",
                    )
            finally:
                writable_parent.chmod(0o700)

    def test_partial_install_failure_isolates_every_known_staging_file(self):
        payload, archives = fixture_lock()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            destination = parent / "bin"
            with mock.patch.object(
                self.installer,
                "_hash_descriptor",
                side_effect=self.installer.ToolchainError("forced pre-record failure"),
            ):
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "forced pre-record failure"
                ):
                    self.installer._install_validated_tools(
                        payload,
                        destination,
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=subprocess.run,
                        system="Linux",
                        machine="x86_64",
                    )
            self.assertFalse(destination.exists())
            self.assertEqual([], list(parent.glob(".ci-tools-staging-*")))
            quarantines = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(quarantines))

    def test_abort_preserves_replaced_known_name_before_or_after_recording(self):
        payload = b"reviewed binary"
        policy = {
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            staging = parent / area.staging_name
            area.install("tool", payload, policy)
            (staging / "tool").rename(staging / "held-original")
            (staging / "tool").write_bytes(b"replacement")
            area.abort()
            quarantines = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(quarantines))
            self.assertEqual(b"replacement", (quarantines[0] / "tool").read_bytes())
            self.assertEqual(
                payload, (quarantines[0] / "held-original").read_bytes()
            )

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            staging = parent / area.staging_name

            def replace_before_record(_descriptor, _maximum):
                (staging / "tool").rename(staging / "held-original")
                (staging / "tool").write_bytes(b"replacement")
                raise self.installer.ToolchainError("forced pre-record failure")

            with mock.patch.object(
                self.installer,
                "_hash_descriptor",
                side_effect=replace_before_record,
            ), self.assertRaisesRegex(
                self.installer.ToolchainError, "forced pre-record failure"
            ):
                area.install("tool", payload, policy)
            area.abort()
            quarantines = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(quarantines))
            self.assertEqual(b"replacement", (quarantines[0] / "tool").read_bytes())
            self.assertEqual(
                payload, (quarantines[0] / "held-original").read_bytes()
            )

    def test_abort_quarantines_before_verifying_file_and_directory_identity(self):
        payload = b"reviewed binary"
        policy = {
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        real_rename = self.installer._rename_noreplace

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            staging = parent / area.staging_name
            area.install("tool", payload, policy)
            swapped = False

            def swap_file_before_quarantine(parent_fd, source, destination):
                nonlocal swapped
                if source == "tool" and not swapped:
                    swapped = True
                    os.rename(
                        "tool",
                        "held-original",
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    replacement_fd = os.open(
                        "tool",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=parent_fd,
                    )
                    os.write(replacement_fd, b"replacement")
                    os.close(replacement_fd)
                return real_rename(parent_fd, source, destination)

            with mock.patch.object(
                self.installer,
                "_rename_noreplace",
                side_effect=swap_file_before_quarantine,
            ):
                area.abort()
            self.assertTrue(swapped)
            quarantines = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(quarantines))
            self.assertEqual(b"replacement", (quarantines[0] / "tool").read_bytes())
            self.assertEqual(
                payload, (quarantines[0] / "held-original").read_bytes()
            )

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            original_name = area.staging_name
            original = parent / original_name
            swapped = False

            def swap_directory_before_quarantine(parent_fd, source, destination):
                nonlocal swapped
                if source == original_name and not swapped:
                    swapped = True
                    os.rename(
                        source,
                        f"{source}.held-original",
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    os.mkdir(source, 0o700, dir_fd=parent_fd)
                    replacement_directory_fd = os.open(
                        source,
                        self.installer._directory_flags(),
                        dir_fd=parent_fd,
                    )
                    try:
                        replacement_fd = os.open(
                            "replacement-marker",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=replacement_directory_fd,
                        )
                        os.close(replacement_fd)
                    finally:
                        os.close(replacement_directory_fd)
                return real_rename(parent_fd, source, destination)

            with mock.patch.object(
                self.installer,
                "_rename_noreplace",
                side_effect=swap_directory_before_quarantine,
            ):
                area.abort()
            self.assertTrue(swapped)
            self.assertTrue((original / "replacement-marker").is_file())
            self.assertTrue((parent / f"{original_name}.held-original").is_dir())

    def test_abort_preserves_post_verification_file_and_directory_swaps(self):
        payload = b"reviewed binary"
        policy = {
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        real_stat = self.installer.os.stat

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            area.install("tool", payload, policy)
            swapped = False

            def swap_file_after_verified_stat(path, *args, **kwargs):
                nonlocal swapped
                metadata = real_stat(path, *args, **kwargs)
                dir_fd = kwargs.get("dir_fd")
                if (
                    isinstance(path, str)
                    and path.startswith(".ci-tools-abort-entry-")
                    and dir_fd is not None
                    and not swapped
                ):
                    swapped = True
                    held = f"{path}.verified-original"
                    os.rename(
                        path,
                        held,
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    replacement_fd = os.open(
                        path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=dir_fd,
                    )
                    os.write(replacement_fd, b"replacement")
                    os.close(replacement_fd)
                return metadata

            with mock.patch.object(
                self.installer.os,
                "stat",
                side_effect=swap_file_after_verified_stat,
            ):
                area.abort()
            self.assertTrue(swapped)
            directories = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(directories))
            contents = sorted(
                path.read_bytes()
                for path in directories[0].iterdir()
                if path.is_file()
            )
            self.assertEqual(sorted([payload, b"replacement"]), contents)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            area = self.installer._StagingArea(parent / "bin")
            swapped = False

            def swap_directory_after_verified_stat(path, *args, **kwargs):
                nonlocal swapped
                metadata = real_stat(path, *args, **kwargs)
                dir_fd = kwargs.get("dir_fd")
                if (
                    isinstance(path, str)
                    and path.startswith(".ci-tools-abort-directory-")
                    and dir_fd is not None
                    and not swapped
                ):
                    swapped = True
                    held = f"{path}.verified-original"
                    os.rename(
                        path,
                        held,
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    os.mkdir(path, 0o700, dir_fd=dir_fd)
                    replacement_directory_fd = os.open(
                        path,
                        self.installer._directory_flags(),
                        dir_fd=dir_fd,
                    )
                    try:
                        marker_fd = os.open(
                            "replacement-marker",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=replacement_directory_fd,
                        )
                        os.close(marker_fd)
                    finally:
                        os.close(replacement_directory_fd)
                return metadata

            with mock.patch.object(
                self.installer.os,
                "stat",
                side_effect=swap_directory_after_verified_stat,
            ):
                area.abort()
            self.assertTrue(swapped)
            replacements = [
                path
                for path in parent.glob(".ci-tools-abort-directory-*")
                if path.is_dir() and (path / "replacement-marker").is_file()
            ]
            originals = list(
                parent.glob(".ci-tools-abort-directory-*.verified-original")
            )
            self.assertEqual(1, len(replacements))
            self.assertEqual(1, len(originals))

    def test_staged_binary_fifo_swap_is_nonblocking_and_cleaned(self):
        payload, archives = fixture_lock()
        real_open = self.installer.os.open
        swapped = False

        def swap_before_read(path, flags, *args, **kwargs):
            nonlocal swapped
            dir_fd = kwargs.get("dir_fd")
            if (
                path == "actionlint"
                and dir_fd is not None
                and (flags & os.O_ACCMODE) == os.O_RDONLY
                and not swapped
            ):
                swapped = True
                self.assertTrue(
                    flags & os.O_NONBLOCK,
                    "staged binary reopen omitted O_NONBLOCK",
                )
                return real_open(fifo, flags)
            return real_open(path, flags, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            destination = parent / "bin"
            fifo = parent / "substituted-binary.fifo"
            os.mkfifo(fifo)
            started = time.monotonic()
            with mock.patch.object(
                self.installer.os, "open", side_effect=swap_before_read
            ):
                with self.assertRaises(self.installer.ToolchainError):
                    self.installer._install_validated_tools(
                        payload,
                        destination,
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=subprocess.run,
                        system="Linux",
                        machine="x86_64",
                    )
            self.assertTrue(swapped)
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertFalse(destination.exists())
            self.assertEqual([], list(parent.glob(".ci-tools-staging-*")))

    def test_staging_identity_and_unknown_entries_fail_closed_without_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            destination = parent / "bin"
            area = self.installer._StagingArea(destination)
            staging = parent / area.staging_name
            descriptor = os.open(
                "unreviewed",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=area.directory_fd,
            )
            os.close(descriptor)
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "unknown entries"
            ):
                area.publish()
            area.abort()
            quarantines = list(parent.glob(".ci-tools-abort-directory-*"))
            self.assertEqual(1, len(quarantines))
            self.assertTrue((quarantines[0] / "unreviewed").is_file())
            self.assertFalse(destination.exists())

        real_open = self.installer.os.open
        captured = {}

        def replace_created_directory(path, flags, *args, **kwargs):
            dir_fd = kwargs.get("dir_fd")
            if (
                isinstance(path, str)
                and path.startswith(".ci-tools-staging-")
                and dir_fd is not None
                and "candidate" not in captured
            ):
                captured["candidate"] = path
                saved = f"{path}.original"
                os.rename(
                    path,
                    saved,
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
                os.mkdir(path, 0o700, dir_fd=dir_fd)
                replacement_fd = real_open(path, flags, *args, **kwargs)
                marker_fd = real_open(
                    "replacement-marker",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=replacement_fd,
                )
                os.close(marker_fd)
                os.close(replacement_fd)
            return real_open(path, flags, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            with mock.patch.object(
                self.installer.os,
                "open",
                side_effect=replace_created_directory,
            ):
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "staging directory binding"
                ):
                    self.installer._StagingArea(parent / "bin")
            replacement = parent / captured["candidate"]
            self.assertTrue((replacement / "replacement-marker").is_file())
            self.assertTrue(
                (parent / f"{captured['candidate']}.original").is_dir()
            )

    def test_version_evidence_requires_exact_line_and_linux_amd64_build_line(self):
        payload, archives = fixture_lock()
        actionlint = next(tool for tool in payload["tools"] if tool["name"] == "actionlint")
        shellcheck = next(tool for tool in payload["tools"] if tool["name"] == "shellcheck")
        exact = {
            "actionlint": expected_version_output(actionlint),
            "shellcheck": expected_version_output(shellcheck),
        }
        cases = (
            (
                "actionlint-prefix",
                "actionlint 1.7.12\ninstalled from release\n"
                "built with go1.25.0 compiler for linux/amd64\n",
                None,
            ),
            (
                "actionlint-near",
                "1.7.120\ninstalled from release\n"
                "built with go1.25.0 compiler for linux/amd64\n",
                None,
            ),
            (
                "actionlint-platform",
                "1.7.12\ninstalled from release\n"
                "built with go1.25.0 compiler for darwin/arm64\n",
                None,
            ),
            ("shellcheck-near", None, "ShellCheck\nversion: 0.11.0-dev\n"),
        )
        for label, action_output, shell_output in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                outputs = dict(exact)
                if action_output is not None:
                    outputs["actionlint"] = action_output
                if shell_output is not None:
                    outputs["shellcheck"] = shell_output

                def runner(arguments, **_kwargs):
                    name = Path(arguments[0]).name
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=outputs[name], stderr=""
                    )

                with self.assertRaises(self.installer.ToolchainError):
                    self.installer._install_validated_tools(
                        payload,
                        Path(directory).resolve() / "bin",
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=runner,
                        system="Linux",
                        machine="x86_64",
                    )

    def test_version_probe_timeout_and_output_size_are_bounded(self):
        payload, archives = fixture_lock()

        def timeout_runner(arguments, **_kwargs):
            raise subprocess.TimeoutExpired(arguments, 0.01)

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(self.installer, "_VERSION_TIMEOUT_SECONDS", 0.01):
                with self.assertRaises(self.installer.ToolchainError):
                    self.installer._install_validated_tools(
                        payload,
                        Path(directory).resolve() / "timeout-bin",
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=timeout_runner,
                        system="Linux",
                        machine="x86_64",
                    )

        def oversized_runner(arguments, **_kwargs):
            return subprocess.CompletedProcess(
                arguments, 0, stdout="x" * 9, stderr=""
            )

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(self.installer, "_MAX_VERSION_OUTPUT_BYTES", 8):
                with self.assertRaises(self.installer.ToolchainError):
                    self.installer._install_validated_tools(
                        payload,
                        Path(directory).resolve() / "oversized-bin",
                        opener=lambda url: FakeResponse(
                            archives[url], final_url=url
                        ),
                        runner=oversized_runner,
                        system="Linux",
                        machine="x86_64",
                    )

    def test_published_binary_and_directory_namespace_swaps_fail_closed(self):
        payload, archives = fixture_lock()

        def runner(arguments, **_kwargs):
            name = Path(arguments[0]).name
            tool = next(item for item in payload["tools"] if item["name"] == name)
            return subprocess.CompletedProcess(
                arguments, 0, stdout=expected_version_output(tool), stderr=""
            )

        for swap in ("binary", "directory"):
            with self.subTest(swap=swap), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory).resolve()
                destination = parent / "bin"
                installed = self.installer._install_validated_tools(
                    payload,
                    destination,
                    opener=lambda url: FakeResponse(archives[url], final_url=url),
                    runner=runner,
                    system="Linux",
                    machine="x86_64",
                )
                try:
                    if swap == "binary":
                        original = parent / "original-actionlint"
                        (destination / "actionlint").rename(original)
                        replacement = destination / "actionlint"
                        replacement.write_text(
                            "#!/bin/sh\nprintf '1.7.12\\n'\n", encoding="utf-8"
                        )
                        replacement.chmod(0o555)
                    else:
                        original = parent / "original-bin"
                        destination.rename(original)
                        destination.mkdir(mode=0o700)
                    with self.assertRaises(self.installer.ToolchainError):
                        installed.verify()
                finally:
                    installed.close()

    def test_real_streaming_runner_caps_output_and_kills_process_group(self):
        with self.assertRaisesRegex(
            self.installer.ToolchainError, "output exceeds its bound"
        ):
            self.installer._run_bounded_process(
                [
                    sys.executable,
                    "-c",
                    "import os\nwhile True: os.write(1, b'x' * 4096)",
                ],
                label="real spewing process",
                timeout=5,
                maximum=8192,
            )

        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory).resolve() / "child.pid"
            program = (
                "import pathlib,subprocess,sys,time\n"
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
                "time.sleep(60)\n"
            )
            started = time.monotonic()
            with self.assertRaisesRegex(self.installer.ToolchainError, "timed out"):
                self.installer._run_bounded_process(
                    [sys.executable, "-c", program],
                    label="real process-group timeout",
                    timeout=0.5,
                    maximum=1024,
                )
            self.assertLess(time.monotonic() - started, 3.0)
            self.assertTrue(pid_file.is_file())
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and self._process_is_running(child_pid):
                time.sleep(0.05)
            self.assertFalse(
                self._process_is_running(child_pid),
                "timed-out descendant survived the process-group kill",
            )

    def test_process_monitor_failure_still_kills_and_reaps_the_group(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory).resolve() / "monitor-child.pid"
            program = (
                "import pathlib,subprocess,sys,time\n"
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
                "print('ready', flush=True)\n"
                "time.sleep(60)\n"
            )

            real_selector = self.installer.selectors.DefaultSelector

            class FailedSelector:
                def __init__(self):
                    self.delegate = real_selector()

                def register(self, *arguments, **kwargs):
                    return self.delegate.register(*arguments, **kwargs)

                def unregister(self, *arguments, **kwargs):
                    return self.delegate.unregister(*arguments, **kwargs)

                def get_map(self):
                    return self.delegate.get_map()

                def select(self, _timeout=None):
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline and not pid_file.is_file():
                        time.sleep(0.01)
                    raise OSError("injected monitor failure")

                def close(self):
                    self.delegate.close()

            with mock.patch.object(
                self.installer.selectors,
                "DefaultSelector",
                side_effect=FailedSelector,
            ):
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "process monitoring failed"
                ):
                    self.installer._run_bounded_process(
                        [sys.executable, "-c", program],
                        label="monitor failure",
                        timeout=5,
                        maximum=1024,
                    )
            self.assertTrue(pid_file.is_file())
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and self._process_is_running(child_pid):
                time.sleep(0.05)
            self.assertFalse(self._process_is_running(child_pid))

    def test_selector_construction_failure_reaps_the_spawned_process(self):
        real_popen = self.installer.subprocess.Popen
        spawned = []

        def record_popen(*arguments, **kwargs):
            process = real_popen(*arguments, **kwargs)
            spawned.append(process)
            return process

        with mock.patch.object(
            self.installer.subprocess, "Popen", side_effect=record_popen
        ), mock.patch.object(
            self.installer.selectors,
            "DefaultSelector",
            side_effect=OSError("selector exhaustion"),
        ):
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "process monitoring failed"
            ):
                self.installer._run_bounded_process(
                    [sys.executable, "-c", "import time;time.sleep(60)"],
                    label="selector construction",
                    timeout=5,
                    maximum=1024,
                )
        self.assertEqual(1, len(spawned))
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux fd execution contract")
    def test_inherited_executable_fd_reaches_a_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory).resolve() / "held-tool"
            script.write_text("#!/bin/sh\nprintf 'grandchild-ok\\n'\n", encoding="utf-8")
            script.chmod(0o555)
            descriptor = os.open(script, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fd_path = f"/proc/self/fd/{descriptor}"
                helper = (
                    "import subprocess,sys\n"
                    "fd=int(sys.argv[1])\n"
                    "path=f'/proc/self/fd/{fd}'\n"
                    "result=subprocess.run([path],pass_fds=(fd,),check=True,"
                    "stdout=subprocess.PIPE)\n"
                    "sys.stdout.buffer.write(result.stdout)\n"
                )
                result = self.installer._run_bounded_process(
                    [sys.executable, "-c", helper, str(descriptor)],
                    label="fd grandchild execution",
                    timeout=5,
                    maximum=1024,
                    inherited_fds=(descriptor,),
                )
                self.assertEqual(0, result.returncode)
                self.assertEqual(b"grandchild-ok\n", result.stdout)
                self.assertEqual(fd_path, f"/proc/self/fd/{descriptor}")
            finally:
                os.close(descriptor)

    @staticmethod
    def _process_is_running(pid):
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        state = result.stdout.strip()
        return result.returncode == 0 and state and not state.startswith("Z")

    @staticmethod
    def _git(root, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _scan_repository(self, parent, *, second_script=False):
        root = parent / "repository"
        root.mkdir()
        self._git(root, "init", "-q")
        workflow = root / ".github/workflows/ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: fixture\n", encoding="utf-8")
        script = root / "script.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if second_script:
            (root / "second.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self._git(root, "add", ".")
        return root

    def test_tracked_scan_rejects_symlink_fifo_and_oversized_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            tracked_link = root / "tracked-link"
            tracked_link.symlink_to("script.sh")
            self._git(root, "add", "tracked-link")
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "index is ambiguous or unsafe"
            ):
                self.installer._prepare_repository_scan(root)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            script = root / "script.sh"
            script.unlink()
            os.mkfifo(script)
            started = time.monotonic()
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "scan input is unsafe"
            ):
                self.installer._prepare_repository_scan(root)
            self.assertLess(time.monotonic() - started, 1.0)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            (root / "script.sh").write_bytes(b"x" * 65)
            with mock.patch.object(self.installer, "_MAX_LINT_INPUT_BYTES", 64):
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "scan input is unsafe"
                ):
                    self.installer._prepare_repository_scan(root)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent, second_script=True)
            with mock.patch.object(
                self.installer, "_MAX_LINT_INPUT_AGGREGATE_BYTES", 20
            ):
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "aggregate bound"
                ):
                    self.installer._prepare_repository_scan(root)

    def test_tracked_scan_rejects_symlink_components_and_post_scan_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            outside = parent / "outside-github"
            (root / ".github").rename(outside)
            (root / ".github").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                self.installer.ToolchainError, "cannot be opened safely"
            ):
                self.installer._prepare_repository_scan(root)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            scan = self.installer._prepare_repository_scan(root)
            try:
                original = root / "original-script"
                (root / "script.sh").rename(original)
                replacement = root / "script.sh"
                replacement.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    self.installer.ToolchainError, "scan input changed"
                ):
                    scan.verify()
            finally:
                scan.close()

    def test_repository_lints_descriptor_bound_bytes_during_swap_and_restore(self):
        payload, archives = fixture_lock()

        def version_runner(arguments, **_kwargs):
            name = Path(arguments[0]).name
            tool = next(item for item in payload["tools"] if item["name"] == name)
            return subprocess.CompletedProcess(
                arguments, 0, stdout=expected_version_output(tool), stderr=""
            )

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = self._scan_repository(parent)
            installed = self.installer._install_validated_tools(
                payload,
                parent / "tools",
                opener=lambda url: FakeResponse(archives[url], final_url=url),
                runner=version_runner,
                system="Linux",
                machine="x86_64",
            )
            expected = {
                "shellcheck": (root / "script.sh").read_bytes(),
                "actionlint": (root / ".github/workflows/ci.yml").read_bytes(),
            }
            observations = {}

            def lint_runner(arguments, **_kwargs):
                tool = Path(arguments[0]).name
                lexical = (
                    root / "script.sh"
                    if tool == "shellcheck"
                    else root / ".github/workflows/ci.yml"
                )
                saved = lexical.with_name(lexical.name + ".held-original")
                lexical.rename(saved)
                lexical.write_text("malicious replacement\n", encoding="utf-8")
                try:
                    inputs = arguments[arguments.index("--") + 1 :]
                    observations[tool] = [
                        (
                            Path(argument)
                            if Path(argument).is_absolute()
                            else root / argument
                        ).read_bytes()
                        for argument in inputs
                    ]
                finally:
                    lexical.unlink()
                    saved.rename(lexical)
                return subprocess.CompletedProcess(
                    arguments, 0, stdout="", stderr=""
                )

            try:
                self.installer._check_repository(
                    installed, root=root, runner=lint_runner
                )
                self.assertEqual({"shellcheck", "actionlint"}, set(observations))
                for tool, observed in observations.items():
                    self.assertEqual([expected[tool]], observed)
            finally:
                installed.close()

    def _run_main_offline(self, destination, *, fail_repository_check=False):
        payload, archives = fixture_lock()
        real_loader = self.installer.load_reviewed_lock
        real_bounded_runner = self.installer._run_bounded_process
        real_close = self.installer._InstalledTools.close
        real_scan_close = self.installer._RepositoryScan.close
        calls = []
        call_details = []
        close_states = []
        scan_close_states = []

        def reviewed_loader(path):
            real_loader(path)
            return payload

        def download(artifact, *_arguments, **_kwargs):
            return archives[artifact["url"]]

        def runner(arguments, **kwargs):
            arguments = [str(argument) for argument in arguments]
            if arguments[0] == "git":
                return real_bounded_runner(arguments, **kwargs)
            calls.append(arguments)
            call_details.append((arguments, dict(kwargs)))
            name = Path(arguments[0]).name
            if arguments[1:] == ["-version"] and name == "actionlint":
                output = expected_version_output(payload["tools"][0])
                return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")
            if arguments[1:] == ["--version"] and name == "shellcheck":
                output = expected_version_output(payload["tools"][1])
                return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")
            if fail_repository_check and name == "actionlint":
                return subprocess.CompletedProcess(arguments, 3, stdout="", stderr="lint failed")
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

        def close_tools(instance):
            binary_before = [
                record["fd"] for record in instance._area.records.values()
            ]
            before = binary_before + [
                instance._area.directory_fd,
                instance._area.parent_fd,
            ]
            real_close(instance)
            binary_after = [
                record["fd"] for record in instance._area.records.values()
            ]
            after = binary_after + [
                instance._area.directory_fd,
                instance._area.parent_fd,
            ]
            close_states.append(
                {
                    "before": before,
                    "after": after,
                    "closed": [self._descriptor_is_closed(fd) for fd in before],
                }
            )

        def close_scan(instance):
            before = [instance.root_fd] + [
                record["fd"] for record in instance.records.values()
            ]
            real_scan_close(instance)
            scan_close_states.append(
                {
                    "before": before,
                    "root_after": instance.root_fd,
                    "records_after": dict(instance.records),
                    "closed": [self._descriptor_is_closed(fd) for fd in before],
                }
            )

        stdout = io.StringIO()
        with contextlib.ExitStack() as stack:
            loader = stack.enter_context(
                mock.patch.object(
                self.installer, "load_reviewed_lock", side_effect=reviewed_loader
                )
            )
            stack.enter_context(
                mock.patch.object(
                self.installer, "_download_artifact", side_effect=download
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.installer.platform, "system", return_value="Linux"
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.installer.platform, "machine", return_value="x86_64"
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.installer, "_run_bounded_process", side_effect=runner
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.installer._InstalledTools, "close", new=close_tools
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.installer._RepositoryScan, "close", new=close_scan
                )
            )
            stack.enter_context(contextlib.redirect_stdout(stdout))
            result = self.installer.main(
                [
                    "--lock",
                    str(LOCK),
                    "--destination",
                    str(destination),
                    "--check-repository",
                ]
            )
        loader.assert_called_once()
        self.assertEqual(LOCK.resolve(), Path(loader.call_args.args[0]).resolve())
        return (
            result,
            calls,
            call_details,
            close_states,
            scan_close_states,
            stdout.getvalue(),
        )

    @staticmethod
    def _descriptor_is_closed(descriptor):
        try:
            os.fstat(descriptor)
        except OSError:
            return True
        return False

    @staticmethod
    def _fd_number(path):
        return int(path.rsplit("/", 1)[1])

    def test_real_main_offline_orchestration_uses_only_pinned_absolute_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = (Path(directory) / "bin").resolve()
            (
                result,
                calls,
                details,
                close_states,
                scan_close_states,
                output,
            ) = self._run_main_offline(destination)
            self.assertEqual(0, result)
            actionlint = str(destination / "actionlint")
            shellcheck = str(destination / "shellcheck")
            self.assertIn([actionlint, "-version"], calls)
            self.assertIn([shellcheck, "--version"], calls)
            shellcheck_checks = [
                call
                for call in calls
                if call[0] == shellcheck and call != [shellcheck, "--version"]
            ]
            actionlint_checks = [
                call
                for call in calls
                if call[0] == actionlint and call != [actionlint, "-version"]
            ]
            self.assertEqual(1, len(shellcheck_checks))
            self.assertEqual("--norc", shellcheck_checks[0][1])
            self.assertEqual(1, shellcheck_checks[0].count("--norc"))
            shell_inputs = shellcheck_checks[0][
                shellcheck_checks[0].index("--") + 1 :
            ]
            self.assertTrue(shell_inputs)
            self.assertTrue(
                all(
                    argument.startswith(("/proc/self/fd/", "/dev/fd/"))
                    for argument in shell_inputs
                )
            )
            self.assertEqual(1, len(actionlint_checks))
            shellcheck_arguments = [
                argument
                for argument in actionlint_checks[0]
                if argument.startswith("-shellcheck=")
            ]
            self.assertEqual(1, len(shellcheck_arguments))
            held_shellcheck = shellcheck_arguments[0].split("=", 1)[1]
            self.assertTrue(
                held_shellcheck.startswith(("/proc/self/fd/", "/dev/fd/"))
            )
            self.assertNotEqual(shellcheck, held_shellcheck)
            self.assertIn("-pyflakes=", actionlint_checks[0])
            self.assertEqual(
                1, actionlint_checks[0].count("-config-file=/dev/null")
            )
            workflow_inputs = actionlint_checks[0][
                actionlint_checks[0].index("--") + 1 :
            ]
            self.assertTrue(workflow_inputs)
            self.assertTrue(
                all(
                    argument.startswith(("/proc/self/fd/", "/dev/fd/"))
                    for argument in workflow_inputs
                )
            )
            self.assertIn("\n1.7.12\n", f"\n{output}")
            self.assertIn("version: 0.11.0\n", output)
            self.assertIn("compiler for linux/amd64\n", output)
            actionlint_detail = next(
                kwargs
                for call, kwargs in details
                if call == actionlint_checks[0]
            )
            shellcheck_detail = next(
                kwargs
                for call, kwargs in details
                if call == shellcheck_checks[0]
            )
            self.assertIsInstance(shellcheck_detail["executable_fd"], int)
            self.assertIsInstance(actionlint_detail["executable_fd"], int)
            self.assertNotEqual(
                shellcheck_detail["executable_fd"],
                actionlint_detail["executable_fd"],
            )
            self.assertEqual(
                {self._fd_number(path) for path in shell_inputs},
                set(shellcheck_detail["inherited_fds"]),
            )
            inherited = set(actionlint_detail["inherited_fds"])
            self.assertIn(self._fd_number(held_shellcheck), inherited)
            self.assertTrue(
                {self._fd_number(path) for path in workflow_inputs}.issubset(inherited)
            )
            self.assertEqual(1, len(close_states))
            state = close_states[0]
            self.assertEqual(4, len(state["before"]))
            self.assertTrue(all(descriptor >= 0 for descriptor in state["before"]))
            self.assertEqual([-1, -1, -1, -1], state["after"])
            self.assertEqual([True] * 4, state["closed"])
            self.assertEqual(1, len(scan_close_states))
            scan_state = scan_close_states[0]
            self.assertEqual(-1, scan_state["root_after"])
            self.assertEqual({}, scan_state["records_after"])
            self.assertTrue(all(scan_state["closed"]))

    def test_real_main_propagates_repository_check_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            (
                result,
                _calls,
                _details,
                close_states,
                scan_close_states,
                _output,
            ) = self._run_main_offline(
                (Path(directory) / "bin").resolve(), fail_repository_check=True
            )
            self.assertNotEqual(0, result)
            self.assertEqual(1, len(close_states))
            self.assertEqual([-1, -1, -1, -1], close_states[0]["after"])
            self.assertTrue(all(close_states[0]["closed"]))
            self.assertEqual(1, len(scan_close_states))
            self.assertEqual(-1, scan_close_states[0]["root_after"])
            self.assertTrue(all(scan_close_states[0]["closed"]))


if __name__ == "__main__":
    unittest.main()
