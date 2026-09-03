---
description: Google provider writes cross a fixed trust boundary and a closed cross-layer vocabulary; load the canonical security, architecture, and contract documents before changing them.
paths:
  - "apps/api/ion_api/calendar_write*"
  - "apps/desktop/src-tauri/src/calendar_write.rs"
  - "apps/desktop/src-tauri/src/google_calendar.rs"
  - "apps/desktop/src/calendarWriteContract*"
  - "contracts/**"
---

# Google provider writes

Before changing provider-write code, OAuth, or the write vocabulary:

- **Read `docs/SECURITY.md`.**
- **Read `docs/ARCHITECTURE.md`.**
- **Read the current authorized phase document** under `docs/phases/` and the
  relevant ADR(s).
- **Inspect `contracts/calendar-write-vocabulary.json`** when changing the write
  vocabulary.

After a provider-boundary change, run `scripts/verify/provider-scan.sh`.

Those documents and that contract are the authority. This rule only determines
what you must load and check.
