"""Offline maintainer-map CLI regressions using disposable payload copies."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-maintainer-map.py"
DISTRIBUTION = Path(".github/distribution")
MAP = DISTRIBUTION / "maintainer-map.v1.json"
INVENTORY = DISTRIBUTION / "payload.v1.tsv"
PAYLOAD = DISTRIBUTION / "payload"
SKILL = ".agents/skills/plan-management/SKILL.md"


class MaintainerMapTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="maintainer-map-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copytree(ROOT / PAYLOAD, root / PAYLOAD)
        for path in (MAP, INVENTORY):
            shutil.copyfile(ROOT / path, root / path)
        return root

    def check(self, root=ROOT, *args):
        return subprocess.run([sys.executable, "-I", str(CHECKER), "--root", str(root), *args],
                              capture_output=True, text=True, timeout=15)

    def alter_map(self, root, edit):
        record = json.loads((root / MAP).read_text())
        edit(record)
        (root / MAP).write_text(json.dumps(record))

    def assert_failure(self, result, *messages):
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        for message in messages:
            self.assertIn(message, result.stdout)

    def test_current_payload_resolves_and_reports_counts(self):
        result = self.check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("47 entries; 260 references checked in 44 text files", result.stdout)
        self.assertIn("238 resolved, 22 allowlisted", result.stdout)

    def test_missing_entry_fails(self):
        root = self.fixture()
        self.alter_map(root, lambda record: record["files"].pop())
        self.assert_failure(self.check(root), str(MAP), "installed_path set differs", "missing=")

    def test_extra_duplicate_and_redirected_entries_fail(self):
        edits = (
            (lambda r: r["files"].append({"installed_path": "extra.md",
                                         "payload_path": str(PAYLOAD / "extra.md")}), "extra="),
            (lambda r: r["files"].append(r["files"][0]), "duplicate installed_path"),
            (lambda r: r["files"][0].update(payload_path="AGENTS.md"), "payload_path must be"),
        )
        for edit, message in edits:
            with self.subTest(message=message):
                root = self.fixture()
                self.alter_map(root, edit)
                self.assert_failure(self.check(root), str(MAP), message)

    def test_changed_inventory_requires_regeneration_even_with_same_destinations(self):
        root = self.fixture()
        with (root / INVENTORY).open("a") as stream:
            stream.write("# Changed inventory metadata\n")
        self.assert_failure(self.check(root), "stale", "--write")
        self.assertEqual(0, self.check(root, "--write").returncode)

    def test_regeneration_uses_only_inventory_and_is_deterministic(self):
        root = self.fixture()
        expected = (root / MAP).read_bytes()
        (root / MAP).unlink()
        result = self.check(root, "--write")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(expected, (root / MAP).read_bytes())
        self.assertEqual(0, self.check(root, "--write").returncode)
        self.assertEqual(expected, (root / MAP).read_bytes())

    def test_missing_payload_file_fails(self):
        root = self.fixture()
        missing = ".github/scripts/ownership-overlap.sh"
        (root / PAYLOAD / missing).unlink()
        self.assert_failure(self.check(root), missing, "not a regular file")

    def test_malformed_map_fails_cleanly(self):
        for content in ('{"schema":', '{"schema": "a", "schema": "b"}',
                        '[]', '{"schema": "maintainer-map/v1", "files": [null]}'):
            with self.subTest(content=content):
                root = self.fixture()
                (root / MAP).write_text(content)
                self.assert_failure(self.check(root), "ERROR:", str(MAP))

    def test_required_namespaces_fail_in_every_scanned_suffix(self):
        for suffix, reference in (
            (".md", ".github/scripts/missing.sh"),
            (".sh", ".github/codex-instructions.md.missing"),
            (".toml", ".agents/skills/missing/SKILL.md"),
            (".yml", ".codex/agents/missing.toml"),
        ):
            with self.subTest(reference=reference):
                root = self.fixture()
                probe = root / PAYLOAD / (".github/probe" + suffix)
                probe.write_text(f"Reference: `{reference}`\n")
                self.assert_failure(self.check(root), str(probe.relative_to(root)) + ":1:",
                                    reference, "no mapped file")

    def test_relative_skill_resources_and_links_fail_when_unmapped(self):
        for reference in ("templates/missing.md", "[missing](../missing/SKILL.md#section)"):
            with self.subTest(reference=reference):
                root = self.fixture()
                (root / PAYLOAD / SKILL).write_text(reference + "\n")
                self.assert_failure(self.check(root), SKILL + ":1:", "missing", "no mapped file")

    def test_directories_globs_braces_relative_links_and_fragments_resolve(self):
        root = self.fixture()
        (root / PAYLOAD / SKILL).write_text("\n".join((
            ".agents/skills/verification",
            ".agents/skills/*/SKILL.md",
            ".github/docs/**",
            ".codex/agents/{planner,reviewer}.toml",
            "[peer](../verification/SKILL.md#ground-truth)",
            "[root](../../../.github/codex-instructions.md)",
            "`templates/task-body.md`",
        )))
        result = self.check(root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_partial_braces_empty_globs_traversal_and_unknown_substitutions_fail(self):
        for reference in (".codex/agents/{planner,absent}.toml", ".agents/skills/absent*/SKILL.md",
                          ".agents/skills/plan-management/../verification/SKILL.md",
                          ".github/scripts/$HELPER", ".agents/skills/${NAME}/SKILL.md"):
            with self.subTest(reference=reference):
                root = self.fixture()
                (root / PAYLOAD / SKILL).write_text(reference + "\n")
                self.assert_failure(self.check(root), SKILL + ":1:", reference)

    def test_allowlist_is_scoped_to_exact_source_and_reference(self):
        for source, reference in (
            (SKILL, ".github/docs/context/<topic>/"),
            (".agents/skills/context-collection/SKILL.md", ".github/docs/context/<other>/"),
        ):
            with self.subTest(source=source, reference=reference):
                root = self.fixture()
                (root / PAYLOAD / source).write_text(reference + "\n")
                self.assert_failure(self.check(root), source + ":1:", reference)

    def test_relative_links_cannot_resolve_only_their_namespace_suffix(self):
        for reference in ("../../.github/codex-instructions.md",
                          "../../../../.agents/skills/verification/SKILL.md"):
            with self.subTest(reference=reference):
                root = self.fixture()
                (root / PAYLOAD / SKILL).write_text(f"[wrong]({reference})\n")
                self.assert_failure(self.check(root), SKILL + ":1:", reference)

    def test_unknown_backslash_suffix_is_not_truncated_to_an_existing_file(self):
        for reference in (r".github/scripts/check-task-ritual.sh\not-a-file",
                          r"templates/task-body.md\not-a-file"):
            with self.subTest(reference=reference):
                root = self.fixture()
                (root / PAYLOAD / SKILL).write_text(reference + "\n")
                self.assert_failure(self.check(root), SKILL + ":1:", "not-a-file")


if __name__ == "__main__":
    unittest.main()
