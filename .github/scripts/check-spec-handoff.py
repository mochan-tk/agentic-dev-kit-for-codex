#!/usr/bin/env python3
"""Warn about missing handoff labels; never assess material quality or consent."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import unicodedata

# Six README groups, with scope and non-goals observed separately. English and
# Japanese labels are accepted in headings or prose; no section body is required.
OBSERVATIONS = (
    ("goal", r"\b(?:goals?|objectives?)\b|目的|目標"),
    ("intended users", r"\b(?:intended|target) (?:users?|audience)\b|対象(?:ユーザー|ユーザ|利用者)|想定(?:ユーザー|ユーザ|利用者)"),
    ("scope", r"\bscope\b|スコープ|対象範囲|対応範囲"),
    ("non-goals", r"\bnon[ -]?goals?\b|\bout[ -]of[ -]scope\b|非目標|対象外|スコープ外"),
    ("constraints", r"\bconstraints?\b|制約"),
    ("acceptance criteria", r"\bacceptance (?:criteria|criterion)\b|受け入れ(?:条件|基準)|受入(?:条件|基準)"),
    ("unresolved questions", r"\b(?:unresolved|open) questions?\b|未解決(?:の)?(?:質問|事項|課題)|未決事項"),
)


def inspect(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[‐‑–—]", "-", text)
    text = re.sub(r"\s+", " ", text)
    # Strip the *whole* excluded-scope/non-goal label before looking for goal
    # or scope, so those words cannot satisfy two distinct observations.
    included = re.sub(OBSERVATIONS[3][1], "", text)
    return {label: bool(re.search(pattern, included if label in {"goal", "scope"} else text))
            for label, pattern in OBSERVATIONS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", type=Path, nargs="+", help="UTF-8 Markdown/text files, inspected together")
    args = parser.parse_args(argv)
    try:
        documents = [path.read_text(encoding="utf-8-sig") for path in args.materials]
        if any("\0" in document for document in documents):
            raise ValueError("binary input")
    except (OSError, UnicodeError, ValueError):
        print("ERROR: material could not be read as UTF-8 text; check the supplied files.", file=sys.stderr)
        return 2
    found = inspect("\n".join(documents))
    print(f"Observed points: {sum(found.values())}/7")
    missing = [label for label, present in found.items() if not present]
    print("Missing: " + (", ".join(missing) if missing else "none"))
    print("Presence only; content quality and sufficiency are not assessed.")
    print("Advisory: the owner decides whether onboarding proceeds; this is not a gate or consent.")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
