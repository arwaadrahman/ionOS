# ADR 0019: Calendar presentation metadata

**Status:** Accepted  
**Date:** 2026-08-29

## Context

Phase 2B owner acceptance established that source-calendar color is not a
meaningful event semantic and that large discovered calendar lists need
reversible local concealment. Google remains authoritative for event and
calendar provider fields, while these two choices are Ion presentation state.
The owner explicitly authorized a narrow two-level CalendarBlock presentation
classification and the minimum persistent local state needed for hide/restore.

## Decision

Migration `0006_calendar_presentation_metadata` adds exactly three fields and
no table: non-null `google_calendars.hidden_in_ion`, default false, plus nullable
`calendar_block_ion_metadata.category` and `category_subtype`. Broad category is
constrained to Academic, Career, Personal project, Routine / physical,
Personal, Fun, or Ion focus; null means Uncategorized. Subtype is a bounded
lowercase slug rather than a closed database enum so the taxonomy can extend
without a schema migration. Fixed local mutation contracts require a subtype
when the selected current category exposes choices. Ion focus has no current
subtype control but retains extensible storage for later owner-approved focus
types.

Because owner visual testing had already applied an earlier unreleased form of
revision `0006`, the runtime migration entry point contains narrow schema-only
compatibility repairs. When and only when the database is stamped at `0006`,
it can complete a missing subtype column/constraint or replace the obsolete
broad-category constraint seen in owner testing. Alembic batch operations
preserve existing rows. The repair creates no new revision and inspects no
calendar content. The retired `work` and `meals` labels map to the owner-approved
Routine work/shift and meal subtypes; the broader retired `health` label is
preserved as an extensible Routine subtype rather than guessed into a narrower
starter meaning.

Fixed authenticated local routes perform revision-checked human mutations and
append compact audit metadata. Google discovery and event reconciliation
preserve all Ion presentation fields. Hiding does not disable sync,
unsubscribe, delete, or change Google visibility. Category changes do not
modify provider event fields. React uses broad category for a restrained color
family and subtype for shade/intensity within that family; filters understand
both levels. Source identity remains textual and a secondary management marker.

## Consequences

- Fresh databases and upgrades begin visible and uncategorized.
- Category, subtype, and hide state survive restart, provider refresh,
  and offline use.
- The event inspector is provider-read-only but may edit its clearly labeled
  Ion category/subtype. No event create/edit/delete or Google write exists.
- No OAuth scope, provider HTTP method, token owner, process, dependency,
  generic transport, AI classifier, or Phase 2C behavior is added.
- Downgrade to Phase 2A removes only these fields and necessarily discards
  their local presentation values while preserving Phase 2A canonical data.

## Alternatives considered

- Calendar/account-owned event color: rejected because one calendar can contain
  semantically different events.
- Hard-coded title classification or AI categorization: rejected because the
  owner did not authorize inference and it would be unreliable.
- Google calendar hiding/unsubscription or event extended properties: rejected
  because either would cross the read-only provider boundary.
- Browser-only category state: rejected because it would not survive restart
  or remain canonical Ion metadata.

## References

- [Phase 2B](../phases/PHASE_2B.md)
- [ADR 0018](0018-google-calendar-read-sync-foundation.md)
- [Data model](../DATA_MODEL.md)
- [Integrations](../INTEGRATIONS.md)
