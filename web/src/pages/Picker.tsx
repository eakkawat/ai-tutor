import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, ApiError, type PickCard } from "../api";
import { CitationChip } from "../components/CitationChip";

/** Choose one skill (C2, C3): a short list for the project, one recommended. The full map is never shown here. */
export default function Picker() {
  const nav = useNavigate();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const project = projects.data?.active ?? null;
  const active = useQuery({ queryKey: ["active-skill"], queryFn: api.activeSkill });
  const list = useQuery({ queryKey: ["shortlist", project?.id], queryFn: () => api.shortlist(project!.id), enabled: Boolean(project), retry: false, staleTime: 60_000 });
  const [picked, setPicked] = useState<number | null>(null);
  const [asking, setAsking] = useState(false);
  const start = useMutation({
    mutationFn: ({ id, pause }: { id: number; pause: boolean }) => api.startSkill(id, project!.id, pause),
    onSuccess: (r) => nav(`/session/${r.session_id}`),
    onError: (e) => { if (e instanceof ApiError && e.field === "active_skill") setAsking(true); },
  });

  if (!projects.data) return <main className="page medium" role="status">Loading…</main>;
  if (!project) return <Navigate to="/project/new" replace />;
  const skills = list.data?.skills ?? [];
  const sel: PickCard | undefined = skills.find((s) => s.id === (picked ?? skills.find((x) => x.recommended)?.id));
  const cur = active.data?.active ?? null;

  return (
    <main className="page wide">
      <nav aria-label="Breadcrumb" className="small muted"><Link to="/">Home</Link> / {project.name} / Choose a skill</nav>
      <div className="row"><h1>What to practice next</h1><Link to="/skills" className="btn">Open full skill map</Link></div>
      <div className="row" style={{ justifyContent: "flex-start", gap: 12 }}>
        <span className="small muted">Project: <strong>{project.name}</strong></span>
        <Link to="/project/new" className="small">Change project</Link>
      </div>

      {cur && (
        <section className="card action row" aria-label="Active skill">
          <div><div className="eyebrow">Active skill</div><strong>{cur.name}</strong>
            <div className="mono small muted">{cur.hours.toFixed(1)} / 20 h · attempt {cur.attempt_next} next</div></div>
          {cur.session_id && <Link to={`/session/${cur.session_id}`} className="btn primary">Continue it</Link>}
        </section>
      )}

      {list.isPending && <p role="status">Finding skills for your project…</p>}
      {list.isError && <p role="alert" className="error">{list.error.message}</p>}
      {list.data && (
        <>
          {list.data.note && <p role="status" className="card" style={{ margin: 0 }}>{list.data.note}</p>}
          {list.data.ranked_by === "similarity" && skills.length > 0 && (
            <p role="status" className="small muted" style={{ margin: 0 }}>The tutor could not be reached, so skills are ordered by how well they match your project.</p>
          )}
          {skills.length > 0 && (
            <>
              <p className="lead" style={{ margin: 0 }}>{skills.length} {skills.length === 1 ? "skill" : "skills"} from your books fit {project.name}. Pick one. The rest stay on your skill map.</p>
              <div className="viewer">
                <ul className="list main" aria-label="Skills for this project">
                  {skills.map((s) => (
                    <li key={s.id}>
                      <button type="button" className="choice" aria-pressed={sel?.id === s.id} onClick={() => setPicked(s.id)}>
                        <div className="row"><strong>{s.name}</strong>
                          <span>{s.recommended && <span className="pill info">Recommended</span>} {s.needs.length > 0 && <span className="pill warning">Needs: {s.needs[0].name}</span>}</span></div>
                        <div className="small" style={{ marginTop: 4 }}>{s.description}</div>
                        <div className="mono small muted" style={{ marginTop: 4 }}>{s.practice_type ?? "practice"} · {s.minutes} min tasks{s.hours > 0 ? ` · ${s.hours.toFixed(1)} h so far` : ""}</div>
                      </button>
                    </li>
                  ))}
                </ul>
                {sel && (
                  <aside className="card action stack" aria-label="Selected skill">
                    <div className="eyebrow">Selected</div>
                    <h2>{sel.name}</h2>
                    {sel.why && <p style={{ margin: 0 }}><strong>Why first:</strong> {sel.why}</p>}
                    <div><div className="eyebrow">You'll be judged on</div>
                      <ul className="list" style={{ gap: 8, marginTop: 8 }}>
                        {sel.principles.map((p) => <li key={p.principle}>{p.principle} {p.citation && <CitationChip chunkId={p.chunk_id} citation={p.citation} />}</li>)}
                      </ul></div>
                    <div className="small"><span className="eyebrow">You'll practice with</span><div>{sel.practice_type ?? "your project"}</div></div>
                    <div className="small"><span className="eyebrow">Typical task</span><div>{sel.minutes} min</div></div>
                    {sel.needs.length > 0 && (
                      <div role="status" className="inset stack" style={{ background: "var(--warning-soft)", color: "var(--warning)" }}>
                        <strong>Needs {sel.needs[0].name} first.</strong>
                        <div className="row" style={{ justifyContent: "flex-start" }}>
                          {skills.some((x) => x.id === sel.needs[0].id)
                            ? <button type="button" className="btn" onClick={() => setPicked(sel.needs[0].id)}>Pick {sel.needs[0].name}</button>
                            : <button type="button" className="btn" onClick={() => start.mutate({ id: sel.needs[0].id, pause: false })}>Start {sel.needs[0].name}</button>}
                        </div>
                      </div>
                    )}
                    <button type="button" className="btn primary" disabled={start.isPending} onClick={() => start.mutate({ id: sel.id, pause: false })}>
                      {sel.needs.length > 0 ? "Start anyway" : sel.learning_status === "paused" ? "Resume this skill" : "Start this skill"}
                    </button>
                    {start.isError && !asking && <p role="alert" className="error" style={{ margin: 0 }}>{start.error.message}</p>}
                  </aside>
                )}
              </div>
            </>
          )}
          {skills.length === 0 && (
            <div className="row" style={{ justifyContent: "flex-start" }}>
              <Link to={list.data.all_passed ? "/review" : "/library"} className="btn primary">{list.data.all_passed ? "Review passed skills" : "Open Library"}</Link>
            </div>
          )}
        </>
      )}

      {asking && cur && sel && (
        <div className="scrim">
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="pause-title">
            <h2 id="pause-title">Pause your current skill?</h2>
            <p style={{ margin: 0 }}>You work on one skill at a time.</p>
            <p style={{ margin: 0 }}><strong>{cur.name}</strong> will be paused with its {cur.hours.toFixed(1)} hours, attempts and next task saved.</p>
            <p style={{ margin: 0 }}>Next: <strong>{sel.name}</strong>, starting with a short diagnosis.</p>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button type="button" className="btn" autoFocus onClick={() => setAsking(false)}>Keep current skill</button>
              <button type="button" className="btn primary" onClick={() => start.mutate({ id: sel.id, pause: true })}>Pause and start</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
