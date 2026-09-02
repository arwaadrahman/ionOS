# Changelog

All notable repository changes are documented here.

## [Unreleased]

### Changed

- **The generic Calendar conflict surface is removed, not hidden.** Owner
  acceptance kept reaching Review differences / Keep Google's version / Apply my
  Ion change during ordinary editing, and each individual route repaired was
  followed by another, because the architecture allowed _any_ unclassified
  provider disagreement to fall through into a generic "review this" decision.
  The projection now carries a closed set of specific recovery conditions with
  deliberately no generic member: `retry_available`, `provider_deleted`,
  `recurrence_target_changed`, `duplicate_identity`,
  `reauthentication_required`, `provider_rejected`. Each names the actual
  situation and offers only truthful actions — "Google deleted this event while
  Ion was saving your change" with _Discard my change_, never a choice between
  versions. An outcome matching nothing in that set is not a decision handed to
  the owner. The three-button chooser and the version-comparison view are gone
  from the Inspector, and their dead machinery with them; the underlying routes
  remain only as mechanisms behind specific actions. A domain test walks an
  ordinary edit through queue, attempt, drift, re-read, rebase, background sync,
  a successive edit, and recovery, asserting no recovery condition is ever
  produced.
- **Recovery no longer manufactures review tasks.** A sweep in `recover()` was
  converting failed occurrence rows into conflicts purely from ETag drift, on
  every dispatch — the obsolete policy running continuously. It now re-arms the
  owner's intent against the confirmed master and retries.
- **A fast gesture is no longer dropped.** The renderer discarded any edit
  arriving while a Tauri command was outstanding, so the owner's _most recent_
  action was the likeliest to be lost, silently. The newest is now held and sent
  when the command returns.

- **The owner can act on the same event repeatedly without waiting for Google.**
  Dragging to 3 PM and straight on to 4 PM, or saving twice in a row, used to be
  refused with `write_pending` — provider serialization surfaced to the user as
  "you cannot edit yet". Human interaction and provider dispatch are now treated
  as the separate concerns they are: a newer direct-human mutation is always
  accepted durably, while the provider still receives one serialized write per
  target. An earlier write that has not left yet (`queued`, `ready`,
  `retry_wait`) is superseded, so an obsolete position costs no round-trip; one
  genuinely in flight (`attempting`, `ambiguous`) is never cancelled and never
  raced — the newer intent waits behind it and is released and re-aimed at the
  authority that attempt confirmed. Rapid actions therefore coalesce to at most
  one in-flight write plus one waiting. The Calendar shows the newest human
  intent throughout and never flicks back through a superseded value. A
  structural `this and following` split is never coalesced away; it waits its
  turn. Reused the existing `predecessor_intent_id` chain, distinguishing a
  superseding edit from a split's second half by whether it targets the same
  block — **no migration**.
- **A recurring delete asks once.** Choosing the scope is the whole decision:
  the warning about what cannot be recovered now lives inside the scope dialog,
  beside the option that causes it, and the separate destructive confirmation
  that followed it is gone. A non-recurring delete keeps its single
  confirmation, since it has no scope to choose.

- **Ordinary Calendar changes now converge automatically in both directions**,
  superseding ADR 0021's rule that every ETag mismatch required explicit human
  resolution. In real use that rule turned every ordinary edit into a review
  task: an edit met a moved ETag, became "needs review", and Apply my Ion
  changes met the next moved ETag — so the owner learned to press Apply
  repeatedly and hope. Two seams produced that loop and both are fixed. A stale
  precondition now re-reads confirmed provider state and re-aims the pending
  write at it rather than conflicting; and a background read sync that finds a
  newer ETag re-aims a pending write instead of marking it "changed elsewhere".
  Field ownership falls out of the existing narrow model rather than any new
  merge rule: a provider body carries only `changed_fields`, so Google's edits
  to untouched fields survive, the pending direct-human value owns its own field
  until it settles, and once it confirms later Google changes flow into Ion
  normally. Not last-write-wins; timestamps are never authority. Exact
  non-wildcard `If-Match` and the bounded automatic attempt budget are
  unchanged, so drift that outlasts the budget — and genuinely unmergeable
  contradictions like provider deletion — still stop honestly. No migration.
- **Google → Ion propagation no longer needs Sync Now.** The Calendar runs the
  existing bounded incremental sync while it is on screen — on open, on becoming
  visible again, then on a slow interval — pausing entirely while hidden and
  backing off on failure. Sync Now remains an explicit refresh.

- **Direct manipulation now commits at drop.** A drag or resize used to render a
  preview, then seed the Inspector with a proposed draft that the user had to
  review and Save. In real use that made the most direct interaction in the
  product the slowest, and left the owner unsure whether a change had taken. A
  gesture now commits when the pointer is released, as Google's does; a
  recurring event asks for scope at that moment, and that choice is the last
  action required. The entire gesture-review surface has been removed rather
  than hidden, and the Ion override that required it is withdrawn from
  `docs/CALENDAR_BEHAVIOR.md`.
- **A waiting write now resumes on its own.** A write that hit a retry backoff
  progressed only when some later action happened to trigger another dispatch —
  which is what made a manual Sync Now feel like part of the workflow. Recovery
  now reports how long until the earliest waiting retry is due, and the
  dispatcher schedules one bounded self-wake for exactly that moment, emitting
  the settled projection so the renderer updates without being asked. It is a
  single scheduled wake, not a poll: a healthy Calendar schedules nothing.
- **Feedback is lightweight.** The Calendar itself is the confirmation, so a
  healthy write now says `Event moved` / `Event updated` (or `· saving…` while
  in flight) beside Undo, instead of a full-width banner explaining provider
  mechanics. The Inspector's provider-identity explainer appears only while a
  change is unsettled.

### Fixed

- **The review loop real owner acceptance still hit.** Editing a single
  occurrence produced a permanent "Needs Review", and `Apply my Ion changes`
  answered with "Google changed this event again" indefinitely. Three earlier
  seams had been fixed, but all of them concerned `expected_provider_etag`; a
  `This event` write also embeds the **master's** ETag in its recurrence
  identity, and occurrence resolution treated any change to it as an identity
  failure. That check ran before an attempt was recorded, so it consumed no part
  of the retry budget — every retry and every Apply re-derived the same stale
  identity and failed identically, which is why it never terminated. Resolution
  now separates structural identity (same master event, still recurring, still
  writable — a real contradiction) from version drift (ordinary concurrency):
  the freshly fetched master's ETag is adopted, the confirmed link is aligned,
  and the write proceeds. Covered by a cross-layer test over the authenticated
  local API, since isolated tests could not see this.
- A read sync that found newer provider state still conflicted a pending
  **delete**; only the patch case had been fixed. A deletion carries no field
  mask to preserve, so it now re-aims at confirmed authority the same way.
- Rows conflicted by the superseded policy are re-armed automatically during
  recovery, so upgrading into the new behavior does not strand the owner in a
  workflow the product no longer has. Original conflict audit is preserved, and
  a row lacking evidence to rebase safely stays explicit.
- Exhausted automatic recovery no longer borrows semantic-conflict language.
  The event reads **Not saved yet** and offers one **Try again**, instead of
  "Needs review" with a Keep Google / Apply Ion chooser — in the Inspector and
  on the grid tile, which was a second surface still showing "Needs review".

### Added

- **Undo for a confirmed Calendar edit**, offered beside the confirmation it
  reverses. It is not a rollback or an event-sourced history: it is the same
  ordinary write aimed at the values the edit replaced, conditional on the
  revision that edit produced, keeping the original recurrence scope and
  occurrence identity, and auditable like any other change. It is offered only
  once the write settles into a block Ion can truthfully aim at, once per
  change, and never for a repeat-rule change — the rule is restated only in the
  forward change, so reversing it is a new deliberate choice rather than a
  symmetric undo. Deliberately Calendar-specific; no general undo stack.
- `docs/CALENDAR_BEHAVIOR.md` is now the **contract** for Calendar work rather
  than a description of it, with a consolidated Ion-overrides list, the
  confirmation/reversibility rule, the modal requirement, and a recorded
  cross-layer invariant. `AGENTS.md` and the task router now require reading it
  before any Calendar interaction change, via a new `ROUTE-CALENDAR-BEHAVIOR`.

- **“This and following events”**, completing Google Calendar recurrence parity,
  under explicit owner authorization to extend the recurrence provider-body
  contract. It performs a real series split rather than a sweep of
  per-occurrence exceptions: the old master is conditionally trimmed to stop
  before the selected occurrence, and only once Google confirms that trim does
  Ion create a new recurring master beginning at it. Both provider operations,
  the new canonical master, its inherited Ion-only metadata, and its
  deterministic provider identity are persisted in one transaction before any
  Google call, so a crash cannot lose the intent and a retry or restart cannot
  produce a duplicate future series. Ordering is durable rather than in-memory:
  the new master is stored queued behind the trim and released only on
  provider-confirmed completion, retired if the trim is discarded, and
  re-chained if the trim is re-authorized through Apply my Ion changes. The
  scope is offered only where Ion can faithfully continue the pattern — a
  custom provider rule and the first occurrence both withhold it truthfully —
  and deleting this-and-following is the trim alone. The authorized contract is
  the same five bounded preset families plus a domain-generated `UNTIL`
  terminator derived from the persisted preset, the selected occurrence's
  immutable identity, and the block's own timezone/all-day semantics; the
  renderer can never supply recurrence text, and no new provider method,
  migration, or OAuth scope was required.

### Fixed

- **“This and following events” failed against real Google** with a generic
  “This calendar change couldn't be saved”, despite green domain tests. The
  scope was implemented end to end in the domain, but the Tauri command's
  validator still allowlisted only `single | occurrence | series`, so every
  real attempt was refused as `local_state_invalid` before reaching the local
  API at all. The domain tests could not see it because they call the domain
  directly and never cross that seam. Both the edit and delete validators now
  accept the scope with its required occurrence identity, are extracted into
  named predicates covered directly by tests, and `recurrence_split_unsupported`
  and `recurrence_split_at_first_occurrence` were added to the safe-reason
  allowlists so a genuine refusal explains itself instead of collapsing into the
  generic fallback. Recorded in `docs/CALENDAR_BEHAVIOR.md` as a standing
  invariant: an offered interaction must be accepted by every layer it crosses.
- **Editing a single occurrence appeared to do nothing.** Every event synced
  from Google carries Ion metadata whose `flexibility` defaults to `locked`, and
  Save was gated behind an “I confirm changing this Ion-locked event” checkbox —
  so with the scope chooser correctly moved to after Save, an unticked checkbox
  made Save inert with nothing to explain it. Confirmation is now spent only
  where it buys something: an interaction requires explicit confirmation only
  when it removes confirmed occurrences. Ordinary edits, moves, resizes, and
  non-destructive `this event` / `all events` / `this and following` changes
  commit on Save; destructive recurrence deletions keep their blocking
  confirmation. The matching domain gates were relaxed for edits and retained
  for deletes. **No ETag, allowlist, scope, or identity precondition changed** —
  removing a checkbox never removed a precondition.
- **The recurrence-scope chooser is now a real modal** — centered over the
  window with an inert backdrop, focus moved in and trapped, focus returned to
  its opener, and Escape or backdrop meaning Cancel — instead of a panel
  rendered inside the Inspector, where it could sit below the fold on the
  surface it was interrupting.
- Google Calendar recurrence parity, part one. **Stale first occurrence:** after
  a confirmed "all events" time change, the first visible instance still showed
  the pre-change state and re-entering that displayed value reported "no
  change". An explicit exception overrides exactly one generated occurrence via
  its immutable original start; once the confirmed series moved, that anchor no
  longer matched any occurrence, so the row suppressed nothing and drew itself
  as a phantom event at the old time while the Inspector edited its stale
  block. Google resets instance exceptions in exactly this case, so an
  exception whose original start the confirmed rule no longer produces is now
  treated as a stale local override awaiting read-sync reconciliation: it
  neither suppresses a generated occurrence nor renders itself. Genuine
  exceptions -- including a moved occurrence, which keeps its original slot --
  still override normally. No canonical data is mutated or discarded.
  **Recurrence scope now follows Google's order:** scope is chosen _after_ the
  change is described, through one shared typed chooser used by inspector
  saves, drag, resize, and delete, replacing the per-surface scope selects.
  Nothing is persisted or dispatched until a scope is chosen, cancelling
  mutates nothing, a repeat-rule change is offered only as series-wide, and the
  whole-series risk acknowledgement now lives in the chooser. Delete picks
  scope first and keeps Ion's stronger destructive confirmation. Ion's accepted
  explicit-save review for pointer gestures is preserved, so a drag or resize
  proposes a draft, saves, then asks for scope.

### Added

- `docs/CALENDAR_BEHAVIOR.md` records the owner's Google Calendar behavioral
  default and Ion's deliberate overrides, including why "This and following
  events" is withheld rather than simulated.

- Phase 2C-6 owner-acceptance repair, part two. **Apply my Ion changes stalled**
  on recurring events: an occurrence intent embeds the master ETag inside its
  recurrence identity, and `begin_attempt` preflights _that_ value against the
  confirmed link, but the rebase only refreshed the row's own
  `expected_provider_etag`. The copied stale identity therefore failed the new
  write's own preflight and immediately re-conflicted it, so the change never
  reached Google while the surface still said "applying". The rebase now
  refreshes every piece of provider authority the write carries, preserving
  identity (master event ID, immutable original start, exception linkage)
  exactly, and the renderer now reports the real outcome -- confirmed, pending,
  reauthentication, re-conflicted, or rejected -- instead of an unconditional
  "applying" message. **Stale "needs review" rows** that reported "no conflict
  to resolve" are also fixed: a conflicted occurrence never materializes an
  exception row, so its conflict is displayed on the recurring master, but the
  resolver skipped occurrence-scoped intents for master rows and could never
  target it. Resolution now selects exactly what the projection displays, so
  every displayed conflict is reachable and a resolved one truthfully projects
  as synced across refresh and restart. A **terminally failed write** was a
  third dead end -- it kept serializing its block with no human exit -- so Keep
  Google now also discards a failed pending intent and Apply my Ion changes
  doubles as the accepted explicit manual retry against fresh authority, both
  reusing the existing `failed -> cancelled` transition and outbox schema. The
  write dispatcher no longer aborts an entire drain when one plan fails, so a
  single stuck write can no longer indefinitely strand every other ready write.
  Also recorded the owner's Google Calendar behavioral-default rule, with
  `this and following` tracked as a future parity requirement rather than
  simulated.

- Phase 2C stabilization pass over the accepted architecture (no rewrite, no
  migration, no OAuth/Calendar mutation): the prior occurrence-sibling repair
  covered virtual occurrences and the write-path predecessor check, but an
  already-_materialized_ occurrence (its own `exception` CalendarBlock row)
  could still stay permanently locked out of editing once a sibling occurrence
  entered conflict or failed, because the read projection's sibling gate used
  an older, coarser "any nonterminal state blocks" rule instead of the refined
  per-occurrence rule. Both gates now agree: a resolved conflict/failure only
  keeps serializing a materialized sibling while genuinely nonterminal, or
  while it targets the master as a whole (series/single scope); a conflict or
  failure scoped to one specific occurrence releases every other, unrelated
  occurrence -- covered by a new regression test with two independently
  materialized exception rows. `recurrence_unsupported` is now wired through
  every safe-copy layer (Python route allowlist, Rust translation, renderer
  copy) instead of silently degrading to the generic "couldn't be saved"
  message; a route-level test and a source-parsing parity test guard the
  duplicated Python/Rust safe-reason allowlists against future drift. The
  block projection now also exposes a bounded `provider_write_failure_class`/
  `provider_write_failure_reason` (mirroring Rust's existing safe
  classification) so the Inspector can show quota/backend/transport-retry,
  reauthentication, stale/conflict, provider-disappearance, and terminal
  rejection with distinct, still-safe guidance instead of one generic pending
  or failed label. The previously dead-end conflict state now has a complete
  human exit path: **Keep Google's version** (discards only the conflicting
  intent, preserves Ion-only metadata), **Apply my Ion change** (rebases the
  stored field mask onto the freshly confirmed provider ETag as a new
  explicit write authorization -- never the stale conflict row's ETag, never
  `If-Match: *`, and never a silent resurrection of a provider-deleted event),
  and **Review differences** (a bounded, normalized comparison of confirmed
  vs. desired values, no raw provider object). All three are reachable only
  through new fixed Ion-ID Tauri commands and routes, using the existing
  outbox schema (no migration). `wait_for_write_slot` no longer polls
  `begin_sync` forever: it now fails safely after a bounded wait rather than
  hanging a Tauri command indefinitely, leaving the durable write intent
  untouched and recoverable on the next trigger. Calendar timed-event resize
  handles are no longer hover-only and have a substantially larger pointer
  target; Escape now cancels an in-progress move/resize gesture before
  pointer-up commits nothing; and the occurrence currently open in the
  Inspector now renders a restrained selected state in the grid, distinct
  from category, pending, and conflict/failure styling.

- Phase 2C-5 owner-acceptance repair: a terminal, reviewable conflict or
  failure on one recurring occurrence (provider drift caught during
  identity/ETag resolution) kept serializing every other occurrence of the
  same master indefinitely, both in the write path -- a genuinely unrelated
  occurrence's edit was rejected with `write_pending` because the "is a
  predecessor still pending" check matched on the shared master id without
  checking which occurrence the predecessor actually targeted -- and in the
  read projection, whose identity fields cleared too eagerly, leaving the
  renderer's sibling guard unable to tell the reviewed occurrence apart from
  an untouched one. The predecessor check now only serializes while a write
  is genuinely nonterminal, or while it targets the exact occurrence being
  edited; the projection keeps a resolved write's identity visible so the
  renderer can still single out the occurrence under review and release
  every other sibling back to current confirmed provider state. The
  conflicting occurrence's own intent, ETag, and conflict state are
  untouched and never retried. The sibling-lock message now reads "Another
  change to this recurring series is still syncing with Google. Wait for it
  to finish before editing another occurrence." when serialization is
  genuinely active.

- Phase 2C-5 owner-acceptance repair: a preexisting recurring Google master's
  capability projection kept a completed occurrence write's operation, scope,
  and original-start identity visible after that write reached a terminal
  state, so the renderer's sibling-occurrence guard permanently treated every
  other occurrence of that master as serialized and refused to open it for
  editing. Those fields now clear once the write is no longer active, matching
  the existing pending-overlay gate, so preexisting recurring masters stay
  editable occurrence-by-occurrence after each write completes. Renderer error
  mapping also now surfaces `timezone_change_unsupported`,
  `recurrence_identity_unresolved`, and `no_change_requested` truthfully
  instead of collapsing them into the generic "couldn't be saved" message.

- Phase 2C-5 owner-acceptance repair now waits for the shared Rust Google gate
  when foreground sync wins serialization, preventing durable ready occurrence
  intents from being stranded unattempted. Calendar timed movement now uses
  pointer-captured direct manipulation with cross-day live preview and top/bottom
  resize edges before one explicit reviewed save. Recurrence siblings respect
  canonical-master nonterminal serialization, occurrence overlays stay scoped to
  their exact original start, and safe write-state failures such as
  `write_pending` reach truthful renderer copy.

- Phase 2B startup now completes the exact interrupted unreleased `0006`
  presentation schemas already used during owner testing, preserving existing
  rows while adding a missing subtype column or replacing the obsolete broad
  category constraint without a second migration revision. This fixes Career,
  Routine / physical, Personal project, and Fun category saves on an existing
  Phase 2B database while preserving retired work/meals/health classifications
  under the extensible Routine family.

- Phase 2A Google Calendar synchronization now uses the canonical account and
  calendar route prefixes, persists safe sync failures instead of returning an
  unchanged `Never synced` projection, constructs the documented Events.list
  path without a duplicate separator, rejects invalid empty sync/page tokens,
  skips roles without event-detail access, and emits allowlisted metadata-only
  sync failure diagnostics.

### Added

- Phase 2C-5 Google Calendar recurrence writes: bounded daily, weekdays,
  weekly, monthly, and yearly create/edit presets; deliberate one-occurrence or
  whole-series edit/move/resize/delete authority; canonical master plus
  immutable original-start resolution through bounded `events.instances`;
  exact-instance conditional patch/cancellation; conditional master series
  patch/delete; preserved exception identity; scoped pending overlays; and
  destructive series confirmation. Migration `0007` remains sufficient; raw
  RRULE, this-and-following, attendees, invitations, reminders, conferencing,
  attachments, cross-calendar move, and autonomous writes remain unreachable.

- Phase 2C-4 Google Calendar delete and cancellation: backend-owned delete
  eligibility, explicit irreversible confirmation, local-first tombstone
  intent, exact-ETag `events.delete`, bounded ambiguity lookup, 404
  already-absent completion, restart-safe retry, refresh drift conflict, and
  wholly local cancellation of never-attempted creates. Migration `0007`
  remains sufficient; recurrence mutation and all unsafe event classes remain
  read-only.

- Phase 2C-3 Google Calendar edit, move, and resize: explicit-save inspector
  editing, direct timed drag/resize review, atomic durable desired overlays,
  changed-field-only `events.patch` with exact non-wildcard `If-Match`, bounded
  ambiguity lookup, restart-safe retry, provider-refresh drift conflicts,
  locked-event confirmation, civil all-day editing, and truthful pending,
  syncing, reauthentication, failure, and conflict UI. Migration `0007`
  remains sufficient; delete, recurring writes, timed/all-day conversion,
  attendee/provider-managed writes, and non-patch mutation methods remain
  unavailable.

- Owner-directed product/roadmap documentation checkpoint: canonical Ion Tasks
  remain primary while Google Tasks is optional/deferred; future
  Aspirations/readiness and cross-cutting evidence-backed Skills are recorded
  without a schema; Phase 13 evolves the existing Ion Core; Phase 14 is Voice
  & Ambient Core; mobile/cross-device/remote expansion is post-v1; and
  multi-calendar event mirroring remains deferred after the single-provider
  lifecycle. No implementation, migration, dependency, or integration was
  added.

- Phase 2C-2 idempotent Google Calendar create: explicit selected-account
  Calendar Events write re-consent, compact click/drag create UI, atomic
  local-first CalendarBlock/outbox persistence, attendee-free `events.insert`,
  deterministic-ID ambiguity lookup, bounded restart-safe retry, visible
  pending/reauth/failure state, and synthetic provider execution tests. No
  migration was needed beyond accepted migration `0007`; all later mutation
  operations remain unavailable.

- Phase 2C-1 Google Calendar write foundation: migration `0007` adds safe
  account/event capability evidence, a typed durable provider-write outbox and
  separate compact audit; Python adds fixed enqueue/ready/transition/recovery/
  pruning contracts with deterministic 160-bit base32hex create IDs, persisted
  five-attempt full-jitter retry state, crash repair, 30-day completed-only
  pruning, and backend-derived eligibility; Rust adds an explicit uninvoked
  write re-consent scope mode, the exact provider-method allowlist, typed unsent
  ETag request construction, safe failure classification, and one read-only
  Tauri capability command. Synthetic Python, migration, Rust, and renderer
  tests cover the accepted failure matrix. No OAuth re-consent or Google event
  mutation is initiated.

- Accepted Phase 2C two-way Calendar architecture/security gate and ADR 0021,
  defining a Rust-owned provider-write boundary, Python/SQLite durable outbox,
  deterministic create idempotency, ETag conflicts, offline/reconnect recovery,
  bounded recurrence writes, minimum OAuth expansion, audit evidence, explicit
  owner decisions, 30-day successful-intent retention, and independently
  testable substeps. No code, migration, dependency, OAuth scope, or provider
  write was added.

- Documentation checkpoint accepting the narrow external Developer Agent
  Bridge boundary, evidence-based local progress observation, strict separation
  from Deep Ask credentials, first-class performance/resource policy, and
  deferred holistic UI-polish requirements. No runtime behavior or numbered
  roadmap phase was added.

- Phase 2B primary read-only Calendar interface with Day, consecutive 3 Day,
  Monday-first Week, rolling Next 7 Days, and Monday-first Month views; bounded recurrence and
  exception projection; two-level category-family/subtype semantic color and
  filtering with required starter subtypes and a graphite Fun family;
  title-first adaptive event detail; compact/default/expanded vertical density;
  calendar-pane Week/3-Day/Day recommendations without manual zoom or horizontal
  day navigation; responsive compact controls; all-day, overlap, current-time, month-overflow,
  mutually exclusive source/filter drawers, pinned account connection,
  reversible Ion-local hide/restore, inspector, and product-language saved-data
  treatments; plus Today
  CalendarBlock occupancy and truthful opaque-block free gaps without
  scheduling Tasks or writing Google data.

- Phase 2A Google Calendar read-sync foundation: Rust-owned Desktop OAuth with
  PKCE/state and ephemeral loopback callback, macOS Keychain refresh tokens,
  memory-only access tokens, exact read-only scopes, multi-account CalendarList
  discovery, independent Ion selection, canonical CalendarBlocks, recurrence
  masters/exceptions, per-calendar full/incremental sync with safe 410 recovery,
  offline cached status, fixed Tauri commands, and minimal setup UI. No Google
  event write/delete, Tasks scope, webhook, daemon, cloud relay, or mobile/LAN
  boundary is included.

- Phase 0A repository documentation, governance, agent routing, and ADR
  bootstrap.
- Phase 0B executable engineering foundation, including accepted local-only
  trust-boundary, toolchain, service-boundary, and SQLite migration decisions.
- Phase 0C production local-runtime and local-process-authentication prototype
  decisions.
- Phase 1A organizer-domain, audit/Trash foundation, and Task vertical slice.
- Phase 1B organizer lifecycle/containment decisions, Python domain/service
  foundation, fixed authenticated desktop commands, and milestone-local UI for
  Areas, Goals, Projects, ordered Milestones, and explicit Task links, including
  safe partial Goal updates and confirmed Goal Save feedback.
- Phase 1C canonical Today planning, deterministic deadline/attention
  projections, local-date rollover, fixed authenticated Today commands, and a
  truthful pre-Calendar execution workspace.
- Phase 1D read-only Home projection, deterministic structural Ion Core, raw
  Three.js WebGL2 renderer with strict lifecycle/fallback behavior, Home-first
  navigation, and compact Today-derived Focus/Attention/Upcoming summaries.
- Phase 1E deterministic local `⌘K` command search over current destinations
  and canonical Home/Core records, with stable lexical ranking and direct
  navigation but no stored index, dependency, migration, or AI.
- Phase 1F bounded Recovery and recent direct-human history projection over
  existing organizer Trash/audit metadata, with explicit entity-specific
  restore and no generic Undo, snapshot, migration, dependency, or cascade.
- Phase 1G native macOS menu-bar actions, minimal canonical Task quick capture,
  close-to-hide/reactivation lifecycle, and a process-held guard against
  duplicate desktop/sidecar instances, with no daemon, migration, or new
  dependency.
- Phase 1H acceptance hardening: in-flight guards against duplicate canonical
  creates, Task workspace refresh synchronization, and explicit same-title
  Task identity coverage, without product, schema, dependency, or
  trust-boundary expansion.
