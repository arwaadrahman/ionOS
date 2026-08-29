# Data Model Principles

## Status

**Phase 1E foundation.** The organizer schema begins in
`0002_organizer_foundation`; `0003_milestone_ordering` adds canonical
owner-scoped positions to Goal and Project Milestones, and
`0004_today_planning` adds human day-planning intent over canonical Tasks.

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
- Phase 1A creates Areas, Goals, Goal Milestones, Projects, Project Milestones,
  Tasks, and append-only audit metadata. Phase 1C adds only
  `task_day_plans`; generic relationships, Calendar, search indexes,
  integrations, and AI data remain deferred.
- Milestone positions are non-negative and unique within the direct owner.
  Trashed Milestones retain their position and remain in the canonical position
  space. Areas, Goals, and Projects have no manual-ordering field.
- Archive never cascades. Trash checks direct non-trashed dependents only, and
  structural relationships continue to use the accepted direct foreign keys.
- Goal/Project progress, Project current Milestone and next actions, and recent
  activity are derived projections rather than duplicated canonical fields.
- A Task may have one `task_day_plans` relation per ISO local civil date. The
  relation stores role (`priority`, `planned`, or `backup`), position,
  timestamps, and its own revision. It does not store timezone, scheduled time,
  lifecycle, urgency, focus, or review state.
- Today position is unique within date and role. Completed/canceled/trashed
  membership remains canonical and reserves its position while normal active
  Today views hide it. Explicit removal deletes and audits only the relation.
- The current IANA timezone is request context for validating Today and
  classifying exact deadlines; historical plan rows retain their original
  civil date.
- Phase 1D adds no migration. Home/Core nodes, edges, lifecycle normalization,
  Today/attention annotations, coordinates, and summaries are deterministic
  read projections over the existing tables and are never persisted.
- The Core includes only untrashed Areas, Goals, both owner-specific Milestone
  types, Projects, and Tasks. Its edges are the existing direct `goal→area`,
  `project→goal`, Milestone→owner, and Task→Goal/Project foreign keys.
- Phase 1E adds no migration or stored index. Command items, normalized search
  text, ranking scores, query state, and selection are ephemeral desktop
  projections over the existing Home/Core DTO and current destinations.

See [Architecture](ARCHITECTURE.md) and ADR
[0001](decisions/0001-local-first-data-ownership.md).
