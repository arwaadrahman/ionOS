# ADR 0015: Deterministic command-search projection

**Status:** Accepted
**Date:** 2026-08-28

## Context

The Master Specification requires a fast deterministic `⌘K` search alongside a
separate future conversational search system. Phase 1 already exposes the
current untrashed organizer as one authenticated, read-only Home projection,
including canonical record IDs, labels, lifecycle, limited Today context, and
the direct relationships needed to open either Milestone type through its
owner.

Phase 1E needs useful command navigation without creating competing canonical
records, a prematurely persisted index, another backend endpoint, or a later
knowledge/semantic retrieval system.

## Decision

Build command search as a rebuildable in-memory desktop projection over the
five implemented destinations and `HomeOutput.core.nodes`. Refresh the source
projection in the background through the existing fixed authenticated
`get_home` command whenever the palette opens. Search adds no database table,
migration, backend route, filesystem access, local storage, or runtime
dependency.

Normalize queries and item text with Unicode compatibility decomposition,
diacritic removal, explicit lowercase rules, whitespace normalization, and
deterministic lexical tiers. Rank exact label, label prefix, word prefix,
label substring, all-token word prefix, then all-token metadata matches. Break
ties by a fixed destination/entity order, normalized label, and canonical ID;
return a bounded result set.

The compact command palette is available through a visible Search control and
macOS `⌘K`. It supports keyboard and pointer selection. Destination results
switch workspace; record results navigate to the existing canonical record;
Milestones navigate to their canonical Goal or Project owner. Search performs
no canonical mutation and records no query, selection, recent item, audit
event, or preference.

Archived, paused, completed, and otherwise inactive untrashed records remain
searchable. Trash remains excluded because the Home projection excludes it.
Missing future entity types are not simulated.

## Consequences

- Search remains offline, fast for the current organizer scale, deterministic,
  and entirely inside the existing Phase 0C trust boundary.
- The renderer receives only the existing Home DTO and fixed navigation
  actions; it still receives no sidecar address, session credential, generic
  HTTP primitive, filesystem, or shell capability.
- The command list always rebuilds from canonical projections and cannot drift
  into a second data owner.
- Later text corpora must benchmark an Ion-native FTS approach before adding an
  index. Semantic, vector, QMD, and conversational search remain later,
  separately authorized work.

## Alternatives considered

- SQLite FTS was rejected for this milestone because the small structured
  organizer already has a complete projection and an index would require a
  migration, synchronization policy, and duplicate derived state.
- A new Python search endpoint was rejected because it adds a product boundary
  without improving the current record corpus.
- QMD, embeddings, fuzzy models, and external services were rejected because
  they add dependencies and later-phase retrieval semantics.
- Browser-persisted recents or query history were rejected because they create
  unnecessary private state and invalidation behavior.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Phase 1E](../phases/PHASE_1E.md)
- [Architecture](../ARCHITECTURE.md)
- [Data Model](../DATA_MODEL.md)
- [ADR 0009](0009-local-process-authentication.md)
- [ADR 0014](0014-ion-core-rendering-and-phase-1d-home-boundary.md)
