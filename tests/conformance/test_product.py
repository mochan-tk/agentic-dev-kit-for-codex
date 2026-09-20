"""Clean-root export regressions; real Git checkout modes, no old Git history."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

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
                     ".github/scripts/scaffold-install.sh"):
            altered = self.fixture()
            (altered / path).unlink()
            self.assertTrue(self.checker.validate(altered))

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
