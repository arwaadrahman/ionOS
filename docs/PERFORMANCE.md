# Performance and Resource Policy

## Status

**Accepted engineering policy.** Concrete budgets remain subject to measured
prototypes and phase-specific acceptance criteria.

## Durable principle

> Persistent intelligence does not require persistent computation.

Ion should remain comfortable to leave open on a Mac throughout the day.
Durable information belongs primarily in SQLite, Markdown, or original source
files. Runtime layers load bounded projections of the information needed for
the current surface or operation and release work that is no longer useful.

Baseline Today, Tasks, Calendar, capture, navigation, and deterministic search
must not depend on:

- an always-loaded local LLM;
- continuous WebGL rendering while hidden or inactive;
- continuous repository indexing or expensive full-diff calculation;
- unbounded caches, event histories, queues, or frontend state;
- one persistent polling worker per integration; or
- heavyweight development-agent runtimes embedded inside Ion.

## Resource ownership and accounting

Ion-owned measurements cover the desktop process, renderer, Rust runtime,
owned Python sidecar, and attributable GPU or helper-process cost where the
platform exposes it. External applications such as Claude Code, Codex, IDEs,
and Ollama are measured separately. Ion observing an external tool must not
mirror that tool's process memory, session state, or conversation history.

Human project time and agent execution time are distinct measures. Unattended
agent runtime is not human focus time and must never be reported as such.

## Heavy systems are on demand

Potentially heavyweight systems include local models, embedding or index
maintenance, advanced Ion Core visualization, expensive project analysis, and
large-repository analysis. Where practical, they should:

- initialize lazily;
- suspend while hidden or inactive;
- use bounded inputs, outputs, caches, and work queues;
- release resources after meaningful idle periods; and
- remain optional for baseline Ion operation.

## Resource-safety guidance

### Filesystem observation

Watching entire repositories can create extreme event volume, especially from
`.git`, `node_modules`, `target`, build output, package caches, and generated
artifacts. Prefer explicitly registered project allowlists, narrow watched
paths, aggressive generated-directory exclusions, debounce/coalescing, and
agent or Git lifecycle signals over raw filesystem observation.

### Git inspection

Continuous large diff computation creates avoidable CPU and disk churn. Use
cheap status checks for ordinary observation. Compute expensive diffs, stats,
or repository analysis at explicit request or meaningful checkpoints.

### Agent events

Long sessions can produce thousands of events. Use bounded queues or ring
buffers, persist compact durable checkpoint state, and expose only recent or
current state to the UI. Full transcripts and hidden reasoning are not default
telemetry.

### React

SQLite remains canonical. Renderer state should be a bounded projection rather
than a whole-database mirror. Subscriptions, observers, timers, and listeners
must have one clear owner and deterministic cleanup.

### Python

Caches require an explicit owner, invalidation rule, and ceiling. Convenience
alone is not sufficient justification for caching, and process-lifetime caches
must not grow without a bound.

### Local AI

Local models may consume multiple gigabytes of unified memory. Load them on
demand, unload them after a meaningful idle period where the provider permits,
and never require them for deterministic baseline workflows.

### WebGL and Ion Core

Suspend rendering when hidden or backgrounded, reduce background animation,
bound graph/node counts, use level of detail where appropriate, and avoid a
permanent expensive animation loop when the visualization is not visible.

### Polling and scheduling

Calendar, Gmail, Canvas, GitHub, developer agents, and future integrations must
not each accumulate independent uncoordinated timers. Prefer event-driven
updates where practical and use centralized scheduling with sensible refresh
intervals where polling is necessary.

Phase 2C-2 Calendar create adds no polling timer or background loop. Each
explicit create, sync, re-consent, or startup recovery trigger drains at most
10 ready write plans after a bounded recovery pass; retry timestamps remain
durable until a later trigger.

### Child processes

External applications own their own lifecycle. Ion may later expose narrow,
explicit launch and observation capabilities, but it must not become a generic
terminal, process launcher, or supervisor. The renderer never receives generic
shell or process authority.

## Initial targets

Approximately **300 MB of Ion-owned idle memory** is a provisional soft
engineering target, not a contractual limit. An idle baseline approaching or
exceeding approximately **500 MB** should be investigated unless a measured,
documented feature requirement clearly justifies it.

The stronger invariant is that Ion's memory must not materially or
monotonically grow merely because the application remains open for days.
Normal bounded fluctuations are acceptable; persistent unexplained growth is
not.

## Measurement and soak testing

Performance evidence should record the Ion version, enabled surfaces, data
scale, machine/OS context, measurement method, and whether external tools were
running. A future soak gate should exercise:

1. Fresh launch, then measure.
2. Idle, then measure.
3. Normal navigation and representative use, then measure.
4. Return to idle, then measure retained memory and CPU.
5. Continue through a multi-hour runtime and remeasure.
6. Run a 24-hour-or-longer soak and inspect memory/CPU trends, listener and
   subscription cleanup, cache bounds, and leaked resources.

Feature-level performance work should prefer evidence over speculative
optimization. Any phase that introduces a heavyweight subsystem must define
its lazy-start, idle/suspension, cleanup, bounding, and measurement behavior
before acceptance.

## References

- [Architecture](ARCHITECTURE.md)
- [Security and privacy](SECURITY.md)
- [AI system boundary](AI_SYSTEM.md)
- [ADR 0020](decisions/0020-external-developer-agent-bridge.md)
