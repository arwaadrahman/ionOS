import { expect, test } from "vitest";
import {
  CommandItem,
  buildCommandItems,
  searchCommands,
} from "./commandSearch";
import { HomeOutput } from "./home";

const home: HomeOutput = {
  planning_date: "2030-01-01",
  timezone: "UTC",
  generated_at: "2030-01-01T00:00:00Z",
  core: {
    nodes: [
      {
        id: "11111111-1111-4111-8111-111111111111",
        entity_type: "area",
        label: "Learning",
        lifecycle: "active",
        today_role: null,
        attention_reason: null,
      },
      {
        id: "22222222-2222-4222-8222-222222222222",
        entity_type: "goal",
        label: "Strengthen systems design",
        lifecycle: "active",
        today_role: null,
        attention_reason: null,
      },
      {
        id: "33333333-3333-4333-8333-333333333333",
        entity_type: "project",
        label: "Café Portfolio",
        lifecycle: "paused",
        today_role: null,
        attention_reason: null,
      },
      {
        id: "44444444-4444-4444-8444-444444444444",
        entity_type: "task",
        label: "Review architecture notes",
        lifecycle: "active",
        today_role: "priority",
        attention_reason: null,
      },
      {
        id: "55555555-5555-4555-8555-555555555555",
        entity_type: "goal_milestone",
        label: "Finish practice module",
        lifecycle: "active",
        today_role: null,
        attention_reason: null,
      },
    ],
    edges: [
      {
        source_id: "55555555-5555-4555-8555-555555555555",
        target_id: "22222222-2222-4222-8222-222222222222",
        relationship_type: "goal_milestone_goal",
      },
    ],
  },
  focus: null,
  needs_attention: [],
  upcoming: [],
};

test("builds commands from destinations and the canonical Home projection", () => {
  const items = buildCommandItems(home);
  expect(items.slice(1, 6).map((item) => item.label)).toEqual([
    "Home",
    "Today",
    "Areas & Goals",
    "Projects",
    "Tasks",
  ]);
  expect(items).toHaveLength(11);
  expect(searchCommands(items, "recovery")[0]).toMatchObject({
    id: "command:recovery",
    action: { type: "recovery" },
  });
  expect(
    items.find((item) => item.label === "Finish practice module")?.action,
  ).toEqual({
    type: "record",
    target: {
      workspace: "areas",
      entityType: "goal",
      id: "22222222-2222-4222-8222-222222222222",
    },
  });
});

test("ranks exact, prefix, title, and metadata matches deterministically", () => {
  const items = buildCommandItems(home);
  expect(searchCommands(items, "projects")[0].id).toBe("destination:projects");
  expect(searchCommands(items, "cafe")[0].label).toBe("Café Portfolio");
  expect(searchCommands(items, "architecture review")[0].label).toBe(
    "Review architecture notes",
  );
  expect(searchCommands(items, "priority")[0].label).toBe(
    "Review architecture notes",
  );
  expect(searchCommands(items, "").map((item) => item.category)).toEqual([
    "destination",
    "destination",
    "destination",
    "destination",
    "destination",
  ]);
});

test("returns a stable bounded result set for a large local projection", () => {
  const items: CommandItem[] = Array.from({ length: 2_000 }, (_, index) => ({
    id: `record:task:${index.toString().padStart(4, "0")}`,
    label: `Synthetic Task ${index.toString().padStart(4, "0")}`,
    description: "task · active",
    category: "task",
    action: {
      type: "record",
      target: {
        workspace: "tasks",
        entityType: "task",
        id: index.toString(),
      },
    },
    searchText: `synthetic task ${index.toString().padStart(4, "0")} active`,
  }));
  const first = searchCommands(items, "synthetic task", 12).map(
    (item) => item.id,
  );
  const second = searchCommands([...items].reverse(), "synthetic task", 12).map(
    (item) => item.id,
  );
  expect(first).toHaveLength(12);
  expect(second).toEqual(first);
});
