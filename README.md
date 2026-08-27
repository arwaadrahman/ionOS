# Ion OS

Ion OS is a private, local-first personal operating system for reducing
administrative overhead while preserving user control. Its active platform is
macOS; mobile support is TBD pending a dedicated security architecture review.

## Status

Current phase: **Phase 0 — Repository + Engineering Foundation**
Current milestone: **Phase 0B — Executable Engineering Foundation**

Phase 0B establishes a minimal local engineering foundation: React + TypeScript
in Tauri, a loopback-only Python/FastAPI service, SQLite migration
infrastructure, settings, logging, tests, and synthetic fixtures. It contains
no Phase 1 product behavior, integrations, AI, cloud services, or mobile code.

## Start here

- [Agent guide](AGENTS.md)
- [Project context](docs/projectContext.md)
- [Master Specification](docs/PRODUCT_SPEC.md)
- [Phase 0B](docs/phases/PHASE_0B.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision index](docs/decisions/README.md)

The Master Specification is canonical. Accepted ADRs and repository-local
documentation govern implementation; research and reference cards are
supporting context.

## Privacy

This public repository must never contain real personal Ion data, local user
databases, vault content, or credentials. Any future fixtures, demos, and
screenshots must be synthetic.

See the Phase 0B record for local developer commands and acceptance criteria.

## Local development

Prerequisites are Node 24, Rust/Cargo with Apple Command Line Tools, and uv.
Install project dependencies with `npm install` and `uv --directory apps/api
sync --dev`; uv provisions the project's Python 3.13 runtime. Then use:

- `npm run dev` — run the loopback API and Tauri desktop development shell.
- `npm run validate` — run all lint, format-check, and test commands.

The API binds only to `127.0.0.1`. Its non-secret development settings live
outside the repository at `~/Library/Application Support/Ion OS/config.toml`;
runtime SQLite databases and logs are also kept there. `ION_DATA_DIR` and
`ION_API_PORT` are narrow local/test overrides, not a secret-management design.
