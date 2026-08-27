# Phase 0A — Documentation and Governance Bootstrap

## Objective

Establish repository governance, canonical-document migration, lightweight
project context, agent routing, ADR bootstrap, and a privacy-safe engineering
foundation. This does not build the executable Ion application.

## Source inputs and permanent owners

| Bootstrap source | Permanent repository owner |
| --- | --- |
| Ion Master Specification | `docs/PRODUCT_SPEC.md` |
| Ion research playbook | `docs/research/ionResearch.md` |
| Task router | `docs/agent/taskRouter.md` |
| Project reference catalog | `docs/references/approvedReferences.md` (Ion-only snapshot) |

Permanent documents must remain self-contained; no permanent link relies on
temporary bootstrap inputs.

## Deliverables

Root governance files, the canonical/research/router documents, project
context, architecture/data/security/AI/design/integration baselines, the
approved-reference snapshot, ADR system and three initial ADRs are all listed
in the repository root and `docs/` tree.

## Explicit exclusions

- Tauri/React, Python/FastAPI, and SQLite executable work.
- Lint/test tooling, runtime settings/logging, design-package implementation,
  integrations, AI, production Ion Core, CI, deployment, and personal data.

## Acceptance checklist

- [x] Canonical, research, and routing sources have permanent repository homes.
- [x] Source hierarchy, active phase, privacy requirements, and approval gates
      are explicit.
- [x] Future agents have a concise entry point and deterministic routing path.
- [x] Proposed stack choices are labeled subject to prototyping.
- [x] Open engineering choices are in the decision backlog rather than silently
      decided.
- [x] No executable application, dependency, integration, AI runtime, or real
      user data is introduced.

## Unresolved decisions

See the [decision backlog](../decisions/README.md#decision-backlog).

## Handoff to Phase 0B

Phase 0A is complete once repository knowledge is self-contained, source
hierarchy and privacy boundaries are explicit, agents can route correctly, and
open choices remain visible. Phase 0B may choose and scaffold the Tauri + React
+ TypeScript workspace, Python service, SQLite foundation, linting, formatting,
tests, and local developer workflow. It is not implemented here.
