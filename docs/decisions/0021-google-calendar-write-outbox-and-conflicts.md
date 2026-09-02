# ADR 0021: Google Calendar write outbox and conflict boundary

**Status:** Accepted; conflict policy amended 2026-09-01

**Date:** 2026-08-30

> **Amendment (2026-09-01, owner-directed after acceptance testing).** The
> conflict rule below — that a stale precondition or newly observed provider
> version creates an explicit human conflict — is **superseded for ordinary
> supported mutations**. In real use it made every ordinary edit a review task.
> Ordinary ETag drift now re-reads confirmed provider state and rebases the
> pending write onto it automatically, bounded by the existing automatic
> attempt budget. `Keep Google version` / `Apply my Ion changes` /
> `Review differences` remain, but only for drift that outlasts that budget and
> for genuinely unmergeable contradictions.
>
> Everything else in this ADR stands unchanged: exact non-wildcard `If-Match`,
> no silent last-write-wins, no timestamp authority, the narrow changed-field
> provider body, deterministic create identity, and durable local intent. The
> current interaction contract is
> [Calendar interaction behavior](../CALENDAR_BEHAVIOR.md).

## Context

The Master Specification requires true two-way Google Calendar synchronization
and makes Ion's Calendar the primary planning interface. Accepted Phase 2A and
2B work deliberately stops at read synchronization and local presentation
metadata. Phase 2C must add consequential provider writes without moving OAuth
or Google HTTP out of Rust, creating a parallel GoogleEvent domain, losing
offline human intent, or silently overwriting a newer Google version.

Google Calendar accepts caller-supplied event IDs for inserts, supports
conditional modification through `If-Match` and event ETags, exposes recurring
instances separately from recurrence masters, and returns distinct duplicate,
deleted, stale-precondition, authorization, quota, and backend failures. Ion
needs durable local semantics around those provider behaviors rather than an
in-memory request queue.

## Decision

Preserve the accepted trust and authority boundaries:

- SQLite owns canonical Ion CalendarBlocks and durable Ion intent.
- Google owns the last confirmed synchronized provider fields for
  Google-backed CalendarBlocks.
- Ion owns flexibility, notes, category/subtype, calendar selection, and local
  presentation state; provider reconciliation never overwrites them.
- Rust alone owns OAuth, Keychain token access, refresh, Google HTTPS, provider
  request construction, and response sanitization.
- Python owns Calendar domain validation, canonical transactions, a durable
  provider-write outbox, reconciliation, conflict state, and compact audit
  evidence.
- React invokes fixed Calendar commands and receives safe product DTOs. It
  receives no token, provider credential, raw provider payload, generic Google
  API, generic HTTP, filesystem, or shell capability.

Every external write starts with one Python transaction that validates a
revision-aware direct-human command, creates or identifies the canonical
CalendarBlock, and persists a typed provider-write intent plus compact audit
metadata. Only after that transaction commits may Rust obtain a bounded write
plan and call Google. A sanitized provider result then returns to Python for one
reconciliation transaction. A crash or offline interval therefore cannot lose
the authorized intent.

The outbox stores a versioned Ion write contract, not a raw Google resource. It
records the CalendarBlock/account/calendar correlation, operation and recurrence
scope, ordered field mask, bounded base and desired values, expected provider
ETag, stable provider event ID, attempt/retry state, safe failure class, and
timestamps. It stores no token, credential, attendee address, full provider
payload, or audit payload snapshot. Writes serialize per CalendarBlock; one
blocked or failed block does not stop unrelated blocks.

For an Ion-created Google event, Python derives and persists a stable opaque
lowercase base32hex event ID from a domain-separated SHA-256 hash of the Ion
CalendarBlock UUID. At least 160 bits are retained. Retries reuse exactly that
ID. After an ambiguous create result, Rust performs bounded `events.get`
reconciliation before retrying `events.insert`; a duplicate-ID response is
also reconciled rather than generating a second ID.

Existing-event patch and delete/cancel requests carry the last confirmed ETag
in `If-Match`. Ion never uses `If-Match: *`. A 412 response or a newly observed
provider version is resolved by re-reading confirmed provider state and
rebasing the pending write onto it (see the amendment above); there is no
silent last-write-wins and no timestamp authority. Only drift that outlasts the
bounded automatic attempt budget, or a contradiction that cannot be merged
truthfully, becomes an explicit conflict. `Keep Google version` discards the
pending provider-field intent. `Apply my Ion changes` is an explicit human
resolution rebased onto the freshly retrieved ETag. `Review differences` may
select a new bounded field mask. Ion-only metadata never participates in a
provider conflict.

The first provider body allowlist is summary, description, location,
transparency, the checked start/end union, and explicitly authorized recurrence
data or cancellation status. Patch semantics preserve omitted provider fields.
Attendees, invitation responses, conference/Meet data, reminders, attachments,
calendar properties, ACLs, and sharing are absent from the write contract.

Initial writes are restricted to non-deleted, enabled Google calendars with
`writer` or `owner` access and ordinary `default` events that are not
provider-locked and have no attendees. `writerWithoutPrivateAccess`, attendee
events, special event types, and resources whose full safe mutation capability
cannot be established remain read-only. Ion's separate `locked` flexibility
classification constrains Ion's own scheduling and future automation, not the
owner's direct action *(amended 2026-09-01; it previously required direct
confirmation before a human-requested change)*; it is not confused with
Google's provider-locked flag.

The accepted Phase 2C OAuth set replaces Events read-only with the event-only read/write
scope while retaining CalendarList read-only:

- current: `calendar.calendarlist.readonly` + `calendar.events.readonly`;
- accepted for Phase 2C: `calendar.calendarlist.readonly` + `calendar.events`.

The broader `calendar` scope is not requested. Existing accounts without the
write scope remain read-only until the account completes a deliberate
re-consent flow during an authorized implementation step. This ADR accepts the
future scope boundary but does not itself change requested scopes.

Recurring masters remain canonical and generated occurrences remain derived.
An occurrence mutation resolves the concrete instance through
`events.instances`, preserving `recurringEventId` and the original-start union.
One-occurrence changes create or cancel an explicit exception. Entire-series
changes target the master with its ETag. `This and following` remains deferred.

## Consequences

- Phase 2C requires one separately implemented and reviewed migration for the
  durable outbox and minimum provider capability/correlation fields. This ADR
  defines that boundary but does not itself add or execute a migration.
- Pending, retry-wait, reconciliation-required, failed, and conflict intents
  are durable. `synced` is a projection meaning a provider-confirmed link has
  no unresolved write intent; pending state never masquerades as confirmation.
- Offline changes can replay after reconnect without converting the renderer or
  Python into a Google client.
- Retry is bounded and durable. Token refresh gets one bounded retry; transport,
  quota, and backend failures use persisted exponential backoff; terminal
  validation/permission failures stop. Manual retry is a new explicit action.
- Successfully completed operational rows may be pruned after 30 days once
  compact durable audit evidence and provider linkage are confirmed. Pruning is
  bounded, deterministic, and restart-safe. Unresolved, failed, conflict, and
  ambiguous rows remain until explicitly resolved and are never evicted merely
  to enforce an in-memory limit.
- Provider deletion is not represented as generic Undo or event sourcing.
  Consequential deletes and series operations require explicit confirmation,
  and a remote-deleted conflict cannot silently recreate an event.
- No daemon, webhook, cloud relay, LAN/mobile boundary, provider SDK, generic
  integration framework, automation engine, or always-running retry worker is
  introduced.

## Owner decisions

The owner accepted this ADR and gate on 2026-08-30 with these locked decisions:

1. Phase 2C uses `calendar.calendarlist.readonly` plus `calendar.events`, not
   `calendar.events.owned`, so legitimate shared calendars with writer access
   can be supported. Broad `calendar` and unrelated scopes remain forbidden.
2. Initial writes require `writer` or `owner`, ordinary/default event type,
   no provider lock, no attendees, and explicit re-consent to the write scope.
3. Attendee/invite events remain entirely read-only. Ion does not mutate
   attendees, invitations, RSVP state, organizer semantics, or conferencing.
4. *(Amended 2026-09-01.)* Ordinary ETag drift is reconciled automatically by
   re-reading confirmed provider state and rebasing the pending write's own
   changed-field mask onto it. There is still no whole-event merge, no silent
   last-write-wins, and no timestamp authority. Explicit conflict handling
   remains for drift that outlasts the bounded automatic attempt budget and for
   contradictions that cannot be reconciled deterministically.
5. Provider deletion uses confirmation plus local tombstone/audit evidence and
   makes no provider Undo claim. Recreating an event produces new identity;
   whole-series deletion uses stronger blocking confirmation.
6. Phase 2C-5 owns a bounded deterministic recurrence surface. Arbitrary RRULE
   entry and `this and following` remain deferred; exact editor choices remain
   a bounded 2C-5 product-design decision.
7. Unresolved, failed, and conflict intents remain until explicitly resolved.
   (Amended: an `ambiguous` intent is now part of the automatic rebase cycle
   rather than something awaiting a human.) Successful intents may be pruned after 30 days while compact audit
   remains durable. A measured reason to change 30 days is a stop-and-report
   owner decision, never a silent implementation change.

This acceptance establishes architecture and security direction only. The
owner explicitly withheld application-code, migration, dependency, OAuth-scope
execution, provider-write, staging, commit, and push authority in this task.

## Alternatives considered

- In-memory write queue: rejected because a crash or offline interval could
  lose direct-human intent.
- Python Google client or renderer-held token: rejected because it breaks the
  accepted credential and request boundary.
- Full Google event mirror or separate canonical GoogleEvent domain: rejected
  because CalendarBlock is already canonical and Google resources are provider
  linkage/evidence.
- Blind retries with server-generated IDs: rejected because an accepted create
  followed by a lost response could duplicate an event.
- Unconditional update/delete or `If-Match: *`: rejected because either can
  overwrite a newer provider version.
- Generic event sourcing/Undo: rejected because the outbox is operational
  intent and provider deletion cannot be truthfully reversed as the same event.
- Broad `calendar` OAuth scope: rejected because event-only write authority is
  sufficient for the proposed feature set.
- Write every provider event Google might permit: rejected because attendee,
  special-event, privacy-limited, and provider-locked semantics exceed the
  minimum safe Phase 2C boundary.

## References

- [Phase 2C architecture and security gate](../phases/PHASE_2C.md)
- [Master Specification](../PRODUCT_SPEC.md)
- [Architecture](../ARCHITECTURE.md)
- [Data model](../DATA_MODEL.md)
- [Security](../SECURITY.md)
- [Performance and Resource Policy](../PERFORMANCE.md)
- [ADR 0018](0018-google-calendar-read-sync-foundation.md)
- [ADR 0019](0019-calendar-presentation-metadata.md)
- [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google Calendar event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Google Calendar resource versions](https://developers.google.com/workspace/calendar/api/guides/version-resources)
- [Google Calendar recurring events](https://developers.google.com/workspace/calendar/api/guides/recurringevents)
- [Google Calendar errors](https://developers.google.com/workspace/calendar/api/guides/errors)
