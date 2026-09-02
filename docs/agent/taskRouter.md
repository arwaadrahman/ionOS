# Task Router

**Version:** 1.1.1
**Updated:** 2026-08-28
**Purpose:** Load the minimum correct context for a project task
**Catalog:** `projectReference.md`

## 0. Start here

This is the normal entry point. Do **not** read the full cross-project catalog or a large product specification for every small task.

For each task:

1. read the repository's `AGENTS.md`, project-local context, and
   `docs/agent/executionPolicy.md`;
2. classify the task using the route table;
3. load only the required project documents and named catalog cards;
4. state the selected route and `read_scope` in the working plan;
5. implement only within the task's authorization boundary;
6. verify using the route's acceptance evidence;
7. write accepted lasting decisions back to project-local docs or an ADR.

Project-local specifications and decisions override this router and the universal catalog.

## 1. Context tiers

| Tier | Typical content | When to load | Rough target |
| --- | --- | --- | --- |
| 0 — Bootstrap | `AGENTS.md`, current request, route row | Every task | A few hundred tokens |
| 1 — Project slice | Relevant section of `projectContext.md`, design system, architecture doc, or ADR | Every implementation/review task | Usually under 1,500 tokens |
| 2 — Resource cards | Only stable IDs named by the route | When an external pattern/tool may help | One to three cards |
| 3 — Canonical deep context | Full product specification, large research report, external docs/source | Phase planning, architecture, security, unfamiliar API, or explicit request | Load deliberately |

For Ion, read the entire Master Specification when beginning a phase, changing architecture, or making broad recommendations. Routine scoped work should use accepted derived docs/ADRs unless the route or `AGENTS.md` requires the full specification again.

`docs/PRODUCT_SPEC.md` is Ion's only Master Specification, and its appended owner amendments supersede its preserved source transcription. Untracked bootstrap or transcription artifacts outside `docs/` are historical inputs, not authority.

## 2. Route table

### Product, architecture, and agents

| Route | Trigger | Required project context | Catalog `read_scope` | Default output |
| --- | --- | --- | --- | --- |
| `ROUTE-ARCH` | New subsystem, data ownership, boundary, runtime, major dependency | Canonical spec, architecture docs, relevant ADRs | `MANUS` only if agent architecture is involved | Options, tradeoffs, recommendation, ADR proposal; no silent architecture change |
| `ROUTE-PHASE` | Start or revise a project phase/milestone | Full phase specification and current status | Only cards directly named by phase requirements | Milestones, acceptance criteria, agent prompt, explicit exclusions |
| `ROUTE-AGENT` | Task routing, skills, context loading, long-running agent behavior | Agent rules, execution policy, data/security model, authorization policy | `MANUS`, applicable process card | Deterministic route, data scope, authority, output schema, audit/failure behavior |
| `ROUTE-DEPENDENCY` | Add or replace a major package/tool | Stack docs, lockfile/package manifest, relevant ADR | Proposed resource card | Need, overlap, license, maintenance, size/runtime cost, security, removal plan; approval before addition |
| `ROUTE-REFERENCE-UPDATE` | Add, amend, verify, supersede, deprecate, retire, or rename a cross-project resource | Current `projectReference.md`, relevant route rows, known project selections if affected | Target cards plus their proposed replacements | Change classification, current-source verification, conflict/impact summary, coordinated versioned update and changelog |
| `ROUTE-LEARNING` | Understand a subsystem by building a small version | Learning goal and production boundary | `BUILD-YOUR-OWN-X` | Isolated spike plan and lessons; no automatic production adoption |

### Application UI and design

| Route | Trigger | Required project context | Catalog `read_scope` | Default output |
| --- | --- | --- | --- | --- |
| `ROUTE-UI-OPERATE` | Dashboard, form, settings, navigation, repeated workflow | Project profile, design tokens, surface requirements | `IMPECCABLE`; `MOTION` only if state continuity needs it | Restrained usable UI; no decorative library browsing by default |
| `ROUTE-HERO` | Homepage/project/case-study opening | Audience, page goal, content hierarchy, design system | `SUPAHERO`, then at most one of `RB-COLORBENDS`/`RB-AURORA`, plus `EMIL-MOTION` | Up to three options, one recommendation, dependency/fallback implications; approval before implementation |
| `ROUTE-CTA` | Contact, project-view, demo/source, résumé, signup, next step | User decision and page context | `CTA-GALLERY`, `IMPECCABLE` | CTA hierarchy and copy/function proposal; no conversion pattern without a real action |
| `ROUTE-FOOTER` | Site ending, missing navigation/contact/closure | Site information architecture and existing header/nav | `FOOTER-DESIGN`, `IMPECCABLE` | Desktop/mobile footer proposal with real links/content and accessibility |
| `ROUTE-COMPONENT` | Need a compact interaction pattern | Existing component system and exact user need | `KOKONUT`; `MOTION` if necessary | Inspect one candidate, retokenize, identify imports/license, avoid unrelated blocks |
| `ROUTE-DESIGN-AUDIT` | Polish, critique, improve hierarchy or accessibility | Current surface and accepted design system | `IMPECCABLE`; `TASTE` only for an explicitly experimental pass | Evidence-based findings ordered by impact; preserve accepted identity |
| `ROUTE-CALENDAR-BEHAVIOR` | Any change to Calendar interaction behavior — editing, moving, resizing, deleting, recurrence scope, confirmation, synchronization/convergence, or error UX | **`docs/CALENDAR_BEHAVIOR.md` (mandatory, read first)**, the Master Specification's Calendar authority amendment, accepted phase gate, ADR 0021 | `IMPECCABLE` only if the surface itself is being redesigned | Behavior that follows the documented convention, or an explicit recorded override; every layer's allowlist updated together. Direct human action is authorization — never add confirmation because an event is `locked`, and never surface ordinary provider drift as a user-facing conflict |
| `ROUTE-ART-DIRECTION` | Page feels generic; explore a distinct identity | Brand goals, content, audience, non-negotiables | `TASTE`, then relevant gallery cards | Isolated directions/reference board; no standing rules or implementation without approval |

### Motion, 3D, and visualization

| Route | Trigger | Required project context | Catalog `read_scope` | Default output |
| --- | --- | --- | --- | --- |
| `ROUTE-MOTION-FIND` | “What should animate?” or “make it feel alive” | Frequency map, motion tokens, product profile | `RB-MOTION-GATE`, `EMIL-MOTION` | At most 5–7 justified opportunities plus rejected candidates; no implementation |
| `ROUTE-MOTION-REVIEW` | Review or improve existing animation | Motion code, tokens, affected interactions | `EMIL-MOTION`, `RB-MOTION-GATE`, implementation owner (`MOTION`/`GSAP`/`ANIME`) | Findings with exact locations and acceptance criteria |
| `ROUTE-MOTION-IMPLEMENT` | Implement approved UI motion | Approved motion spec and surface code | One owner: CSS or `MOTION`; `GSAP`/`ANIME` only if specifically justified | Reversible scoped change with reduced motion and feel/performance verification |
| `ROUTE-SCROLL-STORY` | Pinned/scrubbed explanatory story | Story beats, mobile composition, reduced-motion alternative | `GSAP`, `EMIL-MOTION`; possible `GOOGLE-FLOW` for concepts | Timeline/storyboard first; no scroll hijacking; implementation after approval |
| `ROUTE-3D` | Shader, spatial interface, signature WebGL object | Renderer architecture, semantic state, performance/accessibility budgets | `THREE`; optional `RB-COLORBENDS` or `RB-AURORA` as technique references | Prototype/benchmark before architecture freeze; accessible equivalent and fallback required |
| `ROUTE-ION-CORE` | Ion Core visual/state/graph behavior | Ion Master Specification, Core docs/ADRs, current phase | `THREE`, `EMIL-MOTION`; React Bits shader cards only when phase permits | Semantic state contract and one renderer; no decorative full-screen canvas or second runtime |
| `ROUTE-CHART` | Add or revise a data visualization | Analytical question, source/provenance, narrative, accessible table | `BKLIT` only after chart need is established | Chart choice justified by data relationship; narrative insight and accessible data included |
| `ROUTE-CONCEPT-FILM` | Mood film, motion study, portfolio trailer | Brand/story beats and synthetic-data constraints | `GOOGLE-FLOW`, `EMIL-MOTION` | Shot list/concept; generated film never substitutes for interaction specification |

### Knowledge, retrieval, and code understanding

| Route | Trigger | Required project context | Catalog `read_scope` | Default output |
| --- | --- | --- | --- | --- |
| `ROUTE-VAULT` | Markdown vault, wiki, links, properties, graph | Knowledge ownership, schema, privacy, provenance | `OBSIDIAN`, `LLM-WIKI` | Raw/source/synthesis boundaries, schema, ingest/query/lint operations, user authority |
| `ROUTE-INGEST` | Import PDF/Office/HTML/image/archive | Source model, threat model, supported formats | `MARKITDOWN`; `LLM-WIKI` if compiling knowledge | Narrow adapter design, provenance/hash, malformed-file and resource-limit tests |
| `ROUTE-SEARCH` | FTS, semantic search, reranking, local retrieval | Corpus, latency/privacy targets, existing index | `QMD`, `OBSIDIAN`/`LLM-WIKI` as relevant | Benchmark plan before new runtime/index; deterministic search first |
| `ROUTE-CODE-GRAPH` | Map a growing repository or inspect coupling | Architecture docs and current module boundaries | `GRAPHIFY` | Development-only diagnostic; accepted findings become issues/ADRs |

## 3. Authorization and stop conditions

Proceed autonomously with reversible mechanical implementation that is clearly inside the requested scope. Stop and surface the decision before:

- changing a major architecture or canonical product requirement;
- adding a new major runtime, database, framework, graphics engine, AI provider, or external integration;
- changing security, privacy, data ownership, authentication, authorization, or secret handling;
- performing destructive or difficult-to-recover actions;
- sending/publishing content or creating external side effects not explicitly authorized;
- copying third-party assets/code without confirming license and attribution requirements;
- expanding from the requested phase or surface into unrelated redesign/refactoring.

## 4. Required `read_scope` declaration

At the start of substantial work, use this compact form:

```text
Route: ROUTE-...
Project profile: PROFILE-...
Project docs: [specific files/sections]
Catalog cards: [0–3 stable IDs]
Authority: analyze | propose | implement | publish
Excluded scope: [explicitly out of scope]
Verification: [tests/checks/evidence]
```

This declaration prevents context drift and gives the user a quick way to catch the wrong route before implementation.

## 5. Project-local context template

Keep `docs/projectContext.md` short. It should contain only information that materially changes implementation:

```markdown
# Project Context

## Goal and audience
- Product/user problem:
- Primary users:
- Success criteria:

## Current phase
- In scope:
- Explicitly out of scope:

## Stack and ownership
- Runtime/framework:
- Data owner:
- UI/design tokens:
- Animation owner:
- Deployment/runtime constraints:

## Visual/product character
- Project profile:
- Signature element:
- Approved catalog IDs:
- Rejected/forbidden patterns:

## Non-negotiables
- Privacy/security:
- Accessibility/performance:
- Approval gates:

## Canonical documents
- Specification:
- Architecture:
- Design system:
- ADR index:
```

Aim for roughly one to three pages. Move detailed history, research, and alternatives elsewhere.

## 6. Repository `AGENTS.md` bootstrap

Paste and adapt this at the repository root:

```markdown
# Agent Context Bootstrap

1. Read `docs/projectContext.md` first.
2. Classify the task using `docs/agent/taskRouter.md`.
3. Declare route, project profile, `read_scope`, authority, excluded scope,
   and verification before substantial work.
4. Read only the project documents and stable resource cards selected by the
   route. Do not load the entire universal catalog by default.
5. Project specifications and accepted ADRs override external references.
6. Do not silently change architecture, add major dependencies, weaken
   security/privacy, perform destructive actions, or leave the current phase.
7. Record accepted lasting decisions in project-local docs/ADRs.
```

For repository-only coding agents that cannot access persistent ChatGPT files, place a copy of this router at `docs/agent/taskRouter.md`. Copy only the approved resource cards—not the entire universal catalog—into `docs/references/approvedReferences.md`.

## 7. ChatGPT Project Instructions bootstrap

Do not paste both full documents into Project Instructions. Paste only this:

```text
Use `taskRouter.md` as the entry point for project work.
Read the project's canonical specification and local context as directed by the
selected route. Load only the stable resource cards named in the router from
`projectReference.md`; do not read the entire
catalog by default. State route, read_scope, authority, excluded scope, and
verification before substantial changes. Project-local decisions override the
universal catalog.
```

When persistent files are not available to the environment, attach the small router or keep it in the repository. Do not paste the full catalog into every conversation.

## 8. Minimal task prompts

### General

```text
Route this task using `taskRouter.md`: [task].
Load only the required project context and named resource cards. Start with the
read_scope declaration, then proceed within authority: [analyze/propose/implement].
```

### Portfolio hero

```text
Use ROUTE-HERO with PROFILE-PORTFOLIO. Evaluate RB-COLORBENDS and SUPAHERO for
[surface]. Propose three options and recommend one. Do not implement or add a
dependency until I approve an option.
```

### Ion

```text
Route this Ion task: [task]. The Ion Master Specification and current phase are
canonical. Load only the relevant Ion docs and allowed catalog cards. Do not
enter a later phase or add a major dependency without approval.
```

### Future CS project

```text
Use PROFILE-CS-APP and route [task]. Prefer the simplest owner and load no more
than three external resource cards. Explain any proposed dependency before
adding it.
```

### Reference update

```text
Use ROUTE-REFERENCE-UPDATE to update `projectReference.md`.

Requested change: [natural-language description]
Targets: [stable IDs, resource names, or “discover the affected cards”]
Desired action: [ADD / AMEND / VERIFY / SUPERSEDE / DEPRECATE / RETIRE / RENAME]
Apply after research: [yes / no]
Project impact to check: [Ion / portfolio / named projects / future projects]

Verify time-sensitive claims with current primary sources. Identify conflicts
with existing cards, profiles, routes, and pinned project decisions. Preserve
stable IDs and historical rationale. If the change is material and “Apply after
research” is no, show the impact summary before writing. When approved, update
the catalog and router together as needed, bump semantic versions, and add
changelog entries. Do not silently sync project-local specifications, ADRs,
dependencies, or selected-reference snapshots.
```

## 9. Maintenance

- Use `ROUTE-REFERENCE-UPDATE` whenever a reusable resource or rule changes.
- Update this router only when a task category, loading path, lifecycle status, or authorization rule changes.
- Update `projectContext.md` when the phase, stack, identity, or non-negotiables change.
- Put accepted project decisions in ADRs; do not turn conversation history into canonical context.
- At the end of a long task, record what changed rather than forcing the next agent to reconstruct it from chat.
- Within one session, do not reread unchanged documents. Retain the route and loaded versions in the working plan.
- Pin project-local reference selections to the catalog version used; review updates deliberately instead of syncing automatically.

## 10. Changelog

### 1.1.1 — 2026-08-28

- Required Ion implementation and verification agents to load the durable
  execution policy.

### 1.1.0 — 2026-08-27

- Renamed the router to `taskRouter.md` and the catalog to `projectReference.md`.
- Added `ROUTE-REFERENCE-UPDATE` and a ready-to-use update prompt.
- Added lifecycle-aware maintenance and project-version pinning.

### 1.0.0 — 2026-08-27

- Created the initial context tiers, route tables, authorization boundaries, templates, and minimal prompts.
