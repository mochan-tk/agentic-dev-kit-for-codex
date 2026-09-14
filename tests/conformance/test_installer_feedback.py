"""Source-derived feedback regressions: real Bash, disposable fixtures, fake gh."""
import json
import importlib.util
import os
from pathlib import Path
import pty
import shutil
import select
import subprocess
import tempfile
import termios
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/report-installer-failure.sh"
LIBRARY = ROOT / ".github/scripts/feedback-lib.sh"
REPOSITORY = "https://github.com/mochan-tk/agentic-dev-kit-for-codex"
URL = REPOSITORY + "/issues/42"


class InstallerFeedbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="installer-feedback-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.adopter = self.root / "adopter"
        self.adopter.mkdir()
        (self.adopter / "SCAFFOLD-CHANGELOG.md").write_text("private marker must not be read\n")
        (self.adopter / "private.txt").write_text("private content must remain local\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.jsonl"
        gh = self.bin / "gh"
        gh.write_text("""#!/usr/bin/python3
import json, os, sys
with open(os.environ['FIXTURE_CALLS'], 'a') as output:
    output.write(json.dumps({'argv':sys.argv[1:], 'host':os.environ.get('GH_HOST'),
                            'repo':os.environ.get('GH_REPO')})+'\\n')
if sys.argv[1:] == ['--version']:
    value = os.environ.get('FIXTURE_GH_VERSION', 'gh version 2.96.0 (2026-09-01)')
    if os.environ.get('FIXTURE_VERSION_NUL'): value = value.replace('2.96', '2.'+chr(0)+'96')
    print(value)
    sys.exit(int(os.environ.get('FIXTURE_VERSION_RC', '0')))
if sys.argv[1:3] != ['issue','create']: sys.exit(92)
value = os.environ.get('FIXTURE_CREATE_OUTPUT', 'https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/42')
if os.environ.get('FIXTURE_CREATE_NUL'): value += chr(0) * int(os.environ['FIXTURE_CREATE_NUL'])
print(value)
print(os.environ.get('FIXTURE_CREATE_ERROR', ''), file=sys.stderr)
sys.exit(int(os.environ.get('FIXTURE_CREATE_RC', '0')))
""")
        gh.chmod(0o755)
        for name, text in (("uname", '#!/bin/sh\nif [ "$1" = -s ]; then printf "%s\\n" "${FIXTURE_OS:-Linux}"; else printf "%s\\n" "${FIXTURE_ARCH:-x86_64}"; fi\n'),
                           ("jq", '#!/bin/sh\nprintf "%s\\n" "${FIXTURE_JQ_VERSION:-jq-1.7.1}"\n')):
            path = self.bin / name
            path.write_text(text); path.chmod(0o755)
        for name in ('dirname', 'head', 'od', 'tr'):
            (self.bin / name).symlink_to(shutil.which(name, path='/usr/bin:/bin'))
        # Never fall through to a runner's real gh/jq, including absence tests.
        self.env = dict(os.environ, PATH=str(self.bin), LC_ALL="C",
                        CI="", GITHUB_ACTIONS="", FIXTURE_CALLS=str(self.calls))

    def entries(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def creates(self):
        return [item for item in self.entries() if item['argv'][:2] == ['issue', 'create']]

    def run_report(self, *args, env=None, input=""):
        return subprocess.run(['/bin/bash', str(SCRIPT), *args], cwd=self.adopter,
            env=dict(self.env, **(env or {})), input=input, capture_output=True, text=True, timeout=10)

    def terminal(self, answer="y", *, stdin_tty=True, stderr_tty=True, env=None):
        master, slave = pty.openpty()
        settings = termios.tcgetattr(slave)
        settings[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        process = subprocess.Popen(['/bin/bash', str(SCRIPT), '--send', '--line', '42', '--exit-code', '7'],
            cwd=self.adopter, env=dict(self.env, **(env or {})),
            stdin=slave if stdin_tty else subprocess.PIPE,
            stderr=slave if stderr_tty else subprocess.PIPE, stdout=subprocess.PIPE)
        os.close(slave)
        data = b''
        sent = False
        deadline = time.monotonic() + 10
        try:
            if not stdin_tty:
                process.stdin.write(b'y\n'); process.stdin.close()
            while process.poll() is None and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], .05)
                if ready:
                    try: chunk = os.read(master, 4096)
                    except OSError: chunk = b''
                    data += chunk
                self.assertLessEqual(len(data), 16384, 'bounded fixture capture')
                if b'Send this public report? [y/N]' in data and not sent:
                    os.write(master, b'\x04' if answer is None else answer.encode() + b'\n')
                    sent = True
            if process.poll() is None:
                process.terminate(); process.wait(timeout=3)
                self.fail('bounded PTY fixture timed out')
            while select.select([master], [], [], 0)[0]:
                try: chunk = os.read(master, 4096)
                except OSError: break
                if not chunk: break
                data += chunk
            output = process.stdout.read().decode()
            if not stderr_tty: data += process.stderr.read()
            return process.returncode, output, data.decode().replace('\r\n', '\n')
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=3)
            if process.stdin: process.stdin.close()
            process.stdout.close()
            if process.stderr: process.stderr.close()
            os.close(master)

    def test_draft_has_closed_fields_without_gh_or_adopter_mutation(self):
        (self.bin / 'gh').unlink()
        # The closed fixture PATH excludes any runner-installed gh.
        before = {p.name: p.read_bytes() for p in self.adopter.iterdir()}
        result = self.run_report('--draft', '--line', '42', '--exit-code', '7')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('result=drafted', result.stderr)
        fields = [line.split(' | ')[0][2:] for line in result.stdout.splitlines()
                  if line.startswith('| ') and not line.startswith('| Field')]
        self.assertEqual(['Script', 'Failing line', 'Exit code', 'OS / arch',
                          'bash version', 'gh version', 'jq version', 'Scaffold version'], fields)
        self.assertIn('| Script | scaffold-init |', result.stdout)
        self.assertIn('| Scaffold version | unknown |', result.stdout)
        self.assertIn('| gh version | unknown |', result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.adopter.iterdir()})
        self.assertEqual([], self.entries())

    def test_nonterminal_send_and_environment_prearming_are_blocked(self):
        result = self.run_report('--send', env={'FEEDBACK_ASSUME_TTY':'1', 'FEEDBACK_ERR_SEEN':'1',
            'FEEDBACK_YES':'y', 'GH_REPO':'attacker/elsewhere'}, input='y\n')
        self.assertEqual(4, result.returncode, result.stderr)
        self.assertIn('result=send-unavailable', result.stderr)
        self.assertEqual([], self.creates())


    def test_terminal_y_creates_exact_preview_once_at_fixed_destination(self):
        rc, output, preview = self.terminal(env={'GH_HOST':'private.invalid', 'GH_REPO':'attacker/elsewhere'})
        self.assertEqual(0, rc, preview)
        self.assertEqual(URL + '\n', output)
        self.assertIn('result=confirmed', preview)
        self.assertIn('PUBLIC', preview)
        self.assertIn('existing GitHub account', preview)
        self.assertEqual(1, len(self.creates()))
        request = self.creates()[0]
        args = request['argv']
        self.assertEqual(['issue','create','--repo',REPOSITORY,'--title'], args[:5])
        self.assertIn('Title: ' + args[5] + '\n', preview)
        self.assertEqual('--body', args[6])
        self.assertIn(args[7] + '\n', preview)
        self.assertLess(preview.index(args[7]), preview.index('Send this public report?'))
        self.assertEqual('github.com', request['host'])
        self.assertEqual('mochan-tk/agentic-dev-kit-for-codex', request['repo'])

    def test_failed_creation_remains_unconfirmed_without_raw_response(self):
        rc, output, preview = self.terminal(env={'FIXTURE_CREATE_RC':'1',
            'FIXTURE_CREATE_OUTPUT':'/private/path/token', 'FIXTURE_CREATE_ERROR':'secret-credential'})
        self.assertEqual(5, rc, preview)
        self.assertEqual('', output)
        self.assertIn('result=submission-unconfirmed', preview)
        self.assertNotIn('nothing was filed', preview)
        self.assertNotIn('/private/path/token', preview)
        self.assertNotIn('secret-credential', preview)
        self.assertEqual(1, len(self.creates()))

    def test_invalid_arguments_never_reach_submission(self):
        for args in (('--yes',), ('--repo','attacker/elsewhere'), ('--script','setup-ruleset'),
                     ('--body','private'), ('--line','1\nsecret'), ('--exit-code','256'),
                     ('--line','1000000'), ('--draft','--send'), ('--line',), ('--line','0')):
            with self.subTest(args=args):
                result = self.run_report(*args)
                self.assertEqual(2, result.returncode)
                self.assertNotIn('secret', result.stdout + result.stderr)
        self.assertEqual([], self.creates())

    def test_each_terminal_descriptor_is_mandatory(self):
        for stdin_tty, stderr_tty in ((False, True), (True, False), (False, False)):
            with self.subTest(stdin=stdin_tty, stderr=stderr_tty):
                rc, output, preview = self.terminal(stdin_tty=stdin_tty, stderr_tty=stderr_tty)
                self.assertEqual(4, rc, preview)
                self.assertEqual('', output)
                self.assertNotIn('Send this public report?', preview)
        self.assertEqual([], self.creates())

    def test_nonempty_ci_indicators_block_real_terminal(self):
        for env in ({'CI':'false'}, {'CI':'0'}, {'GITHUB_ACTIONS':'false'}, {'GITHUB_ACTIONS':'1'}):
            with self.subTest(env=env):
                rc, _, preview = self.terminal(env=env)
                self.assertEqual(4, rc)
                self.assertNotIn('Send this public report?', preview)
        self.assertEqual([], self.creates())

    def test_only_literal_y_or_uppercase_y_is_consent(self):
        for answer in ('', None, 'n', 'N', 'yes', ' y', 'y ', 'yy', 'Yy', '1'):
            with self.subTest(answer=answer):
                rc, output, preview = self.terminal(answer)
                self.assertEqual(3, rc, preview)
                self.assertEqual('', output)
                self.assertIn('result=declined', preview)
        self.assertEqual([], self.creates())
        rc, output, _ = self.terminal('Y')
        self.assertEqual((0, URL + '\n'), (rc, output))
        self.assertEqual(1, len(self.creates()))

    def test_nul_consent_bytes_never_normalize_into_literal_y(self):
        for answer in ('y\x00', 'Y\x00', '\x00y', 'y\x00x', 'y\x01'):
            with self.subTest(answer=repr(answer)):
                before = len(self.creates())
                rc, output, preview = self.terminal(answer)
                self.assertEqual(3, rc, preview)
                self.assertEqual('', output)
                self.assertEqual(before, len(self.creates()))

    def test_nul_create_response_and_raw_byte_overflow_remain_unconfirmed(self):
        for count in ('1', '300'):
            with self.subTest(nul_count=count):
                before = len(self.creates())
                rc, output, preview = self.terminal(env={'FIXTURE_CREATE_NUL':count})
                self.assertEqual(5, rc, preview)
                self.assertEqual('', output)
                self.assertIn('result=submission-unconfirmed', preview)
                self.assertEqual(before + 1, len(self.creates()))

    def test_nul_version_output_is_unknown_not_a_normalized_version(self):
        result = self.run_report(env={'FIXTURE_VERSION_NUL':'1'})
        self.assertEqual(0, result.returncode)
        self.assertIn('| gh version | unknown |', result.stdout)
        self.assertNotIn('\x00', result.stdout + result.stderr)

    def test_unknown_malformed_lost_and_overflow_responses_are_unconfirmed(self):
        for value in ('', 'https://github.com/elsewhere/repository/issues/42',
                      URL + '\nprivate-extra', URL + '?secret=private', URL.replace('/42', '/0'),
                      '/private/path', 'x' * 300, URL + '\n' * 300):
            with self.subTest(value=value[:30]):
                before = len(self.creates())
                rc, output, preview = self.terminal(env={'FIXTURE_CREATE_OUTPUT':value})
                self.assertEqual(5, rc, preview)
                self.assertEqual('', output)
                self.assertIn('result=submission-unconfirmed', preview)
                self.assertNotIn('private-extra', preview)
                self.assertNotIn('/private/path', preview)
                self.assertEqual(before + 1, len(self.creates()))

    def test_exact_closed_field_values_and_official_version_output(self):
        result = self.run_report('--line', '999999', '--exit-code', '255',
            env={'FIXTURE_GH_VERSION':'gh version 2.96.0 (2026-09-01)\nhttps://github.com/cli/cli/releases/tag/v2.96.0'})
        self.assertEqual(0, result.returncode)
        for field in ('| Failing line | 999999 |', '| Exit code | 255 |',
                      '| OS / arch | Linux / x86_64 |', '| gh version | 2.96.0 |',
                      '| jq version | jq-1.7.1 |', '| Scaffold version | unknown |'):
            self.assertIn(field, result.stdout)
        self.assertNotIn('https://github.com/cli/', result.stdout)
        self.assertEqual([], self.creates())

    def test_missing_metadata_defaults_to_unknown_not_a_historical_claim(self):
        result = self.run_report()
        self.assertEqual(0, result.returncode)
        self.assertIn('| Failing line | unknown |', result.stdout)
        self.assertIn('| Exit code | unknown |', result.stdout)
        self.assertIn('not proof of a historical run', result.stdout)
        self.assertEqual([], self.creates())

    def test_duplicate_numeric_and_noncanonical_inputs_reject(self):
        for args in (('--line','1','--line','2'), ('--exit-code','1','--exit-code','2'),
                     ('--send','--send'), ('--line','01'), ('--line','-1'),
                     ('--exit-code','0'), ('--exit-code','01'), ('--exit-code','-1')):
            with self.subTest(args=args):
                self.assertEqual(2, self.run_report(*args).returncode)
        self.assertEqual([], self.entries())

    def test_version_and_system_observations_reject_unsafe_values(self):
        for key, row in (('FIXTURE_GH_VERSION','gh version'), ('FIXTURE_JQ_VERSION','jq version'),
                         ('FIXTURE_OS','OS / arch'), ('FIXTURE_ARCH','OS / arch')):
            for value in ('ghp_privatecredential', '/private/secret-path', 'ok\nprivate-log',
                          'ok\rprivate-log', 'x' * 300):
                with self.subTest(key=key, value=value[:20]):
                    result = self.run_report('--draft', env={key:value})
                    self.assertEqual(0, result.returncode)
                    field = next(line for line in result.stdout.splitlines() if line.startswith('| ' + row + ' |'))
                    self.assertIn('unknown', field)
                    for forbidden in ('privatecredential','secret-path','private-log', 'x' * 40):
                        self.assertNotIn(forbidden, result.stdout + result.stderr)
        self.assertEqual([], self.creates())

    def test_valid_first_line_does_not_hide_unknown_multiline_version_data(self):
        for raw in ('gh version 2.96.0\nsecret', 'gh version 2.96.0\nhttps://private.example/x',
                    'gh version 2.96.0\nhttps://github.com/cli/cli/releases/tag/v2.96.0\nsecret'):
            result = self.run_report(env={'FIXTURE_GH_VERSION':raw})
            self.assertIn('| gh version | unknown |', result.stdout)
            self.assertNotIn('secret', result.stdout + result.stderr)

    def test_missing_jq_and_failed_version_observation_are_safe(self):
        (self.bin / 'jq').unlink()
        # A minimal PATH makes jq genuinely unavailable even on Linux images.
        for name in ('dirname','head','uname'):
            if not (self.bin / name).exists():
                (self.bin / name).symlink_to(shutil.which(name, path='/usr/bin:/bin'))
        result = self.run_report(env={'PATH':str(self.bin), 'FIXTURE_VERSION_RC':'1'})
        self.assertEqual(0, result.returncode)
        self.assertIn('| jq version | unknown |', result.stdout)
        self.assertIn('| gh version | unknown |', result.stdout)
        self.assertEqual([], self.creates())

    def test_missing_gh_prevents_terminal_send_before_prompt(self):
        (self.bin / 'gh').unlink()
        rc, output, preview = self.terminal()
        self.assertEqual(4, rc)
        self.assertEqual('', output)
        self.assertNotIn('Send this public report?', preview)
        self.assertEqual([], self.entries())

    def test_library_load_has_no_traps_or_automatic_operations(self):
        script = 'trap "printf kept" EXIT; before=$(trap -p); source "$1"; after=$(trap -p); [ "$before" = "$after" ]'
        result = subprocess.run(['/bin/bash','-c',script,'fixture',str(LIBRARY)],
            cwd=self.adopter, env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual((0, 'kept', ''), (result.returncode, result.stdout, result.stderr))
        self.assertEqual([], self.entries())

    def test_prearmed_marker_and_environment_never_supply_fields_or_destination(self):
        result = self.run_report(env={'FEEDBACK_SCRIPT':'private-script', 'FEEDBACK_ERR_LINE':'123',
            'FEEDBACK_ERR_SEEN':'1','FB_TITLE':'private-title','FB_BODY':'private-body',
            'FEEDBACK_REPO':'attacker/elsewhere','FEEDBACK_SHA':'a' * 40})
        self.assertIn('| Script | scaffold-init |', result.stdout)
        self.assertIn('| Failing line | unknown |', result.stdout)
        self.assertIn('| Scaffold version | unknown |', result.stdout)
        for forbidden in ('private-script','private-title','private-body','attacker/elsewhere', 'a' * 40):
            self.assertNotIn(forbidden, result.stdout + result.stderr)
        self.assertEqual([], self.creates())


class FeedbackCompanionProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specification = importlib.util.spec_from_file_location('feedback_installer_checker', ROOT / '.github/scripts/check-installer.py')
        cls.checker = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.checker)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='feedback-provenance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / '.github/distribution', self.root / '.github/distribution')
        for path in ('.github/scripts/feedback-lib.sh', '.github/scripts/report-installer-failure.sh',
                     'tests/conformance/test_installer_feedback.py'):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
            target.chmod(0o644)
        self.parity = self.root / '.github/distribution/source-parity.v1.json'

    def mutate(self, operation):
        data = json.loads(self.parity.read_bytes())
        operation(data['feedback_companion'])
        self.parity.write_text(json.dumps(data))

    def test_complete_companion_passes_without_payload_expansion(self):
        self.assertEqual([], self.checker.validate(self.root))
        data = json.loads(self.parity.read_bytes())
        self.assertEqual(47, len(data['files']))
        self.assertEqual(3, len(data['feedback_companion']['target_files']))
        self.assertNotIn('.github/scripts/feedback-lib.sh', [x['destination'] for x in data['files']])

    def test_missing_or_extra_companion_fields_reject(self):
        for field in ('source_files', 'fields', 'recipient', 'adaptations', 'evidence'):
            with self.subTest(field=field):
                original = self.parity.read_bytes()
                self.mutate(lambda data: data.pop(field))
                self.assertTrue(self.checker.validate(self.root))
                self.parity.write_bytes(original)
        self.mutate(lambda data: data.update(extra='unreviewed'))
        self.assertTrue(self.checker.validate(self.root))

    def test_frozen_source_drift_rejects(self):
        self.mutate(lambda data: data['source_files'].update({'.github/scripts/feedback-lib.sh':'0' * 40}))
        self.assertTrue(self.checker.validate(self.root))

    def test_target_digest_or_source_bytes_drift_reject(self):
        script = self.root / '.github/scripts/feedback-lib.sh'
        script.write_bytes(script.read_bytes() + b'\n# unreviewed\n')
        self.assertTrue(self.checker.validate(self.root))

    def test_target_missing_extra_symlink_and_executable_mode_reject(self):
        script = self.root / '.github/scripts/feedback-lib.sh'
        original = script.read_bytes()
        script.unlink()
        self.assertTrue(self.checker.validate(self.root))
        script.symlink_to(ROOT / '.github/scripts/feedback-lib.sh')
        self.assertTrue(self.checker.validate(self.root))
        script.unlink(); script.write_bytes(original); script.chmod(0o755)
        self.assertTrue(self.checker.validate(self.root))
        script.chmod(0o644)
        self.mutate(lambda data: data['target_files'].append(dict(data['target_files'][0])))
        self.assertTrue(self.checker.validate(self.root))

    def test_recipient_fields_integration_and_evidence_cannot_drift(self):
        for field, value in (('recipient','https://github.com/attacker/elsewhere'),
                             ('fields',['Script', 'raw log']), ('integration','automatic-traps'),
                             ('evidence','live-public-send-pass')):
            with self.subTest(field=field):
                original = self.parity.read_bytes()
                self.mutate(lambda data: data.update({field:value}))
                self.assertTrue(self.checker.validate(self.root))
                self.parity.write_bytes(original)

    def test_complete_fixture_retains_frozen_source_rejection(self):
        self.assertEqual([], self.checker.validate(self.root))
        data = json.loads(self.parity.read_bytes())
        data['source_commit'] = '0' * 40
        self.parity.write_text(json.dumps(data))
        self.assertIn('installer frozen source provenance drifted', self.checker.validate(self.root))

    def test_complete_fixture_retains_payload_preservation_class_rejection(self):
        self.assertEqual([], self.checker.validate(self.root))
        inventory = self.root / '.github/distribution/payload.v1.tsv'
        inventory.write_text(inventory.read_text().replace('\tengine\t', '\ttuned\t', 1))
        errors = self.checker.validate(self.root)
        self.assertTrue(any(error.startswith('installer inventory class/digest is invalid:') for error in errors), errors)
        self.assertFalse(any('feedback companion' in error for error in errors), errors)

    def test_complete_fixture_retains_malformed_payload_parity_rejection(self):
        self.assertEqual([], self.checker.validate(self.root))
        data = json.loads(self.parity.read_bytes())
        data['files'][0] = 'not-a-record'
        self.parity.write_text(json.dumps(data))
        errors = self.checker.validate(self.root)
        self.assertIn('installer source parity omits, reorders or adds files', errors)
        self.assertFalse(any('feedback companion' in error for error in errors), errors)
