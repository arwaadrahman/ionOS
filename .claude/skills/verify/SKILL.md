---
name: verify
description: Verify an Ion change before reporting it as ready. Runs focused and full checks, inspects the actual diff and new file contents, checks whether tests were weakened, audits artifact and production-data safety, and produces an evidence-based report. Use after implementing anything, and before claiming readiness or requesting owner acceptance.
---

# Verify an Ion change

Automated checks decide nothing on their own. They tell you where to look. **You
must read the actual change** and judge whether it does what it claims without
weakening what the tests prove.

Run from the repository root. Each script takes an optional base ref (default
`HEAD`); pass a commit to verify a whole branch of work.

## Procedure

1. **Checks** — `scripts/verify/run-checks.sh [base]`
   Runs focused checks for the changed areas, then `npm run validate`. It runs
   everything even after a failure so you get complete evidence, and exits
   nonzero if any check failed.

2. **Read the actual change** — `git diff [base]` and `git status --short`.
   Read every tracked hunk **and the contents of every relevant untracked
   file**. `git diff` shows nothing for new files, so a status listing is not
   semantic review: open new source, test, config, and security files and
   inspect what they actually do. Confirm every file belongs to the task and
   that nothing unrelated rode along.

3. **Hygiene and artifacts** — `scripts/verify/diff-audit.sh [base]`
   `PASS WITH SIGNALS` still requires review — it never means "nothing to look
   at". Confirm each untracked file is intended _and_ read it.

4. **Test integrity** — `scripts/verify/test-integrity.sh [base]`
   Then **read the tests yourself**: both changed hunks in tracked test files
   and the full contents of any new untracked test file. The script counts
   tests, assertions, and skip markers; an assertion can be loosened without
   moving any count, so a silent run proves nothing. Ask: does each test still
   fail if the behavior it covers regresses?

5. **Provider boundary** — `scripts/verify/provider-scan.sh`
   Run whenever Rust, `ion_api`, renderer, or `contracts/` code changed.

6. **Production data** — `scripts/verify/db-safety.sh`
   Only meaningful if an Ion writer or runtime entrypoint was run. `NOT SAFE`
   with no runtime work is expected and harmless; `NOT SAFE` after runtime work
   is a hard blocker.

## Exit codes

|     |                                                                 |
| --- | --------------------------------------------------------------- |
| `0` | ran successfully; advisory signals may still need review        |
| `1` | a real failure or boundary violation                            |
| `2` | the check could not run reliably — never report a pass on a `2` |

A `2` means the evidence is missing, not that the code is fine.

## Report

Use only the applicable sections, and quote real output:

- **RESULT** — pass, readiness state, or genuine blocker
- **FILES** — changed files and the purpose of each group
- **DECISIONS / DEVIATIONS** — decisions used, approved deviations, open issues
- **VALIDATION** — exact commands and their results
- **PACKAGE / RUNTIME** — artifact paths and what packaged execution actually
  proved. Required when the change can affect packaging, startup,
  authentication, migrations, service lifecycle, or renderer production
  behavior (AGENTS.md item 7). Keep automated evidence strictly separate from
  owner acceptance, and never state visual or interaction verification that a
  human did not perform.
- **SECURITY / SCOPE** — boundary review and what stayed out of scope
- **GIT STATE** — branch, HEAD, staged/unstaged state, artifact safety
- **OWNER CHECKS** — only what genuinely needs human judgement

Never report readiness while a required check is failing or returned `2`.
Verification is not owner acceptance, and acceptance is not authorization to
commit or push — each is separate.
