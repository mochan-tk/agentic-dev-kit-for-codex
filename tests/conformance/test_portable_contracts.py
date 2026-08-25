import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github/scripts/check-portable-contracts.py"
CONTRACT = "docs/agreements/portable-context-contract.v1.json"
CONNECTOR = ".github/connectors/connector-contract.v1.json"
OWNERSHIP = ".github/governance/phase-task-ownership.v1.json"
PIN = "docs/context/pins/PIN-0001.context-pin.v1.json"
REQ = "docs/agreements/requirements/REQ-0001.json"
DEC = "docs/agreements/decisions/DEC-0001.json"


class PortableContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("portable_contracts", CHECKER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load checker: {CHECKER}")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def read_json(self, root, relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def write_json(self, root, relative, payload):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "repository"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", str(ROOT), str(fixture)],
            check=True,
        )
        subprocess.run(["git", "checkout", "--quiet", "--detach", "HEAD"], cwd=fixture, check=True)
        ownership = self.read_json(ROOT, OWNERSHIP)
        active = [task for task in ownership["tasks"] if task["state"] == "active"]
        self.assertEqual(["T08"], [task["id"] for task in active])
        for entry in active[0]["owned_paths"]:
            source = ROOT / entry["path"]
            if not source.exists():
                continue
            target = fixture / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return fixture

    def errors_after(self, relative, mutate):
        root = self.copy_fixture()
        payload = self.read_json(root, relative)
        mutate(payload)
        self.write_json(root, relative, payload)
        return self.checker.validate_repository(root)

    def assert_error(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def recompute_pin(self, pin):
        pin["aggregate"]["sha256"] = hashlib.sha256(
            self.checker.canonical_pin_bytes(pin)
        ).hexdigest()

    def test_current_repository_passes(self):
        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_documented_isolated_unittest_command_is_runnable(self):
        if os.environ.get("PORTABLE_CONTRACT_SUBPROCESS") == "1":
            return
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests/conformance",
                "-p",
                "test_portable_contracts.py",
            ],
            cwd=ROOT,
            env={**os.environ, "PORTABLE_CONTRACT_SUBPROCESS": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK", result.stderr)

    def test_contract_uses_exact_types_and_preserves_completion_boundary(self):
        def mutate(payload):
            payload["completion"]["release_blocked"] = 1

        self.assert_error(self.errors_after(CONTRACT, mutate), "machine portable contract drifted")

        def claim_complete(payload):
            payload["completion"]["repository_complete"] = True

        self.assert_error(self.errors_after(CONTRACT, claim_complete), "machine portable contract drifted")

    def test_false_k10_k11_runtime_and_feedback_claims_are_rejected(self):
        for field, value in (
            ("K10", "implemented"),
            ("K11", "implemented"),
            ("live_task_ritual", "implemented"),
            ("runtime_adapter", "implemented"),
            ("K16", "feedback-transport-implemented"),
        ):
            with self.subTest(field=field):
                self.assert_error(
                    self.errors_after(CONTRACT, lambda payload, f=field, v=value: payload["implementation"].__setitem__(f, v)),
                    "machine portable contract drifted",
                )

    def test_references_are_linkage_only_not_pin_evidence(self):
        for field in ("proves_pin_validity", "proves_pin_freshness"):
            with self.subTest(field=field):
                self.assert_error(
                    self.errors_after(CONTRACT, lambda payload, f=field: payload["task_reference"].__setitem__(f, True)),
                    "machine portable contract drifted",
                )

    def test_connector_has_exact_operations_and_no_mandatory_service(self):
        for mutation in (
            lambda payload: payload["operations"].append(copy.deepcopy(payload["operations"][0])),
            lambda payload: payload["operations"].__setitem__(0, {**payload["operations"][0], "name": "vendor-discover"}),
            lambda payload: payload["dependencies"].__setitem__("mandatory_external_service", True),
            lambda payload: payload["dependencies"].__setitem__("mandatory_credential", True),
            lambda payload: payload["core_record"]["connector_specific_fields"].append("vendor_workspace"),
        ):
            self.assert_error(self.errors_after(CONNECTOR, mutation), "machine connector contract drifted")

    def test_unknown_and_uncheckable_are_never_success(self):
        for field in ("unknown_is_success", "uncheckable_is_success"):
            self.assert_error(
                self.errors_after(CONNECTOR, lambda payload, f=field: payload["evidence"].__setitem__(f, True)),
                "machine connector contract drifted",
            )

    def test_requirement_and_decision_ids_are_stable_unique_and_sorted(self):
        requirements = self.read_json(ROOT, "tests/contracts/fixtures/requirements-valid.v1.json")["records"]
        errors = []
        duplicate = copy.deepcopy(requirements)
        duplicate.append(copy.deepcopy(duplicate[0]))
        self.checker.validate_record_set(duplicate, "requirement", "requirements", errors)
        self.assert_error(errors, "reuses stable ID")

        decisions = self.read_json(ROOT, "tests/contracts/fixtures/decisions-valid.v1.json")["records"]
        errors = []
        reversed_records = list(reversed(copy.deepcopy(decisions)))
        self.checker.validate_record_set(reversed_records, "decision", "decisions", errors)
        self.assert_error(errors, "sorted by stable ID")

    def test_zero_malformed_and_filename_mismatched_ids_are_rejected(self):
        record = self.read_json(ROOT, REQ)
        record["id"] = "REQ-0000"
        errors = []
        self.checker.validate_record_set([record], "requirement", "requirements", errors)
        self.assert_error(errors, "invalid stable ID")

        for invalid in (True, 7, [], {}):
            with self.subTest(invalid=invalid):
                malformed = self.read_json(ROOT, REQ)
                malformed["id"] = invalid
                errors = []
                self.checker.validate_record_set([malformed], "requirement", "requirements", errors)
                self.assert_error(errors, "must be a string")

        root = self.copy_fixture()
        (root / REQ).rename(root / "docs/agreements/requirements/REQ-0002.json")
        errors = self.checker.validate_repository(root)
        self.assert_error(errors, "filename does not match stable ID")

    def test_wrong_container_and_scalar_types_return_errors_without_traceback(self):
        mutations = (
            lambda payload: payload.__setitem__("sources", {}),
            lambda payload: payload.__setitem__("aggregate", []),
            lambda payload: payload.__setitem__("verification", True),
            lambda payload: payload.__setitem__("repository", 1),
            lambda payload: payload.__setitem__("id", []),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                pin = self.read_json(ROOT, PIN)
                mutation(pin)
                errors = []
                self.checker.validate_pin_shape(pin, PIN, "pin", errors)
                self.assertTrue(errors)

    def test_repository_record_payloads_require_objects_without_traceback(self):
        for relative, kind in ((REQ, "requirement"), (DEC, "decision"), (PIN, "pin")):
            for payload in ([], 7, "scalar"):
                with self.subTest(relative=relative, payload=payload):
                    root = self.copy_fixture()
                    self.write_json(root, relative, payload)
                    errors = self.checker.validate_repository(root)
                    self.assert_error(errors, f"{kind} record must be an object")

            root = self.copy_fixture()
            self.write_json(root, relative, {"unexpected": "field"})
            errors = self.checker.validate_repository(root)
            self.assert_error(errors, "unsupported or missing fields")

    def test_supersedes_must_be_present_earlier_same_kind_and_nonforking(self):
        fixture = self.read_json(ROOT, "tests/contracts/fixtures/decisions-valid.v1.json")["records"]
        missing = copy.deepcopy(fixture)
        missing[1]["supersedes"] = ["DEC-0099"]
        errors = []
        self.checker.validate_record_set(missing, "decision", "decisions", errors)
        self.assert_error(errors, "earlier same-kind")
        self.assert_error(errors, "missing historical record")

        future = copy.deepcopy(fixture)
        future[0]["supersedes"] = ["DEC-0002"]
        errors = []
        self.checker.validate_record_set(future, "decision", "decisions", errors)
        self.assert_error(errors, "earlier same-kind")

        fork = copy.deepcopy(fixture)
        third = copy.deepcopy(fork[1])
        third["id"] = "DEC-0003"
        third["title"] = "Second competing replacement"
        fork.append(third)
        errors = []
        self.checker.validate_record_set(fork, "decision", "decisions", errors)
        self.assert_error(errors, "non-forking supersedes violations")

    def test_record_status_does_not_overclaim_premerge_acceptance(self):
        for relative, kind in ((REQ, "requirement"), (DEC, "decision")):
            record = self.read_json(ROOT, relative)
            record["status"] = "accepted"
            errors = []
            self.checker.validate_record_set([record], kind, kind, errors)
            self.assert_error(errors, "accepted-on-owner-merge")

    def test_req0001_keeps_exact_frozen_source_references(self):
        root = self.copy_fixture()
        record = self.read_json(root, REQ)
        record["source_references"][0] = "https://github.com/example/example/blob/" + "0" * 40 + "/README.md"
        self.write_json(root, REQ, record)
        fixture = self.read_json(root, "tests/contracts/fixtures/requirements-valid.v1.json")
        fixture["records"][0] = copy.deepcopy(record)
        self.write_json(root, "tests/contracts/fixtures/requirements-valid.v1.json", fixture)
        self.assert_error(
            self.checker.validate_repository(root),
            "REQ-0001 source references drifted from the frozen source mapping",
        )

    def test_privacy_forbidden_fields_and_private_paths_are_rejected(self):
        record = self.read_json(ROOT, REQ)
        record["raw_log"] = "output"
        errors = []
        self.checker.validate_record_set([record], "requirement", "requirements", errors)
        self.assert_error(errors, "forbidden durable field")

        record = self.read_json(ROOT, REQ)
        record["statement"] = "Read /Users/example/private.txt"
        errors = []
        self.checker.validate_record_set([record], "requirement", "requirements", errors)
        self.assert_error(errors, "private absolute local path")

    def test_high_confidence_sensitive_values_are_rejected_but_truthful_policy_prose_passes(self):
        sensitive = (
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
            "github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456",
            "AKIAABCDEFGHIJKLMNOP",
            "-----BEGIN PRIVATE KEY-----",
            "Authorization: Bearer abc.def.ghi",
            "raw transcript: confidential payload",
            "raw log: confidential payload",
            "/root/.ssh/id_ed25519",
            "/tmp/private.log",
            "/var/folders/xx/private",
            "~/.ssh/config",
        )
        for value in sensitive:
            with self.subTest(value=value):
                record = self.read_json(ROOT, REQ)
                record["statement"] = value
                errors = []
                self.checker.validate_record_set([record], "requirement", "requirements", errors)
                self.assertTrue(errors)

        record = self.read_json(ROOT, REQ)
        record["statement"] = "Secrets, credential values, raw transcripts, and raw logs are forbidden."
        errors = []
        self.checker.validate_record_set([record], "requirement", "requirements", errors)
        self.assertEqual([], errors)

    def test_pin_canonicalization_is_documented_and_binds_actual_aggregate(self):
        pin = self.read_json(ROOT, PIN)
        canonical = self.checker.canonical_pin_bytes(pin)
        self.assertTrue(canonical.endswith(b"\n"))
        self.assertEqual(7, canonical.count(b"\n"))
        self.assertEqual(
            pin["aggregate"]["sha256"], hashlib.sha256(canonical).hexdigest()
        )
        human = (ROOT / "docs/agreements/portable-context-contract.md").read_text(encoding="utf-8")
        self.assertIn("UTF-8 text with LF separators and a required", human)
        self.assertIn("{path}<TAB>{mode}<TAB>{blob}<TAB>{sha256}", human)

    def test_machine_freshness_semantics_match_head_index_and_live_docs(self):
        contract = self.read_json(ROOT, CONTRACT)
        self.assertEqual(
            "selected-pin-sources-match-head-index-live-worktree",
            contract["pin_verification"]["freshness"],
        )
        for relative in (
            "docs/agreements/portable-context-contract.md",
            "docs/agreements/adr/ADR-0007-connector-neutral-context-contract.md",
            "docs/context/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("`HEAD`", text)
            self.assertIn("index", text)
            self.assertIn("live worktree", text)

    def test_document_sha_bindings_reject_semantic_reversals_while_markers_remain(self):
        contradictions = (
            "K10 and K11 are implemented and production ready.",
            "An external service and credential are mandatory.",
            "The live Task ritual and runtime adapter are production ready.",
            "The repository is complete.",
        )
        for contradiction in contradictions:
            with self.subTest(contradiction=contradiction):
                root = self.copy_fixture()
                path = root / "docs/agreements/portable-context-contract.md"
                path.write_text(path.read_text(encoding="utf-8") + "\n" + contradiction + "\n", encoding="utf-8")
                errors = self.checker.validate_repository(root)
                self.assert_error(errors, "reviewed human document SHA-256 drift")

        self.assertEqual([], self.checker.validate_repository(ROOT))

    def test_pin_rejects_unsafe_absolute_parent_windows_unicode_and_self_paths(self):
        unsafe = [
            "/etc/passwd",
            "../AGENTS.md",
            "C:/outside.txt",
            "\\\\server\\share",
            "docs/e\u0301.txt",
            "docs/zero\u200bwidth.txt",
            PIN,
        ]
        for value in unsafe:
            with self.subTest(value=value):
                pin = self.read_json(ROOT, PIN)
                pin["sources"][0]["path"] = value
                errors = []
                self.checker.validate_pin_shape(pin, PIN, "pin", errors)
                self.assertTrue(errors)

    def test_pin_rejects_duplicate_case_collision_unsorted_and_nonregular_mode(self):
        pin = self.read_json(ROOT, PIN)
        duplicate = copy.deepcopy(pin["sources"][0])
        duplicate["path"] = "agents.md"
        pin["sources"].append(duplicate)
        pin["sources"].sort(key=lambda item: item["path"])
        errors = []
        self.checker.validate_pin_shape(pin, PIN, "pin", errors)
        self.assert_error(errors, "Unicode/case path collision")

        pin = self.read_json(ROOT, PIN)
        pin["sources"][0]["mode"] = "120000"
        errors = []
        self.checker.validate_pin_shape(pin, PIN, "pin", errors)
        self.assert_error(errors, "regular-file Git mode")

    def test_pin_rejects_invalid_revision_tree_blob_source_and_aggregate_digests(self):
        mutations = (
            lambda pin: pin.__setitem__("revision", "0" * 39),
            lambda pin: pin.__setitem__("tree", "z" * 40),
            lambda pin: pin["sources"][0].__setitem__("blob", "0" * 39),
            lambda pin: pin["sources"][0].__setitem__("sha256", "0" * 63),
            lambda pin: pin["aggregate"].__setitem__("sha256", "0" * 64),
        )
        for mutation in mutations:
            pin = self.read_json(ROOT, PIN)
            mutation(pin)
            errors = []
            self.checker.validate_pin_shape(pin, PIN, "pin", errors)
            if not errors:
                self.checker.verify_pin_git(ROOT, pin, PIN, True, errors)
            self.assertTrue(errors)

    def test_missing_git_revision_is_unknown_and_blocks(self):
        pin = self.read_json(ROOT, PIN)
        pin["revision"] = "0" * 40
        pin["tree"] = "0" * 40
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(ROOT, pin, PIN, True, errors)
        self.assert_error(errors, "UNKNOWN")

    def test_observed_blob_revision_and_invalid_tree_bindings_are_fail_not_unknown(self):
        pin = self.read_json(ROOT, PIN)
        pin["revision"] = pin["sources"][0]["blob"]
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(ROOT, pin, PIN, False, errors)
        self.assert_error(errors, "fail: pin PIN-0001 revision is not a commit")

        pin = self.read_json(ROOT, PIN)
        pin["sources"][0]["path"] = "does-not-exist.txt"
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(ROOT, pin, PIN, False, errors)
        self.assert_error(errors, "fail: exact Git path is absent")

        pin = self.read_json(ROOT, PIN)
        pin["sources"][0]["path"] = "docs"
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(ROOT, pin, PIN, False, errors)
        self.assert_error(errors, "fail: pin PIN-0001 source docs is not the exact regular Git blob")

        pin = self.read_json(ROOT, PIN)
        pin["sources"][0]["mode"] = "100755"
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(ROOT, pin, PIN, False, errors)
        self.assert_error(errors, "fail: pin PIN-0001 source binding mismatch")

    def test_malformed_git_tree_output_is_uncheckable(self):
        completed = subprocess.CompletedProcess([], 0, b"malformed\0", b"")
        errors = []
        with mock.patch.object(self.checker, "run_git", return_value=completed):
            self.checker.tree_entry(ROOT, "0" * 40, "AGENTS.md", "fixture", errors)
        self.assert_error(errors, "UNCHECKABLE: malformed Git tree entry")

    def test_nonancestor_commit_revision_is_rejected(self):
        root = self.copy_fixture()
        empty_tree = subprocess.run(
            ["git", "mktree"], cwd=root, input=b"", stdout=subprocess.PIPE, check=True
        ).stdout.decode("ascii").strip()
        revision = subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit-tree", empty_tree],
            cwd=root,
            input=b"unrelated\n",
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.decode("ascii").strip()
        pin = self.read_json(root, PIN)
        pin["revision"] = revision
        self.recompute_pin(pin)
        errors = []
        self.checker.verify_pin_git(root, pin, PIN, False, errors)
        self.assert_error(errors, "not an ancestor of governed HEAD")

    def test_git_execution_failure_is_uncheckable_not_success(self):
        pin = self.read_json(ROOT, PIN)
        errors = []
        with mock.patch.object(self.checker, "run_git", return_value=None):
            self.checker.verify_pin_git(ROOT, pin, PIN, True, errors)
        self.assert_error(errors, "UNCHECKABLE")

    def test_selected_pin_drift_blocks_both_decomposition_and_execution(self):
        root = self.copy_fixture()
        (root / "AGENTS.md").write_text(
            (root / "AGENTS.md").read_text(encoding="utf-8") + "\nDrift fixture.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "drift"],
            cwd=root,
            check=True,
        )
        errors = self.checker.validate_repository(root)
        self.assert_error(errors, "drift: selected pin blocks decomposition and execution")

    def test_unstaged_and_staged_only_drift_each_block_both_gates(self):
        root = self.copy_fixture()
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\nunstaged\n", encoding="utf-8")
        errors = self.checker.validate_repository(root)
        self.assert_error(errors, "drift: selected pin blocks decomposition and execution")

        root = self.copy_fixture()
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\nstaged\n", encoding="utf-8")
        subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
        errors = self.checker.validate_repository(root)
        self.assert_error(errors, "drift: selected pin blocks decomposition and execution")

    def test_live_deletion_symlink_and_fifo_each_block_both_gates(self):
        root = self.copy_fixture()
        (root / "AGENTS.md").unlink()
        self.assert_error(self.checker.validate_repository(root), "drift: selected pin blocks decomposition and execution")

        root = self.copy_fixture()
        agents = root / "AGENTS.md"
        target = root / "agents-target.txt"
        target.write_bytes(self.checker.git_blob(ROOT, self.read_json(ROOT, PIN)["sources"][0]["blob"], "fixture", []))
        agents.unlink()
        agents.symlink_to(target.name)
        self.assert_error(self.checker.validate_repository(root), "drift: selected pin blocks decomposition and execution")

        if hasattr(os, "mkfifo"):
            root = self.copy_fixture()
            agents = root / "AGENTS.md"
            agents.unlink()
            os.mkfifo(agents)
            self.assert_error(self.checker.validate_repository(root), "drift: selected pin blocks decomposition and execution")

    def test_unselected_historical_pin_can_be_valid_and_stale(self):
        root = self.copy_fixture()
        (root / "AGENTS.md").write_text("changed\n", encoding="utf-8")
        subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "drift"],
            cwd=root,
            check=True,
        )
        errors = []
        self.checker.verify_pin_git(root, self.read_json(root, PIN), PIN, False, errors)
        self.assertFalse(any("drift" in error for error in errors), errors)

    def test_immutable_base_record_mutation_and_deletion_are_rejected(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        source = ROOT / REQ
        target = root / REQ
        target.parent.mkdir(parents=True)
        shutil.copy2(source, target)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "base"],
            cwd=root,
            check=True,
        )
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
        ownership = {"tasks": [{"state": "active", "base_commit": base, "base_tree": tree}]}
        payload = self.read_json(root, REQ)
        payload["title"] = "Mutated history"
        self.write_json(root, REQ, payload)
        errors = []
        self.checker.validate_immutable_history(root, ownership, {REQ}, errors)
        self.assert_error(errors, "immutable historical record changed")
        errors = []
        self.checker.validate_immutable_history(root, ownership, set(), errors)
        self.assert_error(errors, "immutable historical record was deleted")

    def test_new_record_id_must_exceed_active_base_maximum(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        base_path = "docs/agreements/requirements/REQ-0002.json"
        target = root / base_path
        target.parent.mkdir(parents=True)
        target.write_text("{}\n", encoding="utf-8")
        subprocess.run(["git", "add", base_path], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "base"],
            cwd=root,
            check=True,
        )
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
        lower = "docs/agreements/requirements/REQ-0001.json"
        lower_path = root / lower
        lower_path.write_text("{}\n", encoding="utf-8")
        ownership = {"tasks": [{"state": "active", "base_commit": base, "base_tree": tree}]}
        errors = []
        self.checker.validate_immutable_history(root, ownership, {base_path, lower}, errors)
        self.assert_error(errors, "must exceed active Task base maximum 0002")

    def test_accepted_main_record_remains_immutable_while_t08_is_still_active(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
        target = root / REQ
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / REQ, target)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "accepted main"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "checkout", "--quiet", "-b", "feature"], cwd=root, check=True)
        record = self.read_json(root, REQ)
        record["title"] = "Post-merge mutation"
        self.write_json(root, REQ, record)
        errors = []
        self.checker.validate_accepted_main_history(root, {REQ}, errors)
        self.assert_error(errors, "accepted main historical record changed")

        errors = []
        self.checker.validate_accepted_main_history(root, set(), errors)
        self.assert_error(errors, "accepted main historical record was deleted")

        shutil.copy2(ROOT / REQ, target)
        target.unlink()
        subprocess.run(["git", "add", "--all", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "delete history"],
            cwd=root,
            check=True,
        )
        shutil.copy2(ROOT / REQ, target)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "re-add history"],
            cwd=root,
            check=True,
        )
        errors = []
        self.checker.validate_accepted_main_history(root, {REQ}, errors)
        self.assert_error(errors, "changed, deleted, renamed, or type-changed")

    def test_accepted_main_modify_then_restore_remains_an_immutability_violation(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
        target = root / REQ
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / REQ, target)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "accepted main"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "checkout", "--quiet", "-b", "feature"], cwd=root, check=True)
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "mutate history"],
            cwd=root,
            check=True,
        )
        target.write_bytes(original)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "restore bytes"],
            cwd=root,
            check=True,
        )
        errors = []
        self.checker.validate_accepted_main_history(root, {REQ}, errors)
        self.assert_error(errors, "changed, deleted, renamed, or type-changed")

    def test_accepted_main_high_similarity_rename_then_exact_restore_is_rejected(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
        target = root / REQ
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / REQ, target)
        original = target.read_bytes()
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "accepted main"],
            cwd=root,
            check=True,
        )
        accepted = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        subprocess.run(["git", "config", "diff.renames", "true"], cwd=root, check=True)
        subprocess.run(["git", "checkout", "--quiet", "-b", "feature"], cwd=root, check=True)
        renamed = "docs/agreements/requirements/REQ-0002.json"
        renamed_path = root / renamed
        target.rename(renamed_path)
        payload = self.read_json(root, renamed)
        payload["id"] = "REQ-0002"
        payload["title"] = "Verify selected context before each governed work boundary"
        payload["supersedes"] = ["REQ-0001"]
        self.write_json(root, renamed, payload)
        subprocess.run(["git", "add", "--all", REQ, renamed], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "rename accepted record"],
            cwd=root,
            check=True,
        )
        rename_status = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "-M", "HEAD^", "HEAD"],
            cwd=root,
            text=True,
        )
        self.assertRegex(rename_status, r"(?m)^R(?:0[5-9][0-9]|100)\s")

        target.write_bytes(original)
        subprocess.run(["git", "add", REQ], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "restore exact accepted record"],
            cwd=root,
            check=True,
        )
        record_errors = []
        self.checker.validate_record_set(
            [self.read_json(root, REQ), self.read_json(root, renamed)],
            "requirement",
            "requirements",
            record_errors,
        )
        self.assertEqual([], record_errors)

        legacy = subprocess.check_output(
            [
                "git",
                "--no-replace-objects",
                "log",
                "-m",
                "--format=",
                "--name-only",
                "-z",
                "--diff-filter=DMRT",
                f"{accepted}..HEAD",
                "--",
                "docs/agreements/requirements",
            ],
            cwd=root,
        )
        legacy_names = {
            item.strip(b"\n").decode("utf-8")
            for item in legacy.split(b"\0")
            if item.strip(b"\n")
        }
        self.assertNotIn(REQ, legacy_names)
        errors = []
        self.checker.validate_accepted_main_history(root, {REQ, renamed}, errors)
        self.assert_error(errors, "changed, deleted, renamed, or type-changed")

    def test_missing_canonical_main_ref_is_uncheckable_for_accepted_history(self):
        root = self.copy_fixture()
        subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=root, check=True)
        subprocess.run(["git", "update-ref", "-d", "refs/heads/main"], cwd=root, check=True)
        errors = []
        self.checker.validate_accepted_main_history(root, {REQ, DEC, PIN}, errors)
        self.assert_error(errors, "UNCHECKABLE: no canonical local or origin main ref")

    def test_fixed_json_inputs_reject_symlink_fifo_oversize_duplicate_and_deep_json(self):
        root = self.copy_fixture()
        contract = root / CONTRACT
        target = root / "contract-target.json"
        contract.rename(target)
        contract.symlink_to(target)
        self.assert_error(self.checker.validate_repository(root), "cannot safely read")

        if hasattr(os, "mkfifo"):
            root = self.copy_fixture()
            contract = root / CONTRACT
            contract.unlink()
            os.mkfifo(contract)
            self.assert_error(self.checker.validate_repository(root), "not a regular file")

        root = self.copy_fixture()
        (root / CONTRACT).write_bytes(b" " * (self.checker.MAX_FILE_BYTES + 1))
        self.assert_error(self.checker.validate_repository(root), "exceeds size limit")

        root = self.copy_fixture()
        (root / CONTRACT).write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
        self.assert_error(self.checker.validate_repository(root), "duplicate JSON key")

        root = self.copy_fixture()
        (root / CONTRACT).write_text("[" * 2000 + '"leaf"' + "]" * 2000, encoding="utf-8")
        self.assert_error(self.checker.validate_repository(root), "invalid JSON")

    def test_record_directories_reject_symlinks(self):
        cases = (
            ("docs/agreements/requirements", re.compile(r"REQ-[0-9]{4}\.json\Z")),
            ("docs/agreements/decisions", re.compile(r"DEC-[0-9]{4}\.json\Z")),
            ("docs/context/pins", re.compile(r"PIN-[0-9]{4}\.context-pin\.v1\.json\Z")),
        )
        for directory, pattern in cases:
            with self.subTest(directory=directory):
                root = self.copy_fixture()
                target = root / directory
                moved = target.with_name(target.name + "-real")
                target.rename(moved)
                target.symlink_to(moved.name, target_is_directory=True)
                errors = []
                paths = self.checker.list_record_paths(root, directory, pattern, errors)
                self.assertEqual([], paths)
                self.assert_error(errors, "cannot safely enumerate")

    def test_record_directory_enumeration_detects_parent_namespace_swap(self):
        root = self.copy_fixture()
        original_scandir = self.checker.os.scandir
        swapped = False

        def swapping_scandir(path):
            nonlocal swapped
            iterator = original_scandir(path)
            if isinstance(path, int) and not swapped:
                swapped = True
                agreements = root / "docs/agreements"
                agreements.rename(root / "docs/agreements-old")
                agreements.mkdir()
            return iterator

        errors = []
        with mock.patch.object(self.checker.os, "scandir", side_effect=swapping_scandir):
            paths = self.checker.list_record_paths(
                root,
                "docs/agreements/requirements",
                re.compile(r"REQ-[0-9]{4}\.json\Z"),
                errors,
            )
        self.assertTrue(swapped)
        self.assertEqual([], paths)
        self.assert_error(errors, "directory binding changed while enumerating")

    def test_record_directory_enumeration_stops_at_max_plus_one(self):
        root = self.copy_fixture()
        directory = root / "docs/agreements/requirements"
        for number in range(2, self.checker.MAX_RECORDS_PER_KIND + 3):
            (directory / f"unsafe\u200b-{number:04d}.json").write_bytes(b"{}\n")

        original_scandir = self.checker.os.scandir
        limit = self.checker.MAX_RECORDS_PER_KIND
        consumed = 0

        class GuardedScandir:
            def __init__(self, iterator):
                self.iterator = iterator

            def __enter__(self):
                return self

            def __exit__(self, _kind, _value, _traceback):
                self.iterator.close()

            def __iter__(self):
                return self

            def __next__(self):
                nonlocal consumed
                value = next(self.iterator)
                consumed += 1
                if consumed > limit + 1:
                    raise AssertionError("record enumeration consumed beyond MAX+1")
                return value

        def guarded_scandir(path):
            return GuardedScandir(original_scandir(path))

        errors = []
        with mock.patch.object(self.checker.os, "scandir", side_effect=guarded_scandir):
            paths = self.checker.list_record_paths(
                root,
                "docs/agreements/requirements",
                re.compile(r"REQ-[0-9]{4}\.json\Z"),
                errors,
            )
        self.assertEqual([], paths)
        self.assert_error(errors, "exceeds record count limit")
        self.assertEqual(limit + 1, consumed)

    def test_safe_reader_fails_when_platform_flags_are_missing(self):
        for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
            with self.subTest(flag=flag), mock.patch.object(self.checker.os, flag, 0):
                with self.assertRaisesRegex(ValueError, f"required platform flag {flag} is unavailable"):
                    self.checker.load_json(ROOT, CONTRACT)

    def test_safe_reader_detects_parent_namespace_swap(self):
        root = self.copy_fixture()
        original_open = self.checker.os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
            if path == "portable-context-contract.v1.json" and dir_fd is not None and not swapped:
                swapped = True
                agreements = root / "docs/agreements"
                agreements.rename(root / "docs/agreements-old")
                agreements.mkdir()
            return descriptor

        with mock.patch.object(self.checker.os, "open", side_effect=swapping_open):
            errors = self.checker.validate_repository(root)
        self.assertTrue(swapped)
        self.assert_error(errors, "repository directory binding changed")

    def test_nonregular_record_input_is_rejected(self):
        root = self.copy_fixture()
        record = root / REQ
        record.unlink()
        if hasattr(os, "mkfifo"):
            os.mkfifo(record)
            self.assert_error(self.checker.validate_repository(root), "not a regular file")

    def test_results_and_release_block_remain_fail_closed(self):
        root = self.copy_fixture()
        results_path = root / "tests/conformance/results.json"
        results = self.read_json(root, "tests/conformance/results.json")
        results["results"] = [{"scenario": "C-001", "result": "pass"}]
        self.write_json(root, "tests/conformance/results.json", results)
        self.assert_error(self.checker.validate_repository(root), "results must remain empty")

        root = self.copy_fixture()
        ownership = self.read_json(root, OWNERSHIP)
        ownership["phase"]["release_blocked"] = False
        self.write_json(root, OWNERSHIP, ownership)
        self.assert_error(self.checker.validate_repository(root), "release_blocked must remain true")


if __name__ == "__main__":
    unittest.main()
