# ADR 0014: Ion Core rendering and Phase 1D Home boundary

**Status:** Accepted
**Date:** 2026-08-28

## Context

Phase 1D needs a default Home overview and the first operational Ion Core. The
Core must reveal the organizer already owned by SQLite without creating a
second graph model, storing visualization state, or turning Home into another
Today execution list. It must also fit the existing authenticated
Rust-to-Python product boundary and React StrictMode lifecycle.

## Decision

Expose one authenticated, read-only `GET /v1/home` projection through the
fixed Tauri `get_home` command. Python reuses the deterministic Today service
projection for Focus, Needs Attention, deadlines, Today roles, and attention
reasons. Home returns untrashed Areas, Goals, Projects, their two Milestone
types, and Tasks plus only the six accepted direct structural relationships.
The database gains no graph, edge, coordinate, Home-state, or visualization
table.

The desktop computes positions with an explicit versioned stable hash. Parent
clustering uses structural edges only and remains stable when unrelated nodes
are added. Coordinates and camera state are never persisted.

The first renderer uses raw Three.js `WebGLRenderer` with a WebGL2 baseline,
`Points`, `LineSegments`, a fixed deterministic ambient-dust layer, and
`OrbitControls`. React Three Fiber was deliberately not admitted: Phase 1D has
one contained renderer whose explicit controller lifetime is small enough to
own directly, while another reconciler/dependency surface is not yet
justified. Drei, postprocessing, force/physics, graph-layout, and vendor patch
stacks are likewise absent.

Home is the five-destination default navigation surface. Today remains the
canonical daily execution workspace; Home only shows compact Focus, Needs
Attention, and Upcoming summaries and does not duplicate plan controls or
scheduling claims. Ask Ion is visibly disabled because AI is deferred.

Renderer construction failure or WebGL context loss falls back to a truthful
static Core summary. Keyboard-operable rotate/zoom/reset controls accompany
pointer interaction. Animation pauses for reduced-motion preference, hidden
documents, and unfocused windows. Renderer resources, controls, observers,
listeners, and animation frames are explicitly released for StrictMode
cleanup/remount.

## Consequences

- Home reads cannot write audit events or mutate organizer records.
- Core positions are rebuildable and deterministic, not canonical data.
- The renderer remains behind the existing narrow local-process trust boundary
  and receives no service address, session credential, filesystem, or shell.
- The Three.js bundle is lazy-loaded with Home's live Core.
- A failed Home refresh preserves the last confirmed projection and cannot
  relabel a successful canonical mutation as failed.
- Explore modes, contextual or inferred relationships, AI, embeddings,
  Calendar, FocusSession, and persisted view preferences remain deferred.

## Alternatives considered

- React Three Fiber was rejected for this milestone because raw Three.js is
  sufficient for one renderer and keeps the authorized dependency delta
  narrower.
- Persisted graph/layout records were rejected because all inputs already have
  canonical owners and coordinates are presentation state.
- Client-side reimplementation of Today ranking was rejected because it would
  create competing product semantics.
- Force-directed and physics layouts were rejected because they add runtime
  dependencies, nondeterminism, and unstable navigation without Phase 1D value.

## References

- [Phase 1D](../phases/PHASE_1D.md)
- [Architecture](../ARCHITECTURE.md)
- [Data Model](../DATA_MODEL.md)
- [ADR 0013](0013-today-planning-and-pre-calendar-boundary.md)
