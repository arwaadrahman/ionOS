# Ion OS Agent Guide

1. Read `docs/projectContext.md` first, then classify the task with
   `docs/agent/taskRouter.md`.
2. Before substantial work, declare route, `PROFILE-ION`, read scope,
   authority, excluded scope, and verification.
3. Read the full [Master Specification](docs/PRODUCT_SPEC.md) when starting or
   revising a phase, changing architecture, or making broad product or
   engineering recommendations. Otherwise, read only the relevant project
   slices and named reference cards.
4. Precedence is: current request; Master Specification; accepted ADRs; local
   implementation context; research; router; approved references; external
   sources. Do not silently resolve a conflict.
5. Remain within the active phase and milestone. Owner approval is required
   for major architecture, dependency, security/privacy, destructive, or
   canonical-specification changes.
6. Never commit real personal data or secrets. Repository fixtures, tests,
   screenshots, prompts, and documentation use synthetic data only. Preserve
   human authority over consequential automated actions.
7. Update relevant tests and documentation with behavior changes, record
   lasting accepted decisions as ADRs, run appropriate verification, and report
   changed files, decisions, unresolved issues, verification, and manual checks.
