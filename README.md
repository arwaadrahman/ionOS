# Ion OS

Ion OS is a private, local-first personal operating system for reducing
administrative overhead while preserving user control. Its primary platform is
macOS; a mobile companion is planned later.

## Status

Current phase: **Phase 0 — Repository + Engineering Foundation**
Current milestone: **Phase 0A — Documentation and governance bootstrap**

No executable application functionality exists yet. The proposed direction is
React + TypeScript in Tauri, with Python + FastAPI application logic, SQLite
for structured records, and an Obsidian-compatible Markdown knowledge layer.
Those implementation choices remain subject to prototyping.

## Start here

- [Agent guide](AGENTS.md)
- [Project context](docs/projectContext.md)
- [Master Specification](docs/PRODUCT_SPEC.md)
- [Phase 0A](docs/phases/PHASE_0A.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision index](docs/decisions/README.md)

The Master Specification is canonical. Accepted ADRs and repository-local
documentation govern implementation; research and reference cards are
supporting context.

## Privacy

This public repository must never contain real personal Ion data, local user
databases, vault content, or credentials. Any future fixtures, demos, and
screenshots must be synthetic.

Next: Phase 0B will choose and scaffold the executable engineering workspace.
