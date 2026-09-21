"""Run the published command blocks; real helpers, synthetic HTTP/GitHub only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/distribution/companion-checks.md"
REVISION = "2213860cbb16bf80d80d1c388c31bc75ae12bb7e"
GOVERNANCE_REVISION = "2213860cbb16bf80d80d1c388c31bc75ae12bb7e"
HELPERS = {"governance": "governance-status.sh", "worktree": "worktree-preflight.sh",
           "connectors": "check-connectors.sh"}


def fixture_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/conformance" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    """Include index, ordinary files and modes; never inspect another adopter."""
    result = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        value = os.readlink(path) if path.is_symlink() else (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        result[str(path.relative_to(root))] = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), value)
    return result


class CompanionAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="companion-access-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.tmp = self.work / "owned scratch with spaces"
        self.tmp.mkdir()
        self.calls = self.work / "calls.jsonl"
        self.calls.write_text("")
        self.launches = self.work / "launches.jsonl"
        self.launches.write_text("")
        self.env = dict(os.environ, LC_ALL="C", LANG="C", LC_CTYPE="C",
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"], TMPDIR=str(self.tmp),
                        COMPANION_ROOT=str(ROOT), COMPANION_CALLS=str(self.calls),
                        COMPANION_LAUNCHES=str(self.launches), COMPANION_MODE="good",
                        COMPANION_GOVERNANCE_REVISION=GOVERNANCE_REVISION)
        self.executable("curl", r'''
import json,os,shutil,stat,sys
from pathlib import Path
a=sys.argv[1:]
fixed=["--disable","--fail","--silent","--show-error","--location","--proto","=https","--proto-redir","=https","--max-time","60","--output"]
if a[:len(fixed)]!=fixed or len(a)!=len(fixed)+2: sys.exit(90)
out=Path(a[-2]); url=a[-1]
helper=url.rsplit("/",1)[-1]
revision=os.environ["COMPANION_GOVERNANCE_REVISION"] if helper=="governance-status.sh" else "2213860cbb16bf80d80d1c388c31bc75ae12bb7e"
prefix="https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/"+revision+"/.github/scripts/"
if url!=prefix+helper or helper not in ("governance-status.sh","worktree-preflight.sh","check-connectors.sh"): sys.exit(91)
with open(os.environ["COMPANION_CALLS"],"a") as f:
 f.write(json.dumps(dict(argv=a,scratch_mode=stat.S_IMODE(out.parent.stat().st_mode)))+"\n")
mode=os.environ["COMPANION_MODE"]
if mode=="missing": sys.exit(0)
if mode=="symlink": out.symlink_to(Path(os.environ["COMPANION_ROOT"])/".github/scripts"/url[len(prefix):]); sys.exit(0)
if mode in ("failed","partial"):
 out.write_text("#!/bin/bash\nprintf 'unverified-code-executed' >> \"$COMPANION_LAUNCHES\"\n")
 sys.exit(22 if mode=="failed" else 0)
if mode=="empty": out.write_bytes(b""); sys.exit(0)
out.write_bytes((Path(os.environ["COMPANION_ROOT"])/".github/scripts"/url[len(prefix):]).read_bytes())
if mode=="corrupt":
 with out.open("ab") as f: f.write(b"\n# substituted content\n")
if mode=="extra": (out.parent/"unexpected-owned-entry").write_text("retain on cleanup failure\n")
if mode=="valid-but-failed": sys.exit(22)
''')
        self.executable("bash", "import json,os,sys\n"
            "with open(os.environ['COMPANION_LAUNCHES'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "os.execv('/bin/bash',['/bin/bash',*sys.argv[1:]])\n")
        self.target = self.work / "synthetic adopter 日本語 with spaces"
        self.target.mkdir()
        connectors = self.target / ".github/connectors"
        shutil.copytree(ROOT / ".github/distribution/payload/.github/connectors", connectors)
        self.env["CHECK_TARGET"] = str(self.target)

    def executable(self, name, code):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + code)
        path.chmod(0o755)

    def block(self, name):
        matches = re.findall(r"<!-- BEGIN companion-" + re.escape(name) +
                             r" -->\n```bash\n(.*?)\n```\n<!-- END companion-" +
                             re.escape(name) + r" -->", GUIDE.read_text(), re.S)
        self.assertEqual(1, len(matches))
        return matches[0]

    def run_block(self, name, conditional=False, **inputs):
        block = self.block(name)
        if conditional:
            block = "if " + block + "; then exit 0; else exit $?; fi"
        result = subprocess.run(["/bin/bash", "-c", block],
                                env=dict(self.env, **inputs), cwd=self.work,
                                capture_output=True, text=True, timeout=30)
        return result

    def assert_clean(self):
        self.assertEqual([], list(self.tmp.iterdir()))

    def transport(self):
        rows = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(rows)
        self.assertTrue(all(row["scratch_mode"] == 0o700 for row in rows))
        return rows

    def governance_fixture(self):
        fixture = fixture_module("test_source_first_governance").GovernanceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.records.write_text(json.dumps(fixture.api))
        fixture.calls.write_text("")
        self.env.update({key: value for key, value in fixture.env.items() if key.startswith("SF_")})
        self.env.update(SF_GET_ONLY="1", CHECK_REPO="fixture/adopter", CHECK_CONTEXTS="lint,test",
                        CHECK_PROFILE="team", CHECK_POSTURE="adopter")
        self.env["PATH"] = str(self.bin) + os.pathsep + fixture.env["PATH"]
        return fixture

    def worktree_fixture(self):
        fixture = fixture_module("test_source_first_procedures").ProcedureTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.env.update({key: value for key, value in fixture.guarded_env.items()
                         if key.startswith(("GIT_", "SF_"))})
        self.env["PATH"] = str(self.bin) + os.pathsep + fixture.guarded_env["PATH"]
        # Whitespace is legal in a writer and claim filename; neither may split.
        self.claims = fixture.work / "claim readback with spaces.json"
        claims = json.loads(fixture.claims.read_text())
        claims["claims"][0]["writer"] = "fixture worker with spaces"
        self.claims.write_text(json.dumps(claims))
        self.env.update(CHECK_TARGET=str(fixture.repo), CHECK_BRANCH="main",
                        CHECK_WRITER="fixture worker with spaces", CHECK_CLAIMS=str(self.claims),
                        CHECK_ACTION="push")
        return fixture

    def test_connector_command_runs_real_helper_and_preserves_target(self):
        before = snapshot(self.target)
        result = self.run_block("connectors")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("structural evidence only", result.stdout)
        self.assertEqual(before, snapshot(self.target))
        self.transport()
        launch = json.loads(self.launches.read_text())
        self.assertEqual(["--target", str(self.target)], launch[1:])
        self.assert_clean()

    def test_governance_command_uses_only_get_and_preserves_caller(self):
        fixture = self.governance_fixture()
        before = snapshot(self.target)
        result = self.run_block("governance")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        calls = [json.loads(line) for line in fixture.calls.read_text().splitlines()]
        self.assertTrue(calls)
        self.assertTrue(all(row["method"] == "GET" and row["body"] is None for row in calls))
        self.assertEqual(before, snapshot(self.target))
        self.transport()
        self.assert_clean()

    def test_worktree_command_preserves_git_index_files_and_claims(self):
        fixture = self.worktree_fixture()
        (fixture.repo / "control.txt").write_text("staged unrelated edit\n")
        fixture.git("add", "control.txt")
        (fixture.repo / "control.txt").write_text("unstaged unrelated edit\n")
        (fixture.repo / "untracked.txt").write_text("preserve untracked\n")
        before = snapshot(fixture.repo)
        claims = self.claims.read_bytes()
        result = self.run_block("worktree")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, snapshot(fixture.repo))
        self.assertEqual(claims, self.claims.read_bytes())
        self.assertEqual("", fixture.sink.read_text())
        self.transport()
        self.assert_clean()

    def test_every_download_failure_blocks_execution_and_cleans(self):
        self.governance_fixture()
        self.worktree_fixture()
        for name in HELPERS:
            for mode, code in (("failed", 22), ("partial", 3), ("empty", 3),
                               ("corrupt", 3), ("missing", 3), ("symlink", 3)):
                with self.subTest(helper=name, mode=mode):
                    self.launches.write_text("")
                    before = snapshot(self.target)
                    result = self.run_block(name, COMPANION_MODE=mode)
                    self.assertEqual(code, result.returncode, result.stdout + result.stderr)
                    self.assertEqual("", self.launches.read_text())
                    self.assertEqual(before, snapshot(self.target))
                    self.assert_clean()

    def test_hash_tool_failure_never_runs_helper(self):
        self.executable("sha256sum", "import sys; sys.exit(7)\n")
        result = self.run_block("connectors")
        self.assertEqual(7, result.returncode)
        self.assertEqual("", self.launches.read_text())
        self.assert_clean()

    def test_conditional_context_still_refuses_failed_complete_download(self):
        self.governance_fixture()
        self.worktree_fixture()
        for name in HELPERS:
            with self.subTest(helper=name):
                result = self.run_block(name, conditional=True, COMPANION_MODE="valid-but-failed")
                self.assertEqual(22, result.returncode)
                self.assertEqual("", self.launches.read_text())
                self.assert_clean()

    def test_conditional_context_mktemp_failure_never_registers_cleanup(self):
        self.governance_fixture()
        self.worktree_fixture()
        self.executable("mktemp", "import os,sys; print(os.environ['CHECK_TARGET']); sys.exit(8)\n")
        self.executable("rm", "raise SystemExit('unsafe cleanup attempted')\n")
        for name in HELPERS:
            with self.subTest(helper=name):
                before = snapshot(self.target)
                result = self.run_block(name, conditional=True)
                self.assertEqual(8, result.returncode, result.stderr)
                self.assertEqual("", self.calls.read_text())
                self.assertEqual("", self.launches.read_text())
                self.assertNotIn("unsafe cleanup", result.stderr)
                self.assertEqual(before, snapshot(self.target))
                self.assert_clean()

    def test_conditional_context_failed_hash_output_never_runs_helper(self):
        self.governance_fixture()
        self.worktree_fixture()
        # Even hash-valid output cannot hide the hash program's failure.
        self.executable("sha256sum", "import hashlib,sys\n"
                        "from pathlib import Path\n"
                        "print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()+'  '+sys.argv[1])\n"
                        "sys.exit(7)\n")
        for name in HELPERS:
            with self.subTest(helper=name):
                result = self.run_block(name, conditional=True)
                self.assertEqual(7, result.returncode)
                self.assertEqual("", self.launches.read_text())
                self.assert_clean()

    def test_shasum_fallback_runs_actual_guide_without_modifying_it(self):
        shasum = shutil.which("shasum")
        self.assertIsNotNone(shasum, "macOS/Linux fallback test needs shasum")
        # Provide only named real tools; deliberately omit sha256sum from PATH.
        for name in ("mktemp", "rm", "rmdir", "shasum", "find", "head", "tr", "grep", "sed", "awk"):
            tool = shutil.which(name)
            self.assertIsNotNone(tool, name)
            (self.bin / name).symlink_to(tool)
        result = self.run_block("connectors", PATH=str(self.bin))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_clean()

    def test_helper_non_success_keeps_exit_code_and_cleans(self):
        # Confirmed invalid connector, usage, and uncheckable filesystem.
        definition = self.target / ".github/connectors/builtin.md"
        original = definition.read_bytes()
        definition.write_text("invalid definition\n")
        self.assertEqual(1, self.run_block("connectors").returncode)
        self.assert_clean()
        definition.write_bytes(original)
        self.assertEqual(3, self.run_block("connectors", CHECK_TARGET=str(self.work / "absent")).returncode)
        self.assert_clean()
        fixture = self.governance_fixture()
        self.assertEqual(2, self.run_block("governance", CHECK_PROFILE="unsupported").returncode)
        self.assertEqual("", fixture.calls.read_text())
        self.assert_clean()
        fixture.records.write_text("{}")
        self.assertEqual(3, self.run_block("governance").returncode)
        self.assert_clean()

    def test_worktree_refusal_does_not_push_repair_or_discard(self):
        fixture = self.worktree_fixture()
        fixture.git("checkout", "--detach", "-q")
        before = snapshot(fixture.repo)
        claims = self.claims.read_bytes()
        self.assertEqual(1, self.run_block("worktree").returncode)
        self.assertEqual(3, self.run_block("worktree", CHECK_ACTION="archive").returncode)
        self.assertEqual(before, snapshot(fixture.repo))
        self.assertEqual(claims, self.claims.read_bytes())
        self.assertEqual("", fixture.sink.read_text())
        self.assert_clean()

    def test_missing_required_inputs_stop_before_download(self):
        self.governance_fixture()
        self.worktree_fixture()
        for name, key in (("connectors", "CHECK_TARGET"), ("governance", "CHECK_PROFILE"),
                          ("governance", "CHECK_REPO"), ("governance", "CHECK_CONTEXTS"),
                          ("governance", "CHECK_POSTURE"), ("worktree", "CHECK_BRANCH"),
                          ("worktree", "CHECK_WRITER"), ("worktree", "CHECK_CLAIMS"),
                          ("worktree", "CHECK_ACTION")):
            with self.subTest(helper=name, missing=key):
                self.calls.write_text("")
                self.assertNotEqual(0, self.run_block(name, **{key: ""}).returncode)
                self.assertEqual("", self.calls.read_text())
                self.assert_clean()

    def test_cleanup_refuses_unknown_scratch_entries_not_recursive_delete(self):
        before = snapshot(self.target)
        result = self.run_block("connectors", COMPANION_MODE="extra")
        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        roots = list(self.tmp.iterdir())
        self.assertEqual(1, len(roots))
        self.assertEqual(["unexpected-owned-entry"], [p.name for p in roots[0].iterdir()])
        self.assertEqual(before, snapshot(self.target))
        self.assertIn("cleanup incomplete", result.stderr)


if __name__ == "__main__":
    unittest.main()
