import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type ConceptRow } from "../api";
import { CitationChip } from "../components/CitationChip";

const LEVEL: Record<string, string> = { none: "Not yet", define: "Define only", spot: "Spot", use: "Use" };
const TONE: Record<string, string> = { none: "neutral", define: "warning", spot: "success", use: "success" };
const ORDER = { none: 0, define: 1, spot: 2, use: 3 };

function LevelPill({ level }: { level: ConceptRow["level"] }) {
  return <span className={`pill ${TONE[level]}`}>{LEVEL[level]}</span>;
}

function Detail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["concept", id], queryFn: () => api.concept(id) });
  if (!q.data) return <section className="card" role="status">Loading…</section>;
  const c = q.data;
  const rank = ORDER[c.level];
  const steps = [["Define", 1], ["Spot", 2], ["Use", 3]] as const;
  return (
    <section className="card stack" aria-label={`Concept: ${c.name}`}>
      <div className="row"><h2>{c.name}</h2>{c.is_foundation && <span className="pill info">Foundation</span>}</div>
      <div><div className="eyebrow">Definition</div><p style={{ margin: "4px 0 0" }}>{c.definition}</p></div>
      <div><div className="eyebrow">Film example</div><p style={{ margin: "4px 0 0" }}>{c.example}</p></div>
      {c.sources.length > 0 && <div className="row" style={{ justifyContent: "flex-start" }}>{c.sources.map((s) => <CitationChip key={s.chunk_id} chunkId={s.chunk_id} citation={s.citation} />)}</div>}

      <div>
        <div className="eyebrow">Your level</div>
        <ol className="list" style={{ gap: 6, marginTop: 6 }}>
          {steps.map(([name, n]) => (
            <li key={name} className="row"><span>{n} · {name}</span><span>{rank >= n ? "Done" : "Not yet"}</span></li>
          ))}
        </ol>
        {c.last_checked_at && <p className="small muted" style={{ margin: "6px 0 0" }}>Last checked {c.last_checked_at.slice(0, 10)}.</p>}
      </div>

      {c.confusions.length > 0 && (
        <p className="warn-row" style={{ margin: 0 }}>
          You tend to mix this up with {c.confusions.map((x) => `${x.with} (${x.count}×)`).join(", ")}.
        </p>
      )}

      <div>
        <div className="eyebrow">Used by</div>
        {c.skills.length === 0 ? <p className="small muted" style={{ margin: "4px 0 0" }}>No skill on your map uses it yet.</p> : (
          <ul className="list" style={{ gap: 6, marginTop: 6 }}>
            {c.skills.map((s) => {
              const needs = rank < ORDER[s.required_level];
              return <li key={s.id} className="row"><span>{s.name}</span><span className="small muted">{needs ? `needs ${LEVEL[s.required_level]}` : "ready"}</span></li>;
            })}
          </ul>
        )}
      </div>

      <div><Link to={`/review?mode=concept&concept=${c.id}`} className="btn primary">Check this concept · 3 min</Link></div>
    </section>
  );
}

type Filter = "all" | "foundations" | "shaky";

export default function Concepts() {
  const q = useQuery({ queryKey: ["concepts"], queryFn: api.concepts });
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  if (!q.data) return <main className="page wide" role="status">Loading…</main>;
  const all = q.data.concepts;
  if (all.length === 0) return (
    <main className="page medium"><h1>Concepts</h1>
      <p className="lead" role="status">No concepts yet. They are collected from your books when you find skills in a book.</p>
      <div><Link to="/library" className="btn primary">Open the Library</Link></div></main>
  );

  const count = (l: ConceptRow["level"]) => all.filter((c) => c.level === l).length;
  const shaky = (c: ConceptRow) => c.confused_with !== null || c.level === "define";
  const shown = all.filter((c) => (filter === "foundations" ? c.is_foundation : filter === "shaky" ? shaky(c) : true) && c.name.toLowerCase().includes(search.trim().toLowerCase()));
  const selected = picked ?? shown[0]?.id ?? null;
  const filters: [Filter, string][] = [["all", `All · ${all.length}`], ["foundations", "Foundations first"], ["shaky", `Shaky · ${all.filter(shaky).length}`]];

  return (
    <main className="page wide">
      <div><h1>Concepts</h1>
        <p className="lead">{all.length} fundamentals from your books. Foundations are used by many skills, so they come first.</p></div>
      <p role="status" className="small" style={{ margin: 0 }}>Use {count("use")} · Spot {count("spot")} · Define only {count("define")} · Not yet {count("none")}</p>
      <div className="row" style={{ justifyContent: "flex-start" }}>
        <div className="chips" role="group" aria-label="Show">
          {filters.map(([k, label]) => <button key={k} type="button" className="chip" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>)}
        </div>
        <div className="field" style={{ flex: "0 1 260px", minWidth: 180 }}>
          <label htmlFor="concept-search" className="sr-only">Search concepts</label>
          <input id="concept-search" className="input" type="search" placeholder="Search concepts" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>
      <div className="viewer">
        <div className="main card">
          {shown.length === 0 ? <p role="status" style={{ margin: 0 }}>No concept matches.</p> : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr className="small muted" style={{ textAlign: "left" }}><th scope="col">Concept</th><th scope="col">Your level</th><th scope="col">Used by</th></tr></thead>
              <tbody>
                {shown.map((c) => (
                  <tr key={c.id} style={{ borderTop: "1px solid var(--border-subtle)", background: c.id === selected ? "var(--accent-tint)" : undefined }}>
                    <td style={{ padding: "6px 0" }}>
                      <button type="button" className="btn quiet" style={{ height: "auto", minHeight: 44, textAlign: "left", padding: "0 8px", color: "var(--text)" }}
                        aria-current={c.id === selected ? "true" : undefined} onClick={() => setPicked(c.id)}>
                        {c.name}{c.is_foundation && <span className="small muted"> · Foundation</span>}
                        {c.confused_with && <span className="small muted"> · Confused with {c.confused_with} {c.confusion_count}×</span>}
                      </button>
                    </td>
                    <td><LevelPill level={c.level} /></td>
                    <td className="small muted">{c.skills} {c.skills === 1 ? "skill" : "skills"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <aside>{selected !== null && <Detail id={selected} />}</aside>
      </div>
    </main>
  );
}
