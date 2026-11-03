import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type SessionView } from "../api";
import { Attachments } from "../components/Attachments";
import { CheckPanel } from "../components/CheckPanel";
import { MessageView, mmss, PhaseStepper, SourcePanel, useTick } from "../components/SessionParts";

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
  const q = useQuery({
    queryKey: ["session", id], queryFn: () => api.session(id), retry: false,
    refetchInterval: (query) => (query.state.data?.assets.some((a) => a.status === "processing") ? 1500 : false),     // clips are processed in the background
  });
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.setupStatus(true), retry: false });
  const mediaEnabled = setup.data?.media_enabled ?? true;
  const v = q.data;
  const [panel, setPanel] = useState<number | null>(null);
  const [comparing, setComparing] = useState(false);
  const vision = useQuery({ queryKey: ["vision"], queryFn: api.vision, retry: false, enabled: q.data?.phase === "practice" || q.data?.phase === "revise" });
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

  // Revising starts from the work you handed in, not from a blank page.
  const lastWork = [...(v?.messages ?? [])].reverse().find((m) => m.kind === "submission")?.content ?? "";
  useEffect(() => { if (v?.phase === "revise" && !text.trim() && lastWork) setText(lastWork); }, [v?.phase, lastWork]);       // eslint-disable-line react-hooks/exhaustive-deps

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
  const waiting = v?.assets.some((a) => a.status === "processing") ?? false;
  const failed = v?.assets.some((a) => a.status === "error") ?? false;
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

          {v.phase === "check" && <CheckPanel v={v} busy={busy} run={run} />}

          {timed && v.task && (
            <form className="card action stack" aria-label="Practice task" onSubmit={(e) => { e.preventDefault(); run("submit", text); }}>
              <div className="eyebrow">{v.phase === "revise" ? "Revise" : "Practice"} · {v.task.minutes} min · Attempt {v.next_attempt}</div>
              <div className="row" style={{ justifyContent: "flex-start", gap: 8 }}>
                {v.task.support && <span className="tag">Support: {v.task.support}</span>}<span className="tag">Speed over polish</span>
              </div>
              {v.task.template.length > 0 && <ol className="small" style={{ margin: 0 }}>{v.task.template.map((b) => <li key={b}>{b}</li>)}</ol>}
              <label htmlFor="work">Your work</label>
              <textarea id="work" className="bigtext" value={text} onChange={(e) => setText(e.target.value)} />
              <Attachments sessionId={v.id} assets={v.assets} mediaEnabled={mediaEnabled} vision={vision.data?.vision ?? null} />
              {waiting && <p id="why-wait" role="status" className="small muted" style={{ margin: 0 }}>A clip is still being processed on this computer. It sends when that finishes.</p>}
              {failed && <p id="why-failed" role="status" className="small error" style={{ margin: 0 }}>A clip could not be processed. Try it again or remove it.</p>}
              <div><button type="submit" className="btn primary" aria-describedby={waiting ? "why-wait" : failed ? "why-failed" : undefined}
                disabled={busy || waiting || failed || !(text.trim() || v.assets.length > 0)}>Submit attempt {v.next_attempt}</button></div>
            </form>
          )}
          {v.phase === "feedback" && !v.ended && v.feedback_pending && (
            <section className="card action stack" aria-label="Feedback pending">
              <p style={{ margin: 0 }}>Attempt {v.attempt} is saved. {v.feedback_error ?? "Feedback is on its way."}</p>
              <div><button type="button" className="btn primary" disabled={busy} onClick={() => run("feedback")}>Get feedback</button></div>
            </section>
          )}
          {v.phase === "feedback" && !v.ended && v.route && (
            <section className="card action stack" aria-label="What next">
              {v.route === "reteach" && <p style={{ margin: 0 }}>A concept needs another look before your next attempt: <strong>{v.route_concepts.join(", ")}</strong>. I will teach it again from a new angle, then check it.</p>}
              {v.route === "revise" && <p style={{ margin: 0 }}>Revise your work using the fixes above. The difficulty stays as it is for now.</p>}
              {v.route === "pass" && <p style={{ margin: 0 }}>Every principle is followed. This skill is yours.</p>}
              <div className="row" style={{ justifyContent: "flex-start" }}>
                {v.route === "pass" && <button type="button" className="btn primary" disabled={busy} onClick={() => run("pass")}>Finish this skill</button>}
                {v.route === "reteach" && <button type="button" className="btn primary" disabled={busy} onClick={() => run("reteach")}>Re-teach {v.route_concepts.join(", ")}</button>}
                {v.route === "revise" && <button type="button" className="btn primary" disabled={busy} onClick={() => run("revise")}>Start attempt {v.next_attempt}</button>}
                {v.attempt >= 2 && <button type="button" className="btn" onClick={() => setComparing(true)}>Compare attempts</button>}
              </div>
            </section>
          )}
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
      {comparing && <CompareDialog id={v.id} latest={v.attempt} onClose={() => setComparing(false)} />}
    </main>
  );
}

function CompareDialog({ id, latest, onClose }: { id: number; latest: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["compare", id, latest], queryFn: () => api.compare(id, latest - 1, latest), retry: false });
  return (
    <div className="scrim">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="cmp-title" style={{ maxWidth: 640 }}>
        <h2 id="cmp-title">Attempt {latest - 1} to attempt {latest}</h2>
        {q.isError && <p role="alert" className="error" style={{ margin: 0 }}>{q.error.message}</p>}
        {q.data && (
          <ul className="list mono small" style={{ gap: 2, maxHeight: 360, overflow: "auto" }}>
            {q.data.lines.map((l, i) => (
              <li key={i} style={{ background: l.op === "+" ? "var(--success-panel)" : l.op === "-" ? "var(--danger-panel)" : undefined, padding: "1px 6px", whiteSpace: "pre-wrap" }}>
                <span aria-hidden="true">{l.op === " " ? "  " : `${l.op} `}</span>
                {l.op !== " " && <span className="sr-only">{l.op === "+" ? "Added: " : "Removed: "}</span>}{l.text}
              </li>
            ))}
          </ul>
        )}
        <div className="row" style={{ justifyContent: "flex-end" }}><button type="button" className="btn primary" autoFocus onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}
