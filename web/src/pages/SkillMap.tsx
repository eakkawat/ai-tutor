import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Skill } from "../api";
import { SkillDetails } from "../components/SkillDetails";
import { SkillEditor } from "../components/SkillEditor";

const LEARNING: Record<string, { text: string; tone: string }> = {
  not_started: { text: "Not started", tone: "neutral" }, active: { text: "In progress", tone: "info" }, paused: { text: "Paused", tone: "neutral" },
  passed: { text: "Passed", tone: "success" }, needs_practice: { text: "Needs practice", tone: "warning" },
};

type Mode = "view" | "edit" | "split" | "merge";

function SkillCard({ skill, others }: { skill: Skill; others: Skill[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("view");
  const [note, setNote] = useState<string | null>(null);
  const [splitName, setSplitName] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [into, setInto] = useState<number>(others[0]?.id ?? 0);
  const refresh = () => qc.invalidateQueries({ queryKey: ["skills"] });
  const done = (msg?: string) => { setMode("view"); if (msg) setNote(msg); refresh(); };
  const del = useMutation({ mutationFn: () => api.deleteSkill(skill.id), onSuccess: () => refresh() });
  const split = useMutation({ mutationFn: () => api.splitSkill(skill.id, { name: splitName, principle_ids: picked }), onSuccess: () => done("Split into two skills.") });
  const merge = useMutation({ mutationFn: () => api.mergeSkill(skill.id, into), onSuccess: () => refresh() });
  const l = LEARNING[skill.learning_status] ?? LEARNING.not_started;
  const err = (split.error ?? merge.error ?? del.error) as Error | null;

  return (
    <li className={`card stack ${open ? "action" : ""}`} aria-label={skill.name}>
      <div className="row">
        <h3 style={{ margin: 0, fontSize: 17 }}>{skill.name}</h3>
        <span><span className={`pill ${l.tone}`}>{l.text}</span> <span className="mono small muted">{skill.hours.toFixed(1)} h</span></span>
      </div>
      <div className="row" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="btn small" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide details" : "Show details"}</button>
      </div>
      {note && <p role="status" className="small muted" style={{ margin: 0 }}>{note}</p>}
      {open && mode === "view" && (
        <>
          <SkillDetails skill={skill} />
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="button" className="btn" onClick={() => setMode("edit")}>Edit</button>
            <button type="button" className="btn" disabled={skill.principles.length < 2} onClick={() => setMode("split")}>Split</button>
            <button type="button" className="btn" disabled={others.length === 0} onClick={() => setMode("merge")}>Merge into…</button>
            <button type="button" className="btn danger"
              onClick={() => { if (window.confirm(`Delete “${skill.name}”? If you have practiced it, it is archived instead so your hours are kept.`)) del.mutate(); }}>Delete</button>
          </div>
        </>
      )}
      {open && mode === "edit" && <SkillEditor skill={skill} onDone={() => done("Saved.")} />}
      {open && mode === "split" && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); split.mutate(); }} aria-label={`Split ${skill.name}`}>
          <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600 }}>Choose the principles that move to a new skill</legend>
            {skill.principles.map((p) => (
              <label key={p.id} style={{ display: "flex", gap: 8, minHeight: 44, alignItems: "center" }}>
                <input type="checkbox" checked={picked.includes(p.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, p.id] : picked.filter((x) => x !== p.id))} />
                {p.principle}
              </label>
            ))}
          </fieldset>
          <div className="field"><label htmlFor={`split-${skill.id}`}>Name of the new skill</label>
            <input id={`split-${skill.id}`} className="input" style={{ fontFamily: "var(--font-sans)" }} value={splitName} onChange={(e) => setSplitName(e.target.value)} /></div>
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="btn primary" disabled={split.isPending}>Split into two skills</button>
            <button type="button" className="btn" onClick={() => setMode("view")}>Cancel</button>
          </div>
        </form>
      )}
      {open && mode === "merge" && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); merge.mutate(); }} aria-label={`Merge ${skill.name}`}>
          <div className="field"><label htmlFor={`merge-${skill.id}`}>Merge “{skill.name}” into</label>
            <select id={`merge-${skill.id}`} className="input" style={{ fontFamily: "var(--font-sans)" }} value={into} onChange={(e) => setInto(Number(e.target.value))}>
              {others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select></div>
          <p className="small muted" style={{ margin: 0 }}>Its principles, sources and concepts move to the chosen skill. This skill is then removed.</p>
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="btn primary" disabled={merge.isPending}>Merge</button>
            <button type="button" className="btn" onClick={() => setMode("view")}>Cancel</button>
          </div>
        </form>
      )}
      {err && <p role="alert" className="error" style={{ margin: 0 }}>{err.message}</p>}
    </li>
  );
}

export default function SkillMapPage() {
  const q = useQuery({ queryKey: ["skills"], queryFn: api.skillMap });
  if (!q.data) return <main className="page medium" role="status">Loading…</main>;
  const { domains, pending } = q.data;
  const all = domains.flatMap((d) => d.skills);
  return (
    <main className="page wide">
      <div>
        <h1>Skill map</h1>
        <p className="lead">{all.length} {all.length === 1 ? "skill" : "skills"} · {domains.length} {domains.length === 1 ? "domain" : "domains"}</p>
      </div>
      {pending > 0 && (
        <div className="banner" role="status">
          <span>{pending} proposed {pending === 1 ? "skill is" : "skills are"} waiting for your review.</span>
          <Link to="/skills/review" className="btn primary">Review skills</Link>
        </div>
      )}
      {all.length === 0 && pending === 0 && (
        <section className="card stack"><h2>No skills yet</h2><p className="lead" style={{ margin: 0 }}>Add a book in the Library. Skills you can practice are found in it.</p>
          <Link to="/library" className="btn primary" style={{ alignSelf: "flex-start" }}>Open Library</Link></section>
      )}
      {domains.map((d) => (
        <section key={d.domain} aria-labelledby={`dom-${d.domain}`} className="stack">
          <h2 id={`dom-${d.domain}`}>{d.domain}</h2>
          <ul className="list">{d.skills.map((s) => <SkillCard key={s.id} skill={s} others={all.filter((o) => o.id !== s.id && o.domain === s.domain)} />)}</ul>
        </section>
      ))}
    </main>
  );
}
