import copy
import datetime
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/post-runtime-receipt.py"
FIXTURE = ROOT / "tests/runtime/fixtures/runtime-receipt-valid.v1.json"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeReceiptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = load_module(SCRIPT, "runtime_receipt_tests")
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assert_receipt_error(self, callback, token=None):
        with self.assertRaises(self.receipt.ReceiptError) as raised:
            callback()
        if token:
            self.assertIn(token, str(raised.exception))

    def fixture_now(self):
        return datetime.datetime(2026, 8, 28, 0, 5, tzinfo=datetime.timezone.utc)

    def lifecycle_fixture(self):
        runtime = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(runtime)
        provider = runtime["containment_provider"]
        return {
            "schema": "t11-colima-lifecycle-receipt-request/v1",
            "repository": "mochan-tk/agentic-dev-kit-for-codex",
            "authority": "owner-authored",
            "codex_authenticated_attestation": False,
            "task": copy.deepcopy(runtime["task"]),
            "pull_request": copy.deepcopy(runtime["pull_request"]),
            "attempt_id": runtime["attempt_id"],
            "provider": {
                "profile_name": provider["profile_name"],
                "vm_instance_identity_sha256": provider["vm_instance_identity_sha256"],
                "normalized_control_plane_sha256": provider["control_plane"]["normalized_control_plane_sha256"],
            },
            "runtime_receipt": {
                "comment_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-900",
                "body_sha256": self.receipt.sha256(body.encode("utf-8")),
                "receipt_sha256": self.receipt.sha256(self.receipt.canonical_bytes(runtime)),
                "posted_at": "2026-08-28T00:00:30Z",
                "request": copy.deepcopy(self.fixture),
            },
            "checks": copy.deepcopy(runtime["checks"]),
            "destroy": {
                "destroy_requested": True,
                "destroy_requested_at": "2026-08-28T00:01:00Z",
                "destroy_completed": True,
                "destroy_completed_at": "2026-08-28T00:02:00Z",
                "profile_absence_readback": "absent",
                "profile_absence_observed_at": "2026-08-28T00:03:00Z",
                "runtime_data_absence_readback": "absent",
                "runtime_data_absence_observed_at": "2026-08-28T00:04:00Z",
            },
            "privacy": copy.deepcopy(self.receipt.LIFECYCLE_PRIVACY),
        }

    def probe_fixture(self):
        profile = copy.deepcopy(self.fixture["artifacts"]["runtime_profile"])
        profile.update({
            "scope": "exact-head-probe-only-sensor",
            "status": "probe-only-match",
            "reason": "all unauthenticated Stage A probe lanes match",
            "live_run_allowed": False,
        })
        profile["auth"] = {
            "class": "unavailable",
            "credential_values_recorded": False,
        }
        profile["evidence"]["lane_statuses"] = copy.deepcopy(
            self.receipt.PROBE_LANES
        )
        return {
            "schema": "t11-stage-a-probe-receipt-request/v1",
            "repository": "mochan-tk/agentic-dev-kit-for-codex",
            "authority": "adapter/owner-authored",
            "codex_authenticated_attestation": False,
            "task": {
                "issue": 23,
                "url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23",
            },
            "pull_request": copy.deepcopy(self.fixture["pull_request"]),
            "attempt_id": "ATTEMPT-0123456789abcdef",
            "runtime_profile": profile,
            "probe_execution": {
                "probe_only": True,
                "device_auth_performed": False,
                "model_invocation_performed": False,
                "live_worker_started": False,
                "native_execution_artifacts_exported": False,
            },
            "checks": copy.deepcopy(self.fixture["checks"]),
            "chronology": {
                "probe_started_at": "2026-08-28T00:00:00Z",
                "probe_completed_at": "2026-08-28T00:01:00Z",
            },
            "destroy": {
                "destroy_requested": True,
                "destroy_requested_at": "2026-08-28T00:02:00Z",
                "destroy_completed": True,
                "destroy_completed_at": "2026-08-28T00:03:00Z",
                "profile_absence_readback": "absent",
                "profile_absence_observed_at": "2026-08-28T00:04:00Z",
                "runtime_data_absence_readback": "absent",
                "runtime_data_absence_observed_at": "2026-08-28T00:04:30Z",
            },
            "privacy": copy.deepcopy(self.receipt.PROBE_PRIVACY),
        }

    def validate_probe(self, fixture=None, now=None):
        adapter = mock.Mock()
        adapter.validate_runtime_profile.return_value = None
        with mock.patch.object(self.receipt, "load_adapter", return_value=adapter):
            result = self.receipt.validate_probe_receipt(
                copy.deepcopy(fixture or self.probe_fixture()),
                now=now or self.fixture_now(),
            )
        adapter.validate_runtime_profile.assert_called_once()
        return result

    def refresh_artifact_chain(self, fixture, observed_at):
        artifacts = fixture["artifacts"]
        profile = artifacts["runtime_profile"]
        envelope = artifacts["envelope"]
        result = artifacts["execution_result"]
        verifier = artifacts["verifier"]
        profile["observed_at"] = observed_at
        provider = profile["evidence"]["containment_provider"]
        provider["created_at"] = observed_at
        control = provider["control_plane"]
        control["pre_create_observed_at"] = observed_at
        control["post_create_observed_at"] = observed_at
        normalized = {key: value for key, value in control.items() if key != "normalized_control_plane_sha256"}
        control["normalized_control_plane_sha256"] = self.receipt.sha256(self.receipt.canonical_bytes(normalized))
        result["digests"]["runtime_profile_sha256"] = self.receipt.sha256(self.receipt.canonical_bytes(profile))
        result["digests"]["envelope_sha256"] = self.receipt.sha256(self.receipt.canonical_bytes(envelope))
        result["verifier"]["record_sha256"] = self.receipt.sha256(self.receipt.canonical_bytes(verifier))
        return fixture

    def test_valid_receipt_and_dry_run_are_canonical_and_private_path_free(self):
        validated = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(validated)
        self.assertIn("T11 exact-head runtime receipt", body)
        self.assertNotRegex(body, r"/Users/|/var/folders/|/tmp/")
        fresh = self.refresh_artifact_chain(
            copy.deepcopy(self.fixture),
            datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--dry-run"], cwd=ROOT,
            input=self.receipt.canonical_bytes(fresh), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(23, payload["target_issue"])
        fresh_body = self.receipt.render_comment(self.receipt.validate_receipt(fresh))
        self.assertEqual(fresh_body, payload["body"])
        self.assertEqual(self.receipt.sha256(fresh_body.encode("utf-8")), payload["body_sha256"])

    def test_receipt_rejects_stale_or_incomplete_check_bindings(self):
        mutations = (
            lambda value: value["checks"].pop(),
            lambda value: value["checks"][0].__setitem__("head", "f" * 40),
            lambda value: value["checks"][0].__setitem__("result", "failure"),
            lambda value: value["checks"][1].__setitem__("context", "quality"),
            lambda value: value["checks"][0].__setitem__("url", "https://example.invalid/job/1"),
        )
        for mutation in mutations:
            fixture = copy.deepcopy(self.fixture)
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now()))

    def test_receipt_rejects_identity_digest_and_nonpass_drift(self):
        mutations = (
            lambda value: value["task"].__setitem__("issue", 24),
            lambda value: value["pull_request"].update({"number": 25, "url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/25"}),
            lambda value: value["pull_request"].__setitem__("head", "short"),
            lambda value: value["artifacts"]["envelope"]["harness"].__setitem__("commit", "f" * 40),
            lambda value: value["artifacts"]["runtime_profile"].__setitem__("status", "UNKNOWN"),
            lambda value: value["artifacts"]["runtime_profile"]["auth"].__setitem__("class", "api-key"),
            lambda value: value["artifacts"]["verifier"].__setitem__("status", "UNKNOWN"),
            lambda value: value["artifacts"]["execution_result"]["git"]["changed_paths"].append("other.txt"),
        )
        for mutation in mutations:
            fixture = copy.deepcopy(self.fixture)
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now()))

    def test_receipt_projects_only_allowlisted_containment_provider_evidence(self):
        projection = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        provider = projection["containment_provider"]
        self.assertEqual("containment-provider-receipt-evidence/v1", provider["schema"])
        self.assertEqual("adapter/owner-authored", provider["authority"])
        self.assertFalse(provider["codex_authenticated_attestation"])
        self.assertEqual("colima-vm", provider["provider_kind"])
        self.assertEqual(1, provider["host_mount_count"])
        self.assertEqual(["provider-internal-cache"], provider["host_mount_classifications"])
        self.assertTrue(provider["all_host_mounts_read_only"])
        self.assertTrue(provider["host_sensitive_mounts_absent"])
        self.assertTrue(provider["unapproved_mounts_absent"])
        control = provider["control_plane"]
        self.assertEqual("colima-control-plane-receipt-evidence/v1", control["schema"])
        self.assertEqual("pass", control["status"])
        self.assertFalse(control["existing_instance_reused"])
        self.assertFalse(control["existing_container_reused"])
        self.assertFalse(control["existing_volume_reused"])
        self.assertFalse(control["default_profile_reused"])
        self.assertFalse(control["raw_paths_recorded"])
        self.assertNotIn("guest_os", provider)
        self.assertNotIn("guest_kernel", provider)
        self.assertNotIn("mounts", provider)
        self.assertNotIn("path", provider)
        self.assertNotIn("process_containment_probe", provider)
        self.assertNotIn("sandbox_configuration_probe", provider)
        self.assertEqual(
            "signed-in-client",
            projection["runtime_profile"]["lane_statuses"]["auth_status"],
        )
        self.assertEqual(
            "pass",
            projection["runtime_profile"]["lane_statuses"]["process_cleanup_status"],
        )
        rendered = self.receipt.render_comment(projection)
        self.assertIn("Provider lifecycle at receipt: destruction required; destruction not yet claimed", rendered)
        self.assertNotIn("6.8.0-fixture", rendered)

    def test_receipt_rejects_forged_or_cross_unbound_containment_provider(self):
        mutations = (
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("authority", "codex-authored"),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("codex_authenticated_attestation", True),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("public_head", "f" * 40),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("public_tree", "f" * 40),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("extracted_binary_sha256", "f" * 64),
            lambda value: value["artifacts"]["runtime_profile"]["platform"].__setitem__("architecture", "x86_64"),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"]["lifecycle"].__setitem__("destroy_completed", True),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("host_mount_count", 0),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"].__setitem__("unapproved_mounts_absent", False),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"]["control_plane"].__setitem__("existing_container_reused", True),
            lambda value: value["artifacts"]["runtime_profile"]["evidence"]["containment_provider"]["control_plane"].__setitem__("existing_volume_reused", True),
        )
        for mutation in mutations:
            fixture = copy.deepcopy(self.fixture)
            mutation(fixture)
            self.refresh_artifact_chain(fixture, fixture["artifacts"]["runtime_profile"]["observed_at"])
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now()))
        fixture = copy.deepcopy(self.fixture)
        profile = fixture["artifacts"]["runtime_profile"]
        profile["evidence"]["containment_provider"]["control_plane"]["normalized_control_plane_sha256"] = "f" * 64
        fixture["artifacts"]["execution_result"]["digests"]["runtime_profile_sha256"] = self.receipt.sha256(
            self.receipt.canonical_bytes(profile)
        )
        self.assert_receipt_error(
            lambda: self.receipt.validate_receipt(fixture, now=self.fixture_now())
        )

    def test_receipt_rejects_raw_provider_mount_or_private_path_material(self):
        fixture = copy.deepcopy(self.fixture)
        provider = fixture["artifacts"]["runtime_profile"]["evidence"]["containment_provider"]
        provider["raw_mount_inventory"] = [{"source": "/Users/alice/private"}]
        self.refresh_artifact_chain(fixture, fixture["artifacts"]["runtime_profile"]["observed_at"])
        self.assert_receipt_error(
            lambda: self.receipt.validate_receipt(fixture, now=self.fixture_now()),
            "private or sensitive",
        )
        for key, raw_value in (
            ("raw_mount_inventory", ["redacted"]),
            ("doctor_report", {"status": "redacted"}),
            ("environment", {"LANG": "C.UTF-8"}),
        ):
            fixture = copy.deepcopy(self.fixture)
            fixture["artifacts"]["runtime_profile"]["evidence"]["containment_provider"][key] = raw_value
            self.refresh_artifact_chain(fixture, fixture["artifacts"]["runtime_profile"]["observed_at"])
            with self.subTest(key=key):
                self.assert_receipt_error(
                    lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now())
                )

    def test_receipt_rejects_private_sensitive_and_raw_fields(self):
        for value in (
            "/Users/alice/private/repository",
            "file:/Users/alice/private/repository",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "Authorization: Bearer secret-value",
            "-----BEGIN PRIVATE KEY-----",
            "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
        ):
            fixture = copy.deepcopy(self.fixture)
            fixture["artifacts"]["runtime_profile"]["client"]["version_output"] = value
            with self.subTest(value=value[:12]):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now()), "private or sensitive")
        fixture = copy.deepcopy(self.fixture)
        fixture["raw_transcript"] = "omitted"
        self.assert_receipt_error(lambda: self.receipt.validate_receipt(fixture, now=self.fixture_now()))

    def test_cli_error_never_echoes_attacker_controlled_key_or_value(self):
        attacker = b'{"file:/Users/alice/private/repo":"sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"}'
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--dry-run"], cwd=ROOT,
            input=attacker, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15,
        )
        self.assertNotEqual(0, result.returncode)
        rendered = result.stdout.decode("utf-8")
        self.assertNotIn("alice", rendered)
        self.assertNotIn("sk-proj", rendered)
        self.assertEqual("bounded receipt validation or actuation failed", json.loads(rendered)["reason"])

    def test_receipt_observation_freshness_and_cross_bindings(self):
        now = datetime.datetime(2026, 8, 28, 0, 5, tzinfo=datetime.timezone.utc)
        self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=now)
        for observed in ("2026-08-27T23:40:00Z", "2026-08-28T00:20:01Z"):
            fixture = copy.deepcopy(self.fixture)
            self.refresh_artifact_chain(fixture, observed)
            with self.subTest(observed=observed):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=now), "stale")
        for section, field, value in (
            ("envelope", "attempt_id", "ATTEMPT-fedcba9876543210"),
            ("envelope", "harness", {"commit": "a" * 40, "tree": "f" * 40}),
            ("execution_result", "digests", {"envelope_sha256": "f" * 64, "runtime_profile_sha256": "f" * 64}),
            ("verifier", "attempt_id", "ATTEMPT-fedcba9876543210"),
        ):
            fixture = copy.deepcopy(self.fixture)
            fixture["artifacts"][section][field] = value
            with self.subTest(section=section, field=field):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=now))

    def test_strict_receipt_json_rejects_duplicate_keys_and_nonfinite(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'):
            with self.subTest(data=data):
                self.assert_receipt_error(lambda d=data: self.receipt.decode_json_object(d, "receipt"))

    def test_apply_capability_gate_precedes_input_and_external_side_effects(self):
        with mock.patch.object(self.receipt, "require_runtime_fs_capabilities", side_effect=self.receipt.ReceiptError("capability gate")) as gate, \
             mock.patch.object(self.receipt, "read_stdin_bounded") as read_input, \
             mock.patch.object(self.receipt, "run_gh") as github:
            with mock.patch.object(sys, "stdout", mock.Mock(buffer=mock.Mock())):
                self.assertEqual(1, self.receipt.main(["--apply"]))
        gate.assert_called_once()
        read_input.assert_not_called()
        github.assert_not_called()

    def test_receipt_input_contains_and_binds_actual_runtime_artifacts(self):
        self.assertIn("artifacts", self.fixture)
        artifacts = self.fixture["artifacts"]
        self.assertEqual("runtime-profile/v1", artifacts["runtime_profile"]["schema"])
        self.assertEqual("task-execution-envelope/v1", artifacts["envelope"]["schema"])
        self.assertEqual("execution-result/v1", artifacts["execution_result"]["schema"])
        self.assertEqual("t11-verifier-result/v1", artifacts["verifier"]["schema"])
        projection = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        self.assertEqual(self.receipt.sha256(self.receipt.canonical_bytes(artifacts["envelope"])), projection["envelope"]["sha256"])
        invented = copy.deepcopy(self.fixture)
        invented.pop("artifacts")
        invented["runtime_profile"] = copy.deepcopy(projection["runtime_profile"])
        invented["envelope"] = copy.deepcopy(projection["envelope"])
        invented["result"] = copy.deepcopy(projection["result"])
        invented["verifier"] = copy.deepcopy(projection["verifier"])
        self.assert_receipt_error(lambda: self.receipt.validate_receipt(invented, now=self.fixture_now()))

    def test_receipt_json_depth_nodes_strings_and_input_bytes_are_bounded(self):
        deep = {}
        cursor = deep
        for _ in range(25):
            cursor["x"] = {}
            cursor = cursor["x"]
        self.assert_receipt_error(lambda: self.receipt.validate_tree_limits(deep), "structural")
        self.assert_receipt_error(lambda: self.receipt.validate_tree_limits({"x": "a" * 4097}), "string")
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--dry-run"], cwd=ROOT,
            input=b"{" + b"x" * (self.receipt.MAX_INPUT + 1),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
        )
        self.assertNotEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("fail", payload["status"])
        self.assertNotIn("Traceback", result.stdout.decode() + result.stderr.decode())

    def test_apply_checks_external_head_tree_posts_once_and_reads_back(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        pr_state = {
            "headRefOid": "a" * 40,
            "state": "OPEN",
            "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [
                {"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]}
                for check in fixture["checks"]
            ],
        }
        outputs = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(),
            json.dumps({"tree": {"sha": "b" * 40}}).encode(),
            b"[]",
            b"https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987\n",
            json.dumps({"body": body}).encode(),
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(),
            json.dumps({"tree": {"sha": "b" * 40}}).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            record = self.receipt.apply_comment(fixture, body)
        self.assertEqual("pass", record["status"])
        self.assertEqual(record["body_sha256"], record["readback_sha256"])
        self.assertEqual(9, run_gh.call_count)
        post_call = run_gh.call_args_list[4]
        self.assertEqual(body.encode("utf-8"), post_call.args[1])
        self.assertIn("--body-file", post_call.args[0])

    def test_apply_is_idempotent_and_reconciles_uncertain_post(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        pr_state = {
            "headRefOid": "a" * 40, "state": "OPEN", "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [{"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]} for check in fixture["checks"]],
        }
        marker = self.receipt.receipt_marker(fixture)
        existing = [{"url": "https://api.github.invalid/comments/987", "html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987", "body": body}]
        outputs = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(), json.dumps({"tree": {"sha": "b" * 40}}).encode(),
            json.dumps(existing).encode(),
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(), json.dumps({"tree": {"sha": "b" * 40}}).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            record = self.receipt.apply_comment(fixture, body)
        self.assertTrue(record["idempotent"])
        self.assertEqual(7, run_gh.call_count)
        self.assertIn(marker, body)

        conflict = copy.deepcopy(existing)
        conflict[0]["body"] = marker + "\nconflict"
        outputs = [json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(), json.dumps(pr_state).encode(), json.dumps({"tree": {"sha": "b" * 40}}).encode(), json.dumps(conflict).encode()]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "conflict")
        self.assertEqual(4, run_gh.call_count)

        reconciled_comment = [{"html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987", "body": body}]
        outputs = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(),
            json.dumps({"tree": {"sha": "b" * 40}}).encode(),
            b"[]",
            self.receipt.ReceiptError("uncertain transport"),
            json.dumps(reconciled_comment).encode(),
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(),
            json.dumps({"tree": {"sha": "b" * 40}}).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            record = self.receipt.apply_comment(fixture, body)
        self.assertTrue(record["idempotent"])
        self.assertTrue(record["reconciled_after_uncertain_post"])
        self.assertEqual(9, run_gh.call_count)

    def test_same_attempt_scan_rejects_conflict_even_after_exact_match(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        marker = self.receipt.receipt_marker(fixture)
        comments = [
            {"html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987", "body": body},
            {"html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-988", "body": marker + "\nconflict"},
        ]
        with mock.patch.object(self.receipt, "existing_comments", return_value=comments):
            self.assert_receipt_error(
                lambda: self.receipt.preflight_existing_receipt(fixture, body),
                "conflicts",
            )

    def test_same_attempt_scan_checks_markers_after_other_attempts(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        other_marker = "<!-- t11-runtime-receipt attempt=ATTEMPT-fedcba9876543210 receipt_sha256={} -->".format("f" * 64)
        current_marker = self.receipt.receipt_marker(fixture)
        comments = [{
            "html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987",
            "body": other_marker + "\nunrelated\n" + current_marker + "\nconflict",
        }]
        with mock.patch.object(self.receipt, "existing_comments", return_value=comments):
            self.assert_receipt_error(
                lambda: self.receipt.preflight_existing_receipt(fixture, body),
                "different attempt",
            )

    def test_runtime_receipt_preflight_rejects_any_prior_different_attempt(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        other = {
            "html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-986",
            "body": "<!-- t11-runtime-receipt attempt=ATTEMPT-fedcba9876543210 receipt_sha256={} -->\nprior".format(
                "f" * 64
            ),
        }
        with mock.patch.object(self.receipt, "existing_comments", return_value=[other]):
            self.assert_receipt_error(
                lambda: self.receipt.preflight_existing_receipt(fixture, body),
                "different attempt",
            )

    def test_idempotent_and_reconciled_success_paths_reread_external_state(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        good_pr = {
            "headRefOid": "a" * 40, "state": "OPEN", "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [{"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]} for check in fixture["checks"]],
        }
        drifted_pr = dict(good_pr)
        drifted_pr["headRefOid"] = "f" * 40
        existing = [{"html_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987", "body": body}]
        initial = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(good_pr).encode(), json.dumps({"tree": {"sha": "b" * 40}}).encode(),
        ]
        final_drift = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(drifted_pr).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=initial + [json.dumps(existing).encode()] + final_drift):
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "head drifted")

        reconciled = [{"html_url": existing[0]["html_url"], "body": body}]
        with mock.patch.object(
            self.receipt,
            "run_gh",
            side_effect=initial + [b"[]", self.receipt.ReceiptError("uncertain"), json.dumps(reconciled).encode()] + final_drift,
        ):
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "head drifted")

    def test_post_readback_head_drift_is_non_success(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        good_pr = {
            "headRefOid": "a" * 40, "state": "OPEN", "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [{"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]} for check in fixture["checks"]],
        }
        drifted_pr = dict(good_pr)
        drifted_pr["headRefOid"] = "f" * 40
        outputs = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(good_pr).encode(), json.dumps({"tree": {"sha": "b" * 40}}).encode(),
            b"[]",
            b"https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987\n",
            json.dumps({"body": body}).encode(),
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(drifted_pr).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs):
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "head drifted")

    def test_apply_stops_before_write_on_external_head_or_tree_drift(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        outputs = [json.dumps({"state": "CLOSED", "url": fixture["task"]["url"]}).encode()]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "not the exact open")
        self.assertEqual(1, run_gh.call_count)
        drift_pr = {"headRefOid": "f" * 40, "state": "OPEN", "url": fixture["pull_request"]["url"], "statusCheckRollup": []}
        outputs = [json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(), json.dumps(drift_pr).encode()]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "head drifted")
        self.assertEqual(2, run_gh.call_count)
        good_pr = {
            "headRefOid": "a" * 40, "state": "OPEN", "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [{"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]} for check in fixture["checks"]],
        }
        outputs = [json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(), json.dumps(good_pr).encode(), json.dumps({"tree": {"sha": "f" * 40}}).encode()]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs) as run_gh:
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "tree drifted")
        self.assertEqual(3, run_gh.call_count)

    def test_readback_mismatch_is_non_success(self):
        fixture = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(fixture)
        pr_state = {
            "headRefOid": "a" * 40,
            "state": "OPEN",
            "url": fixture["pull_request"]["url"],
            "statusCheckRollup": [
                {"name": check["context"], "conclusion": "SUCCESS", "detailsUrl": check["url"]}
                for check in fixture["checks"]
            ],
        }
        outputs = [
            json.dumps({"state": "OPEN", "url": fixture["task"]["url"]}).encode(),
            json.dumps(pr_state).encode(),
            json.dumps({"tree": {"sha": "b" * 40}}).encode(),
            b"[]",
            b"https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-987\n",
            json.dumps({"body": body + "\ndrift"}).encode(),
        ]
        with mock.patch.object(self.receipt, "run_gh", side_effect=outputs):
            self.assert_receipt_error(lambda: self.receipt.apply_comment(fixture, body), "read-back differs")

    def test_stage_a_probe_receipt_is_closed_dual_target_and_distinct_from_live(self):
        validated = self.validate_probe()
        self.assertEqual("t11-stage-a-probe-receipt/v1", validated["schema"])
        self.assertEqual("probe-only-match", validated["runtime_profile"]["observed_status"])
        self.assertFalse(validated["runtime_profile"]["live_run_allowed"])
        self.assertEqual("unavailable", validated["runtime_profile"]["auth_class"])
        self.assertEqual(self.receipt.PROBE_LANES, validated["runtime_profile"]["lane_statuses"])
        self.assertTrue(validated["provider"]["host_sensitive_mounts_absent"])
        self.assertTrue(validated["provider"]["unapproved_mounts_absent"])
        self.assertNotIn("guest_os", validated["provider"])
        self.assertNotIn("guest_kernel", validated["provider"])
        self.assertEqual(
            validated["runtime_profile"]["binary_sha256"],
            validated["provider"]["extracted_binary_sha256"],
        )
        issue_body = self.receipt.render_probe_comment(validated, "issue")
        pr_body = self.receipt.render_probe_comment(validated, "pr")
        self.assertIn("target=issue", issue_body)
        self.assertIn("target=pr", pr_body)
        self.assertIn("model invocation: `not performed`", issue_body)
        self.assertIn("Provider/profile/backend/architecture:", issue_body)
        self.assertIn("VM created at:", issue_body)
        self.assertIn("Profile/runtime-data absence read-back:", issue_body)
        self.assertIn("2026-08-28T00:04:30Z", issue_body)
        self.assertIn("does not consume or replace the distinct live runtime receipt", issue_body)
        self.assertNotRegex(issue_body + pr_body, r"/Users/|/var/folders/|/tmp/")
        self.assertIsNone(self.receipt.MARKER.search(issue_body))
        live_marker = self.receipt.receipt_marker({
            "attempt_id": "ATTEMPT-0123456789abcdef",
            "schema": "runtime-receipt/v1",
        })
        self.assertIsNone(self.receipt.PROBE_MARKER.search(live_marker))
        with mock.patch.object(
            self.receipt, "existing_comments",
            return_value=[{"html_url": "unused", "body": issue_body}],
        ):
            self.assertIsNone(self.receipt.preflight_existing_receipt(
                {"attempt_id": "ATTEMPT-0123456789abcdef"}, "live-body"
            ))
        with mock.patch.object(
            self.receipt, "lifecycle_existing_comments",
            return_value=[{"html_url": "unused", "body": live_marker}],
        ):
            self.assertIsNone(self.receipt.preflight_existing_probe_receipt(
                validated, "issue", issue_body
            ))

    def test_stage_a_probe_rejects_auth_live_artifacts_lanes_destroy_and_stale_checks(self):
        mutations = (
            lambda value: value["runtime_profile"]["auth"].__setitem__("class", "signed-in-client"),
            lambda value: value["runtime_profile"].__setitem__("live_run_allowed", True),
            lambda value: value["probe_execution"].__setitem__("device_auth_performed", True),
            lambda value: value["probe_execution"].__setitem__("model_invocation_performed", True),
            lambda value: value["probe_execution"].__setitem__("live_worker_started", True),
            lambda value: value.__setitem__("execution_result", {"status": "pass"}),
            lambda value: value["runtime_profile"]["evidence"]["lane_statuses"].__setitem__("config_status", "fail"),
            lambda value: value["runtime_profile"]["evidence"]["lane_statuses"].__setitem__("auth_status", "pass"),
            lambda value: value["destroy"].__setitem__("destroy_completed", False),
            lambda value: value["destroy"].__setitem__("profile_absence_readback", "present"),
            lambda value: value["destroy"].pop("runtime_data_absence_observed_at"),
            lambda value: value["checks"][0].__setitem__("head", "f" * 40),
            lambda value: value["checks"][1].__setitem__("result", "failure"),
            lambda value: value["task"].__setitem__("issue", 23.0),
            lambda value: value["pull_request"].__setitem__("number", 24.0),
            lambda value: value["probe_execution"].__setitem__("probe_only", 1),
            lambda value: value["privacy"].__setitem__("allowlisted_projection", 1),
        )
        for mutation in mutations:
            fixture = self.probe_fixture()
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(lambda f=fixture: self.validate_probe(f))

    def test_stage_a_probe_rejects_raw_output_private_data_and_bad_chronology(self):
        for key, value in (
            ("raw_argv", ["codex", "exec"]),
            ("stderr", "Logged in using ChatGPT"),
            ("transcript", "redacted"),
            ("local_path", "/Users/alice/private"),
        ):
            fixture = self.probe_fixture()
            fixture[key] = value
            with self.subTest(key=key):
                self.assert_receipt_error(lambda f=fixture: self.validate_probe(f))
        fixture = self.probe_fixture()
        fixture["destroy"]["destroy_requested_at"] = "2026-08-27T23:59:59Z"
        self.assert_receipt_error(lambda: self.validate_probe(fixture), "chronology")
        fixture = self.probe_fixture()
        self.assert_receipt_error(
            lambda: self.validate_probe(
                fixture,
                now=datetime.datetime(2026, 8, 28, 2, 0, tzinfo=datetime.timezone.utc),
            ),
            "stale",
        )

    def test_stage_a_probe_marker_is_idempotent_and_duplicate_or_conflict_closed(self):
        receipt = self.validate_probe()
        for target, url in (
            ("issue", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-991"),
            ("pr", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-992"),
        ):
            body = self.receipt.render_probe_comment(receipt, target)
            comment = {"html_url": url, "body": body}
            with self.subTest(target=target), mock.patch.object(
                self.receipt, "lifecycle_existing_comments", return_value=[comment]
            ):
                self.assertEqual(
                    url,
                    self.receipt.preflight_existing_probe_receipt(
                        receipt, target, body
                    ),
                )
            duplicate = copy.deepcopy(comment)
            duplicate["body"] = body + "\n" + self.receipt.probe_marker(receipt, target)
            with mock.patch.object(
                self.receipt, "lifecycle_existing_comments", return_value=[duplicate]
            ):
                self.assert_receipt_error(
                    lambda t=target, b=body: self.receipt.preflight_existing_probe_receipt(
                        receipt, t, b
                    ),
                    "duplicated",
                )
            conflict = copy.deepcopy(comment)
            conflict["body"] += "\ndrift"
            with mock.patch.object(
                self.receipt, "lifecycle_existing_comments", return_value=[conflict]
            ):
                self.assert_receipt_error(
                    lambda t=target, b=body: self.receipt.preflight_existing_probe_receipt(
                        receipt, t, b
                    ),
                    "conflicts",
                )

    def test_stage_a_probe_apply_reverifies_exact_head_checks_and_posts_both_targets(self):
        receipt = self.validate_probe()
        issue_body = self.receipt.render_probe_comment(receipt, "issue")
        pr_body = self.receipt.render_probe_comment(receipt, "pr")
        targets = [
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-991", False, False),
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-992", True, True),
        ]
        with mock.patch.object(self.receipt, "verify_external_head") as verify_head, \
             mock.patch.object(self.receipt, "apply_one_probe_comment", side_effect=targets) as apply_one, \
             mock.patch.object(self.receipt, "verify_probe_comment_readback") as final_readback:
            result = self.receipt.apply_probe_comments(receipt, issue_body, pr_body)
        self.assertEqual("t11-stage-a-probe-receipt-application/v1", result["schema"])
        self.assertEqual("pass", result["status"])
        self.assertEqual(4, verify_head.call_count)
        self.assertEqual(["issue", "pr"], [call.args[1] for call in apply_one.call_args_list])
        self.assertEqual([
            mock.call(targets[0][0], "issue", issue_body),
            mock.call(targets[1][0], "pr", pr_body),
        ], final_readback.call_args_list)
        self.assertEqual({"issue": False, "pr": True}, result["idempotent_targets"])
        self.assertEqual({"issue": False, "pr": True}, result["reconciled_after_uncertain_post"])

        with mock.patch.object(
            self.receipt, "verify_external_head",
            side_effect=self.receipt.ReceiptError("required check results are stale"),
        ) as verify_head, mock.patch.object(self.receipt, "apply_one_probe_comment") as post:
            self.assert_receipt_error(
                lambda: self.receipt.apply_probe_comments(receipt, issue_body, pr_body),
                "stale",
            )
        verify_head.assert_called_once()
        post.assert_not_called()

    def test_stage_a_probe_final_dual_readback_fails_closed_on_late_drift(self):
        receipt = self.validate_probe()
        issue_body = self.receipt.render_probe_comment(receipt, "issue")
        pr_body = self.receipt.render_probe_comment(receipt, "pr")
        targets = [
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-991", False, False),
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-992", False, False),
        ]
        with mock.patch.object(self.receipt, "verify_external_head"), \
             mock.patch.object(self.receipt, "apply_one_probe_comment", side_effect=targets), \
             mock.patch.object(
                 self.receipt, "verify_probe_comment_readback",
                 side_effect=self.receipt.ReceiptError("late durable copy drift"),
             ):
            self.assert_receipt_error(
                lambda: self.receipt.apply_probe_comments(receipt, issue_body, pr_body),
                "late durable copy drift",
            )

    def test_stage_a_probe_uncertain_post_reconciles_without_duplicate(self):
        receipt = self.validate_probe()
        body = self.receipt.render_probe_comment(receipt, "issue")
        url = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-991"
        with mock.patch.object(
            self.receipt, "preflight_existing_probe_receipt",
            side_effect=[None, url],
        ), mock.patch.object(
            self.receipt, "run_gh", side_effect=self.receipt.ReceiptError("uncertain")
        ):
            self.assertEqual(
                (url, True, True),
                self.receipt.apply_one_probe_comment(receipt, "issue", body),
            )

    def test_stage_a_probe_apply_capability_gate_precedes_input_and_github(self):
        with mock.patch.object(
            self.receipt, "require_runtime_fs_capabilities",
            side_effect=self.receipt.ReceiptError("capability gate"),
        ) as gate, mock.patch.object(self.receipt, "read_stdin_bounded") as read_input, \
             mock.patch.object(self.receipt, "run_gh") as github:
            with mock.patch.object(sys, "stdout", mock.Mock(buffer=mock.Mock())):
                self.assertEqual(1, self.receipt.main(["--probe-apply"]))
        gate.assert_called_once()
        read_input.assert_not_called()
        github.assert_not_called()

    def test_stage_a_probe_dry_run_cli_emits_both_canonical_target_copies(self):
        receipt = self.validate_probe()
        stdout = mock.Mock(buffer=io.BytesIO())
        with mock.patch.object(self.receipt, "read_stdin_bounded", return_value=b"{}"), \
             mock.patch.object(self.receipt, "decode_json_object", return_value={}), \
             mock.patch.object(self.receipt, "validate_probe_receipt", return_value=receipt), \
             mock.patch.object(sys, "stdout", stdout):
            self.assertEqual(0, self.receipt.main(["--probe-dry-run"]))
        payload = json.loads(stdout.buffer.getvalue())
        self.assertEqual("t11-stage-a-probe-receipt-dry-run/v1", payload["schema"])
        self.assertEqual(
            self.receipt.render_probe_comment(receipt, "issue"), payload["issue_body"]
        )
        self.assertEqual(
            self.receipt.render_probe_comment(receipt, "pr"), payload["pr_body"]
        )

    def test_stage_a_probe_real_adapter_cli_dry_run_accepts_current_request(self):
        fixture = self.probe_fixture()
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        profile = fixture["runtime_profile"]
        provider = profile["evidence"]["containment_provider"]
        control = provider["control_plane"]

        def stamp(seconds):
            return (now - datetime.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

        provider["created_at"] = stamp(300)
        control["pre_create_observed_at"] = stamp(330)
        control["post_create_observed_at"] = stamp(270)
        normalized = {
            key: value for key, value in control.items()
            if key != "normalized_control_plane_sha256"
        }
        control["normalized_control_plane_sha256"] = self.receipt.sha256(
            self.receipt.canonical_bytes(normalized)
        )
        profile["observed_at"] = stamp(210)
        fixture["chronology"] = {
            "probe_started_at": stamp(240),
            "probe_completed_at": stamp(180),
        }
        fixture["destroy"].update({
            "destroy_requested_at": stamp(150),
            "destroy_completed_at": stamp(120),
            "profile_absence_observed_at": stamp(60),
            "runtime_data_absence_observed_at": stamp(30),
        })
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--probe-dry-run"],
            cwd=ROOT,
            input=self.receipt.canonical_bytes(fixture),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("t11-stage-a-probe-receipt-dry-run/v1", payload["schema"])
        self.assertEqual("pass", payload["status"])
        self.assertIn("target=issue", payload["issue_body"])
        self.assertIn("target=pr", payload["pr_body"])

        for mutation in ("pre-after-create", "probe-before-post-create"):
            invalid = copy.deepcopy(fixture)
            invalid_provider = invalid["runtime_profile"]["evidence"]["containment_provider"]
            invalid_control = invalid_provider["control_plane"]
            if mutation == "pre-after-create":
                invalid_control["pre_create_observed_at"] = stamp(290)
            else:
                invalid["chronology"]["probe_started_at"] = stamp(280)
            normalized = {
                key: value for key, value in invalid_control.items()
                if key != "normalized_control_plane_sha256"
            }
            invalid_control["normalized_control_plane_sha256"] = self.receipt.sha256(
                self.receipt.canonical_bytes(normalized)
            )
            rejected = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--probe-dry-run"],
                cwd=ROOT,
                input=self.receipt.canonical_bytes(invalid),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            with self.subTest(mutation=mutation):
                self.assertNotEqual(0, rejected.returncode)
                self.assertNotIn(b"Traceback", rejected.stdout + rejected.stderr)

    def test_lifecycle_receipt_dry_run_is_closed_canonical_and_dual_target(self):
        fixture = self.lifecycle_fixture()
        current = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        fixture["destroy"].update({
            "destroy_requested_at": (current - datetime.timedelta(seconds=180)).isoformat().replace("+00:00", "Z"),
            "destroy_completed_at": (current - datetime.timedelta(seconds=120)).isoformat().replace("+00:00", "Z"),
            "profile_absence_observed_at": (current - datetime.timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
            "runtime_data_absence_observed_at": current.isoformat().replace("+00:00", "Z"),
        })
        validated = self.receipt.validate_lifecycle_receipt(
            copy.deepcopy(fixture), now=current
        )
        self.assertNotIn("request", validated["runtime_receipt"])
        self.assertEqual(
            "runtime-receipt/v1", validated["runtime_receipt"]["record"]["schema"]
        )
        self.assertEqual(
            self.receipt.sha256(
                self.receipt.canonical_bytes(fixture["runtime_receipt"]["request"])
            ),
            validated["runtime_receipt"]["request_sha256"],
        )
        issue_body = self.receipt.render_lifecycle_comment(validated, "issue")
        pr_body = self.receipt.render_lifecycle_comment(validated, "pr")
        self.assertIn("target=issue", issue_body)
        self.assertIn("target=pr", pr_body)
        self.assertIn("final-destroy evidence", issue_body)
        self.assertNotRegex(issue_body + pr_body, r"/Users/|/var/folders/|/tmp/")
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--lifecycle-dry-run"], cwd=ROOT,
            input=self.receipt.canonical_bytes(fixture), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("t11-colima-lifecycle-receipt-dry-run/v1", payload["schema"])
        self.assertEqual(issue_body, payload["issue_body"])
        self.assertEqual(pr_body, payload["pr_body"])

    def test_lifecycle_receipt_rejects_forgery_scope_and_destroy_drift(self):
        mutations = (
            lambda value: value.__setitem__("authority", "codex-authored"),
            lambda value: value.__setitem__("codex_authenticated_attestation", True),
            lambda value: value["pull_request"].update({"number": 25, "url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/25"}),
            lambda value: value["provider"].__setitem__("profile_name", "t11-e2e-ffffffffffff-01"),
            lambda value: value["provider"].__setitem__("vm_instance_identity_sha256", "0" * 64),
            lambda value: value["checks"][0].__setitem__("head", "f" * 40),
            lambda value: value["destroy"].__setitem__("destroy_completed", False),
            lambda value: value["destroy"].__setitem__("profile_absence_readback", "present"),
            lambda value: value["destroy"].__setitem__("destroy_completed_at", "2026-08-28T00:00:00Z"),
            lambda value: value["runtime_receipt"].__setitem__("posted_at", "2026-08-28T00:01:01Z"),
            lambda value: value["runtime_receipt"]["request"]["pull_request"].__setitem__("tree", "f" * 40),
            lambda value: value["privacy"].__setitem__("raw_mount_inventory", True),
        )
        for mutation in mutations:
            fixture = self.lifecycle_fixture()
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(
                    lambda f=fixture: self.receipt.validate_lifecycle_receipt(
                        f, now=self.fixture_now()
                    )
                )

    def test_lifecycle_receipt_rejects_future_and_stale_destroy_evidence(self):
        future_mutations = (
            lambda value: value["runtime_receipt"].__setitem__("posted_at", "2099-01-01T00:00:00Z"),
            lambda value: value["destroy"].__setitem__("destroy_requested_at", "2099-01-01T00:00:00Z"),
            lambda value: value["destroy"].__setitem__("destroy_completed_at", "2099-01-01T00:00:00Z"),
            lambda value: value["destroy"].__setitem__("profile_absence_observed_at", "2099-01-01T00:00:00Z"),
            lambda value: value["destroy"].__setitem__("runtime_data_absence_observed_at", "2099-01-01T00:00:00Z"),
        )
        for mutation in future_mutations:
            fixture = self.lifecycle_fixture()
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(
                    lambda f=fixture: self.receipt.validate_lifecycle_receipt(
                        f, now=self.fixture_now()
                    ),
                    "future-dated",
                )

        stale = self.lifecycle_fixture()
        self.assert_receipt_error(
            lambda: self.receipt.validate_lifecycle_receipt(
                stale,
                now=datetime.datetime(2026, 8, 28, 2, 5, tzinfo=datetime.timezone.utc),
            ),
            "stale",
        )

        at_limit = self.lifecycle_fixture()
        validated = self.receipt.validate_lifecycle_receipt(
            at_limit,
            now=datetime.datetime(2026, 8, 28, 1, 4, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual("t11-colima-lifecycle-receipt/v1", validated["schema"])

    def test_lifecycle_receipt_rejects_private_raw_or_secret_material(self):
        for key, value in (
            ("raw_mounts", ["/Users/alice/private"]),
            ("provider_configuration", {"path": "redacted"}),
            ("credential", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"),
        ):
            fixture = self.lifecycle_fixture()
            fixture[key] = value
            with self.subTest(key=key):
                self.assert_receipt_error(
                    lambda f=fixture: self.receipt.validate_lifecycle_receipt(
                        f, now=self.fixture_now()
                    )
                )

    def test_linked_runtime_receipt_requires_exact_marker_body_and_provider_bindings(self):
        lifecycle = self.receipt.validate_lifecycle_receipt(
            self.lifecycle_fixture(), now=self.fixture_now()
        )
        runtime = self.receipt.validate_receipt(copy.deepcopy(self.fixture), now=self.fixture_now())
        body = self.receipt.render_comment(runtime)
        linked = {
            "html_url": lifecycle["runtime_receipt"]["comment_url"],
            "created_at": lifecycle["runtime_receipt"]["posted_at"],
            "body": body,
        }
        with mock.patch.object(self.receipt, "gh_json", return_value=linked):
            self.receipt.verify_linked_runtime_receipt(lifecycle)
        wrong_time = dict(linked)
        wrong_time["created_at"] = "2026-08-28T00:00:31Z"
        with mock.patch.object(self.receipt, "gh_json", return_value=wrong_time):
            self.assert_receipt_error(
                lambda: self.receipt.verify_linked_runtime_receipt(lifecycle)
            )
        for mutated in (
            body + "\ndrift",
            body.replace(lifecycle["provider"]["vm_instance_identity_sha256"], "f" * 64),
            body.replace(lifecycle["provider"]["normalized_control_plane_sha256"], "f" * 64),
        ):
            with self.subTest(mutated=mutated[-12:]), mock.patch.object(
                self.receipt, "gh_json", return_value={
                    "html_url": linked["html_url"],
                    "created_at": linked["created_at"],
                    "body": mutated,
                }
            ):
                self.assert_receipt_error(
                    lambda: self.receipt.verify_linked_runtime_receipt(lifecycle)
                )

        marker_only_forgery = "\n".join((
            self.receipt.receipt_marker(runtime),
            "## forged runtime receipt",
            "`{}`".format(lifecycle["provider"]["profile_name"]),
            "`{}`".format(lifecycle["provider"]["vm_instance_identity_sha256"]),
            "`{}`".format(lifecycle["provider"]["normalized_control_plane_sha256"]),
        ))
        with mock.patch.object(self.receipt, "gh_json", return_value={
            "html_url": linked["html_url"],
            "created_at": linked["created_at"],
            "body": marker_only_forgery,
        }):
            self.assert_receipt_error(
                lambda: self.receipt.verify_linked_runtime_receipt(lifecycle),
                "canonical",
            )

    def test_lifecycle_markers_are_target_stable_idempotent_and_conflict_closed(self):
        lifecycle = self.receipt.validate_lifecycle_receipt(
            self.lifecycle_fixture(), now=self.fixture_now()
        )
        for target, url in (
            ("issue", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-901"),
            ("pr", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-902"),
        ):
            body = self.receipt.render_lifecycle_comment(lifecycle, target)
            comments = [{"html_url": url, "body": body}]
            with self.subTest(target=target), mock.patch.object(
                self.receipt, "lifecycle_existing_comments", return_value=comments
            ):
                self.assertEqual(
                    url,
                    self.receipt.preflight_existing_lifecycle_receipt(
                        lifecycle, target, body
                    ),
                )
                conflict = copy.deepcopy(comments)
                conflict[0]["body"] += "\ndrift"
                with mock.patch.object(
                    self.receipt, "lifecycle_existing_comments", return_value=conflict
                ):
                    self.assert_receipt_error(
                        lambda: self.receipt.preflight_existing_lifecycle_receipt(
                            lifecycle, target, body
                        ),
                        "conflicts",
                    )

    def test_lifecycle_apply_posts_both_targets_and_reverifies(self):
        lifecycle = self.receipt.validate_lifecycle_receipt(
            self.lifecycle_fixture(), now=self.fixture_now()
        )
        issue_body = self.receipt.render_lifecycle_comment(lifecycle, "issue")
        pr_body = self.receipt.render_lifecycle_comment(lifecycle, "pr")
        targets = [
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-901", False, False),
            ("https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-902", True, False),
        ]
        with mock.patch.object(self.receipt, "verify_external_head") as verify_head, \
             mock.patch.object(self.receipt, "verify_linked_runtime_receipt") as verify_linked, \
             mock.patch.object(self.receipt, "apply_one_lifecycle_comment", side_effect=targets) as apply_one:
            result = self.receipt.apply_lifecycle_comments(lifecycle, issue_body, pr_body)
        self.assertEqual("pass", result["status"])
        self.assertEqual(3, verify_head.call_count)
        self.assertEqual(3, verify_linked.call_count)
        self.assertEqual(["issue", "pr"], [call.args[1] for call in apply_one.call_args_list])
        self.assertEqual({"issue": False, "pr": True}, result["idempotent_targets"])

    def test_lifecycle_target_post_uses_body_file_and_exact_readback(self):
        lifecycle = self.receipt.validate_lifecycle_receipt(
            self.lifecycle_fixture(), now=self.fixture_now()
        )
        for target, url, command in (
            ("issue", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/23#issuecomment-901", "issue"),
            ("pr", "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/24#issuecomment-902", "pr"),
        ):
            body = self.receipt.render_lifecycle_comment(lifecycle, target)
            with self.subTest(target=target), \
                 mock.patch.object(self.receipt, "preflight_existing_lifecycle_receipt", return_value=None), \
                 mock.patch.object(self.receipt, "run_gh", return_value=(url + "\n").encode()) as run_gh, \
                 mock.patch.object(self.receipt, "gh_json", return_value={"html_url": url, "body": body}):
                observed = self.receipt.apply_one_lifecycle_comment(
                    lifecycle, target, body
                )
            self.assertEqual((url, False, False), observed)
            self.assertEqual(command, run_gh.call_args.args[0][0])
            self.assertIn("--body-file", run_gh.call_args.args[0])
            self.assertEqual(body.encode("utf-8"), run_gh.call_args.args[1])

    def test_lifecycle_apply_capability_gate_precedes_input_and_github(self):
        with mock.patch.object(
            self.receipt, "require_runtime_fs_capabilities",
            side_effect=self.receipt.ReceiptError("capability gate"),
        ) as gate, mock.patch.object(self.receipt, "read_stdin_bounded") as read_input, \
             mock.patch.object(self.receipt, "run_gh") as github:
            with mock.patch.object(sys, "stdout", mock.Mock(buffer=mock.Mock())):
                self.assertEqual(1, self.receipt.main(["--lifecycle-apply"]))
        gate.assert_called_once()
        read_input.assert_not_called()
        github.assert_not_called()


if __name__ == "__main__":
    unittest.main()
