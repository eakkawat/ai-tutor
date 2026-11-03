import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ProfileNote } from "../api";

function Note({ n }: { n: ProfileNote }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(n.text);
  const refresh = () => qc.invalidateQueries({ queryKey: ["profile"] });
  const save = useMutation({ mutationFn: () => api.editNote(n.id, text), onSuccess: () => { setEditing(false); refresh(); } });
  const remove = useMutation({ mutationFn: () => api.removeNote(n.id), onSuccess: refresh });
  return (
    <li className="card stack" style={{ gap: 8 }} aria-label={n.text}>
      {editing ? (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} aria-label="Change this note">
          <label htmlFor={`note-${n.id}`} className="small">Edit note</label>
          <textarea id={`note-${n.id}`} className="input" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
          {save.isError && <p role="alert" className="error" style={{ margin: 0 }}>{save.error.message}</p>}
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="btn primary" disabled={save.isPending}>Save</button>
            <button type="button" className="btn" onClick={() => { setEditing(false); setText(n.text); }}>Cancel</button>
          </div>
        </form>
      ) : (
        <>
          <p style={{ margin: 0 }}>{n.text}</p>
          <p className="small muted" style={{ margin: 0 }}>{n.source === "user" ? "You added this" : n.edited ? "You edited this" : n.evidence}</p>
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="button" className="btn small" onClick={() => setEditing(true)}>Edit</button>
            <button type="button" className="btn small danger" aria-label={`Remove note: ${n.text}`} disabled={remove.isPending} onClick={() => remove.mutate()}>Remove</button>
          </div>
        </>
      )}
    </li>
  );
}

/** What the tutor has learned about how this learner learns. The learner can add, change or remove any of it. */
export default function Profile() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const [text, setText] = useState("");
  const [section, setSection] = useState<"understand" | "flow">("understand");
  const add = useMutation({ mutationFn: () => api.addNote(text, section), onSuccess: () => { setText(""); qc.invalidateQueries({ queryKey: ["profile"] }); } });
  if (!q.data) return <main className="page medium" role="status">Loading…</main>;
  const none = q.data.sections.every((s) => s.notes.length === 0);
  return (
    <main className="page medium" style={{ maxWidth: 800 }}>
      <div>
        <h1>How I learn</h1>
        <p className="lead">The tutor reads this before every lesson and task. It adds notes as it learns about you. Edit or remove anything that's wrong.</p>
      </div>
      {none && <p role="status" className="card" style={{ margin: 0 }}>Nothing learned yet. Notes appear as you practice, or add one below.</p>}
      {q.data.sections.filter((s) => s.notes.length > 0).map((s) => (
        <section key={s.key} aria-labelledby={`sec-${s.key}`} className="stack">
          <h2 id={`sec-${s.key}`}>{s.title}</h2>
          <ul className="list">{s.notes.map((n) => <Note key={n.id} n={n} />)}</ul>
        </section>
      ))}
      <form className="card stack" aria-label="Add a note" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <h2 style={{ fontSize: 16 }}>Add a note</h2>
        <div className="field"><label htmlFor="new-note">Something the tutor should know about how you learn</label>
          <textarea id="new-note" className="input" rows={2} value={text} onChange={(e) => setText(e.target.value)} /></div>
        <fieldset className="chips" aria-label="Where it belongs">
          {q.data.sections.map((s) => <button key={s.key} type="button" className="chip" aria-pressed={section === s.key} onClick={() => setSection(s.key)}>{s.title}</button>)}
        </fieldset>
        {add.isError && <p role="alert" className="error" style={{ margin: 0 }}>{add.error.message}</p>}
        <div><button type="submit" className="btn primary" disabled={add.isPending || !text.trim()}>Add</button></div>
        <p className="small muted" style={{ margin: 0 }}>Notes shape how you're taught. They never lower the bar for passing a skill.</p>
      </form>
    </main>
  );
}
