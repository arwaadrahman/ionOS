# ADR 0013: Today planning and pre-Calendar boundary

**Status:** Accepted
**Date:** 2026-08-28

## Context

Today must distinguish work a person deliberately selected for the current day
from Tasks that merely have important or nearby deadlines. Calendar is not yet
implemented, so Today cannot claim to know appointments, occupied time, or
availability. The Phase 1 organizer already owns canonical Tasks, lifecycle,
deadlines, revisions, audit metadata, and Trash behavior.

## Decision

Persist human day-planning intent in `task_day_plans`, a lightweight relation
from one canonical Task to an ISO local civil date. A Task may have at most one
membership per date. Membership has exactly three roles—`priority`, `planned`,
and `backup`—and a manually controlled position within its date and role.

The current Mac IANA timezone is validated request context but is not stored on
the relation. Historical membership remains attached to its original civil
date. Today membership and Task lifecycle remain independent. Completed,
canceled, and trashed Tasks keep existing membership but are hidden from active
plan lists; paused Tasks remain visible. Explicit membership removal deletes
only the relation and is audited.

Each relation owns its revision. Add, role change, reorder, and removal write
compact `task_day_plan` audit events. Reorder operates atomically on the
complete visible sibling set while positions belonging to hidden historical
rows remain reserved.

Deadline groups, Needs Attention, yesterday carry suggestions, and Completed
Today are deterministic projections over canonical Tasks and plan relations.
No urgency score or AI output is stored. Unfinished work from yesterday is
suggested but never copied automatically.

Before Calendar exists, the right pane states that scheduling context is
unavailable and shows truthful deadline markers only. It contains no timeline,
appointments, free/busy calculation, time slots, or FocusSession state.

## Consequences

- Human planning intent survives restart and is available for later review or
  analytics without duplicating Tasks.
- Date travel does not rewrite historical planning records.
- Future automation may use the existing audit authority model, but Phase 1C
  performs only direct human mutations.
- Calendar and FocusSession can be introduced later without converting Today
  membership into scheduled time.
- The table retains historical rows unless a person explicitly removes the
  lightweight membership.

## Alternatives considered

- A fully derived Today list was rejected because it cannot represent direct
  selection, manual priority order, or backups.
- Today fields directly on Task were rejected because one Task can participate
  in many local planning dates.
- Persisting timezone, scheduled times, urgency, focus, or review state was
  rejected because none is required for Phase 1C semantics.
- Automatic carry-forward was rejected because it would silently rewrite the
  current plan.

## References

- [Phase 1C](../phases/PHASE_1C.md)
- [Data Model](../DATA_MODEL.md)
- [Architecture](../ARCHITECTURE.md)
- [ADR 0010](0010-phase-1-organizer-domain.md)
- [ADR 0011](0011-audit-trash-and-recovery-foundation.md)
