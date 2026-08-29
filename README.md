# Ion OS

Ion OS is a private, local-first personal operating system for reducing
administrative overhead while preserving user control. Its active platform is
macOS; mobile support is TBD pending a dedicated security architecture review.

## Status

Current phase: **Phase 1 — Ion Core Personal Organizer**
Current milestone: **Phase 1E — Deterministic Command Search**

Phase 0 established the secure local runtime. Phase 1A added the canonical
organizer schema and Task vertical slice. Phase 1B makes Areas, Goals, Projects,
Milestones, and Task relationships useful. Phase 1C adds persistent human Today
planning, deterministic attention/deadline context, and a truthful pre-Calendar
split workspace while retaining the same Rust-owned authenticated production
service boundary. Phase 1D makes Home the default, adds one read-only organizer
projection, and introduces a deterministic raw Three.js Ion Core without graph
persistence or expanded renderer authority. Phase 1E adds a compact local
`⌘K` command palette over current destinations and canonical organizer records
without a stored index, new dependency, or trust-boundary change.

## Start here

- [Agent guide](AGENTS.md)
- [Project context](docs/projectContext.md)
- [Master Specification](docs/PRODUCT_SPEC.md)
- [Phase 1E](docs/phases/PHASE_1E.md)
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
`npm exec --workspace @ion/desktop -- tauri build`. This produces a local unsigned
or ad-hoc-signed proof only; signing, notarization, installers, and updates are
out of scope. The packaged service receives its launch credential over stdin
and does not require end-user Python or uv.

The API binds only to `127.0.0.1`. Its non-secret development settings live
outside the repository at `~/Library/Application Support/Ion OS/config.toml`;
runtime SQLite databases and logs are also kept there. `ION_DATA_DIR` and
`ION_API_PORT` are narrow local/test overrides, not a secret-management design.
