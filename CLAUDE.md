# Ion OS — Claude Code

@AGENTS.md

The import above is load-bearing: `AGENTS.md` owns repository authority, scope,
and data rules for every agent, and Claude Code does not read it on its own.
This file adds Claude-specific mechanics only and never restates it.

Ion is a private, local-first personal operating system for one owner. React +
TypeScript in Tauri, a Rust core owning OAuth and provider HTTP, and a Python
3.13 / FastAPI sidecar over SQLite bound to loopback.

## Context loading

**Do not load `docs/agent/taskRouter.md`, `docs/agent/executionPolicy.md`, or
the full `docs/PRODUCT_SPEC.md` by default.** They are reference, not per-task
context.

Read the **full `docs/PRODUCT_SPEC.md`** when starting or revising a phase,
changing architecture, or making broad product or engineering recommendations.
Otherwise load only what the task needs:

| Task                            | Load                                                                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Phase or architecture work      | the current phase document under `docs/phases/`, `docs/ARCHITECTURE.md`, the relevant ADR(s); plus the full spec per the rule above |
| Calendar interaction behavior   | `docs/CALENDAR_BEHAVIOR.md` first                                                                                                   |
| UI or design                    | `docs/DESIGN_SYSTEM.md`                                                                                                             |
| Security, data model, migration | `docs/SECURITY.md`, `docs/DATA_MODEL.md`, the relevant ADR(s)                                                                       |
| Agent or tooling questions      | `docs/agent/taskRouter.md` (reference)                                                                                              |
| Routine implementation          | nothing extra                                                                                                                       |

`.claude/rules/` carries short path-scoped pointers that load automatically when
you touch Calendar, provider-write, migration, or renderer code. Use them to
identify when a canonical document matters; read the document itself for what it
says.

## Working method

- Autonomous implementation runs in a native Claude worktree; the primary
  checkout is reserved for owner-controlled review, checkpoints, and
  integration. `docs/agent/executionPolicy.md` is that rule's single home.
- Substantial or multi-step work → **Plan Mode** first, then implement against
  the approved plan.
- After implementing → run the **`verify`** skill. Do not report readiness from
  memory or from a green test line alone.
- Inspect **actual git state** (`git status`, `git log -1`, `git diff`) for any
  substantial task. Never trust a branch name written in `CLAUDE.local.md`.
- Prefer the smallest change consistent with accepted architecture. Update tests
  and behavior docs in the same pass.

## Commands

|                |                                                                             |
| -------------- | --------------------------------------------------------------------------- |
| Everything     | `npm run validate` (lint + format check + all tests)                        |
| Python         | `uv --directory apps/api run pytest`                                        |
| TypeScript     | `npm --workspace @ion/desktop run test`                                     |
| Rust           | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`              |
| Full-loop seam | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml -- --ignored` |

## Runtime data safety

Rebuild and development work uses
`ION_DATA_DIR="$HOME/Library/Application Support/Ion OS Rebuild"`.

`apps/api/ion_api/settings.py` defaults to the owner's **production** directory
whenever `ION_DATA_DIR` is unset, so always set it explicitly before running
`python -m ion_api`, `npm run dev`, or a Tauri build. `pytest` is safe — it uses
isolated temporary directories.

## Hooks

Three hooks block destructive git operations, writes to the owner's production
Ion data, and modification of the guards themselves. They have no
Claude-settable bypass flag or environment variable. If an exceptional
destructive action is genuinely needed, stop and ask the owner to perform it
themselves or to disable the hook. Treat a block as a signal to reconsider, not
an obstacle to route around.

They are conservative by design and will sometimes refuse a harmless command —
`sed`, `python3`, and other unenumerated programs are blocked from touching
guard files, and writer-shaped text is blocked even when inert. That is accepted
policy, not a defect. Inspect guard files with `cat`, `head`, `grep`, `rg`, or
`shasum`.

## Local notes

`CLAUDE.local.md` (gitignored) holds ephemeral machine-local notes only. It is
never authoritative: accepted phase, product requirements, architecture
decisions, owner acceptance, and durable blockers belong in tracked docs.
