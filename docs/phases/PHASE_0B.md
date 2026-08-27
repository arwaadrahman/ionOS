# Phase 0B — Executable Engineering Foundation

## Objective

Create the smallest executable macOS-local engineering foundation for Ion:
React + TypeScript in Tauri, a loopback-only FastAPI service, SQLite migration
infrastructure, settings, local logging, synthetic fixtures, and documented
quality commands. This is not a product-feature milestone.

## Scope

- npm workspaces and Node 24 LTS policy.
- uv-managed Python 3.13 service tooling.
- Minimal Tauri/React engineering shell and token-only `ion-design` package.
- FastAPI loopback health endpoint, SQLAlchemy Core, Alembic baseline,
  non-secret TOML settings, standard-library local logging, and synthetic
  development/test fixtures.
- JavaScript, Python, and Rust formatting, linting, and automated tests.

## Explicit exclusions

- Phase 1 product UI, records, workflows, or domain tables.
- Integrations, AI, cloud services, authentication platforms, Docker, and
  production Python sidecar packaging.
- Mobile/iOS, synchronization, remote/LAN access, or a cloud relay.
- Real personal data, credentials, and committed runtime databases.

## Local service boundary

FastAPI binds only to `127.0.0.1`. The development port is a non-secret,
configuration-driven setting. Production service lifecycle and local-process
authentication are deferred.

## Acceptance checklist

- [ ] Desktop shell launches and renders a minimal engineering surface.
- [ ] Loopback health endpoint and desktop development health check pass.
- [ ] A fresh user-local database upgrades through Alembic to head.
- [ ] Settings, rotating local logs, and synthetic fixture loading are tested.
- [ ] TypeScript, Python, and Rust quality commands pass.
- [ ] Documentation and ADRs reflect the implementation.

## Decisions

- [ADR 0004](../decisions/0004-macos-local-trust-boundary.md)
- [ADR 0005](../decisions/0005-phase-0b-toolchain-baseline.md)
- [ADR 0006](../decisions/0006-local-api-service-boundary.md)
- [ADR 0007](../decisions/0007-sqlite-access-and-migrations.md)
