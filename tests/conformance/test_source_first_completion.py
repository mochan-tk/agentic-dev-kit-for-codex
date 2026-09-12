"""The product contract is traceability, never a replacement result store."""

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RECORD = ".github/governance/source-first-completion.v1.json"
AGREEMENT = "docs/agreements/source-first-completion.md"
CHECKER = ".github/scripts/check-repository-policy.py"


class SourceFirstCompletionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("source_first_policy", ROOT / CHECKER)
        cls.policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.policy)

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repository"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return root

    def fixture_git(self, root, *arguments, umask=-1):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(root), *arguments],
                                env=environment, umask=umask, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def record(self, root=ROOT):
        return json.loads((root / RECORD).read_text())

    def check(self, root):
        errors = []
        self.policy.validate_source_first_completion(root, errors)
        return errors

    def mutate(self, change):
        root = self.fixture()
        record = self.record(root)
        change(record)
        (root / RECORD).write_text(json.dumps(record) + "\n")
        self.assertTrue(self.check(root))

    def test_current_contract_is_structurally_valid_but_incomplete(self):
        self.assertEqual([], self.check(ROOT))
        record = self.record()
        self.assertEqual("incomplete", record["product_state"])
        self.assertEqual("incomplete", record["repository_state"])
        self.assertIs(True, record["release_blocked"])
        self.assertTrue(all(c["acceptance"] == "pending-current-owner-review" for c in record["criteria"]))

    def test_every_original_id_and_expected_behavior_is_bound(self):
        record = self.record()
        catalog = json.loads((ROOT / "tests/conformance/catalog.json").read_text())
        scenarios = [s for family in catalog["families"] for s in family["scenarios"]]
        self.assertEqual([s["id"] for s in scenarios], [r["id"] for r in record["scenarios"]])
        self.assertEqual(136, len(record["scenarios"]))
        for actual, row in zip(scenarios, record["scenarios"]):
            self.assertEqual(hashlib.sha256(actual["expected"]["text"].encode()).hexdigest(), row["expected_sha256"])
            self.assertEqual("not-run", row["original_verification_state"])
            self.assertTrue(row["rationale"])
        self.assertEqual([f"K{i:02d}" for i in range(1, 21)], [r["id"] for r in record["contracts"]])

    def test_criteria_omission_duplication_extra_and_order_refuse(self):
        for change in (lambda r: r["criteria"].pop(),
                       lambda r: r["criteria"].append(copy.deepcopy(r["criteria"][0])),
                       lambda r: r["criteria"][0].update(id="SF-99"),
                       lambda r: r["criteria"].reverse()):
            with self.subTest(change=change): self.mutate(change)

    def test_contract_omission_duplicate_extra_and_changed_original_refuse(self):
        for change in (lambda r: r["contracts"].pop(),
                       lambda r: r["contracts"][1].update(id="K01"),
                       lambda r: r["contracts"][0].update(id="K21"),
                       lambda r: r["contracts"][0].update(original_sha256="0" * 64)):
            with self.subTest(change=change): self.mutate(change)

    def test_scenario_omission_duplicate_unknown_and_reclassified_refuse(self):
        for change in (lambda r: r["scenarios"].pop(),
                       lambda r: r["scenarios"][1].update(id="C-001"),
                       lambda r: r["scenarios"][0].update(id="C-999"),
                       lambda r: r["scenarios"][0].update(applicability="supplemental")):
            with self.subTest(change=change): self.mutate(change)

    def test_expected_behavior_and_rationale_drift_refuse(self):
        for field, value in (("expected_sha256", "0" * 64), ("rationale", ""),
                             ("rationale", "All runtime behavior is already proven.")):
            with self.subTest(field=field): self.mutate(lambda r: r["scenarios"][0].update({field: value}))

    def test_applicability_never_becomes_execution_result(self):
        for change in (lambda r: r["scenarios"][0].update(original_verification_state="pass"),
                       lambda r: r["scenarios"][0].update(result="pass"),
                       lambda r: r.update(results=[{"scenario": "C-001", "status": "pass"}]),
                       lambda r: r["criteria"][0].update(acceptance="accepted")):
            with self.subTest(change=change): self.mutate(change)

    def test_product_repository_and_release_success_claims_refuse(self):
        for field, value in (("product_state", "complete"), ("repository_state", "complete"),
                             ("release_blocked", False), ("release_blocked", 1)):
            with self.subTest(field=field): self.mutate(lambda r: r.update({field: value}))

    def test_unknown_fields_and_wrong_types_refuse(self):
        for change in (lambda r: r.update(extra=True), lambda r: r.update(criteria=True),
                       lambda r: r.update(scenarios={}), lambda r: r.update(contracts=None),
                       lambda r: r["criteria"][0].update(extra=True),
                       lambda r: r["evidence"][0].update(extra=True)):
            with self.subTest(change=change): self.mutate(change)

    def test_unknown_evidence_classes_and_runtime_laundering_refuse(self):
        for value in ("live-runtime-success", "pass", "UNKNOWN", "UNCHECKABLE", None, True):
            with self.subTest(value=value): self.mutate(lambda r: r["evidence"][0].update(evidence_class=value))

    def test_private_or_unreviewed_public_evidence_refuse(self):
        for url in ("https://github.com/example/private-adopter/issues/1",
                    "https://github.com/mochan-tk/agentic-dev-kit-for-codex/issues/999",
                    "/Users/example/private-proof.json", "file:///tmp/proof"):
            with self.subTest(url=url): self.mutate(lambda r: r["evidence"][0].update(reference=url))

    def test_source_and_base_provenance_drift_refuse(self):
        for section, field in (("source", "commit"), ("source", "repository"),
                               ("baseline", "commit"), ("baseline", "tree"),
                               ("authority", "plan")):
            with self.subTest(section=section, field=field): self.mutate(lambda r: r[section].update({field: "unreviewed"}))

    def test_source_row_and_payload_digests_refuse(self):
        for change in (lambda r: r["criteria"][0]["source_files"][0].update(source_blob="0" * 40),
                       lambda r: r["criteria"][0]["source_files"][0].update(target_sha256="0" * 64),
                       lambda r: r["protected_files"][0].update(sha256="0" * 64)):
            with self.subTest(change=change): self.mutate(change)

    def test_original_dod_and_original_result_stores_cannot_be_reinterpreted(self):
        for path in ("docs/agreements/repository-completion.md", "tests/conformance/manifest.json",
                     "tests/conformance/catalog.json", "tests/conformance/coverage.json", "tests/conformance/results.json"):
            with self.subTest(path=path):
                root = self.fixture()
                with (root / path).open("ab") as stream: stream.write(b"\n")
                self.assertTrue(self.check(root))

    def test_definition_drift_refuses_even_after_record_rehash(self):
        root = self.fixture()
        path = root / AGREEMENT
        path.write_text(path.read_text() + "\nNew completion waiver.\n")
        record = self.record(root)
        record["definition"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / RECORD).write_text(json.dumps(record))
        self.assertTrue(self.check(root))

    def test_semantic_rejections_do_not_rely_only_on_the_record_seal(self):
        for change in (lambda r: r.update(product_state="complete"),
                       lambda r: r["scenarios"][0].update(original_verification_state="pass"),
                       lambda r: r["evidence"][0].update(evidence_class="live-runtime-success"),
                       lambda r: r["evidence"][0].update(reference="https://github.com/example/private/issues/1"),
                       lambda r: r["scenarios"].pop(),
                       lambda r: r["contracts"].pop()):
            with self.subTest(change=change):
                root = self.fixture()
                record = self.record(root)
                change(record)
                (root / RECORD).write_text(json.dumps(record))
                seal = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
                with mock.patch.object(self.policy, "SF_REVIEWED_SEAL", seal):
                    self.assertTrue(self.check(root))

    def test_missing_record_definition_or_provenance_refuses(self):
        for path in (RECORD, AGREEMENT, ".github/distribution/source-parity.v1.json"):
            with self.subTest(path=path):
                root = self.fixture()
                (root / path).unlink()
                self.assertTrue(self.check(root))

    def test_symlink_leaf_and_parent_refuse(self):
        root = self.fixture()
        original = root / RECORD
        backup = root / "record-copy"
        original.rename(backup)
        original.symlink_to(backup)
        self.assertTrue(self.check(root))
        root = self.fixture()
        original = root / ".github/governance"
        backup = root / "governance-copy"
        original.rename(backup)
        original.symlink_to(backup, target_is_directory=True)
        self.assertTrue(self.check(root))

    def test_hardlink_and_special_file_refuse_without_blocking(self):
        root = self.fixture()
        os.link(root / RECORD, root / "second-link")
        self.assertTrue(self.check(root))
        root = self.fixture()
        (root / RECORD).unlink()
        os.mkfifo(root / RECORD)
        self.assertTrue(self.check(root))

    def test_mode_and_read_error_are_not_absence(self):
        root = self.fixture()
        (root / RECORD).chmod(0o755)
        self.assertTrue(self.check(root))
        with mock.patch.object(self.policy.os, "read", side_effect=PermissionError):
            self.assertTrue(self.check(ROOT))

    def test_clean_git_checkouts_with_ordinary_umasks_are_structurally_valid(self):
        source = self.fixture()
        self.fixture_git(source, "init", "--quiet", "--template=")
        self.fixture_git(source, "add", "--all")
        tree = self.fixture_git(source, "write-tree")
        commit = self.fixture_git(source, "-c", "user.name=Fixture", "-c",
                                  "user.email=fixture@example.invalid", "commit-tree", tree,
                                  "-m", "Synthetic checkout fixture; not historical authorization evidence")
        self.fixture_git(source, "update-ref", "HEAD", commit)
        for mask, mode in ((0o022, 0o644), (0o077, 0o600), (0o027, 0o640), (0o002, 0o664)):
            with self.subTest(umask=f"{mask:03o}"):
                root = source.parent / f"clone-{mask:03o}"
                self.fixture_git(source.parent, "clone", "--quiet", "--no-hardlinks",
                                 str(source), str(root), umask=mask)
                self.assertEqual(tree, self.fixture_git(root, "rev-parse", "HEAD^{tree}"))
                entries = self.fixture_git(root, "ls-files", "--stage").splitlines()
                self.assertTrue(entries)
                self.assertEqual({"100644"}, {entry.split()[0] for entry in entries})
                for relative in (RECORD, "README.md"):
                    self.assertEqual(mode, stat.S_IMODE((root / relative).stat().st_mode))
                self.assertEqual("", self.fixture_git(root, "status", "--porcelain", "--untracked-files=no"))
                # Run production structural checks; synthetic history cannot authorize a Task.
                self.assertEqual([], self.policy.validate_repository(root, verify_git=False))
                self.fixture_git(root, "diff", "--exit-code")
                self.fixture_git(root, "diff", "--cached", "--exit-code")

    def test_readable_nonexecutable_permissions_are_accepted(self):
        for mode in (0o600, 0o640, 0o644, 0o664, 0o444):
            for relative in (RECORD, "README.md"):
                with self.subTest(mode=f"{mode:04o}", path=relative):
                    root = self.fixture()
                    (root / relative).chmod(mode)
                    self.assertEqual(mode, stat.S_IMODE((root / relative).stat().st_mode))
                    with mock.patch.object(self.policy, "filesystem_mode", side_effect=AssertionError(
                            "secure source-first reads must use descriptor metadata")):
                        self.assertEqual([], self.check(root))

    def test_each_executable_permission_bit_refuses(self):
        for mode in (0o744, 0o654, 0o645):
            with self.subTest(mode=f"{mode:04o}"):
                root = self.fixture()
                (root / RECORD).chmod(mode)
                self.assertEqual(mode, stat.S_IMODE((root / RECORD).stat().st_mode))
                self.assertTrue(self.check(root))

    def test_each_special_permission_bit_refuses(self):
        for mode in (0o4644, 0o2644, 0o1644):
            with self.subTest(mode=f"{mode:04o}"):
                root = self.fixture()
                (root / RECORD).chmod(mode)
                self.assertEqual(mode, stat.S_IMODE((root / RECORD).stat().st_mode))
                self.assertTrue(self.check(root))

    def test_leaf_replacement_during_read_refuses(self):
        root = self.fixture()
        original_read = os.read
        changed = False
        def replace_after_read(fd, limit):
            nonlocal changed
            data = original_read(fd, limit)
            if not changed:
                changed = True
                path = root / RECORD
                previous = path.read_bytes()
                path.rename(root / "old-record")
                path.write_bytes(previous)
            return data
        with mock.patch.object(self.policy.os, "read", side_effect=replace_after_read):
            self.assertTrue(self.check(root))

    def test_parent_namespace_replacement_during_read_refuses(self):
        root = self.fixture()
        original_read = os.read
        changed = False
        def replace_after_read(fd, limit):
            nonlocal changed
            data = original_read(fd, limit)
            if not changed:
                changed = True
                directory = root / ".github/governance"
                directory.rename(root / "old-governance")
                shutil.copytree(root / "old-governance", directory)
            return data
        with mock.patch.object(self.policy.os, "read", side_effect=replace_after_read):
            self.assertTrue(self.check(root))

    def test_duplicate_json_keys_and_invalid_utf8_refuse(self):
        for data in (b'{"schema":"x","schema":"x"}', b'{"a":NaN}', b'\xff', b'[]', b'{',
                     b'{"number":' + b'9' * 129 + b'}'):
            with self.subTest(data=data):
                root = self.fixture()
                (root / RECORD).write_bytes(data)
                self.assertTrue(self.check(root))

    def test_json_byte_depth_node_and_string_limits(self):
        for value in ({"s": "x" * self.policy.SF_MAX_STRING},
                      [0] * (self.policy.SF_MAX_NODES - 1),
                      self.nested(self.policy.SF_MAX_DEPTH)):
            self.policy.source_first_json_limits(value)
        for value in ({"s": "x" * (self.policy.SF_MAX_STRING + 1)},
                      [0] * self.policy.SF_MAX_NODES,
                      self.nested(self.policy.SF_MAX_DEPTH + 1)):
            with self.assertRaises(ValueError): self.policy.source_first_json_limits(value)
        root = self.fixture()
        (root / RECORD).write_bytes(b" " * self.policy.SF_MAX_BYTES)
        self.assertEqual(self.policy.SF_MAX_BYTES, len(self.policy.source_first_bytes(root, RECORD)))
        (root / RECORD).write_bytes(b" " * (self.policy.SF_MAX_BYTES + 1))
        self.assertTrue(self.check(root))

    def test_original_scenario_partition_is_an_inventory_not_progress(self):
        record = self.record()
        counts = {name: sum(r["applicability"] == name for r in record["scenarios"])
                  for name in ("retained", "adapted", "supplemental")}
        self.assertEqual(136, sum(counts.values()))
        self.assertEqual({"retained": 52, "adapted": 51, "supplemental": 33}, counts)
        rows = {r["id"]: r for r in record["scenarios"]}
        for identifier, clause in (("R-007", "release"), ("R-008", "successor"),
                                   ("O-007", "changed files"), ("T-015", "retries"),
                                   ("X-002", "cooperative planned replacement")):
            self.assertIn(clause, rows[identifier]["rationale"])
        evidence = {r["id"]: r for r in record["evidence"]}
        self.assertEqual("historical-public-planning-observation", evidence["E-03"]["evidence_class"])

    @staticmethod
    def nested(depth):
        result = 0
        for _ in range(depth): result = [result]
        return result

    def test_deep_parser_failure_is_bounded_without_traceback(self):
        root = self.fixture()
        (root / RECORD).write_text("[" * 20000 + "0" + "]" * 20000)
        result = subprocess.run([sys.executable, "-I", str(root / CHECKER)], cwd=root,
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("source-first completion contract:", result.stdout + result.stderr)

    def test_required_policy_entrypoint_cannot_skip_product_validation(self):
        with mock.patch.object(self.policy, "validate_source_first_completion") as validate:
            self.policy.validate_repository(ROOT, verify_git=False)
            validate.assert_called_once()
        root = self.fixture()
        text = (root / CHECKER).read_text()
        (root / CHECKER).write_text(text.replace("    validate_source_first_completion(root, errors)\n", "", 1))
        self.assertTrue(self.check(root))

    def test_focused_suite_is_in_existing_repository_wide_discovery(self):
        record = json.loads((ROOT / ".github/governance/phase-task-ownership.v1.json").read_text())
        self.assertEqual(["python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'"],
                         record["policy"]["required_conformance_commands"])
        root = self.fixture()
        (root / "tests/conformance/test_source_first_completion.py").unlink()
        self.assertTrue(self.check(root))

    def test_status_surfaces_link_contract_and_do_not_claim_acceptance(self):
        for path in ("README.md", "docs/known-limitations.md", "docs/distribution/source-first-installer.md"):
            with self.subTest(path=path):
                root = self.fixture()
                text = (root / path).read_text()
                self.assertIn("Source-first product completion", text)
                (root / path).write_text(text.replace("Source-first product completion", "Product done", 1))
                self.assertTrue(self.check(root))


if __name__ == "__main__":
    unittest.main()
