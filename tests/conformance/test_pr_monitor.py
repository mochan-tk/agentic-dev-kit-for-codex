"""Real fake-gh subprocesses, bounded files and mandatory product sensor gates."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ".github/scripts/pr-monitor.py"
REPO = "fixture/example"
HEAD = "a" * 40
BASE = "b" * 40
EXPECTED = [{"name": "quality", "app_id": 15368}]


def pull(number=1, **changes):
    value = {"id": 1000 + number, "number": number, "state": "open", "draft": False,
             "updated_at": "2026-01-01T00:00:00Z", "title": "PRIVATE_SENTINEL",
             "body": "PRIVATE_SENTINEL $(touch should-not-exist)",
             "url": f"https://api.github.com/repos/{REPO}/pulls/{number}",
             "html_url": f"https://github.com/{REPO}/pull/{number}",
             "head": {"sha": HEAD, "ref": "private/branch", "repo": {"id": 91, "full_name": "fixture/fork"}},
             "base": {"sha": BASE, "ref": "main", "repo": {"id": 90, "full_name": REPO}}}
    value.update(changes)
    return value


def check(identifier=20, **changes):
    value = {"id": identifier, "name": "quality", "app": {"id": 15368}, "head_sha": HEAD,
             "status": "completed", "conclusion": "success", "details_url": "https://private.invalid/secret",
             "url": f"https://api.github.com/repos/{REPO}/check-runs/{identifier}"}
    value.update(changes)
    return value


def review(identifier=30, **changes):
    value = {"id": identifier, "user": {"id": 50, "login": "PRIVATE_SENTINEL"},
             "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z", "commit_id": HEAD,
             "body": "PRIVATE_SENTINEL", "pull_request_url": f"https://api.github.com/repos/{REPO}/pulls/1",
             "html_url": f"https://github.com/{REPO}/pull/1#pullrequestreview-{identifier}"}
    value.update(changes)
    return value


FAKE_GH = r'''
import json, os, sys, time
from pathlib import Path
from urllib.parse import parse_qs, urlencode
path = Path(os.environ['FIXTURE_STATE'])
s = json.loads(path.read_text())
args = sys.argv[1:]
assert args[:11] == ['api','--hostname','github.com','--method','GET','--include','-H',
                    'Accept: application/vnd.github+json','-H','X-GitHub-Api-Version: 2022-11-28',args[-1]], args
assert len(args) == 11, args
assert os.environ['GH_HOST'] == 'github.com' and os.environ['GH_DEBUG'] == '', args
assert not sys.stdin.buffer.read(1), args
endpoint = args[-1]
assert endpoint.startswith('repos/fixture/example/'), endpoint
s.setdefault('calls', []).append(endpoint)
call = len(s['calls'])
occurrence = s['calls'].count(endpoint)
if s.get('fail_at') == call:
    path.write_text(json.dumps(s)); print('PRIVATE_SENTINEL /private/local/path',file=sys.stderr); sys.exit(1)
route, query = endpoint.split('?',1) if '?' in endpoint else (endpoint,'')
q = parse_qs(query, strict_parsing=True)
page = int(q.get('page',['1'])[0]); link = ''
if route.endswith('/pulls'):
    assert q.get('state') == ['open'] and q.get('sort') == ['created'] and q.get('direction') == ['asc'] and q.get('per_page') == ['50'], q
    rows = s.get('pulls',[])
elif '/commits/' in route:
    assert route.endswith('/check-runs') and q.get('filter') == ['latest'] and q.get('per_page') == ['50'], q
    rows = s.get('checks',[])
elif route.endswith('/reviews'):
    assert q.get('per_page') == ['50'], q
    rows = s.get('reviews',[])
else:
    assert not query and route.rsplit('/',1)[1].isdigit(), endpoint
    rows = None
    result = next(r for r in s.get('pulls',[]) if r['number'] == int(route.rsplit('/',1)[1]))
if rows is not None:
    start = (page - 1) * 50
    result = rows[start:start + 50]
    if s.get('duplicate_page') and page == 2: result = rows[:1]
    if len(rows) > 50:
        last = (len(rows) + 49) // 50
        root_query = {k:v[0] for k,v in q.items() if k != 'page'}
        prefix = 'https://api.github.com/' + route
        if s.get('numeric_links'): prefix = prefix.replace('repos/fixture/example','repositories/90')
        def url(n): return prefix + '?' + urlencode(dict(root_query,page=n))
        links = []
        if page < last: links.append('<'+url(page+1)+'>; rel="next"')
        links.append('<'+url(last)+'>; rel="last"')
        link = ', '.join(links)
    if route.endswith('/check-runs'): result = {'total_count':len(rows),'check_runs':result}
if s.get('drift_at') == call or (s.get('drift_route') == route.rsplit('/',1)[1] and occurrence > 1):
    result = json.loads(json.dumps(result))
    kind = s.get('drift_kind','head')
    if route.endswith('/pulls'): result = []
    elif route.endswith('/check-runs'):
        result['check_runs'][0]['conclusion'] = 'failure'
    elif route.endswith('/reviews'):
        result[0]['state'] = 'CHANGES_REQUESTED'
    elif kind == 'base': result['base']['sha'] = 'c'*40
    else: result['head']['sha'] = 'c'*40
if s.get('mutate_previous_at') == call:
    p = Path(os.environ['FIXTURE_PREVIOUS']); p.write_bytes(p.read_bytes()+b' ')
path.write_text(json.dumps(s))
if s.get('sleep_at') == call: time.sleep(30)
if s.get('invalid_utf8_at') == call:
    sys.stdout.buffer.write(b'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n\xff'); sys.exit()
body = json.dumps(result,ensure_ascii=False)
if s.get('raw_at') == call: body = s['raw']
if s.get('oversize_at') == call: body = 'x'*2200000
headers = 'HTTP/2 200\r\nContent-Type: application/json\r\n'
if link: headers += 'Link: '+link+'\r\n'
if s.get('header_at') == call: headers = s['header']
if s.get('link_at') == call: headers += 'Link: '+s['link']+'\r\n'
sys.stdout.write(headers+'\r\n'+body)
'''


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("pr_monitor_tests", ROOT / SCRIPT)
        cls.helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.helper)
        spec = importlib.util.spec_from_file_location("pr_monitor_product_tests", ROOT / ".github/scripts/check-product.py")
        cls.checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.checker)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pr-monitor-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.bin = self.directory / "bin"; self.bin.mkdir()
        gh = self.bin / "gh"; gh.write_text("#!" + sys.executable + "\n" + FAKE_GH); gh.chmod(0o700)
        self.state = self.directory / "state.json"
        self.previous = self.directory / "previous.json"
        self.env = {"PATH": str(self.bin) + ":/usr/bin:/bin", "LC_ALL": "C",
                    "GH_HOST": "private.invalid", "GH_DEBUG": "api", "FIXTURE_STATE": str(self.state),
                    "FIXTURE_PREVIOUS": str(self.previous)}
        self.save()

    def save(self, **changes):
        value = {"pulls": [pull()], "checks": [check()], "reviews": [], "calls": []}
        value.update(changes)
        self.state.write_text(json.dumps(value))

    def calls(self):
        return json.loads(self.state.read_text())["calls"]

    def run_cli(self, *extra, ok=0, base=True):
        args = [sys.executable, "-I", str(ROOT / SCRIPT)]
        if base: args += ["--repo", REPO, "--check", "quality=15368"]
        result = subprocess.run(args + list(extra), env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(ok, result.returncode, result.stdout + result.stderr)
        for private in ("PRIVATE_SENTINEL", "private.invalid", str(self.directory)):
            self.assertNotIn(private, result.stdout + result.stderr)
        if ok == 1:
            report = json.loads(result.stdout)
            self.assertEqual("UNCONFIRMED", report["state"])
            self.assertEqual([], report["pull_requests"])
            self.assertEqual("observation-unconfirmed", report["diagnostic"])
        return result

    def report(self):
        return json.loads(self.run_cli().stdout)

    def save_previous(self):
        self.previous.write_text(self.run_cli().stdout)
        return self.previous.read_bytes()

    def test_success_and_empty_double_inventory_get_only(self):
        report = self.report()
        self.assertEqual("NO_ACTION", report["state"])
        row = report["pull_requests"][0]
        self.assertEqual(HEAD, row["head"]["sha"])
        self.assertEqual(BASE, row["base"]["sha"])
        self.assertEqual("https://github.com/fixture/example/runs/20", row["checks"][0]["url"])
        self.assertEqual(8, len(self.calls()))
        self.save(pulls=[])
        self.assertEqual([], self.report()["pull_requests"])
        self.assertEqual(2, len(self.calls()))

    def test_running_failure_draft_and_global_priority(self):
        for status in self.helper.RUNNING:
            with self.subTest(status=status):
                self.save(checks=[check(status=status, conclusion=None)])
                self.assertEqual("WAITING", self.report()["state"])
        for conclusion in self.helper.FAILURES:
            with self.subTest(conclusion=conclusion):
                self.save(checks=[check(conclusion=conclusion)])
                self.assertEqual("ACTION_REQUIRED", self.report()["state"])
        self.save(pulls=[pull(draft=True)])
        self.assertEqual("WAITING", self.report()["state"])
        self.save(pulls=[pull(draft=True)], reviews=[review(state="CHANGES_REQUESTED")])
        self.assertEqual("ACTION_REQUIRED", self.report()["state"])

    def test_current_latest_failure_does_not_select_higher_id_success(self):
        self.save(checks=[check(10, conclusion="failure")])
        self.assertEqual("ACTION_REQUIRED", self.report()["state"])
        self.save(checks=[check(10, conclusion="failure"), check(99)])
        self.run_cli(ok=1)
        self.save(checks=[check(99, status="in_progress", conclusion=None)])
        self.assertEqual("WAITING", self.report()["state"])

    def test_missing_wrong_issuer_or_same_name_mix_refuses(self):
        for rows in ([], [check(app={"id": 1})], [check(), check(21)],
                     [check(), check(21, app={"id": 1})]):
            with self.subTest(rows=len(rows)):
                self.save(checks=rows); self.run_cli(ok=1)
        for conclusion in ("neutral", "skipped", "stale"):
            self.save(checks=[check(conclusion=conclusion)]); self.run_cli(ok=1)

    def test_old_changes_request_new_comment_dismissal_and_approval(self):
        old = review(state="CHANGES_REQUESTED", commit_id="c" * 40)
        self.save(reviews=[old])
        row = self.report()["pull_requests"][0]
        self.assertEqual("ACTION_REQUIRED", row["state"])
        self.assertEqual("c" * 40, row["reviews"][0]["reviews"][0]["commit_sha"])
        later = review(2, submitted_at="2026-01-03T00:00:00Z", state="COMMENTED")
        self.save(reviews=[old, later])
        self.assertEqual("ACTION_REQUIRED", self.report()["state"])
        for state in ("DISMISSED", "APPROVED"):
            later["state"] = state
            self.save(reviews=[old, later])
            self.assertEqual("NO_ACTION", self.report()["state"])

    def test_numeric_user_not_login_and_submitted_time_not_id(self):
        old = review(999, state="CHANGES_REQUESTED")
        later = review(1, submitted_at="2026-01-03T00:00:00Z")
        self.save(reviews=[old, later, review(3, user={"id": 51, "login": "PRIVATE_SENTINEL"}, state="COMMENTED")])
        result = self.report()["pull_requests"][0]["reviews"]
        self.assertEqual([50, 51], [row["user_id"] for row in result])
        self.assertEqual(1, result[0]["reviews"][0]["id"])
        self.assertEqual("NO_ACTION", self.report()["state"])

    def test_pending_unpublished_equal_time_compatible_and_contradictory(self):
        self.save(reviews=[review(state="PENDING", submitted_at=None)])
        self.assertEqual([], self.report()["pull_requests"][0]["reviews"])
        self.save(reviews=[review(), review(31)])
        result = self.report()["pull_requests"][0]["reviews"][0]
        self.assertEqual([30, 31], [row["id"] for row in result["reviews"]])
        self.save(reviews=[review(), review(31, state="CHANGES_REQUESTED")])
        self.run_cli(ok=1)

    def test_initial_and_final_pr_head_base_check_review_inventory_drift(self):
        for changes in ({"drift_at": 2}, {"drift_at": 5}, {"drift_at": 5, "drift_kind": "base"},
                        {"drift_at": 6}, {"drift_at": 7}, {"drift_at": 8}):
            with self.subTest(changes=changes):
                self.save(reviews=[review()], **changes); self.run_cli(ok=1)

    def test_api_failure_at_every_stage_is_not_empty(self):
        for call in range(1, 9):
            with self.subTest(call=call):
                self.save(fail_at=call); self.run_cli(ok=1)
        self.save(pulls=[], fail_at=2); self.run_cli(ok=1)

    def test_complete_check_and_review_paging(self):
        checks = [check(n, name="other" + str(n)) for n in range(1, 52)] + [check(100)]
        reviews = [review(n, user={"id": n}, state="COMMENTED") for n in range(1, 52)]
        for numeric in (False, True):
            self.save(checks=checks, reviews=reviews, numeric_links=numeric)
            row = self.report()["pull_requests"][0]
            self.assertEqual(51, len(row["reviews"]))
            self.assertTrue(any("check-runs?filter=latest&per_page=50&page=2" in endpoint for endpoint in self.calls()))
            self.assertTrue(any("reviews?per_page=50&page=2" in endpoint for endpoint in self.calls()))

    def test_later_page_failure_duplicate_ids_and_missing_page_no_partial(self):
        checks = [check(n, name="other" + str(n)) for n in range(1, 52)] + [check(100)]
        for changes in ({"fail_at": 4}, {"duplicate_page": True},
                        {"header_at": 3, "header": 'HTTP/2 200\r\nContent-Type: application/json\r\nLink: <https://api.github.com/repos/fixture/example/commits/'+HEAD+'/check-runs?filter=latest&per_page=50&page=2>; rel="last"\r\n'}):
            with self.subTest(changes=list(changes)):
                self.save(checks=checks, **changes); self.run_cli(ok=1)
        self.save(checks=[check(), check(20, name="other")]); self.run_cli(ok=1)
        self.save(reviews=[review(), review()]); self.run_cli(ok=1)
        self.save(pulls=[pull(), pull()]); self.run_cli(ok=1)
        self.save(pulls=[pull(), pull(id=2000)]); self.run_cli(ok=1)

    def test_pr_limit_not_silently_truncated_and_multiple_prs(self):
        self.save(pulls=[pull(n) for n in range(1, 27)]); self.run_cli(ok=1)
        self.save(pulls=[pull(2), pull(1)])
        self.assertEqual([1, 2], [row["number"] for row in self.report()["pull_requests"]])

    def test_invalid_http_json_unicode_and_privacy_fixed_diagnostics(self):
        headers = ("HTTP/2 403\r\nContent-Type: application/json\r\n",
                   "HTTP/3 200\r\nContent-Type: application/json\r\n",
                   "HTTP/2 200\r\nContent-Type: text/plain\r\n",
                   "HTTP/2 200\r\nContent-Type: application/json\r\ncontent-type: application/json\r\n",
                   "HTTP/2 200\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n",
                   "HTTP/2 200\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\n",
                   "HTTP/2 200\r\nContent-Type: application/json\r\nLocation: https://private.invalid/\r\n",
                   "HTTP/2 200\r\nContent-Type: application/json\r\nContent-Length: 1\r\n")
        for header in headers:
            self.save(header_at=1, header=header); self.run_cli(ok=1)
        for raw in ('{"x":1,"x":2}', "NaN", "Infinity", "-Infinity", "[", "PRIVATE_SENTINEL", "{}"):
            self.save(raw_at=1, raw=raw); self.run_cli(ok=1)
        self.save(invalid_utf8_at=1); self.run_cli(ok=1)
        self.save(oversize_at=1); self.run_cli(ok=1)

    def test_malformed_identity_types_and_inconsistent_check_state(self):
        for changes in ({"id": True}, {"draft": 0}, {"number": 0}, {"updated_at": "2026-02-30T00:00:00Z"},
                        {"state": "closed"}, {"updated_at": "2999-01-01T00:00:00Z"},
                        {"url": "https://private.invalid"}, {"head": None},
                        {"base": {"sha": BASE, "ref": "main", "repo": {"id": 90, "full_name": "other/repo"}}}):
            self.save(pulls=[pull(**changes)]); self.run_cli(ok=1)
        for changes in ({"id": True}, {"app": None}, {"head_sha": "c" * 40}, {"name": None},
                        {"url": "https://api.github.com/repos/other/repo/check-runs/20"},
                        {"status": "completed", "conclusion": None}, {"status": "queued", "conclusion": "success"}):
            self.save(checks=[check(**changes)]); self.run_cli(ok=1)
        for changes in ({"user": None}, {"user": {"id": True}}, {"commit_id": None},
                        {"submitted_at": "2999-01-01T00:00:00Z"},
                        {"pull_request_url": "https://api.github.com/repos/fixture/example/pulls/2"},
                        {"state": "PENDING", "submitted_at": "2026-01-02T00:00:00Z"}):
            self.save(reviews=[review(**changes)]); self.run_cli(ok=1)

    def test_foreign_or_malformed_links_refuse(self):
        for link in ('<https://private.invalid/>; rel="next"',
                     '<https://api.github.com/repos/fixture/example/pulls?state=open&sort=created&direction=asc&per_page=50&page=2>; rel="unknown"',
                     '<https://api.github.com/repos/fixture/example/pulls?state=open&sort=created&direction=asc&per_page=50&page=3>; rel="next"',
                     '<https://api.github.com/repos/fixture/example/pulls?state=closed&per_page=50&page=2>; rel="next"',
                     '<https://api.github.com/repos/fixture/example/pulls?state=open&sort=created&direction=asc&per_page=50&page=2&page=2>; rel="next"'):
            self.save(link_at=1, link=link); self.run_cli(ok=1)

    def test_ordinary_unicode_and_text_report(self):
        name = "品質 ✅"
        self.save(checks=[check(name=name)], pulls=[pull(title="通常の日本語", body="本文")])
        result = self.run_cli("--check", name + "=15368", ok=1)
        self.assertEqual("UNCONFIRMED", json.loads(result.stdout)["state"])
        result = self.run_cli("--repo", REPO, "--check", name + "=15368", base=False)
        self.assertEqual(name, json.loads(result.stdout)["expected_checks"][0]["name"])
        result = self.run_cli("--repo", REPO, "--check", name + "=15368", "--format", "text", base=False)
        self.assertIn("PR 1: NO_ACTION", result.stdout)
        self.assertIn("tested-latest-base", result.stdout)

    def test_invalid_arguments_before_api(self):
        for args in ([], ["--repo", "PRIVATE_SENTINEL", "--check", "quality=1"],
                     ["--repo", REPO], ["--repo", REPO, "--check", "quality=0"],
                     ["--repo", REPO, "--check", "quality=1", "--check", "quality=2"],
                     ["--repo", REPO, "--check", "x\nPRIVATE_SENTINEL=1"],
                     ["--unknown-PRIVATE_SENTINEL"], ["--repo", REPO, "--check", "quality=1", "--format", "PRIVATE_SENTINEL"]):
            self.save(); self.run_cli(*args, base=False, ok=2); self.assertEqual([], self.calls())

    def test_previous_unchanged_changed_recovery_new_removed_no_persistence(self):
        before = self.save_previous()
        self.save()
        report = json.loads(self.run_cli("--previous", str(self.previous)).stdout)
        self.assertEqual("unchanged", report["comparison"]["pull_requests"][0]["indicator"])
        self.assertEqual(before, self.previous.read_bytes())
        self.save(checks=[check(status="queued", conclusion=None)])
        self.assertEqual("changed", json.loads(self.run_cli("--previous", str(self.previous)).stdout)["comparison"]["pull_requests"][0]["indicator"])
        self.save(checks=[check(conclusion="failure")]); self.save_previous(); self.save()
        self.assertEqual("observed-recovery", json.loads(self.run_cli("--previous", str(self.previous)).stdout)["comparison"]["pull_requests"][0]["indicator"])
        retarget = pull()
        retarget["base"]["ref"] = "other"
        self.save(pulls=[retarget])
        self.assertEqual("changed", json.loads(self.run_cli("--previous", str(self.previous)).stdout)["comparison"]["pull_requests"][0]["indicator"])
        self.save(pulls=[pull(2)])
        report = json.loads(self.run_cli("--previous", str(self.previous)).stdout)
        self.assertEqual("new", report["comparison"]["pull_requests"][0]["indicator"])
        self.assertEqual("removed-from-open-inventory", report["comparison"]["removed"][0]["indicator"])
        self.previous.write_text(json.dumps(report)); self.save(pulls=[pull(2)])
        self.run_cli("--previous", str(self.previous))
        self.assertEqual({"state.json", "previous.json", "bin"}, {p.name for p in self.directory.iterdir()})

    def test_previous_invalid_closed_schema_derived_types_and_contract_before_api(self):
        value = json.loads(self.save_previous())
        for mode in ("repo", "expected", "bool-app", "extra", "duplicate", "state", "fingerprint", "url", "findings", "review", "comparison", "base"):
            record = json.loads(json.dumps(value))
            row = record["pull_requests"][0]
            if mode == "repo": record["repository"] = "other/repo"
            elif mode == "expected": record["expected_checks"][0]["app_id"] = 1
            elif mode == "bool-app": record["expected_checks"][0]["app_id"] = True
            elif mode == "extra": record["delivery"] = True
            elif mode == "duplicate": record["pull_requests"].append(row)
            elif mode == "state": row["state"] = "ACTION_REQUIRED"
            elif mode == "fingerprint": row["fingerprint"] = "0" * 64
            elif mode == "url": row["url"] = "https://private.invalid/"
            elif mode == "findings": row["findings"] = ["check-failed"]
            elif mode == "review": row["reviews"] = [{"state": "APPROVED"}]
            elif mode == "comparison": record["comparison"]["status"] = "delivered"
            else: row["base"]["repository_id"] = True
            self.previous.write_text(json.dumps(record)); self.save()
            self.run_cli("--previous", str(self.previous), ok=2); self.assertEqual([], self.calls())
        for raw in ('{"schema":1,"schema":2}', "NaN", "[]", "x" * (self.helper.FILE_LIMIT + 1)):
            self.previous.write_text(raw); self.save()
            self.run_cli("--previous", str(self.previous), ok=2); self.assertEqual([], self.calls())

    def test_previous_links_fifo_executable_mutation_and_permission_variation(self):
        original = self.save_previous()
        for mode in (0o600, 0o640, 0o644):
            self.previous.chmod(mode); self.save(); self.run_cli("--previous", str(self.previous))
        self.previous.chmod(0o755); self.save(); self.run_cli("--previous", str(self.previous), ok=2)
        self.previous.chmod(0o600)
        link = self.directory / "link.json"; link.symlink_to(self.previous)
        self.save(); self.run_cli("--previous", str(link), ok=2); self.assertEqual([], self.calls())
        linked = self.directory / "hard.json"; os.link(self.previous, linked)
        self.save(); self.run_cli("--previous", str(self.previous), ok=2); self.assertEqual([], self.calls()); linked.unlink()
        parent = self.directory / "linked-dir"; parent.symlink_to(self.directory, target_is_directory=True)
        self.save(); self.run_cli("--previous", str(parent / self.previous.name), ok=2); self.assertEqual([], self.calls())
        fifo = self.directory / "fifo"; os.mkfifo(fifo)
        self.save(); self.run_cli("--previous", str(fifo), ok=2); self.assertEqual([], self.calls())
        self.previous.write_bytes(original); self.save(mutate_previous_at=8)
        self.run_cli("--previous", str(self.previous), ok=1)

    def test_streaming_command_byte_call_total_and_deadline_bounds(self):
        for attribute, value in (("calls", self.helper.MAX_CALLS), ("total", self.helper.MAX_TOTAL_BYTES),
                                 ("deadline", time.monotonic() - 1)):
            transport = self.helper.Transport(); setattr(transport, attribute, value)
            with self.assertRaises(self.helper.Fault):
                transport.command([sys.executable, "-c", "print('bounded')"])
        transport = self.helper.Transport()
        with self.assertRaises(self.helper.Fault):
            transport.command([sys.executable, "-c", "import sys;sys.stdout.write('x'*2200000)"])
        transport = self.helper.Transport()
        with self.assertRaises(UnicodeError):
            transport.command([sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'\\xff')"])

    def test_owned_descendant_cleanup_with_exited_parent(self):
        pid_file = self.directory / "child.pid"
        program = ("import subprocess,sys\nfrom pathlib import Path\n"
                   "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
                   "Path(sys.argv[1]).write_text(str(p.pid))\n")
        transport = self.helper.Transport(); transport.deadline = time.monotonic() + 0.4
        with self.assertRaises(self.helper.Fault):
            transport.command([sys.executable, "-c", program, str(pid_file)])
        pid = int(pid_file.read_text())
        self.assert_process_stopped(pid)

    def assert_process_stopped(self, pid):
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            # A killed descendant may remain a zombie until its OS parent reaps it.
            status = Path("/proc") / str(pid) / "stat"
            try:
                if status.read_text().split(")", 1)[1].split()[0] == "Z":
                    return
            except FileNotFoundError:
                pass
            time.sleep(0.05)
        self.fail("owned command remains running")

    def test_selector_initialization_and_registration_errors_cleanup(self):
        real_popen = subprocess.Popen
        launched = []
        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs); launched.append(process); return process
        for fault in ("construction", "registration"):
            with patch.object(self.helper.subprocess, "Popen", side_effect=launch):
                if fault == "construction":
                    with patch.object(self.helper.selectors, "DefaultSelector", side_effect=OSError("PRIVATE_SENTINEL")):
                        with self.assertRaises(OSError): self.helper.Transport().command([sys.executable, "-c", "import time;time.sleep(30)"])
                else:
                    with patch.object(self.helper.selectors.DefaultSelector, "register", side_effect=OSError("PRIVATE_SENTINEL")):
                        with self.assertRaises(OSError): self.helper.Transport().command([sys.executable, "-c", "import time;time.sleep(30)"])
            self.assertIsNotNone(launched[-1].returncode)
            self.assertTrue(launched[-1].stdout.closed and launched[-1].stderr.closed)

    def test_page_total_caps_full_terminal_and_changed_total(self):
        ledger = self.helper.Ledger(None, REPO)
        class Endless:
            def api(_self, endpoint):
                page = int(endpoint.rsplit("page=", 1)[1]) if "&page=" in endpoint else 1
                return [{"id": (page-1)*50+n} for n in range(1,51)], {"link": (
                    '<https://api.github.com/repos/fixture/example/items?per_page=50&page='+str(page+1)+'>; rel="next", '
                    '<https://api.github.com/repos/fixture/example/items?per_page=50&page=11>; rel="last"')}
        ledger.transport = Endless()
        with self.assertRaises(self.helper.Fault): ledger.pages("repos/fixture/example/items?per_page=50", lambda row: row, 500)
        self.save(checks=[check(n, name="other"+str(n)) for n in range(1, 502)])
        self.run_cli(ok=1)

    @contextmanager
    def guard_fixture(self):
        with tempfile.TemporaryDirectory(prefix="pr-monitor-guard-") as temporary:
            root = Path(temporary)
            for name in (*self.checker.MONITOR_TARGETS, self.checker.MONITOR_RECORD):
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            yield root

    def reseal(self, root):
        path = root / self.checker.MONITOR_RECORD
        value = json.loads(path.read_bytes())
        for row in value["target_files"]:
            row["sha256"] = hashlib.sha256((root / row["path"]).read_bytes()).hexdigest()
        path.write_text(json.dumps(value))
        return patch.object(self.checker, "MONITOR_RECORD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())

    def test_product_requires_every_monitor_path_and_safe_modes(self):
        self.assertEqual([], self.checker.validate_pr_monitor(ROOT))
        for name in (*self.checker.MONITOR_TARGETS, self.checker.MONITOR_RECORD):
            with self.subTest(name=name), self.guard_fixture() as root:
                (root / name).unlink(); self.assertTrue(self.checker.validate_pr_monitor(root))
        for mode in (0o755, 0o744):
            with self.guard_fixture() as root:
                (root / SCRIPT).chmod(mode); self.assertTrue(self.checker.validate_pr_monitor(root))

    def test_manifest_tamper_resealed_closed_schema_inventory_and_modes_refuse(self):
        for kind in ("schema", "source", "task", "scope", "evidence", "inventory", "mode", "extra", "order"):
            with self.subTest(kind=kind), self.guard_fixture() as root:
                path = root / self.checker.MONITOR_RECORD; value = json.loads(path.read_bytes())
                if kind == "schema": value["schema"] = "pr-monitor/v2"
                elif kind == "source": value["product_base"] = "0" * 40
                elif kind == "task": value["task"] = "https://github.com/other/repo/issues/21"
                elif kind == "scope": value["scope"] = "scheduled"
                elif kind == "evidence": value["evidence"] = "runtime-qualified"
                elif kind == "inventory": value["target_files"].pop()
                elif kind == "mode": value["target_files"][0]["mode"] = "100755"
                elif kind == "order": value["target_files"].reverse()
                else: value["waiver"] = True
                path.write_text(json.dumps(value))
                with patch.object(self.checker, "MONITOR_RECORD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()):
                    self.assertTrue(self.checker.validate_pr_monitor(root))

    def test_resealed_forced_pass_transport_parser_and_observation_mutations_refuse(self):
        overrides = ("def require(value):\n    pass\n", "def parse_json(data):\n    return json.loads(data)\n",
                     "def selected_checks(records,expected,repo):\n    return []\n",
                     "def previous_report(data,repo,expected):\n    return json.loads(data)\n",
                     "def observe(ledger,expected):\n    return blank_report(ledger.repo,expected)\n",
                     "def response(raw):\n    return json.loads(raw.split('\\n\\n')[1]),{}\n",
                     "def unsafe_api(self,endpoint):\n    return {},{}\nTransport.api=unsafe_api\n")
        for override in overrides:
            with self.subTest(override=override.splitlines()[0]), self.guard_fixture() as root:
                helper = root / SCRIPT; helper.write_text(helper.read_text()+"\n"+override)
                with self.reseal(root): self.assertTrue(self.checker.validate_pr_monitor(root))


if __name__ == "__main__":
    unittest.main()
