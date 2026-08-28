import copy
import datetime
import importlib.util
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

    def refresh_artifact_chain(self, fixture, observed_at):
        artifacts = fixture["artifacts"]
        profile = artifacts["runtime_profile"]
        envelope = artifacts["envelope"]
        result = artifacts["execution_result"]
        verifier = artifacts["verifier"]
        profile["observed_at"] = observed_at
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
            lambda value: value["pull_request"].__setitem__("head", "short"),
            lambda value: value["artifacts"]["envelope"]["harness"].__setitem__("commit", "f" * 40),
            lambda value: value["artifacts"]["runtime_profile"].__setitem__("status", "UNKNOWN"),
            lambda value: value["artifacts"]["verifier"].__setitem__("status", "UNKNOWN"),
            lambda value: value["artifacts"]["execution_result"]["git"]["changed_paths"].append("other.txt"),
        )
        for mutation in mutations:
            fixture = copy.deepcopy(self.fixture)
            mutation(fixture)
            with self.subTest(mutation=mutation):
                self.assert_receipt_error(lambda f=fixture: self.receipt.validate_receipt(f, now=self.fixture_now()))

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
                "conflicts",
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


if __name__ == "__main__":
    unittest.main()
