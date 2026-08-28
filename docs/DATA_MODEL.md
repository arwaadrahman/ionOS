# Data Model Principles

## Status

**Phase 1A foundation.** The initial organizer schema is implemented through
SQLAlchemy Core and Alembic migration `0002_organizer_foundation`.

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

See [Architecture](ARCHITECTURE.md) and ADR
[0001](decisions/0001-local-first-data-ownership.md).
