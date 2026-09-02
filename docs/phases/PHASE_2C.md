# Phase 2C — Two-way Google Calendar (v2 rebuild)

## Status

**Preparation complete; no v2 implementation has begun.**

This plan replaces the Phase 2C write architecture that failed real owner
acceptance. That implementation is preserved on `main` and
`archive/phase-2c-v1` as reference material and is not accepted product code.
See [ADR 0022](../decisions/0022-phase-2c-controlled-rebuild.md) for why it was
withdrawn.

The rebuild branch `phase-2c-rebuild` starts at the accepted Phase 2B baseline
`72ea3ba` and carries forward the **current** product contract, not Phase 2B's
product assumptions.

## Objective

Make direct human Calendar actions work the way a person expects — the action
happens, the Calendar shows it, and nothing asks again — while keeping the
provider-write safety boundary of [ADR 0021](../decisions/0021-google-calendar-write-outbox-and-conflicts.md)
fully intact.

## The contract this phase implements

[Calendar interaction behavior](../CALENDAR_BEHAVIOR.md) is the binding
interaction contract and must be read before any work in this phase. Its
non-negotiable consequences for every subphase below:

- **Direct human action is authorization.** Create, edit, drag, resize, delete,
  scope choice, Undo, and an explicit retry after a genuine terminal failure are
  each self-authorizing.
- **AI and scheduler changes are proposals.** Owner approval is the single
  authorization; afterwards they follow the identical authorized write path.
- **Provider synchronization is never a second authorization step.**
- **Recurrence scope is target selection**, asked after the change is described,
  and nothing is asked after it.
- **Undo over confirmation** for everything reversible. Confirmation is spent
  only where Ion cannot truthfully offer to undo — removing confirmed
  occurrences.
- **Convergence is automatic in both directions** and is not a workflow.
- **Semantic conflict ≠ sync concurrency.** Version drift is an internal event.
- **No version chooser exists**, in any form, at any rarity.

## Architecture the rebuild must not weaken

Unchanged from the accepted boundary:

```text
renderer → narrow Tauri command → Rust → authenticated loopback FastAPI → SQLite
```

- local-first canonical state; SQLite owns canonical records and durable intent
- Rust alone owns OAuth, Keychain access, tokens, and Google HTTPS
- Python owns domain validation, canonical transactions, and reconciliation
- React receives safe DTOs and fixed commands, never provider request authority
- conditional provider writes with exact non-wildcard `If-Match`; never
  `If-Match: *`
- narrow provider method and body allowlists
- deterministic provider identities where they prevent duplicates
- OAuth secrets never reach the renderer
- no LAN exposure

A simpler UX does not require weakening any of these.

## What is explicitly not carried forward

Rejected by owner acceptance and not to be reimplemented:

- *Needs Review* as an ordinary human state
- *Review differences*, *Keep Google's version*, *Apply my Ion changes* as
  ordinary flow — or as any flow
- human `write_pending` blocking: refusing an edit because an earlier write has
  not finished
- a generic conflict workflow, or any unclassified outcome that could produce one
- confirmation-heavy edits
- manual **Sync Now** as a step in write progression
- provider lifecycle state presented as user workflow
- **Not saved yet** on ordinary Calendar events
- a gesture that produces a review draft instead of committing
- any assumption that provider synchronization is user authorization
- compatibility shims whose purpose is keeping the above alive

## Subphase sequence

Each subphase is the smallest capability that is independently useful, and each
passes the same two gates before the next begins.

### 2C-R0 — clean writable architecture foundation

No user-visible write capability.

- a minimal direct-human mutation coordinator: accept intent durably, always
- provider serialization designed as a **separate** concern from human
  acceptance, so a newer human action can never be refused by an older write
- a write store whose states cannot represent "an unclassified disagreement
  awaiting a person"
- the closed recovery-condition set defined as a type, with no generic member
- its own migration on top of `0006_calendar_presentation_metadata`
- cross-layer seam harness stood up **before** any UI capability work
- every layer's allowlists (renderer draft → Tauri validation → API contract →
  domain → dispatch) enumerated in one place and asserted equal by test

Exit: cross-layer harness green. No real-Google gate — nothing writes yet.

### 2C-R1 — one-time create and edit

- create an ordinary event; edit an ordinary event
- automatic Ion → Google; automatic Google → Ion
- Undo where it is truthful

**Then real Google acceptance. Do not proceed if it fails.**

### 2C-R2 — direct drag and resize

- gesture is the action; it commits at pointer release
- immediate optimistic projection
- repeated rapid gestures on the same event, with no refusal
- no Save review step
- Undo

**Then real Google acceptance.**

### 2C-R3 — delete

- simple delete semantics for a non-recurring event
- one destructive confirmation, because deletion cannot be truthfully undone
- Undo only where it is honest

**Then real Google acceptance.**

### 2C-R4 — recurrence: this event and all events

- post-action centered, focus-trapped scope chooser
- occurrence identity through master plus immutable original start, with
  **structural identity separated from version drift** — the specific defect
  that produced the permanent review loop in v1
- series edit

**Then real Google acceptance.**

### 2C-R5 — this and following

- real series split: conditional trim, then a deterministic new master
- only after the simpler recurrence operations are stable and accepted
- withheld with a plain explanation where Ion cannot faithfully continue the
  pattern

**Then real Google acceptance.**

### 2C-R6 — hardening

- offline and retry, including self-waking backoff rather than a poll
- successive edits across restart
- automatic incremental reconciliation
- genuinely exceptional failures, each a named member of the closed set
- packaging and security gates

**Then real Google acceptance.**

The subphase names may vary. The principle may not:

> smallest capability → cross-layer test → real Google test → only then continue.

## Cross-layer testing from day one

Phase 2C v1 repeatedly passed isolated tests while production seams were broken.
A feature is not ready for owner testing until a test exercises:

```text
renderer → Tauri/Rust → authenticated FastAPI → SQLite → synthetic provider
```

Specifically required:

- every scope, operation, and safe-reason value asserted present in **all**
  layer allowlists by a single test, so a value added to one and missed in
  another fails in CI rather than in the owner's hands
- an ordinary edit walked from gesture through queue, dispatch, drift, re-read,
  rebase, background sync, a successive edit, and settlement, asserting that
  **no recovery condition is ever produced**
- an assertion that no ordinary Calendar surface renders write-lifecycle copy

"Python domain tests pass" is explicitly **not** acceptable evidence.

## Real Google acceptance from day one

After each subphase:

1. synthetic and cross-layer tests green
2. package a fresh build
3. create a disposable real Google event
4. the owner validates the exact interaction the subphase claims to deliver

If real Google fails, that subphase stops. Later write features are not built on
an unaccepted one.

## Database

The rebuild branch's migration head is `0006_calendar_presentation_metadata`.
`0007_calendar_write_foundation` belongs to the withdrawn implementation, stays
committed on `main` and `archive/phase-2c-v1`, and is neither deleted nor
revived. 2C-R0 introduces its own revision chained to `0006`.

A developer database already upgraded to `0007_calendar_write_foundation` cannot
be read by this branch's migration runner. Use a separate `ION_DATA_DIR` for
rebuild work. **No downgrade, deletion, or mutation of the owner's production
database is performed.**

## References

- [Master Specification](../PRODUCT_SPEC.md) — Calendar authority amendment
- [Calendar interaction behavior](../CALENDAR_BEHAVIOR.md)
- [Phase 2A](PHASE_2A.md) · [Phase 2B](PHASE_2B.md)
- [ADR 0021](../decisions/0021-google-calendar-write-outbox-and-conflicts.md)
- [ADR 0022](../decisions/0022-phase-2c-controlled-rebuild.md)
- [Architecture](../ARCHITECTURE.md) · [Security](../SECURITY.md) ·
  [Integrations](../INTEGRATIONS.md) · [Data model](../DATA_MODEL.md)
