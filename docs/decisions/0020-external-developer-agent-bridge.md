# ADR 0020: External Developer Agent Bridge

**Status:** Accepted  
**Date:** 2026-08-30

## Context

Ion should eventually reduce the repeated work of preparing repository-aware
handoffs for external development agents and should understand evidence-based
project progress. Claude Code, Codex, IDEs, Git, and build tools already own
their respective execution and authentication domains. Embedding those tools,
mirroring their sessions, or granting the renderer generic shell authority
would expand Ion into a broad process supervisor and create unnecessary
credential, privacy, and resource risk.

The Master Specification places full GitHub and project-development
intelligence in Phase 8, while allowing useful capabilities to mature earlier
when they help build Ion itself. Cloud Deep Ask is a separate future AI system
with its own provider credentials, retrieval, privacy, and cost boundaries.

## Decision

Ion's first development-agent integration is a lightweight **Developer Agent
Bridge** that prioritizes a Claude Code companion. It is not a broad autonomous
agent platform or process supervisor. Its internal evidence vocabulary remains
extensible to Codex and future coding agents, which also remain external tools.
Their own applications or CLIs own authentication, process lifecycle, session
state, and conversation history.

Claude Code normally uses the user's Claude subscription. Ion never reads,
stores, reuses, exports, or impersonates Claude Code authentication and never
supplies Ion's Anthropic API credential to Claude Code. The same separation
applies to Codex and future external-agent credentials.

For an explicitly registered project, Ion may eventually:

- generate a compact handoff from the registered repository, current
  phase/subphase or milestone, accepted commit, clean/dirty Git state, relevant
  governance documents, prior completion result, and remaining bounded work as
  a compact handoff/prompt;
- launch or resume an allowlisted external agent only after an explicit user
  action; and
- receive bounded structured lifecycle or tool events and combine them with
  deterministic Git, test, build, commit, and checkpoint evidence.

Any launch capability is owned by narrow Rust commands restricted to
allowlisted project paths and allowlisted agent executables. The renderer
receives no generic shell, arbitrary executable, working-directory, process,
terminal, or environment-variable authority. Ion does not silently generate
or send handoffs/prompts or start an agent; handoff generation and agent launch
or resume each require explicit user action.

Default progress observation stores compact evidence such as project,
phase/milestone, agent identity, session start/stop, high-level activity, files
changed, bounded Git statistics, tests/builds attempted, pass/fail state,
commits/checkpoints, agent execution time, and a concise completion summary.
Ion does not collect full transcripts, prompts, source payloads, or hidden
reasoning by default. Event queues and UI projections are bounded; durable
state is compact and local.

Developer telemetry is **Private Local** by default. Project paths, repository
names where sensitive, file lists, diffs, logs, agent activity, and completion
summaries do not gain remote/mobile synchronization merely because such a
surface exists later. Any remote exposure requires a separate accepted
security/privacy decision.

Progress is evidence-based and categorical. Ion may report states such as
`Implementation in progress`, `Validation failing`, `Implementation checkpoint
complete`, or `Clean committed milestone`; it does not fabricate completion
percentages. Human project time and agent execution time are recorded
separately.

The minimal bridge may be implemented before Phase 8 if separately scoped and
approved because it helps build Ion. Full GitHub/project-development
intelligence remains Phase 8. No new numbered roadmap phase is created.

## Consequences

- Ion can reduce repeated context reconstruction without becoming a coding
  runtime, IDE mirror, transcript archive, or autonomous multi-agent platform.
- External tools remain replaceable without a premature broad provider
  framework; the bridge's internal event vocabulary may remain extensible.
- Screen scraping, continuous full-repository filesystem observation,
  continuous expensive diffs, continuous repository embedding, and autonomous
  multi-agent coordination are outside the first bridge.
- Deep Ask API keys remain Ion-owned Keychain credentials used only through the
  separately approved AI boundary. Normal external-agent development requires
  no Ion cloud-AI credential or cloud call.
- Resource behavior follows the bounded, lazy, checkpoint-oriented rules in
  [Performance and Resource Policy](../PERFORMANCE.md).

## Alternatives considered

- Embed Claude Code, Codex, or a full agent runtime: rejected because it
  duplicates external ownership and broadens credentials, lifecycle, and
  resource scope.
- Generic terminal/process launcher: rejected because it grants excessive
  authority and turns Ion into a process manager.
- IDE or terminal screen scraping: rejected as fragile, privacy-invasive, and
  semantically weaker than structured events and deterministic repository
  evidence.
- Store complete transcripts or hidden reasoning: rejected because compact
  outcomes and evidence are sufficient for durable progress context.
- Wait until all Phase 8 work: not required; a narrow bridge may provide useful
  development leverage earlier without moving full project intelligence.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Architecture](../ARCHITECTURE.md)
- [Security and privacy](../SECURITY.md)
- [AI system boundary](../AI_SYSTEM.md)
- [Integration boundaries](../INTEGRATIONS.md)
- [Performance and Resource Policy](../PERFORMANCE.md)
- [ADR 0004](0004-macos-local-trust-boundary.md)
- [ADR 0009](0009-local-process-authentication.md)
