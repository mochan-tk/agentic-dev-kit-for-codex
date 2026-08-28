import copy
import datetime
import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / ".github/scripts/codex-exec-adapter.py"
CHECKER_PATH = ROOT / ".github/scripts/check-runtime-contracts.py"
ENVELOPE_PATH = ROOT / "tests/runtime/fixtures/envelope-valid.v1.json"
PROFILE_PATH = ROOT / "tests/runtime/fixtures/runtime-profile-valid.v1.json"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeVerticalSliceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_module(ADAPTER_PATH, "runtime_adapter_tests")
        cls.checker = load_module(CHECKER_PATH, "runtime_checker_tests")
        cls.envelope = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        cls.profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    def assert_contract_error(self, callback, token=None):
        with self.assertRaises(self.adapter.ContractError) as raised:
            callback()
        if token:
            self.assertIn(token, str(raised.exception))

    def minimal_process_environment(self, root, behavior=None):
        home = root / "home"
        tmp = root / "tmp"
        home.mkdir()
        tmp.mkdir()
        extra = {"T11_FAKE_BEHAVIOR": behavior} if behavior else None
        return self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmp, extra)

    def test_repository_runtime_contract_checker_passes(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))
        result = subprocess.run(
            [sys.executable, "-I", str(CHECKER_PATH)], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("runtime contracts: OK\n", result.stdout)

    def test_offline_slice_runs_one_worker_and_fresh_verifier(self):
        result = self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), copy.deepcopy(self.profile), "offline")
        self.assertEqual("pass", result["status"])
        self.assertEqual(1, result["worker"]["logical_invocations"])
        self.assertEqual(["work-item.txt"], result["git"]["changed_paths"])
        self.assertTrue(result["verifier"]["fresh_process"])
        self.assertTrue(result["verifier"]["read_only"])
        self.assertFalse(result["privacy"]["raw_jsonl_retained"])

    def test_offline_cli_uses_stdin_and_emits_no_private_path(self):
        result = subprocess.run(
            [sys.executable, "-I", str(ADAPTER_PATH), "run", "--mode", "offline"],
            cwd=ROOT, input=ENVELOPE_PATH.read_bytes(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("t11-runtime-artifact-bundle/v1", payload["schema"])
        self.assertEqual("pass", payload["execution_result"]["status"])
        self.assertEqual(
            payload["execution_result"]["verifier"]["record_sha256"],
            self.adapter.sha256_bytes(self.adapter.canonical_bytes(payload["verifier"])),
        )
        self.assertNotRegex(result.stdout.decode(), r"/Users/|/var/folders/|/tmp/")

    def test_committed_prerelease_profile_blocks_live_mode(self):
        profile = json.loads((ROOT / ".github/governance/codex-runtime-profile.v1.json").read_text(encoding="utf-8"))
        self.assertEqual("unsupported-client", profile["status"])
        self.assertFalse(profile["live_run_allowed"])
        self.assert_contract_error(
            lambda: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), profile, "live"),
            "blocked by runtime profile",
        )

    def test_profile_fail_closed_states_never_authorize_live(self):
        for state in ("profile-drift", "unsupported-client", "UNKNOWN", "UNCHECKABLE"):
            profile = copy.deepcopy(self.profile)
            profile["scope"] = "exact-head-live-sensor"
            profile["status"] = state
            profile["live_run_allowed"] = False
            if state != "unsupported-client":
                profile["client"]["release_class"] = "stable"
            profile["capabilities"]["config_recognition_probe"] = "UNCHECKABLE"
            profile["capabilities"]["shell_environment_probe"] = "UNCHECKABLE"
            self.adapter.validate_runtime_profile(profile)
            with self.subTest(state=state):
                self.assert_contract_error(
                    lambda p=profile: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), p, "live")
                )

    def test_profile_release_class_cannot_be_forged(self):
        forged = copy.deepcopy(self.profile)
        forged["client"]["version_output"] = "codex-cli 0.150.0-alpha.8"
        forged["client"]["release_class"] = "stable"
        forged["status"] = "match"
        forged["live_run_allowed"] = True
        self.assert_contract_error(
            lambda: self.adapter.validate_runtime_profile(forged, allow_fixture=True),
            "release class",
        )
        for field in ("exec_json", "ephemeral", "strict_config", "ignore_user_config", "workspace_write", "approval_never", "model", "reasoning", "sandbox", "approval", "overrides"):
            drift = copy.deepcopy(self.profile)
            drift["capabilities"][field] = False
            drift["status"] = "match"
            drift["live_run_allowed"] = True
            with self.subTest(field=field):
                self.assert_contract_error(lambda p=drift: self.adapter.validate_runtime_profile(p, allow_fixture=True))

    def test_stable_semantic_sensor_has_reachable_match_and_live_reprobes(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 1.2.3\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with mock.patch.object(self.adapter, "resolve_executable_from_path", return_value=Path(sys.executable)), \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "probe_runtime_configuration", return_value=("pass", "pass")), \
             mock.patch.object(self.adapter, "live_containment_proven", return_value=True), \
             mock.patch.object(self.adapter, "auth_class", return_value="signed-in-client"), \
             mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64):
            observed = self.adapter.observe_runtime_profile(ROOT, "gpt-5.6-sol", "high")
        self.assertEqual("match", observed["status"])
        self.assertTrue(observed["live_run_allowed"])

        supplied = copy.deepcopy(observed)
        supplied["observed_at"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        drifted = copy.deepcopy(supplied)
        drifted["status"] = "profile-drift"
        drifted["reason"] = "fresh semantic sensor differs"
        drifted["live_run_allowed"] = False
        with mock.patch.object(self.adapter, "observe_runtime_profile", return_value=drifted) as sensor, \
             mock.patch.object(self.adapter, "create_synthetic_repository") as create:
            self.assert_contract_error(
                lambda: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), supplied, "live"),
                "fresh",
            )
        sensor.assert_called_once()
        create.assert_not_called()

    def test_stable_sensor_blocks_live_when_descendant_containment_is_unproven(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 1.2.3\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with mock.patch.object(self.adapter, "resolve_executable_from_path", return_value=Path(sys.executable)), \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "probe_runtime_configuration", return_value=("pass", "pass")), \
             mock.patch.object(self.adapter, "live_containment_proven", return_value=False), \
             mock.patch.object(self.adapter, "auth_class", return_value="signed-in-client"), \
             mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64):
            observed = self.adapter.observe_runtime_profile(ROOT, "gpt-5.6-sol", "high")
        self.assertEqual("UNCHECKABLE", observed["status"])
        self.assertEqual("UNCHECKABLE", observed["capabilities"]["process_containment_probe"])
        self.assertFalse(observed["live_run_allowed"])

    def test_runtime_entrypoints_gate_capabilities_before_side_effects(self):
        with mock.patch.object(self.adapter, "require_runtime_fs_capabilities", side_effect=self.adapter.ContractError("capability gate")) as gate, \
             mock.patch.object(self.adapter, "validate_envelope") as validate, \
             mock.patch.object(self.adapter.tempfile, "TemporaryDirectory") as temporary, \
             mock.patch.object(self.adapter, "observe_runtime_profile") as sensor:
            self.assert_contract_error(lambda: self.adapter.execute_slice(ROOT, {}, {}, "offline"), "capability gate")
        gate.assert_called_once()
        validate.assert_not_called()
        temporary.assert_not_called()
        sensor.assert_not_called()

        with mock.patch.object(self.adapter, "require_runtime_fs_capabilities", side_effect=self.adapter.ContractError("capability gate")) as gate, \
             mock.patch.object(self.adapter, "resolve_executable_from_path") as which, \
             mock.patch.object(self.adapter.tempfile, "TemporaryDirectory") as temporary:
            self.assert_contract_error(lambda: self.adapter.observe_runtime_profile(ROOT, "gpt-5.6-sol", "high"), "capability gate")
        gate.assert_called_once()
        which.assert_not_called()
        temporary.assert_not_called()

        args = SimpleNamespace(mode="offline", fake_behavior="valid")
        with mock.patch.object(self.adapter, "require_runtime_fs_capabilities", side_effect=self.adapter.ContractError("capability gate")) as gate, \
             mock.patch.object(self.adapter, "read_stdin_bounded") as stdin_read:
            self.assert_contract_error(lambda: self.adapter.cli_run(args, ROOT), "capability gate")
        gate.assert_called_once()
        stdin_read.assert_not_called()

        with mock.patch.object(self.adapter, "require_runtime_fs_capabilities", side_effect=self.adapter.ContractError("capability gate")) as gate, \
             mock.patch.object(self.adapter, "read_stdin_bounded") as stdin_read:
            self.assert_contract_error(lambda: self.adapter.cli_verify(ROOT), "capability gate")
        gate.assert_called_once()
        stdin_read.assert_not_called()

    def test_strict_configuration_probe_exercises_every_live_setting(self):
        calls = []
        attestation = {
            "schema": "t11-runtime-configuration-probe/v1",
            "effective_configuration_sha256": "0" * 64,
            "model_invoked": False,
        }

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            calls.append(list(argv))
            payload = self.adapter.canonical_bytes(attestation) if "doctor" in argv else b"PATH=/bin\0"
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with mock.patch.object(self.adapter, "bounded_capture", side_effect=capture):
            config_status, _shell_status = self.adapter.probe_runtime_configuration(
                Path("/reviewed/codex"), ROOT, {"PATH": "/bin", "HOME": "/private-home", "TMPDIR": "/private-tmp", **self.adapter.REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0"}
            )
        self.assertNotEqual("pass", config_status)
        rendered = "\n".join("\n".join(call) for call in calls)
        for key, value in self.adapter.REQUIRED_OVERRIDES.items():
            self.assertIn("{}={}".format(key, self.adapter.toml_literal(value)), rendered)
        self.assertIn('approval_policy="never"', rendered)
        self.assertIn('model_reasoning_effort="high"', rendered)

    def test_strict_configuration_probe_has_a_conforming_no_model_match(self):
        environment = {
            "PATH": "/bin", "HOME": "/private-home", "TMPDIR": "/private-tmp",
            **self.adapter.REQUIRED_ENV_VALUES, "GIT_OPTIONAL_LOCKS": "0",
        }
        expected = self.adapter.reviewed_runtime_configuration(environment)
        attestation = {
            "schema": "t11-runtime-configuration-probe/v1",
            "effective_configuration_sha256": self.adapter.sha256_bytes(self.adapter.canonical_bytes(expected)),
            "model_invoked": False,
        }

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            if "doctor" in argv:
                payload = self.adapter.canonical_bytes(attestation)
            else:
                payload = b"\0".join(
                    (name + "=" + value).encode("utf-8")
                    for name, value in sorted(expected["shell_environment_policy.set"].items())
                ) + b"\0"
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with mock.patch.object(self.adapter, "bounded_capture", side_effect=capture):
            self.assertEqual(
                ("pass", "pass"),
                self.adapter.probe_runtime_configuration(Path("/reviewed/codex"), ROOT, environment),
            )

    def test_live_argv_contains_exact_isolation_and_no_dynamic_task_data(self):
        argv = self.adapter.build_live_argv(Path("/reviewed/codex"), Path("/isolated-target"), ROOT, self.envelope)
        self.assertEqual("-", argv[-1])
        for required in ("exec", "--json", "--ephemeral", "--strict-config", "--ignore-user-config", "workspace-write"):
            self.assertIn(required, argv)
        rendered = "\n".join(argv)
        self.assertNotIn(self.envelope["attempt_id"], rendered)
        self.assertNotIn("Issue #23", rendered)
        self.assertNotIn("--add-dir", argv)
        for key, value in self.adapter.REQUIRED_OVERRIDES.items():
            self.assertIn("{}={}".format(key, self.adapter.toml_literal(value)), argv)

    def test_shell_metacharacters_are_inert_argv_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.minimal_process_environment(root)
            marker = root / "must-not-exist"
            argument = "$(touch {}) ; echo unsafe".format(marker)
            result = self.adapter.run_bounded_process(
                [sys.executable, "-c", "import sys; print(sys.argv[1])", argument],
                root, env, b"", 5, 4096, 4096,
            )
            self.assertEqual(0, result.exit_code)
            self.assertIn(argument.encode(), result.stdout)
            self.assertFalse(marker.exists())

    def test_executable_resolution_uses_only_explicit_path_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attacker = root / "git"
            attacker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(attacker, 0o755)
            with mock.patch.dict(os.environ, {"PATH": str(root)}):
                resolved = self.adapter.resolve_executable_from_path("git", {"PATH": "/usr/bin:/bin"})
            self.assertIsNotNone(resolved)
            self.assertNotEqual(attacker, resolved)
            target = root / "real-git"
            target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(target, 0o755)
            attacker.unlink()
            attacker.symlink_to(target.name)
            self.assert_contract_error(
                lambda: self.adapter.resolve_executable_from_path("git", {"PATH": str(root)}),
                "direct executable",
            )

    def test_version_and_cli_errors_are_privacy_sanitized(self):
        for value in (
            b"codex-cli file:/Users/alice/private/repo",
            b"codex-cli sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
            b"\xff",
        ):
            self.assertEqual("unrecognized-version-output", self.adapter.sanitize_version_output(value))
        result = subprocess.run(
            [sys.executable, "-I", str(ADAPTER_PATH), "run", "--mode", "offline"],
            cwd=ROOT, input=b'{"file:/Users/alice/private/repo":"sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"}',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
        )
        self.assertNotEqual(0, result.returncode)
        rendered = result.stdout.decode("utf-8")
        self.assertNotIn("alice", rendered)
        self.assertNotIn("sk-proj", rendered)
        self.assertEqual("bounded runtime contract failure", json.loads(rendered)["reason"])

    def test_jsonl_rejects_invalid_utf8_partial_scalar_and_terminal_count(self):
        limits = self.envelope["limits"]
        attempt = self.envelope["attempt_id"]
        invalid_cases = (
            b"\xff\n",
            b'{"type":"thread.started"',
            b"7\n",
            b'{"id":"e1","type":"turn.stopped"}\n',
            (ROOT / "tests/runtime/fixtures/codex-jsonl-valid.jsonl").read_bytes().rsplit(b"\n", 2)[0] + b"\n",
            (ROOT / "tests/runtime/fixtures/codex-jsonl-valid.jsonl").read_bytes() + b'{"id":"e5","type":"turn.failed"}\n',
        )
        for data in invalid_cases:
            with self.subTest(data=data[:30]):
                self.assert_contract_error(lambda d=data: self.adapter.parse_jsonl(d, attempt, limits))

    def test_jsonl_attempt_final_and_duplicate_consistency(self):
        base = (ROOT / "tests/runtime/fixtures/codex-jsonl-valid.jsonl").read_text(encoding="utf-8")
        drift = base.replace("ATTEMPT-0123456789abcdef", "ATTEMPT-fedcba9876543210")
        self.assert_contract_error(lambda: self.adapter.parse_jsonl(drift.encode(), self.envelope["attempt_id"], self.envelope["limits"]), "attempt")
        failed_lines = [json.loads(line) for line in base.splitlines()]
        failed_final = json.loads(failed_lines[2]["item"]["text"])
        failed_final["outcome"] = "failed"
        failed_final["changed_paths"] = []
        failed_lines[2]["item"]["text"] = json.dumps(failed_final, separators=(",", ":"))
        failed = ("\n".join(json.dumps(line, separators=(",", ":")) for line in failed_lines) + "\n").encode()
        _, parsed_failed, _ = self.adapter.parse_jsonl(failed, self.envelope["attempt_id"], self.envelope["limits"])
        self.assertEqual("failed", parsed_failed["outcome"])
        lines = base.splitlines()
        identical = ("\n".join([lines[0], lines[0]] + lines[1:]) + "\n").encode()
        events, _, _ = self.adapter.parse_jsonl(identical, self.envelope["attempt_id"], self.envelope["limits"])
        self.assertEqual(4, len(events))
        conflicting = ("\n".join([lines[0], '{"id":"e1","type":"turn.started"}'] + lines[1:]) + "\n").encode()
        self.assert_contract_error(lambda: self.adapter.parse_jsonl(conflicting, self.envelope["attempt_id"], self.envelope["limits"]), "conflicting duplicate")
        duplicate_terminal = ("\n".join(lines + [lines[-1]]) + "\n").encode()
        self.assert_contract_error(
            lambda: self.adapter.parse_jsonl(duplicate_terminal, self.envelope["attempt_id"], self.envelope["limits"]),
            "terminal",
        )

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'):
            with self.subTest(data=data):
                self.assert_contract_error(lambda d=data: self.adapter.decode_json_object(d, "fixture"))
        line = b'{"id":"e1","id":"e2","type":"thread.started"}\n'
        self.assert_contract_error(
            lambda: self.adapter.parse_jsonl(line, self.envelope["attempt_id"], self.envelope["limits"]),
        )

    def test_json_limits_are_iterative_and_bounded(self):
        at_limit = {}
        current = at_limit
        for _ in range(self.envelope["limits"]["json_depth"] - 1):
            current["x"] = {}
            current = current["x"]
        self.adapter.validate_json_limits(at_limit, self.envelope["limits"])
        over = {"x": at_limit}
        self.assert_contract_error(lambda: self.adapter.validate_json_limits(over, self.envelope["limits"]), "depth")
        long_value = "x" * (self.envelope["limits"]["json_string_bytes"] + 1)
        self.assert_contract_error(lambda: self.adapter.validate_json_limits({"x": long_value}, self.envelope["limits"]), "string")
        small_limits = dict(self.envelope["limits"])
        small_limits["json_nodes"] = 2
        self.assert_contract_error(lambda: self.adapter.validate_json_limits({"a": 1, "b": 2}, small_limits), "node")

    def test_process_timeout_flood_signal_and_child_held_pipes_are_bounded(self):
        fake = ROOT / "tests/runtime/fixtures/fake-codex.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "work-item.txt").write_bytes(b"status=pending\n")
            for behavior, timeout, out_limit, err_limit in (
                ("sleep", 0.2, 4096, 4096),
                ("ignore-term", 0.2, 4096, 4096),
                ("child-held-pipe", 0.2, 4096, 4096),
                ("child-exit-holds-pipe", 5, 4096, 4096),
                ("child-exit-closed-pipes", 5, 4096, 4096),
                ("stdout-flood", 5, 1024, 4096),
                ("stderr-flood", 5, 4096, 1024),
                ("signal", 5, 4096, 4096),
            ):
                env_root = root / behavior
                env_root.mkdir()
                env = self.minimal_process_environment(env_root, behavior)
                result = self.adapter.run_bounded_process(
                    [sys.executable, "-I", str(fake)], root, env, b"{}\n",
                    timeout, out_limit, err_limit, 0.1,
                )
                with self.subTest(behavior=behavior):
                    self.assertTrue(result.reaped)
                    if behavior in ("sleep", "ignore-term", "child-held-pipe"):
                        self.assertTrue(result.timed_out)
                    elif behavior in ("child-exit-holds-pipe", "child-exit-closed-pipes"):
                        self.assertFalse(result.timed_out)
                        if behavior == "child-exit-closed-pipes":
                            child_pid = int(result.stdout.decode("ascii").strip())
                            with self.assertRaises(ProcessLookupError):
                                os.kill(child_pid, 0)
                    elif behavior == "stdout-flood":
                        self.assertTrue(result.stdout_overflow)
                    elif behavior == "stderr-flood":
                        self.assertTrue(result.stderr_overflow)
                    elif behavior == "signal":
                        self.assertEqual(signal.SIGTERM, result.signal_number)

    def test_escaped_session_descendant_cannot_survive_success(self):
        fake = ROOT / "tests/runtime/fixtures/fake-codex.py"
        child_pid = None
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "work-item.txt").write_bytes(b"status=pending\n")
                env_root = root / "env"
                env_root.mkdir()
                env = self.minimal_process_environment(env_root, "child-escaped-session")
                result = self.adapter.run_bounded_process([sys.executable, "-I", str(fake)], root, env, b"{}\n", 5, 4096, 4096, 0.2)
                child_pid = int(result.stdout.decode("ascii").strip())
                self.assertTrue(result.reaped)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_process_identity_uses_kernel_birth_token_and_pid_reuse_is_not_signalled(self):
        table = self.adapter.process_table_snapshot(self.adapter.minimal_environment(
            Path(sys.executable).resolve(), Path("/private-home"), Path("/private-tmp")
        ))
        self.assertIn(os.getpid(), table)
        token = table[os.getpid()][2]
        self.assertRegex(token, r"^(?:linux:[0-9]+|darwin:[0-9]+:[0-9]+)$")

        tracker = self.adapter.DescendantTracker(111, {})
        tracker.known = {222: (111, 111, "darwin:100:1")}
        tracker.thread = mock.Mock()
        tracker.thread.is_alive.return_value = False
        with mock.patch.object(
            self.adapter,
            "process_table_snapshot",
            return_value={222: (1, 222, "darwin:100:2")},
        ), mock.patch.object(self.adapter.os, "kill") as signal_call:
            self.assertTrue(tracker.terminate_descendants(0.01))
        signal_call.assert_not_called()

    def test_worktree_preflight_rejects_unreviewed_layers_symlinks_and_modes(self):
        extras = (".codex/config.toml", "AGENTS.md", ".mcp.json", ".codex/agents/worker.toml", ".agents/skills/x/SKILL.md")
        for extra in extras:
            with tempfile.TemporaryDirectory() as temporary:
                container = Path(temporary)
                env = self.minimal_process_environment(container)
                root = self.adapter.create_synthetic_repository(container, env)
                path = root / extra
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("unexpected\n", encoding="utf-8")
                with self.subTest(extra=extra):
                    self.assert_contract_error(lambda r=root: self.adapter.git_snapshot(r, env), "extra entries")
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            env = self.minimal_process_environment(container)
            root = self.adapter.create_synthetic_repository(container, env)
            target = root / "work-item.txt"
            target.unlink()
            target.symlink_to("missing")
            self.assert_contract_error(lambda: self.adapter.git_snapshot(root, env))
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            env = self.minimal_process_environment(container)
            root = self.adapter.create_synthetic_repository(container, env)
            os.chmod(root / "work-item.txt", 0o755)
            self.assert_contract_error(lambda: self.adapter.git_snapshot(root, env), "mode-100644")

    def test_worker_filesystem_and_git_violations_fail_closed(self):
        for behavior in ("no-edit", "extra-file", "mode-change", "rename", "symlink", "stage", "git-config", "git-hook", "git-object", "git-ref", "git-split-index", "branch-drift", "replace-file", "final-failed", "attempt-drift", "multiple-terminal", "conflicting-duplicate"):
            with self.subTest(behavior=behavior):
                self.assert_contract_error(
                    lambda b=behavior: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), copy.deepcopy(self.profile), "offline", b)
                )

    def test_private_execution_root_rejects_tmpdir_and_sibling_writes(self):
        for behavior in ("tmpdir-write", "execution-root-sibling-write"):
            with self.subTest(behavior=behavior):
                self.assert_contract_error(
                    lambda b=behavior: self.adapter.execute_slice(
                        ROOT, copy.deepcopy(self.envelope), copy.deepcopy(self.profile), "offline", b
                    ),
                    "execution root",
                )

    @unittest.skipUnless(sys.platform in ("darwin", "linux"), "xattr sensor is platform-specific")
    def test_execution_root_inventory_rejects_git_head_xattr_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            home = container / "home"
            tmpdir = container / "tmp"
            home.mkdir()
            tmpdir.mkdir()
            env = self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmpdir)
            root = self.adapter.create_synthetic_repository(container, env)
            before = self.adapter.execution_root_inventory(container)
            if hasattr(os, "setxattr"):
                os.setxattr(root / ".git/HEAD", b"user.com.t11.audit", b"unexpected")
            else:
                subprocess.run(
                    ["/usr/bin/xattr", "-w", "com.t11.audit", "unexpected", str(root / ".git/HEAD")],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, check=True, timeout=5,
                )
            after = self.adapter.execution_root_inventory(container)
            self.assert_contract_error(
                lambda: self.adapter.validate_execution_root_transition(before, after),
                "execution root",
            )

    def test_execution_metadata_capability_missing_fails_before_inventory_io(self):
        with mock.patch.object(self.adapter, "runtime_fs_capability_error", return_value=None), \
             mock.patch.object(self.adapter, "runtime_metadata_capability_error", return_value="xattr unavailable"), \
             mock.patch.object(self.adapter.os, "open") as open_call:
            self.assert_contract_error(
                lambda: self.adapter.execution_root_inventory(Path("not-opened")),
                "metadata capability",
            )
        open_call.assert_not_called()

        with mock.patch.object(self.adapter, "runtime_fs_capability_error", return_value=None), \
             mock.patch.object(self.adapter, "runtime_metadata_capability_error", return_value=None), \
             mock.patch.object(self.adapter, "runtime_process_identity_capability_error", return_value="birth identity unavailable"), \
             mock.patch.object(self.adapter.subprocess, "Popen") as process_start:
            self.assert_contract_error(
                lambda: self.adapter.run_bounded_process(
                    [sys.executable, "-c", "pass"], ROOT, {}, b"", 1, 1024, 1024
                ),
                "process-identity capability",
            )
        process_start.assert_not_called()

    def test_git_binding_inventory_rejects_byte_identical_replacements(self):
        for behavior in ("git-head-replace", "git-namespace-replace"):
            with self.subTest(behavior=behavior):
                self.assert_contract_error(
                    lambda b=behavior: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), copy.deepcopy(self.profile), "offline", b),
                    "execution root",
                )

    def test_identical_event_duplicate_is_collapsed_without_second_worker(self):
        result = self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), copy.deepcopy(self.profile), "offline", "identical-duplicate")
        self.assertEqual("pass", result["status"])
        self.assertEqual(1, result["worker"]["logical_invocations"])
        self.assertEqual(4, result["events"]["count"])

    def test_root_and_file_namespace_swaps_during_enumeration_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            env = self.minimal_process_environment(container)
            root = self.adapter.create_synthetic_repository(container, env)
            original_stat = self.adapter.os.stat
            root_calls = {"count": 0}

            def swapped_root(path, *args, **kwargs):
                value = original_stat(path, *args, **kwargs)
                if str(path) == str(root) and kwargs.get("follow_symlinks") is False:
                    root_calls["count"] += 1
                    if root_calls["count"] == 2:
                        return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + 1)
                return value

            with mock.patch.object(self.adapter, "runtime_fs_capability_error", return_value=None), \
                 mock.patch.object(self.adapter.os, "stat", side_effect=swapped_root):
                self.assert_contract_error(lambda: self.adapter.list_worktree_entries(root), "namespace swapped")

            file_calls = {"count": 0}

            def swapped_file(path, *args, **kwargs):
                value = original_stat(path, *args, **kwargs)
                if path == "work-item.txt" and kwargs.get("follow_symlinks") is False:
                    file_calls["count"] += 1
                    if file_calls["count"] == 2:
                        return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + 1)
                return value

            with mock.patch.object(self.adapter, "runtime_fs_capability_error", return_value=None), \
                 mock.patch.object(self.adapter.os, "stat", side_effect=swapped_file):
                self.assert_contract_error(lambda: self.adapter.list_worktree_entries(root), "namespace swapped")

    def test_owned_file_name_rebind_after_descriptor_read_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            env = self.minimal_process_environment(container)
            root = self.adapter.create_synthetic_repository(container, env)
            _names, _root_binding, file_binding = self.adapter.list_worktree_entries(root)
            original_read = self.adapter.os.read
            swapped = {"done": False}

            def swap_after_read(descriptor, count):
                data = original_read(descriptor, count)
                if data and not swapped["done"]:
                    swapped["done"] = True
                    replacement = root / "replacement.tmp"
                    replacement.write_bytes(b"attacker\n")
                    os.chmod(replacement, 0o644)
                    os.replace(replacement, root / "work-item.txt")
                return data

            with mock.patch.object(self.adapter.os, "read", side_effect=swap_after_read):
                self.assert_contract_error(lambda: self.adapter.read_owned_file(root, file_binding), "namespace")

    def test_runtime_profile_schema_pins_nonmatch_live_false(self):
        schema = json.loads((ROOT / "docs/agreements/runtime/runtime-profile.v1.schema.json").read_text(encoding="utf-8"))
        errors = []
        self.checker.validate_runtime_profile_schema(schema, errors)
        self.assertEqual([], errors)
        schema.pop("allOf", None)
        errors = []
        self.checker.validate_runtime_profile_schema(schema, errors)
        self.assertTrue(errors)

    def test_receipt_schema_requires_native_artifacts_and_unsigned_limitation(self):
        schema = json.loads((ROOT / "docs/agreements/runtime/runtime-receipt.v1.schema.json").read_text(encoding="utf-8"))
        errors = []
        self.checker.validate_runtime_receipt_schema(schema, errors)
        self.assertEqual([], errors)
        schema["properties"]["artifacts"]["required"].remove("verifier")
        errors = []
        self.checker.validate_runtime_receipt_schema(schema, errors)
        self.assertTrue(errors)

    def test_envelope_requires_shell_free_command_and_exact_bytes(self):
        mutations = (
            lambda value: value["verification_commands"][0].__setitem__("shell", True),
            lambda value: value["verification_commands"][0].pop("git_state"),
            lambda value: value["representative_task"].__setitem__("initial_utf8", "status=other\n"),
            lambda value: value["target"]["owned_paths"].append("other.txt"),
            lambda value: value["worker"].__setitem__("prompt_transport", "argv"),
            lambda value: value["worker"]["overrides"].__setitem__("features.hooks", True),
            lambda value: value["verification_commands"][0]["cwd"].__setitem__("commit", "f" * 40),
            lambda value: value["verification_commands"][0]["cwd"].__setitem__("tree", "f" * 40),
        )
        for mutation in mutations:
            envelope = copy.deepcopy(self.envelope)
            mutation(envelope)
            self.assert_contract_error(lambda e=envelope: self.adapter.validate_envelope(e))

    def test_fresh_verifier_rejects_forged_parent_prestate(self):
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            env = self.minimal_process_environment(container)
            root = self.adapter.create_synthetic_repository(container, env)
            before = self.adapter.git_snapshot(root, env)
            (root / "work-item.txt").write_bytes(b"status=complete\n")
            subprocess.run(["git", "checkout", "-q", "-b", "drift"], cwd=root, env=env, check=True)
            after = self.adapter.git_snapshot(root, env)
            forged = copy.deepcopy(after)
            forged["file_bytes"] = before["file_bytes"]
            bundle = {
                "schema": "t11-verification-bundle/v1",
                "attempt_id": self.envelope["attempt_id"],
                "target_root": str(root),
                "before": self.adapter.serializable_pre_state(forged),
                "expected": {"path": "work-item.txt", "mode": "100644", "sha256": self.adapter.sha256_bytes(b"status=complete\n")},
            }
            self.assert_contract_error(lambda: self.adapter.validate_verification_bundle(bundle, env), "branch")

    def test_missing_filesystem_capabilities_fail_before_io(self):
        with mock.patch.object(self.adapter, "runtime_fs_capability_error", return_value="O_NOFOLLOW unavailable"), \
             mock.patch.object(self.adapter.os, "stat") as stat_call, \
             mock.patch.object(self.adapter.os, "open") as open_call:
            self.assert_contract_error(lambda: self.adapter.read_bounded_regular(Path("not-read"), 32), "capability")
        stat_call.assert_not_called()
        open_call.assert_not_called()
        errors = []
        with mock.patch.object(self.checker, "runtime_fs_capability_error", return_value="O_NOFOLLOW unavailable"), \
             mock.patch.object(self.checker.os, "lstat") as lstat_call, \
             mock.patch.object(self.checker.os, "open") as checker_open:
            self.assertEqual(b"", self.checker.read_regular(ROOT, "not-read", errors))
        self.assertTrue(errors)
        lstat_call.assert_not_called()
        checker_open.assert_not_called()

    def test_checker_strict_json_rejects_duplicate_and_nonfinite(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.subTest(text=text):
                with self.assertRaises((ValueError, OverflowError)):
                    self.checker.strict_json_loads(text)


if __name__ == "__main__":
    unittest.main()
