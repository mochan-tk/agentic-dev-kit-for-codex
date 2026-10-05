"""Check reference examples and unrun templates, never score agent behavior."""
import ast
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDES = ("docs/worked-example.md", "docs/evaluation-cases.md")
EXAMPLE = ROOT / "docs/examples/report-summary"


class PublicExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("example_product", ROOT / ".github/scripts/check-product.py")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="public-example-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "kit"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return root

    def test_guides_are_registered_and_reachable(self):
        hub = (ROOT / "docs/evidence-status.md").read_text()
        for guide in GUIDES:
            self.assertIn(guide, self.checker.PUBLIC_DOCS)
            self.assertIn(Path(guide).name, hub)
        self.assertIn("test_public_examples.py", self.checker.TEST_MODULES)
        self.assertEqual([], self.checker.validate_navigation(ROOT))

    def test_guide_missing_links_are_not_ignored(self):
        for guide in GUIDES:
            with self.subTest(guide=guide):
                root = self.fixture()
                target = root / guide
                target.write_text(target.read_text() + "\n[missing](missing-example.md)\n")
                self.assertTrue(self.checker.validate_navigation(root))

    def test_reference_production_code_is_unchanged(self):
        self.assertEqual((EXAMPLE / "before/report.py").read_bytes(), (EXAMPLE / "after/report.py").read_bytes())
        counts = []
        for phase in ("before", "after"):
            tree = ast.parse((EXAMPLE / phase / "test_report.py").read_text())
            counts.append(sum(isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
                              for node in ast.walk(tree)))
        self.assertEqual([1, 5], counts)

    def test_documented_reference_commands(self):
        guide = (ROOT / GUIDES[0]).read_text()
        for phase, count in (("before", 1), ("after", 5)):
            with self.subTest(phase=phase):
                directory = f"docs/examples/report-summary/{phase}"
                self.assertIn(f"python3 -I -m unittest discover -s {directory} -p 'test_report.py'", guide)
                result = subprocess.run([sys.executable, "-I", "-B", "-m", "unittest", "discover",
                                         "-s", directory, "-p", "test_report.py"],
                                        cwd=ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn(f"Ran {count} test", result.stderr)
                self.assertRegex(result.stderr, r"\nOK\s*$")

    def test_worked_example_preserves_durable_and_human_boundaries(self):
        text = (ROOT / GUIDES[0]).read_text()
        prose = re.sub(r"\s+", " ", text)
        for heading in ("## Objective", "## Context & references", "## Acceptance criteria",
                        "## Out of scope", "## File ownership", "## Verification", "## Routing",
                        "## Handoff notes", "## Outcome", "## Success criteria", "## Scope & non-goals",
                        "## Phase outline", "## References", "## Summary", "## Evidence",
                        "## Deviations", "## Follow-ups", "## Checklist"):
            self.assertIn(heading, text)
        for fragment in ("illustrative", "not a live Codex", "primary folder",
                         "no worker will be spawned", "Starting in session", "## Plan",
                         "claim → plan → first commit", "NOT_RUN", "PENDING",
                         "Closes #<TASK_NUMBER>", "Post-PR ritual sensor",
                         "bash .github/scripts/check-task-ritual.sh <ACTUAL_PR_NUMBER>",
                         "structured Task outcome comment", "Do not record `Outcome: completed`",
                         "normal completed checkpoint", "not crash recovery"):
            self.assertIn(fragment, prose)
        self.assertIn("\n- `test_report.py`\n", text)
        self.assertNotRegex(text, r"(?m)^- \[[xX]\]")

    def initial_record(self, text):
        blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
        self.assertEqual(1, len(blocks))
        return json.loads(blocks[0])

    def assert_unrun_record(self, record):
        self.assertEqual("evaluation-result-template/v1", record["schema"])
        self.assertEqual("NOT_RUN", record["status"])
        for field in ("case_id", "attempt_id", "authorization_ref", "candidate_head", "candidate_tree"):
            self.assertIsNone(record[field])
        for field in ("observations", "evidence_refs", "violations", "human_interventions"):
            self.assertEqual([], record[field])
        self.assertIsNone(record["conditions"]["observed_model"])
        self.assertEqual("PENDING", record["human_decision"]["status"])
        metrics = record["measurements"]
        self.assertEqual("not_measured", metrics["cost_status"])
        for field in ("wall_seconds", "input_tokens", "output_tokens", "billed_cost", "estimated_cost"):
            self.assertIsNone(metrics[field])

    def test_case_catalog_and_result_have_no_claimed_runs(self):
        text = (ROOT / GUIDES[1]).read_text()
        cases = re.findall(r"^\| (EC[0-9]{2}) \| ([A-Z_]+) \|", text, re.M)
        self.assertEqual([(f"EC{n:02}", "NOT_RUN") for n in range(1, 7)], cases)
        self.assert_unrun_record(self.initial_record(text))
        for token in ("case specifications, not runnable fixtures", "not retroactive case results",
                      "UNKNOWN", "UNCHECKABLE", "all attempts", "denominator",
                      "requested model", "observed model", "separate authorization",
                      "not a benchmark runner", "not native Windows"):
            self.assertIn(token, text)

    def test_template_guard_refuses_fabricated_success_and_zero_cost(self):
        original = self.initial_record((ROOT / GUIDES[1]).read_text())
        for field in ("status", "cost", "observations"):
            with self.subTest(field=field):
                record = json.loads(json.dumps(original))
                if field == "status":
                    record["status"] = "PASS"
                elif field == "cost":
                    record["measurements"]["billed_cost"] = 0
                else:
                    record["observations"] = ["invented success"]
                with self.assertRaises(AssertionError):
                    self.assert_unrun_record(record)


if __name__ == "__main__":
    unittest.main()
