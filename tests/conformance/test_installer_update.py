"""Explicit updater regressions with real Git/Bash and synthetic transport."""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ".github/scripts/scaffold-update.sh"
PS_ENTRY = ".github/scripts/scaffold-update.ps1"
ENGINE = ".github/scripts/scaffold-install.sh"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"
GIT = shutil.which("git")
BASH = shutil.which("bash")


class UpdateTests(unittest.TestCase):
    @staticmethod
    def git(root, *args):
        return subprocess.check_output([GIT, "-C", str(root), *args], text=True,
            env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                     LC_ALL="C", GIT_OPTIONAL_LOCKS="0")).strip()

    @classmethod
    def commit(cls, root):
        cls.git(root, "add", "-A")
        cls.git(root, "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                "commit", "-qm", "Synthetic update fixture")
        return cls.git(root, "rev-parse", "HEAD")

    @staticmethod
    def reseal(root):
        rows = [line.split("\t") for line in (root / INVENTORY).read_text().splitlines()
                if line and not line.startswith("#")]
        (root / INVENTORY).write_text("".join("\t".join((name, kind,
            hashlib.sha256((root / PAYLOAD / name).read_bytes()).hexdigest())) + "\n"
            for name, kind, _ in rows))

    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix="update-seed-")
        cls.seed = Path(cls.shared.name).resolve() / "source"
        cls.seed.mkdir()
        for path in (ENTRY, PS_ENTRY, ENGINE, INVENTORY):
            dest = cls.seed / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)
        shutil.copytree(ROOT / PAYLOAD, cls.seed / PAYLOAD)
        cls.git(cls.seed, "init", "--template=", "-q", "-b", "main")
        cls.old = cls.commit(cls.seed)
        cls.rows = [line.split("\t") for line in (cls.seed / INVENTORY).read_text().splitlines()
                    if line and not line.startswith("#")]
        cls.changed = [row[0] for row in cls.rows if row[1] == "engine"][:2]
        for name in cls.changed:
            path = cls.seed / PAYLOAD / name
            path.write_bytes(path.read_bytes() + b"\nSynthetic newer fixture.\n")
        cls.reseal(cls.seed)
        cls.new = cls.commit(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-real-git-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        self.git(self.base, "clone", "--no-hardlinks", "-q", str(self.seed), str(self.source))
        self.target = self.base / "adopter with spaces"
        self.target.mkdir()
        self.git(self.target, "init", "--template=", "-q", "-b", "main")
        shutil.copytree(ROOT / PAYLOAD, self.target, dirs_exist_ok=True)
        self.commit(self.target)
        self.recovery = self.base / "private recovery"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.shim("git", r'''#!/usr/bin/env bash
set -eu
args=(); operation=""; repo=""
for arg in "$@"; do
  case "$arg" in fetch|fsck|cat-file|ls-tree|--show-prefix) operation="$arg" ;; --git-dir=*) repo="${arg#--git-dir=}" ;; esac
  if [ "$arg" = https://github.com/mochan-tk/agentic-dev-kit-for-codex ]; then args+=("$FIXTURE_SOURCE")
  else args+=("$arg"); fi
done
printf '%s\n' "$*" >> "$TRANSPORT_LOG"
if [ "$operation" = fetch ]; then
  [ "$GIT_CONFIG_NOSYSTEM" = 1 ] && [ "$GIT_CONFIG_GLOBAL" = /dev/null ] && [ "$GIT_TERMINAL_PROMPT" = 0 ] || exit 42
  [ "$HOME" = "${repo%/objects.git}/transport-home" ] && [ ! -e "$HOME/.netrc" ] || exit 45
  case "$*" in *'credential.helper='*'core.hooksPath=/dev/null'*'fetch --no-tags --depth=1 https://github.com/'*) ;; *) exit 43 ;; esac
  [ -n "$repo" ] && [ "$repo" != "$FIXTURE_TARGET/.git" ] || exit 44
  case "$FIXTURE_FAILURE" in fetch) exit 37 ;; wrong-fetch) args[${#args[@]}-1]="$FIXTURE_OTHER" ;; esac
fi
case "$FIXTURE_FAILURE:$operation" in fsck:fsck|lookup:ls-tree|read:cat-file|prefix:--show-prefix) exit 38 ;; esac
"$REAL_GIT" "${args[@]}"
if [ "$operation" = fetch ]; then
  case "$FIXTURE_FAILURE" in corrupt|missing)
    commit="$("$REAL_GIT" --git-dir="$repo" rev-parse FETCH_HEAD)"
    object="$repo/objects/${commit:0:2}/${commit:2}"
    if [ ! -f "$object" ]; then pack=("$repo"/objects/pack/*.pack); object="${pack[0]}"; fi
    [ -f "$object" ] || exit 41
    if [ "$FIXTURE_FAILURE" = corrupt ]; then printf corrupt > "$object"; else rm -- "$object"; fi ;;
  esac
fi
''')
        self.shim("curl", r'''#!/usr/bin/env bash
set -eu
[ "$#" = 2 ] && [ "$1" = -fsSL ] || exit 39
[ "$2" = https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/.github/scripts/scaffold-update.sh ] || exit 39
"$REAL_GIT" -C "$FIXTURE_SOURCE" show main:.github/scripts/scaffold-update.sh
''')
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "SCAFFOLD_"))}
        self.env.update(LC_ALL="C", PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        REAL_GIT=GIT, FIXTURE_SOURCE=str(self.source), FIXTURE_FAILURE="",
                        FIXTURE_OTHER=self.new, FIXTURE_TARGET=str(self.target), TMPDIR=str(self.base),
                        TRANSPORT_LOG=str(self.base / "transport.log"))

    def shim(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def snapshot(self, root=None):
        root = root or self.target
        return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
                else ("file", stat.S_IMODE(p.stat().st_mode), p.read_bytes()) if p.is_file()
                else ("dir", stat.S_IMODE(p.stat().st_mode)) for p in root.rglob("*")}

    def run_entry(self, *args, env=None, old=None, new=None, recovery=None, cwd=None):
        command = [BASH, str(ROOT / ENTRY), "--from", old or self.old, "--to", new or self.new,
                   "--recovery", str(recovery or self.recovery), *args]
        return subprocess.run(command, cwd=cwd or self.target, env=dict(self.env, **(env or {})),
                              capture_output=True, text=True, timeout=120)

    def success(self, result):
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def refuse(self, *args, **kwargs):
        before = self.snapshot()
        result = self.run_entry(*args, **kwargs)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertEqual(before, self.snapshot())
        return result

    def rollback(self, *args):
        # Network is unavailable; only retained inputs and the unchanged engine run.
        log = self.base / "transport.log"
        fetches = [line for line in log.read_text().splitlines() if " fetch " in line]
        result = subprocess.run([BASH, str(self.recovery / "new" / ENGINE), "--rollback",
            "--transaction", str(self.recovery / "transaction"), *args, str(self.target)],
            env=dict(self.env, SCAFFOLD_SOURCE_DIR=str(self.recovery / "new"), FIXTURE_FAILURE="fetch"),
            capture_output=True, text=True, timeout=90)
        self.assertEqual(fetches, [line for line in log.read_text().splitlines() if " fetch " in line])
        return result

    def test_standalone_entry_documents_explicit_inputs(self):
        result = subprocess.run([shutil.which("bash"), str(ROOT / ENTRY), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        for option in ("--from", "--to", "--recovery", "--dry-run", "--apply"):
            self.assertIn(option, result.stdout)

    def test_default_preview_and_apply_preserve_classes_git_and_offline_rollback(self):
        preserved = [name for name, kind, _ in self.rows if kind != "engine"]
        for name in preserved:
            path = self.target / name
            path.write_text("adopter-owned\n")
            path.chmod(0o600)
        note = self.target / "notes"
        note.write_text("staged\n")
        self.git(self.target, "add", "notes")
        note.write_text("unstaged\n")
        before = self.snapshot()
        self.success(self.run_entry())
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.recovery.exists())
        self.assertEqual([], list(self.base.glob("scaffold-update.*")))
        self.success(self.run_entry("--apply"))
        self.assertEqual(0o700, stat.S_IMODE(self.recovery.stat().st_mode))
        after = self.snapshot()
        self.assertEqual({n: v for n, v in before.items() if n not in self.changed},
                         {n: v for n, v in after.items() if n not in self.changed})
        for name in self.changed:
            self.assertEqual((self.source / PAYLOAD / name).read_bytes(), (self.target / name).read_bytes())
        for role in ("old", "new"):
            self.assertTrue((self.recovery / role / ENGINE).is_file())
            self.assertEqual(47, len([p for p in (self.recovery / role / PAYLOAD).rglob("*") if p.is_file()]))
        self.assertTrue((self.recovery / "transaction/meta.tsv").is_file())
        before_rollback = self.snapshot()
        self.success(self.rollback("--dry-run"))
        self.assertEqual(before_rollback, self.snapshot())
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())

    def test_already_new_retains_sources_without_transaction(self):
        self.success(self.run_entry("--apply"))
        before = self.snapshot()
        second = self.base / "second recovery"
        result = self.run_entry("--apply", recovery=second)
        self.success(result)
        self.assertIn("Already new", result.stdout)
        self.assertEqual(before, self.snapshot())
        self.assertTrue((second / "old").is_dir())
        self.assertFalse((second / "transaction").exists())

    def test_rollback_refuses_affected_edit_and_preserves_unrelated_edit(self):
        self.success(self.run_entry("--apply"))
        affected = self.target / self.changed[-1]
        expected = affected.read_bytes()
        affected.write_text("later edit\n")
        before = self.snapshot()
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot())
        affected.write_bytes(expected)
        (self.target / "unrelated").write_text("keep later edit\n")
        self.success(self.rollback("--apply"))
        self.assertEqual("keep later edit\n", (self.target / "unrelated").read_text())

    def test_partial_apply_retains_recoverable_inputs_and_unknown_partial_refuses(self):
        second = str(self.target / self.changed[-1])
        self.shim("cp", "#!/bin/sh\nfor arg in \"$@\"; do last=$arg; done\n"
                  + "if [ \"$last\" = " + shlex.quote(second) + " ]; then exit 77; fi\nexec /bin/cp \"$@\"\n")
        before = self.snapshot()
        result = self.run_entry("--apply")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("partial", (self.recovery / "transaction/status").read_text())
        self.assertEqual((self.source / PAYLOAD / self.changed[0]).read_bytes(),
                         (self.target / self.changed[0]).read_bytes())
        (self.bin / "cp").unlink()
        affected = self.target / self.changed[-1]
        original = affected.read_bytes()
        affected.write_bytes(b"unknown partial")
        partial = self.snapshot()
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(partial, self.snapshot())
        affected.write_bytes(original)
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())

    def test_whole_inventory_collision_refusal_precedes_target_writes(self):
        engines = [name for name, kind, _ in self.rows if kind == "engine"]
        (self.target / engines[-1]).write_text("unknown engine\n")
        self.refuse("--apply")
        self.assertTrue((self.recovery / "new").is_dir())
        self.assertFalse((self.recovery / "transaction").exists())

    def test_retained_source_identity_drift_refuses_even_with_identical_bytes(self):
        self.success(self.run_entry("--apply"))
        retained = self.recovery / "new"
        original = self.recovery / "original-new"
        retained.rename(original)
        shutil.copytree(original, retained)
        before = self.snapshot()
        result = self.rollback("--apply")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("source root mismatch", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_failed_backup_leaves_target_unchanged_and_inputs_retained(self):
        self.shim("cp", "#!/bin/sh\nfor arg in \"$@\"; do last=$arg; done\n"
                  + "case \"$last\" in */transaction/before-*) exit 77 ;; esac\nexec /bin/cp \"$@\"\n")
        before = self.snapshot()
        self.refuse("--apply")
        self.assertEqual(before, self.snapshot())
        self.assertTrue((self.recovery / "old" / ENGINE).is_file())
        self.assertTrue((self.recovery / "new" / ENGINE).is_file())
        self.assertTrue((self.recovery / "transaction").is_dir())
        self.assertFalse((self.recovery / "transaction/record.sha256").exists())
        self.assertNotEqual(0, self.rollback("--apply").returncode)
        self.assertEqual(before, self.snapshot())

    def test_install_missing_file_then_operation_rollback(self):
        missing = self.target / self.changed[0]
        missing.unlink()
        before = self.snapshot()
        self.success(self.run_entry("--apply"))
        self.assertTrue(missing.is_file())
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())

    def test_invalid_options_revisions_and_context_are_prewrite_refusals(self):
        for args in (("--force",), ("--apply", "--dry-run"), ("--from", self.old),
                     ("--to", self.new), ("--recovery", str(self.recovery)), ("--unknown",)):
            with self.subTest(args=args): self.refuse(*args)
        for pin in ("main", self.old[:12], "0" * 40, self.old.upper(), "../bad", ""):
            with self.subTest(pin=pin):
                if pin: self.refuse(old=pin)
        for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_CONFIG_PARAMETERS", "GIT_OBJECT_DIRECTORY",
                    "GIT_CONFIG_COUNT", "GIT_NAMESPACE", "SCAFFOLD_SOURCE_DIR", "GIT_SSL_CERT",
                    "GIT_SSL_KEY", "GIT_SSL_NO_VERIFY", "GIT_SSL_CAINFO", "NETRC"):
            with self.subTest(key=key): self.refuse(env={key: "untrusted"})
        self.refuse(env={"SCAFFOLD_REPO": "https://bad.invalid/repo"})
        self.refuse(env={"FIXTURE_FAILURE": "prefix"})
        self.assertFalse(self.recovery.exists())

    def test_unsafe_target_recovery_and_scratch_paths_refuse_without_mutation(self):
        self.recovery.mkdir()
        (self.recovery / "keep").write_text("existing\n")
        existing = self.snapshot(self.recovery)
        self.refuse("--apply")
        self.assertEqual(existing, self.snapshot(self.recovery))
        for path in (self.target / "recovery", self.target, self.base / "missing/record"):
            with self.subTest(path=path): self.refuse("--apply", recovery=path)
        alias = self.base / "alias"
        alias.symlink_to(self.target, target_is_directory=True)
        self.refuse(str(alias), recovery=self.base / "unused")
        self.refuse(recovery=alias / "record")
        self.refuse(recovery=self.base / "unused", env={"TMPDIR": str(self.target)})
        self.refuse(recovery=self.base / "unused", env={"TMPDIR": str(alias)})
        recovery_link = self.base / "recovery-link"
        recovery_link.symlink_to(self.base / "absent")
        self.refuse(recovery=recovery_link)
        (self.target / ".agents").rename(self.target / "agents-original")
        (self.target / ".agents").symlink_to(self.target / "agents-original", target_is_directory=True)
        self.refuse(recovery=self.base / "unused")

    def test_scratch_os_alias_cleans_up_and_saved_relative_target_works(self):
        physical = self.base / "scratch"
        physical.mkdir()
        alias = self.base / "scratch-alias"
        alias.symlink_to(physical, target_is_directory=True)
        before = self.snapshot()
        self.success(self.run_entry(self.target.name, cwd=self.base, env={"TMPDIR": str(alias)}))
        self.assertEqual(before, self.snapshot())
        self.assertEqual([], list(physical.iterdir()))

    def test_transport_integrity_failures_keep_target_unchanged(self):
        for fault in ("fetch", "wrong-fetch", "corrupt", "missing", "fsck", "lookup", "read"):
            with self.subTest(fault=fault):
                self.refuse(env={"FIXTURE_FAILURE": fault})
                self.assertFalse(self.recovery.exists())
                self.assertEqual([], list(self.base.glob("scaffold-update.*")))
        self.refuse("--apply", env={"FIXTURE_FAILURE": "fetch"})
        self.assertTrue(self.recovery.is_dir())
        self.assertFalse((self.recovery / "transaction").exists())

    def test_selected_payload_layout_hash_mode_size_and_engine_refusals(self):
        for defect in ("missing", "bytes", "mode", "link", "extra", "layout", "engine", "size"):
            with self.subTest(defect=defect):
                self.git(self.source, "reset", "--hard", self.new)
                extra = self.source / PAYLOAD / "extra"
                if extra.exists(): extra.unlink()
                path = self.source / PAYLOAD / "AGENTS.md"
                if defect == "missing": path.unlink()
                elif defect == "bytes": path.write_text("unbound\n")
                elif defect == "mode": path.chmod(0o755)
                elif defect == "link": path.unlink(); path.symlink_to("/etc/passwd")
                elif defect == "extra": extra.write_text("unlisted\n")
                elif defect == "layout":
                    inventory = self.source / INVENTORY
                    inventory.write_text(inventory.read_text().replace("AGENTS.md", "../escape"))
                elif defect == "engine":
                    engine = self.source / ENGINE
                    engine.write_bytes(engine.read_bytes() + b"\n# unreviewed\n")
                else:
                    path.write_bytes(b"x" * (1048576 + 1))
                    self.reseal(self.source)
                pin = self.commit(self.source)
                self.refuse(new=pin)
                # Both requested revisions must pass the same gate.
                if defect == "engine": self.refuse(old=pin)

    def test_selected_updater_is_never_executed_and_config_isolation(self):
        sentinel = self.base / "selected-code-ran"
        (self.source / ENTRY).write_text("#!/bin/sh\ntouch " + shlex.quote(str(sentinel)) + "\nexit 81\n")
        pin = self.commit(self.source)
        global_config = self.base / "global-config"
        global_config.write_text('[url "file:///unreachable/"]\n\tinsteadOf = https://github.com/\n'
                                 '[credential]\n\thelper = !touch ' + shlex.quote(str(sentinel)) + '\n')
        caller_home = self.base / "caller-home"
        caller_home.mkdir()
        (caller_home / ".netrc").write_text("machine github.com login synthetic password never-send\n")
        self.git(self.target, "config", "core.fsmonitor", "touch " + shlex.quote(str(sentinel)))
        self.success(self.run_entry(new=pin, env={"GIT_CONFIG_GLOBAL": str(global_config), "HOME": str(caller_home)}))
        self.assertFalse(sentinel.exists())

    def test_readme_bash_preview_apply_and_initial_download_failure(self):
        lines = [line for line in (ROOT / "README.md").read_text().splitlines()
                 if line.startswith("curl -fsSL ") and "scaffold-update.sh" in line]
        self.assertEqual(2, len(lines))
        env = dict(self.env, FROM=self.old, TO=self.new, RECOVERY=str(self.recovery))
        before = self.snapshot()
        for line in lines:
            result = subprocess.run([BASH, "-o", "pipefail", "-c", line], cwd=self.target,
                                    env=env, capture_output=True, text=True, timeout=120)
            self.success(result)
            if "--apply" not in line:
                self.assertEqual(before, self.snapshot())
                self.assertFalse(self.recovery.exists())
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())
        self.shim("curl", "#!/bin/sh\nexit 22\n")
        result = subprocess.run([BASH, "-o", "pipefail", "-c", lines[0]], cwd=self.target,
                                env=env, capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot())

    def test_readme_powershell_host_preview_apply_and_failure(self):
        pwsh = shutil.which("pwsh")
        if not pwsh: self.skipTest("PowerShell host unavailable; native Windows unmeasured")
        lines = [line for line in (ROOT / "README.md").read_text().splitlines()
                 if line.startswith("& ([scriptblock]::Create((irm ") and "scaffold-update.ps1" in line]
        self.assertEqual(2, len(lines))
        harness = r'''
$ErrorActionPreference = 'Stop'
$From = $env:UPDATE_FROM; $To = $env:UPDATE_TO; $Recovery = $env:UPDATE_RECOVERY
function Get-Command { [pscustomobject]@{Source=$env:FIXTURE_BASH} }
function Read-FixtureUrl([string]$Uri) {
    $prefix = 'https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/main/'
    if (-not $Uri.StartsWith($prefix)) { throw 'unexpected fixture URL' }
    $path = $Uri.Substring($prefix.Length)
    if ($path -notmatch '^\.github/scripts/scaffold-update\.(sh|ps1)$') { throw 'unexpected fixture path' }
    $lines = & $env:REAL_GIT -C $env:FIXTURE_SOURCE show ('main:' + $path)
    if ($LASTEXITCODE -ne 0) { throw 'fixture source missing' }
    return (($lines -join [char]10) + [char]10)
}
function Invoke-RestMethod { param([string]$Uri) Read-FixtureUrl $Uri }
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,[string]$Uri,[string]$OutFile)
    [IO.File]::WriteAllText($OutFile, (Read-FixtureUrl $Uri), [Text.UTF8Encoding]::new($false))
}
'''
        env = dict(self.env, FIXTURE_BASH=BASH, UPDATE_FROM=self.old, UPDATE_TO=self.new,
                   UPDATE_RECOVERY=str(self.recovery))
        runner = self.base / "powershell.ps1"
        before = self.snapshot()
        for line in lines:
            runner.write_text(harness + line + "\n")
            self.success(subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                       env=env, capture_output=True, text=True, timeout=120))
            if "--apply" not in line:
                self.assertEqual(before, self.snapshot())
                self.assertFalse(self.recovery.exists())
        self.success(self.rollback("--apply"))
        self.assertEqual(before, self.snapshot())
        runner.write_text(harness + "try { " + lines[0].replace("--from", "--unknown")
                          + " } catch { Write-Output 'EXPECTED-ERROR' }\nWrite-Output 'CALLER-ALIVE'\n")
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertIn("EXPECTED-ERROR", result.stdout)
        self.assertIn("CALLER-ALIVE", result.stdout)
        runner.write_text(harness + "function Invoke-WebRequest { throw 'HTTP-FAILURE' }\n" + lines[0])
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
