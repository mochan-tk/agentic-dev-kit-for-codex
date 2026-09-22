"""Actual Bash entrypoints and stateful, argument-checking synthetic transports."""
import hashlib
from contextlib import contextmanager
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
REPO = "fixture/example"
BASELINE = ".github/distribution/ongoing-improvement/platform-baseline.v1.json"
HTML = b"<!doctype html><html><body>synthetic checkpoint</body></html>"


def issue(number=1, **changes):
    value = {"id": number + 1000, "number": number, "url": f"https://api.github.com/repos/{REPO}/issues/{number}",
             "html_url": f"https://github.com/{REPO}/issues/{number}",
             "repository_url": f"https://api.github.com/repos/{REPO}", "state": "open",
             "title": "PRIVATE_SENTINEL $(touch should-not-exist)", "body": "Evidence: https://github.com/fixture/example/issues/22",
             "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
             "comments": 0, "labels": [{"name": "retro:candidate"}]}
    value.update(changes)
    return value


FAKE_GH = r'''
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote
p = Path(os.environ["FIXTURE_STATE"])
s = json.loads(p.read_text())
args = sys.argv[1:]
if args == ["--version"]:
    print("gh version 2.80.0 (2026-01-01)"); sys.exit(0)
assert args[:5] == ["api", "--hostname", "github.com", "--method", args[4]], args
method, endpoint = args[4:6]
assert method in ("GET", "POST"), args
assert endpoint.startswith("repos/fixture/example/"), args
assert args[6:] == (["--input", "-"] if method == "POST" else []), args
payload = json.load(sys.stdin) if method == "POST" else None
s.setdefault("calls", []).append([method, endpoint, payload])
path, query = endpoint.split("?", 1) if "?" in endpoint else (endpoint, "")
call = len(s["calls"])
if s.get("fail_at") == call:
    p.write_text(json.dumps(s)); print("PRIVATE_SENTINEL", file=sys.stderr); sys.exit(1)
rows = s.setdefault("issues", [])
if path == "repos/fixture/example/labels/from%3Aadopter" or path == "repos/fixture/example/labels/needs%3Ahuman":
    assert method == "GET"
    if s.get("missing_label"): p.write_text(json.dumps(s)); sys.exit(1)
    result = {"name": unquote(path.rsplit("/", 1)[1])}
elif path == "repos/fixture/example/issues" and method == "GET":
    q = parse_qs(query)
    assert set(q) == {"state", "per_page", "page"} or set(q) == {"state", "per_page", "page", "labels"}, q
    assert q["per_page"] == ["50"] and q["state"][0] in ("all", "open")
    selected = [r for r in rows if q["state"] == ["all"] or r["state"] == "open"]
    if "labels" in q: selected = [r for r in selected if {x["name"] for x in r["labels"]} >= {q["labels"][0]}]
    start = (int(q["page"][0]) - 1) * 50
    result = selected[start:start + 50]
    if s.get("duplicate_pages"): result = (selected * 50)[:50]
elif path.endswith("/comments"):
    assert method == "GET"
    q = parse_qs(query); assert set(q) == {"per_page", "page"} and q["per_page"] == ["50"]
    start = (int(q["page"][0]) - 1) * 50
    result = s.get("comments", [])[start:start + 50]
elif path.endswith("/labels"):
    assert method == "POST" and payload == {"labels": ["from:adopter"]}
    row = next(r for r in rows if r["number"] == int(path.split("/")[-2]))
    row["labels"].append({"name": "from:adopter"}); result = row["labels"]
elif path == "repos/fixture/example/issues" and method == "POST":
    assert set(payload) == {"title", "body", "labels"} and payload["labels"] == ["needs:human"]
    row = dict(s["issue_template"], number=999, id=1999, title=payload["title"], body=payload["body"], labels=[{"name":"needs:human"}])
    row["url"] = "https://api.github.com/repos/fixture/example/issues/999"
    row["html_url"] = "https://github.com/fixture/example/issues/999"
    rows.append(row); result = row
else:
    assert method == "GET" and not query
    result = next(r for r in rows if r["number"] == int(path.rsplit("/", 1)[1]))
if s.get("drift_at") == call:
    result = json.loads(json.dumps(result))
    if isinstance(result, dict): result["body"] = "drift"
    else: result = []
if method == "POST" and s.get("clock_advance"):
    time.sleep(1.1)
    row["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if path.endswith("/issues"): row["created_at"] = row["updated_at"]
if s.get("touch_target_at") == call:
    target = Path(os.environ["FIXTURE_TARGET"]) / "AGENTS.md"
    target.write_bytes(target.read_bytes() + b"changed")
p.write_text(json.dumps(s))
if method == "POST" and s.get("uncertain_write"): print("PRIVATE_SENTINEL", file=sys.stderr); sys.exit(1)
if s.get("oversized_at") == call: print("x" * 2200000)
elif s.get("raw_at") == call: print(s["raw"])
else: print(json.dumps(result))
'''


class ImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ongoing_improvement_tests", ROOT / ".github/scripts/ongoing-improvement.py")
        cls.helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.helper)
        spec = importlib.util.spec_from_file_location("improvement_product_tests", ROOT / ".github/scripts/check-product.py")
        cls.checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.checker)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ongoing-improvement-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.target = self.directory / "target"
        (self.target / ".github").mkdir(parents=True)
        (self.target / "AGENTS.md").write_bytes(b"a\nb")
        (self.target / ".github/codex-instructions.md").write_bytes(b"c\n")
        self.bin = self.directory / "bin"; self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        gh = self.bin / "gh"; gh.write_text("#!" + sys.executable + "\n" + FAKE_GH); gh.chmod(0o700)
        curl = self.bin / "curl"
        curl.write_text("#!" + sys.executable + "\nimport os,sys\nfrom pathlib import Path\n"
                        "assert sys.argv[1:] == ['--disable','--silent','--show-error','--include','--proto','=https','--max-redirs','0','--max-time','15','--max-filesize','2097152','https://learn.chatgpt.com/docs/changelog']\n"
                        "sys.stdout.buffer.write(Path(os.environ['FIXTURE_HTTP']).read_bytes())\n")
        curl.chmod(0o700)
        self.state = self.directory / "state.json"
        self.http = self.directory / "http"
        self.http.write_bytes(b"HTTP/2 200\r\ncontent-type: text/html; charset=utf-8\r\n\r\n" + HTML)
        self.env = {"PATH": str(self.bin) + ":" + str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LC_ALL": "C",
                    "FIXTURE_STATE": str(self.state), "FIXTURE_HTTP": str(self.http), "FIXTURE_TARGET": str(self.target)}
        self.save(issues=[])

    def save(self, **changes):
        value = {"issues": [], "issue_template": issue(), "calls": []}; value.update(changes)
        self.state.write_text(json.dumps(value))

    def run_cli(self, mode="retro", *extra, ok=0):
        name = "retro-hygiene.sh" if mode == "retro" else "feedback-triage.sh"
        args = ["/bin/bash", str(ROOT / ".github/scripts" / name), "--repo", REPO]
        args += ["--target", str(self.target), "--period", "2026-09"] if mode == "retro" else ["--issue", "1"]
        result = subprocess.run(args + list(extra), env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(ok, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("PRIVATE_SENTINEL", result.stdout + result.stderr)
        self.assertNotIn(str(self.directory), result.stdout + result.stderr)
        return result

    def calls(self):
        return json.loads(self.state.read_text())["calls"]

    def test_empty_and_budget_final_non_newline(self):
        out = json.loads(self.run_cli().stdout)
        self.assertEqual("observed-empty", out["ledger"])
        self.assertEqual([2, 1], [r["lines"] for r in out["budget"]])
        self.assertEqual({"GET"}, {c[0] for c in self.calls()})

    def test_references_deduplicated_discussion_not_occurrence(self):
        comments = [{"id": 10, "issue_url": "https://api.github.com/repos/fixture/example/issues/1",
                     "html_url": "https://github.com/fixture/example/issues/1#issuecomment-10",
                     "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z",
                     "body": "Occurrence: https://github.com/fixture/example/issues/22\nPRIVATE_SENTINEL"},
                    {"id": 11, "issue_url": "https://api.github.com/repos/fixture/example/issues/1",
                     "html_url": "https://github.com/fixture/example/issues/1#issuecomment-11",
                     "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z",
                     "body": "> Occurrence: https://github.com/fixture/example/issues/23"}]
        self.save(issues=[issue(comments=2)], comments=comments)
        row = json.loads(self.run_cli().stdout)["candidates"][0]
        self.assertEqual(1, row["unique_evidence_references"])
        self.assertEqual("unverified", row["independent_incidents"])
        self.assertEqual("human-review", row["status"])

    def test_late_failure_no_partial_success(self):
        self.save(issues=[issue()], fail_at=4)
        result = self.run_cli(ok=2)
        self.assertEqual("", result.stdout)

    def test_existing_reporter_and_classification(self):
        draft = subprocess.run(["/bin/bash", str(ROOT / ".github/scripts/report-installer-failure.sh"), "--draft"],
                               env=self.env, text=True, capture_output=True, timeout=10)
        body = draft.stdout[draft.stdout.index("<!-- adopter-feedback:v1 -->"):].rstrip()
        self.save(issues=[issue(body=body, title="ordinary")])
        self.assertEqual("matched", json.loads(self.run_cli("feedback").stdout)["classification"])
        self.assertTrue(all(c[0] == "GET" for c in self.calls()))

    def test_feedback_explicit_write_and_verified_noop(self):
        self.save(issues=[issue(body="<!-- adopter-feedback:v1 -->\n$(touch should-not-exist)")])
        self.assertEqual("confirmed", json.loads(self.run_cli("feedback", "--apply-label").stdout)["publication"])
        self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))
        self.assertEqual("verified-noop", json.loads(self.run_cli("feedback", "--apply-label").stdout)["publication"])
        self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))

    def test_uncertain_write_never_retries(self):
        self.save(issues=[issue(body="<!-- adopter-feedback:v1 -->")], uncertain_write=True)
        result = self.run_cli("feedback", "--apply-label", ok=3)
        self.assertEqual("", result.stdout); self.assertIn("unconfirmed", result.stderr)
        self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))

    def test_monthly_publication_verified_noop(self):
        self.assertEqual("confirmed", json.loads(self.run_cli("retro", "--publish").stdout)["publication"])
        self.assertEqual("verified-noop", json.loads(self.run_cli("retro", "--publish").stdout)["publication"])
        self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))

    def test_plain_and_markdown_filing_and_multiline_occurrences(self):
        for body in ("https://github.com/fixture/example/pull/22#discussion_r123\ncontext",
                     "[review](https://github.com/fixture/example/actions/runs/23)\ncontext"):
            with self.subTest(body=body):
                self.save(issues=[issue(body=body)])
                self.assertEqual(1, json.loads(self.run_cli().stdout)["candidates"][0]["unique_evidence_references"])
        for body in ("Occurrence:\nhttps://github.com/fixture/example/issues/22",
                     "Occurrence: same problem\n[review](https://github.com/fixture/example/pull/22#discussion_r123)"):
            self.assertEqual(1, len(self.helper.evidence(body, occurrence=True)))

    def test_distinct_links_human_review_only(self):
        self.save(issues=[issue(body="https://github.com/fixture/example/issues/22\nhttps://github.com/fixture/example/pull/23")])
        row = json.loads(self.run_cli().stdout)["candidates"][0]
        self.assertEqual(2, row["unique_evidence_references"])
        self.assertEqual("unverified", row["independent_incidents"])
        self.assertEqual("human-review", row["status"])
        self.assertGreater(row["age_days"], row["inactivity_days"])

    def test_budget_boundaries_and_preserves_git_index_and_bytes(self):
        git_env = dict(self.env, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "init", "-q", str(self.target)], env=git_env, check=True)
        (self.target / "unrelated").write_bytes(b"staged")
        subprocess.run(["git", "-C", str(self.target), "add", "unrelated"], env=git_env, check=True)
        (self.target / "unrelated").write_bytes(b"unstaged")
        (self.target / "AGENTS.md").write_bytes(b"a\n" * 150)
        (self.target / ".github/codex-instructions.md").write_bytes(b"b\n" * 150 + b"c")
        before = {str(p.relative_to(self.target)): p.read_bytes() for p in self.target.rglob("*") if p.is_file()}
        rows = json.loads(self.run_cli().stdout)["budget"]
        self.assertEqual(["within-target", "over-target"], [r["status"] for r in rows])
        self.run_cli("retro", "--publish")
        self.assertEqual(before, {str(p.relative_to(self.target)): p.read_bytes() for p in self.target.rglob("*") if p.is_file()})

    def test_budget_unsafe_missing_special_large_or_changed_refuses(self):
        path = self.target / "AGENTS.md"
        for kind in ("missing", "symlink", "fifo", "large"):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == "symlink": path.symlink_to(self.target / ".github/codex-instructions.md")
                elif kind == "fifo": os.mkfifo(path)
                elif kind == "large": path.write_bytes(b"x" * (262144 + 1))
                self.run_cli(ok=2)
                if path.exists() or path.is_symlink(): path.unlink()
                path.write_bytes(b"a\n")
        self.save(issues=[], touch_target_at=2)
        self.assertEqual("", self.run_cli(ok=2).stdout)

    def test_malformed_candidate_shapes_identity_and_timestamps_refuse(self):
        cases = ({"id": True}, {"number": 0}, {"comments": -1}, {"comments": 201},
                 {"body": {}}, {"body": "no evidence"}, {"body": "> https://github.com/fixture/example/issues/22"},
                 {"body": "https://private.invalid/secret"}, {"title": "x" * 1025},
                 {"created_at": None}, {"updated_at": "1900-01-01T00:00:00Z"},
                 {"updated_at": "2999-01-01T00:00:00Z"}, {"url": "https://api.github.com/repos/other/repo/issues/1"},
                 {"labels": [{"name": "retro:candidate"}, {"name": "retro:candidate"}]})
        for changes in cases:
            with self.subTest(changes=list(changes)):
                self.save(issues=[issue(**changes)])
                self.assertEqual("", self.run_cli(ok=2).stdout)

    def test_duplicate_malformed_oversized_and_drifting_api_no_partial_report(self):
        for changes in ({"issues": [issue(), issue()]}, {"issues": [issue()], "duplicate_pages": True},
                        {"issues": [issue()], "oversized_at": 2}, {"raw_at": 1, "raw": "{}"},
                        {"raw_at": 1, "raw": '[{"id":1,"id":2}]'}, {"issues": [issue()], "drift_at": 4},
                        {"issues": [issue(comments=1)]}):
            with self.subTest(changes=list(changes)):
                self.save(**changes)
                self.assertEqual("", self.run_cli(ok=2).stdout)

    def test_complete_issue_pages_and_late_page_failure(self):
        # Unrelated body-null Issues and realistic PRs are valid inventory data.
        rows = [issue(n, labels=[], body=None) for n in range(1, 52)]
        rows[1].update(html_url="https://github.com/fixture/example/pull/2",
                       pull_request={"url": "https://api.github.com/repos/fixture/example/pulls/2"})
        self.save(issues=rows)
        self.run_cli("retro", "--publish")
        self.assertTrue(any("state=all&per_page=50&page=2" in call[1] for call in self.calls()))
        self.save(issues=rows, fail_at=4)
        self.assertEqual("", self.run_cli("retro", "--publish", ok=2).stdout)
        self.assertTrue(all(c[0] == "GET" for c in self.calls()))

    def test_complete_comment_pages_and_duplicate_or_identity_drift(self):
        comments = [{"id": n, "issue_url": "https://api.github.com/repos/fixture/example/issues/1",
                     "html_url": f"https://github.com/fixture/example/issues/1#issuecomment-{n}",
                     "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z",
                     "body": "ordinary discussion PRIVATE_SENTINEL"} for n in range(1, 52)]
        self.save(issues=[issue(comments=51)], comments=comments)
        self.run_cli()
        self.assertTrue(any("comments?per_page=50&page=2" in c[1] for c in self.calls()))
        for change in ("duplicate", "identity", "late-page"):
            values = json.loads(json.dumps(comments))
            if change == "duplicate": values[-1] = values[0]
            if change == "identity": values[-1]["issue_url"] = "https://api.github.com/repos/other/repo/issues/1"
            self.save(issues=[issue(comments=51)], comments=values, **({"fail_at": 4} if change == "late-page" else {}))
            self.run_cli(ok=2)

    def test_platform_same_changed_and_no_baseline_mutation(self):
        baseline = self.directory / "baseline.json"
        value = json.loads((ROOT / BASELINE).read_bytes())
        baseline.write_text(json.dumps(value)); before = baseline.read_bytes()
        self.assertEqual("changed", json.loads(self.run_cli("retro", "--platform", "--baseline", str(baseline)).stdout)["platform"]["status"])
        self.assertEqual(before, baseline.read_bytes())
        value["sha256"] = hashlib.sha256(HTML).hexdigest(); baseline.write_text(json.dumps(value))
        self.assertEqual("unchanged", json.loads(self.run_cli("retro", "--platform", "--baseline", str(baseline)).stdout)["platform"]["status"])

    def test_platform_unavailable_wrong_type_redirect_large_unknown(self):
        for raw in (b"HTTP/2 503\r\ncontent-type: text/html\r\n\r\n" + HTML,
                    b"HTTP/2 302\r\nlocation: https://evil.invalid/\r\n\r\n" + HTML,
                    b"HTTP/2 200\r\ncontent-type: application/json\r\n\r\n{}",
                    b"HTTP/2 200\r\ncontent-type: text/html\r\n\r\nnot html PRIVATE_SENTINEL",
                    b"HTTP/2 200\r\ncontent-type: text/html\r\ncontent-length: 1\r\n\r\n" + HTML,
                    b"HTTP/2 200\r\ncontent-type: text/html\r\n\r\n" + b"x" * 2200000):
            self.http.write_bytes(raw)
            result = self.run_cli("retro", "--platform", ok=2)
            self.assertEqual("", result.stdout); self.assertIn("platform-unknown", result.stderr)
        self.http.unlink()
        self.run_cli("retro", "--platform", ok=2)

    def test_baseline_closed_validation_before_network(self):
        original = json.loads((ROOT / BASELINE).read_bytes())
        baseline = self.directory / "baseline.json"
        for key, value in (("url", "http://learn.chatgpt.com/docs/changelog"),
                           ("url", "https://user:secret@learn.chatgpt.com/docs/changelog"),
                           ("url", "https://evil.invalid/docs/changelog"), ("kind", "version"),
                           ("sha256", "unknown"), ("observed_on", "2026-02-30"), ("extra", True)):
            record = dict(original); record[key] = value; baseline.write_text(json.dumps(record))
            self.run_cli("retro", "--platform", "--baseline", str(baseline), ok=2)
            self.assertEqual([], self.calls())
        baseline.write_text('{"schema":"official-checkpoint/v1","schema":"official-checkpoint/v1"}')
        self.run_cli("retro", "--platform", "--baseline", str(baseline), ok=2)

    def test_receiver_marker_precedence_and_malformed_inputs(self):
        cases = (("ordinary", "> <!-- adopter-feedback:v1 -->", "not-matched"),
                 ("ordinary", "context\n<!-- adopter-feedback:v1 -->", "not-matched"),
                 ("[adopter-feedback] form", "<!-- adopter-feedback:v2 -->", "not-matched"),
                 ("[adopter-feedback] form", "> <!-- adopter-feedback:v1 -->", "not-matched"),
                 ("[adopter-feedback]suffix", "ordinary", "not-matched"),
                 ("[adopter-feedback] form", "ordinary", "matched"),
                 ("ordinary", "<!-- adopter-feedback:v1 -->evil", "not-matched"))
        for title, body, expected in cases:
            self.save(issues=[issue(title=title, body=body)])
            self.assertEqual(expected, json.loads(self.run_cli("feedback").stdout)["classification"])
        self.save(issues=[issue(body=["bad"])])
        self.run_cli("feedback", ok=2)

    def test_missing_labels_prewrite_drift_and_noop_readback_failure(self):
        for changes in ({"missing_label": True}, {"drift_at": 3}, {"fail_at": 3}):
            self.save(issues=[issue(body=self.helper.MARKER)], **changes)
            self.run_cli("feedback", "--apply-label", ok=2)
            self.assertTrue(all(c[0] == "GET" for c in self.calls()))
        self.save(issues=[issue(body=self.helper.MARKER, labels=[{"name": "from:adopter"}])], drift_at=3)
        self.run_cli("feedback", "--apply-label", ok=2)

    def test_write_response_and_readback_uncertainty_no_retry(self):
        for changes in ({"fail_at": 5}, {"drift_at": 5}, {"raw_at": 4, "raw": "[]"}):
            self.save(issues=[issue(body=self.helper.MARKER)], **changes)
            self.run_cli("feedback", "--apply-label", ok=3)
            self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))
        self.save(uncertain_write=True)
        self.run_cli("retro", "--publish", ok=3)
        self.assertEqual(1, sum(c[0] == "POST" for c in self.calls()))

    def test_clock_advance_after_real_fake_writes(self):
        self.save(issues=[issue(body=self.helper.MARKER)], clock_advance=True)
        self.assertEqual("confirmed", json.loads(self.run_cli("feedback", "--apply-label").stdout)["publication"])
        self.save(clock_advance=True)
        self.assertEqual("confirmed", json.loads(self.run_cli("retro", "--publish").stdout)["publication"])

    def test_monthly_conflicting_content_target_schema_and_period(self):
        self.run_cli("retro", "--publish")
        saved = json.loads(self.state.read_text())
        for old, new in (("ongoing-improvement:v1", "ongoing-improvement:v2"),
                         ("https://github.com/fixture/example", "https://github.com/other/repo"),
                         ('"observed-empty"', '"malformed"'), ('"2026-09"', '"2026-08"')):
            changed = json.loads(json.dumps(saved)); changed["calls"] = []
            changed["issues"][0]["body"] = changed["issues"][0]["body"].replace(old, new)
            self.state.write_text(json.dumps(changed))
            self.run_cli("retro", "--publish", ok=2)
            self.assertTrue(all(c[0] == "GET" for c in self.calls()))

    def test_invalid_cli_never_leaks_raw_arguments(self):
        self.run_cli("retro", "--unknown-PRIVATE_SENTINEL", ok=2)
        self.run_cli("retro", "--repo", "PRIVATE_SENTINEL", ok=2)

    def test_fenced_examples_do_not_supply_filing_or_occurrence_evidence(self):
        reference = "https://github.com/fixture/example/issues/22"
        for body in ("```text\n~~~\n" + reference + "\n~~~\n```",
                     "````text\n```\n" + reference + "\n```\n````",
                     "~~~text\n```\n" + reference + "\n```\n~~~"):
            self.save(issues=[issue(body=body)])
            self.run_cli(ok=2)
            with self.assertRaises(self.helper.Fault): self.helper.evidence("Occurrence:\n" + body, occurrence=True)

    def test_renamed_compact_or_malformed_monthly_report_never_creates_duplicate(self):
        self.run_cli("retro", "--publish")
        saved = json.loads(self.state.read_text())
        for mode in ("compact", "invalid", "duplicate-key", "unknown"):
            value = json.loads(json.dumps(saved)); value["calls"] = []
            row = value["issues"][0]; row["title"] = "renamed"
            body = json.loads(row["body"].split("\n", 1)[1])
            row["body"] = self.helper.REPORT_MARKER + "\n" + json.dumps(body, separators=(",", ":"))
            if mode == "invalid": row["body"] = self.helper.REPORT_MARKER + "\n{bad}"
            if mode == "duplicate-key": row["body"] = self.helper.REPORT_MARKER + '\n{"period":"2026-09","period":"2026-08"}'
            if mode == "unknown": row["body"] = row["body"].replace("ongoing-improvement:v1", "ongoing-improvement:v2")
            self.state.write_text(json.dumps(value))
            self.run_cli("retro", "--publish", ok=2)
            self.assertTrue(all(c[0] == "GET" for c in self.calls()))

    def test_nonstandard_json_and_resource_caps_fail_closed(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            self.save(raw_at=1, raw=value)
            self.run_cli(ok=2)
        transport = self.helper.Transport(); transport.calls = self.helper.MAX_CALLS
        with self.assertRaises(self.helper.Fault): transport.command([sys.executable, "-c", "print('unused')"])
        transport = self.helper.Transport(); transport.total = self.helper.MAX_TOTAL_BYTES
        with self.assertRaises(self.helper.Fault): transport.command([sys.executable, "-c", "print('overflow')"])
        ledger = self.helper.Ledger(None, REPO, None)
        class EndlessPages:
            def api(self, endpoint):
                page = int(endpoint.rsplit("=", 1)[1])
                return [{"id": (page - 1) * 50 + n} for n in range(1, 51)]
        ledger.transport = EndlessPages()
        with self.assertRaises(self.helper.Fault): ledger.pages("repos/fixture/example/issues", lambda v: v, 500)
        with self.assertRaises(self.helper.Fault): ledger.pages("repos/fixture/example/issues", lambda v: v, 1000)

    def test_exited_parent_live_stdout_child_is_terminated(self):
        pid_file = self.directory / "child.pid"
        program = ("import subprocess,sys\nfrom pathlib import Path\n"
                   "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
                   "Path(sys.argv[1]).write_text(str(p.pid))\n")
        transport = self.helper.Transport(); transport.deadline = time.monotonic() + 0.5
        with self.assertRaises(self.helper.Fault): transport.command([sys.executable, "-c", program, str(pid_file)])
        child = int(pid_file.read_text())
        try:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True, timeout=3).stdout.strip()
            self.assertTrue(not state or state.startswith("Z"), "transport left running descendant")
        finally:
            try: os.kill(child, 9)
            except ProcessLookupError: pass

    @contextmanager
    def guard_fixture(self):
        # Only the 13 small companion records; every iteration cleans promptly.
        with tempfile.TemporaryDirectory(prefix="improvement-guard-") as temporary:
            root = Path(temporary)
            for name in (*self.checker.IMPROVEMENT_TARGETS, self.checker.IMPROVEMENT_RECORD):
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            yield root

    def reseal(self, root):
        path = root / self.checker.IMPROVEMENT_RECORD
        record = json.loads(path.read_bytes())
        for row in record["target_files"]:
            row["sha256"] = hashlib.sha256((root / row["path"]).read_bytes()).hexdigest()
        path.write_text(json.dumps(record))
        return patch.object(self.checker, "IMPROVEMENT_RECORD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())

    def test_product_requires_every_companion_path_and_nonexecutable_mode(self):
        self.assertEqual([], self.checker.validate_ongoing_improvement(ROOT))
        for name in (*self.checker.IMPROVEMENT_TARGETS, self.checker.IMPROVEMENT_RECORD):
            with self.subTest(name=name), self.guard_fixture() as root:
                (root / name).unlink()
                self.assertTrue(self.checker.validate_ongoing_improvement(root))
        with self.guard_fixture() as root:
            (root / ".github/scripts/retro-hygiene.sh").chmod(0o755)
            self.assertTrue(self.checker.validate_ongoing_improvement(root))

    def test_resealed_source_scope_inventory_and_template_mutations_refuse(self):
        for mode in ("source", "blob", "scope", "inventory", "mode", "extra"):
            with self.subTest(mode=mode), self.guard_fixture() as root:
                path = root / self.checker.IMPROVEMENT_RECORD; record = json.loads(path.read_bytes())
                if mode == "source": record["source_commit"] = "0" * 40
                elif mode == "blob": record["source_files"][".github/scripts/retro-hygiene.sh"] = "0" * 40
                elif mode == "scope": record["scope"] = "activated"
                elif mode == "inventory": record["target_files"].pop()
                elif mode == "mode": record["target_files"][0]["mode"] = "100755"
                else: record["waivers"] = []
                path.write_text(json.dumps(record))
                with patch.object(self.checker, "IMPROVEMENT_RECORD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()):
                    self.assertTrue(self.checker.validate_ongoing_improvement(root))
        for filename in ("retro-hygiene.yml", "adopter-feedback.yml"):
            with self.guard_fixture() as root:
                path = root / ".github/distribution/ongoing-improvement" / filename
                path.write_text(path.read_text().replace("persist-credentials: false", "persist-credentials: true"))
                with self.reseal(root): self.assertTrue(self.checker.validate_ongoing_improvement(root))

    def test_resealed_unsafe_semantic_guards_cannot_waive_product_gate(self):
        overrides = (
            "_original = classification\ndef classification(title, body):\n    return 'matched' if 'v2' in body else _original(title, body)\n",
            "_original = baseline_record\ndef baseline_record(data):\n    value=json.loads(data)\n    return value if value.get('url') == 'https://evil.invalid/' else _original(data)\n",
            "_original = checkpoint_response\ndef checkpoint_response(raw, expected):\n    return {'status':'unchanged'} if b'302' in raw else _original(raw, expected)\n",
            "def parse_json(data):\n    return json.loads(data)\n",
            "_original = evidence\ndef evidence(body, occurrence=False):\n    return {'quoted'} if '~~~' in body else _original(body, occurrence)\n",
            "_original = report_period\ndef report_period(body):\n    return None if '\"period\":\"' in body else _original(body)\n",
            "_original = Ledger.pages\ndef unsafe_pages(self, endpoint, validator, maximum):\n    return [{'id':1}]\nLedger.pages=unsafe_pages\n",
            "_original = feedback\ndef feedback(ledger, number, apply):\n    return {'publication':'verified-noop'} if apply else _original(ledger, number, apply)\n",
        )
        for override in overrides:
            with self.subTest(override=override.splitlines()[0]), self.guard_fixture() as root:
                helper = root / ".github/scripts/ongoing-improvement.py"
                helper.write_text(helper.read_text() + "\n" + override)
                with self.reseal(root): self.assertTrue(self.checker.validate_ongoing_improvement(root))

    def test_workflow_templates_are_inert_pinned_and_not_pr_controlled(self):
        for filename in ("retro-hygiene.yml", "adopter-feedback.yml"):
            text = (ROOT / ".github/distribution/ongoing-improvement" / filename).read_text()
            self.assertFalse((ROOT / ".github/workflows" / filename).exists())
            self.assertIn("permissions: {}", text); self.assertIn("persist-credentials: false", text)
            self.assertNotIn("pull_request", text); self.assertNotIn("schedule:", text)
            self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", text)
            self.assertIn("vars.ONGOING_IMPROVEMENT_KIT_REVISION", text)
        retro = (ROOT / ".github/distribution/ongoing-improvement/retro-hygiene.yml").read_text()
        self.assertIn("&& !inputs.publish", retro); self.assertIn("&& inputs.publish", retro)
        self.assertIn("issues: read", retro); self.assertIn("issues: write", retro)
        docs = (ROOT / "docs/distribution/ongoing-improvement.md").read_text()
        self.assertIn("--repo OWNER/REPOSITORY --target /absolute/target", docs)
        self.assertIn("--repo OWNER/REPOSITORY --issue 123", docs)


if __name__ == "__main__":
    unittest.main()
