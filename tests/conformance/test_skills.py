import copy
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-skills.py"
PARITY = "docs/agreements/skill-parity.v1.json"
SOURCE = "tests/skills/fixtures/source-manifest.v1.json"
LEDGER = ".github/governance/ledger-contracts.v1.json"
EPIC_FORM = ".github/ISSUE_TEMPLATE/epic.yml"
TASK_FORM = ".github/ISSUE_TEMPLATE/ai-task.yml"


class SkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("skill_checker", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot import Skill checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "repository"
        paths = set(self.checker.EXPECTED_FILES) | {
            PARITY,
            SOURCE,
            LEDGER,
            EPIC_FORM,
            TASK_FORM,
        }
        for relative in sorted(paths):
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"fixture source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return fixture

    def read_json(self, root, relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def write_json(self, root, relative, payload):
        (root / relative).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def replace(self, root, relative, old, new):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"mutation anchor missing in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def append(self, root, relative, text):
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def errors_for(self, root):
        return self.checker.validate_repository(root)

    def assert_rejected(self, errors, token=None):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid Skill fixture unexpectedly passed")
        if token is not None:
            self.assertIn(token, rendered)

    def test_live_repository_and_cli_pass(self):
        self.assertEqual([], self.errors_for(ROOT))
        completed = subprocess.run(
            ["python3", "-I", str(CHECKER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("PASS (8 Skills, 12 frozen source artifacts)", completed.stdout)

    def test_exact_inventory_and_progressive_disclosure_are_bounded(self):
        self.assertEqual(19, len(self.checker.EXPECTED_FILES))
        self.assertEqual(
            {
                "plan-management": "references/issue-graph-procedure.md",
                "project-onboarding": "references/onboarding-procedure.md",
                "session-orchestration": "references/orchestration-protocols.md",
            },
            self.checker.REFERENCE_FILES,
        )

    def test_project_onboarding_load_bearing_contracts_are_required(self):
        expected = {
            "ONBOARD-REMOTE-DEFAULT-GATE": (
                "Do not perform any GitHub write, including labels, Ruleset changes, "
                "or Epic creation, until the kit baseline is reachable from the remote "
                "default branch."
            ),
            "ONBOARD-COMMAND-EVIDENCE": (
                "For every candidate command, record the exact command, environment "
                "prerequisites, runtime, and result from a clean checkout."
            ),
            "ONBOARD-NO-UNRUN-PROMOTION": (
                "Never promote an unrun command."
            ),
            "ONBOARD-EVIDENCE-PR-BOUNDARY": (
                "Onboarding is not complete until an evidence PR exists or an exact "
                "blocked-PR receipt and creation command are durably recorded."
            ),
            "ONBOARD-DEFERRED-LEDGER": (
                "Write every unfinished or unverified item to a durable "
                "`## Deferred from onboarding` ledger in the first active Epic or "
                "evidence PR."
            ),
            "ONBOARD-CHAT-NOT-CARRIER": (
                "Chat is not a carrier for deferred work."
            ),
            "ONBOARD-DURABLE-HANDOFF": (
                "Replace the source Project-session step with a Codex-native durable "
                "handoff to the first approved Epic/Task frontier."
            ),
        }
        self.assertEqual(expected, self.checker.ONBOARDING_CONTRACTS)
        paths = (
            ".agents/skills/project-onboarding/SKILL.md",
            ".agents/skills/project-onboarding/references/onboarding-procedure.md",
        )
        self.assertEqual(paths, self.checker.ONBOARDING_CONTRACT_PATHS)

        complete = {relative: "\n".join(expected.values()) + "\n" for relative in paths}
        for relative in paths:
            visible = " ".join(
                line.strip()
                for line in self.checker._visible_markdown_lines(
                    (ROOT / relative).read_text(encoding="utf-8")
                )
                if line.strip()
            )
            for marker in expected.values():
                self.assertIn(marker, visible)

        errors = []
        self.checker.validate_onboarding_contracts(complete, errors)
        self.assertEqual([], errors)

        for contract_id, marker in expected.items():
            for relative in paths:
                with self.subTest(contract_id=contract_id, relative=relative):
                    mutated = dict(complete)
                    mutated[relative] = mutated[relative].replace(marker, "", 1)
                    errors = []
                    self.checker.validate_onboarding_contracts(mutated, errors)
                    self.assert_rejected(errors, f"{contract_id} in {relative}")

        for label, hidden in (
            ("comment", "<!-- {marker} -->\n"),
            ("fence", "```text\n{marker}\n```\n"),
        ):
            with self.subTest(hidden=label):
                contract_id, marker = next(iter(expected.items()))
                relative = paths[0]
                mutated = dict(complete)
                mutated[relative] = mutated[relative].replace(marker, "", 1)
                mutated[relative] += hidden.format(marker=marker)
                errors = []
                self.checker.validate_onboarding_contracts(mutated, errors)
                self.assert_rejected(errors, f"{contract_id} in {relative}")

    def test_missing_and_extra_skill_roots_are_rejected(self):
        fixture = self.copy_fixture()
        shutil.rmtree(fixture / ".agents/skills/retro")
        self.assert_rejected(self.errors_for(fixture), "Skill roots must be exactly")

        fixture = self.copy_fixture()
        extra = fixture / ".agents/skills/extra-skill"
        (extra / "agents").mkdir(parents=True)
        (extra / "SKILL.md").write_text("---\nname: extra\ndescription: extra\n---\n", encoding="utf-8")
        (extra / "agents/openai.yaml").write_text("fixture\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "Skill roots must be exactly")

    def test_frontmatter_missing_malformed_duplicate_and_unsupported_are_rejected(self):
        cases = (
            ("missing", "name: context-collection\n", "", "frontmatter"),
            ("malformed", "name: context-collection\n", "name context-collection\n", "malformed frontmatter"),
            ("duplicate", "name: context-collection\n", "name: context-collection\nname: context-collection\n", "duplicate frontmatter"),
            ("unsupported", "description:", "owner: repository\ndescription:", "keys must be exactly"),
        )
        relative = ".agents/skills/context-collection/SKILL.md"
        for label, old, new, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                self.replace(fixture, relative, old, new)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_name_mismatch_duplicate_name_and_ambiguous_description_are_rejected(self):
        relative = ".agents/skills/context-collection/SKILL.md"
        fixture = self.copy_fixture()
        self.replace(fixture, relative, "name: context-collection", "name: wrong-name")
        self.assert_rejected(self.errors_for(fixture), "must equal directory name")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "name: context-collection", "name: context-distillation")
        self.assert_rejected(self.errors_for(fixture), "must be present and unique")

        fixture = self.copy_fixture()
        description = self.checker.DESCRIPTIONS["context-collection"]
        self.replace(
            fixture,
            relative,
            f"description: {description}",
            "description: Use for anything and every task.",
        )
        self.assert_rejected(self.errors_for(fixture), "reviewed discriminating boundary")

    def test_required_skill_sections_are_present_once_and_ordered(self):
        relative = ".agents/skills/verification/SKILL.md"
        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "## Input")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.append(fixture, relative, "\n## Verification\nDuplicate.\n")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "### Inputs")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "```markdown\n## Inputs\n```")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "<!--\n## Inputs\n-->")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "<!-- hidden -->## Inputs")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "<!-- hidden\n-->## Inputs")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "paragraph <!-- hidden\n-->## Inputs")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "<pre>\n## Inputs\n</pre>\n")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

        fixture = self.copy_fixture()
        self.replace(fixture, relative, "## Inputs", "~~~ lang`x\n## Inputs\n~~~\n")
        self.assert_rejected(self.errors_for(fixture), "must contain heading exactly once")

    def test_openai_metadata_shape_prompt_and_policy_are_fail_closed(self):
        relative = ".agents/skills/context-collection/agents/openai.yaml"
        cases = (
            ("missing-policy", "policy:\n  allow_implicit_invocation: false\n", "", "exact closed"),
            ("extra-policy", "  allow_implicit_invocation: false\n", "  allow_implicit_invocation: false\n  extra: true\n", "exact closed"),
            ("wrong-policy", "allow_implicit_invocation: false", "allow_implicit_invocation: true", "must be false"),
            ("bad-prompt", "Use $context-collection ", "Collect with context-collection ", "must begin"),
            ("unquoted", 'display_name: "Context Collection"', "display_name: Context Collection", "exact closed"),
        )
        for label, old, new, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                self.replace(fixture, relative, old, new)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_only_verification_allows_implicit_invocation(self):
        for skill in self.checker.REQUIRED_SKILLS:
            relative = f".agents/skills/{skill}/agents/openai.yaml"
            text = (ROOT / relative).read_text(encoding="utf-8")
            expected = "true" if skill == "verification" else "false"
            self.assertIn(f"allow_implicit_invocation: {expected}", text)

    def test_openai_metadata_values_are_unique_trimmed_and_bounded(self):
        relative = ".agents/skills/context-collection/agents/openai.yaml"
        cases = (
            (
                "duplicate-display-name",
                'display_name: "Context Collection"',
                'display_name: "Context Distillation"',
                "display names must be present and unique",
            ),
            (
                "leading-whitespace",
                'short_description: "Collect bounded source context with provenance"',
                'short_description: " Collect bounded source context with provenance"',
                "short_description must be trimmed",
            ),
            (
                "too-long",
                'short_description: "Collect bounded source context with provenance"',
                f'short_description: "{"x" * 65}"',
                "25 through 64 characters",
            ),
            (
                "casefold-duplicate",
                'display_name: "Context Collection"',
                'display_name: "context distillation"',
                "unique by NFC casefold",
            ),
            (
                "embedded-newline",
                'display_name: "Context Collection"',
                'display_name: "Context\\nCollection"',
                "control-free",
            ),
            (
                "nel",
                'display_name: "Context Collection"',
                'display_name: "Context\\u0085Collection"',
                "control-free",
            ),
            (
                "bidi",
                'display_name: "Context Collection"',
                'display_name: "Context\\u202eCollection"',
                "control-free",
            ),
        )
        for label, old, new, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                self.replace(fixture, relative, old, new)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_dangling_or_unexpected_scripts_references_and_assets_are_rejected(self):
        targets = ("scripts/run.sh", "references/missing.md", "assets/icon.png")
        relative = ".agents/skills/context-collection/SKILL.md"
        for target in targets:
            with self.subTest(target=target):
                fixture = self.copy_fixture()
                self.append(fixture, relative, f"\n[unexpected resource]({target})\n")
                self.assert_rejected(self.errors_for(fixture), "dangling")

    def test_unsafe_markdown_resource_forms_are_rejected(self):
        relative = ".agents/skills/plan-management/SKILL.md"
        original = "references/issue-graph-procedure.md"
        cases = (
            "/tmp/private.md",
            "references\\issue-graph-procedure.md",
            "references/%69ssue-graph-procedure.md",
            "file:///tmp/private.md",
            "../project-onboarding/SKILL.md",
        )
        for target in cases:
            with self.subTest(target=target):
                fixture = self.copy_fixture()
                self.replace(fixture, relative, original, target)
                self.assert_rejected(self.errors_for(fixture), "resource")

    def test_markdown_resource_fragment_must_resolve(self):
        fixture = self.copy_fixture()
        relative = ".agents/skills/plan-management/SKILL.md"
        self.replace(
            fixture,
            relative,
            "references/issue-graph-procedure.md",
            "references/issue-graph-procedure.md#missing-fragment",
        )
        self.assert_rejected(self.errors_for(fixture), "unresolved Markdown fragment")

        fixture = self.copy_fixture()
        relative = ".agents/skills/context-collection/SKILL.md"
        self.append(fixture, relative, "\n[missing local section](#missing-fragment)\n")
        self.assert_rejected(self.errors_for(fixture), "unresolved Markdown fragment")

        for hidden in (
            "<pre>\n## Hidden Anchor\n</pre>\n",
            "~~~ lang`x\n## Hidden Anchor\n~~~\n",
            "<!-- hidden -->## Hidden Anchor\n",
            "<!-- hidden\n-->## Hidden Anchor\n",
            "paragraph <!-- hidden\n-->## Hidden Anchor\n",
        ):
            with self.subTest(hidden=hidden.splitlines()[0]):
                fixture = self.copy_fixture()
                skill = ".agents/skills/plan-management/SKILL.md"
                reference = ".agents/skills/plan-management/references/issue-graph-procedure.md"
                self.append(fixture, reference, "\n" + hidden)
                self.replace(
                    fixture,
                    skill,
                    "references/issue-graph-procedure.md",
                    "references/issue-graph-procedure.md#hidden-anchor",
                )
                self.assert_rejected(self.errors_for(fixture), "unresolved Markdown fragment")

    def test_noncanonical_markdown_resource_paths_are_rejected_before_resolution(self):
        relative = ".agents/skills/plan-management/SKILL.md"
        original = "references/issue-graph-procedure.md"
        for target in (
            "references/./issue-graph-procedure.md",
            "references//issue-graph-procedure.md",
            "references/x/../issue-graph-procedure.md",
        ):
            with self.subTest(target=target):
                fixture = self.copy_fixture()
                self.replace(fixture, relative, original, target)
                self.assert_rejected(self.errors_for(fixture), "noncanonical Markdown resource")

    def test_unreferenced_progressive_resource_is_rejected(self):
        fixture = self.copy_fixture()
        relative = ".agents/skills/plan-management/SKILL.md"
        self.replace(
            fixture,
            relative,
            "[Issue graph procedure](references/issue-graph-procedure.md)",
            "Issue graph procedure",
        )
        self.assert_rejected(self.errors_for(fixture), "must link its progressive-disclosure resource")

    def test_case_and_nfc_collisions_are_rejected(self):
        errors = self.checker._collision_errors(
            [".agents/skills/Example/SKILL.md", ".agents/skills/example/SKILL.md"]
        )
        self.assert_rejected(errors, "collision")
        errors = self.checker._collision_errors(
            [".agents/skills/cafe\u0301/SKILL.md"]
        )
        self.assert_rejected(errors, "not NFC-normalized")

    def test_repository_relative_paths_must_be_canonical(self):
        for relative in (
            "a//b",
            "a/./b",
            "a/\x01b",
            "a/\u0085b",
            "a/\u202eb",
            "a/\ud800b",
            "cafe\u0301/file",
        ):
            with self.subTest(relative=repr(relative)):
                self.assertFalse(self.checker._valid_relative_path(relative))

    def test_symlinked_skill_root_and_reference_are_rejected(self):
        fixture = self.copy_fixture()
        root = fixture / ".agents/skills/context-collection"
        shutil.rmtree(root)
        os.symlink("context-distillation", root)
        self.assert_rejected(self.errors_for(fixture), "not a directory")

        fixture = self.copy_fixture()
        reference = fixture / ".agents/skills/plan-management/references/issue-graph-procedure.md"
        reference.unlink()
        os.symlink("../../../project-onboarding/SKILL.md", reference)
        self.assert_rejected(self.errors_for(fixture), "not regular")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_skill_root_and_reference_are_rejected_without_blocking(self):
        fixture = self.copy_fixture()
        root = fixture / ".agents/skills/retro"
        shutil.rmtree(root)
        os.mkfifo(root)
        self.assert_rejected(self.errors_for(fixture), "not a directory")

        fixture = self.copy_fixture()
        reference = fixture / ".agents/skills/session-orchestration/references/orchestration-protocols.md"
        reference.unlink()
        os.mkfifo(reference)
        self.assert_rejected(self.errors_for(fixture), "not regular")

    def test_oversized_and_executable_skill_inputs_are_rejected(self):
        fixture = self.copy_fixture()
        relative = ".agents/skills/retro/SKILL.md"
        (fixture / relative).write_text("x" * (self.checker.MAX_FILE_BYTES + 1), encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "exceeds")

        fixture = self.copy_fixture()
        path = fixture / relative
        path.chmod(0o755)
        self.assert_rejected(self.errors_for(fixture), "must not be executable")

    def test_reader_rejects_invalid_utf8_and_nul(self):
        for label, payload, token in (
            ("utf8", b"\xff", "not UTF-8"),
            ("nul", b"safe\x00unsafe", "contains NUL"),
        ):
            with self.subTest(label=label):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name) / "repository"
                target = root / "governed/input.txt"
                target.parent.mkdir(parents=True)
                target.write_bytes(payload)
                errors = []
                self.assertIsNone(
                    self.checker.read_regular_file(root, "governed/input.txt", errors)
                )
                self.assert_rejected(errors, token)

    def test_safe_filesystem_capabilities_and_root_binding_fail_closed(self):
        fixture = self.copy_fixture()
        for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"):
            with self.subTest(flag=flag):
                errors = []
                with mock.patch.object(self.checker.os, flag, 0):
                    self.assertIsNone(
                        self.checker.enumerate_directory(fixture, ".agents/skills", errors)
                    )
                self.assert_rejected(errors, f"capability is unavailable: {flag}")

        for attribute in ("supports_dir_fd", "supports_follow_symlinks"):
            with self.subTest(attribute=attribute):
                errors = []
                with mock.patch.object(self.checker.os, attribute, set()):
                    self.assertIsNone(
                        self.checker.enumerate_directory(fixture, ".agents/skills", errors)
                    )
                self.assert_rejected(errors, "safe filesystem capability is unavailable")

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        container = Path(temporary.name)
        actual = container / "actual"
        (actual / "governed").mkdir(parents=True)
        linked = container / "repository"
        os.symlink(actual.name, linked)
        errors = []
        self.assertIsNone(self.checker.enumerate_directory(linked, "governed", errors))
        self.assert_rejected(errors, "repository root is a symlink")

    def test_root_parent_and_named_file_replacement_are_rejected(self):
        for kind in ("root", "parent", "file"):
            with self.subTest(kind=kind):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name) / "repository"
                parent = root / "governed"
                parent.mkdir(parents=True)
                target = parent / "input.txt"
                target.write_text("original\n", encoding="utf-8")
                original_read = self.checker.os.read
                changed = False

                def swapping_read(file_descriptor, size):
                    nonlocal changed
                    payload = original_read(file_descriptor, size)
                    if payload and not changed:
                        changed = True
                        if kind == "root":
                            root.rename(Path(temporary.name) / "old-repository")
                            parent.mkdir(parents=True)
                            target.write_text("replacement\n", encoding="utf-8")
                        elif kind == "parent":
                            parent.rename(root / "old-governed")
                            parent.mkdir()
                            target.write_text("replacement\n", encoding="utf-8")
                        else:
                            target.rename(parent / "old-input.txt")
                            target.write_text("replacement\n", encoding="utf-8")
                    return payload

                errors = []
                with mock.patch.object(self.checker.os, "read", side_effect=swapping_read):
                    self.assertIsNone(
                        self.checker.read_regular_file(root, "governed/input.txt", errors)
                    )
                token = "namespace binding changed" if kind in {"root", "parent"} else "file binding changed"
                self.assert_rejected(errors, token)

    def test_fixed_json_and_openai_inputs_reject_symlink_fifo_and_oversize(self):
        fixed_inputs = (
            PARITY,
            SOURCE,
            ".agents/skills/context-collection/agents/openai.yaml",
        )
        for relative in fixed_inputs:
            with self.subTest(relative=relative, kind="symlink"):
                fixture = self.copy_fixture()
                path = fixture / relative
                saved = path.with_name(path.name + ".saved")
                path.rename(saved)
                os.symlink(saved.name, path)
                self.assert_rejected(self.errors_for(fixture), "not a regular file")

            if hasattr(os, "mkfifo"):
                with self.subTest(relative=relative, kind="fifo"):
                    fixture = self.copy_fixture()
                    path = fixture / relative
                    path.unlink()
                    os.mkfifo(path)
                    self.assert_rejected(self.errors_for(fixture), "not a regular file")

            with self.subTest(relative=relative, kind="oversize"):
                fixture = self.copy_fixture()
                path = fixture / relative
                path.write_bytes(b"x" * (self.checker.MAX_FILE_BYTES + 1))
                self.assert_rejected(self.errors_for(fixture), "exceeds")

    def test_directory_enumeration_is_bounded_before_name_filtering(self):
        fixture = self.copy_fixture()
        skill_root = fixture / ".agents/skills/retro"
        for index in range(self.checker.MAX_DIRECTORY_ENTRIES + 1):
            (skill_root / f"invalid-{index:03d}.tmp").write_text("x\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "exceeds")

    def test_directory_namespace_swap_during_enumeration_is_rejected(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        target = root / "swap/target"
        target.mkdir(parents=True)
        (target / "entry").write_text("x\n", encoding="utf-8")
        original_scandir = self.checker.os.scandir
        old_target = root / "swap/old-target"

        class SwappingIterator:
            def __init__(self, inner):
                self.inner = inner

            def __enter__(self):
                self.inner.__enter__()
                return self

            def __next__(self):
                return next(self.inner)

            def __exit__(self, exc_type, exc, traceback):
                result = self.inner.__exit__(exc_type, exc, traceback)
                target.rename(old_target)
                target.mkdir()
                (target / "entry").write_text("replacement\n", encoding="utf-8")
                return result

        def swapping_scandir(file_descriptor):
            return SwappingIterator(original_scandir(file_descriptor))

        errors = []
        with mock.patch.object(self.checker.os, "scandir", side_effect=swapping_scandir):
            self.checker.enumerate_directory(root, "swap/target", errors)
        self.assert_rejected(errors, "namespace binding changed")

    def test_frozen_source_repository_commit_tree_and_artifact_metadata_are_exact(self):
        cases = (
            ("repository", lambda value: value["source"].__setitem__("repository", "other/repo"), "source repository"),
            ("commit", lambda value: value["source"].__setitem__("commit", "0" * 40), "source repository"),
            ("tree", lambda value: value["source"].__setitem__("tree", "f" * 40), "source repository"),
            ("path", lambda value: value["artifacts"][0].__setitem__("path", ".github/skills/wrong/SKILL.md"), "unexpected frozen"),
            ("blob", lambda value: value["artifacts"][0].__setitem__("blob", "0" * 40), "metadata drifted"),
            ("sha", lambda value: value["artifacts"][0].__setitem__("sha256", "0" * 64), "metadata drifted"),
        )
        for label, mutation, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, SOURCE)
                mutation(payload)
                self.write_json(fixture, SOURCE, payload)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_frozen_source_artifact_omission_and_duplication_are_rejected(self):
        fixture = self.copy_fixture()
        payload = self.read_json(fixture, SOURCE)
        payload["artifacts"].pop()
        self.write_json(fixture, SOURCE, payload)
        self.assert_rejected(self.errors_for(fixture), "exactly 12")

        fixture = self.copy_fixture()
        payload = self.read_json(fixture, SOURCE)
        payload["artifacts"].append(copy.deepcopy(payload["artifacts"][-1]))
        self.write_json(fixture, SOURCE, payload)
        self.assert_rejected(self.errors_for(fixture), "exactly 12")

    def test_frozen_source_target_and_evidence_dispositions_are_exact(self):
        fixture = self.copy_fixture()
        payload = self.read_json(fixture, SOURCE)
        payload["artifacts"][0]["target_paths"] = ["README.md"]
        self.write_json(fixture, SOURCE, payload)
        self.assert_rejected(self.errors_for(fixture), "target disposition drifted")

        fixture = self.copy_fixture()
        payload = self.read_json(fixture, SOURCE)
        payload["artifacts"][0]["evidence_path"] = "README.md"
        self.write_json(fixture, SOURCE, payload)
        self.assert_rejected(self.errors_for(fixture), "evidence disposition drifted")

    def test_frozen_source_disposition_files_must_be_readable(self):
        fixture = self.copy_fixture()
        (fixture / EPIC_FORM).unlink()
        self.assert_rejected(self.errors_for(fixture), "target is not readable")

        fixture = self.copy_fixture()
        (fixture / LEDGER).unlink()
        self.assert_rejected(self.errors_for(fixture), "evidence is not readable")

    def test_parity_row_category_anchor_and_target_digest_are_exact(self):
        cases = (
            ("row", lambda value: value["skills"].pop(), "exactly eight rows"),
            ("category", lambda value: value["skills"][0].pop("chronology"), "keys must be exactly"),
            ("anchor", lambda value: value["skills"][0]["adaptations"][0].__setitem__("source_anchor", ".github/skills/retro/SKILL.md"), "not in this Skill"),
            ("digest", lambda value: value["skills"][0]["target_files"][0].__setitem__("sha256", "0" * 64), "target Skill digest drifted"),
            ("unclassified", lambda value: value["skills"][2].__setitem__("adaptations", []), "adaptations must"),
        )
        for label, mutation, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, PARITY)
                mutation(payload)
                self.write_json(fixture, PARITY, payload)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_parity_source_artifact_blob_omission_and_duplication_are_rejected(self):
        cases = (
            (
                "path",
                lambda value: value["skills"][0]["source_artifacts"][0].__setitem__(
                    "path", ".github/skills/wrong/SKILL.md"
                ),
            ),
            (
                "blob",
                lambda value: value["skills"][0]["source_artifacts"][0].__setitem__("blob", "0" * 40),
            ),
            ("omission", lambda value: value["skills"][0]["source_artifacts"].pop()),
            (
                "duplication",
                lambda value: value["skills"][0]["source_artifacts"].append(
                    copy.deepcopy(value["skills"][0]["source_artifacts"][0])
                ),
            ),
        )
        for label, mutation in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, PARITY)
                mutation(payload)
                self.write_json(fixture, PARITY, payload)
                self.assert_rejected(self.errors_for(fixture), "source_artifacts path/blob bindings drifted")

    def test_source_anchor_fragment_and_range_must_resolve(self):
        for anchor, token in (
            (".github/skills/project-onboarding/SKILL.md#overview", "unresolved frozen-source fragment"),
            (".github/skills/project-onboarding/SKILL.md#L1-L999", "outside the frozen source"),
        ):
            with self.subTest(anchor=anchor):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, PARITY)
                payload["skills"][0]["adaptations"][0]["source_anchor"] = anchor
                self.write_json(fixture, PARITY, payload)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_reviewed_parity_digest_binds_semantic_prose(self):
        fixture = self.copy_fixture()
        payload = self.read_json(fixture, PARITY)
        payload["skills"][0]["inputs"][0] = "arbitrary structurally valid semantic reversal"
        self.write_json(fixture, PARITY, payload)
        self.assert_rejected(self.errors_for(fixture), "reviewed skill parity digest drifted")

    def test_unapproved_semantic_change_classification_is_rejected(self):
        fixture = self.copy_fixture()
        payload = self.read_json(fixture, PARITY)
        payload["skills"][0]["adaptations"][0]["classification"] = "approved-deviation"
        self.write_json(fixture, PARITY, payload)
        self.assert_rejected(self.errors_for(fixture), "not authorized")

    def test_false_capability_and_completion_claims_are_rejected(self):
        claims = (
            "K10 is implemented.",
            "K11 is supported.",
            "Custom agents are implemented.",
            "Hooks are enforced.",
            "Execution envelope is available.",
            "Loop events are implemented.",
            "Runtime adapter is supported.",
            "Installer is implemented.",
            "Live Task ritual is enforced.",
            "Live runtime routing is supported.",
            "Cross-surface support is guaranteed.",
            "The repository is complete.",
        )
        relative = ".agents/skills/verification/SKILL.md"
        for claim in claims:
            with self.subTest(claim=claim):
                fixture = self.copy_fixture()
                self.append(fixture, relative, f"\n{claim}\n")
                self.assert_rejected(self.errors_for(fixture), "unsupported affirmative")

    def test_release_results_completion_and_scenario_success_are_rejected(self):
        cases = (
            ("release", lambda value: value.__setitem__("release_blocked", False), "release_blocked"),
            ("results", lambda value: value["results"].append({"result": "pass"}), "results must remain empty"),
            ("completion", lambda value: value.__setitem__("repository_completion", "complete"), "must remain incomplete"),
            ("scenario-status", lambda value: value["scenario_evidence"][0].__setitem__("status", "pass"), "must remain not-run"),
            ("scenario-effect", lambda value: value["scenario_evidence"][0].__setitem__("t09_effect", "scenario passed"), "honest bounded"),
        )
        for label, mutation, token in cases:
            with self.subTest(label=label):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, PARITY)
                mutation(payload)
                self.write_json(fixture, PARITY, payload)
                self.assert_rejected(self.errors_for(fixture), token)

    def test_malformed_and_duplicate_key_json_are_rejected(self):
        for relative in (PARITY, SOURCE):
            with self.subTest(relative=relative, kind="malformed"):
                fixture = self.copy_fixture()
                (fixture / relative).write_text("{\n", encoding="utf-8")
                self.assert_rejected(self.errors_for(fixture), "invalid JSON")
            with self.subTest(relative=relative, kind="duplicate"):
                fixture = self.copy_fixture()
                text = (fixture / relative).read_text(encoding="utf-8")
                self.replace(fixture, relative, "{\n", '{\n  "schema": "duplicate",\n')
                self.assert_rejected(self.errors_for(fixture), "duplicate JSON key")

    def test_json_depth_node_and_string_limits_accept_exact_boundaries(self):
        self.assertEqual(32, self.checker.MAX_JSON_DEPTH)
        self.assertEqual(4096, self.checker.MAX_JSON_NODES)
        self.assertEqual(4096, self.checker.MAX_JSON_STRING_LENGTH)

        depth_value = 0
        for _ in range(self.checker.MAX_JSON_DEPTH - 1):
            depth_value = [depth_value]

        node_value = {
            f"key-{index:04d}": 0
            for index in range((self.checker.MAX_JSON_NODES - 2) // 2)
        }
        node_value["key-0000"] = [0]

        cases = (
            ("depth", depth_value),
            ("nodes-including-object-keys", node_value),
            ("string-value", "x" * self.checker.MAX_JSON_STRING_LENGTH),
            ("string-key", {"x" * self.checker.MAX_JSON_STRING_LENGTH: 0}),
        )
        for relative in (PARITY, SOURCE):
            for label, payload in cases:
                with self.subTest(relative=relative, label=label):
                    temporary = tempfile.TemporaryDirectory()
                    self.addCleanup(temporary.cleanup)
                    root = Path(temporary.name) / "repository"
                    target = root / relative
                    target.parent.mkdir(parents=True)
                    target.write_text(json.dumps(payload), encoding="utf-8")
                    errors = []
                    parsed, _ = self.checker.parse_json(root, relative, errors)
                    self.assertIsNotNone(parsed)
                    self.assertEqual([], errors)

    def test_json_depth_node_and_string_limits_reject_over_boundaries(self):
        self.assertEqual(32, self.checker.MAX_JSON_DEPTH)
        self.assertEqual(4096, self.checker.MAX_JSON_NODES)
        self.assertEqual(4096, self.checker.MAX_JSON_STRING_LENGTH)

        depth_value = 0
        for _ in range(self.checker.MAX_JSON_DEPTH):
            depth_value = [depth_value]

        cases = (
            ("depth", depth_value, "JSON depth exceeds 32"),
            (
                "nodes-including-object-keys",
                {
                    f"key-{index:04d}": 0
                    for index in range(self.checker.MAX_JSON_NODES // 2)
                },
                "JSON node count exceeds 4096",
            ),
            (
                "string-value",
                "x" * (self.checker.MAX_JSON_STRING_LENGTH + 1),
                "JSON string length exceeds 4096",
            ),
            (
                "string-key",
                {"x" * (self.checker.MAX_JSON_STRING_LENGTH + 1): 0},
                "JSON string length exceeds 4096",
            ),
        )
        for relative in (PARITY, SOURCE):
            for label, payload, token in cases:
                with self.subTest(relative=relative, label=label):
                    temporary = tempfile.TemporaryDirectory()
                    self.addCleanup(temporary.cleanup)
                    root = Path(temporary.name) / "repository"
                    target = root / relative
                    target.parent.mkdir(parents=True)
                    target.write_text(json.dumps(payload), encoding="utf-8")
                    errors = []
                    parsed, _ = self.checker.parse_json(root, relative, errors)
                    self.assertIsNone(parsed)
                    self.assertEqual(1, len(errors), errors)
                    self.assert_rejected(errors, token)
                    for error in errors:
                        self.assertLess(len(error), 512)
                        self.assertNotIn("Traceback", error)

    def test_json_recursion_failure_is_bounded_and_has_no_traceback(self):
        for relative in (PARITY, SOURCE):
            with self.subTest(relative=relative, kind="direct"):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name) / "repository"
                target = root / relative
                target.parent.mkdir(parents=True)
                target.write_text("{}\n", encoding="utf-8")
                errors = []
                with mock.patch.object(
                    self.checker.json,
                    "loads",
                    side_effect=RecursionError("synthetic JSON recursion"),
                ):
                    parsed, _ = self.checker.parse_json(root, relative, errors)
                self.assertIsNone(parsed)
                self.assertEqual(1, len(errors), errors)
                self.assert_rejected(errors, "parser recursion limit exceeded")
                self.assertLess(len(errors[0]), 512)
                self.assertNotIn("Traceback", errors[0])

            with self.subTest(relative=relative, kind="cli"):
                fixture = self.copy_fixture()
                (fixture / relative).write_text(
                    "[" * 2000 + "0" + "]" * 2000,
                    encoding="utf-8",
                )
                checker = fixture / ".github/scripts/check-skills.py"
                checker.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(CHECKER, checker)
                completed = subprocess.run(
                    ["python3", "-I", str(checker)],
                    cwd=fixture,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(0, completed.returncode)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertLess(len(completed.stderr), 4096)
                self.assertTrue(
                    "parser recursion limit exceeded" in completed.stderr
                    or "JSON depth exceeds 32" in completed.stderr,
                    completed.stderr,
                )

    def test_oversized_duplicate_json_key_has_a_fixed_bounded_error(self):
        oversized_key = "x" * 4097
        duplicate = json.dumps({oversized_key: 0})[:-1] + "," + json.dumps(oversized_key) + ":1}"
        for relative in (PARITY, SOURCE):
            with self.subTest(relative=relative):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name) / "repository"
                target = root / relative
                target.parent.mkdir(parents=True)
                target.write_text(duplicate, encoding="utf-8")
                errors = []
                parsed, _ = self.checker.parse_json(root, relative, errors)
                self.assertIsNone(parsed)
                self.assertEqual(
                    [f"invalid JSON in {relative}: duplicate JSON key"],
                    errors,
                )
                self.assertLess(len(errors[0]), 512)
                self.assertNotIn(oversized_key, errors[0])
                self.assertNotIn("Traceback", errors[0])

    def test_incomplete_invocation_evidence_is_rejected(self):
        fixture = self.copy_fixture()
        payload = self.read_json(fixture, PARITY)
        payload["explicit_invocation_evidence"] = [{"skill": "verification"}]
        self.write_json(fixture, PARITY, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "keys must be exactly")
        self.assert_rejected(errors, "array must remain empty")

    def test_invocation_evidence_uses_the_exact_unambiguous_field_schema(self):
        valid = [{
            "skill": "verification",
            "codex_client_or_surface": "Codex desktop",
            "client_version": "2026-08-26",
            "date": "2026-08-26",
            "repository_commit": "0" * 40,
            "invocation_prompt": "Use $verification to review the exact head.",
            "observed_result": "observed",
            "limitations": "Static fixture only.",
        }]
        errors = []
        self.checker.validate_invocation_evidence(valid, errors)
        self.assertEqual([], errors)

        old_shape = [dict(valid[0], client="Codex desktop")]
        old_shape[0].pop("codex_client_or_surface")
        errors = []
        self.checker.validate_invocation_evidence(old_shape, errors)
        self.assert_rejected(errors, "keys must be exactly")

        malformed = copy.deepcopy(valid)
        malformed[0]["repository_commit"] = "short"
        malformed[0]["date"] = "2026/08/26"
        errors = []
        self.checker.validate_invocation_evidence(malformed, errors)
        self.assert_rejected(errors, "repository_commit must be an exact commit")
        self.assert_rejected(errors, "date must be YYYY-MM-DD")

        mismatched = copy.deepcopy(valid)
        mismatched[0]["invocation_prompt"] = "Use $retro for this review."
        errors = []
        self.checker.validate_invocation_evidence(mismatched, errors)
        self.assert_rejected(errors, "must contain the exact $verification token")

        impossible = copy.deepcopy(valid)
        impossible[0]["date"] = "2026-99-99"
        errors = []
        self.checker.validate_invocation_evidence(impossible, errors)
        self.assert_rejected(errors, "real calendar date")

        untrimmed = copy.deepcopy(valid)
        untrimmed[0]["codex_client_or_surface"] = " Codex desktop "
        errors = []
        self.checker.validate_invocation_evidence(untrimmed, errors)
        self.assert_rejected(errors, "bounded NFC control-free string")

    def test_wrong_nested_container_types_fail_with_bounded_errors(self):
        mutations = (
            (
                lambda value: value["contract_effects"].__setitem__("boundaries", [{}]),
                "contract_effects.boundaries[0] must be a non-empty bounded string",
            ),
            (
                lambda value: value["skills"][0]["adaptations"][0].__setitem__("classification", {}),
                "classification is not authorized",
            ),
            (
                lambda value: value["skills"][0].__setitem__("source_artifacts", [None]),
                "source_artifacts[0] must be an object",
            ),
            (
                lambda value: value["skills"][0].__setitem__("adaptations", [None]),
                "adaptations[0] must be an object",
            ),
            (
                lambda value: value.__setitem__(
                "explicit_invocation_evidence",
                [{
                    "skill": "verification",
                    "codex_client_or_surface": "client",
                    "client_version": "1",
                    "date": "2026-08-26",
                    "repository_commit": "0" * 40,
                    "invocation_prompt": "explicit",
                    "observed_result": {},
                    "limitations": "bounded",
                }],
                ),
                "observed_result",
            ),
        )
        for mutation, token in mutations:
            with self.subTest(token=token):
                fixture = self.copy_fixture()
                payload = self.read_json(fixture, PARITY)
                mutation(payload)
                self.write_json(fixture, PARITY, payload)
                self.assert_rejected(self.errors_for(fixture), token)


if __name__ == "__main__":
    unittest.main()
