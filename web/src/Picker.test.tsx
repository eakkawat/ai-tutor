import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PickCard, Project, Shortlist } from "./api";
import Picker from "./pages/Picker";
import ProjectForm from "./pages/ProjectForm";

const project = (o: Partial<Project> = {}): Project => ({ id: 1, name: "Grandma's Kitchen", description: "short film", good_enough: "clear", minutes_per_session: 25, active: true, skills_practised: 0, ...o });
const card = (o: Partial<PickCard> = {}): PickCard => ({
  id: 10, name: "Write a want and obstacle scene", description: "You can write a scene driven by a want.", practice_type: "scene", domain: "screenwriting",
  learning_status: "not_started", hours: 0, why: "Your kitchen scene needs a clear want.", recommended: false, needs: [], minutes: 25,
  principles: [{ principle: "The want is clear in the first beat", citation: "[Book A, ch. 3, p. 41]", chunk_id: 5 }], ...o,
});
const list = (skills: PickCard[], o: Partial<Shortlist> = {}): Shortlist => ({ project: project(), skills, ranked_by: "tutor", note: null, all_passed: false, total_available: skills.length, ...o });

type Handler = (url: string, init?: RequestInit) => unknown;
function mock(handler: Handler) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const r = handler(url, init);
    return r instanceof Response ? r : new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
const Where = () => <div data-testid="where">{useLocation().pathname}</div>;
const wrap = (ui: React.ReactNode, path: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/new" element={ui} />
        <Route path="/project/new" element={<ProjectForm />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);
afterEach(() => vi.unstubAllGlobals());

const base = (extra: Record<string, unknown> = {}): Handler => (u) => {
  if (u === "/api/projects") return { projects: [project()], active: project() };
  if (u === "/api/active-skill") return { active: null };
  return (extra[u] as unknown) ?? {};
};

describe("Project form", () => {
  it("asks the three things and creates the project", async () => {
    const f = mock((u, init) => (u === "/api/projects" && init?.method === "POST" ? project() : { projects: [], active: null }));
    wrap(<Picker />, "/project/new");
    await userEvent.type(await screen.findByLabelText("Project name"), "Grandma's Kitchen");
    await userEvent.type(screen.getByLabelText("What you're making"), "A three minute short film");
    await userEvent.type(screen.getByLabelText(/“Good enough” means/), "A stranger understands the scene");
    await userEvent.click(screen.getByRole("button", { name: "45 min" }));
    await userEvent.click(screen.getByRole("button", { name: "Create and see skills" }));
    const post = f.mock.calls.find((c) => c[0] === "/api/projects" && (c[1] as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({ name: "Grandma's Kitchen", description: "A three minute short film", good_enough: "A stranger understands the scene", minutes_per_session: 45 });
  });

  it("shows the server's message when something is missing", async () => {
    mock((_u, init) => (init?.method === "POST" ? new Response(JSON.stringify({ detail: { message: "Name your project." } }), { status: 400 }) : { projects: [], active: null }));
    wrap(<Picker />, "/project/new");
    await userEvent.click(await screen.findByRole("button", { name: "Create and see skills" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name your project.");
  });

  it("lets you use an existing project", async () => {
    const f = mock((u) => (u === "/api/projects" ? { projects: [project({ id: 2, name: "Music video", active: false })], active: null } : project()));
    wrap(<Picker />, "/project/new");
    await userEvent.click(await screen.findByRole("button", { name: "Use Music video" }));
    expect(f).toHaveBeenCalledWith("/api/projects/2/activate", expect.objectContaining({ method: "POST" }));
  });
});

describe("Skill picker", () => {
  it("goes to the project form when there is no active project", async () => {
    mock((u) => (u === "/api/projects" ? { projects: [], active: null } : {}));
    wrap(<Picker />, "/new");
    expect(await screen.findByRole("heading", { name: "What do you want to make?" })).toBeInTheDocument();
  });

  it("shows a short list with one recommended, the reason, and what you'll be judged on", async () => {
    mock(base({ "/api/projects/1/shortlist": list([card({ recommended: true }), card({ id: 11, name: "Write subtext", why: null, needs: [{ id: 10, name: "Write a want and obstacle scene" }] })]) }));
    wrap(<Picker />, "/new");
    const items = await screen.findAllByRole("button", { name: /Write/ });
    expect(items).toHaveLength(2);
    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText("Needs: Write a want and obstacle scene")).toBeInTheDocument();
    expect(screen.getByText(/2 skills from your books fit Grandma's Kitchen/)).toBeInTheDocument();
    const panel = within(screen.getByRole("complementary", { name: "Selected skill" }));
    expect(panel.getByText(/Why first:/).parentElement).toHaveTextContent("Your kitchen scene needs a clear want.");
    expect(panel.getByRole("link", { name: "[Book A, ch. 3, p. 41]" })).toHaveAttribute("href", "/source/5");
    expect(panel.getByText("25 min")).toBeInTheDocument();
  });

  it("warns about a missing prerequisite and lets you pick it or continue anyway", async () => {
    const f = mock(base({ "/api/projects/1/shortlist": list([card({ recommended: true }), card({ id: 11, name: "Write subtext", needs: [{ id: 10, name: "Write a want and obstacle scene" }] })]),
      "/api/skills/11/start": { session_id: 3, skill_id: 11, phase: "diagnose" } }));
    wrap(<Picker />, "/new");
    await userEvent.click(await screen.findByRole("button", { name: /Write subtext/ }));
    const panel = within(screen.getByRole("complementary", { name: "Selected skill" }));
    expect(panel.getByText("Needs Write a want and obstacle scene first.")).toBeInTheDocument();
    await userEvent.click(panel.getByRole("button", { name: "Pick Write a want and obstacle scene" }));
    expect(within(screen.getByRole("complementary", { name: "Selected skill" })).getByRole("heading", { name: "Write a want and obstacle scene" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Write subtext/ }));
    await userEvent.click(screen.getByRole("button", { name: "Start anyway" }));
    await waitFor(() => expect(f).toHaveBeenCalledWith("/api/skills/11/start", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByTestId("where")).toHaveTextContent("/session/3");
  });

  it("asks before pausing the active skill, then pauses and starts", async () => {
    let calls = 0;
    const f = mock((u, init) => {
      if (u === "/api/projects") return { projects: [project()], active: project() };
      if (u === "/api/active-skill") return { active: { id: 1, name: "Want vs. obstacle in a scene", hours: 2.9, attempt_next: 3, session_id: 4, phase: "practice" } };
      if (u === "/api/projects/1/shortlist") return list([card({ recommended: true })]);
      if (u === "/api/skills/10/start") {
        calls++;
        const body = JSON.parse(init!.body as string);
        return body.pause_current ? { session_id: 7, skill_id: 10, phase: "diagnose" }
          : new Response(JSON.stringify({ detail: { message: "You are working on it.", code: "active_skill", active: {} } }), { status: 409 });
      }
      return {};
    });
    wrap(<Picker />, "/new");
    expect(await screen.findByText("2.9 / 20 h · attempt 3 next")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue it" })).toHaveAttribute("href", "/session/4");
    await userEvent.click(await screen.findByRole("button", { name: "Start this skill" }));
    const dlg = within(await screen.findByRole("dialog", { name: "Pause your current skill?" }));
    expect(dlg.getByText(/will be paused with its 2.9 hours/)).toBeInTheDocument();
    await userEvent.click(dlg.getByRole("button", { name: "Keep current skill" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start this skill" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Pause and start" }));
    expect(await screen.findByTestId("where")).toHaveTextContent("/session/7");
    expect(calls).toBe(3);
    const last = f.mock.calls.filter((c) => c[0] === "/api/skills/10/start").pop()!;
    expect(JSON.parse(last[1]!.body as string)).toEqual({ project_id: 1, pause_current: true });
  });

  it("says so when the tutor was unreachable, and when there is nothing to pick", async () => {
    mock(base({ "/api/projects/1/shortlist": list([card({ recommended: true, why: null })], { ranked_by: "similarity", note: "Only 1 skill in your library so far. Add more books to see more choices." }) }));
    wrap(<Picker />, "/new");
    expect(await screen.findByText(/ordered by how well they match your project/)).toBeInTheDocument();
    expect(screen.getByText(/Only 1 skill in your library/)).toBeInTheDocument();
  });

  it("offers Review when every skill is passed, and Library when there are no skills", async () => {
    mock(base({ "/api/projects/1/shortlist": list([], { all_passed: true, note: "You have passed every skill in your library." }) }));
    const { unmount } = wrap(<Picker />, "/new");
    expect(await screen.findByRole("link", { name: "Review passed skills" })).toBeInTheDocument();
    unmount();
    mock(base({ "/api/projects/1/shortlist": list([], { note: "There are no skills yet. Add a book in the Library first." }) }));
    wrap(<Picker />, "/new");
    expect(await screen.findByRole("link", { name: "Open Library" })).toHaveAttribute("href", "/library");
  });
});
