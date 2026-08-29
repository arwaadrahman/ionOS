import { CoreEntityType, HomeOutput } from "./home";
import {
  NavigationTarget,
  Workspace,
  destinationForCoreNode,
  workspaceLabel,
  workspaces,
} from "./navigation";

export type CommandAction =
  | { type: "workspace"; workspace: Workspace }
  | { type: "recovery" }
  | { type: "record"; target: NavigationTarget };

export type CommandItem = {
  id: string;
  label: string;
  description: string;
  category: "command" | "destination" | CoreEntityType;
  action: CommandAction;
  searchText: string;
};

const categoryOrder: Record<CommandItem["category"], number> = {
  command: 0,
  destination: 1,
  area: 2,
  goal: 3,
  goal_milestone: 4,
  project: 5,
  project_milestone: 6,
  task: 7,
};
const combiningMarks = /[\u0300-\u036f]/g;
const whitespace = /\s+/g;

export function normalizeSearchText(value: string) {
  return value
    .normalize("NFKD")
    .replace(combiningMarks, "")
    .toLocaleLowerCase("en-US")
    .trim()
    .replace(whitespace, " ");
}

function recordDescription(item: HomeOutput["core"]["nodes"][number]) {
  const type = item.entity_type.replaceAll("_", " ");
  const lifecycle = item.lifecycle.replaceAll("_", " ");
  const ownerSuffix = item.entity_type.endsWith("_milestone")
    ? " · opens owner"
    : "";
  return `${type} · ${lifecycle}${ownerSuffix}`;
}

export function buildCommandItems(home: HomeOutput): CommandItem[] {
  const destinations = workspaces.map<CommandItem>((workspace) => {
    const label = workspaceLabel(workspace);
    return {
      id: `destination:${workspace}`,
      label,
      description: "Open destination",
      category: "destination",
      action: { type: "workspace", workspace },
      searchText: normalizeSearchText(`${label} open go navigate destination`),
    };
  });
  const records = home.core.nodes.flatMap<CommandItem>((node) => {
    const target = destinationForCoreNode(home, node);
    if (!target) return [];
    const description = recordDescription(node);
    return [
      {
        id: `record:${node.entity_type}:${node.id}`,
        label: node.label,
        description,
        category: node.entity_type,
        action: { type: "record", target },
        searchText: normalizeSearchText(
          `${node.label} ${description} ${node.today_role ?? ""} ${node.attention_reason ?? ""}`,
        ),
      },
    ];
  });
  return [
    {
      id: "command:recovery",
      label: "Recovery",
      description: "Open Trash and recent history",
      category: "command",
      action: { type: "recovery" },
      searchText: normalizeSearchText("recovery trash restore history audit"),
    },
    ...destinations,
    ...records,
  ];
}

function lexicalScore(item: CommandItem, query: string) {
  const label = normalizeSearchText(item.label);
  const words = label.split(" ");
  const tokens = query.split(" ");
  if (label === query) return 0;
  if (label.startsWith(query)) return 1;
  if (words.some((word) => word.startsWith(query))) return 2;
  if (label.includes(query)) return 3;
  if (tokens.every((token) => words.some((word) => word.startsWith(token)))) {
    return 4;
  }
  if (tokens.every((token) => item.searchText.includes(token))) return 5;
  return null;
}

function compareCodepoints(left: string, right: string) {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function searchCommands(
  items: readonly CommandItem[],
  rawQuery: string,
  limit = 12,
) {
  const query = normalizeSearchText(rawQuery);
  if (!query) {
    return items
      .filter((item) => item.category === "destination")
      .slice(0, limit);
  }
  return items
    .flatMap((item) => {
      const score = lexicalScore(item, query);
      return score === null ? [] : [{ item, score }];
    })
    .sort(
      (left, right) =>
        left.score - right.score ||
        categoryOrder[left.item.category] -
          categoryOrder[right.item.category] ||
        compareCodepoints(
          normalizeSearchText(left.item.label),
          normalizeSearchText(right.item.label),
        ) ||
        compareCodepoints(left.item.id, right.item.id),
    )
    .slice(0, limit)
    .map(({ item }) => item);
}
