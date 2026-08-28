# ADR 0012: Organizer lifecycle and containment

**Status:** Accepted
**Date:** 2026-08-28

## Context

Phase 1B makes the Phase 1A organizer hierarchy editable. Parent archive,
Trash, relationship changes, and lifecycle actions need durable semantics that
do not silently change or hide independent canonical descendants.

## Decision

Archive affects only the selected Area, Goal, or Project. It never cascades;
descendants retain their lifecycle and relationships and remain visible in
their own contextual views. New relationships to archived or trashed parents
are rejected until the target is restored or unarchived.

Trash checks direct non-trashed dependents only. Area checks Goals. Goal checks
Goal Milestones, directly owned Projects, and directly linked Tasks. Project
checks Project Milestones and directly linked Tasks. A blocked Trash changes no
row, revision, or audit metadata. No transitive blocker engine is introduced.

Goal-to-Area, Project-to-Goal, and Task-to-Goal/Project relationships continue
to use direct foreign keys with revision-aware explicit assignment. Task Goal
and Project relationships are independently nullable. Milestone owners are
immutable during Phase 1B.

Lifecycle changes use entity-specific operations, never a universal engine.
Goal states are directly reversible. Project archive is allowed from completed
and unarchives to completed; completion/archive timestamps remain synchronized.
Milestone achievement timestamps follow the achieved state. No lifecycle action
cascades to descendants.

## Consequences

Archived context remains inspectable, recovery is explicit, and parent actions
cannot silently rewrite work. Users must move, unlink, or Trash direct blockers
before trashing a parent. Services require explicit queries and safe blocker
responses, but no generic relationship, lifecycle, or traversal infrastructure.

## Alternatives considered

- Cascading archive or Trash was rejected because descendants have independent
  lifecycles and human actions must remain authoritative.
- Blocking archive whenever children exist was rejected because archive is
  retained context, not deletion.
- Recursive Trash traversal was rejected because direct structural blockers
  are sufficient and more understandable.
- Generic lifecycle/relationship frameworks were rejected as premature.

## References

- [Phase 1B](../phases/PHASE_1B.md)
- [ADR 0010](0010-phase-1-organizer-domain.md)
- [ADR 0011](0011-audit-trash-and-recovery-foundation.md)
