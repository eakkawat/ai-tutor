import type { FlowView, PracticeTask } from "../api";

const BLOCKS: [keyof NonNullable<PracticeTask["extras"]>, string][] = [
  ["worked_example", "Worked example"], ["hint", "Hint"], ["smaller_scope", "Smaller scope"], ["constraint", "Constraint"], ["higher_standard", "Higher standard"], ["combine", "Also use"],
];

/** The task and exactly the help or constraints that are switched on for it. */
export function TaskDetails({ task, flow }: { task: PracticeTask; flow: FlowView }) {
  const x = task.extras ?? {};
  const steps = x.split_steps ?? [];
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ justifyContent: "flex-start", gap: 8 }}>
        {task.support && <span className="tag">Support: {task.support}</span>}
        {flow.early && <span className="tag">Speed over polish</span>}
        {task.base_minutes && task.minutes < task.base_minutes && <span className="tag">Shorter time: {task.minutes} min</span>}
      </div>
      {BLOCKS.filter(([k]) => x[k]).map(([k, label]) => (
        <div key={k} className="inset stack" style={{ gap: 2 }}><span className="eyebrow">{label}</span><span>{String(x[k])}</span></div>
      ))}
      {steps.length > 0 && <div className="inset stack" style={{ gap: 2 }}><span className="eyebrow">Steps</span><ol style={{ margin: 0 }}>{steps.map((s) => <li key={s}>{s}</li>)}</ol></div>}
      {task.template.length > 0 && <ol className="small" style={{ margin: 0 }} aria-label="Beat template">{task.template.map((b) => <li key={b}>{b}</li>)}</ol>}
    </div>
  );
}
