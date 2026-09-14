"""Execute shipped procedures against real Git and explicitly synthetic ledgers."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
GUARD=ROOT/".github/scripts/worktree-preflight.sh"
RETRO=ROOT/".github/distribution/payload/.agents/skills/retro/SKILL.md"


class ProcedureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="source-procedure-");self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name).resolve();self.repo=self.work/"synthetic repository";self.repo.mkdir()
        self.env=dict(os.environ,GIT_CONFIG_NOSYSTEM="1",GIT_CONFIG_GLOBAL=os.devnull,GIT_OPTIONAL_LOCKS="0")
        self.git("-c","init.defaultBranch=main","init","-q")
        self.git("config","user.name","Synthetic Fixture");self.git("config","user.email","synthetic@example.invalid")
        self.git("config","gc.auto","0");self.git("config","maintenance.auto","false")
        (self.repo/"control.txt").write_text("keep this rule\nobsolete synthetic rule\nkeep another rule\n")
        (self.repo/"retro-log.md").write_text("# Synthetic history\n")
        self.git("add",".");self.git("commit","-qm","explicitly synthetic baseline")
        self.head=self.git("rev-parse","HEAD").stdout.strip()
        self.input=self.work/"synthetic-input.json";self.claims=self.work/"claims.json"
        self.claims.write_text(json.dumps({"claims":[{"writer":"fixture-worker","branch":"main","worktree":str(self.repo),"state":"active"}]}))
        self.sink=self.work/"forbidden.jsonl";self.sink.write_text("")
        self.bin=self.work/"bin";self.bin.mkdir();real_git=shutil.which("git")
        fake=self.bin/"git"
        fake.write_text("#!"+sys.executable+"\n"+"import os,sys,json,base64\na=sys.argv[1:]\n"
            "if 'SF_WORKTREES' in os.environ and 'worktree' in a and 'list' in a:\n"
            " sys.stdout.buffer.write(base64.b64decode(os.environ['SF_WORKTREES']));sys.exit(0)\n"
            "if any(x in a for x in ('push','remove','prune','unlock','--force','-f')):\n"
            " with open(os.environ['SF_SINK'],'a') as f:f.write(json.dumps(a)+'\\n')\n"
            " sys.exit(99)\n"+"os.execv("+repr(real_git)+",["+repr(real_git)+",*a])\n")
        fake.chmod(0o755)
        self.guarded_env=dict(self.env,PATH=str(self.bin)+os.pathsep+os.environ["PATH"],SF_SINK=str(self.sink))

    def git(self,*args,input=None):
        return subprocess.run(["git","-C",str(self.repo),*args],env=self.env,input=input,text=True,capture_output=True,check=True,timeout=15)

    def snapshot(self):
        return (self.git("rev-parse","HEAD").stdout,self.git("log","--format=%H").stdout,
                self.git("diff","--binary","HEAD").stdout,
                {str(p.relative_to(self.repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.repo.rglob("*") if p.is_file()})

    def guard(self,action,branch="main"):
        before=self.snapshot()
        result=subprocess.run(["bash",str(GUARD),"--target",str(self.repo),"--branch",branch,"--writer","fixture-worker", "--claims",str(self.claims),"--action",action],env=self.guarded_env,text=True,capture_output=True,timeout=15)
        self.assertEqual(before,self.snapshot());self.assertEqual("",self.sink.read_text())
        return result

    def block(self,name,record):
        self.input.write_text(json.dumps(record))
        match=re.search(r"<!-- BEGIN "+re.escape(name)+r" -->\n```bash\n(.*?)\n```\n<!-- END "+re.escape(name)+r" -->",RETRO.read_text(),re.S)
        self.assertIsNotNone(match,"named production Skill block missing")
        return subprocess.run(["bash","-c",match.group(1)],env=dict(self.guarded_env,RETRO_INPUT=str(self.input),RETRO_TARGET=str(self.repo)),text=True,capture_output=True,timeout=15)

    def test_w003_detached_push_refuses_and_preserves_recovery(self):
        self.git("checkout","--detach","-q")
        (self.repo/"control.txt").write_text("uncommitted tracked recovery\n")
        (self.repo/"handoff.txt").write_text("untracked synthetic recovery information\n")
        result=self.guard("push")
        self.assertNotEqual(0,result.returncode);self.assertIn("detached",result.stdout+result.stderr)

    def test_w004_occupied_branch_and_duplicate_claim_refuse(self):
        other=self.work/"other worktree"
        self.git("worktree","add","-qb","occupied",str(other))
        self.assertNotEqual(0,self.guard("claim","occupied").returncode)
        result=self.guard("push");self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        claims=json.loads(self.claims.read_text());claims["claims"].append(dict(claims["claims"][0],writer="other-worker"))
        self.claims.write_text(json.dumps(claims))
        self.assertNotEqual(0,self.guard("push").returncode)

    def test_w005_missing_handoff_warns_without_cleanup(self):
        (self.repo/"handoff.txt").write_text("https://example.invalid/exists-is-not-authorization\n")
        result=self.guard("archive")
        self.assertEqual(3,result.returncode);self.assertIn("WARNING",result.stdout)
        self.assertTrue((self.repo/"handoff.txt").exists())

    def test_w004_malformed_or_missing_inventory_is_not_occupancy_proof(self):
        import base64
        real=self.git("worktree","list","--porcelain","-z").stdout
        for raw in ("", "garbage\0", real.rstrip("\0"), real.replace(str(self.repo),str(self.work/"absent")),
                    real+"worktree /synthetic/other\0HEAD "+self.head+"\0branch garbage\0\0", "locked\0"+real, "detached\0"+real):
            with self.subTest(raw=raw):
                self.guarded_env["SF_WORKTREES"]=base64.b64encode(raw.encode()).decode()
                self.assertNotEqual(0,self.guard("push").returncode)
        self.guarded_env.pop("SF_WORKTREES")

    def candidate(self):
        return dict(origin="synthetic",candidate="synthetic-candidate-1",friction="same fixture failure",
                    occurrences=[dict(id="synthetic-event-1",friction="same fixture failure",evidence="https://example.invalid/synthetic/1",root_cause="missing precise guard")])

    def test_p007_occurrences_require_distinct_evidence_and_produce_candidate_only(self):
        record=self.candidate()
        first=json.loads(self.block("retro-candidate-review",record).stdout)
        self.assertEqual("candidate",first["state"]);self.assertEqual(1,first["occurrences"])
        record["occurrences"].append(dict(record["occurrences"][0],id="synthetic-event-2"))
        duplicate=json.loads(self.block("retro-candidate-review",record).stdout)
        self.assertEqual("candidate",duplicate["state"])
        record["occurrences"][1]["evidence"]="https://example.invalid/synthetic/2"
        result=self.block("retro-candidate-review",record);self.assertEqual(0,result.returncode,result.stderr)
        ready=json.loads(result.stdout)
        self.assertEqual("promotion-ready",ready["state"]);self.assertEqual(2,ready["occurrences"])
        self.assertEqual("pending-human-independence-and-adoption-review",ready["review"])
        self.assertEqual(2,len(ready["evidence"]));self.assertEqual("synthetic",ready["origin"])

    def retirement(self):
        blob=self.git("rev-parse","HEAD:control.txt").stdout.strip()
        return dict(origin="synthetic",control=dict(id="synthetic-control",path="control.txt",blob=blob,
            line="obsolete synthetic rule",reason="redundant with retained synthetic guard",evidence=["https://example.invalid/synthetic/control-review"]),
            decision=dict(action="retire",control="synthetic-control",path="control.txt",blob=blob,line="obsolete synthetic rule",actor="synthetic-owner",
                          reference="https://example.invalid/synthetic/owner-decision"),log_path="retro-log.md")

    def test_p012_evidence_and_exact_decision_required_before_bounded_diff(self):
        for mutation in (lambda x:x["control"].update(evidence=[]),lambda x:x.pop("decision"),
                         lambda x:x["decision"].update(control="another-control"),
                         lambda x:x["decision"].update(path="other-control.txt"),
                         lambda x:x["decision"].update(line="keep this rule"),
                         lambda x:x["control"].update(path="--help"),lambda x:x.update(log_path="--help"),
                         lambda x:x["decision"].update(blob="0"*40),lambda x:x["control"].update(reason="")):
            record=self.retirement();mutation(record);before=self.snapshot()
            result=self.block("retro-retirement-diff",record)
            self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())
        record=self.retirement();before=self.snapshot();result=self.block("retro-retirement-diff",record)
        self.assertEqual(0,result.returncode,result.stderr);self.assertEqual(before,self.snapshot())
        self.assertIn("-obsolete synthetic rule",result.stdout)
        # Apply only to this explicitly synthetic disposable repository. The
        # production block itself emits a reviewable diff and does not apply it.
        self.git("apply","--check","-",input=result.stdout);self.git("apply","-",input=result.stdout)
        self.assertEqual("keep this rule\nkeep another rule\n",(self.repo/"control.txt").read_text())
        self.assertIn("synthetic-owner",(self.repo/"retro-log.md").read_text())
        self.assertIn(record["decision"]["reference"],(self.repo/"retro-log.md").read_text())
        self.assertIn("obsolete synthetic rule",self.git("show",self.head+":control.txt").stdout)
        self.assertEqual("",self.sink.read_text())

    def test_p012_existing_option_paths_and_same_blob_wrong_target_refuse(self):
        data=(self.repo/"control.txt").read_bytes()
        (self.repo/"--help").write_bytes(data);(self.repo/"other-control.txt").write_bytes(data)
        self.git("add","--","--help","other-control.txt");self.git("commit","-qm","synthetic ambiguous-path controls")
        for kind in ("control-option","log-option","same-blob-other-path","other-line"):
            record=self.retirement()
            if kind=="control-option":record["control"]["path"]="--help";record["decision"]["path"]="--help"
            elif kind=="log-option":record["log_path"]="--help"
            elif kind=="same-blob-other-path":record["control"]["path"]="other-control.txt"
            else:record["control"]["line"]="keep this rule"
            with self.subTest(kind=kind):
                before=self.snapshot();result=self.block("retro-retirement-diff",record)
                self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())


if __name__=="__main__":unittest.main()
