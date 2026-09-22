"""Clean-root export regressions; real Git checkout modes, no old Git history."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RECORD = ".github/distribution/export-provenance.v1.json"


class ProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("product_check", ROOT / ".github/scripts/check-product.py")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="product-export-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "kit"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return root

    def git(self, root, *args, umask=None):
        options = {} if umask is None else {"umask": umask}
        return subprocess.check_output(["git", "-C", str(root), *args], text=True,
            env=dict(os.environ, LC_ALL="C", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull),
            **options).strip()

    def test_product_cli_requires_all_components_without_git_history(self):
        root = self.fixture()
        self.assertFalse((root / ".git").exists())
        result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts/check-product.py")],
            cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for path in (RECORD, "tests/fixtures/history/manifest.json", "tests/conformance/test_source_first_procedures.py",
                     ".github/scripts/scaffold-install.sh", ".github/scripts/scaffold-update.sh",
                     ".github/scripts/scaffold-update.ps1", "tests/conformance/test_installer_update.py",
                     "tests/fixtures/workflow-parity-baseline.json", "tests/conformance/test_workflow_parity.py"):
            altered = self.fixture()
            (altered / path).unlink()
            self.assertTrue(self.checker.validate(altered))

    def test_adopter_addon_is_mandatory_product_scope_not_installer_fixture_scope(self):
        self.assertEqual([], self.checker.validate_adopter_ci(ROOT))
        for missing in (self.checker.ADOPTER_RECORD, *self.checker.ADOPTER_TARGETS):
            with self.subTest(missing=missing):
                root = self.fixture()
                (root / missing).unlink()
                self.assertTrue(self.checker.validate_adopter_ci(root))
        root = self.fixture()
        (root / self.checker.ADOPTER_RECORD).unlink()
        result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts/check-installer.py")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.checker.validate(root))

    def test_frontier_cache_is_required_in_both_production_entrypoints(self):
        for missing in ("tests/fixtures/frontier-cache-baseline.json", "tests/conformance/test_frontier_cache.py",
                        "docs/parity-status.md"):
            with self.subTest(missing=missing):
                root = self.fixture()
                (root / missing).unlink()
                for checker in ("check-installer.py", "check-product.py"):
                    result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts" / checker)],
                                            cwd=root, capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(0, result.returncode, checker)
        root = self.fixture()
        path = root / ".github/scripts/check-installer.py"
        path.write_text(path.read_text().replace("def validate_frontier_cache(root):", "def removed_cache_guard(root):"))
        self.assertTrue(self.checker.validate(root))

    def test_boundary_repair_baseline_and_contract_are_required_by_both_entrypoints(self):
        for missing in ("tests/fixtures/boundary-repair-baseline.json", "boundary_repair"):
            root = self.fixture()
            if missing == "boundary_repair":
                path = root / ".github/distribution/source-parity.v1.json"
                record = json.loads(path.read_text())
                del record[missing]
                path.write_text(json.dumps(record))
            else: (root / missing).unlink()
            for checker in ("check-installer.py", "check-product.py"):
                result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts" / checker)],
                                        cwd=root, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(0, result.returncode, checker)

    def test_boundary_exact_bytes_and_original_seal_refuse_resealing(self):
        spec = importlib.util.spec_from_file_location("boundary_guard", ROOT / ".github/scripts/check-installer.py")
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.assertEqual([], guard.validate_boundary_repair(ROOT))
        for path in guard.BOUNDARY_BASE_PATHS:
            with self.subTest(path=path):
                root = self.fixture()
                target = root / path
                target.write_bytes(target.read_bytes() + b"\n# unreviewed regression\n")
                parity = root / guard.PARITY
                record = json.loads(parity.read_text())
                row = next(row for row in record["boundary_repair"]["target_files"] if row["path"] == path)
                row["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                for row in record["boundary_repair"]["export_adaptations"]:
                    if row["path"] == path:
                        row["target_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                        row["target_blob"] = self.git_blob(target.read_bytes())
                parity.write_text(json.dumps(record))
                self.assertTrue(guard.validate_boundary_repair(root))
        root = self.fixture()
        baseline = root / guard.BOUNDARY_BASELINE
        baseline.write_bytes(baseline.read_bytes() + b"\n")
        path = root / guard.PARITY
        record = json.loads(path.read_text())
        record["boundary_repair"]["baseline_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
        path.write_text(json.dumps(record))
        self.assertTrue(guard.validate_boundary_repair(root))
        root = self.fixture()
        path = root / guard.PARITY
        record = json.loads(path.read_text())
        record["boundary_repair"]["export_adaptations"][0]["export"]["sha256"] = "0" * 64
        path.write_text(json.dumps(record))
        self.assertTrue(guard.validate_boundary_repair(root))

    @staticmethod
    def git_blob(data):
        return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

    def test_frontier_cache_contract_and_exact_baseline_refuse_resealing(self):
        root = self.fixture()
        spec = importlib.util.spec_from_file_location("frontier_guard", ROOT / ".github/scripts/check-installer.py")
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        path = root / guard.PARITY
        original = path.read_bytes()
        self.assertEqual([], guard.validate_frontier_cache(root))
        for mutation in ("missing", "source", "cache", "extra", "target", "scope", "export", "baseline"):
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                record = value["frontier_cache"]
                if mutation == "missing": del value["frontier_cache"]
                elif mutation == "source": record["source_files"][".github/skills/plan-management/scripts/frontier.sh"] = "0" * 40
                elif mutation == "cache": record["cache"] = "disk-or-cross-invocation"
                elif mutation == "extra": record["waiver"] = True
                elif mutation == "target": record["target_files"][0]["sha256"] = "0" * 64
                elif mutation == "scope": record["target_files"].pop()
                elif mutation == "export": record["export_adaptation"]["export"]["sha256"] = "0" * 64
                else: record["baseline_sha256"] = "0" * 64
                path.write_text(json.dumps(value))
                self.assertTrue(guard.validate_frontier_cache(root))
        path.write_bytes(original)
        baseline = root / guard.FRONTIER_BASELINE
        baseline.write_bytes(baseline.read_bytes() + b"\n")
        value = json.loads(original)
        value["frontier_cache"]["baseline_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
        path.write_text(json.dumps(value))
        self.assertTrue(guard.validate_frontier_cache(root))

    def test_frontier_or_anchor_resealed_regression_still_refuses(self):
        spec = importlib.util.spec_from_file_location("frontier_exact_guard", ROOT / ".github/scripts/check-installer.py")
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        mutations = ((guard.FRONTIER_TARGETS[0], 'blocker_state "$ref" "$blocker_repo"',
                      'STATE=CLOSED # removed observed blocker'),
                     (guard.FRONTIER_TARGETS[1], '[[ "$base_anchor" == "$head_anchor" ]] || return 1',
                      ': # removed exact base/head anchor'))
        for helper, before, after in mutations:
            with self.subTest(helper=helper):
                root = self.fixture()
                target = root / helper
                self.assertIn(before, target.read_text())
                target.write_text(target.read_text().replace(before, after))
                path = root / guard.PARITY
                value = json.loads(path.read_bytes())
                record = value["frontier_cache"]
                for row in record["target_files"]:
                    if row["path"] == helper: row["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                if helper == guard.FRONTIER_TARGETS[0]:
                    data = target.read_bytes()
                    record["export_adaptation"]["target_sha256"] = hashlib.sha256(data).hexdigest()
                    record["export_adaptation"]["target_blob"] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                path.write_text(json.dumps(value))
                self.assertTrue(guard.validate_frontier_cache(root))
                self.assertTrue(self.checker.validate_export(root))

    def test_adopter_provenance_reseal_or_guard_drift_cannot_waive_the_addon(self):
        root = self.fixture()
        path = root / self.checker.ADOPTER_RECORD
        original = path.read_bytes()
        for mutation in ("source", "source-blob", "scope", "mode", "digest", "omit", "extra"):
            with self.subTest(mutation=mutation):
                record = json.loads(original)
                if mutation == "source": record["source_commit"] = "0"*40
                elif mutation == "source-blob": record["source_files"][".github/workflows/ci.yml"] = "0"*40
                elif mutation == "scope": record["scope"] = "waived"
                elif mutation == "mode": record["target_files"][0]["mode"] = "100755"
                elif mutation == "digest": record["target_files"][0]["sha256"] = "0"*64
                elif mutation == "omit": record["target_files"].pop()
                else: record["waivers"] = []
                path.write_text(json.dumps(record))
                self.assertTrue(self.checker.validate_adopter_ci(root))
        path.write_bytes(original)
        sensor = root / ".github/distribution/adopter-ci/check-adopter-ci.py"
        sensor.write_bytes(sensor.read_bytes() + b"\n# changed\n")
        record = json.loads(original)
        for row in record["target_files"]:
            if row["path"] == str(sensor.relative_to(root)):
                row["sha256"] = hashlib.sha256(sensor.read_bytes()).hexdigest()
        path.write_text(json.dumps(record))
        self.assertTrue(self.checker.validate_adopter_ci(root))

    def test_adopter_mandatory_guard_rejects_resealed_review_regressions(self):
        # Permit an exact temporary fixture reseal so this tests the mandatory
        # behavior edge, independently of the production provenance digest.
        for bypass in ('run: " true "', "# disabled verification", "name: {}",
                       "working-directory: {}", "with: {}", "shell: bash"):
            with self.subTest(bypass=bypass):
                root = self.fixture()
                sensor_path = ".github/distribution/adopter-ci/check-adopter-ci.py"
                sensor = root / sensor_path
                sensor.write_text(sensor.read_text() + "\n_original_contract = code_contract\n"
                    "def code_contract(data, checks):\n"
                    "    if " + repr(bypass.encode()) + " in data:\n        return None\n"
                    "    return _original_contract(data, checks)\n")
                path = root / self.checker.ADOPTER_RECORD
                record = json.loads(path.read_bytes())
                for row in record["target_files"]:
                    if row["path"] == sensor_path:
                        row["sha256"] = hashlib.sha256(sensor.read_bytes()).hexdigest()
                path.write_text(json.dumps(record))
                with patch.object(self.checker, "ADOPTER_RECORD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()):
                    self.assertTrue(self.checker.validate_adopter_ci(root))

    def test_explicit_update_contract_and_required_guard_fail_closed(self):
        root = self.fixture()
        path = root / ".github/distribution/source-parity.v1.json"
        original = path.read_text()
        for mutation in ("missing", "source", "source-blob", "mode", "digest", "extra", "reordered"):
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                record = value["explicit_update"]
                if mutation == "missing": del value["explicit_update"]
                elif mutation == "source": record["source_commit"] = "0" * 40
                elif mutation == "source-blob": record["source_files"][".github/scripts/scaffold-init.sh"] = "0" * 40
                elif mutation == "mode": record["target_files"][0]["mode"] = "100755"
                elif mutation == "digest": record["target_files"][0]["sha256"] = "0" * 64
                elif mutation == "extra": record["automatic"] = True
                else: record["target_files"].reverse()
                path.write_text(json.dumps(value))
                self.assertTrue(any("explicit update" in error for error in self.checker.validate(root)))
                result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts/check-installer.py")],
                                        capture_output=True, text=True, timeout=30)
                self.assertNotEqual(0, result.returncode)
        path.write_text(original)
        entry = root / ".github/scripts/scaffold-update.sh"
        entry.write_bytes(entry.read_bytes() + b"\n# drift\n")
        self.assertTrue(any("explicit update" in error for error in self.checker.validate(root)))
        root = self.fixture()
        checker = root / ".github/scripts/check-installer.py"
        checker.write_text(checker.read_text().replace("def validate_explicit_update(root):", "def removed_update_guard(root):"))
        self.assertIn("mandatory installer validation unavailable", self.checker.validate(root))

    def test_companion_guide_and_test_are_mandatory(self):
        self.assertEqual([], self.checker.validate_companion_access(ROOT))
        for missing in (self.checker.COMPANION_GUIDE, "tests/conformance/test_companion_access.py"):
            with self.subTest(missing=missing):
                root = self.fixture()
                (root / missing).unlink()
                self.assertTrue(self.checker.validate_companion_access(root))
                self.assertTrue(self.checker.validate(root))

    def test_companion_fixed_source_and_safety_drift_refuse(self):
        root = self.fixture()
        path = root / self.checker.COMPANION_GUIDE
        original = path.read_text()
        for before, after in (
            (self.checker.COMPANION_REVISION, "main"),
            ("expected=" + self.checker.WORKFLOW_EXPORT_DIGESTS[".github/scripts/governance-status.sh"], "expected=" + "0"*64),
            ("curl --disable --fail", "curl --disable"),
            ('[ "${actual%% *}" = "$expected" ]', "true"),
            ("  trap cleanup EXIT\n", ""),
            ('rm -f -- "$scratch/helper.sh"', 'rm -rf -- "$CHECK_TARGET"'),
            ('--target "$CHECK_TARGET"', '--target $CHECK_TARGET'),
            ('--claims "$CHECK_CLAIMS"', '--claims /dev/null'),
            ("  bash \"$scratch/helper.sh\"", "  bash \"$scratch/helper.sh\"; true #"),
            ("<!-- BEGIN companion-governance -->", "<!-- BEGIN companion-unknown -->"),
        ):
            with self.subTest(change=before):
                self.assertIn(before, original)
                path.write_text(original.replace(before, after))
                self.assertTrue(self.checker.validate_companion_access(root))
        path.write_text(original + original)
        self.assertTrue(self.checker.validate_companion_access(root))

    def test_companion_helper_binding_and_readme_route_cannot_disappear(self):
        root = self.fixture()
        for helper, _ in self.checker.COMPANION_BLOCKS.values():
            path = root / ".github/scripts" / helper
            original = path.read_bytes()
            path.write_bytes(original + b"\n# drift\n")
            self.assertTrue(self.checker.validate_companion_access(root))
            path.write_bytes(original)
        readme = root / "README.md"
        readme.write_text(readme.read_text().replace(self.checker.COMPANION_GUIDE, "docs/product-scope.md"))
        self.assertIn("README companion command navigation missing", self.checker.validate_companion_access(root))

    def test_clean_git_checkouts_with_ordinary_umasks_are_structurally_valid(self):
        source = self.fixture()
        self.git(source, "init", "--quiet", "--template=", "-b", "main")
        self.git(source, "add", "--all")
        tree = self.git(source, "write-tree")
        commit = self.git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                          "commit-tree", tree, "-m", "Synthetic clean checkout fixture")
        self.git(source, "update-ref", "HEAD", commit)
        for mask, mode in ((0o022, 0o644), (0o077, 0o600), (0o027, 0o640), (0o002, 0o664)):
            with self.subTest(umask=f"{mask:03o}"):
                root = source.parent / f"clone-{mask:03o}"
                self.git(source.parent, "clone", "--quiet", "--no-hardlinks", str(source), str(root), umask=mask)
                self.assertEqual(tree, self.git(root, "rev-parse", "HEAD^{tree}"))
                entries = self.git(root, "ls-files", "--stage").splitlines()
                self.assertTrue(entries)
                self.assertEqual({"100644"}, {entry.split()[0] for entry in entries})
                for path in (RECORD, "README.md"):
                    self.assertEqual(mode, stat.S_IMODE((root / path).stat().st_mode))
                self.assertEqual([], self.checker.validate(root))
                self.assertEqual("1", self.git(root, "rev-list", "--count", "HEAD"))
                missing = subprocess.run(["git", "-C", str(root), "cat-file", "-e", self.checker.SOURCE_COMMIT],
                                         capture_output=True)
                self.assertNotEqual(0, missing.returncode)
                self.git(root, "diff", "--exit-code")
                self.git(root, "diff", "--cached", "--exit-code")

    def test_connector_fixture_adaptation_binds_exact_original_and_current_metadata(self):
        root = self.fixture()
        parity = root / ".github/distribution/source-parity.v1.json"
        original = parity.read_text()
        self.assertEqual([], self.checker.validate_export(root))
        for key, wrong in (("path", "tests/conformance/test_installer_feedback.py"),
                           ("export_source_repository", "unknown/repository"),
                           ("export_source_commit", "0" * 40),
                           ("export_source_blob", "0" * 40), ("export_sha256", "0" * 64),
                           ("export_mode", "100755"), ("target_sha256", "0" * 64),
                           ("target_blob", "0" * 40), ("target_mode", "100755"),
                           ("scope", "arbitrary-changes"), ("extra", "unapproved")):
            with self.subTest(key=key):
                value = json.loads(original)
                value["explicit_update"]["fixture_adaptation"][key] = wrong
                parity.write_text(json.dumps(value))
                self.assertTrue(self.checker.validate_export(root))
        value = json.loads(original)
        del value["explicit_update"]["fixture_adaptation"]
        parity.write_text(json.dumps(value))
        self.assertTrue(self.checker.validate_export(root))
        for key in self.checker.CONNECTOR_FIXTURE_ADAPTATION:
            with self.subTest(missing=key):
                value = json.loads(original)
                del value["explicit_update"]["fixture_adaptation"][key]
                parity.write_text(json.dumps(value))
                self.assertTrue(self.checker.validate_export(root))
        parity.write_text(original)
        for key, wrong in (("path", "README.md"), ("source_blob", "0" * 40),
                           ("sha256", "0" * 64), ("mode", "100755"), ("extra", "unapproved")):
            with self.subTest(original_binding=key):
                row = dict(self.checker.CONNECTOR_FIXTURE_EXPORT, **{key: wrong})
                self.assertTrue(self.checker.validate_connector_fixture_adaptation(root, row))

    def test_connector_fixture_resealed_drift_cannot_exempt_any_export(self):
        root = self.fixture()
        fixture = root / self.checker.CONNECTOR_FIXTURE_PATH
        fixture.write_bytes(fixture.read_bytes() + b"\n# unapproved drift\n")
        current_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        parity = root / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        value["explicit_update"]["fixture_adaptation"]["target_sha256"] = current_hash
        data = fixture.read_bytes()
        value["explicit_update"]["fixture_adaptation"]["target_blob"] = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        for row in value["connector_companion"]["target_files"]:
            if row["path"] == self.checker.CONNECTOR_FIXTURE_PATH:
                row["sha256"] = current_hash
        parity.write_text(json.dumps(value))
        self.assertTrue(self.checker.validate_export(root))
        self.assertTrue(self.checker.validate(root))
        root = self.fixture()
        unrelated = root / "tests/conformance/test_installer_feedback.py"
        unrelated.write_bytes(unrelated.read_bytes() + b"\n# unrelated drift\n")
        self.assertIn("approved export file changed: tests/conformance/test_installer_feedback.py",
                      self.checker.validate_export(root))

    def test_workflow_current_adaptations_are_exact_and_separate_from_export(self):
        root = self.fixture()
        parity = root / ".github/distribution/source-parity.v1.json"
        original = parity.read_bytes()
        self.assertEqual([], self.checker.validate_export(root))
        for mutation in ("missing", "source", "scope", "extra", "baseline", "target", "export", "reorder"):
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                record = value["workflow_parity"]
                if mutation == "missing": del value["workflow_parity"]
                elif mutation == "source": record["source_commit"] = "0"*40
                elif mutation == "scope": record["export_adaptations"].pop()
                elif mutation == "extra": record["unreviewed"] = True
                elif mutation == "baseline": record["baseline_sha256"] = "0"*64
                elif mutation == "target": record["target_files"][0]["sha256"] = "0"*64
                elif mutation == "export": record["export_adaptations"][0]["export"]["sha256"] = "0"*64
                else: record["target_files"].reverse()
                parity.write_text(json.dumps(value))
                self.assertTrue(self.checker.validate(root))
                result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts/check-installer.py")],
                                        capture_output=True, text=True, timeout=30)
                self.assertNotEqual(0, result.returncode)
        parity.write_bytes(original)
        helper = root / ".github/distribution/payload/.github/scripts/check-task-ritual.sh"
        helper.write_bytes(helper.read_bytes() + b"\n# unapproved\n")
        value = json.loads(original)
        for row in value["workflow_parity"]["export_adaptations"]:
            if row["path"] == str(helper.relative_to(root)):
                data = helper.read_bytes()
                row["target_sha256"] = hashlib.sha256(data).hexdigest()
                row["target_blob"] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        parity.write_text(json.dumps(value))
        self.assertTrue(self.checker.validate_export(root))
        baseline = root / "tests/fixtures/workflow-parity-baseline.json"
        baseline.write_bytes(baseline.read_bytes() + b"\n")
        self.assertTrue(self.checker.validate(root))
        checker = root / ".github/scripts/check-installer.py"
        checker.write_text(checker.read_text().replace("def validate_workflow_parity(root):", "def removed_workflow_guard(root):"))
        self.assertIn("mandatory installer validation unavailable", self.checker.validate(root))

    def test_readable_nonexecutable_permissions_are_accepted(self):
        for mode in (0o600, 0o640, 0o644, 0o664, 0o444):
            for path in (RECORD, "README.md"):
                with self.subTest(mode=f"{mode:04o}", path=path):
                    root = self.fixture()
                    (root / path).chmod(mode)
                    self.assertEqual([], self.checker.validate(root))

    def test_each_executable_permission_bit_refuses(self):
        for mode in (0o744, 0o654, 0o645):
            with self.subTest(mode=f"{mode:04o}"):
                root = self.fixture()
                (root / RECORD).chmod(mode)
                self.assertTrue(self.checker.validate(root))

    def test_each_special_permission_bit_refuses(self):
        for mode in (0o4644, 0o2644, 0o1644):
            with self.subTest(mode=f"{mode:04o}"):
                root = self.fixture()
                (root / RECORD).chmod(mode)
                self.assertTrue(self.checker.validate(root))

    def test_fixtures_are_bound_to_exact_old_source_bytes(self):
        manifest = json.loads((ROOT / "tests/fixtures/history/manifest.json").read_text())
        self.assertEqual(20, len(manifest["entries"]))
        for row in manifest["entries"]:
            self.assertTrue(self.checker.history_bytes(ROOT, commit=row["source_commit"], path=row["source_path"]))
        with self.assertRaises(ValueError):
            self.checker.history_bytes(ROOT, commit="0" * 40, path="README.md")
        root = self.fixture()
        blob = root / "tests/fixtures/history/blobs" / manifest["entries"][0]["sha256"]
        blob.write_bytes(blob.read_bytes() + b"changed")
        self.assertTrue(self.checker.validate_export(root))

    def test_missing_links_and_product_ci_edges_refuse(self):
        root = self.fixture()
        readme = root / "README.md"
        readme.write_text(readme.read_text() + "\n[broken](missing.md)\n")
        self.assertTrue(self.checker.validate_navigation(root))
        root = self.fixture()
        workflow = root / ".github/workflows/ci.yml"
        workflow.write_text(workflow.read_text().replace("run: python3 -I .github/scripts/check-product.py", "run: true"))
        self.assertTrue(self.checker.validate_policy(root))
        for replacement in ("# run: python3 -I .github/scripts/check-product.py",
                            "run: echo 'python3 -I .github/scripts/check-product.py'"):
            root = self.fixture()
            workflow = root / ".github/workflows/ci.yml"
            workflow.write_text(workflow.read_text().replace("run: python3 -I .github/scripts/check-product.py", replacement))
            self.assertTrue(self.checker.validate_policy(root))

    def test_unsafe_export_files_fail_without_reading_special_inputs(self):
        for kind in ("symlink", "fifo", "hardlink"):
            with self.subTest(kind=kind):
                root = self.fixture()
                path = root / RECORD
                if kind == "hardlink":
                    os.link(path, root / "second-link")
                else:
                    path.unlink()
                    if kind == "symlink": path.symlink_to(root / "README.md")
                    else: os.mkfifo(path)
                self.assertTrue(self.checker.validate_export(root))

    def test_native_powershell_ci_step_is_required(self):
        root = self.fixture()
        workflow = root / ".github/workflows/ci.yml"
        original = workflow.read_text()
        self.assertEqual([], self.checker.validate_policy(root))
        for replacement in ("", "        shell: bash\n", "        shell: sh\n",
                            "        # shell: pwsh\n"):
            with self.subTest(shell=replacement.strip()):
                workflow.write_text(original.replace("        shell: pwsh\n", replacement))
                self.assertIn("mandatory native PowerShell CI step missing or changed",
                              self.checker.validate_policy(root))
        workflow.write_text(original.replace("        shell: pwsh\n", "").replace(
            "      - name: Run product conformance tests\n",
            "      - name: Run product conformance tests\n        shell: pwsh\n"))
        self.assertIn("mandatory native PowerShell CI step missing or changed",
                      self.checker.validate_policy(root))

    def test_powershell_ci_requires_the_actual_version_command(self):
        root = self.fixture()
        workflow = root / ".github/workflows/ci.yml"
        original = workflow.read_text()
        command = "        run: $PSVersionTable.PSVersion.ToString()\n"
        for replacement in ("", "        # run: $PSVersionTable.PSVersion.ToString()\n",
                            "        run: echo '$PSVersionTable.PSVersion.ToString()'\n",
                            "        run: true\n",
                            "        run: pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'\n"):
            with self.subTest(command=replacement.strip()):
                workflow.write_text(original.replace(command, replacement))
                self.assertIn("mandatory product CI edge missing",
                              self.checker.validate_policy(root))

    def test_powershell_ci_cannot_be_commented_skipped_or_suppressed(self):
        root = self.fixture()
        workflow = root / ".github/workflows/ci.yml"
        original = workflow.read_text()
        step = ("      - name: Require real PowerShell test host\n"
                "        shell: pwsh\n"
                "        run: $PSVersionTable.PSVersion.ToString()\n")
        for replacement in ("", "\n".join("# " + line for line in step.splitlines()) + "\n",
                            step + "        if: false\n",
                            step + "        continue-on-error: true\n",
                            step + "        shell: bash\n",
                            step + "      # misleading step boundary\n        shell: bash\n"):
            with self.subTest(step=replacement):
                workflow.write_text(original.replace(step, replacement))
                self.assertIn("mandatory native PowerShell CI step missing or changed",
                              self.checker.validate_policy(root))
        workflow.write_text(original.replace("  conformance:\n",
                                             "  conformance:\n    if: false\n"))
        self.assertIn("unsupported or bypassed product CI edge",
                      self.checker.validate_policy(root))


if __name__ == "__main__":
    unittest.main()
