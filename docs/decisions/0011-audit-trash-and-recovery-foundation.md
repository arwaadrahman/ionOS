# ADR 0011: Audit, Trash, and recovery foundation

**Status:** Accepted
**Date:** 2026-08-27

## Decision

Canonical state tables remain Ion's source of truth. Each organizer record has
a revision counter. Meaningful mutations append compact audit metadata in the
same transaction as the canonical mutation. Audit records contain no service
credentials, secrets, or payload snapshots.

Trash is represented by nullable `trashed_at`; normal active queries exclude
trashed records. Hard-delete relationships use restrictive behavior rather
than SQL cascades. Phase 1A implements Task complete/reopen and trash/restore
only; generic Undo, arbitrary rollback, snapshot history, automatic purge, and
version-history UI remain later Phase 1 work.
