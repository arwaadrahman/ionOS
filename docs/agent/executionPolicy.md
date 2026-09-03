# Ion Agent Execution Policy

**This file is now an index, not an authority.** Its rules were moved to owners
that can actually enforce or canonically state them, so that each rule has
exactly one home. Nothing was deleted without being moved first.

Existing links to this path still resolve; the file is retained deliberately.

## Where execution policy now lives

| Former section | Owner |
| --- | --- |
| Autonomous execution | [`AGENTS.md`](../../AGENTS.md) — scope, no silent change, smallest change, staging restraint, tests with behavior changes |
| Owner-level stop conditions | [`AGENTS.md`](../../AGENTS.md) — the single canonical list |
| Repository data safety | [`AGENTS.md`](../../AGENTS.md) — synthetic-data-only, never commit secrets |
| Git and database safety | Four layers, none of which is a shell interpreter — see below; plus [`.claude/rules/migrations-and-db.md`](../../.claude/rules/migrations-and-db.md) |
| Phase 0C trust boundary | [`SECURITY.md`](../SECURITY.md) and [`ARCHITECTURE.md`](../ARCHITECTURE.md) — this file only restated them |
| Canonical mutation and secondary refresh | [`ARCHITECTURE.md`](../ARCHITECTURE.md) § Accepted principles |
| Transactional invariants (revision, lifecycle, audit, Trash) | [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`DATA_MODEL.md`](../DATA_MODEL.md) |
| Validation procedure and evidence report | `.claude/skills/verify` — including its `PACKAGE / RUNTIME` section |
| When packaged-runtime evidence is required | [`AGENTS.md`](../../AGENTS.md) item 7 |
| Generated-artifact safety | `.claude/skills/verify` → `scripts/verify/diff-audit.sh` |
| Compact final report | `.claude/skills/verify` |
| Claude-specific context and working behaviour | [`CLAUDE.md`](../../CLAUDE.md), [`.claude/rules/`](../../.claude/rules/) |
| Phase scope and acceptance detail | the current document under [`docs/phases/`](../phases/) and the relevant ADRs |

## What actually enforces Git and data safety

Stated precisely, because overstating it would be worse than stating nothing:

| Layer | What it genuinely enforces |
| --- | --- |
| Native sandbox | Hard filesystem boundary. Writes are confined to the session's own project directory; `.claude/**`, `scripts/verify/**`, `AGENTS.md`, `CLAUDE.md` and the owner's production Ion data are denied outright, whatever program attempts them. |
| Worktree isolation | Containment for unattended implementation. Damage stays inside a disposable worktree and cannot reach the primary checkout. |
| Git hook | **Semantic defence-in-depth only.** It recognises common destructive spellings — `reset --hard`, forceful `clean`, whole-tree `checkout`/`restore`, every `stash` form, force-push and moves against `main`. It is **not** a shell interpreter: abbreviated long options, `bash -c` and similar wrappers, and raw `rm`/`find` deletion are outside its reach. |
| Owner authorization | The only gate on commit, push, merge, and canonical history. |

Raw worktree destruction is **not** prevented by any of these. It is tolerable
only because unattended implementation happens in a disposable worktree.

## Where autonomous implementation runs

**Autonomous implementation runs in a native Claude Code isolated worktree. The
primary checkout is reserved for owner-controlled review, checkpoints, and
integration.** This document is that rule's single home; other files point here
rather than restating it.

The boundary is an execution model, not a parsing problem. Inside a disposable
worktree, damage is a recoverable task failure — the worktree is thrown away —
so the guards do not need to recognise every shell spelling of a destructive
command. Outside it, the sandbox confines writes to the session's own project
directory, which is why a worktree session cannot reach the primary checkout.

| | Primary checkout | Isolated worktree |
| --- | --- | --- |
| Autonomous implementation | no | yes, within an approved bounded task |
| Source and test edits | owner-directed | autonomous |
| Ordinary verification | yes | yes |
| Commit, push, merge, history | owner-authorized only | owner-authorized only |

New worktrees branch from the current phase-branch HEAD (`worktree.baseRef:
"head"`), not from the default branch.

### Stop and wait for the owner

Product behaviour is materially ambiguous · an architecture or security boundary
would change · an unapproved schema or migration becomes necessary · real Ion
production data would be touched · real Google owner interaction is required ·
the approved scope must materially expand · canonical Git history, commit, push,
merge, or a destructive primary-checkout action would be required.

### Do not stop for

Source edits · test additions and updates · routine test failures · debugging
inside approved scope · formatting and lint fixes · build failures ·
verification reruns · ordinary implementation iteration.

## Notes

- Reading this file is no longer required for any task. `CLAUDE.md` states that
  explicitly.
- Authority order, and the separation of automated verification from owner
  acceptance and from commit authorization, are stated once in `AGENTS.md`.
- Hard safety is enforced by hooks rather than described in prose, because a
  rule that must never be skipped should not depend on an agent reading it.
