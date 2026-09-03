---
description: Schema, migration, and database-resolution changes have canonical owners; load them before changing anything here.
paths:
  - "apps/api/migrations/**"
  - "apps/api/ion_api/schema.py"
  - "apps/api/ion_api/migrations.py"
  - "apps/api/ion_api/settings.py"
  - "apps/api/ion_api/db.py"
---

# Schema, migrations, and database resolution

Before changing a schema or a migration:

- **Read `docs/DATA_MODEL.md`.**
- **Read the current authorized phase document** under `docs/phases/` and the
  relevant ADR(s).

Before changing `settings.py`, `db.py`, or how the runtime resolves its database
path, also **read `docs/ARCHITECTURE.md`** (runtime data location, and the ADRs
it names) and **`docs/SECURITY.md`** (what may live there).

When you change migration or database-resolution behavior, include
`scripts/verify/db-safety.sh` in that change's verification.

Those documents are the authority. This rule only determines what you must load
and check.
