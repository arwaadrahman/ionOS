# Phase 1G — macOS Menu Bar + Quick Capture

## Objective

Make Ion a dependable macOS menu-bar presence and provide a fast, minimal way
to capture a canonical Task without broadening the local runtime boundary.

## Scope

- One native Tauri tray icon with fixed Open Ion, Home, Today, Quick Capture,
  and Quit Ion actions.
- One fixed, initially hidden quick-capture window with a Task-title form that
  calls the existing canonical `create_task` operation.
- Close-to-hide behavior for Ion windows, Dock reactivation of the main window,
  and explicit Quit with inherited bounded sidecar shutdown.
- A process-held macOS file lock in Application Support that prevents a forced
  second app process from starting another backend.

## Durable behavior

- Rust owns the tray, window visibility/focus, application reactivation,
  instance guard, and sidecar lifecycle. The renderer never owns a process,
  service address, port, or credential.
- Quick Capture creates exactly one unlinked human Task. It does not infer an
  Area, Goal, Project, date, priority, schedule, or workflow.
- A confirmed Task creation remains successful if the secondary main-window
  notification or capture-window hide fails. Canonical refresh remains the
  source of truth.
- Closing a window hides it while Ion remains available in the menu bar. Quit
  is explicit and triggers the existing graceful-then-bounded sidecar shutdown.

## Explicit exclusions

Phase 1G excludes a global OS shortcut (which would require a new native
plugin), background daemon or launch agent, generic shell or HTTP capability,
menu-bar priorities/focus/Ask Ion, AI, integrations, scheduling, inference,
schema migration, new dependency, and changes to `PRODUCT_SPEC.md`.

## Acceptance

- Automated tests prove fixed tray action routing, single-process lock
  contention/release, canonical Task capture, fixed Home/Today event handling,
  and mutation-success semantics.
- Repository validation, frozen ARM64 sidecar, Tauri app packaging, packaged
  launch, tray/window behavior, synthetic Task persistence, explicit Quit, and
  process/listener cleanup pass.
- Owner manually verifies the native menu placement/icon, interaction feel,
  VoiceOver/keyboard usability, and expected close/reopen behavior.

## Decision

- [ADR 0017](../decisions/0017-macos-menu-bar-and-instance-lifecycle.md)
