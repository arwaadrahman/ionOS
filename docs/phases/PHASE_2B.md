# Phase 2B — Calendar Interface

## Objective

Turn the accepted Phase 2A read-sync foundation into Ion's primary Calendar
interface and add truthful current-day CalendarBlock context to Today, while
keeping Google Calendar strictly read-only and preserving Task planning as a
separate human-owned intent.

## Scope

- Five renderer-owned views over cached canonical CalendarBlocks: Day,
  consecutive anchored 3 Day, Monday-to-Sunday Week (wide default), rolling
  today-first Next 7 Days, and a Monday-first Month grid.
- A dedicated all-day strip, local-time vertical grid, current-time emphasis,
  deterministic overlap columns, bounded Month rows with overflow, adaptive
  title-first event detail, and compact/default/expanded hour density. Calendar
  content has no independent zoom or horizontal day navigation.
- Unified rendering across multiple Google accounts with a session-preserved
  secondary drawer that defaults closed, opens to presentation filters, and
  switches between filters and source management. Calendar management includes reversible
  Ion-local hide/restore in a collapsed hidden-calendar area without changing
  provider subscriptions or visibility.
- A provider-read-only event inspector for useful content, source account/calendar,
  timezone, availability, and recurrence/exception context. Provider and
  internal technical identifiers are not rendered. Its one mutation is a
  revisioned Ion-owned broad category plus a required subtype wherever the
  selected category has starter subtype choices. Starter domains cover
  Academic, Career, Personal project, Routine / physical, Personal, Fun, Ion
  focus, and Uncategorized without keyword or AI inference. Ion focus omits a
  subtype control for now while the safe local slug storage remains extensible.
- Broad category, not account or calendar identity, owns a restrained color
  family. Optional subtype varies shade/intensity within that family. Compact
  presentation filters understand both levels without turning the view into a
  rainbow. Fun uses a graphite family; Routine work/shift, meal, gym, hygiene,
  and chores/errands deliberately share teal.
- Deterministic visible-range recurrence expansion from canonical masters and
  explicit exceptions. Moved exceptions replace the superseded generated
  occurrence, cancelled exceptions suppress it, and generated occurrences are
  never persisted.
- Local Mac timezone display with provider timezone context in the inspector,
  DST-sensitive wall-time recurrence, and date-only all-day preservation.
- Today displays real CalendarBlock occupancy and open intervals derived only
  from opaque timed CalendarBlocks. All-day and transparent events stay
  visible without consuming fabricated timed occupancy.
- Cached data remains browsable during sync failure, reauthorization, account
  disconnect, or provider unavailability.

## Read-only boundary

Phase 2B adds no Google event create, edit, move, resize, delete, recurrence mutation,
attendee/invite mutation, Meet creation, reminder configuration, calendar
creation/deletion, or other Google write. Ion-local category and hide/restore
metadata do not mutate Google. Rust continues to own all Google
HTTP and credentials; Python continues to own canonical reconciliation; React
receives only the safe status DTO and fixed Phase 2A commands.

## Data and architecture

Owner acceptance authorized migration `0006_calendar_presentation_metadata`,
which adds exactly `google_calendars.hidden_in_ion` plus nullable
`calendar_block_ion_metadata.category` and `category_subtype`. Two fixed local
mutation routes expose revisioned hide/restore and classification updates; they add no generic transport or
provider authority. No provider SDK, calendar framework, process, dependency,
or trust-boundary change is introduced. The safe CalendarBlock DTO projects the
already-stored exception original-start union so the renderer can correlate
explicit exceptions with generated occurrences. This is read-model metadata,
not a provider identifier or credential surface. A memoized renderer index
filters visible calendars once, correlates recurrence exceptions once, caches
bounded range projections, and isolates derived day/month/overlap layout.
The migration runner also completes both exact earlier unreleased `0006`
shapes seen during owner testing: a missing subtype column and the obsolete
broad-category check constraint. It rebuilds the current constraint in place
while preserving existing rows and without adding another revision. Legacy
`work` and `meals` presentation values map to Routine work/shift and meal;
legacy `health` remains an extensible Routine subtype rather than being
silently discarded.

The usable calendar canvas owns responsive view selection. At 840 logical CSS
pixels and above it recommends Week; from 560 through 839 it recommends 3 Day;
below 560 it recommends Day. Manual selection, including Month or Next 7 Days,
persists while the canvas remains in the same width class. Crossing a major
class re-evaluates the recommendation and closes—but never reopens—the shared
drawer. All active-view day columns fit the canvas without horizontal scrolling.
The production main window has a 540 by 560 logical-pixel minimum so its closed-
drawer Day layout, compact toolbar, and event titles remain usable.

## Explicit exclusions

- No Phase 2C provider writes or conflict resolution.
- No Google Tasks bridge, Task-to-calendar conversion, Task auto-scheduling,
  FocusSession creation, AI scheduling, free/busy provider request, attendee
  workflow, webhook, daemon, cloud relay, LAN, mobile, or generic provider
  abstraction.
- No major calendar/date/UI dependency and no mobile redesign.

## Acceptance

- Deterministic synthetic tests cover every range/navigation rule, current-day
  highlighting, timed/all-day/overlap/month overflow, multiple accounts,
  disabled and Ion-hidden calendars, semantic category-family/subtype colors
  and two-level filters,
  hide/restore persistence, density persistence, adaptive title hierarchy,
  required starter subtype persistence across restart/provider reconciliation,
  filter-first mutually exclusive drawers with a pinned connection action,
  pane-width Week/3-Day/Day recommendations, manual-view stability within a
  width class, absence of calendar zoom and horizontal day scrolling, distinct saved-data status copy,
  empty/offline rendering, recurrence
  masters and moved/cancelled exceptions without duplicates, projection bounds,
  local time/DST/date-only behavior, inspector safety, Today occupancy/free
  gaps, and the absence of event write affordances.
- Existing Phase 1 organizer and Phase 2A read-sync tests remain green.
- Repository validation, a fresh ARM64 Python sidecar, a fresh production Tauri
  macOS package, and feasible packaged startup/authentication/shutdown and
  artifact-safety checks pass without reading or logging owner calendar data.
- The owner performs final visual/semantic acceptance against existing cached
  calendars and confirms no Google data was mutated.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Phase 2A](PHASE_2A.md)
- [Architecture](../ARCHITECTURE.md)
- [Data model](../DATA_MODEL.md)
- [Security](../SECURITY.md)
- [Integrations](../INTEGRATIONS.md)
- [Design system](../DESIGN_SYSTEM.md)
- [ADR 0018](../decisions/0018-google-calendar-read-sync-foundation.md)
- [ADR 0019](../decisions/0019-calendar-presentation-metadata.md)
