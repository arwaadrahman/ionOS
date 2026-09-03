#!/usr/bin/env python3
"""PreToolUse guard: destructive git operations.

Blocks the reliably detectable forms of operations that erase uncommitted work
or rewrite published `main` history. Ordinary commit, non-force push, branch
creation and switching, add, and targeted single-path restoration are NOT
blocked. `git stash` IS blocked in every form -- it moves, overwrites, or
destroys uncommitted worktree state.

This hook has no built-in Claude-settable bypass flag or environment variable.
An exceptional owner-authorised destructive action is performed by the owner
outside Claude, or after the owner edits or disables this hook. That friction is
intentional. The stronger property -- that Claude cannot quietly edit or remove
the guards themselves -- is provided by `permissions.deny` in
`.claude/settings.json` together with `guard-agent-infra.py`, not by this file.

Commands are tokenised with shlex rather than matched with regexes, so forms
like `git checkout HEAD -- .` and `git restore --source=HEAD :/` are recognised.
This is deliberately not a shell interpreter.

FAILS CLOSED. A forced push is allowed only when its destination is provably a
non-main branch. No explicit refspec, an unrecognised push option, or a
symbolic or revision-like destination (HEAD, @, a hash, `HEAD~1`) all block,
because the remote branch behind them may well be main. The destination of a
bare `git push --force` depends on push.default, upstream tracking, and
configured refspecs; this hook refuses rather than reproducing git's
configuration resolution.

Exit 0 = allow. Exit 2 = block (stderr is shown to the model).

RECOGNISED (blocked)
    git reset --hard <any ref>
    git clean with any force spelling      -f, -fd, -fdx, -xfd, -df, --force
    whole-worktree discard                 checkout/restore targeting . ./ :/ *
                                           including with refs and options
                                           between the verb and the target
    forced push                            --force, -f, --force-with-lease, and
                                           any + refspec, unless the destination
                                           is a provably non-main branch
    delete or move main                    branch -d/-D/--delete main
                                           branch -f/--force main <ref>
                                           checkout -B main, switch -C main
                                           update-ref refs/heads/main <sha>
                                           update-ref -d/--delete refs/heads/main
                                           push :main, push :refs/heads/main
                                           push --delete <remote> main
    history rewriting                      filter-branch, filter-repo

NOT RECOGNISED -- documented gaps, not claims of safety
    This guard is SEMANTIC defence-in-depth, not a filesystem boundary. The
    native Claude Code sandbox is the hard boundary for arbitrary subprocess
    writes; see .claude/settings.json `sandbox.filesystem`.
    * a git alias that expands to a blocked command
    * destructive git run inside a script this hook only sees invoked
    * git reached through a wrapper or a differently named binary
    * raw filesystem deletion (rm -rf, find -delete) that never names git. The
      sandbox does NOT prevent this: it protects .claude/**, scripts/verify/**,
      AGENTS.md, CLAUDE.md and owner production data, but the worktree is
      deliberately writable. Raw worktree destruction is recoverable only
      because unattended implementation runs in a disposable isolated worktree.
    * history made unrecoverable later via reflog expire + gc --prune
"""

from __future__ import annotations

import json
import re
import shlex
import sys

HOOK = ".claude/hooks/guard-worktree-and-main.py"

# Pathspecs that mean "the entire working tree".
WHOLE_TREE = {".", "./", ":/", ":/.", "*", ":"}

# Options that discard uncommitted worktree changes outright, independent of any
# pathspec. The sandbox permits ordinary source modification by design, so these
# stay a semantic concern for this guard.
DISCARD_OPTS = {"--force", "--discard-changes", "--ours", "--theirs"}

MAIN_REFS = {"main", "refs/heads/main", "heads/main"}

# Symbolic refs whose remote destination cannot be established from the command.
SYMBOLIC_REFS = {
    "HEAD", "@", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD",
}

# `git push` options that consume the following token as their value. Failing to
# skip one of these would let its value be mistaken for a refspec, which is a
# fail-open error -- `git push --force -o ci.skip origin` would look like a push
# to a ref named "origin" instead of the ambiguous forced push it really is.
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}

# `git push` options that stand alone.
PUSH_NOVALUE_OPTS = {
    "-f", "--force", "--force-with-lease", "--no-force-with-lease",
    "--force-if-includes", "--no-force-if-includes",
    "-u", "--set-upstream", "-n", "--dry-run", "-q", "--quiet",
    "-v", "--verbose", "--porcelain", "--progress", "--no-progress",
    "--atomic", "--no-atomic", "--tags", "--follow-tags", "--all",
    "--mirror", "--delete", "-d", "--prune", "--thin", "--no-thin",
    "--verify", "--no-verify", "--ipv4", "--ipv6", "-4", "-6",
    "--signed", "--no-signed", "--recurse-submodules",
    "--no-recurse-submodules",
}


class UncertainPush(Exception):
    """A push option this guard does not recognise; parsing cannot be trusted."""

    def __init__(self, option: str) -> None:
        super().__init__(option)
        self.option = option


def block(reason: str, detail: str = "") -> None:
    lines = [f"BLOCKED by {HOOK}", "", f"Reason: {reason}"]
    if detail:
        lines.append(f"Command segment: {detail}")
    lines += [
        "",
        "This guard has no Claude-settable bypass flag or environment variable.",
        "If this operation is genuinely required, stop and ask the owner to run",
        "it themselves or to disable the hook. Treat this as a signal to",
        "reconsider, not an obstacle to route around.",
    ]
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(2)


def git_tokens(tokens: list[str]) -> list[str] | None:
    """Return tokens from `git` onward, skipping env assignments and `env`."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t) or t == "env":
            i += 1
            continue
        break
    if i >= len(tokens):
        return None
    if tokens[i].split("/")[-1] != "git":
        return None
    return tokens[i + 1:]


def subcommand(rest: list[str]) -> tuple[str | None, list[str]]:
    """Skip git's global options and return (subcommand, remaining args)."""
    i = 0
    while i < len(rest):
        t = rest[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t, rest[i + 1:]
    return None, []


def targets_whole_tree(args: list[str]) -> bool:
    """True when a checkout/restore names the entire working tree."""
    if "--" in args:
        paths = args[args.index("--") + 1:]
    else:
        # Trailing operands: refs and pathspecs both land here. A whole-tree
        # token among them is what matters; a specific file is not.
        paths = [a for a in args if not a.startswith("-")]
    return any(p in WHOLE_TREE for p in paths)


def names_main(args: list[str]) -> bool:
    for a in args:
        if a in MAIN_REFS or a.lstrip("+") in MAIN_REFS:
            return True
        if ":" in a and a.split(":", 1)[1] in MAIN_REFS:
            return True
    return False


def provably_non_main(dst: str) -> bool:
    """True only for a literal branch name that cannot be main.

    HEAD, @, hashes, and revision expressions are rejected: the remote branch
    they resolve to may be main, and this guard will not guess.
    """
    if dst in MAIN_REFS or dst in SYMBOLIC_REFS:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", dst):      # looks like a commit hash
        return False
    if re.search(r"[~^@{}:\\\s]", dst):              # revision expression
        return False
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", dst):
        return False
    return dst.split("/")[-1] != "main"


def push_positionals(args: list[str]) -> list[str]:
    """Positional `git push` operands, with option values correctly skipped."""
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            out.extend(args[i + 1:])
            break
        if a.startswith("-"):
            if a.startswith("--") and "=" in a:
                i += 1
                continue
            if a in PUSH_VALUE_OPTS:
                i += 2
                continue
            if a in PUSH_NOVALUE_OPTS:
                i += 1
                continue
            if re.fullmatch(r"-[A-Za-z]+", a) and all(
                f"-{c}" in PUSH_NOVALUE_OPTS for c in a[1:]
            ):
                i += 1
                continue
            raise UncertainPush(a)
        out.append(a)
        i += 1
    return out


def push_destinations(args: list[str]) -> list[str] | None:
    """Refs an explicit refspec would update, or None when there is none.

    A bare forced push has no explicit destination, and resolving where it would
    land requires push.default, upstream tracking, and configured refspecs. This
    hook does not reproduce that; the caller treats None as "block".
    """
    positionals = push_positionals(args)
    refspecs = positionals[1:] if len(positionals) >= 2 else []
    if not refspecs:
        return None
    dests = []
    for spec in refspecs:
        spec = spec.lstrip("+")
        dests.append(spec.split(":", 1)[1] if ":" in spec else spec)
    return dests


def inspect(seg: str, tokens: list[str]) -> None:
    rest = git_tokens(tokens)
    if rest is None:
        return
    sub, args = subcommand(rest)
    if sub is None:
        return

    flags = {a for a in args if a.startswith("-")}
    short = "".join(a[1:] for a in args if re.fullmatch(r"-[A-Za-z]+", a))

    if sub in ("filter-branch", "filter-repo"):
        block("history rewriting is not permitted from inside Claude Code", seg)

    if sub == "reset" and "--hard" in flags:
        block("git reset --hard discards uncommitted work", seg)

    if sub == "clean":
        # Without force git clean refuses to act, and -n is a dry run; every
        # force spelling deletes untracked files.
        if "--force" in flags or "f" in short:
            block("git clean with force deletes untracked files", seg)

    if sub in ("checkout", "switch", "restore") and (
        targets_whole_tree(args)
        or any(a in DISCARD_OPTS for a in args)
        or (sub in ("checkout", "switch") and "f" in short)
    ):
        block(
            "repository-wide checkout/restore discards all working-tree changes",
            seg,
        )

    # Every stash subcommand. push/save/-u/-a remove worktree state;
    # pop/apply overwrite it; drop/clear destroy it; branch relocates it. No
    # autonomous Ion workflow needs any of them, and future stash subcommands
    # are covered by construction.
    if sub == "stash":
        block(
            "git stash can move, apply, or destroy uncommitted worktree state",
            seg,
        )

    if sub == "branch":
        if (
            "--delete" in flags
            or "--move" in flags
            or any(c in short for c in "dDmM")
        ) and names_main(args):
            block("deleting or moving the main branch", seg)

    if ("--force" in flags or "f" in short) and names_main(args):
        block("git branch --force moves main to another commit", seg)

    if sub == "checkout" and "B" in short and names_main(args):
        block("git checkout -B main resets main to another commit", seg)

    if sub == "switch" and "C" in short and names_main(args):
        block("git switch -C main resets main to another commit", seg)

    if sub == "update-ref" and names_main(args):
        if "--delete" in flags or "d" in short:
            block("deleting refs/heads/main", seg)
        block("git update-ref moves main to another commit", seg)

    if sub == "push":
        # Deleting a remote branch:
        # `git push origin :main`
        # `git push --delete origin main`
        if any(a.startswith(":") and a[1:] in MAIN_REFS for a in args) or (
            "--delete" in flags and names_main(args)
        ):
            block("deleting the remote main branch", seg)

        # Any `+` refspec forces, whatever it names.
        forced = (
            "--force" in flags
            or "f" in short
            or any(a.startswith("--force-with-lease") for a in args)
            or any(a.startswith("+") for a in args if not a.startswith("-"))
        )

        if forced:
            try:
                dests = push_destinations(args)
            except UncertainPush as uncertain:
                block(
                    "a forced push carrying the unrecognised option "
                    f"'{uncertain.option}': its arguments could not be parsed "
                    "confidently, so the destination is unknown",
                    seg,
                )

            if dests is None:
                block(
                    "a forced push with no explicit refspec: the destination "
                    "depends on push.default and upstream configuration, so it "
                    "cannot be determined reliably. Name the destination "
                    "explicitly if this push is intended.",
                    seg,
                )

            for dst in dests:
                if dst in MAIN_REFS:
                    block("force-pushing main rewrites published history", seg)

                if not provably_non_main(dst):
                    block(
                        f"a forced push to '{dst}', whose remote branch cannot "
                        "be established from the command and may be main. Name "
                        "the destination branch explicitly.",
                        seg,
                    )


OPERATORS = {";", "&&", "||", "|", "&", "\n"}


def split_segments(command: str) -> list[list[str]] | None:
    """Tokenise into command segments, respecting quotes.

    Splitting on `;` with a regex would cut through quoted text -- the `;` in
    `git commit -m "a; b"` is data, not a separator -- producing an unparseable
    fragment and a false block. Returns None if the command as a whole cannot be
    lexed.
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


def main() -> None:
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except Exception:
        block(
            "the PreToolUse payload could not be parsed, so the command "
            "could not be inspected"
        )

    command = payload.get("tool_input", {}).get("command")

    if not isinstance(command, str) or not command.strip():
        block(
            "no inspectable command was present in tool_input, so this "
            "Bash call could not be checked"
        )

    segments = split_segments(command)

    if segments is None:
        # Only fail closed where it matters: a command that never mentions git
        # is not this guard's concern.
        if re.search(r"(^|[^A-Za-z0-9_])git([^A-Za-z0-9_]|$)", command):
            block(
                "a git command could not be tokenised, so it could not be "
                "inspected",
                command,
            )
        raise SystemExit(0)

    for tokens in segments:
        if tokens:
            inspect(" ".join(tokens), tokens)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
