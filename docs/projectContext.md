# Project Context

## Goal and audience

Ion is a private, local-first personal operating system for a primary user who
wants less administrative overhead without surrendering control. It captures,
connects, plans, and reviews life information while treating direct human
actions as authoritative.

## Current development state

- **Phase:** Phase 2 — Calendar
- **Milestone:** Phase 2A — Google Account + Calendar Sync Foundation
- **In scope:** native Google OAuth, secure Keychain token ownership, multiple
  accounts, CalendarList discovery and Ion-owned selection, canonical
  CalendarBlocks, per-calendar full/incremental read sync, offline cached
  state, and minimal setup/status UI under the Rust-owned boundary.
- **Out of scope:** Google event writes/deletes, Tasks, Gmail, push/webhooks,
  Phase 2B calendar interaction/scheduling, Phase 2C conflict resolution, AI,
  free-busy planning,
  FocusSession, DailyReview, WeeklyPlan, semantic/conversational search,
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
restrained Calendar setup/status surface while full calendar interaction,
Explore, semantic search, and AI remain deferred.

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

## Canonical documents

- [Master Specification](PRODUCT_SPEC.md)
- [Research playbook](research/ionResearch.md)
- [Task router](agent/taskRouter.md)
- [Approved Ion reference snapshot](references/approvedReferences.md)
- [Decision index](decisions/README.md)
- [Active phase](phases/PHASE_2A.md)

The approved-reference snapshot derives from `projectReference.md` version
**1.1.0** (updated 2026-08-27). Project-local decisions override it.
