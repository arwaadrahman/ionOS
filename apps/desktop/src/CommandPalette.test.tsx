import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { CommandPalette } from "./CommandPalette";
import { CommandItem } from "./commandSearch";

const items: CommandItem[] = [
  {
    id: "destination:home",
    label: "Home",
    description: "Open destination",
    category: "destination",
    action: { type: "workspace", workspace: "home" },
    searchText: "home open destination",
  },
  {
    id: "record:project:one",
    label: "Synthetic Project",
    description: "project · active",
    category: "project",
    action: {
      type: "record",
      target: { workspace: "projects", entityType: "project", id: "one" },
    },
    searchText: "synthetic project active",
  },
  {
    id: "record:task:two",
    label: "Synthetic Task",
    description: "task · active",
    category: "task",
    action: {
      type: "record",
      target: { workspace: "tasks", entityType: "task", id: "two" },
    },
    searchText: "synthetic task active",
  },
];

afterEach(cleanup);

function Harness({ onExecute }: { onExecute: (item: CommandItem) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Search
      </button>
      <CommandPalette
        items={items}
        open={open}
        stale={false}
        onOpenChange={setOpen}
        onExecute={onExecute}
      />
    </>
  );
}

test("opens with Command-K and executes the keyboard-selected local result", () => {
  const execute = vi.fn();
  render(<Harness onExecute={execute} />);

  fireEvent.keyDown(window, { key: "k", metaKey: true });
  const input = screen.getByRole("combobox", {
    name: "Search commands and records",
  });
  expect(input).toHaveFocus();
  fireEvent.change(input, { target: { value: "synthetic" } });
  expect(
    screen.getByRole("option", { name: /Synthetic Project/ }),
  ).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(
    screen.getByRole("option", { name: /Synthetic Task/ }),
  ).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(input, { key: "Enter" });

  expect(execute).toHaveBeenCalledWith(items[2]);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("supports visible opening, escape, and a truthful empty state", () => {
  render(<Harness onExecute={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: "Search" });
  trigger.focus();
  fireEvent.click(trigger);
  const input = screen.getByRole("combobox", {
    name: "Search commands and records",
  });
  fireEvent.change(input, { target: { value: "no matching local record" } });
  expect(
    screen.getByText("No local match. Try a record title or destination."),
  ).toBeInTheDocument();
  fireEvent.keyDown(input, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});
