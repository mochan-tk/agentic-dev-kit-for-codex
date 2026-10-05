"""Check authored teaching fixtures; never run or grade a model."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "docs/evaluation-fixtures"


class EvaluationFixtureTests(unittest.TestCase):
    def load(self, case):
        return json.loads((PACK / case.lower() / "input.json").read_text())

    def oracle(self, case):
        return json.loads((PACK / "oracles.json").read_text())["cases"][case]

    def assert_packet(self, packet):
        self.assertTrue({"format", "case_id", "case_version", "evidence_class", "evaluation_status",
                         "operation", "allowed_writes", "current_head", "runs", "source_files"} <= packet.keys())
        self.assertEqual("synthetic-ci-diagnosis-input/v1", packet["format"])
        self.assertIn(packet["case_id"], ("EC05", "EC06"))
        self.assertEqual(1, packet["case_version"])
        self.assertEqual("synthetic", packet["evidence_class"])
        self.assertEqual("NOT_RUN", packet["evaluation_status"])
        self.assertEqual("diagnosis_only", packet["operation"])
        self.assertEqual([], packet["allowed_writes"])
        runs = packet["runs"]
        for item in runs:
            self.assertTrue({"run_id", "head", "attempt", "conclusion", "steps", "tests"} <= item.keys())
        self.assertEqual(len(runs), len({run["run_id"] for run in runs}))
        current = [run for run in runs if run["head"] == packet["current_head"]]
        self.assertEqual(1, len(current))
        run = current[0]
        self.assertTrue(run["run_id"].startswith("synthetic-"))
        self.assertTrue(run["head"].startswith("synthetic-"))
        self.assertEqual("failure", run["conclusion"])
        self.assertGreater(run["attempt"], 0)
        if packet["case_id"] == "EC05":
            self.assertEqual(1, len(runs))
            self.assertEqual([("required_host", "failure"), ("product_tests", "skipped")],
                             [(step["name"], step["conclusion"]) for step in run["steps"]])
            self.assertEqual({"status": "not_started", "total": None, "failures": None}, run["tests"])
            self.assertEqual("pwsh", run["steps"][0]["required_tool"])
            self.assertEqual(127, run["steps"][0]["exit_code"])
            self.assertEqual([], packet["source_files"])
        else:
            self.assertEqual(2, len(runs))
            older = [item for item in runs if item != run][0]
            self.assertNotEqual(packet["current_head"], older["head"])
            self.assertEqual("success", older["conclusion"])
            self.assertEqual([("required_host", "success"), ("product_tests", "failure")],
                             [(step["name"], step["conclusion"]) for step in run["steps"]])
            self.assertEqual({"status": "completed", "total": 2, "failures": 1}, run["tests"])
            self.assertEqual({"test": "test_report.ReportTests.test_whitespace_only",
                              "input": ["   "], "expected": 0, "actual": 1}, run["assertion"])
        return run

    def test_packets_and_oracles_are_versioned_bound_and_unrun(self):
        oracles = json.loads((PACK / "oracles.json").read_text())
        self.assertEqual("synthetic-ci-diagnosis-oracles/v1", oracles["format"])
        self.assertEqual({"EC05", "EC06"}, set(oracles["cases"]))
        self.assertEqual("PENDING", oracles["human_trial_approval"])
        for case in ("EC05", "EC06"):
            with self.subTest(case=case):
                packet = self.load(case)
                run = self.assert_packet(packet)
                oracle = self.oracle(case)
                self.assertEqual(packet["case_version"], oracle["case_version"])
                self.assertEqual(hashlib.sha256((PACK / case.lower() / "input.json").read_bytes()).hexdigest(),
                                 oracle["input_sha256"])
                self.assertEqual({key: run[key] for key in ("head", "run_id", "attempt")}, oracle["binding"])
                self.assertEqual("NOT_RUN", oracle["evaluation_status"])
                criteria = oracle["criteria"]
                self.assertEqual(4, len(criteria))
                self.assertEqual(4, len({entry["id"] for entry in criteria}))
                for entry in criteria:
                    self.assertTrue(entry["required"])
                    self.assertTrue(entry["observation"])
                    self.assertTrue(entry["evidence_needed"])

    def test_ec06_source_inventory_matches_actual_bytes(self):
        packet = self.load("EC06")
        self.assertEqual({"report.py", "test_report.py"}, {item["path"] for item in packet["source_files"]})
        self.assertEqual(2, len(packet["source_files"]))
        for item in packet["source_files"]:
            self.assertEqual(hashlib.sha256((PACK / "ec06" / item["path"]).read_bytes()).hexdigest(), item["sha256"])

    def test_behavioral_oracle_uses_independent_character_rule(self):
        spec = importlib.util.spec_from_file_location("seeded_report", PACK / "ec06/report.py")
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        mismatches = []
        for index, example in enumerate(self.oracle("EC06")["behavioral_examples"]):
            lines = example["input"]
            before = list(lines)
            # Independent of the seed's truthiness predicate and proposed strip fix.
            expected = len([line for line in lines if any(not char.isspace() for char in line)])
            self.assertEqual(expected, example["expected"])
            if seed.count_nonblank(lines) != expected:
                mismatches.append(index)
            self.assertEqual(before, lines)
        self.assertEqual([1, 3], mismatches)

    def run_seed(self, directory):
        return subprocess.run([sys.executable, "-I", "-B", "-m", "unittest", "discover",
                               "-s", str(directory), "-p", "test_report.py", "-v"],
                              cwd=directory, capture_output=True, text=True, timeout=20)

    def assert_seeded_failure(self, result):
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("test_empty (test_report.ReportTests.test_empty) ... ok", result.stderr)
        self.assertIn("FAIL: test_whitespace_only (test_report.ReportTests.test_whitespace_only)", result.stderr)
        self.assertIn("AssertionError: 0 != 1", result.stderr)
        self.assertIn("Ran 2 tests", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_seeded_assertion_is_reproducible_without_external_services(self):
        self.assert_seeded_failure(self.run_seed(PACK / "ec06"))

    def test_removing_seeded_defect_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="ci-teaching-fixture-") as directory:
            root = Path(directory)
            shutil.copyfile(PACK / "ec06/test_report.py", root / "test_report.py")
            source = (PACK / "ec06/report.py").read_text()
            self.assertIn("bool(line)", source)
            (root / "report.py").write_text(source.replace("bool(line)", "bool(line.strip())"))
            result = self.run_seed(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            with self.assertRaises(AssertionError):
                self.assert_seeded_failure(result)

    def test_bad_packet_states_are_detected(self):
        mutations = (
            ("EC05", lambda p: p.pop("current_head")),
            ("EC05", lambda p: p["runs"][0].pop("run_id")),
            ("EC05", lambda p: p.update(case_version=2)),
            ("EC05", lambda p: p.update(evaluation_status="PASS")),
            ("EC05", lambda p: p.update(allowed_writes=["workflow.yml"])),
            ("EC05", lambda p: p["runs"][0]["tests"].update(total=0)),
            ("EC05", lambda p: p["runs"][0]["steps"][1].update(conclusion="success")),
            ("EC06", lambda p: p.update(current_head=p["runs"][0]["head"])),
            ("EC06", lambda p: p["runs"][1]["steps"][0].update(conclusion="failure")),
            ("EC06", lambda p: p["runs"][1]["assertion"].update(actual=0)),
        )
        for index, (case, mutate) in enumerate(mutations):
            with self.subTest(index=index, case=case):
                packet = copy.deepcopy(self.load(case))
                mutate(packet)
                with self.assertRaises(AssertionError):
                    self.assert_packet(packet)

    def test_packet_byte_drift_breaks_oracle_binding(self):
        for case in ("EC05", "EC06"):
            original = (PACK / case.lower() / "input.json").read_bytes()
            digest = self.oracle(case)["input_sha256"]
            self.assertEqual(digest, hashlib.sha256(original).hexdigest())
            self.assertNotEqual(digest, hashlib.sha256(original + b"\n").hexdigest())

    def test_documented_boundaries_and_navigation_are_checked(self):
        spec = importlib.util.spec_from_file_location("evaluation_product", ROOT / ".github/scripts/check-product.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertIn("test_evaluation_fixtures.py", checker.TEST_MODULES)
        self.assertIn("docs/evaluation-fixtures/README.md", checker.PUBLIC_DOCS)
        self.assertEqual([], checker.validate_navigation(ROOT))
        guide = (PACK / "README.md").read_text()
        for token in ("NOT_RUN", "synthetic", "not secret holdouts", "separate authorization",
                      "UNCHECKABLE", "UNKNOWN", "not an agent grader", "no model",
                      "test_evaluation_fixtures.py"):
            self.assertIn(token, guide)
        for path in ("docs/evaluation-cases.md", "docs/evidence-status.md"):
            self.assertIn("evaluation-fixtures/README.md", (ROOT / path).read_text())


if __name__ == "__main__":
    unittest.main()
