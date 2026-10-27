"""Run the installed roadmap probe/helper with real tools and synthetic GitHub.

These tests do not prove a live credential's permissions or model compliance.
"""

import json
import copy
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

import test_installer


FAKE_GH = r'''import json, os, sys
from pathlib import Path

a = sys.argv[1:]
state_path = Path(os.environ["ROADMAP_TEST_STATE"])
s = json.loads(state_path.read_text())
with open(os.environ["ROADMAP_TEST_CALLS"], "a") as log:
    log.write(json.dumps(a) + "\n")

def value(flag):
    return a[a.index(flag) + 1]

def save():
    state_path.write_text(json.dumps(s))

def mutation():
    if not s.get("write_consent") or not s.get("write_access"):
        sys.exit("synthetic fixture refused unauthorized mutation")

if a[:2] == ["project", "list"]:
    if s.get("error"):
        print(s["error"], file=sys.stderr)
        sys.exit(1)
    if "raw" in s:
        print(s["raw"])
    else:
        boards = s["projects"]
        if "--closed" not in a:
            boards = [p for p in boards if not p["closed"]]
        print(json.dumps({"projects": boards, "totalCount": s.get("total", len(boards))}))
elif a[:2] == ["api", "user"]:
    print("fixture-owner")
elif a[:2] == ["project", "create"]:
    mutation()
    s["projects"].append({"number": 7, "title": value("--title"), "closed": False})
    save()
    print(7)
elif a[:2] == ["project", "field-list"]:
    print(json.dumps({"fields": s["fields"]}))
elif a[:2] == ["project", "field-create"]:
    mutation()
    s["fields"].append({"name": value("--name"), "dataType": value("--data-type")})
    save()
elif a[:2] == ["project", "view"]:
    print("PVT_fixture" if value("--jq") == ".id" else "https://github.com/users/fixture-owner/projects/7")
elif a[:2] == ["project", "link"]:
    mutation()
    s["linked_repo"] = value("--repo")
    save()
elif a[:2] == ["api", "graphql"]:
    query = next(x for x in a if x.startswith("query="))
    if "query ProjectReadback" in query:
        kind = "items" if "ProjectReadbackItems" in query else "values"
        cursor = next((x[6:] for x in a if x.startswith("after=")), "")
        response = s["readback"][kind][cursor]
        if isinstance(response, dict) and "transport_error" in response:
            print("synthetic transport failure", file=sys.stderr)
            sys.exit(1)
        print(response if isinstance(response, str) else json.dumps(response))
    elif "createProjectV2View" in query:
        mutation()
        s["views"].append(next(x[2:] for x in a if x.startswith("n=")))
        save()
    elif "views(first:" in query:
        print("\n".join(s["views"]))
    else:
        sys.exit("unexpected synthetic GraphQL operation")
else:
    sys.exit("unexpected synthetic gh operation: " + repr(a))
'''


def readback_fixture():
    issue = dict(id="I_target", number=23, url="https://github.com/fixture-owner/sample/issues/23",
                 repository={"nameWithOwner": "fixture-owner/sample"}, __typename="Issue")
    project = dict(id="PVT_fixture", number=7, url="https://github.com/users/fixture-owner/projects/7",
                   owner={"__typename": "User", "login": "fixture-owner"}, __typename="ProjectV2")
    item = dict(id="PVTI_target", content=issue, updatedAt="2026-10-27T00:00:00Z")
    def connection(nodes):
        return dict(nodes=nodes, totalCount=len(nodes), pageInfo=dict(hasNextPage=False, endCursor=None))
    fields = [dict(__typename="ProjectV2ItemFieldSingleSelectValue", name="Task",
                   field=dict(id="F_kind", name="Kind", dataType="SINGLE_SELECT")),
              dict(__typename="ProjectV2ItemFieldDateValue", date="2026-10-27",
                   field=dict(id="F_start", name="Start date", dataType="DATE")),
              dict(__typename="ProjectV2ItemFieldDateValue", date="2026-11-02",
                   field=dict(id="F_target", name="Target date", dataType="DATE"))]
    fixture = dict(items={"": {"data": dict(repository=dict(nameWithOwner="fixture-owner/sample", issue=issue),
                                         node=dict(project, items=connection([item]))) }},
                values={"": {"data": {"node": dict(item, __typename="ProjectV2Item",
                                                    project={"id": "PVT_fixture"}, fieldValues=connection(fields))}}})
    # Raw transport pages have independent objects; avoid fixture aliasing
    # that would accidentally mutate both the original and later readback.
    return json.loads(json.dumps(fixture))


class RoadmapPreflightTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixture; do not import/subclass its TestCase into discovery.
        self.installer = test_installer.InstallerTests()
        self.installer.setUp()
        self.addCleanup(self.installer.doCleanups)
        result = self.installer.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.target = self.installer.target
        self.work = self.installer.base
        self.state_path = self.work / "synthetic-state.json"
        self.calls_path = self.work / "synthetic-calls.jsonl"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text("#!" + sys.executable + "\n" + FAKE_GH)
        gh.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        ROADMAP_TEST_STATE=str(self.state_path), ROADMAP_TEST_CALLS=str(self.calls_path),
                        ROADMAP_OWNER="fixture-owner", ROADMAP_REPO_NAME="sample", ROADMAP_CHOICE="pending")
        self.set_state()

    def set_state(self, **changes):
        state = dict(projects=[], fields=[], views=[], write_access=False, write_consent=False)
        state.update(changes)
        self.state_path.write_text(json.dumps(state))
        self.calls_path.write_text("")

    def calls(self):
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

    def readback(self, fixture, code=0, command=None):
        self.set_state(readback=fixture)
        before = self.installer.snapshot(self.target)
        state_before = self.state_path.read_bytes()
        command = command or ["bash", ".github/scripts/setup-project.sh", "readback",
                              "--project", "7", "--issue", "23", "--owner", "fixture-owner",
                              "-R", "fixture-owner/sample"]
        result = subprocess.run(command, cwd=self.target,
                                env=dict(self.env, ROADMAP_REPOSITORY="fixture-owner/sample",
                                         ROADMAP_PROJECT="7", ROADMAP_ISSUE="23"),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, self.installer.snapshot(self.target))
        self.assertEqual(state_before, self.state_path.read_bytes(), "readback mutated the board")
        for call in self.calls():
            self.assertIn(call[:2], (["api", "user"], ["project", "view"], ["api", "graphql"]))
            if call[:2] == ["api", "graphql"]:
                query = next(x for x in call if x.startswith("query="))
                self.assertTrue(query.startswith("query=query ProjectReadback"), query)
                self.assertNotIn("mutation", query)
        return result

    def test_documented_installed_readback_observes_typed_values_without_writes(self):
        skill = self.target / ".agents/skills/plan-management/SKILL.md"
        match = re.search(r"<!-- BEGIN roadmap-field-readback -->\n```bash\n(.*?)\n```\n"
                          r"<!-- END roadmap-field-readback -->", skill.read_text(), re.S)
        self.assertIsNotNone(match, "installed readback command is missing")
        result = json.loads(self.readback(readback_fixture(), command=["bash", "-c", match.group(1)]).stdout)
        self.assertEqual("project-field-readback/v1", result["schema"])
        self.assertEqual("observed", result["state"])
        self.assertEqual("fixture-owner/sample", result["repository"])
        self.assertEqual(dict(id="PVT_fixture", number=7, owner="fixture-owner",
                              url="https://github.com/users/fixture-owner/projects/7"), result["project"])
        self.assertEqual(dict(id="I_target", number=23,
                              url="https://github.com/fixture-owner/sample/issues/23"), result["issue"])
        self.assertEqual("PVTI_target", result["item_id"])
        self.assertEqual("SINGLE_SELECT", result["fields"]["Kind"]["type"])
        self.assertEqual("DATE", result["fields"]["Start date"]["type"])
        self.assertEqual("DATE", result["fields"]["Target date"]["type"])
        self.assertEqual("Task", result["fields"]["Kind"]["value"])
        self.assertEqual("2026-10-27", result["fields"]["Start date"]["value"])
        self.assertEqual("2026-11-02", result["fields"]["Target date"]["value"])
        self.assertEqual([], result["missing"])

    def test_readback_completes_both_connections_and_skips_known_non_issues(self):
        f = readback_fixture()
        first = f["items"][""]
        target = first["data"]["node"]["items"]["nodes"][0]
        first["data"]["node"]["items"] = dict(nodes=[dict(id="PVTI_draft", content=dict(
            __typename="DraftIssue", id="D_one"), updatedAt="2026-10-27T00:00:00Z"),
            dict(id="PVTI_pr", content=dict(__typename="PullRequest", id="PR_one"),
                 updatedAt="2026-10-27T00:00:00Z")], totalCount=3,
            pageInfo=dict(hasNextPage=True, endCursor="item-next"))
        second = copy.deepcopy(first)
        second["data"]["node"]["items"].update(nodes=[target], pageInfo=dict(hasNextPage=False, endCursor=None))
        f["items"]["item-next"] = second
        values = f["values"][""]["data"]["node"]["fieldValues"]
        remaining = values["nodes"][1:]
        values.update(nodes=values["nodes"][:1], pageInfo=dict(hasNextPage=True, endCursor="field-next"))
        second_values = copy.deepcopy(f["values"][""])
        second_values["data"]["node"]["fieldValues"].update(nodes=remaining, pageInfo=dict(hasNextPage=False, endCursor=None))
        f["values"]["field-next"] = second_values
        self.assertEqual("observed", json.loads(self.readback(f).stdout)["state"])
        self.assertEqual(4, sum(call[:2] == ["api", "graphql"] for call in self.calls()))

    def test_readback_reports_missing_values_and_missing_item_as_non_success(self):
        f = readback_fixture()
        fields = f["values"][""]["data"]["node"]["fieldValues"]
        fields.update(nodes=fields["nodes"][:1], totalCount=1)
        result = json.loads(self.readback(f, 1).stdout)
        self.assertEqual("missing", result["state"])
        self.assertEqual(["Start date", "Target date"], result["missing"])
        self.assertIsNone(result["fields"]["Start date"])
        f = readback_fixture()
        f["items"][""]["data"]["node"]["items"].update(nodes=[], totalCount=0)
        result = json.loads(self.readback(f, 1).stdout)
        self.assertIsNone(result["item_id"])
        self.assertIn("item", result["missing"])

    def test_readback_dates_require_real_calendar_days_including_leap_years(self):
        for day in ("2026-02-31", "2026-04-31", "2025-02-29", "1900-02-29", "0000-01-01"):
            with self.subTest(invalid=day):
                f = readback_fixture()
                f["values"][""]["data"]["node"]["fieldValues"]["nodes"][1]["date"] = day
                self.assertEqual("", self.readback(f, 3).stdout)
        for day in ("2024-02-29", "2000-02-29", "2026-02-28", "2026-04-30"):
            with self.subTest(valid=day):
                f = readback_fixture()
                f["values"][""]["data"]["node"]["fieldValues"]["nodes"][1]["date"] = day
                result = json.loads(self.readback(f).stdout)
                self.assertEqual(day, result["fields"]["Start date"]["value"])

    def test_readback_refuses_identity_ambiguity_and_partial_errors(self):
        for fault in ("wrong-project", "wrong-owner", "wrong-repo", "wrong-issue", "wrong-type", "null-content",
                      "duplicate-item", "duplicate-issue", "error", "null-data", "truncated-count",
                      "missing-pageinfo", "null-hasnext", "loop-cursor", "oversized"):
            with self.subTest(fault=fault):
                f = readback_fixture()
                response = f["items"][""]
                node = response["data"]["node"]
                conn = node["items"]
                item = conn["nodes"][0]
                if fault == "wrong-project": node["number"] = 8
                elif fault == "wrong-owner": node["owner"]["login"] = "other"
                elif fault == "wrong-repo": response["data"]["repository"]["nameWithOwner"] = "other/sample"
                elif fault == "wrong-issue": item["content"]["number"] = 24
                elif fault == "wrong-type": item["content"]["__typename"] = "Redacted"
                elif fault == "null-content": item["content"] = None
                elif fault in ("duplicate-item", "duplicate-issue"):
                    extra = copy.deepcopy(item)
                    if fault == "duplicate-issue": extra["id"] = "PVTI_duplicate"
                    conn["nodes"].append(extra)
                    conn["totalCount"] = 2
                elif fault == "error": response["errors"] = [{"message": "synthetic private error"}]
                elif fault == "null-data": response["data"] = None
                elif fault == "truncated-count": conn["totalCount"] = 2
                elif fault == "missing-pageinfo": del conn["pageInfo"]
                elif fault == "null-hasnext": conn["pageInfo"]["hasNextPage"] = None
                elif fault == "loop-cursor":
                    conn.update(totalCount=2, pageInfo=dict(hasNextPage=True, endCursor="repeat"))
                    f["items"]["repeat"] = copy.deepcopy(response)
                elif fault == "oversized": f["items"][""] = " " * 1048577
                self.assertEqual("", self.readback(f, 3).stdout)

    def test_readback_refuses_bad_field_pages_types_values_and_anchor_drift(self):
        for fault in ("wrong-item", "wrong-project", "wrong-issue", "changed-at", "duplicate-field", "duplicate-name",
                      "wrong-type", "wrong-data-type", "null-value", "invalid-date", "null-field",
                      "truncated-count", "cursor-missing", "transport", "malformed", "two-documents"):
            with self.subTest(fault=fault):
                f = readback_fixture()
                response = f["values"][""]
                node = response["data"]["node"]
                conn = node["fieldValues"]
                field = conn["nodes"][0]
                if fault == "wrong-item": node["id"] = "PVTI_other"
                elif fault == "wrong-project": node["project"]["id"] = "PVT_other"
                elif fault == "wrong-issue": node["content"]["id"] = "I_other"
                elif fault == "changed-at": node["updatedAt"] = "2026-10-28T00:00:00Z"
                elif fault in ("duplicate-field", "duplicate-name"):
                    extra = copy.deepcopy(field)
                    if fault == "duplicate-name": extra["field"]["id"] = "F_duplicate"
                    conn["nodes"].append(extra)
                    conn["totalCount"] = 4
                elif fault == "wrong-type": field["__typename"] = "ProjectV2ItemFieldTextValue"
                elif fault == "wrong-data-type": field["field"]["dataType"] = "TEXT"
                elif fault == "null-value": field["name"] = None
                elif fault == "invalid-date": conn["nodes"][1]["date"] = "2026-99-99"
                elif fault == "null-field": field["field"] = None
                elif fault == "truncated-count": conn["totalCount"] = 4
                elif fault == "cursor-missing": conn["pageInfo"].update(hasNextPage=True)
                elif fault == "transport": f["values"][""] = dict(transport_error=True)
                elif fault == "malformed": f["values"][""] = '{"data":'
                elif fault == "two-documents": f["values"][""] = json.dumps(response) + "\n{}"
                self.assertEqual("", self.readback(f, 3).stdout)

    def probe(self, choice="pending"):
        skill = self.target / ".agents/skills/plan-management/SKILL.md"
        match = re.search(r"<!-- BEGIN roadmap-access-preflight -->\n```bash\n(.*?)\n```\n"
                          r"<!-- END roadmap-access-preflight -->", skill.read_text(), re.S)
        self.assertIsNotNone(match, "installed production probe is missing")
        before = self.installer.snapshot(self.target)
        state_before = self.state_path.read_bytes()
        result = subprocess.run(["bash", "-c", match.group(1)], cwd=self.target,
                                env=dict(self.env, ROADMAP_CHOICE=choice), capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.installer.snapshot(self.target))
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertTrue(all(call[:2] == ["project", "list"] for call in self.calls()))
        return result.stdout

    def test_scope_missing_absent_declined_have_distinct_record_drafts(self):
        self.set_state(error="GraphQL: INSUFFICIENT_SCOPES: requires read:project")
        missing = self.probe()
        self.assertEqual("Roadmap board: scope-missing", missing.splitlines()[0])
        self.assertIn("read:project", missing)
        self.assertIn("project for creation/updates", missing)
        self.assertIn("gh auth refresh -s project", missing)
        self.assertNotIn("GraphQL:", missing)
        self.set_state()
        absent = self.probe()
        self.assertEqual("Roadmap board: absent", absent.splitlines()[0])
        self.set_state(error="GraphQL: INSUFFICIENT_SCOPES")
        declined = self.probe("declined")
        self.assertEqual("Roadmap board: declined\n", declined)
        self.assertEqual([], self.calls())
        self.assertEqual(3, len({x.splitlines()[0] for x in (missing, absent, declined)}))

    def test_failed_incomplete_ambiguous_or_closed_observations_are_not_absence(self):
        board = dict(number=7, title="sample roadmap", closed=False)
        for state in ({"error": "HTTP 403: forbidden"}, {"error": "network unavailable"},
                      {"raw": "not JSON"}, {"raw": "{}"}, {"raw": "[]"}, {"raw": ""},
                      {"raw": '{"projects":[],"totalCount":0}\n' +
                       json.dumps({"projects": [board], "totalCount": 1})},
                      {"total": 2}, {"projects": [board, dict(board, number=8)]},
                      {"projects": [dict(board, closed=True)]}):
            with self.subTest(state=state):
                self.set_state(**state)
                self.assertEqual("Roadmap board: unavailable", self.probe().splitlines()[0])

    def test_one_matching_open_board_is_readable_not_write_permission(self):
        self.set_state(projects=[dict(number=7, title="sample roadmap", closed=False),
                                 dict(number=8, title="other roadmap", closed=False)])
        result = self.probe()
        self.assertEqual("Roadmap board: available", result.splitlines()[0])
        self.assertIn("write permission unverified", result)
        self.assertEqual(["project", "list", "--owner", "fixture-owner", "--closed",
                          "--limit", "100", "--format", "json"], self.calls()[0])

    def test_cli_friendly_scope_error_is_reported_without_raw_response(self):
        self.set_state(error="error: your authentication token is missing required scopes [read:project]\n"
                             "To request it, run: gh auth refresh -s read:project")
        result = self.probe()
        self.assertEqual("Roadmap board: scope-missing", result.splitlines()[0])
        self.assertIn("gh auth refresh -s project", result)
        self.assertNotIn("error: your authentication token", result)

    def test_unknown_choice_cannot_turn_into_consent(self):
        result = self.probe("yes-from-an-unread-record")
        self.assertEqual("Roadmap board: unavailable", result.splitlines()[0])
        self.assertEqual([], self.calls())

    def test_installed_init_creates_links_then_reuses_with_explicit_fixture_consent(self):
        self.set_state(write_access=True, write_consent=True)
        command = ["bash", ".github/scripts/setup-project.sh", "init", "-R", "fixture-owner/sample"]
        first = subprocess.run(command, cwd=self.target, env=self.env, capture_output=True,
                               text=True, timeout=30)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        state = json.loads(self.state_path.read_text())
        self.assertEqual([dict(number=7, title="sample roadmap", closed=False)], state["projects"])
        self.assertEqual([dict(name="Start date", dataType="DATE"),
                          dict(name="Target date", dataType="DATE"),
                          dict(name="Kind", dataType="SINGLE_SELECT")], state["fields"])
        self.assertEqual(["Roadmap", "Kanban", "Backlog"], state["views"])
        self.assertEqual("fixture-owner/sample", state["linked_repo"])
        self.assertIn("https://github.com/users/fixture-owner/projects/7", first.stdout)
        self.calls_path.write_text("")
        second = subprocess.run(command, cwd=self.target, env=self.env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        self.assertEqual(state, json.loads(self.state_path.read_text()))
        self.assertFalse(any(call[:2] in (["project", "create"], ["project", "field-create"])
                             or any("createProjectV2View" in arg for arg in call) for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
