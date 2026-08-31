# AI System Boundary

## Status: Deferred through accepted Phase 2B

AI is not Ion's database and no AI runtime, provider, dependency, or router is
implemented through Phase 2B.

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

## External coding agents are not Ion AI providers

Claude Code and Codex are external development tools, not implementations of
Ion's local AI or Cloud Deep Ask tiers. Their authentication, processes,
sessions, and conversations remain owned by those tools. Normal Claude Code
uses the user's Claude subscription and never receives Ion's Anthropic API
credential. A future Developer Agent Bridge may prepare a compact handoff and
observe bounded evidence, but it does not embed an agent runtime or turn the
agent into Ion's canonical memory. See ADR
[0020](decisions/0020-external-developer-agent-bridge.md).

## Future Deep Ask boundary

Deep Ask may use paid OpenAI or Anthropic APIs only after its separately scoped
privacy and authority work. Provider credentials remain in macOS Keychain or
equivalent secure storage. Local retrieval, context minimization,
sensitive-data filtering, Private Local exclusions, structured-result
validation, explicit cloud use, and configurable usage/cost budgets precede
cloud reasoning. Normal Ion operation and external coding-agent development do
not depend on Deep Ask.

Local models, embedding maintenance, and large retrieval jobs are heavyweight
on-demand systems. They initialize lazily, are not required by baseline
Today/Tasks/Calendar behavior, and should release resources after meaningful
idle periods where the provider permits. See
[Performance and Resource Policy](PERFORMANCE.md).
