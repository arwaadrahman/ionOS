# Integration Boundaries

## Status: Phase 2C-2 bounded Google Calendar create implemented

Integrations are adapters around Ion's local authority; they do not become its
primary storage. Google Calendar is the first active adapter under ADR 0018.

| Integration                                    | Target phase/status                 |
| ---------------------------------------------- | ----------------------------------- |
| Google Calendar                                | Phase 2C write gate accepted        |
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
  retained for later explicit conflict handling.
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

## Phase 2C accepted write contract and implemented 2C-2 create

- Accepted scopes: keep `calendar.calendarlist.readonly` and replace
  `calendar.events.readonly` with `calendar.events` only after deliberate
  re-consent in an authorized implementation step. `calendar.events.owned` is
  not used because legitimate shared calendars with writer authority are in
  scope. Broad `calendar` and unrelated scopes remain forbidden.
- Eligibility: initial writes require `writer` or `owner`, ordinary/default
  event type, no provider lock, no attendees, and the accepted account scope.
  Attendee/invite events remain entirely read-only.
- Dispatch: Python/SQLite persists canonical direct-human intent and a durable
  typed outbox before Rust sends an allowlisted Google request. Rust remains the
  only Google/OAuth/token owner; React and Python gain no provider authority.
- Concurrency: every initial ETag mismatch is an explicit conflict with Keep
  Google, Apply Ion, or Review differences. No automatic merge or silent
  last-write-wins exists.
- Idempotency/recovery: Ion-created events use stable deterministic provider
  IDs; ambiguous requests reconcile before retry; retries are bounded and
  restart-safe.
- Recurrence: one occurrence and whole series are the only accepted scopes.
  Arbitrary RRULE and `this and following` remain deferred.
- Retention: unresolved, failed, conflict, and ambiguous intents remain until
  explicit resolution. Successfully completed intent rows may be pruned after
  30 days while compact audit remains durable.
- Create: migration `0007` is sufficient; no Phase 2C-2 migration is added.
  Explicit selected-account re-consent requests exactly CalendarList read-only
  plus Calendar Events write. A fixed local-first create command dispatches
  only `events.insert`; ambiguous outcomes use `events.get` for the same
  deterministic event ID before any same-ID retry. Existing account sessions
  and the normal connect command remain read-only until explicit re-consent.
- Exclusions: patch, update, move, delete, instances dispatch, recurrence,
  attendee, reminder, conferencing, attachment, and special-event writes are
  not reachable from the Phase 2C-2 command or renderer.

See [ADR 0021](decisions/0021-google-calendar-write-outbox-and-conflicts.md)
and the [Phase 2C gate](phases/PHASE_2C.md).

Authoritative provider references:

- [OAuth 2.0 for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
