# Security and Privacy Baseline

## Status

**Accepted invariants with Phase 2A Google credentials and the implemented
Phase 2C-4 bounded create/edit/delete path.**

- Ion is local-first. The public repository contains no real personal Ion data.
- Tests, demos, screenshots, and fixtures use clearly synthetic records only.
- Real user databases, vaults, local runtime state, and private source content
  remain outside the repository.
- Credentials, API keys, tokens, passwords, private keys, and banking or other
  sensitive data must never appear in source, Git, documentation, or plaintext
  user records.
- Persistent Google refresh tokens belong only in macOS Keychain. Google access
  tokens, OAuth authorization codes, PKCE verifier/state, and temporary callback
  material remain Rust-memory-only and are never persisted or logged.
- Major security/privacy, data-ownership, authentication, or authorization
  changes require owner approval and an ADR where lasting.
- The active trust boundary is macOS-local. Phase 0B's FastAPI service must
  bind only to `127.0.0.1`, with no intentional LAN or public exposure.
- Mobile support, synchronization, remote access, and cloud relays are
  deferred pending a dedicated mobile/security architecture review.

Phase 0C adds only production local-process authentication: Rust creates a
per-launch 256-bit secret from the OS RNG and owns it in memory. The packaged
Python sidecar receives it only through bounded stdin bootstrap, requires it on
every endpoint with constant-time comparison, and binds its retained socket to
`127.0.0.1:0`. The renderer receives neither secret nor port, and production
does not enable CORS. No persistent credential store is introduced.

Phase 1G preserves that boundary while adding a Rust-owned native tray and a
fixed quick-capture WebView. The capture surface can invoke only existing Tauri
product commands and bounded local events; it receives no sidecar address,
credential, generic request, filesystem, shell, or process capability. A
process-held advisory lock in Application Support contains no secret or user
data and prevents a second desktop process from starting another sidecar.

## Phase 2A Google boundary

- OAuth uses the default system browser, a temporary IPv4 `127.0.0.1:0`
  callback, S256 PKCE, and a fresh cryptographic state value. The listener is
  path/state/code validated, bounded to five minutes, returns a no-store generic
  page, and never displays or logs the authorization code.
- Ion requests exactly CalendarList read-only and Events read-only. It requests
  no Tasks, Gmail, ACL, sharing, broad calendar-management, or write scope.
- Rust alone reads the local OAuth client configuration, exchanges and refreshes
  tokens, accesses Keychain, sends bearer-authenticated Google HTTPS requests,
  and attempts revocation on disconnect. The optional Desktop client secret is
  treated as local configuration, never repository content.
- SQLite stores no token or OAuth code. It stores only non-secret account/scope
  state, an opaque Keychain locator, CalendarList/Event metadata, and sync
  tokens. The public status DTO omits even the Keychain locator and provider
  sync token.
- Python receives sanitized provider resource fields only. It receives no
  bearer credential and writes no secret or payload snapshot to audit.
- The renderer can call only fixed status, connect, selection, sync, and
  disconnect commands. It receives no Google token, PKCE verifier, OAuth code,
  Keychain locator, service origin/port/session credential, generic HTTP,
  filesystem, shell, or process authority.
- Google HTTPS uses rustls with bounded request timeouts and bounded retry.
  OAuth callbacks remain loopback; no webhook, inbound provider listener after
  OAuth, daemon, cloud relay, LAN endpoint, or mobile trust boundary exists.
- Repository tests and examples use synthetic identifiers and fake token-store
  behavior. Real account data and configuration remain in Application Support,
  Keychain, and the runtime database outside Git.

## Phase 2C accepted write gate through Phase 2C-4 delete

- The accepted future OAuth set is exactly CalendarList read-only plus Calendar
  Events read/write. It replaces Events read-only after deliberate account
  re-consent. Broad Calendar, Gmail, Tasks, ACL/sharing, calendar management,
  Meet/conference, and reminder authority remain forbidden.
- The ordinary connect flow still requests the current read-only scope set.
  A separate explicit selected-account command initiates the exact write-scope
  re-consent flow only after the owner presses Enable Calendar writing.
  Existing accounts default to read-only until that deliberate re-consent
  confirms the exact accepted grant.
- Initial provider writes require `writer` or `owner`, ordinary/default event
  type, no provider lock, no attendees, and the accepted account scope.
  Attendee/invite events and `writerWithoutPrivateAccess` remain read-only.
- React write commands use Ion IDs and fixed typed contracts; they cannot
  provide provider IDs, ETags, arbitrary bodies, URLs, methods, or headers as
  request authority. Rust constructs the allowlisted Google request.
- Python commits canonical intent and a durable outbox before any provider
  request. The outbox contains no token, credential, attendee address, raw
  provider resource, or audit payload snapshot.
- Every initial ETag mismatch stops as an explicit conflict. Wildcard
  `If-Match: *`, silent last-write-wins, and automatic merge are forbidden.
- Provider errors and audit retain only allowlisted status/reason, operation,
  recurrence scope, internal IDs, revisions, and timestamps. Event content,
  account email, attendee identity, authorization material, and raw response
  bodies are excluded.
- Successful intent rows may be pruned after 30 days by bounded,
  deterministic, restart-safe cleanup. Unresolved, failed, conflict, and
  ambiguous rows remain until explicit resolution.
- Phase 2C-2 exposes one create renderer command. Phase 2C-3 adds one fixed
  Ion-ID edit command whose title/time draft cannot supply provider identifiers,
  ETags, methods, URLs, headers, or arbitrary bodies. Production dispatch
  selects `events.insert` for ready creates, changed-field-only `events.patch`,
  exact-ETag `events.delete` for confirmed single events, and bounded
  same-event `events.get` for
  ambiguity reconciliation. Every patch uses the last confirmed non-wildcard
  ETag as `If-Match`. Delete 404 reconciles confirmed absence. Update, move,
  batch, instances, recurrence mutation, and calendar management remain
  unreachable. Create and patch bodies exclude attendees,
  reminders,
  recurrence, Meet/conference, attachments, extended properties, event colors,
  descriptions, and locations.

See accepted ADR
[0021](decisions/0021-google-calendar-write-outbox-and-conflicts.md) and the
[Phase 2C gate](phases/PHASE_2C.md).

## Phase 0B local development details

The local service's development defaults are an explicitly configured loopback
port and these exact origins only: `http://127.0.0.1:1420` and
`http://localhost:1420` for the Vite development server, and
`tauri://localhost` for the Tauri WebView. Wildcard CORS is prohibited. The
default port is not an enduring protocol commitment: it is a non-secret local
setting and can be changed for development.

## Future external development-agent boundary

- Claude Code, Codex, and future coding agents own their own authentication.
  Ion never reads, stores, reuses, exports, or impersonates those credentials.
- Normal Claude Code development uses the user's Claude subscription and never
  receives an Ion Anthropic API credential through arguments, environment,
  files, prompts, or process inheritance controlled by Ion.
- Future launch/resume capability requires explicit user action and narrow
  Rust-owned commands restricted to allowlisted registered project paths and
  allowlisted agent executables. The renderer receives no generic shell,
  terminal, process, arbitrary path, or environment authority.
- Developer telemetry is Private Local by default. Project paths, sensitive
  repository names, file lists, diffs, test/build logs, agent activity, and
  completion summaries do not automatically synchronize to mobile or cloud.
- Full transcripts, source payloads, prompts, and hidden reasoning are not
  collected by default. Any later remote exposure or broader collection needs
  a separate explicit security/privacy decision.

See ADR [0020](decisions/0020-external-developer-agent-bridge.md).

## Deep Ask credential separation

Future Deep Ask OpenAI/Anthropic API credentials belong only in macOS Keychain
or equivalent secure OS storage. They are Ion credentials, not external coding
agent credentials, and must never be globally exported into Claude Code,
Codex, IDE, or terminal environments. Cloud reasoning remains deliberate and
uses local retrieval, minimized context, deterministic sensitive-data
filtering, Private Local exclusions, and configurable usage/cost controls.
