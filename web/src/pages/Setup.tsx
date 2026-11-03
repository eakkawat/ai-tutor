import { useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError, type Check } from "../api";
import { StatusPill } from "../components/StatusPill";

function CopyFix({ fix }: { fix: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="inset">
      <code>{fix}</code>
      <button type="button" className="btn small" onClick={() => navigator.clipboard?.writeText(fix).then(() => setCopied(true))}>
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function LlmForm({ check }: { check: Check }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ base_url: "", model: "", api_key: "" });
  const save = useMutation({ mutationFn: api.saveLlm, onSuccess: (s) => { qc.setQueryData(["setup"], s); setF((v) => ({ ...v, api_key: "" })); } });
  const bad = (field: string) => save.isError && save.error instanceof ApiError && save.error.field === field;
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      {check.fix && <p role="status" className="small muted" style={{ margin: 0 }}>{check.fix}</p>}
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(f); }}>
        <div className="field">
          <label htmlFor="base_url">Server URL</label>
          <input id="base_url" className="input" type="url" placeholder="http://127.0.0.1:8080/v1" value={f.base_url} onChange={set("base_url")}
            aria-invalid={bad("base_url")} />
        </div>
        <div className="field">
          <label htmlFor="model">Model name</label>
          <input id="model" className="input" placeholder="the model your server serves" value={f.model} onChange={set("model")} aria-invalid={bad("model")} />
        </div>
        <div className="field">
          <label htmlFor="api_key">API key <span className="muted">(optional for local servers)</span></label>
          <input id="api_key" className="input" type="password" autoComplete="off" value={f.api_key} onChange={set("api_key")} aria-invalid={bad("api_key")} />
        </div>
        <button type="submit" className="btn primary" style={{ alignSelf: "flex-start" }} disabled={save.isPending}>
          {save.isPending ? "Checking server…" : "Save and check"}
        </button>
      </form>
      {save.isError && <p role="alert" className="error" style={{ margin: 0 }}>{save.error.message}</p>}
      <p className="small muted" style={{ margin: 0 }}>Any OpenAI-compatible server. Stored only on this computer. Used for teaching, quizzes and feedback.</p>
    </>
  );
}

function ToolRow({ check }: { check: Check }) {
  return (
    <li className="card stack" style={{ gap: 10 }}>
      <div className="row">
        <div><div style={{ fontWeight: 600 }}>{check.label}</div><div className="small muted">{check.purpose}</div></div>
        <StatusPill check={check} />
      </div>
      {check.status !== "ready" && check.fix && <CopyFix fix={check.fix} />}
      {check.status !== "ready" && check.detail && <p className="small muted" style={{ margin: 0 }}>{check.detail}</p>}
    </li>
  );
}

export default function Setup() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["setup"], queryFn: () => api.setupStatus(true), retry: false });
  const recheck = useMutation({ mutationFn: () => api.setupStatus(true), onSuccess: (s) => qc.setQueryData(["setup"], s) });
  const s = q.data;
  if (!s) return <main className="page narrow" role="status">{q.isError ? "Could not reach the app on this computer." : "Checking…"}</main>;

  const llm = s.checks.find((c) => c.id === "llm")!;
  const tools = s.checks.filter((c) => c.id !== "llm");
  return (
    <main className="page narrow">
      <div>
        <h1>Before you start</h1>
        <p className="lead">The tutor runs on this computer. It needs a language model server (any OpenAI-compatible one), and local tools for video feedback.</p>
      </div>
      <ul className="list">
        <li className={`card stack ${llm.status === "ready" ? "" : "problem"}`}>
          <div className="row"><span style={{ fontWeight: 600 }}>{llm.label}</span><StatusPill check={llm} /></div>
          {llm.status === "ready" ? <p className="small muted" style={{ margin: 0 }}>Connected.</p> : <LlmForm check={llm} />}
        </li>
        {tools.map((c) => <ToolRow key={c.id} check={c} />)}
      </ul>
      {s.media_note && <p role="status" className="small muted" style={{ margin: 0 }}>{s.media_note}</p>}
      <div className="row">
        <button type="button" className="btn" onClick={() => recheck.mutate()} disabled={recheck.isPending}>
          {recheck.isPending ? "Checking…" : "Check again"}
        </button>
        {s.can_continue
          ? <Link to="/" className="btn primary">Continue</Link>
          : <button type="button" className="btn" disabled aria-describedby="why">Continue</button>}
      </div>
      {!s.can_continue && <p id="why" className="small muted" style={{ margin: "-8px 0 0", textAlign: "right" }}>Set up the language model to continue.</p>}
    </main>
  );
}
