# Integration Boundaries

## Status: Google Calendar read-only; Phase 2C writes in controlled rebuild

Integrations are adapters around Ion's local authority; they do not become its
primary storage. Google Calendar is the first active adapter under ADR 0018.

| Integration                                    | Target phase/status                 |
| ---------------------------------------------- | ----------------------------------- |
| Google Calendar                                | Read-only; 2C writes rebuilding     |
| Google Tasks                                   | Optional future bridge; owner-deferred, not desktop v1 |
| Canvas                                         | Phase 3, deferred                   |
| Local AI                                       | Phase 4, deferred                   |
| Gmail                                          | Phase 5, deferred                   |
| Obsidian-compatible knowledge/vault operations | Phase 7, deferred                   |
| GitHub                                         | Phase 8, deferred                   |
| External developer-agent bridge                | Narrow precursor allowed; deferred |
| Cloud AI / Deep Ask                            | Phase 12, deferred                  |
| Mobile companion / cross-device sync           | Post-v1 platform expansion; security-gated |

Any other integration requires a scoped route, privacy review, and owner
approval before implementation.

Google Tasks is not Ion's primary task system: canonical Ion Tasks remain
primary. The owner-approved [product / roadmap amendment](PRODUCT_SPEC.md#owner-approved-product--roadmap-amendment--2026-08-31)
keeps a future bridge optional and deferred, along with the future
multi-calendar mirroring direction; neither is active Phase 2 work.

## External development-agent direction

The first development-agent integration is a lightweight Claude Code companion
for explicitly registered projects, not a general agent-provider framework.
Its evidence vocabulary remains extensible to Codex and future agents. After
explicit user action, Ion may generate a compact repo-driven handoff/prompt and
eventually ask narrow Rust-owned commands to launch or resume an allowlisted
agent executable. External tools retain authentication and lifecycle
ownership; Ion never supplies or captures their credentials and the renderer
gains no generic shell/process capability.

Progress input should use bounded structured lifecycle/tool events when the
external tool supports them, plus deterministic Git status and meaningful
test/build/commit checkpoints. Ion does not screen-scrape IDEs, mirror agent
sessions, store complete transcripts, continuously embed repositories, or run
continuous expensive full diffs. Detailed authority, privacy, evidence, and
roadmap boundaries are accepted in ADR
[0020](decisions/0020-external-developer-agent-bridge.md).

This narrow companion may be separately scoped before Phase 8 when it helps
build Ion itself. Full GitHub, portfolio, and project-development intelligence
remains Phase 8. Cloud Deep Ask remains a separate Phase 12-capable integration
with Ion-owned Keychain credentials, privacy filtering, and cost controls.

## Google Calendar Phase 2A/2B contract

- Authority: Google owns synchronized event fields; SQLite owns canonical
  CalendarBlock identity and offline state; Ion owns block flexibility/notes,
  nullable category/subtype, and local calendar hide state
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
  retained for conditional writes and automatic rebase.
- Failure: cached canonical blocks remain readable. Retry/reauth/failure is
  explicit; unavailable provider data is never invented. Provider rejection
  diagnostics retain only allowlisted status/reason classes and never the
  Google response payload.
- Mutations: Phase 2A makes no Google event write/delete request. Disconnect
  records local state, attempts revocation where feasible, clears Keychain and
  memory tokens, and preserves cached blocks.
- Interface: Phase 2B reads the same safe cached DTO into bounded Day, 3 Day,
  Week, Next 7 Days, Month, inspector, and Today occupancy projections. It makes no
  additional Google request and adds no provider-event mutation affordance.
  Revisioned category/subtype and hide/restore commands update only Ion-local SQLite
  fields. Google selection, subscription, visibility, and event content remain
  untouched.

## Phase 2C write contract — rebuild in preparation

**No provider write is implemented on this branch.** The contract below is
binding on the rebuild ([ADR 0022](decisions/0022-phase-2c-controlled-rebuild.md),
[Phase 2C rebuild plan](phases/PHASE_2C.md)); the withdrawn implementation is
preserved on `main` and `archive/phase-2c-v1`.

- **Scopes:** keep `calendar.calendarlist.readonly` and replace
  `calendar.events.readonly` with `calendar.events` only after deliberate
  re-consent. `calendar.events.owned` is not used, because legitimate shared
  calendars with writer authority are in scope. Broad `calendar` and unrelated
  scopes remain forbidden.
- **Eligibility:** `writer` or `owner`, ordinary/default event type, no provider
  lock, no attendees, and the accepted account scope. Attendee/invite events
  remain entirely read-only.
- **Dispatch:** Python/SQLite persists canonical direct-human intent durably
  before Rust sends an allowlisted Google request. Rust remains the only
  Google/OAuth/token owner; React and Python gain no provider authority.
- **Concurrency:** ordinary ETag drift converges automatically — re-read
  confirmed provider state, rebase the changed-field mask onto it, bounded by
  the automatic attempt budget. There is **no** version chooser: drift that
  outlasts the budget and genuinely unmergeable contradictions stop as one of a
  closed set of specifically named recovery conditions. No whole-event merge,
  silent last-write-wins, or timestamp authority.
- **Human acceptance is not provider serialization.** A newer direct-human
  mutation is always accepted; the provider still receives one serialized write
  per target. The owner is never refused because an earlier write is unfinished.
- **Idempotency and recovery:** stable deterministic provider IDs for
  Ion-created events; ambiguous requests reconcile before retry; retries are
  bounded and restart-safe.
- **Recurrence:** This event, All events, and This and following. Daily,
  weekdays, weekly, monthly, and yearly are the writable rules. Occurrences
  resolve by canonical master plus immutable original start, with structural
  identity separated from version drift. `This and following` is a real series
  split — conditional trim, then a deterministic new master — and is withheld
  with a plain explanation where Ion cannot faithfully continue the pattern.
  Arbitrary RRULE entry remains unavailable.
- **Provider surface:** `events.insert`, changed-field-only `events.patch`,
  conditional `events.delete`, and bounded `events.get` / `events.instances` for
  reconciliation and occurrence resolution. `events.update`, `events.move`,
  batch, attendee, reminder, conferencing, attachment, and special-event writes
  are not reachable from any command or the renderer.
- **Retention:** unresolved and failed intents remain until explicit resolution.
  Completed intents may be pruned after 30 days while compact audit remains.

See [ADR 0021](decisions/0021-google-calendar-write-outbox-and-conflicts.md) for
the retained safety architecture.

Authoritative provider references:

- [OAuth 2.0 for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
