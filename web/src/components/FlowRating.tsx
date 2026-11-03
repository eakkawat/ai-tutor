import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type FlowRating as Rating, type SessionView } from "../api";

const CHOICES = [["too_easy", "Too easy"], ["just_right", "Just right"], ["too_hard", "Too hard"]] as const;

/** One tap after a task. The answer says exactly what changes for the next attempt, or why nothing does. */
export function FlowRatingPanel({ v }: { v: SessionView }) {
  const qc = useQueryClient();
  const rate = useMutation({
    mutationFn: (a: { rating: string; cantStart?: boolean }) => api.rate(v.id, a.rating, a.cantStart),
    onSuccess: (view) => qc.setQueryData(["session", v.id], view),
  });
  const r: Rating | null = v.flow.rating;

  if (r) {
    const rest = r.verdict && r.message.startsWith(r.verdict) ? r.message.slice(r.verdict.length).trim() : r.message;
    return (
      <section className="inset stack" aria-label="What changes next" role="status">
        <div className="eyebrow">{r.inferred ? "You did not say how it felt, so I judged from your work" : "How that task felt"}</div>
        <p style={{ margin: 0 }}>{r.verdict && <strong>{r.verdict} </strong>}{rest}</p>
        <p className="mono small muted" style={{ margin: 0 }}>Difficulty {r.level_before} {r.level_after === r.level_before ? "stays at" : "→"} {r.level_after} / 5</p>
      </section>
    );
  }
  if (!v.flow.can_rate) return null;
  return (
    <section className="card action stack" aria-labelledby="flow-q">
      <h2 id="flow-q" style={{ fontSize: 17 }}>How did that task feel?</h2>
      <div className="row" role="group" aria-labelledby="flow-q" style={{ justifyContent: "flex-start", gap: 8 }}>
        {CHOICES.map(([key, label]) => (
          <button key={key} type="button" className="chip" disabled={rate.isPending} onClick={() => rate.mutate({ rating: key })}>{label}</button>
        ))}
      </div>
      <div><button type="button" className="btn small quiet" disabled={rate.isPending} onClick={() => rate.mutate({ rating: "too_hard", cantStart: true })}>
        Too hard, and I don't know where to start</button></div>
      {rate.isPending && <p role="status" className="small muted" style={{ margin: 0 }}>Setting up your next attempt…</p>}
      {rate.isError && <p role="alert" className="error" style={{ margin: 0 }}>{rate.error.message}</p>}
    </section>
  );
}
