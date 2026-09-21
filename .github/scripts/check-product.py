#!/usr/bin/env python3
"""Offline product export, regression fixture, navigation and CI validation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

EXPORT = ".github/distribution/export-provenance.v1.json"
HISTORY = "tests/fixtures/history/manifest.json"
PAYLOAD = ".github/distribution/payload"
SOURCE = "mochan-tk/agentic-dev-kit-for-codex-pre"
SOURCE_COMMIT = "609362b327a4362b5f5eadcf5f8bdc8935948b98"
SOURCE_TREE = "bf38214c82484a5edb47d467a4be951f9c53bea6"
# Reviewed public records; an intentional product change updates these bindings.
EXPORT_SHA256 = "fc48db9474c8cd1a8320805a0c61afe60cd831f3291e3b984315925cf533d4b8"
HISTORY_SHA256 = "d1adafd9d9b91a8ac82648013cb3d720ef5fd85d79e156b4c808f66ddd9f7dd3"
# This single reviewed fixture adaptation has separate current-target evidence.
# The immutable export still describes its original bytes, not the adapted file.
CONNECTOR_FIXTURE_PATH = "tests/conformance/test_connector_validation.py"
CONNECTOR_FIXTURE_EXPORT = {
    "path": CONNECTOR_FIXTURE_PATH,
    "mode": "100644",
    "source_blob": "6b1cd8446b382c37157903fbdb0ffbd2556443db",
    "sha256": "3e03f1436d33fec448b23b3cc51b1a354c7f91cbdc3b5bf9f9a4f99c34ddd778",
}
CONNECTOR_FIXTURE_ADAPTATION = {
    "path": CONNECTOR_FIXTURE_PATH,
    "export_source_repository": SOURCE,
    "export_source_commit": SOURCE_COMMIT,
    "export_source_blob": CONNECTOR_FIXTURE_EXPORT["source_blob"],
    "export_sha256": CONNECTOR_FIXTURE_EXPORT["sha256"],
    "export_mode": "100644",
    "target_blob": "ec57d143f873ffc57c30a452bd461524c11a70a2",
    "target_sha256": "a00b4bd8322acd863d6cb59407c4c20ede6fc1a073a49604220d40dd3bc5d6be",
    "target_mode": "100644",
    "scope": "copy-required-update-and-workflow-inputs-and-assert-complete-fixture",
}
TEST_MODULES = (
    "test_adopter_ci.py", "test_ci_toolchain.py", "test_companion_access.py", "test_connector_validation.py", "test_installer.py",
    "test_installer_bootstrap.py", "test_installer_feedback.py", "test_installer_update.py", "test_product.py",
    "test_source_first_governance.py", "test_source_first_procedures.py", "test_workflow_parity.py",
)
# Exact current adaptations; the original export seal is never rewritten.
WORKFLOW_EXPORT_DIGESTS = {
    ".github/distribution/payload.v1.tsv": "b6d3f58d34272fade2c3bb4919e0b2c3ca4447921780b93a0df549ef3912b0fb",
    ".github/distribution/payload/.agents/skills/plan-management/SKILL.md": "dca2c5bc0f8bdb0910fa9ea48b55fb0a81da8be4bdceca96b1904bac16d572f1",
    ".github/distribution/payload/.agents/skills/project-onboarding/SKILL.md": "0471efc8e37df4c9e63f6a4600018ada490fc183bec06dfcb959f5931d06606e",
    ".github/distribution/payload/.agents/skills/session-orchestration/SKILL.md": "8c458972ea49e94d4d167d6505ff5ce3c90a294ad761e068576c4db787b6cb7b",
    ".github/distribution/payload/.github/codex-instructions.md": "8618593cbad6bc2b17c7b0385efb6f2a6c60aa5ac8879e07031b8c523a464cd2",
    ".github/distribution/payload/.github/scripts/check-task-ritual.sh": "8c4fe064337534106f9636de5bdf4379a05a6ed0a9a5a08eb84dcffced6076f2",
    ".github/distribution/payload/.github/scripts/setup-ruleset.sh": "84ecc688a1c84d398af7ce6a975a00770b2e1acc7d326828e0540b8d63ed5bba",
    ".github/scripts/governance-status.sh": "8bf40f09d11dd0e9552906f2cf2c50d847f8b53367114115b880ae1c592a2a0e",
    "tests/conformance/test_source_first_governance.py": "f61833188bad887719cef5585d103da2bbda08fef76db12f598c56efa992dece",
}
PUBLIC_DOCS = (
    "README.md", "AGENTS.md", "CONTRIBUTING.md", "docs/product-scope.md",
    "docs/provenance.md", "docs/known-limitations.md",
    "docs/distribution/source-first-installer.md", ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/distribution/companion-checks.md",
    "docs/distribution/adopter-ci.md",
)
ADOPTER_RECORD = ".github/distribution/adopter-ci.v1.json"
ADOPTER_RECORD_SHA256 = "6718773bd1395792ac16fe0e6fde627f024631a5c01f6a3318bb3ee6ef48b8f2"
ADOPTER_SOURCE_FILES = {
    ".github/workflows/task-ritual.yml": "76b2db3c69385e7ab20eee9f8847268b7a732389",
    ".github/workflows/ci.yml": "2147dd280f8f24f748487dfb83e2084c6167b899",
    ".github/scripts/check-retarget-freshness.sh": "91347e1f82f386273d27b75a4ff23d59952b2fb5",
    ".github/scripts/governance-drift.sh": "230e08e1ad7df5f66970866eef8dc262131b0555",
    ".github/scripts/governance-controls.tsv": "ea008c9f2b497dc656051761bca25b734b80b6e3",
    ".github/scripts/tests/test-ci-event-isolation.sh": "c896594532d98b57888901e038610fc75c5993da",
    ".github/scripts/tests/test-retarget-freshness.sh": "1f2aa1430055f6cabfae07343a99025bfbbe49c5",
    ".github/scripts/tests/test-governance-drift.sh": "08e2c281d8d2458cc4200bbf558f53bdd50e3ca5",
}
ADOPTER_TARGETS = tuple(sorted((
    ".github/distribution/adopter-ci/task-ritual.yml",
    ".github/distribution/adopter-ci/check-adopter-ci.py",
    ".github/scripts/setup-adopter-ci.py", "tests/conformance/test_adopter_ci.py",
    "tests/conformance/test_product.py", "docs/distribution/adopter-ci.md",
    "README.md", "docs/product-scope.md", "docs/known-limitations.md", "docs/provenance.md",
)))
COMPANION_GUIDE = "docs/distribution/companion-checks.md"
COMPANION_REVISION = "2213860cbb16bf80d80d1c388c31bc75ae12bb7e"
GOVERNANCE_COMPANION_REVISION = "48d5e6b87bbb609598178eaa385dc4ed9ea0a6d4"
# Bind only the three executable guide blocks. Prose may evolve without
# changing execution; intentional command changes need review and regressions.
COMPANION_BLOCKS = {
    "companion-governance": ("governance-status.sh", "52e63878f162a58046ed03b76cc036e4fee51daf2dc005de7c00d620ac66f06a"),
    "companion-worktree": ("worktree-preflight.sh", "9556150d60de556b4c32bcaa734a3a6e1c16995c2f5572fda2d1495903b067e7"),
    "companion-connectors": ("check-connectors.sh", "e6d770142bd142b0dd324d84271e10e91b28c6aaf567742a3bcde8cf2ddd32b5"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(root, relative):
    """Read bounded regular non-executable files without following symlinks.

    Ordinary read/write permission variation is valid for Git mode 100644.
    This is a local integrity check, not isolation from a malicious writer.
    """
    root = Path(root)
    pure = PurePosixPath(relative)
    if (not relative or pure.is_absolute() or str(pure) != relative
            or ".." in pure.parts or root.is_symlink()):
        raise ValueError("unsafe path")
    path = root
    for part in pure.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink")
    with path.open("rb") if stat.S_ISREG(path.lstat().st_mode) else _refuse() as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o7111
                or info.st_nlink != 1 or info.st_size > 1024 * 1024):
            raise ValueError("unsafe file")
        data = stream.read(1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if len(data) > 1024 * 1024 or identity(info) != identity(after) or identity(info) != identity(current):
        raise ValueError("file changed")
    return data


def _refuse():
    raise ValueError("not regular")


def unique_keys(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate key")
        record[key] = value
    return record


def bound_json(root, path, expected):
    data = read_bytes(root, path)
    if digest(data) != expected:
        raise ValueError("reviewed record changed")
    return json.loads(data, object_pairs_hook=unique_keys)


def history_bytes(root, *, commit=None, path=None, blob=None):
    """Exact immutable lookup; no Git object store or network fallback."""
    manifest = bound_json(root, HISTORY, HISTORY_SHA256)
    if (blob is None) == (commit is None or path is None):
        raise ValueError("specify commit/path or blob")
    matches = [row for row in manifest["entries"] if
               (row["source_blob"] == blob if blob else
                row["source_commit"] == commit and row["source_path"] == path)]
    if len(matches) != 1:
        raise ValueError("unbound historical file")
    row = matches[0]
    data = read_bytes(root, "tests/fixtures/history/blobs/" + row["sha256"])
    git_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if (digest(data) != row["sha256"] or git_blob != row["source_blob"]
            or row["source_repository"] != SOURCE or row["mode"] != "100644"):
        raise ValueError("historical bytes or provenance changed")
    return data


def validate_connector_fixture_adaptation(root, export_row):
    """Accept only the exact approved delta, independently of installer checks."""
    errors = []
    try:
        if export_row != CONNECTOR_FIXTURE_EXPORT:
            errors.append("connector fixture original export binding drifted")
        parity = json.loads(read_bytes(root, ".github/distribution/source-parity.v1.json"),
                            object_pairs_hook=unique_keys)
        if parity["explicit_update"]["fixture_adaptation"] != CONNECTOR_FIXTURE_ADAPTATION:
            errors.append("connector fixture current adaptation binding drifted")
        data = read_bytes(root, CONNECTOR_FIXTURE_PATH)
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if (digest(data) != CONNECTOR_FIXTURE_ADAPTATION["target_sha256"]
                or blob != CONNECTOR_FIXTURE_ADAPTATION["target_blob"]):
            errors.append("connector fixture differs from exact approved adaptation")
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        errors.append("connector fixture adaptation is missing, unsafe or unbound")
    return errors


def validate_export(root):
    errors = []
    try:
        record = bound_json(root, EXPORT, EXPORT_SHA256)
        if (record["source_repository"] != SOURCE or record["source_commit"] != SOURCE_COMMIT
                or record["source_tree"] != SOURCE_TREE or record["payload_count"] != 47):
            raise ValueError("source identity")
        parity = json.loads(read_bytes(root, ".github/distribution/source-parity.v1.json"), object_pairs_hook=unique_keys)
        adaptations = parity["workflow_parity"]["export_adaptations"]
        if [row["path"] for row in adaptations] != sorted(WORKFLOW_EXPORT_DIGESTS):
            raise ValueError("workflow adaptation inventory")
        for row in record["frozen_files"]:
            if row["path"] == CONNECTOR_FIXTURE_PATH:
                errors.extend(validate_connector_fixture_adaptation(root, row))
                continue
            data = read_bytes(root, row["path"])
            git_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if row["path"] in WORKFLOW_EXPORT_DIGESTS:
                adaptation = next(item for item in adaptations if item["path"] == row["path"])
                expected = {"path": row["path"], "export": row, "target_mode": "100644",
                            "target_sha256": digest(data), "target_blob": git_blob}
                if adaptation != expected or digest(data) != WORKFLOW_EXPORT_DIGESTS[row["path"]]:
                    errors.append("workflow exact approved export adaptation changed: " + row["path"])
                continue
            if digest(data) != row["sha256"] or git_blob != row["source_blob"] or row["mode"] != "100644":
                errors.append("approved export file changed: " + row["path"])
        actual = {str(p.relative_to(Path(root) / PAYLOAD)) for p in (Path(root) / PAYLOAD).rglob("*") if not p.is_dir() or p.is_symlink()}
        expected = {row["path"][len(PAYLOAD) + 1:] for row in record["frozen_files"] if row["path"].startswith(PAYLOAD + "/")}
        if len(expected) != 47 or actual != expected:
            errors.append("approved 47-file payload layout changed")
        manifest = bound_json(root, HISTORY, HISTORY_SHA256)
        if record["fixture_manifest_sha256"] != HISTORY_SHA256 or len(manifest["entries"]) != 20:
            raise ValueError("fixture inventory")
        expected_blobs = {row["sha256"] for row in manifest["entries"]}
        actual_blobs = {p.name for p in (Path(root) / "tests/fixtures/history/blobs").iterdir()}
        if actual_blobs != expected_blobs:
            errors.append("historical fixture inventory changed")
        for row in manifest["entries"]:
            history_bytes(root, commit=row["source_commit"], path=row["source_path"])
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        errors.append("product export or historical fixture is missing, unsafe or unbound")
    return errors


def validate_navigation(root):
    errors = []
    root = Path(root)
    try:
        docs = list(PUBLIC_DOCS) + [str(p.relative_to(root)) for p in (root / PAYLOAD).rglob("*.md")]
        for name in docs:
            text = read_bytes(root, name).decode()
            references = re.findall(r'\[[^\]]+\]\(([^)]+)\)|(?:href|src)="([^"]+)"', text)
            for markdown, html in references:
                target = (markdown or html).split("#", 1)[0]
                if not target or re.match(r"https?://|mailto:", target):
                    continue
                if target.startswith("/") or ":" in target:
                    errors.append("unsafe document link: " + name)
                    continue
                destination = (root / name).parent / target
                destination.resolve().relative_to(root.resolve())
                if not destination.exists() or destination.is_symlink():
                    errors.append("missing document link: " + name + " -> " + target)
        agents = read_bytes(root, "AGENTS.md").decode()
        if len(agents.splitlines()) > 60 or not all(t in agents for t in ("one active writer", "merge authority", "private paths")):
            errors.append("contributor authority/privacy boundary missing")
        readme = read_bytes(root, "README.md").decode()
        if not all(t in readme for t in ("native Windows", "docs/known-limitations.md", "docs/product-scope.md")):
            errors.append("README product limits missing")
        for name in PUBLIC_DOCS:
            text = read_bytes(root, name).decode()
            if re.search(r"agentic-dev-kit-for-codex/(?:issues|pull)/[0-9]+", text):
                errors.append("historical Issue/PR points to new repository: " + name)
        for name in (".github/ISSUE_TEMPLATE/ai-task.yml", ".github/ISSUE_TEMPLATE/epic.yml"):
            text = read_bytes(root, name).decode()
            if not all(token in text for token in ("name:", "description:", "body:", "required: true", "Acceptance")):
                errors.append("contributor Issue template incomplete")
        read_bytes(root, ".github/ISSUE_TEMPLATE/config.yml")
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        errors.append("public documentation or navigation is uncheckable")
    return errors


def validate_policy(root):
    errors = []
    root = Path(root)
    try:
        workflow = read_bytes(root, ".github/workflows/ci.yml").decode()
        required = ("permissions: {}", "  quality:", "  conformance:", "contents: read",
                    "persist-credentials: false", "fetch-depth: 1")
        commands = ("python3 -I .github/scripts/check-product.py",
                    "python3 -I .github/scripts/check-installer.py",
                    "bash .github/scripts/tests/test-scaffold-init.sh",
                    'python3 -I .github/scripts/install-ci-tools.py --lock .github/governance/ci-tools.lock.v1.json --destination "$RUNNER_TEMP/agentic-ci-tools" --check-repository',
                    "bash .github/scripts/check-action-pins.sh",
                    "bash .github/scripts/tests/test-action-pins.sh",
                    "bash .github/scripts/check-workflow-permissions.sh",
                    "bash .github/scripts/tests/test-workflow-permissions.sh",
                    "python3 -I -m compileall -q .github/scripts tests/conformance",
                    "$PSVersionTable.PSVersion.ToString()",
                    "python3 -I -m unittest discover -s tests/conformance -p 'test_*.py'")
        runs = re.findall(r"^        run: ([^\n]+)$", workflow, re.M)
        if (any(token not in workflow for token in required)
                or runs != list(commands)):
            errors.append("mandatory product CI edge missing")
        # Bind the native shell to the complete required step, not a token elsewhere.
        pwsh_step = ("      - name: Require real PowerShell test host\n"
                     "        shell: pwsh\n"
                     "        run: $PSVersionTable.PSVersion.ToString()\n")
        if pwsh_step not in re.split(r"(?=^      - )", workflow, flags=re.M):
            errors.append("mandatory native PowerShell CI step missing or changed")
        if re.search(r"check-phase|check-runtime|check-repository-policy|conformance-catalog|check-skills|check-ledger|check-portable|continue-on-error|if:", workflow):
            errors.append("unsupported or bypassed product CI edge")
        actual = {p.name for p in (root / "tests/conformance").glob("test_*.py")}
        if actual != set(TEST_MODULES):
            errors.append("mandatory product conformance modules changed")
        for name in TEST_MODULES:
            read_bytes(root, "tests/conformance/" + name)
        for forbidden in (".agents", ".codex", "docs/context", "docs/planning", "docs/agreements",
                          "tests/runtime", "tests/ledger", "tests/conformance/results.json",
                          ".github/scripts/codex-exec-adapter.py", ".github/governance/source-first-completion.v1.json"):
            if (root / forbidden).exists():
                errors.append("predecessor development surface present: " + forbidden)
        for name in PUBLIC_DOCS:
            data = read_bytes(root, name).decode()
            if re.search(r"/Users/|/home/[A-Za-z]|(?:gh[pousr]_|github_pat_)[A-Za-z0-9]{16,}", data):
                errors.append("public documentation contains private-path or credential pattern")
    except (OSError, ValueError, UnicodeError, TypeError):
        errors.append("product CI/policy is uncheckable")
    return errors


def validate_companion_access(root):
    """Bind published commands to separately reviewed immutable revisions."""
    errors = []
    try:
        guide = read_bytes(root, COMPANION_GUIDE).decode()
        matches = re.findall(r"<!-- BEGIN (companion-[a-z]+) -->\n```bash\n(.*?)\n```\n<!-- END \1 -->", guide, re.S)
        if (len(matches) != 3 or {name for name, _ in matches} != set(COMPANION_BLOCKS)
                or guide.count("<!-- BEGIN companion-") != 3
                or guide.count("<!-- END companion-") != 3):
            raise ValueError("missing or duplicated command")
        export = bound_json(root, EXPORT, EXPORT_SHA256)
        for name, block in matches:
            helper, command_digest = COMPANION_BLOCKS[name]
            path = ".github/scripts/" + helper
            rows = [row for row in export["frozen_files"] if row["path"] == path]
            if len(rows) != 1 or rows[0]["mode"] != "100644":
                raise ValueError("unbound helper")
            data = read_bytes(root, path)
            expected = WORKFLOW_EXPORT_DIGESTS[path] if name == "companion-governance" else rows[0]["sha256"]
            revision = GOVERNANCE_COMPANION_REVISION if name == "companion-governance" else COMPANION_REVISION
            if (digest(data) != expected
                    or digest(block.encode()) != command_digest
                    or not re.fullmatch(r"[0-9a-f]{40}", revision)
                    or "  revision=" + revision + "\n" not in block
                    or "  expected=" + expected + "\n" not in block
                    or 'https://raw.githubusercontent.com/mochan-tk/agentic-dev-kit-for-codex/$revision/' + path + '"' not in block):
                errors.append("fixed companion command or helper binding changed: " + name)
        if "docs/distribution/companion-checks.md" not in read_bytes(root, "README.md").decode():
            errors.append("README companion command navigation missing")
        read_bytes(root, "tests/conformance/test_companion_access.py")
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        errors.append("mandatory companion commands are missing, unsafe or unbound")
    return errors


def validate_adopter_ci(root):
    """Mandatory product-only addon gate; legacy installer fixtures stay closed."""
    errors = []
    try:
        record = bound_json(root, ADOPTER_RECORD, ADOPTER_RECORD_SHA256)
        if (set(record) != {"schema", "source_repository", "source_commit", "source_files",
                            "scope", "evidence", "target_files"}
                or record["schema"] != "adopter-ci-provenance/v1"
                or record["source_repository"] != "mochan-tk/agentic-dev-kit-for-copilot"
                or record["source_commit"] != "446071c76f14f5fbda37a0eef1b6eafa0a3ab897"
                or record["source_files"] != ADOPTER_SOURCE_FILES
                or record["scope"] != "separate-opt-in-addon-preserving-all-47-payload-files"
                or record["evidence"] != "actual-local-tools-synthetic-GitHub-not-live-adopter-rollout"
                or [row["path"] for row in record["target_files"]] != list(ADOPTER_TARGETS)):
            raise ValueError("addon source/scope binding")
        for row in record["target_files"]:
            data = read_bytes(root, row["path"])
            if row != {"path": row["path"], "mode": "100644", "sha256": digest(data)}:
                raise ValueError("addon current digest")
        sensor_path = ".github/distribution/adopter-ci/check-adopter-ci.py"
        spec = importlib.util.spec_from_file_location("adopter_product_check", Path(root) / sensor_path)
        sensor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sensor)
        if sensor.METADATA_SHA256 != digest(read_bytes(root, ".github/distribution/adopter-ci/task-ritual.yml")):
            raise ValueError("addon template binding")
        if sensor.RITUAL_SHA256 != WORKFLOW_EXPORT_DIGESTS[PAYLOAD + "/.github/scripts/check-task-ritual.sh"]:
            raise ValueError("addon installed ritual binding")
        supported = ("name: Application\non:\n  pull_request:\n"
                     "    types: [opened, synchronize, reopened]\npermissions:\n  contents: read\n"
                     "concurrency:\n  group: application-${{ github.event.pull_request.number }}\n"
                     "  cancel-in-progress: true\njobs:\n  quality:\n    runs-on: ubuntu-latest\n"
                     "    steps:\n      - run: python3 -m unittest discover\n")
        sensor.code_contract(supported.encode(), ["quality"])
        for before, after in (("  quality:\n", "  quality:\n    if: false\n"),
                              ("      - run:", "      - continue-on-error: true\n        run:"),
                              ("python3 -m unittest discover", "true"),
                              ("python3 -m unittest discover", "echo check"),
                              ("reopened]", "reopened, edited]"),
                              ("application-${{", "adopter-metadata-${{")):
            try:
                sensor.code_contract(supported.replace(before, after).encode(), ["quality"])
            except sensor.Fault:
                continue
            raise ValueError("addon mandatory negative guard missing")
        if "docs/distribution/adopter-ci.md" not in read_bytes(root, "README.md").decode():
            raise ValueError("addon navigation")
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError, ImportError):
        errors.append("mandatory adopter CI addon is missing, unsafe or unbound")
    return errors


def validate(root):
    root = Path(root)
    errors = (validate_export(root) + validate_navigation(root) + validate_policy(root)
              + validate_companion_access(root) + validate_adopter_ci(root))
    try:
        spec = importlib.util.spec_from_file_location("installer_product_check", root / ".github/scripts/check-installer.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        errors += (checker.validate(root) + checker.validate_connector_companion(root)
                   + checker.validate_governance_procedures(root) + checker.validate_bootstrap(root)
                   + checker.validate_explicit_update(root) + checker.validate_workflow_parity(root))
    except (OSError, ValueError, ImportError, AttributeError, TypeError):
        errors.append("mandatory installer validation unavailable")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = validate(args.root)
    for error in errors:
        print("ERROR: " + error)
    if errors:
        return 1
    print("Product integrity: 47 payload paths with bounded current adaptations; 20 immutable historical entries plus accepted workflow baseline; complete product checks and navigation. Offline evidence only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
