# Architecture

## Status

This is a **Baseline** document. It records accepted product principles and
separately labels proposed implementation choices.

## Accepted principles

- Ion is local-first. Its authoritative data lives on the user's Mac; cloud
  services are integrations, not the primary datastore.
- macOS is the active local-only platform. Mobile support is TBD and requires a
  dedicated mobile/security architecture review plus explicit owner approval.
- One canonical record may appear in multiple contextual views. Derived search,
  indexing, and cache structures must be rebuildable.
- Structured records, Markdown knowledge, and original sources have distinct
  owners. An LLM is not a memory system.
- The repository contains only synthetic data and configuration examples; real
  user data remains local and outside the repository.

## Proposed implementation baseline — subject to prototyping

| Concern            | Direction                                                   |
| ------------------ | ----------------------------------------------------------- |
| Desktop UI         | React + TypeScript in Tauri                                 |
| Application logic  | Python + FastAPI                                            |
| Structured records | SQLite                                                      |
| Knowledge          | Obsidian-compatible local Markdown vault                    |
| Future search      | Local text search, then evaluated local retrieval           |
| Future graphics    | One justified Three.js/R3F or suitable custom Core renderer |

## Current boundary

Phase 0B may implement the local development foundation: npm workspace,
Tauri/React shell, loopback-only FastAPI service, SQLite migration mechanism,
settings, logging, quality tooling, and synthetic fixtures. Production Python
sidecar lifecycle, process supervision, local-process authentication, and any
network boundary beyond loopback remain deferred.

## TBD

See ADRs [0004](decisions/0004-macos-local-trust-boundary.md),
[0005](decisions/0005-phase-0b-toolchain-baseline.md),
[0006](decisions/0006-local-api-service-boundary.md), and
[0007](decisions/0007-sqlite-access-and-migrations.md) for accepted Phase 0B
implementation decisions.
