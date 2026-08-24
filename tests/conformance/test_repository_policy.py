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
PHASE_MANIFEST = "tests/conformance/manifest.json"
COVERAGE = "tests/conformance/coverage.json"
HIERARCHY_ADR = "docs/agreements/adr/ADR-0005-issue-graph-authority.md"
REPOSITORY_COMPLETION = "docs/agreements/repository-completion.md"
HIERARCHY_ISSUE = (
    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/7"
)
CURRENT_TASK_ID = "T05"
CURRENT_TASK_BRANCH = "codex/phase-1-hierarchy-agreement"
EXPECTED_I02 = (
    "The Issue graph (repository initiative / Epic set -> Epic issue -> Task issue "
    "-> PR -> commits, checks, and evidence) is canonical; a GitHub Projects board "
    "is an optional projection and never outranks it."
)
EXPECTED_INVARIANT_DIGEST = (
    "a084a123e16d2fd42619b09161efdaf49bda0ea0ca4a1e076254bd1902aa63f6"
)
CANONICAL_HIERARCHY = (
    "Repository initiative / Epic set -> Epic issue -> Task issue -> PR -> "
    "commits, checks, and evidence"
)
PROJECTS_PROJECTION = (
    "A GitHub Projects board is an optional projection. It never outranks the "
    "Issue graph."
)
NO_INDIVIDUAL_COMPLETION = (
    "No individual phase completion constitutes repository-level completion."
)
OVERALL_COMPLETION_CONDITION = (
    "The overall repository implementation remains incomplete until every "
    "required contract has current target-side evidence and a human-reviewed "
    "completion pull request changing `release_blocked` to `false` is merged."
)
REQUIRED_CONTRACTS = [f"K{number:02d}" for number in range(1, 21)]


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

    def active_task(
        self,
        payload,
        *,
        task_id=CURRENT_TASK_ID,
        branch=CURRENT_TASK_BRANCH,
    ):
        active = [
            task
            for task in payload["tasks"]
            if task["state"] == "active"
            and task["id"] == task_id
            and task["branch"] == branch
        ]
        self.assertEqual(1, len(active), "intended active Task fixture is missing")
        return active[0]

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

    def read_json(self, root, relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def write_json(self, root, relative, payload):
        (root / relative).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def bind_coverage_hash(self, root):
        manifest = self.read_json(root, PHASE_MANIFEST)
        manifest["scenario_catalog"]["coverage"]["sha256"] = hashlib.sha256(
            (root / COVERAGE).read_bytes()
        ).hexdigest()
        self.write_json(root, PHASE_MANIFEST, manifest)

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
        task = self.active_task(payload)
        task["owned_paths"].append(
            {"path": relative, "mode": "100644"}
        )
        task["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(root, payload)
        return path

    def assert_rejected(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def current_feature_head(self):
        active_base = self.active_task(self.ownership_payload())["base_commit"]
        parents = subprocess.check_output(
            ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
            cwd=ROOT,
            text=True,
        ).split()
        if len(parents) == 3 and parents[1] == active_base:
            return parents[2]
        return parents[0]

    def materialize_current_worktree_head(self, fixture, feature_head):
        """Create a fixture-only commit when the current governed tree is dirty."""

        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", feature_head],
            cwd=fixture,
            check=True,
        )
        for relative in self.declared_paths(self.ownership_payload()):
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"live source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        subprocess.run(["git", "add", "--all"], cwd=fixture, check=True)
        changed = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=fixture,
            check=False,
        ).returncode
        self.assertIn(changed, {0, 1})
        if changed == 1:
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
                    "materialize current governed worktree",
                ],
                cwd=fixture,
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
                },
            )
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=fixture, text=True
        ).strip()

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
        task = self.active_task(self.ownership_payload())
        feature_head = self.materialize_current_worktree_head(
            fixture, self.current_feature_head()
        )
        subprocess.run(
            [
                "git",
                "branch",
                "--force",
                "main",
                task["base_commit"],
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
                task["branch"],
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
        task = self.active_task(self.ownership_payload())
        feature_head = self.materialize_current_worktree_head(
            fixture, self.current_feature_head()
        )
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
                task["base_commit"],
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
        task = self.active_task(self.ownership_payload())
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_BASE_REF": "main",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_HEAD_REF": task["branch"],
            "GITHUB_REF": "refs/pull/2/merge",
            "GITHUB_REF_NAME": "2/merge",
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REPOSITORY": "mochan-tk/agentic-dev-kit-for-codex",
            "GITHUB_SHA": merge,
        }

    def test_live_repository_passes(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_active_task_helper_selects_t05_among_disjoint_active_tasks(self):
        payload = copy.deepcopy(self.ownership_payload())
        phase0 = next(task for task in payload["tasks"] if task["id"] == "P00")
        phase0["state"] = "active"
        self.assertEqual("T05", self.active_task(payload)["id"])
        errors = []
        self.checker.validate_manifest(payload, errors)
        self.assertEqual([], errors)

    def test_safe_declared_expansion_passes(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        added = fixture / "docs/reviewed-expansion.md"
        added.parent.mkdir(parents=True, exist_ok=True)
        added.write_text("reviewed expansion\n", encoding="utf-8")
        payload = self.ownership_payload(fixture)
        task = self.active_task(payload)
        task["owned_paths"].append(
            {"path": "docs/reviewed-expansion.md", "mode": "100644"}
        )
        task["owned_paths"].sort(key=lambda item: item["path"])
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
        task = self.active_task(payload)
        task["owned_paths"].append(
            {"path": "README.md", "mode": "100644"}
        )
        task["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "overlapping ownership")

    def test_duplicate_path_in_one_task_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        task = self.active_task(payload)
        task["owned_paths"].append(dict(task["owned_paths"][0]))
        task["owned_paths"].sort(key=lambda item: item["path"])
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate paths")

    def test_duplicate_task_id_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        self.active_task(payload)["id"] = payload["tasks"][0]["id"]
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "duplicate ownership task ID")

    def test_malformed_ownership_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        self.active_task(payload)["owned_paths"][0]["path"] = "../escape"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_control_character_in_ownership_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        self.active_task(payload)["owned_paths"][0]["path"] = "bad\npath"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_non_normalized_unicode_path_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        self.active_task(payload)["owned_paths"][0]["path"] = "docs/cafe\u0301.md"
        self.write_ownership(fixture, payload)
        self.assert_rejected(self.errors_for(fixture), "normalized repository path")

    def test_case_collision_in_ownership_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.ownership_payload(fixture)
        task = self.active_task(payload)
        task["owned_paths"].append(
            {"path": "readme.md", "mode": "100644"}
        )
        task["owned_paths"].sort(key=lambda item: item["path"])
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
        task = self.active_task(payload)
        task["state"] = ["active"]
        task["owned_paths"][0]["mode"] = ["100644"]
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
        task = self.active_task(payload)
        task["owned_paths"] = [
            entry
            for entry in task["owned_paths"]
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

    def test_option_b_invariant_and_live_digest_anchors_are_exact(self):
        lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        invariants = [
            match.groups()
            for line in lines
            if (match := self.checker.INVARIANT_ROW.match(line))
        ]
        statements = dict(invariants)
        self.assertEqual(EXPECTED_I02, statements["I02"])
        self.assertEqual(
            EXPECTED_INVARIANT_DIGEST,
            self.checker.invariant_digest(invariants),
        )
        self.assertEqual(
            EXPECTED_INVARIANT_DIGEST,
            self.checker.REVIEWED_INVARIANT_DIGEST,
        )
        self.assertEqual(
            EXPECTED_INVARIANT_DIGEST,
            self.ownership_payload()["policy"]["invariant_digest"],
        )
        self.assertEqual(
            EXPECTED_INVARIANT_DIGEST,
            self.read_json(ROOT, PHASE_MANIFEST)["invariants"]["digest"],
        )

    def test_option_b_manifest_anchors_and_completion_prerequisites_are_exact(self):
        manifest = self.read_json(ROOT, PHASE_MANIFEST)
        hierarchy = manifest["hierarchy_agreement"]
        self.assertEqual(
            {"decision", "issue", "path", "sha256"}, set(hierarchy)
        )
        self.assertEqual("option-b", hierarchy["decision"])
        self.assertEqual(HIERARCHY_ISSUE, hierarchy["issue"])
        self.assertEqual(HIERARCHY_ADR, hierarchy["path"])
        self.assertEqual(
            hashlib.sha256((ROOT / HIERARCHY_ADR).read_bytes()).hexdigest(),
            hierarchy["sha256"],
        )

        completion = manifest["repository_completion"]
        self.assertEqual(
            {
                "state",
                "definition",
                "individual_phase_completion_satisfies_repository_completion",
                "required_contracts",
                "target_side_evidence_required",
                "human_reviewed_completion_pr_required",
            },
            set(completion),
        )
        self.assertEqual("incomplete", completion["state"])
        self.assertIs(
            completion[
                "individual_phase_completion_satisfies_repository_completion"
            ],
            False,
        )
        self.assertEqual(REQUIRED_CONTRACTS, completion["required_contracts"])
        self.assertIs(completion["target_side_evidence_required"], True)
        self.assertIs(completion["human_reviewed_completion_pr_required"], True)
        self.assertEqual(
            {"path", "sha256"}, set(completion["definition"])
        )
        self.assertEqual(
            REPOSITORY_COMPLETION, completion["definition"]["path"]
        )
        self.assertEqual(
            hashlib.sha256((ROOT / REPOSITORY_COMPLETION).read_bytes()).hexdigest(),
            completion["definition"]["sha256"],
        )
        self.assertEqual(
            REQUIRED_CONTRACTS,
            [contract["id"] for contract in manifest["contracts"]],
        )
        self.assertEqual([], manifest["results"])
        self.assertIs(manifest["release_blocked"], True)

    def test_option_b_surfaces_and_repository_completion_boundary_are_explicit(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        adr = (ROOT / HIERARCHY_ADR).read_text(encoding="utf-8")
        completion = (ROOT / REPOSITORY_COMPLETION).read_text(encoding="utf-8")

        for text in (agents, readme, adr):
            self.assertIn(CANONICAL_HIERARCHY, text)
            self.assertIn(PROJECTS_PROJECTION, text)
        for text in (agents, readme, completion):
            self.assertIn(NO_INDIVIDUAL_COMPLETION, text)
            self.assertIn(OVERALL_COMPLETION_CONDITION, text)
        self.assertIn("## Repository completion boundary", agents)
        self.assertIn(f"]({HIERARCHY_ADR})", readme)
        self.assertIn(f"]({REPOSITORY_COMPLETION})", readme)
        for marker in (
            "Phase 0 is complete",
            "Phase 1 is in progress",
            "not installable",
            "not a parity release",
            "`release_blocked` remains `true`",
        ):
            self.assertIn(marker, readme)
        for marker in (
            "durable repository objective",
            "explicitly linked Epic issues",
            "A single Epic issue may be the root",
            "wins if a projection conflicts",
        ):
            self.assertIn(marker, agents)

        for marker in (
            "# ADR-0005: Issue graph authority and optional Project projection",
            "- Status: Proposed; accepted when Issue #7's dedicated agreement pull request is owner-merged",
            "## Options considered",
            "### Option A",
            "### Option B (selected)",
            "### Option C",
            "Selected: Option B.",
            HIERARCHY_ISSUE,
            REPOSITORY_COMPLETION,
            "C-004",
        ):
            self.assertIn(marker, adr)

        for marker in (
            "# Repository-level definition of done",
            "eight repository Skills",
            "six custom agents",
            "project hooks and handlers",
            "Epic, Task, and PR ledger schemas",
            "execution envelope and loop-event schemas",
            "Codex execution adapter",
            "installer and upgrade",
            "Task ritual, ownership, and governance",
            "clean-repository installation and end-to-end Task",
            "all 136 conformance scenarios",
            "satisfying each scenario's expected target behavior",
            "K01 through K20",
            "UNKNOWN",
            "UNCHECKABLE",
            "`fail`",
            "`failed`",
        ):
            self.assertIn(marker, completion)

    def test_synchronized_option_a_or_c_invariant_drift_is_rejected(self):
        alternatives = (
            "GitHub Project -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.",
            "A Project record -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical; Project does not mean GitHub Projects.",
        )
        for alternative in alternatives:
            with self.subTest(alternative=alternative):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                agents_path = fixture / "AGENTS.md"
                agents_text = agents_path.read_text(encoding="utf-8").replace(
                    EXPECTED_I02, alternative, 1
                )
                agents_path.write_text(agents_text, encoding="utf-8")
                invariants = [
                    match.groups()
                    for line in agents_text.splitlines()
                    if (match := self.checker.INVARIANT_ROW.match(line))
                ]
                digest = self.checker.invariant_digest(invariants)
                ownership = self.ownership_payload(fixture)
                ownership["policy"]["invariant_digest"] = digest
                self.write_ownership(fixture, ownership)
                manifest = self.read_json(fixture, PHASE_MANIFEST)
                manifest["invariants"]["digest"] = digest
                self.write_json(fixture, PHASE_MANIFEST, manifest)
                self.assert_rejected(
                    self.errors_for(fixture), "reviewed live anchor"
                )

    def test_hierarchy_manifest_anchor_shape_and_values_are_enforced(self):
        def missing_anchor(payload):
            payload.pop("hierarchy_agreement")

        def missing_field(payload):
            payload["hierarchy_agreement"].pop("sha256")

        def extra_field(payload):
            payload["hierarchy_agreement"]["projection"] = "optional"

        def wrong_decision(payload):
            payload["hierarchy_agreement"]["decision"] = "option-a"

        def wrong_issue(payload):
            payload["hierarchy_agreement"]["issue"] = HIERARCHY_ISSUE + "0"

        def wrong_path(payload):
            payload["hierarchy_agreement"]["path"] = REPOSITORY_COMPLETION

        def malformed_hash(payload):
            payload["hierarchy_agreement"]["sha256"] = "not-a-sha256"

        for name, mutation in (
            ("missing-anchor", missing_anchor),
            ("missing-field", missing_field),
            ("extra-field", extra_field),
            ("wrong-decision", wrong_decision),
            ("wrong-issue", wrong_issue),
            ("wrong-path", wrong_path),
            ("malformed-hash", malformed_hash),
        ):
            with self.subTest(case=name):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                manifest = self.read_json(fixture, PHASE_MANIFEST)
                mutation(manifest)
                self.write_json(fixture, PHASE_MANIFEST, manifest)
                self.assert_rejected(
                    self.errors_for(fixture), "hierarchy agreement"
                )

    def test_repository_completion_manifest_contract_is_enforced(self):
        def missing_object(payload):
            payload.pop("repository_completion")

        def missing_gate(payload):
            payload["repository_completion"].pop(
                "human_reviewed_completion_pr_required"
            )

        def missing_individual_phase_gate(payload):
            payload["repository_completion"].pop(
                "individual_phase_completion_satisfies_repository_completion"
            )

        def wrong_individual_phase_gate(payload):
            payload["repository_completion"][
                "individual_phase_completion_satisfies_repository_completion"
            ] = True

        def missing_target_evidence_gate(payload):
            payload["repository_completion"].pop(
                "target_side_evidence_required"
            )

        def wrong_target_evidence_gate(payload):
            payload["repository_completion"]["target_side_evidence_required"] = False

        def extra_gate(payload):
            payload["repository_completion"]["phase_is_complete"] = True

        def completed_state(payload):
            payload["repository_completion"]["state"] = "complete"

        def missing_contract(payload):
            payload["repository_completion"]["required_contracts"].pop()

        def reordered_contracts(payload):
            payload["repository_completion"]["required_contracts"].reverse()

        def duplicate_contract(payload):
            payload["repository_completion"]["required_contracts"][-1] = "K19"

        def unknown_contract(payload):
            payload["repository_completion"]["required_contracts"][-1] = "K21"

        def disabled_completion_pr_gate(payload):
            payload["repository_completion"][
                "human_reviewed_completion_pr_required"
            ] = False

        def wrong_definition_path(payload):
            payload["repository_completion"]["definition"]["path"] = HIERARCHY_ADR

        def missing_definition(payload):
            payload["repository_completion"].pop("definition")

        def missing_definition_hash(payload):
            payload["repository_completion"]["definition"].pop("sha256")

        def extra_definition_field(payload):
            payload["repository_completion"]["definition"]["status"] = "draft"

        def malformed_definition_hash(payload):
            payload["repository_completion"]["definition"]["sha256"] = "bad"

        for name, mutation in (
            ("missing-object", missing_object),
            ("missing-gate", missing_gate),
            ("missing-individual-phase-gate", missing_individual_phase_gate),
            ("wrong-individual-phase-gate", wrong_individual_phase_gate),
            ("missing-target-evidence-gate", missing_target_evidence_gate),
            ("wrong-target-evidence-gate", wrong_target_evidence_gate),
            ("extra-gate", extra_gate),
            ("completed-state", completed_state),
            ("missing-contract", missing_contract),
            ("reordered-contracts", reordered_contracts),
            ("duplicate-contract", duplicate_contract),
            ("unknown-contract", unknown_contract),
            ("disabled-completion-pr-gate", disabled_completion_pr_gate),
            ("wrong-definition-path", wrong_definition_path),
            ("missing-definition", missing_definition),
            ("missing-definition-hash", missing_definition_hash),
            ("extra-definition-field", extra_definition_field),
            ("malformed-definition-hash", malformed_definition_hash),
        ):
            with self.subTest(case=name):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                manifest = self.read_json(fixture, PHASE_MANIFEST)
                mutation(manifest)
                self.write_json(fixture, PHASE_MANIFEST, manifest)
                self.assert_rejected(
                    self.errors_for(fixture), "repository completion"
                )

    def test_synchronized_agreement_document_rehash_cannot_move_reviewed_anchor(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / HIERARCHY_ADR
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Selected: Option B.", "Selected: Option A.", 1
            ),
            encoding="utf-8",
        )
        manifest = self.read_json(fixture, PHASE_MANIFEST)
        manifest["hierarchy_agreement"]["sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        self.write_json(fixture, PHASE_MANIFEST, manifest)
        self.assert_rejected(
            self.errors_for(fixture), "reviewed hierarchy agreement hash"
        )

    def test_synchronized_completion_document_rehash_cannot_move_reviewed_anchor(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture / REPOSITORY_COMPLETION
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                NO_INDIVIDUAL_COMPLETION,
                "Phase completion constitutes repository-level completion.",
                1,
            ),
            encoding="utf-8",
        )
        manifest = self.read_json(fixture, PHASE_MANIFEST)
        manifest["repository_completion"]["definition"]["sha256"] = (
            hashlib.sha256(path.read_bytes()).hexdigest()
        )
        self.write_json(fixture, PHASE_MANIFEST, manifest)
        self.assert_rejected(
            self.errors_for(fixture), "reviewed repository completion hash"
        )

    def test_option_b_and_completion_markers_are_enforced_on_live_surfaces(self):
        mutations = (
            (
                "AGENTS.md",
                CANONICAL_HIERARCHY,
                "GitHub Project -> Epic issue -> Task issue -> PR -> commits/checks/evidence",
                "Option B hierarchy",
            ),
            (
                "README.md",
                PROJECTS_PROJECTION,
                "A GitHub Projects board is the authoritative hierarchy.",
                "Option B hierarchy",
            ),
            (
                "AGENTS.md",
                NO_INDIVIDUAL_COMPLETION,
                "",
                "repository completion boundary",
            ),
            (
                "README.md",
                OVERALL_COMPLETION_CONDITION,
                "Phase 1 completion completes the repository.",
                "repository completion boundary",
            ),
        )
        for relative, old, new, token in mutations:
            with self.subTest(path=relative, marker=old):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                path = fixture / relative
                text = path.read_text(encoding="utf-8")
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
                self.assert_rejected(self.errors_for(fixture), token)

    def test_contradictory_live_authority_or_completion_insertions_are_rejected(self):
        insertions = (
            (
                "AGENTS.md",
                "GitHub Project -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.",
            ),
            (
                "README.md",
                "A GitHub Projects board is authoritative.",
            ),
            (
                "AGENTS.md",
                "Project Record -> Epic issue -> Task issue -> PR -> commits, checks, and evidence is canonical.",
            ),
            (
                "README.md",
                "Phase 1 completion completes the repository.",
            ),
        )
        for relative, insertion in insertions:
            with self.subTest(path=relative, insertion=insertion):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                path = fixture / relative
                path.write_text(
                    path.read_text(encoding="utf-8") + f"\n{insertion}\n",
                    encoding="utf-8",
                )
                self.assert_rejected(
                    self.errors_for(fixture),
                    "contradictory hierarchy or completion claim",
                )

    def test_c004_canonical_agreement_decision_is_enforced_after_rehash(self):
        def pending_reversion(entry):
            entry["disposition"] = "pending-agreement"
            entry.pop("agreement_adr")

        def planned_reversion(entry):
            entry["disposition"] = "planned"
            entry.pop("agreement_issue")
            entry.pop("agreement_adr")

        def wrong_issue(entry):
            entry["agreement_issue"] = HIERARCHY_ISSUE + "0"

        def wrong_adr(entry):
            entry["agreement_adr"] = (
                "docs/agreements/adr/ADR-0999-wrong-agreement.md"
            )

        def missing_adr(entry):
            entry.pop("agreement_adr")

        def marked_pass(entry):
            entry["verification_state"] = "pass"

        def extra_field(entry):
            entry["specialization"] = "GitHub Projects is authoritative"

        for name, mutation in (
            ("pending-reversion", pending_reversion),
            ("planned-reversion", planned_reversion),
            ("wrong-issue", wrong_issue),
            ("wrong-adr", wrong_adr),
            ("missing-adr", missing_adr),
            ("marked-pass", marked_pass),
            ("extra-field", extra_field),
        ):
            with self.subTest(case=name):
                temporary, fixture = self.copy_fixture()
                self.addCleanup(temporary.cleanup)
                coverage = self.read_json(fixture, COVERAGE)
                entry = next(
                    item
                    for item in coverage["entries"]
                    if item["scenario"] == "C-004"
                )
                mutation(entry)
                self.write_json(fixture, COVERAGE, coverage)
                self.bind_coverage_hash(fixture)
                self.assert_rejected(
                    self.errors_for(fixture), "canonical C-004 agreement decision"
                )

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
        self.active_task(payload)["base_commit"] = "0" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "commit object is missing")

    def test_base_tree_mismatch_is_rejected(self):
        payload = self.ownership_payload()
        self.active_task(payload)["base_tree"] = "f" * 40
        errors = []
        self.checker.validate_git_evidence(ROOT, payload, errors)
        self.assert_rejected(errors, "tree does not match")

    def test_active_task_rejects_change_owned_only_by_phase0(self):
        payload = self.ownership_payload()
        active = self.active_task(payload)
        errors = []
        task = self.checker.active_task_for_branch(
            payload, active["branch"], errors
        )
        self.assertIsNotNone(task)
        self.checker.authorize_changed_paths(task, ["LICENSE"], errors)
        self.assert_rejected(
            errors, f"outside active Task {active['id']} ownership"
        )

    def test_atomic_manifest_ownership_transfer_is_viable(self):
        transferred = copy.deepcopy(self.ownership_payload())
        active = self.active_task(transferred)
        manifest_entry = next(
            entry
            for entry in active["owned_paths"]
            if entry["path"] == OWNERSHIP
        )
        active["owned_paths"].remove(manifest_entry)
        active["state"] = "accepted"
        transferred["tasks"].append(
            {
                "id": "T06",
                "record": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8",
                "state": "active",
                "branch": "codex/phase-1-next-task",
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
            transferred, "codex/phase-1-next-task", errors
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
        active = self.active_task(payload)
        active["base_commit"] = (
            "88179ec6a28393d7bf4cea96684e3af16b512484"
        )
        active["base_tree"] = (
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        )
        errors = []
        self.checker.validate_execution_authorization(fixture, payload, {}, errors)
        self.assert_rejected(errors, "must equal current local main")

    def test_local_branch_rejects_committed_p00_change(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        path = fixture / "LICENSE"
        path.write_text(
            path.read_text(encoding="utf-8") + "\ncommitted outside active Task\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "LICENSE"], cwd=fixture, check=True
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
            f"outside active Task {active['id']} ownership: LICENSE",
        )

    def test_local_branch_rejects_unstaged_p00_content_change(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        path = fixture / "LICENSE"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nunstaged outside active Task\n",
            encoding="utf-8",
        )
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            f"outside active Task {active['id']} ownership: LICENSE",
        )

    def test_local_branch_rejects_staged_p00_content_change(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        path = fixture / "LICENSE"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nstaged outside active Task\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "LICENSE"], cwd=fixture, check=True)
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            f"outside active Task {active['id']} ownership: LICENSE",
        )

    def test_local_branch_rejects_dirty_p00_mode_change(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        (fixture / "LICENSE").chmod(0o755)
        self.assert_rejected(
            self.local_authorization_errors(fixture),
            f"outside active Task {active['id']} ownership: LICENSE",
        )

    def test_local_branch_rejects_dirty_p00_deletion(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        (fixture / "LICENSE").unlink()
        errors = self.local_authorization_errors(fixture)
        self.assert_rejected(errors, "does not support deletion")
        self.assert_rejected(
            errors, f"outside active Task {active['id']} ownership: LICENSE"
        )

    def test_local_branch_allows_checking_active_owned_dirty_change(self):
        fixture = self.local_branch_fixture()
        active = self.active_task(self.ownership_payload(fixture))
        relative = next(
            entry["path"]
            for entry in active["owned_paths"]
            if entry["path"].endswith(".md")
            and entry["path"] != "docs/conformance/catalog.md"
        )
        path = fixture / relative
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            [], self.checker.validate_repository(fixture, environment={})
        )

    def test_github_pull_request_synthetic_ref_context_passes(self):
        fixture, head, merge = self.synthetic_pull_request_fixture()
        task = self.active_task(self.ownership_payload())
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
                            "sha": task["base_commit"],
                        },
                        "head": {
                            "ref": task["branch"],
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
        task = self.active_task(self.ownership_payload())
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
                            "ref": task["branch"],
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
                "GITHUB_HEAD_REF": task["branch"],
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
        task = self.active_task(self.ownership_payload())
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
                        "sha": task["base_commit"],
                    },
                    "head": {
                        "ref": task["branch"],
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
        task = self.active_task(self.ownership_payload())
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
                "GITHUB_HEAD_REF": task["branch"],
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
        task = self.active_task(self.ownership_payload())
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
                            "sha": task["base_commit"],
                        },
                        "head": {
                            "ref": task["branch"],
                            "repo": {
                                "full_name": "mochan-tk/agentic-dev-kit-for-codex"
                            },
                            "sha": task["base_commit"],
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
