#!/usr/bin/env python3
"""PreToolUse guard: the owner's production Ion data.

Policy
    * writes to the owner's normal Ion data directory are blocked
    * explicitly read-only inspection is allowed
    * Ion writer and runtime entrypoints must name a non-production ION_DATA_DIR

The protected directory is `$HOME/Library/Application Support/Ion OS`. The
rebuild directory `Ion OS Rebuild` is a sibling and is never caught: paths are
compared after canonical resolution, with a boundary-safe containment test, and
commands are tokenised with shlex so a quoted path containing spaces is one
token rather than a fragile substring match.

`apps/api/ion_api/settings.py:default_data_dir()` returns the production
directory whenever ION_DATA_DIR is unset, so "unset" is not neutral for a writer
entrypoint -- it means owner data. Each Bash tool call runs in a fresh shell, so
requiring the variable in the same command is correct rather than a false
positive.

This hook has no built-in Claude-settable bypass flag or environment variable.

FAILS CLOSED for known writer entrypoints and for uninspectable payloads. It
does NOT claim universal shell-write detection.

NOT DETECTABLE -- documented gaps, not claims of safety
    * writes performed inside an arbitrary script this hook only sees invoked
    * paths computed at runtime and never present in the command
    * applications the owner launches outside Claude Code
    * Ion writer entrypoints added in future and not listed here

Exit 0 = allow. Exit 2 = block (stderr is shown to the model).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

HOOK = ".claude/hooks/guard-owner-data.py"

HOME = os.path.expanduser("~")
PROD = os.path.realpath(os.path.join(HOME, "Library", "Application Support", "Ion OS"))
SAFE_HINT = os.path.join(HOME, "Library", "Application Support", "Ion OS Rebuild")

# Commands that only read. Anything else touching the production directory is
# treated as a write, so the default is refusal rather than permission.
READ_ONLY_CMDS = {
    "ls", "cat", "head", "tail", "wc", "stat", "file", "shasum", "md5",
    "md5sum", "grep", "egrep", "du", "realpath", "dirname", "basename",
    "echo", "printf", "test", "diff", "cmp", "strings", "sqlite3",
}

# Ion entrypoints that open or create runtime data.
WRITER_HINTS = (
    "ion_api", "serve_api.py", "ion-api", "tauri",
)


def block(reason: str, detail: str = "") -> None:
    lines = [f"BLOCKED by {HOOK}", "", f"Reason: {reason}"]
    if detail:
        lines.append(f"Detail: {detail}")
    lines += [
        "",
        f"Protected directory: {PROD}",
        f"Use instead:         ION_DATA_DIR=\"{SAFE_HINT}\"",
        "",
        "This guard has no Claude-settable bypass flag or environment variable.",
        "If this operation is genuinely required, stop and ask the owner.",
    ]
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(2)


def resolve(raw: str) -> str | None:
    """Canonical filesystem path for a token, or None if it is not path-like."""
    value = raw.strip().strip("'\"")
    if value.startswith("file:"):
        value = value[5:]
    value = value.split("?", 1)[0]
    if not value:
        return None
    value = value.replace("$HOME", HOME).replace("${HOME}", HOME)
    if value.startswith("~"):
        value = os.path.expanduser(value)
    if not value.startswith("/"):
        return None
    try:
        return os.path.realpath(value)
    except Exception:
        return None


def inside_production(path: str) -> bool:
    return path == PROD or path.startswith(PROD + os.sep)


def check_file_path(raw: str) -> None:
    path = resolve(raw)
    if path and inside_production(path):
        block("this writes into the owner's production Ion data directory", raw)


def data_dir_assignment(tokens: list[str]) -> str | None:
    """The ION_DATA_DIR value set in this segment, or None if it is not set."""
    for token in tokens:
        if token.startswith("ION_DATA_DIR="):
            return token.split("=", 1)[1]
    return None


def is_pytest(tokens: list[str]) -> bool:
    # pytest uses isolated tmp_path directories; blocking it would be a false
    # positive. Verified against apps/api/tests.
    joined = " ".join(tokens)
    return "pytest" in joined or "test:py" in joined


def is_writer(tokens: list[str]) -> bool:
    joined = " ".join(tokens)
    if any(os.path.basename(t) == "ion-api" for t in tokens):
        return True
    if "-m" in tokens:
        i = tokens.index("-m")
        if i + 1 < len(tokens) and tokens[i + 1] == "ion_api":
            return True
    if any(t.endswith("serve_api.py") for t in tokens):
        return True
    if re.search(r"\btauri\b.*\b(dev|build)\b", joined):
        return True
    if re.search(r"\bnpm\b.*\brun\b.*\bdev(:api|:desktop)?\b", joined):
        return True
    return False


OPERATORS = {";", "&&", "||", "|", "&", "\n"}
REDIRECTS = {">", ">>", ">|", "&>"}


def split_segments(command: str) -> list[list[str]] | None:
    """Tokenise into command segments, respecting quotes.

    Splitting on `;` with a regex would cut through quoted text -- the `;` in
    `sqlite3 db 'select 1;'` is data, not a separator -- producing an
    unparseable fragment and a false block. Returns None if the command as a
    whole cannot be lexed.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = []
    current: list[str] = []
    try:
        for token in lexer:
            if token in OPERATORS:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(token)
    except ValueError:
        return None
    if current:
        segments.append(current)
    return segments


def inspect_bash(command: str) -> None:
    segments = split_segments(command)
    if segments is None:
        # Only fail closed where it matters: a command that mentions neither the
        # production directory nor an Ion writer is not our concern.
        if "Ion OS" in command or any(h in command for h in WRITER_HINTS):
            block("a command referencing Ion data could not be tokenised, so "
                  "it could not be inspected", command)
        return

    for tokens in segments:
        if not tokens:
            continue
        seg = " ".join(tokens)
        program = os.path.basename(tokens[0])
        redirects = any(t in REDIRECTS for t in tokens)

        # --- direct references to the production directory -------------------
        for token in tokens:
            path = resolve(token)
            if not path or not inside_production(path):
                continue
            if program == "sqlite3" and any("mode=ro" in t for t in tokens):
                continue                      # explicit read-only inspection
            if program == "sqlite3":
                block("sqlite3 against the production database without "
                      "mode=ro could write to owner data", seg)
            if redirects:
                block("output redirection into the production directory", seg)
            if program == "find" and ("-delete" in tokens or "-exec" in tokens):
                block("find with -delete/-exec against production data", seg)
            if program not in READ_ONLY_CMDS:
                block(f"'{program}' is not a known read-only command, so this "
                      "is treated as a write to production data", seg)

        # --- Ion writer and runtime entrypoints ------------------------------
        if is_pytest(tokens) or not is_writer(tokens):
            continue
        assigned = data_dir_assignment(tokens)
        if assigned is None:
            block(
                "an Ion writer or runtime entrypoint with no ION_DATA_DIR set "
                "in this command. settings.py then defaults to the production "
                "directory, so this would open the owner's data.",
                seg,
            )
        resolved = resolve(assigned)
        if resolved is None or inside_production(resolved):
            block("an Ion writer or runtime entrypoint pointed at the "
                  "production directory", seg)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        block("the PreToolUse payload could not be parsed, so the operation "
              "could not be inspected")

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(target, str) or not target.strip():
            block("a file-writing tool call carried no inspectable file_path")
        check_file_path(target)
        raise SystemExit(0)

    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            block("no inspectable command was present in tool_input, so this "
                  "Bash call could not be checked")
        inspect_bash(command)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
