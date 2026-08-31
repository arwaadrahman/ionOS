# Phase 2C-1 Frozen Implementation Contract

## Status and authority

**Frozen for the owner-authorized Phase 2C-1 implementation.** This document
translates accepted ADR 0021 and the accepted Phase 2C gate into exact names
for this bounded implementation. It does not authorize a Calendar write UI,
Google event mutation, or automatic OAuth re-consent.

## Migration and durable schema

Migration `0007_calendar_write_foundation` upgrades the accepted Phase 2B
schema without rewriting an earlier migration.

### Existing-table additions

- `google_accounts.calendar_write_scope_state`: `read_only`, `write_granted`,
  or `reauth_required`; existing rows default to `read_only`.
- `google_event_links.link_state`: `confirmed` or `pending_create`; existing
  rows default to `confirmed`.
- `google_event_links.provider_event_type`: `default`, `special`, or `unknown`.
- `google_event_links.provider_locked`: safe provider capability boolean.
- `google_event_links.has_attendees`: presence only; attendee identities are
  never persisted.
- `google_event_links.last_seen_sync_generation` becomes nullable only for an
  explicit `pending_create` link. A confirmed link still requires a sync
  generation.

### `calendar_provider_write_intents`

The operational outbox stores:

- UUID `id`, unique UUID `command_id`, `calendar_block_id`, `account_id`, and
  `calendar_id`;
- persisted `provider_event_id`, which is internal provider routing metadata;
- monotonic per-block `sequence` and optional `predecessor_intent_id`;
- `operation`: `create`, `patch`, `cancel_occurrence`, `delete_event`, or
  `delete_series`;
- `recurrence_scope`: `single`, `occurrence`, or `series`;
- ordered `changed_fields_json`, versioned bounded `base_values_json`, and
  versioned bounded `desired_values_json`;
- `expected_provider_etag`, `source_block_revision`, and `schema_version=1`;
- state, attempt/retry metadata, safe failure class/reason, timestamps,
  retention eligibility, and `direct_human` provenance.

The table never stores a token, credential, attendee identity, full Google
resource, raw response, account email, or an audit payload snapshot.

### `calendar_provider_write_audit`

Compact append-only lifecycle evidence stores safe Ion IDs, operation and
field names, attempt count, safe class/reason, state transition, revisions,
timestamp, and executor provenance. Event title, description, location,
attendee data, account email, credentials, and provider payloads are excluded.

## State machine

The exact states are:

`queued`, `ready`, `attempting`, `retry_wait`, `reauth_required`, `conflict`,
`ambiguous`, `failed`, `completed`, and `cancelled`.

Allowed transitions are:

- `queued → ready | cancelled`
- `ready → attempting | cancelled`
- `attempting → completed | retry_wait | reauth_required | conflict |
  ambiguous | failed`
- `retry_wait → ready | cancelled`
- `reauth_required → ready | cancelled`
- `ambiguous → attempting | conflict | failed | cancelled`
- `conflict → cancelled`
- `failed → cancelled`

`completed` and `cancelled` are terminal. Starting an attempt persists
`attempting`, the incremented count, and audit evidence before any future
provider call. On restart, every persisted `attempting` row becomes
`ambiguous` before dispatch selection. Invalid transitions are rejected.

## Idempotency and retry

Version `ion-google-event-id-v1` derives a Google ID from a domain-separated
SHA-256 digest of the CalendarBlock UUID. The first 160 bits are encoded as 32
lowercase base32hex characters. The value is opaque, content-free, stable, and
persisted before any future create dispatch.

Automatic attempts are capped at five. Retry delay is exponential full jitter
over `0..min(30 * 2^(attempt-1) seconds, 300 seconds)`, supplied by an injected
bounded random value for deterministic tests. `retry_wait` always persists its
next-attempt timestamp. No worker, timer, or polling loop is added.

Completed rows set `prune_after` to resolution time plus 30 days. Bounded prune
deletes only eligible completed rows after confirming compact audit exists.
Every unresolved or non-success terminal row remains indefinitely.

## Python DTO and fixed local API

The Python owner exposes these fixed routes:

- `GET /v1/calendar/write-foundation`: bounded renderer-safe account,
  calendar, block capability, and pending-state summaries.
- `POST /v1/calendar/internal/write-intents`: validate an Ion block/revision
  and enqueue one typed, bounded direct-human intent. Provider correlation and
  ETag are derived from trusted SQLite linkage, never accepted as request
  authority.
- `POST /v1/calendar/internal/write-intents/ready`: return a bounded internal
  ready page for Rust, with at most one plan per account.
- `POST /v1/calendar/internal/write-intents/recover`: repair persisted
  `attempting` rows to `ambiguous` and promote due `retry_wait` rows to
  `ready`.
- `POST /v1/calendar/internal/write-intents/{intent_id}/transition`: apply one
  validated state transition and safe attempt/result metadata.
- `POST /v1/calendar/internal/write-intents/prune`: bounded completed-only
  retention pruning.

All request models forbid unknown fields. Changed fields are an enum and
values use a bounded versioned Ion model; arbitrary Google JSON is invalid.

## OAuth and capability projection

The ordinary connect flow continues to request exactly CalendarList read-only
plus Events read-only. A separate typed `CalendarWriteReconsent` OAuth mode is
defined and tested for exactly CalendarList read-only plus Calendar Events
read/write, but no renderer command or automatic trigger invokes it in 2C-1.

Python records `write_granted` only when the exact accepted write scope set is
returned through the trusted Rust connect/re-consent path. Existing and partial
grants remain read-only. Initial block eligibility requires all of:

- connected account with `write_granted`;
- enabled, non-deleted calendar with `writer` or `owner` access;
- confirmed linkage for an ordinary/default, non-provider-locked event;
- no attendees.

The renderer receives only `eligible` plus an allowlisted reason. It never
derives provider authority from display strings.

## Tauri and Rust boundary

2C-1 adds one renderer-callable fixed command:

- `get_calendar_write_foundation`

It reads only the safe Python projection. Enqueue, transition, dispatch-plan,
recovery, and prune routes remain Rust-internal helpers with fixed DTOs; 2C-1
adds no renderer write command and no real provider dispatch call.

The frozen future provider method inventory is:

- allowed: existing read-sync methods plus `events.insert`, `events.get`,
  `events.patch`, `events.delete`, and `events.instances`;
- forbidden: `events.update`, `events.move`, `events.import`, `quickAdd`, batch
  writes, and `watch`/webhooks.

Typed request construction requires fixed Google Calendar API origins and
paths, URL-encoded internal provider IDs, an allowlisted method, bounded body,
and a non-wildcard ETag for conditional patch/delete. The 2C-1 implementation
constructs and tests requests but never sends them.

## Safe provider result classification

The exact safe result classes are `success`, `retryable_transport`,
`retryable_backend`, `retryable_quota`, `reauthentication_required`,
`stale_precondition`, `duplicate_or_ambiguous_create`, `provider_not_found`,
`invalid_target`, and `terminal_provider_rejection`. Only allowlisted Google
reason classes influence classification; raw bodies never cross into React,
Python, audit, or logs.

## Synthetic failure and migration verification

Deterministic tests cover success, timeout/ambiguous create, duplicate-ID
reconciliation, 401, permanent 403, 404, 409 duplicate, 412, 429, 5xx,
restart in `retry_wait` and `ambiguous`, read-only denial, writer/owner
eligibility, attendee denial, provider-lock denial, invalid transitions,
five-attempt ceiling, stable jitter, and completed-only retention.

The migration matrix covers fresh install, upgrade from `0006`, downgrade to
`0006`, re-upgrade, and preservation of organizer records, CalendarBlocks,
account/calendar/linkage, Ion metadata, and provider sync metadata using only
isolated synthetic databases.
