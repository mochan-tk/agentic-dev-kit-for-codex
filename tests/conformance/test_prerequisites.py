"""Real local tools and isolated synthetic GitHub responses for Tier diagnosis."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/check-prerequisites.py"
SPEC = importlib.util.spec_from_file_location("introduction_preflight", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
REGISTRY = json.loads(CHECK.REGISTRY.read_text())
FAKE_GH = r'''
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
state = json.loads(Path(os.environ["T2_STATE"]).read_text())
with open(os.environ["T2_CALLS"], "a") as stream:
    stream.write(json.dumps(a) + "\n")
if a == ["--version"]:
    print("gh version 2.80.0")
    sys.exit(0)
if a[:6] != ["api", "--hostname", "github.com", "--method", "GET", "--include"]:
    sys.exit("unexpected or mutating command")
endpoint = a[-1]
if endpoint == "user":
    response = state["user"]
elif endpoint == "repos/fixture/adopter":
    response = state["repo"]
elif endpoint.startswith("repos/fixture/adopter/contents/.github/codex-instructions.md?ref="):
    response = state["anchor"]
else:
    sys.exit("unexpected endpoint")
if response.get("transport"):
    sys.exit("synthetic-secret-do-not-publish")
if response.get("auth_required"):
    print("synthetic-secret-do-not-publish", file=sys.stderr)
    sys.exit(4)
status = response.get("status", 200)
print("HTTP/2 " + str(status))
for key, value in response.get("headers", {}).items():
    print(key + ": " + value)
print()
print(response.get("raw", json.dumps(response.get("data"))))
if status != 200:
    print("synthetic-secret-do-not-publish", file=sys.stderr)
sys.exit(0 if status == 200 else 1)
'''


class PrerequisiteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="t2-prerequisites-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.target = self.work / "adopter"
        self.target.mkdir()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(PATH=str(self.bin), T2_STATE=str(self.work / "state.json"),
                        T2_CALLS=str(self.work / "calls.jsonl"), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull)
        for tool in ("git", "bash"):
            executable = shutil.which(tool)
            self.assertIsNotNone(executable, tool + " required by contributor tests")
            (self.bin / tool).symlink_to(executable)
        self.shim("jq", 'print("jq-1.7.1")\n')
        self.shim("gh", FAKE_GH)
        subprocess.run([str(self.bin / "git"), "init", "-q", str(self.target)],
                       env=self.env, check=True, capture_output=True)
        subprocess.run([str(self.bin / "git"), "-C", str(self.target), "remote", "add", "origin",
                        "https://github.com/fixture/adopter.git"], env=self.env, check=True, capture_output=True)
        self.state = {
            "user": {"headers": {"X-OAuth-Scopes": "repo, project"}, "data": {"login": "fixture"}},
            "repo": {"data": {"full_name": "fixture/adopter", "default_branch": "main"}},
            "anchor": {"data": {"type": "file", "path": ".github/codex-instructions.md", "sha": "a" * 40}},
        }

    def shim(self, name, body):
        path = self.bin / name
        if path.is_symlink():
            path.unlink()
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)

    def invoke(self, target=True, **environment):
        Path(self.env["T2_STATE"]).write_text(json.dumps(self.state))
        Path(self.env["T2_CALLS"]).write_text("")
        before = {str(path.relative_to(self.target)): path.read_bytes()
                  for path in self.target.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), *([str(self.target)] if target else [])],
                                cwd=self.target, env=dict(self.env, **environment),
                                capture_output=True, text=True, timeout=20)
        after = {str(path.relative_to(self.target)): path.read_bytes()
                 for path in self.target.rglob("*") if path.is_file()}
        self.assertEqual(before, after, "diagnostic modified the adopter")
        self.assertNotIn("synthetic-secret", result.stdout + result.stderr)
        calls = [json.loads(line) for line in Path(self.env["T2_CALLS"]).read_text().splitlines()]
        for call in calls:
            self.assertTrue(call == ["--version"] or call[:6] ==
                            ["api", "--hostname", "github.com", "--method", "GET", "--include"], call)
        self.calls = calls
        return result

    def test_detected_tools_and_remote_state_with_honest_manual_entries(self):
        result = self.invoke(target=False)
        self.assertEqual(1, result.returncode, result.stderr)
        for key in ("git", "bash", "jq", "gh", "github-checkout", "repository-access", "remote-scaffold", "projects-scope"):
            self.assertIn(f"OK [{key}]", result.stdout)
        for key in ("codex-desktop", "spec-context", "codex-project", "projects-board-or-exception"):
            self.assertIn(f"PROCEDURE [{key}]", result.stdout)
        self.assertEqual(1, result.stdout.count("Cumulative readiness: OK"))
        self.assertEqual(2, result.stdout.count("Cumulative readiness: CONFIRMATION REQUIRED"))

    def test_missing_jq_names_tier_impact_and_remedy(self):
        (self.bin / "jq").unlink()
        result = self.invoke()
        self.assertEqual(1, result.returncode)
        tier_zero = result.stdout.split("Tier 0", 1)[1].split("Tier 1", 1)[0]
        self.assertIn("MISSING [jq]", tier_zero)
        row = next(row for row in REGISTRY["entries"] if row["id"] == "jq")
        self.assertIn("Impact if missing: " + row["impact_if_missing"], tier_zero)
        self.assertIn("Remedy: " + row["remedy"], tier_zero)
        self.assertEqual(3, result.stdout.count("Cumulative readiness: MISSING"))

    def test_bash_minimum_and_missing_or_invalid_executables(self):
        self.shim("bash", 'print("GNU bash, version 3.1.23")\n')
        self.assertIn("MISSING [bash]", self.invoke().stdout)
        self.shim("bash", 'print("GNU bash, version 3.2.57")\n')
        self.assertIn("OK [bash]", self.invoke().stdout)
        self.shim("jq", 'print("invalid-version synthetic-secret-do-not-publish")\n')
        self.assertIn("UNVERIFIED [jq]", self.invoke().stdout)
        (self.bin / "gh").unlink()
        self.assertIn("MISSING [gh]", self.invoke().stdout)
        self.assertEqual([], self.calls)

    def test_scope_levels_unknown_credentials_and_authentication_failures(self):
        for scopes, expected in (("repo, project", "OK"), ("repo, read:project", "MISSING"),
                                 ("repo", "MISSING"), ("", "PROCEDURE"), (None, "PROCEDURE")):
            with self.subTest(scopes=scopes):
                self.state["user"]["headers"] = {} if scopes is None else {"x-oauth-scopes": scopes}
                result = self.invoke()
                self.assertIn(f"{expected} [projects-scope]", result.stdout)
                if expected == "MISSING":
                    self.assertIn("gh auth refresh -s project", result.stdout)
        self.state["user"] = {"status": 401}
        self.state["repo"] = {"status": 401}
        self.assertIn("MISSING [repository-access]", self.invoke().stdout)
        self.state["user"] = {"transport": True}
        self.state["repo"] = {"transport": True}
        result = self.invoke()
        self.assertIn("UNVERIFIED [repository-access]", result.stdout)
        self.assertIn("UNVERIFIED [projects-scope]", result.stdout)

    def test_local_authentication_required_exit_is_named_and_stops_remote_probes(self):
        self.state["user"] = {"auth_required": True}
        result = self.invoke()
        self.assertEqual(1, result.returncode)
        self.assertIn("MISSING [repository-access]", result.stdout)
        self.assertIn("CLI exit 4", result.stdout)
        self.assertIn("gh auth login", result.stdout)
        self.assertEqual(2, len(self.calls))  # version, then the authentication probe
        self.assertNotIn("HTTP 401", result.stdout)

    def test_repository_denial_and_bad_responses_do_not_claim_absence(self):
        for response in ({"status": 403}, {"status": 404}, {"raw": "bad json"},
                         {"data": []}, {"data": {"full_name": "other/repository"}}):
            with self.subTest(response=response):
                self.state["repo"] = response
                result = self.invoke()
                self.assertIn("UNVERIFIED [repository-access]", result.stdout)
                self.assertIn("UNVERIFIED [remote-scaffold]", result.stdout)
                self.assertFalse(any("/contents/" in call[-1] for call in self.calls))

    def test_absent_or_inaccessible_scaffold_and_bad_metadata_are_unverified(self):
        for response in ({"status": 404}, {"status": 403}, {"transport": True},
                         {"data": {"type": "symlink"}}, {"raw": "bad json"}):
            with self.subTest(response=response):
                self.state["anchor"] = response
                self.assertIn("UNVERIFIED [remote-scaffold]", self.invoke().stdout)
        for branch in (None, 1, ""):
            self.state["repo"]["data"]["default_branch"] = branch
            self.assertIn("UNVERIFIED [remote-scaffold]", self.invoke().stdout)

    def test_branch_names_are_encoded_and_inherited_git_context_cannot_redirect(self):
        self.state["repo"]["data"]["default_branch"] = "release/next#1"
        result = self.invoke(GIT_DIR="/not-the-target", GIT_WORK_TREE="/not-the-target", GH_REPO="other/repo")
        self.assertIn("OK [github-checkout]", result.stdout)
        self.assertIn("OK [repository-access]", result.stdout)
        self.assertTrue(self.calls[-1][-1].endswith("?ref=release%2Fnext%231"))

    def test_remote_parsing_is_explicit_and_never_forwards_embedded_credentials(self):
        for value in ("https://github.com/owner/repo.git", "git@github.com:owner/repo.git", "ssh://git@github.com/owner/repo"):
            self.assertEqual("owner/repo", CHECK.repository_name(value))
        for value in ("https://token@github.com/owner/repo", "https://evil.invalid/owner/repo",
                      "https://github.com/owner/repo?token=secret", "https://github.com/../repo"):
            self.assertIsNone(CHECK.repository_name(value))

    def test_invalid_target_and_command_timeout_do_not_traceback(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.work / "absent")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertNotIn(str(self.work), result.stderr)
        with patch.object(CHECK.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 10)):
            self.assertEqual((126, ""), CHECK.run(["git", "--version"], self.target))


class IntroductionContractTests(unittest.TestCase):
    def test_registry_schema_and_readme_tier_coverage(self):
        self.assertEqual("prerequisites/v1", REGISTRY["schema"])
        ids = [row["id"] for row in REGISTRY["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([0, 1, 2], [row["tier"] for row in REGISTRY["tiers"]])
        readme = (ROOT / "README.md").read_text().split("### Prerequisites", 1)[1].split("\n### ", 1)[0]
        rows = {int(match[1]): match[0] for match in re.finditer(r"^\| Tier ([012])[^\n]+", readme, re.M)}
        for row in REGISTRY["entries"]:
            self.assertEqual({"id", "label", "tier", "kind", "detection", "impact_if_missing", "remedy"}, set(row))
            self.assertIn(row["kind"], {"tool", "scope", "state", "context"})
            self.assertIn(row["detection"]["mode"], {"command", "procedure"})
            self.assertTrue(row["impact_if_missing"] and row["remedy"] and row["detection"]["description"])
            if row["detection"]["mode"] == "command":
                self.assertTrue(row["detection"]["commands"])
            self.assertIn("`" + row["id"] + "`", rows[row["tier"]])
        self.assertIn("required by default", readme)
        self.assertIn("gh auth refresh -s project", readme)
        self.assertIn("date-only defer/decline is not a Project exception", readme)

    def test_lead_time_record_and_interval_definitions_match_p6(self):
        guide = (ROOT / "docs/introduction.md").read_text()
        skill = (ROOT / ".github/distribution/payload/.agents/skills/project-onboarding/SKILL.md").read_text()
        pattern = r"<!-- BEGIN introduction-lead-time -->\n(.*?)\n<!-- END introduction-lead-time -->"
        self.assertEqual(re.search(pattern, guide, re.S)[1], re.search(pattern, skill, re.S)[1])
        for interval in ("scaffold_on_default - adoption_started", "onboarding_completed - scaffold_on_default",
                         "first_task_closed - onboarding_completed", "first_task_closed - adoption_started"):
            self.assertIn(interval, guide)
            self.assertIn(interval, skill)
        self.assertIn("update this same evidence PR", skill)
        self.assertIn("not owner acceptance or merge", skill)


if __name__ == "__main__":
    unittest.main()
