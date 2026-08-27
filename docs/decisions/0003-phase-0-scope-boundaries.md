# ADR 0003: Phase 0 scope boundaries

**Status:** Accepted
**Date:** 2026-08-27

## Context

Phase 0 creates a stable, understandable engineering foundation before product
features, integrations, or AI are introduced.

## Decision

Phase 0 includes repository governance, documentation, architecture records,
then later executable scaffolding, linting/formatting, testing, Tauri/React,
Python service, SQLite connection, logging, settings, and synthetic fixtures.
It excludes AI, Google, and Canvas. Phase 0A is limited to documentation and
governance; executable scaffolding is deferred to Phase 0B and later Phase 0
milestones.

## Consequences

No application/package/test trees, runtime dependencies, integration code, or
personal data are introduced by Phase 0A. Proposed stack choices stay proposed
until the appropriate later decision.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Phase 0A](../phases/PHASE_0A.md)
