#!/usr/bin/env python3
"""Read-only, advisory Tier 0/1/2 diagnostics for an adopter Git checkout."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

REGISTRY = Path(__file__).resolve().parents[1] / "distribution/prerequisites.v1.json"
TIMEOUT = 10
OUTPUT_LIMIT = 1024 * 1024
TOOLS = {"git": r"git version (\d+(?:\.\d+)+)",
         "bash": r"GNU bash, version (\d+(?:\.\d+)+)",
         "jq": r"jq-(\d+(?:\.\d+)+)",
         "gh": r"gh version (\d+(?:\.\d+)+)"}


def run(args, cwd):
    # Observe the requested checkout even when launched from another Git task.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in {"GH_REPO", "GH_HOST", "GH_DEBUG"}}
    env.update(LC_ALL="C", GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1",
               GH_NO_UPDATE_NOTIFIER="1", GH_NO_EXTENSION_UPDATE_NOTIFIER="1",
               NO_COLOR="1")
    try:
        result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=TIMEOUT, check=False)
    except FileNotFoundError:
        return 127, ""
    except (OSError, subprocess.TimeoutExpired):
        return 126, ""
    # Raw stderr/auth/API data never becomes a diagnostic or a saved record.
    if len(result.stdout) > OUTPUT_LIMIT:
        return 126, ""
    return result.returncode, result.stdout.decode("utf-8", errors="replace")


def api(endpoint, cwd):
    code, output = run(["gh", "api", "--hostname", "github.com", "--method", "GET",
                        "--include", "-H", "Accept: application/vnd.github+json", endpoint], cwd)
    if code == 4:
        # gh's documented authentication-required exit is local evidence, not
        # an HTTP response and not a connectivity failure.
        return 4, {}, None
    header, separator, body = output.replace("\r\n", "\n").partition("\n\n")
    status_match = re.match(r"HTTP/\S+ (\d{3})(?:\s|$)", header)
    status = int(status_match[1]) if separator and status_match else None
    headers = {}
    for line in header.splitlines()[1:]:
        key, colon, value = line.partition(":")
        if colon:
            headers[key.strip().lower()] = value.strip()
    try:
        data = json.loads(body) if separator else None
    except ValueError:
        data = None
    if code and status == 200:
        status, data = None, None
    return status, headers, data


def repository_name(remote):
    # Deliberately do not forward credentials, arbitrary hosts or URL parameters.
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                         r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", remote.strip())
    if not match or any(part in {".", ".."} for part in match[1].split("/")):
        return None
    return match[1]


def scope_result(headers):
    value = headers.get("x-oauth-scopes")
    if value is None or not value.strip():
        return "PROCEDURE", "Scopes are not exposed; confirm Projects permissions for this credential type."
    scopes = {item.strip() for item in value.split(",")}
    if "project" in scopes:
        return "OK", "Classic/OAuth project scope includes read:project; board authorization is still separate."
    if "read:project" in scopes:
        return "MISSING", "read:project permits queries; project for creation/updates is missing."
    return "MISSING", "Classic/OAuth read:project and project scopes are missing."


def diagnose(target, registry):
    results = {row["id"]: ("PROCEDURE", row["detection"]["description"])
               for row in registry["entries"]}
    for tool, pattern in TOOLS.items():
        code, output = run([tool, "--version"], target)
        match = re.search(pattern, output) if code == 0 else None
        if match:
            version = tuple(int(part) for part in match[1].split("."))
            if tool == "bash" and version[:2] < (3, 2):
                results[tool] = "MISSING", "Bash " + match[1] + "; 3.2 or later is required."
            elif tool == "bash" and os.name == "nt" and "msys" not in output.lower():
                results[tool] = "PROCEDURE", "Bash version detected; confirm that Windows uses Git Bash."
            else:
                results[tool] = "OK", "Version " + match[1] + "."
        elif code == 127:
            results[tool] = "MISSING", "Executable not found on PATH."
        else:
            results[tool] = "UNVERIFIED", "Executable/version could not be checked."

    results["github-checkout"] = "UNVERIFIED", "Local checkout/origin could not be checked."
    results["repository-access"] = "UNVERIFIED", "Repository access and gh authentication could not be checked."
    results["remote-scaffold"] = "UNVERIFIED", "Remote default branch/scaffold could not be checked."
    results["projects-scope"] = "UNVERIFIED", "Projects scopes could not be checked."
    repo = None
    if results["git"][0] == "OK":
        code, inside = run(["git", "rev-parse", "--is-inside-work-tree"], target)
        if code == 0 and inside.strip() == "true":
            code, remote = run(["git", "remote", "get-url", "origin"], target)
            repo = repository_name(remote) if code == 0 else None
            results["github-checkout"] = (("OK", "Local Git worktree with a github.com origin.") if repo else
                ("PROCEDURE", "Git worktree found; set/confirm a canonical github.com origin (other hosts need manual checks)."))
        else:
            results["github-checkout"] = "MISSING", "Target is not an observable non-bare Git worktree."

    if results["gh"][0] != "OK":
        return results
    # /user establishes active user authentication, independently of public repo
    # readability. Installation tokens may lack /user; their auth stays unverified.
    status, headers, user = api("user", target)
    if status == 4:
        results["repository-access"] = "MISSING", "gh requires authentication (CLI exit 4); no usable login was available."
        return results
    authenticated = status == 200 and isinstance(user, dict) and isinstance(user.get("login"), str) and bool(user["login"])
    if authenticated:
        results["projects-scope"] = scope_result(headers)
    elif status == 401:
        results["repository-access"] = "MISSING", "gh authentication was rejected (HTTP 401)."
    if not repo:
        return results

    status, repo_headers, metadata = api("repos/" + repo, target)
    if status != 200 or not isinstance(metadata, dict) or str(metadata.get("full_name", "")).casefold() != repo.casefold():
        if status == 401:
            results["repository-access"] = "MISSING", "gh authentication was rejected (HTTP 401)."
        elif status in {403, 404}:
            results["repository-access"] = "UNVERIFIED", "Repository unavailable to this credential (denial, absence or policy); access unverified."
        return results
    if authenticated:
        results["repository-access"] = "OK", "gh user authentication and target repository read succeeded."
    else:
        results["repository-access"] = "UNVERIFIED", "Repository is readable; active user authentication was not verified."
    # Repository responses can also expose scopes, without making any board write.
    if results["projects-scope"][0] == "UNVERIFIED":
        results["projects-scope"] = scope_result(repo_headers)
    branch = metadata.get("default_branch")
    if not isinstance(branch, str) or not branch or len(branch) > 255:
        results["remote-scaffold"] = "UNVERIFIED", "Remote default branch metadata is absent or invalid."
        return results
    endpoint = f"repos/{repo}/contents/.github/codex-instructions.md?ref={quote(branch, safe='')}"
    status, _, anchor = api(endpoint, target)
    if (status == 200 and isinstance(anchor, dict) and anchor.get("type") == "file"
            and anchor.get("path") == ".github/codex-instructions.md"
            and re.fullmatch(r"[0-9a-f]{40}", str(anchor.get("sha", "")))):
        results["remote-scaffold"] = "OK", "Scaffold instruction anchor is readable on the current remote default branch (not full installation proof)."
    elif status == 404:
        results["remote-scaffold"] = "UNVERIFIED", "Scaffold instruction anchor is absent or inaccessible on the observed remote default branch; recheck Contents permission and P0."
    return results


def report(registry, results):
    print("Read-only prerequisite observations; no setup, authentication changes or consent implied.")
    for tier in registry["tiers"]:
        rows = [row for row in registry["entries"] if row["tier"] == tier["tier"]]
        print(f"\nTier {tier['tier']} — {tier['label']}")
        print("Reach: " + tier["reach"])
        for row in rows:
            status, detail = results[row["id"]]
            print(f"  {status} [{row['id']}] {row['label']}: {detail}")
            if status != "OK":
                print("    Impact if missing: " + row["impact_if_missing"])
                print("    Remedy: " + row["remedy"])
        cumulative = [results[row["id"]][0] for row in registry["entries"] if row["tier"] <= tier["tier"]]
        verdict = "MISSING" if "MISSING" in cumulative else "CONFIRMATION REQUIRED" if any(s != "OK" for s in cumulative) else "OK"
        print("  Cumulative readiness: " + verdict)
    print("\nPROCEDURE = manual confirmation, not a checked prerequisite; UNVERIFIED = observation unavailable.")
    print("Projects exceptions require a durable owner decision; missing scopes never create an exception.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd(), help="adopter checkout (default: current directory)")
    args = parser.parse_args(argv)
    if not args.target.is_dir():
        print("ERROR: target must be an existing directory.", file=sys.stderr)
        return 2
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        results = diagnose(args.target.resolve(), registry)
        report(registry, results)
    except (OSError, ValueError, KeyError, TypeError):
        print("ERROR: prerequisite registry or observation could not be read.", file=sys.stderr)
        return 2
    # Diagnostics are advisory; a nonzero exit does not grant or deny authority.
    return int(any(status != "OK" for status, _ in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
