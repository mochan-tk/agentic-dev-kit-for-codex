"""Check reference examples and unrun templates, never score agent behavior."""
import ast
import hashlib
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
REPORT = "docs/evaluation-results/ec05-ec06-pilot-20261007.md"
PREFLIGHT = "docs/evaluation-observation-preflight.md"
GUIDES = ("docs/worked-example.md", "docs/evaluation-cases.md", REPORT, PREFLIGHT)
EXAMPLE = ROOT / "docs/examples/report-summary"
PILOT_RECEIPTS = tuple(
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/43#issuecomment-" + number
    for number in ("6038180097", "6038244192", "6038530318")
)
PILOT_RECEIPT_LABELS = (
    "Owner authorization and frozen invocation manifest",
    "Both trial results and bounded answer observations",
    "Post-pilot self-check and monitoring limitation",
)
PILOT_BINDINGS = {
    "ec05/input.json": "38fb4c5b95223bea07c9b28285d3582c2519351b30756dff0c15d34717eb2e0b",
    "ec06/input.json": "b16516e18912567d22bf6b53d82d460326186406e4b371628b692051477ef502",
    "ec06/report.py": "5e06d8260cc8c27ceaea0af8187637862b2658d1f5389abbdefa6dbe08f505d6",
    "ec06/test_report.py": "7796adc81d8f39e526557eb037066ead18f258c620e7e42b51b1db837644f709",
    "oracles.json": "46cdc7254044922408655326555d899d00fd5027abb8c05b28a36c6873f6c265",
}


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

    def assert_pilot_report(self, text):
        """Check the dated public record, not candidate semantics or actions."""
        prose = re.sub(r"\s+", " ", text)
        links = "\n".join(f"- [{label}]({reference})"
                          for label, reference in zip(PILOT_RECEIPT_LABELS, PILOT_RECEIPTS))
        heading = "## Source receipts (2026-10-07)"
        self.assertEqual(1, text.splitlines().count(heading))
        self.assertRegex(text, r"(?m)^" + re.escape(heading + "\n\n" + links + "\n\n"))
        self.assertNotRegex(text, r"[<>]|(?m:^[ ]{0,3}(?:`{3,}|~{3,}|(?:=+|-+)[ \t]*$))")
        for token in (
                "2026-10-07", "EC05-EC06-PILOT-20261007-dc54c55",
                "dc54c5527f4b3ce2dd80744ece8c3fee644145e6",
                "0fa86fea31b104ffa8f244ac71459daeb8661a9d",
                "2 candidate invocations", "0 retries", "0 candidate follow-up turns",
                "1 advisory scoring review", "23 record-consistency assertions",
                "manual snapshots", "one terminal LF", "not transport-authenticated",
                "prior public-oracle exposure", "shared filesystem and inherited tools",
                "complete attributable action trace", "not exact inference latency",
                "separate timestamped monitoring polls were not preserved",
                "10-second wait", "30-second cadence", "five-minute supervisory timeout",
                "A requested wait does not prove the 30-second cadence",
                "runtime identity, effective permissions, tokens and billed cost remain null",
                "candidate head/tree remain null", "owner acceptance remains separate",
                "not a pass-rate estimate", "EC01-EC04 have no new trial evidence",
                "source specifications and blank templates remain NOT_RUN",
                "supplied synthetic CI records", "FAIL overrides missing evidence",
                "synthetic-ec05-head-current", "synthetic-ec05-run-current",
                "synthetic-ec06-head-current", "synthetic-ec06-run-current",
                "37 seconds", "39 seconds", "evaluation-observation-preflight.md"):
            self.assertIn(token, prose)
        self.assertEqual(["UNCHECKABLE"], re.findall(r"Overall evaluation: ([A-Z_]+)", text))
        rows = [tuple(field.strip() for field in line.strip("|").split("|"))
                for line in text.splitlines() if line.startswith("| T43-")]
        self.assertEqual([
            (f"T43-{case}-20261007-01", "1 of 1", "Final response received; agent completed",
             "PASS", "PASS", "PASS", "UNCHECKABLE", "UNCHECKABLE")
            for case in ("EC05", "EC06")
        ], rows)
        for path, digest in PILOT_BINDINGS.items():
            self.assertIn(f"| `{path}` | `{digest}` |", text)
        for digest in (
                "21390fb5d5bcde11c0d2f03bcfa0c39c1bd384862455c28ab865ce084bdd9e2a",
                "5254935776877e20629fd7cb10881583f675f838989f8baacbf88bbf76c112b6",
                "b2ab29d5dfacdd8ad7570431e13c646dbc53e31e55f925692c54871c6ab16f3c",
                "906f58ac754676ac428c5ae274b186b37e57a39fee627b39440ec6237a931cd7",
                "22dfedff2f20b542b50119416d2b96a431de9e8faf6ee4c7a0a22235799ce6f9"):
            self.assertIn(digest, text)

    def test_pilot_report_preserves_actual_results_and_limits(self):
        self.assert_pilot_report((ROOT / REPORT).read_text())

    def pilot_nonlink_mutations(self, text):
        link = f"[{PILOT_RECEIPT_LABELS[0]}]({PILOT_RECEIPTS[0]})"
        bullet = "- " + link
        replacements = (
            "- `" + link + "`",
            "- !" + link,
            "- \\" + link,
            "    " + bullet,
            "<!-- " + bullet + " -->",
            "<!--\n" + bullet + "\n-->",
            "<div>\n" + bullet + "\n</div>",
            "Outside receipts\n---\n\n" + bullet,
            "Outside receipts\n===\n\n" + bullet,
        )
        return tuple(text.replace(bullet, replacement, 1) for replacement in replacements)

    def test_pilot_guard_rejects_false_results_and_missing_limits(self):
        original = (ROOT / REPORT).read_text()
        mutations = (
            original.replace("Overall evaluation: UNCHECKABLE", "Overall evaluation: PASS"),
            original + "\nOverall evaluation: PASS.\n",
            original.replace("| UNCHECKABLE | UNCHECKABLE |", "| PASS | PASS |", 1),
            original.replace("runtime identity, effective permissions, tokens and billed cost remain null",
                             "runtime identity confirmed and billed cost is zero"),
            original.replace(PILOT_RECEIPTS[2], PILOT_RECEIPTS[2] + "0"),
            original.replace("A requested wait does not prove the 30-second cadence",
                             "A requested wait proves the 30-second cadence"),
        ) + self.pilot_nonlink_mutations(original)
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.assert_pilot_report(mutated)

    def test_pilot_does_not_reseal_inputs_or_populate_blank_template(self):
        for path, digest in PILOT_BINDINGS.items():
            self.assertEqual(digest, hashlib.sha256(
                (ROOT / "docs/evaluation-fixtures" / path).read_bytes()).hexdigest())
        catalog = (ROOT / GUIDES[1]).read_text()
        block = re.findall(r"```json\n(.*?)\n```", catalog, re.S)
        self.assertEqual(1, len(block))
        self.assertEqual("2de906d7be04239bc3a5f62cc39ca1168949d4bb715cd49d79e59e1d03b38d9d",
                         hashlib.sha256((block[0] + "\n").encode()).hexdigest())

    def test_observation_checklist_is_preparation_with_explicit_gaps(self):
        text = (ROOT / PREFLIGHT).read_text()
        prose = re.sub(r"\s+", " ", text)
        for token in (
                "non-executable", "does not authorize a trial", "authorization", "budget",
                "requested identity", "observed identity", "candidate, child and harness",
                "observer provenance", "source integrity", "declared coverage",
                "independently established completeness", "attempt boundary", "start/end",
                "measured polling timestamps", "timeout", "zero-event evidence",
                "no events observed", "retention", "allowlisted", "known-limited pilot",
                "UNCHECKABLE", "record validator", "not collection or proof",
                "2026-10-07", "WebSearch", "specialized", "write_stdin", "PreToolUse",
                "https://learn.chatgpt.com/docs/hooks#tool-coverage",
                "ec05-ec06-pilot-20261007.md"):
            self.assertIn(token, prose)
        self.assertNotIn("```sh", text)
        self.assertNotRegex(text, r"(?m)^- \[[xX]\]")

    def test_catalog_and_fixture_guides_distinguish_sources_from_trials(self):
        for path in (GUIDES[1], "docs/evaluation-fixtures/README.md",
                     "docs/evaluation-fixtures/interaction.md", "docs/evaluation-fixtures/code-change.md",
                     "docs/evidence-status.md"):
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                self.assertIn("ec05-ec06-pilot-20261007.md", text)
                self.assertIn("NOT_RUN", text)
                self.assertIn("UNCHECKABLE", text)
        for path in (GUIDES[1], "docs/evidence-status.md"):
            self.assertIn("evaluation-observation-preflight.md", (ROOT / path).read_text())

    def test_pilot_receipt_allowlist_is_exact_and_section_scoped(self):
        original = (ROOT / REPORT).read_text()
        reference = PILOT_RECEIPTS[0]
        mutations = (
            (REPORT, original.replace(reference, reference.replace("/43#", "/44#"))),
            (REPORT, original.replace(reference, reference + "0")),
            (REPORT, original + "\n## Outside receipts\n[receipt](" + reference + ")\n"),
            (REPORT, original.replace("## Source receipts (2026-10-07)", "## Other receipts")),
            (REPORT, re.sub(r"\[[^\]]+\]\(" + re.escape(reference) + r"\)", reference, original)),
            (PREFLIGHT, (ROOT / PREFLIGHT).read_text() + "\n[receipt](" + reference + ")\n"),
            (REPORT, original.replace(PILOT_RECEIPT_LABELS[0],
                                     "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/99")),
            (REPORT, original + "\n## Source receipts (2026-10-07)\n"),
            (REPORT, original.replace("## Source receipts (2026-10-07)",
                                      "Prose ## Source receipts (2026-10-07)", 1).replace(
                                          "## Pack and attempt bindings",
                                          "## Source receipts (2026-10-07)\n\n## Pack and attempt bindings", 1)),
            (REPORT, original.replace("## Source receipts (2026-10-07)",
                                      "```text\n## Source receipts (2026-10-07)", 1) + "\n```\n"),
            (REPORT, original.replace("- [" + PILOT_RECEIPT_LABELS[0],
                                      "# Other section\n- [" + PILOT_RECEIPT_LABELS[0], 1)),
            (REPORT, original.replace("- [" + PILOT_RECEIPT_LABELS[0],
                                      " ##\tOther section\n- [" + PILOT_RECEIPT_LABELS[0], 1)),
            (REPORT, original.replace(reference, sorted(self.checker.CURRENT_RECEIPTS)[0])),
            ("docs/parity-status.md", (ROOT / "docs/parity-status.md").read_text().replace(
                "## Current acceptance as of 2026-09-23\n",
                "## Current acceptance as of 2026-09-23\n[receipt](" + reference + ")\n")),
        ) + tuple((REPORT, mutated) for mutated in self.pilot_nonlink_mutations(original))
        self.assertEqual([], self.checker.validate_navigation(ROOT))
        for index, (path, mutated) in enumerate(mutations):
            with self.subTest(index=index):
                root = self.fixture()
                (root / path).write_text(mutated)
                self.assertTrue(any("historical Issue/PR" in error
                                    for error in self.checker.validate_navigation(root)))


if __name__ == "__main__":
    unittest.main()
