"""Real Git/disposable-adopter bootstrap evidence with synthetic URL transport."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ".github/scripts/scaffold-init.sh"
PS_ENTRY = ".github/scripts/scaffold-init.ps1"
ENGINE = ".github/scripts/scaffold-install.sh"
INVENTORY = ".github/distribution/payload.v1.tsv"
PAYLOAD = ".github/distribution/payload"
GIT = shutil.which("git")
BASH = shutil.which("bash")


def product_checker():
    spec = importlib.util.spec_from_file_location("product_checker", ROOT / ".github/scripts/check-product.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix="bootstrap-git-seed-")
        cls.seed = Path(cls.shared.name) / "source"
        cls.seed.mkdir()
        for path in (ENTRY, PS_ENTRY, ENGINE, INVENTORY):
            dest = cls.seed / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)
        shutil.copytree(ROOT / PAYLOAD, cls.seed / PAYLOAD)
        cls.command(cls.seed, "init", "-q", "-b", "main")
        cls.command(cls.seed, "add", ".")
        cls.command(cls.seed, "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                    "commit", "-qm", "reviewed fixture")
        cls.pin = cls.command(cls.seed, "rev-parse", "HEAD").strip()

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    @staticmethod
    def command(cwd, *args):
        return subprocess.check_output([GIT, "-C", str(cwd), *args],
                                       env=dict(os.environ, LC_ALL="C"), text=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap-real-git-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        subprocess.run([GIT, "clone", "-q", "--no-hardlinks", str(self.seed), str(self.source)], check=True)
        self.target = self.base / "adopter with spaces"
        self.target.mkdir()
        self.command(self.target, "init", "-q", "-b", "main")
        self.command(self.target, "config", "gc.auto", "0")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        # Only the exact public URL is redirected; Git reads/writes real objects.
        git_shim = r"""#!/usr/bin/env bash
set -eu
args=(); operation=""
for arg in "$@"; do
  case "$arg" in ls-remote|fetch|update-index|cat-file|config) operation="$arg" ;; esac
  if [ "$arg" = https://github.com/mochan-tk/agentic-dev-kit-for-codex ]; then
    args+=("$FIXTURE_SOURCE")
  else args+=("$arg"); fi
done
printf '%s\n' "$*" >> "$TRANSPORT_LOG"
if [ "$operation" = ls-remote ] || [ "$operation" = fetch ]; then
  private=0
  for arg in "$@"; do case "$arg" in --git-dir=*/scaffold-bootstrap.*/objects.git) private=1 ;; esac; done
  [ "$private" = 1 ] && [ "$GIT_CONFIG_NOSYSTEM" = 1 ] && [ "$GIT_CONFIG_GLOBAL" = /dev/null ] && [ "$GIT_TERMINAL_PROMPT" = 0 ] || exit 42
fi
case "$FIXTURE_FAILURE:$operation" in fetch:fetch|stage:update-index) exit 37 ;; esac
if [ "$operation" = config ]; then
  case "$FIXTURE_FAILURE" in
    config-error) exit 3 ;;
    config-truncated) printf 'filter.example.clean'; exit 0 ;;
    config-contradiction) printf 'filter.example.clean\0'; exit 1 ;;
    config-empty) exit 0 ;;
  esac
fi
if [ "$operation" = fetch ] && [ "$FIXTURE_FAILURE" = wrong-fetch ]; then
  args[${#args[@]}-1]="$FIXTURE_OTHER"
fi
"$REAL_GIT" "${args[@]}"
code=$?
if [ "$operation" = fetch ]; then
  case "$FIXTURE_FAILURE" in corrupt|missing)
    for arg in "$@"; do case "$arg" in --git-dir=*) repo="${arg#--git-dir=}" ;; esac; done
    commit="$("$REAL_GIT" --git-dir="$repo" rev-parse FETCH_HEAD)"
    object="$repo/objects/${commit:0:2}/${commit:2}"
    if [ ! -f "$object" ]; then pack=("$repo"/objects/pack/*.pack); object="${pack[0]}"; fi
    [ -f "$object" ] || exit 41
    if [ "$FIXTURE_FAILURE" = corrupt ]; then printf 'corrupt' > "$object"
    else rm -- "$object"; fi ;;
  esac
fi
if [ "$operation" = ls-remote ] && [ -n "${FIXTURE_MOVE:-}" ]; then
  "$REAL_GIT" -C "$FIXTURE_SOURCE" update-ref refs/heads/main "$FIXTURE_MOVE"
fi
exit "$code"
"""
        curl_shim = r"""#!/usr/bin/env bash
set -eu
[ "$#" = 2 ] && [ "$1" = -fsSL ] || exit 39
prefix=https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/
case "$2" in "$prefix"*) ;; *) exit 39 ;; esac
rest="${2#"$prefix"}"
ref="${rest%/.github/scripts/scaffold-init.sh}"
[ "$rest" = "$ref/.github/scripts/scaffold-init.sh" ] || exit 39
"$REAL_GIT" -C "$FIXTURE_SOURCE" show "$ref:.github/scripts/scaffold-init.sh"
"""
        for name, text in (("git", git_shim), ("curl", curl_shim)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.env = dict(os.environ, LC_ALL="C", PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        REAL_GIT=GIT, FIXTURE_SOURCE=str(self.source), FIXTURE_FAILURE="",
                        TRANSPORT_LOG=str(self.base / "transport.log"), TMPDIR=str(self.base))
        for name in list(self.env):
            if name.startswith("SCAFFOLD_") or name.startswith("GIT_"):
                self.env.pop(name)

    def run_entry(self, *args, ref=None, saved=False, cwd=None, env=None, bash=BASH):
        selected_env = dict(self.env)
        selected_env.update(env or {})
        if ref:
            selected_env["SCAFFOLD_REF"] = ref
        if saved:
            entry = self.base / "saved bootstrap.sh"
            shutil.copyfile(ROOT / ENTRY, entry)
            command = [bash, str(entry), *args]
        else:
            line = next(line for line in (ROOT / "README.md").read_text().splitlines()
                        if line.startswith("curl -fsSL ") and line.endswith(" | bash"))
            command = [bash, "-o", "pipefail", "-c",
                       line.replace(" | bash", " | " + shlex.quote(bash) + " -s --"
                                    + "".join(" " + shlex.quote(arg) for arg in args))]
        return subprocess.run(command, cwd=cwd or self.target, env=selected_env,
                              capture_output=True, text=True, timeout=90)

    def snapshot(self):
        return {str(p.relative_to(self.target)): ("link", os.readlink(p)) if p.is_symlink()
                else ("file", p.read_bytes()) if p.is_file() else ("dir",)
                for p in self.target.rglob("*")}

    def git(self, *args):
        return self.command(self.target, *args).strip()

    def commit(self, root):
        self.command(root, "add", "-A")
        self.command(root, "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                     "commit", "-qm", "fixture")
        return self.command(root, "rev-parse", "HEAD").strip()

    def assert_success(self, result):
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def assert_refusal_unchanged(self, *args, **kwargs):
        before = self.snapshot()
        result = self.run_entry(*args, **kwargs)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertEqual(before, self.snapshot())
        return result

    def test_readme_pipeline_exact_payload_stage_repeat_and_dry_run(self):
        result = self.run_entry()
        self.assert_success(result)
        self.assertIn("47 newly installed files staged", result.stdout)
        self.assertIn("Selected source-commit=" + self.pin, result.stdout)
        rows = [r.split("\t") for r in (ROOT / INVENTORY).read_text().splitlines() if r and not r.startswith("#")]
        self.assertEqual([r[0] for r in rows], self.git("diff", "--cached", "--name-only").splitlines())
        for name, _, digest in rows:
            self.assertEqual(digest, hashlib.sha256((self.target / name).read_bytes()).hexdigest())
            self.assertEqual((ROOT / PAYLOAD / name).read_bytes(),
                             subprocess.check_output([GIT, "-C", str(self.target), "show", ":" + name]))
        before = self.snapshot()
        self.assert_success(self.run_entry())
        self.assertEqual(before, self.snapshot())
        self.assert_success(self.run_entry("--dry-run"))
        self.assertEqual(before, self.snapshot())

    def test_dry_run_unknown_option_and_invalid_local_source(self):
        before = self.snapshot()
        self.assert_success(self.run_entry("--dry-run"))
        self.assertEqual(before, self.snapshot())
        for option in ("--unknown", "--force", "--upgrade"):
            self.assert_refusal_unchanged(option)
        for local in ("", str(self.base / "missing")):
            self.assert_refusal_unchanged(env={"SCAFFOLD_SOURCE_DIR": local})

    def test_branch_tags_full_sha_and_saved_relative_target(self):
        self.command(self.source, "branch", "feature/one")
        self.command(self.source, "tag", "light")
        self.command(self.source, "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                     "tag", "-a", "annotated", "-m", "fixture")
        for ref in ("feature/one", "light", "annotated", self.pin):
            result = self.run_entry("--dry-run", ref=ref)
            self.assert_success(result)
            self.assertIn("Selected source-commit=" + self.pin, result.stdout)
        self.assert_success(self.run_entry(self.target.name, ref=self.pin, saved=True, cwd=self.base))

    def test_external_drive_target_conversion_is_synthetic(self):
        converter = self.bin / "cygpath"
        converter.write_text("#!/bin/sh\n[ \"$1\" = -u ] && [ \"$2\" = -- ] || exit 1\nprintf '%s\\n' \"$FIXTURE_TARGET\"\n")
        converter.chmod(0o755)
        self.assert_success(self.run_entry("D:\\adopter with spaces", env={"FIXTURE_TARGET": str(self.target)}))

    def test_missing_ref_transport_missing_and_corrupt_objects(self):
        self.assert_refusal_unchanged(ref="does-not-exist")
        self.assert_refusal_unchanged(ref=self.pin[:9])
        for failure in ("fetch", "corrupt", "missing"):
            with self.subTest(failure=failure):
                self.assert_refusal_unchanged(env={"FIXTURE_FAILURE": failure})

    def test_ref_motion_and_canonical_selected_wrapper_dispatch(self):
        path = self.source / ENTRY
        path.write_text(path.read_text().replace("Selected source-commit=%s", "Canonical selected source-commit=%s"))
        other = self.commit(self.source)
        self.command(self.source, "update-ref", "refs/heads/main", self.pin)
        result = self.run_entry("--dry-run", env={"FIXTURE_MOVE": other})
        self.assert_success(result)
        self.assertIn("Selected source-commit=" + self.pin, result.stdout)
        result = self.run_entry("--dry-run", saved=True, ref=other)
        self.assert_success(result)
        self.assertIn("Canonical selected source-commit=" + other, result.stdout)
        self.assert_refusal_unchanged(ref=self.pin, env={"FIXTURE_FAILURE": "wrong-fetch", "FIXTURE_OTHER": other})

    def test_selected_missing_modified_symlink_extra_inventory_and_engine(self):
        for mutation in ("missing", "modified", "symlink", "extra", "inventory", "wrapper-link", "engine"):
            with self.subTest(mutation=mutation):
                self.command(self.source, "reset", "--hard", self.pin)
                extra = self.source / PAYLOAD / "extra"
                if extra.exists(): extra.unlink()
                path = self.source / PAYLOAD / "AGENTS.md"
                if mutation == "missing": path.unlink()
                elif mutation == "modified": path.write_text("changed\n")
                elif mutation == "symlink": path.unlink(); path.symlink_to("/etc/passwd")
                elif mutation == "extra": extra.write_text("unlisted\n")
                elif mutation == "inventory":
                    path = self.source / INVENTORY
                    path.write_text(path.read_text().replace("AGENTS.md", "../escape"))
                elif mutation == "wrapper-link":
                    path = self.source / ENTRY
                    path.unlink(); path.symlink_to("/etc/passwd")
                else:
                    path = self.source / ENGINE
                    path.write_text(path.read_text() + "\n# drift\n")
                pin = self.commit(self.source)
                self.assert_refusal_unchanged(ref=pin, saved=True)

    def test_invalid_selected_payload_cannot_execute_selected_wrapper(self):
        sentinel = self.base / "selected-code-ran"
        path = self.source / ENTRY
        path.write_text(path.read_text().replace("set -euo pipefail", "touch " + shlex.quote(str(sentinel)) + "\nset -euo pipefail", 1))
        (self.source / PAYLOAD / "AGENTS.md").chmod(0o755)
        pin = self.commit(self.source)
        self.assert_refusal_unchanged(ref=pin, saved=True)
        self.assertFalse(sentinel.exists())

    def test_preserved_files_partial_index_clean_filters_and_url_rewrite(self):
        (self.target / "README.md").write_text("mine\n")
        (self.target / ".gitattributes").write_text("* filter=sentinel text\n")
        (self.target / "notes").write_text("base\n")
        self.commit(self.target)
        (self.target / "notes").write_text("staged\n")
        self.git("add", "notes")
        (self.target / "notes").write_text("unstaged\n")
        (self.target / "untracked").write_text("keep\n")
        (self.target / "AGENTS.md").write_text("my instructions\n")
        prior = subprocess.check_output([GIT, "-C", str(self.target), "ls-files", "--stage", "notes", "README.md", ".gitattributes"])
        sentinel = self.base / "filter-ran"
        self.git("config", "filter.sentinel.clean", "touch " + shlex.quote(str(sentinel)))
        self.git("config", "core.fsmonitor", "touch " + shlex.quote(str(sentinel)))
        self.git("config", "url.file:///unreachable/.insteadOf", str(self.source))
        result = self.run_entry()
        self.assert_success(result)
        self.assertIn("44 newly installed files staged", result.stdout)
        self.assertFalse(sentinel.exists())
        actual = subprocess.check_output([GIT, "-c", "core.fsmonitor=false", "-C", str(self.target), "ls-files", "--stage", "notes", "README.md", ".gitattributes"])
        self.assertEqual(prior, actual)
        self.assertEqual("unstaged\n", (self.target / "notes").read_text())
        self.assertEqual("my instructions\n", (self.target / "AGENTS.md").read_text())

    def test_staged_deletion_missing_tracked_and_ignored_new_path(self):
        (self.target / "AGENTS.md").write_text("tracked\n")
        self.commit(self.target)
        (self.target / "AGENTS.md").unlink()
        self.assert_refusal_unchanged()
        self.git("add", "--", "AGENTS.md")
        self.assert_refusal_unchanged()
        self.git("reset", "--hard", "HEAD")
        (self.target / ".gitignore").write_text(".agents/\n")
        self.assert_refusal_unchanged()

    def test_stage_failure_keeps_installed_files_for_manual_recovery(self):
        result = self.run_entry(env={"FIXTURE_FAILURE": "stage"})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("staging failed", result.stderr)
        self.assertTrue((self.target / "AGENTS.md").is_file())
        self.assertEqual("", self.git("ls-files"))
        self.assertEqual(47, len([p for p in self.target.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.target).parts]))

    def test_target_symlink_collision_and_git_context(self):
        (self.target / ".agents").symlink_to(self.base / "outside")
        self.assert_refusal_unchanged()
        (self.target / ".agents").unlink()
        (self.target / "AGENTS.md").mkdir()
        self.assert_refusal_unchanged()
        (self.target / "AGENTS.md").rmdir()
        for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_CONFIG_PARAMETERS"):
            self.assert_refusal_unchanged(env={key: "untrusted"})

    def test_uncheckable_filter_inventory_refuses_before_copy(self):
        for failure in ("config-error", "config-truncated", "config-contradiction", "config-empty"):
            with self.subTest(failure=failure):
                self.assert_refusal_unchanged(env={"FIXTURE_FAILURE": failure})

    def test_explicit_local_pipe_and_saved_default_dry_run(self):
        for saved in (False, True):
            before = self.snapshot()
            result = self.run_entry(saved=saved, env={"SCAFFOLD_SOURCE_DIR": str(self.source)})
            self.assert_success(result)
            self.assertEqual(before, self.snapshot())
        self.assert_success(self.run_entry("--apply", env={"SCAFFOLD_SOURCE_DIR": str(self.source)}))
        self.assertEqual("", self.git("ls-files"))

    def test_system_bin_bash_when_available(self):
        if not Path("/bin/bash").exists(): self.skipTest("system Bash unavailable")
        self.assert_success(self.run_entry("--dry-run", bash="/bin/bash"))

    def test_owned_scratch_alias_old_failure_new_install_cleanup_and_refusals(self):
        old = product_checker().history_bytes(ROOT,
            commit="ab7789274aae99cb4fd8f781672bcb89c71d80ec", path=ENTRY)
        current = (ROOT / ENTRY).read_bytes()
        old_entry = self.base / "previous bootstrap.sh"
        old_entry.write_bytes(old)
        for nested in (False, True):
            with self.subTest(alias="ancestor" if nested else "direct"):
                tag = "ancestor" if nested else "direct"
                physical = self.base / ("physical scratch " + tag)
                physical.mkdir()
                alias = self.base / ("scratch alias " + tag)
                alias.symlink_to(physical, target_is_directory=True)
                # Real filesystem aliases model /tmp and /var/folders, without
                # altering OS links or teaching the transport a successful result.
                if nested:
                    (physical / "folders").mkdir()
                    scratch = alias / "folders"
                    scratch_physical = physical / "folders"
                else:
                    scratch = alias
                    scratch_physical = physical
                self.assertNotEqual(scratch, scratch.resolve())
                self.target = self.base / ("adopter " + tag)
                self.target.mkdir()
                self.command(self.target, "init", "-q", "-b", "main")
                env = dict(self.env, TMPDIR=str(scratch))
                before = self.snapshot()
                if (self.source / ENTRY).read_bytes() != old:
                    (self.source / ENTRY).write_bytes(old)
                    old_pin = self.commit(self.source)
                else:
                    old_pin = self.command(self.source, "rev-parse", "HEAD").strip()
                failed = subprocess.run([BASH, str(old_entry), "--dry-run"],
                                        cwd=self.target, env=dict(env, SCAFFOLD_REF=old_pin),
                                        capture_output=True, text=True, timeout=90)
                self.assertNotEqual(0, failed.returncode)
                self.assertIn("source root or ancestor is a symlink", failed.stderr)
                self.assertEqual(before, self.snapshot())
                self.assertEqual([], list(scratch_physical.iterdir()))
                if (self.source / ENTRY).read_bytes() != current:
                    (self.source / ENTRY).write_bytes(current)
                    pin = self.commit(self.source)
                else:
                    pin = old_pin
                self.assert_success(self.run_entry("--dry-run", ref=pin, env=env))
                self.assertEqual(before, self.snapshot())
                self.assertEqual([], list(scratch_physical.iterdir()))
                applied = self.run_entry(ref=pin, env=env)
                self.assert_success(applied)
                self.assertIn("47 newly installed files staged", applied.stdout)
                self.assertEqual(47, len(self.git("ls-files").splitlines()))
                installed = self.snapshot()
                self.assert_success(self.run_entry(ref=pin, env=env))
                self.assertEqual(installed, self.snapshot())
                self.assertEqual([], list(scratch_physical.iterdir()))
                self.assertTrue(alias.is_symlink())
                target_alias = self.base / ("adopter alias " + tag)
                target_alias.symlink_to(self.target, target_is_directory=True)
                self.assert_refusal_unchanged(str(target_alias), ref=pin, env=env)
                source_alias = self.base / ("source alias " + tag)
                source_alias.symlink_to(self.source, target_is_directory=True)
                self.assert_refusal_unchanged(env=dict(env, SCAFFOLD_SOURCE_DIR=str(source_alias)))
                self.assertEqual([], list(scratch_physical.iterdir()))

    def test_index_link_lock_and_copy_failure(self):
        outside = self.base / "outside-index"
        outside.write_text("preserve\n")
        index = self.target / ".git/index"
        index.symlink_to(outside)
        self.assert_refusal_unchanged()
        index.unlink()
        lock = self.target / ".git/index.lock"
        lock.write_text("owned by another writer\n")
        self.assert_refusal_unchanged()
        lock.unlink()
        cat = self.bin / "cat"
        cat.write_text("#!/bin/sh\ncase \"$1\" in */src/.github/distribution/payload/.agents/skills/context-distillation/SKILL.md) exit 43 ;; esac\nexec "
                       + shlex.quote(shutil.which("cat")) + " \"$@\"\n")
        cat.chmod(0o755)
        result = self.run_entry()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("review partial", result.stderr)
        self.assertTrue((self.target / ".agents/skills/context-collection/SKILL.md").is_file())
        self.assertEqual("", self.git("ls-files"))

    def test_local_engine_and_payload_match_approved_product_export(self):
        self.assertEqual([], product_checker().validate_export(ROOT))

    def test_initial_empty_http_failure_requires_caller_pipefail(self):
        curl = self.bin / "curl"
        curl.write_text("#!/bin/sh\nexit 22\n")
        line = next(line for line in (ROOT / "README.md").read_text().splitlines()
                    if line.startswith("curl -fsSL ") and line.endswith(" | bash"))
        before = self.snapshot()
        plain = subprocess.run([BASH, "-c", line], cwd=self.target, env=self.env)
        strict = subprocess.run([BASH, "-o", "pipefail", "-c", line], cwd=self.target, env=self.env)
        self.assertEqual(0, plain.returncode)
        self.assertEqual(22, strict.returncode)
        self.assertEqual(before, self.snapshot())

    def test_powershell_pipeline_arguments_and_failure_host_synthetic(self):
        pwsh = shutil.which("pwsh")
        if not pwsh: self.skipTest("PowerShell host unavailable; native Windows unmeasured")
        # HTTP responses derive from actual requested URL/ref and real Git blobs.
        script = r'''
$ErrorActionPreference = 'Stop'
function Get-Command { [pscustomobject]@{Source=$env:FIXTURE_BASH} }
function Read-FixtureUrl([string]$Uri) {
    $prefix = 'https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/'
    if (-not $Uri.StartsWith($prefix)) { throw 'unexpected fixture URL' }
    $rest = $Uri.Substring($prefix.Length)
    if ($rest -notmatch '^(.*)/(\.github/scripts/scaffold-init\.(?:sh|ps1))$') { throw 'unexpected fixture path' }
    $ref = [Uri]::UnescapeDataString($Matches[1])
    $path = $Matches[2]
    $lines = & $env:REAL_GIT -C $env:FIXTURE_SOURCE show ($ref + ':' + $path)
    if ($LASTEXITCODE -ne 0) { throw 'fixture source missing' }
    return (($lines -join [char]10) + [char]10)
}
function Invoke-RestMethod { param([string]$Uri) Read-FixtureUrl $Uri }
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,[string]$Uri,[string]$OutFile)
    [IO.File]::WriteAllText($OutFile, (Read-FixtureUrl $Uri), [Text.UTF8Encoding]::new($false))
}
'''
        line = next(line for line in (ROOT / "README.md").read_text().splitlines()
                    if line.startswith("irm ") and line.endswith(" | iex"))
        env = dict(self.env, FIXTURE_BASH=BASH, SCAFFOLD_REF=self.pin)
        runner = self.base / "powershell boundary.ps1"
        runner.write_text(script + line + "\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n")
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                env=env, capture_output=True, text=True, timeout=90)
        self.assert_success(result)
        before = self.snapshot()
        block = "& ([scriptblock]::Create((irm '" + line.split()[1] + "'))) --dry-run '" + str(self.target) + "'"
        runner.write_text(script + block + "\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n")
        self.assert_success(subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.base,
                            env=env, capture_output=True, text=True, timeout=90))
        self.assertEqual(before, self.snapshot())
        runner.write_text(script + "try { " + block.replace("--dry-run", "--unknown") + " } catch { Write-Output 'EXPECTED-ERROR' }\nWrite-Output 'CALLER-ALIVE'\n")
        failed = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.base,
                                env=env, capture_output=True, text=True, timeout=90)
        self.assertIn("CALLER-ALIVE", failed.stdout)
        self.assertIn("EXPECTED-ERROR", failed.stdout)
        self.assertEqual(before, self.snapshot())
        for fault in ("function Invoke-WebRequest { throw 'HTTP-FAILURE' }\n",
                      "function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing) throw 'HTTP-FAILURE' }\n"):
            runner.write_text(script + fault + line)
            result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, self.snapshot())
        no_status = self.base / "no status.ps1"
        no_status.write_text("Write-Output 'NO-NATIVE-STATUS'\n")
        runner.write_text(script + line)
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(runner)], cwd=self.target,
                                env=dict(env, FIXTURE_BASH=str(no_status)), capture_output=True,
                                text=True, timeout=20)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("returned no exit status", result.stderr)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
