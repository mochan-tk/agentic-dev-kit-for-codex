#!/usr/bin/env python3
"""Bounded explicit retrospective observations and receiving-side routing."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time

OFFICIAL_URL = "https://learn.chatgpt.com/docs/changelog"
BASELINE = ".github/distribution/ongoing-improvement/platform-baseline.v1.json"
PAGE_SIZE = 50
MAX_PAGES = 11
MAX_ISSUES = 500
MAX_COMMENTS = 200
MAX_BYTES = 2097152
MAX_TOTAL_BYTES = 16777216
MAX_CALLS = 512
FILE_LIMIT = 262144
MARKER = "<!-- adopter-feedback:v1 -->"
REPORT_MARKER = "<!-- ongoing-improvement:v1 -->"
REPORT_PREFIX = "Retro hygiene review "
REPOSITORY = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}"
REFERENCE = re.compile(r"https://github[.]com/" + REPOSITORY
                       + r"/(?:(?:issues|pull)/[1-9][0-9]{0,9}(?:#(?:issuecomment-|discussion_r|pullrequestreview-)[1-9][0-9]{0,19})?"
                       + r"|actions/runs/[1-9][0-9]{0,19}(?:/job/[1-9][0-9]{0,19})?|commit/[0-9a-f]{40})\Z")


class Fault(ValueError):
    """Only fixed diagnostics may cross the CLI boundary."""


class Unconfirmed(Fault):
    pass


def require(value):
    if not value:
        raise Fault("uncheckable")


def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def parse_json(data):
    try:
        return json.loads(data, object_pairs_hook=unique_keys, parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Fault("uncheckable") from exc


def positive(value, maximum=10**20 - 1):
    require(type(value) is int and 0 < value <= maximum)
    return value


def bounded_text(value, maximum=65536):
    require(isinstance(value, str) and len(value.encode("utf-8")) <= maximum and "\0" not in value)
    return value


def timestamp(value, now):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value))
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise Fault("uncheckable") from exc
    require(parsed <= now)
    return parsed


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def safe_read(path, limit=FILE_LIMIT):
    """No-follow component traversal, regular bounded file, final identity readback."""
    path = Path(os.path.abspath(path))
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit)
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        require(len(data) <= limit and identity(before) == identity(after) == identity(current))
        return data, identity(before)
    finally:
        os.close(descriptor)


class Transport:
    def __init__(self):
        self.deadline = time.monotonic() + 120
        self.calls = 0
        self.total = 0

    def command(self, argv, payload=None):
        self.calls += 1
        require(self.calls <= MAX_CALLS and time.monotonic() < self.deadline)
        environment = dict(os.environ, GH_HOST="github.com", GH_DEBUG="", GH_PROMPT_DISABLED="1", GH_PAGER="cat", PAGER="cat")
        # A bounded private stdin file avoids blocking on a pipe while writing.
        with tempfile.TemporaryFile() as input_file:
            if payload is not None:
                raw = json.dumps(payload, ensure_ascii=True).encode()
                require(len(raw) <= MAX_BYTES)
                input_file.write(raw)
                input_file.seek(0)
            process = subprocess.Popen(argv, stdin=input_file, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=environment, start_new_session=True)
            output = bytearray()
            deadline = min(self.deadline, time.monotonic() + 20)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        require(time.monotonic() < deadline)
                        for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            output.extend(chunk)
                            self.total += len(chunk)
                            require(len(output) <= MAX_BYTES + 16384 and self.total <= MAX_TOTAL_BYTES)
                require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0)
                return bytes(output)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                process.stdout.close()

    def api(self, endpoint, payload=None):
        method = "GET" if payload is None else "POST"
        args = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
        if payload is not None:
            args.extend(["--input", "-"])
        return parse_json(self.command(args, payload))


def labels(value):
    require(isinstance(value, list) and len(value) <= 100)
    names = [bounded_text(row.get("name"), 100) for row in value if isinstance(row, dict)]
    require(len(names) == len(value) == len(set(names)))
    return sorted(names)


def issue_record(value, repo, now, number=None):
    require(isinstance(value, dict))
    number_value = positive(value.get("number"), 10**10 - 1)
    require(number is None or number_value == number)
    prefix = f"https://api.github.com/repos/{repo}"
    is_pull = "pull_request" in value
    route = "pull" if is_pull else "issues"
    require(value.get("url") == f"{prefix}/issues/{number_value}"
            and value.get("html_url") == f"https://github.com/{repo}/{route}/{number_value}"
            and value.get("repository_url") == prefix and value.get("state") in ("open", "closed"))
    if is_pull:
        require(isinstance(value["pull_request"], dict)
                and value["pull_request"].get("url") == f"{prefix}/pulls/{number_value}")
    created = timestamp(value.get("created_at"), now)
    updated = timestamp(value.get("updated_at"), now)
    require(created <= updated and type(value.get("comments")) is int and 0 <= value["comments"] <= MAX_COMMENTS)
    return {"id": positive(value.get("id")), "number": number_value, "url": value["html_url"],
            "state": value["state"], "title": bounded_text(value.get("title"), 1024),
            "body": bounded_text("" if value.get("body") is None and "body" in value else value.get("body")), "created_at": value["created_at"],
            "updated_at": value["updated_at"], "comments": value["comments"],
            "labels": labels(value.get("labels")), "pull_request": is_pull}


def comment_record(value, repo, number, now):
    require(isinstance(value, dict))
    identifier = positive(value.get("id"))
    require(value.get("issue_url") == f"https://api.github.com/repos/{repo}/issues/{number}"
            and value.get("html_url") == f"https://github.com/{repo}/issues/{number}#issuecomment-{identifier}")
    require(timestamp(value.get("created_at"), now) <= timestamp(value.get("updated_at"), now))
    return {key: value[key] for key in ("id", "created_at", "updated_at")} | {"body": bounded_text(value.get("body"))}


class Ledger:
    def __init__(self, transport, repo, now):
        self.transport, self.repo, self.now = transport, repo, now
        self.prefix = "repos/" + repo

    def one(self, number):
        value = self.transport.api(f"{self.prefix}/issues/{number}")
        return issue_record(value, self.repo, datetime.now(timezone.utc), number)

    def pages(self, endpoint, validator, maximum):
        result, identifiers = [], set()
        for page in range(1, MAX_PAGES + 1):
            separator = "&" if "?" in endpoint else "?"
            values = self.transport.api(endpoint + separator + f"per_page={PAGE_SIZE}&page={page}")
            require(isinstance(values, list) and len(values) <= PAGE_SIZE)
            for value in values:
                row = validator(value)
                require(row["id"] not in identifiers)
                identifiers.add(row["id"])
                result.append(row)
                require(len(result) <= maximum)
            if len(values) < PAGE_SIZE:
                return result
        raise Fault("uncheckable")

    def issues(self, candidates=False):
        query = "?state=open&labels=retro%3Acandidate" if candidates else "?state=all"
        rows = self.pages(self.prefix + "/issues" + query,
                          lambda row: issue_record(row, self.repo, datetime.now(timezone.utc)), MAX_ISSUES)
        require(len({r["number"] for r in rows}) == len(rows))
        if candidates:
            require(all(r["state"] == "open" and "retro:candidate" in r["labels"] and not r["pull_request"] for r in rows))
        return rows

    def comments(self, row):
        result = self.pages(f"{self.prefix}/issues/{row['number']}/comments",
                            lambda value: comment_record(value, self.repo, row["number"], datetime.now(timezone.utc)), MAX_COMMENTS)
        require(len(result) == row["comments"])
        require(all(timestamp(c["created_at"], self.now) >= timestamp(row["created_at"], self.now) for c in result))
        return result

    def label(self, name):
        value = self.transport.api(self.prefix + "/labels/" + name.replace(":", "%3A"))
        require(isinstance(value, dict) and value.get("name") == name)


def evidence(body, occurrence=False):
    """Canonical links in a filing, or in an anchored occurrence body.

    Existing retrospective filings have no required field prefix. Quoted and
    fenced examples are excluded; a filing without recognized evidence refuses.
    """
    if occurrence:
        if not body.startswith("Occurrence:"):
            return set()
        body = body[len("Occurrence:"):]
    references = set()
    fence = None
    for line in body.splitlines():
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (delimiter and delimiter[1][0] == fence[0] and len(delimiter[1]) >= fence[1]
                    and not delimiter[2].strip()):
                fence = None
            continue
        if delimiter:
            fence = (delimiter[1][0], len(delimiter[1]))
            continue
        if line.lstrip().startswith(">"):
            continue
        for candidate in re.findall(r"https://[^\s<>\]\)]+", line):
            candidate = candidate.rstrip(".,;")
            require(REFERENCE.fullmatch(candidate) is not None)
            references.add(candidate)
    require(bool(references) and len(references) <= 200)
    return references


def classification(title, body):
    bounded_text(title, 1024)
    bounded_text(body)
    if "<!-- adopter-feedback:" in body and not (body == MARKER or body.startswith(MARKER + "\n")):
        return "not-matched"
    if body == MARKER or body.startswith(MARKER + "\n"):
        return "matched"
    return "matched" if title == "[adopter-feedback]" or title.startswith("[adopter-feedback] ") else "not-matched"


def baseline_record(data):
    record = parse_json(data)
    require(isinstance(record, dict) and set(record) == {"schema", "url", "kind", "sha256", "observed_on"})
    require(record["schema"] == "official-checkpoint/v1" and record["url"] == OFFICIAL_URL
            and record["kind"] == "html-sha256" and isinstance(record["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]))
    require(isinstance(record["observed_on"], str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", record["observed_on"]))
    try:
        datetime.strptime(record["observed_on"], "%Y-%m-%d")
    except ValueError as exc:
        raise Fault("uncheckable") from exc
    return record


def checkpoint_response(raw, expected):
    require(len(raw) <= MAX_BYTES + 16384 and b"\r\n\r\n" in raw)
    headers, body = raw.split(b"\r\n\r\n", 1)
    require(len(headers) <= 16384 and 0 < len(body) <= MAX_BYTES)
    lines = headers.split(b"\r\n")
    require(re.fullmatch(rb"HTTP/(?:1[.]1|2|3) 200(?: [^\r\n]*)?", lines[0]))
    names = {}
    for line in lines[1:]:
        require(b":" in line)
        name, value = line.split(b":", 1)
        name = name.lower()
        if name in (b"content-type", b"location", b"content-length"):
            require(name not in names)
            names[name] = value.strip()
    require(b"location" not in names and names.get(b"content-type", b"").split(b";", 1)[0].strip().lower() == b"text/html")
    if b"content-length" in names:
        require(names[b"content-length"].isdigit() and int(names[b"content-length"]) == len(body))
    require(re.search(rb"<html(?:\s|>)", body[:8192], re.I) is not None)
    observed = hashlib.sha256(body).hexdigest()
    return {"status": "unchanged" if observed == expected else "changed", "url": OFFICIAL_URL,
            "baseline_sha256": expected, "observed_sha256": observed}


def platform(transport, path):
    data, before = safe_read(path, 4096)
    record = baseline_record(data)  # Closed validation precedes every network read.
    raw = transport.command(["curl", "--disable", "--silent", "--show-error", "--include", "--proto", "=https",
                             "--max-redirs", "0", "--max-time", "15", "--max-filesize", str(MAX_BYTES), record["url"]])
    result = checkpoint_response(raw, record["sha256"])
    require(safe_read(path, 4096) == (data, before))
    return result


def budget(target):
    snapshots, rows = {}, []
    for relative in ("AGENTS.md", ".github/codex-instructions.md"):
        snapshot = safe_read(Path(target) / relative)
        data = snapshot[0]
        count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        snapshots[relative] = snapshot
        rows.append({"file": relative, "lines": count, "advisory_target": 150,
                     "status": "over-target" if count > 150 else "within-target"})
    return rows, snapshots


def check_budget(target, snapshots):
    require(all(safe_read(Path(target) / name) == snapshot for name, snapshot in snapshots.items()))


def observe(ledger, target, period, checkpoint):
    budgets, snapshots = budget(target)
    initial = ledger.issues(candidates=True)
    comments, candidates = {}, []
    for row in initial:
        require(ledger.one(row["number"]) == row)
        filing = evidence(row["body"])
        observed_comments = ledger.comments(row)
        comments[row["number"]] = observed_comments
        references = set(filing)
        for comment in observed_comments:
            references.update(evidence(comment["body"], occurrence=True))
        latest = max([timestamp(row["updated_at"], ledger.now)] + [timestamp(c["updated_at"], ledger.now) for c in observed_comments])
        age = (ledger.now - timestamp(row["created_at"], ledger.now)).days
        inactivity = (ledger.now - latest).days
        candidates.append({"issue": row["url"], "unique_evidence_references": len(references),
                           "independent_incidents": "unverified", "age_days": age, "inactivity_days": inactivity,
                           "status": "human-review" if len(references) >= 2 or inactivity >= 30 else "watch"})
    report = {"schema": "ongoing-improvement/v1", "repository": f"https://github.com/{ledger.repo}", "period": period,
              "ledger": "observed-empty" if not candidates else "observed", "candidates": candidates,
              "budget": budgets, "platform": checkpoint, "publication": "read-only"}

    def final_readback():
        require(ledger.issues(candidates=True) == initial)
        for row in initial:
            require(ledger.comments(row) == comments[row["number"]])
            require(ledger.one(row["number"]) == row)
        check_budget(target, snapshots)

    final_readback()
    return report, final_readback


def report_body(report):
    return REPORT_MARKER + "\n\n" + json.dumps(report, sort_keys=True, indent=2) + "\n"


def report_period(body):
    if not body.startswith("<!-- ongoing-improvement:"):
        return None
    require(body.startswith(REPORT_MARKER + "\n"))
    value = parse_json(body[len(REPORT_MARKER):])
    require(isinstance(value, dict)
            and set(value) == {"schema", "repository", "period", "ledger", "candidates", "budget", "platform", "publication"}
            and value["schema"] == "ongoing-improvement/v1" and value["publication"] == "read-only"
            and isinstance(value["period"], str) and re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", value["period"])
            and isinstance(value["repository"], str) and re.fullmatch(r"https://github[.]com/" + REPOSITORY, value["repository"])
            and value["ledger"] in ("observed", "observed-empty") and isinstance(value["candidates"], list)
            and isinstance(value["budget"], list) and isinstance(value["platform"], dict))
    return value["period"]


def publish(ledger, report, final_readback):
    title = REPORT_PREFIX + report["period"]
    body = report_body(report)
    initial = ledger.issues()
    # Same-period titles are reserved. Any conflicting schema, target or content
    # is non-success, even if closed or lacking the expected marker or label.
    related = []
    for row in initial:
        observed_period = report_period(row["body"])
        if row["title"] == title or observed_period == report["period"]:
            related.append(row)
    require(len(related) <= 1)
    if related:
        row = related[0]
        require(not row["pull_request"] and row["title"] == title and row["body"] == body and "needs:human" in row["labels"])
        require(ledger.one(row["number"]) == row)
        require(ledger.issues() == initial)
        final_readback()
        require(ledger.one(row["number"]) == row)
        return "verified-noop", row["url"]
    ledger.label("needs:human")
    final_readback()
    require(ledger.issues() == initial)
    try:
        value = ledger.transport.api(ledger.prefix + "/issues", {"title": title, "body": body, "labels": ["needs:human"]})
        row = issue_record(value, ledger.repo, datetime.now(timezone.utc))
        require(not row["pull_request"] and row["state"] == "open" and row["title"] == title and row["body"] == body
                and row["labels"] == ["needs:human"] and row["comments"] == 0
                and row["number"] not in {r["number"] for r in initial})
        require(ledger.one(row["number"]) == row)
        return "confirmed", row["url"]
    except (Fault, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise Unconfirmed("submission-unconfirmed") from exc


def feedback(ledger, number, apply):
    row = ledger.one(number)
    require(not row["pull_request"])
    matched = classification(row["title"], row["body"])
    result = {"schema": "feedback-triage/v1", "issue": row["url"], "classification": matched, "publication": "read-only"}
    if not apply or matched != "matched":
        require(ledger.one(number) == row)
        return result
    ledger.label("from:adopter")
    require(ledger.one(number) == row)
    if "from:adopter" in row["labels"]:
        result["publication"] = "verified-noop"
        return result
    expected_labels = sorted(row["labels"] + ["from:adopter"])
    try:
        value = ledger.transport.api(f"{ledger.prefix}/issues/{number}/labels", {"labels": ["from:adopter"]})
        require(labels(value) == expected_labels)
        current = ledger.one(number)
        expected = dict(row, labels=expected_labels, updated_at=current["updated_at"])
        require(current == expected and current["updated_at"] >= row["updated_at"])
        result["publication"] = "confirmed"
        return result
    except (Fault, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise Unconfirmed("submission-unconfirmed") from exc


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fault("invalid-input")


def main(argv=None):
    try:
        require(sys.version_info >= (3, 11))
        parser = Parser(description=__doc__)
        parser.add_argument("mode", choices=("retro", "feedback"))
        parser.add_argument("--repo", required=True)
        parser.add_argument("--target")
        parser.add_argument("--period")
        parser.add_argument("--platform", action="store_true")
        parser.add_argument("--baseline", default=str(Path(__file__).resolve().parents[2] / BASELINE))
        parser.add_argument("--publish", action="store_true")
        parser.add_argument("--issue", type=int)
        parser.add_argument("--apply-label", action="store_true")
        args = parser.parse_args(argv)
        require(re.fullmatch(REPOSITORY, args.repo) and not args.repo.endswith(".git"))
        now = datetime.now(timezone.utc)
        transport = Transport()
        ledger = Ledger(transport, args.repo, now)
        if args.mode == "feedback":
            require(args.issue is not None and not args.target and not args.period and not args.platform and not args.publish)
            result = feedback(ledger, positive(args.issue, 10**10 - 1), args.apply_label)
        else:
            require(args.target and not args.issue and not args.apply_label)
            period = args.period or now.strftime("%Y-%m")
            require(re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", period))
            checkpoint = {"status": "not-requested"}
            if args.platform:
                try:
                    checkpoint = platform(transport, args.baseline)
                except (Fault, OSError, ValueError, subprocess.SubprocessError) as exc:
                    raise Fault("platform-unknown") from exc
            result, readback = observe(ledger, args.target, period, checkpoint)
            if args.publish:
                result["publication"], result["report_issue"] = publish(ledger, result, readback)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Unconfirmed:
        print("result=submission-unconfirmed; inspect the exact target before another invocation", file=sys.stderr)
        return 3
    except (Fault, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, subprocess.SubprocessError) as exc:
        print("result=platform-unknown" if isinstance(exc, Fault) and str(exc) == "platform-unknown" else "result=uncheckable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
