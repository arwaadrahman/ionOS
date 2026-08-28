# ADR 0010: Phase 1 organizer domain

**Status:** Accepted
**Date:** 2026-08-27

## Decision

Phase 1A introduces Areas, Goals, Goal Milestones, Projects, Project
Milestones, and Tasks as canonical SQLite records. Areas, Goals, Projects, and
Tasks may exist independently. A Goal optionally belongs to one Area and a
Project optionally belongs to one Goal. Tasks have independently nullable
Goal and Project relationships.

Goal Milestones and Project Milestones use separate tables. Organizer IDs are
lowercase UUIDv4 text created in the trusted Python service. Timestamps are
normalized UTC RFC 3339 text. Tasks preserve `none`, date-only, and exact
instant deadlines without turning date-only deadlines into appointments.

Each concept has its own lifecycle. Goal kinds are limited to outcome, skill,
habit, project, academic, and personal. Today persistence, generic
relationships, and search ranking remain deferred.
