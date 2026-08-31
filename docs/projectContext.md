# Project Context

## Goal and audience

Ion is a private, local-first personal operating system for a primary user who
wants less administrative overhead without surrendering control. It captures,
connects, plans, and reviews life information while treating direct human
actions as authoritative.

## Current development state

- **Phase:** Phase 2 — Calendar
- **Milestone:** Phase 2C-1 write foundation implemented; owner acceptance
  pending
- **In scope:** a primary read-only Calendar over cached canonical
  CalendarBlocks; Day, consecutive 3 Day, Monday-first Week, rolling Next 7
  Days, and Monday-first Month views; bounded recurrence/exception projection;
  unified multi-account rendering; progressive calendar management with local
  hide/restore;
  Ion-owned event categories, semantic colors/filters, adaptive event detail,
  local vertical density and pane-width responsive view selection; mutually
  exclusive source/filter drawers; a provider-read-only event inspector; and
  truthful CalendarBlock occupancy/free gaps in Today.
- **Foundation scope:** migration `0007` now provides the durable typed outbox,
  safe capability evidence, deterministic create ID, retry/restart state,
  compact audit, fixed local routes, one read-only Tauri capability command,
  and unsent Rust provider-request/classification helpers. Existing accounts
  remain read-only and no Google event mutation is reachable.
- **Out of scope:** Google event writes/deletes, Google Tasks, Gmail,
  push/webhooks, Phase 2C create/edit/delete UI or provider mutation, OAuth
  re-consent execution until separately authorized, Task auto-scheduling, AI, provider free/busy
  planning, FocusSession, DailyReview, WeeklyPlan, semantic/conversational search,
  persisted search indexes/history, generic Undo/version history, automatic
  purge, inferred relationships, global shortcuts requiring a new plugin,
  menu-bar AI/focus/planning, final Core Explore modes, mobile, and remote/LAN
  access.

## Proposed stack baseline — subject to prototyping

- React + TypeScript in Tauri, npm workspaces, and Node 24 LTS.
- Python 3.13 managed with uv; FastAPI binds to loopback only during
  development.
- SQLite with SQLAlchemy 2 Core and Alembic; Markdown remains the future owner
  for durable prose knowledge.
- Production sidecar lifecycle and per-launch local-process authentication are
  governed by ADRs 0008 and 0009. Signing/notarization remain deferred.

## Durable ownership boundaries

| Owner                            | Responsibility                                      |
| -------------------------------- | --------------------------------------------------- |
| SQLite                           | Canonical structured records and cached integrations |
| Google Calendar                  | Synchronized provider event fields                  |
| macOS Keychain                   | Persistent Google refresh tokens                    |
| Rust memory                      | Google access tokens and OAuth flow material        |
| Markdown                         | Durable prose knowledge                             |
| Original source files            | Immutable evidence                                  |
| Search, indexes, vectors, caches | Rebuildable derived data                            |
| AI/LLM                           | Temporary reasoning context; never canonical memory |

## Product character

`PROFILE-ION` is a calm operational system with one unmistakable Core:
dark-first, near-black and neutral-dominant, with restrained violet energy and
a premium technical/editorial tone. Phase 1D established the first operational
Core baseline; Phases 1E and 1F add compact command search and contextual
recovery/history; Phase 1G adds a quiet native menu-bar presence and focused
Task capture; Phase 1H hardens the complete Phase 1 flow. Phase 2A adds a
restrained Calendar read-sync foundation. Phase 2B adds the primary read-only
Calendar and truthful CalendarBlock occupancy in Today while provider writes,
Task scheduling, Explore, semantic search, and AI remain deferred.

Design/motion ladder: process guidance (`IMPECCABLE`, `EMIL-MOTION`); CSS for
simple motion; Motion for React for normal stateful UI; Three.js only for a
justified spatial Core. These are future owners/guidance, not current runtime
dependencies. Motion must be purposeful, reduced-motion-aware, and
performance-conscious.

## Non-negotiables and approval gates

- Repository data is synthetic only; real databases, vaults, and secrets stay
  outside the repository.
- The active trust boundary is macOS-local only. Mobile support is deferred
  pending a dedicated mobile/security review and explicit owner approval.
- Google refresh tokens stay in macOS Keychain, access tokens remain
  Rust-memory-only, and provider tokens never enter React, Python, SQLite, or
  logs.
- No agent silently changes major architecture, dependencies, security/privacy,
  data ownership, authentication, authorization, or canonical requirements.
- Destructive actions, publication, and external side effects require approval.
- Current phase boundaries are binding.
- External coding agents retain their own authentication and lifecycle. Any
  future bridge is explicit, allowlisted, Rust-owned, and never grants generic
  renderer shell/process authority; developer telemetry is Private Local.
- Persistent intelligence does not require persistent computation. Heavy
  models, indexing, visualization, and repository analysis remain on-demand and
  baseline resource behavior follows the
  [Performance and resource policy](PERFORMANCE.md).

## Canonical documents

- [Master Specification](PRODUCT_SPEC.md)
- [Research playbook](research/ionResearch.md)
- [Task router](agent/taskRouter.md)
- [Approved Ion reference snapshot](references/approvedReferences.md)
- [Decision index](decisions/README.md)
- [Performance and resource policy](PERFORMANCE.md)
- [External Developer Agent Bridge
  decision](decisions/0020-external-developer-agent-bridge.md)
- [Accepted Phase 2C gate](phases/PHASE_2C.md)
- [Accepted Calendar write
  decision](decisions/0021-google-calendar-write-outbox-and-conflicts.md)

The approved-reference snapshot derives from `projectReference.md` version
**1.1.0** (updated 2026-08-27). Project-local decisions override it.
