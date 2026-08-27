# Data Model Principles

## Status

**Baseline.** Schema design is deferred.

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
- Repository fixtures will be synthetic only. No Phase 1 entity tables or
  complete database schema are created in Phase 0A.

See [Architecture](ARCHITECTURE.md) and ADR
[0001](decisions/0001-local-first-data-ownership.md).
