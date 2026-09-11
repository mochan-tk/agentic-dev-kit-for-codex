"""Disposable-adopter regressions derived from the frozen scaffold installer tests."""

import hashlib
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / ".github/scripts/scaffold-init.sh"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"


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
        prefix = "repos/{owner}/{repo}"
        replies = {}
        def reply(endpoint, query, output, rc=0):
            replies[endpoint + "\n" + query] = [rc, output]
        meta = prefix + "/pulls/1"
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
        if ordinary:
            helper = (self.target / '.github/scripts/check-task-ritual.sh').read_text()
            marker_query = helper.split('markers=$(api ', 1)[1].split("--jq '", 1)[1].split("'", 1)[0]
            resolved_query = helper.split('elif resolved=$(api ', 1)[1].split("--jq '", 1)[1].split("'", 1)[0]
            reply(prefix + '/issues/2/comments', marker_query,
                  'CLAIM\t2026-01-01T00:00:00Z\t2026-01-01T00:00:00Z\n'
                  'PLAN\t2026-01-01T00:01:00Z\t2026-01-01T00:01:00Z\n'
                  'EXEMPT\t2026-01-01T00:01:00Z\t2026-01-01T00:01:00Z')
            reply(meta + '/commits', '.[].commit | ((.committer.date // .author.date) // empty)',
                  '2026-01-01T00:02:00Z')
            reply(prefix + '/issues/2', '[.labels[].name] | join(" ")', 'type:task')
            reply(prefix, '.full_name', 'fixture/adopter')
            reply(prefix + '/issues/comments/3', resolved_query, '2\tplan')
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

    def packaged_json(self, helper, records, *args):
        # Execute the helper's actual --jq expression against raw GitHub JSON.
        # No preprojected IDs/markers can hide a broken query in these fixtures.
        self.assertIsNotNone(shutil.which("jq"), "real jq is required for helper regressions")
        fake = self.base / "json-bin"
        fake.mkdir(exist_ok=True)
        fixture = self.base / "raw-github.json"
        fixture.write_text(json.dumps(records))
        gh = fake / "gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, subprocess, sys
args=sys.argv[1:]
records=json.load(open(os.environ['RAW_GITHUB_FIXTURE']))
if args[:2] == ['issue','list']:
    value=records['list']
    if value is None: sys.exit(90)
    print(value, end=''); sys.exit(0)
if args[0] == 'api':
    key=args[1]
elif args[:2] == ['issue','view']:
    repo=args[args.index('--repo')+1] if '--repo' in args else 'fixture/adopter'
    key=repo+'#'+args[2]+':'+args[args.index('--json')+1]
else: sys.exit(91)
if key not in records or records[key] is None: sys.exit(92)
if '--jq' not in args: sys.exit(93)
sys.exit(subprocess.run(['jq','-r',args[args.index('--jq')+1]],
    input=json.dumps(records[key]),text=True).returncode)
""")
        gh.chmod(0o755)
        return subprocess.run(["bash", str(ROOT / PAYLOAD / helper), *args], cwd=self.target,
            env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"],
                     RAW_GITHUB_FIXTURE=str(fixture), RITUAL_API_RETRY_DELAY="0"),
            capture_output=True, text=True, timeout=15)

    def ordinary_ritual(self, identifier="6af9582d-42d1-425d-82c8-f9ec651225a8", *, defect=None):
        prefix = 'repos/{owner}/{repo}'
        def comment(body, minute):
            stamp = f'2026-01-01T00:{minute:02}:00Z'
            return {'body': body, 'created_at': stamp, 'updated_at': stamp}
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
            prefix + '/pulls/1': {'user': {'login': 'owner', 'type': 'User'}, 'body': body,
                                 'head': {'ref': 'codex/task-2-fix'}},
            prefix + '/issues/2/comments': comments,
            prefix + '/pulls/1/commits': [{'commit': {'committer': {'date': '2026-01-01T00:05:00Z'}}}],
            prefix + '/issues/2': {'labels': [{'name': 'type:task'}]},
            prefix: {'full_name': 'fixture/adopter'},
            prefix + '/issues/comments/3': {'issue_url': 'https://api.github.com/repos/fixture/adopter/issues/2',
                                          'body': '## Plan\nImplement the bounded Task.'},
        }
        if defect == 'wrong-plan-resolution': records[prefix + '/issues/comments/3']['issue_url'] = 'issues/4'
        if defect == 'non-plan-comment': records[prefix + '/issues/comments/3']['body'] = 'Starting in session fixture'
        if defect == 'missing-task-label': records[prefix + '/issues/2']['labels'] = []
        return self.packaged_json('.github/scripts/check-task-ritual.sh', records, '1')

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
            self.assertEqual(source.read_bytes(), (self.target / source.relative_to(payload)).read_bytes())
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
