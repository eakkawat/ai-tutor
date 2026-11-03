import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Check, Home, SetupStatus } from "./api";

const chk = (id: Check["id"], status: Check["status"], over: Partial<Check> = {}): Check => ({
  id, label: { llm: "Language model", ffmpeg: "ffmpeg", ffprobe: "ffprobe", whisper: "Whisper" }[id], purpose: "p",
  required: id === "llm", status, fix: status === "ready" ? null : id === "llm" ? "Enter the server URL and model name below." : "pip install faster-whisper",
  detail: null, ...over,
});
const status = (checks: Check[]): SetupStatus => {
  const media = ["ffmpeg", "ffprobe", "whisper"].every((i) => checks.find((c) => c.id === i)!.status === "ready");
  return { checks, can_continue: checks[0].status !== "missing" && checks[0].status !== "invalid", media_enabled: media,
    media_note: media ? null : "Image and video upload are off until ffmpeg, ffprobe and Whisper are installed. Text practice still works." };
};
const OK = status([chk("llm", "ready"), chk("ffmpeg", "ready"), chk("ffprobe", "ready"), chk("whisper", "ready")]);
const NO_KEY = status([chk("llm", "missing"), chk("ffmpeg", "ready"), chk("ffprobe", "ready"), chk("whisper", "ready")]);
const NO_WHISPER = status([chk("llm", "ready"), chk("ffmpeg", "ready"), chk("ffprobe", "ready"), chk("whisper", "missing")]);
const EMPTY: Home = { state: "empty_library", books: 0, active_skill: null, reviews_due: 0 };

function mockApi(routes: Record<string, unknown | ((init?: RequestInit) => Response)>) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const hit = routes[url];
    if (typeof hit === "function") return hit(init);
    if (hit === undefined) throw new Error(`unmocked ${url}`);
    return new Response(JSON.stringify(hit), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
function renderApp(path = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

async function fill() {
  await userEvent.type(await screen.findByLabelText("Server URL"), "http://127.0.0.1:8080/v1");
  await userEvent.type(screen.getByLabelText("Model name"), "some-model");
}

describe("first run", () => {
  it("sends you to Setup when the language model is not set up and blocks Continue", async () => {
    mockApi({ "/api/setup/status?verify=true": NO_KEY, "/api/home": EMPTY });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Before you start" })).toBeInTheDocument();
    expect(screen.getByText(/Missing · required/)).toBeInTheDocument();
    expect(screen.getByText(/optional for local servers/)).toBeInTheDocument();
    const cont = screen.getByRole("button", { name: "Continue" });
    expect(cont).toBeDisabled();
    expect(cont).toHaveAccessibleDescription("Set up the language model to continue.");
  });

  it("shows the server's message when the key is rejected, and keeps Continue off", async () => {
    mockApi({
      "/api/setup/status?verify=true": NO_KEY,
      "/api/setup/llm": () => new Response(JSON.stringify({ detail: { message: "The server rejected this API key.", field: "api_key" } }), { status: 400 }),
    });
    renderApp("/setup");
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Save and check" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The server rejected this API key.");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("enables Continue after valid settings are saved", async () => {
    mockApi({ "/api/setup/status?verify=true": NO_KEY, "/api/setup/llm": OK });
    renderApp("/setup");
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Save and check" }));
    expect(await screen.findByRole("link", { name: "Continue" })).toBeInTheDocument();
  });

  it("lists a missing optional tool with its fix and says text practice still works", async () => {
    mockApi({ "/api/setup/status?verify=true": NO_WHISPER });
    renderApp("/setup");
    expect(await screen.findByText("pip install faster-whisper")).toBeInTheDocument();
    expect(screen.getByText(/Not found · optional/)).toBeInTheDocument();
    expect(screen.getByText(/Text practice still works/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toBeInTheDocument();
  });
});

describe("empty library", () => {
  it("tells you the one next step: add a book", async () => {
    mockApi({ "/api/setup/status?verify=true": NO_WHISPER, "/api/home": EMPTY });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Add your first book" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a book" })).toHaveAttribute("href", "/library");
    await waitFor(() => expect(screen.getByText(/video feedback|Image and video upload are off/)).toBeInTheDocument());
  });
});

describe("home states", () => {
  it("offers Continue with the active skill and the review count", async () => {
    mockApi({
      "/api/setup/status?verify=true": OK,
      "/api/home": { state: "reviews_due", books: 1, active_skill: { id: 1, name: "Write a want and obstacle scene" }, reviews_due: 2 },
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Write a want and obstacle scene" })).toBeInTheDocument();
    expect(screen.getByText("2 questions to review first.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toBeInTheDocument();
  });

  it("offers New skill when nothing is active", async () => {
    mockApi({ "/api/setup/status?verify=true": OK, "/api/home": { state: "no_active_skill", books: 1, active_skill: null, reviews_due: 0 } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "New skill" })).toBeInTheDocument();
  });
});
