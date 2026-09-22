"""Execute the published feedback route with real Bash/TTY and synthetic HTTP/gh."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/distribution/feedback.md"
REPOSITORY = "https://github.com/mochan-tk/agentic-dev-kit-for-codex"
FORM = REPOSITORY + "/issues/new?template=feedback.yml"
GUIDANCE = "Optional public feedback (review privacy before sharing):"
REVISION = "5ce4585fd9d52842423942fc64713fcd8748b47c"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/conformance" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class FeedbackDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.reporter = module("test_installer_feedback")
        self.fixture = self.reporter.InstallerFeedbackTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.work = self.fixture.root
        self.bin = self.fixture.bin
        self.tmp = self.work / "private scratch"
        self.tmp.mkdir()
        self.http = self.work / "http.jsonl"
        self.launches = self.work / "launches.jsonl"
        self.http.write_text("")
        self.launches.write_text("")
        self.env = dict(self.fixture.env, TMPDIR=str(self.tmp), DELIVERY_ROOT=str(ROOT),
                        DELIVERY_HTTP=str(self.http), DELIVERY_LAUNCHES=str(self.launches),
                        DELIVERY_FAULT="", DELIVERY_FILE="feedback-lib.sh")
        for name in ("mktemp", "rm", "rmdir", "shasum", "sha256sum"):
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.executable("curl", r'''
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
fixed=["--disable","--fail","--silent","--show-error","--location","--proto","=https","--proto-redir","=https","--max-time","60","--output"]
if a[:len(fixed)]!=fixed or len(a)!=len(fixed)+2: sys.exit(90)
out=Path(a[-2]); name=out.name
prefix="https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/5ce4585fd9d52842423942fc64713fcd8748b47c/.github/scripts/"
if name not in ("report-installer-failure.sh","feedback-lib.sh") or a[-1]!=prefix+name: sys.exit(91)
with open(os.environ["DELIVERY_HTTP"],"a") as f: f.write(json.dumps(a)+"\n")
if out.parent.stat().st_mode & 0o777 != 0o700: sys.exit(92)
fault=os.environ["DELIVERY_FAULT"] if name==os.environ["DELIVERY_FILE"] else ""
source=Path(os.environ["DELIVERY_ROOT"])/".github/scripts"/name
if fault=="missing": sys.exit(0)
if fault=="symlink": out.symlink_to(source); sys.exit(0)
if fault=="directory": out.mkdir(); sys.exit(0)
if fault in ("failed","partial"):
 out.write_text("printf unverified-code-executed\\n")
 sys.exit(22 if fault=="failed" else 0)
out.write_bytes(source.read_bytes())
if fault=="corrupt":
 with out.open("ab") as f: f.write(b"\n# tampered\n")
if fault=="extra": (out.parent/"unexpected").write_text("retain\n")
if fault=="valid-but-failed": sys.exit(22)
''')
        self.executable("bash", "import json,os,sys\n"
            "with open(os.environ['DELIVERY_LAUNCHES'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "os.execv('/bin/bash',['/bin/bash',*sys.argv[1:]])\n")

    def executable(self, name, source):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + source)
        path.chmod(0o755)

    def block(self, args="--draft"):
        matches = re.findall(r"<!-- BEGIN feedback-delivery -->\n```bash\n(.*?)\n```\n<!-- END feedback-delivery -->", GUIDE.read_text(), re.S)
        self.assertEqual(1, len(matches))
        block = matches[0]
        self.assertEqual(1, block.count('bash "$scratch/report-installer-failure.sh" --draft'))
        return block.replace('bash "$scratch/report-installer-failure.sh" --draft',
                             'bash "$scratch/report-installer-failure.sh" ' + args)

    def run_block(self, args="--draft", conditional=False, **env):
        block = self.block(args)
        if conditional:
            block = "if " + block + "; then exit 0; else exit $?; fi"
        return subprocess.run(["/bin/bash", "-c", block], cwd=self.fixture.adopter,
                              env=dict(self.env, **env), capture_output=True, text=True, timeout=15)

    def terminal(self, answer="y", **options):
        script = self.work / "published-block.sh"
        script.write_text(self.block("--send --line 42 --exit-code 7") + "\n")
        with patch.object(self.reporter, "SCRIPT", script):
            return self.fixture.terminal(answer, env=dict(self.env, **options.pop("env", {})), **options)

    def test_manual_form_has_public_warning_required_fields_and_no_automatic_labels(self):
        form = (ROOT / ".github/ISSUE_TEMPLATE/feedback.yml").read_text()
        for text in ("[adopter-feedback]", REPOSITORY, "PUBLIC", "credentials", "local paths",
                     "recovery records", "private repository", "id: problem", "id: expectation", "id: privacy"):
            self.assertIn(text, form)
        self.assertGreaterEqual(form.count("required: true"), 3)
        self.assertNotRegex(form, r"(?m)^(labels|assignees):")
        self.assertNotIn("SCAFFOLD-CHANGELOG", form)

    def test_default_downloads_both_pinned_files_drafts_and_preserves_target_index(self):
        subprocess.run([shutil.which("git"), "init", "-q", str(self.fixture.adopter)], check=True)
        before = {str(p.relative_to(self.fixture.adopter)): p.read_bytes()
                  for p in self.fixture.adopter.rglob("*") if p.is_file()}
        result = self.run_block()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("result=drafted", result.stderr)
        self.assertEqual(8, sum(line.startswith("| ") and not line.startswith("| Field") for line in result.stdout.splitlines()))
        self.assertEqual([], self.fixture.creates())
        self.assertEqual(2, len(self.http.read_text().splitlines()))
        self.assertEqual(1, len(self.launches.read_text().splitlines()))
        self.assertEqual([], list(self.tmp.iterdir()))
        self.assertEqual(before, {str(p.relative_to(self.fixture.adopter)): p.read_bytes()
                                 for p in self.fixture.adopter.rglob("*") if p.is_file()})

    def test_every_file_refuses_transport_partial_missing_unsafe_and_tamper_even_in_condition(self):
        for name in ("report-installer-failure.sh", "feedback-lib.sh"):
            for fault in ("failed", "partial", "missing", "symlink", "directory", "corrupt", "valid-but-failed"):
                for conditional in (False, True):
                    with self.subTest(name=name, fault=fault, conditional=conditional):
                        result = self.run_block(conditional=conditional, DELIVERY_FILE=name, DELIVERY_FAULT=fault)
                        self.assertNotEqual(0, result.returncode, result.stderr)
                        self.assertEqual("", self.launches.read_text())
                        self.assertEqual([], self.fixture.creates())
                        if fault != "directory": self.assertEqual([], list(self.tmp.iterdir()))
                        else:
                            # The block must not recursively remove unexpected directories.
                            for scratch in self.tmp.iterdir():
                                (scratch / name).rmdir()
                                scratch.rmdir()

    def test_hash_tool_failure_never_executes_even_in_condition(self):
        for name in ("sha256sum", "shasum"):
            path = self.bin / name
            if path.is_symlink(): path.unlink()
            self.executable(name, "import sys\nsys.exit(31)\n")
        result = self.run_block(conditional=True)
        self.assertEqual(31, result.returncode, result.stderr)
        self.assertEqual("", self.launches.read_text())
        self.assertEqual([], list(self.tmp.iterdir()))

    def test_shasum_fallback_and_draft_without_optional_tools(self):
        path = self.bin / "sha256sum"
        if path.is_symlink(): path.unlink()
        for name in ("gh", "jq"):
            (self.bin / name).unlink()
        result = self.run_block()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("| gh version | unknown |", result.stdout)
        self.assertIn("| jq version | unknown |", result.stdout)
        self.assertEqual([], self.fixture.entries())
        self.assertEqual([], list(self.tmp.iterdir()))

    def test_cleanup_keeps_unexpected_entries_and_preserves_original_failure(self):
        success = self.run_block(DELIVERY_FAULT="extra")
        self.assertEqual(3, success.returncode, success.stderr)
        self.assertIn("cleanup incomplete", success.stderr)
        failure = self.run_block("--send", DELIVERY_FAULT="extra")
        self.assertEqual(4, failure.returncode, failure.stderr)
        for scratch in self.tmp.iterdir():
            self.assertEqual(["unexpected"], [p.name for p in scratch.iterdir()])

    def test_send_needs_both_original_terminal_descriptors_and_empty_ci(self):
        for options in ({"stdin_tty": False}, {"stderr_tty": False}, {"env": {"CI": "false"}},
                        {"env": {"GITHUB_ACTIONS": "true"}}):
            with self.subTest(options=options):
                code, _, output = self.terminal(**options)
                self.assertEqual(4, code, output)
                self.assertEqual([], self.fixture.creates())
        self.assertEqual([], list(self.tmp.iterdir()))

    def test_exact_y_or_Y_after_preview_sends_once_to_fixed_public_destination(self):
        for answer in ("y", "Y"):
            self.fixture.calls.write_text("")
            code, output, preview = self.terminal(answer)
            self.assertEqual(0, code, preview)
            self.assertEqual(REPOSITORY + "/issues/42\n", output)
            creates = self.fixture.creates()
            self.assertEqual(1, len(creates))
            argv = creates[0]["argv"]
            self.assertEqual(REPOSITORY, argv[3])
            self.assertLess(preview.index(argv[7]), preview.index("Send this public report?"))
            self.assertEqual([], list(self.tmp.iterdir()))

    def test_default_no_and_nonexact_consent_never_send(self):
        for answer in ("", "n", "yes", " y", "y ", None):
            with self.subTest(answer=answer):
                code, _, preview = self.terminal(answer)
                self.assertEqual(3, code, preview)
                self.assertEqual([], self.fixture.creates())
        self.assertEqual([], list(self.tmp.iterdir()))

    def test_unconfirmed_send_preserves_one_attempt_and_does_not_leak_or_retry(self):
        code, output, preview = self.terminal(env={"FIXTURE_CREATE_RC": "1", "FIXTURE_CREATE_OUTPUT": "private-response"})
        self.assertEqual(5, code, preview)
        self.assertEqual("", output)
        self.assertIn("result=submission-unconfirmed", preview)
        self.assertNotIn("private-response", preview)
        self.assertEqual(1, len(self.fixture.creates()))
        self.assertEqual([], list(self.tmp.iterdir()))

    def test_local_and_external_failure_guidance_preserves_status_without_network(self):
        entry = ROOT / ".github/scripts/scaffold-init.sh"
        env = dict(self.env, LC_ALL="C", LANG="C", LC_CTYPE="C",
                   PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        for args, changes, expected in (([str(entry), "--unknown"], {}, 2),
                                        ([str(entry), "--dry-run", "invalid\npath"], {}, 1),
                                        ([str(entry)], {"SCAFFOLD_SOURCE_DIR": ""}, 1)):
            result = subprocess.run(["/bin/bash", *args], env=dict(env, **changes), capture_output=True, text=True)
            self.assertEqual(expected, result.returncode, result.stderr)
            self.assertEqual(1, result.stderr.count(GUIDANCE))
            self.assertIn(FORM, result.stderr)
            self.assertNotIn("Send this public report?", result.stderr)
        saved = self.work / "external.sh"
        shutil.copyfile(entry, saved)
        result = subprocess.run(["/bin/bash", str(saved)], env=dict(env, SCAFFOLD_REPO="invalid"), capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertEqual(1, result.stderr.count(GUIDANCE))
        help_result = subprocess.run(["/bin/bash", str(entry), "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(0, help_result.returncode)
        self.assertNotIn(GUIDANCE, help_result.stderr)
        self.assertEqual([], self.fixture.entries())
        self.assertEqual("", self.http.read_text())

    def test_powershell_early_child_failures_restore_caller_and_do_not_report(self):
        pwsh = shutil.which("pwsh")
        if not pwsh: self.skipTest("PowerShell host unavailable; native Windows unmeasured")
        entry = ROOT / ".github/scripts/scaffold-init.ps1"
        child = self.work / "synthetic-bash"
        child.write_text("#!/bin/sh\nexit 37\n")
        child.chmod(0o755)
        runner = self.work / "runner.ps1"
        env = dict(os.environ, LC_ALL="C", LANG="C", LC_CTYPE="C", DELIVERY_PS=str(entry),
                   DELIVERY_CHILD=str(child), SCAFFOLD_SOURCE_DIR=str(ROOT),
                   SCAFFOLD_FAILURE_GUIDANCE_OWNER="caller-value")
        for finding in ("@()", "[pscustomobject]@{Source=$env:DELIVERY_CHILD}"):
            runner.write_text("function Get-Command { " + finding + " }\n"
                "try { & ([scriptblock]::Create([IO.File]::ReadAllText($env:DELIVERY_PS))) } catch { Write-Output ('EXPECTED-ERROR ' + $_.Exception.Message) }\n"
                "Write-Output ('OWNER=' + $env:SCAFFOLD_FAILURE_GUIDANCE_OWNER)\n"
                "Write-Output 'CALLER-ALIVE'\n")
            result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("CALLER-ALIVE", result.stdout)
            self.assertIn("EXPECTED-ERROR", result.stdout)
            self.assertIn("OWNER=caller-value", result.stdout)
            self.assertEqual(1, result.stderr.count(GUIDANCE), result.stderr)
            if finding != "@()": self.assertIn("exited with code 37", result.stdout)
        runner.write_text("function Get-Command { [pscustomobject]@{Source=$env:DELIVERY_CHILD} }\n& $env:DELIVERY_PS\nexit $LASTEXITCODE\n")
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(37, result.returncode, result.stderr)
        self.assertEqual(1, result.stderr.count(GUIDANCE))
        self.assertEqual([], self.fixture.creates())

    def test_terminating_local_entry_pid_cannot_leave_installer_running(self):
        kit = self.work / "kit"
        shutil.copytree(ROOT / ".github/distribution/payload", kit / ".github/distribution/payload")
        shutil.copyfile(ROOT / ".github/distribution/payload.v1.tsv", kit / ".github/distribution/payload.v1.tsv")
        (kit / ".github/scripts").mkdir()
        for name in ("scaffold-init.sh", "scaffold-install.sh"):
            shutil.copyfile(ROOT / ".github/scripts" / name, kit / ".github/scripts" / name)
        self.executable("git", r'''
import os,sys,time
from pathlib import Path
a=sys.argv[1:]
if len(a)==4 and a[0]=='-C' and a[2:]==['rev-parse','--git-dir']:
 Path(os.environ['DELIVERY_HOLD']).touch()
 deadline=time.monotonic()+10
 while not Path(os.environ['DELIVERY_RELEASE']).exists() and time.monotonic()<deadline: time.sleep(.02)
os.execv(os.environ['DELIVERY_GIT'],[os.environ['DELIVERY_GIT'],*a])
''')
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig):
                target = self.work / ("signal-target-" + str(sig))
                target.mkdir()
                subprocess.run([shutil.which("git"), "init", "-q", str(target)], check=True)
                hold = self.work / ("hold-" + str(sig))
                release = self.work / ("release-" + str(sig))
                env = dict(self.env, LC_ALL="C", LANG="C", LC_CTYPE="C",
                           PATH=str(self.bin) + os.pathsep + os.environ["PATH"], DELIVERY_GIT=shutil.which("git"),
                           DELIVERY_HOLD=str(hold), DELIVERY_RELEASE=str(release))
                process = subprocess.Popen(["/bin/bash", str(kit / ".github/scripts/scaffold-init.sh"), "--apply", str(target)],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                try:
                    deadline = time.monotonic() + 8
                    while not hold.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.02)
                    self.assertTrue(hold.exists(), "local engine reached bounded preflight pause")
                    os.kill(process.pid, sig)
                    time.sleep(.1)
                    release.touch()
                    process.communicate(timeout=10)
                    self.assertEqual(-sig, process.returncode)
                    self.assertEqual([], [path for path in target.iterdir() if path.name != ".git"])
                finally:
                    release.touch()
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
