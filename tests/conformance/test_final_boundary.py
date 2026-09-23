"""Audited final boundaries: actual local tools, disposable roots, synthetic APIs."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ".github/distribution/payload"
ENGINE = ".github/scripts/scaffold-install.sh"
TUNING = ".github/scripts/tuning-status.sh"
BASELINE = "tests/fixtures/final-boundary-baseline.json"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/conformance" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def old_bytes(path):
    record = json.loads((ROOT / BASELINE).read_bytes())
    return base64.b64decode(next(row["base64"] for row in record["files"] if row["path"] == path), validate=True)


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
            else ("file", p.stat().st_mode, p.read_bytes()) if p.is_file()
            else ("directory", p.stat().st_mode) for p in root.rglob("*")}


class FinalBoundaryTests(unittest.TestCase):
    def fixture(self, name, cls):
        kind = getattr(module(name), cls)
        if "setUpClass" in kind.__dict__:
            kind.setUpClass()
            self.addCleanup(kind.tearDownClass)
        fixture = kind(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_install_rejects_administration_and_bare_without_mutation(self):
        fixture = self.fixture("test_installer", "InstallerTests")
        bare = fixture.base / "bare"
        subprocess.run(["git", "init", "--bare", "--template=", "-q", str(bare)], check=True)
        for target in (fixture.target / ".git", bare):
            with self.subTest(target=target.name):
                before = snapshot(target)
                result = fixture.run_install("--apply", target=target)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual(before, snapshot(target))

    def test_updater_rejects_administration_and_bare_before_acquisition(self):
        fixture = self.fixture("test_installer_update", "UpdateTests")
        bare = fixture.base / "bare"
        fixture.git(fixture.base, "init", "--bare", "--template=", "-q", str(bare))
        for target in (fixture.target / ".git", bare):
            for mode in ("--dry-run", "--apply"):
                with self.subTest(target=target.name, mode=mode):
                    before = snapshot(target)
                    result = fixture.run_entry(mode, str(target))
                    self.assertNotEqual(0, result.returncode, result.stdout)
                    self.assertNotIn("Acquiring", result.stdout)
                    self.assertFalse(fixture.recovery.exists())
                    self.assertEqual(before, snapshot(target))

    def test_external_bootstrap_rejects_all_identical_invalid_targets(self):
        fixture = self.fixture("test_installer_bootstrap", "BootstrapTests")
        bare = fixture.base / "bare"
        fixture.command(fixture.base, "init", "--bare", "--template=", "-q", str(bare))
        for target in (fixture.target / ".git", bare):
            shutil.copytree(ROOT / PAYLOAD, target, dirs_exist_ok=True)
            before = snapshot(target)
            result = fixture.run_entry(str(target), saved=True)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertNotIn("Already installed", result.stdout)
            self.assertEqual(before, snapshot(target))

    def test_setup_rejects_inherited_context_even_empty_before_git(self):
        fixture = self.fixture("test_adopter_ci", "AdopterTests")
        donor = fixture.work / "donor"
        donor.mkdir()
        subprocess.run(["git", "init", "--template=", "-q", str(donor)], check=True)
        variables = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG",
                     "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_NAMESPACE",
                     "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
        contexts = [{name: ""} for name in variables]
        contexts += [{"GIT_DIR": str(donor / ".git"), "GIT_WORK_TREE": str(fixture.target)},
                     {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.worktree", "GIT_CONFIG_VALUE_0": str(fixture.target)},
                     {"GIT_CONFIG_PARAMETERS": "'core.worktree=" + str(fixture.target) + "'"}]
        call = fixture.work / "git-called"
        git = fixture.fixture.bin / "git"
        git.write_text("#!/bin/sh\n: > " + shlex.quote(str(call)) + "\nexit 77\n")
        git.chmod(0o755)
        before, donor_before = snapshot(fixture.target), snapshot(donor)
        environment = dict(fixture.env)
        for context in contexts:
            for args in ((), ("--apply",)):
                with self.subTest(context=context, args=args):
                    fixture.env = dict(environment, **context)
                    result = fixture.setup(*args)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("Git context override", result.stderr)
                    self.assertFalse(call.exists(), "context must refuse before the first Git command")
                    self.assertEqual(before, snapshot(fixture.target))
                    self.assertEqual(donor_before, snapshot(donor))

    def test_setup_real_misdirection_preserves_nonrepository_target_and_donor(self):
        fixture = self.fixture("test_adopter_ci", "AdopterTests")
        donor = fixture.work / "donor"
        donor.mkdir()
        subprocess.run(["git", "init", "--template=", "-q", str(donor)], check=True)
        (donor / "staged").write_text("donor content\n")
        subprocess.run(["git", "-C", str(donor), "add", "staged"], check=True)
        shutil.rmtree(fixture.target / ".git")
        before, donor_before = snapshot(fixture.target), snapshot(donor)
        contexts = [dict(GIT_DIR=str(donor / ".git"), GIT_WORK_TREE=str(fixture.target)),
                    dict(GIT_DIR=str(donor / ".git"), GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.worktree", GIT_CONFIG_VALUE_0=str(fixture.target)),
                    dict(GIT_DIR=str(donor / ".git"), GIT_CONFIG_PARAMETERS="'core.worktree=" + str(fixture.target) + "'")]
        environment = dict(fixture.env)
        for context in contexts:
            fixture.env = dict(environment, **context)
            result = fixture.setup("--apply")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Git context override", result.stderr)
            self.assertEqual(before, snapshot(fixture.target))
            self.assertEqual(donor_before, snapshot(donor))

    def test_setup_preserves_ordinary_git_config_isolation(self):
        fixture = self.fixture("test_adopter_ci", "AdopterTests")
        fixture.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        before = snapshot(fixture.target)
        result = fixture.setup()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, snapshot(fixture.target))

    def test_local_upgrade_and_recorded_rollback_refuse_invalid_roots(self):
        fixture = self.fixture("test_installer", "InstallerTests")
        old = fixture.base / "old"
        new = fixture.base / "new"
        for source in (old, new):
            shutil.copytree(ROOT / PAYLOAD, source / PAYLOAD)
            (source / ".github/distribution/payload.v1.tsv").write_bytes((ROOT / ".github/distribution/payload.v1.tsv").read_bytes())
        (old / PAYLOAD / TUNING).write_bytes(old_bytes(PAYLOAD + "/" + TUNING))
        module("test_installer_update").UpdateTests.reseal(old)
        old_engine = fixture.base / "audit-engine.sh"
        old_engine.write_bytes(old_bytes(ENGINE))
        bare = fixture.base / "bare"
        subprocess.run(["git", "init", "--bare", "--template=", "-q", str(bare)], check=True)
        for index, target in enumerate((fixture.target / ".git", bare)):
            shutil.copytree(old / PAYLOAD, target, dirs_exist_ok=True)
            transaction = fixture.base / ("transaction-" + str(index))
            environment = dict(os.environ, SCAFFOLD_SOURCE_DIR=str(new), LC_ALL="C")
            args = ["--upgrade", "--old-source", str(old), "--transaction", str(transaction), "--apply", str(target)]
            before = snapshot(target)
            result = subprocess.run(["/bin/bash", str(ROOT / ENGINE), *args], env=environment, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertFalse(transaction.exists())
            self.assertEqual(before, snapshot(target))
            # Preserve a real old-base operation record, then prove that the
            # repaired rollback refuses its invalid target before restoration.
            result = subprocess.run(["/bin/bash", str(old_engine), *args], env=environment, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            before, record_before = snapshot(target), snapshot(transaction)
            for mode in ("--dry-run", "--apply"):
                result = subprocess.run(["/bin/bash", str(ROOT / ENGINE), "--rollback", "--transaction", str(transaction), mode, str(target)], env=environment, capture_output=True, text=True)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual(before, snapshot(target))
                self.assertEqual(record_before, snapshot(transaction))

    def test_actual_audit_base_update_preserves_modes_work_and_offline_rollback(self):
        fixture = self.fixture("test_installer_update", "UpdateTests")
        shutil.copytree(ROOT / PAYLOAD, fixture.source / PAYLOAD, dirs_exist_ok=True)
        (fixture.source / ENGINE).write_bytes(old_bytes(ENGINE))
        (fixture.source / PAYLOAD / TUNING).write_bytes(old_bytes(PAYLOAD + "/" + TUNING))
        fixture.reseal(fixture.source)
        old = fixture.commit(fixture.source)
        (fixture.target / TUNING).write_bytes(old_bytes(PAYLOAD + "/" + TUNING))
        shutil.copyfile(ROOT / ENGINE, fixture.source / ENGINE)
        shutil.copyfile(ROOT / PAYLOAD / TUNING, fixture.source / PAYLOAD / TUNING)
        fixture.reseal(fixture.source)
        new = fixture.commit(fixture.source)
        for name, kind, _ in fixture.rows:
            if kind != "engine":
                (fixture.target / name).write_text("adopter-owned\n")
                (fixture.target / name).chmod(0o600)
        (fixture.target / "notes").write_text("staged\n")
        fixture.git(fixture.target, "add", "notes")
        (fixture.target / "notes").write_text("unstaged\n")
        before = fixture.snapshot()
        fixture.success(fixture.run_entry(old=old, new=new))
        self.assertEqual(before, fixture.snapshot())
        fixture.success(fixture.run_entry("--apply", old=old, new=new))
        after = fixture.snapshot()
        self.assertEqual([TUNING], sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))
        self.assertEqual(old_bytes(ENGINE), (fixture.recovery / "old" / ENGINE).read_bytes())
        self.assertEqual((ROOT / ENGINE).read_bytes(), (fixture.recovery / "new" / ENGINE).read_bytes())
        installed = (fixture.target / TUNING).read_bytes()
        (fixture.target / TUNING).write_bytes(installed + b"\n# adopter edit\n")
        edited = fixture.snapshot()
        self.assertNotEqual(0, fixture.rollback("--apply").returncode)
        self.assertEqual(edited, fixture.snapshot())
        (fixture.target / TUNING).write_bytes(installed)
        fixture.success(fixture.rollback("--apply"))
        self.assertEqual(before, fixture.snapshot())

    def test_normal_linked_submodule_and_nonrepository_preview_controls(self):
        fixture = self.fixture("test_installer", "InstallerTests")
        (fixture.target / "sentinel").write_text("fixture\n")
        fixture.commit_adopter("fixture")
        linked = fixture.base / "linked"
        fixture.git("worktree", "add", "--detach", "--quiet", str(linked), "HEAD")
        subsource = fixture.base / "subsource"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(fixture.target), str(subsource)], check=True)
        fixture.git("-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(subsource), "submodule")
        for target in (fixture.target, linked, fixture.target / "submodule"):
            result = fixture.run_install("--apply", target=target)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            result = fixture.run_install("--apply", target=target)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        preview = fixture.base / "nonrepository"
        preview.mkdir()
        before = snapshot(preview)
        self.assertEqual(0, fixture.run_install("--dry-run", target=preview).returncode)
        self.assertEqual(before, snapshot(preview))

    def test_governance_search_errors_are_unknown_and_profile_scoped(self):
        fixture = self.fixture("test_source_first_governance", "GovernanceTests")
        for command in ("grep", "awk"):
            actual = shutil.which(command)
            shim = fixture.bin / command
            for code in ((2, 7) if command == "grep" else (1, 2, 7)):
                shim.write_text("#!/bin/bash\ncase \"${*: -1}\" in */co.json) exit " + str(code)
                                + ";; esac\nexec " + shlex.quote(actual) + " \"$@\"\n")
                shim.chmod(0o755)
                for profile in ("team", "solo", "single-maintainer"):
                    fixture.baseline(profile)
                    result = fixture.sensor(profile=profile)
                    self.assertIn("codeowners.tuning\tUNKNOWN\t", result.stdout)
                    self.assertEqual(3 if profile == "team" else 0, result.returncode, result.stdout + result.stderr)
                result = fixture.sensor(profile="single-maintainer", posture="source-template")
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("codeowners.tuning\tN/A\t", result.stdout)
            shim.unlink()

    def test_current_receipt_exception_is_exact_dated_and_document_scoped(self):
        fixture = self.fixture("test_product", "ProductTests")
        root = fixture.fixture()
        checker = fixture.checker
        self.assertEqual([], checker.validate_navigation(root))
        path = root / "docs/parity-status.md"
        original = path.read_text()
        receipt = sorted(checker.CURRENT_RECEIPTS)[0]
        for replacement in (receipt + "/extra", receipt + "#extra", receipt.replace("5788166242", "5788166243"),
                            receipt.replace("/issues/12", "/issues/19"), receipt.replace("/issues/12", "/pull/12")):
            path.write_text(original.replace(receipt, replacement))
            self.assertTrue(checker.validate_navigation(root), replacement)
        path.write_text(original.replace("## Current acceptance as of 2026-09-23", "## Undated acceptance"))
        self.assertTrue(checker.validate_navigation(root))
        path.write_text(original)
        other = root / "docs/product-scope.md"
        other.write_text(other.read_text() + "\n[receipt](" + receipt + ")\n")
        self.assertTrue(checker.validate_navigation(root))

    def test_final_contract_is_mandatory_in_both_production_entrypoints(self):
        fixture = self.fixture("test_product", "ProductTests")
        root = fixture.fixture()
        (root / BASELINE).unlink()
        for entry in ("check-product.py", "check-installer.py"):
            result = subprocess.run([sys.executable, "-I", str(root / ".github/scripts" / entry)], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("final boundary", result.stdout)

    def test_resealing_cannot_bypass_exact_repaired_files_or_old_baseline(self):
        fixture = self.fixture("test_product", "ProductTests")
        root = fixture.fixture()
        spec = importlib.util.spec_from_file_location("final_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual([], checker.validate_final_boundary(root))
        parity = root / checker.PARITY
        original_record = parity.read_bytes()
        for name in checker.FINAL_BASE_PATHS:
            path = root / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n# superficial reseal\n")
            record = json.loads(original_record)
            for row in record["final_boundary"]["target_files"]:
                if row["path"] == name:
                    row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            for row in record["final_boundary"]["export_adaptations"]:
                if row["path"] == name:
                    data = path.read_bytes()
                    row["target_sha256"] = hashlib.sha256(data).hexdigest()
                    row["target_blob"] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            parity.write_text(json.dumps(record))
            self.assertTrue(checker.validate_final_boundary(root), name)
            path.write_bytes(original)
        parity.write_bytes(original_record)
        baseline = root / BASELINE
        baseline.write_bytes(baseline.read_bytes() + b"\n")
        record = json.loads(original_record)
        record["final_boundary"]["baseline_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
        parity.write_text(json.dumps(record))
        self.assertTrue(checker.validate_final_boundary(root))


class StartupBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="startup-boundary-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.script = self.work / TUNING
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / PAYLOAD / TUNING, self.script)
        self.required = self.work / ".github/codex-instructions.md"
        self.required.write_text("Project instructions.\n")
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], LC_ALL="C")

    def run_status(self, mode="--quiet"):
        return subprocess.run(["/bin/bash", str(self.script), mode], cwd=self.work,
                              env=self.env, capture_output=True, text=True, timeout=10)

    def error_modes(self):
        for mode in ("--quiet", "", "--ci"):
            result = self.run_status(mode)
            self.assertEqual(0 if mode == "--ci" else 2, result.returncode, result.stdout + result.stderr)
            if mode == "--quiet":
                self.assertEqual("", result.stdout + result.stderr)
            else:
                self.assertIn("observation", result.stdout.lower())
                self.assertNotIn("TUNED:", result.stdout)
                if mode == "--ci":
                    self.assertIn("::warning::", result.stdout)

    def test_required_missing_directory_and_actual_nonroot_read_failure(self):
        self.required.unlink()
        self.error_modes()
        self.required.mkdir()
        self.error_modes()
        self.required.rmdir()
        self.required.write_text("CUSTOMIZE: still pending\n")
        if os.geteuid() == 0:
            self.skipTest("actual permission denial requires a nonroot test process")
        self.required.chmod(0)
        self.addCleanup(self.required.chmod, 0o644)
        self.error_modes()

    def test_optional_files_and_advisory_agreements_are_not_required(self):
        self.assertEqual(0, self.run_status().returncode)
        agreements = self.work / ".github/docs/agreements"
        agreements.mkdir(parents=True)
        (agreements / "notes.md").write_text("(example — replace)\n")
        self.assertEqual(0, self.run_status().returncode)
        self.required.write_text("CUSTOMIZE: pending\n")
        self.assertEqual(1, self.run_status().returncode)
        self.assertEqual(0, self.run_status("--ci").returncode)

    def test_area_and_directory_actual_nonroot_read_failures(self):
        if os.geteuid() == 0:
            self.skipTest("actual permission denial requires a nonroot test process")
        directory = self.work / ".github/instructions"
        directory.mkdir()
        area = directory / "area.instructions.md"
        area.write_text("CUSTOMIZE: area\n")
        self.required.write_text("CUSTOMIZE: already found\n")
        for path, mode in ((area, 0o644), (directory, 0o755)):
            path.chmod(0)
            try:
                self.error_modes()
            finally:
                path.chmod(mode)

    def test_file_symlinks_dangling_required_and_ci_summary_contract(self):
        actual = self.work / "actual.md"
        actual.write_text("CUSTOMIZE: pending\n")
        self.required.unlink()
        self.required.symlink_to(actual)
        self.assertEqual(1, self.run_status().returncode)
        self.env["GITHUB_STEP_SUMMARY"] = str(self.work)
        self.assertEqual(0, self.run_status("--ci").returncode)
        actual.unlink()
        self.error_modes()

    def test_enumeration_and_search_errors_override_partial_markers(self):
        directory = self.work / ".github/instructions"
        directory.mkdir()
        (directory / "area.instructions.md").write_text("CUSTOMIZE: pending\n")
        self.required.write_text("CUSTOMIZE: already found\n")
        for command in ("find", "sort", "grep"):
            for code in (2, 7):
                with self.subTest(command=command, code=code):
                    shim = self.bin / command
                    output = "printf '.github/instructions/area.instructions.md\\0'" if command == "find" else "printf 'partial CUSTOMIZE: result\\n'"
                    shim.write_text("#!/bin/bash\n" + output + "\nexit " + str(code) + "\n")
                    shim.chmod(0o755)
                    self.error_modes()
                    shim.unlink()

    def test_nul_enumeration_preserves_whitespace_and_refuses_ambiguous_names(self):
        directory = self.work / ".github/instructions"
        directory.mkdir()
        (directory / "area with spaces.instructions.md").write_text("CUSTOMIZE: pending\n")
        self.assertEqual(1, self.run_status().returncode)
        (directory / "line\nbreak.instructions.md").write_text("No markers.\n")
        self.error_modes()

    def test_scratch_open_failure_is_observation_error_in_every_mode(self):
        if os.geteuid() == 0:
            self.skipTest("actual permission denial requires a nonroot test process")
        scratch = self.work / "unwritable-scratch"
        scratch.mkdir()
        scratch.chmod(0o500)
        mktemp = self.bin / "mktemp"
        mktemp.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(str(scratch)) + "\n")
        mktemp.chmod(0o755)
        # Recreate the empty directory after the owned cleanup removes it.
        for mode in ("--quiet", "", "--ci"):
            scratch.mkdir(exist_ok=True)
            scratch.chmod(0o500)
            result = self.run_status(mode)
            self.assertEqual(0 if mode == "--ci" else 2, result.returncode, result.stdout + result.stderr)
            if mode == "--quiet":
                self.assertEqual("", result.stdout + result.stderr)
            else:
                self.assertIn("observation", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
