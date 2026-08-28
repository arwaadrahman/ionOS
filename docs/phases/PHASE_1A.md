# Phase 1A — Core Organizer Domain & First Vertical Slice

## Objective

Establish Ion's first canonical organizer schema and prove one real Task record
end-to-end through the React, Tauri, Rust, authenticated FastAPI, SQLAlchemy
Core, and SQLite runtime.

## Scope

- Areas, Goals, Goal Milestones, Projects, Project Milestones, Tasks, and
  append-only audit metadata.
- UUIDv4 text identities, UTC timestamps, revision counters, and soft Trash.
- Programmatic Alembic migration before service readiness.
- Minimal Task create, list, edit, complete, reopen, trash, and restore flow.

## Explicit exclusions

- Today persistence, Calendar, TaskGroup, Skill, generic relationships, search,
  integrations, AI, scheduling, Home/Projects UI, menu bar, mobile, and remote
  access.
- Generic Undo, automatic purge, and universal snapshot history.

## Acceptance

- A fresh or Phase 0 baseline local database upgrades to the organizer schema.
- Product requests use fixed Tauri commands; the renderer never receives the
  production port or session credential.
- Task mutations are revision-aware and write audit metadata atomically.
- Task Trash/Restore works and normal task lists exclude trashed records.
- Production migration/authentication failures preserve the safe Unavailable
  desktop state.
