# ADR 0008: Production service lifecycle

**Status:** Accepted  
**Date:** 2026-08-27

## Context

Phase 0B deliberately established only a development loopback boundary. A
packaged Ion application must not require a user-installed Python runtime and
must own the lifetime of its local application service.

## Decision

For the Phase 0C Apple Silicon prototype, package the Python/FastAPI service as
a PyInstaller one-file executable and embed it as a Tauri sidecar. The Rust
backend is the sole process owner: it starts one child, supplies its private
bootstrap input, validates bounded readiness output, performs authenticated
health verification, observes exit, and requests graceful shutdown before a
bounded forced-termination fallback.

Production service instances bind an IPv4 socket to `127.0.0.1:0` themselves
and retain that bound socket for Uvicorn. Rust never reserves and releases a
port before launch. The service reports its selected port only through the
private readiness protocol. Runtime databases, settings, and logs remain in
the user Application Support directory; no runtime data belongs in the app
bundle, repository, or PyInstaller extraction directory.

The readiness budget is at most 15 seconds and graceful shutdown allowance is
at most 5 seconds. Phase 0C provides no daemon, launch agent, automatic crash
restart loop, or multi-instance policy.

## Consequences

The packaged application does not require system Python or uv. One-file
bootloader/child behavior must be verified specifically for normal shutdown,
failed readiness, forced termination, abnormal exit, repeated cycles, orphan
processes, listeners, and temporary extraction residue. If it cannot meet
those lifecycle criteria, Ion must stop and seek approval for one-directory or
another bounded alternative; one-file is a prototype decision, not a permanent
distribution commitment.

ADR 0006 remains valid for development. This ADR supersedes only its deferred
production lifecycle and packaging portion.

## Alternatives considered

- Require system Python/uv: rejected because an installed Ion app must be
  self-contained.
- PyInstaller one-directory: retained as the approved fallback if one-file
  lifecycle evidence fails, but less convenient for Tauri sidecar embedding.
- Nuitka, PyOxidizer, or an embedded CPython distribution: rejected for this
  bounded prototype because they introduce greater packaging complexity.
- A daemon or launch agent: rejected because it broadens lifecycle scope.

## References

- [ADR 0006](0006-local-api-service-boundary.md)
- [Security baseline](../SECURITY.md)
- [Phase 0C](../phases/PHASE_0C.md)
