import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { RecoveryWorkspace } from "./RecoveryWorkspace";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const item = {
  entity_type: "task" as const,
  entity_id: "11111111-1111-4111-8111-111111111111",
  label: "Synthetic recovery task",
  lifecycle: "open",
  revision: 3,
  trashed_at: "2030-01-01T00:00:00Z",
  owner_label: null,
};

test("restores through the existing entity-specific Task command", async () => {
  const refreshed = vi.fn(async () => undefined);
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_recovery") {
      return {
        trash: [item],
        recent_activity: [
          {
            event_id: "22222222-2222-4222-8222-222222222222",
            occurred_at: item.trashed_at,
            entity_type: "task",
            entity_id: item.entity_id,
            label: item.label,
            action: "trashed",
            authority: "direct",
          },
        ],
      };
    }
    if (command === "restore_task") return { id: item.entity_id, revision: 4 };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<RecoveryWorkspace onRestored={refreshed} />);

  expect(await screen.findByText(item.label)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restore Task" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("restore_task", {
      taskId: item.entity_id,
      input: { expected_revision: item.revision },
    }),
  );
  expect(await screen.findByText("Trash is empty.")).toBeInTheDocument();
  expect(refreshed).toHaveBeenCalledOnce();
});
