# Project Context

## Goal and audience

Ion is a private, local-first personal operating system for a primary user who
wants less administrative overhead without surrendering control. It captures,
connects, plans, and reviews life information while treating direct human
actions as authoritative.

## Current development state

- **Phase:** Phase 1 — Ion Core Personal Organizer
- **Milestone:** Phase 1A — Core Organizer Domain & First Vertical Slice
- **In scope:** canonical organizer schema, local Task vertical slice,
  transactional audit metadata, soft Trash, and the inherited secure runtime.
- **Out of scope:** integrations, AI, scheduling, Calendar, full Home/Today,
  search UI, mobile, remote/LAN access, and a production Ion Core.

## Proposed stack baseline — subject to prototyping

- React + TypeScript in Tauri, npm workspaces, and Node 24 LTS.
- Python 3.13 managed with uv; FastAPI binds to loopback only during
  development.
- SQLite with SQLAlchemy 2 Core and Alembic; Markdown remains the future owner
  for durable prose knowledge.
- Production sidecar lifecycle and per-launch local-process authentication are
  governed by ADRs 0008 and 0009. Signing/notarization remain deferred.

## Durable ownership boundaries

| Owner                            | Responsibility                                      |
| -------------------------------- | --------------------------------------------------- |
| SQLite                           | Canonical structured records                        |
| Markdown                         | Durable prose knowledge                             |
| Original source files            | Immutable evidence                                  |
| Search, indexes, vectors, caches | Rebuildable derived data                            |
| AI/LLM                           | Temporary reasoning context; never canonical memory |

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
- The active trust boundary is macOS-local only. Mobile support is deferred
  pending a dedicated mobile/security review and explicit owner approval.
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
- [Active phase](phases/PHASE_1A.md)

The approved-reference snapshot derives from `projectReference.md` version
**1.1.0** (updated 2026-08-27). Project-local decisions override it.
