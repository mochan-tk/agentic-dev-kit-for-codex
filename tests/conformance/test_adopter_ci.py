"""Actual opt-in setup and sensor with synthetic GET-only GitHub transport."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / ".github/scripts/setup-adopter-ci.py"
SENSOR = ROOT / ".github/distribution/adopter-ci/check-adopter-ci.py"
WORKFLOW = ROOT / ".github/distribution/adopter-ci/task-ritual.yml"
CODE = """name: Application checks
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
concurrency:
  group: application-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Actual application test
        run: python3 -m unittest discover
"""


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class AdopterTests(unittest.TestCase):
    def setUp(self):
        records = load(ROOT / "tests/conformance/test_workflow_parity.py", "existing_records")
        self.fixture = records.RecordTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.work = self.fixture.work.resolve()
        self.target = self.work / "adopter"
        self.target.mkdir()
        subprocess.run(["git", "init", "--quiet", "--template=", str(self.target)], check=True)
        self.code = self.target / ".github/workflows/application.yml"
        self.code.parent.mkdir(parents=True)
        self.code.write_text(CODE)
        self.helper = self.target / ".github/scripts/check-task-ritual.sh"
        self.helper.parent.mkdir(parents=True)
        shutil.copyfile(records.HELPER, self.helper)
        self.env = dict(self.fixture.env)
        self.prefix = self.fixture.prefix

    def api_transport(self):
        gh = self.fixture.bin / "gh"
        gh.write_text("#!" + sys.executable + "\n" + r'''
import json,os,subprocess,sys
from pathlib import Path
a=sys.argv[1:]
if a[:1]!=["api"]:sys.exit(90)
if any(x in a for x in ["--input","-f","-F","--field","--raw-field"]):sys.exit(91)
method=a[a.index("--method")+1] if "--method" in a else "GET"
if method!="GET":sys.exit(92)
key=next(x for x in a if x.startswith("repos/")).replace("{owner}/{repo}","fixture/adopter")
calls=Path(os.environ["RECORD_CALLS"])
old=[json.loads(x) for x in calls.read_text().splitlines()]
with calls.open("a") as f:f.write(json.dumps(dict(argv=a,key=key,method=method))+"\n")
records=json.loads(Path(os.environ["RECORD_API"]).read_text())
value=records.get(key,records.get(key.split("?")[0]))
if isinstance(value,dict) and "responses" in value:
 value=value["responses"][min(sum(x["key"]==key for x in old),len(value["responses"])-1)]
if value is None:sys.exit(93)
if isinstance(value,dict) and value.get("transport_error"):sys.exit(94)
if "--include" in a:
 headers=value.get("http_headers",{}) if isinstance(value,dict) else {}
 raw=value.get("raw_body") if isinstance(value,dict) else None
 body=value.get("http_body",value) if isinstance(value,dict) else value
 print("HTTP/2 200 OK")
 print("content-type: application/json")
 for k,v in headers.items():print(k+": "+v)
 print()
 print(raw if raw is not None else json.dumps(body))
 sys.exit(0)
pages=value.get("pages") if isinstance(value,dict) else None
if pages is None:pages=[value]
if "--paginate" not in a:pages=pages[:1]
if "--slurp" in a:pages=[pages]
for page in pages:
 if "--jq" in a:
  p=subprocess.run([os.environ["RECORD_JQ"],"-r",a[a.index("--jq")+1]],input=json.dumps(page),text=True)
  if p.returncode:sys.exit(p.returncode)
 else:print(json.dumps(page))
''')
        gh.chmod(0o755)

    def remote_head(self, changes=None):
        files = {path: (self.target / path).read_bytes() for path in (
            ".github/adopter-ci.json", ".github/workflows/task-ritual.yml",
            ".github/scripts/check-adopter-ci.py", ".github/scripts/check-task-ritual.sh",
            ".github/workflows/application.yml")}
        files.update(changes or {})
        tree_ids = {"": "b"*40, ".github": "d"*40,
                    ".github/workflows": "e"*40, ".github/scripts": "f"*40}
        trees = {path: [] for path in tree_ids}
        for path, ident in tree_ids.items():
            if path:
                trees[str(Path(path).parent) if "/" in path else ""].append(dict(
                    path=Path(path).name, sha=ident, type="tree", mode="040000"))
        for path, data in files.items():
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            trees[str(Path(path).parent)].append(dict(path=Path(path).name, sha=blob, type="blob", mode="100644"))
            self.api[self.prefix + "/contents/" + path + "?ref=" + "b"*40] = dict(
                type="file", path=path, encoding="base64", size=len(data), sha=blob,
                content=base64.b64encode(data).decode())
        for path, entries in trees.items():
            self.api[self.prefix + "/git/trees/" + tree_ids[path]] = dict(tree=entries, truncated=False)

    def activate(self, retarget=True):
        result = self.setup("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.api_transport()
        self.fixture.rows.append(self.fixture.dispatch())
        self.fixture.ledger(pr=True)
        self.api = copy.deepcopy(self.fixture.api)
        self.pr = self.api[self.prefix + "/pulls/1"]
        self.pr["head"]["repo"] = dict(id=101)
        self.pr["base"].update(ref="main", repo=dict(id=102, full_name="fixture/adopter"))
        self.pr["updated_at"] = "2026-01-01T00:10:00Z"
        self.event = dict(action="synchronize", number=1, repository=dict(id=102),
                          pull_request=copy.deepcopy(self.pr))
        self.event_path = self.work / "event.json"
        self.env.update(GITHUB_EVENT_NAME="pull_request", GITHUB_EVENT_PATH=str(self.event_path),
                        GH_REPO="fixture/adopter", GH_HOST="github.com",
                        GITHUB_API_URL="https://api.github.com", PR_NUMBER="1", PR_HEAD_SHA="b"*40)
        self.timeline = self.prefix + "/issues/1/timeline?per_page=100"
        self.api[self.timeline] = [dict(id=10, event="base_ref_changed", created_at=self.pr["updated_at"])] if retarget else []
        self.descriptor = self.prefix + "/actions/workflows/application.yml"
        self.api[self.descriptor] = dict(id=201, path=".github/workflows/application.yml")
        self.runs = self.prefix + "/actions/runs?head_sha=" + "b"*40 + "&per_page=100"
        self.run_path = self.prefix + "/actions/runs/301"
        self.jobs_path = self.run_path + "/attempts/1/jobs?per_page=100"
        self.check_path = self.prefix + "/check-runs/501"
        self.run = dict(id=301, workflow_id=201, path=".github/workflows/application.yml",
                        event="pull_request", head_sha="b"*40, check_suite_id=401, run_attempt=1,
                        created_at="2026-01-01T00:11:00Z", run_started_at="2026-01-01T00:12:00Z",
                        status="completed", conclusion="success", pull_requests=[dict(number=1,
                            head=copy.deepcopy(self.pr["head"]), base=copy.deepcopy(self.pr["base"]))])
        self.job = dict(id=601, name="quality", head_sha="b"*40, run_id=301, run_attempt=1,
                        check_run_url="https://api.github.com/" + self.check_path,
                        status="completed", conclusion="success", started_at="2026-01-01T00:13:00Z",
                        completed_at="2026-01-01T00:14:00Z")
        self.check_run = dict(id=501, name="quality", head_sha="b"*40, check_suite=dict(id=401),
                              app=dict(id=15368, slug="github-actions"),
                              **{k: self.job[k] for k in ("status", "conclusion", "started_at", "completed_at")})
        self.sync_evidence()
        self.remote_head()

    def sync_evidence(self):
        self.api[self.runs] = dict(total_count=1, workflow_runs=[copy.deepcopy(self.run)])
        self.api[self.run_path] = copy.deepcopy(self.run)
        self.api[self.jobs_path] = dict(total_count=1, jobs=[copy.deepcopy(self.job)])
        self.api[self.check_path] = copy.deepcopy(self.check_run)

    def run_sensor(self, command="check"):
        self.fixture.records.write_text(json.dumps(self.api))
        self.fixture.calls.write_text("")
        self.event_path.write_text(json.dumps(self.event))
        before = self.snapshot()
        result = subprocess.run([sys.executable, "-I", str(self.target / ".github/scripts/check-adopter-ci.py"),
            command, "--root", str(self.target)], env=self.env, cwd=self.work,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(before, self.snapshot(), "sensor must not mutate adopter files")
        self.log = [json.loads(x) for x in self.fixture.calls.read_text().splitlines()]
        self.assertTrue(all(x["method"] == "GET" for x in self.log))
        return result

    def setup(self, *extra):
        return subprocess.run([sys.executable, "-I", str(SETUP), "--target", str(self.target),
            "--code-workflow", ".github/workflows/application.yml", "--check", "quality", *extra],
            env=self.env, cwd=self.work, capture_output=True, text=True, timeout=20)

    def snapshot(self):
        return {str(p.relative_to(self.target)): p.read_bytes() for p in self.target.rglob("*")
                if p.is_file() and not p.is_symlink()}

    def test_preview_apply_repeat_preserve_application_and_git_index(self):
        (self.target / "unrelated.txt").write_text("staged\n")
        subprocess.run(["git", "-C", str(self.target), "add", "unrelated.txt"], check=True)
        (self.target / "unrelated.txt").write_text("unstaged\n")
        before = self.snapshot()
        preview = self.setup()
        self.assertEqual(0, preview.returncode, preview.stderr)
        self.assertEqual(before, self.snapshot())
        applied = self.setup("--apply")
        self.assertEqual(0, applied.returncode, applied.stderr)
        after = self.snapshot()
        self.assertEqual(set(after) - set(before), {".github/adopter-ci.json",
            ".github/scripts/check-adopter-ci.py", ".github/workflows/task-ritual.yml"})
        self.assertTrue(all(after[k] == v for k, v in before.items()))
        self.assertEqual(0, self.setup("--apply").returncode)
        self.assertEqual(after, self.snapshot())

    def test_setup_refuses_unsupported_or_softened_wiring_before_writes(self):
        for before, after in (("reopened]", "reopened, edited]"),
                              ("  quality:\n", "  quality:\n    if: false\n"),
                              ("        run:", "        continue-on-error: true\n        run:"),
                              ("application-${{", "adopter-metadata-${{"),
                              ("  quality:\n", "  quality:\n    name: task-ritual\n")):
            with self.subTest(change=after):
                self.code.write_text(CODE.replace(before, after))
                snapshot = self.snapshot()
                result = self.setup("--apply")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(snapshot, self.snapshot())

    def test_all_destinations_preflight_and_partial_install_refusal(self):
        collision = self.target / ".github/adopter-ci.json"
        collision.write_text("unknown\n")
        before = self.snapshot()
        self.assertNotEqual(0, self.setup("--apply").returncode)
        self.assertEqual(before, self.snapshot())
        collision.unlink()
        self.assertEqual(0, self.setup("--apply").returncode)
        collision.unlink()
        before = self.snapshot()
        self.assertNotEqual(0, self.setup("--apply").returncode)
        self.assertEqual(before, self.snapshot())

    def test_actual_installed_ritual_and_fresh_sensor_pass(self):
        self.activate()
        result = self.run_sensor()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("TASK_RITUAL_PASS; FRESH:", result.stdout)
        self.assertTrue(any("/issues/2/comments" in row["key"] for row in self.log))
        self.assertEqual(2, sum(row["key"] == self.check_path for row in self.log))

    def test_no_retarget_does_not_claim_code_ci_success(self):
        self.activate(retarget=False)
        for path in (self.runs, self.run_path, self.jobs_path, self.check_path):
            del self.api[path]
        result = self.run_sensor()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("NO_RETARGET: code verification remains independently required", result.stdout)
        self.assertFalse(any("/actions/" in row["key"] for row in self.log))

    def test_required_subset_does_not_make_optional_failure_mandatory(self):
        self.activate()
        self.run["conclusion"] = "failure"
        self.sync_evidence()
        result = self.run_sensor()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_safe_application_command_change_on_head_remains_supported(self):
        self.activate()
        self.remote_head({".github/workflows/application.yml": CODE.replace(
            "python3 -m unittest discover", "python3 -m unittest discover -v").encode()})
        result = self.run_sensor()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_actual_ritual_missing_wrong_edited_replaced_and_drifting_records_refuse(self):
        self.activate()
        original = copy.deepcopy(self.api)
        comments = self.prefix + "/issues/2/comments"
        plan = self.prefix + "/issues/comments/3"
        for mutation in ("claim", "plan", "wrong-task", "edited", "replacement", "drift"):
            with self.subTest(mutation=mutation):
                self.api = copy.deepcopy(original)
                rows = self.api[comments]["pages"][0]
                if mutation in ("claim", "plan"):
                    rows.pop(0 if mutation == "claim" else 1)
                    self.api[self.prefix + "/issues/2"]["comments"] = len(rows)
                elif mutation == "wrong-task":
                    self.api[plan]["issue_url"] = self.prefix + "/issues/3"
                elif mutation == "edited":
                    rows[1]["updated_at"] = "2026-01-01T00:04:00Z"
                    self.api[plan] = rows[1]
                elif mutation == "replacement":
                    rows.append(self.fixture.dispatch(minute=3))
                    self.api[self.prefix + "/issues/2"]["comments"] = len(rows)
                else:
                    changed = copy.deepcopy(self.api[plan]); changed["body"] += "changed"
                    self.api[plan] = dict(responses=[self.api[plan], changed])
                result = self.run_sensor()
                self.assertNotEqual(0, result.returncode)
                self.assertNotIn("TASK_RITUAL_PASS", result.stdout)

    def test_stale_original_away_back_equal_and_old_rerun_refuse(self):
        self.activate()
        original = copy.deepcopy(self.api)
        for mutation in ("stale", "away-back", "equal", "rerun", "check-equal"):
            with self.subTest(mutation=mutation):
                self.api = copy.deepcopy(original)
                if mutation in ("stale", "rerun"):
                    for path in (self.run_path, self.runs):
                        row = self.api[path] if path == self.run_path else self.api[path]["workflow_runs"][0]
                        row["created_at"] = "2026-01-01T00:09:00Z"
                        if mutation == "rerun": row["run_attempt"] = 2
                elif mutation == "away-back":
                    self.api[self.timeline].append(dict(id=11, event="base_ref_changed",
                                                       created_at="2026-01-01T00:15:00Z"))
                elif mutation == "equal":
                    self.api[self.timeline][0]["created_at"] = "2026-01-01T00:11:00Z"
                else:
                    self.api[self.jobs_path]["jobs"][0]["started_at"] = self.pr["updated_at"]
                    self.api[self.check_path]["started_at"] = self.pr["updated_at"]
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_latest_failure_and_incomplete_attempt_cannot_borrow_old_success(self):
        self.activate()
        previous = copy.deepcopy(self.run)
        previous.update(id=300, created_at="2026-01-01T00:10:30Z")
        self.api[self.runs]["workflow_runs"].append(previous)
        self.api[self.runs]["total_count"] = 2
        for state in ("failure", "skipped", "neutral", "cancelled", "in_progress", "missing"):
            with self.subTest(state=state):
                self.api[self.jobs_path] = dict(total_count=1, jobs=[copy.deepcopy(self.job)])
                self.api[self.check_path] = copy.deepcopy(self.check_run)
                if state == "missing": self.api[self.jobs_path] = dict(total_count=0, jobs=[])
                else:
                    field = "status" if state == "in_progress" else "conclusion"
                    self.api[self.jobs_path]["jobs"][0][field] = state
                    self.api[self.check_path][field] = state
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_wrong_evidence_identity_refuses(self):
        self.activate()
        original = copy.deepcopy(self.api)
        changes = [
            (self.descriptor, ("path",), ".github/workflows/wrong.yml"),
            (self.run_path, ("id",), 999),
            (self.jobs_path, ("jobs", 0, "run_attempt"), 2),
            (self.jobs_path, ("jobs", 0, "head_sha"), "c"*40),
            (self.jobs_path, ("jobs", 0, "check_run_url"), "https://foreign.invalid/check-runs/501"),
            (self.check_path, ("id",), 999),
            (self.check_path, ("name",), "unrelated"),
            (self.check_path, ("check_suite", "id"), 999),
            (self.check_path, ("app", "id"), 1),
            (self.check_path, ("app", "slug"), "other-actions"),
            (self.runs, ("workflow_runs", 0, "workflow_id"), 999),
            (self.runs, ("workflow_runs", 0, "pull_requests", 0, "number"), 2),
            (self.runs, ("workflow_runs", 0, "pull_requests", 0, "base", "ref"), "other"),
            (self.runs, ("workflow_runs", 0, "pull_requests", 0, "head", "sha"), "c"*40),
            (self.runs, ("workflow_runs", 0, "pull_requests"), []),
            (self.run_path, ("status",), "unknown"),
        ]
        for path, keys, value in changes:
            with self.subTest(path=path, keys=keys):
                self.api = copy.deepcopy(original)
                target = self.api[path]
                for key in keys[:-1]: target = target[key]
                target[keys[-1]] = value
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_readback_drift_for_each_evidence_edge_refuses(self):
        self.activate()
        original = copy.deepcopy(self.api)
        for path, field, value in ((self.descriptor, "id", 999), (self.run_path, "run_attempt", 2),
                                   (self.check_path, "conclusion", "failure"),
                                   (self.runs, "total_count", 0), (self.jobs_path, "total_count", 0)):
            with self.subTest(path=path):
                self.api = copy.deepcopy(original)
                changed = copy.deepcopy(self.api[path]); changed[field] = value
                self.api[path] = dict(responses=[self.api[path], changed])
                self.assertNotEqual(0, self.run_sensor().returncode)
        self.api = copy.deepcopy(original)
        self.api[self.timeline] = dict(responses=[[], original[self.timeline]])
        self.assertNotEqual(0, self.run_sensor().returncode)

    def test_base_edit_webhook_veto_and_delayed_timeline_refuse(self):
        self.activate(retarget=False)
        self.event.update(action="edited", changes=dict(base=dict(ref={"from": "previous"})))
        result = self.run_sensor()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not yet visible", result.stderr)
        self.api[self.timeline] = [dict(id=9, event="base_ref_changed", created_at="2026-01-01T00:09:00Z")]
        self.assertNotEqual(0, self.run_sensor().returncode)

    def test_pagination_is_complete_strict_and_resource_bounded(self):
        self.activate()
        next_path = self.timeline + "&page=2"
        links = '<https://api.github.com/' + next_path + '>; rel="next", <https://api.github.com/' + next_path + '>; rel="last"'
        self.api[self.timeline] = dict(http_body=[dict(id=i+100, event="commented") for i in range(100)],
                                      http_headers=dict(link=links))
        self.api[next_path] = [dict(id=10, event="base_ref_changed", created_at=self.pr["updated_at"])]
        result = self.run_sensor()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        original = copy.deepcopy(self.api)
        for mutation in ("later-error", "foreign", "duplicate-link", "no-last", "missing-next",
                         "duplicate-id", "malformed-json", "duplicate-json", "oversized", "count-cap"):
            with self.subTest(mutation=mutation):
                self.api = copy.deepcopy(original)
                if mutation == "later-error": self.api[next_path] = dict(transport_error=True)
                elif mutation == "foreign": self.api[self.timeline]["http_headers"]["link"] = links.replace("api.github.com", "evil.invalid")
                elif mutation == "duplicate-link": self.api[self.timeline]["http_headers"]["link"] += ", " + links.split(",")[0]
                elif mutation == "no-last": self.api[self.timeline]["http_headers"]["link"] = links.split(",")[0]
                elif mutation == "missing-next": self.api[self.timeline]["http_headers"] = {}
                elif mutation == "duplicate-id": self.api[next_path][0]["id"] = 100
                elif mutation == "malformed-json": self.api[self.timeline] = dict(raw_body="[")
                elif mutation == "duplicate-json": self.api[self.timeline] = dict(raw_body='[{"event":"commented","event":"base_ref_changed"}]')
                elif mutation == "oversized": self.api[self.timeline] = [{}] * 101
                else: self.api[self.runs]["total_count"] = 1000
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_setup_symlink_missing_dependency_and_duplicate_configuration_refuse(self):
        destination = self.target / ".github/adopter-ci.json"
        destination.symlink_to(self.code)
        self.assertNotEqual(0, self.setup("--apply").returncode)
        destination.unlink()
        scripts = self.helper.parent
        real_scripts = self.target / "saved-scripts"
        scripts.rename(real_scripts)
        scripts.symlink_to(real_scripts, target_is_directory=True)
        self.assertNotEqual(0, self.setup("--apply").returncode)
        scripts.unlink(); real_scripts.rename(scripts)
        self.assertNotEqual(0, self.setup("--check", "quality", "--apply").returncode)
        self.assertNotEqual(0, self.setup("--check", "task-ritual", "--apply").returncode)
        self.helper.unlink()
        self.assertNotEqual(0, self.setup("--apply").returncode)
        self.assertFalse(destination.exists())

    def test_local_drift_requires_exact_controls_and_unconditional_metadata(self):
        self.activate()
        metadata = self.target / ".github/workflows/task-ritual.yml"
        original = metadata.read_text()
        for before, after in (("        run: |", "        if: false\n        run: |"),
                              ("        run: |", "        continue-on-error: true\n        run: |"),
                              ("          python3 -I", "          echo python3 -I"),
                              ("          python3 -I", "          true # python3 -I"),
                              ("          python3 -I", "          # python3 -I"),
                              ("    runs-on: ubuntu-latest", "    if: false\n    runs-on: ubuntu-latest"),
                              ("  task-ritual:", "  quality:"),
                              ("          ref: ${{ github.event.pull_request.base.sha }}", "          ref: ${{ github.event.pull_request.head.sha }}")):
            with self.subTest(change=after):
                metadata.write_text(original.replace(before, after))
                result = self.run_sensor("drift")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual([], self.log)
        metadata.write_text(original)
        config_path = self.target / ".github/adopter-ci.json"
        original_config = config_path.read_bytes()
        for mutation in ("omitted", "extra", "duplicate", "unsafe", "sensor", "ritual", "metadata"):
            with self.subTest(mutation=mutation):
                config = json.loads(original_config)
                if mutation == "omitted": config["controls"].pop()
                elif mutation == "extra": config["waivers"] = []
                elif mutation == "unsafe": config["code_workflow"] = "../elsewhere.yml"
                elif mutation != "duplicate": config[mutation + "_sha256"] = "0"*64
                config_path.write_text(json.dumps(config) if mutation != "duplicate" else
                                       original_config.decode().replace('"schema":', '"schema": "wrong", "schema":'))
                self.assertNotEqual(0, self.run_sensor("drift").returncode)
        config_path.write_bytes(original_config)
        self.assertEqual(0, self.run_sensor("drift").returncode)

    def test_head_controls_symlinks_and_duplicate_producers_refuse(self):
        self.activate()
        original = copy.deepcopy(self.api)
        for mutation in ("guard", "symlink", "parent-symlink", "extra-workflow", "truncated", "conditional-code"):
            with self.subTest(mutation=mutation):
                self.api = copy.deepcopy(original)
                if mutation == "guard":
                    self.remote_head({".github/workflows/task-ritual.yml": WORKFLOW.read_bytes().replace(b"python3 -I", b"echo python3 -I")})
                elif mutation == "symlink":
                    self.api[self.prefix + "/git/trees/" + "f"*40]["tree"][0]["mode"] = "120000"
                elif mutation == "parent-symlink":
                    self.api[self.prefix + "/git/trees/" + "d"*40]["tree"][0]["mode"] = "120000"
                elif mutation == "extra-workflow":
                    self.api[self.prefix + "/git/trees/" + "e"*40]["tree"].append(dict(
                        path="duplicate.yml", mode="100644", type="blob", sha="a"*40))
                elif mutation == "truncated": self.api[self.prefix + "/git/trees/" + "b"*40]["truncated"] = True
                else:
                    self.remote_head({".github/workflows/application.yml": CODE.replace(
                        "  quality:\n", "  quality:\n    if: false\n").encode()})
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_workflow_subset_handles_literal_comments_and_refuses_ambiguity(self):
        sensor = load(SENSOR, "workflow_subset_test")
        literal = CODE.replace("run: python3 -m unittest discover", "run: |\n          # harmless body comment\n          python3 -m unittest discover")
        sensor.code_contract(literal.encode(), ["quality"])
        for changed in (CODE.replace("    steps:", "    if: false\n    steps:"),
                        CODE.replace("    steps:", "    steps: []\n    steps:"),
                        CODE.replace("  quality:", "  quality: &anchor"),
                        CODE.replace("run: python3 -m unittest discover", "run: true"),
                        CODE.replace("run: python3 -m unittest discover", "run: echo tests"),
                        CODE.replace("run: python3 -m unittest discover", "# run: python3 -m unittest discover\n        run: true"),
                        CODE.replace("pull_request:\n    types: [opened, synchronize, reopened]", "pull_request: {}")):
            with self.assertRaises(sensor.Fault): sensor.code_contract(changed.encode(), ["quality"])

    def test_first_activation_has_explicit_failing_guard_and_no_code_producers(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("types: [opened, synchronize, reopened, edited]", workflow)
        self.assertIn("exit 2", workflow)
        self.assertNotIn("  quality:", workflow)
        command = workflow.split("        run: |\n", 1)[1]
        command = "\n".join(line[10:] for line in command.splitlines())
        result = subprocess.run(["bash", "-e", "-c", command], cwd=self.target,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertIn("accept addon installation", result.stderr)

    def test_bounded_partial_creation_retains_only_known_new_files(self):
        # Inject a filesystem failure after the real first O_EXCL creation.
        (self.target / "unrelated.txt").write_text("staged\n")
        subprocess.run(["git", "-C", str(self.target), "add", "unrelated.txt"], check=True)
        (self.target / "unrelated.txt").write_text("unstaged\n")
        original = self.snapshot()
        program = ("import os,runpy,sys\noriginal=os.open\n"
                   "def failing(path,flags,*a,**kw):\n"
                   " if str(path)=='check-adopter-ci.py' and flags & os.O_CREAT: raise OSError('fixture failure')\n"
                   " return original(path,flags,*a,**kw)\n"
                   "os.open=failing\nscript=sys.argv[1];sys.argv=sys.argv[1:]\n"
                   "runpy.run_path(script,run_name='__main__')\n")
        result = subprocess.run([sys.executable, "-I", "-c", program, str(SETUP),
            "--target", str(self.target), "--code-workflow", ".github/workflows/application.yml",
            "--check", "quality", "--apply"], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(2, result.returncode)
        self.assertIn("PARTIAL:", result.stderr)
        self.assertEqual(WORKFLOW.read_bytes(), (self.target / ".github/workflows/task-ritual.yml").read_bytes())
        self.assertFalse((self.target / ".github/adopter-ci.json").exists())
        self.assertFalse((self.target / ".github/scripts/check-adopter-ci.py").exists())
        self.assertTrue(all(self.snapshot()[path] == data for path, data in original.items()))
        before = self.snapshot()
        self.assertNotEqual(0, self.setup("--apply").returncode)
        self.assertEqual(before, self.snapshot())

    def test_equal_latest_duplicates_bad_chronology_and_attempt_drift_refuse(self):
        self.activate()
        original = copy.deepcopy(self.api)
        for mutation in ("tie", "duplicate-job", "chronology", "attempt", "pr-base", "head-code"):
            with self.subTest(mutation=mutation):
                self.api = copy.deepcopy(original)
                if mutation == "tie":
                    duplicate = copy.deepcopy(self.run); duplicate["id"] = 302
                    self.api[self.runs]["workflow_runs"].append(duplicate)
                    self.api[self.runs]["total_count"] = 2
                elif mutation == "duplicate-job":
                    duplicate = copy.deepcopy(self.job); duplicate["id"] = 602
                    self.api[self.jobs_path]["jobs"].append(duplicate)
                    self.api[self.jobs_path]["total_count"] = 2
                elif mutation == "chronology":
                    self.api[self.jobs_path]["jobs"][0]["completed_at"] = "2026-01-01T00:12:00Z"
                    self.api[self.check_path]["completed_at"] = "2026-01-01T00:12:00Z"
                elif mutation == "attempt":
                    changed = copy.deepcopy(self.api[self.run_path]); changed["run_attempt"] = 2
                    self.api[self.run_path] = dict(responses=[self.api[self.run_path], changed])
                elif mutation == "pr-base":
                    changed = copy.deepcopy(self.pr); changed["base"]["sha"] = "c"*40
                    self.api[self.prefix + "/pulls/1"] = dict(responses=[self.pr, self.pr, changed])
                else:
                    path = self.prefix + "/contents/.github/workflows/application.yml?ref=" + "b"*40
                    changed = copy.deepcopy(self.api[path]); changed["size"] += 1
                    self.api[path] = dict(responses=[self.api[path], changed])
                self.assertNotEqual(0, self.run_sensor().returncode)

    def test_transport_output_and_page_bounds_refuse(self):
        sensor = load(SENSOR, "resource_bound_test")
        with self.assertRaises(sensor.Fault):
            sensor.bounded_command([sys.executable, "-c", "print('x' * 2097153)"])
        self.activate()
        for page in range(1, 21):
            path = self.timeline + ("&page=" + str(page) if page > 1 else "")
            next_path = self.timeline + "&page=" + str(page + 1)
            self.api[path] = dict(http_body=[dict(id=page, event="commented")],
                http_headers=dict(link='<https://api.github.com/' + next_path + '>; rel="next", '
                                       '<https://api.github.com/' + self.timeline + '&page=21>; rel="last"'))
        self.assertNotEqual(0, self.run_sensor().returncode)


if __name__ == "__main__":
    unittest.main()
