"""Installed workflow delta: real Bash/jq/Git, synthetic GET-only ledger."""
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
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github/distribution/payload/.github/scripts/check-task-ritual.sh"
BASELINE = ROOT / "tests/fixtures/workflow-parity-baseline.json"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/conformance" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class RecordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="workflow-records-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.input = self.work / "input.json"
        self.body = self.work / "body.md"
        self.records = self.work / "records.json"
        self.calls = self.work / "calls.jsonl"
        self.calls.write_text("")
        gh = self.bin / "gh"
        gh.write_text("#!" + sys.executable + "\n" + r'''
import json,os,subprocess,sys
from pathlib import Path
a=sys.argv[1:]
if a[:1]!=["api"]:sys.exit(90)
if any(x in a for x in ["--input","-f","-F","--field","--raw-field"]):sys.exit(91)
method=a[a.index("--method")+1] if "--method" in a else "GET"
if method!="GET":sys.exit(92)
key=a[1].replace("{owner}/{repo}","fixture/adopter").split("?")[0]
calls=Path(os.environ["RECORD_CALLS"])
old=[json.loads(x) for x in calls.read_text().splitlines()]
with calls.open("a") as f:f.write(json.dumps(dict(argv=a,key=key,method=method))+"\n")
records=json.loads(Path(os.environ["RECORD_API"]).read_text())
value=records.get(key)
if isinstance(value,dict) and "responses" in value:
 value=value["responses"][min(sum(x["key"]==key for x in old),len(value["responses"])-1)]
if value is None:sys.exit(93)
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
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        RECORD_API=str(self.records), RECORD_CALLS=str(self.calls),
                        RECORD_JQ=shutil.which("jq"), RITUAL_API_RETRY_DELAY="0")
        self.prefix = "repos/fixture/adopter"
        self.url = "https://api.github.com/" + self.prefix + "/issues/2"
        self.branch = "codex/task-2-fix"
        self.rows = [self.comment("Starting in session supervisor, branch " + self.branch, 0),
                     self.comment("## Plan\n\nTask: #2\n\nImplement the bounded Task.\n\n", 1)]
        self.api = {}
        self.ledger()

    def comment(self, body, minute):
        stamp = f"2026-01-01T00:{minute:02}:00Z"
        return dict(id=minute + 2, body=body, created_at=stamp, updated_at=stamp, issue_url=self.url)

    def dispatch(self, branch=None, minute=2):
        return self.comment("Dispatching worker: Task worker (session /root/supervisor/worker), branch " +
                            (branch or self.branch), minute)

    def ledger(self, *, pr=False):
        self.api[self.prefix] = {"full_name": "fixture/adopter"}
        self.api[self.prefix + "/issues/2"] = dict(number=2, url=self.url, state="open", body="Task brief",
                                                   comments=len(self.rows), labels=[{"name": "type:task"}])
        self.api[self.prefix + "/issues/2/comments"] = {"pages": [self.rows[i:i+100] for i in range(0, len(self.rows), 100)] or [[]]}
        if pr:
            self.api[self.prefix + "/pulls/1"] = dict(number=1, commits=1, user=dict(login="owner", type="User"),
                body="Refs #2\nPlan: https://github.com/fixture/adopter/issues/2#issuecomment-3", title="Task",
                base=dict(sha="a"*40, repo=dict(full_name="fixture/adopter")), head=dict(sha="b"*40, ref=self.branch))
            self.api[self.prefix + "/issues/comments/3"] = copy.deepcopy(self.rows[1])
            self.api[self.prefix + "/pulls/1/commits"] = [{"sha": "b"*40, "commit": {"committer": {"date": "2026-01-01T00:05:00Z"}}}]

    def run_helper(self, *args, data=None, helper=HELPER):
        self.records.write_text(json.dumps(self.api))
        self.calls.write_text("")
        result = subprocess.run(["bash", str(helper), *args], input=data, env=self.env,
                                cwd=self.work, capture_output=True, timeout=20)
        self.log = [json.loads(x) for x in self.calls.read_text().splitlines()]
        self.assertTrue(all(x["method"] == "GET" for x in self.log))
        return result

    def render(self, kind, **values):
        values.setdefault("task", 2)
        return self.run_helper("render", kind, "--input", "-", data=json.dumps(values).encode())

    def preflight(self, kind, body, *, pr=False):
        self.body.write_bytes(body)
        return self.run_helper("preflight", kind, "--repo", "fixture/adopter", "--task", "2", "--body-file", str(self.body),
                               "--branch", self.branch, *(["--pr", "1"] if pr else []))

    def guard_external_argument_size(self):
        # Deterministic cross-platform seam for Linux's per-string boundary.
        # Real tools still consume stdin; this is not a Linux kernel measurement.
        for name in ("jq", "grep", "awk"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            wrapper = self.bin / name
            wrapper.write_text("#!" + sys.executable + "\n" +
                "import os,sys\n"
                "if any(len(os.fsencode(arg)) >= 131072 for arg in sys.argv[1:]):\n"
                " print('fixture: oversized external argument refused',file=sys.stderr);sys.exit(126)\n"
                "os.execv(" + repr(executable) + ", [" + repr(executable) + ", *sys.argv[1:]])\n")
            wrapper.chmod(0o755)
        self.env["RECORD_JQ"] = str(self.bin / "jq")

    def test_render_all_kinds_and_read_only_preflight_use_actual_bytes(self):
        for kind in ("claim", "resume", "plan", "dispatch"):
            with self.subTest(kind=kind):
                values = dict(content="Implement bounded work.\nNo hidden authorization.") if kind == "plan" else dict(session="Task worker", branch=self.branch)
                if kind == "dispatch": values["session_id"] = "/root/supervisor/worker"
                rendered = self.render(kind, **values)
                self.assertEqual(0, rendered.returncode, rendered.stderr)
                self.assertEqual([], self.log)
                result = self.preflight(kind, rendered.stdout)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(2, sum(x["key"].endswith("/issues/2") for x in self.log))
                self.assertEqual(2, sum(x["key"].endswith("/comments") for x in self.log))
                self.assertNotIn(rendered.stdout, result.stdout)
                broken = rendered.stdout.replace(b"Task: #2", b"Task: #3")
                self.assertNotEqual(0, self.preflight(kind, broken).returncode)

    def test_render_refuses_schema_controls_placeholders_and_duplicate_keys_without_body(self):
        records = [b'{"task":2,"task":3,"content":"real prose"}', b'{}', b'[]', b'{"task":true,"content":"plan"}',
                   b'{"task":2,"content":"\\u0000"}', b'{"task":2,"content":"plan","extra":1}',
                   b'{"task":2,"content":"plan"}\n{}', b'x'*262145]
        for raw in records:
            result = self.run_helper("render", "plan", "--input", "-", data=raw)
            self.assertNotEqual(0, result.returncode, repr(raw[:80]))
            self.assertEqual(b"", result.stdout)
            self.assertEqual([], self.log)
        for reference in ("/root/placeholder", "/root/x/../y", "/root/worker;false", "deadbeef suffix", "a"*129):
            result = self.render("dispatch", session="Worker", session_id=reference, branch=self.branch)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"", result.stdout)
        for session in ("unknown", "<name>", "x\nReleasing worker", "X, branch forged", " leading"):
            self.assertNotEqual(0, self.render("claim", session=session, branch=self.branch).returncode)

    def test_legacy_and_canonical_dispatch_ids_have_one_grammar(self):
        for reference in ("deadbeef", "12345678-abcd", "/root/worker", "/root/a_b/worker2"):
            body = self.render("dispatch", session="Worker", session_id=reference, branch=self.branch)
            self.assertEqual(0, body.returncode, body.stderr)
            self.assertEqual(0, self.preflight("dispatch", body.stdout).returncode)

    def test_nested_duplicate_fields_refuse_before_json_collapse(self):
        for kind in ("claim", "resume", "plan", "dispatch"):
            valid = dict(task=2, content="Actual bounded plan.") if kind == "plan" else dict(
                task=2, session="Worker", branch=self.branch)
            if kind == "dispatch": valid["session_id"] = "/root/supervisor/worker"
            self.assertEqual(0, self.run_helper("render", kind, "--input", "-",
                                              data=json.dumps(valid).encode()).returncode)
            for field in valid:
                for nested in ('{"shadow":1}', '[1]', '{"shadow":[{"deep":1}]}'):
                    with self.subTest(kind=kind, field=field, nested=nested):
                        # Even escaped root key spellings denote the same key.
                        key = json.dumps(field[:-1])[0:-1] + '\\u%04x"' % ord(field[-1])
                        raw = ('{' + key + ':' + nested + ',' + json.dumps(valid)[1:]).encode()
                        result = self.run_helper("render", kind, "--input", "-", data=raw)
                        self.assertEqual(2, result.returncode, result.stderr)
                        self.assertEqual(b"", result.stdout)
                        self.assertEqual([], self.log)

    def test_long_utf8_plan_draft_streams_below_unchanged_input_limit(self):
        self.guard_external_argument_size()
        for content in ("あ"*10000, "日本語🙂\n"*11000, "x"*262100):
            raw = json.dumps(dict(task=2, content=content), ensure_ascii=False).encode()
            self.assertLessEqual(len(raw), 262144)
            rendered = self.run_helper("render", "plan", "--input", "-", data=raw)
            self.assertEqual(0, rendered.returncode, rendered.stderr)
            self.assertEqual([], self.log)
            self.assertEqual(("## Plan\n\nTask: #2\n\n"+content+"\n").encode(), rendered.stdout)
            result = self.preflight("plan", rendered.stdout)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn(rendered.stdout, result.stdout)

    def test_malformed_utf8_and_nul_refuse_without_body_or_api(self):
        malformed = (b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xe2\x82", b"\xf4\x90\x80\x80", b"\x00")
        for value in malformed:
            for source in ("-", str(self.input)):
                with self.subTest(value=value, source=source == "-"):
                    raw = b'{"task":2,"content":"actual ' + value + b' plan"}'
                    self.input.write_bytes(raw)
                    result = self.run_helper("render", "plan", "--input", source,
                                             data=raw if source == "-" else None)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertEqual(b"", result.stdout)
                    self.assertEqual([], self.log)
                    body = b"## Plan\n\nTask: #2\n\nactual " + value + b" plan\n"
                    result = self.run_helper("preflight", "plan", "--repo", "fixture/adopter", "--task", "2",
                                             "--body-file", "-", "--branch", self.branch, data=body)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertEqual(b"", result.stdout)
                    self.assertEqual([], self.log)
                    result = self.preflight("plan", body)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertEqual(b"", result.stdout)
                    self.assertEqual([], self.log)

    def test_valid_unicode_trailing_lf_and_exact_byte_boundaries(self):
        self.guard_external_argument_size()
        content = "日本語🙂�\n\n"
        raw = json.dumps(dict(task=2, content=content), ensure_ascii=False).encode()
        for suffix in (b"", b"\n", b"\n\n"):
            result = self.run_helper("render", "plan", "--input", "-", data=raw + suffix)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(("## Plan\n\nTask: #2\n\n" + content + "\n").encode(), result.stdout)
        prefix = b'{"task":2,"content":"'
        raw = prefix + b"x" * (262144 - len(prefix) - 2) + b'"}'
        self.assertEqual(262144, len(raw))
        self.assertEqual(0, self.run_helper("render", "plan", "--input", "-", data=raw).returncode)
        over = self.run_helper("render", "plan", "--input", "-", data=raw + b" ")
        self.assertEqual(2, over.returncode)
        self.assertEqual(b"", over.stdout)
        prefix = b"## Plan\n\nTask: #2\n\n"
        body = prefix + b"x" * (262144 - len(prefix) - 2) + b"\n\n"
        self.assertEqual(262144, len(body))
        self.assertEqual(0, self.preflight("plan", body).returncode)
        over = self.preflight("plan", body + b"\n")
        self.assertEqual(2, over.returncode)
        self.assertEqual(b"", over.stdout)

    def test_long_linked_plan_streams_in_preflight_and_inherited_numeric_mode(self):
        self.guard_external_argument_size()
        for content in ("あ"*10000, "日本語🙂\n"*11000):
            self.rows[1]["body"] = "## Plan\n\nTask: #2\n\n" + content + "\n\n"
            self.rows = self.rows[:2] + [self.dispatch()]
            self.rows += [dict(self.comment("Status " + "x"*1000, 4), id=100+i) for i in range(120)]
            self.ledger(pr=True)
            body = self.render("resume", session="Supervisor", branch=self.branch).stdout
            result = self.preflight("resume", body, pr=True)
            self.assertEqual(0, result.returncode, result.stderr)
            result = self.run_helper("1")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.api[self.prefix+"/issues/comments/3"]["body"] = self.rows[1]["body"][:-1]
            for mode in ("preflight", "numeric"):
                result = self.preflight("resume", body, pr=True) if mode == "preflight" else self.run_helper("1")
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertNotIn(b"PASS:", result.stdout)

    def test_long_linked_plan_final_readbacks_refuse_drift_in_both_modes(self):
        self.guard_external_argument_size()
        self.rows[1]["body"] += "日本語🙂\n"*11000 + "\n\n"
        self.rows.append(self.dispatch())
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        for suffix, change in (("/issues/2/comments", lambda x:x["pages"][0][1].update(body=x["pages"][0][1]["body"]+"\n")),
                               ("/issues/comments/3", lambda x:x.update(body=x["body"]+"\n"))):
            for mode in ("preflight", "numeric"):
                self.ledger(pr=True)
                key = self.prefix + suffix
                old = copy.deepcopy(self.api[key]); changed = copy.deepcopy(old); change(changed)
                self.api[key] = {"responses": [old, changed]}
                result = self.preflight("resume", body, pr=True) if mode == "preflight" else self.run_helper("1")
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn(b"drift" if mode == "numeric" else b"readback", result.stdout + result.stderr)
                self.assertNotIn(b"PASS:", result.stdout)

    def test_preflight_requires_claim_and_plan_without_fabricating_them(self):
        body = self.render("dispatch", session="Worker", session_id="deadbeef", branch=self.branch).stdout
        for rows in ([], self.rows[:1]):
            self.rows = rows; self.ledger()
            result = self.preflight("dispatch", body)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"", result.stdout)

    def test_replacement_release_and_old_branch_are_shared_with_pr_sensor(self):
        self.rows += [self.dispatch("codex/old-worker"), self.comment("Releasing worker: stopped and retained evidence", 3), self.dispatch(minute=4)]
        self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        self.assertEqual(0, self.preflight("resume", body, pr=True).returncode)
        result = self.run_helper("1")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for defect in ("missing-release", "edited-release", "wrong-current-branch"):
            original = copy.deepcopy(self.rows)
            if defect == "missing-release": self.rows.pop(3)
            elif defect == "edited-release": self.rows[3]["updated_at"] = "2026-01-01T00:04:00Z"
            else: self.rows[-1]["body"] = self.rows[-1]["body"].replace(self.branch, "codex/wrong")
            self.ledger(pr=True)
            self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode, defect)
            self.assertNotEqual(0, self.run_helper("1").returncode, defect)
            self.rows = original

    def test_release_alone_never_exempts_last_dispatch_branch(self):
        self.rows += [self.dispatch("codex/old-worker"), self.comment("Releasing worker: old", 3)]
        self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)
        self.assertNotEqual(0, self.run_helper("1").returncode)

    def test_superseded_malformed_branch_still_refuses_both_paths(self):
        self.rows += [self.dispatch("codex/bad..branch"), self.comment("Releasing worker: old", 3), self.dispatch(minute=4)]
        self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)
        self.assertNotEqual(0, self.run_helper("1").returncode)

    def test_first_dispatch_cannot_be_backdated_after_existing_exempt_pr(self):
        self.rows[1]["body"] += "no worker will be spawned\n"
        self.ledger(pr=True)
        body = self.render("dispatch", session="Worker", session_id="deadbeef", branch=self.branch).stdout
        result = self.preflight("dispatch", body, pr=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b"first-dispatch-after-commit", result.stderr)

    def test_complete_long_pages_and_exact_plan_terminal_newline(self):
        self.rows.append(self.dispatch())
        for i in range(120):
            self.rows.append(dict(self.comment("Status 日本語🙂\n" + "x"*1500, 4), id=100+i))
        self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        result = self.preflight("resume", body, pr=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.api[self.prefix + "/issues/comments/3"]["body"] = self.rows[1]["body"][:-1]
        self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)
        self.ledger(pr=True)
        self.api[self.prefix + "/issues/2/comments"]["pages"][1].pop()
        self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)

    def test_final_readbacks_detect_task_pages_plan_and_pr_changes(self):
        self.rows.append(self.dispatch()); self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        for suffix, change in (("/issues/2", lambda x:x.update(body="changed")),
                ("/issues/2/comments", lambda x:x["pages"][0][0].update(body="changed")),
                ("/issues/comments/3", lambda x:x.update(body=x["body"]+"\n")),
                ("/pulls/1", lambda x:x["head"].update(sha="c"*40))):
            self.ledger(pr=True)
            key = self.prefix + suffix
            old = copy.deepcopy(self.api[key]); changed = copy.deepcopy(old); change(changed)
            self.api[key] = {"responses": [old, changed]}
            result = self.preflight("resume", body, pr=True)
            self.assertNotEqual(0, result.returncode, suffix)
            self.assertEqual(b"", result.stdout)

    def test_optional_pr_unavailable_or_bad_chronology_never_downgrades(self):
        self.rows.append(self.dispatch()); self.ledger(pr=True)
        body = self.render("resume", session="Supervisor", branch=self.branch).stdout
        for suffix in ("/pulls/1", "/pulls/1/commits", "/issues/comments/3"):
            self.ledger(pr=True); self.api[self.prefix+suffix] = None
            self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)
        self.ledger(pr=True)
        self.api[self.prefix+"/pulls/1/commits"][0]["commit"]["committer"]["date"] = "2026-01-01T00:00:00Z"
        self.assertNotEqual(0, self.preflight("resume", body, pr=True).returncode)


class DeliveryTests(unittest.TestCase):
    def fixture(self):
        fixture = module("test_installer").InstallerTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def old_source(self, fixture):
        old = fixture.clone_source()
        record = json.loads(BASELINE.read_text())
        self.assertEqual("abd7a4fba7ef5ff484efff625e2474cc32d6ef7b", record["commit"])
        for row in record["entries"]:
            data = base64.b64decode(row["base64"], validate=True)
            self.assertEqual(row["sha256"], hashlib.sha256(data).hexdigest())
            (old / ".github/distribution/payload" / row["path"]).write_bytes(data)
        fixture.reseal_payload(old)
        return old, record

    def test_exact_accepted_old_upgrade_and_rollback_preserve_tuned_files_and_index(self):
        fixture = self.fixture()
        old, record = self.old_source(fixture)
        self.assertEqual(0, fixture.run_install("--apply", source=old).returncode)
        preserved = ("README.md", "AGENTS.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md")
        for name in preserved:
            (fixture.target / name).write_text("Adopter-owned agreement remains authoritative\n")
            (fixture.target / name).chmod(0o600)
        fixture.commit_adopter("Synthetic exact accepted-old installation")
        (fixture.target / "unrelated.txt").write_text("staged content\n")
        fixture.git("add", "unrelated.txt")
        (fixture.target / "unrelated.txt").write_text("unstaged content\n")
        before = fixture.snapshot(fixture.target)
        modes = {str(p.relative_to(fixture.target)): p.stat().st_mode for p in fixture.target.rglob("*")}
        fixture.old_source, fixture.new_source = old, ROOT
        fixture.transaction = fixture.base / "workflow operation"
        result = fixture.upgrade("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        after = fixture.snapshot(fixture.target)
        changed = {row["path"] for row in record["entries"]} - {".github/codex-instructions.md"}
        self.assertEqual(changed, {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)})
        for name in changed:
            self.assertEqual((ROOT / ".github/distribution/payload" / name).read_bytes(), (fixture.target / name).read_bytes())
        result = fixture.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, fixture.snapshot(fixture.target))
        self.assertEqual(modes, {str(p.relative_to(fixture.target)): p.stat().st_mode for p in fixture.target.rglob("*")})

    def test_unknown_engine_edit_refuses_before_any_update(self):
        fixture = self.fixture()
        old, _ = self.old_source(fixture)
        self.assertEqual(0, fixture.run_install("--apply", source=old).returncode)
        helper = fixture.target / ".github/scripts/check-task-ritual.sh"
        helper.write_bytes(helper.read_bytes() + b"\n# adopter edit\n")
        before = fixture.snapshot(fixture.target)
        fixture.old_source, fixture.new_source = old, ROOT
        fixture.transaction = fixture.base / "refused workflow operation"
        self.assertNotEqual(0, fixture.upgrade("--apply").returncode)
        self.assertEqual(before, fixture.snapshot(fixture.target))

    def test_fresh_installed_helper_runs_offline_render_and_get_only_preflight(self):
        fixture = self.fixture()
        self.assertEqual(0, fixture.run_install("--apply").returncode)
        records = RecordTests(methodName="runTest")
        records.setUp(); self.addCleanup(records.doCleanups)
        installed = fixture.target / ".github/scripts/check-task-ritual.sh"
        rendered = records.run_helper("render", "plan", "--input", "-", helper=installed,
            data=b'{"task":2,"content":"Implement the bounded installed workflow."}')
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertEqual([], records.log)
        records.body.write_bytes(rendered.stdout)
        result = records.run_helper("preflight", "plan", "--repo", "fixture/adopter", "--task", "2",
                                    "--body-file", str(records.body), helper=installed)
        self.assertEqual(0, result.returncode, result.stderr)


class StartupContractTests(unittest.TestCase):
    def test_entry_resume_and_supervisor_contract_is_reachable(self):
        payload = ROOT / ".github/distribution/payload"
        instructions = (payload / ".github/codex-instructions.md").read_text()
        session = (payload / ".agents/skills/session-orchestration/SKILL.md").read_text()
        onboarding = (payload / ".agents/skills/project-onboarding/SKILL.md").read_text()
        planning = (payload / ".agents/skills/plan-management/SKILL.md").read_text()
        # Document contracts, not a model or live worker execution claim.
        for token in ("scoped", "unrevoked", "work order/kickoff", "Anything else", "warning-only CI"):
            self.assertIn(token, instructions)
        for token in ("Exit 0", "Exit 1", "Any other exit", "New explicit request", "Worker disposition",
                      "exact worker HEAD SHA", "Role-specific resume", "supervisor only", "Startup context:",
                      "render claim", "GET-only", "preserve evidence on failure"):
            self.assertIn(token, session)
        self.assertIn("before inventory/tuning", onboarding)
        self.assertIn("supervisor posts a *revised-plan comment*", planning)
        self.assertNotIn("Otherwise the report is your", onboarding)
        self.assertNotIn("executor posts a *revised-plan comment*", planning)


if __name__ == "__main__":
    unittest.main()
