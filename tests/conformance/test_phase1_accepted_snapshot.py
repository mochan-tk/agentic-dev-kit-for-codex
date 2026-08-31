import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-phase1-accepted-snapshot.py"
SNAPSHOT = ROOT / "tests/conformance/phase1-accepted-snapshot.v1.json"


class Phase1AcceptedSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("phase1_snapshot", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot import accepted-snapshot checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def payload(self):
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    def resign(self, payload):
        payload["manifest_sha256"] = self.checker.canonical_snapshot_digest(payload)

    def assert_rejected(self, errors, marker):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid snapshot unexpectedly passed")
        self.assertIn(marker, rendered)

    def verified(self):
        payload, contents, errors = self.checker.verified_snapshot_contents(ROOT)
        self.assertEqual([], errors)
        self.assertIsNotNone(payload)
        return payload, contents

    def materialized(self):
        payload, contents = self.verified()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repository"
        repository.mkdir(mode=0o700)
        repository.chmod(0o700)
        self.checker.materialize_snapshot(repository, payload, contents)
        return repository, payload

    def run_fixture_checker(self, snapshot_bytes):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name)
        checker = repository / ".github/scripts/check-phase1-accepted-snapshot.py"
        checker.parent.mkdir(parents=True)
        shutil.copy2(CHECKER, checker)
        snapshot = repository / self.checker.SNAPSHOT_PATH
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes(snapshot_bytes)
        return subprocess.run(
            ["python3", "-I", os.fspath(checker)],
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )

    def test_current_repository_replays_exact_accepted_phase1(self):
        self.assertEqual([], self.checker.validate_historical_repository(ROOT))

    def test_snapshot_binds_complete_tree_and_historical_checker(self):
        payload, contents = self.verified()
        self.assertEqual(self.checker.ACCEPTED_COMMIT, payload["accepted_commit"])
        self.assertEqual(self.checker.ACCEPTED_TREE, payload["accepted_tree"])
        self.assertEqual(self.checker.ACCEPTED_PARENTS, payload["accepted_parents"])
        self.assertEqual(92, len(payload["files"]))
        self.assertEqual(92, len(contents))
        self.assertEqual(1_561_147, sum(len(value) for value in contents.values()))
        checker = payload["historical_checker"]
        self.assertEqual(self.checker.HISTORICAL_CHECKER_BLOB, checker["blob"])
        self.assertEqual(self.checker.HISTORICAL_CHECKER_SHA256, checker["sha256"])
        self.assertEqual(self.checker.HISTORICAL_CHECKER_SIZE, checker["size"])

    def test_manifest_digest_and_exact_commit_tree_parent_bindings_reject_drift(self):
        for field, replacement, marker in (
            ("accepted_commit", "0" * 40, "commit binding drifted"),
            ("accepted_tree", "1" * 40, "tree binding drifted"),
            ("accepted_parents", list(reversed(self.checker.ACCEPTED_PARENTS)), "ordered parent"),
        ):
            with self.subTest(field=field):
                payload = self.payload()
                payload[field] = replacement
                self.resign(payload)
                self.assert_rejected(
                    self.checker.validate_snapshot_payload(payload), marker
                )

        payload = self.payload()
        payload["path_count"] = 91
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "manifest digest mismatch"
        )

    def test_missing_commit_object_is_a_bounded_failure(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name)
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q"],
            cwd=repository,
            check=True,
        )
        errors = self.checker.validate_historical_repository(repository, self.payload())
        self.assert_rejected(errors, "commit object is missing or unreadable")

    def test_blob_digest_or_size_drift_is_rejected_against_git_objects(self):
        payload = self.payload()
        item = next(
            entry
            for entry in payload["files"]
            if entry["path"] != self.checker.HISTORICAL_CHECKER_PATH
        )
        item["sha256"] = "0" * 64
        self.resign(payload)
        errors, _ = self.checker.verify_git_snapshot(ROOT, payload)
        self.assert_rejected(errors, "blob digest mismatch")

        payload = self.payload()
        item = next(
            entry
            for entry in payload["files"]
            if entry["path"] != self.checker.HISTORICAL_CHECKER_PATH
        )
        payload["total_bytes"] += 1
        item["size"] += 1
        self.resign(payload)
        errors = self.checker.validate_snapshot_payload(payload)
        self.assert_rejected(errors, "total byte binding drifted")

    def test_unsafe_path_mode_collision_count_and_size_are_rejected(self):
        payload = self.payload()
        payload["files"][0]["path"] = "../escape"
        self.resign(payload)
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "path is unsafe"
        )

        payload = self.payload()
        payload["files"][0]["mode"] = "120000"
        self.resign(payload)
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "unsafe mode"
        )

        payload = self.payload()
        payload["files"][0]["path"] = "collision/Σ"
        payload["files"][1]["path"] = "collision/σ"
        payload["files"].sort(key=lambda item: item["path"])
        self.resign(payload)
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "case or Unicode collision"
        )

        payload = self.payload()
        payload["files"] = payload["files"] * 3
        payload["path_count"] = len(payload["files"])
        payload["total_bytes"] = sum(item["size"] for item in payload["files"])
        self.resign(payload)
        errors = self.checker.validate_snapshot_payload(payload)
        self.assert_rejected(errors, "path-count safety limit")

        payload = self.payload()
        for item in payload["files"][:20]:
            item["size"] = self.checker.MAX_FILE_BYTES
        payload["total_bytes"] = sum(item["size"] for item in payload["files"])
        self.resign(payload)
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "total-byte safety limit"
        )

        payload = self.payload()
        payload["files"][0]["size"] = self.checker.MAX_FILE_BYTES + 1
        payload["total_bytes"] = sum(item["size"] for item in payload["files"])
        self.resign(payload)
        self.assert_rejected(
            self.checker.validate_snapshot_payload(payload), "file-size limit"
        )

    def test_snapshot_input_symlink_and_duplicate_json_key_are_rejected(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name)
        target = repository / self.checker.SNAPSHOT_PATH
        target.parent.mkdir(parents=True)
        target.symlink_to(SNAPSHOT)
        with self.assertRaises(OSError):
            self.checker.load_snapshot(repository)

        target.unlink()
        target.write_text('{"schema":"one","schema":"two"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            self.checker.load_snapshot(repository)

    def test_snapshot_input_oversize_and_fifo_fail_without_blocking(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name)
        target = repository / self.checker.SNAPSHOT_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x" * (self.checker.MAX_SNAPSHOT_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.checker.load_snapshot(repository)

        if hasattr(os, "mkfifo"):
            target.unlink()
            os.mkfifo(target)
            started = time.monotonic()
            with self.assertRaisesRegex(ValueError, "regular file"):
                self.checker.load_snapshot(repository)
            self.assertLess(time.monotonic() - started, 2)

    def test_non_finite_or_unbounded_json_numbers_fail_without_traceback(self):
        completed = self.run_fixture_checker(b'{"value":1e999}\n')
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)
        self.assertLess(len(completed.stdout) + len(completed.stderr), 1_048_576)

        payload = self.payload()
        payload["files"][0]["size"] = float("inf")
        errors = self.checker.validate_snapshot_payload(payload)
        self.assert_rejected(errors, "floating-point values are not allowed")

        completed = self.run_fixture_checker(b'{"value":999999999999999999999}\n')
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)

        completed = self.run_fixture_checker(b'{"value":"\\ud800"}\n')
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)

    def test_huge_malformed_file_list_has_bounded_work_and_findings(self):
        payload = self.payload()
        payload["files"] = [None] * (self.checker.MAX_PATHS + 44)
        payload["path_count"] = len(payload["files"])
        payload["total_bytes"] = 0
        self.resign(payload)
        started = time.monotonic()
        with mock.patch.object(
            self.checker,
            "_safe_relative_path",
            wraps=self.checker._safe_relative_path,
        ) as path_validator:
            errors = self.checker.validate_snapshot_payload(payload)
        self.assertLess(time.monotonic() - started, 2)
        self.assertLessEqual(path_validator.call_count, self.checker.MAX_PATHS + 1)
        self.assertLessEqual(len(errors), self.checker.MAX_FINDINGS)
        self.assertLess(
            sum(len(error.encode("utf-8")) + 3 for error in errors),
            1_048_576,
        )
        self.assertFalse(any("files[299]" in error for error in errors))

        body = b'{"files":[' + b",".join([b"null"] * 10_000) + b"]}\n"
        completed = self.run_fixture_checker(body)
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)
        self.assertLess(len(completed.stdout) + len(completed.stderr), 1_048_576)

    def test_snapshot_input_parent_namespace_swap_is_rejected(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name)
        target = repository / "tests/conformance"
        target.mkdir(parents=True)
        shutil.copy2(SNAPSHOT, target / SNAPSHOT.name)
        held = repository / "tests/conformance-held"
        original_read = self.checker.os.read
        swapped = False

        def swap_once(descriptor, size):
            nonlocal swapped
            if not swapped:
                swapped = True
                target.rename(held)
                target.mkdir()
                shutil.copy2(held / SNAPSHOT.name, target / SNAPSHOT.name)
            return original_read(descriptor, size)

        with mock.patch.object(self.checker.os, "read", side_effect=swap_once):
            with self.assertRaisesRegex(ValueError, "parent binding changed"):
                self.checker.load_snapshot(repository)

    def test_extraction_uses_private_directories_and_regular_0600_files(self):
        payload, contents = self.verified()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / "accepted"
        destination.mkdir(mode=0o700)
        destination.chmod(0o700)
        self.checker.materialize_snapshot(destination, payload, contents)
        self.assertEqual(0o700, stat.S_IMODE(destination.stat().st_mode))
        for item in payload["files"]:
            details = os.lstat(destination / item["path"])
            self.assertTrue(stat.S_ISREG(details.st_mode))
            self.assertEqual(0o600, stat.S_IMODE(details.st_mode))
            self.assertEqual(item["size"], details.st_size)
        for directory, children, _ in os.walk(destination):
            self.assertEqual(0o700, stat.S_IMODE(os.lstat(directory).st_mode))
            self.assertNotIn(".git", children)

    def test_post_extraction_mutation_of_unused_file_is_rejected(self):
        original = self.checker.materialize_snapshot

        def mutate_after_materialization(destination, payload, contents):
            original(destination, payload, contents)
            target = destination / ".gitignore"
            target.write_bytes(b"mutated after extraction\n")
            target.chmod(0o600)

        with mock.patch.object(
            self.checker,
            "materialize_snapshot",
            side_effect=mutate_after_materialization,
        ):
            errors = self.checker.validate_historical_repository(ROOT)
        self.assert_rejected(errors, "extracted Phase 1 path")

    def test_historical_checker_is_revalidated_and_pinned_immediately_before_run(self):
        original = self.checker.run_historical_checker

        def replace_before_pin(repository, home, temp):
            target = repository / self.checker.HISTORICAL_CHECKER_PATH
            target.write_bytes(b"raise SystemExit(0)\n")
            target.chmod(0o600)
            return original(repository, home, temp)

        with mock.patch.object(
            self.checker,
            "run_historical_checker",
            side_effect=replace_before_pin,
        ):
            errors = self.checker.validate_historical_repository(ROOT)
        self.assert_rejected(errors, "pin digest or size drifted")

    def test_unused_file_mutation_at_checker_boundary_fails_post_checker_validation(self):
        original = self.checker.run_historical_checker
        observed = {"real_checker_succeeded": False}

        def mutate_then_run_real_checker(repository, home, temp):
            target = repository / ".gitignore"
            target.write_bytes(b"mutated at checker boundary\n")
            target.chmod(0o600)
            checker_errors = original(repository, home, temp)
            observed["real_checker_succeeded"] = checker_errors == []
            return checker_errors

        with mock.patch.object(
            self.checker,
            "run_historical_checker",
            side_effect=mutate_then_run_real_checker,
        ):
            errors = self.checker.validate_historical_repository(ROOT)
        self.assertTrue(observed["real_checker_succeeded"])
        self.assert_rejected(errors, "extracted Phase 1 path")

    def test_pinned_checker_descriptor_survives_path_replacement_after_pin(self):
        repository, _ = self.materialized()
        home = repository.parent / "home"
        temp = repository.parent / "tmp"
        home.mkdir(mode=0o700)
        temp.mkdir(mode=0o700)
        observed = {}

        def replace_path_then_observe(argv, **kwargs):
            target = repository / self.checker.HISTORICAL_CHECKER_PATH
            held = target.with_name("checker-held.py")
            target.rename(held)
            target.write_bytes(b"raise SystemExit(0)\n")
            target.chmod(0o600)
            descriptor = kwargs["stdin_fd"]
            os.lseek(descriptor, 0, os.SEEK_SET)
            pinned = os.read(descriptor, self.checker.HISTORICAL_CHECKER_SIZE + 1)
            observed["digest"] = hashlib.sha256(pinned).hexdigest()
            return self.checker.CommandResult(
                0,
                self.checker.HISTORICAL_SUCCESS_STDOUT,
                b"",
            )

        with mock.patch.object(
            self.checker,
            "run_bounded",
            side_effect=replace_path_then_observe,
        ):
            errors = self.checker.run_historical_checker(
                repository,
                home,
                temp,
            )
        self.assertEqual([], errors)
        self.assertEqual(self.checker.HISTORICAL_CHECKER_SHA256, observed["digest"])

    def test_symlinked_extraction_root_or_parent_is_rejected(self):
        payload, contents = self.verified()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        held = base / "held"
        held.mkdir(mode=0o700)
        linked = base / "linked"
        linked.symlink_to(held, target_is_directory=True)
        with self.assertRaises(OSError):
            self.checker.materialize_snapshot(linked, payload, contents)

        target = base / "target"
        target.mkdir(mode=0o700)
        target.chmod(0o700)
        external = base / "external"
        external.mkdir(mode=0o700)
        (target / ".agents").symlink_to(external, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            self.checker.materialize_snapshot(target, payload, contents)

    def test_extraction_namespace_swap_is_rejected(self):
        payload, contents = self.verified()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / "accepted"
        destination.mkdir(mode=0o700)
        destination.chmod(0o700)
        original = self.checker._open_or_create_directory
        swapped = False

        def swap_once(parent_fd, name):
            nonlocal swapped
            descriptor = original(parent_fd, name)
            if not swapped:
                swapped = True
                os.rename(name, f"{name}-held", src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            return descriptor

        with mock.patch.object(
            self.checker, "_open_or_create_directory", side_effect=swap_once
        ):
            with self.assertRaisesRegex(ValueError, "parent binding changed"):
                self.checker.materialize_snapshot(destination, payload, contents)

    def test_historical_process_failure_timeout_and_output_excess_are_non_success(self):
        repository, _ = self.materialized()
        home = repository.parent / "home"
        temp = repository.parent / "tmp"
        home.mkdir(mode=0o700)
        temp.mkdir(mode=0o700)
        failure = self.checker.CommandResult(7, b"", b"failure")
        timeout = self.checker.CommandResult(124, b"", b"", timed_out=True)
        overflow = self.checker.CommandResult(1, b"x", b"", output_overflow=True)
        for result, marker in (
            (failure, "exit code 7"),
            (timeout, "timeout"),
            (overflow, "output limits"),
        ):
            with self.subTest(marker=marker):
                with mock.patch.object(self.checker, "run_bounded", return_value=result):
                    errors = self.checker.run_historical_checker(
                        repository, home, temp
                    )
                self.assert_rejected(errors, marker)

    def test_bounded_runner_terminates_process_groups_and_output_floods(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        timeout = self.checker.run_bounded(
            [
                "python3",
                "-I",
                "-c",
                "import subprocess,time; subprocess.Popen(['python3','-c','import time; time.sleep(30)']); time.sleep(30)",
            ],
            cwd=root,
            timeout_seconds=0.2,
            stdout_limit=32,
            stderr_limit=32,
            environment=self.checker._private_environment(),
        )
        self.assertTrue(timeout.timed_out)

        parent_exits = self.checker.run_bounded(
            [
                "python3",
                "-I",
                "-c",
                "import subprocess; subprocess.Popen(['python3','-c','import time; time.sleep(30)'])",
            ],
            cwd=root,
            timeout_seconds=0.2,
            stdout_limit=32,
            stderr_limit=32,
            environment=self.checker._private_environment(),
        )
        self.assertTrue(parent_exits.timed_out)

        closes_pipes = self.checker.run_bounded(
            [
                "python3",
                "-I",
                "-c",
                "import subprocess; subprocess.Popen(['python3','-c','import time; time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)",
            ],
            cwd=root,
            timeout_seconds=2,
            stdout_limit=32,
            stderr_limit=32,
            environment=self.checker._private_environment(),
        )
        self.assertTrue(closes_pipes.process_group_leak)

        flood = self.checker.run_bounded(
            ["python3", "-I", "-c", "import sys; sys.stdout.write('x'*10000)"],
            cwd=root,
            timeout_seconds=2,
            stdout_limit=64,
            stderr_limit=64,
            environment=self.checker._private_environment(),
        )
        self.assertTrue(flood.output_overflow)
        self.assertLessEqual(len(flood.stdout), 64)

    def test_missing_required_filesystem_capability_has_zero_external_side_effect(self):
        capability_patches = (
            mock.patch.object(self.checker.os, "O_NOFOLLOW", 0),
            mock.patch.object(self.checker.os, "O_DIRECTORY", 0),
            mock.patch.object(self.checker.os, "supports_dir_fd", frozenset()),
            mock.patch.object(
                self.checker.os,
                "supports_follow_symlinks",
                frozenset(),
            ),
        )
        for capability_patch in capability_patches:
            with self.subTest(capability_patch=repr(capability_patch)):
                with capability_patch:
                    with mock.patch.object(self.checker, "load_snapshot") as read:
                        with mock.patch.object(self.checker, "git_command") as git:
                            with mock.patch.object(
                                self.checker.tempfile, "mkdtemp"
                            ) as write:
                                errors = self.checker.validate_historical_repository(
                                    ROOT
                                )
                self.assert_rejected(errors, "required")
                read.assert_not_called()
                git.assert_not_called()
                write.assert_not_called()

    def test_all_git_commands_disable_replacement_objects_and_forbid_checkout(self):
        observed = []
        original = self.checker.run_bounded

        def record(argv, **kwargs):
            observed.append(list(argv))
            return original(argv, **kwargs)

        with mock.patch.object(self.checker, "run_bounded", side_effect=record):
            payload, contents, errors = self.checker.verified_snapshot_contents(ROOT)
        self.assertEqual([], errors)
        self.assertIsNotNone(payload)
        self.assertEqual(92, len(contents))
        self.assertTrue(observed)
        for argv in observed:
            self.assertEqual(["git", "--no-replace-objects"], argv[:2])
            self.assertTrue(
                {"checkout", "archive", "worktree", "clone", "fetch"}.isdisjoint(argv)
            )


if __name__ == "__main__":
    unittest.main()
