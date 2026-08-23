#!/usr/bin/env python3
"""Validate the self-contained Phase 0 contract without network access."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


EXPECTED_PATHS = {
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "AGENTS.md",
    "docs/agreements/adr/ADR-0004-codex-port-baseline.md",
    "docs/known-limitations.md",
    "docs/planning/phase-0-orientation.md",
    "tests/conformance/manifest.json",
    ".github/scripts/check-phase0-contracts.py",
    "tests/conformance/test_phase0_contracts.py",
    ".github/scripts/check-action-pins.sh",
    ".github/scripts/check-workflow-permissions.sh",
    ".github/scripts/tests/lib.sh",
    ".github/scripts/tests/test-action-pins.sh",
    ".github/scripts/tests/test-workflow-permissions.sh",
    ".github/workflows/ci.yml",
}

EXPECTED_TARGET = {
    "repository": "mochan-tk/agentic-dev-kit-for-codex",
    "seed_commit": "88179ec6a28393d7bf4cea96684e3af16b512484",
    "seed_tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
}

EXPECTED_SOURCE = {
    "repository": "mochan-tk/agentic-dev-kit-for-copilot",
    "commit": "fd265ddef150fab86cd54d0e383c2c25fe297ffb",
    "tree": "88f96493ec167602750c8dfec044629bd494a586",
    "tracked_files": 135,
    "guard_test_files": 23,
}

EXPECTED_PACK = {
    "zip_sha256": "55e3e36d581c40a30f4e09e208573fcc15b46a254077da4f177fe7b8adcad0f7",
    "conformance_catalog_sha256": "21d12a287f536188355e75a9d563d4da329eb934f3ce7836db48b62bfd10faa0",
    "supplied_files_verified": 7,
}

EXPECTED_INVARIANT_DIGEST = (
    "ca7732a7f4d928f10fdb826b1a55e3c9ecf93008c5d2b210a35139956da8393c"
)
EXPECTED_INVARIANT_IDS = [f"I{number:02d}" for number in range(1, 14)]
EXPECTED_CONTRACT_IDS = [f"K{number:02d}" for number in range(1, 21)]
EXPECTED_FAMILIES = {
    "A": 6,
    "C": 5,
    "D": 4,
    "E": 10,
    "G": 13,
    "H": 10,
    "I": 15,
    "O": 7,
    "P": 12,
    "R": 10,
    "S": 8,
    "T": 16,
    "W": 12,
    "X": 8,
}

REQUIRED_LIMITATION_PHRASES = (
    "not a parity release",
    "authenticated identity",
    "receipts are not authority",
    "hooks are defense in depth",
    "hosted tools",
    "heartbeat",
    "pause/resume/cancel",
    "budget",
    "auto-merge",
    "sdk is deferred",
    "plugin-only distribution",
    "model-neutral",
    "cross-surface",
)

IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".codex-log"}
INVARIANT_ROW = re.compile(r"^\|\s*(I\d{2})\s*\|\s*(.*?)\s*\|\s*$")
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)(?:\s+#\s*(\S.*))?$")
FULL_ACTION_REF = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
MODEL_SLUG = re.compile(r"\bgpt-[a-z0-9.-]+", re.IGNORECASE)


def discover_paths(root: Path) -> set[str]:
    """Return repository files while excluding known local-only artifacts."""

    paths: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if not path.is_file() or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.name in {".DS_Store", "Thumbs.db"}:
            continue
        paths.add(relative.as_posix())
    return paths


def read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not valid UTF-8 JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object")
        return {}
    return payload


def nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def expect_fields(
    payload: dict[str, Any], expected: dict[str, Any], prefix: str, errors: list[str]
) -> None:
    for key, expected_value in expected.items():
        actual = payload.get(key)
        if actual != expected_value:
            errors.append(
                f"{prefix}.{key} must be {expected_value!r}, found {actual!r}"
            )


def parse_invariants(path: Path, errors: list[str]) -> list[tuple[str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read AGENTS.md invariants: {exc}")
        return []

    invariants: list[tuple[str, str]] = []
    for line in lines:
        match = INVARIANT_ROW.match(line)
        if match:
            invariants.append((match.group(1), match.group(2)))
    return invariants


def invariant_digest(invariants: Iterable[tuple[str, str]]) -> str:
    canonical = "".join(
        f"{identifier}\t{statement}\n"
        for identifier, statement in sorted(invariants, key=lambda item: item[0])
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_invariants(root: Path, manifest: dict[str, Any], errors: list[str]) -> None:
    invariants = parse_invariants(root / "AGENTS.md", errors)
    identifiers = [identifier for identifier, _ in invariants]
    duplicate_ids = sorted(
        identifier for identifier in set(identifiers) if identifiers.count(identifier) > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate invariant ID(s): {', '.join(duplicate_ids)}")
    if sorted(identifiers) != EXPECTED_INVARIANT_IDS:
        errors.append(
            "AGENTS.md invariant IDs must be exactly "
            + ", ".join(EXPECTED_INVARIANT_IDS)
        )

    digest = invariant_digest(invariants)
    if digest != EXPECTED_INVARIANT_DIGEST:
        errors.append(
            f"invariant digest must be {EXPECTED_INVARIANT_DIGEST}, found {digest}"
        )

    invariant_manifest = manifest.get("invariants")
    if not isinstance(invariant_manifest, dict):
        errors.append("manifest invariants must be an object")
        return
    if invariant_manifest.get("algorithm") != "sha256":
        errors.append("invariants.algorithm must be 'sha256'")
    if invariant_manifest.get("count") != len(EXPECTED_INVARIANT_IDS):
        errors.append("invariants.count must be 13")
    if invariant_manifest.get("digest") != digest:
        errors.append("manifest invariant digest does not match AGENTS.md")


def validate_catalog(manifest: dict[str, Any], errors: list[str]) -> None:
    catalog = manifest.get("scenario_catalog")
    if not isinstance(catalog, dict):
        errors.append("scenario_catalog must be an object")
        return
    total = catalog.get("total")
    if total != 136:
        errors.append(f"scenario_catalog.total must be 136, found {total!r}")
    families = catalog.get("families")
    if families != EXPECTED_FAMILIES:
        errors.append("scenario_catalog.families do not match the frozen 136-scenario catalog")
    if isinstance(families, dict) and all(
        isinstance(value, int) and not isinstance(value, bool) for value in families.values()
    ):
        if sum(families.values()) != 136:
            errors.append("scenario family counts must sum to 136")


def validate_contracts(manifest: dict[str, Any], errors: list[str]) -> None:
    contracts = manifest.get("contracts")
    if not isinstance(contracts, list):
        errors.append("contracts must be a list")
        return
    identifiers = [item.get("id") for item in contracts if isinstance(item, dict)]
    duplicates = sorted(
        str(identifier)
        for identifier in set(identifiers)
        if identifiers.count(identifier) > 1
    )
    if duplicates:
        errors.append(f"duplicate contract ID(s): {', '.join(duplicates)}")
    if sorted(identifier for identifier in identifiers if isinstance(identifier, str)) != EXPECTED_CONTRACT_IDS:
        errors.append("contract IDs must be exactly K01 through K20")
    for item in contracts:
        if not isinstance(item, dict):
            errors.append("every contract must be an object")
            continue
        if not item.get("contract") or not item.get("phase0_state"):
            errors.append(f"contract {item.get('id')!r} needs contract and phase0_state")


def validate_results(manifest: dict[str, Any], errors: list[str]) -> None:
    results = manifest.get("results")
    if not isinstance(results, list):
        errors.append("results must be a list")
        return
    allowed = {"pass", "fail", "skipped", "unverified", "approved-deviation"}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            errors.append(f"results[{index}] must be an object")
            continue
        status = result.get("status")
        if status not in allowed:
            errors.append(f"results[{index}].status is invalid")
        if status == "pass" and not result.get("target_evidence"):
            errors.append(f"results[{index}] pass requires non-empty target_evidence")
    if results:
        errors.append("Phase 0 results must remain empty; release evidence belongs to later phases")


def validate_docs(root: Path, errors: list[str]) -> None:
    try:
        readme = (root / "README.md").read_text(encoding="utf-8").lower()
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read README.md: {exc}")
        readme = ""
    for phrase in ("phase 0", "not installable", "not a parity release"):
        if phrase not in readme:
            errors.append(f"README.md must state {phrase!r}")

    try:
        limitations = (root / "docs/known-limitations.md").read_text(
            encoding="utf-8"
        ).lower()
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read known limitations: {exc}")
        limitations = ""
    for phrase in REQUIRED_LIMITATION_PHRASES:
        if phrase not in limitations:
            errors.append(f"known limitations must include {phrase!r}")


def validate_text_surfaces(root: Path, paths: set[str], errors: list[str]) -> None:
    floating_dependency_surfaces = {
        "README.md",
        "AGENTS.md",
        ".github/workflows/ci.yml",
    }
    for relative in sorted(paths & floating_dependency_surfaces):
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read text surface {relative}: {exc}")
            continue
        if "@latest" in text:
            errors.append(f"{relative} contains forbidden floating dependency '@latest'")

    normative = (
        "AGENTS.md",
        "tests/conformance/manifest.json",
        "docs/agreements/adr/ADR-0004-codex-port-baseline.md",
    )
    for relative in normative:
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        match = MODEL_SLUG.search(text)
        if match:
            errors.append(f"{relative} hardcodes model slug {match.group(0)!r}")


def workflow_job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        jobs_index = lines.index("jobs:")
    except ValueError:
        return {}
    starts: list[tuple[int, str]] = []
    for index in range(jobs_index + 1, len(lines)):
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", lines[index])
        if match:
            starts.append((index, match.group(1)))
    blocks: dict[str, str] = {}
    for position, (start, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        blocks[name] = "\n".join(lines[start:end])
    return blocks


def validate_workflow(root: Path, errors: list[str]) -> None:
    path = root / ".github/workflows/ci.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read Phase 0 workflow: {exc}")
        return

    blocks = workflow_job_blocks(text)
    if set(blocks) != {"quality", "conformance"}:
        errors.append("Phase 0 workflow jobs must be exactly quality and conformance")
    for name, block in blocks.items():
        if not re.search(r"(?m)^    permissions:\s*\n      contents: read\s*$", block):
            errors.append(f"workflow job {name!r} must grant exactly contents: read")
        checkout_count = block.count("actions/checkout@")
        if checkout_count != 1:
            errors.append(f"workflow job {name!r} must contain one checkout step")
        if block.count("persist-credentials: false") != checkout_count:
            errors.append(f"workflow job {name!r} must disable persisted checkout credentials")

    uses = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = ACTION_USE.match(line)
        if not match:
            continue
        uses += 1
        reference, comment = match.groups()
        if not FULL_ACTION_REF.fullmatch(reference):
            errors.append(
                f"ci.yml:{line_number} Action reference must use a full commit SHA"
            )
        if not comment or not re.match(r"v\d", comment):
            errors.append(
                f"ci.yml:{line_number} pinned Action needs a version comment"
            )
    if uses == 0:
        errors.append("Phase 0 workflow must contain pinned Action uses")


def validate_repository(root: Path, paths: set[str] | None = None) -> list[str]:
    root = root.resolve()
    observed_paths = discover_paths(root) if paths is None else set(paths)
    errors: list[str] = []

    for relative in sorted(EXPECTED_PATHS):
        if not (root / relative).is_file():
            errors.append(f"missing required Phase 0 path: {relative}")
    for relative in sorted(observed_paths - EXPECTED_PATHS):
        errors.append(f"unexpected Phase 0 path outside ownership allowlist: {relative}")

    manifest_path = root / "tests/conformance/manifest.json"
    manifest = read_json(manifest_path, errors, "conformance manifest")
    if manifest.get("schema") != "phase-0-conformance-manifest/v1":
        errors.append("manifest schema must be phase-0-conformance-manifest/v1")

    target = manifest.get("target")
    if isinstance(target, dict):
        expect_fields(target, EXPECTED_TARGET, "target", errors)
    else:
        errors.append("target must be an object")

    source = manifest.get("source")
    if isinstance(source, dict):
        expect_fields(source, EXPECTED_SOURCE, "source", errors)
        if nested(source, "signature", "github_api") != "verified":
            errors.append("source.signature.github_api must be 'verified'")
        if nested(source, "signature", "local_gpg") != "unverified":
            errors.append("source.signature.local_gpg must remain 'unverified'")
    else:
        errors.append("source must be an object")

    pack = manifest.get("research_pack")
    if isinstance(pack, dict):
        expect_fields(pack, EXPECTED_PACK, "research_pack", errors)
    else:
        errors.append("research_pack must be an object")

    if manifest.get("release_blocked") is not True:
        errors.append("release_blocked must be true in Phase 0")

    validate_invariants(root, manifest, errors)
    validate_catalog(manifest, errors)
    validate_contracts(manifest, errors)
    validate_results(manifest, errors)
    validate_docs(root, errors)
    validate_text_surfaces(root, observed_paths, errors)
    validate_workflow(root, errors)
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        print(f"phase0-contracts: FAIL — {len(errors)} finding(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "phase0-contracts: OK — baseline, 13 invariants, 20 contracts, "
        "136-scenario catalog, limitations, ownership, and CI are consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
