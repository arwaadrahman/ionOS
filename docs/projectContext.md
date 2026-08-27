# Project Context

## Goal and audience

Ion is a private, local-first personal operating system for a primary user who
wants less administrative overhead without surrendering control. It captures,
connects, plans, and reviews life information while treating direct human
actions as authoritative.

## Current development state

- **Phase:** Phase 0 — Repository + Engineering Foundation
- **Milestone:** Phase 0A — documentation and governance bootstrap
- **In scope:** canonical documentation migration, local context, agent
  routing, ADR bootstrap, reference snapshot, and public-repository safety.
- **Out of scope:** executable Tauri/React, Python/FastAPI, and SQLite work;
  lint/test installation; settings/logging runtime; integrations; AI; a
  production Ion Core; CI, deployment, and personal data.

## Proposed stack baseline — subject to prototyping

- React + TypeScript; Tauri desktop shell; Python + FastAPI application logic.
- SQLite for structured records; an Obsidian-compatible local Markdown layer
  for durable prose knowledge.
- This baseline is not an accepted choice of ORM, workspace manager, Python
  packaging, service lifecycle, process supervisor, migration tool, or test
  stack.

## Durable ownership boundaries

| Owner | Responsibility |
| --- | --- |
| SQLite | Canonical structured records |
| Markdown | Durable prose knowledge |
| Original source files | Immutable evidence |
| Search, indexes, vectors, caches | Rebuildable derived data |
| AI/LLM | Temporary reasoning context; never canonical memory |

## Product character

`PROFILE-ION` is a calm operational system with one unmistakable future Core:
dark-first, near-black and neutral-dominant, with restrained violet energy and
a premium technical/editorial tone. The advanced Core renderer is not Phase 0A
scope.

Design/motion ladder: process guidance (`IMPECCABLE`, `EMIL-MOTION`); CSS for
simple motion; Motion for React for normal stateful UI; Three.js only for a
justified spatial Core. These are future owners/guidance, not current runtime
dependencies. Motion must be purposeful, reduced-motion-aware, and
performance-conscious.

## Non-negotiables and approval gates

- Repository data is synthetic only; real databases, vaults, and secrets stay
  outside the repository.
- No agent silently changes major architecture, dependencies, security/privacy,
  data ownership, authentication, authorization, or canonical requirements.
- Destructive actions, publication, and external side effects require approval.
- Current phase boundaries are binding.

## Canonical documents

- [Master Specification](PRODUCT_SPEC.md)
- [Research playbook](research/ionResearch.md)
- [Task router](agent/taskRouter.md)
- [Approved Ion reference snapshot](references/approvedReferences.md)
- [Decision index](decisions/README.md)
- [Active phase](phases/PHASE_0A.md)

The approved-reference snapshot derives from `projectReference.md` version
**1.1.0** (updated 2026-08-27). Project-local decisions override it.
