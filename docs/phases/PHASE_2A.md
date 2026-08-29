# Phase 2A — Google Account + Calendar Sync Foundation

## Objective

Establish a production-quality, macOS-local Google Calendar read-sync path so
Ion can connect multiple accounts, discover calendars, maintain an independent
enabled-in-Ion selection, and keep canonical CalendarBlocks available offline
without exposing Google credentials outside Rust.

## Scope

- Native desktop Google OAuth in the system browser using an ephemeral
  `127.0.0.1` callback, S256 PKCE, and cryptographic state.
- Exactly `calendar.calendarlist.readonly` and `calendar.events.readonly`.
- Refresh tokens in macOS Keychain, access tokens in Rust memory, and only
  non-secret account/scope/auth metadata plus a Keychain locator in SQLite.
- Multi-account-capable account and CalendarList discovery records. Ion owns
  `enabled_in_ion`; Google `selected` and `hidden` are read-only observations.
- Canonical CalendarBlocks with a strict all-day/timed union, IANA timezone
  preservation, provider identity/ETag metadata, recurrence masters and
  explicit exceptions, retained cancelled exceptions, and separate Ion-only
  metadata.
- Full then per-calendar incremental Events sync with pagination, persisted
  sync tokens, duplicate-safe reconciliation, bounded retry/backoff, explicit
  failure/reauth states, and safe HTTP 410 full resync.
- Fixed Tauri commands and a minimal setup/status surface for connect,
  discovery, selection, manual sync, reauthentication, and disconnect/revoke.
- One sync attempt at app launch plus rate-bounded foreground and manual sync.
  Cached canonical state remains readable when Google is unavailable.

## Explicit exclusions

- No Google event create, edit, move, or delete request.
- No Google Tasks, Gmail, ACL, sharing, broad calendar-management, webhook,
  push channel, daemon, launch agent, cloud relay, LAN access, or mobile work.
- No generated recurrence occurrence table; generated instances remain a
  future rebuildable projection.
- No Phase 2B calendar timeline, drag/drop, scheduling, free/busy planning, or
  FocusSession UI.
- No silent last-write-wins. Provider ETags and canonical revisions prepare
  the Phase 2C conflict boundary but no write conflict is resolved here.
- No real account, client configuration, secret, token, calendar payload,
  screenshot, or fixture in the repository.

## Local OAuth configuration

Ion reads `google-oauth.json` from its macOS Application Support directory,
shown exactly in the Calendar setup UI. The file has this shape:

```json
{
  "client_id": "YOUR_DESKTOP_CLIENT_ID.apps.googleusercontent.com",
  "client_secret": "OPTIONAL_DESKTOP_CLIENT_SECRET"
}
```

The repository contains only
[`config/google-oauth.example.json`](../../config/google-oauth.example.json),
whose value is synthetic and unusable. A real local configuration must never
be copied into Git, tests, documentation, screenshots, or logs.

## Acceptance

- OAuth tests cover high-entropy PKCE, exact state/path/code validation,
  cancellation/failure paths, exact scopes, and renderer serialization that
  contains no token, verifier, authorization code, or Keychain locator.
- A fake token store covers Keychain abstraction behavior without touching a
  real credential.
- Synthetic reconciliation tests cover discovery/default selection, independent
  Ion selection, initial paginated sync, incremental sync, duplicate replay,
  event ID versus iCalUID, timed/DST and all-day values, recurrence master,
  moved and cancelled exceptions, ordinary cancellation, audit provenance,
  cached reads, retry state, reauth, disconnect, and 410-style full resync.
- Migration evidence covers fresh install, Phase 1 upgrade/preservation,
  downgrade to `0004_today_planning`, and re-upgrade on isolated databases.
- Repository validation, a fresh ARM64 sidecar, a Tauri production build, and
  feasible packaged startup/authentication/shutdown/orphan/listener checks pass.
- Owner performs the first real Google Testing-mode connect/discovery/read-sync
  and manually accepts the setup/status UI before any commit or push.

## References

- [ADR 0018](../decisions/0018-google-calendar-read-sync-foundation.md)
- [Architecture](../ARCHITECTURE.md)
- [Data model](../DATA_MODEL.md)
- [Security](../SECURITY.md)
- [Integrations](../INTEGRATIONS.md)
