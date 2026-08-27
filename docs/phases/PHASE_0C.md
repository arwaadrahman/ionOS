# Phase 0C — Production Local Runtime & Security Prototype

## Objective

Prove that the packaged Apple Silicon macOS Ion app can securely own, start,
authenticate, monitor, and stop its self-contained Python/FastAPI service.

## Scope

- PyInstaller one-file ARM64 Python sidecar prototype.
- Rust-owned Tauri sidecar lifecycle, bounded readiness, and shutdown.
- Per-launch 256-bit local-process authentication and Rust-only loopback HTTP.
- Race-free `127.0.0.1:0` production socket ownership.
- Local unsigned/ad-hoc-signed `.app` proof and lifecycle evidence.

## Explicit exclusions

No Phase 1 behavior, integrations, AI, mobile, LAN/remote/cloud access,
daemon/LaunchAgent, multi-instance policy, signing/notarization, installers,
automatic updates, or launch-at-login.

## Acceptance evidence

The packaged service requires neither system Python nor uv; binds only IPv4
loopback; rejects missing/wrong credentials; does not disclose session state to
the renderer; obeys readiness/shutdown limits; leaves no listener or orphan on
verified paths; preserves Application Support ownership; and passes applicable
quality checks.

Service startup failure is non-fatal to the desktop engineering shell. Any
spawn, readiness, authentication, timeout, or early-exit failure must clean up
the attempted child and leave Rust-owned service state `Unavailable`; it must
not abort the Tauri application. This correction followed an earlier Phase 0C
verification crash. Outer-bundle resource sealing remains deferred to future
distribution signing/notarization work for this unsigned local prototype.

Final owner manual verification after the startup-failure correction completed
three packaged ARM64 `.app` launch/quit cycles. Each launch and quit completed
normally without a macOS crash alert, and each left no Ion desktop process,
sidecar process, or Ion listener. The post-correction UI-driven normal-quit
verification gap is closed.

## Decisions

- [ADR 0008](../decisions/0008-production-service-lifecycle.md)
- [ADR 0009](../decisions/0009-local-process-authentication.md)
