import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Skill } from "../api";

type Row = { key: number; principle: string; test: string; chunk_id: number };

/** Rename a skill and edit its principle checklist. A new principle cites one of the passages the skill already uses. */
export function SkillEditor({ skill, onDone }: { skill: Skill; onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(skill.name);
  const [description, setDescription] = useState(skill.description);
  const [rows, setRows] = useState<Row[]>(skill.principles.map((p, i) => ({ key: i, principle: p.principle, test: p.test, chunk_id: p.chunk_id })));
  const sources = Array.from(new Map(skill.principles.map((p) => [p.chunk_id, p.citation ?? `passage ${p.chunk_id}`])).entries());
  const save = useMutation({
    mutationFn: async () => {
      await api.patchSkill(skill.id, { name, description });
      await api.setPrinciples(skill.id, rows.map(({ principle, test, chunk_id }) => ({ principle, test, chunk_id })));
    },
    onSuccess: () => { for (const k of ["skills", "pending"]) qc.invalidateQueries({ queryKey: [k] }); onDone(); },
  });
  const set = (key: number, patch: Partial<Row>) => setRows(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const id = (s: string) => `${s}-${skill.id}`;
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} aria-label={`Edit ${skill.name}`}>
      <div className="field"><label htmlFor={id("name")}>Skill name</label>
        <input id={id("name")} className="input" style={{ fontFamily: "var(--font-sans)" }} value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="field"><label htmlFor={id("desc")}>What you will be able to do</label>
        <input id={id("desc")} className="input" style={{ fontFamily: "var(--font-sans)" }} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontWeight: 600, marginBottom: 8 }}>Principles (1 to 6)</legend>
        {rows.map((r, i) => (
          <div key={r.key} className="card stack" style={{ padding: 14, gap: 8 }}>
            <div className="field"><label htmlFor={id(`p${r.key}`)}>Principle {i + 1}</label>
              <input id={id(`p${r.key}`)} className="input" style={{ fontFamily: "var(--font-sans)" }} value={r.principle} onChange={(e) => set(r.key, { principle: e.target.value })} /></div>
            <div className="field"><label htmlFor={id(`t${r.key}`)}>Test {i + 1}</label>
              <input id={id(`t${r.key}`)} className="input" style={{ fontFamily: "var(--font-sans)" }} value={r.test} onChange={(e) => set(r.key, { test: e.target.value })} /></div>
            <div className="field"><label htmlFor={id(`s${r.key}`)}>Source {i + 1}</label>
              <select id={id(`s${r.key}`)} className="input" style={{ fontFamily: "var(--font-sans)" }} value={r.chunk_id} onChange={(e) => set(r.key, { chunk_id: Number(e.target.value) })}>
                {sources.map(([cid, label]) => <option key={cid} value={cid}>{label}</option>)}
              </select></div>
            <div><button type="button" className="btn small danger" onClick={() => setRows(rows.filter((x) => x.key !== r.key))}>Remove principle {i + 1}</button></div>
          </div>
        ))}
        {rows.length < 6 && (
          <div><button type="button" className="btn" onClick={() => setRows([...rows, { key: Date.now(), principle: "", test: "", chunk_id: sources[0]?.[0] ?? 0 }])}>Add a principle</button></div>
        )}
      </fieldset>
      {save.isError && <p role="alert" className="error" style={{ margin: 0 }}>{save.error.message}</p>}
      <div className="row" style={{ justifyContent: "flex-start" }}>
        <button type="submit" className="btn primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</button>
        <button type="button" className="btn" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}
