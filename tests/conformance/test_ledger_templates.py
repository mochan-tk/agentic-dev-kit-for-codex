import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / ".github/scripts/check-ledger-templates.py"
CONTRACT_PATH = ".github/governance/ledger-contracts.v1.json"
FIXTURE_PATH = "tests/ledger/fixtures/ledger-valid.v1.json"
INPUTS = [
    ".github/ISSUE_TEMPLATE/ai-task.yml",
    ".github/ISSUE_TEMPLATE/epic.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    CONTRACT_PATH,
    FIXTURE_PATH,
    "tests/ledger/fixtures/epic-rendered.md",
    "tests/ledger/fixtures/pull-request-rendered.md",
    "tests/ledger/fixtures/task-rendered.md",
]


class LedgerTemplatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ledger_templates", CHECKER_PATH)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load checker: {CHECKER_PATH}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)
        cls.contract = json.loads((ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))
        cls.payload = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))

    def semantic_errors(self, payload=None, contract=None):
        errors = []
        self.checker.validate_records(
            copy.deepcopy(contract if contract is not None else self.contract),
            copy.deepcopy(payload if payload is not None else self.payload),
            errors,
        )
        return errors

    def contract_errors(self, contract):
        errors = []
        self.checker.validate_contract(copy.deepcopy(contract), errors)
        return errors

    def assert_error(self, errors, fragment):
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected {fragment!r} in errors:\n" + "\n".join(errors),
        )

    def copy_inputs(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in INPUTS:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return root

    def write_json(self, root, relative, value):
        (root / relative).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def payload_with_deferred_ac02(self):
        payload = copy.deepcopy(self.payload)
        pull_request = payload["records"]["pull_requests"][0]
        pull_request["evidence"] = [pull_request["evidence"][0]]
        pull_request["deferred_evidence"] = [
            {
                "id": "DE-01",
                "criterion_id": "AC-02",
                "reason": "The conformance receipt will be captured from the exact pull-request head.",
                "owner": "Repository owner",
                "follow_up_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9",
            }
        ]
        return payload

    def string_leaf_paths(self, value, prefix=()):
        if isinstance(value, str):
            yield prefix
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from self.string_leaf_paths(item, prefix + (index,))
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from self.string_leaf_paths(item, prefix + (key,))

    @staticmethod
    def set_path(value, path, replacement):
        target = value
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = replacement

    def test_repository_contract_templates_records_and_renderings_are_valid(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_checker_cli_reports_the_static_boundary(self):
        completed = subprocess.run(
            ["python3", "-I", str(CHECKER_PATH)],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("static validation boundary: OK", completed.stdout)

    def test_contract_has_exact_human_section_counts(self):
        records = self.contract["records"]
        self.assertEqual(5, len(records["epic"]["sections"]))
        self.assertEqual(8, len(records["task"]["sections"]))
        self.assertEqual(5, len(records["pull_request"]["sections"]))
        self.assertEqual(
            self.checker.EXPECTED_HEADINGS["task"],
            [section["heading"] for section in records["task"]["sections"]],
        )

    def test_issue_form_ui_groups_are_not_invented_in_submitted_body_oracles(self):
        self.assertEqual(
            {
                "issue_form_markdown_elements": "displayed-in-form-not-submitted",
                "submitted_issue_body": "field-label-headings-and-values-only",
                "empty_optional_input_or_textarea": "submitted-as-_No response_",
                "pull_request_template_headings": "persisted-markdown",
            },
            self.contract["rendering_semantics"],
        )
        hardcoded_labels = {
            "epic": [
                "Goal",
                "Scope",
                "Non-goals",
                "Task graph",
                "Dependency policy",
                "Acceptance criteria",
                "Evidence requirements",
                "Planning owner",
                "Control policy",
            ],
            "task": [
                "Objective",
                "Scope",
                "Acceptance criteria",
                "Parent Epic Issue URL",
                "Dependencies",
                "References",
                "Owned paths",
                "Risk tier",
                "Risk rationale",
                "Risk constraints",
                "Verification commands",
                "Evidence requirements",
                "Routing",
                "Execution",
                "Completion conditions",
                "Relationships",
                "Task execution envelope reference (optional and opaque)",
                "Loop event reference (optional and opaque)",
            ],
        }
        for kind, labels in hardcoded_labels.items():
            with self.subTest(kind=kind):
                rendered = (ROOT / f"tests/ledger/fixtures/{kind}-rendered.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("type:markdown groups are displayed in the form but not submitted", rendered)
                actual = [
                    line[4:]
                    for line in rendered.splitlines()
                    if line.startswith("### ")
                ]
                self.assertEqual(labels, actual)
                for section in self.checker.EXPECTED_HEADINGS[kind]:
                    self.assertNotIn(f"\n## {section}\n", rendered)

        task_rendered = (ROOT / "tests/ledger/fixtures/task-rendered.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, task_rendered.count("\n_No response_\n"))
        for heading in (
            "Task execution envelope reference (optional and opaque)",
            "Loop event reference (optional and opaque)",
        ):
            self.assertIn(f"### {heading}\n\n_No response_", task_rendered)

        root = self.copy_inputs()
        rendered_path = root / "tests/ledger/fixtures/task-rendered.md"
        rendered_path.write_text(
            rendered_path.read_text(encoding="utf-8").replace(
                "\n### Loop event reference (optional and opaque)\n\n_No response_\n",
                "\n",
            ),
            encoding="utf-8",
        )
        self.assert_error(self.checker.validate_repository(root), "not synchronized")

    def test_optional_dropdown_submitted_body_oracle_uses_none(self):
        contract_record = {
            "sections": [
                {
                    "fields": [
                        {
                            "id": "optional_dropdown",
                            "label": "Optional dropdown",
                            "type": "dropdown",
                            "required": False,
                        }
                    ]
                }
            ]
        }
        rendered = self.checker.render_record(
            "task",
            contract_record,
            {"issue_url": "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9"},
        )
        self.assertIn("### Optional dropdown\n\nNone\n", rendered)

    def test_issue_forms_and_pr_template_are_exact_contract_renderings(self):
        records = self.contract["records"]
        self.assertEqual(
            self.checker.render_issue_form(records["epic"]),
            (ROOT / records["epic"]["template_path"]).read_text(encoding="utf-8"),
        )
        self.assertEqual(
            self.checker.render_issue_form(records["task"]),
            (ROOT / records["task"]["template_path"]).read_text(encoding="utf-8"),
        )
        self.assertEqual(
            self.checker.render_pr_template(records["pull_request"]),
            (ROOT / records["pull_request"]["template_path"]).read_text(encoding="utf-8"),
        )

    def test_tests_ledger_contains_data_only(self):
        self.assertEqual([], sorted((ROOT / "tests/ledger").rglob("*.py")))

    def test_contract_preserves_bounded_progress_and_non_success_evidence_states(self):
        self.assertEqual(["pass"], self.contract["semantics"]["evidence_success_results"])
        self.assertIn("UNKNOWN", self.contract["semantics"]["evidence_results"])
        self.assertIn("UNCHECKABLE", self.contract["semantics"]["evidence_results"])
        self.assertEqual(
            {"C": "not-run", "E": "not-run", "O": "not-run", "T": "not-run", "X": "not-run"},
            self.contract["progress"]["scenario_families"],
        )
        self.assertEqual(
            ["K10", "K11"],
            self.contract["progress"]["contracts_advanced_minimal_partial_offline"],
        )
        self.assertEqual(
            "minimal-partial-offline-implemented",
            self.contract["implementation"]["K10"],
        )
        self.assertEqual(
            "minimal-partial-offline-implemented",
            self.contract["implementation"]["K11"],
        )
        self.assertEqual(
            "opaque-ref/v1:<field-kind>:sha256:<64-lowercase-hex>",
            self.contract["semantics"]["opaque_runtime_reference_format"],
        )

    def test_t11_history_and_t12_activation_frontier_are_exact(self):
        frontier = self.contract["runtime_frontier"]
        self.assertEqual("accepted", frontier["tree_snapshot"]["t11"])
        self.assertEqual("sole-active", frontier["tree_snapshot"]["t12"])
        self.assertEqual("t11-agreement-v2", frontier["t11_history"]["agreement"]["version"])
        self.assertEqual("bounded-non-success", frontier["t11_history"]["stage_a1"]["classification"])
        self.assertEqual("bounded-non-success", frontier["t11_history"]["stage_a2"]["classification"])
        self.assertEqual(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/25",
            frontier["t12_activation"]["task_issue"],
        )
        self.assertEqual(
            "active-in-this-tree", frontier["t12_activation"]["state"]
        )
        self.assertEqual(
            "b3f051da26ebba7e0d49b79917cffa81ec6e9c66d409029ffd0020d0211850ee",
            frontier["t12_activation"]["owner_amendment"]["body_sha256"],
        )
        self.assertFalse(frontier["t12_activation"]["compatibility_baseline"]["current_latest_stable_claimed"])
        self.assertFalse(frontier["t12_activation"]["invocation_boundary"]["backend_model_request_count_claimed"])

    def test_t11_history_and_t12_activation_fail_closed(self):
        cases = (
            (
                "T11 history",
                lambda frontier: frontier["t11_history"]["stage_a2"].__setitem__("aggregate_status", "pass"),
                "runtime frontier T11 history drifted",
            ),
            (
                "amendment",
                lambda frontier: frontier["t12_activation"]["owner_amendment"].__setitem__("body_sha256", "0" * 64),
                "runtime frontier T12 activation drifted",
            ),
            (
                "chronology",
                lambda frontier: frontier["t12_activation"]["receipt_chronology"].reverse(),
                "runtime frontier T12 activation drifted",
            ),
        )
        for label, mutation, fragment in cases:
            with self.subTest(label=label):
                contract = copy.deepcopy(self.contract)
                mutation(contract["runtime_frontier"])
                self.assert_error(self.contract_errors(contract), fragment)

    def test_unknown_and_uncheckable_are_valid_record_states_but_not_success(self):
        for state in ("UNKNOWN", "UNCHECKABLE"):
            with self.subTest(state=state):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["evidence"][0]["result"] = state
                self.assertEqual([], self.semantic_errors(payload))
                self.assertNotIn(state, self.contract["semantics"]["evidence_success_results"])

    def test_contract_rejects_option_b_authority_drift(self):
        contract = copy.deepcopy(self.contract)
        contract["authority"]["github_projects_board"] = "canonical-authority"
        self.assert_error(self.contract_errors(contract), "Option B")

    def test_contract_rejects_k10_or_k11_full_implementation_claims(self):
        for contract_id in ("K10", "K11"):
            with self.subTest(contract_id=contract_id):
                contract = copy.deepcopy(self.contract)
                contract["implementation"][contract_id] = "fully-implemented"
                self.assert_error(
                    self.contract_errors(contract), "minimal/partial offline"
                )

    def test_contract_prose_rejects_positive_authority_and_implementation_claims(self):
        for statement, fragment in (
            ("GitHub Projects board is authoritative.", "must not grant authority"),
            ("K10 is implemented.", "must limit K10 or K11"),
        ):
            with self.subTest(statement=statement):
                contract = copy.deepcopy(self.contract)
                contract["records"]["task"]["sections"][0]["fields"][0][
                    "description"
                ] = statement
                self.assert_error(self.contract_errors(contract), fragment)

        for statement in (
            "GitHub Projects board is not authoritative.",
            "K10 is not implemented.",
            "K10 is minimal/partial offline only.",
        ):
            with self.subTest(statement=statement):
                contract = copy.deepcopy(self.contract)
                contract["records"]["task"]["sections"][0]["fields"][0][
                    "description"
                ] = statement
                self.assertEqual([], self.contract_errors(contract))

    def test_contract_rejects_scenario_pass_claim(self):
        contract = copy.deepcopy(self.contract)
        contract["progress"]["scenario_families"]["C"] = "pass"
        self.assert_error(self.contract_errors(contract), "scenarios not-run")

    def test_contract_rejects_bootstrap_history_synthesis(self):
        contract = copy.deepcopy(self.contract)
        contract["bootstrap_compatibility"]["historical_ritual_synthesis"] = True
        self.assert_error(self.contract_errors(contract), "must not synthesize history")

    def test_contract_keeps_narrow_bootstrap_heading_alias(self):
        aliases = self.contract["bootstrap_compatibility"]["static_heading_aliases"]
        self.assertEqual(
            ["Task graph and dependencies"],
            aliases["epic.decomposition_and_dependency_graph"],
        )
        self.assertEqual(
            ["Objective", "Rationale", "Out of scope"],
            aliases["task.objective_and_scope"],
        )
        self.assertEqual(
            ["Contract and conformance coverage", "Completion boundary"],
            aliases["task.completion_and_relationships"],
        )

    def test_frozen_bootstrap_issue_bodies_map_to_every_conceptual_section(self):
        snapshots = self.payload["bootstrap_snapshots"]
        self.assertEqual("read-only GitHub Issue API body snapshot", snapshots["source"])
        self.assertEqual(["epic", "task"], [item["kind"] for item in snapshots["issues"]])
        for snapshot in snapshots["issues"]:
            with self.subTest(kind=snapshot["kind"]):
                expected = self.checker.EXPECTED_BOOTSTRAP_SNAPSHOTS[snapshot["kind"]]
                self.assertEqual(expected["body_sha256"], snapshot["body_sha256"])
                self.assertEqual(expected["ordered_headings"], snapshot["ordered_headings"])
                self.assertEqual(
                    {section["id"] for section in self.contract["records"][snapshot["kind"]]["sections"]},
                    {mapping["section_id"] for mapping in snapshot["heading_mapping"]},
                )
        self.assertEqual([], self.semantic_errors())

    def test_bootstrap_compatibility_rejects_body_mapping_and_alias_drift(self):
        payload = copy.deepcopy(self.payload)
        snapshot = payload["bootstrap_snapshots"]["issues"][0]
        snapshot["body"] = snapshot["body"].replace("## Acceptance", "## Changed", 1)
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "body does not match body_sha256")
        self.assert_error(errors, "ordered_headings must exactly match")

        payload = copy.deepcopy(self.payload)
        mappings = payload["bootstrap_snapshots"]["issues"][1]["heading_mapping"]
        mappings[0], mappings[1] = mappings[1], mappings[0]
        self.assert_error(self.semantic_errors(payload), "out of frozen-body order")

        payload = copy.deepcopy(self.payload)
        mappings = payload["bootstrap_snapshots"]["issues"][1]["heading_mapping"]
        mappings[1] = copy.deepcopy(mappings[0])
        self.assert_error(self.semantic_errors(payload), "contains duplicate headings")

        payload = copy.deepcopy(self.payload)
        mapping = payload["bootstrap_snapshots"]["issues"][1]["heading_mapping"][0]
        mapping["heading"] = "Unknown legacy heading"
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "not allowed by the canonical heading or alias contract")
        self.assert_error(errors, "missing, unknown, or unmapped headings")

        payload = copy.deepcopy(self.payload)
        mappings = payload["bootstrap_snapshots"]["issues"][1]["heading_mapping"]
        del mappings[8]
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "missing, unknown, or unmapped headings")
        self.assert_error(errors, "leaves required groups unmapped")

        payload = copy.deepcopy(self.payload)
        mapping = payload["bootstrap_snapshots"]["issues"][1]["heading_mapping"][0]
        mapping["section_id"] = "unknown_section"
        self.assert_error(self.semantic_errors(payload), "section_id is unknown")

        contract = copy.deepcopy(self.contract)
        del contract["bootstrap_compatibility"]["static_heading_aliases"][
            "epic.decomposition_and_dependency_graph"
        ]
        self.assert_error(
            self.semantic_errors(contract=contract),
            "not allowed by the canonical heading or alias contract",
        )

    def test_contract_rejects_field_order_type_required_label_and_options_drift(self):
        mutations = []
        contract = copy.deepcopy(self.contract)
        fields = contract["records"]["task"]["sections"][0]["fields"]
        fields.reverse()
        mutations.append((contract, "ordered field layout"))
        contract = copy.deepcopy(self.contract)
        contract["records"]["task"]["sections"][0]["fields"][0]["type"] = "input"
        mutations.append((contract, "ordered field layout"))
        contract = copy.deepcopy(self.contract)
        contract["records"]["task"]["sections"][0]["fields"][0]["required"] = False
        mutations.append((contract, "ordered field layout"))
        contract = copy.deepcopy(self.contract)
        contract["records"]["task"]["sections"][0]["fields"][0]["label"] = "Changed"
        mutations.append((contract, ".label drifted"))
        contract = copy.deepcopy(self.contract)
        contract["records"]["task"]["sections"][4]["fields"][0]["options"] = ["A", "B"]
        mutations.append((contract, ".options must be exactly A-D"))
        contract = copy.deepcopy(self.contract)
        contract["records"]["task"]["sections"][0]["fields"][0]["id"] = ["objective"]
        mutations.append((contract, ".id is invalid"))
        for contract, fragment in mutations:
            with self.subTest(fragment=fragment):
                self.assert_error(self.contract_errors(contract), fragment)

    def test_template_and_rendered_fixture_drift_fail_repository_validation(self):
        for relative in (
            ".github/ISSUE_TEMPLATE/epic.yml",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "tests/ledger/fixtures/task-rendered.md",
        ):
            with self.subTest(relative=relative):
                root = self.copy_inputs()
                path = root / relative
                path.write_text(path.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
                self.assert_error(self.checker.validate_repository(root), "not synchronized")

    def test_missing_dependency_declaration_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        del payload["records"]["tasks"][0]["dependencies"]
        self.assert_error(self.semantic_errors(payload), "missing required fields: dependencies")

    def test_dependency_link_must_be_same_repository(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["epic"]["task_graph"][1]["dependencies"] = [
            "https://github.com/other/repository/issues/8"
        ]
        self.assert_error(self.semantic_errors(payload), "same-repository Issue URL")

    def test_dependency_graph_rejects_unknown_self_duplicate_and_cycle(self):
        mutations = []
        payload = copy.deepcopy(self.payload)
        payload["records"]["epic"]["task_graph"][1]["dependencies"] = [
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/77"
        ]
        mutations.append((payload, "unknown Task node"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["epic"]["task_graph"][1]["dependencies"] = [
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9"
        ]
        mutations.append((payload, "depends on itself"))
        payload = copy.deepcopy(self.payload)
        dependency = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
        payload["records"]["epic"]["task_graph"][1]["dependencies"] = [dependency, dependency]
        mutations.append((payload, "duplicate dependency links"))
        payload = copy.deepcopy(self.payload)
        issue8 = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
        issue9 = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9"
        payload["records"]["epic"]["task_graph"][0]["dependencies"] = [issue9]
        payload["records"]["tasks"][1]["dependencies"] = [issue9]
        mutations.append((payload, "dependency cycle"))
        for payload, fragment in mutations:
            with self.subTest(fragment=fragment):
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_task_dependencies_must_match_epic_graph(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["dependencies"] = "None"
        self.assert_error(self.semantic_errors(payload), "must exactly match the Epic Task graph")

    def test_reverse_ordered_long_dependency_chain_is_bounded_and_non_recursive(self):
        repository = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/"
        nodes = []
        for number in range(2099, 999, -1):
            dependencies = "None" if number == 1000 else [repository + str(number - 1)]
            nodes.append({"task_url": repository + str(number), "dependencies": dependencies})
        self.assertLess(len(json.dumps(nodes).encode("utf-8")), self.checker.MAX_FILE_BYTES)
        errors = []
        graph = self.checker.validate_task_graph(nodes, errors)
        self.assertEqual(1100, len(graph))
        self.assertEqual([], errors)

    def test_invalid_risk_tier_rationale_and_constraints_are_rejected(self):
        mutations = []
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["risk_tier"] = "E"
        mutations.append((payload, "risk_tier must be one of"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["risk_rationale"] = ""
        mutations.append((payload, "risk_rationale must be"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["risk_constraints"] = []
        mutations.append((payload, "risk_constraints must be a non-empty list"))
        for payload, fragment in mutations:
            with self.subTest(fragment=fragment):
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_ownership_rejects_malformed_paths_modes_and_unsupported_globs(self):
        cases = [
            ("../escape", "is not normalized"),
            ("/absolute/path", "relative slash-separated"),
            ("bad\\path", "relative slash-separated"),
            ("C:/outside", "Windows drive or UNC syntax"),
            ("C:\\outside", "Windows drive or UNC syntax"),
            ("//server/share", "Windows drive or UNC syntax"),
            ("\\\\server\\share", "Windows drive or UNC syntax"),
            ("tests/*.json", "terminal /**"),
            ("tests//ledger", "is not normalized"),
            ("tests/ledger\u200b/file", "control or format character"),
            ("dir/name.", "Windows-ambiguous dot or space"),
            ("dir/name ", "trimmed string"),
            ("dir /name", "Windows-ambiguous dot or space"),
            ("dir/name:stream", "Windows-reserved path character"),
            ("dir/CON", "Windows-reserved device component"),
            ("dir/com1.txt", "Windows-reserved device component"),
        ]
        for pattern, fragment in cases:
            with self.subTest(pattern=pattern):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0]["ownership"][0]["pattern"] = pattern
                self.assert_error(self.semantic_errors(payload), fragment)
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["ownership"][0]["mode"] = "120000"
        self.assert_error(self.semantic_errors(payload), ".mode is invalid")

    def test_ownership_rejects_non_nfc_case_and_prefix_overlap(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["ownership"][0]["pattern"] = "tests/cafe\u0301.md"
        self.assert_error(self.semantic_errors(payload), "NFC Unicode normalization")

        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][1]["ownership"].append(
            {"pattern": ".GITHUB/issue_template/example.yml", "mode": "100644"}
        )
        self.assert_error(self.semantic_errors(payload), "ownership overlap")

        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["ownership"].append(
            {"pattern": "tests/ledger/fixtures/example.json", "mode": "100644"}
        )
        self.assert_error(self.semantic_errors(payload), "ownership overlap")

    def test_missing_or_invalid_primary_task_relationship_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        del payload["records"]["pull_requests"][0]["task_url"]
        self.assert_error(self.semantic_errors(payload), "missing required fields: task_url")

        payload = copy.deepcopy(self.payload)
        del payload["records"]["pull_requests"][0]["task_relationship"]
        self.assert_error(
            self.semantic_errors(payload), "missing required fields: task_relationship"
        )

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["task_url"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/77"
        )
        self.assert_error(self.semantic_errors(payload), "identify exactly one ledger Task")

    def test_pr_task_relationship_requires_controlled_disposition_and_matching_url(self):
        task_url = self.payload["records"]["pull_requests"][0]["task_url"]
        for value in (
            task_url,
            f"Fixes {task_url}",
            f"closes {task_url}",
        ):
            with self.subTest(value=value):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["task_relationship"] = value
                self.assert_error(self.semantic_errors(payload), "exactly Closes or Refs")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["task_relationship"] = (
            "Refs https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
        )
        self.assert_error(self.semantic_errors(payload), "Task URL must match task_url")

        for disposition in ("Closes", "Refs"):
            with self.subTest(disposition=disposition):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["task_relationship"] = (
                    f"{disposition} {task_url}"
                )
                self.assertEqual([], self.semantic_errors(payload))

    def test_task_primary_pr_and_pr_task_url_must_be_bidirectional_and_unambiguous(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["relationships"]["primary_pr"] = "None"
        self.assert_error(self.semantic_errors(payload), "not reciprocated")

        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][1]["relationships"]["primary_pr"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/pull/999"
        )
        self.assert_error(self.semantic_errors(payload), "conflicting Tasks claim")

        payload = copy.deepcopy(self.payload)
        pull_request = payload["records"]["pull_requests"][0]
        issue8 = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8"
        pull_request["task_url"] = issue8
        pull_request["task_relationship"] = f"Refs {issue8}"
        pull_request["plan_comment_url"] = f"{issue8}#issuecomment-5404518469"
        self.assert_error(self.semantic_errors(payload), "primary_pr and PR task_url disagree")

    def test_plan_comment_must_be_concrete_and_belong_to_primary_task(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["plan_comment_url"] = "<plan-comment-url>"
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "placeholder value")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["plan_comment_url"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/8#issuecomment-5404518469"
        )
        self.assert_error(self.semantic_errors(payload), "must belong to the primary Task")

    def test_evidence_rejects_missing_fields_invalid_results_and_external_urls(self):
        payload = copy.deepcopy(self.payload)
        del payload["records"]["pull_requests"][0]["evidence"][0]["observed_at"]
        self.assert_error(self.semantic_errors(payload), "missing required fields: observed_at")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["result"] = "pass (untested)"
        self.assert_error(self.semantic_errors(payload), ".result is invalid")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["evidence_url"] = (
            "https://example.net/evidence"
        )
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "same-repository commit/check URL or Actions run/job URL")

    def test_evidence_url_binding_and_offline_actions_boundary_are_explicit(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["evidence_url"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/commit/"
            + "f" * 40
            + "/checks"
        )
        self.assert_error(self.semantic_errors(payload), "embedded commit SHA")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["evidence_url"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/actions/runs/123/job/456"
        )
        self.assertEqual([], self.semantic_errors(payload))
        self.assertIn(
            "Actions run or job URL association with the declared head SHA",
            self.contract["validation_boundary"]["not_validated_offline"],
        )

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["evidence_url"] = (
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9"
        )
        self.assert_error(
            self.semantic_errors(payload),
            "same-repository commit/check URL or Actions run/job URL",
        )

    def test_evidence_rejects_empty_table_stale_head_and_non_utc_time(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"] = []
        self.assert_error(self.semantic_errors(payload), "evidence must be a non-empty list")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["head_sha"] = "0" * 40
        self.assert_error(self.semantic_errors(payload), "must match the exact pull-request head")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["observed_at"] = (
            "2026-08-25T03:04:41+09:00"
        )
        self.assert_error(self.semantic_errors(payload), "ending in Z")

    def test_deferred_evidence_requires_reason_owner_and_follow_up(self):
        for field in ("id", "criterion_id", "reason", "owner", "follow_up_url"):
            with self.subTest(field=field):
                payload = self.payload_with_deferred_ac02()
                del payload["records"]["pull_requests"][0]["deferred_evidence"][0][field]
                self.assert_error(self.semantic_errors(payload), f"missing required fields: {field}")
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["deferred_evidence"] = "None"
        self.assertEqual([], self.semantic_errors(payload))

        self.assertEqual([], self.semantic_errors(self.payload_with_deferred_ac02()))

    def test_pr_evidence_exactly_covers_task_criteria_without_id_collisions(self):
        payload = copy.deepcopy(self.payload)
        del payload["records"]["pull_requests"][0]["evidence"][1]
        self.assert_error(self.semantic_errors(payload), "missing Task criteria: AC-02")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][1]["criterion_id"] = "AC-77"
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "missing Task criteria: AC-02")
        self.assert_error(errors, "unknown Task criteria: AC-77")

        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][1]["criterion_id"] = "AC-01"
        self.assert_error(self.semantic_errors(payload), "duplicate criterion ID AC-01")

        payload = self.payload_with_deferred_ac02()
        payload["records"]["pull_requests"][0]["deferred_evidence"][0]["id"] = "EV-01"
        self.assert_error(self.semantic_errors(payload), "evidence IDs collide")

        payload = self.payload_with_deferred_ac02()
        payload["records"]["pull_requests"][0]["evidence"].append(
            copy.deepcopy(self.payload["records"]["pull_requests"][0]["evidence"][1])
        )
        self.assert_error(self.semantic_errors(payload), "both evidenced and deferred: AC-02")

    def test_github_projects_authority_historical_ritual_and_k10_k11_claims_fail(self):
        cases = [
            ("execution", "A GitHub Projects board is authoritative.", "must not grant authority"),
            (
                "execution",
                "The canonical source of truth is the GitHub Projects board.",
                "must not grant authority",
            ),
            (
                "execution",
                "Use the GitHub Projects board as truth for completion.",
                "must not grant authority",
            ),
            (
                "execution",
                "Treat the GitHub Projects board as authoritative.",
                "must not grant authority",
            ),
            (
                "execution",
                "The GitHub Projects board determines completion.",
                "must not grant authority",
            ),
            (
                "execution",
                "GitHub Project -> Epic Issue -> Task Issue -> PR is canonical.",
                "must not grant authority",
            ),
            (
                "execution",
                "Project Record -> Epic Issue -> Task Issue -> PR is canonical.",
                "must not grant authority",
            ),
            (
                "execution",
                "The board outranks the Issue graph; GitHub Projects renders it.",
                "must not grant authority",
            ),
            (
                "execution",
                "The GitHub Projects board supersedes the Issue graph.",
                "must not grant authority",
            ),
            (
                "execution",
                "The GitHub Projects board has final authority.",
                "must not grant authority",
            ),
            (
                "execution",
                "A Project board is authoritative under Option B.",
                "must not grant authority",
            ),
            (
                "execution",
                "The Project board is the source of truth.",
                "must not grant authority",
            ),
            ("routing", "The historical ritual was verified.", "must not fabricate historical ritual"),
            (
                "routing",
                "Recorded the bootstrap plan and dispatch as historically complete.",
                "must not fabricate bootstrap ritual",
            ),
            ("execution", "K10 is implemented and enforced.", "must limit K10 or K11"),
            ("execution", "Support is complete for K11.", "must limit K10 or K11"),
            ("execution", "K10 is fully working now.", "must limit K10 or K11"),
            ("execution", "K11 is ready for production.", "must limit K10 or K11"),
            ("execution", "K10 works in this repository.", "must limit K10 or K11"),
            ("execution", "K11 functionality is present.", "must limit K10 or K11"),
            (
                "execution",
                "K10 is minimal offline implemented across every runtime surface.",
                "must limit K10 or K11",
            ),
            (
                "execution",
                "K10 is minimal offline implemented.",
                "must limit K10 or K11",
            ),
            (
                "execution",
                "K11 is minimal-partial-offline-implemented with full cross-surface parity.",
                "must limit K10 or K11",
            ),
            (
                "execution",
                "Implemented Task execution envelope for every Task.",
                "must limit the Task execution envelope",
            ),
            (
                "execution",
                "We built the Task execution envelope.",
                "must limit the Task execution envelope",
            ),
            ("execution", "The loop-event contract is implemented.", "must limit the loop-event"),
            (
                "execution",
                "Implemented loop-event support for every Task.",
                "must limit the loop-event",
            ),
            (
                "execution",
                "An opaque task execution envelope reference proves validity and execution.",
                "must limit the Task execution envelope",
            ),
            (
                "execution",
                "The loop-event contract is minimal offline implementation for every client and surface.",
                "must limit the loop-event",
            ),
            (
                "execution",
                "The loop-event contract is minimal offline implementation.",
                "must limit the loop-event",
            ),
            ("routing", "A backfilled plan comment records the old dispatch.", "must not fabricate historical ritual"),
            (
                "routing",
                "We created the bootstrap plan comment retroactively.",
                "must not fabricate bootstrap ritual",
            ),
            ("routing", "Created the bootstrap plan comment.", "must not fabricate bootstrap ritual"),
            ("routing", "Posted the bootstrap dispatch receipt.", "must not fabricate bootstrap ritual"),
            ("routing", "Added bootstrap evidence comments.", "must not fabricate bootstrap ritual"),
            (
                "routing",
                "The bootstrap plan comment was created.",
                "must not fabricate bootstrap ritual",
            ),
        ]
        for field, value, fragment in cases:
            with self.subTest(value=value):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0][field] = value
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_truthful_option_b_and_bounded_runtime_statements_are_accepted(self):
        statements = [
            "The GitHub Projects board is not authoritative; the Issue graph is canonical.",
            "A GitHub Projects board is an optional projection and never outranks the Issue graph.",
            "Do not make a Project board authoritative under Option B.",
            "Repository Initiative / Epic Set -> Epic Issue -> Task Issue -> PR is canonical; the board is optional.",
            "K10 is not implemented.",
            "K10 has not been implemented.",
            "K11 remains planned-unimplemented.",
            "K10 is minimal/partial offline only.",
            "K11 has a minimal partial offline implementation only.",
            "K10 is implemented only for the bounded offline T11 slice.",
            "The Task execution envelope is not implemented.",
            "No Task execution envelope is implemented.",
            "Loop-event support is not implemented.",
            "No loop-event support is implemented.",
            "The Task execution envelope is minimal/partial offline T11 support only.",
            "Loop-event support is implemented only for the bounded offline T11 slice.",
            "task-execution-envelope/v1 is minimal/partial offline T11 implementation only.",
            "loop-event/v1 is implemented only for the bounded offline T11 slice.",
            "The bootstrap plan was not recorded.",
            "No historical ritual was recorded.",
            "The bootstrap plan comment was not created retroactively.",
            "The bootstrap plan comment was not created.",
        ]
        for statement in statements:
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0]["execution"] = statement
                self.assertEqual([], self.semantic_errors(payload))

    def test_canonical_runtime_contract_names_reject_full_or_cross_surface_claims(self):
        for statement, fragment in (
            (
                "task-execution-envelope/v1 is fully implemented and accepted.",
                "must limit the Task execution envelope",
            ),
            (
                "loop-event/v1 has full cross-surface runtime parity.",
                "must limit the loop-event",
            ),
            (
                "task-execution-envelope/v1 is generalized for every Task.",
                "must limit the Task execution envelope",
            ),
        ):
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0]["execution"] = statement
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_safe_boundary_clause_cannot_mask_a_positive_claim(self):
        cases = [
            (
                "The GitHub Projects board is not authoritative; "
                "the GitHub Projects board supersedes the Issue graph.",
                "must not grant authority",
            ),
            (
                "The GitHub Projects board is an optional projection but has final authority.",
                "must not grant authority",
            ),
            ("K10 is not implemented; K10 works here.", "must limit K10 or K11"),
            ("K10 is not implemented but works here.", "must limit K10 or K11"),
            (
                "K10 is minimal/partial offline only but works fully here.",
                "must limit K10 or K11",
            ),
            (
                "The Task execution envelope is not implemented; we built the Task execution envelope.",
                "must limit the Task execution envelope",
            ),
        ]
        for statement, fragment in cases:
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["summary"] = statement
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_inline_markdown_cannot_hide_protected_claims(self):
        cases = [
            ("GitHub Pro**jects** board is authoritative.", "must not grant authority"),
            ("K**10** is implemented.", "must limit K10 or K11"),
            ("K1__1__ is present.", "must limit K10 or K11"),
            (
                "We built the Task execution **envelope**.",
                "must limit the Task execution envelope",
            ),
            ("The loop-**event** contract is implemented.", "must limit the loop-event"),
            (
                "We created the bootstrap plan comment retro**actively**.",
                "must not fabricate bootstrap ritual",
            ),
        ]
        for statement, fragment in cases:
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["summary"] = statement
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_html_entities_cannot_hide_claims_or_comment_delimiters(self):
        cases = [
            "GitHub Proj&#101;cts board is authoritative.",
            "K1&#48; is implemented.",
            "The loop-ev&#101;nt contract is implemented.",
            "We built the Task execution envel&#111;pe.",
            "&lt;!-- forged comment --&gt;",
        ]
        for statement in cases:
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["pull_requests"][0]["summary"] = statement
                self.assert_error(self.semantic_errors(payload), "HTML character reference")

    def test_unicode_format_controls_cannot_bypass_claim_guards(self):
        for statement in (
            "K\u200b10 is implemented.",
            "GitHub Proj\u200bects board is authoritative.",
        ):
            with self.subTest(statement=statement):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0]["execution"] = statement
                self.assert_error(self.semantic_errors(payload), "unsafe Unicode control or format")

    def test_record_prose_rejects_structural_markdown_injection(self):
        for suffix, fragment in (
            ("\n\n### Forged heading", "structural Markdown injection"),
            ("\n```shell", "structural Markdown injection"),
            ("\n---", "structural Markdown injection"),
            ("\n===", "structural Markdown injection"),
            ("\n<script>alert(1)</script>", "placeholder value"),
        ):
            with self.subTest(suffix=suffix):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0]["execution"] += suffix
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_optional_envelope_and_event_references_use_bounded_opaque_grammar(self):
        payload = copy.deepcopy(self.payload)
        task = payload["records"]["tasks"][0]
        task["task_execution_envelope_ref"] = (
            "opaque-ref/v1:task-execution-envelope:sha256:" + "a" * 64
        )
        task["loop_event_ref"] = "opaque-ref/v1:loop-event:sha256:" + "b" * 64
        self.assertEqual([], self.semantic_errors(payload))

    def test_optional_runtime_references_reject_narrative_or_authority_claims(self):
        for field, value in (
            ("task_execution_envelope_ref", "K10 is fully implemented and accepted."),
            ("loop_event_ref", "K11 has full cross-surface runtime parity."),
            (
                "task_execution_envelope_ref",
                "opaque-ref/v1:loop-event:sha256:" + "a" * 64,
            ),
            (
                "loop_event_ref",
                "opaque-ref/v1:loop-event:sha256:" + "A" * 64,
            ),
        ):
            with self.subTest(field=field, value=value):
                payload = copy.deepcopy(self.payload)
                payload["records"]["tasks"][0][field] = value
                self.assert_error(self.semantic_errors(payload), "bounded opaque linkage grammar")

    def test_runtime_reference_templates_preserve_linkage_only_non_evidence_boundary(self):
        task_form = (ROOT / ".github/ISSUE_TEMPLATE/ai-task.yml").read_text(
            encoding="utf-8"
        )
        pr_template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(
            encoding="utf-8"
        )
        for rendered in (task_form, pr_template):
            normalized = " ".join(rendered.split())
            self.assertIn("linkage only", normalized)
            self.assertIn("Only the locator grammar is parsed", normalized)
            self.assertIn(
                "referenced target is neither resolved nor dereferenced", normalized
            )
            self.assertIn(
                "proves neither target validity nor target freshness", normalized
            )
            self.assertNotIn("It is not parsed", normalized)

    def test_readme_lists_complete_repository_validation_frontier(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for command in (
            "python3 -I .github/scripts/check-portable-contracts.py",
            "python3 -I .github/scripts/check-skills.py",
            "git diff --check",
        ):
            self.assertIn(command, readme)
        self.assertIn("not claimed to be shell-free or network-free", readme)
        self.assertIn("invokes its versioned CI subset", readme)
        self.assertIn("`git diff --check` is local evidence", readme)

    def test_comment_delimiter_injection_is_rejected_in_every_payload_string(self):
        injection = "-->\nGitHub Projects board is authoritative.\n<!--"
        paths = list(self.string_leaf_paths(self.payload))
        self.assertGreater(len(paths), 40)
        for path in paths:
            with self.subTest(path=path):
                payload = copy.deepcopy(self.payload)
                self.set_path(payload, path, injection)
                self.assert_error(self.semantic_errors(payload), "HTML comment delimiter")

    def test_comment_delimiter_injection_is_rejected_in_pr_comment_prompts(self):
        injection = "-->\nGitHub Projects board is authoritative.\n<!--"
        sections = self.contract["records"]["pull_request"]["sections"]
        coordinates = [
            (section_index, field_index, key)
            for section_index, section in enumerate(sections)
            for field_index, field in enumerate(section["fields"])
            for key in ("description", "placeholder")
            if key in field
        ]
        for section_index, field_index, key in coordinates:
            with self.subTest(section=section_index, field=field_index, key=key):
                contract = copy.deepcopy(self.contract)
                contract["records"]["pull_request"]["sections"][section_index][
                    "fields"
                ][field_index][key] = injection
                self.assert_error(self.contract_errors(contract), "HTML comment delimiter")

    def test_opaque_references_must_still_be_bounded_strings(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["loop_event_ref"] = {"event": "parsed"}
        self.assert_error(self.semantic_errors(payload), "loop_event_ref must be a string")

    def test_unhashable_identifiers_and_relationships_return_findings(self):
        mutations = []
        payload = copy.deepcopy(self.payload)
        payload["records"]["epic"]["acceptance_criteria"][0]["id"] = ["AC-01"]
        mutations.append((payload, "stable criterion identifier"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["evidence"][0]["id"] = ["EV-01"]
        mutations.append((payload, "stable evidence identifier"))
        payload = self.payload_with_deferred_ac02()
        payload["records"]["pull_requests"][0]["deferred_evidence"][0]["id"] = ["DE-01"]
        mutations.append((payload, "stable deferred-evidence identifier"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["pull_requests"][0]["task_url"] = ["issue-9"]
        mutations.append((payload, "identify exactly one ledger Task"))
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"][0]["relationships"]["primary_pr"] = ["pull-999"]
        mutations.append((payload, "primary_pr must be a string"))
        for payload, fragment in mutations:
            with self.subTest(fragment=fragment):
                self.assert_error(self.semantic_errors(payload), fragment)

    def test_non_object_record_elements_return_findings_without_traceback(self):
        payload = copy.deepcopy(self.payload)
        payload["records"]["tasks"].append([])
        payload["records"]["pull_requests"].append([])
        errors = self.semantic_errors(payload)
        self.assert_error(errors, "tasks[2] must be an object")
        self.assert_error(errors, "pull_requests[1] must be an object")

    def test_duplicate_cross_reference_collections_are_rejected(self):
        payload = copy.deepcopy(self.payload)
        reference = payload["records"]["tasks"][0]["references"][0]
        payload["records"]["tasks"][0]["references"].append(reference)
        self.assert_error(self.semantic_errors(payload), "references contains duplicate values")

    def test_iterative_string_walk_handles_deep_values_without_traceback(self):
        payload = copy.deepcopy(self.payload)
        nested = "leaf"
        for _ in range(1500):
            nested = [nested]
        payload["unexpected"] = nested
        errors = []
        self.checker.validate_records(self.contract, payload, errors)
        self.assert_error(errors, "unsupported fields: unexpected")

    def test_static_validation_boundary_rejects_capability_overclaim(self):
        contract = copy.deepcopy(self.contract)
        contract["validation_boundary"]["validated_offline"].append(
            "GitHub plan-comment authorship and chronology"
        )
        self.assert_error(self.contract_errors(contract), "overclaims proof")

    def test_fixed_inputs_reject_symlink_fifo_oversize_and_duplicate_json_keys(self):
        root = self.copy_inputs()
        contract_path = root / CONTRACT_PATH
        target = root / "contract-target.json"
        contract_path.rename(target)
        contract_path.symlink_to(target)
        self.assert_error(self.checker.validate_repository(root), "cannot safely read")

        if hasattr(os, "mkfifo"):
            root = self.copy_inputs()
            contract_path = root / CONTRACT_PATH
            contract_path.unlink()
            os.mkfifo(contract_path)
            self.assert_error(self.checker.validate_repository(root), "not a regular file")

        root = self.copy_inputs()
        (root / CONTRACT_PATH).write_bytes(b" " * (self.checker.MAX_FILE_BYTES + 1))
        self.assert_error(self.checker.validate_repository(root), "exceeds size limit")

        root = self.copy_inputs()
        (root / CONTRACT_PATH).write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
        self.assert_error(self.checker.validate_repository(root), "duplicate JSON key")

        root = self.copy_inputs()
        deeply_nested = "[" * 2000 + '"leaf"' + "]" * 2000
        (root / CONTRACT_PATH).write_text(deeply_nested, encoding="utf-8")
        self.assert_error(self.checker.validate_repository(root), "nesting depth exceeds")

    def test_json_nesting_limit_has_an_explicit_cross_platform_boundary(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        at_limit = "leaf"
        for _ in range(self.checker.MAX_JSON_NESTING_DEPTH):
            at_limit = [at_limit]
        self.write_json(root, "at-limit.json", at_limit)
        self.assertEqual(at_limit, self.checker.load_json(root, "at-limit.json"))

        over_limit = [at_limit]
        self.write_json(root, "over-limit.json", over_limit)
        with self.assertRaisesRegex(ValueError, "nesting depth exceeds"):
            self.checker.load_json(root, "over-limit.json")

    def test_safe_reader_fails_closed_when_required_platform_flags_are_unavailable(self):
        for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
            with self.subTest(flag=flag), mock.patch.object(self.checker.os, flag, 0):
                root = self.copy_inputs()
                self.assert_error(
                    self.checker.validate_repository(root),
                    f"required platform flag {flag} is unavailable",
                )

    def test_safe_reader_rejects_input_parent_namespace_swap_after_file_open(self):
        root = self.copy_inputs()
        original_open = self.checker.os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            fd = original_open(path, flags, mode, dir_fd=dir_fd)
            if path == "ledger-contracts.v1.json" and dir_fd is not None and not swapped:
                swapped = True
                governance = root / ".github/governance"
                governance.rename(root / ".github/governance-old")
                governance.mkdir()
            return fd

        with mock.patch.object(self.checker.os, "open", side_effect=swapping_open):
            errors = self.checker.validate_repository(root)
        self.assertTrue(swapped)
        self.assert_error(errors, "repository directory binding changed")

    def test_pr_template_has_blank_prompts_and_honest_offline_boundary(self):
        text = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
        self.assertNotIn("issues/9", text)
        self.assertNotIn("issuecomment-5404518469", text)
        self.assertIsNone(re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text))
        self.assertIn("<!-- field:task_relationship", text)
        self.assertIn("|---|---|---|---|---|---|---|", text)
        self.assertIn("does not prove", text)
        self.assertIn("accepted minimal/partial offline T11 slice", text)
        self.assertIn("T12 live evidence is external GitHub", text)
        self.assertIn("opaque references do not prove validity", text)

        fixture = self.payload["records"]["pull_requests"][0]
        self.assertEqual(
            "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/9#issuecomment-5404518469",
            fixture["plan_comment_url"],
        )
        rendered = (ROOT / "tests/ledger/fixtures/pull-request-rendered.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(fixture["plan_comment_url"], rendered)
        self.assertIn(fixture["head_sha"], rendered)


if __name__ == "__main__":
    unittest.main()
