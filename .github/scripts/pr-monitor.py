#!/usr/bin/env python3
"""Manual bounded GET-only GitHub PR observations; no notification or actuator."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import selectors
import signal
import stat
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

PAGE_SIZE = 50
MAX_PAGES = 11
MAX_PRS = 25
MAX_CHECKS = 500
MAX_REVIEWS = 500
MAX_EXPECTED = 20
MAX_BYTES = 2097152
MAX_TOTAL_BYTES = 16777216
MAX_CALLS = 512
FILE_LIMIT = 2097152
INVOCATION_SECONDS = 120
COMMAND_SECONDS = 20
REPOSITORY = r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}"
SCHEMA = "pr-monitor-report/v1"
STATES = ("ACTION_REQUIRED", "WAITING", "NO_ACTION", "UNCONFIRMED")
UNASSESSED = ["human-approval-policy", "resolved-review-threads", "tested-latest-base",
              "workflow-identity", "merge-readiness", "permissions-and-ownership"]
FINDINGS = ("check-failed", "review-changes-requested", "checks-running", "draft")
RUNNING = ("queued", "in_progress", "pending", "waiting", "requested")
FAILURES = ("failure", "timed_out", "cancelled", "action_required", "startup_failure")
CONCLUSIONS = ("success", "neutral", "skipped", "stale", *FAILURES)
REVIEW_STATES = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING")
INTERRUPT_SIGNALS = (signal.SIGINT, signal.SIGTERM)
_cancelled = False


class Fault(ValueError):
    """Fixed CLI diagnostics, independent of raw local or external data."""


class Interrupted(Fault):
    pass


class OutputFault(Fault):
    pass


def cancel(_number, _frame):
    # Record only: raising while Popen acquires its child handle could leave an
    # unowned command. Repeated signals cannot interrupt the finally cleanup.
    global _cancelled
    _cancelled = True


def require(condition):
    if _cancelled:
        raise Interrupted("interrupted")
    if not condition:
        raise Fault("unconfirmed")


def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def parse_json(data):
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data, object_pairs_hook=unique_keys,
                          parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Fault("unconfirmed") from error


def positive(value, maximum=10**20 - 1):
    require(type(value) is int and 0 < value <= maximum)
    return value


def clean_text(value, maximum=256):
    require(isinstance(value, str) and value and value.strip() == value
            and len(value.encode("utf-8")) <= maximum
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    return value


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value))
    return value


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed <= datetime.now(timezone.utc))
        return parsed
    except ValueError as error:
        raise Fault("unconfirmed") from error


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def safe_read(path):
    """No-follow components, bounded single-link regular file and identity readback."""
    # Keep parent components until each preceding directory has passed the
    # no-follow open. Lexical abspath would erase a symlink followed by '..'
    # and could select a different file from the one the caller supplied.
    path = Path(path)
    require(path.name not in ("", ".."))
    descriptor = os.open(path.anchor or ".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[bool(path.anchor):-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                                  dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and not before.st_mode & 0o7111 and before.st_size <= FILE_LIMIT)
            data = stream.read(FILE_LIMIT + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        require(len(data) <= FILE_LIMIT and identity(before) == identity(after) == identity(current))
        return data, identity(before)
    finally:
        os.close(descriptor)


class Transport:
    def __init__(self, deadline=None):
        self.deadline = time.monotonic() + INVOCATION_SECONDS if deadline is None else deadline
        self.calls = 0
        self.total = 0

    def command(self, args):
        """Streaming bounds and owned process-group cleanup, including setup errors."""
        self.calls += 1
        require(self.calls <= MAX_CALLS and time.monotonic() < self.deadline)
        environment = dict(os.environ, GH_HOST="github.com", GH_DEBUG="",
                           GH_PROMPT_DISABLED="1", GH_PAGER="cat", PAGER="cat")
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment, start_new_session=True)
        selector = None
        try:
            require(True)
            selector = selectors.DefaultSelector()
            outputs = {process.stdout: bytearray(), process.stderr: bytearray()}
            for stream in outputs:
                selector.register(stream, selectors.EVENT_READ)
            deadline = min(self.deadline, time.monotonic() + COMMAND_SECONDS)
            size = 0
            while selector.get_map():
                require(time.monotonic() < deadline)
                for selected, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                    chunk = os.read(selected.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(selected.fileobj)
                        continue
                    size += len(chunk)
                    self.total += len(chunk)
                    require(size <= MAX_BYTES + 16384 and self.total <= MAX_TOTAL_BYTES)
                    outputs[selected.fileobj].extend(chunk)
            while process.poll() is None:
                require(time.monotonic() < deadline)
                try:
                    process.wait(timeout=min(0.1, max(0.01, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            require(process.returncode == 0)
            # stderr is consumed and bounded but never disclosed.
            outputs[process.stderr].decode("utf-8")
            return outputs[process.stdout].decode("utf-8")
        finally:
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            finally:
                try:
                    if selector is not None:
                        selector.close()
                finally:
                    process.stdout.close()
                    process.stderr.close()

    def api(self, endpoint):
        # Pinned host and method; no request body, authentication mutation or fallback.
        raw = self.command(["gh", "api", "--hostname", "github.com", "--method", "GET",
                            "--include", "-H", "Accept: application/vnd.github+json", "-H",
                            "X-GitHub-Api-Version: 2022-11-28", endpoint])
        return response(raw)


def response(raw):
    require(isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_BYTES + 16384
            and "\0" not in raw)
    separator = "\r\n\r\n" if "\r\n\r\n" in raw else "\n\n"
    header, separator, body = raw.partition(separator)
    header = header.replace("\r\n", "\n")
    require(separator and "\r" not in header and len(header.encode("utf-8")) <= 16384)
    lines = header.split("\n")
    require(re.fullmatch(r"HTTP/(?:1\.[01]|2(?:\.0)?) 200(?: [A-Za-z ]+)?", lines[0]))
    headers = {}
    for line in lines[1:]:
        key, colon, value = line.partition(":")
        require(colon and re.fullmatch(r"[A-Za-z0-9-]+", key)
                and key.lower() not in headers
                and not any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value))
        headers[key.lower()] = value.strip()
    require(headers.get("content-type", "").lower().split(";")[0].strip() == "application/json"
            and "location" not in headers and "content-encoding" not in headers
            and "transfer-encoding" not in headers)
    if "content-length" in headers:
        require(re.fullmatch(r"0|[1-9][0-9]*", headers["content-length"])
                and int(headers["content-length"]) == len(body.encode("utf-8")))
    require(len(body.encode("utf-8")) <= MAX_BYTES)
    return parse_json(body), headers


def page_links(header, endpoint, page, repo_id=None):
    links = {}
    source = urlsplit(endpoint)
    expected = parse_qs(source.query, strict_parsing=True)
    require(all(len(v) == 1 for v in expected.values()) and "page" not in expected)
    if header is None:
        return links
    require(isinstance(header, str) and header)
    for part in header.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="(next|last|first|prev)"\s*', part)
        require(match)
        url, relation = match.groups()
        require(relation not in links)
        parsed = urlsplit(url)
        allowed = ["/" + source.path]
        if repo_id is not None:
            positive(repo_id)
            allowed.append("/" + re.sub(r"^repos/[^/]+/[^/]+", "repositories/" + str(repo_id), source.path))
        require(parsed.scheme == "https" and parsed.netloc == "api.github.com"
                and parsed.path in allowed and not parsed.fragment)
        query = parse_qs(parsed.query, strict_parsing=True)
        number = query.pop("page", [])
        require(len(number) == 1 and re.fullmatch(r"[1-9][0-9]{0,3}", number[0])
                and query == expected)
        number = int(number[0])
        require((relation == "next" and number == page + 1)
                or (relation == "prev" and page > 1 and number == page - 1)
                or (relation == "first" and number == 1)
                or (relation == "last" and page <= number <= MAX_PAGES))
        links[relation] = number
    return links


class Ledger:
    def __init__(self, transport, repo):
        self.transport, self.repo = transport, repo
        self.prefix = "repos/" + repo

    def pages(self, endpoint, validator, maximum, key=None, repo_id=None):
        records, ids = [], set()
        total = last = None
        for page in range(1, MAX_PAGES + 1):
            data, headers = self.transport.api(endpoint + ("&page=" + str(page) if page > 1 else ""))
            if key:
                require(isinstance(data, dict) and type(data.get("total_count")) is int
                        and 0 <= data["total_count"] <= maximum)
                count = data["total_count"]
                require(total is None or total == count)
                total = count
                data = data.get(key)
            require(isinstance(data, list) and len(data) <= PAGE_SIZE)
            for value in data:
                row = validator(value)
                require(row["id"] not in ids)
                ids.add(row["id"])
                records.append(row)
                require(len(records) <= maximum)
            observed_repo_id = repo_id
            if observed_repo_id is None and records and "base" in records[0]:
                observed_repo_id = records[0]["base"]["repository_id"]
            links = page_links(headers.get("link"), endpoint, page, observed_repo_id)
            if "last" in links:
                require(last is None or last == links["last"])
                last = links["last"]
            if "next" not in links:
                require(len(data) < PAGE_SIZE or last == page or total == len(records))
                require(last is None or last == page)
                require(total is None or total == len(records))
                return sorted(records, key=lambda row: row["id"])
            require(last is not None and page < last and len(data) == PAGE_SIZE)
            require(total is None or len(records) < total)
        raise Fault("unconfirmed")

    def inventory(self):
        rows = self.pages(self.prefix + "/pulls?state=open&sort=created&direction=asc&per_page=50",
                          lambda value: pr_record(value, self.repo), MAX_PRS)
        require(len({row["number"] for row in rows}) == len(rows)
                and len({row["base"]["repository_id"] for row in rows}) <= 1)
        return sorted(rows, key=lambda row: row["number"])

    def detail(self, number):
        data, headers = self.transport.api(f"{self.prefix}/pulls/{number}")
        require("link" not in headers)
        row = pr_record(data, self.repo)
        require(row["number"] == number)
        return row

    def checks(self, row):
        return self.pages(f"{self.prefix}/commits/{row['head']['sha']}/check-runs?filter=latest&per_page=50",
                          lambda value: check_record(value, row["head"]["sha"], self.repo), MAX_CHECKS, "check_runs",
                          row["base"]["repository_id"])

    def reviews(self, row):
        return self.pages(f"{self.prefix}/pulls/{row['number']}/reviews?per_page=50",
                          lambda value: review_record(value, self.repo, row["number"]), MAX_REVIEWS,
                          repo_id=row["base"]["repository_id"])


def pr_record(value, repo):
    require(isinstance(value, dict) and value.get("state") == "open"
            and type(value.get("draft")) is bool)
    number = positive(value.get("number"), 10**10 - 1)
    result = {"id": positive(value.get("id")), "number": number, "draft": value["draft"],
              "updated_at": value.get("updated_at")}
    timestamp(result["updated_at"])
    require(isinstance(value.get("url"), str) and isinstance(value.get("html_url"), str)
            and value["url"].lower() == f"https://api.github.com/repos/{repo}/pulls/{number}".lower()
            and value["html_url"].lower() == f"https://github.com/{repo}/pull/{number}".lower())
    for side in ("head", "base"):
        branch = value.get(side)
        require(isinstance(branch, dict) and isinstance(branch.get("repo"), dict))
        repository = branch["repo"]
        clean_text(repository.get("full_name"), 140)
        if side == "base":
            require(repository["full_name"].lower() == repo.lower())
        result[side] = {"sha": sha(branch.get("sha")), "repository_id": positive(repository.get("id")),
                        "ref": clean_text(branch.get("ref"), 1024)}
    return result


def check_record(value, head, repo=None):
    require(isinstance(value, dict) and isinstance(value.get("app"), dict)
            and sha(value.get("head_sha")) == head)
    status, conclusion = value.get("status"), value.get("conclusion")
    require(status in (*RUNNING, "completed")
            and ((status == "completed" and conclusion in CONCLUSIONS)
                 or (status in RUNNING and conclusion is None)))
    identifier = positive(value.get("id"))
    if repo is not None:
        require(isinstance(value.get("url"), str) and value["url"].lower() ==
                f"https://api.github.com/repos/{repo}/check-runs/{identifier}".lower())
    return {"id": identifier, "name": clean_text(value.get("name")),
            "app_id": positive(value["app"].get("id")), "head_sha": head,
            "status": status, "conclusion": conclusion}


def review_record(value, repo=None, number=None):
    require(isinstance(value, dict) and isinstance(value.get("user"), dict))
    state, submitted = value.get("state"), value.get("submitted_at")
    require(state in REVIEW_STATES)
    if state == "PENDING":
        require(submitted is None)
    else:
        timestamp(submitted)
    identifier = positive(value.get("id"))
    if repo is not None:
        require(isinstance(value.get("pull_request_url"), str) and value["pull_request_url"].lower() ==
                f"https://api.github.com/repos/{repo}/pulls/{number}".lower()
                and isinstance(value.get("html_url"), str) and value["html_url"].lower() ==
                f"https://github.com/{repo}/pull/{number}#pullrequestreview-{identifier}".lower())
    return {"id": identifier, "user_id": positive(value["user"].get("id")),
            "state": state, "submitted_at": submitted, "commit_sha": sha(value.get("commit_id"))}


def selected_checks(records, expected, repo):
    require(len({(row["name"], row["app_id"]) for row in records}) == len(records))
    result = []
    for item in expected:
        matches = [row for row in records if row["name"] == item["name"]]
        require(len(matches) == 1 and matches[0]["app_id"] == item["app_id"])
        row = matches[0]
        require(row["conclusion"] not in ("neutral", "skipped", "stale"))
        result.append({key: row[key] for key in ("name", "app_id", "id", "status", "conclusion")} |
                      {"url": f"https://github.com/{repo}/runs/{row['id']}"})
    return result


def selected_reviews(records, repo, number):
    # Neutral comments cannot erase a decisive published opinion.
    users = {}
    for row in records:
        if row["state"] != "PENDING":
            users.setdefault(row["user_id"], []).append(row)
    result = []
    for user_id, rows in sorted(users.items()):
        decisive = [row for row in rows if row["state"] != "COMMENTED"]
        candidates = decisive or rows
        latest = max(timestamp(row["submitted_at"]) for row in candidates)
        selected = sorted((row for row in candidates if timestamp(row["submitted_at"]) == latest),
                          key=lambda row: row["id"])
        require(len({row["state"] for row in selected}) == 1)
        result.append({"user_id": user_id, "state": selected[0]["state"],
                       "submitted_at": selected[0]["submitted_at"],
                       "reviews": [{"id": row["id"], "commit_sha": row["commit_sha"],
                                    "url": f"https://github.com/{repo}/pull/{number}#pullrequestreview-{row['id']}"}
                                   for row in selected]})
    return result


def state_for(findings):
    require(isinstance(findings, list) and findings == [item for item in FINDINGS if item in findings])
    if "check-failed" in findings or "review-changes-requested" in findings:
        return "ACTION_REQUIRED"
    if "checks-running" in findings or "draft" in findings:
        return "WAITING"
    return "NO_ACTION"


def pr_observation(row, checks, reviews, expected, repo):
    selected = selected_checks(checks, expected, repo)
    opinions = selected_reviews(reviews, repo, row["number"])
    findings = []
    if any(check["conclusion"] in FAILURES for check in selected):
        findings.append("check-failed")
    if any(review["state"] == "CHANGES_REQUESTED" for review in opinions):
        findings.append("review-changes-requested")
    if any(check["status"] in RUNNING for check in selected):
        findings.append("checks-running")
    if row["draft"]:
        findings.append("draft")
    result = {"number": row["number"], "url": f"https://github.com/{repo}/pull/{row['number']}",
              "head": dict(row["head"]), "base": dict(row["base"]),
              "state": state_for(findings), "checks": selected, "reviews": opinions, "findings": findings}
    return result | {"fingerprint": fingerprint(result)}


def blank_report(repo, expected, unconfirmed=False):
    return {"schema": SCHEMA, "repository": repo, "expected_checks": expected,
            "state": "UNCONFIRMED" if unconfirmed else "NO_ACTION", "pull_requests": [],
            "comparison": {"status": "not-supplied", "pull_requests": [], "removed": []},
            "unassessed": UNASSESSED, "diagnostic": "observation-unconfirmed" if unconfirmed else None}


def observe(ledger, expected):
    initial = ledger.inventory()
    snapshots, result = [], []
    for inventory_row in initial:
        row = ledger.detail(inventory_row["number"])
        require(row == inventory_row)
        checks, reviews = ledger.checks(row), ledger.reviews(row)
        result.append(pr_observation(row, checks, reviews, expected, ledger.repo))
        snapshots.append((row, checks, reviews))
    # Re-read every relevant source before publication; failures discard all rows.
    for row, checks, reviews in snapshots:
        require(ledger.detail(row["number"]) == row)
        require(ledger.checks(row) == checks)
        require(ledger.reviews(row) == reviews)
    require(ledger.inventory() == initial)
    report = blank_report(ledger.repo, expected)
    report["pull_requests"] = result
    report["state"] = ("ACTION_REQUIRED" if any(row["state"] == "ACTION_REQUIRED" for row in result)
                       else "WAITING" if any(row["state"] == "WAITING" for row in result) else "NO_ACTION")
    return report


def closed(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys))


def previous_report(data, repo, expected):
    """Closed generated schema and repository/check contract; no foreign comparisons."""
    value = parse_json(data)
    closed(value, ("schema", "repository", "expected_checks", "state", "pull_requests",
                   "comparison", "unassessed", "diagnostic"))
    require(value["schema"] == SCHEMA and value["repository"] == repo
            and value["expected_checks"] == expected and value["unassessed"] == UNASSESSED
            and value["diagnostic"] is None and value["state"] in STATES[:3])
    require(isinstance(value["expected_checks"], list))
    for item in value["expected_checks"]:
        closed(item, ("name", "app_id"))
        clean_text(item["name"], 100)
        positive(item["app_id"])
    rows = value["pull_requests"]
    require(isinstance(rows, list) and len(rows) <= MAX_PRS)
    numbers = []
    for row in rows:
        closed(row, ("number", "url", "head", "base", "state", "checks", "reviews", "findings", "fingerprint"))
        number = positive(row["number"], 10**10 - 1)
        numbers.append(number)
        require(row["url"] == f"https://github.com/{repo}/pull/{number}")
        for side in ("head", "base"):
            closed(row[side], ("sha", "repository_id", "ref"))
            sha(row[side]["sha"])
            positive(row[side]["repository_id"])
            clean_text(row[side]["ref"], 1024)
        require(isinstance(row["checks"], list) and len(row["checks"]) == len(expected))
        ids = set()
        for check, item in zip(row["checks"], expected):
            closed(check, ("name", "app_id", "id", "status", "conclusion", "url"))
            require(check["name"] == item["name"] and type(check["app_id"]) is int
                    and check["app_id"] == item["app_id"])
            identifier = positive(check["id"])
            require(identifier not in ids and check["url"] == f"https://github.com/{repo}/runs/{identifier}")
            ids.add(identifier)
            check_record({"id": identifier, "name": check["name"], "app": {"id": check["app_id"]},
                          "head_sha": row["head"]["sha"], "status": check["status"],
                          "conclusion": check["conclusion"]}, row["head"]["sha"])
            require(check["conclusion"] not in ("neutral", "skipped", "stale"))
        require(isinstance(row["reviews"], list) and len(row["reviews"]) <= MAX_REVIEWS)
        users, review_ids = [], set()
        for review in row["reviews"]:
            closed(review, ("user_id", "state", "submitted_at", "reviews"))
            users.append(positive(review["user_id"]))
            require(review["state"] in REVIEW_STATES[:-1])
            timestamp(review["submitted_at"])
            require(isinstance(review["reviews"], list) and 0 < len(review["reviews"]) <= MAX_REVIEWS)
            selected_ids = []
            for selected in review["reviews"]:
                closed(selected, ("id", "commit_sha", "url"))
                identifier = positive(selected["id"])
                sha(selected["commit_sha"])
                require(identifier not in review_ids and selected["url"] ==
                        f"https://github.com/{repo}/pull/{number}#pullrequestreview-{identifier}")
                review_ids.add(identifier)
                selected_ids.append(identifier)
            require(selected_ids == sorted(selected_ids))
        require(users == sorted(set(users)) and len(review_ids) <= MAX_REVIEWS)
        require(isinstance(row["findings"], list))
        state_for(row["findings"])
        findings = []
        if any(check["conclusion"] in FAILURES for check in row["checks"]):
            findings.append("check-failed")
        if any(review["state"] == "CHANGES_REQUESTED" for review in row["reviews"]):
            findings.append("review-changes-requested")
        if any(check["status"] in RUNNING for check in row["checks"]):
            findings.append("checks-running")
        # Draft is an explicit observation; it cannot imply acceptance.
        if "draft" in row["findings"]:
            findings.append("draft")
        require(row["findings"] == findings and row["state"] == state_for(findings))
        require(row["fingerprint"] == fingerprint({key: item for key, item in row.items() if key != "fingerprint"}))
    require(numbers == sorted(set(numbers)))
    aggregate = ("ACTION_REQUIRED" if any(row["state"] == "ACTION_REQUIRED" for row in rows)
                 else "WAITING" if any(row["state"] == "WAITING" for row in rows) else "NO_ACTION")
    require(value["state"] == aggregate)
    comparison = value["comparison"]
    closed(comparison, ("status", "pull_requests", "removed"))
    require(comparison["status"] in ("not-supplied", "compared"))
    require(isinstance(comparison["pull_requests"], list) and isinstance(comparison["removed"], list))
    if comparison["status"] == "not-supplied":
        require(not comparison["pull_requests"] and not comparison["removed"])
    else:
        compared = []
        for item in comparison["pull_requests"]:
            closed(item, ("number", "indicator"))
            compared.append(positive(item["number"], 10**10 - 1))
            require(item["indicator"] in ("unchanged", "changed", "new", "observed-recovery"))
        require(compared == numbers)
    removed = []
    for item in comparison["removed"]:
        closed(item, ("number", "url", "indicator"))
        number = positive(item["number"], 10**10 - 1)
        removed.append(number)
        require(number not in numbers and item["indicator"] == "removed-from-open-inventory"
                and item["url"] == f"https://github.com/{repo}/pull/{number}")
    require(removed == sorted(set(removed)) and len(removed) <= MAX_PRS)
    return value


def compare(report, previous):
    old = {row["number"]: row for row in previous["pull_requests"]}
    current = {row["number"]: row for row in report["pull_requests"]}
    rows = []
    for number, row in current.items():
        prior = old.get(number)
        indicator = ("new" if prior is None else "unchanged" if row["fingerprint"] == prior["fingerprint"]
                     else "observed-recovery" if prior["state"] == "ACTION_REQUIRED"
                     and row["state"] == "NO_ACTION" and row["head"] == prior["head"]
                     and row["base"] == prior["base"] else "changed")
        rows.append({"number": number, "indicator": indicator})
    report["comparison"] = {"status": "compared", "pull_requests": rows,
                            "removed": [{"number": number, "url": old[number]["url"],
                                         "indicator": "removed-from-open-inventory"}
                                               for number in sorted(old.keys() - current.keys())]}


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Fault("invalid-input")

    def _print_message(self, message, file=None):
        if message:
            publish(message, file or sys.stderr, self.deadline)

    def print_help(self, file=None):
        publish(self.format_help(), sys.stdout if file is None else file, self.deadline)


def arguments(argv, deadline=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.deadline = time.monotonic() + INVOCATION_SECONDS if deadline is None else deadline
    parser.add_argument("--repo", required=True)
    parser.add_argument("--check", action="append", required=True, metavar="NAME=APP_ID")
    parser.add_argument("--previous")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    require(re.fullmatch(REPOSITORY, args.repo) and args.repo.split("/")[1] not in (".", "..")
            and 0 < len(args.check) <= MAX_EXPECTED and os.name == "posix")
    expected = []
    for specification in args.check:
        name, separator, app = specification.rpartition("=")
        clean_text(name, 100)
        require(separator and re.fullmatch(r"[1-9][0-9]{0,19}", app))
        expected.append({"name": name, "app_id": positive(int(app))})
    require(len({item["name"] for item in expected}) == len(expected))
    return args, sorted(expected, key=lambda item: (item["name"], item["app_id"]))


def render(report, style):
    if style == "json":
        return canonical(report).decode("ascii") + "\n"
    lines = ["PR monitor: " + report["state"], "Repository: " + report["repository"]]
    if report["state"] == "UNCONFIRMED":
        lines.append("Observation unconfirmed; no PR queue published.")
    for row in report["pull_requests"]:
        lines.append(f"PR {row['number']}: {row['state']} {row['url']}")
        lines.append("Head: " + row["head"]["sha"] + "  Observed base: " + row["base"]["sha"])
    for row in report["comparison"]["pull_requests"]:
        lines.append(f"PR {row['number']}: {row['indicator']}")
    for row in report["comparison"]["removed"]:
        lines.append(f"PR {row['number']}: removed-from-open-inventory {row['url']}")
    lines.append("Unassessed: " + ", ".join(UNASSESSED))
    return "\n".join(lines) + "\n"


def output_checkpoint(deadline, allow_cancelled=False):
    if _cancelled and not allow_cancelled:
        raise Interrupted("interrupted")
    if time.monotonic() >= deadline:
        raise OutputFault("output-unavailable")


def publish(text, stream, deadline, *, allow_cancelled=False, immediate=False):
    """Unbuffered publication with owned writer cleanup and a shared deadline.

    A child owns potentially blocking writes, including regular files and TTYs;
    the parent keeps cancellation and deadline control without changing their
    shared descriptor flags. No child emits Python diagnostics or flushes at exit.
    Already unsuccessful reports/diagnostics use one nonblocking attempt instead.
    """
    try:
        data = text.encode("utf-8")
        if len(data) > FILE_LIMIT:
            raise OutputFault("output-unavailable")
        if not immediate:
            output_checkpoint(deadline, allow_cancelled)
        if isinstance(stream, io.StringIO):
            stream.write(text)
            if not immediate:
                output_checkpoint(deadline, allow_cancelled)
            return
        descriptor = stream.fileno()
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        try:
            if immediate and not stat.S_ISREG(os.fstat(descriptor).st_mode):
                fcntl.fcntl(descriptor, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                if os.write(descriptor, data) != len(data):
                    raise OutputFault("output-unavailable")
                return
            output_checkpoint(deadline, allow_cancelled)
            pid = os.fork()
            if pid == 0:
                try:
                    os.setsid()
                    offset = 0
                    while offset < len(data):
                        try:
                            size = os.write(descriptor, data[offset:offset + 65536])
                            if size <= 0:
                                os._exit(1)
                            offset += size
                        except BlockingIOError:
                            select.select([], [descriptor], [], 0.1)
                    os._exit(0)
                except BaseException:
                    os._exit(1)
            reaped = False
            try:
                while True:
                    output_checkpoint(deadline, allow_cancelled)
                    try:
                        child, status = os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError as error:
                        # An externally reaped child is no longer ours to kill.
                        reaped = True
                        raise OutputFault("output-unavailable") from error
                    if child:
                        reaped = True
                        if status != 0:
                            raise OutputFault("output-unavailable")
                        output_checkpoint(deadline, allow_cancelled)
                        return
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            finally:
                if not reaped:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        os.waitpid(pid, 0)
                    except ChildProcessError:
                        pass
        finally:
            current = fcntl.fcntl(descriptor, fcntl.F_GETFL)
            fcntl.fcntl(descriptor, fcntl.F_SETFL,
                        (current & ~os.O_NONBLOCK) | (flags & os.O_NONBLOCK))
    except (OSError, ValueError, TypeError, UnicodeError, AttributeError) as error:
        if isinstance(error, Fault):
            raise
        raise OutputFault("output-unavailable") from error


def diagnostic(message, deadline):
    # A full or closed stderr cannot turn a fixed diagnostic into another hang.
    try:
        publish("pr-monitor: " + message + "\n", sys.stderr, deadline,
                allow_cancelled=True, immediate=True)
    except OutputFault:
        pass


def run(argv=None, deadline=None):
    transport = Transport(deadline)
    try:
        args, expected = arguments(argv, transport.deadline)
        previous = previous_bytes = previous_identity = None
        if args.previous is not None:
            previous_bytes, previous_identity = safe_read(args.previous)
            previous = previous_report(previous_bytes, args.repo, expected)
    except (Interrupted, OutputFault):
        raise
    except (Fault, OSError, UnicodeError, TypeError, RecursionError):
        diagnostic("invalid input or previous report", transport.deadline)
        return 2
    try:
        report = observe(Ledger(transport, args.repo), expected)
        if previous is not None:
            compare(report, previous)
            data, current_identity = safe_read(args.previous)
            require(data == previous_bytes and current_identity == previous_identity)
        output = render(report, args.format)
        require(len(output.encode("utf-8")) <= FILE_LIMIT)
    except (Fault, OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError,
            subprocess.SubprocessError):
        publish(render(blank_report(args.repo, expected, True), args.format), sys.stdout,
                transport.deadline, allow_cancelled=True, immediate=True)
        diagnostic("observation unconfirmed", transport.deadline)
        return 1
    publish(output, sys.stdout, transport.deadline)
    return 0


def main(argv=None):
    global _cancelled
    original_cancelled = _cancelled
    handlers = {}
    _cancelled = False
    deadline = time.monotonic() + INVOCATION_SECONDS
    try:
        for number in INTERRUPT_SIGNALS:
            handlers[number] = signal.signal(number, cancel)
        result = run(argv, deadline)
        if result == 0:
            output_checkpoint(deadline)
        return result
    except (Interrupted, KeyboardInterrupt):
        diagnostic("observation interrupted", deadline)
        return 1
    except OutputFault:
        diagnostic("output unavailable", deadline)
        return 1
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        _cancelled = original_cancelled


if __name__ == "__main__":
    sys.exit(main())
