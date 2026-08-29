# ADR 0017: macOS menu-bar and instance lifecycle

**Status:** Accepted  
**Date:** 2026-08-28

## Context

The packaged Phase 0C runtime already makes Rust the sole owner of one
authenticated Python sidecar, but it deliberately deferred a multi-instance
policy. Phase 1G requires a quiet native menu-bar presence, reliable
close/reactivate behavior, and fast Task capture without introducing a daemon,
generic renderer authority, or a new native plugin.

## Decision

Use Tauri's existing built-in tray feature for a fixed menu containing Open
Ion, Home, Today, Quick Capture, and Quit Ion. Rust owns these actions. Closing
either configured window is intercepted as Hide; macOS application reactivation
shows and focuses the main window; explicit Quit follows the inherited bounded
sidecar shutdown path.

Create one initially hidden, always-on-top quick-capture WebView. It submits
only a Task title through the existing fixed `create_task` command, then sends a
bounded local event so the already-running main WebView can refresh its derived
state. A notification or hide failure after confirmed creation cannot relabel
the mutation as failed.

Acquire a non-blocking advisory `flock` on a fixed Application Support lock file
before creating the tray or starting the sidecar. Hold the file descriptor for
the app process lifetime. A forced second process exits before it starts a
backend; normal Dock reactivation is handled by the original process. The lock
file carries no secret or user content and a process death releases the lock.

## Consequences

- Ion can remain available from the native menu bar while its windows are
  hidden, without a daemon or background launch policy.
- Exactly one Ion desktop process owns at most one sidecar for the Application
  Support identity. No new IPC endpoint, credential, or renderer process
  control is introduced.
- Quick Capture creates the same canonical, audited, direct-human Task as the
  organizer UI and duplicates no organizer data.
- A global OS shortcut remains deferred because it requires a separately
  reviewed native plugin/dependency. Later menu-bar Focus, priorities, and AI
  actions also remain deferred.

## Alternatives considered

- A Tauri single-instance plugin was rejected for this milestone because the
  macOS-only advisory lock meets the required process invariant without a new
  dependency or cross-platform IPC surface.
- A background daemon or launch agent was rejected because it changes the
  lifecycle and security model.
- A separate capture API or local cache was rejected because Task creation is
  already canonical through the authenticated Rust-owned sidecar boundary.

## References

- [Phase 1G](../phases/PHASE_1G.md)
- [ADR 0008](0008-production-service-lifecycle.md)
- [ADR 0009](0009-local-process-authentication.md)
- [ADR 0010](0010-phase-1-organizer-domain.md)
- [Master Specification](../PRODUCT_SPEC.md)
