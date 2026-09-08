"""Disposable-adopter regressions derived from the frozen scaffold installer tests."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / ".github/scripts/scaffold-init.sh"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-installer-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.target = self.base / "adopter with spaces"
        self.target.mkdir()
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(self.target)], check=True)

    def run_install(self, *args, source=ROOT, target=None):
        env = dict(os.environ, SCAFFOLD_SOURCE_DIR=str(source), LC_ALL="C")
        return subprocess.run(["bash", str(INSTALLER), *args, str(target or self.target)], env=env,
                              capture_output=True, text=True, timeout=30)

    def snapshot(self, root):
        if not root.exists():
            return None
        return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
                else ("file", hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file()
                else ("directory", "") for p in root.rglob("*")}

    def clone_source(self):
        source = self.base / "local source"
        shutil.copytree(ROOT / ".github/distribution", source / ".github/distribution")
        return source

    def assert_refused_unchanged(self, *args, source=ROOT, target=None):
        target = target or self.target
        before = self.snapshot(target)
        result = self.run_install(*args, source=source, target=target)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertEqual(before, self.snapshot(target))
        return result

    def test_dry_run_preserves_target_git_and_source(self):
        before = self.snapshot(self.target)
        source_before = self.snapshot(ROOT / ".github/distribution")
        result = self.run_install("--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("install", result.stdout)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertEqual(source_before, self.snapshot(ROOT / ".github/distribution"))

    def test_default_is_dry_run(self):
        before = self.snapshot(self.target)
        self.assertEqual(0, self.run_install().returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_absent_dry_run_target_stays_absent(self):
        target = self.base / "absent"
        result = self.run_install("--dry-run", target=target)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(target.exists())

    def test_apply_installs_exact_payload_without_git_mutation(self):
        git_before = self.snapshot(self.target / ".git")
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = ROOT / PAYLOAD
        files = [p for p in payload.rglob("*") if p.is_file()]
        self.assertEqual(47, len(files))
        for source in files:
            self.assertEqual(source.read_bytes(), (self.target / source.relative_to(payload)).read_bytes())
        self.assertEqual(git_before, self.snapshot(self.target / ".git"))
        self.assertFalse((self.target / ".github/governance").exists())
        self.assertFalse((self.target / "tests/conformance/results.json").exists())

    def test_identical_reapply_is_noop(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        before = self.snapshot(self.target)
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertNotIn("install\t", result.stdout)

    def test_tuned_instance_seed_and_unrelated_files_are_preserved(self):
        for name in ["AGENTS.md", "README.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md", "app/private.txt", "SCAFFOLD-CHANGELOG.md"]:
            p = self.target / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("adopter truth\n")
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        for name in ["AGENTS.md", "README.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md", "app/private.txt", "SCAFFOLD-CHANGELOG.md"]:
            self.assertEqual("adopter truth\n", (self.target / name).read_text())

    def test_differing_engine_collision_refuses_before_any_write(self):
        p = self.target / ".agents/skills/verification/SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text("adopter modified engine\n")
        self.assert_refused_unchanged("--apply")

    def test_unknown_force_upgrade_and_conflicting_modes_refuse(self):
        for args in [("--force",), ("--upgrade",), ("--wat",), ("--apply", "--dry-run")]:
            with self.subTest(args=args):
                self.assert_refused_unchanged(*args)

    def test_apply_requires_existing_git_root(self):
        plain = self.base / "plain"
        plain.mkdir()
        self.assert_refused_unchanged("--apply", target=plain)
        sub = self.target / "sub"
        sub.mkdir()
        self.assert_refused_unchanged("--apply", target=sub)

    def test_target_root_and_ancestor_symlinks_refuse(self):
        link = self.base / "target-link"
        link.symlink_to(self.target, target_is_directory=True)
        self.assert_refused_unchanged("--apply", target=link)
        parent = self.base / "linked-parent"
        parent.symlink_to(self.base, target_is_directory=True)
        self.assert_refused_unchanged("--dry-run", target=parent / self.target.name)

    def test_target_leaf_ancestor_and_broken_symlinks_refuse(self):
        for name in ["AGENTS.md", ".agents", ".github/docs"]:
            with self.subTest(name=name):
                p = self.target / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.symlink_to(self.base / "missing")
                self.assert_refused_unchanged("--apply")
                p.unlink()

    def test_file_directory_collisions_refuse(self):
        (self.target / "AGENTS.md").mkdir()
        self.assert_refused_unchanged("--apply")
        (self.target / "AGENTS.md").rmdir()
        (self.target / ".github").write_text("not a directory")
        self.assert_refused_unchanged("--apply")

    def test_source_root_ancestor_and_leaf_symlinks_refuse(self):
        source = self.clone_source()
        link = self.base / "source-link"
        link.symlink_to(source, target_is_directory=True)
        self.assert_refused_unchanged("--apply", source=link)
        p = source / PAYLOAD / "AGENTS.md"
        original = p.read_bytes()
        p.unlink()
        other = self.base / "outside.md"
        other.write_bytes(original)
        p.symlink_to(other)
        self.assert_refused_unchanged("--apply", source=source)

    def test_payload_digest_drift_refuses(self):
        source = self.clone_source()
        with (source / PAYLOAD / "AGENTS.md").open("a") as out:
            out.write("changed\n")
        self.assert_refused_unchanged("--apply", source=source)

    def test_extra_payload_and_unsafe_duplicate_inventory_refuse(self):
        source = self.clone_source()
        (source / PAYLOAD / "extra.md").write_text("unreviewed")
        self.assert_refused_unchanged("--apply", source=source)
        (source / PAYLOAD / "extra.md").unlink()
        inventory = source / INVENTORY
        original = inventory.read_text()
        for text in [original + original.splitlines()[1] + "\n", original.replace("AGENTS.md", "../escape", 1),
                     original.replace("AGENTS.md", "agents.md", 1)]:
            inventory.write_text(text)
            self.assert_refused_unchanged("--apply", source=source)

    def test_missing_source_refuses(self):
        self.assert_refused_unchanged("--apply", source=self.base / "missing-source")

    def test_self_consistent_redirected_inventory_refuses(self):
        source = self.clone_source()
        payload = source / PAYLOAD
        (payload / "other.md").write_bytes((payload / "AGENTS.md").read_bytes())
        (payload / "AGENTS.md").unlink()
        inventory = source / INVENTORY
        inventory.write_text(inventory.read_text().replace("AGENTS.md", "other.md"))
        self.assert_refused_unchanged("--apply", source=source)

    def test_enumeration_failure_refuses_even_after_all_known_entries(self):
        fake = self.base / "bin"
        fake.mkdir()
        find = fake / "find"
        find.write_text('#!/bin/sh\n/usr/bin/find "$@"\nexit 1\n')
        find.chmod(0o755)
        before = self.snapshot(self.target)
        result = subprocess.run(["bash", str(INSTALLER), "--apply", str(self.target)],
                                env=dict(os.environ, SCAFFOLD_SOURCE_DIR=str(ROOT),
                                         PATH=str(fake) + os.pathsep + os.environ["PATH"]),
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_non_git_source_provenance_is_not_claimed_clean(self):
        result = self.run_install("--dry-run", source=self.clone_source())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("source-commit=unknown", result.stdout)

    def test_windows_drive_source_and_target_use_existing_cygpath(self):
        fake = self.base / "bin"
        fake.mkdir()
        converter = fake / "cygpath"
        converter.write_text("""#!/bin/sh
[ "$1" = -u ] && [ "$2" = -- ] || exit 1
case "$3" in
  C:/*) printf '%s\n' "$FIXTURE_SOURCE" ;;
  D:*) printf '%s\n' "$FIXTURE_TARGET" ;;
  *) exit 1 ;;
esac
""")
        converter.chmod(0o755)
        env = dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"],
                   SCAFFOLD_SOURCE_DIR="C:/reviewed/source", FIXTURE_SOURCE=str(ROOT),
                   FIXTURE_TARGET=str(self.target))
        git_before = self.snapshot(self.target / ".git")
        result = subprocess.run(["/bin/bash", str(INSTALLER), "--apply", "D:\\adopter"],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(git_before, self.snapshot(self.target / ".git"))
        self.assertEqual((ROOT / PAYLOAD / "AGENTS.md").read_bytes(),
                         (self.target / "AGENTS.md").read_bytes())

    def test_windows_drive_conversion_unavailable_or_invalid_refuses(self):
        fake = self.base / "bin"
        fake.mkdir()
        command = ["/bin/bash", str(INSTALLER), "--apply", "D:/adopter"]
        env = dict(os.environ, PATH=str(fake), SCAFFOLD_SOURCE_DIR="C:/source")
        before = self.snapshot(self.target)
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("require Git Bash cygpath", result.stderr)
        converter = fake / "cygpath"
        for script in ("#!/bin/sh\nexit 1\n", "#!/bin/sh\nprintf 'relative-path\\n'\n"):
            converter.write_text(script)
            converter.chmod(0o755)
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_frontier_failure_never_becomes_empty_success(self):
        fake = self.base / "bin"
        fake.mkdir()
        gh = fake / "gh"
        gh.write_text("#!/bin/sh\nexit 1\n")
        gh.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / PAYLOAD / ".agents/skills/plan-management/scripts/frontier.sh")],
                                env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"]),
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("No open Task", result.stdout)

    def test_inventory_checker_accepts_tree_and_rejects_provenance_drift(self):
        spec = importlib.util.spec_from_file_location("installer_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual([], checker.validate(ROOT))
        source = self.clone_source()
        parity = source / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        value["source_commit"] = "0" * 40
        parity.write_text(json.dumps(value))
        self.assertTrue(checker.validate(source))

    def test_frontier_keeps_ready_and_blocked_distinct_and_refuses_later_error(self):
        fake = self.base / "bin"
        fake.mkdir()
        gh = fake / "gh"
        gh.write_text("""#!/bin/sh
case "$2" in
  list) printf '1\tReady Task\n2\tDependent Task\n' ;;
  view)
    case "$3" in
      1) exit 0 ;;
      2) if [ "$FIXTURE_FAILURE" = yes ]; then exit 1; fi; printf '3\n' ;;
      3) printf '%s\n' "$FIXTURE_STATE" ;;
      *) exit 1 ;;
    esac ;;
  *) exit 1 ;;
esac
""")
        gh.chmod(0o755)
        command = ["bash", str(ROOT / PAYLOAD / ".agents/skills/plan-management/scripts/frontier.sh"), "--all"]
        for state, failure, succeeds in (("OPEN", "no", True), ("CLOSED", "no", True),
                                         ("UNKNOWN", "no", False), ("OPEN", "yes", False)):
            with self.subTest(state=state, failure=failure):
                result = subprocess.run(command, env=dict(os.environ,
                    PATH=str(fake) + os.pathsep + os.environ["PATH"],
                    FIXTURE_STATE=state, FIXTURE_FAILURE=failure),
                    capture_output=True, text=True, timeout=5)
                if succeeds:
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("#1\tReady Task", result.stdout)
                    self.assertIn("#2\tDependent Task", result.stdout)
                    self.assertEqual(state == "OPEN", "== Blocked ==" in result.stdout)
                else:
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual("", result.stdout, "never publish a partial actionable frontier")

    def test_checker_rejects_wrong_preservation_class_and_malformed_parity_row(self):
        spec = importlib.util.spec_from_file_location("installer_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        source = self.clone_source()
        inventory = source / INVENTORY
        original = inventory.read_text()
        inventory.write_text(original.replace("\tengine\t", "\ttuned\t", 1))
        self.assertTrue(checker.validate(source))
        self.assert_refused_unchanged("--apply", source=source)
        inventory.write_text(original)
        parity = source / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        value["files"][0] = "not-a-record"
        parity.write_text(json.dumps(value))
        self.assertTrue(checker.validate(source))


if __name__ == "__main__":
    unittest.main()
