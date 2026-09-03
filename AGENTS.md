# Ion OS Agent Guide

Tool-agnostic repository policy. Every coding agent follows it. Tool-specific
guidance lives elsewhere and never overrides this file.

1. **Authority order:** the current owner request; `docs/PRODUCT_SPEC.md` (its
   appended owner amendments override its preserved source transcription);
   accepted ADRs in `docs/decisions/`; local implementation context; the
   approved reference snapshot. For Calendar _interaction detail_,
   `docs/CALENDAR_BEHAVIOR.md` governs. Never silently resolve a conflict
   between these — surface it.
2. `docs/PRODUCT_SPEC.md` is the only Master Specification. Untracked bootstrap
   or transcription artifacts outside `docs/` are never authority.
3. Work only inside the currently authorized phase, milestone, and scope, which
   `docs/projectContext.md` records. Do not broaden a task because adjacent
   cleanup is available. Within that scope, diagnose, fix, and verify ordinary
   failures autonomously when the change is reversible. Prefer the smallest
   change consistent with accepted architecture, and update tests and behavior
   documentation in the same pass. A behavior change requires proportionate
   deterministic tests.
4. Do not silently change architecture, security or privacy posture, data
   ownership, the macOS-local trust boundary, dependencies, schemas, migrations,
   or an accepted ADR. Propose and get owner approval first.
5. Stop and ask before a destructive or difficult-to-recover action, before
   publishing or sending anything externally or creating any other external side
   effect, and before using third-party code or assets whose license or
   attribution is unresolved.
6. Before changing Calendar interaction behavior — editing, moving, resizing,
   deleting, recurrence scope, confirmation, synchronization, or error UX — read
   `docs/CALENDAR_BEHAVIOR.md` and either follow it or extend it in the same
   change. Contradicting it without updating it is a defect.
7. Changes that can affect production packaging, startup, authentication,
   migrations, service lifecycle, or renderer production behavior require a
   fresh sidecar build, a production Tauri build, and packaged launch/quit
   verification. Schema work requires fresh, upgrade, preservation, and
   downgrade evidence against isolated databases. Never fabricate visual or
   interaction verification, and keep automated evidence distinct from human UI
   acceptance. A packaged Ion application must not require end-user Python, uv,
   or development tooling.
8. Never commit real personal data, secrets, tokens, credentials, or private
   source material, and never place them in agent output. Fixtures, tests,
   screenshots, prompts, and documentation use clearly synthetic data only.
   Audit records and logs must not contain secret values or payload snapshots.
9. Runtime databases, logs, and vaults live outside the repository. Do not
   modify a real or owner database unless the request authorizes that exact
   operation; inspect read-only otherwise.
10. Record durable accepted decisions in canonical tracked docs or an ADR — not
    in chat history, and not in a machine-local file.
11. **Automated verification is not owner acceptance.** Passing checks means the
    code is ready to be judged, never that it is accepted.
12. **Owner acceptance is not commit authorization.** Commit, push, and history
    changes each require their own explicit approval.
13. Do not stage unless explicitly requested. Staging is a step toward a commit,
    which is separately authorized.
14. Report changed files, decisions and deviations, verification actually run,
    unresolved issues, and anything needing human judgement.
