import type { FbMeta, FbResult } from "../api";

const PILL: Record<FbResult["result"], { text: string; tone: string }> = {
  followed: { text: "Followed", tone: "success" }, partly: { text: "Partly", tone: "warning" }, not: { text: "Not followed", tone: "danger" },
};

/** The checklist, item by item: a verdict in words, the principle with its citation, and the evidence from the work. */
export function FeedbackView({ meta, onOpen }: { meta: FbMeta; onOpen: (chunkId: number) => void }) {
  const repeated = meta.mistakes.filter((m) => (m.count ?? 1) >= 2).map((m) => m.tag);
  return (
    <div className="stack">
      <h2 style={{ fontSize: 20 }}>{meta.summary}</h2>
      {meta.since && <div className="inset stack" style={{ gap: 2 }}><span className="eyebrow">Since the last attempt</span><span>{meta.since}</span></div>}
      <ul className="list" aria-label="Principle checklist" style={{ gap: 0 }}>
        {meta.results.map((r) => (
          <li key={r.n} className="stack" style={{ gap: 6, padding: "12px 0", borderTop: r.n > 1 ? "1px solid var(--border-subtle)" : undefined }}>
            <div className="row" style={{ justifyContent: "flex-start", gap: 10, alignItems: "flex-start" }}>
              <span className={`pill ${PILL[r.result].tone}`} style={{ minWidth: 92, textAlign: "center" }}>{PILL[r.result].text}</span>
              <div style={{ flex: 1 }}>
                <strong>{r.principle}</strong>{" "}
                {r.citation && <button type="button" className="cite" onClick={() => onOpen(r.chunk_id)}>{r.citation}</button>}
              </div>
            </div>
            {(r.locator || r.comment) && (
              <div className="small" style={{ paddingLeft: 102 }}>
                {r.locator && <span className="mono">{r.locator}</span>}{r.locator && r.comment && " · "}{r.comment}
                {r.quote && <div className="mono muted" style={{ marginTop: 4 }}>“{r.quote}”</div>}
              </div>
            )}
          </li>
        ))}
      </ul>
      {meta.fixes.length > 0 && (
        <div className="inset stack" aria-label="Fixes">
          <span className="eyebrow">Fix {meta.fixes.length === 1 ? "this" : `these ${meta.fixes.length === 2 ? "two" : meta.fixes.length}`}</span>
          <ol className="list" style={{ gap: 8, paddingLeft: 18 }}>
            {meta.fixes.map((f) => (
              <li key={f.n}>{f.fix}{f.example && <> For example: {f.example}</>}{" "}
                {f.citation && <button type="button" className="cite" onClick={() => onOpen(f.chunk_id)}>{f.citation}</button>}</li>
            ))}
          </ol>
        </div>
      )}
      {repeated.length > 0 && <p className="small muted" style={{ margin: 0 }}>Recurring mistake: {repeated.join(", ")}.</p>}
    </div>
  );
}
