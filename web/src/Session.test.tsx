import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FbMeta, Msg, SessionPhase, SessionView } from "./api";
import Session from "./pages/Session";

const principles = [
  { id: 1, principle: "The want is clear in the first beat", test: "t1", chunk_id: 5, citation: "[Book A, ch. 3, p. 41]" },
  { id: 2, principle: "The obstacle pushes back", test: "t2", chunk_id: 6, citation: "[Book A, ch. 4, p. 60]" },
];
const msg = (o: Partial<Msg> & { id: number }): Msg => ({ role: "tutor", kind: "note", phase: "diagnose", content: "", citations: [], meta: {}, at: "", ...o });
const view = (o: Partial<SessionView> = {}): SessionView => ({
  id: 1, phase: "diagnose", ended: false, attempt: 0, next_attempt: 1,
  skill: { id: 1, name: "Write a want and obstacle scene", description: "d", principles, concepts: [] },
  project: { id: 1, name: "Grandma's Kitchen", minutes_per_session: 25 }, difficulty: 3, hours: 2.6, task: null, draft: "",
  timer: { limit_s: 0, elapsed_s: 0, running: false, left_s: null, overtime_s: 0 }, diagnosis: null,
  gate: { unlocked: false, done: 0, total: 2, message: "Practice unlocks when all 2 concepts reach Spot. 0 of 2 done. Missing: obstacle, want.", missing: [],
    concepts: [{ id: 1, name: "want", level: "none" }, { id: 2, name: "obstacle", level: "define" }] },
  messages: [], allowed: ["begin", "answer", "advance", "ask", "pause_timer", "resume_timer", "heartbeat"],
  assets: [], check: null, feedback_pending: false, feedback_error: null, route: null, route_concepts: [], ...o,
});
const task = { title: "Rewrite the kitchen scene", instructions: "Mai wants the recipe tin.", support: "beat template", template: ["Show the want", "First block"], minutes: 20, attempt: 1 };

type Handler = (url: string, init?: RequestInit) => unknown;
function mock(handler: Handler) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const r = handler(url, init);
    return r instanceof Response ? r : new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
const acts = (f: ReturnType<typeof vi.fn>) => f.mock.calls.filter((c) => c[0] === "/api/sessions/1/act").map((c) => JSON.parse((c[1] as RequestInit).body as string));
const wrap = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/session/1"]}><Routes><Route path="/session/:id" element={<Session />} /></Routes></MemoryRouter>
  </QueryClientProvider>,
);
const api = (v: SessionView, onAct?: (body: { action: string; text: string }) => SessionView | Response): Handler => (url, init) => {
  if (url === "/api/sessions/1") return v;
  if (url === "/api/sessions/1/act") { const r = onAct?.(JSON.parse(init!.body as string)); return r ?? v; }
  if (url === "/api/sessions/1/draft") return { ok: true };
  return {};
};
afterEach(() => vi.unstubAllGlobals());

describe("Diagnose", () => {
  it("asks the tutor for the first task when a session is new, then takes your answer", async () => {
    let cur = view();
    const f = mock(api(cur, (b) => {
      if (b.action === "begin") cur = view({ messages: [msg({ id: 1, kind: "diagnose_task", content: "Write three lines where Mai wants the tin." })] });
      if (b.action === "answer") cur = view({ diagnosis: { can_do: "You set the scene.", gap: "The want is late.", level: 2, meets_all: false },
        messages: [...cur.messages, msg({ id: 2, role: "user", kind: "answer", content: b.text }), msg({ id: 3, kind: "diagnosis", content: "You set the scene.\nGap: The want is late." })] });
      return cur;
    }));
    vi.spyOn(globalThis, "fetch");
    wrap();
    expect(await screen.findByText("Write three lines where Mai wants the tin.")).toBeInTheDocument();
    expect(acts(f)).toEqual([{ action: "begin", text: "" }]);
    await userEvent.type(screen.getByLabelText("Your answer"), "MAI: Give me the tin.");
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(await screen.findByText(/Gap: The want is late/)).toBeInTheDocument();
    expect(acts(f)[1]).toEqual({ action: "answer", text: "MAI: Give me the tin." });
    expect(screen.getByRole("button", { name: "Continue to the lesson" })).toBeInTheDocument();
  });

  it("shows seven phases with the current one marked", async () => {
    mock(api(view({ phase: "learn", messages: [msg({ id: 1, kind: "learn", phase: "learn", content: "x" })] })));
    wrap();
    const steps = within(await screen.findByRole("list", { name: "Phases" })).getAllByRole("listitem");
    expect(steps).toHaveLength(7);
    expect(steps.map((s) => s.getAttribute("aria-current"))).toEqual([null, "step", null, null, null, null, null]);
  });
});

describe("Learn", () => {
  const lesson = view({
    phase: "learn", messages: [msg({ id: 7, kind: "learn", phase: "learn", meta: { title: "State the want early" },
      content: "A scene needs a want first [Book A, ch. 3, p. 41]. Extra idea [outside my books].", citations: [{ citation: "[Book A, ch. 3, p. 41]", chunk_id: 5 }] })],
  });

  it("turns a citation into a button that opens the passage, and marks outside ideas", async () => {
    mock((url, init) => (url === "/api/chunks/5" ? { id: 5, source_id: 1, source_title: "Book A", author: null, label: "Ch. 3", title: "Want", page_start: 41, page_end: 41,
      citation: "[Book A, ch. 3, p. 41]", text: "A scene needs a want and an obstacle.", before: null, after: null, prev_id: null, next_id: null } : api(lesson)(url, init)));
    wrap();
    expect(await screen.findByRole("heading", { name: "State the want early" })).toBeInTheDocument();
    expect(screen.getByText("[outside my books]")).toHaveClass("outside");
    await userEvent.click(within(screen.getByRole("article", { name: "Learn" })).getByRole("button", { name: "[Book A, ch. 3, p. 41]" }));
    const panel = within(await screen.findByRole("region", { name: "Source" }));
    expect(panel.getByText("A scene needs a want and an obstacle.")).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Open full page" })).toHaveAttribute("href", "/source/5");
  });

  it("flags a message with 'This felt wrong' and a note, without leaving", async () => {
    const f = mock((url, init) => (url === "/api/messages/7/felt-wrong" ? { ok: true } : api(lesson)(url, init)));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "This felt wrong" }));
    await userEvent.type(screen.getByLabelText(/What felt wrong/), "Too long");
    await userEvent.click(screen.getByRole("button", { name: "Save to feedback log" }));
    await waitFor(() => expect(f).toHaveBeenCalledWith("/api/messages/7/felt-wrong", expect.objectContaining({ method: "POST" })));
    expect(JSON.parse((f.mock.calls.find((c) => c[0] === "/api/messages/7/felt-wrong")![1] as RequestInit).body as string)).toEqual({ note: "Too long" });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "State the want early" })).toBeInTheDocument();
  });
});

describe("Check", () => {
  it("keeps practice locked and says which concepts are missing", async () => {
    mock(api(view({ phase: "check" })));
    wrap();
    const btn = await screen.findByRole("button", { name: "Practice is locked" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription(/Practice unlocks when all 2 concepts reach Spot. 0 of 2 done. Missing: obstacle, want./);
    expect(screen.getByText("Define only")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
  });

  it("unlocks when every concept is at Spot", async () => {
    const f = mock(api(view({ phase: "check", gate: { unlocked: true, done: 2, total: 2, message: null, missing: [], concepts: [{ id: 1, name: "want", level: "spot" }, { id: 2, name: "obstacle", level: "use" }] } })));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Start practice" }));
    expect(acts(f)).toEqual([{ action: "unlock", text: "" }]);
  });
});

describe("Practice", () => {
  const practice = (o: Partial<SessionView> = {}) => view({ phase: "practice", task, next_attempt: 1,
    timer: { limit_s: 1200, elapsed_s: 300, running: true, left_s: 900, overtime_s: 0 }, ...o });

  it("shows the task, a running timer you can pause, and the support you were given", async () => {
    const f = mock(api(practice()));
    wrap();
    expect(await screen.findByText("Support: beat template")).toBeInTheDocument();
    expect(screen.getByRole("timer", { name: "Task time" })).toHaveTextContent("15:00");
    expect(screen.getByText("Show the want")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Pause timer" }));
    expect(acts(f).some((a) => a.action === "pause_timer")).toBe(true);
  });

  it("shows time over the limit as over, not as a stop", async () => {
    mock(api(practice({ timer: { limit_s: 1200, elapsed_s: 1500, running: false, left_s: -300, overtime_s: 300 } })));
    wrap();
    expect(await screen.findByRole("timer", { name: "Task time" })).toHaveTextContent("+05:00");
    expect(screen.getByText("Task time over")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume timer" })).toBeInTheDocument();
  });

  it("restores a saved draft, saves while you type, and submits the text", async () => {
    const f = mock(api(practice({ draft: "INT. KITCHEN" }), (b) => (b.action === "submit" ? practice({ phase: "feedback", attempt: 1, draft: "", feedback_pending: true }) : practice())));
    wrap();
    const box = await screen.findByLabelText("Your work");
    expect(box).toHaveValue("INT. KITCHEN");
    await userEvent.type(box, " - NIGHT");
    await waitFor(() => expect(f.mock.calls.some((c) => c[0] === "/api/sessions/1/draft" && String((c[1] as RequestInit).body).includes("INT. KITCHEN - NIGHT"))).toBe(true), { timeout: 3000 });
    await userEvent.click(screen.getByRole("button", { name: "Submit attempt 1" }));
    expect(acts(f).find((a) => a.action === "submit")).toEqual({ action: "submit", text: "INT. KITCHEN - NIGHT" });
    expect(await screen.findByText(/Attempt 1 is saved/)).toBeInTheDocument();
  });

  it("cannot submit an empty attempt", async () => {
    mock(api(practice()));
    wrap();
    expect(await screen.findByRole("button", { name: "Submit attempt 1" })).toBeDisabled();
  });
});

describe("Errors and questions", () => {
  it("says the state did not change and retries the same action", async () => {
    let fail = true;
    const f = mock(api(view({ phase: "diagnose", diagnosis: { can_do: "a", gap: "b", level: 1, meets_all: false }, messages: [msg({ id: 1, kind: "diagnosis", content: "a" })] }), (b) => {
      if (b.action === "advance" && fail) { fail = false; return new Response(JSON.stringify({ detail: { message: "The language model could not be reached. Nothing was changed; try again.", retryable: true } }), { status: 503 }); }
      return view({ phase: "learn", messages: [msg({ id: 2, kind: "learn", phase: "learn", content: "Lesson body" })] });
    }));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Continue to the lesson" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Lesson body")).toBeInTheDocument();
    expect(acts(f).filter((a) => a.action === "advance")).toHaveLength(2);
  });

  it("sends a question and keeps the phase", async () => {
    const f = mock(api(view({ phase: "learn" }), () => view({ phase: "learn", messages: [msg({ id: 1, role: "user", kind: "question", content: "What is a want?" }), msg({ id: 2, kind: "qa", phase: "learn", content: "A want is what a character is after." })] })));
    wrap();
    await userEvent.type(await screen.findByLabelText("Ask a question about this skill"), "What is a want?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("A want is what a character is after.")).toBeInTheDocument();
    expect(acts(f)).toEqual([{ action: "ask", text: "What is a want?" }]);
  });
});

describe("Pass", () => {
  it("shows the pass screen with the hours and one suggested next skill", async () => {
    const f = mock((url) => (url === "/api/sessions/1/next"
      ? { next: { id: 9, name: "Write subtext", why: "Your kitchen scene needs it." }, note: null, all_passed: false } : view({ phase: "pass" as SessionPhase, ended: true, hours: 4.2, allowed: ["ask"] })));
    wrap();
    expect(await screen.findByRole("heading", { name: "Write a want and obstacle scene: passed" })).toBeInTheDocument();
    expect(screen.getByText("4.2")).toBeInTheDocument();
    expect(await screen.findByText("Write subtext")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose your next skill" })).toHaveAttribute("href", "/new");
    expect(f.mock.calls.some((c) => c[0] === "/api/sessions/1/next")).toBe(true);
  });
});


// ---------- the foundations check

const checkView = (cur: Partial<NonNullable<SessionView["check"]>["current"]> | null, o: Partial<SessionView> = {}) => view({
  phase: "check", allowed: ["check", "check_answer", "check_hint", "check_more", "unlock", "ask", "heartbeat"],
  check: { current: cur ? { concept: "obstacle", concept_id: 2, level: "spot", prompt: "Which reply shifts the upper hand?\nA. MAI: Please.\nB. MAI: Then you tell me when.", options: ["A. MAI: Please.", "B. MAI: Then you tell me when."], attempts: 0, hint_shown: false, ...cur } : null,
    remaining_minutes: 3, budget_left: 10, all_done: false }, ...o,
});

describe("Foundations check", () => {
  it("asks a spot question as choices, and sends the chosen one", async () => {
    const f = mock(api(checkView({})));
    wrap();
    const send = await screen.findByRole("button", { name: "Check answer" });
    expect(send).toBeDisabled();
    expect(screen.getByText(/about 3 min/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "B. MAI: Then you tell me when." }));
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(acts(f)).toEqual([{ action: "check_answer", text: "B. MAI: Then you tell me when." }]);
  });

  it("asks a define question as free text, and offers one hint before the answer is shown", async () => {
    const f = mock(api(checkView({ level: "define", prompt: "What is an obstacle?", options: [] })));
    wrap();
    await userEvent.type(await screen.findByLabelText("Your answer, in your own words"), "what pushes back");
    await userEvent.click(screen.getByRole("button", { name: "Check answer" }));
    await userEvent.click(screen.getByRole("button", { name: "Hint" }));
    expect(acts(f)).toEqual([{ action: "check_answer", text: "what pushes back" }, { action: "check_hint", text: "" }]);
  });

  it("disables the hint once it has been given", async () => {
    mock(api(checkView({ hint_shown: true })));
    wrap();
    expect(await screen.findByRole("button", { name: "Hint" })).toBeDisabled();
  });

  it("asks for the next question when none is open, and keeps practice locked with the reason", async () => {
    const f = mock(api(checkView(null)));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Next question" }));
    expect(acts(f)).toEqual([{ action: "check", text: "" }]);
    const locked = screen.getByRole("button", { name: "Practice is locked" });
    expect(locked).toBeDisabled();
    expect(locked).toHaveAccessibleDescription(/Practice unlocks when all 2 concepts reach Spot/);
  });

  it("lets you keep going after a long sitting", async () => {
    const f = mock(api(checkView(null, { check: { current: null, remaining_minutes: 2, budget_left: 0, all_done: false } })));
    wrap();
    expect(await screen.findByText(/enough for one sitting/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep checking" }));
    expect(acts(f)).toEqual([{ action: "check_more", text: "" }]);
  });

  it("unlocks the next attempt once the concept is back at Spot", async () => {
    const unlocked = { unlocked: true, done: 2, total: 2, message: null, missing: [], concepts: [{ id: 1, name: "want", level: "spot" }, { id: 2, name: "obstacle", level: "spot" }] };
    mock(api(checkView(null, { attempt: 1, gate: unlocked, check: { current: null, remaining_minutes: 0, budget_left: 10, all_done: true } })));
    wrap();
    expect(await screen.findByRole("button", { name: "Start the next attempt" })).toBeEnabled();
  });
});

// ---------- feedback

const fbMeta = (o: Partial<FbMeta> = {}): FbMeta => ({
  version: 2, passed: false, summary: "Not passed yet: 1 of 3 principles followed.", since: "Improved: principle 2.",
  results: [
    { n: 1, principle: "The want is clear in the first beat", result: "followed", comment: "Mai reaching for the tin shows it.", quote: "Mai reaches for the tin", locator: "Line 2", citation: "[Book A, ch. 3, p. 41]", chunk_id: 5 },
    { n: 2, principle: "The obstacle pushes back", result: "partly", comment: "Grandma blocks once.", quote: "Grandma slides the tin", locator: "Line 3", citation: "[Book A, ch. 4, p. 60]", chunk_id: 6 },
    { n: 3, principle: "The scene ends on a change", result: "not", comment: "", quote: "", locator: null, citation: "[Book A, ch. 5, p. 70]", chunk_id: 7 },
  ],
  fixes: [{ n: 3, fix: "End on a beat where her want changes.", example: "She starts writing the recipe down.", citation: "[Book A, ch. 5, p. 70]", chunk_id: 7, principle: "The scene ends on a change" }],
  mistakes: [{ n: 3, kind: "execution", concept: null, tag: "weak ending", count: 2 }], diff: null, ...o,
});
const fbView = (o: Partial<SessionView> = {}, meta: Partial<FbMeta> = {}) => view({
  phase: "feedback", attempt: 2, next_attempt: 3, route: "revise", allowed: ["feedback", "revise", "reteach", "pass", "ask", "heartbeat"],
  messages: [msg({ id: 9, kind: "feedback", phase: "feedback", content: "Not passed yet", meta: fbMeta(meta) as unknown as Msg["meta"],
    citations: [{ citation: "[Book A, ch. 3, p. 41]", chunk_id: 5 }] })], ...o,
});

describe("Feedback", () => {
  it("shows every principle with a verdict in words, its citation, the line, and the fix", async () => {
    mock(api(fbView()));
    wrap();
    expect(await screen.findByRole("heading", { name: "Not passed yet: 1 of 3 principles followed." })).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Principle checklist" })).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Followed")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Line 2")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("button", { name: "[Book A, ch. 3, p. 41]" })).toBeInTheDocument();
    expect(within(rows[1]).getByText("Partly")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Not followed")).toBeInTheDocument();
    const fixes = within(screen.getByLabelText("Fixes"));
    expect(fixes.getByText(/End on a beat where her want changes/)).toBeInTheDocument();
    expect(fixes.getByRole("button", { name: "[Book A, ch. 5, p. 70]" })).toBeInTheDocument();
    expect(screen.getByText("Improved: principle 2.")).toBeInTheDocument();
    expect(screen.getByText(/Recurring mistake: weak ending/)).toBeInTheDocument();
  });

  it("sends an execution mistake straight back to revise", async () => {
    const f = mock(api(fbView()));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Start attempt 3" }));
    expect(acts(f)).toEqual([{ action: "revise", text: "" }]);
  });

  it("sends a concept mistake to a re-teach first", async () => {
    const f = mock(api(fbView({ route: "reteach", route_concepts: ["obstacle"] })));
    wrap();
    expect(await screen.findByText(/A concept needs another look before your next attempt/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start attempt/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Re-teach obstacle" }));
    expect(acts(f)).toEqual([{ action: "reteach", text: "" }]);
  });

  it("offers to finish the skill only when every principle is followed", async () => {
    const f = mock(api(fbView({ route: "pass" }, { passed: true, summary: "Passed: every principle is followed." })));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Finish this skill" }));
    expect(acts(f)).toEqual([{ action: "pass", text: "" }]);
  });

  it("keeps your work and offers 'Get feedback' when feedback could not be given", async () => {
    const f = mock(api(view({ phase: "feedback", attempt: 1, feedback_pending: true, feedback_error: "The language model could not be reached.",
      messages: [msg({ id: 1, role: "user", kind: "submission", phase: "practice", content: "INT. KITCHEN", meta: { version: 1, minutes: 12 } })] })));
    wrap();
    expect(await screen.findByText(/Attempt 1 is saved. The language model could not be reached./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Get feedback" }));
    expect(acts(f)).toEqual([{ action: "feedback", text: "" }]);
  });

  it("compares two attempts line by line, saying added and removed in words", async () => {
    mock((url, init) => (url === "/api/sessions/1/compare?a=1&b=2"
      ? { a: { version: 1, text: "" }, b: { version: 2, text: "" }, lines: [{ op: " ", text: "kept line" }, { op: "-", text: "old line" }, { op: "+", text: "new line" }] }
      : api(fbView())(url, init)));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: "Compare attempts" }));
    const dlg = within(await screen.findByRole("dialog", { name: "Attempt 1 to attempt 2" }));
    expect(dlg.getByText("Added:")).toBeInTheDocument();
    expect(dlg.getByText("Removed:")).toBeInTheDocument();
    expect(dlg.getByText("kept line")).toBeInTheDocument();
    await userEvent.click(dlg.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("starts a revision from the work you handed in", async () => {
    mock(api(view({ phase: "revise", task, attempt: 1, next_attempt: 2, timer: { limit_s: 1200, elapsed_s: 0, running: true, left_s: 1200, overtime_s: 0 },
      messages: [msg({ id: 1, role: "user", kind: "submission", phase: "practice", content: "INT. KITCHEN - NIGHT\nMai reaches.", meta: { version: 1, minutes: 12 } })] })));
    wrap();
    expect(await screen.findByLabelText("Your work")).toHaveValue("INT. KITCHEN - NIGHT\nMai reaches.");
    expect(screen.getByRole("button", { name: "Submit attempt 2" })).toBeEnabled();
  });
});
