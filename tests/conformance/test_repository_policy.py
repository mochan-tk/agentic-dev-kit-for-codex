import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-repository-policy.py"
OWNERSHIP = ".github/governance/phase-task-ownership.v1.json"


class RepositoryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("repository_policy", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load repository policy checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def ownership_payload(self, root=ROOT):
        return json.loads((root / OWNERSHIP).read_text(encoding="utf-8"))

    def declared_paths(self, payload):
        return [
            entry["path"]
            for task in payload["tasks"]
            for entry in task["owned_paths"]
        ]

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture = Path(temporary.name)
        payload = self.ownership_payload()
        for relative in self.declared_paths(payload):
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"fixture source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temporary, fixture

    def write_ownership(self, root, payload):
        (root / OWNERSHIP).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def errors_for(self, root):
        return self.checker.validate_repository(root, verify_git=False)

    def local_authorization_errors(self, root):
        errors = []
        self.checker.validate_execution_authorization(
            root, self.ownership_payload(root), {}, errors
        )
        return errors

    def add_declared_workflow(self, root, text, filename="secondary.yml"):
        relative = f".github/workflows/{filename}"
        path = root / relative
        path.write_text(text, encoding="utf-8")
        payload = self.ownership_payload(root)
        payload["tasks"][1]["owned_paths"].append(
            {"path": relative, "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(root, payload)
        return path

    def assert_rejected(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def current_feature_head(self):
        parents = subprocess.check_output(
            ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
            cwd=ROOT,
            text=True,
        ).split()
        if len(parents) == 3 and parents[1] == self.checker.ACCEPTED_PHASE0_COMMIT:
            return parents[2]
        return parents[0]

    def local_branch_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "repository"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", str(ROOT), str(fixture)],
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.filemode", "true"],
            cwd=fixture,
            check=True,
        )
        feature_head = self.current_feature_head()
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", feature_head],
            cwd=fixture,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "branch",
                "--force",
                "main",
                self.checker.ACCEPTED_PHASE0_COMMIT,
            ],
            cwd=fixture,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "checkout",
                "--quiet",
                "-B",
                "codex/phase-1-policy-bridge",
                feature_head,
            ],
            cwd=fixture,
            check=True,
        )
        return fixture

    def synthetic_pull_request_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "repository"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", str(ROOT), str(fixture)],
            check=True,
        )
        feature_head = self.current_feature_head()
        tree = subprocess.check_output(
            ["git", "rev-parse", f"{feature_head}^{{tree}}"], cwd=fixture, text=True
        ).strip()
        merge = subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Policy Test",
                "-c",
                "user.email=policy-test@example.invalid",
                "commit-tree",
                tree,
                "-p",
                self.checker.ACCEPTED_PHASE0_COMMIT,
                "-p",
                feature_head,
            ],
            cwd=fixture,
            input="synthetic test merge\n",
            text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
            },
        ).strip()
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", merge],
            cwd=fixture,
            check=True,
        )
        return fixture, feature_head, merge

    def pull_request_environment(self, event_path, merge):
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_BASE_REF": "main",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_HEAD_REF": "codex/phase-1-policy-bridge",
            "GITHUB_REF": "refs/pull/2/merge",
            "GITHUB_REF_NAME": "2/merge",
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
            "GITHUB_SHA": merge,
        }

    def test_live_repository_passes(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_safe_declared_expansion_passes(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        added = fixture / "docs/reviewed-expansion.md"
        added.parent.mkdir(parents=True, exist_ok=True)
        added.write_text("reviewed expansion\n", encoding="utf-8")
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            {"path": "docs/reviewed-expansion.md", "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assertEqual([], self.errors_for(fixture))

    def test_undeclared_live_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / "undeclared.txt").write_text("not owned\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "undeclared live path")

    def test_missing_declared_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / "README.md").unlink()
        self.assert_rejected(self.errors_for(fixture), "declared live path is missing")

    def test_overlapping_ownership_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            {"path": "README.md", "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "overlapping ownership")

    def test_duplicate_path_in_one_task_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            dict(payload["tasks"][1]["owned_paths"][0])
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate paths")

    def test_duplicate_task_id_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["id"] = payload["tasks"][0]["id"]
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate ownership task ID")

    def test_malformed_ownership_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"][0]["path"] = "../escape"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_control_character_in_ownership_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"][0]["path"] = "bad\npath"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_non_normalized_unicode_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"][0]["path"] = "docs/cafe\u0301.md"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_case_collision_in_ownership_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"].append(
            {"path": "readme.md", "mode": "100644"}
        )
        payload["tasks"][1]["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "Unicode/case path collision")

    def test_unsupported_manifest_shape_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["policy"]["implicit_bypass"] = True
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "unsupported or missing fields")

    def test_unhashable_state_and_mode_return_findings(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["state"] = ["active"]
        payload["tasks"][1]["owned_paths"][0]["mode"] = ["100644"]
        self.write_ownership(fixture, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, ".state is unsupported")
        self.assert_rejected(errors, ".mode is unsupported")

    def test_duplicate_ownership_json_key_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / OWNERSHIP
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '  "schema": "phase-task-ownership/v1",',
                '  "schema": "phase-task-ownership/v1",\n'
                '  "schema": "duplicate",',
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "duplicate object key")

    def test_duplicate_live_conformance_json_key_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "tests/conformance/manifest.json"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '  "schema": "phase-0-conformance-manifest/v1",',
                '  "schema": "phase-0-conformance-manifest/v1",\n'
                '  "schema": "duplicate",',
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "duplicate object key")

    def test_manifest_must_own_itself(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["tasks"][1]["owned_paths"] = [
            entry
            for entry in payload["tasks"][1]["owned_paths"]
            if entry["path"] != OWNERSHIP
        ]
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "own its own path")

    def test_symlink_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.unlink()
        path.symlink_to("AGENTS.md")
        self.assert_rejected(self.errors_for(fixture), "symlink component")

    def test_unapproved_executable_mode_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.chmod(path.stat().st_mode | 0o111)
        self.assert_rejected(self.errors_for(fixture), "mode mismatch")

    def test_gitlink_mode_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        paths = set(self.declared_paths(self.ownership_payload(fixture)))
        modes = {path: "100644" for path in paths}
        modes["README.md"] = "160000"
        self.assert_rejected(
            self.checker.validate_repository(
                fixture,
                verify_git=False,
                observed_paths=paths,
                observed_modes=modes,
            ),
            "mode mismatch",
        )

    def test_release_blocker_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        payload["phase"]["release_blocked"] = False
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "release_blocked must remain true")

    def test_conformance_release_blocker_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "tests/conformance/manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["release_blocked"] = False
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.assert_rejected(
            self.errors_for(fixture), "conformance manifest release_blocked"
        )

    def test_invariant_meaning_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "AGENTS.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "GitHub is durable truth", "A thread is durable truth", 1
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "invariant meanings")

    def test_synchronized_mutable_invariant_digest_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        agents_path = fixture / "AGENTS.md"
        agents_text = agents_path.read_text(encoding="utf-8").replace(
            "GitHub is durable truth", "A thread is durable truth", 1
        )
        agents_path.write_text(agents_text, encoding="utf-8")
        invariants = [
            match.groups()
            for line in agents_text.splitlines()
            if (match := self.checker.INVARIANT_ROW.match(line))
        ]
        canonical = "".join(
            f"{identifier}\t{statement}\n"
            for identifier, statement in sorted(invariants)
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertNotEqual(self.checker.REVIEWED_INVARIANT_DIGEST, digest)

        ownership = self.ownership_payload(fixture)
        ownership["policy"]["invariant_digest"] = digest
        self.write_ownership(fixture, ownership)

        conformance_path = fixture / "tests/conformance/manifest.json"
        conformance = json.loads(conformance_path.read_text(encoding="utf-8"))
        conformance["invariants"]["digest"] = digest
        conformance_path.write_text(
            json.dumps(conformance, indent=2) + "\n", encoding="utf-8"
        )
        self.assert_rejected(self.errors_for(fixture), "reviewed live anchor")

    def test_missing_required_job_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("  quality:\n", "  renamed:\n", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "required job drift")

    def test_duplicate_required_job_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8")
        duplicate = text[text.index("  quality:\n") : text.index("\n  conformance:\n")]
        path.write_text(text + "\n" + duplicate + "\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "duplicate job ID")

    def test_extra_ci_job_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n  extra:\n"
            "    runs-on: ubuntu-latest\n"
            "    permissions:\n"
            "      contents: read\n"
            "    steps:\n"
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "          persist-credentials: false\n",
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "jobs must be exactly")

    def test_extra_workflow_cannot_reuse_reserved_ruleset_job_id(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        self.add_declared_workflow(
            fixture,
            """name: secondary

on:
  pull_request:

permissions: {}

jobs:
  quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Observe
        run: echo observed
""",
            "reserved-id.yml",
        )
        self.assert_rejected(
            self.errors_for(fixture), "reuses reserved Ruleset job ID(s): quality"
        )

    def test_extra_workflow_without_reserved_context_passes(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        self.add_declared_workflow(
            fixture,
            """name: secondary

on:
  pull_request:

permissions: {}

jobs:
  secondary:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Observe
        run: echo observed
""",
            "secondary.yml",
        )
        self.assertEqual([], self.errors_for(fixture))

    def test_extra_workflow_cannot_set_explicit_or_dynamic_job_name(self):
        for label, job_name in (
            ("explicit", "quality"),
            ("dynamic", "${{ github.ref }}"),
        ):
            with self.subTest(label=label):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                self.add_declared_workflow(
                    fixture,
                    """name: secondary

on:
  pull_request:

permissions: {}

jobs:
  secondary:
    name: JOB_NAME
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Observe
        run: echo observed
""".replace("JOB_NAME", job_name),
                    f"named-{label}.yml",
                )
                self.assert_rejected(
                    self.errors_for(fixture), "job-level name is forbidden"
                )

    def test_job_if_false_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  quality:\n    runs-on:",
                "  quality:\n    if: false\n    runs-on:",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "unsupported job metadata")

    def test_step_if_false_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "      - name: Validate live repository policy\n"
                "        run: python3 .github/scripts/check-repository-policy.py",
                "      - name: Validate live repository policy\n"
                "        if: false\n"
                "        run: python3 .github/scripts/check-repository-policy.py",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(
            self.errors_for(fixture), "unsupported fields or execution modifiers"
        )

    def test_job_name_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  quality:\n    runs-on:",
                "  quality:\n    name: not-the-context-id\n    runs-on:",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "unsupported job metadata")

    def test_matrix_strategy_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  quality:\n    runs-on:",
                "  quality:\n    strategy:\n"
                "      matrix:\n"
                "        python: ['3.11']\n"
                "    runs-on:",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "unsupported job metadata")

    def test_defaults_and_custom_shell_are_rejected(self):
        mutations = (
            (
                "defaults",
                "    steps:\n",
                "    defaults:\n      run:\n        shell: bash\n    steps:\n",
                "unsupported job metadata",
            ),
            (
                "shell",
                "        run: python3 .github/scripts/check-repository-policy.py\n",
                "        run: python3 .github/scripts/check-repository-policy.py\n"
                "        shell: bash\n",
                "unsupported fields or execution modifiers",
            ),
        )
        for label, old, new, token in mutations:
            with self.subTest(label=label):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                path = fixture / ".github/workflows/ci.yml"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                self.assert_rejected(self.errors_for(fixture), token)

    def test_trigger_filter_that_disables_required_check_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  pull_request:\n  push:",
                "  pull_request:\n    paths: ['never/**']\n  push:",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "trigger/preamble")

    def test_missing_live_checker_command_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        text = path.read_text(encoding="utf-8").replace(
            "      - name: Validate live repository policy\n"
            "        run: python3 .github/scripts/check-repository-policy.py\n",
            "",
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "reviewed steps")

    def test_checkout_settings_cannot_move_to_another_action(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        original = (
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "          persist-credentials: false"
        )
        moved = (
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
            "      - uses: actions/cache@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # v4.0.2\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "          persist-credentials: false"
        )
        path.write_text(
            path.read_text(encoding="utf-8").replace(original, moved, 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "reviewed steps")

    def test_unpinned_action_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/checkout@v7",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "full commit SHA")

    def test_invalid_permissions_are_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("contents: read", "contents: none", 1),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "permissions must contain only")

    def test_continue_on_error_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / ".github/workflows/ci.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "        run: python3 .github/scripts/check-repository-policy.py",
                "        continue-on-error: true\n"
                "        run: python3 .github/scripts/check-repository-policy.py",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "forbidden continue-on-error")

    def test_stale_or_missing_base_evidence_is_rejected(self):
        payload = self.ownership_payload()
        payload["tasks"][1]["base_commit"] = "0" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "commit object is missing")

    def test_base_tree_mismatch_is_rejected(self):
        payload = self.ownership_payload()
        payload["tasks"][1]["base_tree"] = "f" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "tree does not match")

    def test_active_task_rejects_change_owned_only_by_phase0(self):
        payload = self.ownership_payload()
        errors = []
        task = self.checker.active_task_for_branch(
            payload, "codex/phase-1-policy-bridge", errors
        )
        self.assertIsNotNone(task)
        self.checker.authorize_changed_paths(task, ["README.md"], errors)
        self.assert_rejected(errors, "outside active Task T03 ownership")

    def test_atomic_manifest_ownership_transfer_is_viable(self):
        transferred = copy.deepcopy(self.ownership_payload())
        manifest_entry = next(
            entry
            for entry in transferred["tasks"][1]["owned_paths"]
            if entry["path"] == OWNERSHIP
        )
        transferred["tasks"][1]["owned_paths"].remove(manifest_entry)
        transferred["tasks"][1]["state"] = "accepted"
        transferred["tasks"].append(
            {
                "id": "T04",
                "record": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/6",
                "state": "active",
                "branch": "codex/phase-1-ci-toolchain",
                "base_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "base_tree": subprocess.check_output(
                    ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
                ).strip(),
                "owned_paths": [manifest_entry],
            }
        )
        errors = []
        self.checker.validate_manifest(transferred, errors)
        task = self.checker.active_task_for_branch(
            transferred, "codex/phase-1-ci-toolchain", errors
        )
        self.assertIsNotNone(task)
        self.checker.authorize_changed_paths(task, [OWNERSHIP], errors)
        self.assertEqual([], errors)

    def test_local_branch_execution_context_passes(self):
        fixture = self.local_branch_fixture()
        self.assertEqual(
            [], self.checker.validate_repository(fixture, environment={})
        )

    def test_local_branch_rejects_older_ancestor_as_task_base(self):
        fixture = self.local_branch_fixture()
        payload = copy.deepcopy(self.ownership_payload(fixture))
        payload["tasks"][1]["base_commit"] = (
            "88179ec6a28393d7bf4cea96684e3af16b512484"
        )
        payload["tasks"][1]["base_tree"] = (
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        )
        errors = []
        self.checker.validate_execution_authorization(fixture, payload, {}, errors)
        self.assert_rejected(errors, "must equal current local main")

    def test_local_branch_rejects_committed_p00_change(self):
        fixture = self.local_branch_fixture()
        path = fixture / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\ncommitted outside T03\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "README.md"], cwd=fixture, check=True
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Policy Test",
                "-c",
                "user.email=policy-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "test unauthorized commit",
            ],
            cwd=fixture,
            check=True,
        )
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            "outside active Task T03 ownership: README.md",
        )

    def test_local_branch_rejects_unstaged_p00_content_change(self):
        fixture = self.local_branch_fixture()
        path = fixture / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nunstaged outside T03\n",
            encoding="utf-8",
        )
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            "outside active Task T03 ownership: README.md",
        )

    def test_local_branch_rejects_staged_p00_content_change(self):
        fixture = self.local_branch_fixture()
        path = fixture / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nstaged outside T03\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "README.md"], cwd=fixture, check=True)
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            "outside active Task T03 ownership: README.md",
        )

    def test_local_branch_rejects_dirty_p00_mode_change(self):
        fixture = self.local_branch_fixture()
        (fixture / "README.md").chmod(0o755)
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            "outside active Task T03 ownership: README.md",
        )

    def test_local_branch_rejects_dirty_p00_deletion(self):
        fixture = self.local_branch_fixture()
        (fixture / "README.md").unlink()
        errors = self.local_authorization_errors(fixture)
        self.assert_rejected(errors, "does not support deletion")
        self.assert_rejected(
            errors, "outside active Task T03 ownership: README.md"
        )

    def test_local_branch_allows_checking_active_owned_dirty_change(self):
        fixture = self.local_branch_fixture()
        path = fixture / ".github/scripts/check-repository-policy.py"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# active-owned dirty test\n",
            encoding="utf-8",
        )
        self.assertEqual(
            [], self.checker.validate_repository(fixture, environment={})
        )

    def test_github_pull_request_synthetic_ref_context_passes(self):
        fixture, head, merge = self.synthetic_pull_request_fixture()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        event_path = Path(temporary.name) / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "base": {
                            "ref": "main",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": "32615344ad4f0310948bc59d234a84718741788a",
                        },
                        "head": {
                            "ref": "codex/phase-1-policy-bridge",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": head,
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        environment = self.pull_request_environment(event_path, merge)
        self.assertEqual(
            [], self.checker.validate_repository(fixture, environment=environment)
        )

    def test_github_pull_request_base_must_match_active_task(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        event_path = Path(temporary.name) / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "base": {
                            "ref": "main",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": "88179ec6a28393d7bf4cea96684e3af16b512484"
                        },
                        "head": {
                            "ref": "codex/phase-1-policy-bridge",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": head,
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        errors = []
        self.checker.validate_execution_authorization(
            ROOT,
            self.ownership_payload(),
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_BASE_REF": "main",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_HEAD_REF": "codex/phase-1-policy-bridge",
                "GITHUB_REF": "refs/pull/2/merge",
                "GITHUB_REF_NAME": "2/merge",
                "GITHUB_REF_TYPE": "branch",
                "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
                "GITHUB_SHA": head,
            },
            errors,
        )
        self.assert_rejected(errors, "does not match pull_request.base.sha")

    def test_github_pull_request_requires_same_repository_on_both_sides(self):
        checked_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        cases = (
            ("missing-base", "base", "missing", "base.repo.full_name"),
            ("null-head", "head", None, "head.repo.full_name"),
            (
                "fork-head",
                "head",
                {"full_name": "external/fork"},
                "head.repo.full_name",
            ),
        )
        for label, side, repository, token in cases:
            with self.subTest(label=label):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                event_path = Path(temporary.name) / "event.json"
                pull_request = {
                    "base": {
                        "ref": "main",
                        "repo": {
                            "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                        },
                        "sha": self.checker.ACCEPTED_PHASE0_COMMIT,
                    },
                    "head": {
                        "ref": "codex/phase-1-policy-bridge",
                        "repo": {
                            "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                        },
                        "sha": self.current_feature_head(),
                    },
                }
                if repository == "missing":
                    pull_request[side].pop("repo")
                else:
                    pull_request[side]["repo"] = repository
                event_path.write_text(
                    json.dumps({"pull_request": pull_request}) + "\n",
                    encoding="utf-8",
                )
                errors = []
                self.checker.validate_execution_authorization(
                    ROOT,
                    self.ownership_payload(),
                    self.pull_request_environment(event_path, checked_head),
                    errors,
                )
                self.assert_rejected(errors, token)

    def test_github_pull_request_ref_number_mismatch_fails_closed(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        errors = []
        self.checker.resolve_execution_context(
            ROOT,
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_BASE_REF": "main",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": "/not-read-by-context-resolution",
                "GITHUB_HEAD_REF": "codex/phase-1-policy-bridge",
                "GITHUB_REF": "refs/pull/3/merge",
                "GITHUB_REF_NAME": "2/merge",
                "GITHUB_REF_TYPE": "branch",
                "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
                "GITHUB_SHA": head,
            },
            errors,
        )
        self.assert_rejected(errors, "does not match GITHUB_REF_NAME")

    def test_github_pull_request_requires_exact_synthetic_merge(self):
        checked_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        event_path = Path(temporary.name) / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "base": {
                            "ref": "main",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": self.checker.ACCEPTED_PHASE0_COMMIT,
                        },
                        "head": {
                            "ref": "codex/phase-1-policy-bridge",
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": self.checker.ACCEPTED_PHASE0_COMMIT,
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        errors = []
        environment = self.pull_request_environment(event_path, checked_head)
        self.checker.validate_execution_authorization(
            ROOT, self.ownership_payload(), environment, errors
        )
        self.assert_rejected(errors, "exact synthetic merge")

    def test_github_main_push_context_retains_full_tree_check(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_BASE_REF": "",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_HEAD_REF": "",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_NAME": "main",
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
            "GITHUB_SHA": head,
        }
        self.assertEqual(
            [], self.checker.validate_repository(ROOT, environment=environment)
        )

    def test_unknown_github_event_fails_closed(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        errors = []
        self.checker.resolve_execution_context(
            ROOT,
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_BASE_REF": "",
                "GITHUB_EVENT_NAME": "schedule",
                "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
                "GITHUB_SHA": head,
            },
            errors,
        )
        self.assert_rejected(errors, "unsupported GitHub Actions event")

    def test_floating_dependency_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\npackage@latest\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "@latest")

    def test_model_slug_in_normative_policy_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ngpt-example\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "hardcodes model slug")


if __name__ == "__main__":
    unittest.main()
