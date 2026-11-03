import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Source, type SourceStatus } from "../api";

const STAGES = [["extracting", "Extract text"], ["chunking", "Chunk"], ["embedding", "Index"], ["triage", "Triage"], ["skills", "Find skills"]] as const;
const PILL: Record<SourceStatus, { text: string; tone: string }> = {
  processing: { text: "Processing", tone: "info" }, ready: { text: "Ready", tone: "success" }, reference_only: { text: "Reference only", tone: "neutral" },
  needs_ocr: { text: "Needs OCR", tone: "danger" }, error: { text: "Stopped", tone: "danger" }, cancelled: { text: "Cancelled", tone: "neutral" }, new: { text: "New", tone: "neutral" },
};

function minutes(s: number | null) { return s == null ? "" : s < 90 ? "about a minute" : `about ${Math.round(s / 60)} min`; }
function fmtPages(b: Source) { return `${b.kind === "chapters" ? `${b.files} chapter PDFs · ` : ""}${b.pages} pages`; }

function Processing({ b }: { b: Source }) {
  const idx = STAGES.findIndex(([k]) => k === b.stage);
  const cancel = useMutation({ mutationFn: () => api.cancel(b.id) });
  return (
    <>
      <div className="small muted">{fmtPages(b)} · {minutes(b.estimate_s)} in total</div>
      <div className="bar" role="progressbar" aria-label={`Processing ${b.title}`} aria-valuenow={Math.round(b.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${Math.round(b.progress * 100)}%` }} />
      </div>
      <div className="stages">
        {STAGES.map(([k, label], i) => (
          <div className="stage" key={k}><span style={{ fontWeight: i === idx ? 600 : 400 }}>{label} · {i < idx ? "done" : i === idx ? "now" : "waiting"}</span></div>
        ))}
      </div>
      {b.message && <p role="status" className="small muted" style={{ margin: 0 }}>{b.message}</p>}
      <div><button type="button" className="btn" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel</button></div>
    </>
  );
}

function BookCard({ b }: { b: Source }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["library"] });
  const retry = useMutation({ mutationFn: () => api.retry(b.id), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api.remove(b.id), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["skills"] }); } });
  const again = useMutation({ mutationFn: () => api.findSkills(b.id), onSuccess: refresh });
  const pill = PILL[b.status];
  const t = b.triage;
  return (
    <li className={`card stack ${b.status === "needs_ocr" ? "problem" : ""}`} aria-label={b.title}>
      <div className="row">
        <h2>{b.title}</h2>
        <span className={`pill ${pill.tone}`}>{pill.text}</span>
      </div>
      {b.status === "processing" && <Processing b={b} />}
      {(b.status === "ready" || b.status === "reference_only") && t && (
        <div className="triage">
          {b.status === "ready"
            ? <><strong>Practical to teach from.</strong> Type: {t.book_type}.{t.likely_skills.length > 0 && <> Likely skills: {t.likely_skills.join("; ")}.</>}</>
            : <><strong>No practicable skills found.</strong> Still searchable and citable in lessons. {t.reason}</>}
        </div>
      )}
      {b.status === "needs_ocr" && <p role="alert" className="error" style={{ margin: 0 }}>{b.message}</p>}
      {(b.status === "error" || b.status === "cancelled") && <p role="alert" className="error" style={{ margin: 0 }}>{b.message}</p>}
      {b.pending_skills > 0 && (
        <div className="banner" role="status">
          <span>{b.pending_skills} new {b.pending_skills === 1 ? "skill" : "skills"} from this book {b.pending_skills === 1 ? "is" : "are"} waiting.</span>
          <Link to="/skills/review" className="btn primary">Review skills</Link>
        </div>
      )}
      {b.skills > 0 && <div className="small"><Link to="/skills">See its {b.skills} {b.skills === 1 ? "skill" : "skills"}</Link></div>}
      {b.status !== "processing" && b.message && b.status !== "needs_ocr" && b.status !== "error" && b.status !== "cancelled" && (
        <p role="status" className="small muted" style={{ margin: 0 }}>{b.message}</p>
      )}
      {b.status !== "processing" && <div className="small muted">{fmtPages(b)} · {b.chunks} passages{b.author ? ` · ${b.author}` : ""}</div>}
      {b.status !== "processing" && (
        <div className="row" style={{ justifyContent: "flex-start" }}>
          {["error", "cancelled", "needs_ocr"].includes(b.status) && b.status !== "needs_ocr" && (
            <button type="button" className="btn primary" onClick={() => retry.mutate()} disabled={retry.isPending}>Retry</button>
          )}
          {(b.status === "ready" || b.status === "reference_only") && (
            <button type="button" className="btn" disabled={again.isPending} onClick={() => again.mutate()}>Look for skills again</button>
          )}
          <button type="button" className="btn danger" disabled={remove.isPending}
            onClick={() => { if (window.confirm(`Remove “${b.title}” and its passages from the library?`)) remove.mutate(); }}>Remove</button>
        </div>
      )}
    </li>
  );
}

export default function Library() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [meta, setMeta] = useState({ title: "", author: "" });
  const q = useQuery({
    queryKey: ["library"], queryFn: api.library,
    refetchInterval: (query) => (query.state.data?.sources.some((s) => s.status === "processing") ? 1500 : false),
  });
  const up = useMutation({ mutationFn: api.upload, onSuccess: () => { setMeta({ title: "", author: "" }); qc.invalidateQueries({ queryKey: ["library"] }); qc.invalidateQueries({ queryKey: ["home"] }); } });
  const pick = (files: FileList | File[] | null) => { const list = Array.from(files ?? []); if (list.length) up.mutate({ files: list, ...meta }); };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); };
  const mode = useQuery({ queryKey: ["skill-mode"], queryFn: api.skillMode });
  const setMode = useMutation({ mutationFn: api.setSkillMode, onSuccess: () => qc.invalidateQueries({ queryKey: ["skill-mode"] }) });
  const sources = q.data?.sources ?? [];

  return (
    <main className="page medium" style={{ maxWidth: 880 }}>
      <div>
        <h1>Library</h1>
        <p className="lead">{sources.length} {sources.length === 1 ? "source" : "sources"} · everything stays on this computer</p>
      </div>
      <section aria-label="Add a book" className={`card ${over ? "dropping" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <div className="row" style={{ justifyContent: "flex-start", alignItems: "flex-end", marginBottom: 12 }}>
          <div className="field"><label htmlFor="title">Title <span className="muted">(optional, read from the PDF if empty)</span></label>
            <input id="title" className="input" style={{ fontFamily: "var(--font-sans)" }} value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></div>
          <div className="field"><label htmlFor="author">Author <span className="muted">(optional)</span></label>
            <input id="author" className="input" style={{ fontFamily: "var(--font-sans)" }} value={meta.author} onChange={(e) => setMeta({ ...meta, author: e.target.value })} /></div>
        </div>
        <div className="dropzone">
          <span style={{ fontSize: 16 }}><strong>Drop a PDF here</strong>, or choose files</span>
          <span className="small muted">A whole book, or chapter PDFs from your chapter splitter (they are grouped into one book)</span>
          <input ref={input} id="pdfs" type="file" accept="application/pdf" multiple className="sr-only" onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
          <label htmlFor="pdfs" className="btn primary" style={{ cursor: "pointer" }}>{up.isPending ? "Uploading…" : "Add book"}</label>
        </div>
        {up.isError && <p role="alert" className="error" style={{ margin: "12px 0 0" }}>{up.error.message}{up.error.message.includes("already") && " Nothing was added."}</p>}
      </section>
      <div className="row" style={{ justifyContent: "flex-start", gap: 12 }}>
        <span id="mode-label" className="small">New skills from a book:</span>
        <div className="seg" role="group" aria-labelledby="mode-label">
          <button type="button" aria-pressed={mode.data?.mode === "auto"} onClick={() => setMode.mutate("auto")}>Add automatically</button>
          <button type="button" aria-pressed={mode.data?.mode === "manual"} onClick={() => setMode.mutate("manual")}>Ask me first</button>
        </div>
      </div>
      {q.isPending ? <p role="status">Loading…</p> : <ul className="list">{sources.map((b) => <BookCard key={b.id} b={b} />)}</ul>}
    </main>
  );
}
