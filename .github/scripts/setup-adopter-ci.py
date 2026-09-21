#!/usr/bin/env python3
"""Preview or explicitly create the finite adopter CI addon; never overwrite."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ".github/distribution/adopter-ci/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--code-workflow", required=True)
    parser.add_argument("--check", required=True, action="append", dest="checks")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    created = []
    try:
        spec = importlib.util.spec_from_file_location("adopter_sensor", ROOT / SOURCE / "check-adopter-ci.py")
        sensor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sensor)
        need = sensor.need
        target = sensor.safe_root(args.target)
        need(all(shutil.which(x) for x in ("bash", "git", "jq", "gh", "base64")),
             "required dependency unavailable")
        result = sensor.bounded_command(["git", "-C", str(target), "rev-parse", "--show-toplevel"])
        need(result.returncode == 0 and Path(result.stdout.strip()).resolve() == target,
             "target must be an existing Git repository root")
        source = {sensor.META: sensor.read_file(ROOT, SOURCE + "task-ritual.yml"),
                  sensor.SELF: sensor.read_file(ROOT, SOURCE + "check-adopter-ci.py")}
        need(sensor.digest(source[sensor.META]) == sensor.METADATA_SHA256,
             "source metadata template differs from reviewed sensor")
        ritual = sensor.read_file(target, sensor.RITUAL)
        need(sensor.digest(ritual) == sensor.RITUAL_SHA256, "installed ritual dependency missing or changed")
        config = dict(schema="adopter-ci/v1", code_workflow=args.code_workflow,
                      checks=sorted(args.checks), controls=sensor.CONTROLS,
                      sensor_sha256=sensor.digest(source[sensor.SELF]),
                      metadata_sha256=sensor.digest(source[sensor.META]),
                      ritual_sha256=sensor.RITUAL_SHA256)
        source[sensor.CONFIG] = (json.dumps(config, indent=2) + "\n").encode()
        sensor.configuration(source[sensor.CONFIG])
        code = sensor.read_file(target, args.code_workflow)
        sensor.code_contract(code, config["checks"])
        present = []
        for path, data in source.items():
            destination = sensor.safe_path(target, path)
            if destination.exists():
                need(sensor.read_file(target, path) == data, "addon collision; no overwrite supported: " + path)
                present.append(path)
        need(not present or len(present) == len(source), "partial addon preimage; inspect and recover manually")
        need(sensor.workflow_paths(target) == sorted([args.code_workflow] + ([sensor.META] if present else [])),
             "unsupported or duplicate workflow producer")
        if present:
            sensor.local_drift(target)
            print("UNCHANGED: all three addon files are identical; no files or index changed")
            return 0
        if not args.apply:
            print("PREVIEW: would create " + ", ".join(sorted(source)) + "; no files or index changed")
            return 0
        # Validate all inputs and destinations again immediately before creation.
        need(sensor.read_file(target, args.code_workflow) == code
             and sensor.read_file(target, sensor.RITUAL) == ritual,
             "adopter input changed during preview")
        for path in source:
            need(not sensor.safe_path(target, path).exists(), "destination appeared before apply")
        # Existing dependency paths mean both parent directories already exist.
        # O_EXCL/O_NOFOLLOW never replace a file. A partial failure retains only
        # known newly-created files and reports their finite names for recovery.
        for path, data in source.items():
            sensor.safe_path(target, path)
            parent, name = sensor.open_parent(target, path)
            try:
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=parent)
            finally:
                os.close(parent)
            created.append(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
        sensor.local_drift(target)
        print("CREATED: " + ", ".join(sorted(created)) + "; review the installation PR before activation")
        return 0
    except Exception as error:
        reason = str(error) if type(error).__name__ == "Fault" else "input or operation unavailable"
        print("REFUSED: " + reason, file=sys.stderr)
        if created:
            print("PARTIAL: retained newly created addon paths: " + ", ".join(sorted(created)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
