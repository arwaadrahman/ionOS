import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { CalendarFilterDrawer } from "./CalendarFilterDrawer";
import { CalendarInspector } from "./CalendarInspector";
import { CalendarCreatePanel } from "./CalendarCreatePanel";
import { CalendarMonthGrid } from "./CalendarMonthGrid";
import { CalendarSidebar } from "./CalendarSidebar";
import { CalendarTimeGrid } from "./CalendarTimeGrid";
import { CalendarSidebarToggle, CalendarToolbar } from "./CalendarToolbar";
import {
  CalendarStatus,
  CalendarDensity,
  CalendarDrawerMode,
  CalendarCategorySubtype,
  CalendarFilterCategory,
  CalendarCreateDraft,
  CalendarCreateSeed,
  CalendarEditDraft,
  CalendarEditSeed,
  CalendarRecurrenceScope,
  calendarSplitAvailability,
  calendarFilterCategories,
  calendarSubtypeDefinitions,
  asGoogleError,
  googleCalendarClient,
} from "./calendar";
import {
  buildCalendarEditDraft,
  gestureEditValues,
  occurrenceIsFirstInSeries,
} from "./calendarEdits";
import { CalendarRecurrenceScopeDialog } from "./CalendarRecurrenceScopeDialog";
import {
  CalendarOccurrence,
  CalendarPaneWidthClass,
  CalendarView,
  buildCalendarProjectionIndex,
  calendarPaneWidthClass,
  calendarRange,
  localCivilDate,
  navigateCalendarAnchor,
  projectCalendarIndex,
  recommendedCalendarView,
} from "./calendarProjection";

const densityStorageKey = "ion.calendar-density.v1";
// Slow enough to stay near-free while the Calendar is open, quick enough that a
// change made in Google appears without the user reaching for Sync Now.
const AUTOMATIC_SYNC_INTERVAL_MS = 90_000;
const AUTOMATIC_SYNC_MAX_INTERVAL_MS = 15 * 60_000;
const AUTOMATIC_SYNC_MAX_BACKOFF_STEPS = 4;
const sidebarStorageKey = "ion.calendar-sidebar.v1";

function initialDensity(): CalendarDensity {
  try {
    const value = window.localStorage.getItem(densityStorageKey);
    if (value === "compact" || value === "expanded") return value;
  } catch {
    // A blocked preference store falls back to the product default.
  }
  return "default";
}

function initialDrawerMode(): CalendarDrawerMode {
  try {
    const value = window.sessionStorage.getItem(sidebarStorageKey);
    if (value === "calendars") return "calendars";
    if (value === "open" || value === "filters") return "filters";
  } catch {
    // A blocked preference store falls back to the collapsed drawer.
  }
  return null;
}

const errorCopy: Record<string, string> = {
  not_configured:
    "Add the local Google Desktop OAuth configuration, then try again.",
  configuration_invalid: "The local OAuth configuration is invalid.",
  oauth_cancelled:
    "Google authorization was cancelled. No account was connected.",
  oauth_scope_denied: "Both read-only Calendar permissions are required.",
  oauth_state_mismatch:
    "Ion rejected an OAuth callback that did not match this request.",
  reauth_required: "Google Calendar needs to reconnect before it can refresh.",
  busy: "A calendar synchronization is already running.",
  unavailable: "Google Calendar couldn't refresh. Showing saved events.",
  local_service_unavailable:
    "Ion's local calendar service isn't available. Saved events couldn't be changed.",
  local_state_invalid: "That calendar change couldn't be saved.",
  local_state_conflict:
    "That event changed before this update was saved. Reopen it and try again.",
  local_state_not_found: "That saved event is no longer available.",
  connect_required: "Connect Google Calendar before syncing.",
  account_read_only: "Enable Calendar writing for this Google account.",
  access_role_read_only: "Google exposes this calendar as read-only.",
  attendees_present: "Events with attendees remain read-only.",
  calendar_deleted: "This source calendar is no longer available.",
  calendar_disabled: "This calendar is disabled in Ion.",
  create_reconciliation_required:
    "Google must reconcile this pending create before another change.",
  locked_confirmation_required:
    "Confirm the Ion-locked event before saving this change.",
  no_change_requested: "That change did not modify any editable field.",
  no_conflict_to_resolve:
    "This event no longer has an unresolved conflict to resolve.",
  provider_deleted: "This provider event is no longer active.",
  provider_locked: "Google marks this event as provider-locked.",
  provider_unconfirmed: "Google has not confirmed a safe editable version yet.",
  recurrence_identity_unresolved:
    "Ion hasn't confirmed this recurring event's identity yet. Wait for the next sync and try again.",
  recurrence_split_at_first_occurrence:
    "This is the first event in the series, so changing this and following events would change the whole series. Choose All events instead.",
  recurrence_split_unsupported:
    "This series repeats in a pattern Ion can't continue safely, so it can't be split here. Change this event only, or all events.",
  recurrence_unsupported:
    "This recurring-event change isn't supported yet. Try a bounded recurrence preset or a single occurrence instead.",
  special_event: "Google special event types remain read-only.",
  timezone_change_unsupported:
    "This event uses different start and end time zones, which Ion cannot edit directly.",
  write_pending:
    "Another change to this recurring series is still syncing with Google. Wait for it to finish before editing another occurrence.",
  write_slot_unavailable:
    "Ion couldn't get exclusive access to sync with Google right now. Your change is saved locally and will retry.",
};

export function CalendarWorkspace({
  status,
  onStatus,
  now = new Date(),
  localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
}: {
  status: CalendarStatus;
  onStatus: (status: CalendarStatus) => void;
  now?: Date;
  localTimeZone?: string;
}) {
  const today = localCivilDate(localTimeZone, now);
  const [view, setView] = useState<CalendarView>("week");
  const [anchor, setAnchor] = useState(today);
  const [drawerMode, setDrawerMode] =
    useState<CalendarDrawerMode>(initialDrawerMode);
  const [density, setDensity] = useState<CalendarDensity>(initialDensity);
  const [paneWidthClass, setPaneWidthClass] =
    useState<CalendarPaneWidthClass>("wide");
  const [visibleCategories, setVisibleCategories] = useState<
    CalendarFilterCategory[]
  >(() => [...calendarFilterCategories]);
  const [visibleSubtypes, setVisibleSubtypes] = useState<
    CalendarCategorySubtype[]
  >(() => calendarSubtypeDefinitions.map((item) => item.value));
  const [selected, setSelected] = useState<CalendarOccurrence | null>(null);
  const [createSeed, setCreateSeed] = useState<CalendarCreateSeed | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  // Read by the background sync loop, which must not restart on every change.
  const pendingRef = useRef<string | null>(null);
  pendingRef.current = pending;
  // The owner's most recent action, held while an earlier command is in flight.
  const queuedEdit = useRef<{
    draft: CalendarEditDraft;
    undo: CalendarEditDraft | null;
  } | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  // The reverse of the last edit, offered alongside its confirmation.
  const [undoable, setUndoable] = useState<CalendarEditDraft | null>(null);
  // A finished recurring gesture, waiting only on its scope choice.
  const [gestureScope, setGestureScope] = useState<{
    occurrence: CalendarOccurrence;
    seed: CalendarEditSeed;
  } | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);
  const connectedAccounts = status.accounts.filter(
    (item) => item.auth_state === "connected",
  ).length;

  /**
   * Google -> Ion convergence, without the user asking for it.
   *
   * A change made in Google should appear in Ion on its own, so Ion runs the
   * existing bounded incremental sync while the Calendar is actually on screen:
   * once when it opens, again whenever it becomes visible, and then on a slow
   * interval. Work stops entirely while the window is hidden, and each failure
   * widens the gap so an offline or rate-limited provider is not hammered.
   *
   * Sync Now remains available as an explicit refresh; nothing here depends on
   * the user pressing it.
   */
  useEffect(() => {
    if (connectedAccounts === 0) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const hidden = () =>
      typeof document !== "undefined" && document.visibilityState === "hidden";

    const schedule = () => {
      if (disposed || hidden()) return;
      // Back off on repeated failure, bounded so recovery stays timely.
      const delay = Math.min(
        AUTOMATIC_SYNC_INTERVAL_MS * 2 ** failures,
        AUTOMATIC_SYNC_MAX_INTERVAL_MS,
      );
      timer = setTimeout(run, delay);
    };

    const run = async () => {
      if (disposed || hidden()) return;
      // Never contend with a user-initiated command for the provider slot.
      if (pendingRef.current) {
        schedule();
        return;
      }
      try {
        const next = await googleCalendarClient.sync();
        if (disposed) return;
        failures = 0;
        onStatus(next);
      } catch {
        // A refresh the user did not ask for reports nothing; it just waits
        // longer. Genuine problems still surface through explicit actions.
        failures = Math.min(failures + 1, AUTOMATIC_SYNC_MAX_BACKOFF_STEPS);
      }
      schedule();
    };

    const onVisibility = () => {
      if (hidden()) {
        clearTimeout(timer);
        return;
      }
      // Returning to the Calendar is the moment a stale projection is most
      // visible, so refresh immediately rather than waiting out the interval.
      clearTimeout(timer);
      void run();
    };

    void run();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [connectedAccounts, onStatus]);

  // Ion advances waiting writes on its own. When it does, adopt the settled
  // projection instead of leaving the user looking at a superseded state and
  // wondering whether a manual sync is required.
  useEffect(() => {
    let disposed = false;
    let unlisten: UnlistenFn | null = null;
    void listen<CalendarStatus>("ion:calendar-status", ({ payload }) => {
      onStatus(payload);
    })
      .then((registered) => {
        if (disposed) registered();
        else unlisten = registered;
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [onStatus]);

  const paneWidthClassRef = useRef<CalendarPaneWidthClass | null>(null);
  const range = useMemo(() => calendarRange(view, anchor), [anchor, view]);
  const projectionIndex = useMemo(
    () => buildCalendarProjectionIndex(status, localTimeZone),
    [localTimeZone, status],
  );
  const projection = useMemo(
    () => projectCalendarIndex(projectionIndex, range, localTimeZone),
    [localTimeZone, projectionIndex, range],
  );
  const visibleOccurrences = useMemo(
    () =>
      projection.occurrences.filter((occurrence) => {
        if (
          !visibleCategories.includes(
            occurrence.block.category ?? "uncategorized",
          )
        ) {
          return false;
        }
        const subtype = occurrence.block.category_subtype;
        const knownSubtype = calendarSubtypeDefinitions.some(
          (item) => item.value === subtype,
        );
        return (
          !knownSubtype ||
          visibleSubtypes.includes(subtype as CalendarCategorySubtype)
        );
      }),
    [projection.occurrences, visibleCategories, visibleSubtypes],
  );
  const connected = status.accounts.filter(
    (account) => account.auth_state === "connected",
  );
  const enabledCalendars = status.calendars.filter(
    (calendar) =>
      calendar.enabled_in_ion &&
      !calendar.hidden_in_ion &&
      !calendar.provider_deleted,
  );
  const hasProviderRefreshIssue = enabledCalendars.some((calendar) =>
    ["failed", "retry_wait"].includes(calendar.sync_state),
  );
  const needsReauthentication = status.accounts.some(
    (account) => account.auth_state === "reauth_required",
  );
  const eligibleCalendars = status.calendars.filter(
    (calendar) => calendar.provider_write_eligible,
  );

  useEffect(() => {
    if (!selected) return;
    const refreshed = visibleOccurrences.find(
      (occurrence) => occurrence.key === selected.key,
    );
    if (!refreshed) setSelected(null);
    else if (refreshed !== selected) setSelected(refreshed);
  }, [selected, visibleOccurrences]);

  useEffect(() => {
    try {
      window.localStorage.setItem(densityStorageKey, density);
    } catch {
      // The in-memory preference still applies for this mounted workspace.
    }
  }, [density]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        sidebarStorageKey,
        drawerMode ? "open" : "closed",
      );
    } catch {
      // The in-memory disclosure state remains authoritative for this session.
    }
  }, [drawerMode]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const next = calendarPaneWidthClass(entry.contentRect.width);
      const previous = paneWidthClassRef.current;
      if (previous === next) return;
      paneWidthClassRef.current = next;
      setPaneWidthClass(next);
      setView(recommendedCalendarView(next));
      if (previous !== null) setDrawerMode(null);
    });
    observer.observe(stage);
    return () => {
      observer.disconnect();
    };
  }, []);

  const run = useCallback(
    async (label: string, operation: () => Promise<CalendarStatus>) => {
      if (pending) return;
      setPending(label);
      setFeedback(null);
      setUndoable(null);
      try {
        onStatus(await operation());
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending],
  );

  const connect = useCallback(async () => {
    if (pending) return;
    setPending("connect");
    setFeedback(null);
    setUndoable(null);
    try {
      onStatus(await googleCalendarClient.connect());
      setPending("sync");
      onStatus(await googleCalendarClient.sync());
    } catch (reason) {
      const error = asGoogleError(reason);
      setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
    } finally {
      setPending(null);
    }
  }, [onStatus, pending]);

  const enableWrites = useCallback(
    async (
      account: Parameters<typeof googleCalendarClient.enableWrites>[0],
    ) => {
      if (pending) return;
      setPending(`write-access:${account.id}`);
      setFeedback(null);
      setUndoable(null);
      try {
        onStatus(await googleCalendarClient.enableWrites(account));
        setFeedback(
          "Calendar writing is enabled for eligible attendee-free events in this account.",
        );
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending],
  );

  const openCreate = useCallback(
    (seed: CalendarCreateSeed) => {
      if (eligibleCalendars.length === 0) {
        setFeedback(
          "Enable Calendar writing for an account with an active writer or owner calendar before creating an event.",
        );
        setDrawerMode("calendars");
        return;
      }
      setSelected(null);
      setFeedback(null);
      setUndoable(null);
      setCreateSeed(seed);
    },
    [eligibleCalendars.length],
  );

  const createEvent = useCallback(
    async (draft: CalendarCreateDraft) => {
      if (pending) return;
      setPending("create");
      setFeedback(null);
      setUndoable(null);
      const previousIds = new Set(status.blocks.map((block) => block.id));
      try {
        const next = await googleCalendarClient.create(draft);
        onStatus(next);
        setCreateSeed(null);
        const block = next.blocks.find((item) => !previousIds.has(item.id));
        if (block?.provider_write_state === "synced") {
          setFeedback("Event created");
        } else if (block?.provider_write_detail === "reauth_required") {
          setFeedback("Saved in Ion. Reconnect Google to finish syncing it.");
        } else if (block?.provider_write_state === "failed") {
          setFeedback(
            "Saved in Ion, but Google rejected the new event. Its status stays on the event.",
          );
        } else {
          setFeedback("Event created · saving…");
        }
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending, status.blocks],
  );

  const editEvent = useCallback(
    async (draft: CalendarEditDraft, undo: CalendarEditDraft | null = null) => {
      // A gesture arriving while a previous command is still outstanding must
      // not be dropped -- that would silently lose the owner's most recent
      // action, which is the one they meant. Hold the newest and send it when
      // the current command returns; an older held gesture is already obsolete,
      // so the newest simply replaces it.
      if (pending) {
        queuedEdit.current = { draft, undo };
        return;
      }
      setPending(`edit:${draft.calendar_block_id}`);
      setFeedback(null);
      setUndoable(null);
      try {
        const next = await googleCalendarClient.edit(draft);
        onStatus(next);
        const block =
          next.blocks.find((item) => item.id === draft.calendar_block_id) ??
          next.blocks.find(
            (item) =>
              item.provider_write_operation === "patch" &&
              item.provider_write_recurrence_scope === draft.recurrence_scope,
          );
        // The Calendar itself already shows the result, so a healthy write says
        // only that it landed. Longer copy is reserved for the states where the
        // user genuinely has something to decide.
        const action =
          draft.edit_kind === "move" ? "Event moved" : "Event updated";
        if (block?.provider_write_state === "synced") {
          setFeedback(action);
        } else if (block?.provider_write_detail === "reauth_required") {
          setFeedback("Saved in Ion. Reconnect Google to finish syncing it.");
        } else if (block?.provider_write_state === "conflict") {
          setFeedback(
            "Ion couldn't finish this change automatically. Open the event to see what's needed.",
          );
        } else if (block?.provider_write_state === "failed") {
          setFeedback(
            "Saved in Ion, but Google rejected the change. Your intended value is still shown.",
          );
        } else {
          // Still in flight. Ion finishes this on its own.
          setFeedback(`${action} · saving…`);
        }
        // Undo is an ordinary reverse edit, so it needs the revision this
        // change produced. Without a settled block there is nothing truthful
        // to aim it at, and no Undo is offered.
        if (undo && block) {
          setUndoable({ ...undo, expected_block_revision: block.revision });
        }
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending],
  );

  // Send whatever the owner did while a command was in flight, once it is no
  // longer. This runs after the render that clears `pending`, so the callback
  // it calls sees an idle workspace rather than re-queueing against a stale
  // closure.
  useEffect(() => {
    if (pending) return;
    const held = queuedEdit.current;
    if (!held) return;
    queuedEdit.current = null;
    void editEvent(held.draft, held.undo);
  }, [editEvent, pending]);

  /**
   * A direct drag or resize commits at drop, the way Google's does.
   *
   * The gesture already expressed the whole intent, so there is nothing left to
   * review: Ion builds the same draft an Inspector Save would produce and
   * dispatches it. A recurring event asks for scope first, because scope is the
   * one thing the gesture genuinely did not say -- and that choice is then the
   * last action the user takes.
   */
  const commitGestureWithScope = useCallback(
    (
      occurrence: CalendarOccurrence,
      seed: CalendarEditSeed,
      scope: "single" | CalendarRecurrenceScope,
      seriesConfirmed: boolean,
    ) => {
      const timezone = occurrence.block.start_timezone ?? localTimeZone;
      const { proposed, previous } = gestureEditValues(
        occurrence,
        seed,
        timezone,
      );
      const shared = {
        occurrence,
        editKind: seed.editKind,
        resizeEdge: seed.resizeEdge,
        scope,
        seriesConfirmed,
        sourceTimeZone: occurrence.block.start_timezone,
      } as const;
      void editEvent(
        buildCalendarEditDraft({
          ...shared,
          values: proposed,
          commandId: crypto.randomUUID(),
        }),
        // Reversing a split would split again rather than rejoin, so a gesture
        // resolved that way is not offered back as Undo.
        scope === "this_and_following"
          ? null
          : buildCalendarEditDraft({
              ...shared,
              values: previous,
              commandId: crypto.randomUUID(),
            }),
      );
    },
    [editEvent, localTimeZone],
  );

  const commitGesture = useCallback(
    (occurrence: CalendarOccurrence, seed: CalendarEditSeed) => {
      setSelected(occurrence);
      if (occurrence.block.recurrence_kind === "single") {
        commitGestureWithScope(occurrence, seed, "single", false);
        return;
      }
      setGestureScope({ occurrence, seed });
    },
    [commitGestureWithScope],
  );

  const deleteEvent = useCallback(
    async (draft: Parameters<typeof googleCalendarClient.delete>[0]) => {
      if (pending) return;
      setPending(`delete:${draft.calendar_block_id}`);
      setFeedback(null);
      setUndoable(null);
      try {
        const next = await googleCalendarClient.delete(draft);
        onStatus(next);
        const expectedOperation =
          draft.recurrence_scope === "occurrence"
            ? "cancel_occurrence"
            : draft.recurrence_scope === "series"
              ? "delete_series"
              : "delete_event";
        const block =
          next.blocks.find((item) => item.id === draft.calendar_block_id) ??
          next.blocks.find(
            (item) => item.provider_write_operation === expectedOperation,
          );
        if (!block || block.status === "cancelled") {
          setFeedback("Event deletion is complete.");
          setSelected(null);
        } else if (block.provider_write_detail === "reauth_required") {
          setFeedback("Deletion saved locally. Reconnect Google to finish it.");
        } else if (block.provider_write_state === "conflict") {
          setFeedback(
            "Ion couldn't finish this deletion automatically. Open the event to see what's needed.",
          );
        } else if (block.provider_write_state === "failed") {
          setFeedback(
            "Deletion remains saved locally, but Google synchronization failed.",
          );
        } else {
          setFeedback(
            "Deletion saved locally and pending Google confirmation.",
          );
        }
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending],
  );

  const keepGoogleVersion = useCallback(
    async (
      draft: Parameters<typeof googleCalendarClient.keepGoogleVersion>[0],
    ) => {
      if (pending) return;
      setPending(`keep-google:${draft.calendar_block_id}`);
      setFeedback(null);
      setUndoable(null);
      try {
        const next = await googleCalendarClient.keepGoogleVersion(draft);
        const before = status.blocks.find(
          (item) => item.id === draft.calendar_block_id,
        );
        onStatus(next);
        setFeedback(
          before?.provider_write_state === "failed"
            ? "Your pending change was discarded. This event now shows Google's current version."
            : "Kept Google's version. Your pending change to this field was discarded.",
        );
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending, status.blocks],
  );

  const applyIonChanges = useCallback(
    async (
      draft: Parameters<typeof googleCalendarClient.applyIonChanges>[0],
    ) => {
      if (pending) return;
      setPending(`apply-ion:${draft.calendar_block_id}`);
      setFeedback(null);
      setUndoable(null);
      try {
        const next = await googleCalendarClient.applyIonChanges(draft);
        onStatus(next);
        // Report what actually happened. Dispatch runs inside this command,
        // so an unconditional "applying..." message left the surface looking
        // stuck even after the write had already confirmed, failed, or
        // re-conflicted.
        const block = next.blocks.find(
          (item) => item.id === draft.calendar_block_id,
        );
        if (block?.provider_write_state === "synced") {
          setFeedback("Your Ion change is now confirmed by Google.");
        } else if (block?.provider_write_state === "conflict") {
          setFeedback(
            "Google changed this event again. Review the differences once more before applying.",
          );
        } else if (block?.provider_write_detail === "reauth_required") {
          setFeedback(
            "Your Ion change is queued. Reconnect Google to finish applying it.",
          );
        } else if (block?.provider_write_state === "failed") {
          setFeedback(
            "Google rejected your Ion change. Its status remains visible on the event.",
          );
        } else {
          setFeedback(
            "Your Ion change was re-authorized against Google's latest version and is pending confirmation.",
          );
        }
      } catch (reason) {
        const error = asGoogleError(reason);
        setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
      } finally {
        setPending(null);
      }
    },
    [onStatus, pending],
  );

  const toggleCategory = useCallback(
    (category: CalendarFilterCategory, visible: boolean) => {
      setVisibleCategories((current) =>
        visible
          ? current.includes(category)
            ? current
            : [...current, category]
          : current.filter((item) => item !== category),
      );
    },
    [],
  );
  const toggleSubtype = useCallback(
    (subtype: CalendarCategorySubtype, visible: boolean) => {
      setVisibleSubtypes((current) =>
        visible
          ? current.includes(subtype)
            ? current
            : [...current, subtype]
          : current.filter((item) => item !== subtype),
      );
    },
    [],
  );

  const toggleCalendar = useCallback(
    (
      calendar: Parameters<typeof googleCalendarClient.setEnabled>[0],
      enabled: boolean,
    ) =>
      void run(`selection:${calendar.id}`, () =>
        googleCalendarClient.setEnabled(calendar, enabled),
      ),
    [run],
  );
  const setCalendarHidden = useCallback(
    (
      calendar: Parameters<typeof googleCalendarClient.setHidden>[0],
      hidden: boolean,
    ) =>
      void run(`visibility:${calendar.id}`, () =>
        googleCalendarClient.setHidden(calendar, hidden),
      ),
    [run],
  );
  const disconnect = useCallback(
    (account: Parameters<typeof googleCalendarClient.disconnect>[0]) =>
      void run(`disconnect:${account.id}`, () =>
        googleCalendarClient.disconnect(account),
      ),
    [run],
  );

  return (
    <section className="workspace calendar-workspace" aria-label="Calendar">
      {!status.configured ? (
        <div className="notice notice--warning" role="status">
          <strong>Local OAuth configuration required.</strong>
          <span>
            Create{" "}
            <code>{status.configuration_path || "google-oauth.json"}</code> with
            a Google Desktop OAuth <code>client_id</code> and optional{" "}
            <code>client_secret</code>. Credentials remain outside Git. Ion
            requests only <code>calendarlist.readonly</code> and{" "}
            <code>calendar.events.readonly</code> access.
          </span>
        </div>
      ) : null}
      {feedback ? (
        <p className="notice notice--warning" role="alert">
          <span>{feedback}</span>
          {undoable ? (
            <button
              className="quiet-button"
              type="button"
              disabled={Boolean(pending)}
              onClick={() => {
                const draft = { ...undoable, command_id: crypto.randomUUID() };
                setUndoable(null);
                void editEvent(draft);
              }}
            >
              Undo
            </button>
          ) : null}
        </p>
      ) : null}
      {needsReauthentication ? (
        <div
          className="calendar-cache-status calendar-reauth-status"
          role="status"
        >
          <span>
            Google Calendar needs to reconnect.
            {status.blocks.length > 0 ? " Showing saved events." : ""}
          </span>
          <button type="button" onClick={() => setDrawerMode("calendars")}>
            Open calendars
          </button>
        </div>
      ) : hasProviderRefreshIssue && status.blocks.length > 0 ? (
        <p className="calendar-cache-status" role="status">
          Some calendars couldn't refresh. Showing saved events.
        </p>
      ) : null}
      {projection.limited ? (
        <p className="calendar-cache-status" role="status">
          This visible range reached the bounded recurrence projection limit.
        </p>
      ) : null}

      <div
        className={`calendar-interface ${drawerMode ? "" : "is-sidebar-collapsed"} ${selected || createSeed ? "has-inspector" : ""}`}
      >
        {drawerMode ? (
          <aside className="calendar-sidebar" aria-label="Calendar sidebar">
            <div className="calendar-drawer-header">
              <CalendarSidebarToggle
                open
                onToggle={() => setDrawerMode(null)}
              />
              <div
                className="calendar-drawer-tabs"
                role="tablist"
                aria-label="Sidebar mode"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={drawerMode === "filters"}
                  onClick={() => setDrawerMode("filters")}
                >
                  Filter
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={drawerMode === "calendars"}
                  onClick={() => setDrawerMode("calendars")}
                >
                  Calendars
                </button>
              </div>
            </div>
            {drawerMode === "calendars" ? (
              <CalendarSidebar
                status={status}
                pending={pending}
                onConnect={() => void connect()}
                onEnableWrites={(account) => void enableWrites(account)}
                onToggle={toggleCalendar}
                onHidden={setCalendarHidden}
                onDisconnect={disconnect}
              />
            ) : (
              <CalendarFilterDrawer
                visibleCategories={visibleCategories}
                visibleSubtypes={visibleSubtypes}
                onCategory={toggleCategory}
                onSubtype={toggleSubtype}
              />
            )}
          </aside>
        ) : null}

        <section
          className="calendar-pane"
          aria-label="Calendar pane"
          data-pane-width-class={paneWidthClass}
        >
          <div className="calendar-pane-header">
            {!drawerMode ? (
              <CalendarSidebarToggle
                open={false}
                onToggle={() => setDrawerMode("filters")}
              />
            ) : null}
            <CalendarToolbar
              view={view}
              range={range}
              inspectorOpen={Boolean(selected || createSeed)}
              density={density}
              syncPending={pending === "sync"}
              syncDisabled={Boolean(pending)}
              onView={setView}
              onPrevious={() =>
                setAnchor((current) =>
                  navigateCalendarAnchor(view, current, -1),
                )
              }
              onToday={() => setAnchor(today)}
              onNext={() =>
                setAnchor((current) => navigateCalendarAnchor(view, current, 1))
              }
              onSync={() => {
                if (connected.length === 0) {
                  setFeedback(
                    needsReauthentication
                      ? errorCopy.reauth_required
                      : errorCopy.connect_required,
                  );
                  setDrawerMode("calendars");
                  return;
                }
                void run("sync", googleCalendarClient.sync);
              }}
              onDensity={setDensity}
            />
          </div>

          <div className="calendar-pane-content">
            <main
              ref={stageRef}
              className="calendar-stage"
              tabIndex={0}
              aria-label="Calendar canvas"
            >
              <div className="calendar-content-surface">
                {enabledCalendars.length === 0 ? (
                  <div className="calendar-view-empty">
                    <h2>No visible calendars</h2>
                    <p>
                      Open Calendars to enable or restore an event-readable
                      calendar, or connect another account. Cached data remains
                      local.
                    </p>
                  </div>
                ) : view === "month" ? (
                  <CalendarMonthGrid
                    range={range}
                    anchor={anchor}
                    occurrences={visibleOccurrences}
                    localTimeZone={localTimeZone}
                    today={today}
                    onSelect={(occurrence) => {
                      setSelected(occurrence);
                    }}
                    onCreate={openCreate}
                  />
                ) : (
                  <CalendarTimeGrid
                    range={range}
                    occurrences={visibleOccurrences}
                    localTimeZone={localTimeZone}
                    today={today}
                    now={now}
                    density={density}
                    selectedKey={selected?.key ?? null}
                    onSelect={(occurrence) => {
                      setSelected(occurrence);
                    }}
                    onCreate={openCreate}
                    onEditSeed={(occurrence, seed) => {
                      setCreateSeed(null);
                      commitGesture(occurrence, seed);
                    }}
                  />
                )}
                {enabledCalendars.length > 0 &&
                visibleOccurrences.length === 0 ? (
                  <p className="calendar-range-empty">
                    No events in this range.
                  </p>
                ) : null}
              </div>
            </main>

            {gestureScope ? (
              <CalendarRecurrenceScopeDialog
                mode="edit"
                eventTitle={gestureScope.occurrence.block.title}
                splitAvailable={
                  calendarSplitAvailability(
                    gestureScope.occurrence.block,
                    occurrenceIsFirstInSeries(gestureScope.occurrence),
                  ).available
                }
                splitUnavailableReason={
                  calendarSplitAvailability(
                    gestureScope.occurrence.block,
                    occurrenceIsFirstInSeries(gestureScope.occurrence),
                  ).reason
                }
                pending={Boolean(pending)}
                // Cancelling restores the original position by writing nothing:
                // the grid still renders confirmed state until a write lands.
                onCancel={() => setGestureScope(null)}
                onChoose={(scope, seriesConfirmed) => {
                  const { occurrence, seed } = gestureScope;
                  setGestureScope(null);
                  commitGestureWithScope(
                    occurrence,
                    seed,
                    scope,
                    seriesConfirmed,
                  );
                }}
              />
            ) : null}
            {createSeed ? (
              <CalendarCreatePanel
                seed={createSeed}
                calendars={eligibleCalendars}
                localTimeZone={localTimeZone}
                pending={pending === "create"}
                onSubmit={(draft) => void createEvent(draft)}
                onClose={() => setCreateSeed(null)}
              />
            ) : selected ? (
              <CalendarInspector
                occurrence={selected}
                localTimeZone={localTimeZone}
                categoryPending={pending === `category:${selected.block.id}`}
                editPending={pending === `edit:${selected.block.id}`}
                deletePending={pending === `delete:${selected.block.id}`}
                onCategory={(category, subtype) =>
                  void run(`category:${selected.block.id}`, () =>
                    googleCalendarClient.setCategory(
                      selected.block,
                      category,
                      subtype,
                    ),
                  )
                }
                onEdit={(draft, undo) => void editEvent(draft, undo)}
                onDelete={(draft) => void deleteEvent(draft)}
                keepGooglePending={
                  pending === `keep-google:${selected.block.id}`
                }
                applyIonPending={pending === `apply-ion:${selected.block.id}`}
                onKeepGoogleVersion={(draft) => void keepGoogleVersion(draft)}
                onApplyIonChanges={(draft) => void applyIonChanges(draft)}
                onClose={() => {
                  setSelected(null);
                }}
              />
            ) : null}
          </div>
        </section>
      </div>
      <p className="calendar-readonly-note">
        Eligible attendee-free events support explicit edit, move, resize,
        bounded recurrence presets, one-occurrence cancellation, and confirmed
        whole-series deletion after write consent. This-and-following,
        attendees, reminders, attachments, conferencing, and cross-calendar
        mutation remain unavailable.
      </p>
      {connected.length === 0 &&
      !needsReauthentication &&
      status.blocks.length > 0 ? (
        <p className="calendar-cache-status">
          Google Calendar isn't connected. Showing saved events.
        </p>
      ) : null}
    </section>
  );
}
