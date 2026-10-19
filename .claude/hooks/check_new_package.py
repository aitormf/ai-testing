#!/usr/bin/env python3
# .claude/hooks/check_new_package.py
"""PreToolUse: before `uv add`, check that every package exists on PyPI and has some history."""

import json
import re
import shlex
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

MIN_AGE_DAYS = 90
FLAGS_WITH_VALUE = {
    "--group",
    "--optional",
    "--extra",
    "-r",
    "--requirements",
    "--index",
    "--package",
}
SEPARATORS = {"&&", "||", ";", "|", "&"}


def requested_packages(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)  # splits ";", "&&", "|"… even without surrounding spaces
    except ValueError:
        return []
    packages = []
    for i in range(len(tokens) - 1):
        if tokens[i] != "uv" or tokens[i + 1] != "add":
            continue
        j = i + 2
        while j < len(tokens) and tokens[j] not in SEPARATORS:
            token = tokens[j]
            if token in FLAGS_WITH_VALUE:
                j += 1
            elif not token.startswith(("-", ".", "/", "git+", "http://", "https://")):
                name = re.split(r"[\[<>=!~;@ ]", token, maxsplit=1)[0]
                if name:
                    packages.append(name)
            j += 1
    return packages


def first_upload(name: str) -> datetime | None:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    uploads = [f["upload_time_iso_8601"] for files in data["releases"].values() for f in files]
    if not uploads:
        return None
    return min(datetime.fromisoformat(u.replace("Z", "+00:00")) for u in uploads)


def main() -> int:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    problems = []
    for name in requested_packages(command):
        try:
            first = first_upload(name)
        except Exception as exc:  # no network: warn, do not block
            print(f"Warning: could not check '{name}' on PyPI ({exc}).", file=sys.stderr)
            continue
        if first is None:
            problems.append(
                f"'{name}' does not exist on PyPI or has no releases: possibly a hallucinated package."
            )
        elif (datetime.now(UTC) - first).days < MIN_AGE_DAYS:
            problems.append(
                f"'{name}' was first published on {first:%Y-%m-%d} (less than {MIN_AGE_DAYS} days ago)."
            )
    if problems:
        print(
            "Dependency blocked:\n- "
            + "\n- ".join(problems)
            + "\nCheck the exact name and confirm it with a person before adding it.",
            file=sys.stderr,
        )
        return 2  # exit 2 = block the tool and send the reason back to the agent
    return 0


if __name__ == "__main__":
    sys.exit(main())
