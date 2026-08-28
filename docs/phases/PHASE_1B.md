# Phase 1B — Areas, Goals, Projects & Milestones

## Objective

Turn the Phase 1A organizer schema into a useful deterministic local hierarchy:
Areas contain Goals, Goals may contain Projects, both owner types have ordered
Milestones, and Tasks may link independently to a Goal and a Project.

## Scope

- Area, Goal, Goal Milestone, Project, and Project Milestone create/edit/list.
- Entity-specific lifecycle, archive, soft Trash, restore, revision conflicts,
  and transactional compact audit metadata.
- Direct foreign-key relationship assignment with archived/trashed target
  rejection and direct-only Trash blockers.
- Canonical owner-scoped Milestone positions through migration
  `0003_milestone_ordering`.
- Derived Goal/Project summaries, Project current Milestone, next actions, and
  attributable recent activity without duplicate canonical fields.
- Explicit Task Goal/Project relationship mutation while preserving the Task
  vertical slice.
- Fixed authenticated FastAPI organizer routes and fixed Rust/Tauri commands
  with narrow renderer-safe product errors.
- Milestone-local Areas & Goals, Projects, and Tasks workspaces with canonical
  pre-mount hydration, explicit relationship controls, and reusable visual
  Milestone management.

## Durable behavior

- Archive changes only the selected record and never cascades.
- Descendants keep independent lifecycle and remain contextually visible.
- Trash is blocked only by direct non-trashed dependents named by ADR 0012.
- Goal and Project relationship fields remain optional; Task Goal and Project
  links remain independently nullable.
- Milestone ownership is immutable during Phase 1B. Trash preserves position,
  restore returns to it, and reorder changes only non-trashed siblings.
- Progress, current Milestone, next actions, and activity are projections over
  canonical records and audit metadata, not stored summaries.

## Explicit exclusions

Phase 1B excludes Home, Today, Calendar, scheduling, search, AI, integrations,
adaptive progression, generic relationships, generic Undo, automatic Trash
purge, mobile, cloud, LAN, remote access, and final application navigation or
visual polish.

## Acceptance

- A fresh database and a populated `0002` database migrate losslessly to
  `0003`; downgrade/re-upgrade preserves all Milestone rows.
- Organizer mutations are revision-aware and audit atomically; failures and
  no-ops do not mutate or audit.
- Archive does not mutate descendants, and direct Trash blockers return safe
  structured counts.
- Milestone order, lifecycle timestamps, derived projections, and Task
  relationship independence are covered by temporary-database tests.
- All production endpoints remain authenticated and production CORS remains
  disabled.
- Renderer code receives only fixed product operations and typed product DTOs;
  the sidecar port, launch credential, and generic HTTP capability remain
  Rust-owned.
- Phase 1A Task tests and the repository validation gate remain green.
