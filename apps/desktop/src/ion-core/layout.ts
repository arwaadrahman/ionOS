import { CoreEdge, CoreEntityType, CoreGraph, CoreNode } from "../home";

export type Point3 = readonly [number, number, number];
export type LayoutNode = CoreNode & {
  position: Point3;
  primary_parent_id: string | null;
};
export type CoreLayout = {
  nodes: LayoutNode[];
  edges: CoreEdge[];
  positions: Map<string, Point3>;
};

const TYPE_ORDER: Record<CoreEntityType, number> = {
  area: 0,
  goal: 1,
  project: 2,
  goal_milestone: 3,
  project_milestone: 4,
  task: 5,
};
const PARENT_PRIORITY: Record<CoreEdge["relationship_type"], number> = {
  project_milestone_project: 0,
  goal_milestone_goal: 0,
  task_project: 0,
  task_goal: 1,
  project_goal: 0,
  goal_area: 0,
};
const UINT_RANGE = 0x1_0000_0000;

export function stableHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function unit(seed: string): number {
  return (stableHash(seed) + 0.5) / UINT_RANGE;
}

function normalize([x, y, z]: Point3): Point3 {
  const magnitude = Math.hypot(x, y, z) || 1;
  return [x / magnitude, y / magnitude, z / magnitude];
}

function scale([x, y, z]: Point3, amount: number): Point3 {
  return [x * amount, y * amount, z * amount];
}

function add(a: Point3, b: Point3, c: Point3): Point3 {
  return [a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]];
}

function cross(a: Point3, b: Point3): Point3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function rootPosition(id: string): Point3 {
  const z = unit(`ion-core:v1:${id}:z`) * 2 - 1;
  const angle = unit(`ion-core:v1:${id}:angle`) * Math.PI * 2;
  const radius = Math.sqrt(Math.max(0, 1 - z * z));
  const shell = 3.9 + unit(`ion-core:v1:${id}:radius`) * 0.45;
  return scale([radius * Math.cos(angle), z, radius * Math.sin(angle)], shell);
}

function childPosition(node: CoreNode, parent: Point3): Point3 {
  const normal = normalize(parent);
  const reference: Point3 = Math.abs(normal[1]) > 0.88 ? [1, 0, 0] : [0, 1, 0];
  const tangent = normalize(cross(reference, normal));
  const bitangent = normalize(cross(normal, tangent));
  const angle = unit(`ion-core:v1:${node.id}:orbit`) * Math.PI * 2;
  const spread = 0.28 + TYPE_ORDER[node.entity_type] * 0.035;
  const radial = (unit(`ion-core:v1:${node.id}:radial`) - 0.5) * 0.34;
  const candidate = add(
    parent,
    scale(tangent, Math.cos(angle) * spread),
    scale(bitangent, Math.sin(angle) * spread),
  );
  return scale(normalize(candidate), 4.08 + radial);
}

export function buildCoreLayout(graph: CoreGraph): CoreLayout {
  const nodes = [...graph.nodes].sort(
    (a, b) =>
      TYPE_ORDER[a.entity_type] - TYPE_ORDER[b.entity_type] ||
      a.id.localeCompare(b.id),
  );
  const available = new Set(nodes.map((node) => node.id));
  const parentEdges = new Map<string, CoreEdge[]>();
  for (const edge of graph.edges) {
    if (!available.has(edge.source_id) || !available.has(edge.target_id))
      continue;
    const list = parentEdges.get(edge.source_id) ?? [];
    list.push(edge);
    parentEdges.set(edge.source_id, list);
  }
  const parentById = new Map<string, string>();
  for (const [sourceId, candidates] of parentEdges) {
    candidates.sort(
      (a, b) =>
        PARENT_PRIORITY[a.relationship_type] -
          PARENT_PRIORITY[b.relationship_type] ||
        a.target_id.localeCompare(b.target_id),
    );
    parentById.set(sourceId, candidates[0].target_id);
  }

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const positions = new Map<string, Point3>();
  const resolving = new Set<string>();
  const resolve = (id: string): Point3 => {
    const existing = positions.get(id);
    if (existing) return existing;
    const node = nodeById.get(id);
    if (!node || resolving.has(id)) return rootPosition(id);
    resolving.add(id);
    const parentId = parentById.get(id);
    const position = parentId
      ? childPosition(node, resolve(parentId))
      : rootPosition(id);
    resolving.delete(id);
    positions.set(id, position);
    return position;
  };

  const layoutNodes = nodes.map((node) => ({
    ...node,
    position: resolve(node.id),
    primary_parent_id: parentById.get(node.id) ?? null,
  }));
  return { nodes: layoutNodes, edges: [...graph.edges], positions };
}

export function edgePositionBuffer(layout: CoreLayout): Float32Array {
  const values: number[] = [];
  for (const edge of layout.edges) {
    const source = layout.positions.get(edge.source_id);
    const target = layout.positions.get(edge.target_id);
    if (!source || !target) continue;
    values.push(...source, ...target);
  }
  return new Float32Array(values);
}
