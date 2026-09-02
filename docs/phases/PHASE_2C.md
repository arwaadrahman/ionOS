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
- any new schema as `0008` or later, on top of the ported immutable `0007`
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
- the trim's `UNTIL` is **domain-generated only**, bounded, and re-validated in
  Rust; the renderer can never supply recurrence text or a terminator value
- **`COUNT`, user-configurable end dates, and *Never / On date / After N* are
  excluded from R5** and remain a later bounded capability
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

## Database (owner decision, 2026-09-01)

**Migration history is immutable. Nothing is deleted, replaced, or renumbered.**

The rebuild branch's migration head is `0007_calendar_write_foundation`, ported
**byte-for-byte** from `989a0c4` / `main` / `archive/phase-2c-v1`. Porting the
migration is not porting Phase 2C v1 behavior: it carries schema only, and none
of the withdrawn write orchestration came with it.

This is deliberate, and the reason is concrete: the owner's existing databases
are already at `0007`. A rebuild that started from `0006` would require them to
downgrade, and downgrading a real database to accommodate a branch is not an
acceptable design.

- **Every new schema change for 2C v2 is `0008` or later.** No competing `0007`
  is ever created.
- Reuse only the parts of the `0007` schema that fit the new architecture. The
  rest may sit unused until superseded by an additive `0008+` revision.
- No `0007` table, column, or constraint is dropped to make the rebuild fit.

### What of `0007` the new architecture can use

| Schema | Verdict |
| --- | --- |
| `google_accounts.calendar_write_scope_state` | **Use.** Write re-consent state. Only its old sidebar surfacing was rejected, not the mechanism. |
| `google_event_links.link_state` / `provider_event_type` / `provider_locked` / `has_attendees` | **Use.** Write-eligibility evidence, no behavior attached. |
| `calendar_provider_write_intents` states, `attempt_count` ceiling, `next_attempt_at` | **Use.** `queued` / `ready` / `retry_wait` versus `attempting` / `ambiguous` is exactly the distinction the supersede rule needs. |
| `predecessor_intent_id` + `uq_calendar_write_block_sequence` | **Use.** Already models "supersede an unsent write, queue behind an in-flight one." |
| `failure_class` CHECK (10 named values, no generic member) | **Use.** Already a closed set. |
| `calendar_provider_write_audit` | **Use.** Compact, payload-free audit. |

### Two known forward constraints, neither blocking R0–R6

1. `provenance = 'direct_human'` is a CHECK constraint. Every 2C v2 subphase is
   direct-human, so it blocks nothing now — but owner-approved **AI-originated**
   Calendar writes will need an additive `0008+` widening. Recorded here so it is
   found before it is hit, not after.
2. `failure_reason` is a free string with no CHECK, so a generic reason is
   representable at the storage layer even though `failure_class` is closed.
   R0 must enforce the closed recovery set in the **domain type**, and should
   consider an additive CHECK in `0008`.

`recurrence_scope IN ('single', 'occurrence', 'series')` is **not** a blocker for
R5: a `this and following` split is correctly stored as its two component
operations — a `series`-scope trim plus a `create` — not as a fourth scope value.

### Rebuild data directory

All rebuild development, testing, and runtime use a dedicated directory:

```sh
export ION_DATA_DIR="$HOME/Library/Application Support/Ion OS Rebuild"
```

Never point `phase-2c-rebuild` at the owner's normal `Ion OS` data directory.
**No downgrade, deletion, or mutation of the owner's database is performed.**

## References

- [Master Specification](../PRODUCT_SPEC.md) — Calendar authority amendment
- [Calendar interaction behavior](../CALENDAR_BEHAVIOR.md)
- [Phase 2A](PHASE_2A.md) · [Phase 2B](PHASE_2B.md)
- [ADR 0021](../decisions/0021-google-calendar-write-outbox-and-conflicts.md)
- [ADR 0022](../decisions/0022-phase-2c-controlled-rebuild.md)
- [Architecture](../ARCHITECTURE.md) · [Security](../SECURITY.md) ·
  [Integrations](../INTEGRATIONS.md) · [Data model](../DATA_MODEL.md)
