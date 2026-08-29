# Phase 1E — Deterministic Command Search

## Objective

Provide the canonical keyboard-driven command surface for fast local navigation
across the Ion destinations and organizer records already implemented.

## Scope

- A visible command-search trigger and global macOS `⌘K` shortcut.
- Keyboard-complete dialog interaction: type, arrow selection, Enter to open,
  Escape to close, pointer selection, and truthful empty/stale states.
- Five current destinations plus untrashed Areas, Goals, both Milestone types,
  Projects, and Tasks from the existing authenticated Home projection.
- Deterministic Unicode-normalized lexical ranking with a bounded result set
  and stable tie-breaking.
- Direct navigation to canonical record workspaces. Milestones open through
  their canonical Goal or Project owner.
- Background refresh through the existing fixed `get_home` command whenever
  command search opens.

## Durable behavior

- Command items are an in-memory, rebuildable projection. They are not
  canonical records, a search index, a cache, or stored user history.
- Search is entirely local and deterministic. It does not use an LLM,
  embeddings, vectors, semantic similarity, reranking models, or an external
  service.
- Empty search shows only current destinations. Text search covers current
  record labels, type/lifecycle metadata, and existing Today/attention labels.
- Archived and otherwise inactive untrashed records remain discoverable;
  Trash remains excluded from normal command search.
- Opening a result navigates only. Phase 1E adds no record mutation or
  consequential automated action.

## Explicit exclusions

Phase 1E excludes schema migration, SQLite FTS, a persisted index, query or
recent-history storage, fuzzy/semantic retrieval, QMD, AI, Ask Ion,
conversational search, notes/files/knowledge that do not yet exist, generic
backend requests, new renderer authority, new dependencies, Calendar,
integrations, menu-bar search, mobile, cloud, LAN, and remote access.

## Acceptance

- Pure tests prove normalization, deterministic ranking, bounded output,
  destination order, 2,000-record stability, and Milestone-owner routing.
- UI tests prove visible and `⌘K` opening, focus, keyboard selection, direct
  record navigation, Escape, and empty-state behavior.
- Opening command search reuses only the existing fixed authenticated Home
  command, and the renderer receives no origin, port, credential, or generic
  request capability.
- Repository validation, frozen ARM64 sidecar, Tauri production build,
  packaged startup, and clean packaged shutdown pass.
- Owner manually accepts visual placement, keyboard feel, representative
  result truthfulness, and direct navigation in the packaged application.

## Decision

- [ADR 0015](../decisions/0015-deterministic-command-search-projection.md)
