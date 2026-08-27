# ADR 0005: Phase 0B toolchain baseline

**Status:** Accepted
**Date:** 2026-08-27

## Context

Phase 0 needs one reproducible, low-complexity toolchain for a Tauri React
desktop application and its local Python service.

## Decision

Use npm workspaces with Node 24 LTS for JavaScript tooling. Use uv-managed
Python 3.13 for the local service. TypeScript quality is owned by ESLint,
Prettier, and Vitest; Python quality is owned by Ruff and pytest; Rust/Tauri
quality uses Cargo's built-in formatter, Clippy, and test runner.

## Consequences

The repository commits `package-lock.json`, `pyproject.toml`, and `uv.lock`.
Tooling stays project-local; no machine-wide package manager or Python runtime
is part of Ion's required installation state.

## Alternatives considered

- pnpm/Yarn workspaces: not selected because npm is available and adequate.
- Plain `venv` plus pip: not selected because uv provides reproducible Python
  resolution and interpreter management with less project-specific scripting.
- Multiple overlapping lint/format tools: not selected to keep ownership clear.

## References

- [Phase 0B](../phases/PHASE_0B.md)
- [Architecture](../ARCHITECTURE.md)
