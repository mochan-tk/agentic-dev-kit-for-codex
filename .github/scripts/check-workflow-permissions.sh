#!/usr/bin/env bash
# Compute fail-closed workflow/job effective permissions for a strict YAML subset.

set -euo pipefail

WORKFLOW_DIR="${1:-.github/workflows}"
python3 -I - "$WORKFLOW_DIR" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


SCOPES = {
    "actions",
    "artifact-metadata",
    "attestations",
    "checks",
    "code-quality",
    "contents",
    "deployments",
    "discussions",
    "id-token",
    "issues",
    "models",
    "packages",
    "pages",
    "pull-requests",
    "security-events",
    "statuses",
    "vulnerability-alerts",
}
VALUES = {"none", "read", "write"}
JOB_HEADER = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$")
ENTRY = re.compile(r"^([a-z][a-z0-9-]*):[ ]+(none|read|write)(?:[ ]+#.*)?$")
AMBIGUOUS_PERMISSION_HEADER = re.compile(
    r'''^\s*(?:"permissions"|'permissions'|permissions\s+):'''
)
QUOTED_MAPPING_KEY = re.compile(
    r'''^\s*(?:"(?:[^"\\]|\\.)*"|'[^']*')\s*:'''
)
MERGE_KEY = re.compile(r"^\s*<<\s*:")
YAML_TAG = re.compile(r"^\s*!")
YAML_ANCHOR_OR_ALIAS = re.compile(
    r"(?:^\s*|:\s+|-\s+)[&*][^\s,{}\[\]]+(?=\s|$)"
)
EXPLICIT_MAPPING_KEY = re.compile(r"^\s*(?:\?(?:\s|$)|:(?:\s|$))")


class ParseFailure(ValueError):
    pass


def permission_mapping(
    lines: list[str], header_index: int, header_indent: int, label: str
) -> tuple[dict[str, str], int]:
    header = lines[header_index]
    expected_header = " " * header_indent + "permissions:"
    if header == expected_header + " {}":
        return {}, header_index + 1
    if header != expected_header:
        raise ParseFailure(f"{label} permissions must use a literal block mapping or {{}}")
    mapping: dict[str, str] = {}
    child_indent = header_indent + 2
    index = header_index + 1
    saw_child = False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= header_indent:
            break
        if "\t" in line or indent != child_indent:
            raise ParseFailure(f"{label} permissions indentation is unsupported")
        content = line[child_indent:]
        match = ENTRY.fullmatch(content)
        if match is None:
            raise ParseFailure(f"{label} permissions entry is ambiguous or unsupported")
        scope, value = match.groups()
        if scope not in SCOPES:
            raise ParseFailure(f"{label} permissions scope {scope!r} is unsupported")
        if value not in VALUES:
            raise ParseFailure(f"{label} permissions value is unsupported")
        if scope in mapping:
            raise ParseFailure(f"{label} permissions contains duplicate scope {scope!r}")
        mapping[scope] = value
        saw_child = True
        index += 1
    if not saw_child:
        raise ParseFailure(f"{label} permissions block is empty or uncheckable")
    return mapping, index


def workflow_permission_header(lines: list[str]) -> int | None:
    indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("permissions:")
    ]
    if len(indexes) > 1:
        raise ParseFailure("workflow contains duplicate permissions mappings")
    if not indexes:
        return None
    index = indexes[0]
    if lines[index].lstrip() != lines[index]:
        raise ParseFailure("workflow permissions header indentation is unsupported")
    return index


def jobs(lines: list[str], jobs_index: int) -> list[tuple[str, int, int]]:
    starts: list[tuple[str, int]] = []
    index = jobs_index + 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if not line[0].isspace():
            break
        match = JOB_HEADER.fullmatch(line)
        if match:
            starts.append((match.group(1), index))
        elif len(line) - len(line.lstrip(" ")) <= 2:
            raise ParseFailure("jobs mapping is not canonical block-style YAML")
        index += 1
    if not starts:
        raise ParseFailure("no canonical block-style jobs could be classified")
    names = [name for name, _start in starts]
    if len(names) != len(set(names)):
        raise ParseFailure("jobs mapping contains a duplicate job ID")
    result: list[tuple[str, int, int]] = []
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else index
        result.append((name, start, end))
    return result


def job_permissions(
    lines: list[str], name: str, start: int, end: int
) -> dict[str, str] | None:
    indexes = []
    for index in range(start + 1, end):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 4 and stripped.startswith("permissions:"):
            indexes.append(index)
        elif indent < 4:
            raise ParseFailure(f"job {name!r} metadata indentation is unsupported")
    if len(indexes) > 1:
        raise ParseFailure(f"job {name!r} contains duplicate permissions mappings")
    if not indexes:
        return None
    mapping, _next = permission_mapping(
        lines, indexes[0], 4, f"job {name!r}"
    )
    return mapping


def declared_write(mapping: dict[str, str] | None) -> str | None:
    if mapping is None:
        return None
    return next((scope for scope, value in mapping.items() if value == "write"), None)


def inspect(path: Path) -> tuple[list[str], int]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: cannot read workflow as UTF-8: {exc}"], 0
    if "\r" in text or "\t" in text or "${{" in text:
        return [f"{path}: workflow contains ambiguous indentation or expression syntax"], 0
    lines = text.splitlines()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if QUOTED_MAPPING_KEY.match(line):
            return [f"{path}: quoted or escaped YAML mapping keys are unsupported"], 0
        if AMBIGUOUS_PERMISSION_HEADER.match(line):
            return [f"{path}: quoted or whitespace-shifted permissions key is unsupported"], 0
        if YAML_TAG.match(line):
            return [f"{path}: YAML tags are unsupported"], 0
        if YAML_ANCHOR_OR_ALIAS.search(line):
            return [f"{path}: YAML anchors and aliases are unsupported"], 0
        if EXPLICIT_MAPPING_KEY.match(line):
            return [f"{path}: explicit YAML mapping keys are unsupported"], 0
        if MERGE_KEY.match(line):
            return [f"{path}: YAML merge keys and aliases are unsupported"], 0
    jobs_indexes = [index for index, line in enumerate(lines) if line == "jobs:"]
    if len(jobs_indexes) != 1:
        return [f"{path}: workflow must contain one literal jobs mapping"], 0
    jobs_index = jobs_indexes[0]
    findings: list[str] = []
    evidence: list[str] = []
    checked = 0
    try:
        workflow_header = workflow_permission_header(lines)
        workflow_permissions = (
            None
            if workflow_header is None
            else permission_mapping(lines, workflow_header, 0, "workflow")[0]
        )
        workflow_write = declared_write(workflow_permissions)
        if workflow_write is not None:
            findings.append(
                f"{path}: workflow declares forbidden {workflow_write}: write"
            )
        for name, start, end in jobs(lines, jobs_index):
            checked += 1
            job_mapping = job_permissions(lines, name, start, end)
            job_write = declared_write(job_mapping)
            if job_write is not None:
                findings.append(
                    f"{path}: job {name!r} declares forbidden {job_write}: write"
                )
            effective = job_mapping if job_mapping is not None else workflow_permissions
            if effective is None:
                findings.append(
                    f"{path}: job {name!r} effective permissions are UNKNOWN"
                )
            elif effective != {"contents": "read"}:
                rendered = ", ".join(
                    f"{scope}: {value}" for scope, value in sorted(effective.items())
                ) or "empty"
                findings.append(
                    f"{path}: job {name!r} effective permissions are not approved ({rendered})"
                )
            else:
                evidence.append(
                    f"{path}: job {name!r} effective permissions: contents: read"
                )
    except ParseFailure as exc:
        findings.append(f"{path}: {exc}")
    return findings + evidence, -checked if findings else checked


def main() -> int:
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"FAIL: workflow directory not found: {root}")
        return 2
    paths = sorted(root.glob("*.yml")) + sorted(root.glob("*.yaml"))
    if not paths:
        print(f"FAIL: no workflow files found under {root}")
        return 1
    findings: list[str] = []
    evidence: list[str] = []
    total = 0
    for path in paths:
        messages, count = inspect(path)
        if count < 0:
            findings.extend(messages)
            total += -count
        elif any(" effective permissions: contents: read" not in item for item in messages):
            findings.extend(messages)
            total += count
        else:
            evidence.extend(messages)
            total += count
    if findings:
        print("FAIL: workflow effective-permission policy rejected the repository")
        for finding in findings:
            print(f"- {finding}")
        return 1
    for item in evidence:
        print(item)
    print(
        f"check-workflow-permissions: OK — {total} job(s) checked; "
        "effective permissions are exactly contents: read"
    )
    return 0


raise SystemExit(main())
PY
