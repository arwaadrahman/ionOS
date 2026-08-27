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
- The active trust boundary is macOS-local. Phase 0B's FastAPI service must
  bind only to `127.0.0.1`, with no intentional LAN or public exposure.
- Mobile support, synchronization, remote access, and cloud relays are
  deferred pending a dedicated mobile/security architecture review.

Phase 0C adds only production local-process authentication: Rust creates a
per-launch 256-bit secret from the OS RNG and owns it in memory. The packaged
Python sidecar receives it only through bounded stdin bootstrap, requires it on
every endpoint with constant-time comparison, and binds its retained socket to
`127.0.0.1:0`. The renderer receives neither secret nor port, and production
does not enable CORS. No persistent credential store is introduced.

## Phase 0B local development details

The local service's development defaults are an explicitly configured loopback
port and these exact origins only: `http://127.0.0.1:1420` and
`http://localhost:1420` for the Vite development server, and
`tauri://localhost` for the Tauri WebView. Wildcard CORS is prohibited. The
default port is not an enduring protocol commitment: it is a non-secret local
setting and can be changed for development.
