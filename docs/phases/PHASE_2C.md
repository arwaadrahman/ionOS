# Phase 2C — Two-way Calendar Writes Architecture and Security Gate

## Status

**Architecture/security gate accepted; Phase 2C-5 bounded recurrence writes
implemented and pending owner real-write acceptance.** The owner accepted ADR 0021 and the seven decisions
in this gate on 2026-08-30, then separately authorized the bounded 2C-1
foundation. Migration `0007`, the typed Python outbox/state API, safe
capability projection, deterministic ID/retry/recovery/audit helpers, one
read-only Tauri foundation command, and unsent Rust provider request/result
helpers are now present. Phase 2C-2 adds explicit selected-account re-consent,
local-first create UI, `events.insert`, and deterministic-ID `events.get`
reconciliation. Phase 2C-3 adds durable desired overlays, explicit-save
inspector editing, direct timed move/resize review, changed-field
`events.patch` with exact `If-Match`, and bounded same-event reconciliation.
Phase 2C-4 adds explicit single-event delete confirmation, conditional
`events.delete`, absence reconciliation, and local cancellation before a create
has reached the provider. Phase 2C-5 adds bounded recurrence presets,
master/original-start instance resolution, one-occurrence patch/cancellation,
and explicit whole-series patch/delete. Owner acceptance found that the
recurring-write projection kept a completed occurrence edit's operation,
scope, and original-start identity visible after that write reached a
terminal state; the renderer's sibling-occurrence guard then treated every
other occurrence of that master as a serialized write in progress and refused
to open it for editing. The projection now clears those fields once the write
is no longer active (matching the existing overlay gating), so a recurring
master stays editable occurrence-by-occurrence after each write completes.
Renderer error mapping was also widened so `timezone_change_unsupported`,
`recurrence_identity_unresolved`, and `no_change_requested` reach the user
truthfully instead of collapsing to the generic local-state message. A second
owner-acceptance pass found that a terminal, reviewable conflict or failure
on one occurrence still serialized every other occurrence of the same
master indefinitely: the write-path predecessor check matched only on the
shared master id, not on which occurrence a nonterminal-vs-resolved
predecessor actually targeted, and the read projection cleared a resolved
write's identity too eagerly for the renderer to single out the reviewed
occurrence. Serialization is now scoped to genuinely nonterminal writes (or
the exact occurrence a resolved write concerned); an unrelated sibling
releases back to current confirmed provider state once that write resolves,
without retrying or mutating the reviewed occurrence's own stored intent.
A bounded stabilization pass then found the same coarse rule still applied
to an already-*materialized* occurrence (its own `exception` CalendarBlock
row, as opposed to a virtual not-yet-materialized one): the read projection's
sibling gate used the older "any nonterminal state blocks" check rather than
the refined per-occurrence rule, so a materialized sibling could stay
permanently locked out after an unrelated occurrence's conflict/failure. Both
gates now agree, with a regression test covering two independently
materialized exception rows. The same pass wired `recurrence_unsupported`
through every safe-copy layer (Python route allowlist, Rust translation,
renderer copy) with route-level and cross-source parity test coverage;
exposed a bounded `provider_write_failure_class`/`_reason` so retryable
quota/backend/transport failures, reauthentication, stale/conflict, and
terminal rejection reach the renderer distinctly instead of one generic
label; implemented the three already-accepted ADR 0021 conflict-resolution
actions (Keep Google's version, Apply my Ion change, Review differences)
end to end through new fixed Ion-ID routes/commands using the existing
outbox schema; added a bounded timeout to `wait_for_write_slot` so a stuck
Google-gate holder fails safely instead of hanging a write command
indefinitely; and fixed resize-handle discoverability, Escape-to-cancel, and
a restrained Inspector-selected visual state in the Calendar grid. No real
OAuth or Calendar mutation was used during automated verification, and no
migration was introduced.

## Objective

Define the minimum safe architecture that lets Ion create and deliberately
mutate Google-backed CalendarBlocks while preserving the accepted macOS-local
trust boundary, canonical CalendarBlock model, offline behavior, recurrence
identity, and direct-human authority.

## Non-negotiable authority and trust boundary

The existing path remains:

```text
React renderer
  → fixed Ion-owned Tauri Calendar command
  → Rust orchestration + Google OAuth/request owner
  → authenticated fixed local Ion API route
  → Python Calendar domain transaction
  → SQLite canonical state and durable write intent
```

For a write, the fixed Rust command first asks Python to validate and commit the
canonical mutation intent. Rust may call Google only after that commit. Rust
then returns a sanitized outcome to a fixed Python reconciliation route. Python
never calls Google, and React never calls either Google or FastAPI directly.

- SQLite owns canonical Ion CalendarBlocks and durable local mutation intent.
- Google owns the last confirmed synchronized provider fields for Google-backed
  events.
- Ion owns flexibility, notes, category/subtype, enabled/hidden presentation
  state, and other explicitly local metadata.
- No parallel canonical GoogleEvent domain is created.
- A Task remains a Task. Neither a Task nor Today membership becomes scheduled
  merely because Phase 2C can create a CalendarBlock.
- Direct human action creates the only Phase 2C write intent. Replaying that
  already-authorized durable intent after restart is recovery, not new
  autonomous authority.

Rust continues to own OAuth, Keychain, access-token memory, refresh, Google
HTTPS, URL encoding, request allowlists, timeouts, and response sanitization.
Python continues to own domain validation, transactions, revisions, canonical
state, reconciliation, conflict state, and audit metadata. The renderer never
receives tokens, OAuth material, provider credentials, raw provider payloads,
generic Google/API HTTP, the local service address or credential, filesystem
access, or shell/process authority. Write commands accept Ion IDs only; they do
not accept a renderer-selected provider event ID or ETag as target authority.

## Provider write architecture

### Command and dispatch sequence

1. React sends a typed direct-human create/edit/move/resize/delete request to a
   fixed Tauri command with the CalendarBlock revision and Ion metadata revision
   where applicable.
2. Rust validates command shape and calls a fixed authenticated local route.
3. Python validates calendar/account capability, time/recurrence invariants,
   direct-human authority, revision, and confirmation requirements.
4. One SQLite transaction creates or identifies the canonical CalendarBlock,
   persists a typed provider-write outbox row, and appends compact
   `write_requested` and `write_queued` audit evidence.
5. Python returns a sanitized write plan containing only provider routing
   identifiers, operation, allowed request fields, expected ETag, and mutation
   correlation. It contains no token or arbitrary provider resource.
6. Rust refreshes the account token if needed and issues the exact allowlisted
   Google request.
7. Rust classifies the response using HTTP status, allowlisted Google reason,
   and stage only. Successful event resources are reduced to the existing safe
   provider-event contract plus newly approved capability metadata.
8. Rust calls a fixed authenticated completion/failure/conflict route.
9. Python transactionally reconciles provider-confirmed fields and linkage,
   advances the outbox row, appends audit evidence, and returns a safe Calendar
   DTO. A later UI refresh failure cannot relabel a confirmed provider write as
   failed or cause it to execute twice.

Background recovery uses the same fixed plan/result routes. Rust asks Python for
the next ready bounded plan; Python never pushes a token or opens an outbound
connection. One account owns at most one write dispatch at a time. Per-block
ordering is strict, while an unrelated failed/conflict block does not stop
other ready blocks.

### Provider request allowlist

The initial body contract contains only fields Phase 2C explicitly owns:

- `summary`;
- `description`;
- `location`;
- `transparency`;
- the all-day or timed `start`/`end` union;
- a deliberately supported recurrence rule set for a master; and
- cancellation status only for a specifically resolved occurrence where the
  recurrence operation requires it.

Create may additionally include the deterministic `id`. Requests omit
attendees, attendee response status, reminders, conference/Meet data,
attachments, extended properties, event color, ACL/sharing, calendar
properties, and unsupported special-event fields. Patch semantics preserve
omitted provider fields; arrays are never included casually because a supplied
array replaces the provider array.

The initial provider method inventory is limited to `events.insert`,
`events.get`, `events.patch`, `events.delete`, and `events.instances`, plus the
accepted read-sync methods. Ion does not use `events.update`, `events.move`,
`events.import`, `quickAdd`, batch writes, or `watch`. Although patch consumes
more quota than a full update, its omission semantics are safer for preserving
excluded provider fields in this narrow write contract.

Initial mutation eligibility is conservative:

- calendar is connected, enabled in Ion, non-deleted, and has `writer` or
  `owner` access;
- event type is ordinary `default`;
- provider does not mark the event locked;
- event has no attendees; and
- account holds the accepted write scope.

`freeBusyReader`, `reader`, and `writerWithoutPrivateAccess` calendars are
read-only in the initial implementation. Special events, attendee events,
invitation copies/responses, or any event with incomplete safe mutation
capability are read-only with a product explanation. Provider capability is
distinct from Ion flexibility. A direct-human mutation of an Ion `locked`
event remains possible only after explicit confirmation.

## Canonical and provider state model

Provider-confirmed values and unconfirmed human intent must remain
distinguishable.

- Existing Google-backed edit: the CalendarBlock/linkage retains the latest
  confirmed Google values. The outbox stores a bounded desired-field overlay.
  Calendar may render that overlay optimistically only with an explicit
  `Pending` or `Failed` treatment.
- New Google-backed create: Python creates a `source_kind=google` CalendarBlock,
  Ion metadata, deterministic pending provider linkage, and create intent in
  one transaction. Its fields are canonical local intent but are explicitly
  unconfirmed until Google returns or reconciliation finds the event.
- Provider success: one transaction applies the sanitized provider result to
  the CalendarBlock/link, records the new ETag/update time, marks the intent
  succeeded, and removes its pending projection.
- Conflict: the latest confirmed Google version becomes the visible base; the
  local intended overlay remains durable in the conflict row and is available
  only through the conflict surface.
- Ion-only metadata changes continue through their existing local transaction
  and never enter the provider outbox.

The product-level write state is derived:

| State | Meaning |
| --- | --- |
| `pending` | Durable local intent exists and has not reached a terminal result; includes queued, retry-wait, dispatching, reauthentication-blocked, and reconciliation-required operations. |
| `synced` | A provider-confirmed link exists and no unresolved write intent remains. |
| `failed` | Automatic retry ended or a non-retryable provider/domain failure requires a human action. |
| `conflict` | Google changed, deleted, or invalidated the target relative to the intent's confirmed base. |

Pending and failed writes must never be described as confirmed Google state.

## Durable outbox model

Under a separate Phase 2C-1 implementation request, one reviewed migration
will add an operational table, provisionally
`calendar_provider_write_intents`, and only the minimum capability/linkage
fields required for safe writes. Exact SQL names are implementation details,
but the accepted domain contract is:

| Field group | Required content |
| --- | --- |
| Identity | UUID, unique command ID, CalendarBlock ID, account/calendar IDs, stable provider event ID |
| Ordering | monotonic per-block sequence and optional predecessor ID |
| Operation | create, patch, cancel occurrence, delete event, or delete series; single/occurrence/series scope |
| Concurrency | source CalendarBlock revision, expected provider ETag, provider-confirmed base field mask/values |
| Intent | schema version, ordered changed-field mask, bounded normalized desired values |
| State | pending, attempting, retry-wait, reconciliation-required, reauth-blocked, conflict, terminal-failed, succeeded, or locally cancelled |
| Retry | attempt count, next attempt, last attempt, safe status class/reason, ambiguous-result flag |
| Lifecycle | created, updated, resolved, and bounded-retention timestamps |

The JSON portions, if used, are strictly versioned Ion domain values validated
on write and read. They are not arbitrary Google resources. Sensitive event
content appears only where necessary to preserve the requested local Calendar
mutation; compact audit rows store operation metadata and field names, not
titles, descriptions, locations, attendee data, or provider payload snapshots.

The migration will also need safe provider capability evidence such as ordinary
event type, provider-locked boolean, attendee-presence boolean, and any
organizer/capability boolean required to decide writability without persisting
attendee addresses. A pending create needs a link before the first sync, so the
current sync-generation requirement must be adjusted narrowly or represented
with an equivalent explicit unconfirmed-link state. No token or OAuth material
becomes schema data.

### Ordering and coalescing

- Only one unresolved provider intent per CalendarBlock may dispatch at a time.
- Unattempted edits to an unattempted create may fold into that create
  transactionally.
- Multiple unattempted edits may coalesce into one latest desired overlay while
  preserving one compact audit record for each human request.
- Once any request may have reached Google, it is never silently replaced or
  reordered. A later edit waits for reconciliation of the earlier intent.
- Deleting an unattempted pending create cancels the local intent and the local
  block without a Google call. If an attempt was ambiguous, Ion must first
  establish whether the provider event exists.
- Terminal failure or conflict blocks only later operations for the same block.

### Retry and retention

Automatic retry is capped at five provider attempts per intent. Retryable
transport, 429/rate-limit, retryable 403, and 5xx failures use persisted
exponential full-jitter backoff, capped at five minutes, and honor a bounded
provider `Retry-After` when present. The app makes no rapid retry loop. A manual
Retry is an explicit human action that creates a new retry generation and audit
entry rather than erasing prior evidence.

A 401 gets at most one Rust-owned token refresh and request retry. Refresh
failure moves the account to reauthentication and the intent to
`reauth-blocked` without consuming an endless retry budget. Re-consent does not
immediately blind-replay stale writes: recovery first reconciles their targets.

Successfully completed operational rows may be pruned after 30 days once
durable audit evidence and provider linkage are confirmed. Pruning must be
bounded, deterministic, and restart-safe. Pending, ambiguous, failed, and
conflict rows remain until explicitly resolved and are never removed by
ordinary retention. If synthetic 2C-1 measurement reveals a concrete reason to
change 30 days, implementation stops and reports it for owner decision. Runtime
queues contain only a bounded page of ready IDs; SQLite, not React or Rust
memory, retains durable work.

## Create and idempotency model

Python creates the CalendarBlock, Ion metadata, unconfirmed Google link, and
outbox intent atomically. It derives a provider event ID as lowercase base32hex
from a domain-separated SHA-256 hash of the random Ion CalendarBlock UUID,
retaining at least 160 bits. The algorithm is versioned and the exact result is
persisted before dispatch. The ID remains provider technical metadata and is
not rendered or accepted from React in a write command.

Recovery behavior:

- Timeout before Google accepts create: bounded `events.get` finds no event;
  insert retries with the same ID.
- Timeout after Google accepts create: `events.get` finds the event and its
  sanitized resource is reconciled as success; no second event is inserted.
- Duplicate-ID 409: Ion gets that exact ID. A matching/reconcilable event
  completes the intent; incompatible evidence becomes a terminal ID-collision
  conflict and is never overwritten.
- Crash after local commit but before Google: the pending row is ready after
  restart and dispatches normally.
- Crash after Google but before local completion: persisted `attempting` becomes
  `reconciliation-required`; create recovery checks the deterministic ID before
  any insert retry.

Google does not provide a generic idempotency key for every Calendar write.
Non-create idempotency therefore comes from stable target identity, ETag
preconditions, persisted attempt state, and read-after-ambiguous-result
reconciliation.

## Optimistic concurrency and field authority

Every patch, occurrence cancellation, and delete carries the last confirmed
event ETag in `If-Match`; the wildcard `If-Match: *` is forbidden. A 412 on an
ordinary supported mutation re-reads confirmed provider state and rebases the
pending write onto it, bounded by the automatic attempt budget; only drift that
outlasts that budget becomes an explicit conflict. Before retrying any ambiguous
non-create result, Rust gets the current event and Python compares only the
normalized intent field mask.

Field classes:

| Class | Fields and behavior |
| --- | --- |
| Google-confirmed/provider-authoritative | title, description, location, status, transparency, checked time union, recurrence rules and provider recurrence/exception identity |
| Ion-only | flexibility, notes, category/subtype, local enabled/hidden state; never sent to Google and never discarded by provider reconciliation |
| Automatically rebased | any provider field the pending write did not change: the provider's latest confirmed value is adopted, because the narrow changed-field body never overwrites it *(amended 2026-09-01; previously "review-mergeable", proposed but not written)* |
| Pending-human-owned | the exact provider fields the direct-human action changed: that value wins its own field for this settlement cycle, including when Google changed the same field, and ownership ends when the write confirms *(amended 2026-09-01)* |
| Structurally conflict-sensitive | master/exception/original-start identity, provider deletion, and transformation into an unsupported provider structure — contradictions no rebase can honestly resolve |

*(Amended 2026-09-01 — the owner acceptance this paragraph anticipated has been
granted.)* A provider version mismatch on an ordinary supported mutation no
longer stops dispatch. Ion re-reads confirmed provider state and rebases the
pending write's own changed-field mask onto it automatically, within the bounded
attempt budget. Whole-event merge, silent last-write-wins, and timestamp
authority remain refused, and `If-Match` stays exact and non-wildcard. Conflict
resolution is now reserved for drift that outlasts the budget and for
contradictions that cannot be reconciled deterministically. See
[Calendar interaction behavior](../CALENDAR_BEHAVIOR.md).

Conflict actions:

- **Keep Google version:** discard the pending provider-field intent, retain
  the newest confirmed Google values, preserve Ion-only metadata, and audit the
  resolution.
- **Apply my Ion changes:** rebase the selected local field mask onto the latest
  Google resource and enqueue a new `If-Match` request using its current ETag.
  This is a new explicit external-write authorization.
- **Review differences:** show only relevant normalized field differences and
  let the user select a new bounded intent. Raw provider JSON, technical IDs,
  attendee data, and ETags are not displayed.

If Google deleted the event, `Apply my Ion changes` cannot silently resurrect
it. Creating a new event is a separate explicit create action with a new
CalendarBlock/provider identity.

## Offline and reconnect model

Reasonable direct-human create, edit, move, resize, and delete intent may be
committed while offline. The UI shows a durable pending treatment and the
specific statement that the change is saved in Ion but not yet confirmed in
Google. Cached confirmed events remain available.

On reconnect or app restart:

1. Rust obtains a valid token or leaves intents reauthentication-blocked.
2. Normal read synchronization refreshes calendar access and provider state.
3. Ambiguous or stale existing targets receive bounded point reconciliation.
4. Python detects any ETag/base divergence and moves those rows to conflict.
5. Only ready, non-conflicting rows replay in per-block order.

No foreground loop polls continuously. Recovery is triggered by startup,
successful reauthentication, an explicit Sync/Retry, a bounded foreground
refresh opportunity, or enqueueing a new online intent. Previously authorized
outbox replay does not need a second confirmation. Any required destructive
confirmation is recorded when the intent is queued; a later conflict or changed
capability requires a new human decision instead of blind replay.

## Delete and cancel model

Deletion is type- and scope-specific:

- Ion-only CalendarBlock: local lifecycle/Trash behavior only; no Google call.
- Unattempted pending Google create: cancel the outbox intent and remove/Trash
  the unconfirmed local block transactionally; no external side effect.
- Confirmed non-recurring Google event: conditional `events.delete` against the
  event ETag after explicit confirmation.
- One recurring occurrence: resolve the provider instance, then conditionally
  cancel that instance so Google returns/retains an explicit cancelled
  exception with `recurringEventId` and original start.
- Entire recurring series: conditionally delete the master after a blocking
  confirmation that explicitly says every occurrence is affected.

Delete has no generic Undo promise. Audit and a local cancelled/tombstone state
support explanation and reconciliation, but recreating later would be a new
Google event with new identity. One-occurrence and entire-series choices are
never inferred from gesture context alone.

An ordinary single-event delete requires a direct confirmation in the initial
implementation. A single-occurrence cancellation names the occurrence date;
an entire-series delete uses stronger blocking copy. Deleting or structurally
changing an Ion `locked` event requires the additional accepted locked-event
confirmation.

## Recurrence write model

Generated occurrences remain renderer projections and are never written as
new canonical rows merely because a user selects one.

- Edit one occurrence: use master linkage plus the original-start union to call
  bounded `events.instances`, select the exact matching instance, and patch it
  with its own ETag. Reconciliation creates or updates one explicit exception.
- Move/resize one occurrence: same resolution, with the temporal union treated
  atomically; the stored original start never changes even when actual start
  moves.
- Cancel one occurrence: resolve the instance and conditionally cancel it;
  retain the cancelled exception so projection continues suppressing the
  generated occurrence.
- Edit entire series: patch the master with its ETag. Scalar changes and an
  explicitly supported recurrence/time change apply to the master; provider
  response plus subsequent read sync reconciles exceptions.
- Delete entire series: delete the master conditionally after blocking
  confirmation and preserve local tombstone/audit evidence.

`This and following` is deferred because Google implements it by trimming one
series and inserting another, which resets later exceptions and creates a new
identity boundary. Arbitrary RRULE text entry is not exposed. Phase 2C-5 must
define the bounded recurrence patterns Ion can create/edit, validate them
deterministically, and add destructive confirmation when a rule/time change
would remove, duplicate, or shift existing occurrences or exceptions. The
implemented bounded presets are: no recurrence for ordinary create, plus
daily, weekdays, weekly, monthly, and yearly recurrence. Existing custom rules
remain readable and are preserved during scalar edits, but their raw RRULE text
is never editable.

## Time and all-day invariants

All write contracts preserve the existing checked union.

All-day events:

- store and send civil `start.date` and exclusive `end.date`;
- never fabricate midnight timestamps or timezones; and
- resize by civil-date boundaries.

Timed events:

- store offset-bearing instants plus explicit IANA start/end timezone meaning;
- validate end after start and DST-sensitive wall time before queueing; and
- use the series timezone consistently for timed recurrence.

Timed-to-all-day, all-day-to-timed, and timezone-semantic conversion are
explicit inspector actions, never accidental drag/resize side effects. Their
confirmation shows the resulting dates/times before queueing. Temporal values
are an atomic conflict group.

## OAuth and security gate

Current Phase 2A scopes:

```text
https://www.googleapis.com/auth/calendar.calendarlist.readonly
https://www.googleapis.com/auth/calendar.events.readonly
```

Accepted Phase 2C scopes, not yet requested by the application:

```text
https://www.googleapis.com/auth/calendar.calendarlist.readonly
https://www.googleapis.com/auth/calendar.events
```

`calendar.events` is the accepted narrow event-only scope that covers
read/write across selected calendars where the account has legitimate provider
write access. `calendar.events.owned` is not used because it would exclude
shared writable calendars. The broad `calendar` scope is not needed and must
not be requested. CalendarList remains read-only. No Gmail, Tasks, ACL/sharing,
calendar-management, Meet/conference, or reminder scope is added.

This accepted gate does not alter OAuth configuration or request scopes.
Existing accounts remain read-only until a separately authorized deliberate
consent flow returns the exact required scope. Missing/partial grant is
persisted as a safe capability state, never treated as write success. Refresh
tokens remain in Keychain and access tokens remain Rust-memory-only.

Provider errors retain only allowlisted metadata: mutation stage, HTTP status
class/code, safe Google reason, retryability, reauthentication need, operation,
recurrence scope, and internal Ion mutation/block IDs. Logs and audit exclude
tokens, authorization codes, client credentials, account email, event content,
calendar payloads, provider response bodies, and private attendee data.

## Minimum Phase 2C interaction boundary

Phase 2B Calendar layout and deferred holistic polish remain accepted. Phase
2C adds only:

- create from an empty Calendar time/date through a bounded draft;
- inspector Edit for eligible events;
- direct-human timed move and resize with a keyboard-accessible alternative;
- explicit delete/cancel controls and recurrence scope choice;
- clear pending, saved-offline, terminal-failed, reauthentication, and conflict
  treatments; and
- a bounded conflict detail surface with Keep Google, Apply my Ion changes, and
  Review differences; and
- Undo for a confirmed edit, as an ordinary reverse write rather than a
  rollback or an undo stack.

Calendar interaction semantics follow [`CALENDAR_BEHAVIOR.md`](../CALENDAR_BEHAVIOR.md),
which is the contract for this surface: explicit confirmation is required only
where an interaction removes confirmed occurrences, and the recurrence-scope
chooser is a focus-trapped modal whose Cancel mutates nothing.

Pointer-captured movement or resize renders only transient grid feedback while
the pointer is down, then commits the validated interval at release. A recurring
event asks for scope at that moment, and that choice is the last action
required; no review step and no second save stand between the gesture and the
write. Movement may cross visible day columns; resize exposes both timed edges. Failed UI refresh after a confirmed mutation preserves the
confirmed result and marks only the projection stale. Provider-ineligible
events remain inspectable and explain why editing is unavailable. No attendee,
invitation, Meet, reminder, calendar-management, AI scheduling, or
Task-to-block affordance appears.

## Auditability

Compact local audit evidence records:

- direct-human write requested;
- durable intent queued;
- provider mutation attempted;
- retry scheduled or reauthentication required;
- provider mutation succeeded;
- provider mutation failed terminally;
- ambiguous result entered reconciliation;
- conflict detected; and
- Keep Google, Apply Ion, or reviewed-field resolution chosen.

Evidence includes safe internal IDs, operation, recurrence scope, changed field
names, attempt number, status/reason class, source and resulting canonical
revision, timestamps, and direct-human versus recovery executor provenance. It
does not include event titles/descriptions/locations, raw before/after payloads,
tokens, credentials, authorization material, attendee identities, or full
provider errors.

## Failure and deterministic recovery matrix

| Failure | Required behavior |
| --- | --- |
| Offline create | Commit pending block/link/outbox atomically; replay after reconnect with deterministic event ID. |
| Offline edit/move/resize | Keep last confirmed provider base plus durable desired overlay; show pending; reconcile ETag before replay. |
| Timeout before create accepted | Bounded get by deterministic ID; if absent, retry insert with the same ID. |
| Timeout after create accepted | Get finds the event; sanitize and reconcile success without another insert. |
| Token expires during mutation | Rust refreshes once and retries once; invalid refresh blocks for reauthentication. |
| Crash after local commit, before Google | Pending row resumes after restart. |
| Crash after Google, before local reconciliation | Attempt becomes reconciliation-required; point-get and compare before any retry. |
| Stale ETag / 412 | Fetch latest sanitized event, persist conflict, and require explicit resolution. |
| Provider 404 on edit | Treat as missing/inaccessible, refresh access and event state, then conflict or fail; never create blindly. |
| Provider 404/410 after ambiguous delete | Confirm target absence/deleted state and reconcile delete success; ordinary 410 sync-token handling remains full resync. |
| Recurrence exception disappeared | Re-resolve by master plus original start; if absent, create an occurrence-missing conflict rather than targeting another instance. |
| Occurrence resolution was rejected and the confirmed master later changed | Reclassify the legacy failure as a stale-identity conflict during bounded recovery; do not retry the old mutation. |
| Google changes event while Ion intent pending | Preserve intent, reconcile newest confirmed provider base, and conflict before replay. |
| Permission/access role changes | Stop writes, refresh CalendarList capability, retain intent as failed/conflict, and require a valid writable target or Keep Google resolution. |
| Non-retryable 400/403 | Persist a terminal safe reason; occurrence-resolution target rejection is instead a reviewable identity conflict. Do not loop. |
| Retryable quota/5xx/transport failure | Persist next retry with bounded backoff and attempt ceiling; unrelated blocks continue. |

## Performance and lifecycle

- SQLite, not an in-memory queue, owns all durable pending work.
- Rust loads one bounded ready page and dispatches at most one write per account
  at a time.
- React receives bounded visible Calendar projections and summary write state,
  not the whole outbox or a duplicate whole-calendar mirror.
- No daemon, launch agent, webhook, rapid polling, permanent retry timer, or
  worker per account/calendar is introduced.
- Startup/foreground/manual triggers reuse coordinated Calendar scheduling.
- Backoff timestamps survive restart; hidden/background UI owns no write loop.
- Completed operational state is compacted under a documented policy while
  audit remains compact and content-free.
- Soak acceptance includes a large synthetic pending/failed set, reconnect
  replay, idle return, listener/timer cleanup, bounded memory, and no monotonic
  growth under the accepted performance policy.

## Explicitly deferred scope

- attendee list changes, invitation responses, or organizer/guest workflows;
- notification-delivery policy for attendee events;
- Meet/conference creation or mutation;
- reminders or default-reminder configuration;
- attachments, event colors, extended properties, or special event types;
- moving an event between calendars or changing organizer;
- calendar creation/deletion, CalendarList mutation, ACL/sharing, or ownership
  transfer;
- arbitrary RRULE editing outside an accepted bounded rule set;
- Google Tasks, Gmail, webhooks/push channels, cloud relay, LAN, mobile, or a
  generic provider framework;
- automated scheduling, AI-authored Calendar writes, automatic conflict
  resolution, or autonomous mutation authority; and
- generic Undo, event sourcing, or whole-object provider version history.

## Destructive and external-write boundaries

The owner accepted these Phase 2C architecture boundaries. Their implementation
still requires a separate scoped task, and real-provider acceptance operations
require explicit authorization of the test account/calendar and exact actions:

- OAuth event-write scope and account re-consent;
- every create, edit, move, resize, occurrence cancel, event delete, and series
  mutation as a new provider external side effect;
- deterministic client-supplied provider IDs;
- the outbox/capability migration and interrupted-migration recovery plan;
- automatic replay of previously authorized pending intent after reconnect;
- confirmation copy and behavior for delete, occurrence, and entire-series
  actions *(amended 2026-09-01: `locked` no longer gates a direct human edit —
  it constrains Ion's own automation)*;
- any future relaxation of event eligibility still requires new owner
  acceptance, especially attendee events,
  `writerWithoutPrivateAccess`, special event types, or cross-calendar moves;
- *(granted 2026-09-01.)* Automatic reconciliation of ordinary provider version
  drift is now accepted owner direction: a pending direct-human write re-aims at
  freshly confirmed provider state and retries its own changed-field mask, so
  fields the human did not touch are never overwritten. This remains bounded and
  ETag-conditional; whole-event merge, silent last-write-wins, and timestamp
  authority are still refused. See
  [Calendar interaction behavior](../CALENDAR_BEHAVIOR.md); and
- any broader scope, notification, provider feature, trust boundary, or
  autonomous authority.

## Owner decisions locked

1. **OAuth coverage:** use `calendar.events` so legitimate shared calendars
   with writer authority can be supported; do not use `calendar.events.owned`,
   broad `calendar`, or unrelated scopes.
2. **Initial eligibility:** require owner/writer, ordinary default,
   non-provider-locked, attendee-free events and explicit write-scope
   re-consent.
3. **Attendee events:** keep attendee/invite-bearing events entirely read-only;
   do not mutate attendees, invitations, RSVP state, organizer semantics, or
   conferencing.
4. **Conflict merging:** *(amended 2026-09-01 by owner decision.)* Ordinary
   ETag drift rebases automatically onto freshly confirmed provider state,
   re-sending only the user's changed fields. No whole-event merge, no silent
   last-write-wins, and no timestamp authority. Drift outlasting the bounded
   attempt budget, and genuinely unmergeable contradictions, stay explicit.
5. **Delete recoverability:** use confirmation plus tombstone/audit without
   provider Undo; recreation gets new identity and whole-series deletion uses
   stronger blocking confirmation.
6. **Recurrence surface:** keep it bounded and deterministic in 2C-5 while
   deferring arbitrary RRULE and `this and following`; exact editor choices
   remain a bounded 2C-5 product-design decision.
7. **Operational retention:** unresolved, failed, conflict, and ambiguous rows
   remain until explicit resolution. Successful rows may be pruned after 30
   days while compact audit remains durable. Any measured need to change 30
   days is a stop-and-report owner decision.

## Recommended independently testable substeps

### 2C-1 — Write foundation, OAuth, and durable outbox

**Implemented; owner acceptance pending.** Exact implementation names and
exclusions are frozen in [Phase 2C-1 Contract](PHASE_2C_1_CONTRACT.md).

- Use accepted ADR 0021 and its exact scope boundary.
- Add the one reviewed migration for outbox and provider capability evidence.
- Add fixed enqueue/next-attempt/result/recovery routes and fixed Tauri
  commands without enabling UI writes yet.
- Implement exact scope detection/re-consent, access-role/event eligibility,
  bounded retry, reauth blocking, audit, and crash-state repair against
  synthetic providers.
- Acceptance: fresh/upgrade/downgrade/re-upgrade/data preservation; no Google
  write reachable from UI; deterministic restart/outbox tests; packaged trust
  boundary unchanged.

### 2C-2 — Create

**Implemented; owner real-write acceptance pending.** Migration `0007` was
reviewed and found sufficient, so no schema change was introduced.

- Add bounded create draft and attendee-free ordinary Google event insertion.
- Implement deterministic base32hex ID, ambiguous-result get/retry, duplicate
  prevention, offline create, and success reconciliation.
- Acceptance: no duplicate across every crash/timeout cut point; pending never
  appears synced; all-day/timed/DST invariants pass.

### 2C-3 — Edit, move, and resize

**Implemented; owner real-write acceptance pending.** Migration `0007` was
reviewed and found sufficient, so no schema change was introduced. Automated
verification uses only synthetic provider data and does not initiate OAuth or
Google mutations.

- Add inspector edit plus direct-human timed move/resize and keyboard path.
- Use bounded patches and `If-Match`; add pending overlays. *(Amended
  2026-09-01: the `locked` flexibility flag governs Ion's automation, not the
  owner's direct action, so it adds no confirmation to a human edit.)*
- Acceptance: stale ETags never overwrite; unrelated provider fields remain
  untouched; temporal conversions require explicit action.

### 2C-4 — Delete and cancellation

**Implemented; owner real-delete acceptance pending.** Migration `0007` was
reviewed and remains sufficient. Automated verification uses synthetic state
and does not initiate OAuth or Google mutations. Recurring occurrence and
whole-series deletion remain deliberately assigned to Phase 2C-5.

- Add local-only, unattempted-create, confirmed single-event, and provider
  missing/deleted semantics with explicit confirmation.
- Acceptance: delete ambiguity reconciles deterministically, no accidental
  recurrence cascade, and no false Undo claim.

### 2C-5 — Recurrence writes

**Implemented; owner real-write acceptance pending.** Migration `0007` remains
sufficient. Automated verification uses synthetic recurrence state and does
not initiate OAuth or mutate Google Calendar.

- Resolve instances by master plus original start; support one occurrence and
  whole series for edit/move/resize/cancel/delete.
- Define and test the bounded recurrence rule surface and destructive
  confirmations. Keep `this and following` absent.
- Acceptance: moved/cancelled exceptions preserve identity, masters do not
  duplicate, and all-day/DST recurrence remains correct.

### 2C-6 — Conflict, offline, and acceptance hardening

**Keep Google / Apply Ion / Review differences implemented in a bounded
stabilization pass; owner real-write acceptance pending.** *(Historical record.
Owner acceptance in 2026-09-01 superseded the policy that routed ordinary
version drift here: these actions remain, but only for drift that outlasts the
automatic attempt budget and for genuinely unmergeable contradictions. They are
not ordinary Calendar workflow.)* A conflicted block
now has a complete human exit path through three new fixed Ion-ID routes and
Tauri commands, using the existing `0007` outbox schema (no migration): Keep
Google's version cancels only the conflicting intent and preserves Ion-only
metadata; Apply my Ion change rebases the stored field mask onto the freshly
confirmed provider ETag as a new explicit write authorization (never the
stale conflict row's ETag, never `If-Match: *`, and never a silent
resurrection of a provider-deleted event); Review differences returns a
bounded, normalized comparison with no raw provider object. Automated
verification used only synthetic conflict state.

Owner acceptance of the first conflict-resolution build found three
remaining defects, now repaired: Apply my Ion changes stalled on a recurring
occurrence because the rebase refreshed only the intent's own ETag and not the
master ETag embedded in its recurrence identity, so the new write failed its
own dispatch preflight and re-conflicted; a conflicted occurrence displays on
the master row (it never materializes an exception), but resolution skipped
occurrence-scoped intents for master rows, so those rows reported "no conflict
to resolve" forever; and a terminally failed write had no human exit at all,
permanently serializing its block. Resolution now selects exactly what the
projection displays, the rebase refreshes every piece of provider authority
while preserving identity, and Keep Google / Apply my Ion changes also resolve
a failed pending intent (the latter as the accepted explicit manual retry).
Reconnect ordering, permission/capability loss, retention, and bounded
synthetic soak coverage are implemented and green.

**`This and following events` implemented (2026-09-01) under explicit owner
authorization.** The owner authorized a narrow extension of the recurrence
provider-body contract: the same five bounded preset families, plus a
domain-generated `UNTIL` terminator used only to end an old master before a
selected occurrence. Ion implements Google's real series-split semantics --
conditionally trim the old master, then create a new recurring master beginning
at the selected occurrence -- never a sweep of per-occurrence exceptions. Both
provider operations, the new canonical master, its inherited Ion-only metadata,
and its deterministic provider identity are persisted in one transaction before
any Google call. Ordering is durable: the new master is stored `queued` with
`predecessor_intent_id` pointing at the trim and is released only when the trim
is provider-confirmed; a trim that is cancelled retires the future master with
it, while `Apply my Ion changes` re-chains it onto the re-authorized trim. The
option is offered only where Ion can faithfully continue the pattern and where
it differs from `All events`: a custom provider RRULE and the first occurrence
both withhold it truthfully. Delete `this and following` is the trim alone. No
migration, no new provider method, and no new OAuth scope were required.

Remaining for this substep:

- Owner real-calendar acceptance of the repaired conflict and failure exits,
  and of the series split.
- Run the repository gate, migration matrix, fresh ARM64 sidecar/Tauri package,
  packaged startup/authentication/shutdown/listener/orphan/security checks, and
  an owner-authorized synthetic then real-account mutation acceptance plan.
- No owner account mutation occurs before the owner separately authorizes the
  exact manual test calendar and operations.

## Implementation entry conditions

- ADR 0021 and all seven owner decisions are accepted.
- Exact schema/migration, DTO, route, command, provider method, and OAuth scope
  inventory must be reviewed within the separately authorized 2C-1 task before
  its implementation proceeds.
- Threat review proves tokens remain Rust-only and provider bodies are
  allowlisted.
- Deterministic synthetic test plan covers every failure-matrix row and every
  destructive recurrence scope.
- No application code, dependency, migration, requested OAuth scope, or real
  provider state changes as part of this architecture gate.

## References

- [Accepted ADR 0021](../decisions/0021-google-calendar-write-outbox-and-conflicts.md)
- [Master Specification](../PRODUCT_SPEC.md)
- [Phase 2A](PHASE_2A.md)
- [Phase 2B](PHASE_2B.md)
- [Architecture](../ARCHITECTURE.md)
- [Data model](../DATA_MODEL.md)
- [Security](../SECURITY.md)
- [Integrations](../INTEGRATIONS.md)
- [Performance and Resource Policy](../PERFORMANCE.md)
- [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google Calendar events](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Google Calendar event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Google Calendar event patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch)
- [Google Calendar event deletion](https://developers.google.com/workspace/calendar/api/v3/reference/events/delete)
- [Google Calendar recurring events](https://developers.google.com/workspace/calendar/api/guides/recurringevents)
- [Google Calendar resource versions](https://developers.google.com/workspace/calendar/api/guides/version-resources)
- [Google Calendar errors](https://developers.google.com/workspace/calendar/api/guides/errors)
