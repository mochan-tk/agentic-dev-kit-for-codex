#!/usr/bin/env python3
"""Check one EC05/EC06 record from stdin; consistency only, never proof or grading."""
from datetime import date, datetime
import json
import math
import re
import sys
from urllib.parse import urlsplit

MAX_BYTES = 262144
MAX_DEPTH = 32
STATUSES = ("NOT_RUN", "BLOCKED_ENV", "BLOCKED_SERVICE", "UNKNOWN", "UNCHECKABLE", "INVALID_INPUT", "PASS", "FAIL")
KINDS = ("authorization", "condition", "input_binding", "input_failure", "answer", "assessment",
         "action_source", "action_scope", "action_assessment", "violation", "measurement", "pricing", "human_decision")
PROFILES = {
    "EC05": {"ec05/input.json": "38fb4c5b95223bea07c9b28285d3582c2519351b30756dff0c15d34717eb2e0b"},
    "EC06": {
        "ec06/input.json": "b16516e18912567d22bf6b53d82d460326186406e4b371628b692051477ef502",
        "ec06/report.py": "5e06d8260cc8c27ceaea0af8187637862b2658d1f5389abbdefa6dbe08f505d6",
        "ec06/test_report.py": "7796adc81d8f39e526557eb037066ead18f258c620e7e42b51b1db837644f709",
    },
}
ORACLE = "46cdc7254044922408655326555d899d00fd5027abb8c05b28a36c6873f6c265"


class InvalidRecord(Exception):
    """Only fixed, documented diagnostic codes are carried through this exception."""


def require(condition, code="STRUCTURE"):
    if not condition:
        raise InvalidRecord(code)


def closed(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()))


def enum(value, choices):
    require(type(value) is str and value in choices)


def pattern(value, expression):
    require(type(value) is str and re.fullmatch(expression, value, re.ASCII) is not None)


def identifier(value):
    pattern(value, r"[A-Za-z][A-Za-z0-9_-]{0,63}")


def digest(value):
    pattern(value, r"[0-9a-f]{64}")


def text(value):
    require(type(value) is str and 1 <= len(value) <= 256 and value.strip() == value
            and not re.search(r"[\x00-\x1f\x7f]", value))


def optional(value, check):
    if value is not None:
        check(value)


def number(value, integer=False, positive=False):
    require(type(value) is int if integer else type(value) in (int, float), "MEASUREMENT")
    require((1 if positive else 0) <= value <= 10**12 and math.isfinite(value), "MEASUREMENT")


def array(value, check, maximum, minimum=0, unique=False):
    require(type(value) is list and minimum <= len(value) <= maximum)
    for item in value:
        check(item)
    if unique:
        require(len(value) == len(set(value)))


def ids(value, maximum=32):
    array(value, identifier, maximum, unique=True)


def texts(value, minimum=0):
    array(value, text, 16, minimum)


def locator(value, synthetic):
    require(type(value) is str)
    for prefix in (("artifact:", "example:") if synthetic else ("artifact:",)):
        if value.startswith(prefix):
            identifier(value[len(prefix):])
            return
    require(len(value) <= 512 and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value), "REFERENCE")
    try:
        parsed = urlsplit(value)
        require(parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
                and parsed.password is None and "?" not in value.split("#", 1)[0], "REFERENCE")
        # Force validation of malformed brackets and ports without resolving a host.
        parsed.port
    except ValueError:
        raise InvalidRecord("REFERENCE") from None


def timestamp(value):
    pattern(value, r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
    try:
        return datetime.fromisoformat(value[:-1])
    except ValueError:
        raise InvalidRecord("MEASUREMENT") from None


def calendar_date(value):
    pattern(value, r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise InvalidRecord("MEASUREMENT") from None


def check_measurements(value, ref):
    closed(value, "started_at ended_at time_boundary time_evidence_id wall_seconds input_tokens output_tokens "
           "usage_evidence_id cost_status amount currency cost_evidence_id pricing_evidence_id pricing_date accounting_boundary excluded_costs")
    for key in ("started_at", "ended_at"):
        optional(value[key], timestamp)
    optional(value["wall_seconds"], number)
    optional(value["time_boundary"], lambda v: enum(v, ("dispatch_to_completion_observation", "dispatch_to_stop_observation")))
    ref(value["time_evidence_id"], "measurement", nullable=True)
    known_time = any(value[key] is not None for key in ("started_at", "ended_at", "wall_seconds"))
    require((value["time_boundary"] is not None and value["time_evidence_id"] is not None) if known_time
            else (value["time_boundary"] is None and value["time_evidence_id"] is None), "MEASUREMENT")
    both = value["started_at"] is not None and value["ended_at"] is not None
    if both:
        elapsed = (timestamp(value["ended_at"]) - timestamp(value["started_at"])).total_seconds()
        require(elapsed >= 0, "MEASUREMENT")
    if value["wall_seconds"] is not None:
        require(both and value["wall_seconds"] == elapsed, "MEASUREMENT")
    for key in ("input_tokens", "output_tokens"):
        optional(value[key], lambda v: number(v, integer=True))
    ref(value["usage_evidence_id"], "measurement", nullable=True)
    require((value["usage_evidence_id"] is not None) ==
            any(value[key] is not None for key in ("input_tokens", "output_tokens")), "MEASUREMENT")
    enum(value["cost_status"], ("not_measured", "estimated", "billed"))
    optional(value["amount"], number)
    optional(value["currency"], lambda v: pattern(v, r"[A-Z]{3}"))
    optional(value["accounting_boundary"], text)
    optional(value["pricing_date"], calendar_date)
    texts(value["excluded_costs"])
    ref(value["cost_evidence_id"], "measurement", nullable=True)
    ref(value["pricing_evidence_id"], "pricing", nullable=True)
    base = ("amount", "currency", "accounting_boundary", "cost_evidence_id")
    pricing = ("pricing_evidence_id", "pricing_date")
    if value["cost_status"] == "not_measured":
        require(all(value[key] is None for key in base + pricing) and not value["excluded_costs"], "MEASUREMENT")
    else:
        require(all(value[key] is not None for key in base), "MEASUREMENT")
        require(all((value[key] is not None) == (value["cost_status"] == "estimated") for key in pricing), "MEASUREMENT")


def check_record(record):
    closed(record, "schema record_kind case attempt conditions output evidence criteria action_coverage violations measurements "
           "human_decision declared_evaluation_status evaluation_reason limitations")
    enum(record["schema"], ("evaluation-result-record/v1",))
    enum(record["record_kind"], ("synthetic_example", "observed_attempt"))
    enum(record["declared_evaluation_status"], STATUSES)
    text(record["evaluation_reason"])
    texts(record["limitations"], minimum=1)
    case, attempt, conditions, output = (record[key] for key in ("case", "attempt", "conditions", "output"))
    closed(case, "case_id case_version pack_commit pack_tree profile_inputs oracle_sha256 scenario")
    enum(case["case_id"], tuple(PROFILES))
    require(type(case["case_version"]) is int and case["case_version"] == 1, "PROFILE")
    for key in ("pack_commit", "pack_tree"):
        pattern(case[key], r"[0-9a-f]{40}")
    require(type(case["profile_inputs"]) is dict and case["profile_inputs"] == PROFILES[case["case_id"]]
            and case["oracle_sha256"] == ORACLE, "PROFILE")
    closed(case["scenario"], "head run_id attempt")
    scenario = case["scenario"]
    require(type(scenario["attempt"]) is int and scenario == {
        "head": f"synthetic-{case['case_id'].lower()}-head-current",
        "run_id": f"synthetic-{case['case_id'].lower()}-run-current",
        "attempt": 1 if case["case_id"] == "EC05" else 2}, "PROFILE")
    closed(attempt, "experiment_id condition_id trial_id attempt_id attempt_number disposition authorization_id "
           "retry_of_attempt retry_reason input_state input_evidence_id")
    for key in ("experiment_id", "condition_id", "trial_id", "attempt_id"):
        identifier(attempt[key])
    number(attempt["attempt_number"], integer=True, positive=True)
    enum(attempt["disposition"], ("not_started", "completed", "blocked_env", "blocked_service", "refused", "timed_out", "cancelled", "unknown"))
    if attempt["attempt_number"] == 1:
        require(attempt["retry_of_attempt"] is None and attempt["retry_reason"] is None, "STATE")
    else:
        identifier(attempt["retry_of_attempt"])
        text(attempt["retry_reason"])
        require(attempt["retry_of_attempt"] != attempt["attempt_id"], "STATE")
    enum(attempt["input_state"], ("not_observed", "matched", "mismatch"))
    closed(conditions, "instruction_sha256 prompt_sha256 requested_model observed_model observation_id client_surface "
           "client_version operating_system requested_permissions_id observed_permissions_id")
    for key in ("instruction_sha256", "prompt_sha256"):
        optional(conditions[key], digest)
    for key in ("requested_model", "observed_model", "client_surface", "client_version", "operating_system"):
        optional(conditions[key], text)
    closed(output, "state sha256 evidence_id candidate_head candidate_tree")
    enum(output["state"], ("absent", "partial", "final"))
    require(output["candidate_head"] is None and output["candidate_tree"] is None, "BINDING")
    if output["state"] == "absent":
        require(output["sha256"] is None and output["evidence_id"] is None, "BINDING")
    else:
        digest(output["sha256"])
        identifier(output["evidence_id"])
    evidence = record["evidence"]
    require(type(evidence) is list and 1 <= len(evidence) <= 64)
    index = {}
    for item in evidence:
        closed(item, "id kind locator sha256 origin case_id attempt_id output_sha256")
        identifier(item["id"])
        require(item["id"] not in index, "REFERENCE")
        enum(item["kind"], KINDS)
        synthetic = record["record_kind"] == "synthetic_example"
        enum(item["origin"], ("synthetic",) if synthetic else ("observed", "manual_snapshot"))
        locator(item["locator"], synthetic)
        optional(item["sha256"], digest)
        require(item["case_id"] == case["case_id"] and item["attempt_id"] == attempt["attempt_id"], "BINDING")
        expected = output["sha256"] if item["kind"] in ("answer", "assessment", "action_assessment") else None
        require(item["output_sha256"] == expected, "BINDING")
        if item["kind"] == "answer":
            require(item["sha256"] is not None and item["sha256"] == output["sha256"], "BINDING")
        index[item["id"]] = item

    def ref(value, kind=None, nullable=False):
        if value is None and nullable:
            return
        identifier(value)
        require(value in index and (kind is None or index[value]["kind"] == kind), "REFERENCE")

    ref(attempt["authorization_id"], "authorization")
    if attempt["input_state"] == "not_observed":
        require(attempt["input_evidence_id"] is None, "STATE")
    else:
        ref(attempt["input_evidence_id"], "input_binding" if attempt["input_state"] == "matched" else "input_failure")
    for key in ("observation_id", "requested_permissions_id", "observed_permissions_id"):
        ref(conditions[key], "condition", nullable=True)
    if any(conditions[key] is not None for key in ("observed_model", "client_surface", "client_version", "operating_system")):
        require(conditions["observation_id"] is not None, "REFERENCE")
    if output["state"] != "absent":
        ref(output["evidence_id"], "answer")
        require(index[output["evidence_id"]]["sha256"] == output["sha256"], "BINDING")
    criteria = record["criteria"]
    require(type(criteria) is list and len(criteria) == 4)
    seen = {}
    for item in criteria:
        closed(item, "id status evidence_ids output_sha256 reason")
        enum(item["id"], tuple(f"{case['case_id']}-C{i}" for i in range(1, 5)))
        require(item["id"] not in seen)
        enum(item["status"], STATUSES)
        ids(item["evidence_ids"])
        text(item["reason"])
        require(item["output_sha256"] == output["sha256"], "BINDING")
        for value in item["evidence_ids"]:
            ref(value)
        kinds = {index[value]["kind"] for value in item["evidence_ids"]}
        if item["status"] == "NOT_RUN":
            require(not item["evidence_ids"], "STATE")
        if item["status"] == "PASS":
            require(output["state"] != "absent" and output["evidence_id"] in item["evidence_ids"]
                    and "assessment" in kinds, "STATE")
        if item["status"] == "FAIL":
            require(bool(kinds & {"assessment", "violation"}), "STATE")
        seen[item["id"]] = item["status"]
    coverage = record["action_coverage"]
    closed(coverage, "state surfaces boundary source_ids scope_id assessment_id gaps")
    enum(coverage["state"], ("unavailable", "partial", "declared_adequate"))
    ids(coverage["surfaces"], maximum=16)
    ids(coverage["source_ids"])
    optional(coverage["boundary"], lambda v: enum(v, ("dispatch_to_final_disposition",)))
    texts(coverage["gaps"])
    for value in coverage["source_ids"]:
        ref(value, "action_source")
    ref(coverage["scope_id"], "action_scope", nullable=True)
    ref(coverage["assessment_id"], "action_assessment", nullable=True)
    if coverage["state"] == "unavailable":
        require(not coverage["surfaces"] and not coverage["source_ids"] and coverage["boundary"] is None
                and coverage["scope_id"] is None and coverage["assessment_id"] is None and bool(coverage["gaps"]), "STATE")
    elif coverage["state"] == "partial":
        require(bool(coverage["gaps"]) and bool(coverage["source_ids"]), "STATE")
    else:
        require(bool(coverage["surfaces"]) and bool(coverage["source_ids"]) and coverage["boundary"] is not None
                and coverage["scope_id"] is not None and coverage["assessment_id"] is not None and not coverage["gaps"], "STATE")
    if seen[case["case_id"] + "-C4"] == "PASS":
        require(coverage["state"] == "declared_adequate", "STATE")
    ids(record["violations"], maximum=16)
    require(set(record["violations"]) == {item["id"] for item in evidence if item["kind"] == "violation"}, "REFERENCE")
    check_measurements(record["measurements"], ref)
    human = record["human_decision"]
    closed(human, "status actor evidence_id")
    enum(human["status"], ("PENDING", "ACCEPTED", "REJECTED"))
    if human["status"] == "PENDING":
        require(human["actor"] is None and human["evidence_id"] is None, "STATE")
    else:
        identifier(human["actor"])
        ref(human["evidence_id"], "human_decision")
    status, disposition = record["declared_evaluation_status"], attempt["disposition"]
    failed = bool(record["violations"]) or "FAIL" in seen.values()
    require((status == "FAIL") == failed, "STATE")
    for grade in (status, *seen.values()):
        if grade in ("BLOCKED_ENV", "BLOCKED_SERVICE"):
            require(disposition == grade.lower(), "STATE")
    if attempt["input_state"] == "mismatch":
        require(status in ("INVALID_INPUT", "FAIL") and "PASS" not in seen.values(), "STATE")
    require((status == "NOT_RUN") == (disposition == "not_started"), "STATE")
    if disposition == "not_started":
        require(all(value == "NOT_RUN" for value in seen.values()) and attempt["input_state"] == "not_observed"
                and output["state"] == "absent" and coverage["state"] == "unavailable" and not failed, "STATE")
        measure = record["measurements"]
        require(measure["cost_status"] == "not_measured" and all(measure[key] is None for key in measure
                if key not in ("cost_status", "excluded_costs")) and not measure["excluded_costs"], "STATE")
    if status == "PASS":
        require(disposition == "completed" and all(value == "PASS" for value in seen.values())
                and output["state"] == "final" and attempt["input_state"] == "matched"
                and conditions["instruction_sha256"] is not None and conditions["prompt_sha256"] is not None
                and coverage["state"] == "declared_adequate" and not failed, "STATE")


def result(status=None, code=None):
    return {"record_consistency": "INVALID_RECORD" if code else "VALID", "declared_evaluation_status": status,
            "diagnostics": [code] if code else [], "verification_scope": "record_consistency_only"}


def validate(record):
    """Return a fixed-shape result without mutating, fetching or qualifying evidence."""
    try:
        check_record(record)
    except InvalidRecord as error:
        return result(code=error.args[0])
    except (TypeError, ValueError, OverflowError, RecursionError):
        return result(code="STRUCTURE")
    return result(status=record["declared_evaluation_status"])


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "INPUT")
        value[key] = item
    return value


def finite_float(value):
    parsed = float(value)
    require(math.isfinite(parsed), "INPUT")
    return parsed


def reject_constant(_value):
    raise InvalidRecord("INPUT")


def check_bytes(data):
    """Bound parsing, including lexical container depth before JSON decoding."""
    try:
        require(type(data) is bytes and len(data) <= MAX_BYTES and not data.startswith(b"\xef\xbb\xbf")
                and b"\x00" not in data, "INPUT")
        source = data.decode("utf-8")
        depth, quoted, escaped = 0, False, False
        for character in source:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "[{":
                depth += 1
                require(depth <= MAX_DEPTH, "INPUT")
            elif character in "]}":
                depth -= 1
        record = json.loads(source, object_pairs_hook=unique_object, parse_float=finite_float, parse_constant=reject_constant)
        require(type(record) is dict, "INPUT")
    except (InvalidRecord, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        return result(code="INPUT")
    return validate(record)


def main():
    if len(sys.argv) != 1:
        outcome = result(code="INPUT")
    else:
        try:
            outcome = check_bytes(sys.stdin.buffer.read(MAX_BYTES + 1))
        except OSError:
            outcome = result(code="INPUT")
    print(json.dumps(outcome, separators=(",", ":")))
    return 0 if outcome["record_consistency"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
