# Phase 1F — Recovery & History UX

## Objective

Make the existing organizer Trash and compact audit foundation understandable
and useful without creating a generic Undo, history, or lifecycle framework.

## Scope

- One bounded, authenticated, read-only Recovery projection over canonical
  organizer records already in Trash and the latest direct-human audit events.
- A contextual Recovery workspace reached through the existing command surface,
  preserving Home's five permanent destinations.
- Explicit per-record Restore controls that dispatch to the existing
  entity-specific canonical restore operations.
- Clear direct-dependency Trash-blocker and non-cascading recovery guidance.

## Durable behavior

- SQLite canonical records and append-only audit metadata remain the only data
  owners. Recovery is a read projection: it adds no table, index, cache,
  snapshot, or audit event.
- The projection is bounded to 100 trashed records and 12 recent organizer
  events. It displays compact labels, lifecycle context, milestone owners, and
  no audit payloads or credentials.
- Restore affects exactly the selected record. It does not restore a parent,
  child, relationship, prior field value, or unrelated action.
- A confirmed Restore remains successful if its secondary workspace refresh
  fails; the Recovery surface reports freshness separately.
- The Recovery command is contextual, not a sixth permanent destination, and
  does not put trashed records into normal command-record results.

## Explicit exclusions

Phase 1F excludes generic Undo, arbitrary rollback, event sourcing, universal
snapshots/version history, hard delete, automatic Trash purge, destructive
cascades, AI, schema migration, dependencies, Calendar, integrations,
mobile/cloud/LAN/remote access, and changes to `PRODUCT_SPEC.md`.

## Acceptance

- The Recovery read route remains within the existing authenticated Rust-owned
  local-process boundary; the renderer receives no port, credential, generic
  HTTP, filesystem, or shell capability.
- Tests prove Trash/audit projection content, zero audit writes from reads,
  authenticated routing, and entity-specific restore dispatch.
- Repository validation, frozen ARM64 sidecar, Tauri package build, packaged
  startup, and clean shutdown pass.
- Owner manually verifies representative recovery, lifecycle context, blocker
  wording, recent history truthfulness, and no implied Undo/cascade behavior.

## Decision

- [ADR 0016](../decisions/0016-recovery-and-history-projection.md)
