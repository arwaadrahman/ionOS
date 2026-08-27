# AI System Boundary

## Status: Deferred

AI is not Ion's database and no AI runtime, provider, dependency, or router is
implemented in Phase 0A.

- Prefer deterministic Tier 0 functionality whenever it can solve the task.
- Local structured retrieval and context filtering precede model reasoning.
- Future local and cloud providers must sit behind an abstraction; individual
  product features must not depend directly on a single vendor.
- Future Cloud Deep Ask work needs explicit privacy, context-minimization,
  authorization, usage, and audit boundaries.
- AI suggestions remain candidates until Ion validates and stores an authorized
  structured result. Human actions outrank automated actions.

`packages/ai-router` and any provider or embedding implementation are outside
this milestone.
