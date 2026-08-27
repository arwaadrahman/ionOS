# Design System Baseline

## Status: Baseline; implementation deferred

The future `packages/ion-design` package owns semantic color tokens,
typography, spacing, reusable primitives, interaction patterns, and
accessibility/motion rules. The package is not created in Phase 0A.

## Durable direction

- Dark-first foundation: near-black, neutral-dominant operational surfaces with
  restrained electric-violet emphasis.
- Premium technical/editorial tone, strong readable typography, and limited,
  purposeful glass effects.
- The future Ion Core is a signature identity and data lens, not decoration on
  every screen. Its advanced production renderer is deferred.
- A third-party component library must never determine Ion's identity.

## Motion ownership ladder

1. `IMPECCABLE` is process guidance for hierarchy, accessibility, and polish.
2. `EMIL-MOTION` is process guidance for justified motion and feel review.
3. CSS is the default for simple predetermined motion.
4. Motion for React is the future owner for normal stateful React UI motion.
5. Three.js is the future owner for a justified spatial Ion Core.

All motion must serve feedback, continuity, state explanation, comprehension,
or rare delight; support reduced motion; and respect performance and visibility
constraints. The listed tools are guidance/future owners, not installed
dependencies.
