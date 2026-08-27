# Architecture

## Status

This is a **Baseline** document. It records accepted product principles and
separately labels proposed implementation choices.

## Accepted principles

- Ion is local-first. Its authoritative data lives on the user's Mac; cloud
  services are integrations, not the primary datastore.
- macOS is the primary platform; a mobile companion is secondary and deferred.
- One canonical record may appear in multiple contextual views. Derived search,
  indexing, and cache structures must be rebuildable.
- Structured records, Markdown knowledge, and original sources have distinct
  owners. An LLM is not a memory system.
- The repository contains only synthetic data and configuration examples; real
  user data remains local and outside the repository.

## Proposed implementation baseline — subject to prototyping

| Concern | Direction |
| --- | --- |
| Desktop UI | React + TypeScript in Tauri |
| Application logic | Python + FastAPI |
| Structured records | SQLite |
| Knowledge | Obsidian-compatible local Markdown vault |
| Future search | Local text search, then evaluated local retrieval |
| Future graphics | One justified Three.js/R3F or suitable custom Core renderer |

## Current boundary

Phase 0A creates documentation and governance only. No application process,
database, sidecar lifecycle, package workspace, deployment model, or runtime
service is implemented here.

## TBD

The repository has not chosen an ORM, direct SQLite-access pattern, JavaScript
workspace strategy, Python environment tooling, Tauri-to-Python lifecycle,
Python packaging, process supervision, migrations, logging, settings, or test
stack. See the [decision backlog](decisions/README.md#decision-backlog).
