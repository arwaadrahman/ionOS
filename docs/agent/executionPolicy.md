# Ion Agent Execution Policy

This policy governs implementation and verification work across Ion phases.
The current request, Master Specification, and accepted ADRs remain higher
authorities. Phase documents define scope; this file defines durable execution
behavior inside that scope.

## Autonomous execution

- Inspect existing work before acting and preserve completed work in a dirty
  worktree.
- Diagnose, fix, and verify ordinary in-scope failures autonomously when the
  change is reversible and does not cross an owner-approval boundary.
- Prefer the smallest fix consistent with accepted architecture and update
  relevant tests and behavior documentation with implementation changes.
- Do not broaden a task merely because adjacent cleanup or redesign is
  available. Report unresolved uncertainty rather than silently choosing a new
  product or architecture direction.

## Owner-level stop conditions

Stop and request owner direction before:

- changing canonical requirements, the active phase, major architecture, data
  ownership, or an accepted ADR;
- adding or replacing a dependency, runtime, database, framework, graphics
  engine, AI provider, external integration, or distribution mechanism unless
  the current request and accepted decision explicitly authorize it;
- changing security or privacy posture, authentication, authorization, secret
  handling, the macOS-local trust boundary, or renderer capabilities;
- adding or revising a schema or migration without explicit authorization;
- performing a destructive or difficult-to-recover action, publishing or
  sending externally, or introducing an unapproved external side effect;
- using third-party code or assets when license or attribution is unresolved;
  or
- continuing after evidence reveals a genuine owner-level conflict or blocker.

## Git and database safety

- Begin and end with Git inspection. Preserve unrelated and pre-existing
  changes; never reset, clean, discard, overwrite, or switch away work to make
  a task easier.
- Do not stage unless explicitly requested. Do not commit, push, publish, or
  rewrite history before owner manual acceptance and explicit approval.
  Acceptance approval and commit/push approval are separate authorities.
- Keep runtime databases outside the repository. Never delete, rename, reset,
  migrate, vacuum, or modify a real or owner database unless the request
  explicitly authorizes that exact operation.
- Exercise schema and migration work only against isolated synthetic test
  databases during routine verification. Inspect an existing database
  read-only unless modification is explicitly authorized.
- Treat canonical mutation, revision, lifecycle, audit, and Trash semantics as
  transactional invariants. Do not bypass service ownership with ad hoc writes.

## Phase 0C trust boundary

- Production uses one Rust/Tauri-owned, self-contained Python sidecar. Rust
  owns spawn, bounded readiness, authenticated health checks, exit observation,
  graceful shutdown, and bounded forced cleanup.
- The production service owns an IPv4 `127.0.0.1:0` socket. Rust owns all
  authenticated HTTP calls; the renderer uses fixed Ion-owned commands and
  receives no service origin, port, credential, generic HTTP primitive,
  filesystem access, or shell access.
- Each launch uses an in-memory credential with at least 256 bits from the OS
  cryptographic random source. It crosses only the bounded stdin bootstrap
  channel, is required on every production endpoint, and is never persisted,
  logged, placed in arguments or environment variables, or returned to the
  renderer.
- Production enables no CORS. Development remains loopback-only with only its
  explicitly approved origins.
- Runtime databases, settings, and logs belong in Application Support, never
  the app bundle, repository, or temporary extraction directory. Signing,
  notarization, remote access, mobile, synchronization, and any broader trust
  boundary require their own accepted authorization.

Any implementation that cannot preserve this boundary must stop for owner
review rather than weaken it.

## Canonical mutation and secondary refresh

Once the canonical service confirms a mutation, a later projection, summary,
or workspace refresh failure must not relabel that mutation as failed, retry
it, or apply it again. Preserve the confirmed mutation, retain the last known
projection where available, mark or report the derived view as stale, and make
refresh recovery a separate outcome.

## Repository data safety

- Source, fixtures, tests, screenshots, prompts, examples, documentation, and
  packaged-runtime demonstrations use clearly synthetic data only.
- Never copy real personal data, databases, vault content, private source
  material, secrets, tokens, credentials, keys, or plaintext sensitive records
  into the repository or agent output.
- Test audit records and logs must not contain secret values or payload
  snapshots that could expose private content.

## Validation and packaged-runtime evidence

- Run the narrow checks needed while iterating, then run the repository quality
  gate for an implementation-ready handoff. Report exact commands, results,
  warnings, skipped checks, and environmental limitations.
- Behavior changes require proportionate deterministic tests. Schema work
  requires authorized fresh, upgrade, preservation, and downgrade evidence
  against isolated databases.
- Changes that can affect production packaging, startup, authentication,
  migrations, service lifecycle, or renderer production behavior require the
  self-contained sidecar build, the Tauri production build, and feasible
  packaged launch/quit verification.
- Packaged verification must distinguish automated evidence from human UI
  acceptance. Check readiness, authentication failure paths when relevant,
  loopback listener ownership, shutdown, orphan processes, and temporary
  residue; never fabricate visual or interaction verification.
- A packaged Ion application must not require end-user Python, uv, or
  development tooling.

## Generated-artifact safety

- Keep build outputs, packaged applications, sidecar binaries, runtime
  databases, logs, caches, temporary extraction files, screenshots containing
  private data, and other machine-local artifacts ignored and outside the
  intended commit.
- Do not stage generated artifacts merely because a validation or package build
  created them. Before handoff, inspect `git status --short`, staged changes,
  `git diff --check`, and relevant ignored/tracked paths for accidental runtime,
  private, or generated content.

## Compact final report

Use only applicable sections and keep them evidence-based:

- `RESULT` — pass, readiness state, or genuine blocker.
- `FILES` — changed files and the purpose of each group.
- `DECISIONS / DEVIATIONS` — accepted decisions used, approved deviations, and
  unresolved issues.
- `VALIDATION` — exact automated checks and results.
- `PACKAGE / RUNTIME` — artifact paths and what packaged execution proved.
- `SECURITY / SCOPE` — trust-boundary and exclusion review.
- `GIT STATE` — branch, HEAD, staged/unstaged state, and artifact safety.
- `OWNER CHECKS` — only verification that truly requires human authority or
  interaction.

Do not claim readiness while a required check is failing. End at owner manual
acceptance or a genuine owner-level blocker; do not commit or push without the
separate explicit approval.
