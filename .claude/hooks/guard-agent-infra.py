#!/usr/bin/env python3
"""PreToolUse guard: the agent guard infrastructure itself.

Protects the files whose modification would directly disable the other guards:

    .claude/hooks/**              the guard implementations
    .claude/settings.json         the configuration that activates them
    .claude/settings.local.json   a local override that could deactivate them

Reading these files is always allowed -- the guards should be auditable. What is
blocked is modifying, deleting, renaming, or un-executing them.

This is defence in depth for the Bash path. `permissions.deny` in
`.claude/settings.json` already denies the Write and Edit tools against these
paths; this hook covers `sed -i`, `rm`, `mv`, `chmod -x`, redirection, and
similar shell modification that permission rules do not see. Both layers are
intended to be present.

Paths are resolved after expanding `$CLAUDE_PROJECT_DIR`, `$HOME`, and `~`, and
a protected path is recognised even when it is embedded in an option or value
token such as `of=...` or `--target-directory=...`.

`cd` and `pushd` are tracked across segments, but a directory change is adopted
only when the target actually exists -- a failed `cd` leaves the real shell where
it was, so modelling the move would be a bypass. Once the working directory is
unknown, a modifying command naming anything guard-shaped is refused rather than
resolved against a guessed directory. Shell control flow is deliberately not
modelled; conservative refusal is preferred to guessing.

This hook has no built-in Claude-settable bypass flag or environment variable.
If the guards genuinely need to change, the owner edits them.

NOT DETECTABLE -- documented gaps, not claims of safety. This is not a sandbox.
    * modification performed inside an arbitrary script this hook only sees
      invoked, where the protected path never appears in the command text
    * paths computed at runtime and never present in the command
    * an editor or process launched outside Claude Code
    * user-level or managed settings that override project settings

Exit 0 = allow. Exit 2 = block (stderr is shown to the model).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

HOOK = ".claude/hooks/guard-agent-infra.py"

PROTECTED_DIRS = (".claude/hooks",)
PROTECTED_FILES = (
    ".claude/settings.json",
    ".claude/settings.local.json",
)

# Commands that only read. Anything else touching a protected path is treated as
# a modification, so the default is refusal rather than permission. `chmod` is
# deliberately absent: `chmod -x` would disable a guard.
READ_ONLY_CMDS = {
    "ls", "cat", "head", "tail", "wc", "stat", "file", "shasum", "md5",
    "md5sum", "grep", "egrep", "rg", "du", "realpath", "dirname", "basename",
    "echo", "printf", "test", "diff", "cmp",
}

OPERATORS = {";", "&&", "||", "|", "&", "\n"}
REDIRECTS = {">", ">>", ">|", "&>"}
HOME = os.path.expanduser("~")


def project_root() -> str:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return os.path.realpath(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return os.path.realpath(out.stdout.strip())
    except Exception:
        pass
    return os.path.realpath(os.getcwd())


ROOT = project_root()
PROTECTED_DIR_PATHS = [os.path.realpath(os.path.join(ROOT, d)) for d in PROTECTED_DIRS]
PROTECTED_FILE_PATHS = [os.path.realpath(os.path.join(ROOT, f)) for f in PROTECTED_FILES]

# Basenames that look guard-critical. Used only when the working directory or a
# path expression cannot be resolved, to decide whether to refuse.
PROTECTED_BASENAMES = {os.path.basename(f) for f in PROTECTED_FILE_PATHS}
for _d in PROTECTED_DIR_PATHS:
    if os.path.isdir(_d):
        PROTECTED_BASENAMES.update(os.listdir(_d))

GUARD_SHAPED_RE = re.compile(r"\.claude/(hooks|settings\.json|settings\.local\.json)")


def block(reason: str, detail: str = "") -> None:
    lines = [f"BLOCKED by {HOOK}", "", f"Reason: {reason}"]
    if detail:
        lines.append(f"Detail: {detail}")
    lines += [
        "",
        "These files implement and activate the repository's safety guards.",
        "Reading them is allowed; changing them is not. If a guard genuinely",
        "needs to change, stop and ask the owner to make the change.",
        "",
        "This guard has no Claude-settable bypass flag or environment variable.",
    ]
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(2)


def expand(value: str) -> str:
    for name, target in (("CLAUDE_PROJECT_DIR", ROOT), ("HOME", HOME), ("PWD", ROOT)):
        value = value.replace(f"${{{name}}}", target).replace(f"${name}", target)
    if value.startswith("~"):
        value = os.path.expanduser(value)
    return value


def resolve(raw: str, cwd: str | None) -> tuple[str | None, bool]:
    """Return (canonical path, unresolvable) for a candidate path string.

    `unresolvable` is True when the value still contains an unexpanded variable,
    or when it is relative and the working directory is unknown. Callers must
    treat that as a reason to refuse a modifying command, never as "safe".
    """
    value = raw.strip().strip("'\"")
    if not value:
        return None, False
    value = expand(value)
    if "$" in value:
        return None, True
    if not os.path.isabs(value):
        if cwd is None:
            return None, True
        value = os.path.join(cwd, value)
    try:
        return os.path.realpath(value), False
    except Exception:
        return None, True


def candidate_paths(token: str):
    """A token, plus any value it carries after `=`.

    `dd of=.claude/settings.json` and `cp --target-directory=.claude/hooks`
    both hide a protected path inside a single token.
    """
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]


def is_protected(path: str) -> bool:
    if path in PROTECTED_FILE_PATHS:
        return True
    return any(path == d or path.startswith(d + os.sep) for d in PROTECTED_DIR_PATHS)


def looks_guard_shaped(raw: str) -> bool:
    value = expand(raw.strip().strip("'\""))
    if GUARD_SHAPED_RE.search(value) or ".claude" in value:
        return True
    return os.path.basename(value) in PROTECTED_BASENAMES


def split_segments(command: str) -> list[list[str]] | None:
    """Tokenise into command segments, respecting quotes."""
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
        if ".claude" in command:
            block("a command referencing .claude could not be tokenised, so it "
                  "could not be inspected", command)
        return

    cwd: str | None = ROOT
    for tokens in segments:
        if not tokens:
            continue
        seg = " ".join(tokens)
        program = os.path.basename(tokens[0])

        # --- track the working directory ------------------------------------
        # Adopt a change only when the target exists: a failed `cd` leaves the
        # real shell in place, so modelling the move would be a bypass.
        if program in ("cd", "pushd"):
            if len(tokens) < 2:
                cwd = HOME
            else:
                path, unresolvable = resolve(tokens[1], cwd)
                cwd = path if (not unresolvable and path and os.path.isdir(path)) else None
            continue
        if program == "popd":
            cwd = None          # the stack is not modelled; refuse to guess
            continue

        redirects = any(t in REDIRECTS for t in tokens)
        read_only = program in READ_ONLY_CMDS and not redirects

        # --- an inline script naming the guard files -------------------------
        if "-c" in tokens and GUARD_SHAPED_RE.search(expand(seg)):
            block("an inline script naming the guard infrastructure", seg)

        touched = False
        ambiguous = False
        for token in tokens[1:]:
            for candidate in candidate_paths(token):
                path, unresolvable = resolve(candidate, cwd)
                if unresolvable:
                    if looks_guard_shaped(candidate):
                        ambiguous = True
                    continue
                if path and is_protected(path):
                    touched = True

        if ambiguous and not read_only:
            block(
                "a modifying command naming a guard-critical path whose "
                "location could not be resolved (unknown working directory or "
                "unexpanded variable); refusing rather than guessing",
                seg,
            )
        if not touched:
            continue
        if redirects:
            block("output redirection into the guard infrastructure", seg)
        if program not in READ_ONLY_CMDS:
            block(
                f"'{program}' is not a known read-only command, so this is "
                "treated as a modification of the guard infrastructure",
                seg,
            )


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
        path, unresolvable = resolve(target, ROOT)
        if unresolvable and looks_guard_shaped(target):
            block("a write to a guard-critical path that could not be "
                  "resolved confidently", target)
        if path and is_protected(path):
            block("this modifies the guard infrastructure", target)
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
