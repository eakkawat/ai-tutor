import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type SessionView } from "../api";
import { MessageView, mmss, PhaseStepper, SourcePanel, useTick } from "../components/SessionParts";

const LEVEL: Record<string, string> = { none: "Not yet", define: "Define only", spot: "Spot", use: "Use" };
const HEARTBEAT_MS = 30_000;

function Pass({ v }: { v: SessionView }) {
  const next = useQuery({ queryKey: ["next", v.id], queryFn: () => api.nextSkill(v.id), retry: false });
  return (
    <section className="card action stack" aria-label="Skill passed">
      <div className="eyebrow">Pass</div>
      <h1 style={{ fontSize: 26 }}>{v.skill.name}: passed</h1>
      <p style={{ margin: 0 }}>You logged <span className="mono">{v.hours.toFixed(1)}</span> hours on this skill. It will come back in your reviews.</p>
      {next.isPending && <p role="status" className="small muted" style={{ margin: 0 }}>Finding your next skill…</p>}
      {next.data?.next && (
        <div className="inset stack"><span className="eyebrow">Suggested next</span><strong>{next.data.next.name}</strong>
          {next.data.next.why && <span className="small">{next.data.next.why}</span>}</div>
      )}
      {next.data && !next.data.next && next.data.note && <p className="small muted" style={{ margin: 0 }}>{next.data.note}</p>}
      <div className="row" style={{ justifyContent: "flex-start" }}>
        <Link to="/new" className="btn primary">Choose your next skill</Link><Link to="/" className="btn">Home</Link>
      </div>
    </section>
  );
}

export default function Session() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["session", id], queryFn: () => api.session(id), retry: false });
  const v = q.data;
  const [panel, setPanel] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [question, setQuestion] = useState("");
  const [last, setLast] = useState<{ action: string; text?: string } | null>(null);
  const act = useMutation({
    mutationFn: (a: { action: string; text?: string }) => { setLast(a); return api.act(id, a.action, a.text ?? ""); },
    onSuccess: (view, a) => { qc.setQueryData(["session", id], view); setLast(null); if (a.action === "answer" || a.action === "submit") setText(""); if (a.action === "ask") setQuestion(""); },
  });
  const begun = useRef(false);

  // The first thing a new session does is set the diagnostic task.
  useEffect(() => {
    if (v && v.phase === "diagnose" && v.messages.length === 0 && !begun.current && !v.ended) { begun.current = true; act.mutate({ action: "begin" }); }
  }, [v]);                                                                                        // eslint-disable-line react-hooks/exhaustive-deps

  // The draft is saved as you type, and restored after a restart.
  const timed = v?.phase === "practice" || v?.phase === "revise";
  const draftLoaded = useRef(false);
  useEffect(() => { if (v && !draftLoaded.current) { draftLoaded.current = true; if (v.draft) setText(v.draft); } }, [v]);
  useEffect(() => {
    if (!timed || !draftLoaded.current) return;
    const h = setTimeout(() => { api.saveDraft(id, text).catch(() => undefined); }, 800);
    return () => clearTimeout(h);
  }, [text, timed, id]);

  // While the clock runs, tell the server the screen is still here.
  const running = v?.timer.running === true;
  useEffect(() => {
    if (!running) return;
    const h = setInterval(() => { api.act(id, "heartbeat").then((view) => qc.setQueryData(["session", id], view)).catch(() => undefined); }, HEARTBEAT_MS);
    return () => clearInterval(h);
  }, [running, id, qc]);

  const elapsed = useTick(v?.timer.elapsed_s ?? 0, v?.timer.running ?? false, `${v?.phase}-${v?.attempt}`);

  if (q.isError) return <main className="page medium"><h1>Session not found</h1><p role="alert" className="error">{q.error.message}</p><Link to="/" className="btn" style={{ alignSelf: "flex-start" }}>Home</Link></main>;
  if (!v) return <main className="page medium" role="status">Loading…</main>;

  const can = (a: string) => v.allowed.includes(a);
  const busy = act.isPending;
  const err = act.error as Error | null;
  const lastMsg = v.messages[v.messages.length - 1];
  const left = v.timer.limit_s - elapsed;
  const open = (cid: number) => setPanel(cid);
  const run = (action: string, t?: string) => act.mutate({ action, text: t });

  return (
    <main className="page wide">
      <nav aria-label="Breadcrumb" className="small muted"><Link to="/">Home</Link> / {v.project.name} / {v.skill.name}</nav>
      <header className="row">
        <div><h1 style={{ fontSize: 24 }}>{v.skill.name}</h1>
          <div className="small muted">Difficulty <span className="mono">{v.difficulty} / 5</span> · Practice hours on this skill <span className="mono">{v.hours.toFixed(1)} / 20</span></div></div>
        {timed && (
          <div className="row" style={{ gap: 12 }}>
            <div><div className="eyebrow">Task time {left >= 0 ? "left" : "over"}</div>
              <div className={`timer ${left < 0 ? "over" : ""}`} role="timer" aria-label="Task time">{left < 0 ? "+" : ""}{mmss(left)}</div></div>
            <button type="button" className="btn" disabled={busy} onClick={() => run(v.timer.running ? "pause_timer" : "resume_timer")}>{v.timer.running ? "Pause timer" : "Resume timer"}</button>
          </div>
        )}
      </header>
      <PhaseStepper phase={v.phase} />

      <div className="viewer">
        <div className="main stack">
          {v.messages.map((m) => <MessageView key={m.id} m={m} onOpen={open} />)}
          {busy && <p role="status" className="muted" style={{ margin: 0 }}>{last?.action === "advance" ? "Preparing your lesson…" : last?.action === "begin" ? "Writing your first task…" : "Thinking…"}</p>}
          {err && !busy && (
            <div role="alert" className="card problem stack"><span>{err.message}</span>
              {err instanceof ApiError && err.retryable && last && <div><button type="button" className="btn" onClick={() => act.mutate(last)}>Try again</button></div>}
              {err instanceof ApiError && err.retryable && !last && <div><button type="button" className="btn" onClick={() => act.reset()}>Dismiss</button></div>}
            </div>
          )}

          {v.phase === "diagnose" && lastMsg?.kind === "diagnose_task" && !v.diagnosis && (
            <form className="card action stack" onSubmit={(e) => { e.preventDefault(); run("answer", text); }}>
              <label htmlFor="answer">Your answer</label>
              <textarea id="answer" className="bigtext" style={{ minHeight: 140 }} value={text} onChange={(e) => setText(e.target.value)} />
              <div><button type="submit" className="btn primary" disabled={busy || !text.trim()}>Send answer</button></div>
            </form>
          )}
          {v.phase === "diagnose" && v.diagnosis && can("advance") && (
            <div><button type="button" className="btn primary" disabled={busy} onClick={() => run("advance")}>Continue to the lesson</button></div>
          )}
          {v.phase === "learn" && <div><button type="button" className="btn primary" disabled={busy} onClick={() => run("continue")}>Continue to the check</button></div>}

          {v.phase === "check" && (
            <section className="locked" aria-label="Foundations check">
              <div className="eyebrow">Check · foundations</div>
              <ul className="list" style={{ gap: 6 }}>
                {v.gate.concepts.map((c) => <li key={c.id} className="row"><span>{c.name}</span><span className={`pill ${c.level === "use" || c.level === "spot" ? "success" : c.level === "define" ? "warning" : "neutral"}`}>{LEVEL[c.level]}</span></li>)}
              </ul>
              {!v.gate.unlocked && <p id="why-locked" role="status" style={{ margin: 0 }}>{v.gate.message}</p>}
              <div><button type="button" className="btn primary" disabled={busy || !v.gate.unlocked} aria-describedby={v.gate.unlocked ? undefined : "why-locked"}
                onClick={() => run("unlock")}>{v.gate.unlocked ? "Start practice" : "Practice is locked"}</button></div>
            </section>
          )}

          {timed && v.task && (
            <form className="card action stack" aria-label="Practice task" onSubmit={(e) => { e.preventDefault(); run("submit", text); }}>
              <div className="eyebrow">{v.phase === "revise" ? "Revise" : "Practice"} · {v.task.minutes} min · Attempt {v.next_attempt}</div>
              <div className="row" style={{ justifyContent: "flex-start", gap: 8 }}>
                {v.task.support && <span className="tag">Support: {v.task.support}</span>}<span className="tag">Speed over polish</span>
              </div>
              {v.task.template.length > 0 && <ol className="small" style={{ margin: 0 }}>{v.task.template.map((b) => <li key={b}>{b}</li>)}</ol>}
              <label htmlFor="work">Your work</label>
              <textarea id="work" className="bigtext" value={text} onChange={(e) => setText(e.target.value)} />
              <div><button type="submit" className="btn primary" disabled={busy || !text.trim()}>Submit attempt {v.next_attempt}</button></div>
            </form>
          )}
          {v.phase === "feedback" && !v.ended && <p role="status" className="card" style={{ margin: 0 }}>Attempt {v.attempt} is saved. Feedback on it is not available yet.</p>}
          {v.phase === "pass" && <Pass v={v} />}

          <form className="card stack" aria-label="Ask a question" onSubmit={(e) => { e.preventDefault(); run("ask", question); }}>
            <label htmlFor="ask">Ask a question about this skill</label>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input id="ask" className="input" style={{ fontFamily: "var(--font-sans)", flex: 1 }} value={question} onChange={(e) => setQuestion(e.target.value)} />
              <button type="submit" className="btn" disabled={busy || !question.trim()}>Ask</button>
            </div>
          </form>
        </div>
        <aside className="stack">
          {panel !== null && <SourcePanel chunkId={panel} onClose={() => setPanel(null)} />}
          <section className="card stack" aria-label="Judged on">
            <div className="eyebrow">Your work will be judged on</div>
            <ol className="list" style={{ gap: 8, paddingLeft: 18 }}>
              {v.skill.principles.map((p) => <li key={p.id}>{p.principle}{p.citation && <> <button type="button" className="cite" onClick={() => open(p.chunk_id)}>{p.citation}</button></>}</li>)}
            </ol>
          </section>
        </aside>
      </div>
    </main>
  );
}
