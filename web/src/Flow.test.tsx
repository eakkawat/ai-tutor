import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FlowRating, FlowView, Msg, PracticeTask, SessionView } from "./api";
import Session from "./pages/Session";

const principles = [{ id: 1, principle: "The want is clear", test: "t1", chunk_id: 5, citation: "[Book A, ch. 3, p. 41]" }];
const flow = (o: Partial<FlowView> = {}): FlowView => ({ level: 3, supports: ["template"], constraints: [], hours: 1, early: true, success_rate: null, target: [0.7, 0.85], can_rate: false, rating: null, ...o });
const rating = (o: Partial<FlowRating> = {}): FlowRating => ({
  id: 1, rating: "too_hard", tapped: "too_hard", inferred: false, classification: "productive_struggle", lever: null, lever_label: null, level_before: 3, level_after: 3,
  message: "Keeping the level. You're under 3 hours on this skill and this is your first try at this task, so this is productive struggle, not overwhelm.", verdict: "Keeping the level.", ...o,
});
const fbMsg: Msg = { id: 9, role: "tutor", kind: "feedback", phase: "feedback", content: "", citations: [], at: "", meta: {
  version: 1, passed: false, summary: "Not passed yet: 0 of 1 principles followed.", since: "", fixes: [], mistakes: [], diff: null,
  results: [{ n: 1, principle: "The want is clear", result: "not", comment: "", quote: "", locator: null, citation: "[Book A, ch. 3, p. 41]", chunk_id: 5 }] } };
const view = (o: Partial<SessionView> = {}): SessionView => ({
  id: 1, phase: "feedback", ended: false, attempt: 1, next_attempt: 2,
  skill: { id: 1, name: "Write a want scene", description: "d", principles, concepts: [] }, project: { id: 1, name: "Kitchen", minutes_per_session: 25 },
  difficulty: 3, hours: 1, task: null, draft: "", timer: { limit_s: 0, elapsed_s: 0, running: false, left_s: null, overtime_s: 0 }, diagnosis: null,
  gate: { unlocked: true, done: 0, total: 0, message: null, missing: [], concepts: [] }, messages: [fbMsg], allowed: ["revise", "ask", "heartbeat"],
  assets: [], flow: flow({ can_rate: true }), check: null, feedback_pending: false, feedback_error: null, route: "revise", route_concepts: [], ...o,
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
const wrap = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/session/1"]}><Routes><Route path="/session/:id" element={<Session />} /></Routes></MemoryRouter>
  </QueryClientProvider>,
);
const server = (get: () => SessionView, extra: Handler = () => undefined): Handler => (url, init) => extra(url, init) ?? (url === "/api/sessions/1" || url === "/api/sessions/1/act" || url === "/api/sessions/1/rating" ? get() : url.startsWith("/api/setup/status") ? { media_enabled: true } : {});
const ratings = (f: ReturnType<typeof vi.fn>) => f.mock.calls.filter((c) => c[0] === "/api/sessions/1/rating").map((c) => JSON.parse((c[1] as RequestInit).body as string));
afterEach(() => vi.unstubAllGlobals());

describe("Rating a task", () => {
  it("asks how the task felt with three one-tap choices, after the feedback", async () => {
    mock(server(() => view()));
    wrap();
    const group = within(await screen.findByRole("group", { name: "How did that task feel?" }));
    expect(group.getAllByRole("button").map((b) => b.textContent)).toEqual(["Too easy", "Just right", "Too hard"]);
    expect(screen.getByRole("button", { name: /Too hard, and I don't know where to start/ })).toBeInTheDocument();
  });

  it("sends the tap and then shows what changes, in words, with the difficulty move", async () => {
    let cur = view();
    const f = mock(server(() => cur, (u, init) => {
      if (u === "/api/sessions/1/rating" && init?.method === "POST") {
        cur = view({ flow: flow({ can_rate: false, rating: rating({ rating: "too_easy", classification: "too_easy", lever: "remove_template", lever_label: "Beat template", level_after: 4,
          verdict: "One change:", message: "One change: the beat template is removed for attempt 2. Everything else stays the same." }) }) });
        return cur;
      }
    }));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Too easy" }));
    expect(ratings(f)).toEqual([{ rating: "too_easy", cant_start: false }]);
    const panel = within(await screen.findByRole("status", { name: "What changes next" }));
    expect(panel.getByText("One change:")).toBeInTheDocument();
    expect(panel.getByText(/the beat template is removed for attempt 2/)).toBeInTheDocument();
    expect(panel.getByText("Difficulty 3 → 4 / 5")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "How did that task feel?" })).not.toBeInTheDocument();
  });

  it("says plainly when the level is kept, and why", async () => {
    mock(server(() => view({ flow: flow({ can_rate: false, rating: rating() }) })));
    wrap();
    const panel = within(await screen.findByRole("status", { name: "What changes next" }));
    expect(panel.getByText("Keeping the level.")).toBeInTheDocument();
    expect(panel.getByText(/productive struggle, not overwhelm/)).toBeInTheDocument();
    expect(panel.getByText("Difficulty 3 stays at 3 / 5")).toBeInTheDocument();
  });

  it("lets you say you don't know where to start", async () => {
    const f = mock(server(() => view()));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: /I don't know where to start/ }));
    expect(ratings(f)).toEqual([{ rating: "too_hard", cant_start: true }]);
  });

  it("tells you when the rating was worked out from your work because you did not tap", async () => {
    mock(server(() => view({ phase: "revise", flow: flow({ rating: rating({ inferred: true, tapped: null, rating: "just_right", classification: "on_target", verdict: "No change:", message: "No change: difficulty stays at 3." }) }) })));
    wrap();
    expect(screen.queryByText(/judged from your work/)).not.toBeInTheDocument();                    // only shown in the feedback phase
  });

  it("shows the reason and keeps the choices when the next task could not be set up", async () => {
    mock(server(() => view(), (u, init) => (u === "/api/sessions/1/rating" && init?.method === "POST"
      ? new Response(JSON.stringify({ detail: { message: "The language model could not be reached. Nothing was changed; try again.", retryable: true } }), { status: 503 }) : undefined)));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Too hard" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    expect(screen.getByRole("button", { name: "Too hard" })).toBeEnabled();
  });

  it("does not ask before there is feedback to rate", async () => {
    mock(server(() => view({ messages: [], feedback_pending: true, route: null, flow: flow({ can_rate: false }) })));
    wrap();
    await screen.findByRole("button", { name: "Get feedback" });
    expect(screen.queryByText("How did that task feel?")).not.toBeInTheDocument();
  });
});

describe("The task and its levers", () => {
  const task = { title: "Rewrite the kitchen scene", instructions: "Mai wants the tin.", support: "beat template, worked example", template: ["Show the want", "First block"], minutes: 20, attempt: 1,
    base_minutes: 20, extras: { template: ["Show the want", "First block"], worked_example: "Made-up case: a boy hides a key.", hint: "Think about who pushes back." } };
  const practice = (t: PracticeTask = task, f = flow()) => view({ phase: "practice", task: t, messages: [], route: null, timer: { limit_s: 1200, elapsed_s: 0, running: true, left_s: 1200, overtime_s: 0 }, flow: f, allowed: ["submit", "ask", "heartbeat", "pause_timer"] });

  it("shows only the help that is switched on, each labelled", async () => {
    mock(server(() => practice()));
    wrap();
    expect(await screen.findByText("Support: beat template, worked example")).toBeInTheDocument();
    expect(screen.getByText("Worked example")).toBeInTheDocument();
    expect(screen.getByText("Made-up case: a boy hides a key.")).toBeInTheDocument();
    expect(screen.getByText("Think about who pushes back.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Beat template" })).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("Constraint")).not.toBeInTheDocument();
  });

  it("shows constraints, a split into steps, and a shorter time", async () => {
    const harder = { ...task, support: null, template: [], minutes: 15, extras: { constraint: "No dialogue in the first beat.", split_steps: ["Set the want", "Block it", "End on a change"], higher_standard: "Every exchange must change who is winning." } };
    mock(server(() => practice(harder, flow({ early: false }))));
    wrap();
    expect(await screen.findByText("No dialogue in the first beat.")).toBeInTheDocument();
    expect(screen.getByText("Constraint")).toBeInTheDocument();
    expect(screen.getByText("Higher standard")).toBeInTheDocument();
    expect(within(screen.getByText("Steps").parentElement!).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Shorter time: 15 min")).toBeInTheDocument();
    expect(screen.queryByText("Speed over polish")).not.toBeInTheDocument();                         // only in the early stage
    expect(screen.queryByText(/^Support:/)).not.toBeInTheDocument();
  });

  it("marks the early stage as speed over polish", async () => {
    mock(server(() => practice()));
    wrap();
    expect(await screen.findByText("Speed over polish")).toBeInTheDocument();
  });
});
