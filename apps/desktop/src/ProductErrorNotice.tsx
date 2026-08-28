import { ProductError } from "./organizer";

const labels: Record<string, string> = {
  goal: "Goals",
  milestone: "Goal Milestones",
  project: "Projects",
  project_milestone: "Project Milestones",
  task: "directly linked Tasks",
};

export function ProductErrorNotice({ error }: { error: ProductError | null }) {
  if (!error) return null;
  if (error.code === "trash_blocked") {
    return (
      <aside className="notice notice--warning" role="alert">
        <strong>Cannot move this record to Trash yet.</strong>
        <ul>
          {error.blockers.map((blocker) => (
            <li key={blocker.entity}>
              {blocker.count} {labels[blocker.entity] ?? blocker.entity}
            </li>
          ))}
        </ul>
        <span>Move, unassign, or Trash those records first.</span>
      </aside>
    );
  }
  const message = {
    revision_conflict:
      "This record changed elsewhere. Canonical data was refreshed; review your input and try again.",
    assignment_unavailable:
      "That parent is archived, in Trash, or no longer available.",
    validation:
      "Ion could not accept that value. Review the fields and try again.",
    not_found: "That record is no longer available.",
    unavailable: "This action is temporarily unavailable.",
  }[error.code];
  return (
    <p className="notice" role="alert">
      {message}
    </p>
  );
}
