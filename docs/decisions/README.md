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
- [0008 Production service lifecycle](0008-production-service-lifecycle.md)
- [0009 Local-process authentication](0009-local-process-authentication.md)
- [0010 Phase 1 organizer domain](0010-phase-1-organizer-domain.md)
- [0011 Audit, Trash, and recovery foundation](0011-audit-trash-and-recovery-foundation.md)
- [0012 Organizer lifecycle and containment](0012-organizer-lifecycle-and-containment.md)
- [0013 Today planning and pre-Calendar boundary](0013-today-planning-and-pre-calendar-boundary.md)
- [0014 Ion Core rendering and Phase 1D Home boundary](0014-ion-core-rendering-and-phase-1d-home-boundary.md)
- [0015 Deterministic command-search projection](0015-deterministic-command-search-projection.md)
- [0016 Recovery and history projection](0016-recovery-and-history-projection.md)
- [0017 macOS menu-bar and instance lifecycle](0017-macos-menu-bar-and-instance-lifecycle.md)

## Decision Backlog

- License selection and CI strategy.
- Relationship provenance/promotion rules and future Core Explore modes.
