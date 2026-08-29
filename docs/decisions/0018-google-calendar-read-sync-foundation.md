# ADR 0018: Google Calendar read-sync foundation

**Status:** Accepted  
**Date:** 2026-08-29

## Context

The Master Specification makes Google Calendar authoritative for scheduled
time and Ion's local SQLite database authoritative for canonical structured Ion
records. Phase 2A needs a secure read foundation before calendar editing,
planning, or conflict resolution can exist. The owner completed the Phase 2
architecture gate and explicitly authorized this schema, narrow Rust
dependencies, fixed local surfaces, and documentation.

## Decision

Rust owns Google OAuth, PKCE/state, the temporary loopback callback, system
browser launch, refresh/access tokens, macOS Keychain operations, token refresh,
and all Google HTTPS. OAuth uses a Desktop client, an ephemeral
`127.0.0.1` listener, S256 PKCE, cryptographic state, and no embedded WebView.
Only CalendarList read-only and Events read-only scopes are requested. Refresh
tokens persist only in Keychain; access tokens and authorization flow material
remain memory-only. React and Python never receive them.

SQLite stores non-secret multi-account metadata, the Keychain locator, calendar
discovery metadata, Ion's independent calendar selection, per-calendar sync
state/tokens, canonical CalendarBlocks, separate Ion-only block metadata, and
Google event identity/version linkage. `event.id` is the per-calendar
reconciliation identity; `iCalUID` is separately indexed and is not unique.
Google owns synchronized event fields; Ion owns flexibility and notes.

CalendarBlock time is an explicit all-day/timed union. Date-only values stay
date-only with exclusive end dates. Timed values retain RFC 3339 offsets and
IANA zones. Recurrence persists one canonical master plus explicit moved or
cancelled exceptions. Generated occurrences are derived and are not stored as
hundreds of canonical rows.

Each enabled calendar performs an unexpanded, deletion-inclusive full Events
sync followed by incremental requests using its persisted `nextSyncToken`.
Pagination is applied under one generation. HTTP 410 starts a new full
generation; unseen provider records become locally cancelled while Ion-only
metadata survives. Cancelled recurrence exceptions are retained. Replayed
provider pages are duplicate-safe. Provider ETags and canonical revisions form
the Phase 2C conflict-ready boundary; Phase 2A performs no provider write.

Sync-originated canonical creates/updates/cancellations append compact audit
metadata transactionally with `integration` / `automated` provenance and no
payload snapshot or secret. Retryable provider failures use bounded exponential
request backoff and persist a later retry state. Invalid or unavailable refresh
credentials move the account and its calendars to explicit reauthentication.
Cached canonical blocks remain available offline.

The renderer receives only fixed status/connect/select/sync/disconnect Tauri
commands and product DTOs. It receives no provider token, OAuth code, PKCE
verifier, Keychain locator, service address, backend credential, generic HTTP,
filesystem, shell, or process authority. App launch and rate-bounded foreground
or manual sync run inside the existing desktop process; no daemon, webhook,
launch agent, cloud relay, LAN service, or mobile boundary is introduced.

## Consequences

- Phase 2A adds migration `0005_google_calendar_foundation` and narrow Rust
  dependencies for SHA-256/Base64URL PKCE, rustls HTTPS, async retry timing, and
  the native macOS Security Framework.
- The integration remains useful offline and safe to re-run after pagination,
  transient failure, process restart, or an invalid sync token.
- Disconnect first records local disconnected state, then attempts provider
  revocation where reachable, deletes the Keychain item, and clears the
  memory-only access token. Cached blocks remain local.
- Google calendar selection/visibility is never rewritten by discovery or Ion's
  enabled selection.
- Phase 2B may build the calendar interface over these canonical blocks. Phase
  2C must add explicit ETag conflict handling before enabling provider writes.

## Alternatives considered

- Python Google SDK or tokens in Python/React: rejected because it broadens the
  credential and renderer trust boundary.
- Embedded WebView login: rejected by the native OAuth security model and
  Google's embedded user-agent policy.
- Expanded recurring instances as canonical rows: rejected because occurrences
  are rebuildable and exceptions need stable series identity.
- Polling daemon, push webhook, or cloud relay: rejected because each expands
  lifecycle or network trust beyond Phase 2A.
- Broad `calendar` or write scopes: rejected because Phase 2A is read-only.
- Last-write-wins: rejected because Phase 2C requires explicit provider-version
  conflict handling.

## References

- [Phase 2A](../phases/PHASE_2A.md)
- [Master Specification](../PRODUCT_SPEC.md)
- [ADR 0004](0004-macos-local-trust-boundary.md)
- [ADR 0008](0008-production-service-lifecycle.md)
- [ADR 0009](0009-local-process-authentication.md)
- [Google OAuth for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google Calendar incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
