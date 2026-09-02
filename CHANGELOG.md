# Changelog

All notable repository changes are documented here.

## [Unreleased]

### Changed

- **Phase 2C is being rebuilt from the accepted Phase 2B baseline.** The first
  Phase 2C write implementation failed real owner acceptance: ordinary Calendar
  events displayed "Not saved yet", global surfaces exposed provider and write
  state as product, and ordinary human actions kept arriving at review/conflict
  machinery. Each individual route repaired was followed by another, because the
  architecture allowed any unclassified provider disagreement to fall through
  into a generic "review this" decision and treated provider synchronization as
  a second authorization step — an ordinary edit reaching a review task was the
  design working as specified, so repairing sites could not terminate. That
  implementation is preserved on `main` and `archive/phase-2c-v1` as reference
  material and is not accepted product code. This branch starts at the accepted
  Phase 2B baseline `72ea3ba` and carries forward the current product contract
  rather than Phase 2B-era product assumptions. Google events are read-only
  here; no Phase 2C v2 write code has been written.
  See [ADR 0022](docs/decisions/0022-phase-2c-controlled-rebuild.md).
- **Migration history is immutable.** `0007_calendar_write_foundation` is ported
  onto the rebuild branch byte-for-byte, because existing Ion databases are
  already at `0007` and no rebuild may require real data to be downgraded.
  Porting the migration carries schema only, not the withdrawn write behavior:
  the outbox and audit tables exist and are unused until 2C-R0. Every new
  Phase 2C v2 schema change is `0008` or later; nothing is deleted, replaced, or
  renumbered. Rebuild development uses a dedicated `ION_DATA_DIR`.
- **Recurrence termination is bounded to what a series split needs.** 2C-R5 may
  generate an `UNTIL` inside the trusted domain to trim the old master, derived
  only from the persisted preset and the occurrence's immutable original start,
  and re-validated in Rust; the renderer can never supply recurrence text or a
  terminator value. `COUNT`, user-configurable end dates, and
  _Never / On date / After N_ are excluded, and remain a later bounded
  capability with its own owner decision.
- **The Calendar interaction contract is now authoritative and portable.**
  `docs/CALENDAR_BEHAVIOR.md`, the Master Specification's Calendar authority
  amendment, the Google-Calendar behavioral default, and the
  `ROUTE-CALENDAR-BEHAVIOR` routing rule are carried onto the rebuild branch:
  direct human action is authorization, an AI proposal is authorized once when
  the owner accepts it, provider synchronization is never a second approval
  step, `locked` constrains Ion's automation rather than the owner, recurrence
  scope is target selection, Undo is preferred over confirmation for reversible
  actions, and convergence is automatic in both directions.
- **The version chooser is withdrawn, not narrowed.** _Keep Google's version_,
  _Review differences_, and _Apply my Ion changes_ are not to be reimplemented
  in any form. Conditions that genuinely need a person are a closed set of
  specifically named recovery states with deliberately no generic member. ADR
  0021 is retained for its provider-write **safety** layer — the authority
  split, durable intent before dispatch, exact non-wildcard `If-Match`,
  deterministic identity, bounded restart-safe retry — and superseded for its
  human conflict-resolution policy.

### Added

- **Phase 2C-R0 — the direct-human write foundation.** The smallest trustworthy
  architecture for Phase 2C v2, proving that human intent acceptance and
  provider write execution are separate concerns. Accepting a direct human
  action reads no provider lifecycle state at all, so it cannot be refused
  because provider work is busy — the Phase 2C v1 `write_pending` behaviour is
  not merely avoided, it is unrepresentable. Serialization lives in a separate
  provider lane whose `provider_busy` flag exists so the dispatcher can
  serialize, never so a person can be refused; a test edits the same event three
  times while a write is in flight and every one is accepted durably. The
  recovery taxonomy is closed — five automatic kinds, eight owner-action kinds,
  and deliberately no generic member — and classification is total, so no
  outcome can fall through into a "review this" decision. Ordinary provider
  version drift classifies as automatic and re-arms for another bounded attempt;
  exhausting the budget becomes `automatic_recovery_exhausted`, which names what
  happened instead of borrowing the language of a disagreement about facts. The
  `conflict` storage state survives only because migration 0007 is immutable:
  the coordinator never produces it, and a test drives every failure class end
  to end to prove it. **R0 dispatches nothing** — no operation is dispatchable,
  the Rust write module reaches no Google endpoint, and accepting an intent does
  not mutate the canonical CalendarBlock, so the Calendar is visibly unchanged.
  No migration was required.
- **A cross-layer seam harness, before any write capability.**
  `contracts/calendar-write-vocabulary.json` is the single canonical source for
  every closed vocabulary; Python, Rust, and TypeScript each assert their own
  allowlists against it, and the Python seam suite asserts the other two layers'
  source as well. This targets the exact defect that broke Phase 2C v1, where
  `this and following` shipped implemented end to end in the domain with passing
  tests while the Tauri scope allowlist still read
  `single | occurrence | series`, so every real attempt failed as
  `local_state_invalid`. Injecting that drift was verified to fail all three
  suites. The seam tests drive the authenticated production app over real SQLite
  at head 0007 with the exact bodies Rust serializes, rather than calling the
  domain: "Python domain tests pass" is not accepted as evidence that a Calendar
  write works.

- **A stale recurrence exception no longer renders as a phantom event.** An
  explicit exception overrides exactly one generated occurrence, identified by
  its immutable original start. After a confirmed whole-series move or re-rule,
  an older exception can be left anchored to a slot the confirmed rule no longer
  produces — Google resets instance exceptions in that case. Ion was still
  drawing such a row at its old time, beside the newly confirmed occurrence, and
  opening it handed the Inspector a base that matched nothing visible. The
  projection now treats it as a stale local override awaiting read-sync
  reconciliation: it neither suppresses a generated occurrence nor renders
  itself. Anchoring is denied only when it can be positively determined, so a
  missing master, an unparseable rule, or an absent original start keeps the
  previous behavior and genuine data is never hidden. This is a read-model
  correctness fix, independent of the withdrawn write architecture, and it is
  ported with its two focused regression tests and nothing else.
- The open Calendar occurrence now carries a restrained selection ring —
  `data-selected` plus `aria-current` and a "selected" suffix in its accessible
  name — a shape change as well as a color change, so it is never confused with
  a category color. This is the one presentation improvement from the withdrawn
  Phase 2C work that is independent of write orchestration.
- `docs/phases/PHASE_2C.md` is replaced by the v2 rebuild plan: subphases 2C-R0
  through 2C-R6, each gated first on a cross-layer test spanning renderer →
  Tauri/Rust → authenticated FastAPI → SQLite → synthetic provider, and then on
  real owner acceptance against a disposable Google event. "Python domain tests
  pass" is explicitly not acceptable evidence that a Calendar write works.

### Fixed

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
