# Calendar Interaction Behavior

## Status

**Accepted owner product rule, and the contract for Calendar work.** This
records how Ion's Calendar should *feel* to use. It is deliberately small: it
documents only the interaction semantics Ion actually implements or
deliberately withholds.

It sits under the [Master Specification](PRODUCT_SPEC.md), whose Calendar
authority amendment (2026-09-01) states the product philosophy this document
applies. **Where the specification's preserved source transcription and this
document disagree about Calendar interaction detail, this document governs**;
where they disagree about product authority or philosophy, the specification's
amendments govern.

**Any change to Calendar interaction behavior must be checked against this
document first**, and must either follow it or extend it in the same pass. A
behavior that contradicts this file without updating it is a defect, not a
preference.

**Implementation status (2026-09-01).** This contract is accepted and binding;
the Phase 2C write implementation that produced it was rejected in owner
acceptance and withdrawn. The Calendar is read-only at the current baseline
while Phase 2C is rebuilt against this document from the accepted Phase 2B
foundation. Every behavior below is therefore a **requirement for that
rebuild**, not a description of shipped code. The withdrawn implementation is
preserved for reference on the `archive/phase-2c-v1` branch; see the
[Phase 2C rebuild plan](phases/PHASE_2C.md) and
[ADR 0022](decisions/0022-phase-2c-controlled-rebuild.md).

## The rule

> Unless an Ion-specific requirement explicitly overrides it, ordinary Calendar
> interaction mechanics follow familiar Google Calendar desktop conventions.

Ion keeps its own visual identity, canonical CalendarBlock model, local-first
architecture, ETag/conflict model, privacy and security boundary, and Ion-only
metadata. Parity is about familiar *interaction semantics*, never about copying
branding, assets, or provider architecture.

Where an Ion requirement genuinely overrides the convention, the override is
recorded in the **Ion overrides** section below so it is a decision rather than
an accident. Anything not listed there is expected to behave the familiar way.

## Direct human action is authorization

> When the owner directly edits, drags, resizes, or deletes an event, or picks
> a recurrence scope, **that action is the authorization.** Ion performs it.

Ion does not ask again because an event is `locked`, because the change reaches
Google, or because the write is consequential.

**`flexibility` governs automation, not the owner.** `locked` / `flexible` /
`Ion-controlled` tell Ion's own scheduler and future AI what they may move on
their own: `flexible` time may be placed and rearranged automatically, and a
`locked` commitment must not be moved autonomously without approval. It is
planning metadata, never a permission boundary between the owner and their own
calendar — and since every synced provider event is `locked` by default,
treating it as one put a gate in front of essentially every real edit.

Approval and review requirements elsewhere in Ion apply to Ion acting on its
own, not to a person acting directly.

**What counts as a direct human action**, all of them self-authorizing: create,
edit and Save, drag, resize, delete, choosing a recurrence scope, Undo, and an
explicit retry the owner presses after a genuine terminal failure.

**After it, nothing asks again.** Persisting, dispatching, reconciling a
provider version, and settling are consequences of the decision, not further
decisions. A direct-human Calendar mutation never requires a second Save, a
second Apply, a provider-version approval, or a manual sync.

The one further interaction Ion may show is the destructive-delete warning
below. That is not a second authorization — the delete is already authorized —
it is Ion telling the truth about what it cannot undo. Nothing else interrupts.

### AI-proposed Calendar changes

Automation has the other authorization model, and only the entry point differs:
Ion's scheduler or a future AI **proposes**, the owner **accepts**, and that
acceptance is the single authorization. Everything after it behaves exactly like
a direct human action — dispatch, provider reconciliation, and settlement happen
automatically, and the owner is never asked again for the same change.

Autonomous Calendar mutation without owner approval is not authorized today.
See the Master Specification's *One authorization step, and only one*.

## Confirmation and reversibility

Confirmation is spent where it buys something. Google does not ask a user to
tick a box before renaming an event, and neither does Ion.

> An interaction warns **only when it removes confirmed occurrences**, because
> that is what Ion cannot truthfully offer to undo — and it warns **once**,
> attached to the decision that causes it.

| Interaction | Confirmation |
| --- | --- |
| Edit, move, resize a single event | none |
| This event | none |
| All events (non-destructive) | none |
| This and following (non-destructive) | none |
| Delete a non-recurring event | one destructive confirmation |
| Delete any recurring scope | none after the scope choice |

**For a recurring delete, choosing the scope is the whole decision.** The
warning about what cannot be recovered lives *inside* the scope dialog, beside
the option that causes it — "Deletes this event and every later one. These may
not be recoverable." Nothing follows it: no second modal, no checkbox, no Apply
step. Asking again after the warning has been read and acted on is asking the
same question twice.

A non-recurring delete has no scope to choose, so its single confirmation is
that same one decision, not an extra one.

A destructive confirmation is a **warning about irreversibility, not an
authorization step**. The owner's delete is already authorized; what the dialog
adds is the fact that Ion cannot truthfully offer to undo it, because a deleted
provider event cannot be restored — recreating one produces a new identity. That
is the only thing that earns a second interaction, and it is why the table above
grants none to any non-destructive action.

**This governs confirmation UX only.** ETag conditioning, the write allowlist,
scope validation, occurrence identity, and every other correctness or security
check are unaffected — removing a checkbox never removes a precondition. Human
authorization and provider-write safety are separate layers: the first decides
whether Ion may act, the second decides how Ion acts safely once it may.

## Successive human edits

The owner may act on the same event again immediately, without waiting for the
previous change to visibly finish. Dragging to 3 PM and then straight to 4 PM,
or saving twice in a row, is ordinary use.

> The newest direct-human intent wins the fields it changes. Background
> settlement catching up is never a reason to interrupt the owner.

A second edit arriving while the first is still settling must not produce a
review task, an Apply step, or a "still syncing" refusal.

**Human interaction and provider dispatch are different concerns.** A newer
mutation is always accepted durably; the provider still gets one serialized
write per target at a time. What happens to the earlier one depends only on
whether it has actually left:

| Earlier write | What happens |
| --- | --- |
| `queued`, `ready`, `retry_wait` — nothing in flight | superseded: retired, so an obsolete position costs no provider round-trip |
| `attempting`, `ambiguous` — in flight or outcome unknown | left alone: the newer intent waits durably behind it, then is released and re-aimed at whatever authority that attempt confirmed |
| already settled | independent |

Ion never cancels an in-flight provider request and never dispatches a parallel
write to the same target. Several rapid actions therefore coalesce naturally to
at most one in-flight write plus one waiting behind it, and the newest human
intent is what eventually reaches Google.

A structural change — a `this and following` split — is never coalesced away,
because it is not simply a newer value for the same fields. It waits its turn
truthfully instead, and the owner is still not refused.

**The Calendar always shows the newest human intent**, never an obsolete
intermediate value. When an earlier write confirms, the display does not flick
back through it: the newer intent is still pending, so its value keeps
projecting until it settles in turn.

## Recurring events

### Scope is target selection, not approval

The chooser answers one question — **which events does the owner intend to
change?** — and nothing else.

It is not a permission gate, a safety acknowledgement, a confirmation, or a
provider-conflict resolution. Picking a scope completes the description of the
action; it does not authorize it a second time, and nothing further may be asked
once it is picked.

### The scope chooser is a modal

Choosing a scope interrupts an interaction the user has already committed to,
so it is a real modal: centered over the window, with the surface underneath
covered and inert, focus moved into the dialog and trapped there, and focus
returned to whatever opened it. Escape and the backdrop both mean Cancel, and
Cancel mutates nothing.

### Scope is chosen after the change is described

Google asks *what* changed first and *how far it applies* second. Ion follows
that order for every recurring interaction:

| Interaction | Flow |
| --- | --- |
| Inspector edit | edit fields → **Save** → scope chooser → write |
| Drag | drag → **drop** → scope chooser → write |
| Resize | resize → **release** → scope chooser → write |
| Delete | **Delete** → scope chooser (carrying the warning) → write |

For a non-recurring event there is no chooser, so a drop or release *is* the
write. Scope is the last normal decision in every flow; nothing is asked after
it.

No canonical or provider mutation happens before a scope is chosen.
**Cancel from the chooser mutates nothing** — no outbox row, no local edit, no
Google request.

One shared typed scope model backs all four surfaces
(`CalendarRecurrenceScope`), so scope semantics are never redefined per
surface.

**Direct manipulation commits at drop.** A drag or resize is a complete
statement of intent, so it commits when the pointer is released, exactly as
Google's does. The gesture previews while in flight and writes nothing until
release; a recurring event then asks for scope, because scope is the one thing
the gesture could not express. There is no review step and no second Save.

*(This replaces an earlier Ion override that required an explicit save review
after every gesture. It was removed in owner acceptance: it made the most
direct interaction in the product the slowest, and left users unsure whether
their change had taken.)*

### Supported scopes

- **This event** — resolves the exact occurrence through its master plus its
  immutable original start, and writes one provider exception. A moved
  occurrence keeps its original-start identity. Sibling occurrences are
  unaffected.
- **All events** — targets the confirmed recurring master conditionally on its
  ETag. A whole-series *edit* is reversible and asks for no acknowledgement;
  whole-series *deletion* requires a blocking confirmation.

Changing how often an event repeats is inherently series-wide, as it is in
Google, so the chooser offers only **All events** for a repeat-rule change.

### “This and following events”

Google implements this as a **series split**, not a batch of per-occurrence
exceptions: the original master is trimmed to end immediately before the target
occurrence, and a new recurring master begins at that occurrence.

Ion implements the same semantics. The old master is trimmed conditionally on
its confirmed ETag, and only once Google confirms that trim is the new master
created, with a deterministic identity fixed before any dispatch so a retry or
restart can never produce a duplicate future series. Both operations and the new
canonical master are durable before Ion contacts Google at all.

Ion offers the scope only where it can faithfully continue the series: one of
the five supported preset families. A series using a recurrence pattern Ion
cannot express is left alone and the option is withheld with a plain
explanation, never approximated or destructively rewritten.

Because a split is two provider operations, Ion never claims success until both
are confirmed. If the trim succeeds and the new series has not been created yet,
Ion says so plainly and keeps the intended future series locally rather than
silently discarding it or silently restoring the old series.

Deleting “this and following” is the trim alone — the desired future state is
absence, so no new series is created and no future occurrence is deleted
individually.

### First-occurrence edge

When the selected occurrence is the first in a series, “this and following” is
semantically identical to “all events” — it would leave an empty old series — so
Ion omits the option there, as Google does, and performs no split.

An explicit exception overrides exactly one generated occurrence, identified by
its immutable original start. After a confirmed whole-series change re-anchors
the rule, an older exception can be left pointing at a slot the confirmed rule
no longer produces — Google resets instance exceptions in that case. Ion treats
such a row as a stale local override awaiting read-sync reconciliation: it
neither suppresses a generated occurrence nor renders itself at its old time.
The value shown in the grid and the base the Inspector edits against therefore
always describe the same confirmed state.

## Automatic convergence (supersedes the original conflict policy)

> Ordinary supported Calendar use converges automatically in both directions.
> Neither direction is a workflow the user operates.

**This supersedes ADR 0021's rule that every ETag mismatch requires explicit
human resolution.** That rule was accepted before the product was used, and in
real use it turned every ordinary edit into a review task: an edit met a moved
ETag, became "needs review", and Apply my Ion changes met the next moved ETag,
so the owner learned to press Apply repeatedly and hope. Ordinary drift is now
an internal event.

### Ion → Google

A direct-human change commits locally, dispatches automatically, and settles
automatically. Nothing is required after the action itself.

### Google → Ion

Ion runs the existing bounded incremental sync while the Calendar is on screen —
when it opens, when it becomes visible again, and then on a slow interval —
backing off on failure and stopping entirely while hidden. A change made in
Google appears in Ion on its own. **Sync Now is an explicit refresh, never a
step in normal use.**

### Field ownership

> While a direct-human Ion intent is unsettled, that intent owns **only the
> provider fields the user explicitly changed**. Freshly fetched Google state
> owns every other provider field. Ion-only metadata stays Ion-owned.
>
> Once the intent is provider-confirmed, that ownership ends, and later Google
> changes are authoritative and flow into Ion normally.

This is deliberately **not** last-write-wins, and timestamps are never
authority. It falls out of the existing narrow model rather than any new merge
rule: a provider body carries only `changed_fields`, so Google's edits to other
fields are never overwritten, and the projection overlays exactly those same
fields so the Calendar shows the user's intent while it settles.

### Automatic ETag rebase

An ordinary write that meets a stale precondition re-reads confirmed provider
state, re-aims at that fresh ETag, and retries — bounded by the same automatic
attempt budget as any other retry. A background refresh that discovers newer
state re-aims a pending write the same way instead of conflicting it.

Base ETag `A`, Ion changes the time, Google changes the location:

| Field | Result | Owner |
| --- | --- | --- |
| title | unchanged | Google |
| time | Ion's new value | pending Ion intent |
| location | Google's new value | Google |

Same-field concurrency resolves the same way: the pending direct-human value
wins **that settlement cycle**, because it is the change a person just made and
is still waiting on. It is not a standing preference for Ion — as soon as the
intent confirms, the next Google edit to that field is adopted normally.

Ion never sends `If-Match: *`, and a rebase always uses freshly confirmed
provider authority.

### Occurrence writes carry two pieces of provider authority

A `This event` write targets an instance but preflights against its **master**,
so it embeds the master's ETag alongside the instance's. Both are ordinary
concurrency: when resolution fetches the live master and finds a newer version,
Ion adopts it — and aligns the confirmed link — rather than refusing.

Treating that as an identity failure is the specific defect that produced a
permanent review loop in owner acceptance. Because it failed before any attempt
was recorded, it consumed no part of the retry budget, so every retry and every
`Apply my Ion changes` re-derived the same stale identity and failed the same
way. **Structural identity — same master event, still recurring, still writable
— is what may legitimately fail here. A version difference is not.**

### There are no rows from the superseded policy

The rebuild starts from a schema with no provider-write outbox, so it inherits
no conflict rows created by the old "every mismatch needs review" policy. The
new write store must be designed so that such a row is not representable:
ordinary drift has no durable state that could later be escalated to a person.

### There is no generic conflict decision

Ion does not have a "your version or Google's version" surface, and the domain
has no unclassified outcome that could produce one.

> Every condition a person must settle is **named specifically**, and offers
> only actions that are truthful for that exact condition.

The projection carries one field for this — a closed set of specific kinds, with
deliberately no generic member. Ordinary provider version drift never populates
it, because Ion resolves that itself. An outcome matching nothing in the set is
not a decision handed to the owner; it is Ion's to finish.

That closed set is the architectural guarantee. The previous model let any
provider disagreement fall through into a generic review task, which is why
ordinary drift kept reaching the owner no matter how many individual routes were
repaired. Recovery must also never *manufacture* one: re-arming an intent for
another automatic attempt is correct, escalating it to a human is not.

### What still needs a person

Exhausting the rebase budget means Google kept changing the event faster than
Ion could land the write. That is not a disagreement about facts, so it does not
borrow the language of one: the event says **Not saved yet** and offers a single
**Try again**, not a choice between two versions.

Beyond that, some contradictions cannot be merged truthfully and keep an
explicit, *specific* recovery surface — never the generic chooser:

- Google deleted the event while an Ion edit was pending
- write permission was downgraded
- the recurrence identity no longer resolves
- the event became an unsupported provider structure
- reauthentication is required
- Google rejected the change terminally

These name the actual condition and offer only actions that are truthful for
it. The goal is no routine conflict management — not hiding real contradictions.

## The write machinery is not the workflow

The outbox exists so a change survives a crash, a bad network, and a restart.
It is not something the user operates.

> A healthy Calendar action requires exactly one human decision sequence and no
> recovery controls. Ion finishes the rest by itself.

Internal states — `queued`, `ready`, `attempting`, `retry_wait`, provider
confirmation, reconciliation — are implementation detail. They self-progress:

- A local write **dispatches automatically** as part of the action that created
  it. The user never triggers dispatch.
- A write left waiting on a retry backoff **wakes itself** once, when it is
  actually due, and the resulting dispatch schedules the next wake if anything
  still remains. This is a bounded self-wake, never a poll: a healthy Calendar
  schedules nothing.
- When Ion advances a write on its own, it **announces the settled state** so
  the projection updates without the user asking.

### Sync Now is never required

**Sync Now is a manual refresh and a troubleshooting tool. It must never be
necessary to make a human mutation take effect.** If an ordinary write only
progresses once Sync Now is pressed, that is a lifecycle defect in the
dispatcher, not something to document or explain to the user.

### There is no version chooser at all

**Keep Google's version / Review differences / Apply my Ion changes are
withdrawn, not narrowed.** Owner acceptance reached them repeatedly during
ordinary editing, and each individual route repaired was followed by another,
because a surface that exists can be reached. The rebuild does not implement
them in any form — not as a last resort, not behind a rare state, not as dead
code.

The replacement is the closed set above. Where the old model would have offered
a choice between two versions, the rebuild either resolves the drift itself or
names the specific condition and offers only actions that are truthful for it —
`Try again`, `Discard my change`, `Reconnect Google`. A comparison of an Ion
version against a Google version is never one of them.

If a future condition genuinely cannot be expressed that way, the answer is a
new named member of the closed set, recorded here first — never a generic
chooser reintroduced by the back door.

## Feedback

**The Calendar itself is the primary confirmation.** A moved event appears at
its new position as soon as the intent is durable; that is what tells the user
it worked.

Text is therefore lightweight and secondary — `Event moved`, `Event updated`,
`Event moved · saving…` — and pairs with Undo for reversible actions. Longer
copy is reserved for states where the user actually has something to decide.
When everything is healthy, provider confirmation settles silently.

Status and diagnostics follow progressive disclosure: the Calendar and a small
save state during normal use; an actionable message when something needs a
decision; provider, account, and write diagnostics on demand. Nothing about the
routine surface should imply that manual sync or recovery is part of using the
Calendar.

## Undo

A confirmed edit is offered back as **Undo**, next to the confirmation it
reverses. Undo is not a hidden rollback or an event-sourced history: it is the
same ordinary write aimed at the values the edit replaced, conditional on the
revision that edit produced, and it is visible and auditable like any other
change.

It follows from that honestly:

- Undo is offered only once the write has settled into a block Ion can aim at.
  There is no Undo for a change with no confirmed target.
- Undo keeps the original scope and occurrence identity, so undoing a
  `this event` edit rewrites that occurrence, not the series.
- A **repeat-rule** change is not undoable this way. The rule is restated only
  in the forward change, so reversing it is a new deliberate choice, and Ion
  asks for it rather than implying a symmetric undo.
- Undo is offered once per change, not as a repeatable toggle.

**Scope.** This is Calendar-specific and deliberately narrow. It is not a
general application undo stack, and it does not introduce event sourcing.

## Recurrence termination (owner decision, 2026-09-01)

Google offers *Never* / *On date* / *After N occurrences* when editing how an
event repeats. Ion offers the five preset families with no user-facing
terminator, so a series a person creates in Ion does not end.

Termination is split deliberately into a mechanism Ion needs internally and a
capability the owner has not yet asked for.

### In scope for 2C-R5: a domain-generated `UNTIL`, and nothing else

A `this and following` split trims the old master to end immediately before the
target occurrence. That trim **is** a terminator, so R5 must generate one. It is
admitted under exactly these bounds:

- **Trusted and domain-generated.** Derived only from the persisted preset, the
  selected occurrence's immutable original start, and the block's own
  timezone/all-day semantics — `YYYYMMDD` for an all-day series, basic UTC
  `YYYYMMDDTHHMMSSZ` for a timed one.
- **Never renderer authority.** The renderer submits a closed scope action plus
  trusted Ion identifiers. It cannot supply recurrence text, a `FREQ`, a `BY*`
  clause, a terminator value, or a raw RRULE.
- **Re-validated before dispatch.** Rust checks the full constructed rule
  against the preset allowlist independently of the domain.
- **No new provider method and no new OAuth scope.** A split is an
  `events.patch` trim followed by an `events.insert`.

### Explicitly out of scope for 2C-R5

- a user-configurable recurrence end date
- a *Never* / *On date* / *After N occurrences* control of any kind
- **`COUNT`** — excluded entirely, in the contract and in the validator
- arbitrary or custom RRULE editing
- broader recurrence normalization

User-facing recurrence-ending options are a **later bounded Calendar
capability**, considered only after Phase 2C v2 is stable. Implementing them
will still need the narrow contract extension below, because Ion's recurrence
classifier matches preset rules by exact equality: a rule carrying `UNTIL` or
`COUNT` classifies as `custom` and therefore becomes non-writable. That future
work would need to recognise *preset + terminator* as a supported family in the
classifier, accept a bounded domain-generated terminator on the write contract
with the renderer still choosing only from fixed options, and render the
terminator in the recurrence summary so a series that ends looks different from
one that does not.

Because R5's split already constructs a valid `UNTIL`, the missing piece for
that future capability is classification and contract, not rule construction.

## Ion overrides

The complete list of places Ion deliberately departs from the familiar
convention. Anything not here should behave the familiar way.

- **Scopes are withheld rather than approximated.** Where Ion cannot faithfully
  perform a scope — a recurrence pattern it cannot continue, a split at the
  first occurrence — it withholds the option and says why, instead of
  substituting a different operation.
- **A split is never claimed complete until both operations confirm.** Google
  presents the split as atomic; Ion reports the true intermediate state.

## Every offered interaction must survive every layer

A scope or operation the chooser can offer must be accepted by *all* of the
layers it crosses: renderer draft → Tauri command validation → local API
contract → domain → provider dispatch. Each layer independently validates
shape, so a value added to one and missed in another is refused with a generic
error while looking correct in every isolated test.

This is not hypothetical. `this and following` was implemented end to end in
the domain, with passing tests, while the Tauri command's scope allowlist still
read `single | occurrence | series`. Every real attempt failed as
`local_state_invalid` and surfaced as "This calendar change couldn't be saved" —
green domain tests, broken product.

**When adding a scope, operation, or safe reason, grep every layer's allowlist
for the neighbouring values and update them together**, and cover the seam, not
just the domain.

## Errors say what happened

A refusal names its cause in the user's terms. Generic fallback copy is for
genuinely unclassified failures only — every safe reason Ion can produce is
expected to have specific copy and to be carried through the safe-reason
allowlists rather than flattened into the fallback.

## Truthfulness

Unsupported provider capabilities are represented truthfully rather than
simulated. Ion does not present an action it cannot perform safely, and does not
substitute a different provider operation behind a familiar label.

## References

- [Design system](DESIGN_SYSTEM.md) — the owner rule and Ion's visual identity.
- [Phase 2C rebuild plan](phases/PHASE_2C.md) — the subphase sequence and the
  acceptance discipline that gates each one.
- [ADR 0021](decisions/0021-google-calendar-write-outbox-and-conflicts.md) —
  the durable provider-write safety boundary: outbox, exact ETag conditioning,
  deterministic identity, and the narrow request allowlist.
- [ADR 0022](decisions/0022-phase-2c-controlled-rebuild.md) — why the first
  Phase 2C implementation was withdrawn and what the rebuild may not carry
  forward.
