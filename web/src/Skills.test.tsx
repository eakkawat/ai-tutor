import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Skill, Source } from "./api";
import Library from "./pages/Library";
import SkillMapPage from "./pages/SkillMap";
import SkillReview from "./pages/SkillReview";

const skill = (o: Partial<Skill> = {}): Skill => ({
  id: 1, domain: "screenwriting", name: "Write a want and obstacle scene", description: "You can write a scene driven by a want.", practice_type: "scene",
  status: "active", merge_into: null, merge_note: null, learning_status: "not_started", hours: 0,
  principles: [
    { id: 11, principle: "The want is clear in the first beat", test: "Can you name the want after beat one?", chunk_id: 5, citation: "[Book A, ch. 3, p. 41]" },
    { id: 12, principle: "The obstacle pushes back", test: "Does it answer each attempt?", chunk_id: 6, citation: "[Book A, ch. 3, p. 43]" },
  ],
  sources: [{ source_id: 1, title: "[Book A]", pages: [41, 43] }],
  concepts: [{ id: 1, name: "subtext", required_level: "spot", is_foundation: true }],
  prerequisites: [{ id: 9, name: "Write a logline" }], ...o,
});

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

describe("Skill map", () => {
  const map = (skills: Skill[], pending = 0) => ({ domains: [{ domain: "screenwriting", skills }], pending });

  it("groups skills by domain and shows the checklist with citations when opened", async () => {
    mock(() => map([skill(), skill({ id: 2, name: "Write subtext", learning_status: "passed", hours: 12.5 })]));
    wrap(<SkillMapPage />);
    expect(await screen.findByRole("heading", { name: "screenwriting" })).toBeInTheDocument();
    expect(screen.getByText("2 skills · 1 domain")).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("12.5 h")).toBeInTheDocument();
    const card = within(screen.getAllByRole("listitem")[0]);
    await userEvent.click(card.getByRole("button", { name: "Show details" }));
    expect(card.getByRole("link", { name: "[Book A, ch. 3, p. 41]" })).toHaveAttribute("href", "/source/5");
    expect(card.getByText(/Test: Can you name the want/)).toBeInTheDocument();
    expect(card.getByText(/foundation/)).toBeInTheDocument();
    expect(card.getByText("Needs first:")).toBeInTheDocument();
    expect(card.getByText(/Write a logline/)).toBeInTheDocument();
  });

  it("points to proposed skills waiting for review", async () => {
    mock(() => map([skill()], 3));
    wrap(<SkillMapPage />);
    expect(await screen.findByText(/3 proposed skills are waiting/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review skills" })).toHaveAttribute("href", "/skills/review");
  });

  it("has a plain empty state that leads to the Library", async () => {
    mock(() => ({ domains: [], pending: 0 }));
    wrap(<SkillMapPage />);
    expect(await screen.findByRole("heading", { name: "No skills yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Library" })).toHaveAttribute("href", "/library");
  });

  it("splits a skill by the chosen principles", async () => {
    const f = mock((u) => (u === "/api/skills" ? map([skill()]) : { new_skill: skill({ id: 3 }), skill: skill() }));
    wrap(<SkillMapPage />);
    const card = within(await screen.findByRole("listitem"));
    await userEvent.click(card.getByRole("button", { name: "Show details" }));
    await userEvent.click(card.getByRole("button", { name: "Split" }));
    await userEvent.click(card.getByLabelText("The obstacle pushes back"));
    await userEvent.type(card.getByLabelText("Name of the new skill"), "Make the obstacle push back");
    await userEvent.click(card.getByRole("button", { name: "Split into two skills" }));
    const call = f.mock.calls.find((c) => c[0] === "/api/skills/1/split")!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ name: "Make the obstacle push back", principle_ids: [12] });
  });

  it("edits principles and sends the whole checklist", async () => {
    const f = mock((u) => (u === "/api/skills" ? map([skill()]) : skill()));
    wrap(<SkillMapPage />);
    const card = within(await screen.findByRole("listitem"));
    await userEvent.click(card.getByRole("button", { name: "Show details" }));
    await userEvent.click(card.getByRole("button", { name: "Edit" }));
    await userEvent.clear(card.getByLabelText("Principle 1"));
    await userEvent.type(card.getByLabelText("Principle 1"), "The want is clear at once");
    await userEvent.click(card.getByRole("button", { name: "Remove principle 2" }));
    await userEvent.click(card.getByRole("button", { name: "Save changes" }));
    const put = f.mock.calls.find((c) => c[0] === "/api/skills/1/principles")!;
    expect(JSON.parse(put[1]!.body as string)).toEqual([{ principle: "The want is clear at once", test: "Can you name the want after beat one?", chunk_id: 5 }]);
  });

  it("tells you a practised skill was archived, not lost", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mock((_u, init) => (init?.method === "DELETE" ? { outcome: "archived" } : map([skill()])));
    wrap(<SkillMapPage />);
    const card = within(await screen.findByRole("listitem"));
    await userEvent.click(card.getByRole("button", { name: "Show details" }));
    await userEvent.click(card.getByRole("button", { name: "Delete" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("archived instead"));
  });
});

describe("Skill review", () => {
  it("asks about one proposed skill at a time: keep, edit, delete", async () => {
    const f = mock((u, init) => (u === "/api/skills/pending" ? { skills: [skill({ status: "pending" }), skill({ id: 2, name: "Second", status: "pending" })] } : init ? { skill: 1 } : {}));
    wrap(<SkillReview />);
    expect(await screen.findByRole("heading", { name: "Write a want and obstacle scene" })).toBeInTheDocument();
    expect(screen.getByText(/New skill · 2 waiting/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "[Book A, ch. 3, p. 41]" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Second" })).not.toBeInTheDocument();       // one at a time
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(f).toHaveBeenCalledWith("/api/skills/1/accept", expect.objectContaining({ method: "POST" }));
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("shows a merge as a diff with accept, separate, or discard", async () => {
    const merge = skill({
      status: "pending", merge_into: 7, merge_note: "Both teach scene want.",
      merge: { target: { id: 7, name: "Write a want scene", principles: 3 }, adds: ["The obstacle pushes back"], text: "adds 1 principle to Write a want scene" },
    });
    const f = mock((u) => (u === "/api/skills/pending" ? { skills: [merge] } : {}));
    wrap(<SkillReview />);
    expect(await screen.findByText(/adds 1 principle to Write a want scene/)).toBeInTheDocument();
    expect(screen.getByText(/Both teach scene want/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add as a separate skill" }));
    expect(f).toHaveBeenCalledWith("/api/skills/1/accept-as-new", expect.objectContaining({ method: "POST" }));
    expect(screen.getByRole("button", { name: "Accept merge" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard" })).toBeInTheDocument();
  });

  it("says when there is nothing left to review", async () => {
    mock(() => ({ skills: [] }));
    wrap(<SkillReview />);
    expect(await screen.findByRole("heading", { name: "Nothing to review" })).toBeInTheDocument();
  });
});

describe("Library and skills", () => {
  const src = (o: Partial<Source>): Source => ({
    id: 1, title: "[Book B]", author: null, kind: "single", pages: 268, status: "ready", stage: null, progress: 1, message: null, estimate_s: 60,
    triage: { book_type: "practical", practicable: true, likely_skills: [], reason: "r" }, chunks: 80, files: 1, pages_without_text: [], skills: 0, pending_skills: 8, ...o,
  });

  it("announces skills waiting from a book and offers another look", async () => {
    const f = mock((u) => (u === "/api/library" ? { sources: [src({})] } : u === "/api/settings/skill-mode" ? { mode: "manual" } : { ok: true }));
    wrap(<Library />);
    expect(await screen.findByText(/8 new skills from this book are waiting/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review skills" })).toHaveAttribute("href", "/skills/review");
    await userEvent.click(screen.getByRole("button", { name: "Look for skills again" }));
    expect(f).toHaveBeenCalledWith("/api/library/1/find-skills", expect.objectContaining({ method: "POST" }));
  });

  it("switches between Add automatically and Ask me first", async () => {
    const f = mock((u) => (u === "/api/library" ? { sources: [] } : { mode: "manual" }));
    wrap(<Library />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Ask me first" })).toHaveAttribute("aria-pressed", "true"));
    await userEvent.click(screen.getByRole("button", { name: "Add automatically" }));
    const put = f.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PUT")!;
    expect(JSON.parse(put[1]!.body as string)).toEqual({ mode: "auto" });
  });
});
