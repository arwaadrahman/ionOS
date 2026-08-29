# ADR 0016: Recovery and history projection

**Status:** Accepted  
**Date:** 2026-08-28

## Context

Phase 1A and 1B already provide canonical soft Trash, append-only compact audit
metadata, direct-only Trash blockers, and entity-specific Restore operations.
Those capabilities are scattered across organizer workspaces, while audit is
only selectively visible. Phase 1F needs a useful recovery surface without
turning audit metadata into a generic history/Undo system or weakening the
five-destination Home navigation decision.

## Decision

Expose one authenticated, read-only `GET /v1/recovery` projection through the
fixed Tauri `get_recovery` command. It returns at most 100 currently trashed
organizer records and 12 most recent direct-human organizer audit events. It
derives labels, lifecycle context, and milestone owner labels from the existing
canonical tables. It writes no data and carries no audit payload snapshots.

Recovery is a contextual workspace reached through the existing command palette
by a fixed `Recovery` command. It is not a sixth permanent destination and
normal record search continues to exclude Trash. Each Restore button explicitly
dispatches to the existing entity-specific Area, Goal, Milestone, Project, or
Task operation; no universal lifecycle or restore command is introduced.

## Consequences

- Restore is clear, direct-human, and record-local. It cannot imply arbitrary
  rollback, hierarchy restoration, or a destructive cascade.
- Audit becomes a compact explanation surface, not event sourcing, snapshots,
  version history, persisted user activity, or generic Undo.
- The existing Phase 0C boundary remains intact: Rust owns authenticated
  loopback access and the renderer gains no service address, credential,
  generic HTTP, filesystem, or shell capability.
- The projection adds no migration, dependency, canonical data, or cache.

## Alternatives considered

- A generic Undo/history framework was rejected because canonical lifecycle
  semantics are intentionally entity-specific.
- Separate client aggregation of every trash list was rejected because it
  cannot provide concise cross-entity audit context or bounded consistent
  recovery data without N+1 detail reads.
- A permanent Recovery navigation destination was rejected to preserve the
  established Home-first five-destination baseline.

## References

- [Phase 1F](../phases/PHASE_1F.md)
- [ADR 0011](0011-audit-trash-and-recovery-foundation.md)
- [ADR 0012](0012-organizer-lifecycle-and-containment.md)
- [ADR 0014](0014-ion-core-rendering-and-phase-1d-home-boundary.md)
- [Master Specification](../PRODUCT_SPEC.md)
