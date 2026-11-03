import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Asset, type StepState } from "../api";

function stepText(label: string, s: StepState | undefined): string {
  if (!s || s.status === "waiting") return `${label} · waiting`;
  if (s.status === "done") return `${label} · done${s.count !== undefined ? ` · ${s.count}` : s.lines !== undefined ? ` · ${s.lines} lines` : ""}`;
  if (s.status === "skipped") return `${label} · skipped`;
  return `${label} · ${s.total ? `${s.done ?? 0} of ${s.total}` : "working"}`;
}
const pct = (s: StepState | undefined) => (s?.status === "done" || s?.status === "skipped" ? 100 : s?.total ? Math.round(((s.done ?? 0) / s.total) * 100) : s?.status === "running" ? 40 : 0);

function mmss(t: number) { return `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`; }

function Row({ a, sessionId }: { a: Asset; sessionId: number }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["session", sessionId] });
  const remove = useMutation({ mutationFn: () => api.removeAsset(a.id), onSuccess: refresh });
  const retry = useMutation({ mutationFn: () => api.retryAsset(a.id), onSuccess: refresh });
  const st = a.steps;
  return (
    <li className="card stack" style={{ padding: 12, gap: 8 }} aria-label={a.filename}>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <div className="row" style={{ justifyContent: "flex-start", flexWrap: "nowrap", gap: 12, minWidth: 0 }}>
          {a.thumb
            ? <img src={a.thumb} alt={`Preview of ${a.filename}`} width={64} height={40} style={{ objectFit: "cover", borderRadius: 4, background: "var(--image-placeholder)" }} />
            : <span aria-hidden="true" style={{ width: 64, height: 40, borderRadius: 4, background: "var(--frame-placeholder)", display: "inline-block" }} />}
          <div style={{ minWidth: 0 }}>
            <div className="mono small" style={{ overflowWrap: "anywhere" }}>{a.filename}</div>
            <div className="small muted">
              {a.kind === "image" ? (a.status === "ready" ? `Ready${a.width ? ` · ${a.width}×${a.height}` : ""}${a.downscaled ? " · shrunk for the model" : ""}` : "")
                : a.status === "ready" ? `Ready · ${a.duration_s ? mmss(a.duration_s) : ""}` : a.status === "processing" ? `${a.duration_s ? mmss(a.duration_s) + " · " : ""}processing on this computer` : "Could not be processed"}
            </div>
          </div>
        </div>
        <button type="button" className="btn small" aria-label={`Remove ${a.filename}`} disabled={remove.isPending} onClick={() => remove.mutate()}>Remove</button>
      </div>
      {a.kind === "video" && a.status !== "error" && st && (
        <div className="stages" aria-label={`Processing ${a.filename}`}>
          {([["frames", "Keyframes"], ["transcript", "Transcript"], ["cuts", "Cuts"]] as const).map(([k, label]) => (
            <div className="stage" key={k}>
              <span>{stepText(label, st[k])}</span>
              <div className="bar" role="progressbar" aria-label={label} aria-valuenow={pct(st[k])} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${pct(st[k])}%` }} /></div>
            </div>
          ))}
        </div>
      )}
      {a.notes.map((n) => <p key={n} className="small muted" style={{ margin: 0 }}>{n}</p>)}
      {a.status === "error" && (
        <div role="alert" className="stack" style={{ gap: 6, background: "var(--danger-panel)", border: "1px solid var(--danger-border)", borderRadius: 8, padding: 10 }}>
          <span className="error" style={{ fontSize: 13 }}>{a.error}</span>
          <div><button type="button" className="btn small" disabled={retry.isPending} onClick={() => retry.mutate()}>Try this clip again</button></div>
        </div>
      )}
    </li>
  );
}

/** Pictures and clips for this attempt: drop them here or browse. Clips are processed on this computer before they are sent. */
export function Attachments({ sessionId, assets, mediaEnabled, vision }: { sessionId: number; assets: Asset[]; mediaEnabled: boolean; vision: boolean | null }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState<{ name: string; message: string }[]>([]);
  const up = useMutation({
    mutationFn: (f: File) => api.uploadAsset(sessionId, f),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session", sessionId] }),
    onError: (e, f) => setRejected((r) => [...r.filter((x) => x.name !== f.name), { name: f.name, message: e.message }]),
  });
  const take = (files: FileList | File[] | null) => Array.from(files ?? []).forEach((f) => up.mutate(f));
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); };

  if (!mediaEnabled) {
    return (
      <section aria-label="Pictures and clips" className="inset stack" style={{ gap: 4 }}>
        <strong>Pictures and clips are off</strong>
        <span className="small">They need ffmpeg and Whisper on this computer. Text practice still works. <a href="/setup">See what is missing</a>.</span>
      </section>
    );
  }
  return (
    <section aria-label="Pictures and clips" className="stack" style={{ gap: 10 }}>
      <div className="eyebrow">Attachments</div>
      {vision === false && (
        <p role="status" className="small" style={{ margin: 0, background: "var(--warning-soft)", color: "var(--warning)", padding: "8px 12px", borderRadius: 8 }}>
          Your language model cannot read pictures, so pictures and clips would not be judged. Switch to a model that can in Setup, or submit text only.
        </p>
      )}
      {assets.length > 0 && <ul className="list" style={{ gap: 8 }}>{assets.map((a) => <Row key={a.id} a={a} sessionId={sessionId} />)}</ul>}
      {rejected.map((r) => (
        <div key={r.name} role="alert" className="row" style={{ background: "var(--danger-panel)", border: "1px solid var(--danger-border)", borderRadius: 8, padding: 10, flexWrap: "nowrap" }}>
          <span className="error" style={{ fontSize: 14 }}><strong className="mono">{r.name}</strong> · {r.message}</span>
          <button type="button" className="btn small" aria-label={`Dismiss message about ${r.name}`} onClick={() => setRejected(rejected.filter((x) => x !== r))}>Dismiss</button>
        </div>
      ))}
      <div className={`dropzone ${over ? "dropping" : ""}`} style={{ minHeight: 96 }} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <span>Drop pictures or video clips here, or</span>
        <input ref={input} id="attach" type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv,.mov"
          className="sr-only" onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
        <label htmlFor="attach" className="btn" style={{ cursor: "pointer" }}>Browse files</label>
        <span className="small muted">PNG, JPG, MP4, MOV · clips up to 3 min</span>
      </div>
      <p className="small muted" style={{ margin: 0 }}>A clip is sent when processing finishes. Nothing leaves this computer except the prompt to your language model.</p>
    </section>
  );
}
