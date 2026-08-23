import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-phase0-contracts.py"

PHASE0_PATHS = (
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "AGENTS.md",
    "docs/agreements/adr/ADR-0004-codex-port-baseline.md",
    "docs/known-limitations.md",
    "docs/planning/phase-0-orientation.md",
    "tests/conformance/manifest.json",
    ".github/scripts/check-phase0-contracts.py",
    "tests/conformance/test_phase0_contracts.py",
    ".github/scripts/check-action-pins.sh",
    ".github/scripts/check-workflow-permissions.sh",
    ".github/scripts/tests/lib.sh",
    ".github/scripts/tests/test-action-pins.sh",
    ".github/scripts/tests/test-workflow-permissions.sh",
    ".github/workflows/ci.yml",
)


class Phase0ContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CHECKER.is_file():
            raise AssertionError(f"missing Phase 0 checker: {CHECKER}")
        spec = importlib.util.spec_from_file_location("phase0_checker", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError("cannot load the Phase 0 checker")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture = Path(temporary.name)
        for relative in PHASE0_PATHS:
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"fixture source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temporary, fixture

    def errors_for(self, root):
        paths = self.checker.discover_paths(root)
        return self.checker.validate_repository(root, paths)

    def mutate_manifest(self, fixture, callback):
        path = fixture / "tests/conformance/manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        callback(payload)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def assert_rejected(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def test_repository_passes(self):
        self.assertEqual([], self.errors_for(ROOT))

    def test_phase0_text_files_have_no_blank_line_at_eof(self):
        for relative in PHASE0_PATHS:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).read_bytes().endswith(b"\n\n"))

    def test_ci_runs_repository_guards_directly(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for command in (
            "bash .github/scripts/check-action-pins.sh",
            "bash .github/scripts/check-workflow-permissions.sh",
        ):
            with self.subTest(command=command):
                self.assertIn(f"run: {command}", workflow)

    def test_source_commit_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        self.mutate_manifest(
            fixture,
            lambda payload: payload["source"].update({"commit": "0" * 40}),
        )
        self.assert_rejected(self.errors_for(fixture), "source.commit")

    def test_source_tree_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        self.mutate_manifest(
            fixture,
            lambda payload: payload["source"].update({"tree": "f" * 40}),
        )
        self.assert_rejected(self.errors_for(fixture), "source.tree")

    def test_duplicate_contract_id_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)

        def duplicate(payload):
            payload["contracts"].append(dict(payload["contracts"][0]))

        self.mutate_manifest(fixture, duplicate)
        self.assert_rejected(self.errors_for(fixture), "duplicate contract")

    def test_contract_semantic_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)

        def claim_parity(payload):
            payload["contracts"][-1].update(
                {"phase0_state": "parity-complete", "contract": "all scenarios passed"}
            )

        self.mutate_manifest(fixture, claim_parity)
        self.assert_rejected(self.errors_for(fixture), "contract K20")

    def test_invariant_text_drift_with_stale_digest_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "AGENTS.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "GitHub is durable truth", "A thread is durable truth", 1
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "invariant digest")

    def test_pass_result_without_evidence_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)

        def false_pass(payload):
            payload["results"] = [{"scenario": "C-001", "status": "pass"}]

        self.mutate_manifest(fixture, false_pass)
        self.assert_rejected(self.errors_for(fixture), "target_evidence")

    def test_wrong_scenario_total_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        self.mutate_manifest(
            fixture,
            lambda payload: payload["scenario_catalog"].update({"total": 135}),
        )
        self.assert_rejected(self.errors_for(fixture), "scenario_catalog.total")

    def test_missing_required_limitation_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "docs/known-limitations.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("authenticated identity", "identity"),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "authenticated identity")

    def test_floating_action_reference_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/checkout@v7",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "full commit SHA")

    def test_flow_style_action_reference_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "      - name: Validate Phase 0 contracts",
                "      - { uses: actions/setup-node@v4 }\n"
                "      - name: Validate Phase 0 contracts",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "uses syntax")

    def test_malformed_action_version_comment_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("# v7.0.1", "# v7garbage", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "version comment")

    def test_contents_none_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("contents: read", "contents: none", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "contents: read")

    def test_additional_write_permission_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "      contents: read", "      contents: read\n      issues: write", 1
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "only contents: read")

    def test_checkout_persistence_comment_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace("          persist-credentials: false\n", "", 1)
        text = text.replace(
            "      - name: Validate Phase 0 contracts",
            "      # persist-credentials: false\n"
            "      - name: Validate Phase 0 contracts",
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "checkout with.persist-credentials")

    def test_copilot_execution_asset_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/copilot-instructions.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("copilot execution policy\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "unexpected Phase 0 path")

    def test_floating_latest_dependency_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nFloating example: package@latest\n",
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "@latest")

    def test_unexpected_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / "unexpected.txt").write_text("outside ownership\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "unexpected Phase 0 path")

    def test_tracked_ignored_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        hidden = fixture / ".codex-log/unowned.txt"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("tracked outside ownership\n", encoding="utf-8")
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", str(fixture)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(fixture), "add", "-A"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(fixture), "add", "-f", ".codex-log/unowned.txt"],
            check=True,
        )
        self.assert_rejected(self.errors_for(fixture), "unexpected Phase 0 path")

    def test_required_path_symlink_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.unlink()
        path.symlink_to("AGENTS.md")
        self.assert_rejected(self.errors_for(fixture), "must not be a symlink")


if __name__ == "__main__":
    unittest.main()
