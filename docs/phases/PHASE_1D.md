# Phase 1D — Home and Ion Core baseline

## Objective

Deliver a truthful default Home overview and the first deterministic,
navigable spatial Ion Core over the existing canonical organizer.

## Scope

- One read-only Home API projection and fixed authenticated Tauri command.
- Untrashed Area, Goal, Goal Milestone, Project, Project Milestone, and Task
  nodes with direct structural child-to-owner edges only.
- Normalized lifecycle, current Today role, and Needs Attention context.
- Compact Focus, Needs Attention, and Upcoming summaries derived from the
  established Today projection.
- Versioned deterministic TypeScript layout with stable parent clustering and
  no persisted coordinates.
- Lazy raw Three.js WebGL2 renderer with canonical node points, structural
  lines, deterministic ambient dust, OrbitControls, hover/select/Open, and
  accessible rotate/zoom/reset controls.
- Reduced-motion, focus/visibility pausing, context-loss/static fallback, and
  explicit StrictMode-safe cleanup.
- Home-first five-destination navigation and freshness after canonical
  mutations or local-day context changes.

## Durable behavior

- SQLite remains the sole owner of organizer and Today planning records. Home,
  graph buffers, coordinates, selection, and camera state are derived only.
- Today owns execution and plan mutation. Home summarizes but does not duplicate
  its controls or claim Calendar/scheduling knowledge.
- Archived, paused, completed, and inactive untrashed records remain visible
  with subdued lifecycle treatment; Trash remains excluded.
- Failed Home refresh keeps the last confirmed overview and is reported
  separately from the mutation that made it stale.
- Milestone Open navigation resolves through its canonical Goal or Project
  owner.

## Explicit exclusions

Phase 1D excludes schema migration, persisted graph/layout state, inferred or
contextual edges, force/physics layout, React Three Fiber, Drei,
postprocessing, AI/embeddings, enabled Ask Ion, final Explore modes, Calendar,
FocusSession, integrations, cloud/mobile, and any new renderer capability.

## Acceptance

- Home service tests prove deterministic ordering, relationship coverage,
  summary policy, empty state, Trash exclusion, authentication, and zero audit
  writes.
- Layout tests prove repeatability, finite bounded coordinates, stable
  unrelated additions, parent choice, and valid 1,000/2,000-node buffers.
- StrictMode and repeated mount/unmount tests prove controller cleanup.
- Desktop production build, repository validation, frozen ARM64 sidecar, Tauri
  `.app`, and packaged WKWebView startup succeed.
- Owner manually accepts visual identity, pointer behavior, selection/Open,
  repeated Home/Today navigation, summary truthfulness, and optional
  reduced-motion behavior.
