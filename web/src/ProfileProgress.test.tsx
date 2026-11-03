import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProfileNote, ProfileSection, ProgressData } from "./api";
import Profile from "./pages/Profile";
import Progress from "./pages/Progress";

type Handler = (url: string, init?: RequestInit) => unknown;
function mock(handler: Handler) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const r = handler(url, init);
    return r instanceof Response ? r : new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>,
);
afterEach(() => vi.unstubAllGlobals());

const note = (o: Partial<ProfileNote> & { id: number }): ProfileNote => ({ text: "x", section: "understand", topic: null, evidence: "Learned from 4 recall checks", source: "auto", edited: false, updated_at: "", ...o });
const sections = (u: ProfileNote[], f: ProfileNote[]): ProfileSection[] => [
  { key: "understand", title: "What helps me understand", notes: u }, { key: "flow", title: "Keeping me in the flow zone", notes: f },
];

describe("How I learn", () => {
  it("shows each note under its heading with where it was learned from", async () => {
    mock(() => ({ sections: sections(
      [note({ id: 1, text: "A film scene example works better than a rule on its own." }), note({ id: 2, text: "Short explanations; I'd rather try and get corrected.", source: "user", evidence: "You added this" })],
      [note({ id: 3, section: "flow", text: "A beat template helps on first attempts at a new skill.", evidence: "Learned from 2 flow ratings · lever: beat template" })]) }));
    wrap(<Profile />);
    const understand = within(await screen.findByRole("region", { name: "What helps me understand" }));
    expect(understand.getByText("Learned from 4 recall checks")).toBeInTheDocument();
    expect(understand.getByText("You added this")).toBeInTheDocument();
    const flow = within(screen.getByRole("region", { name: "Keeping me in the flow zone" }));
    expect(flow.getByText(/Learned from 2 flow ratings/)).toBeInTheDocument();
    expect(screen.getByText(/never lower the bar for passing a skill/)).toBeInTheDocument();
  });

  it("says plainly when nothing has been learned yet and still lets you add a note", async () => {
    const f = mock((_u, init) => (init?.method === "POST" ? note({ id: 9, source: "user" }) : { sections: sections([], []) }));
    wrap(<Profile />);
    expect(await screen.findByText(/Nothing learned yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Something the tutor should know about how you learn"), "Recall questions bore me unless they're timed.");
    await userEvent.click(screen.getByRole("button", { name: "Keeping me in the flow zone" }));
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    const post = f.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({ text: "Recall questions bore me unless they're timed.", section: "flow" });
  });

  it("edits a note in place and sends the new wording", async () => {
    const f = mock((_u, init) => (init?.method === "PATCH" ? note({ id: 1 }) : { sections: sections([note({ id: 1, text: "Old wording." })], []) }));
    wrap(<Profile />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Edit note");
    await userEvent.clear(box);
    await userEvent.type(box, "New wording.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const patch = f.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PATCH")!;
    expect(patch[0]).toBe("/api/profile/notes/1");
    expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({ text: "New wording." });
  });

  it("shows an edited note as the learner's own and removes a note on request", async () => {
    const f = mock((_u, init) => (init?.method === "DELETE" ? { ok: true } : { sections: sections([note({ id: 1, text: "Mine now.", edited: true })], []) }));
    wrap(<Profile />);
    expect(await screen.findByText("You edited this")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove note: Mine now." }));
    await waitFor(() => expect(f.mock.calls.some((c) => c[0] === "/api/profile/notes/1" && (c[1] as RequestInit).method === "DELETE")).toBe(true));
  });

  it("shows the server's reason when a note is refused", async () => {
    mock((_u, init) => (init?.method === "POST" ? new Response(JSON.stringify({ detail: { message: "Keep a note under 300 characters." } }), { status: 400 }) : { sections: sections([], []) }));
    wrap(<Profile />);
    await userEvent.type(await screen.findByLabelText(/Something the tutor should know/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("under 300 characters");
  });
});

describe("Progress", () => {
  const data = (o: Partial<ProgressData> = {}): ProgressData => ({
    totals: { practice_hours: 6.3, skills_passed: 1, just_right: [7, 11], reviews_right: [8, 10] }, target: 20,
    skills: [
      { id: 1, name: "Write a logline in one sentence", status: "passed", status_text: "passed", hours: 3.4, target: 20, bar: 0.17, over: 0, success_rate: 1 },
      { id: 2, name: "Want vs. obstacle in a scene", status: "active", status_text: "active", hours: 2.9, target: 20, bar: 0.145, over: 0, success_rate: 0.5 }],
    mistakes: [
      { tag: "Endings don't change the want", kind: "execution", count: 3, last_seen: new Date().toISOString().slice(0, 10) + " 10:00:00", skill: "s", fixed: false },
      { tag: "Want stated too late", kind: "concept", count: 2, last_seen: "2026-10-30 09:00:00", skill: "s", fixed: true }],
    flow_history: [
      { id: 2, task: "Attempt 2", skill: "Want vs. obstacle", felt: "Too hard", inferred: false, changed: "Kept level (productive struggle)", at: "" },
      { id: 1, task: "Attempt 1", skill: "Want vs. obstacle", felt: "Just right", inferred: true, changed: "No change", at: "" }], ...o,
  });

  it("shows the totals and the hours per skill toward 20, with status in words", async () => {
    mock(() => data());
    wrap(<Progress />);
    const totals = within(await screen.findByRole("group", { name: "Totals" }));
    expect(totals.getByText("6.3 h")).toBeInTheDocument();
    expect(totals.getByText("7 of 11")).toBeInTheDocument();
    expect(totals.getByText("8 of 10")).toBeInTheDocument();
    expect(screen.getByText("20 hours is the target, not a requirement. You pass when your work follows the principles.")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Want vs. obstacle in a scene: 2.9 of 20 hours" });
    expect(bar).toHaveAttribute("aria-valuenow", "14.5");
    expect(screen.getByText("· passed")).toBeInTheDocument();
    expect(screen.getByText("· active")).toBeInTheDocument();
    expect(screen.getByText("3.4 h")).toBeInTheDocument();
  });

  it("does not break the bar past 20 hours and says how far past", async () => {
    mock(() => data({ skills: [{ id: 1, name: "Big skill", status: "active", status_text: "active", hours: 21.4, target: 20, bar: 1, over: 1.4, success_rate: null }] }));
    wrap(<Progress />);
    expect(await screen.findByText("21.4 h · 1.4 past the target")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /Big skill/ })).toHaveAttribute("aria-valuenow", "100");
  });

  it("lists recurring mistakes with their count, when last seen, and whether they are fixed", async () => {
    mock(() => data());
    wrap(<Progress />);
    const rows = within(await screen.findByRole("region", { name: "Recurring mistakes" })).getAllByRole("row");
    expect(within(rows[1]).getByText("Endings don't change the want")).toBeInTheDocument();
    expect(within(rows[1]).getByText("3")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Today")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Still happening")).toBeInTheDocument();
    expect(within(rows[2]).getByText("2026-10-30")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Fixed")).toBeInTheDocument();
  });

  it("shows the flow history with what felt how and what changed", async () => {
    mock(() => data());
    wrap(<Progress />);
    const rows = within(await screen.findByRole("region", { name: "Flow history" })).getAllByRole("row");
    expect(within(rows[1]).getByText("Too hard")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Kept level (productive struggle)")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/judged from your work/)).toBeInTheDocument();
  });

  it("has plain empty states", async () => {
    mock(() => data({ totals: { practice_hours: 0, skills_passed: 0, just_right: [0, 0], reviews_right: [0, 0] }, skills: [], mistakes: [], flow_history: [] }));
    wrap(<Progress />);
    expect(await screen.findByText(/No practice yet/)).toBeInTheDocument();
    expect(screen.getByText("No mistakes recorded yet.")).toBeInTheDocument();
    expect(screen.getByText(/No ratings yet/)).toBeInTheDocument();
    expect(screen.getAllByText("0 of 0")).toHaveLength(2);
  });
});
