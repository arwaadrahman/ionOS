# Data Model Principles

## Status

**Phase 2B interface over the Phase 2A foundation.** The organizer schema begins in
`0002_organizer_foundation`; `0003_milestone_ordering` adds canonical
owner-scoped positions to Goal and Project Milestones, and
`0004_today_planning` adds human day-planning intent over canonical Tasks.
`0005_google_calendar_foundation` adds Google account/calendar sync metadata,
canonical CalendarBlocks, Ion-only block metadata, and provider linkage.
Owner-authorized Phase 2B migration `0006_calendar_presentation_metadata` adds
only persistent local calendar hide state and nullable CalendarBlock category
plus extensible subtype; existing rows migrate to visible and uncategorized.

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
  Tasks, and append-only audit metadata. Phase 1C adds `task_day_plans`.
  Phase 2A adds only the Calendar read-sync model below; generic relationships,
  search indexes, other integrations, and AI data remain deferred.
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
- Phase 1F adds no migration or recovery table. Bounded Trash cards and recent
  direct-human audit summaries are read projections over the existing canonical
  records and audit metadata; they are neither snapshots nor version history.
- `google_accounts` persists non-secret provider identity, exact granted scopes,
  auth state, and an opaque Keychain locator. Tokens are never SQLite data.
- `google_calendars` belongs to one account and stores provider discovery
  metadata separately from `enabled_in_ion`. Provider `selected`/`hidden` are
  observations only. The same row owns per-calendar sync token, active
  generation/mode, last success, failure, retry, and reauth state.
- `calendar_blocks` is the canonical scheduled-time record. Provider-owned
  summary, description, location, time, status, transparency, and recurrence
  state update through reconciliation. `calendar_block_ion_metadata` separately
  owns flexibility and notes, so provider resync cannot overwrite Ion metadata.
- CalendarBlock time is a checked union: all-day stores civil `start_date` and
  exclusive `end_date` with no midnight coercion; timed stores offset-bearing
  start/end instants plus IANA start/end timezones and no date-only columns.
- Recurrence persists a master and explicit exceptions. An exception retains
  provider series ID, original-start union, and resolved canonical master link.
  Cancelled exceptions remain canonical so generated occurrences cannot
  reappear. Generated occurrences are derived/rebuildable and not stored.
- Phase 2B projects generated occurrences only across the visible Calendar or
  Today range. The safe status DTO includes the linkage row's original-start
  date/instant/timezone union so moved and cancelled exceptions can replace or
  suppress a generated occurrence without exposing tokens, ETags, sync tokens,
  or Keychain metadata. Projection, overlap columns, colors, and free-gap
  intervals are renderer-only state.
- `google_calendars.hidden_in_ion` is a reversible Ion-local presentation flag.
  It does not alter `enabled_in_ion`, Google selection, subscription, or
  visibility, and provider rediscovery preserves it.
- `calendar_block_ion_metadata.category` is nullable and constrained to the
  starter broad domains `academic`, `career`, `personal_project`,
  `routine_physical`, `personal`, `fun`, or `ion_focus`. Null means
  uncategorized. `category_subtype` is a bounded lowercase slug so Ion can
  extend the presentation taxonomy without a schema migration. The local
  mutation contracts require a subtype for every current broad category that
  exposes subtype choices; Ion focus currently omits that control. Both fields
  share the Ion metadata revision, and provider reconciliation preserves them
  alongside flexibility and notes.
- `google_event_links` separates provider event ID, iCalUID, ETag, provider
  update time, series identity, original start, and sync generation. Event ID
  is unique only within its calendar. iCalUID is indexed but deliberately not
  unique.
- Full-sync generation completion marks unseen provider blocks cancelled
  instead of deleting them. Incremental cancellation updates the same record.
  Either path preserves Ion-only metadata and appends an integration/automated
  audit event without payload snapshots.

See [Architecture](ARCHITECTURE.md) and ADR
[0001](decisions/0001-local-first-data-ownership.md).
