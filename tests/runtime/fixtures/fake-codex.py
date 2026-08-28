#!/usr/bin/env python3
"""Offline-only fake for the T11 codex exec process boundary."""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


def emit(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def final(attempt="ATTEMPT-0123456789abcdef", outcome="completed"):
    return {
        "schema": "codex-final-response/v1",
        "attempt_id": attempt,
        "outcome": outcome,
        "summary": "Updated the sole owned representative file.",
        "changed_paths": ["work-item.txt"] if outcome == "completed" else [],
    }


def main():
    behavior = os.environ.get("T11_FAKE_BEHAVIOR", "valid")
    prompt = sys.stdin.buffer.read()
    if not prompt:
        return 64

    if behavior == "sleep":
        time.sleep(60)
        return 70
    if behavior == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
        return 70
    if behavior == "child-held-pipe":
        subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=sys.stdout,
            stderr=sys.stderr,
            start_new_session=False,
        )
        time.sleep(60)
        return 70
    if behavior == "child-exit-holds-pipe":
        subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=sys.stdout,
            stderr=sys.stderr,
            start_new_session=False,
        )
        # Keep the leader alive long enough for the immutable-identity tracker
        # to observe the child deterministically before orphan reparenting.
        time.sleep(0.1)
        return 0
    if behavior == "child-exit-closed-pipes":
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=False,
        )
        sys.stdout.write(str(child.pid) + "\n")
        sys.stdout.flush()
        time.sleep(0.1)
        return 0
    if behavior == "child-escaped-session":
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        sys.stdout.write(str(child.pid) + "\n")
        sys.stdout.flush()
        time.sleep(0.25)
        return 0
    if behavior == "signal":
        os.kill(os.getpid(), signal.SIGTERM)
        return 70
    if behavior == "invalid-utf8":
        sys.stdout.buffer.write(b"\xff\n")
        sys.stdout.buffer.flush()
        return 0
    if behavior == "partial-jsonl":
        sys.stdout.write('{"id":"e1","type":"thread.started"')
        sys.stdout.flush()
        return 0
    if behavior == "scalar-event":
        sys.stdout.write("7\n")
        sys.stdout.flush()
        return 0
    if behavior == "stdout-flood":
        sys.stdout.buffer.write(b"x" * 5_000_000)
        sys.stdout.buffer.flush()
        return 0
    if behavior == "stderr-flood":
        sys.stderr.buffer.write(b"x" * 500_000)
        sys.stderr.buffer.flush()
        return 1

    if behavior not in {"no-edit", "final-failed"}:
        Path("work-item.txt").write_bytes(b"status=complete\n")
    if behavior == "extra-file":
        Path("unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    elif behavior == "mode-change":
        os.chmod("work-item.txt", 0o755)
    elif behavior == "rename":
        Path("work-item.txt").rename("renamed.txt")
    elif behavior == "symlink":
        Path("work-item.txt").unlink()
        Path("work-item.txt").symlink_to("missing")
    elif behavior == "stage":
        subprocess.run(["git", "add", "work-item.txt"], check=True)
    elif behavior == "git-config":
        subprocess.run(["git", "config", "t11.drift", "true"], check=True)
    elif behavior == "git-hook":
        hook = Path(".git/hooks/post-checkout")
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(hook, 0o755)
    elif behavior == "branch-drift":
        subprocess.run(["git", "checkout", "-q", "-b", "drift"], check=True)
    elif behavior == "git-object":
        subprocess.run(["git", "hash-object", "-w", "--stdin"], input=b"unreachable\n", check=True)
    elif behavior == "git-ref":
        subprocess.run(["git", "update-ref", "refs/t11-hidden/drift", "HEAD"], check=True)
    elif behavior == "git-split-index":
        subprocess.run(["git", "update-index", "--split-index"], check=True)
    elif behavior == "git-head-replace":
        head = Path(".git/HEAD")
        replacement = Path(".git/HEAD.replacement")
        replacement.write_bytes(head.read_bytes())
        os.chmod(replacement, head.stat().st_mode & 0o777)
        os.replace(replacement, head)
    elif behavior == "git-namespace-replace":
        source = Path(".git")
        backup = Path("../t11-git-backup")
        replacement = Path("../t11-git-replacement")
        shutil.copytree(source, replacement, symlinks=True)
        source.rename(backup)
        replacement.rename(source)
    elif behavior == "replace-file":
        replacement = Path("replacement.tmp")
        replacement.write_bytes(b"status=complete\n")
        os.replace(replacement, Path("work-item.txt"))
    elif behavior == "tmpdir-write":
        (Path(os.environ["TMPDIR"]) / "unowned-worker-output").write_bytes(b"unexpected\n")
    elif behavior == "execution-root-sibling-write":
        (Path(os.environ["TMPDIR"]).parent / "unowned-worker-output").write_bytes(b"unexpected\n")

    events = [
        {"id": "e1", "type": "thread.started", "thread_id": "fixture-thread"},
        {"id": "e2", "type": "turn.started"},
        {
            "id": "e3",
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": json.dumps(
                    final(
                        "ATTEMPT-fedcba9876543210" if behavior == "attempt-drift" else "ATTEMPT-0123456789abcdef",
                        "failed" if behavior == "final-failed" else "completed",
                    ),
                    separators=(",", ":"),
                ),
            },
        },
        {"id": "e4", "type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    if behavior == "zero-terminal":
        events = events[:-1]
    elif behavior == "multiple-terminal":
        events.append({"id": "e5", "type": "turn.failed", "error": {"message": "fixture"}})
    elif behavior == "unknown-terminal":
        events[-1] = {"id": "e4", "type": "turn.stopped"}
    elif behavior == "interrupted":
        events[-1] = {"id": "e4", "type": "turn.failed", "error": {"message": "interrupted"}}
    elif behavior == "identical-duplicate":
        events.insert(1, dict(events[0]))
    elif behavior == "conflicting-duplicate":
        events.insert(1, {"id": "e1", "type": "turn.started"})
    elif behavior == "nested-json":
        value = current = {}
        for _ in range(40):
            current["x"] = {}
            current = current["x"]
        events[0]["nested"] = value
    elif behavior == "long-string":
        events[0]["long"] = "x" * 70_000

    for event in events:
        emit(event)
    return 1 if behavior in {"interrupted", "final-failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
