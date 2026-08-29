# Integration Boundaries

## Status: Google Calendar Phase 2A active; other integrations deferred

Integrations are adapters around Ion's local authority; they do not become its
primary storage. Google Calendar is the first active adapter under ADR 0018.

| Integration                                    | Target phase/status             |
| ---------------------------------------------- | ------------------------------- |
| Google Calendar                                | Phase 2A read-sync foundation   |
| Canvas                                         | Phase 3, deferred               |
| Local AI                                       | Phase 4, deferred               |
| Gmail                                          | Phase 5, deferred               |
| Obsidian-compatible knowledge/vault operations | Phase 7, deferred               |
| GitHub                                         | Phase 8, deferred               |
| Cloud AI / Deep Ask                            | Phase 12, deferred              |
| Mobile companion                               | TBD; security-gated by ADR 0004 |

Any other integration requires a scoped route, privacy review, and owner
approval before implementation.

## Google Calendar Phase 2A contract

- Authority: Google owns synchronized event fields; SQLite owns canonical
  CalendarBlock identity and offline state; Ion owns block flexibility/notes
  and enabled-in-Ion calendar selection.
- Scope: `calendar.calendarlist.readonly` and `calendar.events.readonly` only.
- Credential owner: Rust + macOS Keychain; no token in React, Python, SQLite,
  logs, docs, fixtures, screenshots, or source.
- Discovery: full CalendarList pagination at connect, including hidden/deleted
  metadata. Primary or Google-selected readable calendars default enabled.
  Later Ion selection never writes Google's selected/hidden state.
- Events: unexpanded recurrence with deleted entries, full then incremental
  per calendar, stable parameters across pages, persisted next sync token,
  bounded retry, and safe 410 full resync.
- Identity: provider event ID reconciles within one calendar. iCalUID is a
  separate non-unique correlation value. ETag/provider revision metadata is
  retained for later explicit conflict handling.
- Failure: cached canonical blocks remain readable. Retry/reauth/failure is
  explicit; unavailable provider data is never invented. Provider rejection
  diagnostics retain only allowlisted status/reason classes and never the
  Google response payload.
- Mutations: Phase 2A makes no Google event write/delete request. Disconnect
  records local state, attempts revocation where feasible, clears Keychain and
  memory tokens, and preserves cached blocks.

Authoritative provider references:

- [OAuth 2.0 for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
