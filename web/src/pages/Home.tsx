import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Check } from "../api";
import { checkPill } from "../components/StatusPill";

function SetupCheck({ checks, note }: { checks: Check[]; note: string | null }) {
  return (
    <section aria-labelledby="setup" className="card">
      <h2 id="setup" style={{ fontSize: 15, marginBottom: 12 }}>Setup check</h2>
      <ul className="list" style={{ gap: 10, fontSize: 14 }}>
        {checks.filter((c) => c.id !== "ffprobe").map((c) => {
          const p = checkPill(c);
          const bad = c.status !== "ready";
          return (
            <li key={c.id} className={`row ${bad && !c.required ? "warn-row" : ""}`}>
              <span>{c.label}</span>
              <span style={{ fontWeight: 500, color: `var(--${p.tone})` }}>
                {p.text}{bad && c.fix && <> · <Link to="/setup" style={{ color: "inherit" }}>How to fix</Link></>}
              </span>
            </li>
          );
        })}
      </ul>
      {note && <p className="small muted" style={{ margin: "12px 0 0" }}>{note}</p>}
      <p className="small muted" style={{ margin: "12px 0 0" }}>Everything stays on this computer except prompts sent to your language model server.</p>
    </section>
  );
}

export default function Home() {
  const home = useQuery({ queryKey: ["home"], queryFn: api.home });
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.setupStatus(true), retry: false });
  if (!home.data) return <main className="page medium" role="status">Loading…</main>;
  const h = home.data;

  if (h.state === "empty_library") {
    return (
      <main className="page medium" style={{ paddingTop: 56 }}>
        <div>
          <h1 style={{ fontSize: 32, lineHeight: 1.2 }}>Add your first book</h1>
          <p className="lead" style={{ fontSize: 16 }}>Your tutor teaches only from the books and courses you add. Start with one book on the skill you want to learn.</p>
        </div>
        <section aria-label="Add a book" className="card hero stack" style={{ gap: 16 }}>
          <div className="dropzone">
            <span style={{ fontSize: 16 }}>A whole book, or chapter PDFs from your chapter splitter</span>
            <Link to="/library" className="btn primary">Add a book</Link>
          </div>
          <div>
            <h2 style={{ fontSize: 14, marginBottom: 10 }}>What happens next</h2>
            <ol className="steps">
              <li><div className="n">1</div>The book is read on this computer and split into chapters and pages.</li>
              <li><div className="n">2</div>It's broken into small skills you can practice, each with its principles.</li>
              <li><div className="n">3</div>You name a project, pick one skill, and start practicing.</li>
            </ol>
          </div>
        </section>
        {setup.data && <SetupCheck checks={setup.data.checks} note={setup.data.media_note} />}
      </main>
    );
  }

  return (
    <main className="page medium">
      {h.state === "no_active_skill" && (
        <section className="card action stack">
          <h1>Pick your next skill</h1>
          <p className="lead">Tell the tutor what you want to make. It will suggest a short list.</p>
          <Link to="/new" className="btn primary" style={{ alignSelf: "flex-start" }}>New skill</Link>
        </section>
      )}
      {(h.state === "active_skill" || h.state === "reviews_due") && h.active_skill && (
        <section className="card action stack">
          <h1>{h.active_skill.name}</h1>
          {h.state === "reviews_due" && <p className="lead">{h.reviews_due} {h.reviews_due === 1 ? "question" : "questions"} to review first.</p>}
          <Link to={h.active_skill.session_id ? `/session/${h.active_skill.session_id}` : "/new"} className="btn primary" style={{ alignSelf: "flex-start" }}>Continue</Link>
        </section>
      )}
      {setup.data && <SetupCheck checks={setup.data.checks} note={setup.data.media_note} />}
    </main>
  );
}
