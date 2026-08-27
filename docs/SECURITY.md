# Security and Privacy Baseline

## Status

**Accepted invariants; implementation deferred.**

- Ion is local-first. The public repository contains no real personal Ion data.
- Tests, demos, screenshots, and fixtures use clearly synthetic records only.
- Real user databases, vaults, local runtime state, and private source content
  remain outside the repository.
- Credentials, API keys, tokens, passwords, private keys, and banking or other
  sensitive data must never appear in source, Git, documentation, or plaintext
  user records.
- Future credentials belong in macOS Keychain or an equivalent secure OS store;
  this milestone does not implement credential storage.
- Major security/privacy, data-ownership, authentication, or authorization
  changes require owner approval and an ADR where lasting.

Phase 0A does not implement authentication, secret scanning, encryption,
credential storage, API authentication, or integration security.
