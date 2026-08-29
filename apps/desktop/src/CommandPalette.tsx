import {
  Dispatch,
  KeyboardEvent,
  SetStateAction,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { CommandItem, searchCommands } from "./commandSearch";

type Props = {
  items: readonly CommandItem[];
  open: boolean;
  stale: boolean;
  onOpenChange: Dispatch<SetStateAction<boolean>>;
  onExecute(item: CommandItem): void;
};

export function CommandPalette({
  items,
  open,
  stale,
  onOpenChange,
  onExecute,
}: Props) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const deferredQuery = useDeferredValue(query);
  const results = useMemo(
    () => searchCommands(items, deferredQuery),
    [deferredQuery, items],
  );
  const selectedIndex = Math.min(activeIndex, Math.max(results.length - 1, 0));

  useEffect(() => {
    const shortcut = (event: globalThis.KeyboardEvent) => {
      if (event.metaKey && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange((current) => !current);
        return;
      }
      if (open && event.key === "Escape") {
        event.preventDefault();
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [onOpenChange, open]);

  useEffect(() => {
    if (!open) return;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setQuery("");
    setActiveIndex(0);
    inputRef.current?.focus();
    return () => previousFocus?.focus();
  }, [open]);

  if (!open) return null;

  function close() {
    onOpenChange(false);
  }

  function execute(item: CommandItem) {
    onExecute(item);
    close();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        results.length ? (current + 1) % results.length : 0,
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) =>
        results.length ? (current - 1 + results.length) % results.length : 0,
      );
      return;
    }
    if (event.key === "Enter" && results[selectedIndex]) {
      event.preventDefault();
      execute(results[selectedIndex]);
    }
  }

  function trapFocus(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(
        'input, button:not([tabindex="-1"])',
      ),
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="command-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) close();
      }}
    >
      <section
        ref={dialogRef}
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby="command-heading"
        onKeyDown={trapFocus}
      >
        <header className="command-header">
          <div>
            <p className="eyebrow">Local command search</p>
            <h2 id="command-heading">Go anywhere</h2>
          </div>
          <div className="command-header-actions">
            <kbd>⌘K</kbd>
            <button type="button" className="command-close" onClick={close}>
              Close
            </button>
          </div>
        </header>
        <input
          ref={inputRef}
          className="command-input"
          type="search"
          role="combobox"
          aria-autocomplete="list"
          aria-controls="command-results"
          aria-expanded="true"
          aria-activedescendant={
            results[selectedIndex]
              ? `command-${results[selectedIndex].id}`
              : undefined
          }
          aria-label="Search commands and records"
          placeholder="Search destinations and records"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={handleKeyDown}
        />
        {stale ? (
          <p className="command-stale" role="status">
            Showing the last confirmed local index.
          </p>
        ) : null}
        <ul id="command-results" className="command-results" role="listbox">
          {results.map((item, index) => (
            <li key={item.id} role="none">
              <button
                id={`command-${item.id}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={index === selectedIndex}
                className={index === selectedIndex ? "is-selected" : ""}
                onMouseMove={() => setActiveIndex(index)}
                onClick={() => execute(item)}
              >
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.description}</small>
                </span>
                <span className="command-open-label">Open</span>
              </button>
            </li>
          ))}
        </ul>
        {!results.length ? (
          <p className="command-empty" role="status">
            No local match. Try a record title or destination.
          </p>
        ) : null}
        <footer className="command-footer">
          <span>↑↓ select</span>
          <span>↵ open</span>
          <span>esc close</span>
        </footer>
      </section>
    </div>
  );
}
