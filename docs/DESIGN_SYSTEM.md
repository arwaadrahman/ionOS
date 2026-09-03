# Design System Baseline

## Status: Baseline with implemented Phase 1 and Phase 2B product surfaces

The future `packages/ion-design` package owns semantic color tokens,
typography, spacing, reusable primitives, interaction patterns, and
accessibility/motion rules.

The package is not yet implemented as a standalone design-system package.

## Durable direction

- Dark-first foundation: near-black, neutral-dominant operational surfaces with
  restrained electric-violet emphasis.

- Premium technical/editorial tone, strong readable typography, and limited,
  purposeful glass effects.

- Familiar mechanics, distinctive identity. Where established user expectations
  exist for common desktop interactions, Ion should follow familiar conventions
  unless there is a clear usability reason to diverge. Ion's distinctiveness
  should come primarily from information hierarchy, contextual intelligence,
  restrained visual language, semantic color, purposeful motion, and the Ion
  Core rather than unnecessary reinvention of common controls.

- **Google Calendar behavioral default (owner rule).** Unless the owner has
  explicitly specified different behavior, ordinary Calendar interaction
  mechanics follow Google Calendar conventions as closely as possible while
  preserving Ion's visual identity, local-first architecture, security model,
  and currently supported provider semantics. This applies especially to
  recurring-event scope choice, edit confirmation behavior, move/resize
  expectations, destructive confirmation, and overall interaction flow. Where
  Google offers an option Ion cannot yet support safely, Ion exposes only its
  currently supported safe choices and never simulates the unsupported one.
  The supported recurrence scopes are **This event**, **This and following
  events**, and **All events**, chosen after the change is described. `This and
  following` performs a real series split and is offered only where Ion can
  faithfully continue the pattern; where it cannot, the option is withheld with
  a plain explanation rather than faked. The durable interaction contract lives
  in [Calendar interaction behavior](CALENDAR_BEHAVIOR.md).

- Progressive disclosure is preferred over permanently visible secondary
  controls. Frequently used information and actions remain immediately
  accessible; configuration, provider state, metadata, and infrequent controls
  should appear on demand.

- Useful information takes priority over decorative or redundant chrome.
  Interfaces should maximize the space available for the user's actual content
  while preserving visual balance and clear hierarchy.

- Responsive desktop layouts must degrade gracefully across large, split-screen,
  and narrower supported macOS window sizes. Primary controls and meaningful
  content must not clip. When space becomes constrained, prefer shortening
  labels, familiar icons, hiding secondary text, overflow menus, deliberate
  wrapping, and collapsible secondary panels rather than unreadably shrinking
  the interface.

- Control geometry should be visually consistent. Buttons, segmented controls,
  selects, icon buttons, panels, and related surfaces should use deliberate,
  shared radius, height, spacing, and padding rules rather than accidental
  one-off styling.

- Color should communicate semantic structure without becoming a rainbow.
  Related concepts should share color families, while subtype or state may be
  distinguished through restrained differences in shade, brightness, fill,
  border, or accent intensity.

- Color must never be the sole carrier of meaning. Accessible text, labels,
  structure, or disclosure must remain available where semantic distinction
  matters.

- The future Ion Core is a signature identity and data lens, not decoration on
  every screen. Its advanced production renderer is deferred.

- A third-party component library must never determine Ion's identity.

## Calendar interface direction

- Calendar event colors express Ion-owned semantic category rather than Google
  account identity.

- Broad categories own restrained color families. Subtypes may vary shade,
  tonal fill, brightness, border strength, or accent intensity within the same
  family so related event types remain visually connected without becoming
  indistinguishable.

- Source account and calendar remain available as secondary metadata in
  management and inspector surfaces, but should not dominate event appearance.

- Calendar event blocks are title-first. Short or narrow cards show the title
  only. Time appears only when space permits. Location, provider source,
  category labels, and other secondary metadata belong in the inspector rather
  than competing with the event title inside the grid.

- Calendar density is owner-selectable across compact, default, and expanded
  hour-row treatments and changes vertical spacing only. Calendar content
  adapts to the usable pane width instead of exposing independent zoom or
  horizontal day navigation.

- Responsive Calendar view choice is container-owned: wide canvases recommend
  Week, medium canvases 3 Day, and narrow canvases Day. Manual view choice is
  respected within a stable width class; a major class crossing may restore the
  readable recommendation and close secondary drawers.

- Calendar controls should use progressive disclosure. Calendar/source
  management and category filters share one secondary drawer region; provider
  status and infrequent controls should not permanently consume primary canvas
  space. Safe routine sync remains compact beside date navigation.

- Calendar layouts should remain balanced and symmetric across supported macOS
  window sizes. Toolbars may compact labels, use familiar icons, move secondary
  actions into overflow, wrap deliberately, or collapse management surfaces,
  but should not clip primary controls.

- Month view should remain scan-friendly rather than becoming a dense agenda
  dump. Overflow should be disclosed cleanly, with full detail available through
  interaction.

- Event details remain keyboard-focusable and accessible through one
  inspector. Ion-owned presentation metadata is editable locally where
  explicitly supported. Google events are read-only at the current baseline
  while Phase 2C is rebuilt.

- **Design requirements for the Phase 2C rebuild.** A gesture previews while in
  flight and commits at drop, with no review step; a recurring event asks for
  scope at that moment through one shared centered, focus-trapped modal chooser
  (This event / This and following events / All events) rather than a control
  inside each surface, matching Google's order. Confirmation is reserved for
  interactions that remove confirmed occurrences; ordinary edits — including
  non-destructive whole-series and this-and-following changes — commit
  immediately and are offered back as Undo, so reversibility is demonstrated
  rather than asserted through a checkbox. The selected occurrence carries a
  restrained ring that is a shape change, not only a hue change, so it is never
  confused with a category color. Raw RRULE entry remains intentionally absent.

- **Write lifecycle is not a design surface.** Pending, syncing, retry, and
  provider-confirmation state must not appear on ordinary Calendar events or as
  a global provider banner during normal use. The Calendar itself is the
  confirmation; text is lightweight and secondary. Only a named condition the
  owner must actually settle earns explicit copy. See
  [Calendar interaction behavior](CALENDAR_BEHAVIOR.md).

## Motion ownership ladder

1. `IMPECCABLE` is process guidance for hierarchy, accessibility, and polish.
2. `EMIL-MOTION` is process guidance for justified motion and feel review.
3. CSS is the default for simple predetermined motion.
4. Motion for React is the future owner for normal stateful React UI motion.
5. Three.js is the future owner for a justified spatial Ion Core.

All motion must serve feedback, continuity, state explanation, comprehension,
or rare delight; support reduced motion; and respect performance and visibility
constraints.

The listed tools are guidance/future owners, not installed dependencies.

## Deferred holistic polish requirements

These notes are accepted future polish direction, not implementation work for
the phase that owns the surface today. Their numbered home is **Phase 14 —
Final UI/UX Overhaul & Visual Cohesion**; see the
[roadmap amendment](PRODUCT_SPEC.md#owner-approved-roadmap-amendment--2026-09-02).

Earlier phases still owe functional, usable, accessible, responsive,
design-system-conformant surfaces, and fix anything that materially harms
usability rather than deferring it.

- Calendar navigation arrows are functionally accepted. A later polish pass
  should improve their symmetry, geometry, stroke/weight, hit area, spacing,
  and perceived craftsmanship to the standard expected of mature desktop
  calendar interfaces without copying Apple or Google branding.
- Ion's current interaction structure is broadly acceptable. A holistic pass
  should refine spacing, alignment, shared control geometry, icon consistency,
  typography, responsive hierarchy, interaction states, and perceived
  craftsmanship while preserving **Familiar mechanics, distinctive identity.**
- Narrow Calendar and Day layouts should preserve readable primary typography.
  Use available horizontal space, reflow or reposition secondary information,
  and simplify chrome before mechanically shrinking all type merely because
  the application reaches its minimum width.
