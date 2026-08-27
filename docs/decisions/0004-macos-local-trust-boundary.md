# ADR 0004: macOS-local trust boundary

**Status:** Accepted
**Date:** 2026-08-27

## Context

Ion's personal data and local application service need a deliberately narrow
trust boundary during its early engineering work. Mobile support would require
separate decisions about synchronization, remote access, authentication,
authorization, transport security, credentials, and attack surface.

## Decision

Ion operates within a macOS-local trust boundary. Mobile support is
intentionally deferred until a dedicated mobile/security architecture review is
completed and the owner explicitly approves expanding Ion beyond the local
macOS trust boundary.

Phase 0B contains no mobile code, synchronization, remote-access service,
cloud relay, or LAN-exposed API. The local application service binds to
loopback only.

## Consequences

The historical mobile roadmap in the Master Specification is superseded for
current implementation purposes. Any future mobile work requires a new
approved architecture and security decision before implementation begins.

## Alternatives considered

- Scaffold a future mobile client now: rejected because it would prematurely
  shape synchronization and security architecture.
- Expose the local API on a network interface: rejected because it expands the
  trust boundary without an approved authentication or authorization model.

## References

- [Security baseline](../SECURITY.md)
- [Architecture](../ARCHITECTURE.md)
- [Phase 0B](../phases/PHASE_0B.md)
