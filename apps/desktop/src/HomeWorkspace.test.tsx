import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { HomeWorkspace } from "./HomeWorkspace";
import { HomeOutput } from "./home";

vi.mock("./ion-core/CoreCanvas", () => ({
  default: ({
    graph,
    onSelect,
  }: {
    graph: HomeOutput["core"];
    onSelect: (node: HomeOutput["core"]["nodes"][number]) => void;
  }) => (
    <div>
      {graph.nodes.map((node) => (
        <button key={node.id} onClick={() => onSelect(node)}>
          Select {node.label}
        </button>
      ))}
    </div>
  ),
}));

const node = (
  id: string,
  label: string,
  entity_type: HomeOutput["core"]["nodes"][number]["entity_type"],
) => ({
  id,
  label,
  entity_type,
  lifecycle: "active" as const,
  today_role: null,
  attention_reason: null,
});

const home: HomeOutput = {
  planning_date: "2030-01-01",
  timezone: "UTC",
  generated_at: "2030-01-01T00:00:00Z",
  core: {
    nodes: [
      node("goal", "Synthetic Goal", "goal"),
      node("milestone", "Synthetic checkpoint", "goal_milestone"),
      node("task", "Synthetic Task", "task"),
    ],
    edges: [
      {
        source_id: "milestone",
        target_id: "goal",
        relationship_type: "goal_milestone_goal",
      },
    ],
  },
  focus: null,
  needs_attention: [],
  upcoming: [],
};

afterEach(cleanup);

test("opens a selected milestone through its canonical owner", async () => {
  const onNavigate = vi.fn();
  render(
    <HomeWorkspace
      home={home}
      processing={false}
      stale={false}
      onRetry={vi.fn()}
      onNavigate={onNavigate}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Select Synthetic checkpoint" }),
  );
  expect(
    screen.getByRole("heading", { name: "Synthetic checkpoint" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(onNavigate).toHaveBeenCalledWith({
    workspace: "areas",
    entityType: "goal",
    id: "goal",
  });
});

test("opens a selected task in Tasks and exposes disabled Ask Ion honestly", async () => {
  const onNavigate = vi.fn();
  render(
    <HomeWorkspace
      home={home}
      processing={false}
      stale={false}
      onRetry={vi.fn()}
      onNavigate={onNavigate}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Select Synthetic Task" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(onNavigate).toHaveBeenCalledWith({
    workspace: "tasks",
    entityType: "task",
    id: "task",
  });
  expect(screen.getByRole("button", { name: "Ask Ion" })).toBeDisabled();
});
