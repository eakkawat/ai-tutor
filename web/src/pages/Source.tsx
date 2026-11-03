import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

/** The passage behind a citation, with a little text before and after it (B6). */
export default function Source() {
  const { chunkId } = useParams();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["passage", chunkId], queryFn: () => api.passage(Number(chunkId)), retry: false });
  if (q.isError) {
    return (
      <main className="page medium">
        <h1>Passage not found</h1>
        <p role="alert" className="error">{q.error.message}</p>
        <Link to="/library" className="btn" style={{ alignSelf: "flex-start" }}>Back to Library</Link>
      </main>
    );
  }
  const p = q.data;
  if (!p) return <main className="page medium" role="status">Loading…</main>;
  const pages = p.page_start === p.page_end ? `page ${p.page_start}` : `pages ${p.page_start}–${p.page_end}`;
  return (
    <main className="page wide">
      <div className="row">
        <button type="button" className="btn" onClick={() => nav(-1)}>Back</button>
        <span className="mono small muted">{p.page_start === p.page_end ? `p. ${p.page_start}` : `pp. ${p.page_start}–${p.page_end}`}</span>
      </div>
      <div className="viewer">
        <div className="main">
          <div className="reader-bg">
            <article className="reader" aria-label="Book passage">
              {p.before && <span className="ctx">…{p.before}{"\n\n"}</span>}
              <mark>{p.text}</mark>
              {p.after && <span className="ctx">{"\n\n"}{p.after}…</span>}
            </article>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button type="button" className="btn" disabled={p.prev_id === null} onClick={() => nav(`/source/${p.prev_id}`, { replace: true })}>Previous passage</button>
            <button type="button" className="btn" disabled={p.next_id === null} onClick={() => nav(`/source/${p.next_id}`, { replace: true })}>Next passage</button>
          </div>
        </div>
        <aside className="card stack">
          <div className="small muted" style={{ letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600 }}>Source</div>
          <h2>{p.source_title}</h2>
          <div className="mono small muted">{[p.author, p.label && p.label !== p.title ? p.label : null, p.title, pages].filter(Boolean).join(" · ")}</div>
          <div className="mono small">{p.citation}</div>
        </aside>
      </div>
    </main>
  );
}
