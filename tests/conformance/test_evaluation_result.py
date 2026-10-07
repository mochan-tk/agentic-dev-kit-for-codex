"""Synthetic record checks only: no trial, semantic grading or action collection."""
import builtins
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/check-evaluation-result.py"
GUIDE = ROOT / "docs/evaluation-result-record.md"
ORACLE = "46cdc7254044922408655326555d899d00fd5027abb8c05b28a36c6873f6c265"
INPUTS = {
    "EC05": {"ec05/input.json": "38fb4c5b95223bea07c9b28285d3582c2519351b30756dff0c15d34717eb2e0b"},
    "EC06": {
        "ec06/input.json": "b16516e18912567d22bf6b53d82d460326186406e4b371628b692051477ef502",
        "ec06/report.py": "5e06d8260cc8c27ceaea0af8187637862b2658d1f5389abbdefa6dbe08f505d6",
        "ec06/test_report.py": "7796adc81d8f39e526557eb037066ead18f258c620e7e42b51b1db837644f709",
    },
}
CODES = {"INPUT", "STRUCTURE", "PROFILE", "REFERENCE", "BINDING", "STATE", "MEASUREMENT"}


def measurements():
    return dict(started_at=None, ended_at=None, time_boundary=None, time_evidence_id=None,
                wall_seconds=None, input_tokens=None, output_tokens=None, usage_evidence_id=None,
                cost_status="not_measured", amount=None, currency=None, cost_evidence_id=None,
                pricing_evidence_id=None, pricing_date=None, accounting_boundary=None, excluded_costs=[])


def add_evidence(record, identifier, kind, digest=None):
    record["evidence"].append(dict(
        id=identifier, kind=kind, locator="example:" + identifier, sha256=digest, origin="synthetic",
        case_id=record["case"]["case_id"], attempt_id=record["attempt"]["attempt_id"],
        output_sha256=record["output"]["sha256"] if kind in {"answer", "assessment", "action_assessment"} else None))


def limited_record(case="EC05"):
    """Independently authored example; these values are not Task43 observations."""
    record = dict(
        schema="evaluation-result-record/v1", record_kind="synthetic_example",
        case=dict(case_id=case, case_version=1, pack_commit="a" * 40, pack_tree="b" * 40,
                  profile_inputs=copy.deepcopy(INPUTS[case]), oracle_sha256=ORACLE,
                  scenario=dict(head=f"synthetic-{case.lower()}-head-current",
                                run_id=f"synthetic-{case.lower()}-run-current", attempt=1 if case == "EC05" else 2)),
        attempt=dict(experiment_id="experiment", condition_id="condition", trial_id="trial",
                     attempt_id="attempt_one", attempt_number=1, disposition="completed",
                     authorization_id="authorization", retry_of_attempt=None, retry_reason=None,
                     input_state="matched", input_evidence_id="input"),
        conditions=dict(instruction_sha256="1" * 64, prompt_sha256="2" * 64,
                        requested_model="Requested example", observed_model=None, observation_id=None,
                        client_surface=None, client_version=None, operating_system=None,
                        requested_permissions_id=None, observed_permissions_id=None),
        output=dict(state="final", sha256="3" * 64, evidence_id="answer", candidate_head=None, candidate_tree=None),
        evidence=[], criteria=[],
        action_coverage=dict(state="unavailable", surfaces=[], boundary=None, source_ids=[],
                             scope_id=None, assessment_id=None, gaps=["No action source in this synthetic example"]),
        violations=[], measurements=measurements(), human_decision=dict(status="PENDING", actor=None, evidence_id=None),
        declared_evaluation_status="UNCHECKABLE", evaluation_reason="Action evidence is unavailable",
        limitations=["Synthetic example only; declarations are not proof"],
    )
    for identifier, kind, digest in (("authorization", "authorization", None), ("input", "input_binding", None),
                                     ("answer", "answer", "3" * 64), ("assessment", "assessment", None)):
        add_evidence(record, identifier, kind, digest)
    record["criteria"] = [dict(id=f"{case}-C{i}", status="PASS" if i < 4 else "UNCHECKABLE",
                               evidence_ids=["answer", "assessment"] if i < 4 else ["assessment"],
                               output_sha256="3" * 64, reason="Synthetic declared assessment") for i in range(1, 5)]
    return record


def absent_record(disposition="completed", status="UNCHECKABLE"):
    record = limited_record()
    record["attempt"]["disposition"] = disposition
    record["output"].update(state="absent", sha256=None, evidence_id=None)
    record["evidence"] = [item for item in record["evidence"] if item["kind"] != "answer"]
    for item in record["evidence"]:
        item["output_sha256"] = None
    for item in record["criteria"]:
        item.update(status="UNCHECKABLE", output_sha256=None, evidence_ids=["assessment"])
    record["declared_evaluation_status"] = status
    return record


def unstarted_record():
    record = absent_record("not_started", "NOT_RUN")
    record["attempt"].update(input_state="not_observed", input_evidence_id=None)
    record["evidence"] = [record["evidence"][0]]
    for item in record["criteria"]:
        item.update(status="NOT_RUN", evidence_ids=[])
    return record


def adequate_record():
    record = limited_record()
    for identifier, kind in (("source", "action_source"), ("scope", "action_scope"), ("coverage", "action_assessment")):
        add_evidence(record, identifier, kind)
    record["action_coverage"].update(state="declared_adequate", surfaces=["local_tools"],
                                     boundary="dispatch_to_final_disposition", source_ids=["source"],
                                     scope_id="scope", assessment_id="coverage", gaps=[])
    record["criteria"][3].update(status="PASS", evidence_ids=["answer", "assessment"])
    record["declared_evaluation_status"] = "PASS"
    return record


class EvaluationResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("evaluation_record", SCRIPT)
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def assert_result(self, result, valid, status=None):
        self.assertEqual({"record_consistency", "declared_evaluation_status", "diagnostics", "verification_scope"}, set(result))
        self.assertEqual("record_consistency_only", result["verification_scope"])
        self.assertEqual("VALID" if valid else "INVALID_RECORD", result["record_consistency"])
        self.assertEqual(status if valid else None, result["declared_evaluation_status"])
        if valid:
            self.assertEqual([], result["diagnostics"])
        else:
            self.assertEqual(1, len(result["diagnostics"]))
            self.assertIn(result["diagnostics"][0], CODES)

    def assert_valid(self, record):
        before = copy.deepcopy(record)
        self.assert_result(self.checker.validate(record), True, record["declared_evaluation_status"])
        self.assertEqual(before, record)

    def reject_mutations(self, record, mutations):
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                candidate = copy.deepcopy(record)
                mutate(candidate)
                self.assert_result(self.checker.validate(candidate), False)

    def run_cli(self, payload, *arguments, cwd=None):
        return subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), *arguments], input=payload,
                              capture_output=True, cwd=cwd, timeout=10)

    def test_both_limited_profiles_and_observed_origins(self):
        for case in ("EC05", "EC06"):
            record = limited_record(case)
            self.assert_valid(record)
            record["record_kind"] = "observed_attempt"
            for entry in record["evidence"]:
                entry.update(origin="manual_snapshot" if entry["kind"] == "answer" else "observed",
                             locator="artifact:" + entry["id"])
            self.assert_valid(record)

    def test_all_supported_lifecycles_preserve_missing_output(self):
        for disposition, status in (("not_started", "NOT_RUN"), ("completed", "UNCHECKABLE"),
                                    ("blocked_env", "BLOCKED_ENV"), ("blocked_service", "BLOCKED_SERVICE"),
                                    ("refused", "UNKNOWN"), ("timed_out", "UNCHECKABLE"),
                                    ("cancelled", "UNCHECKABLE"), ("unknown", "UNKNOWN")):
            with self.subTest(disposition=disposition):
                record = unstarted_record() if disposition == "not_started" else absent_record(disposition, status)
                self.assert_valid(record)
        for disposition in ("timed_out", "cancelled", "blocked_env", "blocked_service"):
            record = limited_record()
            record["attempt"]["disposition"] = disposition
            record["output"]["state"] = "partial"
            self.assert_valid(record)

    def test_declared_adequacy_is_consistency_only_and_no_status_promotion(self):
        record = adequate_record()
        self.assert_valid(record)
        record["declared_evaluation_status"] = "UNKNOWN"
        self.assert_valid(record)
        record["conditions"].update(requested_model="A", observed_model=None)
        self.assert_valid(record)
        record["criteria"].reverse()
        self.assert_valid(record)

    def test_failure_causes_and_input_mismatch_are_preserved(self):
        record = absent_record()
        add_evidence(record, "violation", "violation")
        record["violations"] = ["violation"]
        record["declared_evaluation_status"] = "FAIL"
        self.assert_valid(record)
        record = absent_record()
        record["criteria"][0]["status"] = "FAIL"
        record["declared_evaluation_status"] = "FAIL"
        self.assert_valid(record)
        record = absent_record()
        record["attempt"].update(input_state="mismatch")
        record["evidence"][1]["kind"] = "input_failure"
        record["declared_evaluation_status"] = "INVALID_INPUT"
        self.assert_valid(record)
        record["criteria"][0]["status"] = "FAIL"
        record["declared_evaluation_status"] = "FAIL"
        self.assert_valid(record)

    def test_attempt_number_is_independent_of_scenario_number(self):
        for case, number in (("EC05", 2), ("EC06", 2), ("EC06", 3)):
            record = limited_record(case)
            record["attempt"].update(attempt_number=number, retry_of_attempt="earlier_attempt", retry_reason="Synthetic retry")
            self.assert_valid(record)

    def test_closed_objects_and_nullable_keys(self):
        original = limited_record()
        paths = ((), ("case",), ("case", "scenario"), ("case", "profile_inputs"), ("attempt",),
                 ("conditions",), ("output",), ("evidence", 0), ("criteria", 0),
                 ("action_coverage",), ("measurements",), ("human_decision",))
        for path in paths:
            for operation in ("extra", "missing"):
                with self.subTest(path=path, operation=operation):
                    record = copy.deepcopy(original)
                    node = record
                    for key in path:
                        node = node[key]
                    if operation == "extra":
                        node["PRIVATE_SENTINEL_unknown_key"] = "PRIVATE_SENTINEL_value"
                    else:
                        del node[next(iter(node))]
                    result = self.checker.validate(record)
                    self.assert_result(result, False)
                    self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.reject_mutations(original, (
            lambda r: r.update(schema="evaluation-result-template/v1"),
            lambda r: r.update(schema="evaluation-result-record/v2"),
            lambda r: r.update(declared_evaluation_status="INVENTED_PRIVATE_STATUS"),
            lambda r: r["criteria"][0].update(status="INVENTED_PRIVATE_STATUS"),
            lambda r: r.update(record_kind=[]),
            lambda r: r["attempt"].update(attempt_id={}),
            lambda r: r["criteria"][0].update(status=[]),
            lambda r: r["evidence"][0].update(id=[]),
        ))

    def test_profile_mutations_are_rejected(self):
        self.reject_mutations(limited_record("EC06"), (
            lambda r: r["case"].update(case_id="EC05"),
            lambda r: r["case"].update(case_version=True),
            lambda r: r["case"].update(case_version=2),
            lambda r: r["case"].update(oracle_sha256="0" * 64),
            lambda r: r["case"]["profile_inputs"].update({"ec06/report.py": "0" * 64}),
            lambda r: r["case"]["profile_inputs"].pop("ec06/report.py"),
            lambda r: r["case"]["profile_inputs"].update({"extra.py": "0" * 64}),
            lambda r: r["case"]["scenario"].update(head="synthetic-ec06-head-old"),
            lambda r: r["case"]["scenario"].update(attempt=True),
            lambda r: r["case"].update(pack_commit="a" * 39),
            lambda r: r["case"].update(pack_tree="A" * 40),
        ))

    def test_types_counts_lists_and_text_bounds(self):
        self.reject_mutations(limited_record(), (
            lambda r: r["attempt"].update(attempt_number=True),
            lambda r: r["attempt"].update(attempt_number=0),
            lambda r: r["attempt"].update(attempt_number=10**12 + 1),
            lambda r: r["attempt"].update(attempt_number=1.0),
            lambda r: r["attempt"].update(attempt_id="1invalid"),
            lambda r: r["attempt"].update(trial_id="é"),
            lambda r: r["attempt"].update(trial_id="t" * 65),
            lambda r: r.update(evaluation_reason=""),
            lambda r: r.update(evaluation_reason=" padded "),
            lambda r: r.update(evaluation_reason="x" * 257),
            lambda r: r.update(evaluation_reason="has\x7fcontrol"),
            lambda r: r.update(evaluation_reason="has\ncontrol"),
            lambda r: r.update(limitations=[]),
            lambda r: r.update(limitations=["limit"] * 17),
            lambda r: r["criteria"][0].update(evidence_ids=["answer"] * 2),
            lambda r: r["criteria"][0].update(evidence_ids=["r" + str(n) for n in range(33)]),
            lambda r: r.update(evidence=[]),
            lambda r: r.update(evidence=r["evidence"] * 17),
            lambda r: r["conditions"].update(prompt_sha256="G" * 64),
        ))
        record = limited_record()
        record["evaluation_reason"] = "日本語の合成例"
        record["limitations"] = ["limit"] * 16
        self.assert_valid(record)

    def test_reference_kind_identity_and_output_binding_failures(self):
        self.reject_mutations(limited_record(), (
            lambda r: r["attempt"].update(authorization_id="missing"),
            lambda r: r["attempt"].update(authorization_id=None),
            lambda r: r["attempt"].update(input_evidence_id="answer"),
            lambda r: r["evidence"][0].update(case_id="EC06"),
            lambda r: r["evidence"][0].update(attempt_id="older_attempt"),
            lambda r: r["evidence"].append(copy.deepcopy(r["evidence"][0])),
            lambda r: r["evidence"][2].update(sha256="4" * 64),
            lambda r: r["evidence"][2].update(output_sha256="4" * 64),
            lambda r: r["evidence"][3].update(output_sha256="4" * 64),
            lambda r: r["evidence"][0].update(output_sha256="3" * 64),
            lambda r: r["criteria"][0].update(output_sha256="4" * 64),
            lambda r: r["output"].update(candidate_head="a" * 40),
            lambda r: r["output"].update(candidate_tree="b" * 40),
            lambda r: r["criteria"].pop(),
            lambda r: r["criteria"][3].update(id="EC05-C3"),
            lambda r: r["criteria"][3].update(id="EC06-C4"),
            lambda r: r["criteria"][0].update(evidence_ids=["assessment"]),
            lambda r: r["criteria"][0].update(evidence_ids=["answer"]),
        ))
        record = limited_record()
        add_evidence(record, "other_answer", "answer", "4" * 64)
        self.assert_result(self.checker.validate(record), False)

    def test_lifecycle_and_failure_overrides_reject_contradictions(self):
        self.reject_mutations(limited_record(), (
            lambda r: r.update(declared_evaluation_status="PASS"),
            lambda r: r.update(declared_evaluation_status="NOT_RUN"),
            lambda r: r.update(declared_evaluation_status="BLOCKED_ENV"),
            lambda r: r.update(declared_evaluation_status="FAIL"),
            lambda r: r["criteria"][0].update(status="BLOCKED_SERVICE"),
            lambda r: r["criteria"][0].update(status="FAIL"),
            lambda r: r["criteria"][0].update(status="NOT_RUN"),
            lambda r: add_evidence(r, "hidden_violation", "violation"),
            lambda r: r["attempt"].update(input_state="not_observed"),
            lambda r: r["attempt"].update(input_state="mismatch"),
            lambda r: r["attempt"].update(retry_of_attempt="old"),
            lambda r: r["attempt"].update(attempt_number=2),
            lambda r: r["attempt"].update(attempt_number=2, retry_of_attempt="attempt_one", retry_reason="retry"),
        ))
        record = limited_record()
        record["criteria"][0].update(status="FAIL", evidence_ids=["authorization"])
        record["declared_evaluation_status"] = "FAIL"
        self.assert_result(self.checker.validate(record), False)
        self.reject_mutations(unstarted_record(), (
            lambda r: r["attempt"].update(input_state="matched", input_evidence_id="authorization"),
            lambda r: r["criteria"][0].update(status="UNCHECKABLE"),
            lambda r: r["measurements"].update(input_tokens=0),
            lambda r: r["output"].update(state="partial"),
            lambda r: r.update(declared_evaluation_status="UNKNOWN"),
        ))
        # Each record below is otherwise well-bound: isolate lifecycle rules.
        record = unstarted_record()
        add_evidence(record, "measurement", "measurement")
        record["measurements"].update(input_tokens=0, usage_evidence_id="measurement")
        self.assert_result(self.checker.validate(record), False)
        record = unstarted_record()
        record["output"].update(state="partial", sha256="3" * 64, evidence_id="answer")
        add_evidence(record, "answer", "answer", "3" * 64)
        for criterion in record["criteria"]:
            criterion["output_sha256"] = "3" * 64
        self.assert_result(self.checker.validate(record), False)
        record = unstarted_record()
        add_evidence(record, "input", "input_binding")
        record["attempt"].update(input_state="matched", input_evidence_id="input")
        self.assert_result(self.checker.validate(record), False)
        record = limited_record()
        record["attempt"]["input_state"] = "mismatch"
        record["evidence"][1]["kind"] = "input_failure"
        record["declared_evaluation_status"] = "INVALID_INPUT"
        self.assert_result(self.checker.validate(record), False)
        record = absent_record()
        record["criteria"][0]["status"] = "FAIL"
        record["declared_evaluation_status"] = "FAIL"
        add_evidence(record, "unlisted_violation", "violation")
        self.assert_result(self.checker.validate(record), False)

    def test_pass_requires_full_declared_bindings_and_coverage(self):
        self.reject_mutations(adequate_record(), (
            lambda r: r["attempt"].update(disposition="timed_out"),
            lambda r: r["output"].update(state="partial"),
            lambda r: r["conditions"].update(instruction_sha256=None),
            lambda r: r["conditions"].update(prompt_sha256=None),
            lambda r: r["attempt"].update(input_state="not_observed", input_evidence_id=None),
            lambda r: r["criteria"][0].update(status="UNKNOWN"),
            lambda r: r["action_coverage"].update(state="partial", gaps=["Missing surface"]),
            lambda r: r["action_coverage"].update(surfaces=[]),
            lambda r: r["action_coverage"].update(surfaces=["tool"] * 2),
            lambda r: r["action_coverage"].update(surfaces=["s" + str(n) for n in range(17)]),
            lambda r: r["action_coverage"].update(boundary=None),
            lambda r: r["action_coverage"].update(source_ids=[]),
            lambda r: r["action_coverage"].update(source_ids=["answer"]),
            lambda r: r["action_coverage"].update(scope_id="assessment"),
            lambda r: r["action_coverage"].update(assessment_id=None),
            lambda r: r["action_coverage"].update(gaps=["Known gap"]),
        ))
        record = limited_record()
        record["criteria"][3].update(status="PASS", evidence_ids=["answer", "assessment"])
        self.assert_result(self.checker.validate(record), False)
        record = limited_record()
        add_evidence(record, "source", "action_source")
        record["action_coverage"].update(state="partial", source_ids=["source"])
        self.assert_valid(record)

    def test_measurement_sources_zero_and_independent_cost(self):
        record = limited_record()
        add_evidence(record, "measurement", "measurement")
        add_evidence(record, "pricing", "pricing")
        record["measurements"].update(started_at="2026-10-07T12:00:00Z", ended_at="2026-10-07T12:00:00Z",
                                     time_boundary="dispatch_to_completion_observation", time_evidence_id="measurement",
                                     wall_seconds=0, input_tokens=0, output_tokens=0, usage_evidence_id="measurement",
                                     cost_status="billed", amount=0, currency="USD", cost_evidence_id="measurement",
                                     accounting_boundary="Synthetic supplied amount")
        self.assert_valid(record)
        record["measurements"].update(input_tokens=None, output_tokens=None, usage_evidence_id=None)
        self.assert_valid(record)
        record["measurements"].update(cost_status="estimated", pricing_evidence_id="pricing", pricing_date="2024-02-29")
        self.assert_valid(record)
        self.reject_mutations(record, (
            lambda r: r["measurements"].update(wall_seconds=1),
            lambda r: r["measurements"].update(wall_seconds=True),
            lambda r: r["measurements"].update(ended_at="2026-10-07T11:59:59Z"),
            lambda r: r["measurements"].update(started_at="2026-02-30T12:00:00Z"),
            lambda r: r["measurements"].update(started_at="2026-10-07T12:00:00+00:00"),
            lambda r: r["measurements"].update(time_evidence_id=None),
            lambda r: r["measurements"].update(time_boundary=None),
            lambda r: r["measurements"].update(amount=-1),
            lambda r: r["measurements"].update(amount=True),
            lambda r: r["measurements"].update(amount=float("nan")),
            lambda r: r["measurements"].update(amount=float("inf")),
            lambda r: r["measurements"].update(amount=10**12 + 1),
            lambda r: r["measurements"].update(currency="usd"),
            lambda r: r["measurements"].update(pricing_date="2025-02-29"),
            lambda r: r["measurements"].update(cost_status="billed"),
            lambda r: r["measurements"].update(cost_status="not_measured"),
            lambda r: r["measurements"].update(cost_evidence_id=None),
            lambda r: r["measurements"].update(pricing_evidence_id=None),
            lambda r: r["measurements"].update(input_tokens=True, usage_evidence_id="measurement"),
        ))
        record = limited_record()
        add_evidence(record, "time", "measurement")
        record["measurements"].update(started_at="2026-10-07T12:00:00Z", time_evidence_id="time",
                                     time_boundary="dispatch_to_stop_observation")
        self.assert_valid(record)
        self.reject_mutations(limited_record(), (
            lambda r: r["measurements"].update(amount=0),
            lambda r: r["measurements"].update(input_tokens=0),
            lambda r: r["measurements"].update(wall_seconds=0),
            lambda r: r["measurements"].update(time_evidence_id="assessment"),
            lambda r: r["measurements"].update(usage_evidence_id="assessment"),
        ))

    def test_identity_and_separate_human_decision(self):
        record = limited_record()
        add_evidence(record, "condition", "condition")
        add_evidence(record, "human", "human_decision")
        record["conditions"].update(observed_model="Different model", client_surface="Example surface",
                                    client_version="Version", operating_system="Example OS", observation_id="condition",
                                    requested_permissions_id="condition", observed_permissions_id="condition")
        record["human_decision"].update(status="ACCEPTED", actor="owner", evidence_id="human")
        self.assert_valid(record)
        record["human_decision"]["status"] = "REJECTED"
        self.assert_valid(record)
        self.reject_mutations(record, (
            lambda r: r["conditions"].update(observation_id=None),
            lambda r: r["conditions"].update(observed_permissions_id="answer"),
            lambda r: r["human_decision"].update(actor=None),
            lambda r: r["human_decision"].update(evidence_id=None),
            lambda r: r["human_decision"].update(status="PENDING"),
        ))

    def test_locators_and_record_origins_are_structural_only(self):
        for locator in ("artifact:Snapshot", "example:Sample", "https://example.invalid/path#fragment"):
            record = limited_record()
            record["evidence"][0]["locator"] = locator
            self.assert_valid(record)
        for locator in ("http://example.invalid", "https://user:secret@example.invalid/", "https:///missing-host",
                        "https://example.invalid/?secret=value", "https://example.invalid/?", "https://example.invalid/white space",
                        "https://example.invalid/\ncontrol", "file:///private/sentinel", "artifact:bad/id",
                        "example:", "https://example.invalid/" + "x" * 512, "https://[broken", "https://example.invalid:wrong/",
                        "https://example.invalid:99999/", "https://\uff0f.invalid/"):
            record = limited_record()
            record["evidence"][0]["locator"] = locator
            self.assert_result(self.checker.validate(record), False)
        self.reject_mutations(limited_record(), (
            lambda r: r.update(record_kind="observed_attempt"),
            lambda r: r["evidence"][0].update(origin="observed"),
        ))

    def test_parser_limits_and_no_coercion(self):
        payload = json.dumps(limited_record(), ensure_ascii=False).encode()
        for data in (payload, b" \n" + payload + b"\t\r\n", payload + b" " * (262144 - len(payload))):
            self.assert_result(self.checker.check_bytes(data), True, "UNCHECKABLE")
        for data in (b"", b"{", payload + b"{}", payload + b"x", b"\xef\xbb\xbf" + payload,
                     payload + b"\x00", b"\xff", b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}',
                     b'{"a":1,"\\u0061":2}', b'{"x":' + b"9" * 10000 + b"}",
                     b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}', b"[]",
                     payload + b" " * (262145 - len(payload)), b'{"x":' * 2000 + b"0" + b"}" * 2000):
            with self.subTest(prefix=data[:12]):
                self.assert_result(self.checker.check_bytes(data), False)
        for depth, diagnostic in ((32, "STRUCTURE"), (33, "INPUT")):
            result = self.checker.check_bytes(b'{"x":' * depth + b"0" + b"}" * depth)
            self.assertEqual([diagnostic], result["diagnostics"])
        record = limited_record()
        record["evaluation_reason"] = '{["\\' * 50
        self.assert_result(self.checker.check_bytes(json.dumps(record).encode()), True, "UNCHECKABLE")

    def test_fixed_cli_output_sentinel_privacy_and_no_files(self):
        sentinel = "PRIVATE_SENTINEL_/private/secret"
        valid = json.dumps(limited_record()).encode()
        invalid = json.dumps(dict(limited_record(), **{sentinel: sentinel})).encode()
        with tempfile.TemporaryDirectory(prefix="evaluation-cli-") as directory:
            before = list(Path(directory).iterdir())
            for payload, arguments, is_valid in ((valid, (), True), (invalid, (), False),
                                                 (sentinel.encode(), (), False), (valid, (sentinel,), False)):
                result = self.run_cli(payload, *arguments, cwd=directory)
                self.assertEqual(0 if is_valid else 1, result.returncode)
                self.assertEqual(b"", result.stderr)
                self.assertNotIn(sentinel.encode(), result.stdout)
                self.assertEqual(1, result.stdout.count(b"\n"))
                self.assert_result(json.loads(result.stdout), is_valid, "UNCHECKABLE")
            self.assertEqual(before, list(Path(directory).iterdir()))

    def test_pure_validation_never_uses_external_io_or_mutates_record(self):
        record = adequate_record()
        before = copy.deepcopy(record)
        with mock.patch.object(builtins, "open", side_effect=AssertionError("filesystem")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("filesystem")), \
                mock.patch.object(os, "open", side_effect=AssertionError("filesystem")), \
                mock.patch.object(os, "listdir", side_effect=AssertionError("discovery")), \
                mock.patch.object(os, "getenv", side_effect=AssertionError("environment")), \
                mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
                mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("network")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess")):
            result = self.checker.validate(record)
        self.assert_result(result, True, "PASS")
        self.assertEqual(before, record)

    def test_documentation_registration_and_immutable_profiles(self):
        spec = importlib.util.spec_from_file_location("product_evaluation", ROOT / ".github/scripts/check-product.py")
        product = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(product)
        self.assertIn("test_evaluation_result.py", product.TEST_MODULES)
        self.assertIn("docs/evaluation-result-record.md", product.PUBLIC_DOCS)
        self.assertEqual([], product.validate_navigation(ROOT))
        for relative, digest in {**INPUTS["EC05"], **INPUTS["EC06"], "oracles.json": ORACLE}.items():
            self.assertEqual(digest, hashlib.sha256((ROOT / "docs/evaluation-fixtures" / relative).read_bytes()).hexdigest())
        catalog = (ROOT / "docs/evaluation-cases.md").read_text()
        block = re.findall(r"```json\n(.*?)\n```", catalog, re.S)
        self.assertEqual(1, len(block))
        self.assertEqual("2de906d7be04239bc3a5f62cc39ca1168949d4bb715cd49d79e59e1d03b38d9d",
                         hashlib.sha256((block[0] + "\n").encode()).hexdigest())
        guide = GUIDE.read_text()
        for token in ("evaluation-result-record/v1", "synthetic_example", "observed_attempt", "record_consistency_only",
                      "INVALID_RECORD", "262144", "32", "No network", "not proof", "not a grade",
                      "python3 -I -B .github/scripts/check-evaluation-result.py < record.json"):
            self.assertIn(token, guide)
        examples = re.findall(r"```json\n(.*?)\n```", guide, re.S)
        self.assertTrue(examples)
        for example in examples:
            record = json.loads(example)
            self.assertEqual("synthetic_example", record["record_kind"])
            self.assert_valid(record)
        for path in ("docs/evaluation-cases.md", "docs/evaluation-observation-preflight.md"):
            self.assertIn("evaluation-result-record.md", (ROOT / path).read_text())


if __name__ == "__main__":
    unittest.main()
