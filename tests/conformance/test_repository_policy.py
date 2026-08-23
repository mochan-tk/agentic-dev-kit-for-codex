import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-repository-policy.py"
OWNERSHIP = ".github/governance/phase-task-ownership.v1.json"


class RepositoryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("repository_policy", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load repository policy checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def ownership_payload(self, root=ROOT):
        return json.loads((root / OWNERSHIP).read_text(encoding="utf-8"))

    def declared_paths(self, payload):
        return [
            entry["path"]
            for task in payload["tasks"]
            for entry in task["owned_paths"]
        ]

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture = Path(temporary.name)
        payload = self.ownership_payload()
        for relative in self.declared_paths(payload):
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"fixture source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temporary, fixture

    def write_ownership(self, root, payload):
        (root / OWNERSHIP).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def errors_for(self, root):
        return self.checker.validate_repository(root, verify_git=False)

    def assert_rejected(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def test_live_repository_passes(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_safe_declared_expansion_passes(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        added = fixture / "docs/reviewed-expansion.md"
        added.parent.mkdir(parents=True, exist_ok=True)
        added.write_text("reviewed expansion\n", encoding="utf-8")
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            {"path": "docs/reviewed-expansion.md", "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assertEqual([], self.errors_for(fixture))

    def test_undeclared_live_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / "undeclared.txt").write_text("not owned\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "undeclared live path")

    def test_missing_declared_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / "README.md").unlink()
        self.assert_rejected(self.errors_for(fixture), "declared live path is missing")

    def test_overlapping_ownership_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            {"path": "README.md", "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "overlapping ownership")

    def test_duplicate_path_in_one_task_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            dict(payload["tasks"][1]["owned_paths"][0])
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate paths")

    def test_duplicate_task_id_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["id"] = payload["tasks"][0]["id"]
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate ownership task ID")

    def test_malformed_ownership_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"][0]["path"] = "../escape"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_unsupported_manifest_shape_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["policy"]["implicit_bypass"] = True
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "unsupported or missing fields")

    def test_manifest_must_own_itself(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"] = [
            entry
            for entry in payload["tasks"][1]["owned_paths"]
            if entry["path"] != OWNERSHIP
        ]
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "own its own path")

    def test_symlink_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.unlink()
        path.symlink_to("AGENTS.md")
        self.assert_rejected(self.errors_for(fixture), "symlink component")

    def test_unapproved_executable_mode_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.chmod(path.stat().st_mode | 0o111)
        self.assert_rejected(self.errors_for(fixture), "mode mismatch")

    def test_gitlink_mode_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        paths = set(self.declared_paths(self.ownership_payload(fixture)))
        modes = {path: "100644" for path in paths}
        modes["README.md"] = "160000"
        self.assert_rejected(
            self.checker.validate_repository(
                fixture,
                verify_git=False,
                observed_paths=paths,
                observed_modes=modes,
            ),
            "mode mismatch",
        )

    def test_release_blocker_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["phase"]["release_blocked"] = False
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "release_blocked must remain true")

    def test_conformance_release_blocker_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "tests/conformance/manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["release_blocked"] = False
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.assert_rejected(
            self.errors_for(fixture), "conformance manifest release_blocked"
        )

    def test_invariant_meaning_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "AGENTS.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "GitHub is durable truth", "A thread is durable truth", 1
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "invariant meanings")

    def test_missing_required_job_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("  quality:\n", "  renamed:\n", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "required job drift")

    def test_duplicate_required_job_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8")
        duplicate = text[text.index("  quality:\n") : text.index("\n  conformance:\n")]
        path.write_text(text + "\n" + duplicate + "\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "duplicate job ID")

    def test_missing_live_checker_command_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8").replace(
            "      - name: Validate live repository policy\n"
            "        run: python3 .github/scripts/check-repository-policy.py\n",
            "",
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "missing required command")

    def test_unpinned_action_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/checkout@v7",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "full commit SHA")

    def test_invalid_permissions_are_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("contents: read", "contents: none", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "permissions must contain only")

    def test_continue_on_error_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "        run: python3 .github/scripts/check-repository-policy.py",
                "        continue-on-error: true\n"
                "        run: python3 .github/scripts/check-repository-policy.py",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "forbidden continue-on-error")

    def test_stale_or_missing_base_evidence_is_rejected(self):
        payload = self.ownership_payload()
        payload["tasks"][1]["base_commit"] = "0" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "commit object is missing")

    def test_base_tree_mismatch_is_rejected(self):
        payload = self.ownership_payload()
        payload["tasks"][1]["base_tree"] = "f" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "tree does not match")

    def test_floating_dependency_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\npackage@latest\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "@latest")

    def test_model_slug_in_normative_policy_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ngpt-example\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "hardcodes model slug")


if __name__ == "__main__":
    unittest.main()
