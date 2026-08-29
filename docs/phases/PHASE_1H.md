# Phase 1H — Phase 1 Acceptance & Hardening

## Objective

Verify the complete Phase 1 local desktop organizer and correct in-scope
consistency, lifecycle, refresh, interaction, packaging, and runtime defects
without adding another product subsystem.

## Scope

- Acceptance coverage for startup, Home/Core, Today, organizer records,
  deterministic command navigation, Recovery/history, and the native
  menu-bar/Quick Capture lifecycle.
- Preserve canonical record identity: identical Task titles remain valid,
  distinct records.
- Prevent repeated user interaction from issuing a second in-flight canonical
  creation request, including Quick Capture and existing organizer creates.
- Ensure externally refreshed Task records appear in an already open Task
  workspace without a manual reload.
- Rebuild and verify the ARM64 sidecar and packaged macOS application under
  the existing Rust-owned authenticated runtime boundary.

## Explicit exclusions

Phase 1H adds no product subsystem, AI, integration, calendar, generic Undo,
event sourcing, dependency, migration, trust-boundary capability, or Master
Specification change. Distribution signing and notarization remain deferred.

## Acceptance

- Tests demonstrate distinct same-title Task records and one canonical
  mutation for rapid Task/Quick Capture submission.
- The repository validation gate, ARM64 sidecar build, Tauri production build,
  and feasible packaged startup, persistence, shutdown, duplicate-instance,
  listener, and process checks pass.
- Owner manually verifies native macOS menu-bar placement, window behavior,
  visual consistency, and keyboard/VoiceOver interaction.
