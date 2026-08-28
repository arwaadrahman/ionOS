# Phase 1C — Today

## Objective

Deliver a persistent, execution-oriented Today dashboard over canonical Tasks
without fabricating Calendar or scheduling knowledge.

## Scope

- Canonical `task_day_plans` through migration `0004_today_planning`.
- Direct `priority`, `planned`, and `backup` selection with manual Move Up/Down
  ordering and relation-owned revisions/audit metadata.
- Deterministic Today projection: plan roles, overdue/due/next-seven deadlines,
  Needs Attention, unfinished work from yesterday, and Completed Today.
- Current Mac local-date and IANA-timezone validation with DST-safe deadline
  boundaries and midnight/focus/visibility rehydration.
- Compact Goal/Project context while retaining one canonical Task.
- Fixed authenticated FastAPI and Tauri Today operations.
- A split desktop workspace whose schedule pane explicitly communicates that
  Calendar, occupied time, and available time are unavailable.
- Existing canonical Task complete/reopen operations with separate mutation and
  Today-refresh outcomes.

## Durable behavior

- Today membership is human planning intent, not Task lifecycle or scheduled
  time.
- A Task has at most one plan relation per local civil date.
- Hidden completed/canceled/trashed memberships reserve their historical
  positions; paused Tasks remain visible.
- Completing, reopening, trashing, and restoring a Task never cascade to its
  plan relation.
- Yesterday's incomplete plan is suggested only; adding it today is explicit.
- Past planning rows remain canonical unless explicitly removed.
- Exact deadlines retain their UTC instant and display timezone. Date-only
  deadlines never receive a synthetic time.

## Explicit exclusions

Phase 1C excludes Calendar and Google authentication/sync, CalendarBlock,
appointments, free/busy, scheduling/capacity, automatic carry-forward, AI,
stored urgency, automated task/plan mutation, FocusSession, DailyReview,
WeeklyPlan, Home, command search, menu bar, integrations, mobile, cloud, LAN,
and remote access.

## Acceptance

- Fresh and populated databases migrate exactly from `0003` to `0004` without
  changing organizer/Task rows; downgrade removes only Today planning.
- Today service mutations are revision-aware, transactional, and audited.
- Deadline, attention, local-date, DST, lifecycle, history, and ordering rules
  have deterministic tests.
- Startup mounts non-empty canonical Today state and Today is the initial
  Phase 1C workspace.
- Midnight, focus, visibility, and timezone changes recheck Today without a
  polling scheduler or app restart.
- A confirmed Task mutation is never reported as failed merely because the
  subsequent Today refresh failed.
- Production routes remain authenticated, CORS remains disabled, and the
  renderer receives no origin, port, credential, or generic request primitive.
- Repository validation, frozen sidecar, Tauri build, and packaged startup pass.
