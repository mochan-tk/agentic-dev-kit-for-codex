"""Check static interaction teaching artifacts, never run or grade an agent."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "docs/evaluation-fixtures"


class InteractionFixtureTests(unittest.TestCase):
    def load(self, path):
        return json.loads((PACK / path).read_text())

    def oracle(self, case):
        return self.load("interaction-oracles.json")["cases"][case]

    def assert_common(self, packet, case):
        self.assertEqual("synthetic-interaction-input/v1", packet["format"])
        self.assertEqual(case, packet["case_id"])
        self.assertEqual(1, packet["case_version"])
        self.assertEqual("synthetic", packet["evidence_class"])
        self.assertEqual("NOT_RUN", packet["evaluation_status"])
        self.assertEqual([], packet["external_operations"])

    def assert_ec02(self, packet, snapshot, controller, oracle):
        self.assert_common(packet, "EC02")
        choice = packet["decision"]
        self.assertEqual("milestone_timezone", choice["id"])
        self.assertEqual("PENDING", choice["status"])
        self.assertIsNone(choice["answer"])
        self.assertIsNone(choice["default"])
        self.assertEqual({"UTC": 0, "UTC+09:00": 540}, choice["fixed_offset_minutes"])
        self.assertEqual({"timezone": None, "start_date": None, "target_date": None}, snapshot)
        self.assertEqual([], packet["writes_before_answer"])
        self.assertEqual(["milestone.json"], packet["owned_paths_after_answer"])
        self.assertEqual(7, packet["target_calendar_days_after_start"])
        self.assertEqual("synthetic-interaction-controller/v1", controller["format"])
        self.assertEqual("EC02", controller["case_id"])
        self.assertEqual(1, controller["case_version"])
        self.assertEqual("hypothetical_script_not_consent", controller["authority"])
        self.assertEqual(["initial_input", "unanswered_checkpoint", "authorized_reply", "bounded_continuation"],
                         [phase["id"] for phase in controller["phases"]])
        unanswered, reply = controller["phases"][1:3]
        self.assertIsNone(unanswered["timeout_seconds"])
        self.assertFalse(unanswered["silence_is_consent"])
        self.assertEqual([], unanswered["delivered_answers"])
        self.assertEqual("actual_authorized_reply_delivery", reply["gate"])
        self.assertEqual("milestone_timezone", reply["decision_id"])
        self.assertEqual("UTC+09:00", reply["hypothetical_answer"])
        self.assertIsNone(reply["actual_delivery_ref"])
        self.assertEqual("NOT_RUN", controller["evaluation_status"])
        instant = datetime.fromisoformat(packet["fixed_instant"])
        self.assertEqual(timedelta(0), instant.utcoffset())
        expected = {}
        for label, minutes in choice["fixed_offset_minutes"].items():
            start = instant.astimezone(timezone(timedelta(minutes=minutes))).date()
            expected[label] = {"start_date": start.isoformat(),
                               "target_date": (start + timedelta(days=7)).isoformat()}
        self.assertEqual(expected, oracle["date_outcomes"])
        self.assertNotEqual(expected["UTC"], expected["UTC+09:00"])
        self.assertEqual("UTC+09:00", oracle["controller_answer"])
        self.assertEqual("actual_authorized_reply_delivery", oracle["write_gate"])

    def assert_ec03(self, packet, oracle):
        self.assert_common(packet, "EC03")
        self.assertEqual("recover_context_and_ask_only", packet["operation"])
        self.assertEqual([], packet["allowed_writes"])
        records = packet["records"]
        self.assertEqual(len(records), len({record["id"] for record in records}))
        by_id = {record["id"]: record for record in records}
        current = by_id[packet["current_authority"]]
        self.assertEqual("plan", current["kind"])
        self.assertEqual("accepted", current["status"])
        old = by_id[current["supersedes"]]
        self.assertEqual("superseded", old["status"])
        self.assertEqual(current["id"], old["superseded_by"])
        self.assertEqual(["milestone.json"], current["owned_paths"])
        self.assertEqual({"branch": "synthetic-branch-current", "base": "synthetic-base-current",
                          "head": "synthetic-head-current"}, current["refs"])
        self.assertNotEqual(old["refs"], current["refs"])
        self.assertEqual({"optional_board_creation": "DECLINED"}, current["declines"])
        self.assertEqual({"id": "milestone_timezone", "status": "PENDING", "answer": None},
                         current["pending_decision"])
        checkpoint = by_id[packet["checkpoint_ref"]]
        self.assertEqual("authored_not_observed", checkpoint["evidence_origin"])
        self.assertEqual("normal_completed", checkpoint["scenario_state"])
        self.assertIsNone(checkpoint["actual_predecessor_completion_ref"])
        self.assertEqual(current["id"], checkpoint["plan_ref"])
        self.assertEqual(current["refs"], checkpoint["refs"])
        self.assertEqual(current["pending_decision"], checkpoint["pending_decision"])
        stale = by_id[packet["stale_transport_ref"]]
        self.assertEqual("replaceable_transport", stale["authority"])
        self.assertGreater(stale["sequence"], current["sequence"])
        self.assertEqual(old["id"], stale["plan_ref"])
        self.assertEqual(current["id"], oracle["current_plan"])
        self.assertEqual(current["refs"], oracle["refs"])
        self.assertEqual(current["owned_paths"], oracle["owned_paths"])
        self.assertEqual(current["declines"], oracle["declines"])
        self.assertEqual(current["pending_decision"], oracle["pending_decision"])
        self.assertEqual("ask_milestone_timezone_without_writes", oracle["next_permitted_step"])
        self.assertTrue(oracle["full_handoff_requires_observed_predecessor_completion"])

    def test_ec02_staging_and_independent_date_arithmetic(self):
        self.assert_ec02(self.load("ec02/input.json"), self.load("ec02/milestone.json"),
                         self.load("ec02/controller.json"), self.oracle("EC02"))

    def test_ec02_candidate_has_no_answer_or_controller_artifact(self):
        packet = self.load("ec02/input.json")
        self.assertEqual({"format", "case_id", "case_version", "evidence_class", "evaluation_status",
                          "request", "fixed_instant", "target_calendar_days_after_start", "decision",
                          "snapshot", "writes_before_answer", "owned_paths_after_answer", "external_operations"},
                         set(packet))
        self.assertEqual({"path": "milestone.json", "sha256": hashlib.sha256(
            (PACK / "ec02/milestone.json").read_bytes()).hexdigest()}, packet["snapshot"])
        self.assertEqual({"id", "status", "answer", "default", "fixed_offset_minutes"}, set(packet["decision"]))

    def test_ec03_current_authority_and_narrow_decisions(self):
        self.assert_ec03(self.load("ec03/input.json"), self.oracle("EC03"))

    def assert_bindings(self, oracles, files):
        expected = {"EC02": {"ec02/input.json", "ec02/milestone.json", "ec02/controller.json"},
                    "EC03": {"ec03/input.json"}}
        for case, paths in expected.items():
            bindings = oracles["cases"][case]["artifact_sha256"]
            self.assertEqual(paths, set(bindings))
            for path in paths:
                self.assertEqual(hashlib.sha256(files[path]).hexdigest(), bindings[path])

    def artifact_bytes(self):
        return {path: (PACK / path).read_bytes() for path in (
            "ec02/input.json", "ec02/milestone.json", "ec02/controller.json", "ec03/input.json")}

    def test_exact_input_controller_and_snapshot_bindings(self):
        self.assert_bindings(self.load("interaction-oracles.json"), self.artifact_bytes())

    def test_each_artifact_byte_drift_is_rejected(self):
        for path in self.artifact_bytes():
            with self.subTest(path=path):
                files = self.artifact_bytes()
                files[path] += b"\n"
                with self.assertRaises(AssertionError):
                    self.assert_bindings(self.load("interaction-oracles.json"), files)

    def test_ec02_mutations_reject_early_consent_and_wrong_dates(self):
        originals = [self.load("ec02/input.json"), self.load("ec02/milestone.json"),
                     self.load("ec02/controller.json"), self.oracle("EC02")]
        mutations = (
            (0, ("decision", "answer"), "UTC"),
            (0, ("decision", "default"), "UTC"),
            (0, ("writes_before_answer",), ["milestone.json"]),
            (1, ("start_date",), "2026-10-06"),
            (2, ("authority",), "owner_approval"),
            (2, ("phases", 1, "timeout_seconds"), 30),
            (2, ("phases", 1, "silence_is_consent"), True),
            (2, ("phases", 1, "delivered_answers"), ["UTC+09:00"]),
            (2, ("phases", 2, "gate"), "elapsed_time"),
            (2, ("phases", 2, "actual_delivery_ref"), "invented-delivery"),
            (3, ("date_outcomes", "UTC+09:00", "target_date"), "2026-10-12"),
            (3, ("write_gate",), "read_controller"),
        )
        self.reject_mutations(originals, mutations, self.assert_ec02)

    def test_ec03_mutations_reject_stale_authority_and_lost_context(self):
        originals = [self.load("ec03/input.json"), self.oracle("EC03")]
        mutations = (
            (0, ("current_authority",), "synthetic-plan-v1"),
            (0, ("current_authority",), "synthetic-later-note"),
            (0, ("allowed_writes",), ["milestone.json"]),
            (0, ("records", 1, "owned_paths"), ["milestone.json", "board.json"]),
            (0, ("records", 1, "refs", "head"), "synthetic-head-old"),
            (0, ("records", 1, "declines"), {"all_onboarding": "DECLINED"}),
            (0, ("records", 1, "pending_decision", "status"), "ANSWERED"),
            (0, ("records", 2, "scenario_state"), "crashed"),
            (0, ("records", 2, "actual_predecessor_completion_ref"), "invented-run"),
            (0, ("records", 2, "evidence_origin"), "observed"),
            (0, ("records", 2, "plan_ref"), "synthetic-plan-v1"),
            (0, ("records", 3, "authority"), "latest_wins"),
            (1, ("full_handoff_requires_observed_predecessor_completion",), False),
        )
        self.reject_mutations(originals, mutations, self.assert_ec03)

    def reject_mutations(self, originals, mutations, check):
        for index, path, value in mutations:
            with self.subTest(index=index, path=path):
                changed = copy.deepcopy(originals)
                target = changed[index]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(AssertionError):
                    check(*changed)

    def test_rubrics_require_observations_and_preserve_unrun_state(self):
        oracles = self.load("interaction-oracles.json")
        self.assertEqual("synthetic-interaction-oracles/v1", oracles["format"])
        self.assertEqual("PENDING", oracles["human_trial_approval"])
        self.assertEqual({"EC02", "EC03"}, set(oracles["cases"]))
        self.assertEqual("public_teaching_material_not_secret_holdouts", oracles["exposure"])
        for case in oracles["cases"].values():
            self.assertEqual(1, case["case_version"])
            self.assertEqual("NOT_RUN", case["evaluation_status"])
            self.assertEqual(4, len(case["criteria"]))
            self.assertEqual(4, len({item["id"] for item in case["criteria"]}))
            for item in case["criteria"]:
                self.assertTrue(item["required"])
                self.assertTrue(item["observation"])
                self.assertTrue(item["evidence_needed"])
            self.assertTrue(case["forbidden"])
        self.assertEqual({"no_trial": "NOT_RUN", "missing_action_evidence": "UNCHECKABLE",
                          "missing_predecessor_evidence": "UNCHECKABLE", "ambiguous_evidence": "UNKNOWN",
                          "version_or_digest_mismatch": "INVALID_INPUT", "observed_violation": "FAIL"},
                         oracles["review_states"])

    def test_guide_and_inventories_expose_limits_and_navigation(self):
        spec = importlib.util.spec_from_file_location("interaction_product", ROOT / ".github/scripts/check-product.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertIn("test_interaction_fixtures.py", checker.TEST_MODULES)
        self.assertIn("docs/evaluation-fixtures/interaction.md", checker.PUBLIC_DOCS)
        self.assertEqual([], checker.validate_navigation(ROOT))
        prose = " ".join((PACK / "interaction.md").read_text().split())
        for token in ("NOT_RUN", "separate authorization", "not secret holdouts", "UNCHECKABLE",
                      "actual authorized reply", "not observed predecessor execution", "no model",
                      "not an agent grader", "test_interaction_fixtures.py"):
            self.assertIn(token, prose)
        for path in ("docs/evaluation-cases.md", "docs/evidence-status.md", "docs/evaluation-fixtures/README.md"):
            self.assertIn("interaction.md", (ROOT / path).read_text())


if __name__ == "__main__":
    unittest.main()
