# ADR 0007: SQLite access and migrations

**Status:** Accepted
**Date:** 2026-08-27

## Context

Ion needs an executable local structured-data foundation without preempting the
Phase 1 domain model.

## Decision

Use SQLite outside the repository, SQLAlchemy 2 Core for database access, and
Alembic for migrations. Phase 0B creates no ORM domain models and no Phase 1
entity tables. Its baseline migration proves database opening, Alembic upgrade
to head, and version-state recording only.

## Consequences

Runtime databases are never committed. The project has a migration path before
canonical entity schemas are designed, while avoiding a premature product
schema.

## Alternatives considered

- Direct `sqlite3` with a handwritten migration runner: smaller initially but
  creates project-specific migration infrastructure.
- ORM entity models now: rejected because the Phase 1 domain schema is out of
  scope.

## References

- [Data model principles](../DATA_MODEL.md)
- [Phase 0B](../phases/PHASE_0B.md)
