"""Chat-tree delivery and real installer preservation, not app/model E2E proof."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ROOT / ".github/distribution/payload"
SKILL = ".agents/skills/session-orchestration/SKILL.md"
GUIDE = "docs/distribution/chat-tree.md"
GUIDE_URL = "https://github.com/mochan-tk/agentic-dev-kit-for-codex/blob/main/" + GUIDE
HANDOFF_PACKET = ROOT / "docs/evaluation-fixtures/chat-tree-handoff/input.json"


def installer_fixture():
    spec = importlib.util.spec_from_file_location(
        "chat_tree_installer_fixture", ROOT / "tests/conformance/test_installer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.InstallerTests()


class ChatTreeDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = installer_fixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_public_guide_and_installed_handoff_are_reachable(self):
        # Link/delivery checks, not assertions that prose makes agents comply.
        self.assertIn(GUIDE, re.findall(r"\]\(([^)]+)\)",
                                       (ROOT / "README.md").read_text()))
        self.assertTrue((ROOT / GUIDE).is_file())
        self.assertIn(GUIDE_URL, re.findall(r"\]\(([^)]+)\)",
                                           (PAYLOAD / SKILL).read_text()))

    def test_inventory_keeps_one_existing_engine_and_no_new_installed_guide(self):
        rows = [line.split("\t") for line in
                (ROOT / ".github/distribution/payload.v1.tsv").read_text().splitlines()
                if line and not line.startswith("#")]
        self.assertEqual(47, len(rows))
        entries = {name: (kind, digest) for name, kind, digest in rows}
        self.assertEqual(47, len(entries))
        self.assertEqual(("engine", hashlib.sha256((PAYLOAD / SKILL).read_bytes()).hexdigest()),
                         entries[SKILL])
        self.assertNotIn(GUIDE, entries)

    def test_fresh_install_delivers_exact_skill_and_public_guide_handoff(self):
        result = self.fixture.run_install("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        installed = self.fixture.target / SKILL
        self.assertEqual((PAYLOAD / SKILL).read_bytes(), installed.read_bytes())
        self.assertEqual(0o644, installed.stat().st_mode & 0o777)
        self.assertIn(GUIDE_URL, re.findall(r"\]\(([^)]+)\)", installed.read_text()))
        self.assertFalse((self.fixture.target / GUIDE).exists())

    def old_skill_installation(self):
        # Use sealed historical bytes, not a fabricated "old" instructional file.
        record = json.loads((ROOT / "tests/fixtures/workflow-parity-baseline.json").read_text())
        self.assertEqual("abd7a4fba7ef5ff484efff625e2474cc32d6ef7b", record["commit"])
        entry = next(row for row in record["entries"] if row["path"] == SKILL)
        data = base64.b64decode(entry["base64"], validate=True)
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual("100644", entry["mode"])
        self.assertNotEqual(data, (PAYLOAD / SKILL).read_bytes())
        old = self.fixture.clone_source()
        (old / ".github/distribution/payload" / SKILL).write_bytes(data)
        self.fixture.reseal_payload(old)
        result = self.fixture.run_install("--apply", source=old)
        self.assertEqual(0, result.returncode, result.stderr)
        self.fixture.old_source, self.fixture.new_source = old, ROOT
        self.fixture.transaction = self.fixture.base / "chat tree operation"

    def test_known_old_single_engine_upgrade_and_rollback_preserve_adopter(self):
        self.old_skill_installation()
        preserved = ("README.md", "AGENTS.md", "SCAFFOLD-CHANGELOG.md",
                     ".github/codex-instructions.md", ".github/docs/agreements/requirements.md",
                     ".github/docs/context/SOURCES.md")
        for name in preserved:
            path = self.fixture.target / name
            path.write_text("Synthetic adopter-owned content\n")
            path.chmod(0o600)
        self.fixture.commit_adopter("synthetic prior installation")
        unrelated = self.fixture.target / "unrelated.txt"
        unrelated.write_text("staged application change\n")
        self.fixture.git("add", "unrelated.txt")
        unrelated.write_text("later unstaged application change\n")
        before = self.fixture.snapshot(self.fixture.target)
        modes = {str(p.relative_to(self.fixture.target)): p.stat().st_mode
                 for p in self.fixture.target.rglob("*")}
        result = self.fixture.upgrade("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        after = self.fixture.snapshot(self.fixture.target)
        self.assertEqual({SKILL}, {name for name in before.keys() | after.keys()
                                  if before.get(name) != after.get(name)})
        self.assertEqual((PAYLOAD / SKILL).read_bytes(),
                         (self.fixture.target / SKILL).read_bytes())
        self.assertEqual(modes, {str(p.relative_to(self.fixture.target)): p.stat().st_mode
                                 for p in self.fixture.target.rglob("*")})
        result = self.fixture.rollback("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.fixture.snapshot(self.fixture.target))
        self.assertEqual(modes, {str(p.relative_to(self.fixture.target)): p.stat().st_mode
                                 for p in self.fixture.target.rglob("*")})

    def test_customized_engine_refuses_upgrade_without_writes(self):
        self.old_skill_installation()
        (self.fixture.target / SKILL).write_text("Unrecognized local engine customization\n")
        before = self.fixture.snapshot(self.fixture.base)
        result = self.fixture.upgrade("--apply")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.fixture.snapshot(self.fixture.base))
        self.assertFalse(self.fixture.transaction.exists())


class ChatTreeHandoffPacketTests(unittest.TestCase):
    """Input integrity only; observed candidate behavior has separate receipts."""

    def test_candidate_packet_binds_current_skill_without_live_authority(self):
        packet = json.loads(HANDOFF_PACKET.read_text())
        self.assertEqual("synthetic", packet["evidence_class"])
        self.assertEqual("NOT_RUN", packet["evaluation_status"])
        self.assertEqual([], packet["allowed_writes"])
        self.assertEqual([], packet["external_operations"])
        skill = packet["skill"]
        self.assertEqual(str((PAYLOAD / SKILL).relative_to(ROOT)), skill["path"])
        self.assertEqual(hashlib.sha256((ROOT / skill["path"]).read_bytes()).hexdigest(),
                         skill["sha256"])

    def test_candidate_references_are_unambiguous_and_controller_is_separate(self):
        packet = json.loads(HANDOFF_PACKET.read_text())
        scenarios = packet["scenarios"]
        self.assertEqual(len(scenarios), len({case["id"] for case in scenarios}))
        decisions = [case["owner_display_decision"]["record"] for case in scenarios
                     if case["owner_display_decision"] is not None]
        self.assertEqual(len(decisions), len(set(decisions)))
        self.assertTrue(all(ref.startswith("synthetic:") for ref in decisions))
        app = packet["context"]["app_observation"]
        nodes = {node["id"]: node for node in app["nodes"]}
        self.assertEqual(len(nodes), len(app["nodes"]))
        self.assertEqual(set(nodes), set(app["owner_verified_order"]))
        for node in nodes.values():
            if node["parent"] is not None:
                self.assertIn(node["parent"], nodes)
        self.assertTrue((HANDOFF_PACKET.parent / "controller-review.md").is_file())
        self.assertNotIn("expected", packet)
        self.assertTrue(all("expected" not in case for case in scenarios))


if __name__ == "__main__":
    unittest.main()
