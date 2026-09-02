import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarFilterDrawer } from "./CalendarFilterDrawer";
import { CalendarInspector } from "./CalendarInspector";
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
  calendarFilterCategories,
  calendarSubtypeDefinitions,
  asGoogleError,
  googleCalendarClient,
} from "./calendar";
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
    "That event changed before the category was saved. Reopen it and try again.",
  local_state_not_found: "That saved event is no longer available.",
  connect_required: "Connect Google Calendar before syncing.",
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
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);
  const paneWidthClassRef = useRef<CalendarPaneWidthClass | null>(null);
  const range = useMemo(() => calendarRange(view, anchor), [anchor, view]);
  const projectionIndex = useMemo(
    () => buildCalendarProjectionIndex(status),
    [status],
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
          {feedback}
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
        className={`calendar-interface ${drawerMode ? "" : "is-sidebar-collapsed"} ${selected ? "has-inspector" : ""}`}
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
              inspectorOpen={Boolean(selected)}
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
                    selectedKey={selected?.key ?? null}
                    onSelect={setSelected}
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
                    onSelect={setSelected}
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

            {selected ? (
              <CalendarInspector
                occurrence={selected}
                localTimeZone={localTimeZone}
                categoryPending={pending === `category:${selected.block.id}`}
                onCategory={(category, subtype) =>
                  void run(`category:${selected.block.id}`, () =>
                    googleCalendarClient.setCategory(
                      selected.block,
                      category,
                      subtype,
                    ),
                  )
                }
                onClose={() => setSelected(null)}
              />
            ) : null}
          </div>
        </section>
      </div>
      <p className="calendar-readonly-note">
        Ion reads cached Google Calendar data here. Phase 2B provides no event
        create, edit, move, resize, delete, attendee, reminder, or
        provider-write action.
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
