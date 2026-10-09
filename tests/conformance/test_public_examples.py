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
EC02_REPORT = "docs/evaluation-results/ec02-pilot-20261008.md"
EC04_REPORT = "docs/evaluation-results/ec04-checkpoint-pilot-20261009.md"
PREFLIGHT = "docs/evaluation-observation-preflight.md"
GUIDES = ("docs/worked-example.md", "docs/evaluation-cases.md", REPORT, PREFLIGHT, EC02_REPORT, EC04_REPORT)
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
EC02_RECEIPTS = tuple(
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/50#issuecomment-" + number
    for number in ("6050705018", "6050715762", "6050728607", "6050762273")
)
EC02_RECEIPT_LABELS = (
    "Owner trial authorization", "Frozen preflight", "Unanswered checkpoint",
    "Result and advisory scoring review",
)
EC02_BINDINGS = {
    "ec02/input.json": "ee23049072fc46c5cf19db51d15e3a51adc5b5d2aa7f2106c67ed7106de91b48",
    "ec02/milestone.json": "88718464b353f975be04da9da5e26d9987526149e4bb0c5d6206eeb6cfdedef3",
    "ec02/controller.json": "f801b46042e7322b499459748060ca4b842e6e9ac5731124c8a76a76071c697c",
    "interaction-oracles.json": "8ccf07c204810e13c66e7c2d0221aa7a5e1e501d814c0f998ae749bd7caa56d2",
}
EC04_RECEIPTS = tuple(
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/53#issuecomment-" + number
    for number in ("6069266306", "6069369140", "6069407447", "6069497243")
)
EC04_RECEIPT_LABELS = (
    "Owner trial authorization", "Frozen staging and focal observation qualification",
    "Observed red checkpoint and separate supervisor replay", "Final result and advisory scoring review",
)
EC04_BINDINGS = {
    "ec04/input.json": "e1af01bfacc850c3bd575534f4dff8d4318a7e95571c12e1dffff86c55877474",
    "code-change-oracles.json": "07e9ac8d7e5f3f520d6a7aae32ec2363c5b32b2d6101ff97542c0e97ffdc716c",
    "code-change/seed/capacity.py": "cae3a5479ec05e92ea34ec4d8a6b57933e1eda824e3b2aa10062ef6225f01413",
    "code-change/seed/test_capacity.py": "f9a25d165b2d9ed49c4128dde296aa4a39e0fd790e6d28132dd9ba93ac449483",
    "code-change/seed/backlog.md": "c5053788eaa88c73ec8c1e2ccc8bb77686bcc2635f17d5488e28c6cf7a35fd38",
    "code-change/seed/user-notes.md": "9cc2a7fa4ca9f8cce75b77648bb719b3ce7924ce9a3c2a569ba7974ed778dd99",
    "code-change/baseline/user-notes.md": "7d554744c94ab8ea642e823d1dee165feffd1db15a2878cde9b20237147ebf25",
    "code-change/reference/test_capacity_reference.py": "eac16ed789b38a34b9406f3aedec22df7291dd31e354774338cf10b7c23e7193",
}
# Fixed public Task #53 receipt bindings, independent of the report under test.
EC04_RETAINED_BINDINGS = {
    "Initial prompt": "a76ff73dd9ba96188cbab621602df329600599010354dfc54a93827b19226c7d",
    "Continuation prompt": "96b0165ce6763169c4c36471129d89776342171c8312fda7b04eb69a83b5f062",
    "Original user delta": "ff45bfb40d9012734768bff41d11b88feee710876c931e88bf22fec43999b392",
    "Index inventory": "1da5ba4a4fed9ce1854ae70184bb2efa7ef538bebd9c52a5240a80dc5b142bbc",
    "Checkpoint/final candidate tests": "483c919ab99cb860bd2b3d3a40f8bad2d6ce10e315483c88e01682a92c3e320b",
    "Final candidate source": "4f760bef1396b20489c1c8329fb2422b8d15a44b09252ca91ac1961e4b6f7614",
    "Checkpoint inventory/diff evidence": "57ee90496cc80a90b4f3231e510072a592b850093b0dc107f283b63298238e71",
    "Supervisor red replay": "1fe603d276ce764d5970401ecd7f2ec279762327426d88f234041591288564f2",
    "Native two-turn evidence, reasoning omitted": "e64b6c3488300d60b641229750521fc13540f35392ad3ac38a4ea130f3b8bb6c",
    "Extracted native parent-to-child mapping": "acd9fbc189de3721a53312231aa2ae0d2b4e3a50fe3cee61c47f2aa0a09c452c",
    "Supervisor green replay": "e148b6965dc974fc19aad5b33bfdc546c449fcc9ce3e67f1eaaf870ea63671bf",
    "Supervisor reference replay": "c0bc2fb7f9fa16fefd17386f3975b8fdc8a8ac185f89261c34307c206f1cb723",
    "Independent advisory review": "d28e02316a0bd5aafceb0cd3966f79207d1038406f3d72ec9f5c51e738fb8bb2",
    "Timing record": "96a982306575aca5105f35f609c5c88bf84afe3269d846f2664422dc5f92876d",
    "Final normalized result": "1cfefa57f5e507eca86d88d221a21dd929dbeef8ed40a07925375f58f578052f",
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

    def assert_first_task_example_navigation(self, text):
        # Ignore fenced examples and comments, then check the two entry-point
        # forms. This is a focused README check, not a general Markdown parser.
        text = re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*(?:\n|$)", "", text)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        link = r"(?<!!)(?<!\\)\[[^\[\]`<>\\\n]+\]\(docs/worked-example\.md\)"
        for heading, level, row in (("### 4. Complete one small Task", 3, False),
                                    ("## Documentation", 2, True)):
            self.assertEqual(1, text.splitlines().count(heading))
            section = text.split(heading + "\n", 1)[1]
            section = re.split(r"(?m)^#{1," + str(level) + r"} ", section, maxsplit=1)[0]
            pattern = (r"^\| [^|`<>\n]+ \| " + link + r" \|$" if row else
                       r"^[A-Za-z][^`<>\n]*" + link + r"[^`<>\n]*$")
            self.assertRegex(section, "(?m)" + pattern)

    def test_readme_first_task_example_navigation(self):
        text = (ROOT / "README.md").read_text()
        self.assert_first_task_example_navigation(text)
        for heading in ("### 4. Complete one small Task", "## Documentation"):
            self.assert_first_task_example_navigation(text.replace(
                heading + "\n", heading + "\n\nOther `code` and <em>prose</em>.\n", 1))

    def test_readme_example_navigation_guard_rejects_missing_or_hidden_links(self):
        original = (ROOT / "README.md").read_text()
        lines = [line for line in original.splitlines(keepends=True)
                 if "](docs/worked-example.md)" in line]
        self.assertEqual(2, len(lines))
        for line in lines:
            mutations = (
                original.replace(line, "", 1),
                original.replace(line, line.replace("worked-example.md", "evidence-status.md"), 1),
                original.replace(line, "", 1) + "\n## Elsewhere\n" + line,
                original.replace(line, "```text\n" + line + "```\n", 1),
                original.replace(line, "<!--\n" + line + "-->\n", 1),
                original.replace(line, line.replace("[", "![", 1), 1),
                original.replace(line, line.replace("[", "\\[", 1), 1),
                original.replace(line, "    " + line, 1),
            )
            for index, mutated in enumerate(mutations):
                with self.subTest(line=line, mutation=index), self.assertRaises(AssertionError):
                    self.assert_first_task_example_navigation(mutated)

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

    def assert_ec02_report(self, text):
        """Guard this publication's fixed facts, not candidate behavior."""
        prose = re.sub(r"\s+", " ", text)
        links = "\n".join(f"- [{label}]({reference})"
                          for label, reference in zip(EC02_RECEIPT_LABELS, EC02_RECEIPTS))
        heading = "## Source receipts (2026-10-08)"
        self.assertEqual(1, text.splitlines().count(heading))
        self.assertRegex(text, r"(?m)^" + re.escape(heading + "\n\n" + links + "\n\n"))
        self.assertNotRegex(text, r"[<>]|(?m:^[ ]{0,3}(?:`{3,}|~{3,}|(?:=+|-+)[ \t]*$))")
        self.assertEqual(["UNCHECKABLE"], re.findall(r"Overall evaluation: ([A-Z_]+)", text))
        outcomes = re.findall(r"(?m)^\| (EC02-C[1-4]) \| ([A-Z_]+) \|", text)
        self.assertEqual([("EC02-C1", "PASS")] +
                         [(f"EC02-C{number}", "UNCHECKABLE") for number in range(2, 5)], outcomes)
        for token in (
                "EC02-INTERACTION-PILOT-2ba67b03-20261008", "EC02-20261008-A1",
                "case EC02 version 1", "2ba67b03c0d32a8621ab7656c83c0d2047a2a7ce",
                "67146a0dbc095dd9e20b89e8f86df7aeec029715", "1 candidate attempt",
                "2 candidate turns", "1 scripted reply", "0 retries", "0 replacements",
                "1 advisory scoring review", "authorized in advance",
                "not a new human UI selection", "published and read back before reply delivery",
                "no default", "two regular files", "0644", "three null fields",
                "early write followed by a revert", "no qualified independently attributable write observation",
                "whole shared action surface is not covered", "unverified self-report",
                "not proof that no forbidden action occurred", "FAIL overrides missing evidence",
                "UTC+09:00", "2026-10-06", "2026-10-13", "seven calendar days",
                "24 seconds", "not exact inference latency", "no gap over 30 seconds",
                "five-minute per-turn supervisory budget", "not an authenticated collector",
                "shared tools/filesystem", "not a blind benchmark", "model ranking",
                "installed-kit benefit", "runtime isolation", "question-bubble behavior",
                "one terminal LF", "not authenticated transport captures",
                "candidate head/tree remain null", "owner final acceptance remains separate",
                "source specifications and blank templates remain NOT_RUN",
                "EC01/EC03/EC04 have no trial evidence", "EC05/EC06-only record validator",
                "evaluation-observation-preflight.md"):
            self.assertIn(token, prose)
        for field in ("Actual model", "Actual reasoning setting", "Client version",
                      "Input tokens", "Output tokens", "Billed cost", "Estimated cost"):
            self.assertIn(f"| {field} | null |", text)
        for time in ("02:08:31", "02:08:44", "02:08:49", "02:08:55", "02:09:20",
                     "02:09:36", "02:09:44", "02:10:00"):
            self.assertIn(time, text)
        for path, digest in EC02_BINDINGS.items():
            self.assertIn(f"| `{path}` | `{digest}` |", text)
        for digest in (
                "3273d53233e24b97b3c973e9167b8e6568ee6944c45d954636d764f573800b4e",
                "022df77dfef9f600eaf0436bf3ceda4718c6df02eb94da4be23a9c2710c4f209",
                "2734f741f9a3e3883a22edab0c59ef273e895f8b01f574922297e5d9c02e99ad",
                "c39fec439237983c67b7dffb36306a9a6a9942413ccec3e81e0ae191b5974076",
                "e471fc797d7022200b6752b880d2c0ad09ff38d3662a18243fa26274cd5648f9"):
            self.assertIn(digest, text)

    def test_ec02_report_preserves_actual_results_and_limits(self):
        self.assert_ec02_report((ROOT / EC02_REPORT).read_text())

    def test_ec02_guard_rejects_false_results_and_missing_limits(self):
        original = (ROOT / EC02_REPORT).read_text()
        mutations = [
            original.replace("Overall evaluation: UNCHECKABLE", "Overall evaluation: PASS"),
            original + "\nOverall evaluation: PASS.\n",
            original.replace("1 candidate attempt", "2 candidate attempts"),
            original.replace("not a new human UI selection", "a new human UI selection"),
            original.replace("no qualified independently attributable write observation", "attributed write"),
            original.replace("whole shared action surface is not covered", "complete action coverage"),
            original.replace("unverified self-report", "independent proof"),
            original.replace("not exact inference latency", "exact inference latency"),
        ]
        mutations += [original.replace(f"| EC02-C{number} | UNCHECKABLE |",
                                       f"| EC02-C{number} | PASS |") for number in range(2, 5)]
        mutations += [original.replace(f"| {field} | null |", f"| {field} | 0 |")
                      for field in ("Input tokens", "Output tokens", "Billed cost", "Estimated cost")]
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.assert_ec02_report(mutated)

    def test_ec02_publication_preserves_fixture_bindings(self):
        for path, digest in EC02_BINDINGS.items():
            self.assertEqual(digest, hashlib.sha256(
                (ROOT / "docs/evaluation-fixtures" / path).read_bytes()).hexdigest())
        self.assert_unrun_record(self.initial_record((ROOT / GUIDES[1]).read_text()))

    def test_current_guides_link_pilots_without_claiming_unrun_cases_ran(self):
        for path in ("docs/evidence-status.md", GUIDES[1], "docs/evaluation-fixtures/README.md",
                     "docs/evaluation-fixtures/interaction.md", "docs/evaluation-fixtures/code-change.md"):
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                self.assertRegex(text, r"\[[^\]]+\]\((?:\.\./)?evaluation-results/ec02-pilot-20261008\.md\)")
                self.assertRegex(text, r"\[[^\]]+\]\((?:\.\./)?evaluation-results/ec04-checkpoint-pilot-20261009\.md\)")
                self.assertIn("EC01/EC03 have no trial evidence", re.sub(r"\s+", " ", text))
                self.assertNotIn("EC01/EC03/EC04 have no trial evidence", text)
                self.assertNotIn("EC01-EC04 have no new trial", text)
                self.assertIn("NOT_RUN", text)
                self.assertIn("UNCHECKABLE", text)

    def test_ec02_receipt_allowlist_is_exact_and_section_scoped(self):
        original = (ROOT / EC02_REPORT).read_text()
        heading = "## Source receipts (2026-10-08)"
        reference = EC02_RECEIPTS[0]
        bullet = f"- [{EC02_RECEIPT_LABELS[0]}]({reference})"
        mutations = [
            original.replace(heading, "## Other receipts"),
            original + "\n" + heading + "\n",
            original.replace(heading, "Prose " + heading),
            original + "\n## Outside receipts\n" + bullet + "\n",
            original.replace(bullet, "# Outside receipts\n" + bullet),
            original.replace(bullet, " ##\tOutside receipts\n" + bullet),
            original.replace(bullet, "```text\n" + bullet + "\n```"),
            original.replace(bullet, "~~~text\n" + bullet + "\n~~~"),
            original.replace(bullet, reference),
            original.replace(bullet, "- `" + bullet[2:] + "`"),
            original.replace(bullet, "- !" + bullet[2:]),
            original.replace(bullet, "- \\" + bullet[2:]),
            original.replace(bullet, "    " + bullet),
            original.replace(bullet, "<!-- " + bullet + " -->"),
            original.replace(bullet, "<!--\n" + bullet + "\n-->"),
            original.replace(bullet, "<div>\n" + bullet + "\n</div>"),
            original.replace(bullet, "Outside receipts\n---\n\n" + bullet),
            original.replace(bullet, "Outside receipts\n===\n\n" + bullet),
            original.replace(EC02_RECEIPT_LABELS[0],
                             "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/99"),
        ]
        mutations += [original.replace(url, url + "0") for url in EC02_RECEIPTS]
        mutations += [original.replace(url, url.replace("/50#", "/51#")) for url in EC02_RECEIPTS]
        mutations += [original.replace(reference, url)
                      for url in (*PILOT_RECEIPTS, *self.checker.CURRENT_RECEIPTS)]
        targets = [(EC02_REPORT, mutated) for mutated in mutations]
        targets += [(REPORT, (ROOT / REPORT).read_text().replace(PILOT_RECEIPTS[0], reference)),
                    (PREFLIGHT, (ROOT / PREFLIGHT).read_text() + "\n" + bullet + "\n"),
                    ("docs/parity-status.md", (ROOT / "docs/parity-status.md").read_text().replace(
                        "## Current acceptance as of 2026-09-23\n",
                        "## Current acceptance as of 2026-09-23\n" + bullet + "\n"))]
        self.assertEqual([], self.checker.validate_navigation(ROOT))
        for index, (path, mutated) in enumerate(targets):
            with self.subTest(index=index):
                root = self.fixture()
                (root / path).write_text(mutated)
                self.assertTrue(any("historical Issue/PR" in error
                                    for error in self.checker.validate_navigation(root)))

    def assert_ec04_report(self, text):
        """Guard fixed publication facts; this does not score or rerun a candidate."""
        prose = re.sub(r"\s+", " ", text)
        heading = "## Source receipts (2026-10-09)"
        links = "\n".join(f"- [{label}]({reference})"
                          for label, reference in zip(EC04_RECEIPT_LABELS, EC04_RECEIPTS))
        self.assertEqual(1, text.splitlines().count(heading))
        self.assertRegex(text, r"(?m)^" + re.escape(heading + "\n\n" + links + "\n\n"))
        self.assertNotRegex(text, r"[<>]|(?m:^[ ]{0,3}(?:`{3,}|~{3,}|(?:=+|-+)[ \t]*$))")
        self.assertEqual(["UNCHECKABLE"], re.findall(r"Overall evaluation: ([A-Z_]+)", text))
        self.assertEqual([(f"EC04-C{number}", "PASS") for number in range(1, 4)] +
                         [("EC04-C4", "UNCHECKABLE")],
                         re.findall(r"(?m)^\| (EC04-C[1-4]) \| ([A-Z_]+) \|", text))
        for token in (
                "EC04-CHECKPOINT-PILOT-068f5923-20261009", "EC04-20261009-A1", "case EC04 version 1",
                "068f592329980f2a17083e1eedc48a6f8a34120c", "8771f2f631d842b73aa980c25e15da9093aad8b2",
                "690455a63ab6328c6a31efb160c4ea58cbcc9717", "fecbf4bd19e1da28cc6bbdc4d90178b01efe56ee",
                "1 candidate attempt", "2 candidate turns", "1 frozen checkpoint continuation",
                "0 retries", "0 replacements", "1 advisory scoring review",
                "candidate output HEAD/tree remain null, not the baseline identities",
                "source/test fingerprint immediately before", "source retained its seed digest",
                "nine subtest failures produced exit 1", "no syntax/import/setup failure",
                "supervisor evidence, not candidate-run proof", "explicit supervisory intervention",
                "native final run passed all three methods, exit 0", "eight methods, exit 0",
                "Checkpoint and final test bytes were identical", "less than or equal to capacity",
                "Complete action coverage is missing", "does not establish global non-action",
                "not independent action proof", "FAIL override missing evidence",
                "47.635 seconds and 22.130 seconds, sum 69.765 seconds",
                "not total wall-clock work, cost or an inference-latency benchmark",
                "33 seconds; 3 seconds beyond the planned 30-second interval",
                "21:27:34 to 21:28:07", "21:29:36 to 21:30:05", "29 seconds",
                "supervision deviation, not a demonstrated candidate violation",
                "did not independently certify the supervisor clock observations",
                "mapping payload were additionally preserved after the advisory review",
                "non-truncated focal command outputs/diffs", "Shared tools/filesystem",
                "public teaching-material exposure", "not blind evaluation", "runtime isolation",
                "installed-kit efficacy", "not claimed to be free", "owner final acceptance remains separate",
                "source specifications and blank templates remain NOT_RUN",
                "pending approval fields describe authored preparation",
                "EC01/EC03 have no trial evidence", "EC05/EC06-only record validator"):
            self.assertIn(token, prose)
        for field in ("Actual model", "Actual reasoning setting", "Client version",
                      "Input tokens", "Output tokens", "Billed cost", "Estimated cost"):
            self.assertIn(f"| {field} | null |", text)
        for path, digest in EC04_BINDINGS.items():
            self.assertIn(f"| `{path}` | `{digest}` |", text)
        for label, digest in EC04_RETAINED_BINDINGS.items():
            self.assertIn(f"| {label} | `{digest}` |", text)

    def test_ec04_report_preserves_actual_results_and_limits(self):
        self.assert_ec04_report((ROOT / EC04_REPORT).read_text())

    def test_ec04_guard_rejects_every_retained_binding_mutation(self):
        original = (ROOT / EC04_REPORT).read_text()
        self.assertEqual(15, len(EC04_RETAINED_BINDINGS))
        for label, digest in EC04_RETAINED_BINDINGS.items():
            row = f"| {label} | `{digest}` |"
            for mutation, replacement in (
                    ("hash", row.replace(digest, "0" * 64)),
                    ("missing", ""),
                    ("label", row.replace(label, "Unbound artifact"))):
                with self.subTest(label=label, mutation=mutation):
                    mutated = original.replace(row, replacement)
                    self.assertNotEqual(original, mutated)
                    with self.assertRaises(AssertionError):
                        self.assert_ec04_report(mutated)

    def test_ec04_guard_rejects_false_results_and_removed_limits(self):
        original = (ROOT / EC04_REPORT).read_text()
        replacements = (
            ("Overall evaluation: UNCHECKABLE", "Overall evaluation: PASS"),
            ("| EC04-C4 | UNCHECKABLE |", "| EC04-C4 | PASS |"),
            ("1 candidate attempt", "2 candidate attempts"),
            ("Complete action coverage is missing", "Complete action coverage is established"),
            ("supervisor evidence, not candidate-run proof", "candidate-run proof"),
            ("explicit supervisory intervention", "autonomous continuation"),
            ("candidate output HEAD/tree remain null, not the baseline identities", "candidate output is baseline"),
            ("33 seconds; 3 seconds beyond the planned 30-second interval", "30 seconds; no deviation"),
            ("did not independently certify", "independently certified"),
            ("additionally preserved after the advisory review", "verified during the advisory review"),
            ("an inference-latency benchmark", "measured inference latency"),
        )
        mutations = [original.replace(old, new) for old, new in replacements]
        mutations += [original + "\nOverall evaluation: PASS.\n"]
        mutations += [original.replace(f"| {field} | null |", f"| {field} | 0 |")
                      for field in ("Input tokens", "Output tokens", "Billed cost", "Estimated cost")]
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.assert_ec04_report(mutated)

    def test_ec04_publication_preserves_source_bindings(self):
        for path, digest in EC04_BINDINGS.items():
            with self.subTest(path=path):
                self.assertEqual(digest, hashlib.sha256(
                    (ROOT / "docs/evaluation-fixtures" / path).read_bytes()).hexdigest())
        self.assert_unrun_record(self.initial_record((ROOT / GUIDES[1]).read_text()))

    def test_ec04_receipts_are_exact_section_scoped_and_not_interchangeable(self):
        original = (ROOT / EC04_REPORT).read_text()
        heading = "## Source receipts (2026-10-09)"
        reference = EC04_RECEIPTS[0]
        bullet = f"- [{EC04_RECEIPT_LABELS[0]}]({reference})"
        mutations = [original.replace(heading, "## Other receipts"),
                     original + "\n" + heading + "\n",
                     original.replace(heading, "Prose " + heading),
                     original + "\n## Outside receipts\n" + bullet + "\n"]
        for replacement in (
                "# Outside receipts\n" + bullet, " ##\tOutside receipts\n" + bullet,
                "```text\n" + bullet + "\n```", "~~~text\n" + bullet + "\n~~~",
                reference, "- `" + bullet[2:] + "`", "- !" + bullet[2:],
                "- \\" + bullet[2:], "    " + bullet, "<!-- " + bullet + " -->",
                "<div>\n" + bullet + "\n</div>", "Outside receipts\n---\n\n" + bullet,
                "Outside receipts\n===\n\n" + bullet):
            mutations.append(original.replace(bullet, replacement))
        mutations += [original.replace(url, url + "0") for url in EC04_RECEIPTS]
        mutations += [original.replace(url, url.replace("/53#", "/54#")) for url in EC04_RECEIPTS]
        mutations += [original.replace(reference, url)
                      for url in (*EC02_RECEIPTS, *PILOT_RECEIPTS, *self.checker.CURRENT_RECEIPTS)]
        targets = [(EC04_REPORT, mutated) for mutated in mutations]
        targets += [(EC02_REPORT, (ROOT / EC02_REPORT).read_text().replace(EC02_RECEIPTS[0], reference)),
                    (REPORT, (ROOT / REPORT).read_text().replace(PILOT_RECEIPTS[0], reference)),
                    (PREFLIGHT, (ROOT / PREFLIGHT).read_text() + "\n" + bullet + "\n"),
                    ("docs/parity-status.md", (ROOT / "docs/parity-status.md").read_text().replace(
                        "## Current acceptance as of 2026-09-23\n",
                        "## Current acceptance as of 2026-09-23\n" + bullet + "\n"))]
        self.assertEqual(set(EC04_RECEIPTS), self.checker.EC04_RECEIPTS)
        self.assertEqual([], self.checker.validate_navigation(ROOT))
        for index, (path, mutated) in enumerate(targets):
            with self.subTest(index=index):
                root = self.fixture()
                (root / path).write_text(mutated)
                self.assertTrue(any("historical Issue/PR" in error
                                    for error in self.checker.validate_navigation(root)))

    def test_ec04_report_is_covered_by_existing_privacy_guard(self):
        self.assertEqual([], self.checker.validate_policy(ROOT))
        for synthetic_private_value in ("/Users/synthetic/private", "/home/synthetic/private",
                                        "github_pat_" + "x" * 20):
            with self.subTest(value=synthetic_private_value):
                root = self.fixture()
                target = root / EC04_REPORT
                target.write_text(target.read_text() + "\n" + synthetic_private_value + "\n")
                self.assertTrue(any("private-path or credential pattern" in error
                                    for error in self.checker.validate_policy(root)))

    def test_receipt_sections_end_at_every_atx_heading(self):
        for report, label, reference in (
                (REPORT, PILOT_RECEIPT_LABELS[0], PILOT_RECEIPTS[0]),
                (EC02_REPORT, EC02_RECEIPT_LABELS[0], EC02_RECEIPTS[0]),
                (EC04_REPORT, EC04_RECEIPT_LABELS[0], EC04_RECEIPTS[0])):
            original = (ROOT / report).read_text()
            bullet = f"- [{label}]({reference})"
            root = self.fixture()
            for level in range(1, 7):
                for heading in ("#" * level + " Outside receipts",
                                "   " + "#" * level + "\tOutside receipts",
                                "#" * level,
                                "#" * level + "\r",
                                "#" * level + "\rFollowing paragraph",
                                "Preceding paragraph\r" + "#" * level + "\rFollowing paragraph"):
                    with self.subTest(report=report, heading=heading):
                        (root / report).write_text(original.replace(bullet, heading + "\n\n" + bullet))
                        self.assertTrue(any("historical Issue/PR" in error
                                            for error in self.checker.validate_navigation(root)))


if __name__ == "__main__":
    unittest.main()
