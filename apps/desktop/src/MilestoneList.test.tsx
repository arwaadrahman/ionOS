import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MilestoneList, VisualMilestone } from "./MilestoneList";

afterEach(cleanup);
const first: VisualMilestone = {
  id: "first",
  title: "First",
  state: "in_progress",
  target_date: null,
  position: 0,
  revision: 2,
};
const second: VisualMilestone = {
  id: "second",
  title: "Second",
  state: "in_progress",
  target_date: null,
  position: 1,
  revision: 4,
};

test("keeps canonical order until reorder is confirmed and sends the complete set", async () => {
  let confirm: () => void = () => undefined;
  const response = new Promise<void>((resolve) => {
    confirm = resolve;
  });
  const reorder = vi.fn().mockReturnValue(response);
  const props = {
    label: "Project Milestones",
    items: [first, second],
    trashItems: [],
    currentId: first.id,
    onCreate: vi.fn(),
    onUpdate: vi.fn(),
    onState: vi.fn(),
    onReorder: reorder,
    onTrash: vi.fn(),
    onRestore: vi.fn(),
    onLoadTrash: vi.fn(),
    onError: vi.fn(),
  };
  const { rerender } = render(<MilestoneList {...props} />);
  fireEvent.click(screen.getAllByRole("button", { name: "Move Down" })[0]);
  expect(reorder).toHaveBeenCalledWith([second, first]);
  expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("First");
  confirm();
  await response;
  rerender(
    <MilestoneList {...props} items={[second, first]} currentId={second.id} />,
  );
  await waitFor(() =>
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Second"),
  );
  expect(
    screen
      .getAllByRole("combobox")
      .filter(
        (select) => (select as HTMLSelectElement).value === "in_progress",
      ),
  ).toHaveLength(2);
});

test("routes create, edit, state, Trash, and restore through confirmed callbacks", async () => {
  const onCreate = vi.fn().mockResolvedValue(undefined);
  const onUpdate = vi.fn().mockResolvedValue(undefined);
  const onState = vi.fn().mockResolvedValue(undefined);
  const onTrash = vi.fn().mockResolvedValue(undefined);
  const onRestore = vi.fn().mockResolvedValue(undefined);
  const onLoadTrash = vi.fn().mockResolvedValue(undefined);
  render(
    <MilestoneList
      label="Goal Milestones"
      items={[first]}
      trashItems={[second]}
      onCreate={onCreate}
      onUpdate={onUpdate}
      onState={onState}
      onReorder={vi.fn()}
      onTrash={onTrash}
      onRestore={onRestore}
      onLoadTrash={onLoadTrash}
      onError={vi.fn()}
    />,
  );

  fireEvent.change(
    screen.getByRole("textbox", { name: "Goal Milestones title" }),
    {
      target: { value: "Created" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Add milestone" }));
  await waitFor(() =>
    expect(onCreate).toHaveBeenCalledWith({
      title: "Created",
      target_date: null,
    }),
  );

  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "Goal Milestones title" }),
    {
      target: { value: "Edited" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save milestone" }));
  await waitFor(() =>
    expect(onUpdate).toHaveBeenCalledWith(first, {
      title: "Edited",
      target_date: null,
    }),
  );

  fireEvent.change(screen.getByRole("combobox", { name: "First state" }), {
    target: { value: "achieved" },
  });
  await waitFor(() => expect(onState).toHaveBeenCalledWith(first, "achieved"));
  fireEvent.click(screen.getByRole("button", { name: "Trash" }));
  await waitFor(() => expect(onTrash).toHaveBeenCalledWith(first));

  fireEvent.click(screen.getByRole("button", { name: "Milestone Trash" }));
  await waitFor(() => expect(onLoadTrash).toHaveBeenCalledOnce());
  fireEvent.click(await screen.findByRole("button", { name: "Restore" }));
  await waitFor(() => expect(onRestore).toHaveBeenCalledWith(second));
});
