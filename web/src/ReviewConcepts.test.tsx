import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConceptDetail, ConceptRow, ReviewQuestion, ReviewRun } from "./api";
import Concepts from "./pages/Concepts";
import Review from "./pages/Review";

type Handler = (url: string, init?: RequestInit) => unknown;
function mock(handler: Handler) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const r = handler(url, init);
    return r instanceof Response ? r : new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
const wrap = (ui: React.ReactNode, at = "/") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}>
      <Routes><Route path="/session/:id" element={<p>Session screen</p>} /><Route path="/concepts" element={<p>Concepts screen</p>} /><Route path="*" element={ui} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);
afterEach(() => vi.unstubAllGlobals());

const question = (o: Partial<ReviewQuestion> = {}): ReviewQuestion => ({
  n: 1, context: "Write a logline in one sentence · passed 9 days ago", level: "use", kind: "skill", prompt: "What must a logline include?", options: [], attempts: 0, hint: null,
  feedback: "", correct: false, finished: false, first: null, answer: null, citations: [], ...o,
});
const run = (o: Partial<ReviewRun> = {}): ReviewRun => ({ id: 5, mode: "review", session_id: null, concept_id: null, total: 3, answered: 0, ended: false, current: question(), summary: null, ...o });
const body = (init?: RequestInit) => JSON.parse(String(init?.body ?? "{}"));

describe("Review", () => {
  it("shows one question at a time with its place in the sitting", async () => {
    mock(() => ({ run: run({ current: question({ n: 2 }) }) }));
    wrap(<Review />, "/review?mode=review");
    const card = await screen.findByRole("region", { name: "Question 2 of 3" });
    expect(within(card).getByText("What must a logline include?")).toBeInTheDocument();
    expect(within(card).getByText(/passed 9 days ago/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End review" })).toBeInTheDocument();
  });

  it("checks an answer, gives a hint on a miss, then lets the learner show the answer with its citation", async () => {
    const user = userEvent.setup();
    let state = run();
    mock((url, init) => {
      if (url === "/api/review/start") return { run: state };
      if (url === "/api/review/5/answer") {
        expect(body(init).text).toBe("the hero and the goal");
        state = run({ current: question({ attempts: 1, hint: "Think about what makes the goal hard.", feedback: "You left out the obstacle." }) });
      } else if (url === "/api/review/5/show") {
        state = run({ current: question({ attempts: 1, finished: true, first: "wrong", feedback: "You left out the obstacle.", answer: "The hero, the goal and the obstacle.",
          citations: [{ citation: "[Book A, ch. 3, p. 41]", chunk_id: 1 }] }) });
      }
      return state;
    });
    wrap(<Review />, "/review?mode=review");
    await user.type(await screen.findByLabelText("Your answer"), "the hero and the goal");
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    expect(await screen.findByText(/Think about what makes the goal hard/)).toBeInTheDocument();
    expect(screen.getByText(/Not quite\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show answer" }));
    expect(await screen.findByText(/The hero, the goal and the obstacle/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "[Book A, ch. 3, p. 41]" })).toHaveAttribute("href", "/source/1");
    expect(screen.getByRole("button", { name: "Next question" })).toBeInTheDocument();
  });

  it("uses choices when the question lists options", async () => {
    const user = userEvent.setup();
    const f = mock((url) => (url === "/api/review/start" ? { run: run({ current: question({ kind: "concept", level: "spot", prompt: "Which line shows a want?\nA. x\nB. y", options: ["A. x", "B. y"] }) }) } : run()));
    wrap(<Review />, "/review?mode=review");
    expect(await screen.findByRole("button", { name: "Check answer" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "B. y" }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await waitFor(() => expect(f.mock.calls.some(([u, i]) => u === "/api/review/5/answer" && body(i as RequestInit).text === "B. y")).toBe(true));
  });

  it("says when nothing is due", async () => {
    mock(() => ({ run: null }));
    wrap(<Review />, "/review?mode=review");
    expect(await screen.findByText(/Nothing is due/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Home" })).toBeInTheDocument();
  });

  it("goes straight to the session when Continue has nothing to review", async () => {
    mock(() => ({ run: null }));
    wrap(<Review />, "/review?mode=continue&session=7");
    expect(await screen.findByText("Session screen")).toBeInTheDocument();
  });

  it("ends with a summary, and Continue returns to the saved session", async () => {
    const user = userEvent.setup();
    const ended = run({ mode: "continue", session_id: 7, ended: true, current: null, summary: {
      right: 1, wrong: 1, skipped: 0, level: null, notes: ["Cut on action is back on your skill map as needs practice. You missed it twice in a row."],
      rows: [{ context: "Concept · want", result: "right", when: "back in 3 days", dropped_to: null }, { context: "Cut on action · passed yesterday", result: "wrong", when: "back tomorrow", dropped_to: null }] } });
    mock(() => ({ run: ended }));
    wrap(<Review />, "/review?mode=continue&session=7");
    expect(await screen.findByText("1 right, 1 to come back sooner.")).toBeInTheDocument();
    expect(screen.getByText(/Missed · back tomorrow/)).toBeInTheDocument();
    expect(screen.getByText(/needs practice/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to your skill" }));
    expect(await screen.findByText("Session screen")).toBeInTheDocument();
  });

  it("shows the level reached after a concept check", async () => {
    mock(() => ({ run: run({ mode: "concept", concept_id: 3, ended: true, current: null, summary: { right: 2, wrong: 1, skipped: 0, level: "spot", notes: [], rows: [] } }) }));
    wrap(<Review />, "/review?mode=concept&concept=3");
    expect(await screen.findByText(/This concept is now at Spot/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Concepts" })).toBeInTheDocument();
  });

  it("shows the server's message when the model fails and keeps the answer box", async () => {
    const user = userEvent.setup();
    mock((url) => (url === "/api/review/start" ? { run: run() }
      : new Response(JSON.stringify({ detail: { message: "The language model could not be reached. Nothing was changed; try again." } }), { status: 503 })));
    wrap(<Review />, "/review?mode=review");
    await user.type(await screen.findByLabelText("Your answer"), "x");
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    expect(screen.getByLabelText("Your answer")).toHaveValue("x");
  });
});

const row = (o: Partial<ConceptRow> & { id: number; name: string }): ConceptRow => ({ is_foundation: false, level: "none", skills: 1, confused_with: null, confusion_count: 0, ...o });
const detail = (o: Partial<ConceptDetail> & { id: number; name: string }): ConceptDetail => ({
  definition: "What a character means but does not say.", example: "Made-up example: two people talk about the weather.", is_foundation: false, level: "define", last_checked_at: "2026-10-29 09:00:00",
  confusions: [{ with: "exposition", count: 2 }], sources: [{ chunk_id: 4, citation: "[Book B, ch. 5, p. 151]" }],
  skills: [{ id: 1, name: "Write subtext into a two-person exchange", required_level: "use" }, { id: 2, name: "Show emotion through action", required_level: "spot" }],
  questions: { define: 1, spot: 0, use: 0 }, ...o,
});

describe("Concepts", () => {
  const list = [row({ id: 1, name: "Shot size", is_foundation: true, level: "use", skills: 9 }), row({ id: 2, name: "Subtext", level: "define", skills: 4, confused_with: "exposition", confusion_count: 2 }),
    row({ id: 3, name: "Cut on action", level: "none", skills: 2 })];
  const api = (url: string) => {
    if (url === "/api/concepts") return { concepts: list };
    const id = Number(url.split("/").pop());
    return detail({ id, name: list.find((c) => c.id === id)!.name });
  };

  it("lists concepts with the level as words and what each is confused with", async () => {
    mock(api);
    wrap(<Concepts />);
    expect(await screen.findByText(/3 fundamentals from your books/)).toBeInTheDocument();
    expect(screen.getByText("Use 1 · Spot 0 · Define only 1 · Not yet 1")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Define only")).toBeInTheDocument();
    expect(within(table).getByText("Not yet")).toBeInTheDocument();
    expect(within(table).getByText(/Confused with exposition 2×/)).toBeInTheDocument();
    expect(within(table).getByText("9 skills")).toBeInTheDocument();
  });

  it("shows a concept's definition, example, sources, skills and what it is confused with", async () => {
    const user = userEvent.setup();
    mock(api);
    wrap(<Concepts />);
    await user.click(await screen.findByRole("button", { name: /Subtext/ }));
    const d = within(await screen.findByRole("region", { name: "Concept: Subtext" }));
    expect(await d.findByText("What a character means but does not say.")).toBeInTheDocument();
    expect(d.getByText(/Made-up example/)).toBeInTheDocument();
    expect(d.getByRole("link", { name: "[Book B, ch. 5, p. 151]" })).toHaveAttribute("href", "/source/4");
    expect(d.getByText(/mix this up with exposition \(2×\)/)).toBeInTheDocument();
    expect(d.getByText("Write subtext into a two-person exchange")).toBeInTheDocument();
    expect(d.getByText("needs Use")).toBeInTheDocument();
    expect(d.getByText("needs Spot")).toBeInTheDocument();
    expect(d.getByText("1 · Define").closest("li")).toHaveTextContent("Done");
    expect(d.getByText("2 · Spot").closest("li")).toHaveTextContent("Not yet");
    expect(d.getByRole("link", { name: "Check this concept · 3 min" })).toHaveAttribute("href", "/review?mode=concept&concept=2");
  });

  it("filters to foundations and to shaky concepts, and searches by name", async () => {
    const user = userEvent.setup();
    mock(api);
    wrap(<Concepts />);
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Foundations first" }));
    expect(within(screen.getByRole("table")).queryByText(/Subtext/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Shaky/ }));
    expect(within(screen.getByRole("table")).getByRole("button", { name: /Subtext/ })).toBeInTheDocument();
    expect(within(screen.getByRole("table")).queryByRole("button", { name: /Shot size/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /All/ }));
    await user.type(screen.getByLabelText("Search concepts"), "cut");
    const rows = within(screen.getByRole("table")).getAllByRole("button");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("Cut on action");
  });

  it("explains an empty list", async () => {
    mock(() => ({ concepts: [] }));
    wrap(<Concepts />);
    expect(await screen.findByText(/No concepts yet/)).toBeInTheDocument();
  });
});
