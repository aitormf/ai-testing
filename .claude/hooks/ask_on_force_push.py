#!/usr/bin/env python3
# .claude/hooks/ask_on_force_push.py
"""PreToolUse: before a forced `git push`, asks the person for confirmation."""

import json
import shlex
import sys

SEPARATORS = {"&&", "||", ";", "|", "&"}
GIT_FLAGS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def is_force_push(command: str) -> bool:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)  # splits ";", "&&", "|"… even when not space-separated
    except ValueError:
        return False
    for i, word in enumerate(tokens):
        if word != "git":
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):  # git -C <dir> push …
            j += 2 if tokens[j] in GIT_FLAGS_WITH_VALUE else 1
        if j >= len(tokens) or tokens[j] != "push":
            continue
        for arg in tokens[j + 1 :]:
            if arg in SEPARATORS:
                break
            if arg.startswith(("--force", "+")):  # --force, --force-with-lease, +refspec
                return True
            if arg.startswith("-") and not arg.startswith("--") and "f" in arg:  # -f, -uf
                return True
    return False


def main() -> int:
    event = json.load(sys.stdin)
    if is_force_push(event.get("tool_input", {}).get("command", "")):
        decision = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Forced push: it can overwrite others' history.",
        }
        print(json.dumps({"hookSpecificOutput": decision}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
