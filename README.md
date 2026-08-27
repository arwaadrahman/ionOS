# Ion OS

Ion OS is a private, local-first personal operating system for reducing
administrative overhead while preserving user control. Its active platform is
macOS; mobile support is TBD pending a dedicated security architecture review.

## Status

Current phase: **Phase 0 — Repository + Engineering Foundation**
Current milestone: **Phase 0C — Production Local Runtime & Security Prototype**

Phase 0B established a minimal local engineering foundation: React + TypeScript
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

Phase 0C adds a bounded ARM64 packaged-sidecar proof: Rust owns an
authenticated production loopback connection to a self-contained Python
service. Development retains the direct Phase 0B loopback workflow.

See the Phase 0B and Phase 0C records for commands and acceptance criteria.

## Local development

Prerequisites are Node 24, Rust/Cargo with Apple Command Line Tools, and uv.
Install project dependencies with `npm install` and `uv --directory apps/api
sync --dev`; uv provisions the project's Python 3.13 runtime. Then use:

- `npm run dev` — run the loopback API and Tauri desktop development shell.
- `npm run validate` — run all lint, format-check, and test commands.

## Phase 0C ARM64 local bundle proof

On Apple Silicon macOS, regenerate the ignored packaged Python sidecar with
`apps/api/packaging/build-sidecar.sh`, then run
`npm --workspace @ion/desktop run tauri:build`. This produces a local unsigned
or ad-hoc-signed proof only; signing, notarization, installers, and updates are
out of scope. The packaged service receives its launch credential over stdin
and does not require end-user Python or uv.

The API binds only to `127.0.0.1`. Its non-secret development settings live
outside the repository at `~/Library/Application Support/Ion OS/config.toml`;
runtime SQLite databases and logs are also kept there. `ION_DATA_DIR` and
`ION_API_PORT` are narrow local/test overrides, not a secret-management design.
