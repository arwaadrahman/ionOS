# Data Model Principles

## Status

**Phase 1B foundation.** The organizer schema begins in
`0002_organizer_foundation`; `0003_milestone_ordering` adds canonical
owner-scoped positions to Goal and Project Milestones only.

- Use one canonical record with multiple contextual views; do not duplicate an
  object merely because multiple areas display it.
- SQLite is the planned owner of canonical structured records. Markdown owns
  durable prose knowledge. Original source files remain immutable evidence.
- Keep source evidence, companion notes, and cross-source synthesis distinct.
  Generated prose must not silently become a structured action or preference.
- Relationships may be structural, contextual, or soft/inferred. Their
  provenance and promotion rules require a later decision before implementation.
- Search indexes, embeddings, graph projections, summaries, and caches are
  derived and rebuildable, not canonical truth.
- Organizer IDs are lowercase UUIDv4 text; canonical timestamps are UTC RFC
 3339 text. Canonical records carry revision counters and soft Trash state.
- Phase 1A creates Areas, Goals, Goal Milestones, Projects, Project
  Milestones, Tasks, and append-only audit metadata only. Today persistence,
  generic relationships, Calendar, search indexes, integrations, and AI data
  remain deferred.
- Milestone positions are non-negative and unique within the direct owner.
  Trashed Milestones retain their position and remain in the canonical position
  space. Areas, Goals, and Projects have no manual-ordering field.
- Archive never cascades. Trash checks direct non-trashed dependents only, and
  structural relationships continue to use the accepted direct foreign keys.
- Goal/Project progress, Project current Milestone and next actions, and recent
  activity are derived projections rather than duplicated canonical fields.

See [Architecture](ARCHITECTURE.md) and ADR
[0001](decisions/0001-local-first-data-ownership.md).
