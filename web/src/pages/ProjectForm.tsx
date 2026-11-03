import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

const LENGTHS = [25, 45, 60, 90];

/** Create a project (C1) or pick an existing one. Skills are chosen and practised in service of it. */
export default function ProjectForm() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [f, setF] = useState({ name: "", description: "", good_enough: "", minutes_per_session: 25 });
  const done = () => { qc.invalidateQueries({ queryKey: ["projects"] }); nav("/new"); };
  const create = useMutation({ mutationFn: () => api.createProject(f), onSuccess: done });
  const use = useMutation({ mutationFn: api.activateProject, onSuccess: done });
  const text = (k: "name" | "description" | "good_enough") => ({ value: f[k], onChange: (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value }) });
  const others = list.data?.projects ?? [];

  return (
    <main className="page narrow">
      <nav aria-label="Breadcrumb" className="small muted"><Link to="/">Home</Link> / New project</nav>
      <div>
        <h1>What do you want to make?</h1>
        <p className="lead">Skills are chosen and practiced for this project. Pick something real you care about.</p>
      </div>
      <form className="card stack" style={{ gap: 16 }} onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div className="field"><label htmlFor="p-name">Project name</label>
          <input id="p-name" className="input" style={{ fontFamily: "var(--font-sans)" }} {...text("name")} /></div>
        <div className="field"><label htmlFor="p-desc">What you're making</label>
          <textarea id="p-desc" className="input" rows={3} {...text("description")} /></div>
        <div className="field"><label htmlFor="p-good">“Good enough” means</label>
          <span id="p-good-help" className="small muted">Something you could check yourself when it's done. Skills pass when your work meets this.</span>
          <textarea id="p-good" className="input" rows={3} aria-describedby="p-good-help" {...text("good_enough")} /></div>
        <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 8 }}>
          <legend style={{ marginBottom: 8 }}>Session length</legend>
          <div className="chips">
            {LENGTHS.map((m) => (
              <button type="button" key={m} className="chip" aria-pressed={f.minutes_per_session === m} onClick={() => setF({ ...f, minutes_per_session: m })}>{m} min</button>
            ))}
          </div>
        </fieldset>
        {create.isError && <p role="alert" className="error" style={{ margin: 0 }}>{create.error.message}</p>}
        <div className="row">
          <Link to={list.data?.active ? "/new" : "/"} className="btn">Cancel</Link>
          <button type="submit" className="btn primary" disabled={create.isPending}>Create and see skills</button>
        </div>
      </form>
      {others.length > 0 && (
        <section aria-labelledby="existing" className="stack">
          <h2 id="existing" style={{ fontSize: 15 }}>Or use an existing project</h2>
          <ul className="list">
            {others.map((p) => (
              <li key={p.id} className="card row" aria-label={p.name}>
                <div><strong>{p.name}</strong><div className="small muted">{p.active ? "active" : "paused"} · {p.skills_practised} {p.skills_practised === 1 ? "skill" : "skills"}</div></div>
                <button type="button" className="btn" onClick={() => use.mutate(p.id)} disabled={use.isPending}>Use {p.name}</button>
              </li>
            ))}
          </ul>
          {use.isError && <p role="alert" className="error">{use.error.message}</p>}
        </section>
      )}
    </main>
  );
}
