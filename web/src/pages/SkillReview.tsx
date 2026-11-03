import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { SkillDetails } from "../components/SkillDetails";
import { SkillEditor } from "../components/SkillEditor";

/** Manual mode: one proposed skill at a time. Keep, edit, or delete. A proposed merge shows what it would add (B5). */
export default function SkillReview() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pending"], queryFn: api.pendingSkills });
  const [editing, setEditing] = useState(false);
  const refresh = () => { setEditing(false); for (const k of ["pending", "skills", "library"]) qc.invalidateQueries({ queryKey: [k] }); };
  const first = q.data?.skills[0];
  const accept = useMutation({ mutationFn: () => api.acceptSkill(first!.id), onSuccess: refresh });
  const asNew = useMutation({ mutationFn: () => api.acceptAsNew(first!.id), onSuccess: refresh });
  const discard = useMutation({ mutationFn: () => api.deleteSkill(first!.id), onSuccess: refresh });
  const err = (accept.error ?? asNew.error ?? discard.error) as Error | null;

  if (!q.data) return <main className="page medium" role="status">Loading…</main>;
  if (!first) {
    return (
      <main className="page medium">
        <h1>Nothing to review</h1>
        <p className="lead">Every proposed skill has been dealt with.</p>
        <Link to="/skills" className="btn primary" style={{ alignSelf: "flex-start" }}>Open the skill map</Link>
      </main>
    );
  }
  const total = q.data.skills.length;
  const isMerge = Boolean(first.merge);
  return (
    <main className="page medium" style={{ maxWidth: 800 }}>
      <nav aria-label="Breadcrumb" className="small muted"><Link to="/skills">Skill map</Link> / Review</nav>
      <section className="card action stack" aria-label={first.name}>
        <div className="eyebrow">{isMerge ? "Possible merge" : "New skill"} · {total} waiting</div>
        <h1 style={{ fontSize: 24 }}>{first.name}</h1>
        {first.merge && (
          <div className="banner" role="status">
            <span><strong>This {first.merge.text}.</strong> {first.merge_note}</span>
          </div>
        )}
        {editing ? <SkillEditor skill={first} onDone={refresh} /> : <SkillDetails skill={first} />}
        {!editing && (
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="button" className="btn primary" onClick={() => accept.mutate()} disabled={accept.isPending}>{isMerge ? "Accept merge" : "Keep"}</button>
            {isMerge && <button type="button" className="btn" onClick={() => asNew.mutate()} disabled={asNew.isPending}>Add as a separate skill</button>}
            <button type="button" className="btn" onClick={() => setEditing(true)}>Edit</button>
            <button type="button" className="btn danger" onClick={() => discard.mutate()} disabled={discard.isPending}>{isMerge ? "Discard" : "Delete"}</button>
          </div>
        )}
        {err && <p role="alert" className="error" style={{ margin: 0 }}>{err.message}</p>}
      </section>
    </main>
  );
}
