"""Exercise the warning-only material CLI and its installed manual fallback."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/check-spec-handoff.py"
SPEC = importlib.util.spec_from_file_location("spec_handoff", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
LABELS = ("goal", "intended users", "scope", "non-goals", "constraints",
          "acceptance criteria", "unresolved questions")


class SpecHandoffTests(unittest.TestCase):
    def invoke(self, documents):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, content in enumerate(documents):
                path = Path(directory) / f"material-{index}.md"
                path.write_bytes(content)
                paths.append(str(path))
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *paths],
                                  capture_output=True, text=True, timeout=10)

    def test_all_observations_exit_zero_without_assessing_content(self):
        text = "\ufeff" + "\r\n".join(f"## {label.title()}" for label in LABELS)
        result = self.invoke([text.encode()])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Observed points: 7/7", result.stdout)
        self.assertIn("Missing: none", result.stdout)
        self.assertIn("quality and sufficiency are not assessed", result.stdout)

    def test_each_missing_point_is_named_with_exit_one(self):
        for missing in LABELS:
            with self.subTest(missing=missing):
                text = "\n".join(f"## {label}" for label in LABELS if label != missing)
                result = self.invoke([text.encode()])
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("Observed points: 6/7", result.stdout)
                self.assertIn(f"Missing: {missing}\n", result.stdout)
                self.assertIn("owner decides", result.stdout)

    def test_prose_mentions_multiple_files_and_explicit_none(self):
        result = self.invoke([b"Our goal serves the intended users. Scope: local. Non-goals: sync.",
                              b"Constraints: offline. Acceptance criteria: runs. Unresolved questions: none."])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("7/7", result.stdout)

    def test_japanese_labels_and_unicode_hyphens(self):
        text = "目的\n対象ユーザー\nスコープ\n対象外\n制約\n受け入れ条件\n未決事項\n"
        self.assertEqual(0, self.invoke([text.encode()]).returncode)
        self.assertTrue(CHECK.inspect("Non‑goals")["non-goals"])

    def test_excluded_scope_and_non_goals_do_not_imply_included_scope_or_goal(self):
        for text in ("Non-goals", "Non goals", "out of scope", "out-of-scope", "スコープ外", "非目標"):
            with self.subTest(text=text):
                found = CHECK.inspect(text)
                self.assertTrue(found["non-goals"])
                self.assertFalse(found["goal"])
                self.assertFalse(found["scope"])
        self.assertFalse(any(CHECK.inspect("goalkeeper userland telescope unconstrained").values()))

    def test_empty_file_reports_all_seven(self):
        result = self.invoke([b""])
        self.assertEqual(1, result.returncode)
        self.assertIn("Observed points: 0/7", result.stdout)
        for label in LABELS:
            self.assertIn(label, result.stdout)

    def test_wrapped_labels_and_whitespace_preserve_exclusions(self):
        found = CHECK.inspect("Intended  users\nAcceptance\ncriteria\nNon\tgoals\nOut of\nscope")
        for label in ("intended users", "acceptance criteria", "non-goals"):
            self.assertTrue(found[label])
        self.assertFalse(found["goal"])
        self.assertFalse(found["scope"])

    def test_unreadable_and_binary_input_are_errors_not_success(self):
        for content in (b"\xff", b"Goal\0Scope"):
            result = self.invoke([content])
            self.assertEqual(2, result.returncode)
            self.assertNotIn("Observed points", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", str(SCRIPT), str(Path(directory) / "absent")],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertNotIn(directory, result.stderr)

    def test_installed_instructions_keep_warning_and_manual_semantics(self):
        skill = (ROOT / ".github/distribution/payload/.agents/skills/project-onboarding/SKILL.md").read_text()
        intake = skill.split("**Advisory handoff presence check.**", 1)[1].split("3. **Implementation model.**", 1)[0]
        for label in LABELS:
            self.assertIn(f"**{label}**", intake)
        for phrase in ("kit-side, not installed", "label the result as manual", "exit 1 means missing points",
                       "the owner decides", "explicit-answer wait", "never content quality"):
            self.assertIn(phrase, intake)
        self.assertIn("Wait for an explicit answer, without a time limit.", skill)


if __name__ == "__main__":
    unittest.main()
