import copy
import contextlib
import datetime
import errno
import hashlib
import importlib.util
import io
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

import jsonschema


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

    def assert_draft_2020_valid(self, schema, instance):
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertTrue(jsonschema.Draft202012Validator(schema).is_valid(instance))

    def assert_draft_2020_invalid(self, schema, instance):
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(instance))

    def t12_live_profile(self):
        profile = copy.deepcopy(self.profile)
        provider = profile["evidence"]["containment_provider"]
        provider["repository_git_clone_contract_sha256"] = (
            self.adapter.stage_a1_git_clone_contract_sha256(
                provider["public_head"], provider["public_tree"],
                self.adapter.T12_PUBLIC_BRANCH,
            )
        )
        return profile

    def test_t12_activation_identity_is_exact_and_pr_agnostic(self):
        self.assertEqual(25, self.adapter.TASK_ISSUE)
        self.assertEqual(
            "codex/phase-2-live-codex-runtime",
            self.adapter.T12_PUBLIC_BRANCH,
        )
        self.assertEqual(
            "codex/phase-2-minimal-execution-slice",
            self.adapter.T11_ACCEPTED_PUBLIC_BRANCH,
        )
        self.assertFalse(hasattr(self.adapter, "T11_PUBLIC_BRANCH"))
        self.assertEqual(
            {
                "repository": "mochan-tk/agentic-dev-kit-for-codex",
                "issue": 25,
                "url": (
                    "https://github.com/mochan-tk/"
                    "agentic-dev-kit-for-codex/issues/25"
                ),
            },
            self.envelope["task"],
        )
        schema = json.loads(
            (
                ROOT
                / "docs/agreements/runtime/"
                "task-execution-envelope.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(25, schema["properties"]["task"]["properties"]["issue"]["const"])
        self.assertEqual(
            self.envelope["task"]["url"],
            schema["properties"]["task"]["properties"]["url"]["const"],
        )
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("PULL_REQUEST", source)

    def test_t12_stage_a_and_stage_b_profile_semantics_are_exact(self):
        stage_a = self.t12_live_profile()
        stage_a["scope"] = "exact-head-probe-only-sensor"
        stage_a["status"] = "probe-only-match"
        stage_a["reason"] = "exact unauthenticated Stage A probes match"
        stage_a["auth"]["class"] = "unavailable"
        stage_a["evidence"]["lane_statuses"]["auth_status"] = "unavailable"
        stage_a["live_run_allowed"] = False
        self.adapter.validate_runtime_profile(stage_a, allow_fixture=True)
        self.assert_contract_error(
            lambda: self.adapter.execute_slice(
                ROOT, copy.deepcopy(self.envelope), stage_a, "live"
            ),
            "blocked",
        )

        stage_b = self.t12_live_profile()
        stage_b["scope"] = "exact-head-live-sensor"
        stage_b["status"] = "match"
        stage_b["auth"]["class"] = "signed-in-client"
        stage_b["evidence"]["lane_statuses"]["auth_status"] = (
            "signed-in-client"
        )
        stage_b["live_run_allowed"] = True
        self.adapter.validate_runtime_profile(stage_b, allow_fixture=True)

    def test_execution_result_requires_exactly_one_logical_invocation(self):
        verifier = {
            "schema": "t11-verifier-result/v1",
            "attempt_id": self.envelope["attempt_id"],
            "status": "pass",
            "fresh_process": True,
            "read_only": True,
            "checks": self.adapter.VERIFIER_CHECKS,
        }
        result = json.loads(
            (
                ROOT / "tests/runtime/fixtures/execution-result-valid.v1.json"
            ).read_text(encoding="utf-8")
        )
        for count in (0, 2):
            candidate = copy.deepcopy(result)
            candidate["worker"]["logical_invocations"] = count
            with self.subTest(count=count):
                self.assert_contract_error(
                    lambda value=candidate: self.adapter.validate_execution_result(
                        value, self.envelope, self.profile, verifier
                    ),
                    "exactly one logical invocation",
                )

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
                "shell_environment_behavior": self.adapter.shell_environment_evidence(
                    "pass", "none"
                ),
                "network_sandbox_behavior": self.passing_network_evidence(),
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

    def passing_network_evidence(self):
        return self.adapter.network_sandbox_evidence(
            "pass", "none",
            control_accepted=True,
            control_closed=True,
            parent_namespace_sha256="1" * 64,
            sandbox_namespace_sha256="2" * 64,
            marker_status="exact-1",
            connect_status="denied",
            connect_errno="EPERM",
            process_cleanup_status="pass",
            process_reaped=True,
        )

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
            "codex/phase-2-live-codex-runtime", contract["branch"],
        )
        self.assertEqual("0077", contract["process_umask"])
        self.assertEqual(
            [
                "/usr/bin/python3", "-I", "-c",
                self.adapter.STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT,
            ],
            contract["umask_wrapper_argv"],
        )
        self.assertEqual("replace", contract["environment"]["policy"])
        self.assertEqual(
            self.adapter.STAGE_A1_GIT_FIXED_ENVIRONMENT,
            contract["environment"]["fixed"],
        )
        self.assertEqual(
            {
                "wrapper_input_HOME": (
                    "private-vm-absolute-empty-current-uid-mode-0700-no-follow"
                ),
                "git_child_HOME": "inherited-private-home-directory-descriptor",
            },
            contract["environment"]["dynamic"],
        )
        self.assertEqual([], contract["environment"]["inherited_keys"])
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
            self.assertEqual(contract["umask_wrapper_argv"], argv[:4])
            self.assertEqual("/usr/bin/git", argv[4])
            self.assertIn("--no-replace-objects", argv)
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertIn("credential.helper=", argv)
            self.assertNotIn("/bin/sh", argv)
            self.assertNotIn("/bin/bash", argv)
        digest = self.adapter.stage_a1_git_clone_contract_sha256(head, tree)
        self.assertEqual(
            self.adapter.sha256_bytes(self.adapter.canonical_bytes(contract)),
            digest,
        )
        self.assertEqual(
            "af134538a459119e618854b6455199ac92ee0b7abd4546fabc1c7330d4eb51d8",
            digest,
        )
        historical = self.adapter.stage_a1_git_clone_contract(
            head, tree, self.adapter.T11_ACCEPTED_PUBLIC_BRANCH,
        )
        self.assertEqual(
            "codex/phase-2-minimal-execution-slice", historical["branch"],
        )
        self.assertEqual(
            "80175bb5a8b09587866e54b425361eaa796213e770e40b3b866d389796da12b7",
            self.adapter.stage_a1_git_clone_contract_sha256(
                head, tree, self.adapter.T11_ACCEPTED_PUBLIC_BRANCH,
            ),
        )
        self.assert_contract_error(
            lambda: self.adapter.stage_a1_git_clone_contract(
                head, tree, "codex/unreviewed-branch",
            ),
            "branch",
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

    def test_stage_a1_private_umask_wrapper_is_shell_free_and_effective(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            target = Path(temporary) / "target"
            role = source / self.adapter.STATIC_ROLE_PATH
            role.parent.mkdir(parents=True)
            role.write_bytes((ROOT / self.adapter.STATIC_ROLE_PATH).read_bytes())
            envelope_relative = "tests/runtime/fixtures/envelope-valid.v1.json"
            envelope = source / envelope_relative
            envelope.parent.mkdir(parents=True)
            envelope.write_bytes((ROOT / envelope_relative).read_bytes())
            executable = source / "tool.sh"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            os.chmod(executable, 0o755)
            for argv in (
                ["/usr/bin/git", "init", "--quiet", str(source)],
                [
                    "/usr/bin/git", "-C", str(source), "checkout", "--quiet",
                    "-b", self.adapter.T12_PUBLIC_BRANCH,
                ],
                ["/usr/bin/git", "-C", str(source), "add", "."],
                [
                    "/usr/bin/git", "-C", str(source),
                    "-c", "user.name=T11 Test", "-c", "user.email=t11@example.invalid",
                    "commit", "--quiet", "-m", "fixture",
                ],
            ):
                subprocess.run(
                    argv, cwd=ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=15, check=True,
                )
            head = subprocess.run(
                ["/usr/bin/git", "-C", str(source), "rev-parse", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, check=True,
            ).stdout.strip().decode("ascii")
            tree = subprocess.run(
                ["/usr/bin/git", "-C", str(source), "rev-parse", "HEAD^{tree}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, check=True,
            ).stdout.strip().decode("ascii")
            base_python = (
                Path(sys.base_prefix) / "bin"
                / ("python" + str(sys.version_info.major) + "." + str(sys.version_info.minor))
            )
            self.assertTrue(base_python.is_file())
            wrapper = [
                str(base_python), "-I", "-c",
                self.adapter.STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT,
            ]
            private_home = Path(temporary) / "private-home"
            private_home.mkdir(mode=0o700)
            git_environment = dict(self.adapter.STAGE_A1_GIT_FIXED_ENVIRONMENT)
            git_environment["HOME"] = str(private_home)
            prefix = [
                "/usr/bin/git", "--no-replace-objects",
                "-c", "core.hooksPath=/dev/null",
                "-c", "credential.helper=",
            ]
            clone = subprocess.run(
                [
                    *wrapper, *prefix, "clone", "--quiet", "--no-checkout",
                    "--single-branch", "--branch", self.adapter.T12_PUBLIC_BRANCH,
                    str(source), str(target),
                ],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, env=git_environment,
            )
            self.assertEqual(0, clone.returncode, clone.stderr)
            checkout = subprocess.run(
                [*wrapper, *prefix, "-C", str(target), "checkout", "--detach", head],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, env=git_environment,
            )
            self.assertEqual(0, checkout.returncode, checkout.stderr)
            checked_out_role = target / self.adapter.STATIC_ROLE_PATH
            checked_out_envelope = target / envelope_relative
            self.assertEqual(0o600, stat.S_IMODE(checked_out_role.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(checked_out_envelope.stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE((target / "tool.sh").stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE(checked_out_role.parent.stat().st_mode))
            observed = []
            for suffix in (
                ["rev-parse", "--verify", "HEAD"],
                ["rev-parse", "--verify", "HEAD^{tree}"],
                ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            ):
                result = subprocess.run(
                    [*wrapper, *prefix, "-C", str(target), *suffix],
                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=15, env=git_environment,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                observed.append(result.stdout)
            self.assertEqual(head.encode("ascii"), observed[0].strip())
            self.assertEqual(tree.encode("ascii"), observed[1].strip())
            self.assertEqual(b"", observed[2])
            self.assertEqual(
                self.adapter.extract_static_role(ROOT),
                self.adapter.extract_static_role(target),
            )
            self.adapter.extract_static_role(
                target, require_private_projection=True,
            )
            self.assertEqual(
                self.envelope,
                self.adapter.load_repository_json(target, envelope_relative),
            )
            self.assertEqual(
                self.envelope,
                self.adapter.load_repository_json(
                    target, envelope_relative,
                    require_private_projection=True,
                ),
            )
            for accepted_mode in (0o600, 0o644):
                os.chmod(checked_out_envelope, accepted_mode)
                self.assertEqual(
                    self.envelope,
                    self.adapter.load_repository_json(target, envelope_relative),
                )
                if accepted_mode == 0o600:
                    self.adapter.load_repository_json(
                        target, envelope_relative,
                        require_private_projection=True,
                    )
                else:
                    self.assert_contract_error(
                        lambda: self.adapter.load_repository_json(
                            target, envelope_relative,
                            require_private_projection=True,
                        ),
                        "mode",
                    )
            for rejected_mode in (0o660, 0o664, 0o620, 0o602):
                os.chmod(checked_out_envelope, rejected_mode)
                self.assert_contract_error(
                    lambda: self.adapter.load_repository_json(
                        target, envelope_relative,
                    ),
                    "non-writable",
                )
            os.chmod(checked_out_envelope, 0o600)
            envelope_alias = target / "envelope-alias.json"
            os.link(checked_out_envelope, envelope_alias)
            self.assert_contract_error(
                lambda: self.adapter.load_repository_json(
                    target, envelope_relative,
                ),
                "single-link",
            )
            envelope_alias.unlink()
            checker_errors = []
            self.assertEqual(
                checked_out_role.read_bytes(),
                self.checker.read_regular(
                    target, self.adapter.STATIC_ROLE_PATH, checker_errors,
                ),
            )
            self.assertEqual([], checker_errors)
            for accepted_mode in (0o600, 0o644):
                os.chmod(checked_out_role, accepted_mode)
                self.adapter.extract_static_role(target)
                if accepted_mode == 0o600:
                    self.adapter.extract_static_role(
                        target, require_private_projection=True,
                    )
                else:
                    self.assert_contract_error(
                        lambda: self.adapter.extract_static_role(
                            target, require_private_projection=True,
                        ),
                        "mode",
                    )
                checker_errors = []
                self.assertTrue(self.checker.read_regular(
                    target, self.adapter.STATIC_ROLE_PATH, checker_errors,
                ))
                self.assertEqual([], checker_errors)
            for rejected_mode in (0o660, 0o664, 0o620, 0o602):
                os.chmod(checked_out_role, rejected_mode)
                self.assert_contract_error(
                    lambda: self.adapter.extract_static_role(target), "mode",
                )
                checker_errors = []
                self.assertEqual(
                    b"", self.checker.read_regular(
                        target, self.adapter.STATIC_ROLE_PATH, checker_errors,
                    ),
                )
                self.assertTrue(checker_errors)
            os.chmod(checked_out_role, 0o600)
            role_alias = target / "role-alias.toml"
            os.link(checked_out_role, role_alias)
            self.assert_contract_error(
                lambda: self.adapter.extract_static_role(target),
                "single-link",
            )
            checker_errors = []
            self.assertEqual(
                b"", self.checker.read_regular(
                    target, self.adapter.STATIC_ROLE_PATH, checker_errors,
                ),
            )
            self.assertTrue(checker_errors)
            role_alias.unlink()
            checked_out_role.unlink()
            checked_out_role.symlink_to(ROOT / self.adapter.STATIC_ROLE_PATH)
            self.assert_contract_error(
                lambda: self.adapter.extract_static_role(target), "regular",
            )
            checker_errors = []
            self.assertEqual(
                b"", self.checker.read_regular(
                    target, self.adapter.STATIC_ROLE_PATH, checker_errors,
                ),
            )
            self.assertTrue(checker_errors)
            wrong_target = subprocess.run(
                [
                    str(base_python), "-I", "-c",
                    self.adapter.STAGE_A1_PRIVATE_UMASK_EXEC_SCRIPT,
                    str(base_python), "-c", "pass",
                ],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, env=git_environment,
            )
            self.assertEqual(64, wrong_target.returncode)
            self.assertEqual(b"", wrong_target.stdout)
            self.assertEqual(b"", wrong_target.stderr)
            for poisoned_name in (
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
                "GIT_CONFIG_GLOBAL", "GIT_EXEC_PATH",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_TEMPLATE_DIR", "GIT_ASKPASS", "SSH_AUTH_SOCK",
            ):
                poisoned = dict(git_environment)
                poisoned[poisoned_name] = "unexpected"
                rejected = subprocess.run(
                    [*wrapper, "/usr/bin/git", "--version"],
                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=15, env=poisoned,
                )
                self.assertEqual(64, rejected.returncode, poisoned_name)
                self.assertEqual(b"", rejected.stdout)
                self.assertEqual(b"", rejected.stderr)
            missing_environment_cases = (
                {key: value for key, value in git_environment.items() if key != "HOME"},
                {
                    key: value for key, value in git_environment.items()
                    if key != "GIT_CONFIG_NOSYSTEM"
                },
            )
            for incomplete in missing_environment_cases:
                rejected = subprocess.run(
                    [*wrapper, "/usr/bin/git", "--version"],
                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=15, env=incomplete,
                )
                self.assertEqual(64, rejected.returncode)
                self.assertEqual(b"", rejected.stdout)
                self.assertEqual(b"", rejected.stderr)
            def assert_home_rejected(home_value):
                invalid = dict(git_environment)
                invalid["HOME"] = str(home_value)
                rejected = subprocess.run(
                    [*wrapper, "/usr/bin/git", "--version"],
                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=15, env=invalid,
                )
                self.assertEqual(64, rejected.returncode)
                self.assertEqual(b"", rejected.stdout)
                self.assertEqual(b"", rejected.stderr)

            assert_home_rejected("relative-home")
            assert_home_rejected("/")
            linked_home = Path(temporary) / "linked-home"
            linked_home.symlink_to(private_home, target_is_directory=True)
            assert_home_rejected(linked_home)
            os.chmod(private_home, 0o755)
            assert_home_rejected(private_home)
            os.chmod(private_home, 0o700)
            for name in (".gitconfig", ".netrc"):
                injected = private_home / name
                injected.write_bytes(b"unreviewed\n")
                assert_home_rejected(private_home)
                injected.unlink()

    def test_governed_input_mode_and_link_transitions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "governed.json"
            target.write_bytes(b'{"schema":"fixture"}\n')
            os.chmod(target, 0o600)
            real_open = self.adapter.os.open

            def writable_before_open(path, flags, *args, **kwargs):
                os.chmod(target, 0o664)
                return real_open(path, flags, *args, **kwargs)

            with mock.patch.object(
                self.adapter, "require_runtime_fs_capabilities",
            ), mock.patch.object(
                self.adapter.os, "open", side_effect=writable_before_open,
            ):
                self.assert_contract_error(
                    lambda: self.adapter.read_bounded_regular(
                        target, 1024, allowed_modes=(0o600, 0o644),
                        require_single_link=True,
                    ),
                    "mode",
                )

            os.chmod(target, 0o600)
            alias = Path(temporary) / "governed-alias.json"
            real_read = self.adapter.os.read
            linked = False

            def link_during_read(descriptor, size):
                nonlocal linked
                if not linked:
                    os.link(target, alias)
                    linked = True
                return real_read(descriptor, size)

            with mock.patch.object(
                self.adapter, "require_runtime_fs_capabilities",
            ), mock.patch.object(
                self.adapter.os, "read", side_effect=link_during_read,
            ):
                self.assert_contract_error(
                    lambda: self.adapter.read_bounded_regular(
                        target, 1024, allowed_modes=(0o600, 0o644),
                        require_single_link=True,
                    ),
                    "changed",
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
                    b"bwrap (enforce)\nunpriv_bwrap (enforce)\n", 0, True,
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

        stacked_only = self.adapter._stage_a1_profile_load_status(
            self.adapter.ProcessResult(
                0, None, False, False, False,
                b"bwrap (enforce)\nbwrap//&unpriv_bwrap (enforce)\n",
                0, True,
            )
        )
        self.assertEqual("not-loaded", stacked_only)
        self.assertEqual(
            "UNCHECKABLE",
            self.adapter._stage_a1_profile_load_status(
                self.adapter.ProcessResult(
                    0, None, False, False, False,
                    b"bwrap (enforce)\nunpriv_bwrap (enforce)\n", 1, True,
                )
            ),
        )
        for missing in (b"bwrap (enforce)\n", b"unpriv_bwrap (enforce)\n"):
            with self.subTest(missing_source_profile=missing):
                self.assertEqual(
                    "not-loaded",
                    self.adapter._stage_a1_profile_load_status(
                        self.adapter.ProcessResult(
                            0, None, False, False, False,
                            missing, 0, True,
                        )
                    ),
                )
        self.assertEqual(
            "not-loaded",
            self.adapter._stage_a1_profile_load_status(
                self.adapter.ProcessResult(
                    0, None, False, False, False,
                    b"bwrap (complain)\nunpriv_bwrap (complain)\n", 0, True,
                )
            ),
        )
        uncheckable_profile_results = (
            self.adapter.ProcessResult(
                1, None, False, False, False,
                b"bwrap (enforce)\nunpriv_bwrap (enforce)\n", 0, True,
            ),
            self.adapter.ProcessResult(
                None, None, True, False, False, b"", 0, True,
            ),
            self.adapter.ProcessResult(
                0, None, False, True, False, b"", 0, True,
            ),
            self.adapter.ProcessResult(
                0, None, False, False, True, b"", 0, True,
            ),
            self.adapter.ProcessResult(
                0, None, False, False, False, b"\xff", 0, True,
            ),
            self.adapter.ProcessResult(
                0, None, False, False, False,
                b"bwrap (enforce)\nunpriv_bwrap (enforce)\n", 0, False,
            ),
        )
        for unsafe_result in uncheckable_profile_results:
            with self.subTest(unsafe_profile_result=unsafe_result):
                self.assertEqual(
                    "UNCHECKABLE",
                    self.adapter._stage_a1_profile_load_status(unsafe_result),
                )

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
                self.adapter, "shell_environment_probe",
                return_value=self.adapter.shell_environment_evidence("pass", "none"),
            ) as shell_probe, mock.patch.object(
                self.adapter, "network_sandbox_behavior_probe",
                return_value=self.passing_network_evidence(),
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
        valid = self.t12_live_profile()
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
            profile = self.t12_live_profile()
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

    def test_stage_a2_remains_non_success_with_no_real_worker_or_receipt_apply(self):
        contract = json.loads(
            (ROOT / ".github/governance/ledger-contracts.v1.json").read_text(
                encoding="utf-8"
            )
        )
        stage_a2 = contract["runtime_frontier"]["t11_history"]["stage_a2"]
        self.assertEqual("bounded-non-success", stage_a2["classification"])
        self.assertEqual("UNCHECKABLE", stage_a2["aggregate_status"])
        self.assertEqual("fail", stage_a2["shell_environment_status"])
        self.assertEqual("process-nonzero", stage_a2["shell_environment_reason_code"])
        self.assertEqual(
            "UNCHECKABLE", stage_a2["codex_sandbox_network_status"]
        )
        self.assertEqual(
            "process-nonzero", stage_a2["codex_sandbox_network_reason_code"]
        )
        self.assertEqual("unavailable", stage_a2["auth_status"])
        self.assertIs(stage_a2["device_auth_performed"], False)
        self.assertEqual(
            0, stage_a2["logical_codex_exec_worker_process_invocation_count"],
        )
        self.assertEqual(0, stage_a2["runtime_receipt_dry_run_count"])
        self.assertEqual(0, stage_a2["runtime_receipt_apply_count"])

    def test_runtime_checker_rejects_stage_a2_success_or_live_receipt_claims(self):
        contract_path = ".github/governance/ledger-contracts.v1.json"
        original_read = self.checker.read_regular
        original_contract = json.loads(
            (ROOT / contract_path).read_text(encoding="utf-8")
        )
        mutations = (
            lambda stage: stage.__setitem__("classification", "pass"),
            lambda stage: stage.__setitem__("aggregate_status", "match"),
            lambda stage: stage.__setitem__("shell_environment_status", "pass"),
            lambda stage: stage.__setitem__(
                "logical_codex_exec_worker_process_invocation_count", 1
            ),
            lambda stage: stage.__setitem__("runtime_receipt_apply_count", 1),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(original_contract)
                mutation(candidate["runtime_frontier"]["t11_history"]["stage_a2"])
                encoded = (
                    json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")

                def altered_read(root, relative, errors):
                    if relative == contract_path:
                        return encoded
                    return original_read(root, relative, errors)

                with mock.patch.object(
                    self.checker, "read_regular", side_effect=altered_read
                ):
                    errors = self.checker.validate_repository(ROOT)
                self.assertTrue(
                    errors,
                    "runtime checker accepted a forbidden Stage A.2/live claim",
                )

    def test_runtime_checker_binds_canonical_scenarios_and_release_sentinels(self):
        originals = {
            relative: json.loads((ROOT / relative).read_text(encoding="utf-8"))
            for relative in (
                "tests/conformance/coverage.json",
                "tests/conformance/manifest.json",
                "tests/conformance/results.json",
            )
        }
        original_read = self.checker.read_regular
        cases = (
            (
                "scenario passed",
                "tests/conformance/coverage.json",
                lambda value: value["entries"][0].__setitem__(
                    "verification_state", "pass"
                ),
            ),
            (
                "scenario missing",
                "tests/conformance/coverage.json",
                lambda value: value["entries"].pop(),
            ),
            (
                "scenario duplicate",
                "tests/conformance/coverage.json",
                lambda value: value["entries"][1].__setitem__(
                    "scenario", value["entries"][0]["scenario"]
                ),
            ),
            (
                "manifest scenario state",
                "tests/conformance/manifest.json",
                lambda value: value["scenario_catalog"].__setitem__(
                    "verification_state", "pass"
                ),
            ),
            (
                "manifest result",
                "tests/conformance/manifest.json",
                lambda value: value.__setitem__(
                    "results", [{"scenario": "C-001", "result": "pass"}]
                ),
            ),
            (
                "manifest release blocker",
                "tests/conformance/manifest.json",
                lambda value: value.__setitem__("release_blocked", False),
            ),
            (
                "release result",
                "tests/conformance/results.json",
                lambda value: value.update(
                    {
                        "result_count": 1,
                        "results": [{"scenario": "C-001", "result": "pass"}],
                    }
                ),
            ),
            (
                "results release blocker",
                "tests/conformance/results.json",
                lambda value: value.__setitem__("release_blocked", False),
            ),
        )
        for label, relative, mutation in cases:
            with self.subTest(label=label):
                candidate = copy.deepcopy(originals[relative])
                mutation(candidate)
                encoded = (
                    json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")

                def altered_read(root, observed, errors, max_bytes=self.checker.MAX_FILE_BYTES):
                    if observed == relative:
                        return encoded
                    return original_read(root, observed, errors, max_bytes)

                with mock.patch.object(
                    self.checker, "read_regular", side_effect=altered_read
                ):
                    errors = self.checker.validate_repository(ROOT)
                self.assertTrue(
                    errors,
                    "runtime checker accepted canonical release-state drift",
                )

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
            profile = self.t12_live_profile()
            profile["scope"] = "exact-head-live-sensor"
            profile["status"] = state
            profile["live_run_allowed"] = False
            if state != "unsupported-client":
                profile["client"]["release_class"] = "stable"
            profile["capabilities"]["documented_config_keys_probe"] = "UNCHECKABLE"
            profile["capabilities"]["shell_environment_probe"] = "UNCHECKABLE"
            profile["evidence"]["shell_environment_behavior"] = (
                self.adapter.shell_environment_evidence(
                    "UNCHECKABLE", "observation-uncheckable"
                )
            )
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
                if network_status == "fail":
                    probe["evidence"]["network_sandbox_behavior"] = (
                        self.adapter.network_sandbox_evidence(
                            "fail", "network-marker-missing",
                            control_accepted=True,
                            control_closed=True,
                            parent_namespace_sha256="1" * 64,
                            sandbox_namespace_sha256="2" * 64,
                            marker_status="missing",
                            connect_status="denied",
                            connect_errno="EPERM",
                            process_cleanup_status="pass",
                            process_reaped=True,
                        )
                    )
                probe["evidence"]["lane_statuses"]["codex_sandbox_network_status"] = network_status
                with self.subTest(network_status=network_status), \
                     mock.patch.object(self.adapter, "prepare_colima_runtime_layout", return_value=layout), \
                     mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
                     mock.patch.object(self.adapter, "observe_stage_a1_prerequisite", return_value=self.passing_stage_a1_prerequisite()), \
                     mock.patch.object(
                         self.adapter, "probe_runtime_evidence", return_value=probe,
                     ) as probe_sensor, \
                     mock.patch.object(self.adapter, "observe_colima_provider_evidence", return_value=containment), \
                     mock.patch.object(self.adapter, "auth_class", return_value="unavailable"), \
                     mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64), \
                     mock.patch.object(self.adapter.os, "uname", return_value=uname):
                    observed = self.adapter.observe_runtime_profile(
                        ROOT, "gpt-5.6-sol", "high", provider_input,
                        probe_only=True,
                    )
                self.assertTrue(
                    probe_sensor.call_args.kwargs["require_private_projection"],
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

    def test_official_0150_dispatch_rejects_strict_only_on_sandbox(self):
        # Static source regression, not execution/compatibility evidence:
        # 90854393966b21e9ebfd21b122334eb09a20c93d cli/src/main.rs
        # rejects --strict-config for Sandbox before dispatch (2467, 2490).
        environment = {name: "reviewed" for name in self.adapter.SHELL_ENVIRONMENT_NAMES}
        sandbox = self.adapter.sandbox_probe_argv(
            Path("/reviewed/codex"), environment, ["/usr/bin/env", "-0"],
            Path("/reviewed/root"),
        )
        doctor = self.adapter.runtime_configuration_argv(
            Path("/reviewed/codex"), environment,
        ) + ["doctor", "--json"]
        self.assertNotIn("--strict-config", sandbox)
        self.assertEqual(1, doctor.count("--strict-config"))
        self.assertEqual(
            [item for item in doctor[:-2] if item != "--strict-config"],
            sandbox[:sandbox.index("sandbox")],
        )
        live = self.adapter.build_live_argv(
            Path("/reviewed/codex"), Path("/reviewed/root"), ROOT, self.envelope,
        )
        self.assertEqual(1, live.count("--strict-config"))

        self.assert_contract_error(lambda: self.adapter.validate_sandbox_probe_argv(
            sandbox[:1] + ["--strict-config"] + sandbox[1:],
        ))
        self.assert_contract_error(lambda: self.adapter.runtime_configuration_argv(
            Path("/reviewed/codex"), environment, surface="unreviewed",
        ))

    def test_sandbox_launch_diagnostics_closed_numeric_and_reason_projection(self):
        base = self.adapter.ProcessResult(0, None, False, False, False, b"", 0, True)
        rejection = self.adapter.STRICT_SANDBOX_REJECTION
        cases = (
            (base, "none", "process-execution"),
            (base._replace(exit_code=1), "process-nonzero", "unclassified"),
            (base._replace(exit_code=2), "process-nonzero", "unclassified"),
            (base._replace(exit_code=None, signal_number=9), "process-signal", "process-execution"),
            (base._replace(timed_out=True), "process-timeout", "process-execution"),
            (base._replace(stderr_overflow=True), "output-overflow", "process-execution"),
            (base._replace(stdout_overflow=True), "output-overflow", "process-execution"),
            (base._replace(reaped=False, timed_out=True), "process-not-reaped", "process-cleanup"),
            (base._replace(exit_code=1, stderr=rejection, stderr_size=len(rejection)), "unsupported-strict-config", "cli-dispatch"),
            (base._replace(exit_code=2, stderr=b"unknown", stderr_size=7), "unrecognized-stderr", "unclassified"),
            (base._replace(exit_code=None), "process-observation-uncheckable", "unclassified"),
        )
        for process, reason, stage in cases:
            with self.subTest(reason=reason, exit=process.exit_code):
                result = self.adapter.classify_sandbox_launch(process)
                self.assertEqual({"status", "stage", "reason_code", "exit_code", "signal"}, set(result))
                self.assertEqual(reason, result["reason_code"])
                self.assertEqual(stage, result["stage"])
                self.assertEqual(process.exit_code, result["exit_code"])
                self.assertEqual(process.signal_number, result["signal"])
        for size, reason in ((4096, "unrecognized-stderr"), (4097, "output-overflow")):
            result = self.adapter.classify_sandbox_launch(base._replace(
                exit_code=1, stderr=b"x" * size, stderr_size=size,
            ))
            self.assertEqual(reason, result["reason_code"])
        private = b"/private/synthetic-fixture secret=synthetic-value"
        result = self.adapter.classify_sandbox_launch(base._replace(
            exit_code=1, stderr=private, stderr_size=len(private),
        ))
        self.assertNotIn(private, self.adapter.canonical_bytes(result))
        self.assertEqual("unrecognized-stderr", result["reason_code"])
        for changed in (
            base._replace(exit_code=True), base._replace(exit_code=256),
            base._replace(exit_code=0, signal_number=9),
            base._replace(signal_number=65),
        ):
            self.assertEqual("process-observation-uncheckable", self.adapter.classify_sandbox_launch(changed)["reason_code"])

    def test_sandbox_launch_diagnostic_capture_is_single_bounded_and_scrubbed(self):
        synthetic = b"Error: synthetic private path /private/fixture\n"
        process = self.adapter.ProcessResult(1, None, False, False, False, b"", len(synthetic), True, synthetic)
        for lane in ("shell", "network"):
            for enabled in (False, True):
                diagnostics = {} if enabled else None
                with mock.patch.object(self.adapter, "bounded_capture", return_value=process) as capture:
                    result = self.adapter._capture_sandbox_probe(
                        ["/synthetic/codex"], ROOT, {}, 4096, diagnostics, lane,
                    )
                capture.assert_called_once()
                self.assertEqual(4096, capture.call_args.kwargs["stderr_limit"])
                self.assertEqual(enabled, capture.call_args.kwargs.get("capture_stderr", False))
                self.assertEqual(b"", result.stderr)
                if enabled:
                    self.assertEqual("unrecognized-stderr", diagnostics[lane]["reason_code"])
                    self.assertNotIn(synthetic, self.adapter.canonical_bytes(diagnostics))
        for failure, reason in (
            (self.adapter.ProcessSpawnError("private"), "process-spawn-failed"),
            (OSError("private"), "process-observation-uncheckable"),
            (self.adapter.ContractError("private"), "process-observation-uncheckable"),
        ):
            diagnostics = {}
            with mock.patch.object(self.adapter, "bounded_capture", side_effect=failure):
                with self.assertRaises(type(failure)):
                    self.adapter._capture_sandbox_probe(["/synthetic/codex"], ROOT, {}, 4096, diagnostics, "shell")
            self.assertEqual(reason, diagnostics["shell"]["reason_code"])

    def test_sandbox_launch_diagnostic_buffer_bound_on_synthetic_process(self):
        # Ordinary offline Python fixture, never Codex, a VM, or a sandbox.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home, tmp = root / "home", root / "tmp"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            env = self.adapter.minimal_environment(Path(sys.executable).resolve(), home, tmp)
            for size in (4096, 4097):
                result = self.adapter.bounded_capture(
                    [sys.executable, "-I", "-c", "import sys; sys.stderr.buffer.write(b'x'*{})".format(size)],
                    root, env, stdout_limit=64, stderr_limit=4096, capture_stderr=True,
                )
                self.assertLessEqual(len(result.stderr), 4096)
                self.assertEqual(size == 4097, result.stderr_overflow)
                self.assertTrue(result.reaped)

    def test_sandbox_launch_diagnostics_each_lane_invokes_once_without_promoting_gate(self):
        environment = {name: "reviewed" for name in self.adapter.SHELL_ENVIRONMENT_NAMES}
        required = self.adapter.reviewed_runtime_configuration(environment)
        process = self.adapter.ProcessResult(2, None, False, False, False, b"", 7, True, b"unknown")
        listener, client, accepted = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        listener.getsockname.return_value = ("127.0.0.1", 43123)
        client.getsockname.return_value = ("127.0.0.1", 54321)
        listener.accept.return_value = (accepted, ("127.0.0.1", 54321))
        for lane in ("shell", "network"):
            diagnostics = {}
            with mock.patch.object(self.adapter, "bounded_capture", return_value=process) as capture, \
                 mock.patch.object(self.adapter, "_network_namespace_sha256", return_value="1" * 64), \
                 mock.patch.object(self.adapter.socket, "socket", return_value=listener), \
                 mock.patch.object(self.adapter.socket, "create_connection", return_value=client):
                if lane == "shell":
                    evidence = self.adapter.shell_environment_probe(
                        Path("/synthetic/codex"), ROOT, environment, required, diagnostics,
                    )
                else:
                    evidence = self.adapter.network_sandbox_behavior_probe(
                        Path("/synthetic/codex"), ROOT, environment, diagnostics,
                    )
            capture.assert_called_once()
            self.assertTrue(capture.call_args.kwargs["capture_stderr"])
            self.assertEqual("process-nonzero", evidence["reason_code"])
            self.assertEqual("fail" if lane == "shell" else "UNCHECKABLE", evidence["status"])
            self.assertEqual("unrecognized-stderr", diagnostics[lane]["reason_code"])

    def test_sandbox_launch_diagnostics_auth_observation_is_reused(self):
        stable_help = b"--json --ephemeral --strict-config --ignore-user-config workspace-write --model --sandbox\n"
        calls = []
        diagnostics = {lane: self.adapter.launch_diagnostic_record() for lane in ("shell", "network")}
        def auth(*_args):
            calls.append("auth")
            return "unavailable"
        def capture(argv, *_args, **_kwargs):
            calls.append("version-help")
            return self.adapter.ProcessResult(0, None, False, False, False,
                b"codex-cli 0.150.1\n" if argv[-1] == "--version" else stable_help, 0, True)
        def probe(*_args, **kwargs):
            calls.append("lanes")
            self.assertIs(diagnostics, kwargs["launch_diagnostics"])
            self.assertFalse(kwargs["auth_required"])
            return self.passing_runtime_probe()
        with mock.patch.object(self.adapter, "auth_class", side_effect=auth) as auth_sensor, \
             mock.patch.object(self.adapter, "bounded_capture", side_effect=capture), \
             mock.patch.object(self.adapter, "hash_regular_file", return_value="a" * 64), \
             mock.patch.object(self.adapter, "observe_stage_a1_prerequisite", return_value=self.passing_stage_a1_prerequisite()), \
             mock.patch.object(self.adapter, "probe_runtime_evidence", side_effect=probe), \
             mock.patch.object(self.adapter, "observe_colima_provider_evidence", return_value=self.passing_containment_evidence()), \
             mock.patch.object(self.adapter.os, "uname", return_value=SimpleNamespace(sysname="Linux", machine="aarch64")):
            profile = self.adapter._observe_runtime_profile_bound_inner(
                ROOT, "gpt-5.6-sol", "high", Path("/synthetic/codex"), ROOT,
                {}, self.colima_provider_input(), object(), True, diagnostics,
            )
        auth_sensor.assert_called_once()
        self.assertEqual("auth", calls[0])
        self.assertEqual(1, calls.count("lanes"))
        self.assertEqual("probe-only-match", profile["status"])
        self.assertFalse(profile["live_run_allowed"])

    def test_sandbox_launch_checker_detects_surface_and_projection_drift(self):
        errors = []
        self.checker.validate_sandbox_launch_contract(self.adapter, errors)
        self.assertEqual([], errors)
        with mock.patch.object(self.adapter, "LAUNCH_DIAGNOSTIC_STDERR_LIMIT", 8192):
            self.checker.validate_sandbox_launch_contract(self.adapter, errors)
        self.assertTrue(errors)
        errors = []
        with mock.patch.object(self.adapter, "classify_sandbox_launch", return_value={"raw_stderr": "synthetic"}):
            self.checker.validate_sandbox_launch_contract(self.adapter, errors)
        self.assertTrue(errors)

    def test_sandbox_launch_diagnostics_gate_before_capture_and_reject_live(self):
        parser = self.adapter.build_parser()
        self.assertTrue(parser.parse_args(["profile", "--probe-only", "--launch-diagnostics"]).launch_diagnostics)
        args = parser.parse_args(["profile", "--launch-diagnostics"])
        with mock.patch.object(self.adapter, "read_stdin_bounded") as stdin:
            self.assert_contract_error(lambda: self.adapter.cli_profile(args, ROOT), "probe-only")
        stdin.assert_not_called()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["run", "--mode", "live", "--launch-diagnostics"])
        for auth in ("signed-in-client", "api-key", "unknown"):
            with mock.patch.object(self.adapter, "auth_class", return_value=auth) as auth_sensor, \
                 mock.patch.object(self.adapter, "bounded_capture") as capture, \
                 mock.patch.object(self.adapter, "probe_runtime_evidence") as probe:
                self.assert_contract_error(lambda: self.adapter._observe_runtime_profile_bound_inner(
                    ROOT, "gpt-5.6-sol", "high", Path("/synthetic/codex"), ROOT,
                    {}, {}, object(), probe_only=True, launch_diagnostics={},
                ), "unavailable authentication")
            auth_sensor.assert_called_once()
            capture.assert_not_called()
            probe.assert_not_called()
        for probe_only, provider in ((False, {}), (True, None)):
            with mock.patch.object(self.adapter, "require_runtime_fs_capabilities") as fs:
                self.assert_contract_error(lambda: self.adapter.observe_runtime_profile(
                    ROOT, "gpt-5.6-sol", "high", provider, probe_only=probe_only, launch_diagnostics={},
                ))
            fs.assert_not_called()
        with mock.patch.object(self.adapter, "bounded_capture") as capture:
            self.assert_contract_error(lambda: self.adapter.probe_runtime_evidence(
                Path("/synthetic/codex"), ROOT, {}, ROOT, launch_diagnostics={},
            ))
        capture.assert_not_called()

    def test_sandbox_launch_wrapper_is_separate_from_unchanged_profile_schema(self):
        profile = self.adapter._unavailable_runtime_profile("gpt-5.6-sol", "high", True)
        wrapper = {
            "schema": self.adapter.LAUNCH_DIAGNOSTIC_SCHEMA,
            "authority": "adapter-authored", "runtime_profile": profile,
            "launch_diagnostics": {lane: self.adapter.launch_diagnostic_record() for lane in ("shell", "network")},
        }
        schema = json.loads((ROOT / "docs/agreements/runtime/runtime-profile.v1.schema.json").read_text())
        self.assert_draft_2020_valid(schema, profile)
        self.assert_draft_2020_invalid(schema, wrapper)
        self.adapter.validate_runtime_profile(profile)
        self.adapter.validate_launch_diagnostics_wrapper(wrapper)
        self.assert_contract_error(lambda: self.adapter.validate_runtime_profile(wrapper))
        omitted = copy.deepcopy(wrapper)
        del omitted["launch_diagnostics"]
        self.assert_contract_error(lambda: self.adapter.validate_launch_diagnostics_wrapper(omitted))
        inline = copy.deepcopy(profile)
        inline["launch_diagnostics"] = wrapper["launch_diagnostics"]
        self.assert_contract_error(lambda: self.adapter.validate_runtime_profile(inline))
        self.assert_draft_2020_invalid(schema, inline)
        for key, value in (("raw_stderr", "private"), ("reason_code", "invented"), ("exit_code", True), ("signal", 999), ("stage", "private")):
            bad = copy.deepcopy(wrapper)
            bad["launch_diagnostics"]["shell"][key] = value
            self.assert_contract_error(lambda: self.adapter.validate_launch_diagnostics_wrapper(bad))
        args = self.adapter.build_parser().parse_args(["profile", "--probe-only", "--launch-diagnostics"])
        with mock.patch.object(self.adapter, "read_stdin_bounded", return_value=self.adapter.canonical_bytes(self.colima_provider_input())), \
             mock.patch.object(self.adapter, "observe_runtime_profile", return_value=profile):
            observed = self.adapter.cli_profile(args, ROOT)
        self.assertEqual(wrapper, observed)
        args.launch_diagnostics = False
        with mock.patch.object(self.adapter, "read_stdin_bounded", return_value=self.adapter.canonical_bytes(self.colima_provider_input())), \
             mock.patch.object(self.adapter, "observe_runtime_profile", return_value=profile) as sensor:
            self.assertEqual(profile, self.adapter.cli_profile(args, ROOT))
        self.assertNotIn("launch_diagnostics", sensor.call_args.kwargs)

    def test_sandbox_launch_diagnostics_capability_error_preserves_safe_error(self):
        args = self.adapter.build_parser().parse_args(["profile", "--probe-only", "--launch-diagnostics"])
        with mock.patch.object(self.adapter, "require_runtime_fs_capabilities", side_effect=self.adapter.ContractError("synthetic private detail")), \
             mock.patch.object(self.adapter, "read_stdin_bounded") as stdin, \
             mock.patch.object(self.adapter, "observe_runtime_profile") as sensor:
            with self.assertRaises(self.adapter.ProfileProbeError) as caught:
                self.adapter.cli_profile(args, ROOT)
        stdin.assert_not_called()
        sensor.assert_not_called()
        safe = self.adapter.safe_error(caught.exception)
        self.assertNotIn(b"synthetic private detail", self.adapter.canonical_bytes(safe))

    def test_shell_environment_probe_has_closed_reason_codes_and_safe_metrics(self):
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

            def payload(entries):
                return b"\0".join(
                    (name + "=" + value).encode("utf-8")
                    for name, value in entries
                ) + b"\0"

            valid_entries = sorted(configured.items()) + [
                ("CODEX_SANDBOX_NETWORK_DISABLED", "1"),
            ]

            def result_with(entries=valid_entries, **overrides):
                return self.adapter.ProcessResult(
                    overrides.get("exit_code", 0), None,
                    overrides.get("timed_out", False),
                    overrides.get("stdout_overflow", False),
                    overrides.get("stderr_overflow", False),
                    payload(entries), 0, overrides.get("reaped", True),
                )

            cases = [
                ("none", "pass", result_with()),
                ("process-nonzero", "fail", result_with(exit_code=7)),
                ("process-timeout", "UNCHECKABLE", result_with(timed_out=True)),
                ("output-overflow", "UNCHECKABLE", result_with(stdout_overflow=True)),
                ("process-not-reaped", "UNCHECKABLE", result_with(reaped=False)),
                ("malformed-env-output", "fail", self.adapter.ProcessResult(
                    0, None, False, False, False, b"NO-EQUALS\0", 0, True,
                )),
                ("duplicate-env-key", "fail", result_with(valid_entries + [valid_entries[0]])),
                ("required-value-missing", "fail", result_with(valid_entries[1:])),
                ("required-value-mismatch", "fail", result_with([
                    (name, "wrong" if name == valid_entries[0][0] else value)
                    for name, value in valid_entries
                ])),
                ("forbidden-sentinel-survived", "fail", result_with(
                    valid_entries + [("T11_FORBIDDEN_SENTINEL", "must-not-survive")],
                )),
                ("network-marker-missing", "fail", result_with(valid_entries[:-1])),
                ("network-marker-mismatch", "fail", result_with(
                    valid_entries[:-1] + [("CODEX_SANDBOX_NETWORK_DISABLED", "0")],
                )),
                ("unexpected-key-set", "fail", result_with(
                    valid_entries + [("T11_UNKNOWN_AUTOMATIC", "1")],
                )),
                ("secret-shaped-key", "fail", result_with(
                    valid_entries + [("T11_ACCESS_TOKEN", "redacted")],
                )),
            ]
            observed_reasons = set()
            for reason, status, process_result in cases:
                with self.subTest(reason=reason), mock.patch.object(
                    self.adapter, "bounded_capture", return_value=process_result,
                ) as capture:
                    evidence = self.adapter.shell_environment_probe(
                        Path("/reviewed/codex"), root, environment, required,
                    )
                    self.assertEqual(status, evidence["status"])
                    self.assertEqual(reason, evidence["reason_code"])
                    self.assertEqual(
                        {
                            "schema", "authority", "status", "reason_code",
                            "unexpected_key_count",
                            "unexpected_key_names_sha256", "secret_shaped_key_count",
                        },
                        set(evidence),
                    )
                    observed_reasons.add(reason)
                    self.assertEqual(
                        "must-be-overridden",
                        capture.call_args.args[2]["CODEX_SANDBOX_NETWORK_DISABLED"],
                    )

            unknown_result = cases[-2][2]
            with mock.patch.object(
                self.adapter, "bounded_capture", return_value=unknown_result,
            ):
                evidence = self.adapter.shell_environment_probe(
                    Path("/reviewed/codex"), root, environment, required,
                )
            self.assertEqual(1, evidence["unexpected_key_count"])
            self.assertEqual(0, evidence["secret_shaped_key_count"])
            self.assertEqual(
                hashlib.sha256(self.adapter.canonical_bytes([
                    "T11_UNKNOWN_AUTOMATIC",
                ])).hexdigest(),
                evidence["unexpected_key_names_sha256"],
            )
            self.assertNotIn("T11_UNKNOWN_AUTOMATIC", json.dumps(evidence))

            with mock.patch.object(
                self.adapter, "sandbox_probe_argv",
                side_effect=self.adapter.ContractError("private observation failure"),
            ):
                evidence = self.adapter.shell_environment_probe(
                    Path("/reviewed/codex"), root, environment, required,
                )
            self.assertEqual("UNCHECKABLE", evidence["status"])
            self.assertEqual("observation-uncheckable", evidence["reason_code"])
            observed_reasons.add("observation-uncheckable")
            self.assertEqual(
                set(self.adapter.SHELL_ENVIRONMENT_REASON_CODES) - {"not-run"},
                observed_reasons,
            )

            private_stderr = b"/Users/alice/private/auth.json"
            nonzero_with_stderr = self.adapter.ProcessResult(
                7, None, False, False, False, b"", len(private_stderr), True,
                private_stderr,
            )
            evidence = self.adapter.classify_shell_environment_result(
                nonzero_with_stderr, configured,
            )
            self.assertEqual("process-nonzero", evidence["reason_code"])
            self.assertNotIn("alice", json.dumps(evidence))
            signaled_with_stderr = self.adapter.ProcessResult(
                None, signal.SIGTERM, False, False, False, b"",
                len(private_stderr), True, private_stderr,
            )
            evidence = self.adapter.classify_shell_environment_result(
                signaled_with_stderr, configured,
            )
            self.assertEqual("process-nonzero", evidence["reason_code"])
            self.assertNotIn("alice", json.dumps(evidence))

    def test_shell_environment_parser_bounds_are_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            tmp = root / "tmp"
            home.mkdir(mode=0o700)
            tmp.mkdir(mode=0o700)
            environment = self.adapter.minimal_environment(
                Path(sys.executable).resolve(), home, tmp,
            )
            configured = self.adapter.reviewed_runtime_configuration(
                environment,
            )["shell_environment_policy.set"]
            base_entries = sorted(configured.items()) + [
                ("CODEX_SANDBOX_NETWORK_DISABLED", "1"),
            ]

            def payload(entries):
                return b"\0".join(
                    (name + "=" + value).encode("utf-8")
                    for name, value in entries
                ) + b"\0"

            def classify(raw):
                return self.adapter.classify_shell_environment_result(
                    self.adapter.ProcessResult(
                        0, None, False, False, False, raw, 0, True,
                    ),
                    configured,
                )

            extra_count = (
                self.adapter.MAX_SHELL_ENVIRONMENT_ENTRIES - len(base_entries)
            )
            at_entry_limit = base_entries + [
                ("T11_EXTRA_{:03d}".format(index), "1")
                for index in range(extra_count)
            ]
            evidence = classify(payload(at_entry_limit))
            self.assertEqual("unexpected-key-set", evidence["reason_code"])
            self.assertEqual(extra_count, evidence["unexpected_key_count"])
            over_entry_limit = at_entry_limit + [("T11_EXTRA_OVER", "1")]
            self.assertEqual(
                "malformed-env-output",
                classify(payload(over_entry_limit))["reason_code"],
            )

            at_name_limit = "N" + "A" * (
                self.adapter.MAX_SHELL_ENVIRONMENT_NAME_BYTES - 1
            )
            self.assertEqual(
                "unexpected-key-set",
                classify(payload(base_entries + [(at_name_limit, "1")]))[
                    "reason_code"
                ],
            )
            over_name_limit = at_name_limit + "A"
            self.assertEqual(
                "malformed-env-output",
                classify(payload(base_entries + [(over_name_limit, "1")]))[
                    "reason_code"
                ],
            )

            at_value_limit = "x" * self.adapter.MAX_SHELL_ENVIRONMENT_VALUE_BYTES
            self.assertEqual(
                "unexpected-key-set",
                classify(payload(base_entries + [("T11_EXTRA_VALUE", at_value_limit)]))[
                    "reason_code"
                ],
            )
            self.assertEqual(
                "malformed-env-output",
                classify(payload(base_entries + [(
                    "T11_EXTRA_VALUE", at_value_limit + "x",
                )]))["reason_code"],
            )

            malformed = (
                payload(base_entries)[:-1],
                payload(base_entries)[:-1] + b"\0\0",
                b"\xff=1\0",
                b"BAD-NAME=1\0",
            )
            for raw in malformed:
                with self.subTest(raw=raw[:32]):
                    self.assertEqual(
                        "malformed-env-output", classify(raw)["reason_code"],
                    )

    def test_shell_environment_semantics_reject_status_and_count_contradictions(self):
        valid = self.adapter.shell_environment_evidence("pass", "none")
        mutations = []
        wrong_status = copy.deepcopy(valid)
        wrong_status["status"] = "fail"
        mutations.append(wrong_status)
        wrong_count = self.adapter.shell_environment_evidence(
            "fail", "secret-shaped-key", ["T11_ACCESS_TOKEN"], 1,
        )
        wrong_count["secret_shaped_key_count"] = 2
        mutations.append(wrong_count)
        for candidate in mutations:
            with self.subTest(candidate=candidate):
                self.assert_contract_error(
                    lambda value=candidate: self.adapter.validate_shell_environment_evidence(value),
                )
                errors = []
                self.checker.validate_shell_environment_evidence(
                    candidate, "mutated-shell", errors,
                )
                self.assertTrue(errors)

        schema = json.loads((
            ROOT / "docs/agreements/runtime/runtime-profile.v1.schema.json"
        ).read_text(encoding="utf-8"))
        shell_schema = schema["properties"]["evidence"]["properties"][
            "shell_environment_behavior"
        ]
        unexpected = self.adapter.shell_environment_evidence(
            "fail", "unexpected-key-set", ["T11_UNKNOWN_AUTOMATIC"], 0,
        )
        secret = self.adapter.shell_environment_evidence(
            "fail", "secret-shaped-key", ["T11_ACCESS_TOKEN"], 1,
        )
        self.assert_draft_2020_valid(shell_schema, unexpected)
        self.assert_draft_2020_valid(shell_schema, secret)
        for candidate in (
            {**unexpected, "unexpected_key_count": 0},
            {**unexpected, "unexpected_key_names_sha256": "0" * 64},
            {**secret, "secret_shaped_key_count": 0},
            {**secret, "unexpected_key_names_sha256": "0" * 64},
        ):
            with self.subTest(draft_candidate=candidate):
                self.assert_draft_2020_invalid(shell_schema, candidate)
        shell_schema["allOf"].pop()
        errors = []
        self.checker.validate_runtime_profile_schema(schema, errors)
        self.assertTrue(errors)

    def test_network_child_namespace_failure_is_bounded_and_classified(self):
        def execute_child(readlink_effect):
            stdout = io.StringIO()
            stderr = io.StringIO()
            patcher = (
                mock.patch("os.readlink", side_effect=readlink_effect)
                if isinstance(readlink_effect, BaseException)
                else mock.patch("os.readlink", return_value=readlink_effect)
            )
            with patcher, mock.patch(
                "socket.socket", side_effect=OSError(errno.EPERM, "private")
            ), mock.patch.object(sys, "argv", ["network-probe", "43123"]), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(
                    self.adapter.NETWORK_SANDBOX_PROBE_SCRIPT,
                    "<network-sandbox-probe>", "exec",
                ), {})
            self.assertEqual("", stderr.getvalue())
            payload = json.loads(stdout.getvalue())
            self.assertEqual("0" * 64, payload["sandbox_network_namespace_sha256"])
            result = self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes(payload), 0, True,
            )
            evidence = self.adapter.classify_network_sandbox_result(
                "accepted-and-closed", "1" * 64, result,
            )
            self.assertEqual("UNCHECKABLE", evidence["status"])
            self.assertEqual("sandbox-netns-unavailable", evidence["reason_code"])
            self.assertEqual("pass", evidence["process_cleanup_status"])
            self.assertTrue(evidence["process_reaped"])
            self.assertNotIn("private", json.dumps(evidence))

        execute_child(OSError(errno.ENOENT, "private namespace path"))
        execute_child("mnt:[123]")

    def test_network_sandbox_probe_binds_control_namespace_marker_and_denial(self):
        parent_namespace = "1" * 64
        sandbox_namespace = "2" * 64

        def result(namespace=sandbox_namespace, marker="exact-1", connection="denied", denial="EPERM", **overrides):
            payload = self.adapter.canonical_bytes({
                "sandbox_network_namespace_sha256": namespace,
                "network_marker_status": marker,
                "sandbox_connection_status": connection,
                "denial_errno": denial,
            })
            return self.adapter.ProcessResult(
                overrides.get("exit_code", 0), None,
                overrides.get("timed_out", False),
                overrides.get("stdout_overflow", False),
                overrides.get("stderr_overflow", False),
                payload, 0, overrides.get("reaped", True),
            )

        passing_errnos = ("EPERM", "EACCES", "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED")
        for denial in passing_errnos:
            with self.subTest(denial=denial):
                evidence = self.adapter.classify_network_sandbox_result(
                    "accepted-and-closed", parent_namespace, result(denial=denial),
                )
                self.assertEqual("pass", evidence["status"])
                self.assertEqual("none", evidence["reason_code"])
                self.assertTrue(evidence["unsandboxed_control_accepted"])
                self.assertTrue(evidence["unsandboxed_control_closed"])
                self.assertTrue(evidence["netns_different"])
                self.assertEqual("exact-1", evidence["network_marker_status"])
                self.assertEqual("denied", evidence["sandbox_connect_status"])
                self.assertEqual(denial, evidence["sandbox_connect_errno"])
                self.assertEqual("pass", evidence["process_cleanup_status"])
                self.assertTrue(evidence["process_reaped"])
                self.assertFalse(evidence["raw_stdout_recorded"])
                self.assertFalse(evidence["raw_stderr_recorded"])

        cases = (
            ("parent-netns-unavailable", "UNCHECKABLE", "0" * 64, result()),
            ("netns-not-separated", "fail", parent_namespace, result(namespace=parent_namespace)),
            ("network-marker-missing", "fail", parent_namespace, result(marker="missing")),
            ("network-marker-mismatch", "fail", parent_namespace, result(marker="mismatch")),
            ("sandbox-connection-succeeded", "fail", parent_namespace, result(connection="succeeded", denial="none")),
            ("unapproved-denial-errno", "UNCHECKABLE", parent_namespace, result(denial="unapproved")),
            ("process-nonzero", "UNCHECKABLE", parent_namespace, result(exit_code=7)),
            ("process-timeout", "UNCHECKABLE", parent_namespace, result(timed_out=True)),
            ("output-overflow", "UNCHECKABLE", parent_namespace, result(stdout_overflow=True)),
            ("process-not-reaped", "UNCHECKABLE", parent_namespace, result(reaped=False)),
        )
        for reason, status, parent, process_result in cases:
            with self.subTest(reason=reason):
                evidence = self.adapter.classify_network_sandbox_result(
                    "accepted-and-closed", parent, process_result,
                )
                self.assertEqual(status, evidence["status"])
                self.assertEqual(reason, evidence["reason_code"])
                self.assertNotIn("/proc/", json.dumps(evidence))

        for reason, process_result, expected_cleanup, expected_reaped in (
            ("process-timeout", result(timed_out=True, reaped=True), "pass", True),
            ("process-timeout", result(timed_out=True, reaped=False), "UNCHECKABLE", False),
            ("output-overflow", result(stdout_overflow=True, reaped=True), "pass", True),
            ("output-overflow", result(stdout_overflow=True, reaped=False), "UNCHECKABLE", False),
        ):
            with self.subTest(reason=reason, reaped=expected_reaped):
                evidence = self.adapter.classify_network_sandbox_result(
                    "accepted-and-closed", parent_namespace, process_result,
                )
                self.assertEqual(reason, evidence["reason_code"])
                self.assertEqual(expected_cleanup, evidence["process_cleanup_status"])
                self.assertIs(expected_reaped, evidence["process_reaped"])

        private_stderr = b"/Users/alice/private/runtime.err"
        nonzero_with_stderr = self.adapter.ProcessResult(
            9, None, False, False, False, b"", len(private_stderr), True,
            private_stderr,
        )
        evidence = self.adapter.classify_network_sandbox_result(
            "accepted-and-closed", parent_namespace, nonzero_with_stderr,
        )
        self.assertEqual("process-nonzero", evidence["reason_code"])
        self.assertEqual("UNCHECKABLE", evidence["status"])
        self.assertEqual("pass", evidence["process_cleanup_status"])
        self.assertTrue(evidence["process_reaped"])
        self.assertNotIn("alice", json.dumps(evidence))
        signaled_with_stderr = self.adapter.ProcessResult(
            None, signal.SIGTERM, False, False, False, b"",
            len(private_stderr), True, private_stderr,
        )
        evidence = self.adapter.classify_network_sandbox_result(
            "accepted-and-closed", parent_namespace, signaled_with_stderr,
        )
        self.assertEqual("process-nonzero", evidence["reason_code"])
        self.assertEqual("UNCHECKABLE", evidence["status"])
        self.assertEqual("pass", evidence["process_cleanup_status"])
        self.assertNotIn("alice", json.dumps(evidence))

    def test_network_sandbox_semantics_reject_contradictory_records(self):
        valid = self.passing_network_evidence()
        mutations = []
        for field, replacement in (
            ("status", "fail"),
            ("unsandboxed_control_closed", False),
            ("netns_different", False),
            ("sandbox_connect_errno", "none"),
            ("process_reaped", False),
        ):
            candidate = copy.deepcopy(valid)
            candidate[field] = replacement
            mutations.append(candidate)
        marker = self.adapter.network_sandbox_evidence(
            "fail", "network-marker-missing",
            control_accepted=True, control_closed=True,
            parent_namespace_sha256="1" * 64,
            sandbox_namespace_sha256="2" * 64,
            marker_status="missing", connect_status="denied",
            connect_errno="EPERM", process_cleanup_status="pass",
            process_reaped=True,
        )
        marker["network_marker_status"] = "exact-1"
        mutations.append(marker)
        timeout = self.adapter.network_sandbox_evidence(
            "UNCHECKABLE", "process-timeout",
            control_accepted=True, control_closed=True,
            parent_namespace_sha256="1" * 64,
            process_cleanup_status="pass", process_reaped=True,
        )
        self.adapter.validate_network_sandbox_evidence(timeout)
        timeout_unreaped = copy.deepcopy(timeout)
        timeout_unreaped["process_cleanup_status"] = "UNCHECKABLE"
        timeout_unreaped["process_reaped"] = False
        self.adapter.validate_network_sandbox_evidence(timeout_unreaped)
        timeout_not_run = copy.deepcopy(timeout)
        timeout_not_run["process_cleanup_status"] = "not-run"
        timeout_not_run["process_reaped"] = False
        mutations.append(timeout_not_run)
        overflow = copy.deepcopy(timeout)
        overflow["reason_code"] = "output-overflow"
        self.adapter.validate_network_sandbox_evidence(overflow)
        overflow_unreaped = copy.deepcopy(overflow)
        overflow_unreaped["process_cleanup_status"] = "UNCHECKABLE"
        overflow_unreaped["process_reaped"] = False
        self.adapter.validate_network_sandbox_evidence(overflow_unreaped)
        overflow_not_run = copy.deepcopy(overflow)
        overflow_not_run["process_cleanup_status"] = "not-run"
        overflow_not_run["process_reaped"] = False
        mutations.append(overflow_not_run)
        for candidate in mutations:
            with self.subTest(candidate=candidate):
                self.assert_contract_error(
                    lambda value=candidate: self.adapter.validate_network_sandbox_evidence(value),
                )
                errors = []
                self.checker.validate_network_sandbox_evidence(
                    candidate, "mutated-network", errors,
                )
                self.assertTrue(errors)

        schema = json.loads((
            ROOT / "docs/agreements/runtime/runtime-profile.v1.schema.json"
        ).read_text(encoding="utf-8"))
        network_schema = schema["properties"]["evidence"]["properties"][
            "network_sandbox_behavior"
        ]
        marker_valid = self.adapter.network_sandbox_evidence(
            "fail", "network-marker-missing",
            control_accepted=True, control_closed=True,
            parent_namespace_sha256="1" * 64,
            sandbox_namespace_sha256="2" * 64,
            marker_status="missing", connect_status="denied",
            connect_errno="EPERM", process_cleanup_status="pass",
            process_reaped=True,
        )
        marker_bad_connection = copy.deepcopy(marker_valid)
        marker_bad_connection["sandbox_connect_status"] = "succeeded"
        netns_valid = self.adapter.network_sandbox_evidence(
            "fail", "netns-not-separated",
            control_accepted=True, control_closed=True,
            parent_namespace_sha256="1" * 64,
            sandbox_namespace_sha256="1" * 64,
            marker_status="exact-1", connect_status="denied",
            connect_errno="EPERM", process_cleanup_status="pass",
            process_reaped=True,
        )
        netns_unobserved = copy.deepcopy(netns_valid)
        netns_unobserved["network_marker_status"] = "not-run"
        netns_unobserved["sandbox_connect_status"] = "not-run"
        netns_unobserved["sandbox_connect_errno"] = "not-run"
        for candidate in (
            marker_valid, netns_valid, timeout, timeout_unreaped,
            overflow, overflow_unreaped,
        ):
            with self.subTest(draft_valid=candidate["reason_code"]):
                self.assert_draft_2020_valid(network_schema, candidate)
        for candidate in (
            marker_bad_connection, netns_unobserved, timeout_not_run,
            overflow_not_run,
        ):
            with self.subTest(draft_invalid=candidate["reason_code"]):
                self.assert_draft_2020_invalid(network_schema, candidate)
        network_schema["allOf"].pop()
        errors = []
        self.checker.validate_runtime_profile_schema(schema, errors)
        self.assertTrue(errors)

    def test_runtime_checker_reason_and_errno_registries_match_adapter(self):
        self.assertEqual(
            tuple(self.adapter.SHELL_ENVIRONMENT_REASON_CODES),
            tuple(self.checker.SHELL_ENVIRONMENT_REASON_CODES),
        )
        self.assertEqual(
            tuple(self.adapter.NETWORK_SANDBOX_REASON_CODES),
            tuple(self.checker.NETWORK_SANDBOX_REASON_CODES),
        )
        self.assertEqual(
            tuple(self.adapter.APPROVED_NETWORK_DENIAL_ERRNOS),
            tuple(self.checker.APPROVED_NETWORK_DENIAL_ERRNOS),
        )

    def test_network_sandbox_probe_control_must_connect_accept_and_close(self):
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
            connection.getsockname.return_value = ("127.0.0.1", 54321)
            accepted = mock.MagicMock()
            listener.accept.return_value = (accepted, ("127.0.0.1", 54321))
            child = self.adapter.ProcessResult(
                0, None, False, False, False,
                self.adapter.canonical_bytes({
                    "sandbox_network_namespace_sha256": "2" * 64,
                    "network_marker_status": "exact-1",
                    "sandbox_connection_status": "denied",
                    "denial_errno": "EPERM",
                }), 0, True,
            )
            with mock.patch.object(
                self.adapter.socket, "socket", return_value=listener,
            ), mock.patch.object(
                self.adapter.socket, "create_connection", return_value=connection,
            ), mock.patch.object(
                self.adapter, "_network_namespace_sha256", return_value="1" * 64,
            ), mock.patch.object(
                self.adapter, "bounded_capture", return_value=child,
            ):
                evidence = self.adapter.network_sandbox_behavior_probe(
                    Path("/reviewed/codex"), root, environment,
                )
            self.assertEqual("pass", evidence["status"])
            listener.accept.assert_called_once_with()
            accepted.close.assert_called_once_with()
            connection.close.assert_called_once_with()

            with mock.patch.object(
                self.adapter.socket, "socket", side_effect=OSError("control unavailable"),
            ), mock.patch.object(
                self.adapter, "_network_namespace_sha256", return_value="1" * 64,
            ):
                evidence = self.adapter.network_sandbox_behavior_probe(
                    Path("/reviewed/codex"), root, environment,
                )
            self.assertEqual("UNCHECKABLE", evidence["status"])
            self.assertEqual("control-unavailable", evidence["reason_code"])

            mismatch_listener = mock.MagicMock()
            mismatch_listener.getsockname.return_value = ("127.0.0.1", 43123)
            mismatch_client = mock.MagicMock()
            mismatch_client.getsockname.return_value = ("127.0.0.1", 54321)
            mismatch_accepted = mock.MagicMock()
            mismatch_listener.accept.return_value = (
                mismatch_accepted, ("127.0.0.1", 54322),
            )
            with mock.patch.object(
                self.adapter.socket, "socket", return_value=mismatch_listener,
            ), mock.patch.object(
                self.adapter.socket, "create_connection",
                return_value=mismatch_client,
            ), mock.patch.object(
                self.adapter, "_network_namespace_sha256", return_value="1" * 64,
            ), mock.patch.object(self.adapter, "bounded_capture") as capture:
                evidence = self.adapter.network_sandbox_behavior_probe(
                    Path("/reviewed/codex"), root, environment,
                )
            self.assertEqual("UNCHECKABLE", evidence["status"])
            self.assertEqual("control-peer-mismatch", evidence["reason_code"])
            capture.assert_not_called()
            mismatch_accepted.close.assert_called_once_with()
            mismatch_client.close.assert_called_once_with()

    def test_worker_argv_failure_is_fixed_stage_and_reason_only(self):
        private_projection = self.adapter.exact_worker_argv_evidence(
            Path("/reviewed/codex"), ROOT, ROOT, {},
            require_private_projection=True,
        )
        self.assertEqual("fail", private_projection["status"])
        self.assertEqual("load-envelope", private_projection["stage"])
        self.assertEqual("envelope-invalid", private_projection["reason_code"])
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
        profile = self.t12_live_profile()
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

            def capture(argv, _cwd, _env, stdin_bytes=b"", timeout=15, **_limits):
                del stdin_bytes, timeout, _limits
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

            with mock.patch.object(
                self.adapter, "bounded_capture", side_effect=capture,
            ), mock.patch.object(
                self.adapter, "network_sandbox_behavior_probe",
                return_value=self.passing_network_evidence(),
            ):
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
        self.assertNotIn("Issue #25", rendered)
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
