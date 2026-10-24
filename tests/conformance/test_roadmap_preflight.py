"""Run the installed roadmap probe/helper with real tools and synthetic GitHub.

These tests do not prove a live credential's permissions or model compliance.
"""

import json
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
    if "createProjectV2View" in query:
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
