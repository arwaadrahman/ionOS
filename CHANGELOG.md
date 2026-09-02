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
