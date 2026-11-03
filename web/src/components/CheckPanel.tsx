import { useState } from "react";
import type { SessionView } from "../api";

const LEVEL: Record<string, string> = { none: "Not yet", define: "Define only", spot: "Spot", use: "Use" };
const TONE: Record<string, string> = { none: "neutral", define: "warning", spot: "success", use: "success" };

/** The foundations check: practice needs each concept at Spot. One question at a time, a hint before the answer is shown. */
export function CheckPanel({ v, busy, run }: { v: SessionView; busy: boolean; run: (action: string, text?: string) => void }) {
  const [text, setText] = useState("");
  const [pick, setPick] = useState<string | null>(null);
  const c = v.check;
  const q = c?.current ?? null;
  const send = () => { run("check_answer", q && q.options.length >= 2 ? (pick ?? "") : text); setText(""); setPick(null); };

  return (
    <section className="locked" aria-label="Foundations check" style={q ? { borderStyle: "solid", borderColor: "var(--accent)" } : undefined}>
      <div className="eyebrow">Check · foundations{c && !c.all_done ? ` · about ${c.remaining_minutes} min` : ""}</div>
      <ul className="list" style={{ gap: 6 }}>
        {v.gate.concepts.map((k) => <li key={k.id} className="row"><span>{k.name}</span><span className={`pill ${TONE[k.level]}`}>{LEVEL[k.level]}</span></li>)}
      </ul>

      {q && (
        <form className="stack" aria-label={`Question about ${q.concept}`} onSubmit={(e) => { e.preventDefault(); send(); }}>
          <div className="eyebrow">{q.level === "define" ? "Define" : "Spot"} · {q.concept}</div>
          {q.options.length >= 2 ? (
            <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 8 }}>
              <legend className="sr-only">Choose one</legend>
              {q.options.map((o) => <button key={o} type="button" className="choice" aria-pressed={pick === o} onClick={() => setPick(o)}>{o}</button>)}
            </fieldset>
          ) : (
            <div className="field"><label htmlFor="check-answer">Your answer, in your own words</label>
              <textarea id="check-answer" className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} /></div>
          )}
          <p className="small muted" style={{ margin: 0 }}>Pick one, then check. A hint comes before the answer.</p>
          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="btn primary" disabled={busy || (q.options.length >= 2 ? !pick : !text.trim())}>Check answer</button>
            <button type="button" className="btn" disabled={busy || q.hint_shown} onClick={() => run("check_hint")}>Hint</button>
          </div>
        </form>
      )}

      {!q && c && !c.all_done && (
        c.budget_left > 0
          ? <div><button type="button" className="btn primary" disabled={busy} onClick={() => run("check")}>Next question</button></div>
          : <div className="stack"><p role="status" style={{ margin: 0 }}>That is enough for one sitting. Take a short break.</p>
              <div><button type="button" className="btn" disabled={busy} onClick={() => run("check_more")}>Keep checking</button></div></div>
      )}

      <div>
        {!v.gate.unlocked && <p id="why-locked" role="status" style={{ margin: "0 0 10px" }}>{v.gate.message}</p>}
        <button type="button" className="btn primary" disabled={busy || !v.gate.unlocked} aria-describedby={v.gate.unlocked ? undefined : "why-locked"}
          onClick={() => run("unlock")}>{v.gate.unlocked ? (v.attempt > 0 ? "Start the next attempt" : "Start practice") : "Practice is locked"}</button>
      </div>
    </section>
  );
}
