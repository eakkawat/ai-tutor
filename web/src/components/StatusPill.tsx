import type { Check } from "../api";

/** Status is always words; color only reinforces it (DESIGN_SYSTEM §1.3). */
export function checkPill(c: Check): { text: string; tone: "success" | "warning" | "danger" } {
  if (c.status === "ready") return { text: "Ready", tone: "success" };
  if (c.status === "unreachable") return { text: "Not verified · offline", tone: "warning" };
  const word = c.status === "invalid" ? "Rejected" : "Missing";
  return c.required ? { text: `${word} · required`, tone: "danger" } : { text: `Not found · optional`, tone: "warning" };
}

export function StatusPill({ check }: { check: Check }) {
  const p = checkPill(check);
  return <span className={`pill ${p.tone}`}>{p.text}</span>;
}
