# Architecture Decision Records

An ADR records a consequential, durable decision and its context,
consequences, and alternatives. Create one when an architecture, dependency,
data ownership, security/privacy, or long-lived product boundary changes.

## Status vocabulary

- **Canonical:** Established by the Master Specification.
- **Proposed:** Under consideration; not approved for implementation.
- **Accepted:** Deliberately adopted and binding until superseded.
- **Superseded:** Replaced by a later ADR.
- **Deferred/TBD:** Explicitly unresolved and not authorized for silent choice.

Canonical decisions may be recorded as Accepted when an ADR faithfully captures
them without adding unapproved implementation detail. Research recommendations
remain proposed until intentionally accepted.

## Index

- [0000 ADR template](0000-adr-template.md)
- [0001 Local-first data ownership](0001-local-first-data-ownership.md)
- [0002 Public repository data safety](0002-public-repository-data-safety.md)
- [0003 Phase 0 scope boundaries](0003-phase-0-scope-boundaries.md)
- [0004 macOS-local trust boundary](0004-macos-local-trust-boundary.md)
- [0005 Phase 0B toolchain baseline](0005-phase-0b-toolchain-baseline.md)
- [0006 local API service boundary](0006-local-api-service-boundary.md)
- [0007 SQLite access and migrations](0007-sqlite-access-and-migrations.md)

## Decision Backlog

- License selection and CI strategy.
- Production Python sidecar lifecycle, port allocation, local-process
  authentication, crash recovery, and supervision.
- Relationship provenance/promotion rules and the future Ion Core spike plan.
