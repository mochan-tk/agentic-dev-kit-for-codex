import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-phase1-acceptance.py"
PHASE1 = "tests/conformance/results/phase-1.json"
RELEASE_RESULTS = "tests/conformance/results.json"
ACCEPTANCE_DOC = "docs/planning/phase-1-acceptance.md"
SCORECARD_DOC = "docs/conformance/phase-1-scorecard.md"
MANIFEST = "tests/conformance/manifest.json"


class Phase1AcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("phase1_acceptance", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load Phase 1 acceptance checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture = Path(temporary.name)
        for relative in self.checker.REQUIRED_INPUT_PATHS:
            source = ROOT / relative
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temporary, fixture

    def read_json(self, root, relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def write_json(self, root, relative, payload):
        (root / relative).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def errors_for(self, root):
        return self.checker.validate_repository(root)

    def assert_rejected(self, errors, marker):
        self.assertTrue(
            any(marker in error for error in errors),
            f"missing rejection marker {marker!r}: {errors}",
        )

    def test_current_repository_is_valid(self):
        self.assertEqual([], self.errors_for(ROOT))

    def test_all_catalog_scenarios_occur_once_and_are_non_pass(self):
        payload = self.read_json(ROOT, PHASE1)
        catalog = self.read_json(ROOT, "tests/conformance/catalog.json")
        expected = [
            scenario["id"]
            for family in catalog["families"]
            for scenario in family["scenarios"]
        ]
        actual = [entry["scenario"] for entry in payload["scenarios"]]
        self.assertEqual(expected, actual)
        self.assertEqual(136, len(actual))
        self.assertEqual(136, len(set(actual)))
        self.assertTrue(all(entry["status"] != "pass" for entry in payload["scenarios"]))

    def test_duplicate_or_missing_scenario_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["scenarios"][-1] = dict(payload["scenarios"][0])
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "scenario inventory must exactly match")

    def test_scenario_pass_without_exact_action_evidence_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["scenarios"][0]["status"] = "pass"
        payload["scenarios"][0]["evidence"] = []
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "pass requires exact scenario-action evidence")

    def test_plausible_scenario_pass_missing_tree_and_execution_class_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["scenarios"][0]["status"] = "pass"
        payload["scenarios"][0]["evidence"] = [
            {
                "command": "python3 -I .github/scripts/check-repository-policy.py",
                "target_commit": "1" * 40,
                "result": "success",
                "url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/1/job/1",
                "observed_at": "2026-08-26T12:00:00Z",
            }
        ]
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "unsupported or missing fields")
        self.assert_rejected(errors, "must remain exactly not-run")

    def test_unexplained_fail_cannot_replace_package_not_run_state(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["scenarios"][0]["status"] = "fail"
        payload["scenarios"][0]["evidence"] = []
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "fail requires exact scenario-action evidence")
        self.assert_rejected(errors, "must remain exactly not-run")

    def test_static_generic_check_cannot_promote_package_scenario(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["scenarios"][0]["status"] = "pass"
        payload["scenarios"][0]["evidence"] = [
            {
                "command": "python3 -I .github/scripts/check-repository-policy.py",
                "execution_class": "static-scenario-action",
                "target_commit": "1" * 40,
                "target_tree": "2" * 40,
                "result": "success",
                "url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/1/job/1",
                "observed_at": "2026-08-26T12:00:00Z",
            }
        ]
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "must remain exactly not-run")
        self.assert_rejected(errors, "exactly 136 not-run")

    def test_unknown_and_uncheckable_are_non_success(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["summary"]["successful_scenarios"] = 1
        payload["scenarios"][0]["status"] = "UNKNOWN"
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "scenario summary does not match")

    def test_contract_inventory_and_later_handoffs_are_complete(self):
        payload = self.read_json(ROOT, PHASE1)
        self.assertEqual(
            [f"K{number:02d}" for number in range(1, 21)],
            [entry["id"] for entry in payload["contracts"]],
        )
        by_id = {entry["id"]: entry for entry in payload["contracts"]}
        for contract_id in [f"K{number:02d}" for number in range(9, 17)] + ["K20"]:
            self.assertNotEqual("complete", by_id[contract_id]["status"])
            self.assertTrue(by_id[contract_id]["remaining"])
            self.assertTrue(by_id[contract_id]["later_owner"])
        self.assertTrue(
            all(entry["later_owner"]["state"] == "unassigned" for entry in payload["contracts"])
        )
        self.assertTrue(
            all(
                entry["state"] == "deferred-to-planning-intake"
                and entry["planning_issue_url"]
                == "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/21"
                and entry["later_owner"]["state"] == "unassigned"
                for entry in payload["later_handoffs"]
            )
        )
        self.assertNotIn(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/2",
            json.dumps(payload["contracts"] + payload["later_handoffs"]),
        )

    def test_complete_later_contract_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        next(entry for entry in payload["contracts"] if entry["id"] == "K10")[
            "status"
        ] = "complete"
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "K10 exact reviewed disposition drifted")

    def test_arbitrary_contract_claim_or_missing_evidence_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        contract = next(entry for entry in payload["contracts"] if entry["id"] == "K10")
        contract["advanced"] = "The task execution envelope is implemented."
        contract["evidence"] = ["does/not/exist.md"]
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "K10 exact reviewed disposition drifted")

    def test_contract_evidence_path_must_be_readable_without_symlink_follow(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        relative = ".agents/skills/verification/SKILL.md"
        target = fixture / relative
        external = fixture / "verification-skill-held.md"
        external.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(external)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, f"cannot read {relative}")

    def test_task_index_is_exact_and_evidence_bound(self):
        payload = self.read_json(ROOT, PHASE1)
        self.assertEqual(
            [f"T{number:02d}" for number in range(1, 10)],
            [entry["id"] for entry in payload["task_index"]],
        )
        for entry in payload["task_index"]:
            self.assertEqual("CLOSED", entry["issue_state"])
            self.assertEqual("COMPLETED", entry["issue_state_reason"])
            self.assertTrue(entry["plan_or_intent_url"].startswith("https://github.com/"))
            self.assertTrue(entry["receipt_url"].startswith("https://github.com/"))
            if entry["id"] in {"T01", "T02"}:
                self.assertEqual("not-applicable-external-state-task", entry["pull_request"])
                self.assertEqual(
                    "baseline-pre-actuator-observation",
                    entry["revision_evidence_class"],
                )
                self.assertEqual(
                    "32615344ad4f0310948bc59d234a84718741788a",
                    entry["reviewed_head"],
                )
                self.assertEqual(
                    "33259721ec9f378fa67392ef8e1c7645db1321f9",
                    entry["reviewed_tree"],
                )
                for check in entry["checks"].values():
                    self.assertEqual("baseline-pre-actuator-check", check["evidence_class"])
                    self.assertEqual(entry["reviewed_head"], check["target_commit"])
                    self.assertEqual(entry["reviewed_tree"], check["target_tree"])
            else:
                self.assertEqual("reviewed-pr-head", entry["revision_evidence_class"])
                self.assertRegex(entry["reviewed_head"], r"^[0-9a-f]{40}$")
                self.assertRegex(entry["merge_commit"], r"^[0-9a-f]{40}$")
                self.assertEqual("success", entry["checks"]["quality"]["result"])
                self.assertEqual("success", entry["checks"]["conformance"]["result"])

    def test_task_evidence_omission_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["task_index"][2]["checks"]["quality"]["url"] = ""
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "T03 quality evidence URL is invalid")

    def test_ruleset_snapshot_is_complete_and_digest_bound(self):
        payload = self.read_json(ROOT, PHASE1)
        ruleset = payload["governance"]["ruleset"]
        self.assertEqual([], ruleset["managed_ruleset_omitted_fields"])
        self.assertEqual(
            [{"actor_id": 9846618, "actor_type": "User", "bypass_mode": "always"}],
            ruleset["managed_ruleset"]["bypass_actors"],
        )
        self.assertEqual("always", ruleset["managed_ruleset"]["current_user_can_bypass"])
        self.assertEqual("not-configured", ruleset["classic_branch_protection"]["state"])
        self.assertEqual(
            404,
            ruleset["classic_branch_protection"]["details_read"]["http_status"],
        )
        canonical = json.dumps(
            {
                "managed_ruleset": ruleset["managed_ruleset"],
                "classic_branch_protection": ruleset["classic_branch_protection"],
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            "655d99c11deceebdb81222afc7a23e5a2349203a017abd219a46bd873bb60d0e",
            hashlib.sha256(canonical).hexdigest(),
        )

        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        drift = self.read_json(fixture, PHASE1)
        drift["governance"]["ruleset"]["managed_ruleset"]["bypass_actors"][0][
            "actor_id"
        ] = 1
        self.write_json(fixture, PHASE1, drift)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "owner emergency bypass snapshot drifted")
        self.assert_rejected(errors, "normalized snapshot digest drifted")

    def test_time_invariant_acceptance_states_are_separate(self):
        payload = self.read_json(ROOT, PHASE1)
        status = payload["acceptance_status"]
        self.assertEqual("satisfied", status["implementation_gate"]["state"])
        self.assertEqual(
            "pre-merge", status["snapshot_at_tree_creation"]["tree_creation_stage"]
        )
        self.assertEqual(
            "external-github-state", status["current_acceptance_authority"]["kind"]
        )
        self.assertEqual(
            "not-embedded",
            status["post_merge_outcome_not_embedded_in_tree"]["state"],
        )
        self.assertEqual("non-pass", status["later_repository"]["state"])

    def test_time_invariant_acceptance_status_drift_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["acceptance_status"]["implementation_gate"]["state"] = "candidate"
        self.write_json(fixture, PHASE1, payload)
        self.assert_rejected(
            self.errors_for(fixture), "time-invariant acceptance status classes drifted"
        )

    def test_release_results_and_completion_boundary_remain_blocked(self):
        payload = self.read_json(ROOT, PHASE1)
        release = self.read_json(ROOT, RELEASE_RESULTS)
        self.assertEqual([], release["results"])
        self.assertEqual(0, release["result_count"])
        self.assertIs(release["release_blocked"], True)
        self.assertIs(payload["completion"]["release_blocked"], True)
        self.assertIs(payload["completion"]["repository_complete"], False)
        self.assertEqual(
            "satisfied",
            payload["completion"]["phase1_portable_core_implementation_gate"],
        )
        self.assertIs(
            payload["completion"]["post_merge_outcome_embedded_in_tree"], False
        )

    def test_release_result_success_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, RELEASE_RESULTS)
        payload["release_blocked"] = False
        self.write_json(fixture, RELEASE_RESULTS, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "release result store must remain empty and blocked")

    def test_document_digests_and_compatibility_manifest_are_enforced(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture / SCORECARD_DOC).write_text("drift\n", encoding="utf-8")
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "document digest mismatch")

        temporary2, fixture2 = self.copy_fixture()
        self.addCleanup(temporary2.cleanup)
        manifest = self.read_json(fixture2, MANIFEST)
        manifest["results"] = [{"fabricated": True}]
        self.write_json(fixture2, MANIFEST, manifest)
        errors = self.errors_for(fixture2)
        self.assert_rejected(errors, "Phase 0 compatibility manifest must remain exact")

    def test_human_contract_table_must_match_machine_semantics(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        scorecard_path = fixture / SCORECARD_DOC
        scorecard_path.write_text(
            scorecard_path.read_text(encoding="utf-8").replace(
                "task-execution-envelope/v1 is unimplemented.",
                "task-execution-envelope/v1 is implemented.",
                1,
            ),
            encoding="utf-8",
        )
        payload = self.read_json(fixture, PHASE1)
        binding = next(
            item for item in payload["document_bindings"] if item["path"] == SCORECARD_DOC
        )
        binding["sha256"] = hashlib.sha256(scorecard_path.read_bytes()).hexdigest()
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "scorecard exact contract row is not synchronized: K10")

    def test_standalone_package_is_deterministically_discoverable(self):
        phase1 = self.read_json(ROOT, PHASE1)
        compatibility = phase1["compatibility_layer"]
        self.assertEqual(
            "unchanged-manifest-pin-fresh",
            compatibility["phase0_manifest"]["state"],
        )
        self.assertEqual(
            "docs/context/pins/PIN-0002.context-pin.v1.json",
            compatibility["phase0_manifest"]["selected_pin"],
        )
        self.assertEqual(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12#issuecomment-5419726866",
            compatibility["compatibility_replan_url"],
        )
        self.assertEqual(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/12#issuecomment-5421277687",
            compatibility["continuation_replan_url"],
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("tests/conformance/results/phase-1.json", readme)
        self.assertIn("docs/planning/phase-1-acceptance.md", readme)
        self.assertIn("docs/conformance/phase-1-scorecard.md", readme)
        ownership = self.read_json(
            ROOT, ".github/governance/phase-task-ownership.v1.json"
        )
        command = "python3 -I .github/scripts/check-phase1-acceptance.py"
        self.assertEqual(1, ownership["policy"]["required_quality_commands"].count(command))
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(1, workflow.count(f"run: {command}"))

    def test_fixed_input_symlink_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / PHASE1
        external = fixture / "outside.json"
        external.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(external)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "cannot read Phase 1 acceptance record")

    def test_symlinked_fixed_input_directory_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / "tests/conformance/results"
        held = fixture / "tests/conformance/results-held"
        target.rename(held)
        target.symlink_to(held, target_is_directory=True)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "cannot read Phase 1 acceptance record")

    def test_parent_namespace_swap_during_read_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / "tests/conformance/results"
        held = fixture / "tests/conformance/results-held"
        original_read = self.checker.os.read
        swapped = False

        def swap_once(descriptor, size):
            nonlocal swapped
            if not swapped:
                swapped = True
                target.rename(held)
                target.mkdir()
                shutil.copy2(held / "phase-1.json", target / "phase-1.json")
            return original_read(descriptor, size)

        with mock.patch.object(self.checker.os, "read", side_effect=swap_once):
            with self.assertRaisesRegex(ValueError, "binding changed"):
                self.checker.read_regular_bytes(fixture, PHASE1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fixed_input_fifo_returns_bounded_failure_without_traceback(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / PHASE1
        target.unlink()
        os.mkfifo(target)
        completed = subprocess.run(
            ["python3", "-I", os.fspath(CHECKER)],
            cwd=fixture,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_oversized_and_overdeep_json_fail_without_traceback(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / PHASE1
        target.write_bytes(b"{" + b" " * self.checker.MAX_FILE_BYTES + b"}")
        completed = subprocess.run(
            ["python3", "-I", os.fspath(CHECKER)],
            cwd=fixture,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

        temporary2, fixture2 = self.copy_fixture()
        self.addCleanup(temporary2.cleanup)
        (fixture2 / PHASE1).write_text(
            "[" * (self.checker.MAX_JSON_DEPTH + 2)
            + "0"
            + "]" * (self.checker.MAX_JSON_DEPTH + 2),
            encoding="utf-8",
        )
        errors = self.errors_for(fixture2)
        self.assert_rejected(errors, "JSON")

    def test_duplicate_keys_and_non_standard_constants_are_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        target = fixture / PHASE1
        text = target.read_text(encoding="utf-8")
        target.write_text(
            text.replace(
                '  "schema": "phase-1-acceptance/v1",',
                '  "schema": "phase-1-acceptance/v1",\n  "schema": "duplicate",',
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "duplicate JSON key")

        temporary2, fixture2 = self.copy_fixture()
        self.addCleanup(temporary2.cleanup)
        (fixture2 / PHASE1).write_text('{"value": NaN}\n', encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture2), "non-standard JSON constant")

    def test_json_limits_are_inclusive_and_fail_closed(self):
        value = 0
        for _ in range(self.checker.MAX_JSON_DEPTH - 1):
            value = [value]
        self.checker.validate_json_limits(value)
        with self.assertRaisesRegex(ValueError, "depth"):
            self.checker.validate_json_limits([value])

        self.checker.validate_json_limits("x" * self.checker.MAX_JSON_STRING_LENGTH)
        with self.assertRaisesRegex(ValueError, "string"):
            self.checker.validate_json_limits(
                "x" * (self.checker.MAX_JSON_STRING_LENGTH + 1)
            )

        self.checker.validate_json_limits(
            [0] * (self.checker.MAX_JSON_NODES - 1)
        )
        with self.assertRaisesRegex(ValueError, "nodes"):
            self.checker.validate_json_limits([0] * self.checker.MAX_JSON_NODES)

    def test_malformed_nested_shape_returns_findings_without_exception(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        payload = self.read_json(fixture, PHASE1)
        payload["summary"] = []
        self.write_json(fixture, PHASE1, payload)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "scenario summary")

    def test_docs_state_is_time_invariant_without_release_claim(self):
        acceptance = (ROOT / ACCEPTANCE_DOC).read_text(encoding="utf-8")
        scorecard = (ROOT / SCORECARD_DOC).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        limitations = (ROOT / "docs/known-limitations.md").read_text(encoding="utf-8")
        for marker in (
            "Phase 1 portable-core implementation gate",
            "creation-time snapshot",
            "current durable owner-acceptance outcome is external GitHub state",
            "Issue #12",
            "Epic #2",
            "post-merge outcome",
            "post-merge receipt",
            "repository implementation remains incomplete",
            "`release_blocked` remains `true`",
        ):
            self.assertIn(marker, acceptance + scorecard + readme + limitations)
        self.assertNotIn("repository implementation is complete", readme)
        self.assertNotIn("durable owner acceptance remains pending merge", readme)

    def test_stale_phase1_status_in_agents_is_rejected(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        agents = fixture / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8")
            + "\nPhase 1 is in progress; the full GitHub ledger arrives later.\n",
            encoding="utf-8",
        )
        self.assert_rejected(
            self.errors_for(fixture), "AGENTS.md contains stale Phase 1 status text"
        )

    def test_readme_and_limitations_each_require_the_full_status_boundary(self):
        temporary, fixture = self.copy_fixture()
        self.addCleanup(temporary.cleanup)
        limitations = fixture / "docs/known-limitations.md"
        body = limitations.read_text(encoding="utf-8")
        limitations.write_text(
            "# Known limitations\n\n" + body.split("## The portable core", 1)[1],
            encoding="utf-8",
        )
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "docs/known-limitations.md status marker is missing")


if __name__ == "__main__":
    unittest.main()
