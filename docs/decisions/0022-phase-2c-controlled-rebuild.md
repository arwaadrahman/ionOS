# ADR 0022: Controlled Phase 2C rebuild from the accepted Phase 2B baseline

**Status:** Accepted

**Date:** 2026-09-01

## Context

Phase 2C added two-way Google Calendar writes in five increments on top of the
accepted Phase 2B Calendar. Every increment passed its own tests. Real owner
acceptance nonetheless failed, repeatedly and in the same shape:

- ordinary Calendar events displayed **Not saved yet**;
- global Calendar surfaces exposed incomplete provider and write state as if it
  were part of the product;
- ordinary human actions kept arriving at review/conflict machinery —
  *Needs review*, *Review differences*, *Keep Google's version*,
  *Apply my Ion changes*;
- the owner could not tell whether a normal action would settle;
- each individual route repaired was followed by another, and the fixes began
  exposing cross-layer blockers rather than converging.

The last symptom is the diagnostic one. The defects were not independent. The
architecture permitted **any** unclassified provider disagreement to fall
through into a generic "review this" decision, and it treated provider
synchronization as a second authorization step. Given those two properties, an
ordinary edit reaching a review task is not a bug to be fixed at each site — it
is the design working as specified. Repairing sites could not terminate.

A second structural cause: the increments were validated by isolated layer
tests. `this and following` shipped implemented end to end in the Python domain,
with passing tests, while the Tauri command's scope allowlist still read
`single | occurrence | series`. Every real attempt failed as
`local_state_invalid`. Green domain tests were not evidence that a Calendar
write worked.

Continuing to repair the implementation was rejected by the owner.

## Decision

Rebuild Phase 2C from the last accepted Phase 2B baseline
(`72ea3ba`, "Phase 2B accepted; documentation checkpoint before Phase 2C"),
on the branch `phase-2c-rebuild`, under the following constraints.

### 1. Preserve, do not delete

The complete Phase 2C v1 implementation — five commits plus the entire dirty
worktree at the time of the decision — is preserved on `main` and on
`archive/phase-2c-v1`, both pushed to `origin`. It is historical reference
material, not accepted product code. No history is rewritten and nothing is
force-pushed. `phase-2c-rebuild` is intended to become the accepted Phase 2C
implementation and to integrate back into `main` by ordinary merge; `main` is
never reset to Phase 2B.

### 2. The current product contract carries forward; the Phase 2B-era rules do not

The rebuild branch starts at a Phase 2B commit but **not** at Phase 2B's
product assumptions. The Master Specification's Calendar authority amendment,
[Calendar interaction behavior](../CALENDAR_BEHAVIOR.md), the Google-Calendar
behavioral default, and the routing rule that requires reading that contract
are ported forward even though they post-date the baseline. Where the contract
and a Phase 2B-era statement disagree, the contract governs.

### 3. Two authorization models, and only two

| Origin | Authorization |
| --- | --- |
| The owner acting directly | the action itself |
| Ion's scheduler or a future AI | the owner accepting the proposal |

After either, **nothing asks again.** Persisting, dispatching, reconciling a
provider version, and settling are consequences of a decision already made.
Provider synchronization is never a second authorization step. `flexibility`
(`locked` / `flexible` / `Ion-controlled`) constrains Ion's own automation, not
the owner.

### 4. Human acceptance and provider serialization are separate concerns

A newer direct-human mutation is always accepted durably. The provider still
receives one serialized write per target. The owner is never refused because an
earlier write has not finished, and provider lifecycle state is never surfaced
as workflow.

### 5. The version chooser is withdrawn, not narrowed

*Keep Google's version*, *Review differences*, and *Apply my Ion changes* are
not reimplemented in any form. Conditions that genuinely need a person are a
closed set of specifically named recovery states with deliberately no generic
member, each offering only actions truthful for that exact condition. An
outcome matching nothing in the set is Ion's to finish, not a decision handed
to the owner.

### 6. Provider-write safety is unchanged

ADR 0021's safety layer is retained in full: the Rust/Python/React authority
split, canonical intent before dispatch, the durable outbox, exact non-wildcard
`If-Match` (never `If-Match: *`), the narrow method and body allowlists,
deterministic create identity, bounded restart-safe retry, and the sanitized
audit boundary. **A simpler UX does not weaken provider safety.** The two are
separate layers, and this ADR changes only the first.

### 7. Smallest capability, then two gates

Each subphase delivers the smallest useful capability and must pass, in order:

1. a **cross-layer** test spanning renderer → Tauri/Rust → authenticated
   FastAPI → SQLite → synthetic provider;
2. **real owner acceptance** against a disposable Google event in a freshly
   packaged build.

A failed real-Google gate stops that subphase. No later write capability is
built on top of an unaccepted one. "Python domain tests pass" is not evidence
that a Calendar write feature works.

## Consequences

- The rebuild branch is read-only for Google events at its baseline, exactly as
  accepted Phase 2B was. That is preferable to shipping writable-state UX the
  owner has rejected.
- **Migration history is immutable** (owner decision, 2026-09-01). Migration
  `0007_calendar_write_foundation` is ported byte-for-byte onto the rebuild
  branch, because the owner's existing databases are already at `0007` and a
  rebuild must never require real data to be downgraded. Porting the migration
  carries schema only, not the withdrawn write behavior. Every new 2C v2 schema
  change is `0008` or later; no competing `0007` is created and nothing is
  deleted or renumbered.
- The Phase 2C v1 provider-safety mechanisms — the request allowlist, ETag
  helpers, deterministic identities, bounded recurrence rules, the shared
  Google gate — are available for deliberate reuse, read from the archive and
  reintroduced with tests, never bulk-copied.
- Work that mixed presentation with rejected write orchestration in one file is
  ported by extraction, not by taking the file.

## References

- [Calendar interaction behavior](../CALENDAR_BEHAVIOR.md)
- [Phase 2C rebuild plan](../phases/PHASE_2C.md)
- [ADR 0021](0021-google-calendar-write-outbox-and-conflicts.md)
- [Master Specification](../PRODUCT_SPEC.md) — Calendar authority amendment
