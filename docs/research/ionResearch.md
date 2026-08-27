# Ion OS Research, Implementation & Cross-Project Design Playbook

**Status:** Durable research reference; not a replacement for the Master Product & Engineering Specification  
**Research date:** 2026-08-27  
**Canonical precedence:** Master specification → accepted architecture/design decisions (ADRs) → implementation docs → this research playbook → external references

## 1. Purpose

This document converts a broad set of references—personal knowledge systems, LLM-maintained wikis, graph visualizations, agent workflows, design-engineering skills, component libraries, animation engines, and curated web-design galleries—into a restrained plan for Ion OS. Its cross-project design registry is also intended to support Arwaad's portfolio and future software projects without requiring the original research conversation.

The central conclusion is that Ion should not become a collection of fashionable tools. It should borrow a few durable ideas from each source while keeping one coherent architecture and one visual language.

Two principles govern every recommendation:

1. **Ion is a second brain and an assistant, but the LLM is not its memory.** Structured records, source files, Markdown knowledge, indexes, provenance, and revision history are the memory system.
2. **The Ion Core is a product identity and a data lens, not decoration pasted onto every screen.** Motion and glow must communicate state, hierarchy, or relationships.

## 2. Where this knowledge should live

ChatGPT Library is appropriate for durable research reports and cross-conversation reference. It is not the final source of truth for a codebase.

When the Ion repository exists:

- keep this research report as background reference;
- move accepted rules into `docs/DESIGN_SYSTEM.md`, `docs/ARCHITECTURE.md`, `docs/AI_SYSTEM.md`, and `docs/DATA_MODEL.md`;
- record consequential choices as ADRs in `docs/DECISIONS.md` or a dedicated `docs/decisions/` directory;
- put short agent-routing instructions in `AGENTS.md`;
- keep the real user's vault and database outside the public repository;
- use synthetic fixtures for screenshots, tests, and portfolio demonstrations.

The Library can preserve research. The repository must preserve implementation truth. Ion's own Obsidian-compatible vault will eventually preserve the user's personal knowledge.

## 3. Executive decisions

### 3.1 Adopt as core direction

| Area | Decision |
| --- | --- |
| Knowledge ownership | SQLite owns canonical structured records; Markdown owns durable prose knowledge; original source files are immutable; indexes are rebuildable; the LLM owns none of these. |
| Knowledge architecture | Adapt Karpathy's raw sources → compiled wiki → schema pattern to Ion's existing Sources → Knowledge → agent rules model. |
| Search | Deterministic exact/full-text search first; local semantic and graph-assisted retrieval later; cloud reasoning only after local context minimization. |
| Visual identity | Establish the Ion Core as a restrained black/violet spherical field with semantic state changes and an accessible non-visual equivalent. |
| App motion | CSS first, Motion for React second, custom Three.js motion for the Core. |
| Design-agent workflow | Use Impeccable as the broad product-design process and Emil Kowalski's skills for motion-specific construction and review. |
| Component policy | Copy and adapt individual source components only when they satisfy an Ion need; never let a component library define Ion's visual identity. |
| Agent routing | Use an explicit deterministic routing table before model-based routing. Every route declares data scope, reasoning tier, authority, and output schema. |

### 3.2 Evaluate later; do not add now

| Reference | Ion use | Why not now |
| --- | --- | --- |
| MarkItDown | Candidate Phase 7 ingestion adapter for PDFs, Office files, HTML, images, and other inputs. | Phase 0 explicitly excludes AI/knowledge ingestion; optional converters should be installed narrowly, not with every extra. |
| QMD | Benchmark as a local Markdown search sidecar in Phase 7. | It adds a Node/native-model runtime beside Tauri and Python; Ion may be better served by SQLite FTS5 plus a local embedding adapter. |
| Graphify | Developer-only codebase map and architectural diagnostic after the repository becomes large. | It is not an Ion runtime dependency and would add little to an empty/small repository. |
| Bklit UI | Source/reference for selective charts in contextual Insights. | Ion's specification says narrative before charts; chart choices must follow actual data needs. |
| Kokonut UI | Source/reference for a few interaction patterns or primitives. | Most expressive components are website-oriented and could quickly make a restrained productivity app feel ornamental. |
| React Bits | Strong candidate for isolated portfolio backgrounds, text effects, and rare expressive surfaces; shader ideas may later inform the Ion Core. | Several effects create continuous WebGL render loops or introduce Three.js/OGL/GSAP-level dependencies. Admit individual components only after measuring their actual cost and adding fallbacks. |
| Supahero / CTA Gallery / Footer Design | Inspiration indexes for page composition, conversion moments, and finishing patterns. | They are galleries, not implementation systems or evidence that a pattern fits the project's content, accessibility, or identity. |
| GSAP | Marketing site, onboarding story, or a rare scroll-directed explainer. | The desktop application is not a scroll-driven narrative and must avoid scroll hijacking. |
| Anime.js | Standalone SVG/DOM animation experiments and future small web projects. | It overlaps with Motion in the React app and with custom animation in the Three.js Core. |
| Google Flow | Future concept films, brand motion studies, and portfolio trailers using synthetic data. | Generated video is not executable UI, a motion specification, or evidence that an interaction is usable. |
| `3d-force-graph` / Sigma.js / Cytoscape.js | Rapid graph-layout and exploration prototypes. | The defining sphere likely needs custom spatial rules, visual encoding, state transitions, and accessibility beyond a stock graph renderer. |

### 3.3 Do not combine by default

- Do not install Motion, Anime.js, and GSAP into the same application without three distinct, documented owners.
- Do not install both Impeccable and Taste as always-on design authorities. Their large overlapping rule sets can pull the agent in different directions.
- Do not use Graphify as Ion's personal knowledge graph. Graphify maps a codebase; Ion's life graph has different entity semantics, authority rules, privacy boundaries, and temporal behavior.
- Do not represent every semantic similarity as a visible or permanent edge.
- Do not make the Core's data density an excuse to conceal provenance or create fabricated meaning.

## 4. Second-brain architecture

### 4.1 The six memory types Ion actually needs

“Memory” should not be one undifferentiated vector store.

| Memory type | Ion examples | Durable owner | Retrieval behavior |
| --- | --- | --- | --- |
| Structured/semantic | Courses, projects, people, goals, concepts, applications | SQLite + canonical entity IDs | SQL, filters, deterministic joins |
| Source | PDFs, syllabi, articles, emails, screenshots, imported files | Original local file + source record | Exact source lookup and citations |
| Knowledge/synthesis | What the user understands, summaries, comparisons, concept pages | Markdown vault | Full text, link traversal, semantic retrieval |
| Episodic | Focus sessions, task events, daily reviews, integration events | Event/audit tables | Time windows, recency, sequences |
| Prospective | Deadlines, reminders, planned blocks, follow-ups | Task/deadline/calendar entities | Time and constraint queries |
| Procedural | How Ion performs ingestion, planning, design review, or an authorized workflow | Versioned skills/rules/configuration | Intent routing; load on demand |

The LLM receives a temporary working context assembled from these stores. That context can be discarded and rebuilt.

### 4.2 Raw sources → knowledge → action

Adapt the LLM Wiki pattern as follows:

1. **Raw sources are immutable evidence.** Ion may hash, copy, classify, OCR, or convert them, but does not overwrite them.
2. **Companion notes explain a source.** A companion Markdown note can contain bibliographic metadata, summary, key claims, quotations within legal limits, user notes, questions, and related Ion IDs.
3. **Knowledge pages synthesize across sources.** They are living concept/entity pages with explicit source references and revision history.
4. **Structured records drive action.** A sentence in a note does not silently become a deadline, calendar block, goal, or user preference. Extraction creates a proposal or structured candidate that passes validation and authority rules.
5. **Indexes are derived.** Full-text, embedding, reranking, graph projections, summaries, and caches must be rebuildable from canonical records and files.

This preserves Karpathy's compounding-wiki advantage without allowing generated prose to become an unchecked control plane.

### 4.3 Vault structure

Keep the specification's readable structure; avoid a complicated taxonomy that the user must maintain:

```text
Inbox/
Knowledge/
Projects/
Courses/
Research/
Library/
Journal/
Daily Reviews/
Decisions/
Sources/
Assets/
```

Guidelines:

- `Inbox/` is low-friction capture, not a permanent dumping ground.
- `Sources/` contains source companion notes and references to immutable originals.
- `Knowledge/` is the compiled wiki: concepts, people, methods, questions, and syntheses.
- domain folders are contextual authoring surfaces, not duplicate databases;
- one stable `ion_id` ties a note to its canonical record, regardless of filename or folder;
- Ion should write standard Markdown links when practical for portability; Obsidian-style links can remain supported for user-authored notes;
- use Obsidian YAML properties for small atomic metadata, not nested database objects.

Suggested minimal frontmatter:

```yaml
---
ion_id: kn_01J...
entity_type: knowledge_node
title: Example concept
aliases: []
status: active
source_ids: []
created_at: 2026-08-27T00:00:00Z
updated_at: 2026-08-27T00:00:00Z
reviewed_at: null
---
```

Do not duplicate fast-changing structured fields such as task completion, grades, application status, or calendar state into Markdown unless the Markdown is explicitly a snapshot. Otherwise the vault and database will drift.

### 4.4 Ingestion pipeline

The eventual Phase 7 pipeline should be explicit and restartable:

```text
Capture
→ sensitive-data/secret scan
→ file type and size validation
→ hash + duplicate detection
→ immutable source preservation
→ text/metadata extraction
→ source companion proposal
→ structured candidate extraction
→ relationship suggestions
→ user confirmation where required
→ canonical write
→ full-text/semantic index update
→ audit event
```

MarkItDown is a strong adapter candidate because it converts many common formats to structure-preserving Markdown and fits the Python backend. Use the narrowest converter and optional dependencies needed. Treat conversion as untrusted I/O: restrict paths, formats, size, archives, and remote URI behavior.

### 4.5 Search and retrieval ladder

Use the cheapest sufficient layer:

1. **Direct ID/path lookup** for known records and files.
2. **SQLite query** for structured filters, joins, dates, states, and exact facts.
3. **FTS/BM25** for deterministic text search.
4. **Local semantic retrieval** for paraphrases and conceptual similarity.
5. **Graph expansion** for explicit neighboring entities and provenance-bearing paths.
6. **Local reranking** when the candidate set is ambiguous.
7. **Cloud Deep Ask** only for opted-in synthesis after filtering and minimization.

QMD is valuable as a reference because it combines BM25, vector search, fusion, and local reranking. Before adoption, benchmark it against a simpler Ion-native implementation on:

- retrieval quality;
- cold-start and warm latency;
- memory use;
- binary/model size;
- incremental indexing;
- offline behavior;
- source-line citation quality;
- packaging inside Tauri;
- maintenance and update risk.

### 4.6 Compounding wiki operations

Ion should support four explicit knowledge operations:

| Operation | Result |
| --- | --- |
| Ingest | Preserve source, create/update source page, update relevant knowledge pages, propose links, append audit/log entry. |
| Query | Retrieve relevant pages and sources, answer with provenance, optionally offer to save a useful synthesis. |
| Lint | Find contradictions, stale claims, orphans, missing sources, broken links, unresolved uncertainty, and duplicate entities. |
| Reconcile | Present competing claims with sources and dates; let the user accept, supersede, or preserve uncertainty. |

Maintain a generated `index.md` for human/agent navigation at moderate scale and an append-only activity log for traceability. Both are secondary projections; neither replaces the database audit trail.

### 4.7 Temporal truth and forgetting

Personal assistants fail when they retrieve an old fact as though it were current. Important memories and preferences therefore need temporal metadata:

- `observed_at`;
- `effective_from` / `effective_to` where relevant;
- `supersedes_id`;
- `source_id`;
- `confirmed_by_user`;
- `last_verified_at`;
- confidence only when uncertainty matters;
- an invalidated/tombstoned state rather than silent erasure.

A correction should not merely add a competing memory. It should explicitly supersede, constrain, or dispute the earlier one. Retrieval should prefer current, user-confirmed, and source-supported records while retaining history for explanation.

## 5. Ion as a personal “Jarvis” assistant

The useful part of the Jarvis metaphor is not omnipotence or constant chatter. It is continuity, situational awareness, concise recommendations, and reliable execution within clear authority.

### 5.1 Product loop

Ion's existing product loop is strong:

```text
Capture → Understand → Connect → Plan → Execute → Review → Adapt
```

Each stage should have a deterministic contract:

| Stage | Contract |
| --- | --- |
| Capture | Store with minimal friction; never invent missing source facts. |
| Understand | Extract candidates with evidence and uncertainty. |
| Connect | Prefer explicit structural links; keep inferred links soft. |
| Plan | Check time, resources, locked commitments, and user goals; surface infeasibility. |
| Execute | Respect authority level; confirm consequential external writes. |
| Review | Compare prediction with outcome without rewriting history. |
| Adapt | Update models/preferences only from sufficient evidence or user confirmation. |

### 5.2 The assistant should be artifact-first, not chat-first

Borrow this from Manus and LLM Wiki patterns:

- the conversation is a control surface;
- completed work becomes a plan, record, decision, note, schedule proposal, or report;
- the current plan remains visible during long operations;
- failures remain in the audit trail so the system and user can understand what happened;
- repeatable successful workflows can become versioned procedural skills;
- skills describe how to work, while integrations provide data and actions;
- long tasks should checkpoint durable intermediate state instead of relying on one context window.

Ion should not copy Manus's cloud-first autonomy. Ion remains local-first, minimally scoped, and approval-aware.

### 5.3 Human-AI behavior requirements

Preserve and extend the specification's safeguards:

- state what Ion can and cannot currently do;
- explain consequential recommendations through `Why?`;
- make it easy to correct, dismiss, undo, or refine AI output;
- learn from repeated behavior, not a single accidental correction;
- distinguish user intention from model suggestion;
- surface stale or failed integration data only when it affects a decision;
- keep audit and provenance accessible without exposing internal metrics by default;
- never use warmth/personality to disguise uncertainty or missing evidence.

## 6. Runtime task-routing tables

Start with explicit rules. A model may classify ambiguous intent later, but cannot decide its own authority or privacy boundary.

### 6.1 Core routing table

| Request class | Primary engine | AI tier | Context scope | Authority | Output |
| --- | --- | --- | --- | --- | --- |
| Exact record lookup | SQLite / file lookup | Tier 0 | Named entity or collection | Read | Deterministic result + source |
| Keyword search | FTS/BM25 | Tier 0 | User-selected domains | Read | Ranked records/files |
| Semantic knowledge search | Local hybrid retrieval | Tier 1 optional | Vault only unless expanded | Read | Ranked evidence; no new permanent links |
| Capture classification | Rules, then local model | Tier 1 | Captured item only | Propose | Typed candidate + evidence + uncertainty |
| Deadline/task extraction | Parser/rules, then local model | Tier 1 | Source item only | Propose | Structured candidate; source retained |
| Schedule construction | Constraint engine | Tier 0; AI may explain | Tasks, calendar, estimates, policies | Propose | Feasible plan or explicit overload |
| Schedule explanation | Template/local model | Tier 0/1 | Selected plan factors | Read | `Why?` explanation |
| Deep project/research analysis | Local retrieval + cloud provider | Tier 2 opt-in | Minimized relevant context | Read/Propose | Cited analysis; no automatic intention |
| Financial calculation | Deterministic math | Tier 0 | Private Local finance records | Read/Propose | Reproducible calculation; no transactions |
| External write | Integration adapter | No AI authority | Exact proposed change | Confirm or whitelist | Write receipt + audit + undo/retry |
| Delete/move/rename user knowledge | Filesystem operation | No AI authority | Exact item | Confirm initially | Reversible action + history/trash |
| Ambiguous or conflicting source | Conflict resolver UI | Tier 0/1 | Competing sources only | Ask | Conservative options with provenance |

### 6.2 Router contract

Every route should declare:

```text
intent
required inputs
allowed data classes
retrieval strategy
AI tier/provider eligibility
authority level
confirmation rule
output schema
audit event
failure behavior
```

The router should reject a route when required inputs, permissions, authoritative freshness, or privacy conditions are not satisfied. It should not “best effort” an external write from stale or inferred data.

### 6.3 Development-agent routing table

| Work requested | Required reference/process | Default tool/library | Gate before merge |
| --- | --- | --- | --- |
| New app surface | Master spec + product/design docs; Impeccable `shape`/product-mode guidance | Existing Ion primitives | Desktop visual check, keyboard flow, reduced motion, empty/error/loading states |
| Design audit/polish | Impeccable critique/audit/polish | No new dependency by default | Batched desktop/mobile review and accessibility checks |
| New motion | Emil `animate` decision sequence | CSS first, Motion second | Purpose stated; frequency considered; reduced motion; cleanup/perf verified |
| Motion review | Emil `review-animations` | Existing engine | No `transition: all`; appropriate curves/durations; interruptibility |
| Ion Core prototype | Core visual spec + Core ADR | Three.js + React Three Fiber | FPS/frame-time benchmark, no per-frame React state, semantic state tests, accessible equivalent |
| Scroll story/marketing | Separate marketing brief | Motion `useScroll` for simple effects; GSAP ScrollTrigger for real choreography | No wheel hijack; reduced-motion static composition; mobile fallback |
| Chart | Narrative insight and actual data question first | Bklit source as reference, or existing chart primitive | Chart answers the question, uses Ion tokens, accessible data table/summary |
| Knowledge ingestion | Knowledge ADR + security docs | MarkItDown candidate, narrow converter | Malformed/untrusted file tests, size/path limits, provenance, deterministic retry |
| Local retrieval | Search evaluation corpus | SQLite FTS first; QMD benchmark later | Quality/latency/memory benchmark; citations; offline behavior |
| Architecture navigation | Repository docs first | `rg`; Graphify only after threshold/experiment | Output treated as derived diagnostic, not canonical documentation |
| High-expression visual exploration | Isolated prototype and explicit brief | Taste as a temporary exploration lens | Human selection; re-implement with Ion tokens; no automatic dependency carryover |

## 7. Ion visual identity baseline

### 7.1 Identity statement

**Ion is a quiet instrument surrounding a concentrated field of energy.**

The interface is calm, editorial, and operational. The Core carries the energy; the rest of the product gives it room. Purple is not decoration—it means active intelligence, focus, or selected structure.

### 7.2 Visual grammar

| Element | Direction |
| --- | --- |
| Environment | Tinted near-black, not flat #000 everywhere |
| Surfaces | Charcoal-violet neutrals with small luminance steps; low visual chrome |
| Energy | Electric violet used sparingly for the Core, selection, focus, and active transitions |
| Secondary signal | Restricted indigo/blue and teal for clearly distinct states, not category rainbows |
| Text | Soft off-white; metadata is lower contrast but must remain accessible |
| Shape | Precise geometry, modest radii, thin separators; avoid pills and nested cards as defaults |
| Glass | Temporary overlays, Ask Ion, command palette, modal/detail layers only |
| Depth | Localized bloom around meaningful energy; not blurred panels across the entire UI |
| Typography | Modern, highly readable sans; technical through hierarchy and spacing, not a sci-fi typeface |

### 7.3 Provisional semantic tokens

These values are a prototype starting point, not a frozen brand palette. They require contrast and display testing.

```css
:root {
  --ion-canvas: #07060a;
  --ion-surface-1: #0d0b12;
  --ion-surface-2: #14111b;
  --ion-rule: rgba(224, 213, 255, 0.10);

  --ion-text: #f4f0f8;
  --ion-text-muted: #aaa3b4;
  --ion-text-faint: #777080;

  --ion-energy: #a463ff;
  --ion-energy-hot: #c187ff;
  --ion-indigo: #6f73ff;
  --ion-teal: #58cfc7;

  --ion-glow-soft: rgba(164, 99, 255, 0.18);
  --ion-glow-active: rgba(164, 99, 255, 0.34);
}
```

Do not use these tokens to fill large cards with purple. Energy color should occupy a small portion of the screen and feel more intense because the environment is restrained.

### 7.4 Design-system rules

- One token source in `packages/ion-design/`; no scattered hex values or easing curves.
- Brand direction and product-operating direction are separate briefs. Ion's marketing site may be more expressive than Ion's daily task UI.
- “Summary first, detail on demand” applies to layout as well as data.
- Use spacing, typography, and separators before introducing another card.
- A component copied from Kokonut, Bklit, shadcn, or elsewhere must be absorbed into Ion's tokens and interaction rules; the source's demo styling is not the design.
- Every animated chart or visual component needs a static state, reduced-motion behavior, empty state, error state, and data explanation.
- The Core is the only always-available expressive object. Pages do not each get their own competing particle field.

## 8. The Ion Core sphere

### 8.1 Separate brand object from analytical graph

Use two modes over the same relationship projection:

| Mode | Purpose | Default behavior |
| --- | --- | --- |
| Ambient Core | Identity, system state, high-level connectedness | Quiet rotation/pulse; no permanent labels; limited interaction |
| Explore / Knowledge Map | Deliberate navigation and analysis | Scope, select, zoom, labels, provenance, filters, alternative accessible list/table |

The ambient Core may aggregate data into clusters when 1:1 representation is misleading or unsafe for performance. Explore mode must make that aggregation clear and allow scoped inspection.

### 8.2 Visual encoding

| Data concept | Visual treatment |
| --- | --- |
| Entity/record | Node with stable ID; size is capped and based on a documented measure |
| Structural relationship | Most legible edge; stable and explicit |
| Contextual relationship | Muted until relevant or selected |
| Soft/inferred relationship | Lowest emphasis; provenance/uncertainty visible in Explore; never promoted silently |
| Active context | Local illumination, not recoloring the entire sphere |
| Recent activity | Brief energy travel/pulse that decays; not permanent importance |
| Dense cluster | Greater local density/bloom with level-of-detail controls |
| Sparse/undeveloped area | Lower density without labeling the user as deficient |

Do not encode sensitive categories through a globally visible sphere if someone nearby could infer private information. Private Mode can switch to a neutral or locally limited projection.

### 8.3 Core state motion

| State | Motion language | Reduced-motion equivalent |
| --- | --- | --- |
| Idle | Very slow rotation; low-amplitude breathing; no attention-seeking particles | Static field with stable soft glow |
| Processing | Energy moves only through relevant region/paths; progress is also shown textually | Local brightness change + textual status |
| Urgent | Slightly faster/intense pulse; never red alarm theatrics | Higher local contrast + concise badge/text |
| Focus | Slower, dimmer, more coherent motion; fewer active edges | Dim static field |
| Deep Ask | Relevant cluster illuminates and scope tightens | Highlighted cluster outline + status text |
| Offline | Core remains stable; remote unavailability shown separately | Same Core + explicit offline indicator |
| Error | Do not glitch the whole Core; identify the affected integration/action | Stable Core + localized error and retry |

Ambient loops should be slow enough to disappear from attention. User-triggered state transitions may take longer than ordinary UI micro-interactions when they explain a spatial change, but should remain interruptible.

### 8.4 Renderer direction

Primary recommendation:

- Three.js with React Three Fiber for integration with the React shell;
- `BufferGeometry`, shared materials, instancing, and GPU-friendly attributes for large point/edge sets;
- one render loop owned by the Core;
- semantic application state enters through a small Core state machine;
- frame-by-frame animation mutates Three.js objects or shader uniforms without React state updates;
- lower frame rate or pause when backgrounded, on battery-saving policy, or outside the viewport;
- level of detail and deterministic sampling for large graphs;
- separate data/layout, rendering, interaction, and motion controllers.

Suggested module boundaries:

```text
ion-core/
├── model/          graph projection + stable IDs
├── layout/         clustering + spherical positions
├── render/         points, edges, bloom, labels
├── interaction/    orbit, hit testing, scope, keyboard bridge
├── motion/         state transitions + energy paths
├── accessibility/  list/table/announcements/reduced motion
└── benchmarks/     fixtures + frame-time budgets
```

`3d-force-graph` is useful for a spike because it supplies Three.js rendering, force layout, zoom, hover, and selection quickly. It should not be assumed as production architecture: a generic force-directed volume may not produce Ion's intentional spherical shell, stable clusters, semantic state transitions, or distinctive rendering.

Sigma.js is a stronger reference for a large 2D WebGL Explore view. Cytoscape.js is a stronger reference for graph algorithms and multiple layouts. Either can be prototyped without committing the Core to that library.

### 8.5 Performance acceptance criteria

Set measurable budgets during the prototype rather than promising “thousands” abstractly:

- foreground frame-time target on the minimum supported Mac;
- degraded/battery target;
- maximum nodes/edges at each level of detail;
- memory allocation and GPU resource cleanup after repeated scope changes;
- no unbounded object creation in the render loop;
- hit-testing latency;
- time to first meaningful render;
- pause/background behavior;
- reduced-motion energy use.

Benchmark representative sparse, medium, dense, and pathological graphs with synthetic data. Record the hardware, renderer, node/edge counts, and visual features enabled.

### 8.6 Accessibility

The Core cannot be the only way to understand Ion state or navigate knowledge.

- Provide an equivalent structured list/table and command-search route.
- Announce state changes through accessible text, not animation alone.
- Support keyboard scoping and selection in Explore mode.
- Never rely only on violet/teal distinctions.
- Disable continuous motion under reduced motion; reduce transparency where supported.
- Labels appear on deliberate focus/selection and remain readable at zoom.
- Preserve selection when switching between visual and structured views.

## 9. Motion engine policy

### 9.1 Default decision ladder

1. **No animation** when frequency is high or motion communicates nothing.
2. **CSS transitions** for hover, press, opacity, color, simple enter/exit, and interruptible state changes.
3. **Motion for React** for layout transitions, presence, gestures, drag, shared layout, and React-coordinated sequences.
4. **Three.js/custom shader motion** for Core geometry, camera, particles, bloom, and energy paths.
5. **GSAP** only for a genuine multi-scene scroll/timeline problem, normally outside daily app operation.
6. **Anime.js** for isolated DOM/SVG experiments when its small modular timeline/SVG toolset is the best fit and Motion/GSAP are not already owners.

The same visual property must have one animation owner. Do not let CSS, Motion, GSAP, and a Three.js loop fight over transforms or opacity.

### 9.2 Motion craft rules absorbed from Emil Kowalski

- First ask whether the interaction should animate at all.
- Name the purpose: feedback, spatial consistency, state indication, explanation, or prevention of a jarring change.
- High-frequency and keyboard-driven actions should be instant or nearly instant.
- Prefer transforms and opacity; specify exact transitioned properties, never `transition: all`.
- Enter/exit motion should generally feel immediately responsive; avoid slow ease-in entrances.
- Keep ordinary app micro-interactions short; allow longer durations only for deliberate spatial or explanatory movement.
- Springs are useful for interruptible gestures and physically responsive interaction, not as a universal “bouncy” style.
- Do not animate from `scale(0)`; use a subtle scale/opacity transition if scaling is appropriate.
- Anchor popovers to their trigger; keep modals centered.
- Ship reduced-motion and hover-capability handling with the animation.
- Review motion as strictly as functionality: interruption, exit, rapid repetition, cleanup, and perceived latency all matter.

### 9.3 Scroll animation

For the Ion desktop app:

- do not make the Core's primary state depend on page scroll;
- do not pin or hijack the Today, Projects, School, or Career interfaces;
- use normal scrolling for content and state-driven Core transitions for actual application events;
- a small parallax/opacity response may be acceptable only if it does not compete with reading or operation.

For a marketing site, portfolio case study, or onboarding explainer:

- treat scroll as a timeline that explains the product loop or Core states;
- use Motion's scroll APIs for one-to-one transforms and simple progress effects;
- use GSAP ScrollTrigger for a real pinned multi-scene story, synchronized camera choreography, or complex scrubbed sequence;
- never block native wheel/touch behavior;
- build mobile and reduced-motion compositions that communicate the same story without the choreography;
- keep the actual Three.js state machine as the source of the animation; scroll should drive normalized semantic progress, not reach into arbitrary scene internals.

Google Flow can generate a short mood film or shot reference for future brand/portfolio work. A useful shot list would cover Idle → Capture → Connect → Focus → Deep Ask → Resolve. Recreate accepted behavior with real Three.js code and synthetic records rather than embedding generated video as product interaction.

## 10. Design skills and UI references

### 10.1 Impeccable: primary design process

Use Impeccable as the broad workflow because it distinguishes product-operation surfaces from marketing/brand surfaces and supports shaping, critique, accessibility/performance audit, hardening, and polish.

Ion-specific use:

- create `PRODUCT.md`/`DESIGN.md`-equivalent context only if it does not duplicate canonical repo docs; preferably point the skill at Ion's existing docs;
- classify daily app surfaces as **Operate**, documentation as **Read**, marketing as **Persuade**, and visual case studies as **Experience**;
- preserve the Master Spec and accepted design identity instead of allowing a “redesign” command to replace them casually;
- run bounded visual review passes, not open-ended polishing loops;
- use deterministic detector rules as review findings, not permission to bulk-rewrite unrelated UI.

### 10.2 Emil Kowalski: motion specialist

Use the focused `animate`, `review-animations`, `improve-animations`, and `find-animation-opportunities` skills when motion work begins. This is the best match for Ion because the product is frequently operated and should feel refined without becoming theatrical.

### 10.3 Taste Skill: reference and exploration, not standing authority

Taste offers useful anti-generic rules, design dials, and image-first exploration. Its current default skill is explicitly experimental and overlaps heavily with Impeccable and Emil.

Use it only when:

- exploring a distinct marketing/portfolio visual direction in an isolated prototype;
- creating a reference board or brand-kit study;
- diagnosing a demonstrably generic agent-generated page.

Do not let its generic bans override a deliberate Ion requirement. For example, purple is an intentional Ion identity; the problem is indiscriminate gradients, not purple itself.

### 10.4 Kokonut UI

The intended reference appears to be **Kokonut UI**, not “Coconut UI.” It provides copyable React/Tailwind/Motion components through a shadcn-style registry.

Good Ion uses:

- inspect a compact search/action input, disclosure, loader, or navigation interaction;
- borrow an implementation technique and retokenize it;
- use a component as a prototype, then remove unnecessary visual effects.

Avoid as defaults:

- particle buttons;
- shimmer text;
- liquid glass cards;
- animated backgrounds;
- large marketing blocks inside operational dashboards.

### 10.5 Bklit UI

The intended “Backlit UI” reference appears to be **Bklit UI**, an animated chart library/registry with an interactive studio.

Good Ion uses:

- prototype a line, area, bar, gauge, ring, scatter, or Sankey chart for a clearly stated analytical question;
- copy the open-source chart component rather than depending on a proprietary studio;
- tune motion and appearance to Ion tokens;
- pair every chart with narrative insight and accessible data.

Do not add a chart merely because a dashboard has empty space. Ion's specification explicitly prefers narrative insights first.

### 10.6 Manus AI

Manus is a product/architecture reference, not a dependency. Useful ideas include:

- action and deliverable orientation instead of chat-only output;
- persistent file artifacts as externalized context;
- visible plans/todos during long operations;
- leaving failed attempts available for diagnosis;
- progressive disclosure for skills;
- reusable, composable procedures;
- parallel processing only when items are independent and synthesis has an explicit schema.

Ion should retain stricter local-first privacy, authority, and human confirmation than a general cloud execution agent.

### 10.7 React Bits

React Bits is both an inspiration source and an implementation library. Unlike a screenshot gallery, it publishes editable React source in JavaScript/TypeScript and CSS/Tailwind variants. The repository uses an **MIT + Commons Clause** license: its components may be used and modified inside an application, website, or product, but the components themselves may not be resold, sublicensed, redistributed as a bundle, or ported for resale.

The three attached homepage states establish a useful visual vocabulary:

| Captured preset | Dominant color | Character | Best portfolio use | Possible Ion use |
| --- | --- | --- | --- | --- |
| Nebula | `#A855F7` violet | Atmospheric, creative, expansive | Primary hero or selected-work transition; strongest match for the existing Ion-violet family | Rare brand/knowledge state, Core halo study, or portfolio explanation of Ion |
| Aurora | `#10B981` green | Organic, connective, alive | A restrained project transition or one contextual section, not a second competing hero | Connected/success state only; green must remain semantic rather than a permanent Ion brand color |
| Ice | `#06B6D4` cyan | Technical, calm, precise | Computing/data work, timeline, or a cool alternate case-study theme | Analysis/focus accent if it remains subordinate to Ion violet |

These are **captured homepage presets**, not guaranteed drop-in APIs. The displayed homepage snippet includes values such as `fadeTop` and a normalized-looking `bandWidth`, while the current open-source `ColorBends` component exposes a different prop surface. Recheck the component page and source at implementation time rather than pasting screenshot code blindly.

Implementation findings:

- `ColorBends` is a full-screen plane rendered by Three.js with custom vertex/fragment shaders, continuously updated time/rotation uniforms, smoothed pointer influence, resize observation, a device-pixel-ratio cap of 2, and renderer/material/context cleanup.
- `Aurora` is a separate OGL/WebGL shader using simplex noise, a three-stop color ramp, amplitude, blend, and time/speed controls.
- The dependency list for the whole React Bits documentation site is **not** the cost of one copied component. Audit only the imports and transitive packages of the selected component.
- React Bits' agent skills contain a useful motion gate: judge frequency, purpose, speed, and function; reject motion that only “looks cool” on high-frequency operational UI. This complements the Emil motion rules already adopted here.

Portfolio posture:

- `ColorBends`/Nebula is the highest-priority future hero experiment because it matches the requested visual direction and can be isolated behind the existing content.
- Use only one continuously animated atmospheric background in a viewport. Pair it with still typography, simple CTAs, and a conventional navigation structure.
- Treat the effect as `aria-hidden`; ensure contrast comes from a stable overlay rather than hoping the shader stays dark behind text.
- Add a static CSS gradient or pre-rendered still fallback for reduced motion, low-power/mobile devices, missing WebGL, page backgrounding, and renderer failure.
- Pause or throttle the render loop when the canvas is offscreen or `document.visibilityState !== 'visible'`; measure mobile GPU use, Largest Contentful Paint, interaction latency, memory, and battery impact.

Ion posture:

- Do not add React Bits during Phase 0.
- When the advanced Core is built, port an accepted shader idea into Ion's existing Three.js/R3F renderer rather than running an unrelated full-screen canvas or adding OGL beside Three.js.
- Bind visual uniforms to a small semantic state contract (`idle`, `listening`, `thinking`, `connected`, `warning`, `complete`) rather than exposing decorative controls to product logic.
- Never place a continuously moving shader behind dense operational tables, tasks, notes, or graphs. The Core or an explanatory portfolio surface owns the effect.

## 11. Cross-project design and interaction resource registry

This is the reusable collection for the portfolio, Ion, and future projects. When a repository exists, copy this section into `docs/references/UI_REFERENCE_CATALOG.md` and keep accepted project-specific choices in the normal design system or an ADR. The stable IDs below allow a future request to name a reference without retelling this research.

### 11.1 Registry

| Stable ID | Resource class | Best used for | Portfolio default | Ion default |
| --- | --- | --- | --- | --- |
| `RB-COLORBENDS` | Copyable React + Three.js shader | Nebula-like hero fields, atmospheric case-study transitions | Strong candidate; prototype first | Shader ideas only until advanced Core work |
| `RB-AURORA` | Copyable React + OGL shader | Organic light curtains and soft motion | Candidate for one secondary surface | Avoid adding OGL; port an accepted shader to Three.js |
| `RB-MOTION-GATE` | Agent/review method | Finding, rejecting, and auditing animation opportunities | Use before and after expressive work | Use alongside Emil for strict frequency/purpose review |
| `SUPAHERO` | Curated hero gallery | Information hierarchy, hero composition, visual hooks, portfolio/project openings | Consult before a homepage or case-study hero refresh | Consult for public Ion landing page, history timeline, or future-project storytelling—not daily app UI |
| `CTA-GALLERY` | Curated CTA gallery | Contact, project-view, download, signup, and next-step patterns | Consult for contact/project conversion moments | Consult for public website/onboarding; operational buttons follow the design system |
| `FOOTER-DESIGN` | Curated footer gallery | Navigation closure, contact, status, social, credits, legal, and expressive page endings | High-value reference because the current portfolio needs a stronger footer | Public Ion website only; desktop app uses restrained status/about surfaces |
| `KOKONUT` | Copyable React component registry | Compact controls and selected interaction patterns | Selective use after retokenization | Primitive-level inspiration only |
| `BKLIT` | Copyable animated chart registry | Prototyping charts for a defined analytical question | Useful for data-oriented case studies | Evaluate only after narrative insight and data requirements exist |
| `MOTION` | Primary React motion engine | Stateful interface transitions and gestures | Default React animation owner | Default non-Core animation owner |
| `THREE` | 3D/WebGL engine | Custom spatial systems and signature visuals | Use for a justified hero/case study | Core renderer and graph-exploration candidate |
| `GSAP` | Timeline/scroll engine | Pinned, scrubbed, multi-scene storytelling | Exception for a true scroll-directed case study | Marketing/onboarding exception only |
| `ANIME` | DOM/SVG animation engine | Small non-React experiments or isolated SVG choreography | Optional specialist | Avoid when Motion/Three already owns the surface |
| `IMPECCABLE` | Design process skill | Shaping, critique, accessibility, hardening, and polish | Primary review process | Primary review process |
| `EMIL-MOTION` | Motion craft skills | Purposeful construction and high-bar motion review | Primary motion specialist | Primary motion specialist |
| `TASTE` | Experimental visual-direction skill | Escaping generic agent output and exploring a distinct art direction | Isolated exploration only | Never a standing authority |
| `GOOGLE-FLOW` | Generative concept-film tool | Mood films and visual shot exploration | Concept/brand film only | Synthetic-data concept footage only |

### 11.2 How to use galleries without copying them

For `SUPAHERO`, `CTA-GALLERY`, and `FOOTER-DESIGN`, record design properties rather than “make it look like this site”:

1. identify the content job: introduce, persuade, route, reassure, or close;
2. capture hierarchy, spacing rhythm, grid, type scale, imagery role, CTA placement, and motion behavior;
3. shortlist at most three references that fit the project's content and personality;
4. synthesize one project-native solution using existing tokens and copy;
5. verify desktop/mobile, keyboard, contrast, reduced motion, content length, and loading behavior;
6. retain the source URL and access date for provenance, but do not copy protected brand assets, text, screenshots, or proprietary code.

Use these galleries as specialized search indexes:

- `SUPAHERO`: begin a page, case study, history segment, or future-project story.
- `CTA-GALLERY`: define the decision the visitor should make after understanding the content.
- `FOOTER-DESIGN`: finish the information architecture instead of ending after the final project card.

### 11.3 Cross-project selection protocol

Before implementation, the coding agent should produce a compact reference decision table:

| Required field | Meaning |
| --- | --- |
| Surface and user job | Exact page/section and what the user must understand or do |
| Selected resource IDs | One primary implementation source and up to two composition references |
| Extracted properties | What is being borrowed: hierarchy, motion model, shader behavior, layout, or interaction |
| Rejected references | What was considered and why it conflicts with identity, frequency, performance, or content |
| Dependency effect | New runtime packages, copied source, bundle/GPU impact, and license |
| Ownership | CSS, Motion, Three.js, GSAP, or another single animation owner |
| Fallback | Static, reduced-motion, no-WebGL, mobile, and failure behavior |
| Acceptance evidence | Screenshots/video, browser checks, performance measurements, accessibility checks, and tests |

Do not combine a gallery, component library, and animation engine merely because all three appear in the same prompt. The agent must explain the job of each selected reference.

### 11.4 Minimum-context prompt for a portfolio exploration

```text
Read the project's design documentation and the Cross-Project Design and
Interaction Resource Registry in the Ion research playbook. Use the stable
resource IDs below as references, not as instructions to copy an entire site.

Task: audit and propose a cohesive improvement for [surface].
Primary implementation candidate: [for example RB-COLORBENDS].
Composition references: [for example SUPAHERO, CTA-GALLERY, FOOTER-DESIGN].

Before editing code:
1. inspect the existing stack, content, tokens, responsive behavior, and motion;
2. return three clearly differentiated options and a reference decision table;
3. recommend one option with explicit identity, accessibility, performance,
   mobile, reduced-motion, and licensing implications;
4. list new dependencies, but do not install any or implement until approved.

Preserve the site's real content and personality. Use one dominant visual idea,
keep typography and CTAs legible over every animation frame, and do not copy
third-party brand assets or text.
```

After an option is approved, the implementation prompt should add:

```text
Implement approved option [ID] in an isolated, reversible change. Copy only the
selected component source or add the smallest justified dependency. Add a
static/reduced-motion/no-WebGL fallback, pause offscreen/background animation,
gate pointer effects to capable devices, and verify desktop + mobile visually.
Report changed files, dependency/bundle impact, measured runtime behavior, test
results, and any remaining tradeoffs. Do not redesign unrelated sections.
```

### 11.5 Minimum-context prompt for Ion

```text
Read the Ion Master Specification first, then the research playbook sections on
visual identity, the Core, motion ownership, and the Cross-Project Design and
Interaction Resource Registry. The Master Specification and accepted ADRs win
over every external reference.

Evaluate [resource ID] for [exact Ion surface and phase]. Do not implement work
from a later phase. First return the reference decision table, identify the
semantic user/state purpose, and state whether the result should be adapted,
deferred, or rejected. Reuse Ion tokens and the existing Three.js/R3F renderer;
do not add a second graphics or animation runtime without an ADR. Preserve the
calm operational interface, local-first constraints, reduced-motion behavior,
accessible non-visual equivalents, and performance budgets.
```

## 12. Reference repositories

### 12.1 Karpathy's LLM Wiki

**Adopt:** immutable raw sources, LLM-maintained compiled Markdown, a schema/rule file, index, append-only log, ingest/query/lint operations, and filing valuable analyses back into the knowledge base.

**Modify for Ion:** the user remains able to edit knowledge; AI edits are versioned/audited; source and synthesis are distinct; structured actions require validation; inferred links remain soft; private data rules apply before indexing or model use.

### 12.2 Microsoft MarkItDown

**Adopt later:** a Python ingestion adapter and normalized Markdown intermediate representation.

**Guardrails:** narrow converter APIs, only required optional dependencies, local-path/URI restrictions, archive limits, malformed-file tests, timeouts, resource limits, and source hash/provenance.

### 12.3 Tobi QMD

**Adopt conceptually:** hybrid local retrieval, explicit collections/context, structured agent output, reranking only when helpful, and a long-lived local process to avoid repeated model loading.

**Decision later:** benchmark QMD as a sidecar against an Ion-native search service. Do not duplicate indexes unless the quality gain justifies operational complexity.

### 12.4 CodeCrafters Build Your Own X

This is a learning reference, not production code. It supports a healthy development practice:

- build a small isolated toy version to understand an important subsystem;
- document what was learned;
- use the lesson to evaluate the mature production implementation;
- keep learning spikes outside Ion's main runtime unless they meet the same testing/security bar.

High-value future learning spikes for Ion include a tiny inverted index, a constraint scheduler, a graph layout, a Markdown parser, a synchronization engine, and an event-sourced undo log.

### 12.5 Graphify

Graphify's explicit distinction between extracted and inferred edges is especially relevant to Ion. Use the same provenance concept in Ion's relationship model.

Potential developer workflow after the codebase grows:

1. generate a repository graph on demand or at major architecture checkpoints;
2. compare high-degree nodes and detected communities with documented module boundaries;
3. investigate surprising cross-subsystem dependencies;
4. file accepted findings as normal docs/ADRs/issues;
5. delete/rebuild the diagnostic output when stale.

Do not make coding agents query Graphify instead of reading the relevant canonical specification and code. A generated graph is an accelerator, not truth.

## 13. Phased implementation plan

### Phase 0 — Repository + engineering foundation

Do now:

- preserve this report as research;
- establish `packages/ion-design/` token ownership and semantic naming;
- document the visual identity, motion ladder, reduced-motion policy, and dependency-admission rule;
- document knowledge ownership and relationship provenance in architecture/decision records;
- add agent routing instructions telling coding agents which docs to read for UI, motion, Core, knowledge, and AI work;
- preserve the stable cross-project resource IDs in a repo-local reference catalog once the repository exists;
- keep Core fixtures synthetic and the advanced renderer out of scope;
- do not add MarkItDown, QMD, Graphify, React Bits, GSAP, Anime.js, Kokonut, Bklit, or AI providers.

An early isolated Core visual spike is allowed only if it is explicitly outside the production milestone and does not change Phase 0 acceptance criteria.

### Phase 1 — Core organizer

- implement the restrained app shell using Ion tokens;
- add CSS/Motion only for purposeful shell interactions;
- consider a lightweight visual Core placeholder driven by synthetic/static state, not the real graph;
- build deterministic search and structured views before graphical exploration.

### Phase 4 — Local AI

- implement the routing contract and structured-output validation;
- preserve candidate vs accepted intention boundaries;
- begin procedural skill loading only for clearly scoped workflows.

### Phase 7 — Knowledge + Obsidian

- implement raw source preservation, companion notes, wiki operations, frontmatter schema, provenance, reconciliation, and lint;
- evaluate MarkItDown;
- benchmark QMD against Ion-native FTS/semantic retrieval;
- make links structural/contextual/inferred with separate persistence rules;
- implement memory invalidation and temporal truth.

### Phase 8 — Career + GitHub

- use GitHub as a first-class structured integration;
- consider Graphify only as a developer/portfolio-maintenance diagnostic, never as user data storage.

### Phase 13 — Advanced Ion Core

- implement the data-connected R3F/Three.js renderer;
- benchmark layouts and LOD;
- build the state machine and accessible equivalent;
- prototype 3D force layout, spherical clustered layout, and 2D Explore alternatives before freezing architecture;
- add motion review as an acceptance gate.

### Future marketing/portfolio work

- use `RB-COLORBENDS` as the first atmospheric portfolio-hero prototype, with Nebula as the leading palette direction and Aurora/Ice as alternatives rather than simultaneous layers;
- consult `SUPAHERO` for hero hierarchy, `CTA-GALLERY` for the visitor's next action, and `FOOTER-DESIGN` to complete the portfolio's closing information architecture;
- use `RB-MOTION-GATE` and `EMIL-MOTION` to reject unnecessary motion before implementation and review accepted motion afterward;
- use GSAP ScrollTrigger only for a real scroll-directed story;
- use Anime.js for isolated SVG/DOM experiments when it is the smallest owner;
- use Google Flow for concept footage and motion mood studies;
- record the real interactive Core for final portfolio demos whenever accuracy matters.

## 14. Dependency-admission checklist

Before adding any referenced package, answer:

1. What exact user problem does it solve now?
2. Which existing tool overlaps with it?
3. Is it runtime, build-time, development-only, or a copied source component?
4. Can a simpler CSS/platform/standard-library solution meet the requirement?
5. Does it work offline and fit Tauri packaging?
6. What data leaves the device?
7. What are its license and redistribution constraints?
8. Is it maintained, typed, testable, accessible, and compatible with the selected stack?
9. What is its bundle, memory, startup, and GPU cost?
10. What is the removal/migration plan?
11. Which module owns it and which properties is it allowed to control?
12. Which ADR records the decision?
13. Is this resource executable source, a visual gallery, a process skill, or merely concept inspiration?
14. For animated/WebGL work, what happens under reduced motion, on coarse pointers, without WebGL, while offscreen, and while the page is backgrounded?

If the answer is “it may look useful later,” keep it in this research document and do not install it.

## 15. Recommended first ADRs derived from this research

1. **Knowledge ownership and projection boundaries**  
   SQLite vs Markdown vs immutable sources vs derived indexes vs LLM context.

2. **Relationship provenance and promotion**  
   Structural, contextual, and inferred edges; who may create/promote/remove them.

3. **Frontend motion ownership**  
   CSS → Motion → Three.js; GSAP/Anime exceptions; reduced motion and high-frequency rules.

4. **Ion Core architecture spike plan**  
   Renderer candidates, layout candidates, accessibility equivalent, benchmark fixtures, and decision criteria.

5. **Agent task routing contract**  
   Intent, data classes, AI tier, authority, confirmation, output schema, audit, and failure.

6. **External design skill policy**  
   Impeccable as broad process, Emil for motion, Taste for isolated exploration, human review before rules become Ion canon.

7. **External UI reference and copied-component policy**  
   Stable resource IDs, gallery-vs-source boundaries, license checks, retokenization, animation ownership, fallbacks, and provenance.

## 16. Primary references

### Knowledge, memory, and human-AI interaction

- [Andrej Karpathy — LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Obsidian — How data is stored](https://obsidian.md/help/data-storage)
- [Obsidian — Graph view](https://obsidian.md/help/plugins/graph)
- [Obsidian — Properties](https://obsidian.md/help/properties)
- [Obsidian — Internal links](https://obsidian.md/help/links)
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560)
- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)
- [Microsoft Research — GraphRAG](https://www.microsoft.com/en-us/research/project/graphrag/)
- [Microsoft Research — Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [William Jones — The Study and Practice of Personal Information Management](https://dl.acm.org/doi/10.5555/2155696)
- [Benchmarking Long-Term Memory for Personalized Agents](https://arxiv.org/html/2604.20006v1)

### Ingestion, retrieval, graphs, and learning

- [Microsoft MarkItDown](https://github.com/microsoft/markitdown)
- [Tobi QMD](https://github.com/tobi/qmd)
- [Graphify](https://github.com/Graphify-Labs/graphify)
- [CodeCrafters — Build Your Own X](https://github.com/codecrafters-io/build-your-own-x)
- [Three.js documentation](https://threejs.org/docs/)
- [React Three Fiber — Scaling performance](https://r3f.docs.pmnd.rs/advanced/scaling-performance)
- [3D Force Graph](https://github.com/vasturiano/3d-force-graph)
- [Sigma.js](https://www.sigmajs.org/)
- [Cytoscape.js](https://js.cytoscape.org/)

### Motion, design skills, and UI sources

- [Motion for React](https://motion.dev/docs/react)
- [Anime.js](https://animejs.com/)
- [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/)
- [Emil Kowalski — Skills for Designers and Engineers](https://github.com/emilkowalski/skills)
- [Impeccable](https://github.com/pbakaus/impeccable)
- [Taste Skill](https://github.com/Leonxlnx/taste-skill)
- [React Bits](https://reactbits.dev/)
- [React Bits — GitHub repository](https://github.com/DavidHDev/react-bits)
- [React Bits — Color Bends](https://reactbits.dev/backgrounds/color-bends)
- [React Bits — Aurora](https://reactbits.dev/backgrounds/aurora)
- [Kokonut UI](https://kokonutui.com/)
- [Bklit UI](https://github.com/bklit/bklit-ui)
- [Supahero](https://supahero.io/)
- [CTA Gallery](https://www.cta.gallery/)
- [Footer Design](https://www.footer.design/)
- [Manus — Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Manus — Agent Skills](https://manus.im/docs/features/skills)
- [Google — Flow](https://blog.google/innovation-and-ai/products/google-flow-veo-ai-filmmaking-tool/)

## 17. Bottom line

Ion's strongest version is not the one with the most libraries or the most animated particles. It is the one where:

- personal truth has a durable, inspectable owner;
- sources and synthesis remain distinguishable;
- retrieval gets cheaper and better as the knowledge base compounds;
- old memories can be corrected without losing history;
- the assistant turns conversation into trustworthy artifacts and proposals;
- external actions have explicit authority and recovery;
- the Core makes state and connectedness feel tangible without becoming noise;
- the rest of the interface remains calm enough for that Core to matter.

That combination—a disciplined local memory system, a restrained action-oriented assistant, and one unmistakable visual object—is the useful synthesis of the references in this report.
