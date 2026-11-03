import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type ReviewRun, type ReviewSummary } from "../api";
import { CitationChip } from "../components/CitationChip";

const LEVEL_TEXT: Record<string, string> = { none: "Not yet", define: "Define", spot: "Spot", use: "Use" };

function Summary({ run, s, onContinue }: { run: ReviewRun; s: ReviewSummary; onContinue: () => void }) {
  const concept = run.mode === "concept";
  return (
    <section className="card stack" aria-labelledby="sum-h">
      <h1 id="sum-h" style={{ fontSize: 24 }}>{concept ? "Check finished" : "Review finished"}</h1>
      <p className="lead" role="status" style={{ margin: 0 }}>
        {s.right} right, {s.wrong} to come back sooner.{s.skipped > 0 ? ` ${s.skipped} left for another time.` : ""}
        {concept && s.level ? ` This concept is now at ${LEVEL_TEXT[s.level]}.` : ""}
      </p>
      {s.rows.length > 0 && (
        <ul className="list" style={{ gap: 8 }}>
          {s.rows.map((r, i) => (
            <li key={i} className="row"><span>{r.context}</span>
              <span>{r.result === "right" ? "Right" : "Missed"}{r.when ? ` · ${r.when}` : ""}</span></li>
          ))}
        </ul>
      )}
      {s.notes.map((n) => <p key={n} className="warn-row" style={{ margin: 0 }}>{n}</p>)}
      <div className="row" style={{ justifyContent: "flex-start" }}>
        {run.mode === "continue" && run.session_id
          ? <button type="button" className="btn primary" onClick={onContinue}>Back to your skill</button>
          : concept ? <Link to="/concepts" className="btn primary">Back to Concepts</Link> : <Link to="/" className="btn primary">Back to Home</Link>}
      </div>
    </section>
  );
}

/** Review mode, the two questions before Continue, and the 3-minute check on one concept: one question at a time. */
export default function Review() {
  const [params] = useSearchParams();
  const mode = (params.get("mode") ?? "review") as ReviewRun["mode"];
  const session = params.get("session") ? Number(params.get("session")) : undefined;
  const concept = params.get("concept") ? Number(params.get("concept")) : undefined;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [none, setNone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [pick, setPick] = useState<string | null>(null);

  const resume = () => nav(session ?? run?.session_id ? `/session/${session ?? run?.session_id}` : "/", { replace: true });

  useEffect(() => {
    let live = true;
    api.reviewStart(mode, { sessionId: session, conceptId: concept }).then((r) => {
      if (!live) return;
      if (r.run) setRun(r.run);
      else if (mode === "continue" && session) nav(`/session/${session}`, { replace: true });          // nothing to review: straight to the work
      else setNone(true);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [mode, session, concept, nav]);

  async function go(fn: () => Promise<ReviewRun>, clear = false) {
    setBusy(true);
    setError(null);
    try {
      setRun(await fn());
      if (clear) { setText(""); setPick(null); }
      qc.invalidateQueries({ queryKey: ["home"] });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (error && !run) return <main className="page narrow"><p className="error" role="alert">{error}</p><Link to="/" className="btn">Back to Home</Link></main>;
  if (none) return (
    <main className="page narrow">
      <h1>Review</h1>
      <p className="lead" role="status">Nothing is due. Questions come back a day or more after you pass a skill or check a concept.</p>
      <div><Link to="/" className="btn primary">Back to Home</Link></div>
    </main>
  );
  if (!run) return <main className="page narrow" role="status">Loading…</main>;
  if (run.ended && run.summary) return <main className="page narrow"><Summary run={run} s={run.summary} onContinue={resume} /></main>;

  const q = run.current!;
  const choices = q.options.length >= 2;
  const answer = choices ? (pick ?? "") : text;
  const last = q.n >= run.total;
  const title = run.mode === "concept" ? "3-minute check" : run.mode === "continue" ? "Before you continue" : "Review";

  return (
    <main className="page narrow">
      <div className="row">
        <h1>{title}</h1>
        <button type="button" className="btn quiet" disabled={busy} onClick={() => go(() => api.reviewEnd(run.id))}>End review</button>
      </div>
      <section className="card stack" aria-label={`Question ${q.n} of ${run.total}`}>
        <div className="row"><span className="eyebrow">Question {q.n} of {run.total} · {LEVEL_TEXT[q.level]}</span><span className="small muted">{q.context}</span></div>
        <p style={{ margin: 0, fontSize: 16, whiteSpace: "pre-wrap" }}>{choices ? q.prompt.split("\n")[0] : q.prompt}</p>

        {!q.finished && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); if (answer.trim()) go(() => api.reviewAnswer(run.id, answer), true); }}>
            {choices ? (
              <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 8 }}>
                <legend className="sr-only">Choose one</legend>
                {q.options.map((o) => <button key={o} type="button" className="choice" aria-pressed={pick === o} onClick={() => setPick(o)}>{o}</button>)}
              </fieldset>
            ) : (
              <div className="field"><label htmlFor="review-answer">Your answer</label>
                <textarea id="review-answer" className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} /></div>
            )}
            {q.attempts > 0 && <p role="status" style={{ margin: 0 }}><strong>Not quite.</strong> {q.feedback}</p>}
            {q.hint && <p className="inset" style={{ margin: 0 }}><span><strong>Hint.</strong> {q.hint}</span></p>}
            <p className="small muted" style={{ margin: 0 }}>Your first answer is the one that counts. Missed questions come back sooner.</p>
            <div className="row" style={{ justifyContent: "flex-start" }}>
              <button type="submit" className="btn primary" disabled={busy || !answer.trim()}>{q.attempts > 0 ? "Try again" : "Check answer"}</button>
              <button type="button" className="btn" disabled={busy || !!q.hint} onClick={() => go(() => api.reviewHint(run.id))}>Hint</button>
              <button type="button" className="btn" disabled={busy} onClick={() => go(() => api.reviewShow(run.id))}>Show answer</button>
            </div>
          </form>
        )}

        {q.finished && (
          <div className="stack" role="status">
            <p style={{ margin: 0 }}><strong>{q.correct ? (q.first === "right" ? "Right." : "Right this time.") : "Not quite."}</strong> {q.feedback}</p>
            {q.answer && <p className="inset" style={{ margin: 0 }}><span><strong>The answer.</strong> {q.answer}</span></p>}
            {q.citations.length > 0 && <div className="row" style={{ justifyContent: "flex-start" }}>{q.citations.map((c) => <CitationChip key={c.chunk_id} chunkId={c.chunk_id} citation={c.citation} />)}</div>}
            <div><button type="button" className="btn primary" disabled={busy} onClick={() => go(() => api.reviewNext(run.id), true)}>
              {last || (run.mode === "concept" && q.first === "wrong") ? "See summary" : "Next question"}</button></div>
          </div>
        )}
      </section>
      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}
