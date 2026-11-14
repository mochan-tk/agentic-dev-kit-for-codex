"""Manifest set operations using real Bash/Git and synthetic parity sections."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ".github/distribution/payload"
INVENTORY = ".github/distribution/payload.v1.tsv"
PARITY = ".github/distribution/source-parity.v1.json"
ENGINE = ".github/scripts/scaffold-install.sh"
ENTRY = ".github/scripts/scaffold-init.sh"
EXTRA = "zz-fixture/nested/engine.txt"


def rows_at(root):
    return [line.split("\t") for line in (root / INVENTORY).read_text().splitlines()
            if line and not line.startswith("#")]


def change_payload(root, additions=None, removals=(), permute=None):
    """Use the approved parity-section flow; re-seal only current manifest pins."""
    old_digest = hashlib.sha256((root / INVENTORY).read_bytes()).hexdigest()
    rows = [row for row in rows_at(root) if row[0] not in removals]
    for name in removals:
        (root / PAYLOAD / name).unlink()
    for name, kind in (additions or {}).items():
        path = root / PAYLOAD / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("Synthetic manifest fixture: " + name + "\n").encode())
        path.chmod(0o644)
        rows.append([name, kind, hashlib.sha256(path.read_bytes()).hexdigest()])
    rows.sort()
    if permute:
        rows = permute(rows)
    data = "".join("\t".join(row) + "\n" for row in rows).encode()
    (root / INVENTORY).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    parity = json.loads((root / PARITY).read_text())
    initial = {row["destination"] for row in parity["files"]}
    names = {row[0] for row in rows}
    parity["added_payload_files"] = sorted(names - initial)
    parity["removed_payload_files"] = sorted(initial - names)
    layout = b"".join(sorted((name + "\t" + kind + "\n").encode()
                            for name, kind, _ in rows))
    parity["payload_layout_sha256"] = hashlib.sha256(layout).hexdigest()
    for section in parity.values():
        if isinstance(section, dict):
            for row in section.get("target_files", []):
                if row["path"] == INVENTORY:
                    row["sha256"] = digest
            for row in section.get("export_adaptations", []):
                if row["path"] == INVENTORY:
                    row["target_sha256"] = digest
                    row["target_blob"] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    (root / PARITY).write_text(json.dumps(parity, indent=2) + "\n")
    for script in ("check-product.py", "check-installer.py"):
        path = root / ".github/scripts" / script
        if path.exists():
            path.write_text(path.read_text().replace(old_digest, digest))


class ManifestSetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="installer-sets-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "SCAFFOLD_"))}
        self.env.update(LC_ALL="C", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.target = self.adopter("adopter")

    def adopter(self, name):
        target = self.base / name
        target.mkdir()
        subprocess.run(["git", "init", "--template=", "-q", "-b", "main", str(target)],
                       check=True, env=self.env)
        return target

    def source(self, name):
        source = self.base / name
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        # Fixture inputs retain reviewed Git modes despite the checkout's umask.
        for path in source.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        return source

    @staticmethod
    def snapshot(root):
        return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
                else ("file", stat.S_IMODE(p.stat().st_mode), p.read_bytes()) if p.is_file()
                else ("dir", stat.S_IMODE(p.stat().st_mode)) for p in root.rglob("*")}

    def run_engine(self, source, *args, target=None, entry=ENGINE):
        return subprocess.run(["bash", str(source / entry), *args, str(target or self.target)],
                              env=dict(self.env, SCAFFOLD_SOURCE_DIR=str(source)),
                              capture_output=True, text=True, timeout=120)

    def success(self, result):
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def product(self, source):
        return subprocess.run([sys.executable, "-I", str(source / ".github/scripts/check-product.py")],
                              cwd=source, capture_output=True, text=True, timeout=60)

    def upgrade(self, old, new, tx, apply=True, target=None):
        return self.run_engine(new, "--upgrade", "--old-source", str(old), "--transaction", str(tx),
                               "--apply" if apply else "--dry-run", target=target)

    def rollback(self, new, tx, apply=True, target=None):
        return self.run_engine(new, "--rollback", "--transaction", str(tx),
                               "--apply" if apply else "--dry-run", target=target)

    def assert_union_rows(self, old_names, new, tx):
        union = sorted(set(old_names) | {row[0] for row in rows_at(new)})
        records = [row.split("\t") for row in (tx / "files.tsv").read_text().splitlines()]
        self.assertEqual(sorted(row[1] for row in records), [row[1] for row in records])
        for index, name, _, _ in records:
            self.assertEqual(union.index(name), int(index))
        return records

    def test_added_file_install_upgrade_delete_and_rollback(self):
        old, added = self.source("old"), self.source("added")
        self.assertEqual(47, len(rows_at(old)), "property of this base fixture")
        change_payload(added, {EXTRA: "engine"})
        self.assertEqual(48, len(rows_at(added)), "property of this expanded fixture")
        self.success(self.product(added))
        self.success(self.run_engine(added, "--apply", entry=ENTRY))
        installed = self.snapshot(self.target)
        addition_target = self.adopter("addition-adopter")
        self.success(self.run_engine(old, "--apply", target=addition_target))
        before_add = self.snapshot(addition_target)
        add_tx = self.base / "addition-record"
        (old / PARITY).unlink()  # OLD never depends on old parity.
        self.success(self.upgrade(old, added, add_tx, target=addition_target))
        self.assertEqual((added / PAYLOAD / EXTRA).read_bytes(), (addition_target / EXTRA).read_bytes())
        self.success(self.rollback(added, add_tx, target=addition_target))
        self.assertEqual(before_add, self.snapshot(addition_target))
        removed = self.base / "removed"
        shutil.copytree(added, removed)
        change_payload(removed, removals=(EXTRA,))
        self.success(self.product(removed))
        old_names = [row[0] for row in rows_at(added)]
        (added / PARITY).unlink()
        tx = self.base / "deletion-record"
        self.success(self.upgrade(added, removed, tx, apply=False))
        self.assertEqual(installed, self.snapshot(self.target))
        self.assertFalse(tx.exists())
        self.success(self.upgrade(added, removed, tx))
        records = self.assert_union_rows(old_names, removed, tx)
        self.assertEqual(1, len(records))
        self.assertEqual([EXTRA, hashlib.sha256(installed[EXTRA][2]).hexdigest(), "-"], records[0][1:])
        self.assertEqual(installed[EXTRA][2], (tx / "before-0").read_bytes())
        self.assertEqual(["zz-fixture", "zz-fixture/nested"], (tx / "directories.tsv").read_text().splitlines())
        self.assertFalse((self.target / "zz-fixture").exists())
        self.assertEqual("schema\tlocal-upgrade/v1", (tx / "meta.tsv").read_text().splitlines()[0])
        self.assertEqual({"meta.tsv", "files.tsv", "directories.tsv", "record.sha256", "status", "before-0"},
                         {path.name for path in tx.iterdir()})
        after = self.snapshot(self.target)
        self.success(self.rollback(removed, tx, apply=False))
        self.assertEqual(after, self.snapshot(self.target))
        self.success(self.rollback(removed, tx))
        self.assertEqual(installed, self.snapshot(self.target))
        self.assertEqual(0o644, stat.S_IMODE((self.target / EXTRA).stat().st_mode))
        self.success(self.rollback(removed, tx))
        self.assertEqual(installed, self.snapshot(self.target))

    def test_actual_digest_and_layout_tamper_refuse(self):
        for defect in ("bytes", "layout"):
            with self.subTest(defect=defect):
                source = self.source(defect)
                name = rows_at(source)[0][0]
                if defect == "bytes":
                    path = source / PAYLOAD / name
                    path.write_bytes(path.read_bytes() + b"tampered\n")
                else:
                    rows = rows_at(source)
                    rows[0][1] = "seed"
                    (source / INVENTORY).write_text("".join("\t".join(row) + "\n" for row in rows))
                result = self.product(source)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("digest" if defect == "bytes" else "payload_layout_sha256", result.stdout + result.stderr)
                before = self.snapshot(self.target)
                for entry in (ENTRY, ENGINE):
                    result = self.run_engine(source, "--apply", entry=entry)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("digest drift" if defect == "bytes" else "layout", result.stderr)
                    self.assertEqual(before, self.snapshot(self.target))

    def test_layout_digest_requires_exactly_one_match(self):
        for defect in ("missing", "duplicate"):
            with self.subTest(defect=defect):
                source = self.source(defect)
                path = source / PARITY
                lines = path.read_text().splitlines(keepends=True)
                match = next(line for line in lines if '"payload_layout_sha256":' in line)
                path.write_text("".join(lines).replace(match, "" if defect == "missing" else match + match))
                before = self.snapshot(self.target)
                result = self.run_engine(source, "--apply")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("missing or ambiguous payload layout digest", result.stderr)
                self.assertEqual(before, self.snapshot(self.target))

    def test_modified_engine_removal_refuses_before_any_write(self):
        old, new = self.source("old"), self.source("new")
        change_payload(old, {EXTRA: "engine"})
        change_payload(new, {".000-addition.txt": "engine"})
        self.success(self.run_engine(old, "--apply"))
        (self.target / EXTRA).write_bytes(b"adopter edit\n")
        before = self.snapshot(self.target)
        tx = self.base / "record"
        result = self.upgrade(old, new, tx)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("removed engine modified: " + EXTRA, result.stderr)
        self.assertEqual(before, self.snapshot(self.target))
        self.assertFalse(tx.exists())

    def test_non_engine_removal_refuses_before_any_write(self):
        for kind in ("tuned", "instance", "seed"):
            with self.subTest(kind=kind):
                old, new = self.source("old-" + kind), self.source("new-" + kind)
                change_payload(old, {EXTRA: kind})
                target = self.adopter("target-" + kind)
                self.success(self.run_engine(old, "--apply", target=target))
                before = self.snapshot(target)
                tx = self.base / ("record-" + kind)
                result = self.upgrade(old, new, tx, target=target)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("removed non-engine path: " + EXTRA, result.stderr)
                self.assertEqual(before, self.snapshot(target))
                self.assertFalse(tx.exists())

    def test_head_middle_permutations_install_upgrade_and_rollback(self):
        old, new = self.source("old"), self.source("new")
        old_added = {".000-fixture/old.txt": "engine", ".github/aaa-fixture/old.txt": "engine"}
        new_added = {".001-fixture/new.txt": "engine", ".github/aab-fixture/new.txt": "engine"}
        change_payload(old, old_added, permute=lambda rows: list(reversed(rows)))
        change_payload(new, new_added, permute=lambda rows: rows[17:] + rows[:17])
        self.success(self.product(old))
        self.success(self.product(new))
        self.success(self.run_engine(old, "--apply"))
        before = self.snapshot(self.target)
        install_target = self.adopter("new-install")
        self.success(self.run_engine(new, "--apply", target=install_target))
        tx = self.base / "record"
        self.success(self.upgrade(old, new, tx))
        records = self.assert_union_rows([row[0] for row in rows_at(old)], new, tx)
        self.assertEqual(set(old_added) | set(new_added), {row[1] for row in records})
        for name in old_added:
            self.assertFalse((self.target / name).exists())
        for name in new_added:
            self.assertEqual((new / PAYLOAD / name).read_bytes(), (self.target / name).read_bytes())
        self.assertNotIn(".github", (tx / "directories.tsv").read_text().splitlines())
        self.success(self.rollback(new, tx))
        self.assertEqual(before, self.snapshot(self.target))

    def test_unrecorded_empty_directory_is_retained(self):
        old, new = self.source("old"), self.source("new")
        change_payload(old, {EXTRA: "engine"})
        self.success(self.run_engine(old, "--apply"))
        unrelated = self.target / "zz-fixture/unrelated-empty"
        unrelated.mkdir()
        before = self.snapshot(self.target)
        tx = self.base / "record"
        self.success(self.upgrade(old, new, tx))
        self.assertTrue(unrelated.is_dir())
        self.assertEqual(["zz-fixture/nested"], (tx / "directories.tsv").read_text().splitlines())
        self.success(self.rollback(new, tx))
        self.assertEqual(before, self.snapshot(self.target))

    def test_oversized_recovery_records_refuse_before_target_writes(self):
        for defect in ("directories", "record-size"):
            with self.subTest(defect=defect):
                old, new = self.source("old-" + defect), self.source("new-" + defect)
                target = self.adopter("target-" + defect)
                if defect == "directories":
                    name = "zz-limit/" + "d/" * 128 + "engine.txt"
                    change_payload(new, {name: "engine"})
                    expected_error = "too many operation directories"
                else:
                    base_size = len((old / INVENTORY).read_bytes())
                    names = ["zz-limit/old-" + str(i) + "-" + "x" * 180 + ".txt" for i in range(100)]
                    count = (16384 - base_size - 100) // (len(names[-1]) + 73)
                    old_added = {name: "engine" for name in names[:count]}
                    new_added = {name.replace("/old-", "/new-"): "engine" for name in old_added}
                    change_payload(old, old_added)
                    change_payload(new, new_added)
                    self.assertLessEqual(len((old / INVENTORY).read_bytes()), 16384)
                    self.assertLessEqual(len((new / INVENTORY).read_bytes()), 16384)
                    expected_rows = sum(len(name) + 70 for name in old_added.keys() | new_added.keys())
                    self.assertGreater(expected_rows, 16384)
                    expected_error = "bounded file size exceeded"
                self.success(self.run_engine(old, "--apply", target=target))
                before = self.snapshot(target)
                tx = self.base / ("record-" + defect)
                result = self.upgrade(old, new, tx, target=target)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertEqual(before, self.snapshot(target))

    def test_rollback_without_parity_retains_record_and_payload_link_checks(self):
        old, new = self.source("old"), self.source("new")
        change_payload(new, {EXTRA: "engine"})
        self.success(self.run_engine(old, "--apply"))
        original = self.snapshot(self.target)
        tx = self.base / "record"
        self.success(self.upgrade(old, new, tx))
        after = self.snapshot(self.target)
        (new / PARITY).unlink()
        # Parity absence is compatible only with recorded rollback.
        refused = self.run_engine(new, "--apply")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("input is not a no-link regular file", refused.stderr)
        self.assertEqual(after, self.snapshot(self.target))
        for path in (tx / "files.tsv", new / PAYLOAD / EXTRA):
            with self.subTest(path=str(path.relative_to(self.base))):
                saved = self.base / "saved-input"
                path.rename(saved)
                path.symlink_to(saved)
                result = self.rollback(new, tx)
                self.assertNotEqual(0, result.returncode)
                self.assertTrue("no-link regular file" in result.stderr or "source payload symlink" in result.stderr,
                                result.stderr)
                self.assertEqual(after, self.snapshot(self.target))
                path.unlink()
                saved.rename(path)
        self.success(self.rollback(new, tx))
        self.assertEqual(original, self.snapshot(self.target))

    def test_transaction_progress_uses_record_count(self):
        old, new = self.source("old"), self.source("new")
        change_payload(new, {EXTRA: "engine"})
        before = self.snapshot(self.target)
        tx = self.base / "record"
        self.success(self.upgrade(old, new, tx))
        records = self.assert_union_rows([row[0] for row in rows_at(old)], new, tx)
        self.assertEqual(48, len(records), "this fixture changes every expanded payload entry")
        self.assertEqual("applied\t48\n", (tx / "status").read_text())
        self.success(self.rollback(new, tx))
        self.assertEqual(before, self.snapshot(self.target))


if __name__ == "__main__":
    unittest.main()
