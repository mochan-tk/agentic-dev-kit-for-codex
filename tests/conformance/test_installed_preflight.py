"""Exercise the installed manual preflight, without a kit/helper/network dependency."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "preflight_fixture", ROOT / "tests/conformance/test_source_first_procedures.py")
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class InstalledPreflightTests(unittest.TestCase):
    def setUp(self):
        self.fixture = FIXTURE.ProcedureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        git_shim = fixture.bin / "git"
        git_shim.write_text(git_shim.read_text().replace(
            "a=sys.argv[1:]\n", "a=sys.argv[1:]\n"
            "if os.environ.get('PREFLIGHT_FAIL_COMMAND') in a: sys.exit(7)\n"))
        installed = subprocess.run(
            ["bash", str(ROOT / ".github/scripts/scaffold-init.sh"), "--apply", str(fixture.repo)],
            env=dict(fixture.env, SCAFFOLD_SOURCE_DIR=str(ROOT)),
            text=True, capture_output=True, timeout=30)
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        self.assertFalse((fixture.repo / ".github/scripts/worktree-preflight.sh").exists())
        skill = (fixture.repo / ".agents/skills/session-orchestration/SKILL.md").read_text()
        blocks = re.findall(
            r"<!-- BEGIN installed-worktree-observations -->\n```bash\n(.*?)\n```\n"
            r"<!-- END installed-worktree-observations -->", skill, re.S)
        self.assertEqual(1, len(blocks), "installed observation procedure missing")
        self.block = blocks[0]
        fixture.git("add", ".")
        fixture.git("commit", "-qm", "synthetic installed scaffold")
        for tool in ("curl", "wget", "gh"):
            shim = fixture.bin / tool
            shim.write_text('#!/bin/bash\nprintf "%s\\n" network >> "$SF_SINK"\nexit 99\n')
            shim.chmod(0o755)

    def observe(self, action="push", branch="main", conditional=False, **overrides):
        fixture = self.fixture
        env = dict(fixture.guarded_env, TASK_WORKTREE=str(fixture.repo),
                   PLANNED_BRANCH=branch, ACTUAL_WORKER="fixture-worker",
                   CLAIM_READBACK=str(fixture.claims), PREFLIGHT_ACTION=action)
        env.pop("REVIEWED_KIT", None)
        env.update(overrides)
        before = fixture.snapshot()
        block = "if " + self.block + "; then exit 0; else exit $?; fi" if conditional else self.block
        result = subprocess.run(["bash", "-c", block], cwd=fixture.repo,
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(before, fixture.snapshot(), "observation mutated adopter")
        self.assertEqual("", fixture.sink.read_text(), "actuator/network invoked")
        return result

    def test_fresh_install_observes_local_state_without_helper_or_network(self):
        (self.fixture.repo / "recovery.txt").write_text("untracked work to preserve\n")
        result = self.observe()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("recovery.txt", result.stdout)
        self.assertIn("refs/heads/main", result.stdout)
        self.assertIn("fixture-worker", result.stdout)
        self.assertIn("manual comparison required", result.stdout)
        self.assertNotIn("PASS", result.stdout)

    def test_detached_and_mismatched_push_refuse(self):
        self.assertNotEqual(0, self.observe(branch="other-branch").returncode)
        self.fixture.git("checkout", "--detach", "-q")
        self.assertNotEqual(0, self.observe().returncode)

    def test_missing_malformed_and_conflicting_claims_refuse(self):
        for content in ("{}", "bad json", '{"claims":[]}', '{"claims":[]}\n{}'):
            with self.subTest(content=content):
                self.fixture.claims.write_text(content)
                self.assertNotEqual(0, self.observe().returncode)
        active = dict(writer="fixture-worker", branch="main", worktree=str(self.fixture.repo), state="active")
        self.fixture.claims.write_text(json.dumps({"claims": [active, dict(active, writer="other-worker")]}))
        self.assertNotEqual(0, self.observe().returncode)
        self.fixture.claims.unlink()
        self.assertNotEqual(0, self.observe().returncode)

    def test_wrong_root_unset_inputs_and_archive_are_non_success(self):
        self.assertNotEqual(0, self.observe(TASK_WORKTREE=str(self.fixture.repo / ".github")).returncode)
        self.assertNotEqual(0, self.observe(ACTUAL_WORKER="").returncode)
        self.assertNotEqual(0, self.observe(PREFLIGHT_ACTION="unexpected").returncode)
        self.assertEqual(3, self.observe(action="archive").returncode)

    def test_failed_git_observations_are_non_success(self):
        for command in ("rev-parse", "symbolic-ref", "status", "worktree"):
            with self.subTest(command=command):
                self.assertNotEqual(0, self.observe(PREFLIGHT_FAIL_COMMAND=command).returncode)
                self.assertNotEqual(0, self.observe(conditional=True, PREFLIGHT_FAIL_COMMAND=command).returncode)

    def test_inherited_git_context_cannot_redirect_observation(self):
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                     "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"):
            for value in ("", str(self.fixture.repo / ".git")):
                with self.subTest(name=name, value=value):
                    self.assertEqual(3, self.observe(**{name: value}).returncode)

    def test_occupied_branch_is_visible_for_mandatory_manual_comparison(self):
        other = self.fixture.work / "occupied worktree"
        self.fixture.git("worktree", "add", "-qb", "occupied", str(other))
        self.fixture.claims.write_text(json.dumps({"claims": [dict(
            writer="fixture-worker", branch="occupied", worktree=str(self.fixture.repo), state="active")]}))
        result = self.observe(action="claim", branch="occupied")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        # Collection succeeds; this is not a preflight verdict. The installed
        # procedure requires a supervisor to reject this conflicting record.
        self.assertIn(str(other), result.stdout)
        self.assertIn("branch refs/heads/occupied", result.stdout)
        self.assertIn("manual comparison required", result.stdout)


if __name__ == "__main__":
    unittest.main()
