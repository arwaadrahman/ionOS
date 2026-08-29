import { describe, expect, test } from "vitest";
import { CoreGraph, CoreNode } from "../home";
import { buildCoreLayout, edgePositionBuffer, stableHash } from "./layout";

const node = (id: string, entity_type: CoreNode["entity_type"]): CoreNode => ({
  id,
  entity_type,
  label: id,
  lifecycle: "active",
  today_role: null,
  attention_reason: null,
});

const graph: CoreGraph = {
  nodes: [node("goal", "goal"), node("area", "area"), node("task", "task")],
  edges: [
    { source_id: "goal", target_id: "area", relationship_type: "goal_area" },
    { source_id: "task", target_id: "goal", relationship_type: "task_goal" },
  ],
};

describe("Ion Core deterministic layout", () => {
  test("is repeatable, finite, bounded, and has exact edge buffers", () => {
    const first = buildCoreLayout(graph);
    const second = buildCoreLayout(graph);
    expect(first.nodes).toEqual(second.nodes);
    expect(stableHash("ion")).toBe(stableHash("ion"));
    for (const item of first.nodes) {
      expect(item.position.every(Number.isFinite)).toBe(true);
      expect(Math.hypot(...item.position)).toBeGreaterThanOrEqual(3.7);
      expect(Math.hypot(...item.position)).toBeLessThanOrEqual(4.4);
    }
    expect([...edgePositionBuffer(first)]).toEqual(
      Array.from(
        new Float32Array([
          ...first.positions.get("goal")!,
          ...first.positions.get("area")!,
          ...first.positions.get("task")!,
          ...first.positions.get("goal")!,
        ]),
      ),
    );
  });

  test("keeps existing positions stable when unrelated nodes are added", () => {
    const before = buildCoreLayout(graph);
    const after = buildCoreLayout({
      ...graph,
      nodes: [...graph.nodes, node("unrelated", "project")],
    });
    for (const item of graph.nodes) {
      expect(after.positions.get(item.id)).toEqual(
        before.positions.get(item.id),
      );
    }
  });

  test("prefers a task project as its visual parent without dropping edges", () => {
    const taskProject = buildCoreLayout({
      nodes: [...graph.nodes, node("project", "project")],
      edges: [
        ...graph.edges,
        {
          source_id: "task",
          target_id: "project",
          relationship_type: "task_project",
        },
      ],
    });
    expect(
      taskProject.nodes.find((item) => item.id === "task")?.primary_parent_id,
    ).toBe("project");
    expect(taskProject.edges).toHaveLength(3);
  });

  test.each([1_000, 2_000])(
    "builds finite deterministic buffers for %i canonical nodes",
    (count) => {
      const nodes = [node("root-goal", "goal")];
      const edges: CoreGraph["edges"] = [];
      for (let index = 1; index < count; index += 1) {
        const id = `task-${index.toString().padStart(4, "0")}`;
        nodes.push(node(id, "task"));
        edges.push({
          source_id: id,
          target_id: "root-goal",
          relationship_type: "task_goal",
        });
      }
      const first = buildCoreLayout({ nodes, edges });
      const second = buildCoreLayout({ nodes: [...nodes].reverse(), edges });
      const buffer = edgePositionBuffer(first);
      expect(first.nodes).toEqual(second.nodes);
      expect(first.nodes).toHaveLength(count);
      expect(buffer).toHaveLength((count - 1) * 6);
      expect([...buffer].every(Number.isFinite)).toBe(true);
    },
  );
});
