#!/usr/bin/env python3
"""Opt-in metadata CI; selective Copilot source reuse, strict Codex controls."""
from datetime import datetime
import argparse
import base64
import hashlib
import selectors
import shutil
import stat
import time
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

CONTEXTS = ()
WORKFLOW = ""
PR = os.environ.get("PR_NUMBER", "?")
HEAD = os.environ.get("PR_HEAD_SHA", "?")
REPO = os.environ.get("GH_REPO", "")
PREFIX = "repos/" + REPO
diagnostic = {"retarget": "?", "context": "-", "run": "-", "attempt": "-"}


class Fault(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code


def need(condition, reason, code=2):
    if not condition:
        raise Fault(code, reason)


def obj(value, label):
    need(isinstance(value, dict), "schema: expected object for " + label)
    return value


def array(value, label):
    need(isinstance(value, list), "schema: expected array for " + label)
    return value


def ident(value, label):
    need(type(value) is int and value > 0, "identity: invalid " + label)
    return value


def text(value, label):
    need(isinstance(value, str) and value.strip() == value and value
         and not any(ord(c) < 32 or ord(c) == 127 for c in value),
         "identity: invalid " + label)
    return value


def sha(value, label):
    need(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
         "identity: invalid " + label)
    return value


def stamp(value):
    need(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", value),
        "timestamp: expected valid UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Fault(2, "timestamp: invalid calendar value") from error


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "schema: duplicate JSON key")
        result[key] = value
    return result


def bad_constant(_value):
    raise Fault(2, "schema: non-finite JSON number")


def decode(value):
    try:
        return json.loads(value, object_pairs_hook=unique_object, parse_constant=bad_constant)
    except (ValueError, UnicodeError) as error:
        raise Fault(2, "schema: malformed JSON") from error


def api_failure(detail):
    status = re.search(r"\bHTTP(?:/\S+)?\s+([0-9]{3})\b", detail)
    if status:
        number = status.group(1)
        if number == "401":
            return "API authentication failure (HTTP 401)"
        if number == "403":
            return "API permission/access refusal (HTTP 403)"
        return "API HTTP failure (" + number + ")"
    return "API transport/CLI read failure"


def get(endpoint):
    try:
        result = bounded_command(
            ["gh", "api", "--method", "GET", "--include", "-H",
             "Accept: application/vnd.github+json", "-H",
             "X-GitHub-Api-Version: 2022-11-28", endpoint])
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise Fault(2, "API: read unavailable or timed out for " + endpoint) from error
    need(result.returncode == 0,
         api_failure(result.stderr + "\n" + result.stdout) + "; cannot verify " + endpoint)
    header, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    lines = header.splitlines()
    need(separator and lines, "API: missing HTTP response framing for " + endpoint)
    need(re.fullmatch(r"HTTP/\S+ 200(?: .*)?", lines[0]),
         api_failure(lines[0]) + "; invalid response for " + endpoint)
    headers = {}
    for line in lines[1:]:
        key, colon, value = line.partition(":")
        key = key.lower()
        need(colon and key not in headers, "API: malformed or duplicate response header")
        headers[key] = value.strip()
    need(headers.get("content-type", "").split(";")[0] == "application/json",
         "API: response is not JSON")
    return decode(body), headers


def page_links(header, endpoint, page, repo_id):
    links = {}
    source = urlsplit(endpoint)
    expected_query = parse_qs(source.query, strict_parsing=True)
    if not header:
        return links
    for part in header.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="(next|last|first|prev)"\s*', part)
        need(match, "pagination: malformed Link header")
        url, relation = match.groups()
        need(relation not in links, "pagination: duplicate Link relation")
        try:
            parsed = urlsplit(url)
        except ValueError as error:
            raise Fault(2, "pagination: malformed Link URL") from error
        allowed = ("/" + source.path,
                   "/" + source.path.replace(PREFIX, f"repositories/{repo_id}", 1))
        need(parsed.scheme == "https" and parsed.netloc == "api.github.com"
             and not parsed.fragment and parsed.path in allowed,
             "pagination: foreign host or wrong resource Link")
        try:
            query = parse_qs(parsed.query, strict_parsing=True)
        except ValueError as error:
            raise Fault(2, "pagination: malformed Link query") from error
        number = query.pop("page", [])
        need(len(number) == 1 and re.fullmatch(r"[1-9][0-9]*", number[0])
             and query == expected_query, "pagination: wrong Link query")
        number = int(number[0])
        need((relation == "next" and number == page + 1)
             or (relation == "prev" and page > 1 and number == page - 1)
             or (relation == "first" and number == 1)
             or (relation == "last" and number >= page),
             "pagination: inconsistent page sequence")
        links[relation] = number
    return links


def listing(endpoint, repo_id, key=None):
    records, ids = [], set()
    total = last = None
    for page in range(1, 21):
        target = endpoint if page == 1 else endpoint + "&page=" + str(page)
        data, headers = get(target)
        if key:
            data = obj(data, endpoint)
            count = data.get("total_count")
            need(type(count) is int and 0 <= count <= 2000, "pagination: invalid total_count")
            need(key != "workflow_runs" or count < 1000, "pagination: Actions cap reached")
            need(total is None or count == total, "pagination: total_count changed")
            total = count
            data = data.get(key)
        items = array(data, endpoint)
        need(len(items) <= 100, "pagination: oversized page")
        for item in items:
            obj(item, "page record")
            # Non-retarget timeline kinds need not carry a numeric event ID.
            value = item.get("id")
            if key:
                ident(value, key + " record")
            if type(value) is int:
                need(value not in ids, "pagination: duplicate record ID")
                ids.add(value)
            records.append(item)
        links = page_links(headers.get("link"), endpoint, page, repo_id)
        if "last" in links:
            need(last is None or last == links["last"], "pagination: last page changed")
            last = links["last"]
        if "next" not in links:
            need(len(items) < 100 or last == page or total == len(records),
                 "pagination: full terminal page lacks completeness evidence")
            need(last is None or last == page, "pagination: missing next page")
            need(total is None or len(records) == total, "pagination: count mismatch")
            return records
        need(last is not None and page < last, "pagination: missing terminal boundary")
        need(total is None or len(records) < total, "pagination: continuation past count")
    raise Fault(2, "pagination: bounded page limit reached; history uncheckable")


def repository(value):
    return ident(obj(value, "repository").get("id"), "repository ID")


def pr_identity(value):
    value = obj(value, "PR")
    head = obj(value.get("head"), "PR head")
    base = obj(value.get("base"), "PR base")
    base_repo = obj(base.get("repo"), "base repository")
    need(text(base_repo.get("full_name"), "base repository name").lower() == REPO.lower(),
         "identity: PR base repository name differs")
    base_sha = sha(base.get("sha"), "current base SHA")
    return (ident(value.get("number"), "PR number"), sha(head.get("sha"), "PR head SHA"),
            repository(head.get("repo")), repository(base_repo), text(base.get("ref"), "base ref"), base_sha)


def history(repo_id):
    events = listing(f"{PREFIX}/issues/{PR}/timeline?per_page=100", repo_id)
    retargets = []
    for event in events:
        need(isinstance(event.get("event"), str), "schema: missing timeline event kind")
        if event["event"] == "base_ref_changed":
            retargets.append((ident(event.get("id"), "retarget ID"), stamp(event.get("created_at"))))
    return tuple(sorted(retargets))


def trigger(identity):
    need(os.environ.get("GITHUB_EVENT_NAME") == "pull_request", "identity: unsupported trigger")
    try:
        event_path = Path(os.environ["GITHUB_EVENT_PATH"])
        event = obj(decode(read_file(safe_root(event_path.parent), event_path.name)), "event")
    except (KeyError, OSError, UnicodeError) as error:
        raise Fault(2, "identity: event payload unavailable") from error
    need(event.get("action") in ("opened", "synchronize", "reopened", "edited"),
         "identity: unexpected PR action")
    need(event.get("number") == int(PR) and pr_identity(event.get("pull_request")) == identity
         and repository(event.get("repository")) == identity[3],
         "identity: event and current PR disagree")
    changes = obj(event.get("changes", {}), "event changes")
    if event["action"] == "edited" and "base" in changes:
        base = changes["base"]
        need(isinstance(base, dict) and base
             and all(key in ("ref", "sha") and isinstance(value, dict)
                     and isinstance(value.get("from"), str) and value["from"]
                     for key, value in base.items()), "identity: malformed changes.base")
        return stamp(event["pull_request"].get("updated_at"))
    return None


RUN_FIELDS = ("id", "workflow_id", "path", "event", "head_sha", "check_suite_id",
              "run_attempt", "created_at", "run_started_at", "status", "conclusion", "pull_requests")
JOB_FIELDS = ("id", "name", "head_sha", "run_id", "run_attempt", "check_run_url",
              "status", "conclusion", "started_at", "completed_at")
CHECK_FIELDS = ("id", "name", "head_sha", "check_suite", "app",
                "status", "conclusion", "started_at", "completed_at")


def project(value, fields):
    value = obj(value, "evidence")
    return {key: value.get(key) for key in fields}


def descriptor():
    value = obj(get(PREFIX + "/actions/workflows/" + WORKFLOW.rsplit("/", 1)[1])[0], "workflow")
    need(value.get("path") == WORKFLOW, "identity: configured workflow descriptor path differs")
    return ident(value.get("id"), "workflow ID")


def candidates(runs, workflow_id, identity):
    result = []
    for run in runs:
        if sha(run.get("head_sha"), "run head") != HEAD:
            continue
        same_id = ident(run.get("workflow_id"), "run workflow") == workflow_id
        same_path = text(run.get("path"), "run path") == WORKFLOW
        need(same_id == same_path, "identity: workflow ID/path disagreement")
        if not same_id or text(run.get("event"), "run event") != "pull_request":
            continue
        diagnostic.update(run=run["id"], attempt=run.get("run_attempt", "?"))
        association = array(run.get("pull_requests"), "run PR association identity")
        need(association, "identity: empty PR association")
        matches = []
        for entry in association:
            entry = obj(entry, "PR association")
            number = ident(entry.get("number"), "associated PR number")
            head = obj(entry.get("head"), "associated head")
            base = obj(entry.get("base"), "associated base")
            head_sha = sha(head.get("sha"), "associated head SHA")
            head_repo = repository(head.get("repo"))
            base_repo = repository(base.get("repo"))
            base_ref = text(base.get("ref"), "associated base ref")
            sha(base.get("sha"), "associated base SHA")
            if number == int(PR):
                need(head_sha == HEAD and head_repo == identity[2],
                     "identity: associated PR head/repository mismatch")
                matches.append((base_repo, base_ref))
        if not matches:
            continue
        need(len(matches) == 1, "identity: ambiguous PR association")
        ident(run.get("check_suite_id"), "check suite")
        ident(run.get("run_attempt"), "current attempt")
        result.append((stamp(run.get("created_at")), run, matches[0]))
    need(result, "missing attributable current-head code run", 1)
    latest = max(item[0] for item in result)
    selected = [item for item in result if item[0] == latest]
    need(len(selected) == 1, "identity: ambiguous latest original creation timestamp")
    return selected[0]


def required_jobs(jobs):
    selected = {}
    for context in CONTEXTS:
        diagnostic["context"] = context
        matching = [job for job in jobs if job.get("name") == context]
        need(len(matching) == 1, "missing or duplicate required context in current attempt", 1)
        selected[context] = matching[0]
    return selected


def checks_for(jobs, run, created, started, boundary):
    checks = {}
    for context, job in jobs.items():
        diagnostic["context"] = context
        need(ident(job.get("run_id"), "job run ID") == run["id"]
             and ident(job.get("run_attempt"), "job attempt") == run["run_attempt"]
             and job.get("head_sha") == HEAD, "identity: job run/attempt/head mismatch")
        url = job.get("check_run_url")
        match = re.fullmatch(
            r"https://api\.github\.com/" + re.escape(PREFIX) + r"/check-runs/([1-9][0-9]*)",
            url if isinstance(url, str) else "")
        need(match, "identity: check_run_url is not a local direct check ID")
        check_id = int(match.group(1))
        check = obj(get(f"{PREFIX}/check-runs/{check_id}")[0], "check run")
        need(ident(check.get("id"), "check ID") == check_id
             and check.get("name") == context and check.get("head_sha") == HEAD
             and ident(obj(check.get("check_suite"), "check suite").get("id"), "suite ID")
             == run["check_suite_id"]
             and ident(obj(check.get("app"), "check App").get("id"), "App ID") == 15368
             and check["app"].get("slug") == "github-actions",
             "identity: check name/head/suite/issuer mismatch")
        for field in ("status", "conclusion", "started_at", "completed_at"):
            need(job.get(field) == check.get(field), "identity: job/check " + field + " mismatch")
        need(check.get("status") in ("queued", "in_progress", "completed", "pending", "waiting", "requested")
             and check.get("conclusion") in (None, "success", "failure", "cancelled", "skipped",
                                             "neutral", "timed_out", "action_required", "stale",
                                             "startup_failure"), "schema: invalid check status/conclusion")
        need(check.get("status") == "completed" and check.get("conclusion") == "success",
             "non-success required context (incomplete/failed checks cannot qualify)", 1)
        check_start = stamp(check.get("started_at"))
        check_end = stamp(check.get("completed_at"))
        need(check_start > boundary and check_end > boundary, "stale required context", 1)
        need(created <= started <= check_start <= check_end, "timestamp: check chronology invalid")
        checks[context] = (check_id, project(check, CHECK_FIELDS))
    return checks


def stable(condition):
    need(condition, "unstable snapshot; evidence changed during reads", 1)


def freshness():
    need(re.fullmatch(r"[1-9][0-9]*", PR), "identity: invalid PR_NUMBER")
    sha(HEAD, "PR_HEAD_SHA")
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", REPO)
         and REPO.split("/")[-1] not in (".", ".."), "identity: invalid GH_REPO")
    need(os.environ.get("GH_HOST", "github.com") == "github.com"
         and os.environ.get("GITHUB_API_URL", "https://api.github.com") == "https://api.github.com",
         "issuer: unsupported host; separately reviewed adaptation required")
    identity = pr_identity(get(f"{PREFIX}/pulls/{PR}")[0])
    need(identity[0] == int(PR) and identity[1] == HEAD, "identity: current PR/head mismatch")
    veto_time = trigger(identity)
    repo_id = identity[3]
    retargets = history(repo_id)
    if retargets:
        boundary = max(value for _, value in retargets)
        diagnostic["retarget"] = ",".join(
            str(event_id) for event_id, value in retargets if value == boundary) + "@" + boundary.isoformat()
    else:
        boundary = None
        diagnostic["retarget"] = "none"
    need(veto_time is None or (boundary is not None and boundary >= veto_time),
         "edited base retarget not yet visible in timeline", 1)
    if boundary is None:
        stable(pr_identity(get(f"{PREFIX}/pulls/{PR}")[0]) == identity)
        stable(history(repo_id) == retargets)
        return "NO_RETARGET: code verification remains independently required"

    workflow_id = descriptor()
    run_endpoint = PREFIX + "/actions/runs?" + urlencode({"head_sha": HEAD, "per_page": 100})
    runs = listing(run_endpoint, repo_id, "workflow_runs")
    created, selected, associated_base = candidates(runs, workflow_id, identity)
    diagnostic.update(run=selected["id"], attempt=selected["run_attempt"])
    need(associated_base == identity[3:5], "selected run base mismatch", 1)
    need(created > boundary, "stale original run; new original code verification required", 1)
    run_path = f"{PREFIX}/actions/runs/{selected['id']}"
    current = obj(get(run_path)[0], "selected run")
    need(ident(current.get("id"), "selected run ID") == selected["id"],
         "identity: selected run ID mismatch")
    stable(project(current, RUN_FIELDS) == project(selected, RUN_FIELDS))
    need(current.get("status") in ("queued", "in_progress", "completed", "pending", "waiting", "requested"),
         "schema: invalid run status")
    need(current.get("status") == "completed", "non-success run is incomplete", 1)
    started = stamp(selected.get("run_started_at"))
    need(started >= created, "timestamp: run starts before original creation")
    job_path = run_path + f"/attempts/{selected['run_attempt']}/jobs?per_page=100"
    jobs = required_jobs(listing(job_path, repo_id, "jobs"))
    checks = checks_for(jobs, selected, created, started, boundary)

    # Compare the observed evidence, not a success-filtered replacement snapshot.
    diagnostic["context"] = "-"
    stable(pr_identity(get(f"{PREFIX}/pulls/{PR}")[0]) == identity)
    stable(history(repo_id) == retargets)
    stable(descriptor() == workflow_id)
    reread = listing(run_endpoint, repo_id, "workflow_runs")
    stable(sorted((project(run, RUN_FIELDS) for run in reread), key=lambda run: run["id"])
           == sorted((project(run, RUN_FIELDS) for run in runs), key=lambda run: run["id"]))
    stable(project(get(run_path)[0], RUN_FIELDS) == project(current, RUN_FIELDS))
    again = required_jobs(listing(job_path, repo_id, "jobs"))
    stable({key: project(job, JOB_FIELDS) for key, job in again.items()}
           == {key: project(job, JOB_FIELDS) for key, job in jobs.items()})
    for context, (check_id, check) in checks.items():
        diagnostic["context"] = context
        stable(project(get(f"{PREFIX}/check-runs/{check_id}")[0], CHECK_FIELDS) == check)
    diagnostic["context"] = ",".join(CONTEXTS)
    return "FRESH: all required current-head contexts verified after retarget"


METADATA_SHA256 = "af89c249a185a57c453c6de0d2822d2899c8389035d457ddeb85c5abce773cd0"

# The protocol is deliberately a small workflow subset, not a YAML interpreter.
CONFIG = ".github/adopter-ci.json"
META = ".github/workflows/task-ritual.yml"
SELF = ".github/scripts/check-adopter-ci.py"
RITUAL = ".github/scripts/check-task-ritual.sh"
RITUAL_SHA256 = "8c4fe064337534106f9636de5bdf4379a05a6ed0a9a5a08eb84dcffced6076f2"
CONTROLS = ["metadata-workflow", "sensor", "installed-ritual", "code-events",
            "code-producers", "cancellation-isolation", "retarget-freshness"]
MAX_BYTES = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_command(args, *, cwd=None, env=None):
    """Bound both pipe streams and wall time without writing logs to disk."""
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    streams = selectors.DefaultSelector()
    outputs = {process.stdout: bytearray(), process.stderr: bytearray()}
    for stream in outputs:
        streams.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + 30
    size = 0
    try:
        while streams.get_map():
            need(time.monotonic() < deadline, "command timed out")
            for selected, _ in streams.select(timeout=0.2):
                chunk = os.read(selected.fileobj.fileno(), 65536)
                if not chunk:
                    streams.unregister(selected.fileobj)
                    continue
                size += len(chunk)
                need(size <= 2 * MAX_BYTES, "command response exceeds resource bound")
                outputs[selected.fileobj].extend(chunk)
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return subprocess.CompletedProcess(args, process.returncode,
            outputs[process.stdout].decode("utf-8"), outputs[process.stderr].decode("utf-8"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        streams.close()
        for stream in outputs:
            stream.close()


def relative(value):
    need(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value)
         and all(part not in (".", "..") for part in value.split("/")),
         "unsafe relative path")
    return value


def safe_root(root):
    root = Path(os.path.abspath(root))
    need(root.is_dir() and not root.is_symlink(), "target is not a regular directory")
    for parent in root.parents:
        need(not parent.is_symlink(), "target has a symlink parent")
    return root


def safe_path(root, path):
    current = safe_root(root)
    for part in relative(path).split("/"):
        current = current / part
        need(not current.is_symlink(), "guarded path has a symlink")
        if current != root / path and current.exists():
            need(current.is_dir(), "guarded parent is not a directory")
    return current


def open_parent(root, path):
    parts = relative(path).split("/")
    descriptor = os.open(safe_root(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except Exception:
        os.close(descriptor)
        raise


def read_file(root, path):
    path = safe_path(root, path)
    parent, name = open_parent(root, str(path.relative_to(root)))
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        need(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o7111
             and info.st_nlink == 1 and info.st_size <= MAX_BYTES, "unsafe guarded file")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            data = os.read(fd, MAX_BYTES + 1)
            after = os.fstat(fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(len(data) == info.st_size and len(data) <= MAX_BYTES and identity(info) == identity(before) == identity(after)
         == identity(path.lstat()), "guarded file changed while reading")
    return data


def scalar(value):
    if value == "{}":
        return {}
    if value.startswith("[") and value.endswith("]"):
        members = value[1:-1].split(",")
        need(all(re.fullmatch(r"\s*[A-Za-z0-9_-]+\s*", x) for x in members),
             "unsupported workflow flow value")
        return [x.strip() for x in members]
    if value.startswith('"'):
        result = decode(value)
        need(isinstance(result, str), "unsupported workflow scalar")
        return result
    if value.startswith("'"):
        need(value.endswith("'") and "'" not in value[1:-1], "unsupported workflow quote")
        return value[1:-1]
    need(value and value[0] not in "{}[]&*!>|%@" and ": " not in value
         and not value.endswith(":") and " #" not in value,
         "unsupported workflow scalar or inline comment")
    return value


def workflow_subset(data):
    """Indentation maps, step sequences, literal blocks, simple scalar/flow lists.

    Reject aliases, merge keys, tags, folding, duplicate keys and ambiguous syntax.
    Literal run bodies are data and cannot manufacture a structural guard.
    """
    text_data = data.decode("utf-8")
    need("\t" not in text_data and "\r" not in text_data and "\x00" not in text_data,
         "unsupported workflow whitespace")
    lines = text_data.splitlines()
    position = 0

    def skip():
        nonlocal position
        while position < len(lines) and (not lines[position].strip()
                                         or lines[position].lstrip().startswith("#")):
            position += 1

    def mapping(indent):
        nonlocal position
        result = {}
        while True:
            skip()
            if position >= len(lines):
                return result
            line = lines[position]
            actual = len(line) - len(line.lstrip(" "))
            if actual < indent:
                return result
            need(actual == indent, "unsupported workflow indentation")
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?: (.*))?", line[indent:])
            need(match, "unsupported workflow mapping")
            key, value = match.groups()
            need(key not in result, "duplicate workflow key")
            position += 1
            if value in ("|", "|-"):
                body = []
                while position < len(lines):
                    row = lines[position]
                    if row.strip() and len(row) - len(row.lstrip(" ")) <= indent:
                        break
                    need(not row.strip() or row.startswith(" " * (indent + 2)),
                         "unsupported literal indentation")
                    body.append(row[indent + 2:])
                    position += 1
                need(body, "empty workflow literal")
                result[key] = "\n".join(body)
            elif value is not None:
                result[key] = scalar(value)
            else:
                skip()
                need(position < len(lines), "empty workflow mapping")
                if lines[position].startswith(" " * (indent + 2) + "- "):
                    result[key] = sequence(indent + 2)
                else:
                    result[key] = mapping(indent + 2)
                need(result[key], "empty workflow mapping")

    def sequence(indent):
        nonlocal position
        result = []
        while True:
            skip()
            if position >= len(lines) or not lines[position].startswith(" " * indent + "- "):
                return result
            # Expand a mapping-item marker in memory; never touch the file.
            lines[position] = " " * (indent + 2) + lines[position][indent + 2:]
            result.append(mapping(indent + 2))
            need(len(result) <= 100, "too many workflow steps")

    result = mapping(0)
    skip()
    need(position == len(lines), "trailing unsupported workflow content")
    return result


def code_contract(data, checks):
    workflow = workflow_subset(data)
    need(set(workflow) == {"name", "on", "permissions", "concurrency", "jobs"},
         "unsupported application workflow top-level keys")
    need(isinstance(workflow["name"], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,99}", workflow["name"])
         and workflow["name"] != "Adopter Task metadata", "unsupported or duplicate workflow name")
    need(workflow["on"] == {"pull_request": {"types": ["opened", "synchronize", "reopened"]}},
         "application events require explicit opened/synchronize/reopened only")
    need(workflow["permissions"] == {"contents": "read"}, "application grants must be contents read")
    concurrency = workflow["concurrency"]
    need(isinstance(concurrency, dict) and set(concurrency) == {"group", "cancel-in-progress"}
         and concurrency["cancel-in-progress"] == "true", "unsupported application concurrency")
    group = concurrency["group"]
    need(isinstance(group, str) and re.fullmatch(
         r"[A-Za-z][A-Za-z0-9_-]{0,63}-\$\{\{ github\.event\.pull_request\.number \}\}", group)
         and not group.lower().startswith("adopter-metadata-"),
         "application cancellation domain is not isolated")
    jobs = obj(workflow["jobs"], "application jobs")
    need(1 <= len(jobs) <= 16 and set(checks) <= set(jobs), "application check producer mismatch")
    for name, job in jobs.items():
        need(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", name)
             and name != "task-ritual" and isinstance(job, dict), "unsupported application job")
        need(set(job) in ({"runs-on", "steps"}, {"name", "runs-on", "steps"})
             and job.get("name", name) == name
             and job["runs-on"] in ("ubuntu-latest", "macos-latest", "windows-latest"),
             "application job must have static unconditional producer")
        steps = array(job["steps"], "application steps")
        need(steps and len(steps) <= 100, "missing application steps")
        actual_run = False
        for step in steps:
            obj(step, "application step")
            need(set(step) <= {"name", "uses", "with", "run", "env", "shell", "working-directory"}
                 and ("run" in step) != ("uses" in step),
                 "unsupported, conditional or softened application step")
            for key in ("env", "with"):
                if key in step:
                    need(isinstance(step[key], dict) and all(isinstance(value, str)
                         for value in step[key].values()), "unsupported step mapping")
            if "shell" in step:
                need(step["shell"] in ("bash", "sh", "pwsh", "python"), "unsupported application shell")
            if "run" in step:
                command = step["run"]
                need(isinstance(command, str) and command.strip()
                     and not any(ord(c) < 32 and c != "\n" for c in command),
                     "invalid application run")
                need(not re.fullmatch(r"(?:true|:|echo(?:\s.*)?)", command),
                     "application check needs an actual verification command")
                actual_run = True
            else:
                need(isinstance(step["uses"], str) and re.fullmatch(
                     r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}", step["uses"]),
                     "application action must have a full commit pin")
        need(actual_run, "application job lacks a verification command")


def configuration(data):
    config = obj(decode(data), "addon configuration")
    need(set(config) == {"schema", "code_workflow", "checks", "controls",
                        "sensor_sha256", "metadata_sha256", "ritual_sha256"}
         and config["schema"] == "adopter-ci/v1" and config["controls"] == CONTROLS,
         "unsupported or incomplete addon control inventory")
    relative(config["code_workflow"])
    need(re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", config["code_workflow"])
         and config["code_workflow"] != META, "unsupported application workflow path")
    checks = config["checks"]
    need(isinstance(checks, list) and 1 <= len(checks) <= 16
         and all(isinstance(x, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", x)
                 and x != "task-ritual" for x in checks)
         and checks == sorted(set(checks)), "invalid or duplicate required checks")
    for key in ("sensor_sha256", "metadata_sha256", "ritual_sha256"):
        need(isinstance(config[key], str) and re.fullmatch(r"[0-9a-f]{64}", config[key]),
             "invalid addon digest")
    need(config["ritual_sha256"] == RITUAL_SHA256, "unsupported installed ritual version")
    need(config["metadata_sha256"] == METADATA_SHA256, "metadata template changed")
    return config


def workflow_paths(root):
    directory = safe_path(root, ".github/workflows")
    need(directory.is_dir(), "workflow directory missing")
    entries = list(directory.iterdir())
    need(len(entries) <= 32, "workflow inventory exceeds resource bound")
    need(all(not entry.is_symlink() and entry.is_file()
             and entry.suffix in (".yml", ".yaml") for entry in entries),
         "unsupported workflow directory member")
    return sorted(str(p.relative_to(root)) for p in entries)


def local_drift(root):
    config_data = read_file(root, CONFIG)
    config = configuration(config_data)
    expected = sorted([META, config["code_workflow"]])
    need(workflow_paths(root) == expected, "unsupported or duplicate workflow producer")
    snapshot = {path: read_file(root, path) for path in
                (CONFIG, META, SELF, RITUAL, config["code_workflow"])}
    need(snapshot[CONFIG] == config_data, "configuration changed during read")
    for path, key in ((META, "metadata_sha256"), (SELF, "sensor_sha256"), (RITUAL, "ritual_sha256")):
        need(digest(snapshot[path]) == config[key], "required control bytes drifted: " + path)
    code_contract(snapshot[config["code_workflow"]], config["checks"])
    return config, snapshot


def remote_file(path, head, blob):
    value = obj(get(PREFIX + "/contents/" + path + "?ref=" + head)[0], "head content")
    need(value.get("type") == "file" and value.get("path") == path
         and value.get("encoding") == "base64" and type(value.get("size")) is int
         and 0 <= value["size"] <= MAX_BYTES, "unsupported head content")
    encoded = value.get("content")
    need(isinstance(encoded, str) and len(encoded) <= 2 * MAX_BYTES, "head content limit")
    try:
        content = base64.b64decode(encoded.replace("\n", ""), validate=True)
    except ValueError as error:
        raise Fault(2, "malformed head content") from error
    need(len(content) == value["size"]
         and hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
         == sha(value.get("sha"), "head blob") == blob, "head content binding mismatch")
    return content


def tree_entries(tree):
    value = obj(get(PREFIX + "/git/trees/" + sha(tree, "head tree"))[0], "head tree")
    need(value.get("truncated") is False and isinstance(value.get("tree"), list)
         and len(value["tree"]) <= 2000, "incomplete or oversized head tree")
    entries = {}
    for row in value["tree"]:
        row = obj(row, "tree entry")
        name = text(row.get("path"), "tree entry path")
        need("/" not in name and name not in (".", "..") and name not in entries,
             "unsafe or duplicate head tree entry")
        sha(row.get("sha"), "tree entry blob")
        entries[name] = row
    return entries


def head_blobs(paths):
    # Contents API may dereference repository symlinks. Tree modes provide the
    # independent regular-file/regular-parent proof before any content is used.
    cache = {"": tree_entries(HEAD)}
    blobs = {}
    for path in paths:
        parts = path.split("/")
        parent = ""
        for index, name in enumerate(parts):
            row = cache[parent].get(name)
            need(isinstance(row, dict), "required head path missing")
            if index == len(parts) - 1:
                need(row.get("mode") == "100644" and row.get("type") == "blob",
                     "head guarded path is not a regular nonexecutable file")
                blobs[path] = row["sha"]
            else:
                need(row.get("mode") == "040000" and row.get("type") == "tree",
                     "head guarded parent is not a directory")
                parent = parent + ("/" if parent else "") + name
                if parent not in cache:
                    cache[parent] = tree_entries(row["sha"])
    need(sorted(cache[".github/workflows"]) == sorted(Path(p).name for p in paths
         if p.startswith(".github/workflows/")), "unsupported head workflow producer")
    return blobs


def remote_drift(config, snapshot):
    blobs = head_blobs(snapshot)
    observed = {}
    for path in snapshot:
        observed[path] = remote_file(path, HEAD, blobs[path])
        if path != config["code_workflow"]:
            need(observed[path] == snapshot[path], "head guarded addon control changed: " + path)
    code_contract(observed[config["code_workflow"]], config["checks"])
    return observed


def check(root):
    global WORKFLOW, CONTEXTS
    config, snapshot = local_drift(root)
    WORKFLOW, CONTEXTS = config["code_workflow"], config["checks"]
    need(all(shutil.which(x) for x in ("gh", "bash", "git", "jq", "base64")),
         "required dependency unavailable")
    need(os.environ.get("GITHUB_EVENT_NAME") == "pull_request", "unsupported event")
    need(re.fullmatch(r"[1-9][0-9]*", PR) and re.fullmatch(r"[0-9a-f]{40}", HEAD)
         and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", REPO)
         and REPO.split("/")[-1] not in (".", ".."),
         "invalid repository/PR/head input")
    need(os.environ.get("GH_HOST", "github.com") == "github.com"
         and os.environ.get("GITHUB_API_URL", "https://api.github.com") == "https://api.github.com",
         "unsupported GitHub host")
    identity = pr_identity(get(f"{PREFIX}/pulls/{PR}")[0])
    need(identity[0] == int(PR) and identity[1] == HEAD, "current PR/head mismatch")
    trigger(identity)
    observed = remote_drift(config, snapshot)
    result = bounded_command(["bash", str(root / RITUAL), PR], cwd=root,
                             env=dict(os.environ, GH_REPO=REPO))
    need(result.returncode == 0, "installed Task ritual refused; inspect its bounded read-only result", 1)
    message = freshness()
    stable(pr_identity(get(f"{PREFIX}/pulls/{PR}")[0]) == identity)
    stable(remote_drift(config, snapshot) == observed)
    stable(local_drift(root) == (config, snapshot))
    return "CONTROLS_ACTIVE; TASK_RITUAL_PASS; " + message


def main():
    parser = argparse.ArgumentParser(description="Read-only opt-in adopter CI controls")
    parser.add_argument("command", choices=("check", "drift"))
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        root = safe_root(args.root)
        if args.command == "drift":
            config, snapshot = local_drift(root)
            stable(local_drift(root) == (config, snapshot))
            message = "CONTROLS_ACTIVE: supported local wiring observed"
        else:
            message = check(root)
        print(message)
        return 0
    except (Fault, OSError, UnicodeError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError) as error:
        # No remote bodies, raw helper output, credentials or local paths.
        print(("STALE" if isinstance(error, Fault) and error.code == 1 else "UNCHECKABLE")
              + ": " + (str(error) if isinstance(error, Fault) else "input or observation unavailable"),
              file=sys.stderr)
        return error.code if isinstance(error, Fault) else 2


if __name__ == "__main__":
    sys.exit(main())
