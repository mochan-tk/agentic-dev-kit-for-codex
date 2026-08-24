import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / ".github/scripts/conformance-catalog.py"


class ConformanceCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("conformance_catalog", TOOL)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load conformance catalog tool: {TOOL}")
        cls.catalog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.catalog)

    def fixture_paths(self):
        return [
            self.catalog.TOOL_PATH,
            self.catalog.SOURCE_PATH,
            self.catalog.SOURCE_MANIFEST_PATH,
            self.catalog.CATALOG_PATH,
            self.catalog.CATALOG_SCHEMA_PATH,
            self.catalog.COVERAGE_PATH,
            self.catalog.COVERAGE_SCHEMA_PATH,
            self.catalog.RESULTS_PATH,
            self.catalog.RESULTS_SCHEMA_PATH,
            self.catalog.HUMAN_CATALOG_PATH,
            self.catalog.PROVENANCE_ADR_PATH,
            self.catalog.PHASE_MANIFEST_PATH,
        ]

    def copy_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "repository"
        fixture.mkdir()
        for relative in self.fixture_paths():
            source = ROOT / relative
            self.assertTrue(source.is_file(), f"fixture source missing: {relative}")
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return fixture

    def read_json(self, root, relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def write_json(self, root, relative, payload):
        (root / relative).write_bytes(self.catalog.canonical_json_bytes(payload))

    def mutate_json(self, root, relative, mutation):
        payload = self.read_json(root, relative)
        mutation(payload)
        self.write_json(root, relative, payload)

    def errors_for(self, root):
        return self.catalog.validate_repository(root)

    def assert_rejected(self, errors, token):
        rendered = "\n".join(errors)
        self.assertTrue(errors, "invalid fixture unexpectedly passed")
        self.assertIn(token, rendered)

    def capture_command(self, command, root):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = command(root)
        return status, output.getvalue()

    def assert_no_sensitive_reflection(self, rendered, root, *secret_tokens):
        for marker in (
            "/Users/",
            "/home/",
            r"C:\private",
            str(root),
            *secret_tokens,
        ):
            self.assertNotIn(marker, rendered)

    def scenario_map(self, catalog):
        return {
            scenario["id"]: scenario
            for family in catalog["families"]
            for scenario in family["scenarios"]
        }

    def test_live_catalog_passes(self):
        self.assertEqual([], self.errors_for(ROOT))

    def test_catalog_is_exactly_136_unique_gap_free_scenarios(self):
        catalog = self.read_json(ROOT, self.catalog.CATALOG_PATH)
        scenarios = list(self.catalog.iter_scenarios(catalog))
        observed = [scenario["id"] for scenario in scenarios]
        expected = [
            f"{family}-{number:03d}"
            for family in self.catalog.SOURCE_FAMILY_ORDER
            for number in range(
                1, self.catalog.EXPECTED_FAMILY_COUNTS[family] + 1
            )
        ]
        self.assertEqual(self.catalog.TOTAL_SCENARIOS, len(observed))
        self.assertEqual(expected, observed)
        self.assertEqual(len(observed), len(set(observed)))

    def test_family_counts_match_reviewed_inventory(self):
        catalog = self.read_json(ROOT, self.catalog.CATALOG_PATH)
        observed = {
            family["id"]: len(family["scenarios"])
            for family in catalog["families"]
        }
        self.assertEqual(
            {
                family: self.catalog.EXPECTED_FAMILY_COUNTS[family]
                for family in self.catalog.SOURCE_FAMILY_ORDER
            },
            observed,
        )

    def test_catalog_reconstructs_source_byte_for_byte(self):
        catalog = self.read_json(ROOT, self.catalog.CATALOG_PATH)
        reconstructed = self.catalog.reconstruct_source(catalog).encode("utf-8")
        source = (ROOT / self.catalog.SOURCE_PATH).read_bytes()
        self.assertEqual(source, reconstructed)
        self.assertEqual(self.catalog.SOURCE_SHA256, self.catalog.sha256_bytes(source))

    def test_optional_clauses_and_d002_label_are_preserved(self):
        scenarios = self.scenario_map(
            self.read_json(ROOT, self.catalog.CATALOG_PATH)
        )
        self.assertNotIn("precondition", scenarios["T-005"])
        self.assertNotIn("action", scenarios["T-005"])
        self.assertEqual(
            "Expected target behavior", scenarios["D-002"]["expected"]["label"]
        )

    def test_coverage_is_definitions_only_and_not_run(self):
        coverage = self.read_json(ROOT, self.catalog.COVERAGE_PATH)
        entries = coverage["entries"]
        self.assertEqual(self.catalog.TOTAL_SCENARIOS, len(entries))
        self.assertTrue(
            all(entry["verification_state"] == "not-run" for entry in entries)
        )
        self.assertFalse(any("status" in entry for entry in entries))

    def test_target_specializations_do_not_rewrite_source(self):
        catalog = self.read_json(ROOT, self.catalog.CATALOG_PATH)
        coverage = self.read_json(ROOT, self.catalog.COVERAGE_PATH)
        entries = {entry["scenario"]: entry for entry in coverage["entries"]}
        self.assertEqual(
            self.catalog.A002_SPECIALIZATION, entries["A-002"]["specialization"]
        )
        self.assertEqual(
            self.catalog.W008_SPECIALIZATION, entries["W-008"]["specialization"]
        )
        source = self.catalog.reconstruct_source(catalog).encode("utf-8")
        self.assertEqual(self.catalog.SOURCE_SHA256, self.catalog.sha256_bytes(source))

    def test_c004_remains_pending_agreement(self):
        coverage = self.read_json(ROOT, self.catalog.COVERAGE_PATH)
        c004 = next(
            entry for entry in coverage["entries"] if entry["scenario"] == "C-004"
        )
        self.assertEqual("pending-agreement", c004["disposition"])
        self.assertEqual(self.catalog.C004_AGREEMENT_ISSUE, c004["agreement_issue"])
        self.assertEqual("not-run", c004["verification_state"])

    def test_c004_accepts_only_versioned_issue7_agreement_transition(self):
        fixture = self.copy_fixture()
        agreement = "docs/agreements/adr/ADR-0005-issue-graph-authority.md"
        agreement_path = fixture / agreement
        agreement_path.parent.mkdir(parents=True, exist_ok=True)
        agreement_path.write_text("# Human-reviewed agreement\n", encoding="utf-8")

        def decide(payload):
            c004 = next(
                entry for entry in payload["entries"] if entry["scenario"] == "C-004"
            )
            c004["disposition"] = "agreement-decision"
            c004["agreement_adr"] = agreement

        self.mutate_json(fixture, self.catalog.COVERAGE_PATH, decide)
        self.assertEqual([], self.catalog.validate_coverage(fixture))

    def test_results_and_phase_release_remain_blocked(self):
        results = self.read_json(ROOT, self.catalog.RESULTS_PATH)
        phase = self.read_json(ROOT, self.catalog.PHASE_MANIFEST_PATH)
        self.assertEqual([], results["results"])
        self.assertEqual(0, results["result_count"])
        self.assertIs(results["release_blocked"], True)
        self.assertNotIn("coverage", results)
        self.assertEqual([], phase["results"])
        self.assertIs(phase["release_blocked"], True)

    def test_source_provenance_has_reviewed_hashes_and_no_private_path(self):
        provenance = self.read_json(ROOT, self.catalog.SOURCE_MANIFEST_PATH)
        self.assertEqual(
            self.catalog.RESEARCH_ARCHIVE_SHA256,
            provenance["research_archive"]["sha256"],
        )
        self.assertEqual(
            self.catalog.SOURCE_SHA256,
            provenance["scenario_member"]["sha256"],
        )
        self.assertEqual(
            self.catalog.RESEARCH_ARCHIVE_MEMBER,
            provenance["scenario_member"]["archive_member"],
        )
        self.assertEqual(
            self.catalog.SOURCE_BASELINE_REPOSITORY,
            provenance["source_baseline"]["repository"],
        )
        self.assertEqual(
            self.catalog.SOURCE_BASELINE_COMMIT,
            provenance["source_baseline"]["commit"],
        )
        self.assertEqual(
            7, provenance["research_archive"]["supplied_files_verified"]
        )
        conversion = provenance["conversion"]
        self.assertEqual(
            [
                self.catalog.SOURCE_MANIFEST_PATH,
                self.catalog.CATALOG_PATH,
                self.catalog.CATALOG_SCHEMA_PATH,
            ],
            conversion["import_outputs"],
        )
        self.assertEqual(
            [
                self.catalog.COVERAGE_PATH,
                self.catalog.COVERAGE_SCHEMA_PATH,
                self.catalog.RESULTS_PATH,
                self.catalog.RESULTS_SCHEMA_PATH,
            ],
            conversion["independent_update_authorities"],
        )
        self.assertEqual(
            self.catalog.HUMAN_CATALOG_PATH, conversion["render_output"]
        )
        self.assertEqual(
            f"python3 {self.catalog.TOOL_PATH} import", conversion["import_write"]
        )
        self.assertEqual(
            f"python3 {self.catalog.TOOL_PATH} render", conversion["render_write"]
        )
        self.assertEqual([], list(self.catalog.private_path_values(provenance)))
        advisory = provenance["independent_full_text_comparison"]
        self.assertEqual("advisory", advisory["classification"])
        self.assertIs(advisory["required_approver"], False)

    def test_import_and_render_check_modes_are_non_mutating(self):
        fixture = self.copy_fixture()
        before = {
            relative: (fixture / relative).read_bytes()
            for relative in self.fixture_paths()
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_import(fixture, True))
            self.assertEqual(0, self.catalog.run_render(fixture, True))
        after = {
            relative: (fixture / relative).read_bytes()
            for relative in self.fixture_paths()
        }
        self.assertEqual(before, after)

    def test_import_write_is_reproducible(self):
        fixture = self.copy_fixture()
        expected = {
            relative: (fixture / relative).read_bytes()
            for relative in (
                self.catalog.SOURCE_MANIFEST_PATH,
                self.catalog.CATALOG_PATH,
                self.catalog.CATALOG_SCHEMA_PATH,
            )
        }
        for relative in expected:
            (fixture / relative).unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_import(fixture, False))
        self.assertEqual(
            expected,
            {relative: (fixture / relative).read_bytes() for relative in expected},
        )

    def test_import_write_preserves_future_coverage_and_results_bytes(self):
        fixture = self.copy_fixture()

        def advance_coverage(payload):
            c004 = next(
                entry for entry in payload["entries"] if entry["scenario"] == "C-004"
            )
            c004["disposition"] = "agreement-decision"
            c004["agreement_adr"] = (
                "docs/agreements/adr/ADR-0005-issue-graph-authority.md"
            )

        def add_future_result(payload):
            payload["result_count"] = 1
            payload["results"] = [
                {
                    "scenario": "C-001",
                    "status": "unverified",
                    "source_contract": "tests/conformance/catalog.json#C-001",
                    "target_evidence": ["future-evidence"],
                    "target_commit": "a" * 40,
                    "client": {
                        "surface": "static",
                        "name": "future-checker",
                        "version": "1",
                    },
                    "observed_at": "2026-08-24T00:00:00Z",
                    "notes": "future state owned by a later Task",
                }
            ]

        self.mutate_json(fixture, self.catalog.COVERAGE_PATH, advance_coverage)
        self.mutate_json(fixture, self.catalog.RESULTS_PATH, add_future_result)
        before = {
            relative: (fixture / relative).read_bytes()
            for relative in (self.catalog.COVERAGE_PATH, self.catalog.RESULTS_PATH)
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_import(fixture, False))
        after = {
            relative: (fixture / relative).read_bytes()
            for relative in (self.catalog.COVERAGE_PATH, self.catalog.RESULTS_PATH)
        }
        self.assertEqual(before, after)

    def test_render_write_is_reproducible(self):
        fixture = self.copy_fixture()
        expected = (fixture / self.catalog.HUMAN_CATALOG_PATH).read_bytes()
        (fixture / self.catalog.HUMAN_CATALOG_PATH).unlink()
        real_open = self.catalog.open_managed_parent
        opened_descriptors = []

        def capture_open(root, relative, *, create_parents):
            descriptors = real_open(
                root, relative, create_parents=create_parents
            )
            opened_descriptors.extend(descriptors[1:3])
            return descriptors

        output = io.StringIO()
        with mock.patch.object(
            self.catalog, "open_managed_parent", side_effect=capture_open
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_render(fixture, False))
        self.assertEqual(
            expected, (fixture / self.catalog.HUMAN_CATALOG_PATH).read_bytes()
        )
        for descriptor in opened_descriptors:
            with self.assertRaises(OSError):
                self.catalog.os.fstat(descriptor)

    def test_render_is_independent_of_coverage_state(self):
        fixture = self.copy_fixture()
        expected = (fixture / self.catalog.HUMAN_CATALOG_PATH).read_bytes()
        coverage = fixture / self.catalog.COVERAGE_PATH
        coverage.write_text('{"future":"coverage state"}\n', encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_render(fixture, False))
        self.assertEqual(
            expected, (fixture / self.catalog.HUMAN_CATALOG_PATH).read_bytes()
        )

    def test_import_rejects_target_symlink_without_touching_outside_file(self):
        fixture = self.copy_fixture()
        outside = fixture.parent / "outside-import-target"
        outside.mkdir()
        sentinel = outside / "catalog.json"
        sentinel.write_bytes(b"outside sentinel\n")
        target = fixture / self.catalog.CATALOG_PATH
        target.unlink()
        target.symlink_to(sentinel)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_import(fixture, False))
        self.assertEqual(b"outside sentinel\n", sentinel.read_bytes())
        self.assertIn("target is a symlink", output.getvalue())
        self.assertNotIn(str(sentinel), output.getvalue())

    def test_import_rejects_parent_symlink_without_touching_outside_file(self):
        fixture = self.copy_fixture()
        source_parent = fixture / "tests/conformance/source"
        outside = fixture.parent / "outside-import-parent"
        shutil.move(source_parent, outside)
        source_parent.symlink_to(outside, target_is_directory=True)
        sentinel = outside / "manifest.json"
        before = sentinel.read_bytes()

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_import(fixture, False))
        self.assertEqual(before, sentinel.read_bytes())
        self.assertIn("parent is a symlink", output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())

    def test_render_rejects_target_symlink_without_touching_outside_file(self):
        fixture = self.copy_fixture()
        outside = fixture.parent / "outside-render-target"
        outside.mkdir()
        sentinel = outside / "catalog.md"
        sentinel.write_bytes(b"outside sentinel\n")
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        target.unlink()
        target.symlink_to(sentinel)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, False))
        self.assertEqual(b"outside sentinel\n", sentinel.read_bytes())
        self.assertIn("target is a symlink", output.getvalue())
        self.assertNotIn(str(sentinel), output.getvalue())

    def test_render_rejects_parent_symlink_without_touching_outside_file(self):
        fixture = self.copy_fixture()
        render_parent = fixture / "docs/conformance"
        outside = fixture.parent / "outside-render-parent"
        shutil.move(render_parent, outside)
        render_parent.symlink_to(outside, target_is_directory=True)
        sentinel = outside / "catalog.md"
        before = sentinel.read_bytes()

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, False))
        self.assertEqual(before, sentinel.read_bytes())
        self.assertIn("parent is a symlink", output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())

    def test_import_parent_swap_race_cannot_write_through_external_symlink(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.CATALOG_PATH
        target.unlink()
        parent = target.parent
        opened_parent = fixture.parent / "opened-import-parent"
        outside = fixture.parent / "outside-import-race"
        outside.mkdir()
        sentinel = outside / target.name
        sentinel.write_bytes(b"outside sentinel\n")
        real_open = self.catalog.open_managed_parent
        swapped = False
        opened_descriptors = []

        def open_then_swap(root, relative, *, create_parents):
            nonlocal swapped
            descriptors = real_open(
                root, relative, create_parents=create_parents
            )
            if relative == self.catalog.CATALOG_PATH:
                opened_descriptors.extend(descriptors[1:3])
            if relative == self.catalog.CATALOG_PATH and not swapped:
                parent.rename(opened_parent)
                parent.symlink_to(outside, target_is_directory=True)
                swapped = True
            return descriptors

        output = io.StringIO()
        with mock.patch.object(
            self.catalog, "open_managed_parent", side_effect=open_then_swap
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_import(fixture, False))

        self.assertTrue(swapped)
        self.assertEqual(b"outside sentinel\n", sentinel.read_bytes())
        self.assertFalse((opened_parent / target.name).exists())
        self.assertEqual([], list(opened_parent.glob(f".{target.name}.*.tmp")))
        self.assertIn("parent changed during operation", output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())
        for descriptor in opened_descriptors:
            with self.assertRaises(OSError):
                self.catalog.os.fstat(descriptor)

    def test_rename_window_parent_swap_stays_on_open_directory_and_fails(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        expected = target.read_bytes()
        target.unlink()
        parent = target.parent
        opened_parent = fixture.parent / "opened-render-parent"
        outside = fixture.parent / "outside-render-race"
        outside.mkdir()
        sentinel = outside / target.name
        sentinel.write_bytes(b"outside sentinel\n")
        real_rename = self.catalog.os.rename
        swapped = False

        def swap_then_rename(
            source,
            destination,
            *,
            src_dir_fd=None,
            dst_dir_fd=None,
        ):
            nonlocal swapped
            real_rename(parent, opened_parent)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
            return real_rename(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )

        output = io.StringIO()
        with mock.patch.object(
            self.catalog.os, "rename", side_effect=swap_then_rename
        ) as patched_rename:
            supported = set(self.catalog.os.supports_dir_fd)
            supported.add(patched_rename)
            with mock.patch.object(
                self.catalog.os, "supports_dir_fd", supported
            ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(1, self.catalog.run_render(fixture, False))

        self.assertTrue(swapped)
        self.assertEqual(b"outside sentinel\n", sentinel.read_bytes())
        self.assertEqual(expected, (opened_parent / target.name).read_bytes())
        self.assertEqual([], list(opened_parent.glob(f".{target.name}.*.tmp")))
        self.assertIn("parent changed during operation", output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())

    def test_render_check_parent_swap_cannot_accept_external_projection(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        expected = target.read_bytes()
        parent = target.parent
        opened_parent = fixture.parent / "opened-render-check-parent"
        outside = fixture.parent / "outside-render-check-race"
        outside.mkdir()
        sentinel = outside / target.name
        sentinel.write_bytes(expected)
        real_open = self.catalog.open_managed_parent
        swapped = False

        def open_then_swap(root, relative, *, create_parents):
            nonlocal swapped
            descriptors = real_open(
                root, relative, create_parents=create_parents
            )
            if relative == self.catalog.HUMAN_CATALOG_PATH and not swapped:
                parent.rename(opened_parent)
                parent.symlink_to(outside, target_is_directory=True)
                swapped = True
            return descriptors

        output = io.StringIO()
        with mock.patch.object(
            self.catalog, "open_managed_parent", side_effect=open_then_swap
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, True))

        self.assertTrue(swapped)
        self.assertEqual(expected, sentinel.read_bytes())
        self.assertEqual(expected, (opened_parent / target.name).read_bytes())
        self.assertIn("parent changed during operation", output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())

    def test_root_swap_after_open_is_detected_before_target_replace(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        target.unlink()
        opened_root = fixture.parent / "opened-repository-root"
        replacement_sentinel = fixture.parent / "replacement sentinel"
        real_open = self.catalog.open_managed_parent
        swapped = False

        def open_then_swap_root(root, relative, *, create_parents):
            nonlocal swapped
            descriptors = real_open(
                root, relative, create_parents=create_parents
            )
            if relative == self.catalog.HUMAN_CATALOG_PATH and not swapped:
                fixture.rename(opened_root)
                (fixture / target.parent.relative_to(fixture)).mkdir(
                    parents=True
                )
                replacement = fixture / target.relative_to(fixture)
                replacement.write_bytes(b"outside sentinel\n")
                replacement_sentinel.write_bytes(b"outside sentinel\n")
                swapped = True
            return descriptors

        output = io.StringIO()
        with mock.patch.object(
            self.catalog, "open_managed_parent", side_effect=open_then_swap_root
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, False))

        replacement = fixture / target.relative_to(fixture)
        self.assertTrue(swapped)
        self.assertEqual(b"outside sentinel\n", replacement.read_bytes())
        self.assertEqual(b"outside sentinel\n", replacement_sentinel.read_bytes())
        moved_target = opened_root / target.relative_to(fixture)
        self.assertFalse(moved_target.exists())
        self.assertEqual(
            [], list(moved_target.parent.glob(f".{target.name}.*.tmp"))
        )
        self.assertIn("parent changed during operation", output.getvalue())
        self.assertNotIn(str(fixture), output.getvalue())

    def test_benign_ancestor_symlink_is_canonicalized_before_root_walk(self):
        fixture = self.copy_fixture()
        ancestor_link = fixture.parent / "repository-parent-link"
        ancestor_link.symlink_to(fixture.parent, target_is_directory=True)
        aliased_root = ancestor_link / fixture.name
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(0, self.catalog.run_render(aliased_root, True))

    def test_target_fifo_swap_between_stat_and_open_fails_without_blocking(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        real_stat = self.catalog.os.stat
        swapped = False

        def stat_then_fifo(path, *args, **kwargs):
            nonlocal swapped
            observed = real_stat(path, *args, **kwargs)
            if (
                path == target.name
                and kwargs.get("dir_fd") is not None
                and not swapped
            ):
                target.unlink()
                self.catalog.os.mkfifo(target)
                swapped = True
            return observed

        output = io.StringIO()
        with mock.patch.object(
            self.catalog.os, "stat", side_effect=stat_then_fifo
        ) as patched_stat:
            dir_fd_support = set(self.catalog.os.supports_dir_fd)
            dir_fd_support.add(patched_stat)
            follow_support = set(self.catalog.os.supports_follow_symlinks)
            follow_support.add(patched_stat)
            with mock.patch.object(
                self.catalog.os, "supports_dir_fd", dir_fd_support
            ), mock.patch.object(
                self.catalog.os, "supports_follow_symlinks", follow_support
            ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(1, self.catalog.run_render(fixture, False))

        self.assertTrue(swapped)
        self.assertTrue(target.is_fifo())
        self.assertIn("target is not a regular file", output.getvalue())

    def test_parent_fsync_failure_is_non_success_without_temp_residue(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        expected = target.read_bytes()
        target.unlink()
        real_fsync = self.catalog.os.fsync

        def fail_directory_fsync(descriptor):
            if self.catalog.stat.S_ISDIR(
                self.catalog.os.fstat(descriptor).st_mode
            ):
                raise OSError("private filesystem detail")
            return real_fsync(descriptor)

        output = io.StringIO()
        with mock.patch.object(
            self.catalog.os, "fsync", side_effect=fail_directory_fsync
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, False))

        self.assertEqual(expected, target.read_bytes())
        self.assertEqual([], list(target.parent.glob(f".{target.name}.*.tmp")))
        self.assertIn("managed output cannot be written", output.getvalue())
        self.assertNotIn("private filesystem detail", output.getvalue())

    def test_temp_cleanup_failure_has_bounded_non_success_diagnostic(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.CATALOG_PATH
        target.unlink()
        parent = target.parent
        opened_parent = fixture.parent / "opened-cleanup-parent"
        outside = fixture.parent / "outside-cleanup-race"
        outside.mkdir()
        sentinel = outside / target.name
        sentinel.write_bytes(b"outside sentinel\n")
        real_open = self.catalog.open_managed_parent
        real_unlink = self.catalog.os.unlink
        swapped = False

        def open_then_swap(root, relative, *, create_parents):
            nonlocal swapped
            descriptors = real_open(
                root, relative, create_parents=create_parents
            )
            if relative == self.catalog.CATALOG_PATH and not swapped:
                parent.rename(opened_parent)
                parent.symlink_to(outside, target_is_directory=True)
                swapped = True
            return descriptors

        def fail_temp_unlink(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith(f".{target.name}."):
                raise OSError("private cleanup detail")
            return real_unlink(path, *args, **kwargs)

        output = io.StringIO()
        with mock.patch.object(
            self.catalog, "open_managed_parent", side_effect=open_then_swap
        ), mock.patch.object(
            self.catalog.os, "unlink", side_effect=fail_temp_unlink
        ) as patched_unlink:
            supported = set(self.catalog.os.supports_dir_fd)
            supported.add(patched_unlink)
            with mock.patch.object(
                self.catalog.os, "supports_dir_fd", supported
            ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(1, self.catalog.run_import(fixture, False))

        leftovers = list(opened_parent.glob(f".{target.name}.*.tmp"))
        self.assertTrue(swapped)
        self.assertEqual(b"outside sentinel\n", sentinel.read_bytes())
        self.assertEqual(1, len(leftovers))
        self.assertIn("temporary cleanup could not be confirmed", output.getvalue())
        self.assertNotIn(leftovers[0].name, output.getvalue())
        self.assertNotIn("private cleanup detail", output.getvalue())

    def test_check_and_write_modes_fail_closed_without_no_follow_support(self):
        fixture = self.copy_fixture()
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        before = target.read_bytes()
        output = io.StringIO()
        with mock.patch.object(self.catalog.os, "O_NOFOLLOW", 0), \
             contextlib.redirect_stdout(output), \
             contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_render(fixture, True))
            self.assertEqual(1, self.catalog.run_render(fixture, False))
        self.assertEqual(before, target.read_bytes())
        self.assertIn("safe descriptor operations are unsupported", output.getvalue())
        self.assertIn("safe managed output writes are unsupported", output.getvalue())

    def test_write_mode_rejects_symlinked_repository_root(self):
        fixture = self.copy_fixture()
        root_link = fixture.parent / "repository-link"
        root_link.symlink_to(fixture, target_is_directory=True)
        target = fixture / self.catalog.HUMAN_CATALOG_PATH
        before = target.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(
                1,
                self.catalog.main(
                    ["render", "--root", str(root_link)]
                ),
            )
        self.assertEqual(before, target.read_bytes())
        self.assertIn("repository root cannot be opened safely", output.getvalue())
        self.assertNotIn(str(fixture), output.getvalue())

    def test_missing_input_diagnostic_does_not_disclose_fixture_path(self):
        fixture = self.copy_fixture()
        (fixture / self.catalog.SOURCE_PATH).unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(1, self.catalog.run_import(fixture, True))
        rendered = output.getvalue()
        self.assertIn("scenario source cannot be read", rendered)
        self.assertNotIn(str(fixture), rendered)
        self.assertNotIn("No such file", rendered)

    def test_source_content_drift_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.SOURCE_PATH
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "GitHub outranks thread narrative",
                "Thread narrative outranks GitHub",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "source SHA-256")

    def test_crlf_source_drift_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.SOURCE_PATH
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))
        self.assert_rejected(self.errors_for(fixture), "LF line endings")

    def test_non_normalized_source_unicode_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.SOURCE_PATH
        text = path.read_text(encoding="utf-8")
        text = text.replace("GitHub", unicodedata.normalize("NFD", "GítHub"), 1)
        path.write_text(text, encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "NFC-normalized Unicode")

    def test_duplicate_json_key_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.CATALOG_PATH
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '  "schema": "conformance-catalog/v1",',
                '  "schema": "conformance-catalog/v1",\n'
                '  "schema": "duplicate",',
                1,
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "duplicate object key")

    def test_duplicate_private_json_key_is_not_reflected_by_run_check(self):
        fixture = self.copy_fixture()
        secret = "DUPLICATE_SECRET_7F31"
        injection = "INJECTED_DIAGNOSTIC_LINE"
        private_key = f"/Users/private/person/{secret}\n{injection}"
        path = fixture / self.catalog.RESULTS_PATH
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "{\n",
                "{\n"
                f"  {json.dumps(private_key)}: 1,\n"
                f"  {json.dumps(private_key)}: 2,\n",
                1,
            ),
            encoding="utf-8",
        )

        status, rendered = self.capture_command(self.catalog.run_check, fixture)
        self.assertEqual(1, status)
        self.assertIn("duplicate object key", rendered)
        self.assert_no_sensitive_reflection(rendered, fixture, secret, injection)

    def test_unsupported_private_json_key_is_counted_not_reflected(self):
        fixture = self.copy_fixture()
        secret = "WINDOWS_KEY_SECRET_29B4"
        private_key = rf"C:\private\person\{secret}"

        def add_unsupported_keys(payload):
            payload[private_key] = True
            payload["entries"][0][f"/home/private/person/{secret}"] = True

        self.mutate_json(
            fixture,
            self.catalog.COVERAGE_PATH,
            add_unsupported_keys,
        )

        status, rendered = self.capture_command(self.catalog.run_check, fixture)
        self.assertEqual(1, status)
        self.assertIn("invalid key set (missing=0, unsupported=1)", rendered)
        self.assert_no_sensitive_reflection(rendered, fixture, secret)

    def test_private_marker_in_dict_key_uses_safe_structural_location(self):
        fixture = self.copy_fixture()
        secret = "PROVENANCE_KEY_SECRET_441A"
        private_key = f"/home/private/person/{secret}"
        self.mutate_json(
            fixture,
            self.catalog.SOURCE_MANIFEST_PATH,
            lambda payload: payload.update({private_key: "present"}),
        )

        status, rendered = self.capture_command(self.catalog.run_check, fixture)
        self.assertEqual(1, status)
        self.assertIn("private local path material", rendered)
        self.assertIn(".<key>", rendered)
        self.assert_no_sensitive_reflection(rendered, fixture, secret)

    def test_private_location_report_is_capped_and_omits_raw_keys_and_values(self):
        fixture = self.copy_fixture()
        secret = "MANY_PRIVATE_LOCATIONS_77D2"

        def add_private_material(payload):
            for index in range(10):
                payload[f"/Users/private/{secret}/key-{index}"] = (
                    f"/home/private/{secret}/value-{index}"
                )

        self.mutate_json(
            fixture,
            self.catalog.SOURCE_MANIFEST_PATH,
            add_private_material,
        )
        status, rendered = self.capture_command(self.catalog.run_check, fixture)
        self.assertEqual(1, status)
        self.assertIn("additional locations omitted", rendered)
        self.assertLessEqual(rendered.count("$[depth="), 8)
        self.assert_no_sensitive_reflection(rendered, fixture, secret)

    def test_malformed_private_json_reports_only_line_and_column(self):
        fixture = self.copy_fixture()
        secret = "MALFORMED_JSON_SECRET_A11C"
        private_key = f"/Users/private/person/{secret}"
        (fixture / self.catalog.RESULTS_PATH).write_text(
            "{\n" + f"  {json.dumps(private_key)}: ,\n" + "}\n",
            encoding="utf-8",
        )

        status, rendered = self.capture_command(self.catalog.run_check, fixture)
        self.assertEqual(1, status)
        self.assertIn("not valid JSON (line 2, column", rendered)
        self.assert_no_sensitive_reflection(rendered, fixture, secret)

    def test_private_source_content_is_hash_gated_before_parse(self):
        fixture = self.copy_fixture()
        secret = "SOURCE_TITLE_SECRET_5D20"
        path = fixture / self.catalog.SOURCE_PATH
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "## 1. Core durable-truth and orchestration",
            f"## 1. /Users/private/person/{secret}",
            1,
        ).replace("### C-002", "### A-002", 1)
        path.write_text(text, encoding="utf-8")

        check_status, check_output = self.capture_command(
            self.catalog.run_check, fixture
        )
        import_status, import_output = self.capture_command(
            lambda root: self.catalog.run_import(root, True), fixture
        )
        self.assertEqual(1, check_status)
        self.assertEqual(1, import_status)
        self.assertIn("source SHA-256", check_output)
        self.assertIn("source SHA-256", import_output)
        self.assert_no_sensitive_reflection(check_output, fixture, secret)
        self.assert_no_sensitive_reflection(import_output, fixture, secret)
        with self.assertRaises(self.catalog.CatalogError) as parse_error:
            self.catalog.parse_source(text)
        self.assertIn("family section index 1", str(parse_error.exception))
        self.assertNotIn(secret, str(parse_error.exception))
        self.assertNotIn("/Users/", str(parse_error.exception))

    def test_invalid_utf8_and_raw_oserror_details_are_not_reflected(self):
        secret = "SOURCE_IO_SECRET_D808"

        invalid_fixture = self.copy_fixture()
        (invalid_fixture / self.catalog.SOURCE_PATH).write_bytes(
            f"/Users/private/person/{secret}\n".encode("utf-8") + b"\xff\n"
        )
        invalid_status, invalid_output = self.capture_command(
            lambda root: self.catalog.run_import(root, True), invalid_fixture
        )
        self.assertEqual(1, invalid_status)
        self.assertIn("scenario source is not valid UTF-8", invalid_output)
        self.assert_no_sensitive_reflection(
            invalid_output, invalid_fixture, secret
        )
        self.assertNotIn("byte 0xff", invalid_output)
        self.assertNotIn("position", invalid_output)

        error_fixture = self.copy_fixture()
        raw_error = f"/home/private/person/{secret}: raw OSError detail"
        with mock.patch.object(Path, "read_bytes", side_effect=OSError(raw_error)):
            error_status, error_output = self.capture_command(
                lambda root: self.catalog.run_import(root, True), error_fixture
            )
        self.assertEqual(1, error_status)
        self.assertIn("scenario source cannot be read", error_output)
        self.assert_no_sensitive_reflection(error_output, error_fixture, secret)
        self.assertNotIn("raw OSError detail", error_output)

    def test_pathological_json_failures_have_bounded_diagnostics(self):
        cases = {
            "deep": "[" * 1200 + "0" + "]" * 1200 + "\n",
            "huge-integer": "{\"value\":" + "9" * 5000 + "}\n",
            "lone-surrogate": "{\"value\":\"\\ud800\"}\n",
        }
        for name, content in cases.items():
            with self.subTest(case=name):
                fixture = self.copy_fixture()
                (fixture / self.catalog.RESULTS_PATH).write_text(
                    content, encoding="utf-8"
                )
                status, rendered = self.capture_command(
                    self.catalog.run_check, fixture
                )
                self.assertEqual(1, status)
                self.assertLess(len(rendered), 4096)
                self.assertNotIn("Traceback", rendered)
                self.assert_no_sensitive_reflection(rendered, fixture)

    def test_noncanonical_json_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.COVERAGE_PATH
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        self.assert_rejected(self.errors_for(fixture), "canonical JSON form")

    def test_catalog_source_body_drift_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            payload["families"][0]["scenarios"][0][
                "source_body_markdown"
            ] += "drift\n"

        self.mutate_json(fixture, self.catalog.CATALOG_PATH, mutate)
        self.assert_rejected(self.errors_for(fixture), "deterministic import output")

    def test_catalog_scenario_gap_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            payload["families"][0]["scenarios"].pop(1)

        self.mutate_json(fixture, self.catalog.CATALOG_PATH, mutate)
        errors = self.errors_for(fixture)
        self.assert_rejected(errors, "deterministic import output")
        self.assert_rejected(errors, "scenario IDs")

    def test_schema_drift_is_rejected(self):
        fixture = self.copy_fixture()
        self.mutate_json(
            fixture,
            self.catalog.CATALOG_SCHEMA_PATH,
            lambda payload: payload.update({"title": "weakened"}),
        )
        self.assert_rejected(self.errors_for(fixture), "deterministic import output")

    def test_independent_contract_schema_drift_is_rejected(self):
        for relative in (
            self.catalog.COVERAGE_SCHEMA_PATH,
            self.catalog.RESULTS_SCHEMA_PATH,
        ):
            with self.subTest(path=relative):
                fixture = self.copy_fixture()
                self.mutate_json(
                    fixture,
                    relative,
                    lambda payload: payload.update({"title": "weakened"}),
                )
                self.assert_rejected(
                    self.errors_for(fixture), "differs from its deterministic contract"
                )

    def test_coverage_gap_is_rejected(self):
        fixture = self.copy_fixture()
        self.mutate_json(
            fixture,
            self.catalog.COVERAGE_PATH,
            lambda payload: payload["entries"].pop(),
        )
        self.assert_rejected(self.errors_for(fixture), "one entry per scenario")

    def test_illegal_coverage_disposition_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            payload["entries"][0]["disposition"] = "passed"

        self.mutate_json(fixture, self.catalog.COVERAGE_PATH, mutate)
        self.assert_rejected(self.errors_for(fixture), "disposition must remain planned")

    def test_specialization_drift_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            next(
                entry for entry in payload["entries"] if entry["scenario"] == "A-002"
            )["specialization"] = "nested files always load"

        self.mutate_json(fixture, self.catalog.COVERAGE_PATH, mutate)
        self.assert_rejected(self.errors_for(fixture), "A-002 target specialization")

    def test_c004_agreement_drift_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            entry = next(
                item for item in payload["entries"] if item["scenario"] == "C-004"
            )
            entry["disposition"] = "planned"
            entry.pop("agreement_issue")

        self.mutate_json(fixture, self.catalog.COVERAGE_PATH, mutate)
        self.assert_rejected(
            self.errors_for(fixture),
            "C-004 must be pending-agreement or a versioned agreement-decision",
        )

    def test_synthetic_result_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            payload["result_count"] = 1
            payload["results"] = [
                {
                    "scenario": "C-001",
                    "status": "pass",
                    "source_contract": "invented",
                    "target_evidence": ["none"],
                    "target_commit": "a" * 40,
                    "client": {
                        "surface": "static",
                        "name": "synthetic",
                        "version": "1",
                    },
                    "observed_at": "2026-08-24T00:00:00Z",
                    "notes": "synthetic",
                }
            ]

        self.mutate_json(fixture, self.catalog.RESULTS_PATH, mutate)
        self.assert_rejected(self.errors_for(fixture), "results must remain empty")

    def test_result_release_unblock_is_rejected(self):
        fixture = self.copy_fixture()
        self.mutate_json(
            fixture,
            self.catalog.RESULTS_PATH,
            lambda payload: payload.update({"release_blocked": False}),
        )
        self.assert_rejected(self.errors_for(fixture), "release_blocked true")

    def test_phase_release_unblock_is_rejected(self):
        fixture = self.copy_fixture()
        self.mutate_json(
            fixture,
            self.catalog.PHASE_MANIFEST_PATH,
            lambda payload: payload.update({"release_blocked": False}),
        )
        self.assert_rejected(
            self.errors_for(fixture), "Phase conformance manifest must keep"
        )

    def test_phase0_results_sentinel_drift_is_rejected(self):
        fixture = self.copy_fixture()
        self.mutate_json(
            fixture,
            self.catalog.PHASE_MANIFEST_PATH,
            lambda payload: payload.update({"results": [{"synthetic": True}]}),
        )
        self.assert_rejected(self.errors_for(fixture), "compatibility results sentinel")

    def test_phase_asset_hash_drift_is_rejected(self):
        fixture = self.copy_fixture()

        def mutate(payload):
            payload["scenario_catalog"]["definitions"]["sha256"] = "0" * 64

        self.mutate_json(fixture, self.catalog.PHASE_MANIFEST_PATH, mutate)
        self.assert_rejected(self.errors_for(fixture), "asset/hash links drifted")

    def test_rendered_markdown_drift_is_rejected(self):
        fixture = self.copy_fixture()
        path = fixture / self.catalog.HUMAN_CATALOG_PATH
        path.write_text(
            path.read_text(encoding="utf-8") + "manual edit\n",
            encoding="utf-8",
        )
        self.assert_rejected(self.errors_for(fixture), "deterministic output")

    def test_private_provenance_path_delimiter_bypasses_are_rejected(self):
        markers = (
            "path=/Users/example/private.zip",
            "[/home/example/private.zip]",
            r"path=C:\private\pack.zip",
        )
        for marker in markers:
            with self.subTest(marker=marker):
                fixture = self.copy_fixture()

                def mutate(payload):
                    payload["research_archive"]["file_name"] = marker

                self.mutate_json(fixture, self.catalog.SOURCE_MANIFEST_PATH, mutate)
                self.assert_rejected(
                    self.errors_for(fixture), "private local path material"
                )

    def test_https_url_is_not_misclassified_as_windows_drive_path(self):
        self.assertEqual(
            [],
            list(
                self.catalog.private_path_values(
                    {"url": "https://github.com/example/repository"}
                )
            ),
        )

    def test_all_schema_assets_use_json_schema_2020_12(self):
        for relative in (
            self.catalog.CATALOG_SCHEMA_PATH,
            self.catalog.COVERAGE_SCHEMA_PATH,
            self.catalog.RESULTS_SCHEMA_PATH,
        ):
            with self.subTest(path=relative):
                payload = self.read_json(ROOT, relative)
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema",
                    payload["$schema"],
                )
                self.assertIs(payload["additionalProperties"], False)

    def test_result_schema_binds_head_client_and_deviation_adr(self):
        schema = self.read_json(ROOT, self.catalog.RESULTS_SCHEMA_PATH)
        self.assertNotIn("coverage", schema["properties"])
        self.assertNotIn("coverage", schema["required"])
        item = schema["properties"]["results"]["items"]
        self.assertIn("target_commit", item["required"])
        self.assertEqual(
            "^[0-9a-f]{40}$",
            item["properties"]["target_commit"]["pattern"],
        )
        client = item["properties"]["client"]
        self.assertEqual(["surface", "name", "version"], client["required"])
        self.assertIs(client["additionalProperties"], False)
        deviation_rule = item["allOf"][0]
        self.assertEqual(
            "approved-deviation",
            deviation_rule["if"]["properties"]["status"]["const"],
        )
        self.assertEqual(["deviation_adr"], deviation_rule["then"]["required"])

    def test_coverage_schema_supports_only_versioned_c004_decision(self):
        schema = self.read_json(ROOT, self.catalog.COVERAGE_SCHEMA_PATH)
        item = schema["properties"]["entries"]["items"]
        self.assertIn(
            "agreement-decision",
            item["properties"]["disposition"]["enum"],
        )
        self.assertEqual(
            self.catalog.C004_AGREEMENT_ISSUE,
            item["properties"]["agreement_issue"]["const"],
        )
        decision = next(
            rule
            for rule in item["allOf"]
            if rule["if"]["properties"]["disposition"]["const"]
            == "agreement-decision"
        )
        self.assertEqual(
            ["agreement_issue", "agreement_adr"],
            decision["then"]["required"],
        )


if __name__ == "__main__":
    unittest.main()
