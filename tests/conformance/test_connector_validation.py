"""Frozen-source fixtures and safety regressions; actual Bash, no live services."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.github/scripts/check-connectors.sh'
SOURCE_BASELINE = os.environ.get('CONNECTOR_REVIEW_BASELINE')


def valid(name):
    # Adapted verbatim fixture semantics from frozen test-connectors.sh.
    return f'''# Connector: {name}

## Metadata

- name: {name}
- access: in-repo files
- reach: repository only
- trust-default: draft
- status: core

## discover

How to find material.

## retrieve

How to fetch it.

## pin

How to pin it.

## verify

How to re-verify it.
'''


class ConnectorValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='connector-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / 'target'
        self.definitions = self.target / '.github/connectors'
        self.definitions.mkdir(parents=True)
        (self.definitions / 'README.md').write_text('# Connectors\n')
        (self.definitions / 'CONNECTOR-TEMPLATE.md').write_text('# Template\n')
        self.binary = self.root / 'bin'
        self.binary.mkdir()
        for tool in ('awk', 'grep', 'sed', 'head', 'tr', 'find', 'wc', 'basename', 'dirname'):
            executable = shutil.which(tool, path='/usr/bin:/bin')
            self.assertIsNotNone(executable, tool)
            (self.binary / tool).symlink_to(executable)
        self.calls = self.root / 'forbidden-calls'
        for tool in ('gh', 'git', 'curl', 'wget', 'codex', 'ssh'):
            path = self.binary / tool
            path.write_text('#!/bin/sh\nprintf forbidden >> "$FIXTURE_CALLS"\nexit 91\n')
            path.chmod(0o755)
        self.env = dict(PATH=str(self.binary), LC_ALL='C', FIXTURE_CALLS=str(self.calls))
        self.script = SCRIPT
        if SOURCE_BASELINE:
            self.script = self.target / '.github/scripts/check-connectors.sh'
            self.script.parent.mkdir()
            shutil.copyfile(SOURCE_BASELINE, self.script)

    def write(self, name='alpha', text=None):
        path = self.definitions / (name + '.md')
        path.write_text(valid(name) if text is None else text)
        return path

    def run_checker(self, *args, target=True):
        command = ['/bin/bash', str(self.script)]
        if not SOURCE_BASELINE and target:
            command += ['--target', str(self.target)]
        command += list(args)
        result = subprocess.run(command, cwd=self.root, env=self.env,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=10)
        self.assertLess(len(result.stdout + result.stderr), 65536)
        self.assertFalse(self.calls.exists(), 'checker attempted a forbidden operation')
        return result

    def expect(self, code, reason=None, **kwargs):
        result = self.run_checker(**kwargs)
        self.assertEqual(code, result.returncode, result.stderr)
        if reason:
            self.assertIn(reason, result.stderr)
        return result

    # The following twelve cases map 1:1 to the frozen source test suite.
    def test_source_01_two_valid_connectors(self):
        self.write(); self.write('beta')
        result = self.expect(0)
        self.assertIn('2 connector definition(s)', result.stdout)

    def test_source_02_missing_reach(self):
        self.write(text=valid('alpha').replace('- reach: repository only\n', ''))
        self.expect(1, 'metadata-missing:reach')

    def test_source_03_invalid_status(self):
        self.write(text=valid('alpha').replace('status: core', 'status: bespoke'))
        self.expect(1, 'status-invalid')

    def test_source_04_missing_pin_heading(self):
        self.write(text=valid('alpha').replace('## pin', '## pinning'))
        self.expect(1, 'operation-missing:pin')

    def test_source_05_missing_metadata(self):
        self.write(text=valid('alpha').replace('## Metadata', '## About'))
        self.expect(1, 'metadata-section-missing')

    def test_source_06_missing_framework(self):
        self.write(); (self.definitions / 'CONNECTOR-TEMPLATE.md').unlink()
        self.expect(1, 'framework-template:missing')

    def test_source_07_empty_definitions(self):
        self.expect(1, 'definitions-missing')

    def test_source_08_bad_among_valid(self):
        self.write(); self.write('beta', valid('beta').replace('- trust-default: draft\n', ''))
        self.expect(1, 'metadata-missing:trust-default')

    def test_source_09_duplicate_status(self):
        self.write(text=valid('alpha').replace('- status: core', '- status: core\n- status: experimental'))
        self.expect(1, 'metadata-duplicate:status')

    def test_source_10_extra_metadata_bullet(self):
        self.write(text=valid('alpha').replace('- status: core', '- status: core\n- flavor: vanilla'))
        self.expect(1, 'metadata-undeclared')

    def test_source_11_field_outside_metadata(self):
        self.write(text=valid('alpha').replace('- access: in-repo files\n', '') + '\n- access: in-repo files\n')
        self.expect(1, 'metadata-missing:access')

    def test_source_12_name_filename_mismatch(self):
        self.write('foo', valid('foo').replace('- name: foo', '- name: bar'))
        self.expect(1, 'name-filename-mismatch')

    def test_empty_name_is_rejected_before_filename_comparison(self):
        self.write(text=valid('alpha').replace('- name: alpha', '- name:   '))
        result = self.run_checker()
        self.assertEqual(1, result.returncode, 'frozen source previously accepted an empty name')
        if not SOURCE_BASELINE:
            self.assertIn('name-empty', result.stderr)

    def test_shipped_builtin_speckit_smoke(self):
        shutil.copytree(ROOT / '.github/distribution/payload/.github/connectors',
                        self.definitions, dirs_exist_ok=True)
        self.expect(0)

    def test_requires_explicit_target_and_rejects_usage_errors(self):
        self.write()
        for arguments in ((), ('--target',), ('--target', ''), ('--target', str(self.target), '--fix'),
                          ('--target', str(self.target), '--target', str(self.target))):
            with self.subTest(arguments=arguments):
                result = self.run_checker(*arguments, target=False)
                self.assertEqual(2, result.returncode)
        self.assertEqual(0, self.run_checker('--help', target=False).returncode)

    def test_missing_target_and_connector_directory_are_not_success(self):
        result = self.run_checker('--target', str(self.root / 'absent'), target=False)
        self.assertEqual(3, result.returncode)
        shutil.rmtree(self.definitions)
        self.expect(3, 'connector-directory:uncheckable')

    def test_symlink_target_ancestor_directory_and_leaf_are_refused(self):
        self.write()
        alias = self.root / 'alias'; alias.symlink_to(self.target, target_is_directory=True)
        self.assertEqual(3, self.run_checker('--target', str(alias), target=False).returncode)
        self.assertEqual(3, self.run_checker('--target', str(alias / '.github/..'), target=False).returncode)
        for name in ('alpha.md', 'README.md', 'CONNECTOR-TEMPLATE.md'):
            path = self.definitions / name
            data = path.read_bytes(); path.unlink(); path.symlink_to(self.root / 'absent')
            self.expect(3, 'unsafe-file')
            path.unlink(); path.write_bytes(data)
        saved = self.root / 'saved'; self.definitions.rename(saved)
        self.definitions.symlink_to(saved, target_is_directory=True)
        self.expect(3, 'connector-directory:uncheckable')

    def test_fifo_and_directory_definition_are_not_skipped(self):
        self.write()
        path = self.definitions / 'special.md'
        os.mkfifo(path); self.expect(3, 'unsafe-file'); path.unlink()
        path.mkdir(); self.expect(3, 'unsafe-file')

    def test_unreadable_file_or_directory_is_not_missing_or_success(self):
        path = self.write()
        if os.geteuid() == 0:
            self.skipTest('permission-bit refusal requires an unprivileged test user')
        path.chmod(0); self.addCleanup(path.chmod, 0o644)
        self.expect(3, 'unsafe-file'); path.chmod(0o644)
        self.definitions.chmod(0); self.addCleanup(self.definitions.chmod, 0o755)
        self.expect(3, 'connector-directory:uncheckable')

    def test_failed_enumeration_and_read_tools_are_uncheckable(self):
        self.write()
        for tool in ('find', 'head', 'awk', 'grep', 'sed', 'tr'):
            with self.subTest(tool=tool):
                path = self.binary / tool
                original = path.readlink(); path.unlink()
                path.write_text('#!/bin/sh\nprintf private-value >&2\nexit 7\n'); path.chmod(0o755)
                result = self.expect(3)
                self.assertNotIn('private-value', result.stdout + result.stderr)
                path.unlink(); path.symlink_to(original)

    def test_private_values_paths_and_filenames_never_enter_diagnostics(self):
        self.write('private-name', valid('private-name').replace('status: core', 'status: private-secret')
                   .replace('- reach: repository only', '- reach: private-value\n- unknown: private-body'))
        result = self.expect(1)
        for private in ('private-name', 'private-secret', 'private-value', 'private-body', str(self.root)):
            self.assertNotIn(private, result.stdout + result.stderr)

    def test_input_and_definition_limits_fail_closed(self):
        path = self.write(text=valid('alpha') + 'x' * 1048576)
        self.expect(3, 'input-limit'); path.unlink()
        for index in range(129): self.write('c' + str(index))
        self.expect(3, 'definition-limit')

    def test_zero_writes_preserves_content_modes_and_git_metadata(self):
        self.write()
        (self.target / '.git').mkdir()
        (self.target / '.git/config').write_text('synthetic private configuration\n')
        (self.target / '.git/index').write_bytes(b'synthetic-index')
        (self.target / 'user.txt').write_text('adopter-owned content\n')
        def snapshot():
            return {str(p.relative_to(self.target)): (stat.S_IMODE(p.lstat().st_mode),
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
                    p.stat().st_mtime_ns) for p in self.target.rglob('*')}
        before = snapshot(); self.expect(0); self.assertEqual(before, snapshot())
        self.write(text=valid('alpha').replace('status: core', 'status: unknown'))
        before = snapshot(); self.expect(1); self.assertEqual(before, snapshot())

    def test_source_whitespace_and_all_status_values_remain_supported(self):
        for status in ('core', 'community', 'experimental'):
            self.write(text=valid('alpha').replace('status: core', 'status: ' + status + '  ')
                       .replace('## Metadata', '## Metadata\t').replace('## pin', '## pin  '))
            self.expect(0)

    def test_nul_input_cannot_be_normalized_into_valid_metadata(self):
        self.write(text=valid('alpha').replace('- name: alpha', '- name: al\x00pha'))
        self.expect(3, 'nontext-input')


class ConnectorCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specification = importlib.util.spec_from_file_location('connector_installer_checker', ROOT / '.github/scripts/check-installer.py')
        cls.checker = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.checker)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='connector-provenance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        shutil.copytree(ROOT / '.github/distribution', self.root / '.github/distribution')
        for path in self.checker.FEEDBACK_PATHS + self.checker.CONNECTOR_PATHS:
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, destination); destination.chmod(0o644)
        self.parity = self.root / self.checker.PARITY

    def cli(self):
        return subprocess.run([sys.executable, '-I', str(ROOT / '.github/scripts/check-installer.py'),
                               '--root', str(self.root)], capture_output=True, text=True, timeout=10)

    def test_complete_cli_proves_both_components_without_payload_growth(self):
        self.assertEqual([], self.checker.validate(self.root))
        self.assertEqual([], self.checker.validate_connector_companion(self.root))
        result = self.cli(); self.assertEqual(0, result.returncode, result.stdout)
        parity = json.loads(self.parity.read_bytes())
        self.assertEqual(47, len(parity['files']))
        self.assertNotIn('.github/scripts/check-connectors.sh', [r['destination'] for r in parity['files']])

    def test_production_cli_does_not_exempt_missing_connector_companion(self):
        self.assertEqual(0, self.cli().returncode)
        (self.root / self.checker.CONNECTOR_PATHS[0]).unlink()
        self.assertEqual([], self.checker.validate(self.root), 'legacy component remains distinct')
        result = self.cli()
        self.assertEqual(1, result.returncode)
        self.assertIn('connector companion is missing', result.stdout)

    def test_production_cli_still_requires_payload_and_feedback_components(self):
        self.assertEqual(0, self.cli().returncode)
        (self.root / self.checker.FEEDBACK_PATHS[0]).unlink()
        self.assertEqual([], self.checker.validate_connector_companion(self.root))
        self.assertEqual(1, self.cli().returncode)

    def test_companion_contract_and_inventory_drift_refuse(self):
        original = self.parity.read_bytes()
        for field, value in (('source_files', {}), ('fields', ['name']), ('operations', ['verify']),
                             ('statuses', ['trusted']), ('integration', 'auto-activate'),
                             ('adaptations', []), ('evidence', 'live-pass'), ('target_files', []),
                             ('unreviewed', True)):
            with self.subTest(field=field):
                data = json.loads(original); data['connector_companion'][field] = value
                self.parity.write_text(json.dumps(data))
                self.assertTrue(self.checker.validate_connector_companion(self.root))
        data = json.loads(original); del data['connector_companion']
        self.parity.write_text(json.dumps(data))
        self.assertEqual(1, self.cli().returncode)

    def test_companion_bytes_mode_link_and_record_shape_drift_refuse(self):
        path = self.root / self.checker.CONNECTOR_PATHS[0]
        original = path.read_bytes()
        path.write_bytes(original + b'\n# drift\n')
        self.assertTrue(self.checker.validate_connector_companion(self.root))
        path.write_bytes(original); path.chmod(0o755)
        self.assertTrue(self.checker.validate_connector_companion(self.root))
        path.unlink(); path.symlink_to(SCRIPT)
        self.assertTrue(self.checker.validate_connector_companion(self.root))
        data = json.loads(self.parity.read_bytes()); data['connector_companion']['target_files'][0] = 'malformed'
        self.parity.write_text(json.dumps(data))
        self.assertTrue(self.checker.validate_connector_companion(self.root))
