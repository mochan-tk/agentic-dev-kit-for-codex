"""Frozen sensor/setup semantics, using actual Bash/jq and raw fake API data."""
import copy
import json
import os
import re
import shlex
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SENSOR = ROOT / ".github/scripts/governance-status.sh"
SETUP = ROOT / ".github/distribution/payload/.github/scripts/setup-ruleset.sh"
CHECKS = ["lint", "test"]
REPO = "repos/fixture/adopter"


def canonical(profile="team", app=15368):
    team = profile == "team"
    return dict(id=42, name="scaffold-branch-protection", target="branch", enforcement="active",
                source_type="Repository", source="fixture/adopter",
                bypass_actors=[] if profile=="single-maintainer" else [dict(actor_id=5, actor_type="RepositoryRole", bypass_mode="pull_request")],
                conditions=dict(ref_name=dict(include=["~DEFAULT_BRANCH"], exclude=[])),
                rules=[dict(type="pull_request", parameters=dict(required_approving_review_count=0 if profile=="single-maintainer" else 1,
                    dismiss_stale_reviews_on_push=team, require_code_owner_review=team,
                    require_last_push_approval=team, required_review_thread_resolution=team)),
                    dict(type="required_status_checks", parameters=dict(strict_required_status_checks_policy=team,
                        required_status_checks=[dict(context=x, **({"integration_id":app} if team else {})) for x in CHECKS]))])


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="source-governance-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.records = self.work / "api.json"
        self.calls = self.work / "calls.jsonl"
        # This fake transports raw JSON and records the actual method/argv/body.
        # It never returns a precomputed governance verdict.
        gh = self.bin / "gh"
        gh.write_text("#!" + sys.executable + "\n" + r'''
import json,os,subprocess,sys
from pathlib import Path
a=sys.argv[1:]; method="GET"; endpoint=""; query=None; body=None; i=1
if not a or a[0]!="api": sys.exit(91)
while i<len(a):
 x=a[i]
 if x in ("--method","-X"): method=a[i+1]; i+=2
 elif x in ("-H","--header"): i+=2
 elif x in ("--jq","-q"): query=a[i+1]; i+=2
 elif x=="--input":
  body=json.load(sys.stdin) if a[i+1]=="-" else json.loads(Path(a[i+1]).read_text()); i+=2
 elif x in ("-f","-F"):
  k,v=a[i+1].split("=",1); body=body or {}; body[k]=v; i+=2
 elif x=="--paginate": i+=1
 elif x.startswith("-"): sys.exit(92)
 elif not endpoint: endpoint=x; i+=1
 else: sys.exit(93)
with open(os.environ["SF_CALLS"],"a") as f: f.write(json.dumps(dict(argv=a,method=method,endpoint=endpoint,body=body))+"\n")
if os.environ.get("SF_GET_ONLY")=="1" and (method!="GET" or body is not None): sys.exit(94)
record=json.loads(Path(os.environ["SF_API"]).read_text()).get(method+" "+endpoint)
if record is None: print("gh: Not Found (HTTP 404)",file=sys.stderr); sys.exit(1)
if record.get("rc",0): print(record.get("error","gh: HTTP 500"),file=sys.stderr); sys.exit(record["rc"])
raw=record["raw"] if "raw" in record else json.dumps(record.get("body",{}))
if query:
 p=subprocess.run([os.environ["SF_JQ"],"-r",query],input=raw,text=True,capture_output=True)
 sys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.exit(p.returncode)
print(raw)
''')
        gh.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin)+os.pathsep+os.environ["PATH"],
                        SF_API=str(self.records), SF_CALLS=str(self.calls), SF_JQ=shutil.which("jq"))
        self.api = {}
        self.baseline()

    def put(self, endpoint, body=None, *, method="GET", raw=None, rc=0):
        self.api[method+" "+endpoint] = {"rc":rc, **({"raw":raw} if raw is not None else {"body":body})}

    def baseline(self, profile="team"):
        self.api = {}
        self.put(REPO, dict(default_branch="main", owner=dict(type="User",login="fixture"), private=False))
        self.put("user", {"login":"fixture"})
        self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE", {"name":"SCAFFOLD_GOVERNANCE_PROFILE","value":profile})
        self.put(REPO+"/actions/permissions/workflow", dict(default_workflow_permissions="read",can_approve_pull_request_reviews=False))
        detail=canonical(profile)
        rules=copy.deepcopy(detail["rules"])
        for row in rules: row.update(ruleset_id=42,ruleset_source_type="Repository",ruleset_source="fixture/adopter")
        self.put(REPO+"/rules/branches/main?per_page=100",rules)
        self.put(REPO+"/rulesets?per_page=100", [])
        self.put(REPO+"/rulesets/42", detail)
        self.runs([dict(id=i+1,name=x,app=dict(id=15368)) for i,x in enumerate(CHECKS)])
        self.put(REPO+"/contents/.github/CODEOWNERS?ref=main", raw="* @fixture-maintainer\n")
        for method, endpoint in (("PATCH",REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE"),
                                 ("POST",REPO+"/actions/variables"), ("POST",REPO+"/rulesets"),
                                 ("PUT",REPO+"/rulesets/42")):
            self.put(endpoint,{"id":42},method=method)

    def runs(self, rows, total=None):
        self.put(REPO+"/commits/main/check-runs?filter=latest&per_page=100",
                 dict(total_count=len(rows) if total is None else total,check_runs=rows))

    def run_script(self, script, *args, sensor=False):
        self.records.write_text(json.dumps(self.api)); self.calls.write_text("")
        result=subprocess.run(["bash",str(script),*args],env=dict(self.env,SF_GET_ONLY="1" if sensor else "0"),
                              cwd=self.work,capture_output=True,text=True,timeout=20)
        self.log=[json.loads(x) for x in self.calls.read_text().splitlines()]
        if sensor: self.assertTrue(all(x["method"]=="GET" and x["body"] is None for x in self.log),self.log)
        return result

    def sensor(self,*args,profile="team",posture="adopter"):
        return self.run_script(SENSOR,"-R","fixture/adopter","--checks","lint,test","--posture",posture,
                               *(["--profile",profile] if profile is not None else []),*args,sensor=True)

    def setup(self,*args,profile="team"):
        return self.run_script(SETUP,"-R","fixture/adopter","--checks","lint,test",
                               *(["--profile",profile] if profile is not None else []),*args)

    def no_writes(self):
        self.assertTrue(all(x["method"]=="GET" for x in self.log),self.log)

    def installed_onboarding(self):
        adopter = self.work / "adopter"
        adopter.mkdir()
        subprocess.run(["git", "init", "-q", str(adopter)], check=True, capture_output=True)
        result = subprocess.run(["bash", str(ROOT / ".github/scripts/scaffold-init.sh"),
                                 "--apply", str(adopter)], env=dict(self.env, SCAFFOLD_SOURCE_DIR=str(ROOT)),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        return adopter

    def onboarding_command(self, adopter, name, **inputs):
        skill = (adopter / ".agents/skills/project-onboarding/SKILL.md").read_text()
        match = re.search(r"<!-- " + re.escape(name) + r" -->\s*```bash\n(.*?)\n```", skill, re.S)
        self.assertIsNotNone(match, "missing executable installed onboarding example: " + name)
        self.records.write_text(json.dumps(self.api)); self.calls.write_text("")
        result = subprocess.run(["bash", "-c", match.group(1)], cwd=adopter,
                                env=dict(self.env, **inputs), capture_output=True, text=True, timeout=20)
        self.log = [json.loads(x) for x in self.calls.read_text().splitlines()]
        return result

    def test_f01_installed_onboarding_choice_create_reconcile_and_refusals(self):
        adopter = self.installed_onboarding()
        inputs = dict(ONBOARD_REPO="fixture/adopter", ONBOARD_CHECKS="lint,test",
                      ONBOARD_PROFILE="solo", ONBOARD_RULESET="new", ONBOARD_CHOICE="disabled")
        for profile in ("solo", "team"):
            for choice in ("disabled", "active"):
                with self.subTest(profile=profile, choice=choice):
                    self.baseline(profile)
                    result = self.onboarding_command(adopter, "onboarding-ruleset-apply",
                                                     **dict(inputs, ONBOARD_PROFILE=profile, ONBOARD_CHOICE=choice))
                    self.assertEqual(0, result.returncode, result.stderr)
                    writes = [x for x in self.log if x["method"] != "GET"]
                    self.assertEqual(["PATCH", "POST"], [x["method"] for x in writes])
                    self.assertEqual(profile, writes[0]["body"]["value"])
                    self.assertEqual(choice, writes[1]["body"]["enforcement"])
        self.baseline("solo")
        existing = canonical("solo"); existing["enforcement"] = "disabled"
        self.put(REPO+"/rulesets?per_page=100", [dict(id=42,name=existing["name"],enforcement="disabled")])
        self.put(REPO+"/rulesets/42", existing)
        result = self.onboarding_command(adopter, "onboarding-ruleset-apply",
                                         **dict(inputs, ONBOARD_RULESET="canonical", ONBOARD_CHOICE="active"))
        self.assertEqual(0, result.returncode, result.stderr)
        writes = [x for x in self.log if x["method"] != "GET"]
        self.assertEqual(["PATCH", "PUT"], [x["method"] for x in writes])
        self.assertEqual({"enforcement":"active"}, writes[1]["body"])
        for changes in (dict(ONBOARD_PROFILE=""), dict(ONBOARD_PROFILE="unknown"),
                        dict(ONBOARD_RULESET="new"), dict(ONBOARD_RULESET="unknown"),
                        dict(ONBOARD_CHOICE="unknown")):
            with self.subTest(changes=changes):
                result = self.onboarding_command(adopter, "onboarding-ruleset-apply", **dict(inputs, **changes))
                self.assertNotEqual(0, result.returncode); self.no_writes()
        existing["rules"][0]["parameters"]["required_approving_review_count"] = 2
        self.put(REPO+"/rulesets/42", existing)
        self.assertNotEqual(0, self.onboarding_command(adopter, "onboarding-ruleset-apply",
                           **dict(inputs, ONBOARD_RULESET="canonical")).returncode); self.no_writes()
        self.baseline("team"); self.runs([])
        self.assertNotEqual(0, self.onboarding_command(adopter, "onboarding-ruleset-apply",
                           **dict(inputs, ONBOARD_PROFILE="team")).returncode); self.no_writes()
        self.baseline("solo")
        self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE", method="PATCH", rc=1)
        self.assertNotEqual(0, self.onboarding_command(adopter, "onboarding-ruleset-apply", **inputs).returncode)
        self.assertFalse(any(x["method"]!="GET" and "/rulesets" in x["endpoint"] for x in self.log))
        self.assertEqual(0, self.onboarding_command(adopter, "onboarding-ruleset-apply",
                         ONBOARD_CHOICE="skip").returncode)
        self.assertEqual([], self.log)

    def test_f01_installed_preview_and_help_network_boundaries(self):
        adopter = self.installed_onboarding()
        for profile in ("solo", "team"):
            self.baseline(profile)
            result = self.onboarding_command(adopter, "onboarding-ruleset-preview", ONBOARD_REPO="fixture/adopter",
                                             ONBOARD_CHECKS="lint,test", ONBOARD_PROFILE=profile)
            self.assertEqual(0, result.returncode, result.stderr); self.no_writes()
            self.assertEqual(profile == "team", bool(self.log))
        help_result = self.run_script(adopter / ".github/scripts/setup-ruleset.sh", "--help")
        self.assertEqual(0, help_result.returncode); self.assertEqual([], self.log)
        examples = [shlex.split(line.strip())[2:] for line in help_result.stdout.splitlines()
                    if line.startswith("  bash .github/scripts/setup-ruleset.sh")]
        self.assertEqual(5, len(examples))
        for original in examples:
            with self.subTest(example=original):
                args = ["fixture/adopter" if x == "owner/repo" else x for x in original]
                if "--dry-run" not in args: args.append("--dry-run")
                profile = args[args.index("--profile")+1] if "--profile" in args else None
                self.baseline(profile or "solo")
                if "--reconcile" in args:
                    detail = canonical(profile); detail["enforcement"] = "disabled"
                    self.put(REPO+"/rulesets?per_page=100", [dict(id=42,name=detail["name"],enforcement="disabled")])
                    self.put(REPO+"/rulesets/42", detail)
                result = self.run_script(adopter / ".github/scripts/setup-ruleset.sh", *args)
                self.assertEqual(0, result.returncode, result.stderr); self.no_writes()
                self.assertEqual(profile == "team" or "--reconcile" in args, bool(self.log))
                if "--reconcile" in args: self.assertIn("explicit solo candidate", result.stderr)
                self.assertEqual("scaffold-branch-protection", json.loads(result.stdout)["name"])

    def test_f02_bypass_actor_id_types_and_incomplete_details(self):
        cases = [("DeployKey", None, "User", 0), ("OrganizationAdmin", None, "Organization", 0),
                 ("OrganizationAdmin", 17, "Organization", 0),
                 ("OrganizationAdmin", None, "User", 3), ("OrganizationAdmin", 17, "User", 3),
                 ("DeployKey", 17, "User", 3),
                 ("UnknownActor", 17, "User", 3)]
        for kind in ("Integration", "RepositoryRole", "Team", "User"):
            cases += [(kind, 17, "User", 0), (kind, None, "User", 3)]
        cases += [("Team", value, "User", 3) for value in ("17", True, -1, 1.5, [], {})]
        for kind, identifier, owner, expected in cases:
            with self.subTest(kind=kind, identifier=identifier, owner=owner):
                self.baseline()
                self.api["GET "+REPO]["body"]["owner"]["type"] = owner
                if owner == "Organization":
                    self.api["GET "+REPO+"/rules/branches/main?per_page=100"]["body"].append(
                        dict(type="merge_queue",parameters={},ruleset_id=42,ruleset_source_type="Repository",ruleset_source="fixture/adopter"))
                    self.put(REPO+"/contents/.github/workflows?ref=main", [dict(type="file",name="ci.yml")])
                    self.put(REPO+"/contents/.github/workflows/ci.yml?ref=main", raw="on: [merge_group]\n")
                detail = canonical(); detail["bypass_actors"] = [dict(actor_type=kind,actor_id=identifier,bypass_mode="always")]
                self.put(REPO+"/rulesets/42", detail)
                result = self.sensor()
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                if expected == 0:
                    self.assertIn("actor_type="+kind+" actor_id="+("none" if identifier is None else str(identifier)), result.stdout)
                else:
                    self.assertIn("bypass.ruleset.42\tUNKNOWN", result.stdout)
        self.baseline()
        for actor in ({"actor_type":"Team","bypass_mode":"always"},
                      {"actor_type":"DeployKey","bypass_mode":"always"},
                      {"actor_type":"DeployKey","actor_id":None,"bypass_mode":"pull_request"},
                      {"actor_type":"Team","actor_id":17,"bypass_mode":"exempt"},
                      None, []):
            self.put(REPO+"/rulesets/42", dict(id=42,bypass_actors=[actor]))
            self.assertEqual(3, self.sensor().returncode)
        self.put(REPO+"/rulesets/42", dict(id=42))
        self.assertEqual(3, self.sensor().returncode)

    def test_g002_declared_profile_never_inferred(self):
        for value in (None,True,0,[],{},"","Solo","solo ","team\n","pirate"):
            with self.subTest(value=value):
                self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE",{"value":value})
                result=self.sensor(profile=None)
                self.assertEqual(3,result.returncode,result.stderr)
                self.assertIn("governance.profile\tUNKNOWN",result.stdout)
        self.assertEqual(0,self.sensor(profile="team").returncode)
        self.assertFalse(any("variables" in x["endpoint"] for x in self.log))

    def test_g003_solo_minimum_and_stronger_observations(self):
        self.assertEqual(0,self.sensor(profile="solo").returncode)
        self.assertIn("pull_request.dismiss_stale_reviews\tACTIVE",self.sensor(profile="solo").stdout)
        self.baseline("solo")
        self.assertEqual(0,self.sensor(profile="solo").returncode)
        self.api["GET "+REPO+"/rules/branches/main?per_page=100"]["body"][0]["parameters"]["required_approving_review_count"]=0
        self.assertEqual(1,self.sensor(profile="solo").returncode)

    def test_g004_g005_raw_issuer_failures_never_write(self):
        cases=[[],[dict(id=1,name="lint",app=dict(id=15368))]]
        for bad in (None,"15368",True,-1,1.5):
            cases.append([dict(id=1,name="lint",app=dict(id=bad)),dict(id=2,name="test",app=dict(id=15368))])
        cases.append([dict(id=1,name="lint",app=dict(id=15368)),dict(id=2,name="test",app=dict(id=77))])
        cases.append([dict(id=1,name="lint",app=dict(id=15368)),dict(id=2,name="lint",app=dict(id=77)),dict(id=3,name="test",app=dict(id=15368))])
        for rows in cases:
            with self.subTest(rows=rows):
                self.runs(rows)
                self.assertNotEqual(0,self.sensor().returncode)
                result=self.setup()
                self.assertNotEqual(0,result.returncode,result.stderr); self.no_writes()
        # Per-context matches must not hide different issuers across contexts.
        self.runs([dict(id=1,name="lint",app=dict(id=15368)),dict(id=2,name="test",app=dict(id=77))])
        self.api["GET "+REPO+"/rules/branches/main?per_page=100"]["body"][1]["parameters"]["required_status_checks"][1]["integration_id"]=77
        self.assertIn("different issuing App IDs",self.sensor().stdout)

    def test_g005_complete_pages_and_late_conflict(self):
        endpoint=REPO+"/commits/main/check-runs?filter=latest&per_page=100"
        pages=[dict(total_count=2,check_runs=[dict(id=1,name="lint",app=dict(id=15368))]),
               dict(total_count=2,check_runs=[dict(id=2,name="test",app=dict(id=15368))])]
        self.put(endpoint,raw="\n".join(map(json.dumps,pages)))
        self.assertEqual(0,self.sensor().returncode)
        self.assertEqual(0,self.setup("--dry-run").returncode);self.no_writes()
        pages[1]["check_runs"].append(dict(id=3,name="lint",app=dict(id=77)))
        for page in pages:page["total_count"]=3
        self.put(endpoint,raw="\n".join(map(json.dumps,pages)))
        self.assertIn("UNCHECKABLE",self.sensor().stdout)
        self.assertNotEqual(0,self.setup().returncode);self.no_writes()
        self.runs([dict(id=1,name=x,app=dict(id=15368)) for x in CHECKS],total=3)
        self.assertNotEqual(0,self.sensor().returncode)
        self.assertNotEqual(0,self.setup().returncode);self.no_writes()

    def test_g006_unknown_and_noncanonical_refuse(self):
        self.put(REPO+"/rulesets?per_page=100",[dict(id=42,name="scaffold-branch-protection",enforcement="active")])
        changes=[lambda d:d.update(target="tag"),lambda d:d.pop("bypass_actors"),
                 lambda d:d["rules"].append(dict(type="deletion")),
                 lambda d:d["rules"][0]["parameters"].update(required_approving_review_count=2),
                 lambda d:d["rules"][1]["parameters"]["required_status_checks"].append(dict(context="extra")),
                 lambda d:d.update(id="42"),lambda d:d.update(conditions={})]
        for change in changes:
            detail=canonical();change(detail);self.put(REPO+"/rulesets/42",detail)
            with self.subTest(detail=detail):
                self.assertNotEqual(0,self.setup("--reconcile").returncode);self.no_writes()
        self.put(REPO+"/rulesets/42",rc=1)
        self.assertNotEqual(0,self.setup("--reconcile").returncode);self.no_writes()

    def test_g007_intent_persistence_precedes_ruleset(self):
        result=self.setup();self.assertEqual(0,result.returncode,result.stderr)
        writes=[x for x in self.log if x["method"]!="GET"]
        self.assertEqual(["PATCH","POST"],[x["method"] for x in writes])
        self.assertEqual({"name":"SCAFFOLD_GOVERNANCE_PROFILE","value":"team"},writes[0]["body"])
        self.assertTrue(all(x["integration_id"]==15368 for x in writes[1]["body"]["rules"][1]["parameters"]["required_status_checks"]))
        self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE",method="PATCH",rc=1)
        self.assertNotEqual(0,self.setup().returncode)
        self.assertFalse(any(x["method"]!="GET" and "/rulesets" in x["endpoint"] for x in self.log))
        self.assertNotEqual(0,self.setup(profile=None).returncode);self.assertEqual([],self.log)
        self.assertEqual(0,self.setup("--dry-run",profile=None).returncode);self.assertEqual([],self.log)

    def test_g008_effective_org_rule_and_real_trigger(self):
        self.assertIn("merge_queue.applicability\tN/A",self.sensor().stdout)
        self.api["GET "+REPO]["body"]["owner"]["type"]="Organization"
        self.assertEqual(3,self.sensor().returncode)
        self.api["GET "+REPO+"/rules/branches/main?per_page=100"]["body"].append(dict(type="merge_queue",parameters={},ruleset_id=42,ruleset_source_type="Repository",ruleset_source="fixture/adopter"))
        self.put(REPO+"/contents/.github/workflows?ref=main",[dict(type="file",name="ci.yml")])
        endpoint=REPO+"/contents/.github/workflows/ci.yml?ref=main"
        for raw in ("on: [pull_request, merge_group]\n", "on:\n  merge_group:\n    types: [checks_requested]\n"):
            self.put(endpoint,raw=raw);self.assertEqual(0,self.sensor().returncode)
        for raw in ("on: [push] # merge_group\n", "jobs:\n  x:\n    steps:\n      - run: |\n          on:\n            merge_group:\n", "on: |\n  merge_group:\n", "on: *events\n", 'on: [merge_group]\n"on": [push]\n', "on:\n  merge_group:\n    types: [unterminated\n"):
            self.put(endpoint,raw=raw);self.assertNotEqual(0,self.sensor().returncode)

    def test_g009_explicit_posture_and_unresolved_installed_owners(self):
        endpoint=REPO+"/contents/.github/CODEOWNERS?ref=main"
        for raw in ("# CUSTOMIZE replace owner\n* @owner\n", "# no actual ownership\n", ""):
            self.put(endpoint,raw=raw);self.assertNotEqual(0,self.sensor().returncode)
        self.assertEqual(0,self.sensor(posture="source-template").returncode)
        self.api.pop("GET "+endpoint)
        self.assertNotEqual(0,self.sensor().returncode)

    def test_malformed_failed_reads_and_missing_inputs_fail_closed(self):
        for endpoint in (REPO,REPO+"/rules/branches/main?per_page=100",REPO+"/rulesets/42",REPO+"/actions/permissions/workflow"):
            for raw in ("{", "null", "{}", "[]"):
                with self.subTest(endpoint=endpoint,raw=raw):
                    self.baseline();self.put(endpoint,raw=raw)
                    self.assertNotEqual(0,self.sensor().returncode)
            self.baseline();self.put(endpoint,rc=1);self.assertNotEqual(0,self.sensor().returncode)
        self.assertEqual(2,self.run_script(SENSOR,"--profile","solo",sensor=True).returncode)
        self.assertEqual([],self.log)

    def test_paginated_inherited_rules_bypass_and_incomplete_array_page(self):
        endpoint=REPO+"/rules/branches/main?per_page=100"
        original=self.api["GET "+endpoint]["body"]
        parent=copy.deepcopy(original[0]);parent.update(ruleset_id=900,ruleset_source_type="Organization",ruleset_source="parent")
        parent["parameters"]["required_approving_review_count"]=2
        self.put(endpoint,raw=json.dumps(original)+"\n"+json.dumps([parent]))
        self.put("orgs/parent/rulesets/900",dict(id=900,source_type="Organization",source="parent",enforcement="active",bypass_actors=[dict(actor_id=77,actor_type="Integration",bypass_mode="always")]))
        result=self.sensor();self.assertEqual(0,result.returncode,result.stderr)
        self.assertIn("count=2",result.stdout);self.assertIn("Integration:77:always",result.stdout)
        self.assertTrue(any(x["endpoint"]=="orgs/parent/rulesets/900" for x in self.log))
        self.put(endpoint,original*50)
        self.assertEqual(3,self.sensor().returncode)

    def test_untyped_bypass_and_multidocument_profile_detail_refuse(self):
        self.put(REPO+"/rulesets/42",dict(id=42,bypass_actors=None))
        self.assertEqual(3,self.sensor(profile="solo").returncode)
        self.baseline();self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE",raw='{"value":"solo"}\n{"value":"team"}')
        self.assertEqual(3,self.sensor(profile=None).returncode)
        self.baseline();self.put(REPO+"/rulesets?per_page=100",[dict(id=42,name="scaffold-branch-protection",enforcement="active")])
        self.put(REPO+"/rulesets/42",raw=json.dumps(canonical())+"\n"+json.dumps(canonical()))
        self.assertNotEqual(0,self.setup("--reconcile").returncode);self.no_writes()

    def test_large_codeowners_placeholder_does_not_become_pipefail_absence(self):
        self.put(REPO+"/contents/.github/CODEOWNERS?ref=main",raw="# CUSTOMIZE replace owner\n"+"# padding1234567890\n"*15000+"* @fixture-maintainer\n")
        self.assertNotEqual(0,self.setup().returncode);self.no_writes()

    def test_single_maintainer_create_preview_and_persisted_sensor(self):
        self.baseline("single-maintainer")
        result=self.setup("--dry-run",profile="single-maintainer")
        self.assertEqual(0,result.returncode,result.stderr);self.assertEqual([],self.log)
        candidate=json.loads(result.stdout)
        self.assertEqual([],candidate["bypass_actors"])
        self.assertEqual(0,candidate["rules"][0]["parameters"]["required_approving_review_count"])
        result=self.setup(profile="single-maintainer");self.assertEqual(0,result.returncode,result.stderr)
        writes=[x for x in self.log if x["method"]!="GET"]
        self.assertEqual(["PATCH","POST"],[x["method"] for x in writes])
        self.assertEqual("single-maintainer",writes[0]["body"]["value"])
        self.assertEqual(0,self.sensor(profile=None).returncode)
        self.put(REPO+"/actions/variables/SCAFFOLD_GOVERNANCE_PROFILE",method="PATCH",rc=1)
        self.assertNotEqual(0,self.setup(profile="single-maintainer").returncode)
        self.assertFalse(any(x["method"]!="GET" and "/rulesets" in x["endpoint"] for x in self.log))

    def test_single_maintainer_reconcile_preserves_preimage_and_is_idempotent(self):
        self.baseline("solo")
        detail=canonical("solo")
        detail["rules"][0]["parameters"].update(allowed_merge_methods=["merge","squash","rebase"],required_reviewers=[],require_extra_approval_for_unattributed_changes=True)
        detail["rules"][1]["parameters"]["do_not_enforce_on_create"]=False
        self.put(REPO+"/rulesets?per_page=100",[dict(id=42,name=detail["name"],enforcement="active")])
        self.put(REPO+"/rulesets/42",detail)
        result=self.setup("--reconcile","--enforcement","active",profile="single-maintainer")
        self.assertEqual(0,result.returncode,result.stderr)
        body=next(x["body"] for x in self.log if x["method"]=="PUT")
        want={k:copy.deepcopy(detail[k]) for k in ("name","target","enforcement","bypass_actors","conditions","rules")}
        want["bypass_actors"]=[];want["rules"][0]["parameters"]["required_approving_review_count"]=0
        self.assertEqual(want,body)
        self.put(REPO+"/rulesets/42",dict(detail,**body))
        self.assertEqual(0,self.setup("--reconcile","--enforcement","active",profile="single-maintainer").returncode)
        self.assertEqual(["PATCH"],[x["method"] for x in self.log if x["method"]!="GET"])

    def test_single_maintainer_refuses_foreign_unknown_team_and_missing_reconcile(self):
        for change in (lambda d:d.update(source="other/repo"),lambda d:d.update(source_type="Organization"),
                       lambda d:d.update(custom_policy={}),lambda d:d["rules"][0]["parameters"].update(required_reviewers=None),
                       lambda d:d["rules"][0]["parameters"].update(require_extra_approval_for_unattributed_changes=False)):
            detail=canonical("solo");change(detail)
            self.put(REPO+"/rulesets?per_page=100",[dict(id=42,name=detail["name"],enforcement="active")])
            self.put(REPO+"/rulesets/42",detail)
            self.assertNotEqual(0,self.setup("--reconcile",profile="single-maintainer").returncode);self.no_writes()
        self.put(REPO+"/rulesets/42",canonical("team"))
        self.assertNotEqual(0,self.setup("--reconcile",profile="single-maintainer").returncode);self.no_writes()
        self.put(REPO+"/rulesets/42",canonical("solo"))
        self.assertNotEqual(0,self.setup(profile="single-maintainer").returncode);self.no_writes()

    def test_single_maintainer_residual_review_and_all_source_bypass_refuse(self):
        endpoint=REPO+"/rules/branches/main?per_page=100"
        for key,value in (("required_approving_review_count",1),("require_code_owner_review",True),
                          ("require_last_push_approval",True),("required_reviewers",[{"minimum_approvals":1,"file_patterns":["*"],"reviewer":{"type":"Team","id":7}}])):
            self.baseline("single-maintainer")
            self.api["GET "+endpoint]["body"][0]["parameters"][key]=value
            self.assertEqual(1,self.sensor(profile="single-maintainer").returncode,key)
        for malformed in (None,{},False,[{"minimum_approvals":"1"}]):
            self.baseline("single-maintainer")
            self.api["GET "+endpoint]["body"][0]["parameters"]["required_reviewers"]=malformed
            self.assertEqual(3,self.sensor(profile="single-maintainer").returncode)
        for index in (0,1):
            self.baseline("single-maintainer")
            row=self.api["GET "+endpoint]["body"][index]
            row.update(ruleset_id=77,ruleset_source_type="Organization",ruleset_source="parent")
            self.put("orgs/parent/rulesets/77",dict(id=77,source_type="Organization",source="parent",enforcement="active",
                bypass_actors=[dict(actor_id=1,actor_type="Integration",bypass_mode="always")]))
            self.assertEqual(1,self.sensor(profile="single-maintainer").returncode)

    def test_sensor_detail_origin_active_state_and_conflicting_origins_are_unknown(self):
        for change in (lambda d:d.update(source="other/repo"),lambda d:d.update(source_type="Organization"),lambda d:d.update(enforcement="disabled")):
            self.baseline("single-maintainer")
            change(self.api["GET "+REPO+"/rulesets/42"]["body"])
            result=self.sensor(profile="single-maintainer")
            self.assertEqual(3,result.returncode)
            self.assertIn("no_bypass_actors\tUNKNOWN",result.stdout)
        self.baseline("single-maintainer")
        self.api["GET "+REPO+"/rules/branches/main?per_page=100"]["body"][1]["ruleset_source"]="other/repo"
        self.assertEqual(3,self.sensor(profile="single-maintainer").returncode)

    def test_installed_onboarding_single_maintainer_commands_and_skip(self):
        adopter=self.installed_onboarding()
        self.baseline("single-maintainer")
        result=self.onboarding_command(adopter,"onboarding-ruleset-apply",ONBOARD_REPO="fixture/adopter",ONBOARD_CHECKS="lint,test",ONBOARD_PROFILE="single-maintainer",ONBOARD_CHOICE="active",ONBOARD_RULESET="new")
        self.assertEqual(0,result.returncode,result.stderr)
        body=next(x["body"] for x in self.log if x["method"]=="POST" and x["endpoint"].endswith("/rulesets"))
        self.assertEqual([],body["bypass_actors"])
        self.assertEqual(0,body["rules"][0]["parameters"]["required_approving_review_count"])
        result=self.onboarding_command(adopter,"onboarding-ruleset-apply",ONBOARD_CHOICE="skip")
        self.assertEqual(0,result.returncode,result.stderr);self.assertEqual([],self.log)


if __name__ == "__main__":
    unittest.main()
