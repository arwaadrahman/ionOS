# ADR 0006: local API service boundary

**Status:** Accepted
**Date:** 2026-08-27

## Context

The approved Phase 0B stack uses a React/Tauri desktop surface and Python
FastAPI application service, while preserving Ion's macOS-local trust boundary.

## Decision

During development, React/Tauri communicates with FastAPI via loopback HTTP.
The service binds only to `127.0.0.1`; the development port is configuration
driven. CORS, where required by development WebView origins, is limited to
explicit known origins and never uses a wildcard.

Production Python sidecar packaging, port allocation, process ownership,
local-process authentication, crash recovery, and service supervision are
explicitly deferred to a dedicated architecture/security prototype.

## Consequences

`npm run dev` may supervise the two development processes. No LAN/public API,
remote access, cloud relay, authentication platform, or mobile synchronization
is added in Phase 0B.

## Alternatives considered

- A Rust proxy or Tauri command layer: deferred; it adds a second application
  boundary before the local service has functional requirements.
- Network-bound API: rejected because it violates the approved trust boundary.

## References

- [ADR 0004](0004-macos-local-trust-boundary.md)
- [Security baseline](../SECURITY.md)
