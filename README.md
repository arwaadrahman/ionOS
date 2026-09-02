# Ion OS

Ion OS is a private, local-first personal operating system for reducing
administrative overhead while preserving user control. Its active platform is
macOS; mobile support is TBD pending a dedicated security architecture review.

## Status

Current phase: **Phase 2 — Calendar**
Current milestone: **Phase 2C-5 — Google Calendar recurrence writes**

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
Phase 1F adds a bounded contextual Recovery workspace for current Trash and
concise direct-human organizer history, using only existing entity-specific
restore operations without Undo, snapshots, or cascades.
Phase 1G adds a native fixed menu-bar presence, minimal canonical Task capture,
close-to-hide/Dock reactivation behavior, and one desktop/sidecar process owner
without a daemon, migration, or new dependency.
Phase 1H validates and hardens the complete Phase 1 organizer and packaged
runtime flow.
Phase 2A adds Rust-owned Google Desktop OAuth and Keychain credentials,
multi-account CalendarList discovery, independent Ion selection, canonical
offline CalendarBlocks, and full/incremental read sync without enabling Google
event writes.
Phase 2B adds the primary read-only Day, 3 Day, Week, Next 7 Days, and Month Calendar,
bounded recurrence/exception rendering, Ion-local categories and hide/restore,
adaptive density, and truthful CalendarBlock occupancy and free gaps in Today
without scheduling Tasks or writing Google data.
Phase 2C-2 adds deliberate write re-consent and idempotent local-first event
creation. Phase 2C-3 adds bounded explicit-save title/time editing and reviewed
timed move/resize for eligible ordinary attendee-free events, with durable
offline intent and explicit ETag conflicts.
Phase 2C-4 adds explicitly confirmed single-event deletion with conditional
`events.delete`, deterministic ambiguity/404 reconciliation, and wholly local
cancellation of provider-unattempted creates.
Phase 2C-5 adds bounded daily/weekday/weekly/monthly/yearly recurrence create
and edit, exact master-plus-original-start occurrence resolution, deliberate
This occurrence / Entire series mutation scopes, occurrence cancellation, and
conditional whole-series deletion while keeping raw RRULE and This and
following unavailable.

## Start here

- [Agent guide](AGENTS.md)
- [Project context](docs/projectContext.md)
- [Master Specification](docs/PRODUCT_SPEC.md)
- [Phase 2C](docs/phases/PHASE_2C.md)
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
