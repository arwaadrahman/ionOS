# ADR 0001: Local-first data ownership

**Status:** Accepted
**Date:** 2026-08-27

## Context

Ion is a private personal operating system. Its data model requires durable,
inspectable ownership rather than a cloud service or model context acting as
the source of truth.

## Decision

Ion is local-first: authoritative Ion data lives on the user's Mac. SQLite is
the proposed owner for canonical structured records; Markdown owns durable
prose knowledge; original source files are immutable evidence; derived indexes
are rebuildable. LLM context is never canonical memory.

## Consequences

Cloud services are integrations, not Ion's primary datastore. Future retrieval,
AI, and projection work must preserve provenance and reconstructibility.
Implementation details remain subject to later ADRs.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Data model principles](../DATA_MODEL.md)
