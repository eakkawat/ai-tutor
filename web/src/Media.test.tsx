import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Asset, FbMeta, Msg, SessionView } from "./api";
import Session from "./pages/Session";

const principles = [{ id: 1, principle: "The tin is the focus", test: "t1", chunk_id: 5, citation: "[Book A, ch. 3, p. 41]" }];
const task = { title: "Storyboard the reach", instructions: "Draw one frame.", support: null, template: [], minutes: 20, attempt: 1 };
const asset = (o: Partial<Asset> = {}): Asset => ({
  id: 1, kind: "image", filename: "frame_01.png", status: "ready", error: null, duration_s: null, size_bytes: 1000, steps: null, notes: [], width: 640, height: 360,
  downscaled: false, thumb: "/api/assets/1/file?variant=thumb", attached: false, ...o,
});
const view = (o: Partial<SessionView> = {}): SessionView => ({
  id: 1, phase: "practice", ended: false, attempt: 0, next_attempt: 1,
  skill: { id: 1, name: "Compose a frame", description: "d", principles, concepts: [] }, project: { id: 1, name: "Grandma's Kitchen", minutes_per_session: 25 },
  difficulty: 3, hours: 1, task, draft: "", timer: { limit_s: 1200, elapsed_s: 0, running: true, left_s: 1200, overtime_s: 0 }, diagnosis: null,
  gate: { unlocked: true, done: 0, total: 0, message: null, missing: [], concepts: [] }, messages: [], allowed: ["submit", "ask", "heartbeat", "pause_timer", "resume_timer"],
  assets: [], flow: { level: 3, supports: ["template"], constraints: [], hours: 1, early: true, success_rate: null, target: [0.7, 0.85], can_rate: false, rating: null }, check: null, feedback_pending: false, feedback_error: null, route: null, route_concepts: [], ...o,
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
const setup = (media: boolean) => ({ checks: [], can_continue: true, media_enabled: media, media_note: null });
const server = (get: () => SessionView, extra: Handler = () => undefined, media = true): Handler => (url, init) => {
  const e = extra(url, init);
  if (e !== undefined) return e;
  if (url === "/api/sessions/1") return get();
  if (url.startsWith("/api/setup/status")) return setup(media);
  if (url === "/api/setup/vision") return { vision: true };
  if (url === "/api/sessions/1/draft") return { ok: true };
  return {};
};
const calls = (f: ReturnType<typeof vi.fn>, url: string) => f.mock.calls.filter((c) => c[0] === url);
afterEach(() => vi.unstubAllGlobals());

describe("Attachments", () => {
  it("uploads a chosen picture and then lists it with a preview, its size and a Remove button", async () => {
    let assets: Asset[] = [];
    const f = mock(server(() => view({ assets }), (u, init) => {
      if (u === "/api/sessions/1/assets" && init?.method === "POST") { assets = [asset()]; return asset(); }
      if (u === "/api/assets/1" && init?.method === "DELETE") { assets = []; return { ok: true }; }
    }));
    wrap();
    const input = await screen.findByLabelText("Browse files");
    await userEvent.upload(input, new File(["x"], "frame_01.png", { type: "image/png" }));
    const row = within(await screen.findByRole("listitem", { name: "frame_01.png" }));
    expect(row.getByRole("img", { name: "Preview of frame_01.png" })).toHaveAttribute("src", "/api/assets/1/file?variant=thumb");
    expect(row.getByText(/Ready · 640×360/)).toBeInTheDocument();
    const sent = (calls(f, "/api/sessions/1/assets")[0][1] as RequestInit).body as FormData;
    expect((sent.get("file") as File).name).toBe("frame_01.png");
    await userEvent.click(row.getByRole("button", { name: "Remove frame_01.png" }));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "frame_01.png" })).not.toBeInTheDocument());
  });

  it("accepts files dropped on the area", async () => {
    const f = mock(server(() => view(), (u, init) => (u === "/api/sessions/1/assets" && init?.method === "POST" ? asset() : undefined)));
    wrap();
    const zone = (await screen.findByText(/Drop pictures or video clips here/)).parentElement!;
    const file = new File(["x"], "board.png", { type: "image/png" });
    zone.dispatchEvent(Object.assign(new Event("drop", { bubbles: true, cancelable: true }), { dataTransfer: { files: [file] } }));
    await waitFor(() => expect(calls(f, "/api/sessions/1/assets")).toHaveLength(1));
  });

  it("turns picture and clip upload off, with the reason, when the media tools are missing — text still works", async () => {
    mock(server(() => view(), () => undefined, false));
    wrap();
    await waitFor(() => expect(screen.getByText("Pictures and clips are off")).toBeInTheDocument());
    expect(screen.getByText(/Text practice still works/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Browse files")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your work"), "INT. KITCHEN");
    expect(screen.getByRole("button", { name: "Submit attempt 1" })).toBeEnabled();
  });

  it("shows a clip's progress step by step and holds the submission until it has finished", async () => {
    const processing = asset({ id: 2, kind: "video", filename: "take2.mp4", status: "processing", duration_s: 108, thumb: null,
      steps: { frames: { status: "running", done: 3, total: 20 }, transcript: { status: "waiting" }, cuts: { status: "done", count: 5 } } });
    mock(server(() => view({ assets: [processing] })));
    wrap();
    const row = within(await screen.findByRole("listitem", { name: "take2.mp4" }));
    expect(row.getByText("Keyframes · 3 of 20")).toBeInTheDocument();
    expect(row.getByText("Transcript · waiting")).toBeInTheDocument();
    expect(row.getByText("Cuts · done · 5")).toBeInTheDocument();
    expect(row.getByText(/1:48 · processing on this computer/)).toBeInTheDocument();
    expect(row.getByRole("progressbar", { name: "Keyframes" })).toHaveAttribute("aria-valuenow", "15");
    await userEvent.type(screen.getByLabelText("Your work"), "INT. KITCHEN");
    const submit = screen.getByRole("button", { name: "Submit attempt 1" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription(/still being processed on this computer/);
  });

  it("says why a clip failed, offers to try again, and does not let it be submitted", async () => {
    const bad = asset({ id: 3, kind: "video", filename: "broken.mp4", status: "error", error: "ffmpeg could not take a picture at 0:02.", thumb: null });
    const f = mock(server(() => view({ assets: [bad] }), (u, init) => (u === "/api/assets/3/retry" && init?.method === "POST" ? { ok: true } : undefined)));
    wrap();
    const row = within(await screen.findByRole("listitem", { name: "broken.mp4" }));
    expect(row.getByRole("alert")).toHaveTextContent("ffmpeg could not take a picture at 0:02.");
    expect(screen.getByRole("button", { name: "Submit attempt 1" })).toBeDisabled();
    await userEvent.click(row.getByRole("button", { name: "Try this clip again" }));
    expect(calls(f, "/api/assets/3/retry")).toHaveLength(1);
  });

  it("shows the server's reason when a file is rejected, naming the file", async () => {
    mock(server(() => view(), (u, init) => (u === "/api/sessions/1/assets" && init?.method === "POST"
      ? new Response(JSON.stringify({ detail: { message: "This clip is 4:12 long. Clips can be up to 3 minutes. Split it into shorter clips and add them again.", code: "too_long" } }), { status: 422 }) : undefined)));
    wrap();
    await userEvent.upload(await screen.findByLabelText("Browse files"), new File(["x"], "long_take.mp4", { type: "video/mp4" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("long_take.mp4");
    expect(alert).toHaveTextContent("Split it into shorter clips");
    await userEvent.click(within(alert).getByRole("button", { name: /Dismiss message about long_take.mp4/ }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lets you submit with only a picture, no text", async () => {
    const f = mock(server(() => view({ assets: [asset()] }), (u) => (u === "/api/sessions/1/act" ? view({ phase: "feedback", attempt: 1, feedback_pending: true }) : undefined)));
    wrap();
    const submit = await screen.findByRole("button", { name: "Submit attempt 1" });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(JSON.parse((calls(f, "/api/sessions/1/act")[0][1] as RequestInit).body as string)).toEqual({ action: "submit", text: "" });
  });

  it("warns when the language model cannot read pictures", async () => {
    mock(server(() => view({ assets: [asset()] }), (u) => (u === "/api/setup/vision" ? { vision: false } : undefined)));
    wrap();
    expect(await screen.findByText(/cannot read pictures, so pictures and clips would not be judged/)).toBeInTheDocument();
  });

  it("shows what was handed in with an attempt", async () => {
    const msg: Msg = { id: 4, role: "user", kind: "submission", phase: "practice", content: "", citations: [], at: "", meta: { version: 1, minutes: 12, assets: [asset({ attached: true })] } };
    mock(server(() => view({ phase: "feedback", attempt: 1, messages: [msg] })));
    wrap();
    const list = within(await screen.findByRole("list", { name: "Attachments" }));
    expect(list.getByText("frame_01.png")).toBeInTheDocument();
  });
});

describe("Feedback on pictures and clips", () => {
  const meta = (): FbMeta => ({
    version: 1, passed: false, summary: "Not passed yet: 0 of 2 principles followed.", since: "", fixes: [], mistakes: [], diff: null,
    results: [
      { n: 1, principle: "The tin is the focus", result: "partly", comment: "The tin is large but dim.", quote: "", locator: "Image 1, upper left", citation: "[Book A, ch. 3, p. 41]", chunk_id: 5,
        evidence: { kind: "image", n: 1, asset_id: 1, filename: "frame_01.png", locator: "Image 1, upper left", region: [0.1, 0.2, 0.3, 0.4] } },
      { n: 2, principle: "The shot changes", result: "followed", comment: "The cut lands at 0:02.", quote: "", locator: "Video 1 · 0:02–0:05", citation: "[Book A, ch. 4, p. 60]", chunk_id: 6,
        evidence: { kind: "video", n: 1, asset_id: 2, filename: "take2.mp4", locator: "Video 1 · 0:02–0:05", start_s: 2, end_s: 5, frames: [{ id: 11, idx: 2, t: 2.1 }, { id: 12, idx: 3, t: 4 }] } },
    ],
  });

  it("shows the part of the picture and the frames from the moment, beside the comment", async () => {
    const fb: Msg = { id: 9, role: "tutor", kind: "feedback", phase: "feedback", content: "", citations: [], at: "", meta: meta() as unknown as Msg["meta"] };
    mock(server(() => view({ phase: "feedback", attempt: 1, route: "revise", messages: [fb], allowed: ["revise", "ask", "heartbeat"] })));
    wrap();
    const rows = within(await screen.findByRole("list", { name: "Principle checklist" })).getAllByRole("listitem");
    expect(within(rows[0]).getByText("Image 1, upper left")).toBeInTheDocument();
    const box = within(rows[0]).getByRole("img", { name: "Region in Image 1" });
    expect(box).toHaveStyle({ left: "10%", top: "20%", width: "30%", height: "40%" });
    expect(within(rows[0]).getByRole("img", { name: "frame_01.png" })).toHaveAttribute("src", "/api/assets/1/file?variant=thumb");
    expect(within(rows[1]).getByText("Video 1 · 0:02–0:05")).toBeInTheDocument();
    const frames = within(rows[1]).getAllByRole("img");
    expect(frames.map((i) => i.getAttribute("src"))).toEqual(["/api/frames/11", "/api/frames/12"]);
    expect(frames[0]).toHaveAccessibleName("Frame 2 of take2.mp4 at 0:02");
    expect(within(rows[1]).getByText("0:04")).toBeInTheDocument();
  });
});
