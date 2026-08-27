# ADR 0002: Public repository data safety

**Status:** Accepted
**Date:** 2026-08-27

## Context

Ion manages private life information, but its repository must be safe to make
public and useful for review.

## Decision

The repository must never contain real personal Ion data. Fixtures, tests,
demos, and screenshots use synthetic records. User databases, vaults,
credentials, tokens, and local runtime state remain outside the repository.

## Consequences

Documentation and tooling must avoid real values. Secrets may not be stored in
source, Git, documentation, or plaintext user records. Future credential
handling is directed to macOS Keychain or an equivalent secure OS facility.

## References

- [Master Specification](../PRODUCT_SPEC.md)
- [Security baseline](../SECURITY.md)
