import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { CalendarDensity } from "./calendar";
import { CalendarRange, CalendarView } from "./calendarProjection";

const views: { value: CalendarView; label: string; shortLabel: string }[] = [
  { value: "day", label: "Day", shortLabel: "D" },
  { value: "threeDay", label: "3 Day", shortLabel: "3" },
  { value: "week", label: "Week", shortLabel: "W" },
  { value: "next7", label: "Next 7 Days", shortLabel: "7" },
  { value: "month", label: "Month", shortLabel: "M" },
];

const densities: { value: CalendarDensity; label: string }[] = [
  { value: "compact", label: "Compact" },
  { value: "default", label: "Default" },
  { value: "expanded", label: "Expanded" },
];

function SidebarIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" data-icon="sidebar">
      <path d="M2.5 3.25h11M2.5 8h11M2.5 12.75h11" />
    </svg>
  );
}

export function CalendarSidebarToggle({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle(): void;
}) {
  return (
    <button
      className={`calendar-drawer-trigger ${open ? "is-active" : ""}`}
      type="button"
      aria-label="Toggle calendar sidebar"
      title="Calendar sidebar"
      aria-expanded={open}
      onClick={onToggle}
    >
      <SidebarIcon />
    </button>
  );
}

function SyncIcon({ pending }: { pending: boolean }) {
  return (
    <svg
      className={pending ? "is-spinning" : ""}
      viewBox="0 0 16 16"
      aria-hidden="true"
    >
      <path d="M13.25 5.7A5.75 5.75 0 0 0 3.1 4.1L2 5.25M2 2.75v2.5h2.5M2.75 10.3A5.75 5.75 0 0 0 12.9 11.9l1.1-1.15M14 13.25v-2.5h-2.5" />
    </svg>
  );
}

function DensityIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" data-icon="density-spacing">
      <path d="M3 3h10M3 13h10M8 4.5v7M5.8 6.7 8 4.5l2.2 2.2M5.8 9.3 8 11.5l2.2-2.2" />
    </svg>
  );
}

function ViewMenuIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <rect x="2.5" y="3" width="11" height="10" rx="1.25" />
      <path d="M2.5 6h11M6.2 6v7" />
    </svg>
  );
}

function portalPosition(trigger: HTMLElement) {
  const rect = trigger.getBoundingClientRect();
  const width = 144;
  return {
    top: rect.bottom + 6,
    left: Math.max(
      8,
      Math.min(window.innerWidth - width - 8, rect.right - width),
    ),
  };
}

function CalendarToolbarMenu({
  className,
  label,
  children,
  icon,
}: {
  className: string;
  label: string;
  children(close: () => void): ReactNode;
  icon: ReactNode;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const dialogId = useId();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const close = useCallback(() => {
    setOpen(false);
    trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      if (trigger.current) setPosition(portalPosition(trigger.current));
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        !trigger.current?.contains(target) &&
        !popover.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const focusFrame = window.requestAnimationFrame(() => {
      popover.current?.querySelector<HTMLButtonElement>("button")?.focus();
    });
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, {
      capture: true,
      passive: true,
    });
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  return (
    <>
      <button
        ref={trigger}
        className={`calendar-compact-menu ${className}`}
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? dialogId : undefined}
        onClick={() => {
          if (!open && trigger.current) {
            setPosition(portalPosition(trigger.current));
          }
          setOpen((current) => !current);
        }}
      >
        {icon}
      </button>
      {open
        ? createPortal(
            <div
              ref={popover}
              id={dialogId}
              className="calendar-menu-popover calendar-toolbar-popover"
              role="dialog"
              aria-label={`${label} options`}
              data-portal-layer="calendar-toolbar"
              style={position as CSSProperties}
            >
              {children(close)}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

export function CalendarToolbar({
  view,
  range,
  inspectorOpen,
  density,
  syncPending,
  syncDisabled,
  onView,
  onPrevious,
  onToday,
  onNext,
  onSync,
  onDensity,
}: {
  view: CalendarView;
  range: CalendarRange;
  inspectorOpen: boolean;
  density: CalendarDensity;
  syncPending: boolean;
  syncDisabled: boolean;
  onView(view: CalendarView): void;
  onPrevious(): void;
  onToday(): void;
  onNext(): void;
  onSync(): void;
  onDensity(density: CalendarDensity): void;
}) {
  return (
    <div
      className={`calendar-toolbar ${inspectorOpen ? "is-inspector-open" : ""}`}
      aria-label="Calendar controls"
      data-layout="single-row"
    >
      <div className="calendar-toolbar-leading">
        <div className="calendar-navigation" aria-label="Date navigation">
          <button
            className="calendar-nav-arrow"
            type="button"
            aria-label="Previous period"
            title="Previous period"
            onClick={onPrevious}
          >
            ‹
          </button>
          <button type="button" onClick={onToday}>
            Today
          </button>
          <button
            className="calendar-nav-arrow"
            type="button"
            aria-label="Next period"
            title="Next period"
            onClick={onNext}
          >
            ›
          </button>
          <button
            className="calendar-sync-button"
            type="button"
            aria-label={syncPending ? "Syncing calendars" : "Sync calendars"}
            title={syncPending ? "Syncing calendars" : "Sync calendars"}
            disabled={syncDisabled}
            onClick={onSync}
          >
            <SyncIcon pending={syncPending} />
          </button>
        </div>
      </div>
      <h2 aria-live="polite">
        <span className="calendar-range-label-full">{range.label}</span>
        <span className="calendar-range-label-compact" aria-hidden="true">
          {range.compactLabel}
        </span>
      </h2>
      <div className="calendar-toolbar-trailing">
        <CalendarToolbarMenu
          className="calendar-density-menu"
          label="Calendar density"
          icon={<DensityIcon />}
        >
          {(close) =>
            densities.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={density === item.value}
                onClick={() => {
                  onDensity(item.value);
                  close();
                }}
              >
                {item.label}
              </button>
            ))
          }
        </CalendarToolbarMenu>
        <div className="calendar-view-inline" aria-label="Calendar view">
          {views.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-label={`${item.label} view`}
              title={item.label}
              aria-pressed={view === item.value}
              onClick={() => onView(item.value)}
            >
              {item.shortLabel}
            </button>
          ))}
        </div>
        <CalendarToolbarMenu
          className="calendar-view-menu"
          label="Choose calendar view"
          icon={<ViewMenuIcon />}
        >
          {(close) =>
            views.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={view === item.value}
                onClick={() => {
                  onView(item.value);
                  close();
                }}
              >
                {item.label}
              </button>
            ))
          }
        </CalendarToolbarMenu>
      </div>
    </div>
  );
}
