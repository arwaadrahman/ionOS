# Architecture

## Status

This is a **Baseline** document. It records accepted product principles and
separately labels proposed implementation choices.

## Accepted principles

- Ion is local-first. Its authoritative data lives on the user's Mac; cloud
  services are integrations, not the primary datastore.
- macOS is the active local-only platform. Mobile support is TBD and requires a
  dedicated mobile/security architecture review plus explicit owner approval.
- One canonical record may appear in multiple contextual views. Derived search,
  indexing, and cache structures must be rebuildable.
- Structured records, Markdown knowledge, and original sources have distinct
  owners. An LLM is not a memory system.
- The repository contains only synthetic data and configuration examples; real
  user data remains local and outside the repository.

## Proposed implementation baseline — subject to prototyping

| Concern            | Direction                                                   |
| ------------------ | ----------------------------------------------------------- |
| Desktop UI         | React + TypeScript in Tauri                                 |
| Application logic  | Python + FastAPI                                            |
| Structured records | SQLite                                                      |
| Knowledge          | Obsidian-compatible local Markdown vault                    |
| Future search      | Local text search, then evaluated local retrieval           |
| Core graphics      | Raw Three.js `WebGLRenderer` behind a React-owned controller |

## Phase 0C production runtime

The packaged macOS prototype uses a PyInstaller one-file Python sidecar owned
by the Rust/Tauri backend. Renderer code invokes narrow Ion-owned commands
only. Rust generates a per-launch session credential, supplies it over the
sidecar's private stdin bootstrap channel, and makes authenticated HTTP calls
to the service's self-owned `127.0.0.1:0` socket. Production FastAPI does not
enable CORS and the renderer receives neither port nor credential.

The sidecar lifecycle is one child only: bounded readiness, exit observation,
graceful shutdown, then forced fallback. SQLite, settings, and logs remain
outside the application bundle in Application Support. See ADRs 0008 and 0009.

## Development boundary

Phase 0B retains its local development foundation: npm workspace, Tauri/React
shell, direct loopback-only FastAPI service, SQLite migration mechanism,
settings, logging, quality tooling, and synthetic fixtures. Production
packaging, supervision, and authentication are intentionally a separate
runtime mode.

## Phase 1A organizer path

Product operations use fixed Ion-owned Tauri commands in development and
production. Rust owns the authenticated production request and a validated
development loopback target; renderer code receives product DTOs only. The
Python service owns UUID generation, SQLAlchemy Core transactions, Alembic
migration-before-readiness, and SQLite canonical state. The production
database is `ion.sqlite3`; development uses `ion-development.sqlite3`.

## Phase 1B organizer domain

Phase 1B preserves the same product boundary while adding fixed Area, Goal,
Project, Milestone, and Task-relationship operations. Python owns explicit
entity services, optimistic concurrency, direct Trash blockers, transactional
audit metadata, and derived organizer projections. Archive never cascades and
no generic lifecycle, relationship, proxy, or command framework is introduced.

## Phase 1C Today path

Phase 1C adds one canonical `task_day_plans` relation and a deterministic Today
projection. Python validates the Mac local civil date against the supplied IANA
timezone, owns revision-aware planning transactions, and derives deadline,
attention, yesterday, and completion sections from canonical Tasks. Planning
does not mutate Task lifecycle and does not create scheduled time.

React hydrates Today with the other canonical startup records before mounting
the workspace. It recomputes local date/timezone at the next local midnight and
on focus or return to visibility. Rust exposes only fixed Today commands over
the inherited authenticated request primitive. The renderer still receives no
service origin, port, session credential, or generic HTTP capability.

The right pane is an explicit pre-Calendar boundary: it may render canonical
deadline markers but cannot render a timeline, appointments, occupied/free
time, or FocusSession state.

## Phase 1D Home and Ion Core path

Phase 1D adds one read-only Python Home projection over existing organizer and
Today records. Rust exposes it only as fixed `get_home`; the WebView still has
no generic HTTP, port, credential, filesystem, or shell access. Home performs
no writes and creates no audit records.

The desktop derives a structural graph and versioned hash-based positions in
memory. Raw Three.js owns one lazy WebGL2 renderer with explicit controller
lifecycle, while React owns product selection, navigation, summary cards, and
fallback UI. No graph/layout state is stored. React Three Fiber, force/physics
layout, inferred edges, Explore modes, and AI remain outside this boundary.

## Phase 1E deterministic command-search path

Phase 1E builds one ephemeral desktop command list from the five implemented
destinations and the existing authenticated Home/Core projection. Opening the
palette refreshes through fixed `get_home`; the WebView receives the same DTO
and gains no generic request, service address, credential, filesystem, or shell
capability.

Unicode-normalized lexical ranking and stable tie-breaking run locally in
TypeScript. The database, Python service, and Rust command surface gain no
search table, index, endpoint, or mutation. SQLite FTS, persisted recents,
semantic/vector retrieval, QMD, conversational search, and AI remain deferred.

## Phase 1F recovery and history path

Phase 1F adds one fixed authenticated `get_recovery` command and read-only
`GET /v1/recovery` projection. Python reads the existing canonical organizer
tables and append-only audit metadata to return bounded Trash and recent
direct-human action summaries; it performs no mutation or audit write. Rust
continues to own the authenticated request. The renderer dispatches an explicit
selected-record restore only through the existing entity-specific commands and
never receives a port, credential, generic HTTP capability, filesystem, or
shell access.

Recovery is contextual through the existing command palette, preserving the
Home-first five-destination primary navigation. Generic Undo, event sourcing,
snapshots, version history, automatic purge, and cascades remain deferred.

## Phase 1G macOS application lifecycle

Phase 1G enables Tauri's built-in tray support and keeps all fixed menu actions,
window visibility/focus, macOS reactivation, explicit Quit, and single-instance
enforcement in Rust. A process-held advisory lock in Application Support is
acquired before sidecar startup, so a forced second desktop process cannot own
a duplicate backend. Closing either configured window hides it; Quit retains
the existing bounded sidecar shutdown path.

The fixed quick-capture WebView creates one canonical unlinked Task through the
existing `create_task` command and uses only bounded local Tauri events for
secondary main-window freshness. It receives no generic HTTP, filesystem,
shell, process, port, or credential authority. No daemon, launch agent, schema,
service endpoint, or data owner is added.

## Phase 2A Google Calendar read-sync path

Rust owns the complete Google credential and network boundary: Desktop OAuth
authorization URL construction, S256 PKCE and state, the ephemeral
`127.0.0.1` callback listener, system-browser launch, authorization-code
exchange, macOS Keychain refresh-token access, memory-only access tokens,
refresh, CalendarList discovery, Events pagination, retry/backoff, revocation,
and all Google HTTPS. Python and React receive no Google token, OAuth code, or
PKCE verifier. Real client configuration lives outside the repository in the
Application Support path shown by the setup UI.

Rust sends only sanitized CalendarList/Event DTOs through fixed authenticated
local routes. Python owns account/calendar metadata, the independent
enabled-in-Ion selection, sync generations and tokens, duplicate-safe
reconciliation, canonical CalendarBlock transactions, and compact automated
audit records. The renderer receives only fixed Tauri commands and safe status
DTOs; it receives neither the Keychain locator nor any generic provider,
network, service, filesystem, shell, or process capability.

Each enabled calendar starts with an unexpanded, deletion-inclusive full sync,
then reuses a per-calendar incremental token. One generation spans every
provider page. HTTP 410 abandons the incremental generation and begins a safe
full generation; full completion cancels unseen provider records without
deleting their Ion-only metadata. Provider event ID is the reconciliation key;
iCalUID remains separate. Recurrence stores masters and explicit exceptions,
while generated occurrences remain derived.

Startup hydration reads cached canonical blocks without Google. A connected
account then gets one background-in-process sync attempt; later foreground
attempts are rate-bounded to five minutes and manual sync is explicit. This
adds no daemon, launch agent, webhook, cloud relay, LAN/mobile boundary, Google
event write, generic integration framework, or Python provider SDK. See ADR
[0018](decisions/0018-google-calendar-read-sync-foundation.md).

## TBD

See ADRs [0004](decisions/0004-macos-local-trust-boundary.md),
[0005](decisions/0005-phase-0b-toolchain-baseline.md),
[0006](decisions/0006-local-api-service-boundary.md), and
[0007](decisions/0007-sqlite-access-and-migrations.md) for accepted Phase 0B
implementation decisions.
