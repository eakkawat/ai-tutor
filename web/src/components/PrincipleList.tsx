import type { Principle } from "../api";
import { CitationChip } from "./CitationChip";

/** The skill's checklist: every principle names its test and links to the passage it comes from. */
export function PrincipleList({ principles }: { principles: Principle[] }) {
  return (
    <ol className="list" style={{ gap: 10, paddingLeft: 0 }}>
      {principles.map((p, i) => (
        <li key={p.id} className="stack" style={{ gap: 4 }}>
          <div><span className="mono small muted">{i + 1}. </span><strong>{p.principle}</strong> {p.citation && <CitationChip chunkId={p.chunk_id} citation={p.citation} />}</div>
          <div className="small muted">Test: {p.test}</div>
        </li>
      ))}
    </ol>
  );
}
