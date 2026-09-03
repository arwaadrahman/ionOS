---
description: These renderer files cross the Tauri trust boundary; load the canonical architecture and security documents before changing what the renderer may invoke or receive.
paths:
  - "apps/desktop/src/calendar.ts"
  - "apps/desktop/src/home.ts"
  - "apps/desktop/src/organizer.ts"
  - "apps/desktop/src/recovery.ts"
  - "apps/desktop/src/tasks.ts"
  - "apps/desktop/src/today.ts"
  - "apps/desktop/src/App.tsx"
  - "apps/desktop/src/OrganizerShell.tsx"
  - "apps/desktop/src/QuickCapture.tsx"
  - "apps/desktop/src/main.tsx"
  - "apps/desktop/src-tauri/src/lib.rs"
  - "apps/desktop/src-tauri/src/service.rs"
  - "apps/desktop/src-tauri/src/organizer.rs"
  - "apps/desktop/src-tauri/src/today.rs"
  - "apps/desktop/src-tauri/src/home.rs"
  - "apps/desktop/src-tauri/capabilities/*.json"
  - "apps/desktop/src-tauri/tauri.conf.json"
---

# Renderer trust boundary

These files define or call the Tauri command bridge — the renderer clients, and
the Rust side that declares commands and registers them in `lib.rs`. Adding or
widening a `#[tauri::command]` is the most direct way to widen renderer
authority. `service.rs` additionally owns the sidecar auth and loopback
boundary. (`calendar_write.rs` and `google_calendar.rs` are covered by
`provider-writes.md`.)

The Tauri capability manifests and `tauri.conf.json` are the declarative half of
the same boundary: widening a capability or relaxing the CSP grants renderer
authority as directly as adding a command.

Before changing what the renderer is permitted to **invoke or receive** across
that boundary:

- **Read `docs/ARCHITECTURE.md`** for the renderer's authority boundary.
- **Read `docs/SECURITY.md`** for what data, credentials, and capabilities may
  cross it.

Ordinary UI presentation is not an authority change; it follows the normal
UI/design context loading.

Those documents are the authority. This rule only determines what you must load.
