import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Passage, Source } from "./api";
import { CitationChip } from "./components/CitationChip";
import Library from "./pages/Library";
import SourcePage from "./pages/Source";

const src = (o: Partial<Source>): Source => ({
  id: 1, title: "[Book A]", author: "[Author]", kind: "single", pages: 312, status: "ready", stage: null, progress: 1, message: null, estimate_s: 60,
  triage: null, chunks: 120, files: 1, pages_without_text: [], skills: 0, pending_skills: 0, ...o,
});
const triage = (practicable: boolean) => ({ book_type: "practical", practicable, likely_skills: ["Write a want-and-obstacle scene"], reason: "Film theory, no exercises." });

function mock(handler: (url: string, init?: RequestInit) => unknown) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const r = handler(url, init);
    if (r instanceof Response) return r;
    return new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", f);
  return f;
}
const wrap = (ui: React.ReactNode, path = "/library") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
  </QueryClientProvider>,
);
afterEach(() => vi.unstubAllGlobals());

describe("Library", () => {
  it("shows a processing book with progress, stage and Cancel", async () => {
    const f = mock((u) => (u === "/api/library" ? { sources: [src({ status: "processing", stage: "embedding", progress: 0.5, message: "Indexing… 8 of 16 passages" })] } : { ok: true }));
    wrap(<Library />);
    expect(await screen.findByRole("progressbar", { name: "Processing [Book A]" })).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByText("Index · now")).toBeInTheDocument();
    expect(screen.getByText("Extract text · done")).toBeInTheDocument();
    expect(screen.getByText(/Indexing… 8 of 16/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(f).toHaveBeenCalledWith("/api/library/1/cancel", expect.objectContaining({ method: "POST" }));
  });

  it("explains triage for a ready book and for a reference-only book", async () => {
    mock(() => ({ sources: [src({ id: 1, triage: triage(true) }), src({ id: 2, title: "[Book D]", status: "reference_only", triage: triage(false) })] }));
    wrap(<Library />);
    const a = within(await screen.findByRole("listitem", { name: "[Book A]" }));
    expect(a.getByText("Ready")).toBeInTheDocument();
    expect(a.getByText(/Likely skills: Write a want-and-obstacle scene/)).toBeInTheDocument();
    const d = within(screen.getByRole("listitem", { name: "[Book D]" }));
    expect(d.getByText("Reference only")).toBeInTheDocument();
    expect(d.getByText(/Still searchable and citable in lessons/)).toBeInTheDocument();
  });

  it("flags a scanned book as Needs OCR with an alert and no Retry", async () => {
    mock(() => ({ sources: [src({ title: "notes.pdf", status: "needs_ocr", message: "No text found. This looks like a scanned book, so it can't be taught from yet.", chunks: 0 })] }));
    wrap(<Library />);
    expect(await screen.findByText("Needs OCR")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("scanned book");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("offers Retry after the model was unreachable", async () => {
    const f = mock((u) => (u === "/api/library" ? { sources: [src({ status: "error", message: "The language model could not be reached (down). Press Retry when the server is up." })] } : { ok: true }));
    wrap(<Library />);
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(f).toHaveBeenCalledWith("/api/library/1/retry", expect.objectContaining({ method: "POST" }));
  });

  it("uploads chosen PDFs and shows the duplicate message when the book is already there", async () => {
    const f = mock((u) => {
      if (u === "/api/library/upload") return new Response(JSON.stringify({ detail: { message: "“[Book A]” is already in your library.", field: "duplicate" } }), { status: 409 });
      return { sources: [] };
    });
    wrap(<Library />);
    const file = new File(["%PDF"], "book.pdf", { type: "application/pdf" });
    await userEvent.type(await screen.findByLabelText(/^Title/), "My Title");
    await userEvent.upload(screen.getByLabelText("Add book"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("already in your library. Nothing was added.");
    const call = f.mock.calls.find((c) => c[0] === "/api/library/upload")!;
    expect((call[1]!.body as FormData).getAll("files")).toHaveLength(1);
    expect((call[1]!.body as FormData).get("title")).toBe("My Title");
  });
});

describe("Source viewer", () => {
  const passage: Passage = {
    id: 5, source_id: 1, source_title: "[Book A]", author: "[Author]", label: "Ch. 3", title: "Want", page_start: 41, page_end: 43,
    citation: "[[Book A], ch. 3, pp. 41–43]", text: "[The cited passage.]", before: "[Text before.]", after: "[Text after.]", prev_id: null, next_id: 6,
  };
  const view = () => wrap(<Routes><Route path="/source/:chunkId" element={<SourcePage />} /></Routes>, "/source/5");

  it("shows the cited passage highlighted, with context and where it is from", async () => {
    mock(() => passage);
    view();
    expect(await screen.findByRole("article", { name: "Book passage" })).toBeInTheDocument();
    expect(screen.getByText("[The cited passage.]").tagName).toBe("MARK");
    expect(screen.getByText(/\[Text before\.\]/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "[Book A]" })).toBeInTheDocument();
    expect(screen.getByText("pp. 41–43", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous passage" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next passage" })).toBeEnabled();
  });

  it("says plainly when the passage is gone", async () => {
    mock(() => new Response(JSON.stringify({ detail: { message: "This passage no longer exists. The book may have been removed." } }), { status: 404 }));
    view();
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer exists");
  });
});

it("a citation chip is a real link to its passage", () => {
  wrap(<CitationChip chunkId={5} citation="[Book A, ch. 3, p. 41]" />);
  expect(screen.getByRole("link", { name: "[Book A, ch. 3, p. 41]" })).toHaveAttribute("href", "/source/5");
});
