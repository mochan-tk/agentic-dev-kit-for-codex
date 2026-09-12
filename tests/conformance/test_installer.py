"""Disposable-adopter regressions derived from the frozen scaffold installer tests."""

import hashlib
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / ".github/scripts/scaffold-init.sh"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"
KICKOFF_BASE = "219202b28c980e417283d761dbd8515c8b38e69f"
KICKOFF_PATHS = (".agents/skills/context-collection/SKILL.md",
                 ".github/connectors/builtin.md", "README.md")
TASK_CREATION_BASE = "7565593f470fa6515a138c730f2545595cbd888f"
TASK_CREATION_PATHS = (".agents/skills/plan-management/SKILL.md",
                       ".agents/skills/plan-management/scripts/new-task.sh")
SOURCE_REGISTRY_PATH = ".github/scripts/setup-sources.sh"
TASK_SELECTION_BASE = "4e62351d3c053e6c72cc1d295df5567245340014"
TASK_SELECTION_ACCEPTED = "d396865c0f5e23fa01bb790242835dda482d679d"
RITUAL_PATH = ".github/scripts/check-task-ritual.sh"
RITUAL_PATHS = (RITUAL_PATH, ".agents/skills/verification/SKILL.md")
RITUAL_INITIAL_HEAD = "a49847680ba39a2d901ae9b309bf72142ac9e46c"
AUDIT_PAYLOAD_PATHS = (
    ".agents/skills/project-onboarding/SKILL.md", ".github/codex-instructions.md",
    ".github/connectors/speckit.md", ".github/scripts/setup-ruleset.sh",
    SOURCE_REGISTRY_PATH, ".github/scripts/tuning-status.sh",
)
TASK_SELECTION_PATHS = (".agents/skills/plan-management/SKILL.md",
                        ".agents/skills/plan-management/scripts/frontier.sh",
                        ".github/scripts/ownership-overlap.sh",
                        ".github/scripts/check-task-ritual.sh")
REGISTRY_REL = ".github/docs/context/SOURCES.md"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-installer-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.target = self.base / "adopter with spaces"
        self.target.mkdir()
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(self.target)], check=True)

    def run_install(self, *args, source=ROOT, target=None):
        env = dict(os.environ, SCAFFOLD_SOURCE_DIR=str(source), LC_ALL="C")
        return subprocess.run(["bash", str(INSTALLER), *args, str(target or self.target)], env=env,
                              capture_output=True, text=True, timeout=30)

    def snapshot(self, root):
        if not root.exists():
            return None
        return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
                else ("file", hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file()
                else ("directory", "") for p in root.rglob("*")}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.target), *args], text=True).strip()

    def commit_adopter(self, message):
        self.git("add", "--all")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def adoption_fixture(self, *, initial=False, preserved=False, tune=True, application=False,
                         anchor=None, head_anchor=None):
        (self.target / "existing.txt").write_text("existing adopter file\n")
        if preserved:
            for name in ("AGENTS.md", "README.md", "SCAFFOLD-CHANGELOG.md"):
                (self.target / name).write_text("adopter-owned " + name + "\n")
        before_install = self.commit_adopter("before adoption")
        self.assertEqual(0, self.run_install("--apply").returncode)
        anchor_path = self.target / ".agents/skills/plan-management/scripts/frontier.sh"
        if anchor is not None:
            anchor_path.write_bytes(anchor)
        adopted = self.commit_adopter("adopt reviewed local payload")
        if initial:
            return before_install, adopted
        if tune:
            path = self.target / ".github/codex-instructions.md"
            path.write_text(path.read_text().replace("CUSTOMIZE", "CONFIGURED"))
        if application:
            (self.target / "application.py").write_text("print('application change')\n")
        if head_anchor is not None:
            anchor_path.write_bytes(head_anchor)
        if not tune and not application:
            (self.target / "existing.txt").write_text("ordinary work\n")
        return adopted, self.commit_adopter("onboarding candidate")

    def ritual(self, base, head, *, initial=False, defect=None, ordinary=False):
        # GitHub projections are fixtures derived from real local Git objects.
        # The fake transports data only; all proof decisions remain in the helper.
        if ordinary:
            # Ordinary proof uses real queries/raw JSON, never bootstrap trees.
            return self.packaged_json(RITUAL_PATH, self.ordinary_records(), '1', installed=True)
        prefix = "repos/{owner}/{repo}"
        replies = {}
        def reply(endpoint, query, output, rc=0):
            replies[endpoint + "\n" + query] = [rc, output]
        meta = prefix + "/pulls/1"
        helper = (self.target / RITUAL_PATH).read_text()
        pr_query = helper.split("pr_query='", 1)[1].split("'", 1)[0]
        reply(meta, pr_query, '\t'.join(['1', base, head, 'fixture-branch', '1',
                                       'fixture/adopter', 'b', 'owner', 'User']))
        for query, value in {
            '[.user.login, .user.type] | @tsv': 'owner\tUser',
            '.body // ""': ('Refs #2\nPlan: https://github.com/fixture/adopter/issues/2#issuecomment-3'
                           if ordinary else ''), '.base.ref': 'main', '.base.sha': base,
            '.head.sha': head, '.title // ""': 'adopt source-first kit' if initial else 'scaffold: onboard fixture',
            '[.base.sha, .head.sha] | @tsv': base + '\t' + head,
        }.items(): reply(meta, query, value)
        for ref in (base, head):
            tree = self.git("show", "-s", "--format=%T", ref)
            reply(prefix + "/git/commits/" + ref, '.tree.sha', tree)
            rows = []
            for line in self.git("ls-tree", "-rt", ref).splitlines():
                metadata, name = line.split("\t", 1)
                mode, kind, oid = metadata.split()
                rows.append("\t".join((name, mode, kind, oid)))
                if kind == "blob":
                    data = subprocess.check_output(["git", "-C", str(self.target), "cat-file", "blob", oid])
                    reply(prefix + "/git/blobs/" + oid, '.encoding', 'base64')
                    reply(prefix + "/git/blobs/" + oid, '.content | type', 'string')
                    reply(prefix + "/git/blobs/" + oid, '.content', base64.b64encode(data).decode())
            endpoint = prefix + "/git/trees/" + tree + "?recursive=1"
            header = tree + "\tstring\tfalse\tboolean\tarray"
            if ref == base and defect == "truncated": header = tree + "\tstring\ttrue\tboolean\tarray"
            if ref == base and defect == "header-type": header = tree + "\tstring\tfalse\tstring\tarray"
            if ref == base and defect == "duplicate": rows.append(rows[0])
            if ref == base and defect == "symlink":
                rows = [line.replace("\t100644\tblob\t", "\t120000\tblob\t")
                        if line.startswith(".agents/skills/plan-management/scripts/frontier.sh\t") else line for line in rows]
            if ref == base and defect == "missing-anchor":
                rows = [line for line in rows if not line.startswith(
                    ".agents/skills/plan-management/scripts/frontier.sh\t")]
            reply(endpoint, '[.sha, (.sha | type), .truncated, (.truncated | type), (.tree | type)] | @tsv', header,
                  1 if defect == "read-error" and ref == base else 0)
            reply(endpoint, 'if all(.tree[]; ([.path, .mode, .type, .sha] | all(.[]; type == "string"))) then .tree[] | [.path, .mode, .type, .sha] | @tsv else error("invalid tree field type") end', "\n".join(rows),
                  1 if ref == base and defect == "entry-type" else 0)
        # Baseline consumer compatibility, including its incorrect error-as-absence path.
        for name in ("AGENTS.md", "SCAFFOLD-CHANGELOG.md", ".github/codex-instructions.md"):
            endpoint = prefix + "/contents/" + name + "?ref=main"
            exists = subprocess.run(["git", "-C", str(self.target), "cat-file", "-e", base + ":" + name],
                                    capture_output=True).returncode == 0
            if exists:
                data = subprocess.check_output(["git", "-C", str(self.target), "show", base + ":" + name])
                reply(endpoint, '.content', base64.b64encode(data).decode())
                reply(endpoint, '.sha', self.git("rev-parse", base + ":" + name),
                      1 if defect == "read-error" and name == "AGENTS.md" else 0)
            else:
                reply(endpoint, '.content', '', 1); reply(endpoint, '.sha', '', 1)
        added = self.git("diff", "--name-only", "--diff-filter=A", base, head).splitlines()
        if defect == "read-error": added = ["AGENTS.md", ".github/codex-instructions.md"]
        reply(meta + "/files?per_page=100", '[.[] | select(.status == "added") | .filename]', json.dumps(added))
        if defect == "blob-error":
            oid = self.git("rev-parse", base + ":.github/codex-instructions.md")
            reply(prefix + "/git/blobs/" + oid, '.content', '', 1)
        if defect in ("blob-type", "blob-content"):
            oid = self.git("rev-parse", base + ":.github/codex-instructions.md")
            reply(prefix + "/git/blobs/" + oid,
                  '.content | type' if defect == "blob-type" else '.content',
                  'array' if defect == "blob-type" else base64.b64encode(b"altered\n").decode())
        fake = self.base / "ritual-bin"
        fake.mkdir(exist_ok=True)
        records = self.base / "github-fixture.json"
        records.write_text(json.dumps(replies))
        gh = fake / "gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
if len(args)<4 or args[0]!='api' or '--jq' not in args: sys.exit(91)
query=args[args.index('--jq')+1]
value=json.load(open(os.environ['GITHUB_FIXTURE'])).get(args[1]+'\\n'+query)
if value is None: sys.exit(92)
print(value[1]); sys.exit(value[0])
""")
        gh.chmod(0o755)
        if defect == "entry-error":
            awk = fake / "awk"
            base_oid = self.git("rev-parse", base + ":.github/codex-instructions.md")
            awk.write_text("#!/usr/bin/env python3\nimport subprocess,sys\n"
                "data=sys.stdin.buffer.read()\n"
                "if any(arg in ('path=AGENTS.md','path=.github/codex-instructions.md') for arg in sys.argv[1:]) and "
                + repr(base_oid.encode()) + " in data: sys.exit(93)\n"
                "sys.exit(subprocess.run(['/usr/bin/awk',*sys.argv[1:]],input=data).returncode)\n")
            awk.chmod(0o755)
        return subprocess.run(["bash", ".github/scripts/check-task-ritual.sh", "1"],
            cwd=self.target, env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"],
                GITHUB_FIXTURE=str(records), RITUAL_API_RETRY_DELAY="0"),
            capture_output=True, text=True, timeout=15)

    def test_f1_installed_documented_invocations_use_0644_helpers(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        skill = (self.target / ".agents/skills/project-onboarding/SKILL.md").read_text()
        command = re.search(r"Then run `([^`]+)`", skill).group(1)
        helper = self.target / ".github/scripts/tuning-status.sh"
        self.assertEqual(0o644, helper.stat().st_mode & 0o777)
        try:
            result = subprocess.run(shlex.split(command), cwd=self.target,
                                    capture_output=True, text=True, timeout=5)
        except PermissionError:
            self.fail("documented direct execution fails against installed 0644 helper")
        self.assertEqual(1, result.returncode, result.stderr)  # actually runs, reports untuned.
        self.assertIn("CUSTOMIZE", result.stdout)
        command = re.search(r"Run `([^`]*setup-labels\.sh)`", skill).group(1)
        fake = self.base / "documented-bin"
        fake.mkdir()
        calls = self.base / "documented-calls"
        gh = fake / "gh"
        gh.write_text('#!/bin/sh\nprintf "called\\n" >> "$FIXTURE_CALLS"\nexit 1\n')
        gh.chmod(0o755)
        self.assertEqual(0o644, (self.target / '.github/scripts/setup-labels.sh').stat().st_mode & 0o777)
        result = subprocess.run(shlex.split(command), cwd=self.target,
            env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ['PATH'], FIXTURE_CALLS=str(calls)),
            capture_output=True, text=True, timeout=5)
        self.assertEqual(1, result.returncode)
        self.assertEqual('called\n', calls.read_text())  # stopped at the fake authentication probe.

    def test_f2_fresh_adoption_then_taskless_onboarding(self):
        base, head = self.adoption_fixture()
        result = self.ritual(base, head)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("onboarding evidence PR", result.stdout)

    def test_f2_initial_adoption_read_error_is_not_absence(self):
        base, head = self.adoption_fixture()
        result = self.ritual(base, head, defect="read-error")
        self.assertNotEqual(0, result.returncode, result.stdout)

    def test_f2_initial_adoption_has_complete_structural_proof(self):
        base, head = self.adoption_fixture(initial=True)
        self.assertEqual(0, self.ritual(base, head, initial=True).returncode)

    def test_f2_preserved_adopter_records_do_not_block_real_adoption(self):
        base, head = self.adoption_fixture(preserved=True)
        for name in ("AGENTS.md", "README.md", "SCAFFOLD-CHANGELOG.md"):
            self.assertEqual("adopter-owned " + name + "\n", (self.target / name).read_text())
        result = self.ritual(base, head)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_f2_title_only_and_application_work_do_not_get_onboarding_exception(self):
        base, head = self.adoption_fixture(tune=False, application=True)
        self.assertNotEqual(0, self.ritual(base, head).returncode)
        instructions = self.target / ".github/codex-instructions.md"
        instructions.write_text(instructions.read_text().replace("CUSTOMIZE", "CONFIGURED"))
        head = self.commit_adopter("tuning does not hide application work")
        self.assertNotEqual(0, self.ritual(base, head).returncode)

    def test_f2_invalid_or_unreadable_proof_is_non_success(self):
        base, head = self.adoption_fixture()
        for defect in ("truncated", "duplicate", "symlink", "blob-error", "missing-anchor",
                       "blob-type", "blob-content", "entry-error", "header-type", "entry-type"):
            with self.subTest(defect=defect):
                self.assertNotEqual(0, self.ritual(base, head, defect=defect).returncode)

    def test_f2_changed_output_symlink_does_not_get_onboarding_exception(self):
        base, _ = self.adoption_fixture()
        (self.target / '.github/docs/context/unsafe').symlink_to('../../../existing.txt')
        head = self.commit_adopter('unsafe onboarding output')
        self.assertNotEqual(0, self.ritual(base, head).returncode)

    def test_f2_normal_task_uses_ritual_without_bootstrap_proof(self):
        base, head = self.adoption_fixture(tune=False, application=True)
        result = self.ritual(base, head, defect="read-error", ordinary=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('ritual in order', result.stdout)

    def packaged_json(self, helper, records, *args, installed=False):
        # Execute the helper's actual --jq expression against raw GitHub JSON.
        # No preprojected IDs/markers can hide a broken query in these fixtures.
        self.assertIsNotNone(shutil.which("jq"), "real jq is required for helper regressions")
        fake = self.base / "json-bin"
        fake.mkdir(exist_ok=True)
        fixture = self.base / "raw-github.json"
        fixture.write_text(json.dumps(records))
        calls = self.base / "raw-github-calls.jsonl"
        calls.write_text("")
        gh = fake / "gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, subprocess, sys
args=sys.argv[1:]
records=json.load(open(os.environ['RAW_GITHUB_FIXTURE']))
call_path=os.environ['RAW_GITHUB_CALLS']
previous=[json.loads(line) for line in open(call_path)]
with open(call_path,'a') as stream: stream.write(json.dumps(args)+'\\n')
if args[:2] == ['issue','list']:
    value=records['list']
    if value is None: sys.exit(90)
    print(value, end=''); sys.exit(0)
if args[:2] == ['auth','status']: sys.exit(0)
if args[:2] == ['repo','view']:
    key='repository'
    records.setdefault(key, {'url':'https://github.com/fixture/adopter','nameWithOwner':'fixture/adopter'})
elif args[0] == 'api':
    method=args[args.index('--method')+1] if '--method' in args else args[args.index('-X')+1] if '-X' in args else 'GET'
    if method!='GET' or any(x in args for x in ('-f','-F','--field','--raw-field','--input')): sys.exit(94)
    key=args[1].split('?')[0]
elif args[:2] == ['issue','view']:
    repo=args[args.index('--repo')+1] if '--repo' in args else args[args.index('-R')+1] if '-R' in args else 'fixture/adopter'
    key=repo+'#'+args[2]+':'+args[args.index('--json')+1]
    host=records.get('repository',{}).get('url','https://github.com/fixture/adopter').split('/')[2]
    def canonical(value):
        return (host+'/'+value if value.split('#')[0].count('/')==1 else value).lower()
    records={canonical(k) if '#' in k else k:v for k,v in records.items()}
    key=canonical(key)
else: sys.exit(91)
if key not in records or records[key] is None: sys.exit(92)
if '--jq' not in args: sys.exit(93)
value=records[key]
if isinstance(value,dict) and '__responses__' in value:
    count=sum(1 for old in previous if old[:1]==['api'] and old[1].split('?')[0]==key)
    value=value['__responses__'][min(count,len(value['__responses__'])-1)]
if value is None: sys.exit(92)
pages=value.get('__pages__') if isinstance(value,dict) else None
if pages is None: pages=[value]
if '--paginate' not in args: pages=pages[:1]
if '--slurp' in args: pages=[pages]
for page in pages:
    if isinstance(page,dict) and '__error__' in page:
        print('synthetic transport error',file=sys.stderr); sys.exit(95)
    result=subprocess.run(['jq','-r',args[args.index('--jq')+1]],input=json.dumps(page),text=True)
    if result.returncode: sys.exit(result.returncode)
sys.exit(0)
""")
        gh.chmod(0o755)
        result = subprocess.run(["bash", str((self.target if installed else ROOT / PAYLOAD) / helper), *args], cwd=self.target,
            env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"],
                     RAW_GITHUB_FIXTURE=str(fixture), RAW_GITHUB_CALLS=str(calls), RITUAL_API_RETRY_DELAY="0"),
            capture_output=True, text=True, timeout=15)
        self.last_gh_calls = [json.loads(line) for line in calls.read_text().splitlines()]
        return result

    def test_ownership_lexical_aliases_never_report_disjoint(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        for path in ('src/./target.py', 'src//target.py', './src/./target.py',
                     'src///target.py', 'src/./**'):
            with self.subTest(path=path):
                records = {'fixture/adopter#1:body': {'body': '## File ownership\n\n- ' + path + '\n'},
                           'fixture/adopter#2:body': {'body': '## File ownership\n\n- src/target.py\n'}}
                result = self.packaged_json(TASK_SELECTION_PATHS[2], records, '-R', 'fixture/adopter', '1', '2', installed=True)
                self.assertIn(result.returncode, (1, 3), result.stdout + result.stderr)
                self.assertNotIn('NO_OVERLAP', result.stdout)

    def test_ownership_preserves_ordinary_glob_and_refusal_results(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        for left, right, expected in (
            ('src/a.py', 'src/a.py', 1), ('./src/a.py', 'src/a.py', 1),
            ('src/a.py', 'test/a.py', 0), ('src/**', 'src/a.py', 1),
            ('**/a.py', 'other/a.py', 1), ('src/[ab].py', 'src/a.py', 1),
            ('../src/a.py', 'src/a.py', 3), ('src/../a.py', 'src/a.py', 3),
            ('/src/a.py', 'src/a.py', 3), ('C:/src/a.py', 'src/a.py', 3),
            ('`broken', 'src/a.py', 3), ('', 'src/a.py', 3)):
            with self.subTest(left=left, right=right):
                records = {f'fixture/adopter#{n}:body': {'body': '## File ownership\n\n- ' + path + '\n'}
                           for n, path in ((1, left), (2, right))}
                result = self.packaged_json(TASK_SELECTION_PATHS[2], records, '-R', 'fixture/adopter', '1', '2', installed=True)
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                self.assertEqual(expected == 0, 'NO_OVERLAP' in result.stdout)

    def test_frontier_mixed_dependency_identity_never_publishes(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        local = [{'number': 3}, {'number': 3, 'repository': {'nameWithOwner': 'Fixture/Adopter'}},
                 {'number': 3, 'url': 'https://GitHub.Com/fixture/adopter/issues/3'}]
        cross = [{'number': 3, 'repository': {'name': 'dependency', 'owner': {'login': 'other'}}},
                 {'number': 3, 'url': 'https://github.com/Other/Dependency/issues/3'}]
        for nodes in ([local[0], local[1]], [local[0], local[2]], [local[1], local[2]], cross):
            for shape in ('connection', 'legacy-array'):
                with self.subTest(nodes=nodes, shape=shape):
                    blockers = {'nodes': nodes, 'totalCount': 2} if shape == 'connection' else nodes
                    records = {'list': '1\tReady\n2\tAmbiguous\n',
                               'fixture/adopter#1:blockedBy': {'blockedBy': []},
                               'fixture/adopter#2:blockedBy': {'blockedBy': blockers}}
                    for repo in ('fixture/adopter', 'Fixture/Adopter', 'github.com/fixture/adopter',
                                 'GitHub.Com/fixture/adopter', 'other/dependency', 'github.com/Other/Dependency'):
                        records[repo + '#3:state'] = {'state': 'CLOSED'}
                    result = self.packaged_json(TASK_SELECTION_PATHS[1], records, '-R', 'fixture/adopter', installed=True)
                    self.assertNotEqual(0, result.returncode, result.stdout)
                    self.assertEqual('', result.stdout)

    def test_task_creation_fake_transport_uses_actual_arguments_and_body(self):
        command, env, state, _events = self.task_creation_inputs(ready=False)
        body = self.base / 'actual transport body.md'
        body.write_bytes(b'Actual transport bytes\r\n\n')
        create = ['gh', 'issue', 'create', '--repo', 'github.com/fixture/adopter', '--title', 'Actual title',
                  '--body-file', str(body), '--parent', '11', '--blocked-by', '18,19', '--label', 'type:task,exec:ide']
        result = subprocess.run(create, env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        issue = json.loads(state.read_text())['issue']
        self.assertEqual('Actual transport bytes\r\n\n', issue['body'])
        self.assertEqual('Actual title', issue['title'])
        self.assertEqual(11, issue['parent']['number'])
        self.assertEqual([18, 19], [node['number'] for node in issue['blockedBy']['nodes']])
        self.assertEqual(['type:task', 'exec:ide'], [label['name'] for label in issue['labels']])
        result = subprocess.run(['gh', 'issue', 'edit', '40', '--repo', 'github.com/fixture/adopter',
                                 '--add-label', 'needs:human'], env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        names = {label['name'] for label in json.loads(state.read_text())['issue']['labels']}
        self.assertIn('needs:human', names)
        self.assertNotIn('ai:ready', names)

    def test_task_creation_fake_transport_detects_broken_helper_copies(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        helper = self.target / TASK_CREATION_PATHS[1]
        original = helper.read_text()
        for before, after in (
            ('--body-file "$WORK/body"', '--body-file /dev/null'),
            ('--body-file "$WORK/body"', '--body-file "$WORK/repo"'),
            ('--add-label ai:ready', '--add-label needs:human'),
        ):
            with self.subTest(mutation=after):
                self.assertIn(before, original)
                helper.write_text(original.replace(before, after))
                result, events = self.task_creation_fixture(installed=True)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertNotIn('Created and verified', result.stdout)
                self.assertEqual(1, sum(event[:2] == ['issue', 'create'] for event in events))
        helper.write_text(original)
        result, _events = self.task_creation_fixture(installed=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_task_creation_snapshot_survives_later_caller_body_edit(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        body = '## File ownership\n\n- src/**\n\n## Notes\n\n日本語\n\n'
        command, env, state, _events = self.task_creation_inputs('caller-body-drift', installed=True, body=body)
        result = subprocess.run(command, cwd=self.target, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(body, json.loads(state.read_text())['issue']['body'])
        self.assertEqual('Later caller edit\n', (self.base / 'task body.md').read_text())

    def ordinary_records(self, identifier="6af9582d-42d1-425d-82c8-f9ec651225a8", *, defect=None, count=1):
        prefix = 'repos/{owner}/{repo}'
        def comment(body, minute):
            stamp = f'2026-01-01T00:{minute:02}:00Z'
            return {'id': minute + 2, 'body': body, 'created_at': stamp, 'updated_at': stamp,
                    'issue_url': 'https://api.github.com/repos/fixture/adopter/issues/2'}
        dispatch = f'Dispatching worker: Task #2 worker (session {identifier}), branch codex/task-2-fix'
        comments = [comment('Starting in session fixture-supervisor', 0),
                    comment('## Plan\nImplement the bounded Task.', 1), comment(dispatch, 2)]
        body = 'Refs #2\nPlan: https://github.com/fixture/adopter/issues/2#issuecomment-3'
        if defect == 'wrong-branch': comments[2]['body'] = dispatch.replace('task-2-fix', 'task-4-fix')
        if defect == 'edited': comments[2]['updated_at'] = '2026-01-01T00:03:00Z'
        if defect == 'early': comments[2] = comment(dispatch, 0)
        if defect == 'late': comments[2] = comment(dispatch, 6)
        if defect == 'claim-after-plan': comments[0] = comment(comments[0]['body'], 2)
        if defect in ('replacement', 'missing-release', 'edited-release'):
            if defect != 'missing-release': comments.append(comment('Releasing worker: prior attempt', 3))
            if defect == 'edited-release': comments[-1]['updated_at'] = '2026-01-01T00:04:00Z'
            comments.append(comment(dispatch, 4))
        if defect == 'missing-session': comments[2]['body'] = dispatch.replace(f' (session {identifier})', '')
        if defect == 'duplicate-session': comments[2]['body'] = dispatch + ' (session deadbeef)'
        if defect == 'wrong-plan-repo': body = body.replace('fixture/adopter/issues', 'other/repo/issues')
        if defect == 'wrong-plan-issue': body = body.replace('/issues/2#', '/issues/4#')
        if defect == 'missing-plan-link': body = 'Refs #2'
        records = {
            prefix + '/pulls/1': {'number': 1, 'user': {'login': 'owner', 'type': 'User'}, 'body': body,
                                 'title': 'Task fixture', 'commits': count,
                                 'base': {'sha': 'a' * 40, 'ref': 'main', 'repo': {'full_name': 'fixture/adopter'}},
                                 'head': {'ref': 'codex/task-2-fix', 'sha': f'{count:040x}'}},
            prefix + '/issues/2/comments': comments,
            prefix + '/pulls/1/commits': [{'sha': f'{i + 1:040x}', 'commit': {
                'committer': {'date': '2026-01-01T00:05:00Z'}}} for i in range(count)],
            prefix + '/issues/2': {'number': 2, 'state': 'open', 'body': 'Task fixture',
                                    'comments': len(comments), 'labels': [{'name': 'type:task'}]},
            prefix: {'full_name': 'fixture/adopter'},
            prefix + '/issues/comments/3': copy.deepcopy(comments[1]),
        }
        if defect == 'wrong-plan-resolution': records[prefix + '/issues/comments/3']['issue_url'] = 'issues/4'
        if defect == 'non-plan-comment': records[prefix + '/issues/comments/3']['body'] = 'Starting in session fixture'
        if defect == 'missing-task-label': records[prefix + '/issues/2']['labels'] = []
        return records

    def ordinary_ritual(self, identifier="6af9582d-42d1-425d-82c8-f9ec651225a8", *, defect=None):
        return self.packaged_json(RITUAL_PATH, self.ordinary_records(identifier, defect=defect), '1')

    def assert_ritual_refuses(self, records):
        result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn('PASS:', result.stdout + result.stderr)
        return result

    def test_ritual_commit_collection_fail_closed(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        pr = 'repos/{owner}/{repo}/pulls/1'
        for defect in ('empty', 'missing-date', 'mixed-missing-date', 'invalid-date', 'false-date',
                       'duplicate', 'missing-head', 'count-mismatch', 'oversize', 'non-array',
                       'partial-page', 'failed-page'):
            with self.subTest(defect=defect):
                records = self.ordinary_records(count=2)
                commits = records[pr + '/commits']
                if defect == 'empty': records[pr + '/commits'] = []
                if defect in ('missing-date', 'mixed-missing-date'):
                    commits[0]['commit'] = {}
                    if defect == 'missing-date': commits[1]['commit'] = {}
                if defect in ('invalid-date', 'false-date'):
                    commits[0]['commit'] = {'committer': {'date': '2026-02-30T00:05:00Z' if defect == 'invalid-date' else False},
                                             'author': {'date': '2026-01-01T00:05:00Z'}}
                if defect == 'duplicate': commits[0]['sha'] = commits[1]['sha']
                if defect == 'missing-head': records[pr]['head']['sha'] = 'f' * 40
                if defect == 'count-mismatch': records[pr]['commits'] = 3
                if defect == 'oversize': records[pr]['commits'] = 251
                if defect == 'non-array': records[pr + '/commits'] = {'unexpected': commits[0]}
                if defect == 'partial-page': records[pr + '/commits'] = {'__pages__': [commits[:1]]}
                if defect == 'failed-page': records[pr + '/commits'] = {'__pages__': [commits[:1], {'__error__': True}]}
                self.assert_ritual_refuses(records)

    def test_ritual_pr_snapshot_drift_refuses(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        pr = 'repos/{owner}/{repo}/pulls/1'
        for field in ('head', 'base', 'ref', 'body', 'count', 'repository', 'unavailable'):
            with self.subTest(field=field):
                records = self.ordinary_records()
                changed = copy.deepcopy(records[pr])
                if field in ('head', 'base'): changed[field]['sha'] = 'f' * 40
                if field == 'ref': changed['head']['ref'] = 'codex/other'
                if field == 'body': changed['body'] += '\nChanged Task plan context.'
                if field == 'count': changed['commits'] = 2
                if field == 'repository': changed['base']['repo']['full_name'] = 'other/repo'
                records[pr] = {'__responses__': [records[pr], None if field == 'unavailable' else changed]}
                self.assert_ritual_refuses(records)

    def test_ritual_comment_dates_and_record_drift_refuse(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        issue = 'repos/{owner}/{repo}/issues/2'
        for defect in ('missing-created', 'missing-updated', 'bad-created', 'bad-updated',
                       'edit-body', 'delete-plan', 'new-dispatch', 'label-drift', 'plan-drift'):
            with self.subTest(defect=defect):
                records = self.ordinary_records()
                comments = records[issue + '/comments']
                if defect == 'missing-created': comments[0].pop('created_at')
                if defect == 'missing-updated': comments[0].pop('updated_at')
                if defect == 'bad-created': comments[0]['created_at'] = '2026-13-01T00:00:00Z'
                if defect == 'bad-updated': comments[0]['updated_at'] = False
                changed = copy.deepcopy(comments)
                if defect == 'edit-body': changed[1]['body'] += '\nAltered work order.'
                if defect == 'delete-plan': changed.pop(1)
                if defect == 'new-dispatch':
                    extra = copy.deepcopy(changed[-1]); extra['id'] = 90; changed.append(extra)
                if defect in ('edit-body', 'delete-plan', 'new-dispatch'):
                    records[issue + '/comments'] = {'__responses__': [comments, changed]}
                if defect == 'label-drift':
                    changed_issue = copy.deepcopy(records[issue]); changed_issue['labels'] = []
                    records[issue] = {'__responses__': [records[issue], changed_issue]}
                if defect == 'plan-drift':
                    plan = 'repos/{owner}/{repo}/issues/comments/3'
                    changed_plan = copy.deepcopy(records[plan]); changed_plan['body'] += '\nChanged.'
                    records[plan] = {'__responses__': [records[plan], changed_plan]}
                self.assert_ritual_refuses(records)

    def test_ritual_complete_paginated_counts_and_retry_are_bound(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        pr = 'repos/{owner}/{repo}/pulls/1'
        for count in (1, 30, 31, 100, 101, 200, 250):
            with self.subTest(count=count):
                records = self.ordinary_records(count=count)
                commits = records[pr + '/commits']
                records[pr + '/commits'] = {'__pages__': [commits[i:i + 100] for i in range(0, count, 100)]}
                result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn(f'head {count:040x}', result.stdout)
                self.assertIn(f'{count} commits;', result.stdout)
                commit_calls = [call for call in self.last_gh_calls if call[1].split('?')[0] == pr + '/commits']
                self.assertEqual(1, len(commit_calls))
                self.assertIn('--paginate', commit_calls[0])
                self.assertIn('per_page=100', commit_calls[0][1])
        # A failed later page may print valid partial data before failure. The
        # helper must discard that attempt, then consume the successful retry once.
        records = self.ordinary_records(count=101)
        commits = records[pr + '/commits']
        records[pr + '/commits'] = {'__responses__': [
            {'__pages__': [commits[:100], {'__error__': True}]},
            {'__pages__': [commits[:100], commits[100:]]}]}
        result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('101 commits;', result.stdout)
        self.assertNotIn('synthetic transport error', result.stdout + result.stderr)
        self.assertEqual(2, sum(call[1].split('?')[0] == pr + '/commits' for call in self.last_gh_calls))

    def test_ritual_calendar_validation_and_author_fallback(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        pr = 'repos/{owner}/{repo}/pulls/1'
        issue = 'repos/{owner}/{repo}/issues/2'
        bad = ('', None, False, 12, [], {}, '2026-01-01T00:05:00Z\n', '2026-01-01T00:05:00Zjunk',
               '2023-02-29T00:05:00Z', '1900-02-29T00:05:00Z', '2026-04-31T00:05:00Z',
               '2026-00-01T00:05:00Z', '2026-13-01T00:05:00Z', '2026-01-00T00:05:00Z',
               '2026-01-01T24:05:00Z', '2026-01-01T00:60:00Z', '2026-01-01T00:05:60Z')
        for value in bad:
            with self.subTest(value=value):
                records = self.ordinary_records()
                records[pr + '/commits'][0]['commit']['committer']['date'] = value
                self.assert_ritual_refuses(records)
                if value is not None:
                    records[pr + '/commits'][0]['commit']['author'] = {'date': '2026-01-01T00:05:00Z'}
                    self.assert_ritual_refuses(records)
        for committer in (None, {}, {'date': None}, {'date': '2026-01-01T00:05:00Z'}):
            records = self.ordinary_records()
            records[pr + '/commits'][0]['commit'] = {
                'committer': committer, 'author': {'date': '2026-01-01T00:05:00Z'}}
            result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        # Committer date takes precedence; an old author date is not a violation.
        records[pr + '/commits'][0]['commit']['author']['date'] = '1900-01-01T00:00:00Z'
        self.assertEqual(0, self.packaged_json(RITUAL_PATH, records, '1', installed=True).returncode)
        for stamp in ('2024-02-29T00:00:00Z', '2000-02-29T00:00:00Z'):
            records = self.ordinary_records()
            records[pr + '/commits'][0]['commit']['committer']['date'] = stamp
            for comment in records[issue + '/comments']:
                comment['created_at'] = comment['updated_at'] = stamp
            records['repos/{owner}/{repo}/issues/comments/3'] = copy.deepcopy(records[issue + '/comments'][1])
            result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_ritual_typed_identity_and_comment_completeness(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        pr = 'repos/{owner}/{repo}/pulls/1'
        issue = 'repos/{owner}/{repo}/issues/2'
        for defect in ('sha-newline', 'sha-short', 'sha-null', 'sha-number', 'head-null', 'base-null',
                       'ref-empty', 'count-string', 'count-fraction', 'comment-count', 'comment-duplicate',
                       'comment-page-object', 'comment-dates-empty', 'comment-dates-null', 'plan-id', 'plan-url', 'foreign-repository'):
            with self.subTest(defect=defect):
                records = self.ordinary_records()
                if defect.startswith('sha-'):
                    sha = {'sha-newline': '1' * 40 + '\n', 'sha-short': '1' * 39,
                           'sha-null': None, 'sha-number': 1}[defect]
                    records[pr]['head']['sha'] = records[pr + '/commits'][0]['sha'] = sha
                if defect in ('head-null', 'base-null'): records[pr][defect.split('-')[0]]['sha'] = None
                if defect == 'ref-empty': records[pr]['head']['ref'] = ''
                if defect == 'count-string': records[pr]['commits'] = '1'
                if defect == 'count-fraction': records[pr]['commits'] = 1.5
                if defect == 'comment-count': records[issue]['comments'] += 1
                if defect == 'comment-duplicate': records[issue + '/comments'][1]['id'] = 2
                if defect == 'comment-page-object': records[issue + '/comments'] = {'unexpected': []}
                if defect in ('comment-dates-empty', 'comment-dates-null'):
                    records[issue + '/comments'][0]['created_at'] = records[issue + '/comments'][0]['updated_at'] = '' if defect.endswith('empty') else None
                if defect == 'plan-id': records['repos/{owner}/{repo}/issues/comments/3']['id'] = 4
                if defect == 'plan-url': records['repos/{owner}/{repo}/issues/comments/3']['issue_url'] = 'https://api.github.com/repos/other/repo/issues/2'
                if defect == 'foreign-repository':
                    records[pr]['base']['repo']['full_name'] = 'other/repo'
                    records[pr]['body'] = records[pr]['body'].replace('fixture/adopter', 'other/repo')
                    for comment in records[issue + '/comments'] + [records['repos/{owner}/{repo}/issues/comments/3']]:
                        comment['issue_url'] = comment['issue_url'].replace('fixture/adopter', 'other/repo')
                self.assert_ritual_refuses(records)

    def test_ritual_exemption_priority_and_later_comment_membership(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        issue = 'repos/{owner}/{repo}/issues/2'
        for dispatch in (False, True):
            records = self.ordinary_records()
            comments = records[issue + '/comments']
            comments[1]['body'] += '\nno worker will be spawned'
            if not dispatch: comments.pop()
            records[issue]['comments'] = len(comments)
            records['repos/{owner}/{repo}/issues/comments/3'] = copy.deepcopy(comments[1])
            result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('two-tier' if dispatch else 'declared small-task exemption', result.stdout)
        records = self.ordinary_records()
        comments = records[issue + '/comments']
        for number in range(10, 112):
            item = copy.deepcopy(comments[0]); item['id'] = number; item['body'] = 'Unrelated comment.'
            comments.append(item)
        records[issue]['comments'] = len(comments)
        pages = {'__pages__': [comments[:100], comments[100:]]}
        records[issue + '/comments'] = pages
        result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        changed = copy.deepcopy(pages)
        changed['__pages__'][1][-1]['body'] = 'Releasing worker: changed later page'
        records[issue + '/comments'] = {'__responses__': [pages, changed]}
        self.assert_ritual_refuses(records)

    def test_ritual_marker_names_inside_dispatch_are_not_claims(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        records = self.ordinary_records()
        issue = 'repos/{owner}/{repo}/issues/2'
        comments = records[issue + '/comments']
        comments.pop(0)
        comments[-1]['body'] = comments[-1]['body'].replace('Task #2 worker', 'CLAIM PLAN EXEMPT worker')
        records[issue]['comments'] = len(comments)
        self.assert_ritual_refuses(records)

    def test_f2_whole_legacy_and_tool_scoped_identifiers(self):
        for identifier in ('deadbeef', '6af9582d-42d1-425d-82c8-f9ec651225a8',
                           'a' * 128, '/root/worker', '/root/example_supervisor/example_worker',
                           '/root/' + 'a' * 63, '/root/' + '/'.join(['worker'] * 16)):
            with self.subTest(identifier=identifier):
                result = self.ordinary_ritual(identifier)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn('two-tier', result.stdout)

    def test_f2_missing_malformed_or_unbounded_identifiers_refuse(self):
        for identifier in ('', '<id>', 'UNKNOWN', 'TBD', '--------', 'a' * 129,
                           'deadbeef-tail', 'deadbeef/garbage', 'xdeadbeef', 'deadbeef extra',
                           'deadbeef,garbage', 'deadbeef)garbage', 'deadbeef\tgarbage',
                           'deadbeef\r', 'deadbeef\x1b', '/root', '/root/', '/root//worker',
                           '/root/../worker', '/root/./worker', '/root/worker/', '/root/Worker',
                           '/root/<worker>', '/root/unknown', '/root/tbd', '/root/' + 'a' * 64,
                           '/root/' + '/'.join(['a'] * 17), '/root/' + '/'.join(['a' * 63] * 4)):
            with self.subTest(identifier=identifier):
                result = self.ordinary_ritual(identifier)
                self.assertNotEqual(0, result.returncode, result.stdout)

    def test_f2_ordinary_provenance_chronology_branch_and_replacement(self):
        result = self.ordinary_ritual(defect='replacement')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for defect in ('wrong-branch', 'edited', 'early', 'late', 'claim-after-plan',
                       'missing-release', 'edited-release', 'missing-session', 'duplicate-session',
                       'wrong-plan-repo', 'wrong-plan-issue', 'missing-plan-link',
                       'wrong-plan-resolution', 'non-plan-comment', 'missing-task-label'):
            with self.subTest(defect=defect):
                result = self.ordinary_ritual(defect=defect)
                self.assertNotEqual(0, result.returncode, result.stdout)

    def test_f2_bootstrap_retains_exact_historical_anchor(self):
        old = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob',
                                       'f66d3aa5e73abf24052c70f557cd6df9177ca012'])
        base, head = self.adoption_fixture(anchor=old)
        result = self.ritual(base, head)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_f2_bootstrap_retains_t18_anchor(self):
        old = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob',
                                       'cc888c829bc5957871376004cb59a93b4980b50f'])
        base, head = self.adoption_fixture(anchor=old)
        result = self.ritual(base, head)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_f2_bootstrap_rejects_t18_to_current_mixed_anchors(self):
        old = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob',
                                       'cc888c829bc5957871376004cb59a93b4980b50f'])
        new = (ROOT / PAYLOAD / TASK_SELECTION_PATHS[1]).read_bytes()
        base, head = self.adoption_fixture(anchor=old, head_anchor=new)
        self.assertNotEqual(0, self.ritual(base, head).returncode)

    def test_f2_bootstrap_rejects_unknown_and_mixed_anchors(self):
        old = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob',
                                       'f66d3aa5e73abf24052c70f557cd6df9177ca012'])
        new = (ROOT / PAYLOAD / '.agents/skills/plan-management/scripts/frontier.sh').read_bytes()
        self.assertNotEqual(old, new, 'the compatibility correction must have a new reviewed anchor')
        base, head = self.adoption_fixture(anchor=old, head_anchor=new)
        self.assertNotEqual(0, self.ritual(base, head).returncode)
        path = self.target / '.agents/skills/plan-management/scripts/frontier.sh'
        path.write_bytes(b'unknown anchor\n')
        head = self.commit_adopter('unreviewed anchor')
        self.assertNotEqual(0, self.ritual(base, head).returncode)

    def clone_source(self):
        source = self.base / "local source"
        shutil.copytree(ROOT / ".github/distribution", source / ".github/distribution")
        return source

    def kickoff_checker(self):
        spec = importlib.util.spec_from_file_location("kickoff_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        return checker

    def task_creation_inputs(self, defect=None, *, ready=True, dependencies="14,15", repo="fixture/adopter", body=None, installed=False):
        # Raw gh 2.96.0 exports, not a made-up repository node or labels connection.
        self.assertIsNotNone(shutil.which("jq"), "real jq is needed by the fake-gh query evaluator")
        helper = (self.target if installed else ROOT / PAYLOAD) / TASK_CREATION_PATHS[1]
        body_path = self.base / "task body.md"
        body_text = body if body is not None else "## Objective\n\nBuild a bounded fixture.\n\n## File ownership\n\n- app/**\n"
        body_path.write_text(body_text)
        def related(number, state="OPEN"):
            return {"id": "I_fixture_" + str(number), "number": number, "title": "Related issue",
                    "url": "https://github.com/fixture/adopter/issues/" + str(number), "state": state}
        value = {**related(40), "title": "Fixture Task", "body": body_text,
                 "parent": related(12), "blockedBy": {"nodes": [related(14), related(15, "CLOSED")], "totalCount": 2},
                 "labels": [{"id": "L_task", "name": "type:task"}, {"id": "L_exec", "name": "exec:cli"}]}
        if not dependencies:
            value["blockedBy"] = {"nodes": [], "totalCount": 0}
        elif all(part.isdigit() for part in dependencies.split(",")):
            numbers = [int(part) for part in dependencies.split(",")]
            value["blockedBy"] = {"nodes": [related(n) for n in numbers], "totalCount": len(numbers)}
        original_value = json.loads(json.dumps(value))
        mutations = {
            "wrong-body": lambda v: v.update(body=v["body"] + "changed"),
            "wrong-title": lambda v: v.update(title="Other Task"),
            "wrong-url": lambda v: v.update(url="https://github.com/other/adopter/issues/40"),
            "wrong-number": lambda v: v.update(number=41),
            "bad-id": lambda v: v.update(id=None),
            "closed-task": lambda v: v.update(state="CLOSED"),
            "wrong-parent": lambda v: v.update(parent=related(13)),
            "absent-parent": lambda v: v.update(parent=None),
            "cross-repo-parent": lambda v: v["parent"].update(url="https://github.com/other/adopter/issues/12"),
            "wrong-dependency": lambda v: v["blockedBy"]["nodes"].__setitem__(0, related(16)),
            "duplicate-dependency": lambda v: v["blockedBy"]["nodes"].__setitem__(1, related(14)),
            "duplicate-id": lambda v: v["blockedBy"]["nodes"][1].update(id=v["blockedBy"]["nodes"][0]["id"]),
            "truncated-dependencies": lambda v: v["blockedBy"].update(totalCount=3),
            "malformed-dependencies": lambda v: v.update(blockedBy=[]),
            "string-count": lambda v: v["blockedBy"].update(totalCount="2"),
            "cross-repo-dependency": lambda v: v["blockedBy"]["nodes"][0].update(url="https://github.com/other/adopter/issues/14"),
            "unknown-dependency-state": lambda v: v["blockedBy"]["nodes"][0].update(state="UNKNOWN"),
            "missing-label": lambda v: v.update(labels=v["labels"][:1]),
            "wrong-exec": lambda v: v["labels"][1].update(name="exec:ide"),
            "duplicate-label": lambda v: v["labels"].append(v["labels"][0]),
            "labels-connection": lambda v: v.update(labels={"nodes": v["labels"], "totalCount": 2}),
            "labels-cap": lambda v: v["labels"].extend({"name": "label" + str(n)} for n in range(98)),
            "premature-ready": lambda v: v["labels"].append({"name": "ai:ready"}),
        }
        if defect in mutations:
            mutations[defect](value)
        faults = {key: item for key, item in value.items() if item != original_value[key]}
        directory = self.base / "task-bin"
        directory.mkdir(exist_ok=True)
        state = self.base / "task-fixture.json"
        events = self.base / "task-events.jsonl"
        events.write_text("")
        state.write_text(json.dumps({"issue": value, "faults": faults, "defect": defect,
                                     "views": 0, "edited": False, "created": False,
                                     "caller_body": str(body_path)}))
        fake = directory / "gh"
        fake.write_text("""#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args=sys.argv[1:]; path=Path(os.environ['TASK_FIXTURE']); s=json.loads(path.read_text())
with open(os.environ['TASK_EVENTS'],'a') as f: f.write(json.dumps(args)+'\\n')
defect=s['defect']
if args[:2]==['api','user']:
    if defect=='setup-auth-error': sys.exit(1)
    value={'login':'fixture','plan':{'name':'free' if defect=='setup-private-free' else None if defect=='setup-private-unknown' else 'pro'}}
elif args[:2]==['api','repos/fixture/adopter']:
    value={'private':defect in ('setup-private-free','setup-private-unknown'),'owner':{'type':'User'}}
elif args[:2]==['repo','view']:
    if defect=='repo-read-error': sys.exit(1)
    if defect=='caller-body-drift': Path(s['caller_body']).write_text('Later caller edit\\n')
    value={'url':'https://github.com/fixture/adopter','nameWithOwner':'fixture/adopter'}
elif args[:2]==['issue','create']:
    options={}
    for i in range(2,len(args),2):
        if i+1>=len(args) or args[i] not in ('--repo','--title','--body-file','--parent','--blocked-by','--label') or args[i] in options: sys.exit(95)
        options[args[i]]=args[i+1]
    if not {'--repo','--title','--body-file','--parent','--label'} <= options.keys(): sys.exit(95)
    repo=options['--repo']
    if repo.count('/')==1: repo='github.com/'+repo
    if repo!='github.com/fixture/adopter': sys.exit(95)
    def related(number):
        return {'id':'I_fixture_'+str(number),'number':number,'title':'Related issue',
                'url':'https://'+repo+'/issues/'+str(number),'state':'OPEN'}
    try:
        body=Path(options['--body-file']).read_bytes().decode('utf-8')
        blockers=[related(int(n)) for n in options.get('--blocked-by','').split(',') if n]
        s['issue']={**related(40),'title':options['--title'],'body':body,
                    'parent':related(int(options['--parent'])),
                    'blockedBy':{'nodes':blockers,'totalCount':len(blockers)},
                    'labels':[{'name':name} for name in options['--label'].split(',')]}
    except (OSError,ValueError): sys.exit(95)
    # Explicit server-response faults apply after actual argument transport.
    s['issue'].update(s['faults'])
    s['created']=True; path.write_text(json.dumps(s))
    if defect=='create-link-failure': sys.exit(1)
    if defect=='create-failed-known': print('https://github.com/fixture/adopter/issues/40'); sys.exit(1)
    if defect=='create-malformed': print('not an issue URL'); sys.exit(0)
    if defect=='create-wrong-repo': print('https://github.com/other/adopter/issues/40'); sys.exit(0)
    if defect=='create-oversized': print('x'*200000); sys.exit(0)
    if defect=='create-nul': sys.stdout.buffer.write(b'https://github.com/fixture/adopter/issues/40\\0\\n'); sys.exit(0)
    print('https://github.com/fixture/adopter/issues/40'); sys.exit(0)
elif args[:2]==['issue','edit']:
    if not s['created'] or args[2]!='40' or len(args)!=7 or args[3]!='--repo' or args[4]!='github.com/fixture/adopter' or args[5]!='--add-label': sys.exit(95)
    s['edited']=True
    if defect!='ready-not-applied':
        names={label['name'] for label in s['issue']['labels']}
        s['issue']['labels'].extend({'name':name} for name in args[6].split(',') if name not in names)
    path.write_text(json.dumps(s))
    if defect=='ready-write-error': sys.exit(1)
    print('https://github.com/fixture/adopter/issues/40'); sys.exit(0)
elif args[:2]==['issue','list']:
    names={label['name'] for label in s['issue']['labels']}
    if s['created'] and s['issue']['state']=='OPEN' and {'type:task','ai:ready'} <= names:
        print(str(s['issue']['number'])+'\\t'+s['issue']['title'])
    sys.exit(0)
elif args[:2]==['issue','view'] and args[2]!='40':
    matches=[node for node in s['issue']['blockedBy']['nodes'] if str(node['number'])==args[2]]
    if len(matches)!=1 or args[args.index('--repo')+1]!='github.com/fixture/adopter': sys.exit(94)
    value={'state':matches[0]['state']}
elif args[:2]==['issue','view']:
    s['views']+=1; path.write_text(json.dumps(s))
    if defect=='read-error' or (s['edited'] and defect=='final-read-error'): sys.exit(1)
    value=s['issue']
    if defect=='frontier-read-error': sys.exit(1)
    if defect=='frontier-incomplete': value['blockedBy']['totalCount']+=1
    if s['edited'] and defect=='final-body-drift': value['body']+='drift'
    if s['edited'] and defect=='final-id-drift': value['id']='I_other'
    if s['edited'] and defect=='final-parent-id-drift': value['parent']['id']='I_other_parent'
    if s['edited'] and defect=='final-blocker-id-drift': value['blockedBy']['nodes'][0]['id']='I_other_blocker'
    if defect=='view-oversized': print('x'*200000); sys.exit(0)
else: sys.exit(91)
if '--jq' not in args: sys.exit(92)
if args[0]!='api':
    if '--json' not in args: sys.exit(92)
    fields=args[args.index('--json')+1].split(',')
    if any(name not in value for name in fields): sys.exit(93)
result=subprocess.run(['jq','-r',args[args.index('--jq')+1]],input=json.dumps(value),text=True)
sys.exit(result.returncode)
""")
        fake.chmod(0o755)
        fake_head = directory / "head"
        if defect == "body-read-error":
            fake_head.write_text('#!/usr/bin/env bash\nprintf "cannot read %s\\n" "$3" >&2\nexit 1\n')
            fake_head.chmod(0o755)
        elif fake_head.exists():
            fake_head.unlink()
        args = ["bash", str(helper), "-t", "Fixture Task", "-b", str(body_path), "-p", "12", "-e", "cli"]
        if dependencies: args.extend(["-d", dependencies])
        if repo is not None: args.extend(["-R", repo])
        if ready: args.append("--ready")
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ["PATH"],
                   TASK_FIXTURE=str(state), TASK_EVENTS=str(events))
        return args, env, state, events

    def task_creation_fixture(self, *args, **kwargs):
        command, env, _state, events = self.task_creation_inputs(*args, **kwargs)
        result = subprocess.run(command, cwd=self.target, env=env,
            capture_output=True, text=True, timeout=15)
        return result, [json.loads(line) for line in events.read_text().splitlines()]

    def source_preparation_inputs(self, *, installed=False):
        _args, env, state, events = self.task_creation_inputs(installed=installed)
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        helper = (self.target if installed else ROOT / PAYLOAD) / SOURCE_REGISTRY_PATH
        return ["bash", str(helper)], env, state, events

    def audit_source_records(self, visibility=False, plan="pro"):
        return {"user": {"login": "fixture", "plan": {"name": plan}},
                "repos/fixture/adopter": {"private": visibility, "owner": {"type": "User"}}}

    def test_audit_visibility_requires_raw_boolean_without_registry_write(self):
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        registry = self.target / REGISTRY_REL
        registry.parent.mkdir(parents=True)
        registry.write_text("# Adopter registry\n")
        registry.chmod(0o600)
        before = self.snapshot(self.target)
        for visibility in (None, "unknown", "true", "false", 1, {}, [], "missing"):
            with self.subTest(visibility=visibility):
                records = self.audit_source_records(visibility)
                if visibility == "missing": records["repos/fixture/adopter"].pop("private")
                result = self.packaged_json(SOURCE_REGISTRY_PATH, records, "--source", "builtin", "--yes")
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual(before, self.snapshot(self.target))
                self.assertEqual(0o600, registry.stat().st_mode & 0o777)

    def test_audit_visibility_preserves_existing_plan_controls(self):
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        for visibility, plan, success in ((False, None, True), (True, "pro", True),
                                          (True, "team", True), (True, "enterprise", True),
                                          (True, "free", False), (True, None, False)):
            with self.subTest(visibility=visibility, plan=plan):
                before = self.snapshot(self.target)
                result = self.packaged_json(SOURCE_REGISTRY_PATH, self.audit_source_records(visibility, plan),
                                            "--source", "builtin", "--dry-run")
                self.assertEqual(success, result.returncode == 0, result.stdout + result.stderr)
                if success: self.assertIn("pending-activation", result.stdout)
                self.assertEqual(before, self.snapshot(self.target))

    def test_audit_visibility_broken_copy_and_resealed_checker_guard(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        helper = self.target / SOURCE_REGISTRY_PATH
        original = helper.read_text()
        query = 'if (.private | type) == "boolean" then .private else error("uncheckable repository visibility") end'
        self.assertIn(query, original)
        helper.write_text(original.replace(query, '.private', 1))
        result = self.packaged_json(SOURCE_REGISTRY_PATH, self.audit_source_records("false"),
                                    "--source", "builtin", "--dry-run", installed=True)
        self.assertEqual(0, result.returncode, result.stderr)
        helper.write_text(original)
        result = self.packaged_json(SOURCE_REGISTRY_PATH, self.audit_source_records("false"),
                                    "--source", "builtin", "--dry-run", installed=True)
        self.assertNotEqual(0, result.returncode)
        source, checker = self.complete_checker_source()
        (source / PAYLOAD / SOURCE_REGISTRY_PATH).write_text(original.replace(query, '.private', 1))
        self.reseal_payload(source)
        self.assertIn("source preparation typed visibility guard drifted", checker.validate(source))

    def test_audit_duplicate_provenance_rejected_by_composed_cli_and_both_readers(self):
        source, checker = self.complete_checker_source()
        target = source / checker.PARITY
        original = target.read_text()
        baseline = subprocess.run([sys.executable, "-I", str(ROOT / ".github/scripts/check-installer.py"),
                                   "--root", str(source)], capture_output=True, text=True, timeout=15)
        self.assertEqual(0, baseline.returncode, baseline.stdout)
        for key, token in (("source_commit", '"source_commit":'),
                           ("source_blob", '"source_blob":'),
                           ("schema", '"schema": "connector-validation-companion/v1"')):
            match = re.search(re.escape(token) + (r'\s*"[^"\n]+"' if key != "schema" else ''), original)
            self.assertIsNotNone(match)
            field = match.group(0)
            wrong = json.dumps(key) + ': "wrong"'
            escaped = field.replace(key, key[:-1] + '\\u%04x' % ord(key[-1]), 1)
            for variant, replacement in (("wrong-first", wrong + ', ' + field),
                                          ("wrong-last", field + ', ' + wrong),
                                          ("same-value", field + ', ' + field),
                                          ("escaped-key", field + ', ' + escaped)):
                with self.subTest(key=key, variant=variant):
                    target.write_text(original[:match.start()] + replacement + original[match.end():])
                    result = subprocess.run([sys.executable, "-I", str(ROOT / ".github/scripts/check-installer.py"),
                                             "--root", str(source)], capture_output=True, text=True, timeout=15)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("malformed or uncheckable", result.stdout)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)
                    self.assertTrue(checker.validate(source))
                    self.assertTrue(checker.validate_connector_companion(source))

    def test_audit_onboarding_carries_approved_source_in_noninteractive_shell(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        skill = (self.target / ".agents/skills/project-onboarding/SKILL.md").read_text()
        apply_section = skill.split("### P4 — Apply", 1)[1].split("### P5", 1)[0]
        for source in ("builtin", "speckit"):
            with self.subTest(source=source):
                command = "bash .github/scripts/setup-sources.sh --source " + source + " --yes"
                self.assertIn(command, apply_section)
                result = self.packaged_json(SOURCE_REGISTRY_PATH, self.audit_source_records(),
                                            *shlex.split(command)[2:], installed=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("## " + source, (self.target / REGISTRY_REL).read_text())
        self.assertIn("pending-activation", apply_section)
        self.assertIn("explicit write consent", apply_section)

    def test_audit_ruleset_help_examples_are_executable_previews(self):
        helper = ".github/scripts/setup-ruleset.sh"
        help_result = self.packaged_json(helper, {}, "--help")
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        examples = [line.strip() for line in help_result.stdout.splitlines()
                    if line.startswith("  bash .github/scripts/setup-ruleset.sh")]
        self.assertEqual(3, len(examples))
        for example in examples:
            with self.subTest(example=example):
                self.assertNotIn("|", example)
                args = shlex.split(example)[2:]
                self.assertIn("--checks", args)
                if "--dry-run" not in args: args.append("--dry-run")
                result = self.packaged_json(helper, {}, *args)
                self.assertEqual(0, result.returncode, result.stderr)
                payload = json.loads(result.stdout)
                checks = next(row for row in payload["rules"] if row["type"] == "required_status_checks")
                self.assertEqual(["lint", "test"], [item["context"] for item in checks["parameters"]["required_status_checks"]])
                self.assertEqual([], self.last_gh_calls)

    def test_audit_tuning_summary_names_literal_installed_skill(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        summary = self.base / "summary.md"
        result = subprocess.run(["bash", str(self.target / ".github/scripts/tuning-status.sh"), "--ci"],
                                cwd=self.target, env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary), project="expanded"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("`$project-onboarding`", summary.read_text())
        self.assertNotIn("/onboard-project", summary.read_text())

    def test_audit_speckit_proves_tracking_and_exact_pin_tree(self):
        text = (ROOT / PAYLOAD / ".github/connectors/speckit.md").read_text()
        block = re.search(r"```sh\n(spec_pin=.*?)\n```", text, re.S)
        self.assertIsNotNone(block, "connector must give the pinned-tree verification command")
        (self.target / "initial.txt").write_text("base\n")
        old_pin = self.commit_adopter("before specs")
        spec = self.target / "specs/example/plan.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("reviewed specification\n")
        def verify(pin):
            command = re.sub(r"^spec_pin=.*$", "spec_pin=" + shlex.quote(pin), block.group(1), count=1, flags=re.M)
            return subprocess.run(["bash", "-c", command], cwd=self.target, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, verify(old_pin).returncode)  # Untracked, not ignored.
        self.git("add", "--", "specs/example/plan.md")
        self.assertNotEqual(0, verify(old_pin).returncode)  # Staged only.
        current_pin = self.commit_adopter("commit specs")
        self.assertNotEqual(0, verify(old_pin).returncode)  # Tracked now, absent at intended old pin.
        self.assertEqual(0, verify(current_pin).returncode)
        self.assertNotEqual(0, verify("0" * 40).returncode)

    def test_audit_adopter_checkout_and_supervisor_ritual_handoffs(self):
        for name in ("README.md", "docs/distribution/source-first-installer.md"):
            text = (ROOT / name).read_text()
            self.assertIn("open or select the adopter checkout in Codex", text)
            self.assertIn(".agents/skills/project-onboarding/SKILL.md", text)
        instructions = (ROOT / PAYLOAD / ".github/codex-instructions.md").read_text()
        for token in ("supervisor", "claim", "dispatch", "worker", "trivial-task exemption", "Refs #<n>", "post-merge", "non-final"):
            self.assertIn(token, instructions)

    def test_source_preparation_refuses_registry_symlink_without_changing_referent(self):
        command, env, _state, _events = self.source_preparation_inputs()
        registry = self.target / REGISTRY_REL
        registry.parent.mkdir(parents=True)
        outside = self.base / "external registry.md"
        outside.write_text("External sentinel\n")
        registry.symlink_to(outside)
        result = subprocess.run(command + ["--source", "builtin", "--yes"], cwd=self.target,
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("External sentinel\n", outside.read_text())
        self.assertTrue(registry.is_symlink())

    def test_source_preparation_refuses_unsafe_destinations_and_parents(self):
        cases = ["dangling-registry", "directory-registry", "fifo-registry", "dangling-parent"]
        cases += [kind + ":" + path for kind in ("link", "file")
                  for path in (".github", ".github/docs", ".github/docs/context")]
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                self.target = self.base / ("unsafe-adopter-" + str(index))
                self.target.mkdir()
                self.git("init", "-q")
                command, env, _state, events = self.source_preparation_inputs()
                registry = self.target / REGISTRY_REL
                outside = self.base / ("outside-" + str(index))
                outside.mkdir()
                (outside / "sentinel").write_text("Unrelated bytes\n")
                if case in ("dangling-registry", "directory-registry", "fifo-registry"):
                    registry.parent.mkdir(parents=True)
                    if case == "dangling-registry": registry.symlink_to(outside / "absent")
                    elif case == "directory-registry": registry.mkdir()
                    else: os.mkfifo(registry)
                else:
                    kind, name = ("link", ".github/docs") if case == "dangling-parent" else case.split(":")
                    path = self.target / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if kind == "file": path.write_text("Parent obstruction\n")
                    else: path.symlink_to(outside / "absent" if case == "dangling-parent" else outside)
                before, external = self.snapshot(self.target), self.snapshot(outside)
                for option in ("--yes", "--dry-run"):
                    result = subprocess.run(command + ["--source", "builtin", option], cwd=self.target,
                                            env=env, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(0, result.returncode)
                    self.assertNotIn(str(self.base), result.stderr + result.stdout)
                    self.assertEqual(before, self.snapshot(self.target))
                    self.assertEqual(external, self.snapshot(outside))
                self.assertEqual("", events.read_text())

    def test_source_preparation_checks_logical_in_repository_invocation_ancestry(self):
        command, env, _state, _events = self.source_preparation_inputs()
        nested = self.target / "ordinary" / "nested"
        nested.mkdir(parents=True)
        alias = self.target / "alias"
        alias.symlink_to(self.target / "ordinary")
        short = self.target / "short"
        short.symlink_to(nested)
        root_alias = self.base / "root-alias"
        root_alias.symlink_to(self.target)
        before = self.snapshot(self.target)
        for cwd in (alias / "nested", short, root_alias):
            with self.subTest(kind=cwd.name):
                result = subprocess.run(command + ["--source", "builtin", "--yes"], cwd=cwd,
                                        env=dict(env, PWD=str(cwd)), capture_output=True, text=True, timeout=5)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, self.snapshot(self.target))
                self.assertNotIn(str(self.base), result.stderr + result.stdout)
        # An OS/path alias above the repository is outside this bounded check.
        outer_alias = self.base / "outer-alias"
        outer_alias.symlink_to(self.base)
        cwd = outer_alias / self.target.name / "ordinary" / "nested"
        result = subprocess.run(command + ["--source", "builtin", "--dry-run"], cwd=cwd,
                                env=dict(env, PWD=str(cwd)), capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))

    def test_source_preparation_preserves_normal_create_append_duplicate_dry_run_and_pins(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        command, env, _state, events = self.source_preparation_inputs(installed=True)
        nested = self.target / "ordinary" / "nested"
        nested.mkdir(parents=True)
        def run(*options):
            return subprocess.run(command + ["--source", *options], cwd=nested,
                                  env=dict(env, PWD=str(nested)), capture_output=True, text=True, timeout=5)
        before = self.snapshot(self.target)
        preview = run("builtin", "--dry-run")
        self.assertEqual(0, preview.returncode, preview.stderr)
        self.assertIn("status: pending-activation", preview.stdout)
        self.assertEqual(before, self.snapshot(self.target))
        refused = run("builtin")
        self.assertNotEqual(0, refused.returncode)
        self.assertEqual(before, self.snapshot(self.target))
        created = subprocess.run(["bash", "-c", 'umask 027; exec "$@"', "fixture", *command,
                                  "--source", "builtin", "--yes"], cwd=nested, env=dict(env, PWD=str(nested)),
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(0, created.returncode, created.stderr)
        registry = self.target / REGISTRY_REL
        initial = registry.read_bytes()
        self.assertTrue(initial.startswith(b"# Context sources registry\n"))
        self.assertIn(b"activation PR #<fill in from inside the activation PR>", initial)
        self.assertEqual(0o640, registry.stat().st_mode & 0o777)
        registry.chmod(0o600)
        for options in (("builtin", "--yes"), ("builtin", "--dry-run")):
            self.assertEqual(0, run(*options).returncode)
            self.assertEqual(initial, registry.read_bytes())
            self.assertEqual(0o600, registry.stat().st_mode & 0o777)
        (self.target / "specs").mkdir()
        (self.target / "specs/example.md").write_text("Synthetic spec\n")
        spec_sha = self.commit_adopter("synthetic specs pin")
        self.assertEqual(0, run("speckit", "--yes").returncode)
        appended = registry.read_bytes()
        self.assertTrue(appended.startswith(initial + b"\n## speckit\n"))
        self.assertIn(("specs/** adoption SHA " + spec_sha).encode(), appended)
        self.assertEqual(2, appended.count(b"status: pending-activation"))
        self.assertEqual(0o600, registry.stat().st_mode & 0o777)
        self.assertTrue(all(json.loads(line)[0] == "api" for line in events.read_text().splitlines()))

    def test_source_preparation_chains_installed_pending_registry_task_and_frontier(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        brief = ("## Objective\n\nImplement the synthetic application change.\n\n"
                 "## Context & references\n\n- Epic: #12\n- Derived from: #14\n\n"
                 "## Acceptance criteria\n\n- [ ] Application tests pass.\n\n"
                 "## Out of scope\n\n- Production deployment.\n\n"
                 "## File ownership\n\n- app/**\n\n"
                 "## Verification\n\nRun the synthetic application test suite.\n\n"
                 "## Routing\n\n- Surface: exec:cli\n- Parallel-safe: yes, subject to ownership checks.\n\n"
                 "## Handoff notes\n\n- Wait for #14 and #15 to close.\n")
        task, env, state, events = self.task_creation_inputs(installed=True, body=brief)
        self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
        setup = ["bash", str(self.target / SOURCE_REGISTRY_PATH), "--source", "builtin", "--yes"]
        frontier = ["bash", str(self.target / ".agents/skills/plan-management/scripts/frontier.sh"), "-R", "fixture/adopter", "--all"]
        def run(command):
            return subprocess.run(command, cwd=self.target, env=env, capture_output=True, text=True, timeout=10)
        prepared = run(setup)
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        registry = (self.target / REGISTRY_REL).read_bytes()
        self.assertIn(b"status: pending-activation", registry)
        created = run(task)
        self.assertEqual(0, created.returncode, created.stderr)
        blocked = run(frontier)
        self.assertEqual(0, blocked.returncode, blocked.stderr)
        self.assertNotIn("#40", blocked.stdout.split("== Blocked ==")[0])
        self.assertIn("== Blocked ==\n#40\tFixture Task", blocked.stdout)
        value = json.loads(state.read_text())
        for node in value["issue"]["blockedBy"]["nodes"]: node["state"] = "CLOSED"
        state.write_text(json.dumps(value))
        actionable = run(frontier)
        self.assertEqual(0, actionable.returncode, actionable.stderr)
        self.assertIn("== Actionable frontier (all dependency observations succeeded) ==\n#40\tFixture Task", actionable.stdout)
        self.assertNotIn("== Blocked ==", actionable.stdout)
        body_check = run(["bash", str(self.target / TASK_SELECTION_PATHS[2]),
                          "--validate-body", str(self.base / "task body.md")])
        self.assertEqual(0, body_check.returncode, body_check.stderr)
        self.assertIn('VALID', body_check.stdout)
        self.assertEqual(brief, json.loads(state.read_text())['issue']['body'])
        self.assertEqual(registry, (self.target / REGISTRY_REL).read_bytes())
        calls = [json.loads(line) for line in events.read_text().splitlines()]
        self.assertEqual(["api", "api", "repo", "issue", "issue", "issue", "issue"], [call[0] for call in calls[:7]])
        self.assertEqual(1, sum(call[:2] == ["issue", "create"] for call in calls))

    def test_source_preparation_preserves_preflight_selection_and_uncommitted_spec_pin(self):
        command, env, state, events = self.source_preparation_inputs()
        before = self.snapshot(self.target)
        for defect in ("setup-auth-error", "setup-private-free", "setup-private-unknown"):
            with self.subTest(defect=defect):
                value = json.loads(state.read_text())
                value["defect"] = defect
                state.write_text(json.dumps(value))
                result = subprocess.run(command + ["--source", "builtin", "--yes"], cwd=self.target,
                                        env=env, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, self.snapshot(self.target))
        value["defect"] = None
        state.write_text(json.dumps(value))
        (self.target / "specs").mkdir()
        before = self.snapshot(self.target)
        result = subprocess.run(command + ["--yes"], cwd=self.target, env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(2, result.returncode)
        self.assertIn("consider --source speckit", result.stderr)
        preview = subprocess.run(command + ["--source", "speckit", "--dry-run"], cwd=self.target,
                                 env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(0, preview.returncode, preview.stderr)
        self.assertIn("specs/** adoption SHA <record the current specs/** commit SHA>", preview.stdout)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertTrue(all(json.loads(line)[0] == "api" for line in events.read_text().splitlines()))

    def test_source_preparation_chain_refuses_unsafe_and_nonactionable_observations(self):
        for case in ("no-ready", "frontier-read-error", "frontier-incomplete", "unsafe-registry"):
            with self.subTest(case=case):
                self.target = self.base / case
                self.target.mkdir()
                self.git("init", "-q")
                self.assertEqual(0, self.run_install("--apply").returncode)
                task, env, state, events = self.task_creation_inputs(installed=True, ready=case != "no-ready")
                self.git("remote", "add", "origin", "https://github.com/fixture/adopter.git")
                registry = self.target / REGISTRY_REL
                outside = self.base / (case + "-sentinel")
                if case == "unsafe-registry":
                    outside.write_text("External sentinel\n")
                    registry.symlink_to(outside)
                setup = ["bash", str(self.target / SOURCE_REGISTRY_PATH), "--source", "builtin", "--yes"]
                prepared = subprocess.run(setup, cwd=self.target, env=env, capture_output=True, text=True, timeout=10)
                # This conditional is a disposable test driver, not shipped orchestration.
                if prepared.returncode != 0:
                    self.assertEqual("unsafe-registry", case)
                    self.assertEqual("External sentinel\n", outside.read_text())
                    self.assertEqual("", events.read_text())
                    continue
                self.assertNotEqual("unsafe-registry", case)
                result = subprocess.run(task, cwd=self.target, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
                value = json.loads(state.read_text())
                if case != "no-ready": value["defect"] = case
                state.write_text(json.dumps(value))
                frontier = subprocess.run(["bash", str(self.target / ".agents/skills/plan-management/scripts/frontier.sh"), "-R", "fixture/adopter"],
                                          cwd=self.target, env=env, capture_output=True, text=True, timeout=10)
                self.assertNotIn("#40", frontier.stdout)
                if case == "no-ready":
                    self.assertEqual(0, frontier.returncode)
                    self.assertIn("No open Task issues labeled ai:ready", frontier.stdout)
                else:
                    self.assertNotEqual(0, frontier.returncode)
                    self.assertNotIn("Actionable frontier", frontier.stdout)

    def test_source_preparation_checker_rejects_resealed_path_guard_and_provenance_drift(self):
        source, checker = self.complete_checker_source()
        script = source / PAYLOAD / SOURCE_REGISTRY_PATH
        original = script.read_text()
        for old, replacement in (("\ncheck_registry_path\n", "\n:\n"),
                                 ('[ -L "$REGISTRY" ]', 'false'),
                                 ('[ ! -L "$INVOCATION" ]', 'true'),
                                 ('status: pending-activation', 'status: active')):
            with self.subTest(guard=old):
                self.assertIn(old, original)
                script.write_text(original.replace(old, replacement))
                self.reseal_payload(source)
                self.assertTrue(any("source preparation" in item for item in checker.validate(source)))
                script.write_text(original)
                self.reseal_payload(source)
        path = source / ".github/distribution/source-parity.v1.json"
        original_parity = path.read_bytes()
        for mutation in ("missing", "source", "extra", "digest", "mode"):
            with self.subTest(mutation=mutation):
                value = json.loads(original_parity)
                record = value["source_preparation"]
                if mutation == "missing": del value["source_preparation"]
                elif mutation == "source": record["source_files"][SOURCE_REGISTRY_PATH] = "0" * 40
                elif mutation == "extra": record["automatic_activation"] = True
                elif mutation == "digest": record["target_files"][0]["sha256"] = "0" * 64
                else: record["target_files"][0]["mode"] = "100755"
                path.write_text(json.dumps(value))
                self.assertTrue(any("source preparation" in item for item in checker.validate(source)))
        path.write_bytes(original_parity)
        self.assertEqual([], checker.validate(source))

    def test_task_creation_deferred_link_failure_never_initially_ready(self):
        result, events = self.task_creation_fixture("create-link-failure")
        self.assertNotEqual(0, result.returncode)
        creates = [event for event in events if event[:2] == ["issue", "create"]]
        self.assertEqual(1, len(creates))
        self.assertNotIn("ai:ready", creates[0][creates[0].index("--label") + 1])
        self.assertEqual("12", creates[0][creates[0].index("--parent") + 1])
        self.assertEqual("14,15", creates[0][creates[0].index("--blocked-by") + 1])
        self.assertFalse(any(event[:2] == ["issue", "edit"] for event in events))
        self.assertIn("unconfirmed", result.stderr)

    def test_task_creation_ready_requires_two_verified_reads_and_open_blockers_are_allowed(self):
        result, events = self.task_creation_fixture()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["repo", "view"], ["issue", "create"], ["issue", "view"],
                          ["issue", "edit"], ["issue", "view"]], [event[:2] for event in events])
        self.assertNotIn("ai:ready", events[1][events[1].index("--label") + 1])
        self.assertIn("--add-label", events[3])
        self.assertIn("ai:ready", events[3])

    def test_task_creation_without_ready_has_one_read_and_no_edit(self):
        result, events = self.task_creation_fixture(ready=False, dependencies="", repo=None)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["repo", "view"], ["issue", "create"], ["issue", "view"]], [event[:2] for event in events])
        self.assertNotIn("--blocked-by", events[1])

    def test_task_creation_preserves_body_bytes_and_accepts_bounded_complete_inputs(self):
        prefix = "## File ownership\n\n- app/**\n\n## Notes\n\n"
        for body, ready, dependencies in (
            (prefix + "\n日本語 'quotes' $() and trailing lines\n\n", True, "14,15"),
            (prefix + "x" * (65536 - len(prefix)), False, ""),
            ("An unfinished brief without an ownership section.\n", False, ""),
            (prefix, True, ",".join(str(n) for n in range(100, 150))),
        ):
            with self.subTest(body_bytes=len(body.encode()), ready=ready, dependencies=len(dependencies.split(","))):
                result, events = self.task_creation_fixture(body=body, ready=ready, dependencies=dependencies)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(1, sum(event[:2] == ["issue", "create"] for event in events))

    def test_task_creation_rejects_bad_graph_body_identity_and_labels_before_ready(self):
        for defect in ("wrong-body", "wrong-title", "wrong-url", "wrong-number", "bad-id", "closed-task",
                       "wrong-parent", "absent-parent", "cross-repo-parent", "wrong-dependency", "duplicate-dependency",
                       "duplicate-id", "truncated-dependencies", "malformed-dependencies", "string-count",
                       "cross-repo-dependency", "unknown-dependency-state", "missing-label", "wrong-exec",
                       "duplicate-label", "labels-connection", "labels-cap", "premature-ready", "read-error", "view-oversized"):
            with self.subTest(defect=defect):
                result, events = self.task_creation_fixture(defect)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(1, sum(event[:2] == ["issue", "create"] for event in events))
                self.assertFalse(any(event[:2] == ["issue", "edit"] for event in events))
                self.assertNotIn("Created and verified", result.stdout)

    def test_task_creation_ambiguous_create_and_readiness_never_retry_or_claim_success(self):
        for defect in ("create-failed-known", "create-malformed", "create-wrong-repo", "create-oversized", "create-nul",
                       "ready-write-error", "ready-not-applied", "final-read-error", "final-body-drift", "final-id-drift",
                       "final-parent-id-drift", "final-blocker-id-drift"):
            with self.subTest(defect=defect):
                result, events = self.task_creation_fixture(defect)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(1, sum(event[:2] == ["issue", "create"] for event in events))
                self.assertLessEqual(sum(event[:2] == ["issue", "edit"] for event in events), 1)
                self.assertFalse(any(event[:2] == ["issue", "delete"] for event in events))
                self.assertNotIn("Created and verified", result.stdout)
                self.assertIn("unconfirmed", result.stderr)
                if defect in ("create-failed-known", "ready-write-error", "final-read-error"):
                    self.assertIn("https://github.com/fixture/adopter/issues/40", result.stderr)

    def test_task_creation_invalid_inputs_and_ownership_do_not_create(self):
        for kwargs in ({"dependencies": "14,14"}, {"dependencies": "0"}, {"dependencies": "01"},
                       {"dependencies": "14,"}, {"dependencies": ",14"}, {"dependencies": "14,x"},
                       {"dependencies": ",".join(str(n) for n in range(1, 52))},
                       {"repo": "-evil"}, {"repo": "other/adopter"}, {"defect": "repo-read-error"},
                       {"body": "## File ownership\n\n- ../escape\n"}, {"body": "x" * 65537}, {"body": "NUL\0input"}):
            with self.subTest(kwargs={key: str(value)[:40] for key, value in kwargs.items()}):
                result, events = self.task_creation_fixture(**kwargs)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(any(event[:2] == ["issue", "create"] for event in events))

    def test_task_creation_local_body_read_error_has_safe_diagnostic_and_no_write(self):
        result, events = self.task_creation_fixture("body-read-error")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], events)
        self.assertIn("invalid or incomplete Task inputs", result.stderr)
        self.assertNotIn(str(self.base), result.stderr + result.stdout)

    def test_task_creation_rejects_entire_dependency_value_before_any_gh_call(self):
        for dependencies in ("14,15\n", "14,15\r", "14,15\n,16", "14,15\n]", "14,15\t", "14,15\x01"):
            with self.subTest(dependencies=repr(dependencies)):
                result, events = self.task_creation_fixture(dependencies=dependencies)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual([], events)

    def complete_checker_source(self):
        source = self.clone_source()
        checker = self.kickoff_checker()
        for name in (*checker.FEEDBACK_PATHS, *checker.CONNECTOR_PATHS):
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        self.assertEqual([], checker.validate(source))
        self.assertEqual([], checker.validate_connector_companion(source))
        return source, checker

    def reseal_payload(self, source):
        # Self-consistent digests alone must not bypass the routing/review guard.
        manifest = source / INVENTORY
        rows = [line.split("\t") for line in manifest.read_text().splitlines()
                if line and not line.startswith("#")]
        digests = {name: hashlib.sha256((source / PAYLOAD / name).read_bytes()).hexdigest()
                   for name, _kind, _digest in rows}
        manifest.write_text("".join("\t".join((name, kind, digests[name])) + "\n"
                                    for name, kind, _digest in rows))
        parity = source / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        for row in value["files"]:
            row["target_sha256"] = digests[row["destination"]]
        for component in ("context_kickoff", "task_creation", "source_preparation", "task_selection", "ritual_verification"):
            for row in value.get(component, {}).get("target_files", []):
                if component == "task_selection" and row["path"] == RITUAL_PATH:
                    continue  # The T24 ritual digest is bound to its accepted merge.
                row["sha256"] = digests[row["path"]]
        parity.write_text(json.dumps(value))

    def test_kickoff_installed_entry_and_links_without_adopter_readme(self):
        (self.target / "README.md").write_text("Existing adopter README\n")
        (self.target / "README.md").chmod(0o600)
        (self.target / "AGENTS.md").write_text("Existing tuned instructions\n")
        before_git = self.snapshot(self.target / ".git")
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("Existing adopter README\n", (self.target / "README.md").read_text())
        self.assertEqual(0o600, (self.target / "README.md").stat().st_mode & 0o777)
        self.assertEqual("Existing tuned instructions\n", (self.target / "AGENTS.md").read_text())
        self.assertEqual(before_git, self.snapshot(self.target / ".git"))
        for name in KICKOFF_PATHS[:2]:
            self.assertEqual((ROOT / PAYLOAD / name).read_bytes(), (self.target / name).read_bytes())
            self.assertEqual(0o644, (self.target / name).stat().st_mode & 0o777)
        skill = (self.target / KICKOFF_PATHS[0]).read_text()
        builtin = (self.target / KICKOFF_PATHS[1]).read_text()
        self.assertIn("`builtin.retrieve`", skill)
        self.assertNotIn("/kickoff-context", builtin)
        self.assertIn("human says stop", builtin)
        self.assertIn("Do not write to `.github/docs/agreements/`", builtin)
        for name in KICKOFF_PATHS[:2]:
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", (self.target / name).read_text()):
                target, _, anchor = link.partition("#")
                path = (self.target / name).parent / target
                self.assertTrue(path.is_file(), link)
                if anchor:
                    self.assertIn("## " + anchor, path.read_text(), link)

    def test_kickoff_checker_rejects_resealed_routing_and_boundary_mutations(self):
        source, checker = self.complete_checker_source()
        cases = (
            (KICKOFF_PATHS[0], "`builtin.retrieve`", "`speckit.retrieve`", "routing"),
            (KICKOFF_PATHS[0], "Only for explicit builtin kickoff", "For every collection pass", "routing"),
            (KICKOFF_PATHS[0], "read the builtin procedure only when this route is selected",
             "always preload the builtin procedure", "routing"),
            (KICKOFF_PATHS[0], "never present a generated candidate as a source fact",
             "treat generated candidates as source facts", "routing"),
            (KICKOFF_PATHS[1], "human says stop", "all questions are exhausted", "boundary"),
            (KICKOFF_PATHS[1], "Do not write to `.github/docs/agreements/`",
             "Write directly to `.github/docs/agreements/`", "boundary"),
            (KICKOFF_PATHS[1], "human-reviewed distillation PR", "automatic promotion", "boundary"),
            (KICKOFF_PATHS[1], "3–5 questions per round", "unlimited questions", "boundary"),
            (KICKOFF_PATHS[1], "`REQ-C##`", "temporary IDs", "boundary"),
            (KICKOFF_PATHS[1], "**Assumptions**", "**Facts**", "boundary"),
            (KICKOFF_PATHS[1], "redaction first", "unredacted capture", "boundary"),
            (KICKOFF_PATHS[2], "Registry preparation is not activation or context sufficiency",
             "Registry preparation proves activation and context sufficiency", "boundary"),
            (KICKOFF_PATHS[0], "builtin.md#retrieve", "builtin.md#pin", "routing"),
            (KICKOFF_PATHS[1], "context-collection/SKILL.md", "missing/SKILL.md", "resource"),
            (KICKOFF_PATHS[2], "setup-sources.sh)", "missing-setup.sh)", "resource"),
        )
        originals = {name: (source / PAYLOAD / name).read_bytes() for name in KICKOFF_PATHS}
        for name, old, new, reason in cases:
            with self.subTest(name=name, mutation=new):
                path = source / PAYLOAD / name
                text = originals[name].decode()
                self.assertIn(old, text)
                path.write_text(text.replace(old, new))
                self.reseal_payload(source)
                errors = checker.validate(source)
                self.assertTrue(any("kickoff" in item and reason in item for item in errors), errors)
                if new == "`speckit.retrieve`":
                    result = subprocess.run([sys.executable, "-I", str(ROOT / ".github/scripts/check-installer.py"),
                                             "--root", str(source)], capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("kickoff routing", result.stdout)
                path.write_bytes(originals[name])
                self.reseal_payload(source)
        self.assertEqual([], checker.validate(source))

    def test_kickoff_prompt_provenance_and_closed_target_bindings(self):
        source, checker = self.complete_checker_source()
        parity = source / ".github/distribution/source-parity.v1.json"
        original = parity.read_bytes()
        value = json.loads(original)
        self.assertIn("context_kickoff", value)
        self.assertEqual(list(KICKOFF_PATHS), [row["path"] for row in value["context_kickoff"]["target_files"]])
        for mutation in ("missing", "prompt", "target", "extra", "mode"):
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                record = value["context_kickoff"]
                if mutation == "missing": del value["context_kickoff"]
                elif mutation == "prompt": record["source_files"][".github/prompts/kickoff-context.prompt.md"] = "0" * 40
                elif mutation == "target": record["target_files"][0]["sha256"] = "0" * 64
                elif mutation == "extra": record["automatic_activation"] = True
                else: record["target_files"][0]["mode"] = "100755"
                parity.write_text(json.dumps(value))
                self.assertTrue(any("kickoff" in item for item in checker.validate(source)))
        parity.write_bytes(original)

    def assert_payload_upgrade_preserves_adopter_state(self, paths, base, *, changed=None):
        # Actual accepted old bytes and actual current new bytes, real Bash only.
        old = self.clone_source()
        for name in paths:
            data = subprocess.check_output(["git", "-C", str(ROOT), "show", base + ":" + PAYLOAD + "/" + name])
            (old / PAYLOAD / name).write_bytes(data)
        self.reseal_payload(old)
        self.assertEqual(0, self.run_install("--apply", source=old).returncode)
        preserved = ("README.md", "AGENTS.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md", REGISTRY_REL)
        for name in preserved:
            (self.target / name).write_text("Synthetic adopter-owned content\n")
            (self.target / name).chmod(0o600)
        self.commit_adopter("synthetic old installation")
        (self.target / "later.txt").write_text("Unrelated staged content\n")
        self.git("add", "later.txt")
        before = self.snapshot(self.target)
        modes = {str(path.relative_to(self.target)): path.stat().st_mode for path in self.target.rglob("*")}
        self.old_source, self.new_source = old, ROOT
        self.transaction = self.base / "kickoff operation"
        result = self.upgrade("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        after = self.snapshot(self.target)
        changed = paths[:2] if changed is None else changed
        self.assertEqual(set(changed), {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)})
        for name in changed:
            self.assertNotEqual((old / PAYLOAD / name).read_bytes(), (ROOT / PAYLOAD / name).read_bytes())
            self.assertEqual((ROOT / PAYLOAD / name).read_bytes(), (self.target / name).read_bytes())
        for name in preserved:
            self.assertEqual("Synthetic adopter-owned content\n", (self.target / name).read_text())
            self.assertEqual(0o600, (self.target / name).stat().st_mode & 0o777)
        result = self.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertEqual(modes, {str(path.relative_to(self.target)): path.stat().st_mode for path in self.target.rglob("*")})

    def test_kickoff_known_old_upgrade_and_rollback_preserve_adopter_state(self):
        self.assert_payload_upgrade_preserves_adopter_state(KICKOFF_PATHS, KICKOFF_BASE)

    def test_task_creation_known_old_upgrade_and_rollback_preserve_adopter_state(self):
        self.assert_payload_upgrade_preserves_adopter_state(TASK_CREATION_PATHS, TASK_CREATION_BASE)

    def test_source_preparation_combined_three_engine_upgrade_and_rollback_preserve_registry(self):
        paths = TASK_CREATION_PATHS + (SOURCE_REGISTRY_PATH,)
        self.assert_payload_upgrade_preserves_adopter_state(paths, TASK_CREATION_BASE, changed=paths)

    def test_kickoff_changes_only_three_payload_bytes_and_no_layout_or_modes(self):
        old = subprocess.check_output(["git", "-C", str(ROOT), "show", KICKOFF_BASE + ":" + INVENTORY], text=True)
        old_rows = [line.split("\t") for line in old.splitlines() if line and not line.startswith("#")]
        accepted = subprocess.check_output(["git", "-C", str(ROOT), "show", TASK_CREATION_BASE + ":" + INVENTORY], text=True)
        new_rows = [line.split("\t") for line in accepted.splitlines() if line and not line.startswith("#")]
        self.assertEqual(47, len(new_rows))
        self.assertEqual([row[:2] for row in old_rows], [row[:2] for row in new_rows])
        self.assertEqual(set(KICKOFF_PATHS), {old[0] for old, new in zip(old_rows, new_rows) if old[2] != new[2]})
        for name, _kind, digest in new_rows:
            if name not in KICKOFF_PATHS:
                continue
            path = ROOT / PAYLOAD / name
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(0o644, path.stat().st_mode & 0o777)

    def test_task_creation_changes_only_three_payload_bytes_and_no_layout_or_modes(self):
        old = subprocess.check_output(["git", "-C", str(ROOT), "show", TASK_CREATION_BASE + ":" + INVENTORY], text=True)
        old_rows = [line.split("\t") for line in old.splitlines() if line and not line.startswith("#")]
        accepted = subprocess.check_output(["git", "-C", str(ROOT), "show", TASK_SELECTION_BASE + ":" + INVENTORY], text=True)
        new_rows = [line.split("\t") for line in accepted.splitlines() if line and not line.startswith("#")]
        self.assertEqual(47, len(new_rows))
        self.assertEqual([row[:2] for row in old_rows], [row[:2] for row in new_rows])
        self.assertEqual(set(TASK_CREATION_PATHS + (SOURCE_REGISTRY_PATH,)),
                         {old[0] for old, new in zip(old_rows, new_rows) if old[2] != new[2]})

    def test_task_selection_four_payload_changes_preserve_layout_modes_and_other_43(self):
        old = subprocess.check_output(["git", "-C", str(ROOT), "show", TASK_SELECTION_BASE + ":" + INVENTORY], text=True)
        old_rows = [line.split("\t") for line in old.splitlines() if line and not line.startswith("#")]
        accepted = subprocess.check_output(["git", "-C", str(ROOT), "show", TASK_SELECTION_ACCEPTED + ":" + INVENTORY], text=True)
        new_rows = [line.split("\t") for line in accepted.splitlines() if line and not line.startswith("#")]
        self.assertEqual(47, len(new_rows))
        self.assertEqual([row[:2] for row in old_rows], [row[:2] for row in new_rows])
        self.assertEqual(set(TASK_SELECTION_PATHS), {old[0] for old, new in zip(old_rows, new_rows) if old[2] != new[2]})
        for name, _kind, digest in new_rows:
            data = subprocess.check_output(['git', '-C', str(ROOT), 'show', TASK_SELECTION_ACCEPTED + ':' + PAYLOAD + '/' + name])
            self.assertEqual(digest, hashlib.sha256(data).hexdigest())
            entry = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', TASK_SELECTION_ACCEPTED, '--', PAYLOAD + '/' + name], text=True)
            self.assertTrue(entry.startswith('100644 blob '), entry)

    def test_ritual_two_payload_changes_preserve_45_and_layout_modes(self):
        accepted = subprocess.check_output(['git', '-C', str(ROOT), 'show', TASK_SELECTION_ACCEPTED + ':' + INVENTORY], text=True)
        old_rows = [line.split('\t') for line in accepted.splitlines() if line and not line.startswith('#')]
        historical = subprocess.check_output(['git', '-C', str(ROOT), 'show', RITUAL_INITIAL_HEAD + ':' + INVENTORY], text=True)
        rows = [line.split('\t') for line in historical.splitlines() if line and not line.startswith('#')]
        self.assertEqual(47, len(rows))
        self.assertEqual([row[:2] for row in old_rows], [row[:2] for row in rows])
        self.assertEqual(set(RITUAL_PATHS), {old[0] for old, new in zip(old_rows, rows) if old[2] != new[2]})
        for name, _kind, digest in rows:
            data = subprocess.check_output(['git', '-C', str(ROOT), 'show', RITUAL_INITIAL_HEAD + ':' + PAYLOAD + '/' + name])
            self.assertEqual(digest, hashlib.sha256(data).hexdigest())
            entry = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', RITUAL_INITIAL_HEAD, '--', PAYLOAD + '/' + name], text=True)
            self.assertTrue(entry.startswith('100644 blob '), entry)

    def test_audit_cumulative_eight_payload_changes_preserve_39_and_original_ritual(self):
        accepted = subprocess.check_output(['git', '-C', str(ROOT), 'show', TASK_SELECTION_ACCEPTED + ':' + INVENTORY], text=True)
        old_rows = [line.split('\t') for line in accepted.splitlines() if line and not line.startswith('#')]
        rows = [line.split('\t') for line in (ROOT / INVENTORY).read_text().splitlines() if line and not line.startswith('#')]
        self.assertEqual(47, len(rows))
        self.assertEqual([row[:2] for row in old_rows], [row[:2] for row in rows])
        self.assertEqual(set(RITUAL_PATHS + AUDIT_PAYLOAD_PATHS), {old[0] for old, new in zip(old_rows, rows) if old[2] != new[2]})
        for name, _kind, digest in rows:
            self.assertEqual(digest, hashlib.sha256((ROOT / PAYLOAD / name).read_bytes()).hexdigest())
            self.assertEqual(0o644, (ROOT / PAYLOAD / name).stat().st_mode & 0o777)
        for name in RITUAL_PATHS:
            original = subprocess.check_output(['git', '-C', str(ROOT), 'show', RITUAL_INITIAL_HEAD + ':' + PAYLOAD + '/' + name])
            self.assertEqual(original, (ROOT / PAYLOAD / name).read_bytes())

    def test_audit_upgrade_and_rollback_preserve_adopter_state(self):
        self.assert_payload_upgrade_preserves_adopter_state(AUDIT_PAYLOAD_PATHS, RITUAL_INITIAL_HEAD,
            changed=tuple(path for path in AUDIT_PAYLOAD_PATHS if path != ".github/codex-instructions.md"))

    def test_ritual_known_old_upgrade_and_rollback_preserve_adopter_state(self):
        self.assert_payload_upgrade_preserves_adopter_state(RITUAL_PATHS, TASK_SELECTION_ACCEPTED, changed=RITUAL_PATHS)

    def test_ritual_broken_installed_copies_expose_guards(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        helper = self.target / RITUAL_PATH
        original = helper.read_text()
        pr = 'repos/{owner}/{repo}/pulls/1'
        for defect, before, after in (
            ('head', '[[ "$final_pr" == "$pr_snapshot" ]] || observation_fail pr-drift', ': # omitted snapshot comparison'),
            ('date', 'valid_timestamp "$timestamp" || observation_fail commit-date', ': # omitted calendar check'),
            ('claim', 'if ! has_marker CLAIM; then', 'if [[ "$markers" != *CLAIM* ]]; then'),
        ):
            with self.subTest(defect=defect):
                self.assertIn(before, original)
                helper.write_text(original.replace(before, after, 1))
                records = self.ordinary_records()
                if defect == 'head':
                    changed = copy.deepcopy(records[pr]); changed['head']['sha'] = 'f' * 40
                    records[pr] = {'__responses__': [records[pr], changed]}
                elif defect == 'date': records[pr + '/commits'][0]['commit']['committer']['date'] = '2026-02-30T00:05:00Z'
                else:
                    issue = 'repos/{owner}/{repo}/issues/2'
                    records[issue + '/comments'].pop(0)
                    records[issue + '/comments'][-1]['body'] = records[issue + '/comments'][-1]['body'].replace('Task #2 worker', 'CLAIM worker')
                    records[issue]['comments'] = 2
                result = self.packaged_json(RITUAL_PATH, records, '1', installed=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn('PASS:', result.stdout)
                helper.write_text(original)
                self.assert_ritual_refuses(records)

    def test_ritual_checker_rejects_resealed_guard_and_provenance_drift(self):
        source, checker = self.complete_checker_source()
        for name, before, after in (
            (RITUAL_PATH, 'commit_count <= 250', 'commit_count <= 999'),
            (RITUAL_PATH, 'valid_timestamp "$timestamp" || observation_fail commit-date', ': # omitted date check'),
            (RITUAL_PATH, '"$unique_commits" == "$commit_count"', 'true'),
            (RITUAL_PATH, '"$final_comments" == "$comment_snapshot"', 'true'),
            (RITUAL_PATHS[1], 'bash .github/scripts/check-task-ritual.sh 123', '.github/scripts/check-task-ritual.sh 123'),
        ):
            with self.subTest(before=before):
                path = source / PAYLOAD / name
                original = path.read_text(); self.assertIn(before, original)
                path.write_text(original.replace(before, after)); self.reseal_payload(source)
                self.assertTrue(any('ordinary ritual' in error for error in checker.validate(source)))
                path.write_text(original); self.reseal_payload(source)
        parity = source / '.github/distribution/source-parity.v1.json'
        original = parity.read_text()
        for defect in ('missing', 'source', 'limit', 'target', 'extra'):
            value = json.loads(original)
            record = value['ritual_verification']
            if defect == 'missing': del value['ritual_verification']
            if defect == 'source': record['source_files'][RITUAL_PATH] = '0' * 40
            if defect == 'limit': record['commit_limit'] = 999
            if defect == 'target': record['target_files'][0]['mode'] = '100755'
            if defect == 'extra': record['runtime_authenticated'] = True
            parity.write_text(json.dumps(value))
            self.assertTrue(any('ordinary ritual' in error for error in checker.validate(source)))
        parity.write_text(original)
        self.assertEqual([], checker.validate(source))

    def test_task_selection_known_old_upgrade_and_rollback_preserve_adopter_state(self):
        self.assert_payload_upgrade_preserves_adopter_state(TASK_SELECTION_PATHS, TASK_SELECTION_BASE,
                                                          changed=TASK_SELECTION_PATHS)

    def test_task_selection_checker_rejects_resealed_guards_and_provenance_drift(self):
        source, checker = self.complete_checker_source()
        for name, before, after in (
            (TASK_SELECTION_PATHS[2], '.|./*|*/.|*/./*|*//*) invalid=1; continue ;;', '.|./*) invalid=1; continue ;;'),
            (TASK_SELECTION_PATHS[1], '($url.host | ascii_downcase) == $host', 'true'),
            (TASK_SELECTION_PATHS[1], '($repo // $selected)', '($repo // "-")'),
            (TASK_SELECTION_PATHS[3], '*) return 1 ;;', '*) return 0 ;;'),
            (TASK_SELECTION_PATHS[3], '[[ "$base_anchor" == "$head_anchor" ]] || return 1', ': # omitted exact comparison'),
        ):
            with self.subTest(name=name, guard=before):
                path = source / PAYLOAD / name
                original = path.read_text()
                self.assertIn(before, original)
                path.write_text(original.replace(before, after))
                self.reseal_payload(source)
                self.assertTrue(any('task selection' in error for error in checker.validate(source)))
                path.write_text(original)
                self.reseal_payload(source)
        parity = source / '.github/distribution/source-parity.v1.json'
        original = parity.read_text()
        for mutation in ('missing', 'source', 'extra', 'digest', 'mode'):
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                record = value['task_selection']
                if mutation == 'missing': del value['task_selection']
                elif mutation == 'source': record['source_files']['.github/scripts/ownership-overlap.sh'] = '0' * 40
                elif mutation == 'extra': record['automatic_dispatch'] = True
                elif mutation == 'digest': record['target_files'][0]['sha256'] = '0' * 64
                else: record['target_files'][0]['mode'] = '100755'
                parity.write_text(json.dumps(value))
                self.assertTrue(any('task selection' in error for error in checker.validate(source)))
        parity.write_text(original)
        self.assertEqual([], checker.validate(source))

    def test_task_creation_checker_rejects_resealed_unsafe_readiness_and_source_drift(self):
        source, checker = self.complete_checker_source()
        path = source / PAYLOAD / TASK_CREATION_PATHS[1]
        original = path.read_text()
        for old, replacement in (
            ('--label "type:task,exec:$EXEC"', '--label "type:task,exec:$EXEC,ai:ready"'),
            ('read_back false || unconfirmed "Task read-back"', ': # omitted read-back'),
            ('read_back true || unconfirmed "Task readiness read-back"', ': # omitted final verification'),
            ('"$DEPS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$', 'true'),
        ):
            with self.subTest(replacement=replacement):
                self.assertIn(old, original)
                path.write_text(original.replace(old, replacement))
                self.reseal_payload(source)
                self.assertTrue(any("task creation" in error for error in checker.validate(source)))
                path.write_text(original)
                self.reseal_payload(source)
        parity = source / ".github/distribution/source-parity.v1.json"
        original_parity = parity.read_text()
        for mutation in ("missing", "source", "extra", "digest", "mode"):
            with self.subTest(mutation=mutation):
                value = json.loads(original_parity)
                record = value["task_creation"]
                if mutation == "missing": del value["task_creation"]
                elif mutation == "source": record["cli_source"] = "cli/cli@" + "0" * 40
                elif mutation == "extra": record["retry"] = True
                elif mutation == "digest": record["target_files"][0]["sha256"] = "0" * 64
                else: record["target_files"][0]["mode"] = "100755"
                parity.write_text(json.dumps(value))
                self.assertTrue(any("task creation" in error for error in checker.validate(source)))
        parity.write_text(original_parity)
        self.assertEqual([], checker.validate(source))

    def upgrade_fixture(self):
        old = self.clone_source()
        new = self.base / "new local source"
        shutil.copytree(old, new)
        rows = [line.split("\t") for line in (new / INVENTORY).read_text().splitlines()
                if line and not line.startswith("#")]
        changed = [row[0] for row in rows if row[1] == "engine"][:2]
        for name in changed:
            path = new / PAYLOAD / name
            path.write_bytes(path.read_bytes() + b"\nSynthetic newer fixture.\n")
        (new / INVENTORY).write_text("".join("\t".join((name, kind,
            hashlib.sha256((new / PAYLOAD / name).read_bytes()).hexdigest())) + "\n"
            for name, kind, _ in rows))
        self.assertEqual(0, self.run_install("--apply", source=old).returncode)
        self.old_source, self.new_source, self.changed = old, new, changed
        self.transaction = self.base / "operation record"
        return changed

    def upgrade(self, *args, **kwargs):
        return self.run_install("--upgrade", "--old-source", str(self.old_source),
            "--transaction", str(self.transaction), *args, source=self.new_source, **kwargs)

    def rollback(self, *args, **kwargs):
        return self.run_install("--rollback", "--transaction", str(self.transaction),
            *args, source=self.new_source, **kwargs)

    def test_upgrade_roundtrip_preserves_customization_modes_and_git(self):
        self.upgrade_fixture()
        for name in ("AGENTS.md", "README.md", "SCAFFOLD-CHANGELOG.md",
                     ".github/codex-instructions.md", ".github/docs/agreements/requirements.md"):
            (self.target / name).write_text("adopter-owned\n")
            (self.target / name).chmod(0o600)
        self.commit_adopter("synthetic adopted baseline")
        (self.target / "staged.txt").write_text("unrelated staged change\n")
        self.git("add", "staged.txt")
        before = self.snapshot(self.target)
        modes = {p.relative_to(self.target): p.stat().st_mode for p in self.target.rglob("*")}
        result = self.upgrade("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        for name in self.changed:
            self.assertEqual((self.new_source / PAYLOAD / name).read_bytes(), (self.target / name).read_bytes())
        result = self.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertEqual(modes, {p.relative_to(self.target): p.stat().st_mode for p in self.target.rglob("*")})

    def test_upgrade_dry_run_and_already_new_create_no_record(self):
        self.upgrade_fixture()
        before = self.snapshot(self.base)
        result = self.upgrade()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.base))
        for name in self.changed:
            (self.target / name).write_bytes((self.new_source / PAYLOAD / name).read_bytes())
        before = self.snapshot(self.base)
        self.assertEqual(0, self.upgrade("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_absent_dry_run_target_stays_absent(self):
        self.upgrade_fixture()
        result = self.upgrade(target=self.base / "absent")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.base / "absent").exists())
        self.assertFalse(self.transaction.exists())

    def test_upgrade_unknown_engine_refuses_whole_plan(self):
        self.upgrade_fixture()
        (self.target / self.changed[-1]).write_text("unknown edit\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.upgrade("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_unknown_engine_mode_refuses(self):
        self.upgrade_fixture()
        (self.target / self.changed[-1]).chmod(0o755)
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.upgrade("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))
        self.assertEqual(0o755, (self.target / self.changed[-1]).stat().st_mode & 0o777)

    def test_rollback_original_absence_and_only_created_directories(self):
        self.upgrade_fixture()
        shutil.rmtree(self.target / ".codex")
        (self.target / "AGENTS.md").unlink()
        before = self.snapshot(self.target)
        self.assertEqual(0, self.upgrade("--apply").returncode)
        self.assertTrue((self.target / ".codex/agents/planner.toml").is_file())
        self.assertEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_rollback_preserves_unrelated_later_edits(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        (self.target / "app.py").write_text("later application edit\n")
        (self.target / "README.md").write_text("later notes\n")
        self.assertEqual(0, self.rollback("--apply").returncode)
        self.assertEqual("later application edit\n", (self.target / "app.py").read_text())
        self.assertEqual("later notes\n", (self.target / "README.md").read_text())

    def test_rollback_post_upgrade_edit_refuses_all_writes(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        (self.target / self.changed[-1]).write_text("later affected edit\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_rollback_dry_run_and_repeat_are_zero_write(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        before = self.snapshot(self.base)
        self.assertEqual(0, self.rollback().returncode)
        self.assertEqual(before, self.snapshot(self.base))
        self.assertEqual(0, self.rollback("--apply").returncode)
        before = self.snapshot(self.base)
        self.assertEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_transaction_overlap_or_existing_record_refuses(self):
        self.upgrade_fixture()
        for transaction in (self.target / "record", self.new_source / "record", self.old_source / "record", self.base):
            with self.subTest(transaction=transaction.name):
                self.transaction = transaction
                before = self.snapshot(self.base)
                self.assertNotEqual(0, self.upgrade("--apply").returncode)
                self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_backup_and_record_tampering_refuse(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        backup = self.transaction / "before-0"
        original = backup.read_bytes()
        backup.write_bytes(b"tampered\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))
        backup.write_bytes(original)
        record = self.transaction / "files.tsv"
        record.write_text(record.read_text().replace(self.changed[0], "../escape"))
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_interrupted_apply_is_explicitly_recoverable(self):
        self.upgrade_fixture()
        before = self.snapshot(self.target)
        fake = self.base / "copy-failure-bin"
        fake.mkdir()
        # Real Bash engine and real copy; fail only the second target replacement.
        cp = fake / "cp"
        cp.write_text('#!/bin/sh\ncase "$*" in *"' + self.changed[-1] + '") exit 77 ;; esac\nexec /bin/cp "$@"\n')
        cp.chmod(0o755)
        result = subprocess.run(["bash", str(INSTALLER), "--upgrade", "--apply", "--old-source",
            str(self.old_source), "--transaction", str(self.transaction), str(self.target)],
            env=dict(os.environ, SCAFFOLD_SOURCE_DIR=str(self.new_source), PATH=str(fake) + os.pathsep + os.environ['PATH']),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual((self.new_source / PAYLOAD / self.changed[0]).read_bytes(), (self.target / self.changed[0]).read_bytes())
        self.assertIn("partial", (self.transaction / "status").read_text())
        result = self.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))

    def run_upgrade_with_copy_probe(self, code):
        fake = self.base / "instrumented-copy-bin"
        fake.mkdir()
        cp = fake / "cp"
        cp.write_text('#!/usr/bin/env python3\nimport os,pathlib,subprocess,sys\n'
                      'src,dst=sys.argv[-2:]\nroot=pathlib.Path(os.environ["FIXTURE_TRANSACTION"])\n'
                      + code + '\nsys.exit(subprocess.run(["/bin/cp",*sys.argv[1:]]).returncode)\n')
        cp.chmod(0o755)
        return subprocess.run(["bash", str(INSTALLER), "--upgrade", "--apply", "--old-source",
            str(self.old_source), "--transaction", str(self.transaction), str(self.target)],
            env=dict(os.environ, SCAFFOLD_SOURCE_DIR=str(self.new_source),
                     FIXTURE_TRANSACTION=str(self.transaction), FIXTURE_TARGET=str(self.target),
                     PATH=str(fake) + os.pathsep + os.environ['PATH']),
            capture_output=True, text=True, timeout=30)

    def test_upgrade_complete_recovery_data_precedes_first_target_write(self):
        self.upgrade_fixture()
        result = self.run_upgrade_with_copy_probe(
            'if dst.startswith(os.environ["FIXTURE_TARGET"]+"/"):\n'
            '    assert (root/"before-0").is_file() and (root/"before-1").is_file()\n'
            '    assert len((root/"files.tsv").read_text().splitlines())==2\n'
            '    assert (root/"meta.tsv").is_file() and (root/"directories.tsv").is_file()\n'
            '    assert (root/"record.sha256").is_file() and (root/"status").is_file()\n')
        self.assertEqual(0, result.returncode, result.stderr)

    def test_upgrade_prewrite_backup_failure_leaves_target_unchanged(self):
        self.upgrade_fixture()
        before = self.snapshot(self.target)
        result = self.run_upgrade_with_copy_probe('if dst==str(root/"before-1"): sys.exit(77)\n')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertIn("partial", (self.transaction / "status").read_text())
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_rollback_missing_or_unsafe_backup_and_record_refuse(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        for name in ("before-0", "files.tsv"):
            path = self.transaction / name
            data, mode = path.read_bytes(), path.stat().st_mode & 0o777
            for kind in ("missing", "symlink", "hardlink", "fifo", "oversized"):
                with self.subTest(name=name, kind=kind):
                    path.unlink()
                    outside = self.base / "outside-data"
                    outside.write_bytes(data)
                    if kind == "symlink": path.symlink_to(outside)
                    elif kind == "hardlink": os.link(outside, path)
                    elif kind == "fifo": os.mkfifo(path)
                    elif kind == "oversized": path.write_bytes(b"x" * (1024 * 1024 + 1))
                    # Snapshot only targets: generic snapshot's FIFO classification
                    # does not open the FIFO, and the actual engine must not either.
                    before = self.snapshot(self.target)
                    result = self.rollback("--apply")
                    self.assertNotEqual(0, result.returncode, result.stdout)
                    self.assertEqual(before, self.snapshot(self.target))
                    if path.exists() or path.is_symlink(): path.unlink()
                    path.write_bytes(data); path.chmod(mode); outside.unlink()

    def test_rollback_affected_mode_change_refuses_before_any_write(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        path = self.target / self.changed[-1]
        path.chmod(0o600)
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))
        self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_rollback_wrong_target_and_moved_transaction_refuse(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        other = self.base / "other adopter"
        shutil.copytree(self.target, other)
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply", target=other).returncode)
        self.assertEqual(before, self.snapshot(self.base))
        renamed = self.base / "moved transaction"
        self.transaction.rename(renamed); self.transaction = renamed
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_rollback_created_directory_with_later_unrelated_child_refuses(self):
        self.upgrade_fixture()
        shutil.rmtree(self.target / ".codex")
        self.assertEqual(0, self.upgrade("--apply").returncode)
        unrelated = self.target / ".codex/notes.md"
        unrelated.write_text("keep later unrelated notes\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_upgrade_old_source_drift_and_transaction_symlink_refuse(self):
        self.upgrade_fixture()
        path = self.old_source / PAYLOAD / self.changed[-1]
        data = path.read_bytes()
        path.write_text("old source drift\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.upgrade("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))
        path.write_bytes(data)
        self.transaction.symlink_to(self.base / "missing")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.upgrade("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_rollback_resealed_unsafe_path_is_not_executed(self):
        self.upgrade_fixture()
        self.assertEqual(0, self.upgrade("--apply").returncode)
        path = self.transaction / "files.tsv"
        path.write_text(path.read_text().replace(self.changed[0], "../escape"))
        data = b"".join((self.transaction / name).read_bytes()
                        for name in ("meta.tsv", "files.tsv", "directories.tsv"))
        (self.transaction / "record.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
        before = self.snapshot(self.base)
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot(self.base))

    def test_rollback_noncanonical_records_refuse(self):
        self.upgrade_fixture()
        shutil.rmtree(self.target / ".codex")
        self.assertEqual(0, self.upgrade("--apply").returncode)
        records = {name: (self.transaction / name).read_bytes()
                   for name in ("meta.tsv", "files.tsv", "directories.tsv", "status")}
        cases = [
            ("files.tsv", records["files.tsv"].replace(b".agents/", b".ag\x00ents/", 1)),
            ("files.tsv", records["files.tsv"].rstrip(b"\n")),
            ("meta.tsv", records["meta.tsv"].replace(b"schema", b"sch\x00ema", 1)),
            ("status", records["status"].replace(b"applied", b"app\x00lied", 1)),
            ("directories.tsv", b"\n".join(reversed(records["directories.tsv"].splitlines())) + b"\n"),
        ]
        for name, data in cases:
            with self.subTest(name=name, digest=hashlib.sha256(data).hexdigest()):
                for key, value in records.items(): (self.transaction / key).write_bytes(value)
                (self.transaction / name).write_bytes(data)
                sealed = b"".join((self.transaction / key).read_bytes()
                                   for key in ("meta.tsv", "files.tsv", "directories.tsv"))
                (self.transaction / "record.sha256").write_text(hashlib.sha256(sealed).hexdigest() + "\n")
                before = self.snapshot(self.base)
                self.assertNotEqual(0, self.rollback("--apply").returncode)
                self.assertEqual(before, self.snapshot(self.base))

    def assert_refused_unchanged(self, *args, source=ROOT, target=None):
        target = target or self.target
        before = self.snapshot(target)
        result = self.run_install(*args, source=source, target=target)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertEqual(before, self.snapshot(target))
        return result

    def test_dry_run_preserves_target_git_and_source(self):
        before = self.snapshot(self.target)
        source_before = self.snapshot(ROOT / ".github/distribution")
        result = self.run_install("--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("install", result.stdout)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertEqual(source_before, self.snapshot(ROOT / ".github/distribution"))

    def test_default_is_dry_run(self):
        before = self.snapshot(self.target)
        self.assertEqual(0, self.run_install().returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_absent_dry_run_target_stays_absent(self):
        target = self.base / "absent"
        result = self.run_install("--dry-run", target=target)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(target.exists())

    def test_apply_installs_exact_payload_without_git_mutation(self):
        git_before = self.snapshot(self.target / ".git")
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = ROOT / PAYLOAD
        files = [p for p in payload.rglob("*") if p.is_file()]
        self.assertEqual(47, len(files))
        for source in files:
            installed = self.target / source.relative_to(payload)
            self.assertEqual(source.read_bytes(), installed.read_bytes())
            self.assertEqual(0o644, installed.stat().st_mode & 0o777)
        for name in KICKOFF_PATHS:
            installed = self.target / name
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", installed.read_text()):
                target, _, anchor = link.partition("#")
                linked = installed.parent / target
                self.assertTrue(linked.is_file(), link)
                if anchor:
                    self.assertIn("## " + anchor, linked.read_text().splitlines(), link)
        self.assertEqual(git_before, self.snapshot(self.target / ".git"))
        self.assertFalse((self.target / ".github/governance").exists())
        self.assertFalse((self.target / "tests/conformance/results.json").exists())

    def test_identical_reapply_is_noop(self):
        self.assertEqual(0, self.run_install("--apply").returncode)
        before = self.snapshot(self.target)
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertNotIn("install\t", result.stdout)

    def test_tuned_instance_seed_and_unrelated_files_are_preserved(self):
        for name in ["AGENTS.md", "README.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md", "app/private.txt", "SCAFFOLD-CHANGELOG.md"]:
            p = self.target / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("adopter truth\n")
        result = self.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        for name in ["AGENTS.md", "README.md", ".github/codex-instructions.md",
                     ".github/docs/agreements/requirements.md", "app/private.txt", "SCAFFOLD-CHANGELOG.md"]:
            self.assertEqual("adopter truth\n", (self.target / name).read_text())

    def test_differing_engine_collision_refuses_before_any_write(self):
        p = self.target / ".agents/skills/verification/SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text("adopter modified engine\n")
        self.assert_refused_unchanged("--apply")

    def test_unknown_force_upgrade_and_conflicting_modes_refuse(self):
        for args in [("--force",), ("--upgrade",), ("--wat",), ("--apply", "--dry-run")]:
            with self.subTest(args=args):
                self.assert_refused_unchanged(*args)

    def test_apply_requires_existing_git_root(self):
        plain = self.base / "plain"
        plain.mkdir()
        self.assert_refused_unchanged("--apply", target=plain)
        sub = self.target / "sub"
        sub.mkdir()
        self.assert_refused_unchanged("--apply", target=sub)

    def test_target_root_and_ancestor_symlinks_refuse(self):
        link = self.base / "target-link"
        link.symlink_to(self.target, target_is_directory=True)
        self.assert_refused_unchanged("--apply", target=link)
        parent = self.base / "linked-parent"
        parent.symlink_to(self.base, target_is_directory=True)
        self.assert_refused_unchanged("--dry-run", target=parent / self.target.name)

    def test_target_leaf_ancestor_and_broken_symlinks_refuse(self):
        for name in ["AGENTS.md", ".agents", ".github/docs"]:
            with self.subTest(name=name):
                p = self.target / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.symlink_to(self.base / "missing")
                self.assert_refused_unchanged("--apply")
                p.unlink()

    def test_file_directory_collisions_refuse(self):
        (self.target / "AGENTS.md").mkdir()
        self.assert_refused_unchanged("--apply")
        (self.target / "AGENTS.md").rmdir()
        (self.target / ".github").write_text("not a directory")
        self.assert_refused_unchanged("--apply")

    def test_source_root_ancestor_and_leaf_symlinks_refuse(self):
        source = self.clone_source()
        link = self.base / "source-link"
        link.symlink_to(source, target_is_directory=True)
        self.assert_refused_unchanged("--apply", source=link)
        p = source / PAYLOAD / "AGENTS.md"
        original = p.read_bytes()
        p.unlink()
        other = self.base / "outside.md"
        other.write_bytes(original)
        p.symlink_to(other)
        self.assert_refused_unchanged("--apply", source=source)

    def test_payload_digest_drift_refuses(self):
        source = self.clone_source()
        with (source / PAYLOAD / "AGENTS.md").open("a") as out:
            out.write("changed\n")
        self.assert_refused_unchanged("--apply", source=source)

    def test_extra_payload_and_unsafe_duplicate_inventory_refuse(self):
        source = self.clone_source()
        (source / PAYLOAD / "extra.md").write_text("unreviewed")
        self.assert_refused_unchanged("--apply", source=source)
        (source / PAYLOAD / "extra.md").unlink()
        inventory = source / INVENTORY
        original = inventory.read_text()
        for text in [original + original.splitlines()[1] + "\n", original.replace("AGENTS.md", "../escape", 1),
                     original.replace("AGENTS.md", "agents.md", 1)]:
            inventory.write_text(text)
            self.assert_refused_unchanged("--apply", source=source)

    def test_missing_source_refuses(self):
        self.assert_refused_unchanged("--apply", source=self.base / "missing-source")

    def test_self_consistent_redirected_inventory_refuses(self):
        source = self.clone_source()
        payload = source / PAYLOAD
        (payload / "other.md").write_bytes((payload / "AGENTS.md").read_bytes())
        (payload / "AGENTS.md").unlink()
        inventory = source / INVENTORY
        inventory.write_text(inventory.read_text().replace("AGENTS.md", "other.md"))
        self.assert_refused_unchanged("--apply", source=source)

    def test_enumeration_failure_refuses_even_after_all_known_entries(self):
        fake = self.base / "bin"
        fake.mkdir()
        find = fake / "find"
        find.write_text('#!/bin/sh\n/usr/bin/find "$@"\nexit 1\n')
        find.chmod(0o755)
        before = self.snapshot(self.target)
        result = subprocess.run(["bash", str(INSTALLER), "--apply", str(self.target)],
                                env=dict(os.environ, SCAFFOLD_SOURCE_DIR=str(ROOT),
                                         PATH=str(fake) + os.pathsep + os.environ["PATH"]),
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_non_git_source_provenance_is_not_claimed_clean(self):
        result = self.run_install("--dry-run", source=self.clone_source())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("source-commit=unknown", result.stdout)

    def test_windows_drive_source_and_target_use_existing_cygpath(self):
        fake = self.base / "bin"
        fake.mkdir()
        converter = fake / "cygpath"
        converter.write_text("""#!/bin/sh
[ "$1" = -u ] && [ "$2" = -- ] || exit 1
case "$3" in
  C:/*) printf '%s\n' "$FIXTURE_SOURCE" ;;
  D:*) printf '%s\n' "$FIXTURE_TARGET" ;;
  *) exit 1 ;;
esac
""")
        converter.chmod(0o755)
        env = dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"],
                   SCAFFOLD_SOURCE_DIR="C:/reviewed/source", FIXTURE_SOURCE=str(ROOT),
                   FIXTURE_TARGET=str(self.target))
        git_before = self.snapshot(self.target / ".git")
        result = subprocess.run(["/bin/bash", str(INSTALLER), "--apply", "D:\\adopter"],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(git_before, self.snapshot(self.target / ".git"))
        self.assertEqual((ROOT / PAYLOAD / "AGENTS.md").read_bytes(),
                         (self.target / "AGENTS.md").read_bytes())

    def test_windows_drive_conversion_unavailable_or_invalid_refuses(self):
        fake = self.base / "bin"
        fake.mkdir()
        command = ["/bin/bash", str(INSTALLER), "--apply", "D:/adopter"]
        env = dict(os.environ, PATH=str(fake), SCAFFOLD_SOURCE_DIR="C:/source")
        before = self.snapshot(self.target)
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("require Git Bash cygpath", result.stderr)
        converter = fake / "cygpath"
        for script in ("#!/bin/sh\nexit 1\n", "#!/bin/sh\nprintf 'relative-path\\n'\n"):
            converter.write_text(script)
            converter.chmod(0o755)
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot(self.target))

    def test_frontier_failure_never_becomes_empty_success(self):
        fake = self.base / "bin"
        fake.mkdir()
        gh = fake / "gh"
        gh.write_text("#!/bin/sh\nexit 1\n")
        gh.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / PAYLOAD / ".agents/skills/plan-management/scripts/frontier.sh")],
                                env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"]),
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("No open Task", result.stdout)

    def test_inventory_checker_accepts_tree_and_rejects_provenance_drift(self):
        spec = importlib.util.spec_from_file_location("installer_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual([], checker.validate(ROOT))
        source = self.clone_source()
        parity = source / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        value["source_commit"] = "0" * 40
        parity.write_text(json.dumps(value))
        self.assertTrue(checker.validate(source))

    def test_frontier_keeps_ready_and_blocked_distinct_and_refuses_later_error(self):
        for shape, state, failure, succeeds in (
                (shape, state, failure, succeeds)
                for shape in ('connection', 'legacy-array')
                for state, failure, succeeds in (("OPEN", False, True), ("CLOSED", False, True),
                                                 ("UNKNOWN", False, False), ("OPEN", True, False))):
            with self.subTest(shape=shape, state=state, failure=failure):
                empty = {'nodes': [], 'totalCount': 0} if shape == 'connection' else []
                nodes = [{'number': 3}]
                blockers = {'nodes': nodes, 'totalCount': 1} if shape == 'connection' else nodes
                records = {'list': '1\tReady Task\n2\tDependent Task\n',
                    'fixture/adopter#1:blockedBy': {'blockedBy': empty},
                    'fixture/adopter#2:blockedBy': None if failure else {'blockedBy': blockers},
                    'fixture/adopter#3:state': {'state': state}}
                result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh',
                                            records, '--all')
                if succeeds:
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("#1\tReady Task", result.stdout)
                    self.assertIn("#2\tDependent Task", result.stdout)
                    self.assertEqual(state == "OPEN", "== Blocked ==" in result.stdout)
                else:
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual("", result.stdout, "never publish a partial actionable frontier")

    def test_frontier_typed_complete_dependencies_and_repository_identity(self):
        nodes = [{'number': 3, 'repository': {'nameWithOwner': 'other/dependency'}}]
        records = {'list': '1\tReady Task\n2\tDependent Task\n',
            'fixture/adopter#1:blockedBy': {'blockedBy': {'nodes': [], 'totalCount': 0}},
            'fixture/adopter#2:blockedBy': {'blockedBy': {'nodes': nodes, 'totalCount': 1}},
            'fixture/adopter#3:state': {'state': 'CLOSED'},
            'other/dependency#3:state': {'state': 'OPEN'}}
        for identity in ({'nameWithOwner': 'other/dependency'},
                         {'name': 'dependency', 'owner': {'login': 'other'}}):
            with self.subTest(identity=identity):
                nodes[0]['repository'] = identity
                result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh',
                                            records, '--all', '-R', 'fixture/adopter')
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn('== Blocked ==\n#2', result.stdout)
        records['other/dependency#3:state'] = None
        result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh', records)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('', result.stdout)

    def test_frontier_documented_node_url_preserves_host_and_repository(self):
        # CLI 2.96.0 LinkedIssue includes both URL and repository.nameWithOwner.
        node = {'id': 'fixture-id', 'title': 'Dependency', 'number': 3, 'state': 'CLOSED',
                'url': 'https://github.example/other/dependency/issues/3',
                'repository': {'nameWithOwner': 'other/dependency'}}
        records = {'list': '2\tDependent Task\n',
            'repository': {'url': 'https://github.example/fixture/adopter', 'nameWithOwner': 'fixture/adopter'},
            'fixture/adopter#2:blockedBy': {'blockedBy': {'nodes': [node], 'totalCount': 1}},
            'fixture/adopter#3:state': {'state': 'CLOSED'},
            'other/dependency#3:state': {'state': 'CLOSED'},
            'github.example/other/dependency#3:state': {'state': 'OPEN'}}
        result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh', records, '--all')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('== Blocked ==\n#2', result.stdout)
        for url in (None, 'https://github.example/other/dependency/issues/4',
                    'https://github.example/wrong/repo/issues/3',
                    'https://github.example/other/dependency/issues/3?extra',
                    'https://github.example/other/dependency/issues/3\n'):
            with self.subTest(url=url):
                node['url'] = url
                result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh', records)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual('', result.stdout)

    def test_frontier_selected_repository_and_foreign_host_refuse_before_output(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        records = {'list': '1\tReady\n2\tForeign\n',
                   'fixture/adopter#1:blockedBy': {'blockedBy': []},
                   'fixture/adopter#2:blockedBy': {'blockedBy': [
                       {'number': 3, 'url': 'https://other.example/fixture/adopter/issues/3'}]},
                   'other.example/fixture/adopter#3:state': {'state': 'CLOSED'}}
        result = self.packaged_json(TASK_SELECTION_PATHS[1], records, installed=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('', result.stdout)
        for repository in (None, {}, {'url': 'https://github.com/fixture/adopter', 'nameWithOwner': 'other/repo'},
                           {'url': 'https://github.com/fixture/adopter\n', 'nameWithOwner': 'fixture/adopter'},
                           {'url': 'https://github.com/other/repo', 'nameWithOwner': 'other/repo'}):
            with self.subTest(repository=repository):
                result = self.packaged_json(TASK_SELECTION_PATHS[1], {'list': '', 'repository': repository},
                                            '-R', 'fixture/adopter', installed=True)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual('', result.stdout)

    def test_frontier_same_number_different_repositories_stays_blocked(self):
        self.assertEqual(0, self.run_install('--apply').returncode)
        for shape in ('connection', 'legacy-array'):
            nodes = [{'number': 3}, {'number': 3, 'repository': {'nameWithOwner': 'other/dependency'}}]
            blockers = {'nodes': nodes, 'totalCount': 2} if shape == 'connection' else nodes
            records = {'list': '2\tDependent\n', 'fixture/adopter#2:blockedBy': {'blockedBy': blockers},
                       'fixture/adopter#3:state': {'state': 'CLOSED'}, 'other/dependency#3:state': {'state': 'OPEN'}}
            result = self.packaged_json(TASK_SELECTION_PATHS[1], records, '--all', installed=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('== Blocked ==\n#2\tDependent', result.stdout)

    def test_frontier_missing_malformed_and_incomplete_dependencies_never_publish(self):
        invalid = [None, {}, {'blockedBy': None}, {'blockedBy': {}},
            {'blockedBy': {'nodes': [], 'totalCount': 1}},
            {'blockedBy': {'nodes': [], 'totalCount': '0'}},
            {'blockedBy': {'nodes': [], 'totalCount': False}},
            {'blockedBy': {'nodes': [], 'totalCount': -1}},
            {'blockedBy': {'nodes': [], 'totalCount': 0.5}},
            {'blockedBy': {'nodes': None, 'totalCount': 0}},
            {'blockedBy': {'nodes': [{'number': 3}], 'totalCount': 0}},
            {'blockedBy': {'nodes': [{'number': 3}, {'number': 3}], 'totalCount': 2}},
            {'blockedBy': {'nodes': [
                {'number': 3, 'repository': {'nameWithOwner': 'other/dependency'}},
                {'number': 3, 'repository': {'nameWithOwner': 'Other/Dependency'}}], 'totalCount': 2}},
            {'blockedBy': {'nodes': [
                {'number': 3, 'url': 'https://github.example/other/dependency/issues/3'},
                {'number': 3, 'url': 'https://GitHub.Example/Other/Dependency/issues/3'}], 'totalCount': 2}},
            {'blockedBy': {'nodes': [{'number': n} for n in range(1, 51)], 'totalCount': 51}}]
        for node in (None, {}, {'number': 0}, {'number': -1}, {'number': 2.5},
                     {'number': True}, {'number': '3'},
                     {'number': 3, 'repository': None}, {'number': 3, 'repository': {}},
                     {'number': 3, 'repository': {'nameWithOwner': 'other/repo\tbad'}},
                     {'number': 3, 'repository': {'nameWithOwner': '../repo'}},
                     {'number': 3, 'repository': {'nameWithOwner': 'other/repo',
                                                'name': 'different', 'owner': {'login': 'other'}}}):
            invalid.extend([{'blockedBy': [node]}, {'blockedBy': {'nodes': [node], 'totalCount': 1}}])
        for value in invalid:
            with self.subTest(value=value):
                records = {'list': '1\tReady Task\n2\tDependent Task\n',
                    'fixture/adopter#1:blockedBy': {'blockedBy': []},
                    'fixture/adopter#2:blockedBy': value,
                    'fixture/adopter#3:state': {'state': 'CLOSED'},
                    'other/dependency#3:state': {'state': 'CLOSED'},
                    'Other/Dependency#3:state': {'state': 'CLOSED'},
                    'github.example/other/dependency#3:state': {'state': 'CLOSED'},
                    'GitHub.Example/Other/Dependency#3:state': {'state': 'CLOSED'}}
                result = self.packaged_json('.agents/skills/plan-management/scripts/frontier.sh', records)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual('', result.stdout, 'late invalid data must not publish earlier ready Tasks')

    def test_checker_rejects_wrong_preservation_class_and_malformed_parity_row(self):
        spec = importlib.util.spec_from_file_location("installer_checker", ROOT / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        source = self.clone_source()
        inventory = source / INVENTORY
        original = inventory.read_text()
        inventory.write_text(original.replace("\tengine\t", "\ttuned\t", 1))
        self.assertTrue(checker.validate(source))
        self.assert_refused_unchanged("--apply", source=source)
        inventory.write_text(original)
        parity = source / ".github/distribution/source-parity.v1.json"
        value = json.loads(parity.read_text())
        value["files"][0] = "not-a-record"
        parity.write_text(json.dumps(value))
        self.assertTrue(checker.validate(source))


if __name__ == "__main__":
    unittest.main()
