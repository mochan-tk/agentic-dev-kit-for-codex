import copy
import datetime
import errno
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

    def passing_runtime_probe(self):
        return {
            "documented_config_keys_probe": "pass",
            "shell_environment_probe": "pass",
            "evidence": {
                "configuration_intent": self.adapter.runtime_configuration_intent(),
                "diagnostic_health": {
                    "classification": "diagnostic-only",
                    "status": "pass",
                    "checks": [
                        {"id": "auth.credentials", "category": "auth", "status": "ok"},
                        {"id": "config.load", "category": "config", "status": "ok"},
                        {"id": "runtime.provenance", "category": "runtime", "status": "ok"},
                        {"id": "sandbox.helpers", "category": "sandbox", "status": "ok"},
                    ],
                    "codex_issued_effective_configuration_proof": False,
                },
                "exact_worker_argv": {
                    "status": "pass",
                    "stage": "argv-policy",
                    "reason_code": "none",
                    "rules_bypass_absent": True,
                    "dynamic_task_data_stdin_only": True,
                },
                "network_sandbox_behavior": {"status": "pass"},
                "bubblewrap_prerequisite": self.passing_stage_a1_prerequisite(),
                "lane_statuses": {
                    "provider_isolation_status": "not-run",
                    "mount_boundary_status": "not-run",
                    "process_cleanup_status": "pass",
                    "codex_sandbox_network_status": "pass",
                    "shell_environment_status": "pass",
                    "config_status": "pass",
                    "auth_status": "unavailable",
                },
            },
        }

    def passing_stage_a1_prerequisite(self):
        controller_argv = [list(argv) for argv in self.adapter.STAGE_A1_CONTROLLER_ARGV]
        smoke_argv = list(self.adapter.STAGE_A1_BWRAP_SMOKE_ARGV)
        return {
            "schema": "t11-bubblewrap-prerequisite-evidence/v1",
            "authority": "adapter/owner-authored",
            "status": "pass",
            "reason_code": "none",
            "guest": {
                "distribution_id": "ubuntu",
                "distribution_version": "24.04",
                "distribution_codename": "noble",
                "kernel": "6.8.0-79-generic",
                "architecture": "aarch64",
            },
            "apparmor": {
                "enabled": True,
                "unprivileged_userns_restriction": "active",
                "profile_required": True,
                "profile_source": "ubuntu-noble-apparmor-profiles",
                "source_sha256": "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9",
                "installed_sha256": "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9",
                "load_status": "enforce",
            },
            "bubblewrap": {
                "package_name": "bubblewrap",
                "package_version": "0.9.0-1ubuntu0.1",
                "package_architecture": "arm64",
                "install_status": "installed",
                "binary_sha256": "ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8",
                "version_output": "bubblewrap 0.9.0",
                "help_sha256": "a" * 64,
            },
            "git": {
                "package_name": "git",
                "package_version": "1:2.43.0-1ubuntu7.3",
                "package_architecture": "arm64",
                "install_status": "installed",
                "binary_sha256": "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942",
                "version_output": "git version 2.43.0",
            },
            "controller": {
                "argv_sha256": self.adapter.sha256_bytes(
                    self.adapter.canonical_bytes(controller_argv)
                ),
                "shell": False,
                "model_invoked": False,
                "device_auth_performed": False,
                "legacy_landlock_enabled": False,
                "global_apparmor_userns_disabled": False,
            },
            "smoke": {
                "argv_sha256": self.adapter.sha256_bytes(
                    self.adapter.canonical_bytes(smoke_argv)
                ),
                "status": "pass",
                "reason_code": "none",
                "exit_code": 0,
                "raw_stdout_recorded": False,
                "raw_stderr_recorded": False,
            },
        }

    def colima_provider_input(self, head="a" * 40, tree="b" * 40):
        control_plane = {
            "schema": "t11-colima-control-plane-evidence/v1",
            "authority": "owner-authored",
            "codex_authenticated_attestation": False,
            "status": "pass",
            "pre_create_observed_at": "2026-08-28T23:59:59Z",
            "post_create_observed_at": "2026-08-29T00:00:00Z",
            "profile_name": "t11-e2e-{}-01".format(head[:12]),
            "colima_version": "0.10.1",
            "vm_backend": "vz",
            "architecture": "aarch64",
            "pre_create_profile_absent": True,
            "pre_create_runtime_data_absent": True,
            "fresh_instance": True,
            "existing_instance_reused": False,
            "existing_container_reused": False,
            "existing_volume_reused": False,
            "default_profile_reused": False,
            "activation_context_unchanged": True,
            "private_vm_disk": True,
            "repository_on_private_vm_disk": True,
            "runtime_root_on_private_vm_disk": True,
            "additional_disks": 0,
            "instance_identity_sha256": "5" * 64,
            "provider_configuration_sha256": "1" * 64,
            "normalized_control_plane_sha256": "0" * 64,
            "raw_paths_recorded": False,
        }
        control_plane["normalized_control_plane_sha256"] = self.adapter.normalized_control_plane_sha256(control_plane)
        return {
            "schema": "t11-colima-provider-input/v1",
            "authority": "owner-authored",
            "provider": {
                "kind": "colima-vm",
                "profile_name": "t11-e2e-{}-01".format(head[:12]),
                "vm_backend": "vz",
                "architecture": "aarch64",
                "created_at": "2026-08-29T00:00:00Z",
                "provider_configuration_sha256": "1" * 64,
                "effective_mount_inventory_sha256": "2" * 64,
                "provider_cache_mount_sha256": "3" * 64,
                "provider_cache_guest_mountpoint_sha256": "4" * 64,
                "host_mount_count": 1,
                "host_mount_classifications": ["provider-internal-cache"],
                "all_host_mounts_read_only": True,
                "ssh_agent_forwarding": False,
                "dot_ssh_public_key_loading": False,
                "user_ssh_config_modified": False,
            },
            "control_plane": control_plane,
            "repository": {
                "head": head,
                "tree": tree,
                "git_bootstrap": self.git_bootstrap_evidence(),
                "git_clone_contract_sha256": (
                    self.adapter.stage_a1_git_clone_contract_sha256(head, tree)
                ),
            },
            "client": {
                "version_output": "codex-cli 0.150.1",
                "approved_archive_sha256": "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264",
                "observed_archive_sha256": "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264",
                "extracted_binary_sha256": "a" * 64,
            },
            "lifecycle": {
                "destroy_required": True,
                "destroy_requested": False,
                "destroy_completed": False,
                "profile_absence_readback": "not-run",
            },
        }

    def passing_containment_evidence(self, head="a" * 40, tree="b" * 40):
        control_plane = self.colima_provider_input(head, tree)["control_plane"]
        return {
            "schema": "t11-containment-provider-evidence/v1",
            "authority": "adapter/owner-authored",
            "codex_authenticated_attestation": False,
            "status": "pass",
            "provider_kind": "colima-vm",
            "profile_name": "t11-e2e-{}-01".format(head[:12]),
            "vm_backend": "vz",
            "architecture": "aarch64",
            "native_architecture": True,
            "guest_os": "Linux",
            "guest_kernel": "6.12.0-t11",
            "created_at": "2026-08-29T00:00:00Z",
            "provider_configuration_sha256": "1" * 64,
            "effective_mount_inventory_sha256": "2" * 64,
            "provider_cache_mount_sha256": "3" * 64,
            "provider_cache_guest_mountpoint_sha256": "4" * 64,
            "host_mount_count": 1,
            "host_mount_classifications": ["provider-internal-cache"],
            "all_host_mounts_read_only": True,
            "provider_cache_only": True,
            "host_sensitive_mounts_absent": True,
            "unapproved_mounts_absent": True,
            "ssh_agent_forwarding": False,
            "dot_ssh_public_key_loading": False,
            "user_ssh_config_modified": False,
            "vm_instance_identity_sha256": "5" * 64,
            "public_head": head,
            "public_tree": tree,
            "repository_clean": True,
            "repository_git_bootstrap": self.git_bootstrap_evidence(),
            "repository_git_bootstrap_runtime_match": True,
            "repository_git_clone_contract_sha256": (
                self.adapter.stage_a1_git_clone_contract_sha256(head, tree)
            ),
            "codex_version_output": "codex-cli 0.150.1",
            "approved_archive_sha256": "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264",
            "observed_archive_sha256": "5bb1f75e1a1588845b4a31f2c98fb2b394be5c2a8d90a24a8ab0ebbae1169264",
            "extracted_binary_sha256": "a" * 64,
            "runtime_root_binding_sha256": "6" * 64,
            "dedicated_codex_home_binding_sha256": "7" * 64,
            "control_plane": control_plane,
            "lifecycle": {
                "destroy_required": True,
                "destroy_requested": False,
                "destroy_completed": False,
                "profile_absence_readback": "not-run",
            },
        }

    def git_bootstrap_evidence(self):
        return {
            "schema": "t11-git-bootstrap-evidence/v1",
            "authority": "owner/controller-authored",
            "package_name": "git",
            "package_version": "1:2.43.0-1ubuntu7.3",
            "package_architecture": "arm64",
            "install_status": "installed",
            "binary_sha256": (
                "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942"
            ),
            "version_output": "git version 2.43.0",
            "preclone_qualification_argv_sha256": (
                "a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc"
            ),
            "controller_argv_sha256": (
                "3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff"
            ),
            "raw_stdout_recorded": False,
            "raw_stderr_recorded": False,
        }

    def test_colima_provider_input_is_closed_exact_and_stdin_only(self):
        value = self.colima_provider_input()
        self.assertEqual(value, self.adapter.validate_colima_provider_input(copy.deepcopy(value)))
        mutations = (
            lambda item: item.pop("provider"),
            lambda item: item.__setitem__("extra", "forbidden"),
            lambda item: item["provider"].__setitem__("kind", "docker"),
            lambda item: item["provider"].__setitem__("vm_backend", "qemu"),
            lambda item: item["provider"].__setitem__("architecture", "x86_64"),
            lambda item: item["provider"].__setitem__("profile_name", "default"),
            lambda item: item["repository"].__setitem__("head", "c" * 40),
            lambda item: item["repository"].__setitem__("tree", "short"),
            lambda item: item["repository"].pop("git_clone_contract_sha256"),
            lambda item: item["repository"].__setitem__(
                "git_clone_contract_sha256", "0" * 64,
            ),
            lambda item: item["repository"].__setitem__(
                "git_clone_contract_sha256",
                self.adapter.stage_a1_git_clone_contract_sha256(
                    "c" * 40, item["repository"]["tree"],
                ),
            ),
            lambda item: item["repository"].pop("git_bootstrap"),
            lambda item: item["repository"]["git_bootstrap"].pop("package_name"),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "extra", "forbidden",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "package_name", "git-core",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "package_version", "1:2.43.0-1ubuntu7.2",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "package_architecture", "amd64",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "install_status", "unknown",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "binary_sha256", "0" * 64,
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "version_output", "git version 2.42.0",
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "preclone_qualification_argv_sha256", "0" * 64,
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "controller_argv_sha256", "0" * 64,
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "raw_stdout_recorded", True,
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "raw_stderr_recorded", True,
            ),
            lambda item: item["repository"]["git_bootstrap"].__setitem__(
                "version_output", "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            ),
            lambda item: item["client"].__setitem__("version_output", "codex-cli 0.150.0"),
            lambda item: item["client"].__setitem__("observed_archive_sha256", "0" * 64),
            lambda item: item["client"].__setitem__("extracted_binary_sha256", "0" * 64),
            lambda item: item["provider"].__setitem__("host_mount_count", 2),
            lambda item: item["provider"].__setitem__("all_host_mounts_read_only", False),
            lambda item: item["control_plane"].__setitem__("existing_instance_reused", True),
            lambda item: item["control_plane"].__setitem__("existing_container_reused", True),
            lambda item: item["control_plane"].__setitem__("existing_volume_reused", True),
            lambda item: item["control_plane"].__setitem__("default_profile_reused", True),
            lambda item: item["control_plane"].__setitem__("raw_paths_recorded", True),
            lambda item: item["control_plane"].__setitem__("normalized_control_plane_sha256", "0" * 64),
            lambda item: item["lifecycle"].__setitem__("destroy_requested", True),
        )
        for mutation in mutations:
            candidate = copy.deepcopy(value)
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assert_contract_error(lambda c=candidate: self.adapter.validate_colima_provider_input(c))
        token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        token_candidate = copy.deepcopy(value)
        token_candidate["repository"]["git_bootstrap"]["version_output"] = token
        with self.assertRaises(self.adapter.ContractError) as raised:
            self.adapter.validate_colima_provider_input(token_candidate)
        self.assertNotIn(token, str(raised.exception))
        parser = self.adapter.build_parser()
        parsed = parser.parse_args(["profile"])
        self.assertFalse(any("provider" in token for token in vars(parsed).values() if isinstance(token, str)))
        self.assertFalse(parsed.probe_only)
        self.assertTrue(parser.parse_args(["profile", "--probe-only"]).probe_only)

    def test_git_clone_digest_is_a_closed_owner_contract_not_chronology_proof(self):
        head = "a" * 40
        tree = "b" * 40
        contract = self.adapter.stage_a1_git_clone_contract(head, tree)
        self.assertEqual("t11-git-clone-contract/v1", contract["schema"])
        self.assertEqual("reviewed-static-contract", contract["authority"])
        self.assertFalse(contract["shell"])
        self.assertEqual("/usr/bin/git", contract["git_binary"])
        self.assertEqual(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex.git",
            contract["repository_url"],
        )
        self.assertEqual(
            "codex/phase-2-minimal-execution-slice", contract["branch"],
        )
        self.assertEqual({
            "head": head, "tree": tree, "status_porcelain_v1_z": "empty",
        }, contract["expected_outputs"])
        self.assertNotIn("observed_at", contract)
        self.assertNotIn("executed_at", contract)
        rendered = json.dumps(contract, sort_keys=True)
        self.assertIn("<private-vm-repository>", rendered)
        self.assertNotIn("/Users/", rendered)
        self.assertNotIn("credential value", rendered)
        for argv in contract["argv_templates"]:
            self.assertEqual("/usr/bin/git", argv[0])
            self.assertIn("--no-replace-objects", argv)
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertIn("credential.helper=", argv)
        digest = self.adapter.stage_a1_git_clone_contract_sha256(head, tree)
        self.assertEqual(
            self.adapter.sha256_bytes(self.adapter.canonical_bytes(contract)),
            digest,
        )
        self.assertEqual(
            "960514bc6501c6b10aa63bd8907f91c883be8860c5d9134801e4458a3d11f80f",
            digest,
        )
        self.assertNotEqual(
            digest,
            self.adapter.stage_a1_git_clone_contract_sha256("c" * 40, tree),
        )
        self.assertNotEqual(
            digest,
            self.adapter.stage_a1_git_clone_contract_sha256(head, "d" * 40),
        )
        self.assert_contract_error(
            lambda: self.adapter.stage_a1_git_clone_contract("short", tree),
            "head",
        )

    def test_stage_a1_controller_and_non_root_smoke_argv_are_exact_and_safe(self):
        self.assertEqual((
            "/usr/bin/bwrap", "--unshare-user", "--unshare-net",
            "--ro-bind", "/", "/", "/bin/true",
        ), self.adapter.STAGE_A1_BWRAP_SMOKE_ARGV)
        commands = self.adapter.STAGE_A1_CONTROLLER_ARGV
        self.assertIsInstance(commands, tuple)
        self.assertGreaterEqual(len(commands), 4)
        self.assertEqual(
            ("/usr/bin/sudo", "-n", "/usr/bin/apt-get", "update"),
            commands[0],
        )
        self.assertEqual(
            ("/usr/bin/sudo", "-n", "/usr/bin/apt-get", "install",
             "--yes", "--no-install-recommends",
             "apparmor=4.0.1really4.0.1-0ubuntu0.24.04.7",
             "apparmor-profiles=4.0.1really4.0.1-0ubuntu0.24.04.7",
             "bubblewrap=0.9.0-1ubuntu0.1",
             "git=1:2.43.0-1ubuntu7.3"),
            commands[1],
        )
        self.assertEqual(self.adapter.STAGE_A1_GIT_PACKAGE_QUERY_ARGV, commands[2])
        self.assertEqual(
            ("/usr/bin/sha256sum", "--", "/usr/bin/git"), commands[3],
        )
        self.assertEqual(("/usr/bin/git", "--version"), commands[4])
        self.assertEqual(
            self.adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV, commands[:5],
        )
        self.assertEqual("/usr/bin/install", commands[5][2])
        self.assertEqual("/usr/sbin/apparmor_parser", commands[6][2])
        self.assertEqual(self.adapter.STAGE_A1_BWRAP_SMOKE_ARGV, commands[-1])
        tokens = [token for argv in commands for token in argv]
        for forbidden in (
            "/bin/sh", "/bin/bash", "-c", "--ignore-rules",
            "login", "device-auth", "exec", "--model",
        ):
            self.assertNotIn(forbidden, tokens)
        for token in tokens:
            self.assertFalse(token.startswith("--dangerously-bypass-"))
            self.assertFalse(token.startswith("features.use_legacy_landlock"))
            self.assertFalse(token.startswith(
                "apparmor_restrict_unprivileged_userns=0"
            ))
        for argv in commands:
            self.assertIsInstance(argv, tuple)
            self.assertTrue(argv)
            self.assertTrue(argv[0].startswith("/"))
        self.assertRegex(
            self.adapter.STAGE_A1_CONTROLLER_ARGV_SHA256, r"^[0-9a-f]{64}$",
        )
        self.assertEqual(
            self.adapter.sha256_bytes(self.adapter.canonical_bytes(
                [list(argv) for argv in commands]
            )),
            self.adapter.STAGE_A1_CONTROLLER_ARGV_SHA256,
        )
        self.assertEqual(
            "a5ea1c6699df4dcde3d7c7572b80fb866a242e016bb9d30399f9d01d3b3650dc",
            self.adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256,
        )
        self.assertEqual(
            self.adapter.sha256_bytes(self.adapter.canonical_bytes(
                [list(argv) for argv in self.adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV]
            )),
            self.adapter.STAGE_A1_PRECLONE_CONTROLLER_ARGV_SHA256,
        )
        self.assertEqual(
            "3d61c7c2a924a30853381dbebd912e33d474ec0dd226598b540ecc1e0f1f44ff",
            self.adapter.STAGE_A1_CONTROLLER_ARGV_SHA256,
        )

    def test_stage_a1_prerequisite_evidence_is_closed_and_fail_closed(self):
        valid = self.passing_stage_a1_prerequisite()
        self.assertEqual(
            valid,
            self.adapter.validate_stage_a1_prerequisite_evidence(copy.deepcopy(valid)),
        )
        not_run = self.adapter.not_run_stage_a1_prerequisite_evidence()
        self.assertEqual(
            not_run,
            self.adapter.validate_stage_a1_prerequisite_evidence(copy.deepcopy(not_run)),
        )
        self.assertEqual("not-run", not_run["status"])
        self.assertFalse(not_run["controller"]["model_invoked"])
        self.assertFalse(not_run["controller"]["device_auth_performed"])
        self.assertFalse(not_run["smoke"]["raw_stdout_recorded"])
        self.assertFalse(not_run["smoke"]["raw_stderr_recorded"])
        mutations = (
            lambda item: item.__setitem__("extra", "forbidden"),
            lambda item: item["guest"].__setitem__("distribution_version", "24.10"),
            lambda item: item["guest"].__setitem__("distribution_codename", "oracular"),
            lambda item: item["guest"].__setitem__("kernel", "not-run"),
            lambda item: item["guest"].__setitem__("architecture", "x86_64"),
            lambda item: item["apparmor"].__setitem__("enabled", False),
            lambda item: item["apparmor"].__setitem__("unprivileged_userns_restriction", "inactive"),
            lambda item: item["apparmor"].__setitem__("installed_sha256", "7" * 64),
            lambda item: item["apparmor"].__setitem__("load_status", "complain"),
            lambda item: item["bubblewrap"].__setitem__("package_name", "unreviewed"),
            lambda item: item["bubblewrap"].__setitem__(
                "package_version", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
            ),
            lambda item: item["bubblewrap"].__setitem__("install_status", "unknown"),
            lambda item: item["bubblewrap"].__setitem__(
                "version_output", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
            ),
            lambda item: item.pop("git"),
            lambda item: item["git"].__setitem__("package_name", "unreviewed"),
            lambda item: item["git"].__setitem__(
                "package_version", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
            ),
            lambda item: item["git"].__setitem__("package_architecture", "x86_64"),
            lambda item: item["git"].__setitem__("install_status", "unknown"),
            lambda item: item["git"].__setitem__("binary_sha256", "0" * 64),
            lambda item: item["git"].__setitem__(
                "version_output", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
            ),
            lambda item: item["controller"].__setitem__("argv_sha256", "0" * 64),
            lambda item: item["controller"].__setitem__("shell", True),
            lambda item: item["controller"].__setitem__("model_invoked", True),
            lambda item: item["controller"].__setitem__("device_auth_performed", True),
            lambda item: item["controller"].__setitem__("legacy_landlock_enabled", True),
            lambda item: item["controller"].__setitem__("global_apparmor_userns_disabled", True),
            lambda item: item["smoke"].__setitem__("argv_sha256", "0" * 64),
            lambda item: item["smoke"].__setitem__("raw_stdout_recorded", True),
            lambda item: item["smoke"].__setitem__("raw_stderr_recorded", True),
        )
        for mutation in mutations:
            candidate = copy.deepcopy(valid)
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assert_contract_error(
                    lambda value=candidate:
                    self.adapter.validate_stage_a1_prerequisite_evidence(value),
                )

        inconsistent_outcomes = []
        failed_none = copy.deepcopy(valid)
        failed_none["status"] = "fail"
        inconsistent_outcomes.append(failed_none)
        precondition_with_smoke = copy.deepcopy(valid)
        precondition_with_smoke["status"] = "fail"
        precondition_with_smoke["reason_code"] = "package-drift"
        inconsistent_outcomes.append(precondition_with_smoke)
        uncheckable_with_pass = copy.deepcopy(valid)
        uncheckable_with_pass["status"] = "UNCHECKABLE"
        uncheckable_with_pass["reason_code"] = "timeout"
        inconsistent_outcomes.append(uncheckable_with_pass)
        for reason_code, exit_code in (
            ("nonzero-exit", 0), ("signal", 1), ("unexpected-output", 1),
        ):
            invalid_exit = copy.deepcopy(valid)
            invalid_exit["status"] = "fail"
            invalid_exit["reason_code"] = reason_code
            invalid_exit["smoke"].update({
                "status": "fail", "reason_code": reason_code,
                "exit_code": exit_code,
            })
            inconsistent_outcomes.append(invalid_exit)
        for candidate in inconsistent_outcomes:
            with self.subTest(inconsistent_outcome=candidate):
                self.assert_contract_error(
                    lambda value=candidate:
                    self.adapter.validate_stage_a1_prerequisite_evidence(value),
                )

        missing = copy.deepcopy(self.profile)
        missing["evidence"].pop("bubblewrap_prerequisite")
        self.assert_contract_error(
            lambda: self.adapter.validate_runtime_profile(missing, allow_fixture=True),
            "runtime evidence",
        )
        failed = copy.deepcopy(self.profile)
        failed_prerequisite = failed["evidence"]["bubblewrap_prerequisite"]
        failed_prerequisite["status"] = "fail"
        failed_prerequisite["reason_code"] = "nonzero-exit"
        failed_prerequisite["smoke"].update({
            "status": "fail", "reason_code": "nonzero-exit", "exit_code": 1,
        })
        self.assert_contract_error(
            lambda: self.adapter.validate_runtime_profile(failed, allow_fixture=True),
            "live_run_allowed",
        )

    def test_stage_a1_pseudo_file_read_bounds_actual_bytes_not_page_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "apparmor-enabled"
            target.write_bytes(b"Y\n")
            actual = os.stat(target, follow_symlinks=False)
            advertised = SimpleNamespace(
                st_mode=actual.st_mode,
                st_size=4096,
                st_dev=actual.st_dev,
                st_ino=actual.st_ino,
                st_mtime_ns=actual.st_mtime_ns,
            )
            original_stat = self.adapter.os.stat

            def stat_with_page_size(path, *, follow_symlinks=True):
                if str(path) == str(target):
                    self.assertFalse(follow_symlinks)
                    return advertised
                return original_stat(path, follow_symlinks=follow_symlinks)

            with mock.patch.object(
                self.adapter, "require_runtime_fs_capabilities",
            ), mock.patch.object(
                self.adapter.os, "stat", side_effect=stat_with_page_size,
            ):
                self.assertEqual(
                    b"Y\n",
                    self.adapter.read_bounded_regular(
                        target, 16, max_advertised_bytes=65_536,
                    ),
                )
                self.assert_contract_error(
                    lambda: self.adapter.read_bounded_regular(target, 16),
                    "exceeds",
                )
                self.assert_contract_error(
                    lambda: self.adapter.read_bounded_regular(
                        target, 16, max_advertised_bytes=8,
                    ),
                    "policy",
                )

    def test_stage_a1_observation_maps_allowlisted_system_and_smoke_evidence(self):
        os_release = (
            b'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n'
        )
        profile = b"abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap flags=(unconfined) {\n}\n"
        reads = {
            "/usr/lib/os-release": os_release,
            "/sys/module/apparmor/parameters/enabled": b"Y\n",
            "/proc/sys/kernel/apparmor_restrict_unprivileged_userns": b"1\n",
            str(self.adapter.STAGE_A1_PROFILE_SOURCE): profile,
            str(self.adapter.STAGE_A1_PROFILE_INSTALLED): profile,
        }

        def read(
            path, _limit, expected_mode=None, max_advertised_bytes=None,
        ):
            del expected_mode, max_advertised_bytes
            return reads[str(path)]

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15, **_kwargs):
            del stdin_bytes, timeout
            if list(argv) == list(self.adapter.STAGE_A1_BWRAP_SMOKE_ARGV):
                return self.adapter.ProcessResult(0, None, False, False, False, b"", 0, True)
            if tuple(argv) == self.adapter.STAGE_A1_PACKAGE_QUERY_ARGV:
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    b"installed\t0.9.0-1ubuntu0.1\tarm64\n", 0, True,
                )
            if tuple(argv) == self.adapter.STAGE_A1_GIT_PACKAGE_QUERY_ARGV:
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    b"installed\t1:2.43.0-1ubuntu7.3\tarm64\n", 0, True,
                )
            if tuple(argv) == (str(self.adapter.STAGE_A1_BWRAP_BINARY), "--version"):
                return self.adapter.ProcessResult(
                    0, None, False, False, False, b"bubblewrap 0.9.0\n", 0, True,
                )
            if tuple(argv) == (str(self.adapter.STAGE_A1_GIT_BINARY), "--version"):
                return self.adapter.ProcessResult(
                    0, None, False, False, False, b"git version 2.43.0\n", 0, True,
                )
            if list(argv)[-1:] == ["--help"]:
                return self.adapter.ProcessResult(
                    0, None, False, False, False, b"Usage: bwrap [OPTIONS...]\n", 0, True,
                )
            if tuple(argv) == self.adapter.STAGE_A1_LOADED_PROFILES_ARGV:
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    b"bwrap (enforce)\nbwrap//&unpriv_bwrap (enforce)\n", 0, True,
                )
            raise AssertionError(list(argv))

        uname = SimpleNamespace(
            sysname="Linux", machine="aarch64", release="6.8.0-79-generic",
        )
        def hashed(path, *_args, **_kwargs):
            if str(path) == "/usr/bin/bwrap":
                return "ae27935781511400c65ebcc0b4669775d602f46251b8707c947a1ac1b160c1c8"
            if str(path) == "/usr/bin/git":
                return "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942"
            return "11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9"

        with mock.patch.object(self.adapter, "read_bounded_regular", side_effect=read), \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "hash_regular_file", side_effect=hashed), \
             mock.patch.object(self.adapter.os, "uname", return_value=uname):
            observed = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("pass", observed["status"])
        self.assertEqual("ubuntu", observed["guest"]["distribution_id"])
        self.assertEqual("24.04", observed["guest"]["distribution_version"])
        self.assertEqual("noble", observed["guest"]["distribution_codename"])
        self.assertEqual("aarch64", observed["guest"]["architecture"])
        self.assertTrue(observed["apparmor"]["enabled"])
        self.assertEqual("active", observed["apparmor"]["unprivileged_userns_restriction"])
        self.assertEqual(observed["apparmor"]["source_sha256"], observed["apparmor"]["installed_sha256"])
        self.assertEqual("enforce", observed["apparmor"]["load_status"])
        self.assertEqual("0.9.0-1ubuntu0.1", observed["bubblewrap"]["package_version"])
        self.assertEqual("arm64", observed["bubblewrap"]["package_architecture"])
        self.assertEqual("1:2.43.0-1ubuntu7.3", observed["git"]["package_version"])
        self.assertEqual("arm64", observed["git"]["package_architecture"])
        self.assertEqual(
            "aa6540695d076182256dd6e96c8b302e4d56381e3000bbfd5c71bbdfe94a4942",
            observed["git"]["binary_sha256"],
        )
        self.assertEqual("git version 2.43.0", observed["git"]["version_output"])
        self.assertEqual("pass", observed["smoke"]["status"])
        self.assertEqual("none", observed["smoke"]["reason_code"])
        self.assertFalse(observed["smoke"]["raw_stdout_recorded"])
        self.assertFalse(observed["smoke"]["raw_stderr_recorded"])

        for query, valid_payload in (
            (
                self.adapter.STAGE_A1_PACKAGE_QUERY_ARGV,
                b"installed\t0.9.0-1ubuntu0.1\tarm64\n",
            ),
            (
                self.adapter.STAGE_A1_GIT_PACKAGE_QUERY_ARGV,
                b"installed\t1:2.43.0-1ubuntu7.3\tarm64\n",
            ),
        ):
            invalid_cases = (
                ("full-status-field", b"install ok " + valid_payload, 0),
                (
                    "non-installed",
                    valid_payload.replace(b"installed\t", b"config-files\t"),
                    0,
                ),
                (
                    "unknown-status",
                    valid_payload.replace(b"installed\t", b"mystery-status\t"),
                    0,
                ),
                ("missing-lf", valid_payload.rstrip(b"\n"), 0),
                ("crlf", valid_payload.rstrip(b"\n") + b"\r\n", 0),
                ("extra-field", valid_payload.rstrip(b"\n") + b"\textra\n", 0),
                ("duplicate-row", valid_payload + valid_payload, 0),
                ("invalid-utf8", b"installed\t\xff\tarm64\n", 0),
                ("nonempty-stderr", valid_payload, 1),
            )
            for label, rejected_payload, stderr_size in invalid_cases:
                seen = []

                def rejected_status_capture(
                    argv, *args, selected=query, payload=rejected_payload,
                    observed_stderr_size=stderr_size, **kwargs,
                ):
                    seen.append(tuple(argv))
                    if tuple(argv) == selected:
                        return self.adapter.ProcessResult(
                            0, None, False, False, False, payload,
                            observed_stderr_size, True,
                        )
                    return capture(argv, *args, **kwargs)

                with self.subTest(query=query, case=label), mock.patch.object(
                    self.adapter, "read_bounded_regular", side_effect=read,
                ), mock.patch.object(
                    self.adapter, "bounded_capture",
                    side_effect=rejected_status_capture,
                ), mock.patch.object(
                    self.adapter, "hash_regular_file", side_effect=hashed,
                ), mock.patch.object(
                    self.adapter.os, "uname", return_value=uname,
                ):
                    rejected = self.adapter.observe_stage_a1_prerequisite(
                        ROOT, {},
                    )
                self.assertEqual("UNCHECKABLE", rejected["status"])
                self.assertEqual(
                    "observation-uncheckable", rejected["reason_code"],
                )
                self.assertEqual("UNCHECKABLE", rejected["smoke"]["status"])
                self.assertNotIn(
                    self.adapter.STAGE_A1_BWRAP_SMOKE_ARGV, seen,
                )
        for result, expected in (
            (self.adapter.ProcessResult(1, None, False, False, False, b"", 0, True), ("fail", "nonzero-exit")),
            (self.adapter.ProcessResult(None, 9, False, False, False, b"", 0, True), ("fail", "signal")),
            (self.adapter.ProcessResult(0, None, False, False, False, b"unexpected", 0, True), ("fail", "unexpected-output")),
            (self.adapter.ProcessResult(0, None, False, False, False, b"", 7, True), ("fail", "unexpected-output")),
            (self.adapter.ProcessResult(None, None, True, False, False, b"", 0, True), ("UNCHECKABLE", "timeout")),
            (self.adapter.ProcessResult(0, None, False, True, False, b"", 0, True), ("UNCHECKABLE", "output-overflow")),
            (self.adapter.ProcessResult(0, None, False, False, False, b"", 0, False), ("UNCHECKABLE", "process-not-reaped")),
        ):
            with self.subTest(expected=expected):
                classified = self.adapter.classify_stage_a1_bwrap_smoke(result)
                self.assertEqual(expected, (classified["status"], classified["reason_code"]))
                self.assertNotIn("stdout", classified)
                self.assertNotIn("stderr", classified)

        for field_path, unknown_bytes in (
            ("/sys/module/apparmor/parameters/enabled", b"?\n"),
            ("/proc/sys/kernel/apparmor_restrict_unprivileged_userns", b"2\n"),
        ):
            unknown_reads = dict(reads)
            unknown_reads[field_path] = unknown_bytes
            with self.subTest(field_path=field_path), mock.patch.object(
                self.adapter, "read_bounded_regular",
                side_effect=lambda path, _limit, expected_mode=None,
                max_advertised_bytes=None, values=unknown_reads: values[str(path)],
            ), mock.patch.object(
                self.adapter, "bounded_capture", side_effect=capture,
            ), mock.patch.object(
                self.adapter, "hash_regular_file", side_effect=hashed,
            ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
                uncheckable = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
            self.assertEqual("UNCHECKABLE", uncheckable["status"])
            self.assertEqual("observation-uncheckable", uncheckable["reason_code"])
            self.assertEqual("UNCHECKABLE", uncheckable["smoke"]["status"])

        def uncheckable_load_capture(argv, *args, **kwargs):
            if tuple(argv) == self.adapter.STAGE_A1_LOADED_PROFILES_ARGV:
                return self.adapter.ProcessResult(
                    1, None, False, False, False, b"", 0, True,
                )
            return capture(argv, *args, **kwargs)

        with mock.patch.object(
            self.adapter, "read_bounded_regular", side_effect=read,
        ), mock.patch.object(
            self.adapter, "bounded_capture", side_effect=uncheckable_load_capture,
        ), mock.patch.object(
            self.adapter, "hash_regular_file", side_effect=hashed,
        ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
            uncheckable_load = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("UNCHECKABLE", uncheckable_load["status"])
        self.assertEqual("observation-uncheckable", uncheckable_load["reason_code"])

        token = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"

        def token_version_capture(argv, *args, **kwargs):
            if tuple(argv) == (str(self.adapter.STAGE_A1_BWRAP_BINARY), "--version"):
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    (token + "\n").encode("ascii"), 0, True,
                )
            return capture(argv, *args, **kwargs)

        with mock.patch.object(
            self.adapter, "read_bounded_regular", side_effect=read,
        ), mock.patch.object(
            self.adapter, "bounded_capture", side_effect=token_version_capture,
        ), mock.patch.object(
            self.adapter, "hash_regular_file", side_effect=hashed,
        ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
            sanitized = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("fail", sanitized["status"])
        self.assertEqual("binary-drift", sanitized["reason_code"])
        self.assertEqual("unrecognized", sanitized["bubblewrap"]["version_output"])
        self.assertNotIn(token, json.dumps(sanitized, sort_keys=True))

        def token_git_package_capture(argv, *args, **kwargs):
            if tuple(argv) == self.adapter.STAGE_A1_GIT_PACKAGE_QUERY_ARGV:
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    ("installed\t" + token + "\tarm64\n").encode("ascii"),
                    0, True,
                )
            return capture(argv, *args, **kwargs)

        with mock.patch.object(
            self.adapter, "read_bounded_regular", side_effect=read,
        ), mock.patch.object(
            self.adapter, "bounded_capture", side_effect=token_git_package_capture,
        ), mock.patch.object(
            self.adapter, "hash_regular_file", side_effect=hashed,
        ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
            sanitized_git_package = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("fail", sanitized_git_package["status"])
        self.assertEqual("git-package-drift", sanitized_git_package["reason_code"])
        self.assertEqual("unrecognized", sanitized_git_package["git"]["package_version"])
        self.assertNotIn(token, json.dumps(sanitized_git_package, sort_keys=True))

        def token_git_version_capture(argv, *args, **kwargs):
            if tuple(argv) == (str(self.adapter.STAGE_A1_GIT_BINARY), "--version"):
                return self.adapter.ProcessResult(
                    0, None, False, False, False,
                    (token + "\n").encode("ascii"), 0, True,
                )
            return capture(argv, *args, **kwargs)

        with mock.patch.object(
            self.adapter, "read_bounded_regular", side_effect=read,
        ), mock.patch.object(
            self.adapter, "bounded_capture", side_effect=token_git_version_capture,
        ), mock.patch.object(
            self.adapter, "hash_regular_file", side_effect=hashed,
        ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
            sanitized_git_version = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("fail", sanitized_git_version["status"])
        self.assertEqual("git-binary-drift", sanitized_git_version["reason_code"])
        self.assertEqual("unrecognized", sanitized_git_version["git"]["version_output"])
        self.assertNotIn(token, json.dumps(sanitized_git_version, sort_keys=True))

        def missing_git_capture(argv, *args, **kwargs):
            if tuple(argv) == self.adapter.STAGE_A1_GIT_PACKAGE_QUERY_ARGV:
                return self.adapter.ProcessResult(
                    1, None, False, False, False, b"", 0, True,
                )
            return capture(argv, *args, **kwargs)

        with mock.patch.object(
            self.adapter, "read_bounded_regular", side_effect=read,
        ), mock.patch.object(
            self.adapter, "bounded_capture", side_effect=missing_git_capture,
        ), mock.patch.object(
            self.adapter, "hash_regular_file", side_effect=hashed,
        ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
            missing_git = self.adapter.observe_stage_a1_prerequisite(ROOT, {})
        self.assertEqual("UNCHECKABLE", missing_git["status"])
        self.assertEqual("observation-uncheckable", missing_git["reason_code"])
        self.assertEqual("not-run", missing_git["git"]["package_name"])
        self.assertEqual("UNCHECKABLE", missing_git["smoke"]["status"])

    def test_stage_a1_prerequisite_gates_codex_shell_and_network_probes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            work = root / "work"
            for path in (home, tmp, work):
                path.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            passing = self.passing_stage_a1_prerequisite()
            for prerequisite_status in ("not-run", "fail", "UNCHECKABLE"):
                if prerequisite_status == "not-run":
                    prerequisite = self.adapter.not_run_stage_a1_prerequisite_evidence()
                else:
                    prerequisite = copy.deepcopy(passing)
                    prerequisite["status"] = prerequisite_status
                    prerequisite["reason_code"] = (
                        "nonzero-exit" if prerequisite_status == "fail"
                        else "observation-uncheckable"
                    )
                    prerequisite["smoke"]["status"] = prerequisite_status
                    prerequisite["smoke"]["reason_code"] = prerequisite["reason_code"]
                    prerequisite["smoke"]["exit_code"] = (
                        1 if prerequisite_status == "fail" else None
                    )
                with self.subTest(prerequisite_status=prerequisite_status), \
                     mock.patch.object(
                         self.adapter, "materialize_reviewed_rules_profile",
                         return_value=self.adapter.runtime_configuration_intent()["rules_profile_sha256"],
                     ), mock.patch.object(
                         self.adapter, "doctor_diagnostic_health",
                         return_value=self.passing_runtime_probe()["evidence"]["diagnostic_health"],
                     ), mock.patch.object(
                         self.adapter, "exact_worker_argv_evidence",
                         return_value=self.passing_runtime_probe()["evidence"]["exact_worker_argv"],
                     ), mock.patch.object(
                         self.adapter, "bounded_capture",
                         return_value=self.adapter.ProcessResult(
                             0, None, False, False, False, b"{}\n", 0, True,
                         ),
                     ), mock.patch.object(
                         self.adapter, "shell_environment_probe",
                     ) as shell_probe, mock.patch.object(
                         self.adapter, "network_sandbox_behavior_probe",
                     ) as network_probe, mock.patch.object(
                         self.adapter, "process_cleanup_probe", return_value="pass",
                     ):
                    evidence = self.adapter.probe_runtime_evidence(
                        Path(sys.executable).resolve(), work, environment, ROOT,
                        auth_required=False,
                        prerequisite_evidence=prerequisite,
                    )
                shell_probe.assert_not_called()
                network_probe.assert_not_called()
                self.assertEqual(
                    prerequisite_status,
                    evidence["evidence"]["bubblewrap_prerequisite"]["status"],
                )
                self.assertEqual(
                    "not-run",
                    evidence["evidence"]["lane_statuses"]["shell_environment_status"],
                )
                self.assertEqual(
                    "not-run",
                    evidence["evidence"]["lane_statuses"]["codex_sandbox_network_status"],
                )

            with mock.patch.object(
                self.adapter, "materialize_reviewed_rules_profile",
                return_value=self.adapter.runtime_configuration_intent()["rules_profile_sha256"],
            ), mock.patch.object(
                self.adapter, "doctor_diagnostic_health",
                return_value=self.passing_runtime_probe()["evidence"]["diagnostic_health"],
            ), mock.patch.object(
                self.adapter, "exact_worker_argv_evidence",
                return_value=self.passing_runtime_probe()["evidence"]["exact_worker_argv"],
            ), mock.patch.object(
                self.adapter, "bounded_capture",
                return_value=self.adapter.ProcessResult(
                    0, None, False, False, False, b"{}\n", 0, True,
                ),
            ), mock.patch.object(
                self.adapter, "shell_environment_probe", return_value="pass",
            ) as shell_probe, mock.patch.object(
                self.adapter, "network_sandbox_behavior_probe", return_value="pass",
            ) as network_probe, mock.patch.object(
                self.adapter, "process_cleanup_probe", return_value="pass",
            ):
                evidence = self.adapter.probe_runtime_evidence(
                    Path(sys.executable).resolve(), work, environment, ROOT,
                    auth_required=False,
                    prerequisite_evidence=passing,
                )
            shell_probe.assert_called_once()
            network_probe.assert_called_once()
            self.assertEqual(
                "pass",
                evidence["evidence"]["bubblewrap_prerequisite"]["status"],
            )

    def test_profile_cli_requires_bounded_provider_input_on_stdin(self):
        result = subprocess.run(
            [sys.executable, "-I", str(ADAPTER_PATH), "profile"], cwd=ROOT,
            input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("fail", json.loads(result.stdout)["status"])

    def test_colima_mount_inventory_allows_only_one_read_only_bound_cache_share(self):
        line = (
            b"42 1 0:99 / /Users/Shared/t11-colima-t11-e2e-aaaaaaaaaaaa-01.A1b2C3d4/xdg-cache/colima ro,relatime - "
            b"virtiofs mount0 ro\n"
        )
        provider = self.colima_provider_input()["provider"]
        provider["effective_mount_inventory_sha256"] = self.adapter.sha256_bytes(line)
        provider["provider_cache_mount_sha256"] = self.adapter.sha256_bytes(line)
        provider["provider_cache_guest_mountpoint_sha256"] = self.adapter.sha256_bytes(
            b"/Users/Shared/t11-colima-t11-e2e-aaaaaaaaaaaa-01.A1b2C3d4/xdg-cache/colima\n"
        )
        facts = self.adapter.inspect_colima_mount_inventory(line, provider)
        self.assertEqual("pass", facts["status"])
        self.assertTrue(facts["provider_cache_only"])
        self.assertNotIn("/Users/", json.dumps(facts))
        for bad in (
            line.replace(b" ro,relatime", b" rw,relatime"),
            line + b"43 1 0:100 / /Users/alice ro - 9p host ro\n",
            line.replace(b"/Users/Shared/t11-colima-t11-e2e-aaaaaaaaaaaa-01.A1b2C3d4/xdg-cache/colima", b"/Users/alice/repository"),
            line + b"43 1 0:100 / /mnt/nfs rw,relatime - nfs4 server:/share rw\n",
            line + b"43 1 0:100 / /mnt/cifs rw,relatime - cifs //server/share rw\n",
            line + b"43 1 0:100 / /mnt/opaque rw,relatime - fuse.unreviewed opaque rw\n",
            line + b"43 1 0:100 / /mnt/vbox rw,relatime - vboxsf shared rw\n",
            line + b"43 1 0:100 / /mnt/unknown ro,relatime - madeupfs opaque ro\n",
        ):
            with self.subTest(bad=bad):
                drift = self.adapter.inspect_colima_mount_inventory(bad, provider)
                self.assertEqual("fail", drift["status"])
                self.assertFalse(drift["host_sensitive_mounts_absent"] if b"alice" in bad else drift["unapproved_mounts_absent"])

    def test_colima_provider_reobserves_instance_repo_and_extracted_binary(self):
        line = (
            b"42 1 0:99 / /Users/Shared/t11-colima-t11-e2e-aaaaaaaaaaaa-01.A1b2C3d4/xdg-cache/colima ro,relatime - "
            b"virtiofs mount0 ro\n"
        )
        machine = b"0123456789abcdef0123456789abcdef\n"
        boot = b"12345678-1234-1234-1234-123456789abc\n"
        value = self.colima_provider_input()
        value["provider"]["effective_mount_inventory_sha256"] = self.adapter.sha256_bytes(line)
        value["provider"]["provider_cache_mount_sha256"] = self.adapter.sha256_bytes(line)
        value["provider"]["provider_cache_guest_mountpoint_sha256"] = self.adapter.sha256_bytes(
            b"/Users/Shared/t11-colima-t11-e2e-aaaaaaaaaaaa-01.A1b2C3d4/xdg-cache/colima\n"
        )
        value["control_plane"]["provider_configuration_sha256"] = value["provider"]["provider_configuration_sha256"]
        value["control_plane"]["instance_identity_sha256"] = self.adapter.sha256_bytes(
            machine.strip().lower() + b"\0" + boot.strip().lower()
        )
        value["control_plane"]["normalized_control_plane_sha256"] = self.adapter.normalized_control_plane_sha256(
            value["control_plane"]
        )
        layout = self.adapter.ColimaRuntimeLayout(
            Path("/private"), Path("/private/home"), Path("/private/tmp"),
            Path("/private/work"), Path("/private/bin/codex"), "6" * 64, "7" * 64,
        )

        def read(path, _limit):
            if str(path) == "/proc/self/mountinfo":
                return line
            if str(path) == "/etc/machine-id":
                return machine
            if str(path) == "/proc/sys/kernel/random/boot_id":
                return boot
            raise AssertionError(str(path))

        events = []

        def observe_git(_root, _environment):
            events.append("git-package-and-binary")
            bootstrap = value["repository"]["git_bootstrap"]
            return {
                key: bootstrap[key] for key in (
                    "package_name", "package_version", "package_architecture",
                    "install_status", "binary_sha256", "version_output",
                )
            }

        def executable_git(_root, _environment, *, require_approved=False):
            events.append("git-executable")
            self.assertTrue(require_approved)
            bootstrap = value["repository"]["git_bootstrap"]
            return bootstrap["version_output"], bootstrap["binary_sha256"]

        def provider_git(_root, arguments, _environment, **_kwargs):
            events.append("run-approved-provider-git")
            if arguments[0] == "status":
                return b""
            return (value["repository"]["head"] if arguments[-1] == "HEAD" else value["repository"]["tree"]).encode() + b"\n"

        uname = SimpleNamespace(sysname="Linux", machine="aarch64", release="6.12.0-t11")
        with mock.patch.object(self.adapter, "read_bounded_regular", side_effect=read), \
             mock.patch.object(self.adapter, "observe_stage_a1_git", side_effect=observe_git), \
             mock.patch.object(self.adapter, "git_executable_evidence", side_effect=executable_git), \
             mock.patch.object(
                 self.adapter, "run_approved_provider_git", side_effect=provider_git,
             ) as approved_git, \
             mock.patch.object(self.adapter, "run_git") as generic_git, \
             mock.patch.object(self.adapter.os, "uname", return_value=uname), \
             mock.patch.dict(os.environ, {}, clear=True):
            passed = self.adapter.observe_colima_provider_evidence(
                ROOT, value, layout, "a" * 64, "codex-cli 0.150.1", {},
            )
            drifted = self.adapter.observe_colima_provider_evidence(
                ROOT, value, layout, "f" * 64, "codex-cli 0.150.1", {},
            )
        self.assertEqual("pass", passed["status"])
        self.assertEqual(
            value["repository"]["git_bootstrap"],
            passed["repository_git_bootstrap"],
        )
        self.assertTrue(passed["repository_git_bootstrap_runtime_match"])
        self.assertEqual(
            value["repository"]["git_clone_contract_sha256"],
            passed["repository_git_clone_contract_sha256"],
        )
        self.assertEqual(
            [
                "git-package-and-binary", "git-executable",
                "run-approved-provider-git",
            ],
            events[:3],
        )
        self.assertEqual(6, approved_git.call_count)
        generic_git.assert_not_called()
        self.assertEqual("fail", drifted["status"])
        self.assertEqual("f" * 64, drifted["extracted_binary_sha256"])
        self.assertFalse(drifted["codex_authenticated_attestation"])

        mismatched = {
            **observe_git(ROOT, {}),
            "package_version": "unrecognized",
        }
        with mock.patch.object(self.adapter, "read_bounded_regular", side_effect=read), \
             mock.patch.object(self.adapter, "observe_stage_a1_git", return_value=mismatched), \
             mock.patch.object(self.adapter, "git_executable_evidence") as executable_probe, \
             mock.patch.object(
                 self.adapter, "run_approved_provider_git",
             ) as repository_git, \
             mock.patch.object(self.adapter, "run_git") as generic_git, \
             mock.patch.object(self.adapter.os, "uname", return_value=uname), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assert_contract_error(
                lambda: self.adapter.observe_colima_provider_evidence(
                    ROOT, value, layout, "a" * 64, "codex-cli 0.150.1", {},
                ),
                "pre-clone trust anchor",
            )
        executable_probe.assert_not_called()
        repository_git.assert_not_called()
        generic_git.assert_not_called()

    def test_approved_provider_git_revalidates_fixed_root_owned_binary_each_time(self):
        safe_directory = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_nlink=1,
        )
        safe_git = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o755, st_uid=0, st_nlink=1,
        )

        def safe_stat(path, **_kwargs):
            return safe_git if str(path) == "/usr/bin/git" else safe_directory

        success = self.adapter.ProcessResult(
            0, None, False, False, False, b"ok\n", 0, True,
        )
        with mock.patch.object(self.adapter.os, "stat", side_effect=safe_stat), \
             mock.patch.object(
                 self.adapter, "hash_regular_file",
                 side_effect=[
                     self.adapter.APPROVED_GIT_BINARY_SHA256,
                     "0" * 64,
                 ],
             ) as digest_sensor, \
             mock.patch.object(
                 self.adapter, "run_bounded_process", return_value=success,
             ) as process:
            first = self.adapter.run_approved_provider_git(
                ROOT, ("rev-parse", "--verify", "HEAD"),
                {"PATH": "/unreviewed/bin"}, max_bytes=128,
            )
            self.assertEqual(b"ok\n", first)
            self.assertEqual("/usr/bin/git", process.call_args.args[0][0])
            self.assert_contract_error(
                lambda: self.adapter.run_approved_provider_git(
                    ROOT, ("rev-parse", "--verify", "HEAD^{tree}"),
                    {"PATH": "/unreviewed/bin"}, max_bytes=128,
                ),
                "digest drifted",
            )
        self.assertEqual(2, digest_sensor.call_count)
        process.assert_called_once()

        for unsafe_path, unsafe_info in (
            ("/usr", SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o775, st_uid=0, st_nlink=1,
            )),
            ("/usr/bin", SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o755, st_uid=501, st_nlink=1,
            )),
            ("/usr/bin/git", SimpleNamespace(
                st_mode=stat.S_IFREG | 0o775, st_uid=0, st_nlink=1,
            )),
        ):
            def unsafe_stat(path, **_kwargs):
                if str(path) == unsafe_path:
                    return unsafe_info
                return safe_git if str(path) == "/usr/bin/git" else safe_directory

            with self.subTest(unsafe_path=unsafe_path), \
                 mock.patch.object(self.adapter.os, "stat", side_effect=unsafe_stat), \
                 mock.patch.object(self.adapter, "hash_regular_file") as digest_sensor, \
                 mock.patch.object(self.adapter, "run_bounded_process") as process:
                self.assert_contract_error(
                    lambda: self.adapter.run_approved_provider_git(
                        ROOT, ("status", "--porcelain=v1", "-z"), {},
                    ),
                    "binding is unsafe",
                )
            digest_sensor.assert_not_called()
            process.assert_not_called()

        with mock.patch.object(
            self.adapter, "resolve_executable_from_path",
            return_value=Path("/opt/unreviewed/git"),
        ), mock.patch.object(
            self.adapter, "run_bounded_process",
        ) as process:
            self.assert_contract_error(
                lambda: self.adapter.git_executable_evidence(
                    ROOT, {"PATH": "/opt/unreviewed"}, require_approved=True,
                ),
                "outside the approved namespace",
            )
        process.assert_not_called()

    def test_colima_runtime_root_and_codex_home_are_nofollow_private_and_bound(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            root = parent / "runtime"
            root.mkdir(mode=0o700)
            (root / "bin").mkdir(mode=0o700)
            with mock.patch.dict(os.environ, {"T11_VM_RUNTIME_ROOT": str(root)}):
                layout = self.adapter.prepare_colima_runtime_layout()
            self.assertEqual(0o700, stat.S_IMODE(os.stat(root, follow_symlinks=False).st_mode))
            self.assertRegex(layout.runtime_root_binding_sha256, r"^[0-9a-f]{64}$")
            self.assertRegex(layout.dedicated_codex_home_binding_sha256, r"^[0-9a-f]{64}$")
            public_projection = {
                "runtime_root_binding_sha256": layout.runtime_root_binding_sha256,
                "dedicated_codex_home_binding_sha256": layout.dedicated_codex_home_binding_sha256,
            }
            self.assertNotIn(str(root), json.dumps(public_projection))
            os.chmod(root, 0o755)
            with mock.patch.dict(os.environ, {"T11_VM_RUNTIME_ROOT": str(root)}):
                self.assert_contract_error(self.adapter.prepare_colima_runtime_layout, "mode")
            os.chmod(root, 0o700)
            unsafe = parent / "unsafe"
            unsafe.symlink_to(root, target_is_directory=True)
            with mock.patch.dict(os.environ, {"T11_VM_RUNTIME_ROOT": str(unsafe)}):
                self.assert_contract_error(self.adapter.prepare_colima_runtime_layout, "link")
            (root / "home/.codex").rmdir()
            (root / "home/.codex").symlink_to(root / "bin", target_is_directory=True)
            with mock.patch.dict(os.environ, {"T11_VM_RUNTIME_ROOT": str(root)}):
                self.assert_contract_error(self.adapter.prepare_colima_runtime_layout, "link")

    def test_containment_evidence_is_not_codex_attestation_and_lifecycle_is_honest(self):
        evidence = self.adapter.not_run_containment_provider_evidence()
        self.assertFalse(evidence["codex_authenticated_attestation"])
        self.assertEqual({
            "destroy_required": False,
            "destroy_requested": False,
            "destroy_completed": False,
            "profile_absence_readback": "not-run",
        }, evidence["lifecycle"])
        self.assertNotIn("/Users/", json.dumps(evidence))
        self.assertEqual("not-run", evidence["control_plane"]["status"])
        self.assertFalse(evidence["control_plane"]["fresh_instance"])
        self.assertEqual(
            self.adapter.not_run_git_bootstrap_evidence(),
            evidence["repository_git_bootstrap"],
        )
        self.assertFalse(evidence["repository_git_bootstrap_runtime_match"])
        self.assertEqual(
            "0" * 64, evidence["repository_git_clone_contract_sha256"],
        )

        passing = self.passing_containment_evidence()
        self.assertEqual(
            passing,
            self.adapter.validate_containment_provider_evidence(
                copy.deepcopy(passing), allow_fixture=True,
            ),
        )
        mutations = (
            lambda item: item.pop("repository_git_bootstrap"),
            lambda item: item.__setitem__(
                "repository_git_bootstrap_runtime_match", False,
            ),
            lambda item: item.pop("repository_git_clone_contract_sha256"),
            lambda item: item.__setitem__(
                "repository_git_clone_contract_sha256", "0" * 64,
            ),
            lambda item: item.__setitem__(
                "repository_git_clone_contract_sha256",
                self.adapter.stage_a1_git_clone_contract_sha256(
                    "c" * 40, item["public_tree"],
                ),
            ),
            lambda item: item["repository_git_bootstrap"].__setitem__(
                "package_version", "1:2.43.0-1ubuntu7.2",
            ),
            lambda item: item["repository_git_bootstrap"].__setitem__(
                "binary_sha256", "0" * 64,
            ),
            lambda item: item["repository_git_bootstrap"].__setitem__(
                "controller_argv_sha256", "0" * 64,
            ),
            lambda item: item["repository_git_bootstrap"].__setitem__(
                "raw_stderr_recorded", True,
            ),
        )
        for mutation in mutations:
            candidate = copy.deepcopy(passing)
            mutation(candidate)
            with self.subTest(candidate=candidate):
                self.assert_contract_error(
                    lambda c=candidate: self.adapter.validate_containment_provider_evidence(
                        c, allow_fixture=True,
                    )
                )

    def test_live_profile_cross_binds_provider_platform_client_and_chronology(self):
        valid = copy.deepcopy(self.profile)
        valid["scope"] = "exact-head-live-sensor"
        valid["platform"] = {"os": "Linux", "architecture": "aarch64"}
        self.adapter.validate_runtime_profile(valid)
        mutations = (
            lambda item: item["platform"].__setitem__("os", "Darwin"),
            lambda item: item["client"].__setitem__("binary_sha256", "f" * 64),
            lambda item: item["auth"].__setitem__("class", "api-key"),
            lambda item: item["evidence"]["containment_provider"].__setitem__("codex_authenticated_attestation", True),
            lambda item: item["evidence"]["containment_provider"]["control_plane"].__setitem__("codex_authenticated_attestation", True),
            lambda item: item["evidence"]["containment_provider"].__setitem__("created_at", "2099-01-01T00:00:00Z"),
            lambda item: item["evidence"]["containment_provider"].__setitem__(
                "repository_git_bootstrap_runtime_match", False,
            ),
            lambda item: item["evidence"]["containment_provider"].__setitem__(
                "repository_git_clone_contract_sha256", "0" * 64,
            ),
            lambda item: item["evidence"]["containment_provider"][
                "repository_git_bootstrap"
            ].__setitem__("package_version", "1:2.43.0-1ubuntu7.2"),
        )
        for mutation in mutations:
            profile = copy.deepcopy(valid)
            mutation(profile)
            with self.subTest(profile=profile):
                self.assert_contract_error(lambda p=profile: self.adapter.validate_runtime_profile(p))

    def live_claim_layout(self, root):
        return self.adapter.ColimaRuntimeLayout(
            root=root,
            home=root / "home",
            tmp=root / "tmp",
            work=root / "work",
            binary=root / "bin/codex",
            runtime_root_binding_sha256=self.adapter._directory_binding_sha256(
                os.stat(root, follow_symlinks=False), "runtime-root",
            ),
            dedicated_codex_home_binding_sha256="7" * 64,
        )

    def live_claim_argv(self):
        return [
            "/reviewed/codex",
            "-c", "memories.generate_memories=false",
            "-c", "memories.use_memories=false",
        ]

    def test_live_attempt_claim_is_durable_exact_and_blocks_same_or_different_retry(self):
        failed_worker = self.adapter.ProcessResult(1, None, False, False, False, b"", 0, True)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            layout = self.live_claim_layout(root)
            with mock.patch.object(self.adapter, "run_bounded_process", return_value=failed_worker) as worker:
                first = self.adapter.run_claimed_live_worker(
                    layout, copy.deepcopy(self.envelope), copy.deepcopy(self.profile),
                    self.live_claim_argv(), root, {}, b"stdin-only prompt",
                )
                self.assertEqual(1, first.exit_code)
                self.assert_contract_error(
                    lambda: self.adapter.run_claimed_live_worker(
                        layout, copy.deepcopy(self.envelope), copy.deepcopy(self.profile),
                        self.live_claim_argv(), root, {}, b"stdin-only prompt",
                    ),
                    "already consumed",
                )
                different = copy.deepcopy(self.envelope)
                different["attempt_id"] = "ATTEMPT-fedcba9876543210"
                self.assert_contract_error(
                    lambda: self.adapter.run_claimed_live_worker(
                        layout, different, copy.deepcopy(self.profile),
                        self.live_claim_argv(), root, {}, b"different stdin-only prompt",
                    ),
                    "already consumed",
                )
            worker.assert_called_once()
            claim_path = root / self.adapter.LIVE_ATTEMPT_CLAIM_NAME
            info = os.stat(claim_path, follow_symlinks=False)
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(0o600, stat.S_IMODE(info.st_mode))
            self.assertEqual(1, info.st_nlink)
            record = json.loads(claim_path.read_text(encoding="utf-8"))
            payload = {
                "schema": record["schema"],
                "attempt_id": record["attempt_id"],
                "public_head": record["public_head"],
                "public_tree": record["public_tree"],
                "provider_profile_name": record["provider_profile_name"],
                "vm_instance_identity_sha256": record["vm_instance_identity_sha256"],
                "control_plane_sha256": record["control_plane_sha256"],
            }
            self.assertEqual(
                self.adapter.sha256_bytes(self.adapter.canonical_bytes(payload)),
                record["canonical_sha256"],
            )
            self.assertNotIn(str(root), json.dumps(record))
            self.assertNotIn("stdin-only prompt", json.dumps(record))
            self.assertEqual(
                self.profile["evidence"]["containment_provider"]["profile_name"],
                record["provider_profile_name"],
            )
            self.assertEqual(
                self.profile["evidence"]["containment_provider"]["vm_instance_identity_sha256"],
                record["vm_instance_identity_sha256"],
            )

    def test_live_attempt_claim_mode_namespace_binding_and_durability_fail_closed(self):
        failed_worker = self.adapter.ProcessResult(1, None, False, False, False, b"", 0, True)

        def exercise(patch_context, expect_claim=True):
            with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
                root = Path(temporary)
                os.chmod(root, 0o700)
                layout = self.live_claim_layout(root)
                with patch_context, mock.patch.object(
                    self.adapter, "run_bounded_process", return_value=failed_worker,
                ) as worker:
                    self.assert_contract_error(lambda: self.adapter.run_claimed_live_worker(
                        layout, copy.deepcopy(self.envelope), copy.deepcopy(self.profile),
                        self.live_claim_argv(), root, {}, b"stdin-only prompt",
                    ))
                worker.assert_not_called()
                self.assertEqual(expect_claim, (root / self.adapter.LIVE_ATTEMPT_CLAIM_NAME).exists())

        real_fchmod = self.adapter.os.fchmod
        exercise(mock.patch.object(
            self.adapter.os, "fchmod",
            side_effect=lambda descriptor, _mode: real_fchmod(descriptor, 0o644),
        ))

        real_write = self.adapter.os.write

        def corrupt_write(descriptor, data):
            corrupted = (b"X" + data[1:]) if data else data
            return real_write(descriptor, corrupted)

        exercise(mock.patch.object(self.adapter.os, "write", side_effect=corrupt_write))

        real_stat = self.adapter.os.stat
        swapped = {"done": False}

        def namespace_swap(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            if path == self.adapter.LIVE_ATTEMPT_CLAIM_NAME and kwargs.get("dir_fd") is not None and not swapped["done"]:
                swapped["done"] = True
                values = list(info)
                values[1] += 1
                return os.stat_result(values)
            return info

        exercise(mock.patch.object(self.adapter.os, "stat", side_effect=namespace_swap), expect_claim=False)
        exercise(mock.patch.object(self.adapter.os, "fsync", side_effect=OSError("durability unavailable")))

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            profile = copy.deepcopy(self.profile)
            profile["evidence"]["containment_provider"]["public_head"] = "f" * 40
            with mock.patch.object(self.adapter, "run_bounded_process", return_value=failed_worker) as worker:
                self.assert_contract_error(lambda: self.adapter.run_claimed_live_worker(
                    self.live_claim_layout(root), copy.deepcopy(self.envelope), profile,
                    self.live_claim_argv(), root, {}, b"stdin-only prompt",
                ), "binding")
            worker.assert_not_called()
            self.assertFalse((root / self.adapter.LIVE_ATTEMPT_CLAIM_NAME).exists())

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            with mock.patch.object(self.adapter, "run_bounded_process", return_value=failed_worker) as worker:
                self.assert_contract_error(lambda: self.adapter.run_claimed_live_worker(
                    self.live_claim_layout(root), copy.deepcopy(self.envelope), copy.deepcopy(self.profile),
                    ["/reviewed/codex"], root, {}, b"stdin-only prompt",
                ), "memory")
            worker.assert_not_called()
            self.assertFalse((root / self.adapter.LIVE_ATTEMPT_CLAIM_NAME).exists())

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
            profile["capabilities"]["documented_config_keys_probe"] = "UNCHECKABLE"
            profile["capabilities"]["shell_environment_probe"] = "UNCHECKABLE"
            profile["evidence"]["lane_statuses"]["config_status"] = "UNCHECKABLE"
            profile["evidence"]["lane_statuses"]["shell_environment_status"] = "UNCHECKABLE"
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
        stable_version = b"codex-cli 0.150.1\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            for child in ("home", "tmp", "work", "bin"):
                (root / child).mkdir(mode=0o700)
            (root / "home/.codex").mkdir(mode=0o700)
            layout = self.adapter.ColimaRuntimeLayout(
                root, root / "home", root / "tmp", root / "work", Path(sys.executable),
                "6" * 64, "7" * 64,
            )
            provider_input = self.colima_provider_input()
            containment = self.passing_containment_evidence()
            uname = SimpleNamespace(sysname="Linux", machine="aarch64", release="6.12.0-t11")
            with mock.patch.object(self.adapter, "prepare_colima_runtime_layout", return_value=layout), \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "observe_stage_a1_prerequisite", return_value=self.passing_stage_a1_prerequisite()), \
             mock.patch.object(self.adapter, "probe_runtime_evidence", return_value=self.passing_runtime_probe()), \
             mock.patch.object(self.adapter, "observe_colima_provider_evidence", return_value=containment), \
             mock.patch.object(self.adapter, "auth_class", return_value="signed-in-client"), \
             mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64), \
             mock.patch.object(self.adapter.os, "uname", return_value=uname):
                observed = self.adapter.observe_runtime_profile(ROOT, "gpt-5.6-sol", "high", provider_input)
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
        fresh_provider_input = sensor.call_args.args[3]
        self.assertEqual("t11-colima-provider-input/v1", fresh_provider_input["schema"])
        self.assertEqual(self.envelope["harness"]["commit"], fresh_provider_input["repository"]["head"])
        self.assertEqual(self.envelope["harness"]["tree"], fresh_provider_input["repository"]["tree"])
        self.assertEqual(
            self.adapter.expected_git_bootstrap_evidence(),
            fresh_provider_input["repository"]["git_bootstrap"],
        )
        self.assertEqual(
            self.adapter.stage_a1_git_clone_contract_sha256(
                self.envelope["harness"]["commit"],
                self.envelope["harness"]["tree"],
            ),
            fresh_provider_input["repository"]["git_clone_contract_sha256"],
        )
        live_argv_text = "\n".join(self.adapter.build_live_argv(
            Path("/reviewed/codex"), Path("/isolated-target"), ROOT, self.envelope,
        ))
        self.assertNotIn(fresh_provider_input["provider"]["profile_name"], live_argv_text)
        self.assertNotIn(fresh_provider_input["repository"]["head"], live_argv_text)
        create.assert_not_called()

    def test_stable_sensor_blocks_live_without_approved_provider(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 0.150.1\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)

        with mock.patch.object(self.adapter, "resolve_executable_from_path", return_value=Path(sys.executable)), \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "observe_stage_a1_prerequisite", return_value=self.passing_stage_a1_prerequisite()), \
             mock.patch.object(self.adapter, "probe_runtime_evidence", return_value=self.passing_runtime_probe()), \
             mock.patch.object(self.adapter, "auth_class", return_value="signed-in-client"), \
             mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64):
            observed = self.adapter.observe_runtime_profile(ROOT, "gpt-5.6-sol", "high")
        self.assertEqual("UNCHECKABLE", observed["status"])
        self.assertEqual("pass", observed["capabilities"]["process_cleanup_probe"])
        self.assertEqual(
            "not-run", observed["evidence"]["lane_statuses"]["provider_isolation_status"],
        )
        self.assertFalse(observed["live_run_allowed"])

    def test_stage_a_probe_only_matches_without_auth_and_keeps_lanes_independent(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 0.150.1\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(
                0, None, False, False, False, payload, 0, True,
            )

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            for child in ("home", "tmp", "work", "bin"):
                (root / child).mkdir(mode=0o700)
            (root / "home/.codex").mkdir(mode=0o700)
            layout = self.adapter.ColimaRuntimeLayout(
                root, root / "home", root / "tmp", root / "work",
                Path(sys.executable), "6" * 64, "7" * 64,
            )
            provider_input = self.colima_provider_input()
            containment = self.passing_containment_evidence()
            uname = SimpleNamespace(
                sysname="Linux", machine="aarch64", release="6.12.0-t11",
            )
            for network_status, expected_status in (
                ("pass", "probe-only-match"), ("fail", "profile-drift"),
            ):
                probe = self.passing_runtime_probe()
                probe["evidence"]["network_sandbox_behavior"]["status"] = network_status
                probe["evidence"]["lane_statuses"]["codex_sandbox_network_status"] = network_status
                with self.subTest(network_status=network_status), \
                     mock.patch.object(self.adapter, "prepare_colima_runtime_layout", return_value=layout), \
                     mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
                     mock.patch.object(self.adapter, "observe_stage_a1_prerequisite", return_value=self.passing_stage_a1_prerequisite()), \
                     mock.patch.object(self.adapter, "probe_runtime_evidence", return_value=probe), \
                     mock.patch.object(self.adapter, "observe_colima_provider_evidence", return_value=containment), \
                     mock.patch.object(self.adapter, "auth_class", return_value="unavailable"), \
                     mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64), \
                     mock.patch.object(self.adapter.os, "uname", return_value=uname):
                    observed = self.adapter.observe_runtime_profile(
                        ROOT, "gpt-5.6-sol", "high", provider_input,
                        probe_only=True,
                    )
                self.assertEqual(expected_status, observed["status"])
                self.assertEqual(
                    "pass",
                    observed["evidence"]["lane_statuses"]["provider_isolation_status"],
                )
                self.assertEqual(
                    network_status,
                    observed["evidence"]["lane_statuses"]["codex_sandbox_network_status"],
                )
                self.assertEqual("unavailable", observed["auth"]["class"])
                self.assertFalse(observed["live_run_allowed"])

    def test_profile_probe_outer_failures_use_only_fixed_safe_enums(self):
        private_failure = self.adapter.ContractError(
            "file:/Users/alice/private sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
        )
        self.assertEqual(
            {
                "schema": "codex-exec-adapter-error/v1",
                "status": "fail",
                "reason": "bounded runtime contract failure",
            },
            self.adapter.safe_error(private_failure),
        )
        for stage, reason_code in self.adapter.PROFILE_PROBE_FAILURES.items():
            with self.subTest(stage=stage):
                rendered = self.adapter.safe_error(
                    self.adapter.ProfileProbeError(stage, reason_code),
                )
                self.assertEqual(
                    {
                        "schema": "codex-exec-adapter-error/v1",
                        "status": "fail",
                        "reason": "bounded runtime contract failure",
                        "stage": stage,
                        "reason_code": reason_code,
                    },
                    rendered,
                )
                serialized = json.dumps(rendered)
                self.assertNotIn("alice", serialized)
                self.assertNotIn("sk-proj", serialized)
                self.assertNotRegex(serialized, r"/Users/|/home/|/tmp/")
        self.assert_contract_error(
            lambda: self.adapter.ProfileProbeError(
                "runtime-layout", "not-an-allowed-reason",
            ),
            "classification",
        )

    def test_profile_probe_outer_boundaries_are_safely_classified(self):
        provider_input = self.colima_provider_input()

        with mock.patch.object(
            self.adapter, "require_runtime_fs_capabilities",
            side_effect=self.adapter.ContractError("private capability detail"),
        ):
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter.observe_runtime_profile(
                    ROOT, "gpt-5.6-sol", "high", provider_input,
                    probe_only=True,
                )
        self.assertEqual(
            ("runtime-capabilities", "capability-unavailable"),
            (raised.exception.stage, raised.exception.reason_code),
        )

        with self.assertRaises(self.adapter.ProfileProbeError) as raised:
            self.adapter.observe_runtime_profile(
                ROOT, "gpt-5.6-sol", "high", {}, probe_only=True,
            )
        self.assertEqual(
            ("provider-input", "input-invalid"),
            (raised.exception.stage, raised.exception.reason_code),
        )

        with mock.patch.object(
            self.adapter, "prepare_colima_runtime_layout",
            side_effect=self.adapter.ContractError("private layout detail"),
        ):
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter.observe_runtime_profile(
                    ROOT, "gpt-5.6-sol", "high", provider_input,
                    probe_only=True,
                )
        self.assertEqual(
            ("runtime-layout", "layout-invalid"),
            (raised.exception.stage, raised.exception.reason_code),
        )

        layout = self.adapter.ColimaRuntimeLayout(
            ROOT, ROOT, ROOT, ROOT, Path(sys.executable), "6" * 64, "7" * 64,
        )
        with mock.patch.object(
            self.adapter, "bounded_capture",
            side_effect=self.adapter.ContractError("private client detail"),
        ):
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter._observe_runtime_profile_bound(
                    ROOT, "gpt-5.6-sol", "high", Path(sys.executable), ROOT,
                    {}, provider_input, layout, probe_only=True,
                )
        self.assertEqual(
            ("client-evidence", "version-help-uncheckable"),
            (raised.exception.stage, raised.exception.reason_code),
        )

        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 0.150.1\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(
                0, None, False, False, False, payload, 0, True,
            )

        common_patches = (
            mock.patch.object(self.adapter, "bounded_capture", side_effect=capture),
            mock.patch.object(
                self.adapter, "probe_runtime_evidence",
                return_value=self.passing_runtime_probe(),
            ),
            mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64),
        )
        with common_patches[0], common_patches[1], common_patches[2], \
             mock.patch.object(
                 self.adapter, "observe_colima_provider_evidence",
                 side_effect=self.adapter.ContractError("private provider detail"),
             ):
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter._observe_runtime_profile_bound(
                    ROOT, "gpt-5.6-sol", "high", Path(sys.executable), ROOT,
                    {}, provider_input, layout, probe_only=True,
                )
        self.assertEqual(
            ("provider-evidence", "observation-invalid"),
            (raised.exception.stage, raised.exception.reason_code),
        )

        with mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(
                 self.adapter, "probe_runtime_evidence",
                 return_value=self.passing_runtime_probe(),
             ), mock.patch.object(
                 self.adapter, "observe_colima_provider_evidence",
                 return_value=self.passing_containment_evidence(),
             ), mock.patch.object(
                 self.adapter, "auth_class", return_value="unavailable",
             ), mock.patch.object(
                 self.adapter, "hash_regular_file", return_value="a" * 64,
             ), mock.patch.object(
                 self.adapter, "validate_runtime_profile",
                 side_effect=self.adapter.ContractError("private profile detail"),
             ):
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter._observe_runtime_profile_bound(
                    ROOT, "gpt-5.6-sol", "high", Path(sys.executable), ROOT,
                    {}, provider_input, layout, probe_only=True,
                )
        self.assertEqual(
            ("profile-validation", "profile-invalid"),
            (raised.exception.stage, raised.exception.reason_code),
        )

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
            with self.assertRaises(self.adapter.ProfileProbeError) as raised:
                self.adapter.observe_runtime_profile(
                    ROOT, "gpt-5.6-sol", "high",
                )
            self.assertEqual(
                ("runtime-capabilities", "capability-unavailable"),
                (raised.exception.stage, raised.exception.reason_code),
            )
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

    def real_doctor_report_fixture(self, overall="ok"):
        checks = {}
        for check_id, category in (
            ("auth.credentials", "auth"),
            ("config.load", "config"),
            ("runtime.provenance", "runtime"),
            ("sandbox.helpers", "sandbox"),
        ):
            status = overall if category == "config" else "ok"
            checks[check_id] = {
                "id": check_id,
                "category": category,
                "status": status,
                "summary": "redacted diagnostic row",
                "details": {"state": "redacted"},
                "durationMs": 1,
                "remediation": None,
            }
        return {
            "schemaVersion": 1,
            "generatedAt": "2026-08-28T00:00:00Z",
            "codexVersion": "0.150.1",
            "overallStatus": overall,
            "checks": checks,
        }

    def test_documented_memory_keys_and_runtime_argv_policy_fail_closed(self):
        self.assertFalse(self.adapter.REQUIRED_OVERRIDES["memories.generate_memories"])
        self.assertFalse(self.adapter.REQUIRED_OVERRIDES["memories.use_memories"])
        self.assertNotIn("features.memory_tool", self.adapter.REQUIRED_OVERRIDES)
        self.assertNotIn("features.memory_tool_use", self.adapter.REQUIRED_OVERRIDES)
        self.adapter.validate_documented_memory_overrides(self.adapter.REQUIRED_OVERRIDES)
        for mutation in ("missing-generate", "missing-use", "true-generate", "true-use", "legacy"):
            values = dict(self.adapter.REQUIRED_OVERRIDES)
            if mutation == "missing-generate":
                values.pop("memories.generate_memories")
            elif mutation == "missing-use":
                values.pop("memories.use_memories")
            elif mutation == "true-generate":
                values["memories.generate_memories"] = True
            elif mutation == "true-use":
                values["memories.use_memories"] = True
            else:
                values["features.memory_tool"] = False
            with self.subTest(mutation=mutation):
                self.assert_contract_error(
                    lambda v=values: self.adapter.validate_documented_memory_overrides(v),
                    "memory",
                )

        valid = [
            "/reviewed/codex", "-c", "memories.generate_memories=false",
            "-c", "memories.use_memories=false",
        ]
        self.adapter.validate_runtime_argv_policy(valid, require_memory_overrides=True)
        for forbidden in ("--ignore-rules", "--ignore-rules=true", "--dangerously-bypass-approvals-and-sandbox"):
            with self.subTest(forbidden=forbidden):
                self.assert_contract_error(
                    lambda f=forbidden: self.adapter.validate_runtime_argv_policy(valid + [f], True),
                    "bypass",
                )
        for invalid in (
            ["/reviewed/codex", "-c", "memories.use_memories=false"],
            ["/reviewed/codex", "-c", "memories.generate_memories=true", "-c", "memories.use_memories=false"],
            ["/reviewed/codex", "-c", "features.memory_tool=false", "-c", "memories.generate_memories=false", "-c", "memories.use_memories=false"],
        ):
            self.assert_contract_error(
                lambda value=invalid: self.adapter.validate_runtime_argv_policy(value, True),
                "memory",
            )
        self.assert_contract_error(
            lambda: self.adapter.validate_runtime_argv_policy(
                valid + ["-c", "features.use_legacy_landlock=true"], True,
            ),
            "legacy Landlock",
        )

    def test_configuration_intent_is_adapter_authored_stable_and_rules_are_no_follow(self):
        intent = self.adapter.runtime_configuration_intent()
        self.assertEqual("adapter-authored", intent["authority"])
        self.assertFalse(intent["effective_configuration_proven"])
        self.assertEqual(["CODEX_HOME", "HOME", "PATH", "TMPDIR"], intent["dynamic_environment_values_excluded"])
        self.assertNotRegex(self.adapter.canonical_bytes(intent).decode("utf-8"), r"/Users/|/tmp/|/private/")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            for home in (first, second):
                home.mkdir(mode=0o700)
                tmp = home / "tmp"
                tmp.mkdir(mode=0o700)
                env = self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmp)
                self.assertEqual(intent["rules_profile_sha256"], self.adapter.materialize_reviewed_rules_profile(env))
                rules = Path(env["CODEX_HOME"]) / self.adapter.REVIEWED_RULES_RELATIVE_PATH
                self.assertEqual(self.adapter.REVIEWED_RULES_BYTES, rules.read_bytes())
                self.assertEqual(0o600, stat.S_IMODE(os.stat(rules, follow_symlinks=False).st_mode))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            attacker = root / "attacker"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            attacker.mkdir(mode=0o700)
            (home / ".codex").symlink_to(attacker, target_is_directory=True)
            environment = self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmp)
            self.assert_contract_error(
                lambda: self.adapter.materialize_reviewed_rules_profile(environment),
                "safely",
            )
        self.assertEqual(intent, self.adapter.runtime_configuration_intent())

    def test_real_doctor_report_is_diagnostic_only_even_with_nonzero_exit(self):
        report = self.real_doctor_report_fixture("fail")
        result = self.adapter.ProcessResult(
            1, None, False, False, False,
            self.adapter.canonical_bytes(report), 0, True,
        )
        evidence = self.adapter.doctor_diagnostic_health(result)
        self.assertEqual("diagnostic-only", evidence["classification"])
        self.assertEqual("fail", evidence["status"])
        self.assertFalse(evidence["codex_issued_effective_configuration_proof"])

        impossible = {
            "schema": "t11-runtime-configuration-probe/v1",
            "effective_configuration_sha256": "0" * 64,
            "model_invoked": False,
        }
        not_doctor = self.adapter.doctor_diagnostic_health(self.adapter.ProcessResult(
            0, None, False, False, False,
            self.adapter.canonical_bytes(impossible), 0, True,
        ))
        self.assertEqual("UNCHECKABLE", not_doctor["status"])
        self.assertFalse(not_doctor["codex_issued_effective_configuration_proof"])

        for field, invalid in (("schemaVersion", 2), ("codexVersion", "0.150.0")):
            drifted = self.real_doctor_report_fixture()
            drifted[field] = invalid
            evidence = self.adapter.doctor_diagnostic_health(
                self.adapter.ProcessResult(
                    0, None, False, False, False,
                    self.adapter.canonical_bytes(drifted), 0, True,
                )
            )
            with self.subTest(field=field):
                self.assertEqual("UNCHECKABLE", evidence["status"])

    def test_auth_probe_classifies_only_exact_bounded_stderr(self):
        cases = (
            (0, b"", b"Logged in using ChatGPT\n", "signed-in-client"),
            (0, b"", b"Logged in using an API key - sk-abcde***vwxyz\n", "api-key"),
            (0, b"", b"abcdefgh***vwxyz\n", "unknown"),
            (0, b"", b"Logged in using an API key - abcdefgh***vwxyz\n", "api-key"),
            (0, b"", b"Logged in using an API key - ***\n", "api-key"),
            (1, b"", b"not logged in\n", "unavailable"),
            (0, b"Logged in using ChatGPT\n", b"", "unknown"),
            (0, b"", b"Logged in using ChatGPT\nextra\n", "unknown"),
            (0, b"", b"unexpected success\n", "unknown"),
        )
        for exit_code, stdout, stderr, expected in cases:
            result = self.adapter.ProcessResult(
                exit_code, None, False, False, False, stdout, len(stderr), True,
                stderr,
            )
            with self.subTest(expected=expected), mock.patch.object(
                self.adapter, "bounded_capture", return_value=result,
            ) as capture:
                observed = self.adapter.auth_class(Path("/reviewed/codex"), ROOT, {})
                self.assertEqual(expected, observed)
                if stderr:
                    self.assertNotIn(stderr.decode("utf-8", errors="ignore"), observed)
                self.assertTrue(capture.call_args.kwargs["capture_stderr"])
        with mock.patch.object(
            self.adapter, "bounded_capture",
            side_effect=self.adapter.ContractError("private process failure"),
        ):
            self.assertEqual(
                "unknown", self.adapter.auth_class(Path("/reviewed/codex"), ROOT, {}),
            )

    def test_official_0150_sandbox_probe_argv_uses_read_only_profile_and_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            argv = self.adapter.sandbox_probe_argv(
                Path("/reviewed/codex"), environment, ["/usr/bin/env", "-0"],
            )
        sandbox_index = argv.index("sandbox")
        self.assertEqual([
            "sandbox", "--permission-profile", ":read-only",
            "-C", str(root), "--", "/usr/bin/env", "-0",
        ], argv[sandbox_index:])
        self.assertNotIn("--sandbox-state-json", argv)
        self.assertNotIn("--sandbox-state-disable-network", argv)
        self.adapter.validate_sandbox_probe_argv(argv)
        for mutation in (
            [item for item in argv if item != "--"],
            [item for item in argv if item != "--permission-profile"],
            [item for item in argv if item != ":read-only"],
            argv + ["--sandbox-state-json", "{}"],
            argv + ["--sandbox-state-disable-network"],
            argv[:sandbox_index + 1] + ["-C", str(root)] + argv[sandbox_index + 1:],
        ):
            with self.subTest(mutation=mutation):
                self.assert_contract_error(
                    lambda value=mutation: self.adapter.validate_sandbox_probe_argv(value),
                    "sandbox probe argv",
                )

    def test_shell_environment_probe_requires_exact_sandbox_network_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            required = self.adapter.reviewed_runtime_configuration(environment)
            configured = required["shell_environment_policy.set"]
            self.assertNotIn("CODEX_SANDBOX_NETWORK_DISABLED", configured)

            def result_with(extra):
                entries = dict(configured)
                entries.update(extra)
                payload = b"\0".join(
                    (name + "=" + value).encode("utf-8")
                    for name, value in sorted(entries.items())
                ) + b"\0"
                return self.adapter.ProcessResult(
                    0, None, False, False, False, payload, 0, True,
                )

            cases = (
                ({"CODEX_SANDBOX_NETWORK_DISABLED": "1"}, "pass"),
                ({}, "fail"),
                ({"CODEX_SANDBOX_NETWORK_DISABLED": "0"}, "fail"),
                ({"CODEX_SANDBOX_NETWORK_DISABLED": "true"}, "fail"),
                ({
                    "CODEX_SANDBOX_NETWORK_DISABLED": "1",
                    "T11_UNKNOWN_AUTOMATIC": "1",
                }, "fail"),
            )
            for extra, expected in cases:
                with self.subTest(extra=extra), mock.patch.object(
                    self.adapter, "bounded_capture", return_value=result_with(extra),
                ) as capture:
                    self.assertEqual(
                        expected,
                        self.adapter.shell_environment_probe(
                            Path("/reviewed/codex"), root, environment, required,
                        ),
                    )
                    self.assertEqual(
                        "must-be-overridden",
                        capture.call_args.args[2]["CODEX_SANDBOX_NETWORK_DISABLED"],
                    )

    def test_network_sandbox_child_handles_socket_creation_and_connect_denial(self):
        class ChildSocket:
            def __init__(self, connect_error=None):
                self.connect_error = connect_error

            def __enter__(self):
                return self

            def __exit__(self, _kind, _value, _traceback):
                return False

            def settimeout(self, _seconds):
                pass

            def connect(self, _address):
                if self.connect_error is not None:
                    raise self.connect_error

        original_import = __import__

        def run_child(factory):
            fake_socket = SimpleNamespace(socket=factory)

            def import_module(name, *args, **kwargs):
                if name == "socket":
                    return fake_socket
                return original_import(name, *args, **kwargs)

            with mock.patch.object(sys, "argv", ["network-probe", "9"]), \
                 mock.patch("builtins.__import__", side_effect=import_module), \
                 self.assertRaises(SystemExit) as raised:
                exec(
                    self.adapter.NETWORK_SANDBOX_PROBE_SCRIPT,
                    {"__builtins__": __builtins__},
                )
            return raised.exception.code

        def denied_creation():
            raise OSError(errno.EPERM, "sandbox denied socket creation")

        def exhausted_creation():
            raise OSError(errno.EMFILE, "unrelated resource exhaustion")

        self.assertEqual(0, run_child(denied_creation))
        self.assertEqual(43, run_child(exhausted_creation))
        self.assertEqual(0, run_child(
            lambda: ChildSocket(connect_error=OSError(errno.EPERM, "denied")),
        ))
        self.assertEqual(42, run_child(ChildSocket))
        self.assertEqual(43, run_child(
            lambda: ChildSocket(connect_error=OSError(errno.EMFILE, "unrelated")),
        ))

    def test_network_sandbox_probe_preserves_closed_result_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            listener = mock.MagicMock()
            listener.__enter__.return_value = listener
            listener.getsockname.return_value = ("127.0.0.1", 43123)
            connection = mock.MagicMock()
            connection.__enter__.return_value = connection
            for exit_code, expected in (
                (0, "pass"), (42, "fail"), (43, "UNCHECKABLE"),
                (1, "UNCHECKABLE"),
            ):
                result = self.adapter.ProcessResult(
                    exit_code, None, False, False, False, b"", 0, True,
                )
                with self.subTest(exit_code=exit_code), \
                     mock.patch.object(self.adapter.socket, "socket", return_value=listener), \
                     mock.patch.object(
                         self.adapter.socket, "create_connection", return_value=connection,
                     ), mock.patch.object(
                         self.adapter, "bounded_capture", return_value=result,
                     ):
                    self.assertEqual(
                        expected,
                        self.adapter.network_sandbox_behavior_probe(
                            Path("/reviewed/codex"), root, environment,
                        ),
                    )

            with mock.patch.object(
                self.adapter.socket, "socket", side_effect=OSError("control unavailable"),
            ):
                self.assertEqual(
                    "UNCHECKABLE",
                    self.adapter.network_sandbox_behavior_probe(
                        Path("/reviewed/codex"), root, environment,
                    ),
                )

    def test_worker_argv_failure_is_fixed_stage_and_reason_only(self):
        with mock.patch.object(
            self.adapter, "load_repository_json",
            side_effect=self.adapter.ContractError("file:/Users/alice/private/envelope"),
        ):
            evidence = self.adapter.exact_worker_argv_evidence(
                Path("/reviewed/codex"), ROOT, ROOT, {},
            )
        self.assertEqual({
            "status": "fail",
            "stage": "load-envelope",
            "reason_code": "envelope-invalid",
            "rules_bypass_absent": False,
            "dynamic_task_data_stdin_only": False,
        }, evidence)
        rendered = json.dumps(evidence, sort_keys=True)
        self.assertNotIn("alice", rendered)
        self.assertNotIn("argv", evidence)
        self.assertNotIn("exception", evidence)

    def test_doctor_retains_only_safe_checks_and_limits_blocking_warnings(self):
        report = self.real_doctor_report_fixture("warning")
        report["checks"]["config.load"]["category"] = "config"
        report["checks"]["config.load"]["notes"] = ["file:/Users/alice/private"]
        report["checks"]["config.load"]["issues"] = []
        report["checks"]["ui.theme"] = {
            "id": "ui.theme", "category": "ui", "status": "warning",
            "summary": "file:/Users/alice/private", "details": {"token": "secret"},
            "durationMs": 1, "remediation": "private detail",
        }
        required_warning = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            )
        )
        self.assertEqual("fail", required_warning["status"])
        self.assertEqual(5, len(required_warning["checks"]))
        projected = {check["id"]: check for check in required_warning["checks"]}
        self.assertEqual(
            {"id": "config.load", "category": "config", "status": "warning"},
            projected["config.load"],
        )
        self.assertEqual(
            {"id": "ui.theme", "category": "ui", "status": "warning"},
            projected["ui.theme"],
        )
        self.assertNotIn("alice", json.dumps(required_warning))

        report["checks"]["config.load"]["status"] = "ok"
        advisory = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            )
        )
        self.assertEqual("pass-with-advisory-warning", advisory["status"])

        report["checks"]["auth.session"] = {
            "id": "auth.session", "category": "auth", "status": "warning",
            "summary": "unauthenticated", "details": {}, "durationMs": 1,
            "remediation": None,
        }
        report["checks"].pop("ui.theme")
        live_auth_required = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            )
        )
        self.assertEqual("fail", live_auth_required["status"])
        stage_a = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            ),
            ("config", "runtime", "sandbox"),
        )
        self.assertEqual("pass-with-advisory-warning", stage_a["status"])

    def test_stage_a_doctor_accepts_only_expected_auth_failure_and_requires_categories(self):
        report = self.real_doctor_report_fixture()
        report["checks"]["auth.credentials"]["status"] = "fail"
        report["overallStatus"] = "fail"
        stage_a = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                1, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            ),
            ("config", "runtime", "sandbox"),
        )
        self.assertEqual("pass-with-advisory-warning", stage_a["status"])
        self.assertEqual("fail", next(
            check["status"] for check in stage_a["checks"]
            if check["id"] == "auth.credentials"
        ))

        missing = self.real_doctor_report_fixture()
        missing["checks"].pop("sandbox.helpers")
        missing_evidence = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(missing), 0, True,
            )
        )
        self.assertEqual("UNCHECKABLE", missing_evidence["status"])

        inconsistent_exit = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            ),
            ("config", "runtime", "sandbox"),
        )
        self.assertEqual("UNCHECKABLE", inconsistent_exit["status"])

    def test_runtime_lanes_are_independent_and_probe_only_never_authorizes_live(self):
        profile = copy.deepcopy(self.profile)
        profile["scope"] = "exact-head-probe-only-sensor"
        profile["status"] = "probe-only-match"
        profile["live_run_allowed"] = False
        profile["auth"]["class"] = "unavailable"
        profile["evidence"]["lane_statuses"]["auth_status"] = "unavailable"
        report = self.real_doctor_report_fixture()
        report["checks"]["auth.credentials"]["status"] = "fail"
        report["overallStatus"] = "fail"
        profile["evidence"]["diagnostic_health"] = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                1, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            ),
            ("config", "runtime", "sandbox"),
        )
        self.adapter.validate_runtime_profile(profile, allow_fixture=True)
        self.assertEqual(
            "pass", profile["evidence"]["lane_statuses"]["provider_isolation_status"],
        )
        self.assertFalse(profile["live_run_allowed"])
        self.assert_contract_error(
            lambda: self.adapter.execute_slice(ROOT, copy.deepcopy(self.envelope), profile, "live"),
            "blocked",
        )

        mount_drift = copy.deepcopy(self.profile)
        mount_drift["status"] = "profile-drift"
        mount_drift["reason"] = "mount boundary drifted"
        mount_drift["live_run_allowed"] = False
        mount_drift["evidence"]["containment_provider"]["ssh_agent_forwarding"] = True
        mount_drift["evidence"]["containment_provider"]["host_sensitive_mounts_absent"] = False
        mount_drift["evidence"]["lane_statuses"]["mount_boundary_status"] = "fail"
        self.adapter.validate_runtime_profile(mount_drift, allow_fixture=True)
        self.assertEqual(
            "pass", mount_drift["evidence"]["lane_statuses"]["provider_isolation_status"],
        )
        self.assertEqual(
            "fail", mount_drift["evidence"]["lane_statuses"]["mount_boundary_status"],
        )

    def test_persisted_doctor_projection_cannot_forge_required_lane_success(self):
        profile = copy.deepcopy(self.profile)
        profile["scope"] = "exact-head-probe-only-sensor"
        profile["status"] = "probe-only-match"
        profile["live_run_allowed"] = False
        profile["auth"]["class"] = "unavailable"
        profile["evidence"]["lane_statuses"]["auth_status"] = "unavailable"
        report = self.real_doctor_report_fixture()
        report["checks"]["auth.credentials"]["status"] = "fail"
        report["overallStatus"] = "fail"
        diagnostic = self.adapter.doctor_diagnostic_health(
            self.adapter.ProcessResult(
                1, None, False, False, False,
                self.adapter.canonical_bytes(report), 0, True,
            ),
            ("config", "runtime", "sandbox"),
        )
        profile["evidence"]["diagnostic_health"] = diagnostic
        self.adapter.validate_runtime_profile(profile, allow_fixture=True)

        forged = copy.deepcopy(profile)
        for check in forged["evidence"]["diagnostic_health"]["checks"]:
            if check["category"] == "config":
                check["status"] = "fail"
        with self.assertRaisesRegex(self.adapter.ContractError, "diagnostic status"):
            self.adapter.validate_runtime_profile(forged, allow_fixture=True)

        missing = copy.deepcopy(profile)
        missing["evidence"]["diagnostic_health"]["checks"] = [
            check for check in missing["evidence"]["diagnostic_health"]["checks"]
            if check["category"] != "sandbox"
        ]
        with self.assertRaisesRegex(self.adapter.ContractError, "required category"):
            self.adapter.validate_runtime_profile(missing, allow_fixture=True)

        too_many = copy.deepcopy(profile)
        too_many["evidence"]["diagnostic_health"]["checks"] = [
            {"id": "ui.check-{:02d}".format(index), "category": "ui", "status": "ok"}
            for index in range(61)
        ] + diagnostic["checks"]
        too_many["evidence"]["diagnostic_health"]["checks"].sort(
            key=lambda item: (item["id"], item["category"], item["status"])
        )
        with self.assertRaisesRegex(self.adapter.ContractError, "safe checks"):
            self.adapter.validate_runtime_profile(too_many, allow_fixture=True)

        uppercase = copy.deepcopy(profile)
        uppercase["evidence"]["diagnostic_health"]["checks"][0]["id"] = "Auth.credentials"
        uppercase["evidence"]["diagnostic_health"]["checks"].sort(
            key=lambda item: (item["id"], item["category"], item["status"])
        )
        with self.assertRaisesRegex(self.adapter.ContractError, "safe check"):
            self.adapter.validate_runtime_profile(uppercase, allow_fixture=True)

    def test_lane_local_probe_exceptions_preserve_independent_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            work = root / "work"
            for path in (home, tmp, work):
                path.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            diagnostic = {
                "classification": "diagnostic-only", "status": "pass",
                "checks": [
                    {"id": "auth.credentials", "category": "auth", "status": "ok"},
                    {"id": "config.load", "category": "config", "status": "ok"},
                    {"id": "runtime.provenance", "category": "runtime", "status": "ok"},
                    {"id": "sandbox.helpers", "category": "sandbox", "status": "ok"},
                ],
                "codex_issued_effective_configuration_proof": False,
            }
            worker = {
                "status": "pass", "stage": "argv-policy", "reason_code": "none",
                "rules_bypass_absent": True, "dynamic_task_data_stdin_only": True,
            }
            with mock.patch.object(
                self.adapter, "materialize_reviewed_rules_profile",
                return_value=self.adapter.runtime_configuration_intent()["rules_profile_sha256"],
            ), mock.patch.object(
                self.adapter, "bounded_capture",
                return_value=self.adapter.ProcessResult(
                    0, None, False, False, False, b"{}\n", 0, True,
                ),
            ), mock.patch.object(
                self.adapter, "doctor_diagnostic_health", return_value=diagnostic,
            ), mock.patch.object(
                self.adapter, "exact_worker_argv_evidence", return_value=worker,
            ), mock.patch.object(
                self.adapter, "shell_environment_probe",
                side_effect=self.adapter.ContractError("private shell failure"),
            ), mock.patch.object(
                self.adapter, "network_sandbox_behavior_probe",
                side_effect=OSError("private network failure"),
            ), mock.patch.object(
                self.adapter, "process_cleanup_probe", return_value="pass",
            ):
                evidence = self.adapter.probe_runtime_evidence(
                    Path(sys.executable).resolve(), work, environment, ROOT,
                    prerequisite_evidence=self.passing_stage_a1_prerequisite(),
                )
        lanes = evidence["evidence"]["lane_statuses"]
        self.assertEqual("UNCHECKABLE", lanes["shell_environment_status"])
        self.assertEqual("UNCHECKABLE", lanes["codex_sandbox_network_status"])
        self.assertEqual("pass", lanes["process_cleanup_status"])
        self.assertEqual("pass", lanes["config_status"])

    def test_probe_orchestrator_failure_still_records_provider_and_mount_lanes(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        stable_version = b"codex-cli 0.150.1\n"

        def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
            del stdin_bytes, timeout
            payload = stable_version if argv[-1] == "--version" else stable_help
            return self.adapter.ProcessResult(
                0, None, False, False, False, payload, 0, True,
            )

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            for child in ("home", "tmp", "work", "bin"):
                (root / child).mkdir(mode=0o700)
            (root / "home/.codex").mkdir(mode=0o700)
            layout = self.adapter.ColimaRuntimeLayout(
                root, root / "home", root / "tmp", root / "work",
                Path(sys.executable), "6" * 64, "7" * 64,
            )
            provider_input = self.colima_provider_input()
            containment = self.passing_containment_evidence()
            uname = SimpleNamespace(
                sysname="Linux", machine="aarch64", release="6.12.0-t11",
            )
            with mock.patch.object(
                self.adapter, "prepare_colima_runtime_layout", return_value=layout,
            ), mock.patch.object(
                self.adapter, "bounded_capture", side_effect=capture,
            ), mock.patch.object(
                self.adapter, "probe_runtime_evidence",
                side_effect=self.adapter.ContractError("private probe failure"),
            ), mock.patch.object(
                self.adapter, "observe_colima_provider_evidence", return_value=containment,
            ), mock.patch.object(
                self.adapter, "auth_class", return_value="unavailable",
            ), mock.patch.object(
                self.adapter, "hash_regular_file", return_value="a" * 64,
            ), mock.patch.object(self.adapter.os, "uname", return_value=uname):
                observed = self.adapter.observe_runtime_profile(
                    ROOT, "gpt-5.6-sol", "high", provider_input, probe_only=True,
                )
        self.assertEqual("UNCHECKABLE", observed["status"])
        self.assertEqual(
            "pass", observed["evidence"]["lane_statuses"]["provider_isolation_status"],
        )
        self.assertEqual(
            "pass", observed["evidence"]["lane_statuses"]["mount_boundary_status"],
        )
        self.assertEqual(
            "UNCHECKABLE", observed["evidence"]["lane_statuses"]["config_status"],
        )

    def test_separated_runtime_probe_never_promotes_doctor_to_effective_config(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            work = root / "work"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            work.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmp)
            expected = self.adapter.reviewed_runtime_configuration(environment)
            report = self.real_doctor_report_fixture("fail")

            def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15):
                del stdin_bytes, timeout
                calls.append(list(argv))
                if "doctor" in argv:
                    return self.adapter.ProcessResult(1, None, False, False, False, self.adapter.canonical_bytes(report), 0, True)
                if str(Path("/usr/bin/env")) in argv:
                    observed = dict(expected["shell_environment_policy.set"])
                    observed["CODEX_SANDBOX_NETWORK_DISABLED"] = "1"
                    payload = b"\0".join(
                        (name + "=" + value).encode("utf-8")
                        for name, value in sorted(observed.items())
                    ) + b"\0"
                    return self.adapter.ProcessResult(0, None, False, False, False, payload, 0, True)
                return self.adapter.ProcessResult(0, None, False, False, False, b"", 0, True)

            with mock.patch.object(self.adapter, "bounded_capture", side_effect=capture):
                probe = self.adapter.probe_runtime_evidence(
                    Path(sys.executable).resolve(), work, environment, ROOT,
                    prerequisite_evidence=self.passing_stage_a1_prerequisite(),
                )
        self.assertEqual("pass", probe["documented_config_keys_probe"])
        self.assertEqual("pass", probe["shell_environment_probe"])
        self.assertEqual("fail", probe["evidence"]["diagnostic_health"]["status"])
        self.assertFalse(probe["evidence"]["configuration_intent"]["effective_configuration_proven"])
        self.assertEqual("pass", probe["evidence"]["exact_worker_argv"]["status"])
        self.assertEqual("pass", probe["evidence"]["network_sandbox_behavior"]["status"])
        rendered = "\n".join("\n".join(call) for call in calls)
        for key, value in self.adapter.REQUIRED_OVERRIDES.items():
            self.assertIn("{}={}".format(key, self.adapter.toml_literal(value)), rendered)
        self.assertNotIn("--ignore-rules", rendered)
        self.assertNotIn("--dangerously-bypass-", rendered)

    def test_live_argv_contains_exact_isolation_and_no_dynamic_task_data(self):
        argv = self.adapter.build_live_argv(Path("/reviewed/codex"), Path("/isolated-target"), ROOT, self.envelope)
        self.assertEqual("-", argv[-1])
        for required in ("exec", "--json", "--ephemeral", "--strict-config", "--ignore-user-config", "workspace-write"):
            self.assertIn(required, argv)
        rendered = "\n".join(argv)
        self.assertNotIn(self.envelope["attempt_id"], rendered)
        self.assertNotIn("Issue #23", rendered)
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn("--ignore-rules", argv)
        self.assertFalse(any(value.startswith("--dangerously-bypass-") for value in argv))
        self.adapter.validate_runtime_argv_policy(argv, require_memory_overrides=True)
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

    def test_linux_stat_parser_accepts_zero_start_tick_and_unrepresented_group(self):
        valid = b"4321 (worker) S 0 0 4321 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0 98765\n"
        self.assertEqual(
            (4321, 0, 0, "linux:98765"),
            self.adapter.parse_linux_process_stat(valid),
        )
        zero_start_tick = valid.replace(b" 98765\n", b" 0\n")
        self.assertEqual(
            (4321, 0, 0, "linux:0"),
            self.adapter.parse_linux_process_stat(zero_start_tick),
        )
        negative_group = valid.replace(b") S 0 0 4321", b") S 0 -1 4321")
        self.assert_contract_error(
            lambda: self.adapter.parse_linux_process_stat(negative_group),
            "invalid data",
        )
        negative_start_tick = valid.replace(b" 98765\n", b" -1\n")
        self.assert_contract_error(
            lambda: self.adapter.parse_linux_process_stat(negative_start_tick),
            "invalid data",
        )
        self.assert_contract_error(
            lambda: self.adapter.parse_linux_process_stat(b"4321 malformed\n"),
            "malformed data",
        )

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

    def test_checker_pins_fixed_revalidated_provider_git_call_graph(self):
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        errors = []
        self.checker.validate_provider_git_source(source, str(ADAPTER_PATH), errors)
        self.assertEqual([], errors)
        mutations = (
            source.replace(
                "head_bytes = run_approved_provider_git(",
                "head_bytes = run_git(", 1,
            ),
            source.replace(
                "git, _digest = approved_provider_git_binding()",
                "git = resolve_executable_from_path('git', env)", 1,
            ),
            source.replace(
                "os.stat(raw, follow_symlinks=False)",
                "os.stat(raw)", 1,
            ),
        )
        for candidate in mutations:
            self.assertNotEqual(source, candidate)
            errors = []
            self.checker.validate_provider_git_source(
                candidate, str(ADAPTER_PATH), errors,
            )
            with self.subTest(errors=errors):
                self.assertTrue(errors)

    def test_runtime_profile_schema_pins_stage_a1_fail_closed_semantics(self):
        original = json.loads((
            ROOT / "docs/agreements/runtime/runtime-profile.v1.schema.json"
        ).read_text(encoding="utf-8"))

        def prerequisite(schema):
            return schema["properties"]["evidence"]["properties"][
                "bubblewrap_prerequisite"
            ]

        def pass_then(schema):
            return prerequisite(schema)["allOf"][0]["then"]["properties"]

        def containment(schema):
            return schema["properties"]["evidence"]["properties"][
                "containment_provider"
            ]

        mutations = (
            lambda schema: prerequisite(schema)["properties"]["controller"][
                "properties"
            ]["argv_sha256"].__setitem__("const", "0" * 64),
            lambda schema: prerequisite(schema)["properties"]["smoke"][
                "properties"
            ]["argv_sha256"].__setitem__("const", "0" * 64),
            lambda schema: pass_then(schema)["guest"]["properties"].pop("kernel"),
            lambda schema: pass_then(schema)["bubblewrap"]["properties"][
                "help_sha256"
            ].pop("not"),
            lambda schema: prerequisite(schema)["required"].remove("git"),
            lambda schema: prerequisite(schema)["properties"].pop("git"),
            lambda schema: pass_then(schema)["git"]["properties"][
                "package_version"
            ].__setitem__("const", "1:2.43.0-1ubuntu7.2"),
            lambda schema: pass_then(schema)["git"]["properties"][
                "binary_sha256"
            ].__setitem__("const", "0" * 64),
            lambda schema: pass_then(schema)["git"]["properties"][
                "version_output"
            ].__setitem__("const", "git version 2.42.0"),
            lambda schema: containment(schema)["required"].remove(
                "repository_git_bootstrap"
            ),
            lambda schema: containment(schema)["properties"].pop(
                "repository_git_bootstrap_runtime_match"
            ),
            lambda schema: containment(schema)["properties"].pop(
                "repository_git_clone_contract_sha256"
            ),
            lambda schema: containment(schema)["properties"][
                "repository_git_bootstrap"
            ]["oneOf"][0]["const"].__setitem__(
                "package_version", "1:2.43.0-1ubuntu7.2",
            ),
            lambda schema: containment(schema)["properties"][
                "repository_git_bootstrap"
            ]["oneOf"][0]["const"].__setitem__(
                "binary_sha256", "0" * 64,
            ),
            lambda schema: containment(schema)["properties"][
                "repository_git_bootstrap"
            ]["oneOf"][0]["const"].__setitem__(
                "controller_argv_sha256", "0" * 64,
            ),
            lambda schema: containment(schema)["properties"][
                "repository_git_bootstrap"
            ]["oneOf"][0]["const"].__setitem__(
                "preclone_qualification_argv_sha256", "0" * 64,
            ),
            lambda schema: prerequisite(schema)["properties"]["smoke"][
                "allOf"
            ].pop(),
            lambda schema: prerequisite(schema)["allOf"].pop(),
            lambda schema: schema["allOf"][1]["then"]["properties"][
                "evidence"
            ]["properties"].pop("diagnostic_health"),
        )
        for mutation in mutations:
            candidate = copy.deepcopy(original)
            mutation(candidate)
            errors = []
            self.checker.validate_runtime_profile_schema(candidate, errors)
            with self.subTest(errors=errors):
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
