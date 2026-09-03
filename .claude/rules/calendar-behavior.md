---
description: Calendar interaction behavior is governed by a canonical contract that must be read before changing it.
paths:
  - "docs/CALENDAR_BEHAVIOR.md"
  - "apps/desktop/src/Calendar*"
  - "apps/desktop/src/calendar*"
  - "apps/api/ion_api/calendar*"
---

# Calendar interaction behavior

Before changing any Calendar interaction behavior — editing, moving, resizing,
deleting, recurrence scope, confirmation, synchronization, or error UX:

- **Read `docs/CALENDAR_BEHAVIOR.md` first.**
- Follow it, or update that canonical document in the same approved change.
  Contradicting it without updating it is a defect.
- **Read `docs/DESIGN_SYSTEM.md`** when the task changes Calendar UI or design.

Those documents are the authority. This rule only determines when you must load
them; do not act on a summary of them, including this one.
