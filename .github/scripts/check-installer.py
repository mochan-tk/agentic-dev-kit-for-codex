#!/usr/bin/env python3
"""Validate the closed adopter payload; no installation or external service."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

SOURCE_COMMIT = "fd265ddef150fab86cd54d0e383c2c25fe297ffb"
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"
PARITY = ".github/distribution/source-parity.v1.json"
FEEDBACK_PATHS = (
    ".github/scripts/feedback-lib.sh",
    ".github/scripts/report-installer-failure.sh",
    "tests/conformance/test_installer_feedback.py",
)
FEEDBACK_SOURCES = {
    ".github/scripts/feedback-lib.sh": "b09747ae0bc8ffa2183fec48b578b97cdb45c67b",
    ".github/scripts/tests/test-feedback-lib.sh": "fce1632234b8e9f64ab374130cb39c667eafb7b5",
    ".github/scripts/scaffold-init.sh": "7236d06b901da97c2a1a37fd4a51f6fbd89a75d1",
    "docs/agreements/adr/ADR-0002-consent-gated-adopter-feedback.md": "65c4c20ee9fd2c91d0738a38fa8558be8761dc42",
    "docs/context/feedback-loop/privacy-posture.md": "d417b2c7114913aaea80b03014f3c5f7e5458fe8",
}
FEEDBACK_FIELDS = ["Script", "Failing line", "Exit code", "OS / arch", "bash version",
                   "gh version", "jq version", "Scaffold version"]
FEEDBACK_ADAPTATIONS = [
    "Reuse source bounded fields, TTY/CI gates, preview-before-consent and one create attempt; standalone opt-in replaces automatic ERR/EXIT integration.",
    "Fixed public github.com recipient replaces adopter changelog routing; Scaffold version is unknown and caller failure metadata is user-reported, not historical proof.",
    "Draft requires no gh/account; no auth, labels, retry or receiving workflow. Failed/lost/invalid create response is submission-unconfirmed, never confirmed absence.",
    "Narrow version/system grammars and bounded tool-output capture reject unsafe observations; actual Bash/fake-gh/PTY tests replace the source TTY override seam.",
    "Literal terminal consent and tool-output limits preserve byte distinctions before Bash string normalization.",
]
INSTALLER_LIMITS = [
    "Local-source explicit install/known-old upgrade and operation-scoped rollback; no auto download/init/stage/commit/force.",
    "Source class dispatch and two-version preservation tests are reused; old-byte/mode checks, prewrite backups and explicit rollback are Codex-target safety adaptations, not source-provided transactions.",
    "Rollback preserves unrelated edits and refuses changed affected files; exclusive-writer local fixtures do not prove power-loss atomicity or malicious same-user race resistance.",
    "No live Codex, Windows or GitHub-helper execution proof; no VM prerequisite.",
    "Development-only AGENTS/PIN/Task IDs/governance/results are excluded.",
]
EXPECTED = {
    ".agents/skills/context-collection/SKILL.md": [
        ".github/skills/context-collection/SKILL.md",
        "cead6452f8a7015ef2070596bde26da3e2ae2cfd"
    ],
    ".agents/skills/context-distillation/SKILL.md": [
        ".github/skills/context-distillation/SKILL.md",
        "4f2e57a7f613cdadb7c7d76306c3a04458ca7b08"
    ],
    ".agents/skills/plan-management/SKILL.md": [
        ".github/skills/plan-management/SKILL.md",
        "4c76ec1a95516358b038f915668e01eac7f126e5"
    ],
    ".agents/skills/plan-management/scripts/frontier.sh": [
        ".github/skills/plan-management/scripts/frontier.sh",
        "af0905cb90626001c50c2937d35ba7ea5f9d077c"
    ],
    ".agents/skills/plan-management/scripts/new-task.sh": [
        ".github/skills/plan-management/scripts/new-task.sh",
        "1156b004fd554b12cdccf55bc5b62a98e3a82bda"
    ],
    ".agents/skills/plan-management/templates/epic-body.md": [
        ".github/skills/plan-management/templates/epic-body.md",
        "b01a35256b48f1c1e1c31c4d1e35822767bd5551"
    ],
    ".agents/skills/plan-management/templates/task-body.md": [
        ".github/skills/plan-management/templates/task-body.md",
        "2338d2e79db0afad54e498d5582b80ad63fa198f"
    ],
    ".agents/skills/project-onboarding/SKILL.md": [
        ".github/skills/project-onboarding/SKILL.md",
        "20643ee9c8f5c3e0221db41e05b0abe3e1b22943"
    ],
    ".agents/skills/retro/SKILL.md": [
        ".github/skills/retro/SKILL.md",
        "e0f059e8b98d9692c4ae47d45c9da49a9ab711f3"
    ],
    ".agents/skills/session-orchestration/SKILL.md": [
        ".github/skills/session-orchestration/SKILL.md",
        "d50002b5a95fef18fb651cd4fe31b459593bedb0"
    ],
    ".agents/skills/task-routing/SKILL.md": [
        ".github/skills/task-routing/SKILL.md",
        "30a6b0123f82b15f6379a4b1e62f5c6d30c7e984"
    ],
    ".agents/skills/verification/SKILL.md": [
        ".github/skills/verification/SKILL.md",
        "6d0916437bf490116cefaf71e234a6f1aa3eaf6a"
    ],
    ".codex/agents/orchestrator.toml": [
        ".github/agents/orchestrator.agent.md",
        "5574a1422f53651330a204dce08dce49ea4c1f59"
    ],
    ".codex/agents/planner.toml": [
        ".github/agents/planner.agent.md",
        "7227835f359f3383cd2ddbc47ffb69e5e1ce867e"
    ],
    ".codex/agents/reviewer.toml": [
        ".github/agents/reviewer.agent.md",
        "36901b4a8835ebe8f0989994bf3847bcd2809beb"
    ],
    ".gitattributes": [
        ".gitattributes",
        "beda7eb8fb0d073281b23f758094da7348e92ee8"
    ],
    ".github/ISSUE_TEMPLATE/ai-task.yml": [
        ".github/ISSUE_TEMPLATE/ai-task.yml",
        "f8d70b3d44f53de307d88284f192da79cdf45fdd"
    ],
    ".github/ISSUE_TEMPLATE/config.yml": [
        ".github/ISSUE_TEMPLATE/config.yml",
        "a3649e71ac42fee71010da2292893c900536e650"
    ],
    ".github/ISSUE_TEMPLATE/epic.yml": [
        ".github/ISSUE_TEMPLATE/epic.yml",
        "2fd09aceddf192a2d2c1816dcdc2a25873340da4"
    ],
    ".github/PULL_REQUEST_TEMPLATE.md": [
        ".github/PULL_REQUEST_TEMPLATE.md",
        "145a05bbc0050c215b397e7d7c029507c7f065fa"
    ],
    ".github/codex-instructions.md": [
        ".github/copilot-instructions.md",
        "c2ec9fb4c156b5139b7d88624593216c69a800f0"
    ],
    ".github/connectors/CONNECTOR-TEMPLATE.md": [
        ".github/connectors/CONNECTOR-TEMPLATE.md",
        "997e2dc5825d2cabeafbbbe01ab997ae86b958d4"
    ],
    ".github/connectors/README.md": [
        ".github/connectors/README.md",
        "386639f24f8323ce92bed53c5ea6518bc50c2dc5"
    ],
    ".github/connectors/builtin.md": [
        ".github/connectors/builtin.md",
        "3bf19026be22f7d167f9c26d82410c4b9b9ca022"
    ],
    ".github/connectors/speckit.md": [
        ".github/connectors/speckit.md",
        "441b1c8e639813a49dcc200ae4c1c2b018f91a5a"
    ],
    ".github/docs/agreements/README.md": [
        ".github/docs/agreements/README.md",
        "413054a2fb8f80406c62491fdb558efa302c43f0"
    ],
    ".github/docs/agreements/adr/ADR-0000-template.md": [
        ".github/docs/agreements/adr/ADR-0000-template.md",
        "269f127a929cf24e2f9979c189a725b2683bb80d"
    ],
    ".github/docs/agreements/glossary.md": [
        ".github/docs/agreements/glossary.md",
        "cc5336086dd24145067be37c4282288cd2fa8709"
    ],
    ".github/docs/agreements/non-goals.md": [
        ".github/docs/agreements/non-goals.md",
        "abd4ca28ba184f6aa5173b383afab873038577f0"
    ],
    ".github/docs/agreements/requirements.md": [
        ".github/docs/agreements/requirements.md",
        "f68e5804e54c7e71ce65775794685bab70270676"
    ],
    ".github/docs/agreements/retro-log.md": [
        ".github/docs/agreements/retro-log.md",
        "f401f268702fd21efeb8db85e7b380ef69f3de5d"
    ],
    ".github/docs/context/README.md": [
        ".github/docs/context/README.md",
        "3b915dda3cd9968757c90d8d3a03f11e6378e0b6"
    ],
    ".github/instructions/code-review.instructions.md": [
        ".github/instructions/code-review.instructions.md",
        "1336728a7d8f72520bec2b97a2ed25568e17d0b3"
    ],
    ".github/instructions/docs.instructions.md": [
        ".github/instructions/docs.instructions.md",
        "68ff889b87df96282cdb014f1ee88a1922dfc072"
    ],
    ".github/scripts/check-task-ritual.sh": [
        ".github/scripts/check-task-ritual.sh",
        "9365796d80e80e6ee1a94bc6e0cb08686682852c"
    ],
    ".github/scripts/ownership-overlap.sh": [
        ".github/scripts/ownership-overlap.sh",
        "7ed866ebd4baaf5d73f2a3ebcb1dedb35638a52a"
    ],
    ".github/scripts/run.ps1": [
        ".github/scripts/run.ps1",
        "269b798e1d163b0832a3036114c9550684a1aa76"
    ],
    ".github/scripts/setup-labels.sh": [
        ".github/scripts/setup-labels.sh",
        "f76b67dcbe9563cfb61bd56451f7c51a68f8afca"
    ],
    ".github/scripts/setup-project.sh": [
        ".github/scripts/setup-project.sh",
        "4dd5b61186b8488e5e8fff143e5b40d3958087ca"
    ],
    ".github/scripts/setup-ruleset.sh": [
        ".github/scripts/setup-ruleset.sh",
        "c36e2cf098cab29851d5da2eb0f340b0dd5f1940"
    ],
    ".github/scripts/setup-sources.sh": [
        ".github/scripts/setup-sources.sh",
        "e60fe75c1fd47f5ca7ccfb8ae80f395162f196ff"
    ],
    ".github/scripts/tuning-status.sh": [
        ".github/scripts/tuning-status.sh",
        "1b764f3bd67e897e64c11c98503e5750d73746dd"
    ],
    ".gitignore": [
        ".gitignore",
        "8b8c60b83d8d879d40b0c803931a1d68d76ab742"
    ],
    "AGENTS.md": [
        "AGENTS.md",
        "d575018d2d456c9376144495467cfcf8ac498b96"
    ],
    "README.md": [
        "README.md",
        "76480f3ae0458926d854e62f51d10958ff229bd3"
    ],
    "SCAFFOLD-CHANGELOG.md": [
        "SCAFFOLD-CHANGELOG.md",
        "c0898a331200d0a332c5c4423fefc9017531a95f"
    ],
    "docs/agreements/adr/ADR-0003-two-tier-task-execution.md": [
        "docs/agreements/adr/ADR-0003-two-tier-task-execution.md",
        "f07906ce7eea7dc45b04cbdd1b739557ec018df8"
    ]
}

def preservation_class(name):
    if name in {"README.md", ".gitignore", ".gitattributes"}:
        return "seed"
    if name == "SCAFFOLD-CHANGELOG.md" or name.startswith(".github/docs/"):
        return "instance"
    if name in {"AGENTS.md", ".github/codex-instructions.md"} or name.startswith(".github/instructions/"):
        return "tuned"
    return "engine"

def layout_bytes():
    return "".join(name + "\t" + preservation_class(name) + "\n" for name in sorted(EXPECTED)).encode()

def regular_bytes(root, name):
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symlink")
    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
        raise ValueError("not bounded regular file")
    with path.open("rb") as handle:
        data = handle.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("input too large")
    return data

def validate(root):
    errors = []
    root = Path(root)
    try:
        if root.is_symlink():
            raise ValueError("root symlink")
        inventory = regular_bytes(root, INVENTORY).decode()
        rows = [line.split("\t") for line in inventory.splitlines() if line and not line.startswith("#")]
        names = [row[0] for row in rows]
        if names != sorted(EXPECTED) or any(len(row) != 3 for row in rows):
            return ["installer inventory paths/order/columns differ from the exact reviewed set"]
        actual = {str(p.relative_to(root / PAYLOAD)) for p in (root / PAYLOAD).rglob("*") if not p.is_dir() or p.is_symlink()}
        if actual != set(EXPECTED):
            errors.append("installer payload has missing, extra or symlink entries")
        payload_data = {}
        for name, kind, digest in rows:
            if kind != preservation_class(name) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                errors.append("installer inventory class/digest is invalid: " + name)
            data = regular_bytes(root, PAYLOAD + "/" + name)
            payload_data[name] = data
            if hashlib.sha256(data).hexdigest() != digest:
                errors.append("installer payload digest drift: " + name)
            if stat.S_IMODE((root / PAYLOAD / name).stat().st_mode) & 0o111:
                errors.append("installer payload mode must be non-executable 100644: " + name)
        parity = json.loads(regular_bytes(root, PARITY))
        if set(parity) != {"schema", "source_repository", "source_commit", "files", "installer_source", "limits", "feedback_companion"}:
            errors.append("installer provenance fields drifted")
        if parity.get("schema") != "source-first-installer-parity/v1" or parity.get("source_repository") != "mochan-tk/agentic-dev-kit-for-copilot" or parity.get("source_commit") != SOURCE_COMMIT:
            errors.append("installer frozen source provenance drifted")
        if parity.get("limits") != INSTALLER_LIMITS:
            errors.append("installer known-old/operation-scoped preservation boundary drifted")
        if parity.get("installer_source") != {
            "scaffold-init.sh": "7236d06b901da97c2a1a37fd4a51f6fbd89a75d1",
            "scaffold-init.ps1": "6baa8ca94535d25c3b3b1cc1e4ac4ba95542321f",
            "test-scaffold-init.sh": "e060e59ef1fc4c8dabdae2de091ed8eabafba8a9",
        }:
            errors.append("installer source script/test provenance drifted")
        companion = parity.get("feedback_companion")
        expected = {
            "schema": "installer-feedback-companion/v1",
            "source_files": FEEDBACK_SOURCES,
            "fields": FEEDBACK_FIELDS,
            "recipient": "https://github.com/mochan-tk/agentic-dev-kit-for-codex",
            "integration": "standalone-opt-in-outside-payload",
            "adaptations": FEEDBACK_ADAPTATIONS,
            "evidence": "offline-real-bash-fake-gh-pty-only",
        }
        if not isinstance(companion, dict) or set(companion) != set(expected) | {"target_files"}:
            errors.append("feedback companion fields are missing or unreviewed")
        elif any(companion.get(key) != value for key, value in expected.items()):
            errors.append("feedback companion source/consent/privacy/evidence contract drifted")
        if isinstance(companion, dict):
            targets = companion.get("target_files")
            if not isinstance(targets, list) or [item.get("path") for item in targets] != list(FEEDBACK_PATHS):
                errors.append("feedback companion target inventory drifted")
            else:
                for item in targets:
                    name = item["path"]
                    data = regular_bytes(root, name)
                    if set(item) != {"path", "mode", "sha256"} or item.get("mode") != "100644" or stat.S_IMODE((root / name).stat().st_mode) != 0o644:
                        errors.append("feedback companion mode/fields drifted: " + name)
                    if item.get("sha256") != hashlib.sha256(data).hexdigest():
                        errors.append("feedback companion target digest drifted: " + name)
        files = parity.get("files", [])
        if not isinstance(files, list) or any(not isinstance(row, dict) for row in files) or [row.get("destination") for row in files] != sorted(EXPECTED):
            errors.append("installer source parity omits, reorders or adds files")
        else:
            for row in files:
                name = row["destination"]
                source, blob = EXPECTED[name]
                if set(row) != {"destination", "source_path", "source_blob", "target_sha256", "adaptations"} or row.get("source_path") != source or row.get("source_blob") != blob:
                    errors.append("installer source blob/path drift: " + name)
                if row.get("target_sha256") != hashlib.sha256(payload_data[name]).hexdigest():
                    errors.append("installer parity target digest drift: " + name)
                if not isinstance(row.get("adaptations"), list) or not row["adaptations"] or any(not isinstance(x, str) or not x.strip() for x in row["adaptations"]):
                    errors.append("installer adaptation/limitation record missing: " + name)
        skill_names = []
        for name, data in payload_data.items():
            text = data.decode("utf-8")
            if name.endswith("/SKILL.md"):
                match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n(?:\n)?---\n", text)
                if not match or match.group(1) != PurePosixPath(name).parent.name:
                    errors.append("installer Skill frontmatter malformed: " + name)
                else:
                    skill_names.append(match.group(1))
            if name.startswith(".codex/agents/"):
                role = PurePosixPath(name).stem
                if not text.startswith('name = "' + role + '"\ndescription = "') or text.count('"""') != 2:
                    errors.append("installer native role structure drift: " + name)
                if re.search(r"^(model|sandbox_mode|approval_policy|permissions|mcp_servers)\s*=", text, re.M):
                    errors.append("installer native role must not override permissions/runtime: " + name)
            # Only concrete mandatory repository file references are checked.
            # Glob/placeholder/producer-created paths are not installed inputs.
            for reference in re.findall(r"`((?:\.agents/|\.codex/|\.github/)[A-Za-z0-9_./-]+\.(?:md|sh|ps1|toml|yml))`", text):
                optional = {".github/workflows/ci.yml", ".github/docs/context/SOURCES.md"}
                if reference not in EXPECTED and reference not in optional:
                    errors.append("installer dangling concrete resource: " + name + " -> " + reference)
            if re.search(r"\bPIN-000[12]\b|phase-task-ownership|codex-runtime-profile|t11-colima|T12 sole active", text):
                errors.append("installer payload leaks kit-development truth: " + name)
        if len(skill_names) != 8 or len(set(skill_names)) != 8:
            errors.append("installer must contain exactly eight unique Skills")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        errors.append("installer payload/provenance is missing, malformed or uncheckable")
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
    print("Installer inventory/parity: 47 files, 8 Skills, 3 role definitions; standalone feedback companion; offline structural evidence only.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
