import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

const today = () => new Date().toISOString().slice(0, 10);
const when = (s: string) => (s.slice(0, 10) === today() ? "Today" : s.slice(0, 10));

function Tile({ label, value }: { label: string; value: string }) {
  return <div className="card" style={{ padding: 16 }}><div className="small muted">{label}</div><div className="mono" style={{ fontSize: 24, fontWeight: 500 }}>{value}</div></div>;
}

export default function Progress() {
  const q = useQuery({ queryKey: ["progress"], queryFn: api.progress });
  if (!q.data) return <main className="page wide" role="status">Loading…</main>;
  const { totals: t, skills, mistakes, flow_history: hist, target } = q.data;
  return (
    <main className="page wide">
      <h1>Progress</h1>
      <div className="steps" role="group" aria-label="Totals">
        <Tile label="Total practice" value={`${t.practice_hours.toFixed(1)} h`} />
        <Tile label="Skills passed" value={String(t.skills_passed)} />
        <Tile label={'Tasks "just right"'} value={`${t.just_right[0]} of ${t.just_right[1]}`} />
        <Tile label="Reviews answered right" value={`${t.reviews_right[0]} of ${t.reviews_right[1]}`} />
      </div>

      <section className="card stack" aria-labelledby="hours-h">
        <h2 id="hours-h">Hours toward {target}, per skill</h2>
        <p className="small muted" style={{ margin: 0 }}>{target} hours is the target, not a requirement. You pass when your work follows the principles.</p>
        {skills.length === 0 && <p role="status" style={{ margin: 0 }}>No practice yet. Start a skill and your hours appear here.</p>}
        <ul className="list" style={{ gap: 14 }}>
          {skills.map((s) => (
            <li key={s.id} className="stack" style={{ gap: 4 }}>
              <div className="row"><span><strong>{s.name}</strong> <span className="small muted">· {s.status_text}</span></span>
                <span className="mono">{s.hours.toFixed(1)} h{s.over > 0 ? ` · ${s.over.toFixed(1)} past the target` : ""}</span></div>
              <div className="bar" style={{ height: 12 }} role="progressbar" aria-label={`${s.name}: ${s.hours.toFixed(1)} of ${target} hours`}
                aria-valuenow={Number((s.bar * 100).toFixed(1))} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${s.bar * 100}%`, background: s.status === "passed" ? "var(--success)" : undefined }} /></div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card stack" aria-labelledby="mist-h">
        <h2 id="mist-h">Recurring mistakes</h2>
        {mistakes.length === 0 ? <p role="status" style={{ margin: 0 }}>No mistakes recorded yet.</p> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", minWidth: 480, borderCollapse: "collapse" }}>
              <thead><tr className="small muted" style={{ textAlign: "left" }}><th scope="col">Mistake</th><th scope="col" style={{ textAlign: "right" }}>Times</th><th scope="col">Last seen</th><th scope="col">Status</th></tr></thead>
              <tbody>
                {mistakes.map((m) => (
                  <tr key={`${m.skill}-${m.kind}-${m.tag}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "10px 0" }}>{m.tag} <span className="small muted">· {m.kind === "concept" ? "concept" : "execution"}</span></td>
                    <td className="mono" style={{ textAlign: "right" }}>{m.count}</td><td>{when(m.last_seen)}</td><td>{m.fixed ? "Fixed" : "Still happening"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card stack" aria-labelledby="flow-h">
        <h2 id="flow-h">Flow history</h2>
        {hist.length === 0 ? <p role="status" style={{ margin: 0 }}>No ratings yet. After each task you say how it felt.</p> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", minWidth: 480, borderCollapse: "collapse" }}>
              <thead><tr className="small muted" style={{ textAlign: "left" }}><th scope="col">Task</th><th scope="col">Felt</th><th scope="col">What changed</th></tr></thead>
              <tbody>
                {hist.map((h) => (
                  <tr key={h.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "10px 0" }}>{h.task}{h.skill && <span className="small muted"> · {h.skill}</span>}</td>
                    <td>{h.felt}{h.inferred && <span className="small muted"> (judged from your work)</span>}</td><td>{h.changed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
