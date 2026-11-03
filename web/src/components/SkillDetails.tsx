import type { Skill } from "../api";
import { PrincipleList } from "./PrincipleList";

/** Everything B3 asks a skill to show: name, one line, 2–6 principles with citations, prerequisites, practice type (+ concepts and sources). */
export function SkillDetails({ skill }: { skill: Skill }) {
  return (
    <div className="stack">
      <p style={{ margin: 0 }}>{skill.description}</p>
      <div className="small muted">
        Practice: <span className="mono">{skill.practice_type || "not set"}</span>
        {skill.sources.length > 0 && <> · From {skill.sources.map((s) => `${s.title} (pp. ${s.pages[0]}–${s.pages[1]})`).join("; ")}</>}
      </div>
      <PrincipleList principles={skill.principles} />
      {skill.concepts.length > 0 && (
        <div className="small"><strong>Concepts: </strong>
          {skill.concepts.map((c) => <span key={c.id} className="tag">{c.name}{c.is_foundation ? " · foundation" : ""}</span>)}
        </div>
      )}
      {skill.prerequisites.length > 0 && <div className="small"><strong>Needs first: </strong>{skill.prerequisites.map((p) => p.name).join(", ")}</div>}
    </div>
  );
}
