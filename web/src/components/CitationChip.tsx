import { Link } from "react-router-dom";

/** A citation is always a link to the exact passage (DESIGN_SYSTEM: "Show the source"). */
export function CitationChip({ chunkId, citation }: { chunkId: number; citation: string }) {
  return <Link className="cite" to={`/source/${chunkId}`}>{citation}</Link>;
}
