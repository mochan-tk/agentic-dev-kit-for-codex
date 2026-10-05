"""Adopter documentation and one-file export adaptation, not live UI evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
README = ".github/distribution/payload/README.md"


class AdoptionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("adoption_product", ROOT / ".github/scripts/check-product.py")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="adoption-evidence-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "kit"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return root

    def test_installed_guide_matches_desktop_and_seed_contract(self):
        text = (ROOT / README).read_text()
        normalized = " ".join(text.split())
        for token in ("ChatGPT Codex desktop app is required", "primary folder",
                      "ChatGPT Chat or Work", "explicitly invoke", "newly installed files",
                      "local installer engine does not stage", "Neither entry commits or pushes",
                      "Existing adopter README files are preserved by install and upgrade"):
            self.assertIn(token, normalized)
        for token in ("In Codex CLI or IDE", "available Codex client", "installer never stages"):
            self.assertNotIn(token, text)
        row = next(line.split("\t") for line in (ROOT / ".github/distribution/payload.v1.tsv").read_text().splitlines()
                   if line.startswith("README.md\t"))
        self.assertEqual("seed", row[1])

    def test_first_existing_codebase_task_is_characterization(self):
        readme = (ROOT / "README.md").read_text()
        section = readme.split("### 4. Complete one small Task\n", 1)[1].split("\n### ", 1)[0]
        self.assertIn("characterization tests", section)
        self.assertIn("before feature work", section)
        self.assertNotIn("add CSV export", section)

    def test_evidence_page_separates_baseline_and_historical_live_evidence(self):
        self.assertIn("docs/evidence-status.md", self.checker.PUBLIC_DOCS)
        text = (ROOT / "docs/evidence-status.md").read_text()
        for token in ("2026-10-05", "9fdbf91d9980b5c632e0f3483c97098358ce519f",
                      "37250779904", "Baseline", "2026-09-23", "synthetic",
                      "does not remeasure later kit revisions", "no new E01 run",
                      "release_blocked=true"):
            self.assertIn(token, text)
        parity = (ROOT / "docs/parity-status.md").read_text()
        self.assertIn("## Historical implementation checkpoint", parity)
        self.assertIn("**Pending** separate authority and actual measurements", parity)
        self.assertIn("## Current acceptance as of 2026-09-23\n", parity)
        self.assertIn("docs/evidence-status.md", (ROOT / "README.md").read_text())

    def test_current_readme_is_exact_and_export_remains_original(self):
        self.assertEqual([], self.checker.validate_export(ROOT))
        export = json.loads((ROOT / self.checker.EXPORT).read_bytes())
        row = next(row for row in export["frozen_files"] if row["path"] == README)
        self.assertEqual({"path": README, "mode": "100644",
                          "source_blob": "45f522d80380d130d2894606fa41fa19dada2f3a",
                          "sha256": "48fb7e3655acaf651a62ddb801e0a8586b2f991a262c6f633338e3d5a86d726b"}, row)
        self.assertNotEqual(row["sha256"], hashlib.sha256((ROOT / README).read_bytes()).hexdigest())
        root = self.fixture()
        target = root / README
        target.write_bytes(target.read_bytes() + b"\nUnreviewed guide change.\n")
        self.assertTrue(self.checker.validate_export(root))

    def test_resealed_original_readme_row_is_not_a_current_adaptation(self):
        for field, changed in (("sha256", "0" * 64), ("source_blob", "0" * 40), ("mode", "100755")):
            with self.subTest(field=field):
                root = self.fixture()
                path = root / self.checker.EXPORT
                record = json.loads(path.read_bytes())
                next(row for row in record["frozen_files"] if row["path"] == README)[field] = changed
                path.write_text(json.dumps(record))
                with patch.object(self.checker, "EXPORT_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()):
                    self.assertTrue(self.checker.validate_export(root))

    def test_readme_adaptation_cannot_extend_workflow_exemptions(self):
        root = self.fixture()
        target = root / ".github/distribution/payload/AGENTS.md"
        target.write_bytes(target.read_bytes() + b"\nUnreviewed extra-path change.\n")
        path = root / ".github/distribution/source-parity.v1.json"
        parity = json.loads(path.read_bytes())
        export = json.loads((root / self.checker.EXPORT).read_bytes())
        original = next(row for row in export["frozen_files"] if row["path"].endswith("/AGENTS.md"))
        data = target.read_bytes()
        parity["workflow_parity"]["export_adaptations"].append({
            "path": original["path"], "export": original, "target_mode": "100644",
            "target_sha256": hashlib.sha256(data).hexdigest(),
            "target_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        })
        parity["workflow_parity"]["export_adaptations"].sort(key=lambda row: row["path"])
        path.write_text(json.dumps(parity))
        self.assertTrue(self.checker.validate_export(root))

    def test_evidence_page_navigation_is_checked_without_new_receipt_exceptions(self):
        self.assertEqual([], self.checker.validate_navigation(ROOT))
        for addition in ("\n[missing](missing-proof.md)\n",
                         "\n[receipt](https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12#issuecomment-5788166242)\n"):
            with self.subTest(addition=addition):
                root = self.fixture()
                target = root / "docs/evidence-status.md"
                target.write_text(target.read_text() + addition)
                self.assertTrue(self.checker.validate_navigation(root))


if __name__ == "__main__":
    unittest.main()
