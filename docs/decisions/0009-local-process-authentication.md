# ADR 0009: Local-process authentication

**Status:** Accepted  
**Date:** 2026-08-27

## Context

Loopback binding and CORS alone do not authenticate a caller. A packaged Ion
service must resist opportunistic local-service calls and must not disclose its
credential to renderer JavaScript.

## Decision

For every production service launch, Rust obtains at least 256 bits from the OS
cryptographic random source and keeps the resulting transport-safe session
credential in memory only. It sends the credential exactly once through a
bounded newline-delimited stdin bootstrap message after spawning the sidecar.
It is never persisted, placed in arguments or environment variables, stored in
Keychain or SQLite, returned to the renderer, or written to logs.

Production FastAPI requires the credential on every endpoint through a
dedicated header and compares it with `hmac.compare_digest`. It fails closed
when bootstrap/authentication initialization is incomplete. Production has no
CORS middleware because the renderer calls narrow Ion-owned Tauri commands,
not FastAPI directly. Rust owns the selected port and all authenticated
loopback requests. The renderer receives neither port nor credential.

The sidecar control protocol accepts one bounded bootstrap message, then only a
bounded shutdown command. Readiness uses one bounded, identifiable stdout
record containing only the port. EOF on the control channel requests service
shutdown where the platform/process model permits it.

## Consequences

The local trust boundary is materially narrower than a renderer-held token.
It does not defend against code already able to control or inspect Ion as the
same macOS user; OS process isolation and future signing remain separate
concerns. A retry starts a new service and generates a new credential.

## Alternatives considered

- CORS-only loopback service: rejected because CORS is not authentication.
- Renderer-held bearer token: rejected because renderer compromise exposes it.
- Persistent token/Keychain storage: rejected because this credential is only
  a process-session secret.

## References

- [ADR 0004](0004-macos-local-trust-boundary.md)
- [ADR 0008](0008-production-service-lifecycle.md)
- [Security baseline](../SECURITY.md)
