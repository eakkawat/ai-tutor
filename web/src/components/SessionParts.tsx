import { Fragment, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type FbMeta, type Msg, type SessionPhase } from "../api";
import { FeedbackView } from "./FeedbackView";

export const PHASES: { key: SessionPhase; label: string }[] = [
  { key: "diagnose", label: "Diagnose" }, { key: "learn", label: "Learn" }, { key: "check", label: "Check" }, { key: "practice", label: "Practice" },
  { key: "feedback", label: "Feedback" }, { key: "revise", label: "Revise" }, { key: "pass", label: "Pass" },
];

/** Seven steps. Done = a check mark, current = a number and aria-current, upcoming = outline. */
export function PhaseStepper({ phase }: { phase: SessionPhase }) {
  const at = PHASES.findIndex((p) => p.key === phase);
  return (
    <ol className="stepper" aria-label="Phases">
      {PHASES.map((p, i) => (
        <li key={p.key} className={i < at ? "done" : i === at ? "current" : ""} aria-current={i === at ? "step" : undefined}>
          <span className="dot" aria-hidden="true">{i < at ? "✓" : i + 1}</span>
          <span>{p.label}{i < at && <span className="sr-only"> (done)</span>}</span>
        </li>
      ))}
    </ol>
  );
}

const OUTSIDE = "[outside my books]";

/** Text with every verified citation turned into a button that opens the passage, and [outside my books] marked. */
export function RichText({ text, citations, onOpen }: { text: string; citations: Msg["citations"]; onOpen: (chunkId: number) => void }) {
  const cites = new Map(citations.map((c) => [c.citation, c.chunk_id]));
  const re = new RegExp(`(${[...cites.keys(), OUTSIDE].map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
  return (
    <p>
      {text.split(re).map((part, i) => {
        if (part === OUTSIDE) return <span key={i} className="outside">{part}</span>;
        const id = cites.get(part);
        return id !== undefined
          ? <button key={i} type="button" className="cite" onClick={() => onOpen(id)}>{part}</button>
          : <Fragment key={i}>{part}</Fragment>;
      })}
    </p>
  );
}

/** "This felt wrong": saves the message and an optional note to data/feedback.log, without leaving the session (G1). */
export function FeltWrong({ messageId }: { messageId: number }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const send = useMutation({ mutationFn: () => api.feltWrong(messageId, note), onSuccess: () => { setOpen(false); setNote(""); } });
  return (
    <span>
      <button type="button" className="btn small quiet" aria-expanded={open} onClick={() => setOpen(!open)}>This felt wrong</button>
      {send.isSuccess && !open && <span role="status" className="small muted"> Saved.</span>}
      {open && (
        <form className="stack" style={{ marginTop: 8, gap: 8 }} aria-label="Report a message" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
          <label htmlFor={`fw-${messageId}`} className="small">What felt wrong? (optional)</label>
          <textarea id={`fw-${messageId}`} className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          {send.isError && <span role="alert" className="error small">{send.error.message}</span>}
          <span className="row" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="btn small primary" disabled={send.isPending}>Save to feedback log</button>
            <button type="button" className="btn small" onClick={() => setOpen(false)}>Cancel</button>
          </span>
        </form>
      )}
    </span>
  );
}

const LABEL: Record<string, string> = {
  diagnose_task: "Diagnosis", diagnosis: "Diagnosis", learn: "Learn", practice_task: "Practice", qa: "Answer", note: "Note", check_question: "Check", check_result: "Check",
  check_hint: "Hint", check_reteach: "Re-teach", reteach: "Re-teach", check_done: "Check", feedback: "Feedback", feedback_error: "Feedback",
};

export function MessageView({ m, onOpen }: { m: Msg; onOpen: (chunkId: number) => void }) {
  if (m.role === "user") {
    return (
      <article className="card msg user" aria-label={m.kind === "submission" ? `Attempt ${String(m.meta.version)}` : "You"}>
        <div className="eyebrow">{m.kind === "submission" ? `Attempt ${String(m.meta.version)} · ${String(m.meta.minutes)} min` : m.kind === "question" ? "Your question" : "You"}</div>
        <p className={m.kind === "submission" ? "mono" : undefined}>{m.content}</p>
      </article>
    );
  }
  if (m.kind === "feedback") {
    return (
      <article className="card msg" aria-label="Feedback">
        <div className="who"><span className="eyebrow">Feedback · Attempt {String((m.meta as unknown as FbMeta).version)}</span><FeltWrong messageId={m.id} /></div>
        <FeedbackView meta={m.meta as unknown as FbMeta} onOpen={onOpen} />
      </article>
    );
  }
  if (m.kind === "feedback_error") {
    return <article className="card problem msg" role="alert" aria-label="Feedback"><p>{m.content}</p></article>;
  }
  const title = typeof m.meta.title === "string" ? m.meta.title : null;
  const [head, ...rest] = m.kind === "practice_task" ? m.content.split("\n") : [null];
  return (
    <article className="card msg" aria-label={LABEL[m.kind ?? ""] ?? "Tutor"}>
      <div className="who"><span className="eyebrow">{LABEL[m.kind ?? ""] ?? "Tutor"}{m.kind === "qa" && m.meta.steered ? " · back to the task" : ""}</span><FeltWrong messageId={m.id} /></div>
      {title && <h2 style={{ fontSize: 18 }}>{title}</h2>}
      {head ? <><h2 style={{ fontSize: 18 }}>{head}</h2><RichText text={rest.join("\n")} citations={m.citations} onOpen={onOpen} /></> : <RichText text={m.content} citations={m.citations} onOpen={onOpen} />}
    </article>
  );
}

/** The passage behind a citation, beside the conversation. */
export function SourcePanel({ chunkId, onClose }: { chunkId: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["passage", chunkId], queryFn: () => api.passage(chunkId), retry: false });
  return (
    <section className="card stack" aria-label="Source">
      <div className="row"><span className="eyebrow">Source</span><button type="button" className="btn small quiet" onClick={onClose}>Close</button></div>
      {q.isError && <p role="alert" className="error" style={{ margin: 0 }}>{q.error.message}</p>}
      {q.data && (
        <>
          <strong>{q.data.source_title}</strong>
          <div className="mono small muted">{q.data.citation}</div>
          <div className="reader" style={{ padding: 16, fontSize: 14, maxHeight: 240, overflow: "auto" }}><mark>{q.data.text}</mark></div>
          <Link to={`/source/${chunkId}`} className="small">Open full page</Link>
        </>
      )}
    </section>
  );
}

export function mmss(total: number): string {
  const s = Math.abs(Math.trunc(total));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Seconds on the task clock, ticking on the screen from the server's snapshot (the server stays the source of truth). */
export function useTick(elapsed_s: number, running: boolean, key: string): number {
  const [stamp, setStamp] = useState(Date.now());
  const [, force] = useState(0);
  useEffect(() => { setStamp(Date.now()); }, [elapsed_s, running, key]);
  useEffect(() => {
    if (!running) return;
    const h = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(h);
  }, [running]);
  return elapsed_s + (running ? Math.floor((Date.now() - stamp) / 1000) : 0);
}
