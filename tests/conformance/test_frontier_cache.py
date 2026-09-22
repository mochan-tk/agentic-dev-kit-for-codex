"""Invocation-local frontier cache: real Bash/jq, synthetic GitHub transport."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ".github/distribution/payload"
FRONTIER = ".agents/skills/plan-management/scripts/frontier.sh"
RITUAL = ".github/scripts/check-task-ritual.sh"
BASELINE = "tests/fixtures/frontier-cache-baseline.json"


def old_bytes(path):
    record = json.loads((ROOT / BASELINE).read_bytes())
    return base64.b64decode(next(row["base64"] for row in record["entries"] if row["path"] == path), validate=True)


class FrontierCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="frontier-cache-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.records = self.work / "records.json"
        self.calls = self.work / "calls.jsonl"
        self.gh = self.bin / "gh"
        self.gh.write_text("#!" + sys.executable + "\n" + r'''
import json,os,subprocess,sys
from pathlib import Path
a=sys.argv[1:]
with Path(os.environ['CACHE_CALLS']).open('a') as f:f.write(json.dumps(a)+'\n')
r=json.loads(Path(os.environ['CACHE_RECORDS']).read_bytes())
if a[:2]==['repo','view']: value=r['repository']
elif a[:2]==['issue','list']:
 assert a[2:]==['--repo',r['repository']['url'].removeprefix('https://').lower(),'--state','open',
                '--label','type:task','--label','ai:ready','--limit','200','--json','number,title',
                '--template','{{range .}}{{.number}}{{"\\t"}}{{.title}}{{"\\n"}}{{end}}']
 for task in r['tasks']: print(str(task['number'])+'\t'+task['title'])
 sys.exit(0)
elif a[:2]==['issue','view']:
 repo=a[a.index('--repo')+1];field=a[a.index('--json')+1]
 assert len(a)==9 and a[3]=='--repo' and a[5]=='--json' and a[7]=='--jq'
 if field=='blockedBy':
  assert repo==r['repository']['url'].removeprefix('https://').lower()
  value=r['dependencies'].get(a[2])
 elif field=='state':value=r['states'].get(repo+'#'+a[2])
 else:sys.exit(91)
else:sys.exit(92)
if value is None:sys.exit(93)
if '--jq' not in a:sys.exit(94)
p=subprocess.run([os.environ['CACHE_JQ'],'-r',a[a.index('--jq')+1]],input=json.dumps(value),text=True)
sys.exit(p.returncode)
''')
        self.gh.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        CACHE_CALLS=str(self.calls), CACHE_RECORDS=str(self.records), CACHE_JQ=shutil.which("jq"))
        self.api = dict(repository=dict(url="https://github.com/fixture/adopter", nameWithOwner="fixture/adopter"),
                        tasks=[], dependencies={}, states={})

    def task(self, number, blockers):
        self.api["tasks"].append(dict(number=number, title="Task " + str(number)))
        self.api["dependencies"][str(number)] = dict(blockedBy=dict(nodes=blockers, totalCount=len(blockers)))

    def state(self, number, state="CLOSED", repo="fixture/adopter"):
        self.api["states"]["github.com/" + repo + "#" + str(number)] = dict(state=state)

    def run_frontier(self, *, baseline=False, bash="/bin/bash", extra=()):
        self.records.write_text(json.dumps(self.api))
        self.calls.write_text("")
        helper = ROOT / PAYLOAD / FRONTIER
        if baseline:
            helper = self.work / "accepted-old.sh"
            helper.write_bytes(old_bytes(FRONTIER))
        before = {p.relative_to(self.work) for p in self.work.rglob("*")}
        result = subprocess.run([bash, str(helper), "-R", "fixture/adopter", "--all", *extra],
                                cwd=self.work, env=self.env, text=True, capture_output=True, timeout=60)
        self.assertEqual(before, {p.relative_to(self.work) for p in self.work.rglob("*")}, "no persistent cache")
        self.log = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.state_calls = [row for row in self.log if "--json" in row and row[row.index("--json") + 1] == "state"]
        self.assertTrue(all(row[:2] in (["repo", "view"], ["issue", "view"], ["issue", "list"]) for row in self.log))
        return result

    def test_fifty_tasks_two_shared_blockers_exact_calls_old_new(self):
        nodes = [dict(id="I_" + str(n), number=n, state="CLOSED", title="Shared blocker",
                      url="https://github.com/fixture/adopter/issues/" + str(n)) for n in (201, 202)]
        for number in range(1, 51): self.task(number, nodes)
        self.state(201); self.state(202)
        old = self.run_frontier(baseline=True)
        self.assertEqual(0, old.returncode, old.stderr)
        self.assertEqual((152, 100), (len(self.log), len(self.state_calls)))
        new = self.run_frontier()
        self.assertEqual(0, new.returncode, new.stderr)
        self.assertEqual(old.stdout, new.stdout)
        self.assertEqual((54, 2), (len(self.log), len(self.state_calls)))
        self.assertEqual(["201", "202"], [row[2] for row in self.state_calls])
        self.assertEqual([str(n) for n in range(1, 51)],
                         [row[2] for row in self.log if "blockedBy" in row])

    def test_canonical_aliases_share_cache_but_distinct_repositories_do_not(self):
        self.task(1, [dict(number=9)])
        self.task(2, [dict(number=9, repository=dict(nameWithOwner="FiXtUrE/AdOpTeR"))])
        self.task(3, [dict(number=9, url="https://GitHub.COM/FIXTURE/ADOPTER/issues/9")])
        self.task(4, [dict(number=9, repository=dict(name="other", owner=dict(login="fixture")))])
        self.task(5, [dict(number=9, url="https://github.com/FIXTURE/OTHER/issues/9")])
        self.state(9); self.state(9, "OPEN", "fixture/other")
        result = self.run_frontier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, len(self.state_calls))
        self.assertIn("#3\tTask 3\n== Blocked ==\n#4\tTask 4\n#5\tTask 5", result.stdout)

    def test_separate_invocations_refetch_and_observe_changed_state(self):
        self.task(1, [dict(number=9)]); self.task(2, [dict(number=9)])
        self.state(9)
        first = self.run_frontier()
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertNotIn("== Blocked ==", first.stdout)
        self.assertEqual(1, len(self.state_calls))
        self.state(9, "OPEN")
        second = self.run_frontier()
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn("== Blocked ==", second.stdout)
        self.assertEqual(1, len(self.state_calls))

    def test_open_blocker_never_skips_later_failed_or_unknown_observations(self):
        self.task(1, [dict(number=9)]); self.task(2, [dict(number=9), dict(number=10)])
        self.state(9, "OPEN")
        for value in (None, "UNKNOWN", "closed", "", 1, {}, []):
            with self.subTest(value=value):
                if value is None: self.api["states"].pop("github.com/fixture/adopter#10", None)
                else: self.state(10, value)
                result = self.run_frontier()
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual(["9", "10"], [row[2] for row in self.state_calls])

    def test_cached_state_never_exempts_later_dependency_validation(self):
        self.task(1, [dict(number=9)]); self.task(2, [dict(number=9)])
        self.state(9)
        invalid = [None, dict(blockedBy=dict(nodes=[dict(number=9)], totalCount=2)),
                   dict(blockedBy=[dict(number=9), dict(number=9, repository=dict(nameWithOwner="FIXTURE/ADOPTER"))]),
                   dict(blockedBy=[dict(number=9, url="https://other.example/fixture/adopter/issues/9")]),
                   dict(blockedBy=[dict(number=9, repository=dict(nameWithOwner="fixture/other"),
                                            url="https://github.com/fixture/adopter/issues/9")])]
        for value in invalid:
            with self.subTest(value=value):
                self.api["dependencies"]["2"] = value
                result = self.run_frontier()
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual(1, len(self.state_calls))

    def test_no_blockers_no_state_reads_and_explicit_selected_host(self):
        self.task(1, [])
        self.assertEqual(0, self.run_frontier().returncode)
        self.assertEqual([], self.state_calls)
        self.api["repository"]["url"] = "https://git.example/fixture/adopter"
        self.task(2, [dict(number=9)])
        self.api["states"]["git.example/fixture/adopter#9"] = dict(state="CLOSED")
        result = self.run_frontier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("git.example/fixture/adopter", self.state_calls[0][self.state_calls[0].index("--repo") + 1])


class FrontierIntegrationTests(unittest.TestCase):
    def installer(self):
        spec = importlib.util.spec_from_file_location("frontier_installer_tests", ROOT / "tests/conformance/test_installer.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case = module.InstallerTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_public_accepted_old_and_new_anchors_pass_but_mixed_refuses(self):
        for old, new, expected in ((True, False, 0), (False, False, 0), (True, True, 1)):
            with self.subTest(old=old, new=new):
                case = self.installer()
                base, head = case.adoption_fixture(anchor=old_bytes(FRONTIER) if old else None,
                    head_anchor=(ROOT / PAYLOAD / FRONTIER).read_bytes() if new else None)
                result = case.ritual(base, head)
                self.assertEqual(expected, int(result.returncode != 0), result.stdout + result.stderr)

    def test_actual_bash_install_upgrade_rollback_preserve_tuned_and_unrelated_index(self):
        case = self.installer()
        old = case.clone_source()
        for path in (FRONTIER, RITUAL): (old / PAYLOAD / path).write_bytes(old_bytes(path))
        rows = [line.split("\t") for line in (old / ".github/distribution/payload.v1.tsv").read_text().splitlines()
                if line and not line.startswith("#")]
        (old / ".github/distribution/payload.v1.tsv").write_text("".join("\t".join((name, kind,
            hashlib.sha256((old / PAYLOAD / name).read_bytes()).hexdigest())) + "\n" for name, kind, _ in rows))
        self.assertEqual(0, case.run_install("--apply", source=old).returncode)
        (case.target / "AGENTS.md").write_text("adopter instructions\n")
        (case.target / "AGENTS.md").chmod(0o600)
        (case.target / "README.md").write_text("adopter documentation\n")
        case.commit_adopter("public accepted baseline")
        (case.target / "unrelated.txt").write_text("staged\n")
        case.git("add", "unrelated.txt")
        (case.target / "unrelated.txt").write_text("unstaged\n")
        before = case.snapshot(case.target)
        modes = {p.relative_to(case.target): p.stat().st_mode for p in case.target.rglob("*")}
        case.old_source, case.new_source = old, ROOT
        case.transaction = case.base / "operation"
        result = case.upgrade("--apply")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        after = case.snapshot(case.target)
        self.assertEqual({FRONTIER, RITUAL}, {str(path) for path in before.keys() | after.keys()
                                             if before.get(path) != after.get(path)})
        for path in (FRONTIER, RITUAL): self.assertEqual((ROOT / PAYLOAD / path).read_bytes(), (case.target / path).read_bytes())
        result = case.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, case.snapshot(case.target))
        self.assertEqual(modes, {p.relative_to(case.target): p.stat().st_mode for p in case.target.rglob("*")})


if __name__ == "__main__":
    unittest.main()
