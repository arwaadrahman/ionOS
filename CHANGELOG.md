# Changelog

All notable repository changes are documented here.

## [Unreleased]

### Fixed

- Phase 2A Google Calendar synchronization now uses the canonical account and
  calendar route prefixes, persists safe sync failures instead of returning an
  unchanged `Never synced` projection, constructs the documented Events.list
  path without a duplicate separator, rejects invalid empty sync/page tokens,
  skips roles without event-detail access, and emits allowlisted metadata-only
  sync failure diagnostics.

### Added

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
